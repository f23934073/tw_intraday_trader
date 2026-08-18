"""Check that the dashboard's inline JavaScript is syntactically valid."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_HTML = REPOSITORY_ROOT / "dashboard" / "static" / "index.html"


def extract_inline_script(html: str) -> str:
    """Return the sole inline script from the dashboard HTML."""

    start_tag = "<script>"
    end_tag = "</script>"
    start = html.find(start_tag)
    end = html.find(end_tag, start + len(start_tag))
    if start == -1 or end == -1:
        raise ValueError("dashboard must contain one inline <script> block")
    if html.find(start_tag, start + len(start_tag)) != -1:
        raise ValueError("dashboard must contain exactly one inline <script> block")
    return html[start + len(start_tag) : end]


def main() -> int:
    node = shutil.which("node")
    if node is None:
        print("Node.js is required to validate dashboard JavaScript.", file=sys.stderr)
        return 1

    try:
        javascript = extract_inline_script(DASHBOARD_HTML.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"Unable to read dashboard JavaScript: {exc}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as directory:
        script_path = Path(directory) / "dashboard-inline.js"
        script_path.write_text(javascript, encoding="utf-8")
        result = subprocess.run([node, "--check", str(script_path)], check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
