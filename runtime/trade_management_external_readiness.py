"""Owner-only provisioning for the uninstalled external Shadow runner."""

from __future__ import annotations

import json
import os
import plistlib
import stat
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values


ENVIRONMENT_KEYS = (
    "SHIOAJI_API_KEY",
    "SJ_API_KEY",
    "SHIOAJI_SECRET",
    "SJ_SECRET_KEY",
    "SJ_SEC_KEY",
    "LOCAL_PAPER_DATABASE_URL",
    "TRADE_MANAGEMENT_SHADOW_DATABASE_URL",
    "SJ_SIMULATION",
)
API_KEY_ALIASES = frozenset({"SHIOAJI_API_KEY", "SJ_API_KEY"})
SECRET_ALIASES = frozenset(
    {"SHIOAJI_SECRET", "SJ_SECRET_KEY", "SJ_SEC_KEY"}
)
SANDBOX_TEMPLATE = "trade_management_shadow_external.sb.template"
SANDBOX_RENDERED = "trade_management_shadow_external.sb"
PLIST_TEMPLATE = "com.stevehuang.trade-management-shadow.plist.template"
PLIST_RENDERED = "com.stevehuang.trade-management-shadow.plist"


class ReadinessBlocked(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def provision_owner_only_environment(
    *,
    source: Path,
    target: Path,
) -> dict[str, object]:
    """Filter an existing dotenv file without exposing values in the result."""

    _require_absolute_regular_file(source)
    if not target.is_absolute():
        raise ReadinessBlocked("ENVIRONMENT_TARGET_MUST_BE_ABSOLUTE")
    _reject_symlink_components(target.parent, allow_missing=True)
    _ensure_owner_only_directory(target.parent)
    if target.exists() or target.is_symlink():
        raise ReadinessBlocked("ENVIRONMENT_TARGET_ALREADY_EXISTS")

    parsed = dotenv_values(source, interpolate=False)
    values = {
        key: str(value)
        for key, value in parsed.items()
        if key in ENVIRONMENT_KEYS and value is not None and str(value).strip()
    }
    _validate_environment(values)
    values["SJ_SIMULATION"] = "true"
    content = "".join(
        f"{key}={json.dumps(values[key], ensure_ascii=False)}\n"
        for key in ENVIRONMENT_KEYS
        if key in values
    ).encode("utf-8")
    descriptor = os.open(
        target,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        observed = os.fstat(descriptor)
        if (
            observed.st_uid != os.getuid()
            or stat.S_IMODE(observed.st_mode) != 0o600
        ):
            raise ReadinessBlocked("OWNER_ONLY_FILE_MODE_INVALID")
        _write_all(descriptor, content)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(target.parent)
    return {
        "target": str(target),
        "mode": "0600",
        "keys": [key for key in ENVIRONMENT_KEYS if key in values],
        "provider_api_alias_count": len(API_KEY_ALIASES & set(values)),
        "provider_secret_alias_count": len(SECRET_ALIASES & set(values)),
        "dsn_separation_verified": True,
        "provider_simulation_forced": True,
        "values_disclosed": False,
    }


def render_disabled_deployment_candidates(
    *,
    project_root: Path,
    environment_file: Path,
    artifact_root: Path,
    records_root: Path,
    ownership_lock_root: Path,
    tmp_root: Path,
) -> dict[str, object]:
    """Render disabled, deny-network deployment candidates with exact paths."""

    for path in (
        project_root,
        environment_file,
        artifact_root,
        records_root,
        ownership_lock_root,
        tmp_root,
    ):
        if not path.is_absolute():
            raise ReadinessBlocked("DEPLOYMENT_PATH_MUST_BE_ABSOLUTE")
        _require_sandbox_literal_safe(path)
    _require_absolute_directory(project_root)
    _require_owner_only_file(environment_file)
    _require_disjoint_runtime_paths(
        project_root=project_root,
        environment_file=environment_file,
        runtime_roots=(artifact_root, records_root, ownership_lock_root, tmp_root),
    )
    for root in (artifact_root, records_root, ownership_lock_root, tmp_root):
        _ensure_owner_only_directory(root)

    deployment_root = project_root / "architecture/deployment"
    sandbox_template = deployment_root / SANDBOX_TEMPLATE
    plist_template = deployment_root / PLIST_TEMPLATE
    _require_absolute_regular_file(sandbox_template)
    _require_absolute_regular_file(plist_template)
    python_executable = project_root / ".venv/bin/python"
    _require_absolute_regular_file(python_executable, allow_final_symlink=True)
    resolved_python = python_executable.resolve()
    resolved_python_runtime_root = resolved_python.parent.parent
    _require_absolute_regular_file(resolved_python)
    _require_sandbox_literal_safe(resolved_python)
    _require_sandbox_literal_safe(resolved_python_runtime_root)

    replacements = {
        "/ABSOLUTE/PINNED_CHECKOUT": str(project_root),
        "/ABSOLUTE/RESOLVED/PYTHON_RUNTIME_ROOT": str(
            resolved_python_runtime_root
        ),
        "/ABSOLUTE/RESOLVED/PYTHON": str(resolved_python),
        "/ABSOLUTE/OWNER_ONLY_SECRETS/trade_management_shadow.env": str(
            environment_file
        ),
        "/ABSOLUTE/OWNER_ONLY_CONFIG/trade_management_shadow_external_execution_approval.json": str(
            environment_file.parent
            / "trade_management_shadow_external_execution_approval.json"
        ),
        "/ABSOLUTE/OWNER_ONLY_RUNTIME/artifacts": str(artifact_root),
        "/ABSOLUTE/OWNER_ONLY_RUNTIME/records": str(records_root),
        "/ABSOLUTE/OWNER_ONLY_RUNTIME/locks": str(ownership_lock_root),
        "/ABSOLUTE/OWNER_ONLY_RUNTIME/tmp": str(tmp_root),
    }
    sandbox_text = _render_text(
        sandbox_template.read_text(encoding="utf-8"),
        replacements,
    ).replace(
        ";; TEMPLATE ONLY — NOT APPROVED, NOT INSTALLED, NETWORK INTENTIONALLY DENIED.",
        ";; RENDERED CANDIDATE — NOT APPROVED, NOT INSTALLED, NETWORK INTENTIONALLY DENIED.",
    )
    plist_text = _render_text(
        plist_template.read_text(encoding="utf-8"),
        replacements,
    ).replace(
        "<!-- TEMPLATE ONLY: NOT APPROVED, NOT INSTALLED, DISABLED. -->",
        "<!-- RENDERED CANDIDATE: NOT APPROVED, NOT INSTALLED, DISABLED. -->",
    )
    parsed_plist = plistlib.loads(plist_text.encode("utf-8"))
    expected_arguments = [
        "/usr/bin/sandbox-exec",
        "-f",
        str(deployment_root / SANDBOX_RENDERED),
        str(python_executable),
        str(project_root / "scripts/run_trade_management_shadow_external_supervisor.py"),
        "--approval-spec",
        str(
            environment_file.parent
            / "trade_management_shadow_external_execution_approval.json"
        ),
    ]
    if parsed_plist.get("Disabled") is not True:
        raise ReadinessBlocked("RENDERED_PLIST_MUST_REMAIN_DISABLED")
    if parsed_plist.get("ProgramArguments") != expected_arguments:
        raise ReadinessBlocked("RENDERED_PLIST_ARGUMENTS_INVALID")
    if parsed_plist.get("EnvironmentVariables", {}).get("TMPDIR") != str(tmp_root):
        raise ReadinessBlocked("RENDERED_PLIST_TMPDIR_INVALID")
    if "(deny network*)" not in sandbox_text:
        raise ReadinessBlocked("RENDERED_SANDBOX_MUST_DENY_NETWORK")

    sandbox_output = deployment_root / SANDBOX_RENDERED
    plist_output = deployment_root / PLIST_RENDERED
    _write_text_exclusive(sandbox_output, sandbox_text, mode=0o644)
    _write_text_exclusive(plist_output, plist_text, mode=0o644)
    return {
        "sandbox_profile": str(sandbox_output),
        "launchd_plist": str(plist_output),
        "disabled": True,
        "installed": False,
        "network_policy": "DENY_ALL_PENDING_REVIEW",
        "execution_authority": False,
        "execution_enabled": False,
        "evidence_only": True,
        "production_shadow_gate": "NOT_PASSED",
    }


def _validate_environment(values: Mapping[str, str]) -> None:
    api_aliases = API_KEY_ALIASES & set(values)
    secret_aliases = SECRET_ALIASES & set(values)
    if len(api_aliases) != 1 or len(secret_aliases) != 1:
        raise ReadinessBlocked("PROVIDER_CREDENTIAL_ALIAS_SET_INVALID")
    fill_dsn = values.get("LOCAL_PAPER_DATABASE_URL", "").strip()
    shadow_dsn = values.get("TRADE_MANAGEMENT_SHADOW_DATABASE_URL", "").strip()
    if not fill_dsn or not shadow_dsn:
        raise ReadinessBlocked("LOCAL_PAPER_AND_SHADOW_DSNS_ARE_REQUIRED")
    if fill_dsn == shadow_dsn:
        raise ReadinessBlocked("SHADOW_DSN_MUST_BE_DEDICATED")
    if values.get("SJ_SIMULATION", "true").lower() != "true":
        raise ReadinessBlocked("PROVIDER_SIMULATION_MUST_BE_TRUE")
    if any(
        "\n" in value or "\r" in value or "\x00" in value
        for value in values.values()
    ):
        raise ReadinessBlocked("ENVIRONMENT_VALUE_CONTAINS_CONTROL_CHARACTER")


def _render_text(template: str, replacements: Mapping[str, str]) -> str:
    rendered = template
    for placeholder, value in sorted(
        replacements.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        rendered = rendered.replace(placeholder, value)
    if "/ABSOLUTE/" in rendered:
        raise ReadinessBlocked("DEPLOYMENT_TEMPLATE_PLACEHOLDER_REMAINS")
    return rendered


def _require_sandbox_literal_safe(path: Path) -> None:
    value = str(path)
    if any(character in value for character in ('"', "\\", "\r", "\n", "\x00")):
        raise ReadinessBlocked("DEPLOYMENT_PATH_UNSAFE_FOR_SANDBOX")


def _write_text_exclusive(path: Path, value: str, *, mode: int) -> None:
    if path.exists() or path.is_symlink():
        raise ReadinessBlocked("RENDERED_DEPLOYMENT_TARGET_ALREADY_EXISTS")
    descriptor = os.open(
        path,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
        mode,
    )
    try:
        _write_all(descriptor, value.encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _require_disjoint_runtime_paths(
    *,
    project_root: Path,
    environment_file: Path,
    runtime_roots: tuple[Path, ...],
) -> None:
    for root in runtime_roots:
        if root.is_relative_to(project_root):
            raise ReadinessBlocked("RUNTIME_ROOT_INSIDE_PROJECT")
    for index, left in enumerate(runtime_roots):
        for right in runtime_roots[index + 1 :]:
            if left.is_relative_to(right) or right.is_relative_to(left):
                raise ReadinessBlocked("RUNTIME_ROOTS_OVERLAP")
    if environment_file.is_relative_to(project_root) or any(
        environment_file.is_relative_to(root) for root in runtime_roots
    ):
        raise ReadinessBlocked("ENVIRONMENT_FILE_INSIDE_WRITABLE_ROOT")


def _ensure_owner_only_directory(path: Path) -> None:
    if not path.is_absolute():
        raise ReadinessBlocked("ABSOLUTE_PATH_REQUIRED")
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        if cursor.is_symlink():
            raise ReadinessBlocked("SYMLINK_PATH_REJECTED")
        missing.append(cursor)
        parent = cursor.parent
        if parent == cursor:
            raise ReadinessBlocked("OWNER_ONLY_DIRECTORY_INVALID")
        cursor = parent
    _reject_symlink_components(cursor, allow_missing=False)
    if cursor.is_symlink() or not cursor.is_dir():
        raise ReadinessBlocked("OWNER_ONLY_DIRECTORY_INVALID")
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
        observed = directory.stat()
        if (
            observed.st_uid != os.getuid()
            or stat.S_IMODE(observed.st_mode) != 0o700
        ):
            raise ReadinessBlocked("OWNER_ONLY_DIRECTORY_MODE_INVALID")
    if path.is_symlink() or not path.is_dir():
        raise ReadinessBlocked("OWNER_ONLY_DIRECTORY_INVALID")
    observed = path.stat()
    if observed.st_uid != os.getuid() or stat.S_IMODE(observed.st_mode) != 0o700:
        raise ReadinessBlocked("OWNER_ONLY_DIRECTORY_MODE_INVALID")


def _require_owner_only_file(path: Path) -> None:
    _require_absolute_regular_file(path)
    observed = path.stat()
    if observed.st_uid != os.getuid() or stat.S_IMODE(observed.st_mode) != 0o600:
        raise ReadinessBlocked("OWNER_ONLY_FILE_MODE_INVALID")


def _require_absolute_directory(path: Path) -> None:
    if not path.is_absolute():
        raise ReadinessBlocked("ABSOLUTE_PATH_REQUIRED")
    _reject_symlink_components(path.parent, allow_missing=False)
    if path.is_symlink() or not path.is_dir():
        raise ReadinessBlocked("REQUIRED_DIRECTORY_INVALID")


def _require_absolute_regular_file(
    path: Path,
    *,
    allow_final_symlink: bool = False,
) -> None:
    if not path.is_absolute():
        raise ReadinessBlocked("ABSOLUTE_PATH_REQUIRED")
    _reject_symlink_components(path.parent, allow_missing=False)
    if (path.is_symlink() and not allow_final_symlink) or not path.is_file():
        raise ReadinessBlocked("REQUIRED_FILE_INVALID")


def _reject_symlink_components(path: Path, *, allow_missing: bool) -> None:
    if not path.is_absolute():
        raise ReadinessBlocked("ABSOLUTE_PATH_REQUIRED")
    cursor = Path(path.anchor)
    for part in path.parts[1:]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ReadinessBlocked("SYMLINK_PATH_REJECTED")
        if not cursor.exists():
            if allow_missing:
                return
            raise ReadinessBlocked("REQUIRED_PATH_MISSING")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_all(descriptor: int, value: bytes) -> None:
    view = memoryview(value)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("owner-only file write made no progress")
        view = view[written:]
