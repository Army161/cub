"""Smart front-assistant routing layer (reply vs delegate)."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from cub.settings import Settings
from cub.store import TaskStore

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")

_ROUTER_DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["reply", "delegate"]},
        "reply": {"type": "string"},
        "delegate_prompt": {"type": "string"},
        "label": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["action"],
    "additionalProperties": True,
}

_ROUTER_SYSTEM_PROMPT = """You are the front assistant for a Telegram coding bot.
Your job is to decide whether to answer directly or delegate to background Claude CLI.

Return JSON only with this schema:
{
  "action": "reply" | "delegate",
  "reply": "string",
  "delegate_prompt": "string",
  "label": "short label",
  "reason": "brief reason"
}

Rules:
- Use action=reply when the user request can be answered conversationally without shell/file/tool execution.
- Use action=delegate when it likely requires coding work, shell commands, file edits, debugging, long-running tasks, or external operations.
- Keep reply concise and useful.
- If action=delegate, provide a concrete delegate_prompt for the worker.
- Output valid JSON only. No markdown, no backticks.
"""

_FAST_CLAUDE_CLI_SYSTEM_PROMPT = """You are a fast Telegram assistant.
You are running with tools disabled.

If the user asks for anything requiring shell commands, filesystem reads/writes,
code edits, debugging, builds, tests, deployments, or external actions, respond
exactly as:

NEEDS_TOOLS
<one-line summary of what should be done>

Never describe your own limitations or ask the user to do it manually.
If tools are needed, output only NEEDS_TOOLS format and nothing else.
For conversational, math, reasoning, and general questions, answer directly and concisely.
"""

_FAST_CLAUDE_CLI_READ_ONLY_SYSTEM_PROMPT = """You are a fast Telegram assistant.
You may use read-only inspection tools for quick lookups, but never write or edit files.

If the request requires shell commands, file writes/edits, test/build execution, or substantial implementation work,
respond exactly as:

NEEDS_TOOLS
<one-line summary of what should be done>

Keep responses concise. Prefer at most one short read operation before answering.
If work exceeds quick read-only lookup, output NEEDS_TOOLS format and nothing else.
"""

_TOOL_REFUSAL_PATTERNS = (
    re.compile(r"don't have.{0,30}tool", re.I),
    re.compile(r"don't have.{0,30}access", re.I),
    re.compile(r"can'?t.{0,20}(access|check|run|execute|read|write|browse)", re.I),
    re.compile(r"cannot.{0,20}(access|check|run|execute|read|write|browse)", re.I),
    re.compile(r"unable to.{0,20}(access|check|run|execute|read|write)", re.I),
    re.compile(r"lack.{0,30}abilit", re.I),
    re.compile(r"cannot.{0,30}create", re.I),
    re.compile(r"can'?t.{0,30}create", re.I),
    re.compile(r"do it manually", re.I),
    re.compile(r"on your machine", re.I),
    re.compile(r"provide.{0,30}all the code", re.I),
)

_PROGRESS_SYSTEM_PROMPT = """You rewrite technical stream updates for end users.
Return one concise progress update for Telegram.

Rules:
- Keep it to 1-2 short lines.
- Keep only useful status details.
- If approval is needed, explicitly say approval is required.
- Avoid raw JSON fields, IDs, duplicated text, and log noise.
- No markdown tables, no code fences.
"""

_FINAL_RESULT_SYSTEM_PROMPT = """You format a task completion update for Telegram users.
Return only Markdown text (no JSON).

Format:
- First line: clear completion status.
- Then a short "Summary:" section with bullet points.
- If relevant commands or outputs exist, include one fenced code block (prefer ```shell).
- Keep concise, practical, and easy to scan.
- Avoid repeating identical lines.
"""

_LOW_SIGNAL_ASSISTANT_PREFIXES = (
    "queued task ",
    "commands:",
    "usage: /",
    "reminder #",
    "progress updates muted",
    "progress updates unmuted",
    "access denied for this telegram user id.",
)


@dataclass(frozen=True)
class AssistantDecision:
    """Decision produced by front assistant router."""

    action: Literal["reply", "delegate"]
    reply: str | None = None
    delegate_prompt: str | None = None
    label: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ClaudeCLIResult:
    """Result from one claude CLI invocation."""

    returncode: int
    stdout_text: str
    stderr_text: str


class SmartAssistant:
    """Optional LLM router that keeps the main assistant smart and responsive."""

    def __init__(self, settings: Settings, store: TaskStore):
        self.settings = settings
        self.store = store
        self.provider = settings.front_assistant_provider
        self.enabled = self.provider != "none"
        self._client = httpx.AsyncClient(timeout=15)

    async def close(self) -> None:
        await self._client.aclose()

    async def decide(self, chat_id: int, user_text: str) -> AssistantDecision:
        """Return reply/delegate decision. Falls back to delegate on any failure."""
        if not self.enabled:
            return AssistantDecision(action="delegate", delegate_prompt=user_text)

        recent_chat, recent_tasks = self._load_context(chat_id)

        if self.provider == "claude_cli":
            return await self._decide_claude_cli(chat_id, user_text, recent_chat, recent_tasks)

        user_prompt = _build_router_user_prompt(recent_chat, recent_tasks, user_text)

        try:
            raw = await asyncio.wait_for(
                self._complete(
                    user_prompt,
                    system_prompt=_ROUTER_SYSTEM_PROMPT,
                    max_tokens=350,
                    temperature=0.2,
                    chat_id=chat_id,
                    use_persistent_session=True,
                    structured_schema=_ROUTER_DECISION_SCHEMA,
                ),
                timeout=self.settings.front_assistant_timeout_seconds,
            )
            decision = parse_assistant_decision(raw, user_text)
            if (
                self.provider == "claude_cli"
                and decision.action == "delegate"
                and decision.reason == "invalid_json"
                and raw.strip()
            ):
                return AssistantDecision(action="reply", reply=raw.strip(), reason="claude_cli_raw_reply")
            return decision
        except Exception:
            return AssistantDecision(action="delegate", delegate_prompt=user_text, reason="router_fallback")

    async def _decide_claude_cli(
        self,
        chat_id: int,
        user_text: str,
        recent_chat: list[dict[str, Any]],
        recent_tasks: list[dict[str, Any]],
    ) -> AssistantDecision:
        timeout = max(self.settings.front_assistant_timeout_seconds, 8.0)
        user_prompt = _build_fast_claude_cli_user_prompt(recent_chat, recent_tasks, user_text)
        system_prompt = (
            _FAST_CLAUDE_CLI_READ_ONLY_SYSTEM_PROMPT
            if self.settings.front_assistant_tool_mode == "read_only"
            else _FAST_CLAUDE_CLI_SYSTEM_PROMPT
        )
        try:
            raw = await asyncio.wait_for(
                self._complete(
                    user_prompt,
                    system_prompt=system_prompt,
                    max_tokens=300,
                    temperature=0.2,
                    chat_id=chat_id,
                    use_persistent_session=True,
                    structured_schema=None,
                ),
                timeout=timeout,
            )
        except Exception:
            return AssistantDecision(action="delegate", delegate_prompt=user_text, reason="router_fallback")

        text = (raw or "").strip()
        if not text:
            return AssistantDecision(action="delegate", delegate_prompt=user_text, reason="empty_reply")

        if _contains_needs_tools_token(text):
            summary = _extract_needs_tools_summary(text)
            return AssistantDecision(
                action="delegate",
                delegate_prompt=summary or user_text,
                label=summary,
                reason="needs_tools",
            )

        if _looks_like_tool_refusal(text):
            return AssistantDecision(action="delegate", delegate_prompt=user_text, reason="tool_refusal")

        return AssistantDecision(action="reply", reply=text, reason="claude_cli_fast_reply")

    def _load_context(self, chat_id: int) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
        context_limit = min(max(self.settings.front_assistant_context_messages, 10), 120)
        raw_chat = self.store.recent_chat_messages(chat_id, limit=context_limit)
        recent_chat = _prepare_recent_chat_for_router(raw_chat, max_messages=context_limit)
        recent_tasks = self.store.list_tasks(chat_id, limit=5)
        return recent_chat, recent_tasks

    async def format_progress(self, task_id: str, snippets: list[str]) -> str | None:
        """Use front assistant to rewrite progress snippets into a compact user update."""
        if not self.enabled:
            return None
        if not snippets:
            return None

        prompt = _build_progress_user_prompt(task_id, snippets)
        timeout = min(2.5, self.settings.front_assistant_timeout_seconds)

        try:
            raw = await asyncio.wait_for(
                self._complete(
                    prompt,
                    system_prompt=_PROGRESS_SYSTEM_PROMPT,
                    max_tokens=120,
                    temperature=0.1,
                    chat_id=None,
                    use_persistent_session=False,
                    structured_schema=None,
                ),
                timeout=timeout,
            )
        except Exception:
            return None

        text = _clean_progress_text(raw)
        return text or None

    async def format_task_result(
        self,
        task_id: str,
        status: str,
        exit_code: int | None,
        snippets: list[str],
        error: str | None,
    ) -> str | None:
        """Rewrite final task results into a polished Markdown summary."""
        if not self.enabled:
            return None

        prompt = _build_final_result_user_prompt(task_id, status, exit_code, snippets, error)
        timeout = min(5.0, self.settings.front_assistant_timeout_seconds + 1.5)

        try:
            raw = await asyncio.wait_for(
                self._complete(
                    prompt,
                    system_prompt=_FINAL_RESULT_SYSTEM_PROMPT,
                    max_tokens=420,
                    temperature=0.2,
                    chat_id=None,
                    use_persistent_session=False,
                    structured_schema=None,
                ),
                timeout=timeout,
            )
        except Exception:
            return None

        text = _clean_final_result_text(raw)
        return text or None

    async def _complete(
        self,
        user_prompt: str,
        *,
        system_prompt: str,
        max_tokens: int,
        temperature: float,
        chat_id: int | None,
        use_persistent_session: bool,
        structured_schema: dict[str, Any] | None,
    ) -> str:
        if self.provider == "anthropic":
            return await self._complete_anthropic(
                user_prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        if self.provider == "openrouter":
            return await self._complete_openrouter(
                user_prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        if self.provider == "claude_cli":
            return await self._complete_claude_cli(
                user_prompt,
                system_prompt=system_prompt,
                chat_id=chat_id,
                use_persistent_session=use_persistent_session,
                structured_schema=structured_schema,
            )
        raise ValueError(f"Unsupported provider: {self.provider}")

    async def _complete_anthropic(
        self,
        user_prompt: str,
        *,
        system_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        url = f"{self.settings.anthropic_base_url.rstrip('/')}/v1/messages"
        headers = {
            "x-api-key": self.settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.settings.front_assistant_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        response = await self._client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        chunks: list[str] = []
        for item in data.get("content", []):
            if isinstance(item, dict) and item.get("type") == "text":
                text = str(item.get("text", "")).strip()
                if text:
                    chunks.append(text)

        return "\n".join(chunks)

    async def _complete_openrouter(
        self,
        user_prompt: str,
        *,
        system_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        url = f"{self.settings.openrouter_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "content-type": "application/json",
        }
        payload = {
            "model": self.settings.front_assistant_model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        response = await self._client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return str(message.get("content") or "")

    async def _complete_claude_cli(
        self,
        user_prompt: str,
        *,
        system_prompt: str,
        chat_id: int | None,
        use_persistent_session: bool,
        structured_schema: dict[str, Any] | None,
    ) -> str:
        if use_persistent_session and chat_id is None:
            raise ValueError("chat_id is required for persistent session mode")

        output_format = "json" if structured_schema else "text"
        session_id = self.store.get_or_create_front_session_id(chat_id) if use_persistent_session else None

        if not use_persistent_session:
            result = await self._run_claude_cli(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                output_format=output_format,
                structured_schema=structured_schema,
                resume_session_id=None,
                session_id=None,
                persist_session=False,
            )
            return _coerce_claude_cli_output(result, structured_schema)

        assert session_id is not None
        resume_result = await self._run_claude_cli(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            output_format=output_format,
            structured_schema=structured_schema,
            resume_session_id=session_id,
            session_id=None,
            persist_session=True,
        )
        if resume_result.returncode == 0:
            return _coerce_claude_cli_output(resume_result, structured_schema)

        create_result = await self._run_claude_cli(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            output_format=output_format,
            structured_schema=structured_schema,
            resume_session_id=None,
            session_id=session_id,
            persist_session=True,
        )
        if create_result.returncode == 0:
            return _coerce_claude_cli_output(create_result, structured_schema)

        reset_id = self.store.reset_front_session_id(chat_id)
        reset_result = await self._run_claude_cli(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            output_format=output_format,
            structured_schema=structured_schema,
            resume_session_id=None,
            session_id=reset_id,
            persist_session=True,
        )
        if reset_result.returncode == 0:
            return _coerce_claude_cli_output(reset_result, structured_schema)

        detail = (
            reset_result.stderr_text
            or create_result.stderr_text
            or resume_result.stderr_text
            or reset_result.stdout_text
            or create_result.stdout_text
            or resume_result.stdout_text
            or f"exit code {reset_result.returncode}"
        )
        raise RuntimeError(f"claude_cli failed: {detail}")

    async def _run_claude_cli(
        self,
        *,
        user_prompt: str,
        system_prompt: str,
        output_format: Literal["text", "json"],
        structured_schema: dict[str, Any] | None,
        resume_session_id: str | None,
        session_id: str | None,
        persist_session: bool,
    ) -> "ClaudeCLIResult":
        command = _build_claude_cli_command(
            claude_command=self.settings.front_claude_command,
            claude_args=self.settings.front_claude_args,
            model=self.settings.front_assistant_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_format=output_format,
            json_schema=structured_schema,
            resume_session_id=resume_session_id,
            session_id=session_id,
            persist_session=persist_session,
            tool_mode=self.settings.front_assistant_tool_mode,
            max_turns=self.settings.front_assistant_max_turns,
        )

        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(self.settings.workspace_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )

        try:
            stdout, stderr = await process.communicate()
        except asyncio.CancelledError:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise

        return ClaudeCLIResult(
            returncode=process.returncode or 0,
            stdout_text=stdout.decode("utf-8", errors="replace").strip(),
            stderr_text=stderr.decode("utf-8", errors="replace").strip(),
        )


def parse_assistant_decision(raw_text: str, original_message: str) -> AssistantDecision:
    """Parse model text into a normalized decision."""
    payload = _parse_json_payload(raw_text)
    if not payload:
        return AssistantDecision(action="delegate", delegate_prompt=original_message, reason="invalid_json")

    action = str(payload.get("action", "")).strip().lower()
    if action not in {"reply", "delegate"}:
        return AssistantDecision(action="delegate", delegate_prompt=original_message, reason="invalid_action")

    reply = _maybe_text(payload.get("reply"))
    delegate_prompt = _maybe_text(payload.get("delegate_prompt"))
    label = _maybe_text(payload.get("label"))
    reason = _maybe_text(payload.get("reason"))

    if action == "reply":
        if not reply:
            return AssistantDecision(action="delegate", delegate_prompt=original_message, reason="empty_reply")
        return AssistantDecision(action="reply", reply=reply, reason=reason)

    return AssistantDecision(
        action="delegate",
        delegate_prompt=delegate_prompt or original_message,
        label=label,
        reason=reason,
    )


def _parse_json_payload(raw_text: str) -> dict[str, Any] | None:
    text = (raw_text or "").strip()
    if not text:
        return None

    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    match = _JSON_BLOCK_RE.search(text)
    if not match:
        return None

    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _build_router_user_prompt(
    recent_chat: list[dict[str, Any]],
    recent_tasks: list[dict[str, Any]],
    user_message: str,
) -> str:
    lines = ["Recent conversation in this chat (oldest -> newest):"]
    if not recent_chat:
        lines.append("- (none)")
    else:
        for item in recent_chat:
            role = item.get("role", "user")
            content = str(item.get("content") or "").strip()
            if content:
                lines.append(f"- {role}: {content}")

    lines.append("")
    lines.append(f"Current user message:\n{user_message}")
    lines.append("")
    lines.append("Recent tasks in this chat:")
    if not recent_tasks:
        lines.append("- (none)")
    else:
        for task in recent_tasks:
            session = str(task.get("claude_session_id") or "").strip()
            session_part = f" | session={session}" if session else ""
            lines.append(
                f"- {task['id']} | {task.get('status')} | {task.get('label') or task['id']}{session_part}"
            )

    lines.append("")
    lines.append("Decide whether to reply directly or delegate.")
    return "\n".join(lines)


def _build_fast_claude_cli_user_prompt(
    recent_chat: list[dict[str, Any]],
    recent_tasks: list[dict[str, Any]],
    user_message: str,
) -> str:
    lines = ["Recent conversation in this chat (oldest -> newest):"]
    if not recent_chat:
        lines.append("- (none)")
    else:
        for item in recent_chat:
            role = item.get("role", "user")
            content = str(item.get("content") or "").strip()
            if content:
                lines.append(f"- {role}: {content}")

    lines.append("")
    lines.append("Recent tasks in this chat:")
    if not recent_tasks:
        lines.append("- (none)")
    else:
        for task in recent_tasks:
            status = str(task.get("status") or "unknown")
            label = str(task.get("label") or task["id"])
            exit_code = task.get("exit_code")
            session = str(task.get("claude_session_id") or "").strip()
            session_part = f" | session={session}" if session else ""
            if exit_code is None:
                lines.append(f"- {task['id']} | {status} | {label}{session_part}")
            else:
                lines.append(f"- {task['id']} | {status} | exit={exit_code} | {label}{session_part}")

    lines.append("")
    lines.append(f"Current user message:\n{user_message}")
    lines.append("")
    lines.append("Use the context above.")
    lines.append(
        "If the request can be answered from context and reasoning alone, reply directly."
    )
    lines.append(
        "If shell/filesystem/code edits/tests or any external actions are needed, respond using NEEDS_TOOLS format."
    )
    return "\n".join(lines)


def _build_progress_user_prompt(task_id: str, snippets: list[str]) -> str:
    lines = [f"Task id: {task_id}", "Raw progress snippets:"]
    for item in snippets[-6:]:
        text = item.strip()
        if text:
            lines.append(f"- {text}")
    lines.append("")
    lines.append("Rewrite into one concise user-facing progress update.")
    return "\n".join(lines)


def _build_final_result_user_prompt(
    task_id: str,
    status: str,
    exit_code: int | None,
    snippets: list[str],
    error: str | None,
) -> str:
    lines = [
        f"Task id: {task_id}",
        f"Status: {status}",
        f"Exit code: {exit_code}",
    ]
    if error:
        lines.append(f"Error: {error}")
    lines.append("")
    lines.append("Recent snippets:")
    if snippets:
        for item in snippets[-10:]:
            lines.append(f"- {item}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("Produce a concise Telegram-ready Markdown completion message.")
    return "\n".join(lines)


def _prepare_recent_chat_for_router(
    recent_chat: list[dict[str, Any]],
    *,
    max_messages: int,
) -> list[dict[str, str]]:
    prepared: list[dict[str, str]] = []
    for item in recent_chat:
        role = str(item.get("role") or "user").strip().lower()
        if role not in {"user", "assistant"}:
            role = "user"

        content = str(item.get("content") or "").strip()
        if not content:
            continue

        if role == "assistant" and _is_low_signal_assistant_message(content):
            continue

        compact = _compact_message_for_router(content)
        if not compact:
            continue

        prepared.append({"role": role, "content": compact})

    if len(prepared) > max_messages:
        prepared = prepared[-max_messages:]

    return prepared


def _is_low_signal_assistant_message(text: str) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return True

    if lowered.startswith("task ") and " in progress:" in lowered:
        return True

    return any(lowered.startswith(prefix) for prefix in _LOW_SIGNAL_ASSISTANT_PREFIXES)


def _compact_message_for_router(text: str, *, max_chars: int = 480) -> str:
    lines = _deduped_non_empty_lines(text)
    if not lines:
        return ""

    lowered = text.lower()
    if lowered.startswith("task ") and "recent output:" in lowered:
        header = lines[0]
        exit_line = ""
        for line in lines[1:]:
            if line.lower().startswith("exit code:"):
                exit_line = line
                break

        output_lines: list[str] = []
        seen: set[str] = set()
        for line in lines:
            if not line.startswith("- "):
                continue
            value = line[2:].strip()
            if not value or value in seen:
                continue
            seen.add(value)
            output_lines.append(value)

        parts = [header]
        if exit_line:
            parts.append(exit_line)
        if output_lines:
            parts.append("Output: " + " | ".join(output_lines[-4:]))

        compact = " ".join(parts).strip()
    else:
        compact = " | ".join(lines)

    compact = " ".join(compact.split())
    if len(compact) > max_chars:
        return compact[: max_chars - 3] + "..."
    return compact


def _deduped_non_empty_lines(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out


def _clean_progress_text(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""

    if text.startswith("```"):
        text = text.strip("`").strip()
        text = text.replace("text\n", "", 1).strip()

    lines = [line.strip("- ").strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""

    compact = " ".join(" ".join(lines).split())
    return compact[:240]


def _clean_final_result_text(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""

    if text.startswith("```"):
        stripped = text.strip("`").strip()
        if stripped.startswith("markdown"):
            text = stripped[len("markdown") :].strip()

    return text.strip()


def _extract_needs_tools_summary(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    if lines[0].upper() != "NEEDS_TOOLS":
        return None
    if len(lines) < 2:
        return None
    return lines[1]


def _contains_needs_tools_token(text: str) -> bool:
    return bool(re.search(r"\bNEEDS_TOOLS\b", text, flags=re.IGNORECASE))


def _looks_like_tool_refusal(text: str) -> bool:
    return any(pattern.search(text) for pattern in _TOOL_REFUSAL_PATTERNS)


def _build_claude_cli_command(
    *,
    claude_command: str,
    claude_args: tuple[str, ...],
    model: str,
    system_prompt: str,
    user_prompt: str,
    output_format: Literal["text", "json"],
    json_schema: dict[str, Any] | None,
    resume_session_id: str | None,
    session_id: str | None,
    persist_session: bool,
    tool_mode: Literal["none", "read_only"],
    max_turns: int,
) -> list[str]:
    cmd = [claude_command, *claude_args, "--print", "--output-format", output_format]

    if model:
        cmd.extend(["--model", model])

    cmd.extend(["--system-prompt", system_prompt])

    if not _has_cli_flag(claude_args, "--max-turns"):
        cmd.extend(["--max-turns", str(max_turns)])

    # Front assistant defaults to tool-free mode.
    # In read-only mode we allow only Read for quick lookups.
    if tool_mode == "none":
        if not _has_cli_flag(claude_args, "--tools") and not _has_cli_flag(claude_args, "--allowed-tools"):
            cmd.extend(["--tools", ""])
    elif tool_mode == "read_only":
        if not _has_cli_flag(claude_args, "--allowed-tools") and not _has_cli_flag(claude_args, "--tools"):
            cmd.extend(["--allowed-tools", "Read"])
    else:
        raise ValueError(f"unsupported front assistant tool mode: {tool_mode}")

    if output_format == "json" and json_schema is not None:
        cmd.extend(["--json-schema", json.dumps(json_schema, separators=(",", ":"))])

    if persist_session:
        if resume_session_id:
            cmd.extend(["--resume", resume_session_id])
        elif session_id:
            cmd.extend(["--session-id", session_id])
    else:
        cmd.append("--no-session-persistence")

    cmd.append(user_prompt)
    return cmd


def _coerce_claude_cli_output(result: ClaudeCLIResult, schema: dict[str, Any] | None) -> str:
    if result.returncode != 0:
        detail = result.stderr_text or result.stdout_text or f"exit code {result.returncode}"
        raise RuntimeError(f"claude_cli failed: {detail}")

    if schema is None:
        return result.stdout_text

    payload = _parse_json_payload(result.stdout_text)
    if not payload:
        return result.stdout_text

    structured = payload.get("structured_output")
    if isinstance(structured, dict):
        return json.dumps(structured, separators=(",", ":"))

    if isinstance(payload, dict):
        return json.dumps(payload, separators=(",", ":"))

    return result.stdout_text


def _maybe_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _has_cli_flag(args: tuple[str, ...], flag: str) -> bool:
    token = flag.strip()
    if not token:
        return False
    for arg in args:
        if arg == token or arg.startswith(f"{token}="):
            return True
    return False
