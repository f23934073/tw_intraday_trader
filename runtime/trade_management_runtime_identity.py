"""Pure source-content identity for Trade Management Shadow runtimes."""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Iterable
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_IDENTITY_PATHS = (
    "config",
    "market_data",
    "runtime",
    "trading",
    "scripts/preflight_trade_management_shadow.py",
    "scripts/run_trade_management_shadow_c1.py",
    "scripts/prepare_trade_management_shadow_inputs.py",
    "scripts/review_trade_management_shadow_inputs.py",
    "scripts/promote_trade_management_shadow_inputs.py",
    "pyproject.toml",
    "uv.lock",
)


def git_head(project_root: Path = PROJECT_ROOT) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def runtime_code_identity(
    *,
    project_root: Path = PROJECT_ROOT,
    identity_paths: Iterable[str] = RUNTIME_IDENTITY_PATHS,
    git_head_value: str | None = None,
) -> str:
    """Identify the exact runtime source tree, including uncommitted code."""

    digest = hashlib.sha256()
    files: list[Path] = []
    for item in identity_paths:
        path = project_root / item
        if path.is_dir():
            files.extend(
                candidate
                for candidate in path.rglob("*.py")
                if "__pycache__" not in candidate.parts
            )
        elif path.is_file():
            files.append(path)
    for path in sorted(
        set(files),
        key=lambda item: item.relative_to(project_root).as_posix(),
    ):
        relative = path.relative_to(project_root).as_posix().encode()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    head = git_head_value if git_head_value is not None else git_head(project_root)
    return f"git:{head}:source-sha256:{digest.hexdigest()}"
