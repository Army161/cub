from pathlib import Path

import pytest

from cub.state_reset import reset_cub_home, resolve_cub_home


def test_resolve_cub_home_uses_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CUB_HOME", str(tmp_path / "my-cub-home"))
    resolved = resolve_cub_home()
    assert resolved == (tmp_path / "my-cub-home").resolve()


def test_resolve_cub_home_explicit_overrides_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CUB_HOME", str(tmp_path / "from-env"))
    explicit = str(tmp_path / "from-arg")
    resolved = resolve_cub_home(explicit)
    assert resolved == (tmp_path / "from-arg").resolve()


def test_reset_cub_home_recreates_default_subdirs(tmp_path: Path) -> None:
    home = tmp_path / "cub-home"
    (home / "state").mkdir(parents=True)
    (home / "state" / "assistant.db").write_text("old-db", encoding="utf-8")
    (home / "work" / "chat-app").mkdir(parents=True)
    (home / "work" / "chat-app" / "frontend").mkdir(parents=True)
    (home / "work" / "chat-app" / "frontend" / "tsconfig.json").write_text(
        '{"compilerOptions":{}}',
        encoding="utf-8",
    )

    reset_cub_home(home)

    assert home.exists()
    assert (home / "state").is_dir()
    assert (home / "mind").is_dir()
    assert (home / "work").is_dir()
    assert not (home / "state" / "assistant.db").exists()
    assert not (home / "work" / "chat-app").exists()


def test_reset_cub_home_dry_run_does_not_delete(tmp_path: Path) -> None:
    home = tmp_path / "cub-home"
    (home / "state").mkdir(parents=True)
    marker = home / "state" / "assistant.db"
    marker.write_text("keep", encoding="utf-8")

    reset_cub_home(home, dry_run=True)

    assert marker.exists()


def test_reset_cub_home_rejects_unsafe_targets() -> None:
    with pytest.raises(ValueError, match="unsafe target"):
        reset_cub_home(Path("/"), dry_run=True)


def test_reset_cub_home_rejects_home_directory() -> None:
    with pytest.raises(ValueError, match="unsafe target"):
        reset_cub_home(Path.home(), dry_run=True)


def test_reset_cub_home_rejects_broad_top_level_target() -> None:
    anchor = Path.home().anchor
    broad = Path(anchor) / "opt"
    with pytest.raises(ValueError, match="broad target"):
        reset_cub_home(broad, dry_run=True)


def test_reset_cub_home_rejects_file_target(tmp_path: Path) -> None:
    target_file = tmp_path / "not-a-dir"
    target_file.write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match="non-directory"):
        reset_cub_home(target_file)
