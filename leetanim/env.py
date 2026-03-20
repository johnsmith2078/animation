from __future__ import annotations

from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback is exercised only when dependency is absent.
    def load_dotenv(*_args, **_kwargs) -> bool:
        return False


def load_project_env(project_root: Path | None = None) -> Path:
    root = project_root.resolve() if project_root else Path(__file__).resolve().parent.parent
    env_path = root / ".env"
    load_dotenv(env_path, override=False)
    return env_path
