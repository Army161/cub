"""CLI helper to reset local Cub runtime state."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path
from typing import Sequence

from cub.dotenv import load_dotenv

_DEFAULT_CUB_HOME = "~/.cub"
_DEFAULT_SUBDIRS = ("state", "mind", "work")


def resolve_cub_home(explicit_home: str | None = None) -> Path:
    """Resolve target Cub home from argument or env."""
    raw = explicit_home if explicit_home is not None else os.getenv("CUB_HOME", _DEFAULT_CUB_HOME)
    return Path(raw).expanduser().resolve()


def reset_cub_home(home: Path, *, dry_run: bool = False) -> Path:
    """Delete and recreate standard Cub local state tree."""
    target = home.expanduser().resolve()
    _validate_reset_target(target)

    if target.exists():
        if not dry_run:
            if not target.is_dir():
                raise ValueError(f"refusing to reset non-directory target: {target}")
            shutil.rmtree(target)

    if not dry_run:
        target.mkdir(parents=True, exist_ok=True)
        for name in _DEFAULT_SUBDIRS:
            (target / name).mkdir(parents=True, exist_ok=True)

    return target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reset local Cub state directory")
    parser.add_argument(
        "--home",
        type=str,
        default=None,
        help="Cub home directory to reset (default: CUB_HOME or ~/.cub)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show target only; do not modify files",
    )
    return parser


def _confirm(target: Path) -> bool:
    prompt = f"Reset Cub state at {target}? This deletes local DB/history/work files. [y/N] "
    try:
        answer = input(prompt).strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}


def _validate_reset_target(target: Path) -> None:
    resolved = target.expanduser().resolve()
    home = Path.home().resolve()
    unsafe_targets = {
        Path("/").resolve(),
        home,
        home.parent.resolve(),
        Path("/tmp").resolve(),
        Path("/var/tmp").resolve(),
    }
    if resolved in unsafe_targets:
        raise ValueError(f"refusing to reset unsafe target: {resolved}")
    if len(resolved.parts) <= 2:
        raise ValueError(f"refusing to reset broad target: {resolved}")


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    target = resolve_cub_home(args.home)
    if args.dry_run:
        print(f"Would reset Cub state at: {target}")
        return 0

    if not args.yes and not _confirm(target):
        print("Aborted.")
        return 1

    try:
        reset_cub_home(target, dry_run=False)
    except ValueError as exc:
        print(f"Reset failed: {exc}")
        return 2
    print(f"Reset complete: {target}")
    print(f"Recreated: {target / 'state'}, {target / 'mind'}, {target / 'work'}")
    return 0


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
