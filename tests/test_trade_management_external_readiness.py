from __future__ import annotations

import ast
import os
import stat
from pathlib import Path

import pytest
from dotenv import dotenv_values

from runtime.trade_management_external_readiness import (
    ReadinessBlocked,
    provision_owner_only_environment,
    render_disabled_deployment_candidates,
)


def _source_environment(path: Path, *, shadow_dsn: str = "postgresql://shadow") -> None:
    path.write_text(
        "\n".join(
            (
                "SHIOAJI_API_KEY=api-key",
                "SHIOAJI_SECRET=top-secret-value",
                "LOCAL_PAPER_DATABASE_URL=postgresql://paper",
                f"TRADE_MANAGEMENT_SHADOW_DATABASE_URL={shadow_dsn}",
                "UNRELATED_KEY=must-not-leak",
                "",
            )
        ),
        encoding="utf-8",
    )


def test_provision_environment_filters_and_forces_safe_values(tmp_path: Path) -> None:
    source = tmp_path / "source.env"
    config = tmp_path / "config"
    target = config / "trade_management_shadow.env"
    _source_environment(source)

    result = provision_owner_only_environment(source=source, target=target)

    parsed = dotenv_values(target, interpolate=False)
    assert parsed == {
        "SHIOAJI_API_KEY": "api-key",
        "SHIOAJI_SECRET": "top-secret-value",
        "LOCAL_PAPER_DATABASE_URL": "postgresql://paper",
        "TRADE_MANAGEMENT_SHADOW_DATABASE_URL": "postgresql://shadow",
        "SJ_SIMULATION": "true",
    }
    assert stat.S_IMODE(config.stat().st_mode) == 0o700
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert result["values_disclosed"] is False
    assert "api-key" not in repr(result)
    assert "top-secret-value" not in repr(result)


def test_provision_environment_is_immutable(tmp_path: Path) -> None:
    source = tmp_path / "source.env"
    target = tmp_path / "config/trade_management_shadow.env"
    _source_environment(source)
    provision_owner_only_environment(source=source, target=target)

    with pytest.raises(ReadinessBlocked, match="ENVIRONMENT_TARGET_ALREADY_EXISTS"):
        provision_owner_only_environment(source=source, target=target)


def test_provision_environment_rejects_shared_dsn(tmp_path: Path) -> None:
    source = tmp_path / "source.env"
    target = tmp_path / "config/trade_management_shadow.env"
    _source_environment(source, shadow_dsn="postgresql://paper")

    with pytest.raises(ReadinessBlocked, match="SHADOW_DSN_MUST_BE_DEDICATED"):
        provision_owner_only_environment(source=source, target=target)
    assert not target.exists()


def test_provision_environment_rejects_non_simulation(tmp_path: Path) -> None:
    source = tmp_path / "source.env"
    target = tmp_path / "config/trade_management_shadow.env"
    _source_environment(source)
    with source.open("a", encoding="utf-8") as handle:
        handle.write("SJ_SIMULATION=false\n")

    with pytest.raises(ReadinessBlocked, match="PROVIDER_SIMULATION_MUST_BE_TRUE"):
        provision_owner_only_environment(source=source, target=target)
    assert not target.exists()


def test_provision_environment_verifies_observed_target_mode(tmp_path: Path) -> None:
    source = tmp_path / "source.env"
    config = tmp_path / "config"
    config.mkdir(mode=0o700)
    target = config / "trade_management_shadow.env"
    _source_environment(source)
    previous_umask = os.umask(0o777)
    try:
        with pytest.raises(ReadinessBlocked, match="OWNER_ONLY_FILE_MODE_INVALID"):
            provision_owner_only_environment(source=source, target=target)
    finally:
        os.umask(previous_umask)

    assert target.exists()
    assert target.stat().st_size == 0


def test_rendered_candidates_remain_disabled_and_network_denied(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    deployment = project / "architecture/deployment"
    deployment.mkdir(parents=True)
    source_root = Path(__file__).resolve().parents[1]
    for name in (
        "trade_management_shadow_external.sb.template",
        "com.stevehuang.trade-management-shadow.plist.template",
    ):
        (deployment / name).write_text(
            (source_root / "architecture/deployment" / name).read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )
    venv_bin = project / ".venv/bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").symlink_to(Path(os.sys.executable))
    config = tmp_path / "config"
    config.mkdir(mode=0o700)
    environment_file = config / "trade_management_shadow.env"
    environment_file.write_text("fixture\n", encoding="utf-8")
    environment_file.chmod(0o600)
    state = tmp_path / "state"

    result = render_disabled_deployment_candidates(
        project_root=project,
        environment_file=environment_file,
        artifact_root=state / "artifacts",
        records_root=state / "records",
        ownership_lock_root=state / "locks",
        tmp_root=state / "tmp",
    )

    sandbox = (deployment / "trade_management_shadow_external.sb").read_text(
        encoding="utf-8"
    )
    plist = (deployment / "com.stevehuang.trade-management-shadow.plist").read_text(
        encoding="utf-8"
    )
    assert "/ABSOLUTE/" not in sandbox
    assert "/ABSOLUTE/" not in plist
    assert "(deny network*)" in sandbox
    assert "RENDERED CANDIDATE — NOT APPROVED" in sandbox
    assert "<key>Disabled</key>" in plist
    assert "<true/>" in plist
    assert str(state / "tmp") in plist
    assert result["installed"] is False
    assert result["production_shadow_gate"] == "NOT_PASSED"
    for name in ("artifacts", "records", "locks", "tmp"):
        assert stat.S_IMODE((state / name).stat().st_mode) == 0o700

    with pytest.raises(
        ReadinessBlocked,
        match="DEPLOYMENT_PATH_UNSAFE_FOR_SANDBOX",
    ):
        render_disabled_deployment_candidates(
            project_root=project,
            environment_file=environment_file,
            artifact_root=state / "artifacts",
            records_root=state / "records",
            ownership_lock_root=state / "locks",
            tmp_root=state / 'unsafe"tmp',
        )


def test_rendered_candidates_are_immutable(tmp_path: Path) -> None:
    project = tmp_path / "project"
    deployment = project / "architecture/deployment"
    deployment.mkdir(parents=True)
    source_root = Path(__file__).resolve().parents[1]
    for name in (
        "trade_management_shadow_external.sb.template",
        "com.stevehuang.trade-management-shadow.plist.template",
    ):
        (deployment / name).write_text(
            (source_root / "architecture/deployment" / name).read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )
    venv_bin = project / ".venv/bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").symlink_to(Path(os.sys.executable))
    config = tmp_path / "config"
    config.mkdir(mode=0o700)
    environment_file = config / "trade_management_shadow.env"
    environment_file.write_text("fixture\n", encoding="utf-8")
    environment_file.chmod(0o600)
    state = tmp_path / "state"
    arguments = {
        "project_root": project,
        "environment_file": environment_file,
        "artifact_root": state / "artifacts",
        "records_root": state / "records",
        "ownership_lock_root": state / "locks",
        "tmp_root": state / "tmp",
    }
    render_disabled_deployment_candidates(**arguments)

    with pytest.raises(
        ReadinessBlocked,
        match="RENDERED_DEPLOYMENT_TARGET_ALREADY_EXISTS",
    ):
        render_disabled_deployment_candidates(**arguments)


def test_readiness_import_boundary_has_no_execution_capability() -> None:
    project_root = Path(__file__).resolve().parents[1]
    paths = (
        project_root / "runtime/trade_management_external_readiness.py",
        project_root
        / "scripts/prepare_trade_management_shadow_external_readiness.py",
    )
    forbidden = {
        "subprocess",
        "shioaji",
        "psycopg",
        "psycopg_pool",
        "trading",
        "simulation",
        "position",
    }
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        assert imported.isdisjoint(forbidden), (path, imported)
