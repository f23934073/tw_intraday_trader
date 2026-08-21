"""Check the dashboard ES-module entrypoint and every static module."""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_HTML = REPOSITORY_ROOT / "dashboard" / "static" / "index.html"
DASHBOARD_STATIC = DASHBOARD_HTML.parent


def module_entrypoint(html: str) -> Path:
    """Resolve the sole same-origin module entrypoint from dashboard markup."""

    entries = re.findall(r'<script\s+type="module"\s+src="([^"]+)"\s*></script>', html)
    if len(entries) != 1:
        raise ValueError("dashboard must contain exactly one module entrypoint")
    entry = entries[0]
    if not entry.startswith("/static/"):
        raise ValueError("dashboard module entrypoint must be served from /static/")
    entry_path = entry.partition("?")[0]
    path = (DASHBOARD_STATIC / entry_path.removeprefix("/static/")).resolve()
    if DASHBOARD_STATIC.resolve() not in path.parents or not path.is_file():
        raise ValueError("dashboard module entrypoint is missing")
    return path


def main() -> int:
    node = shutil.which("node")
    if node is None:
        print("Node.js is required to validate dashboard JavaScript.", file=sys.stderr)
        return 1

    try:
        entrypoint = module_entrypoint(DASHBOARD_HTML.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"Unable to read dashboard JavaScript: {exc}", file=sys.stderr)
        return 1

    modules = sorted(entrypoint.parent.rglob("*.js"))
    if entrypoint not in modules:
        modules.append(entrypoint)
    for module in modules:
        result = subprocess.run([node, "--check", str(module)], check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
