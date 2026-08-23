from pathlib import Path
import subprocess


STATIC = Path(__file__).resolve().parents[1] / "dashboard" / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
BACKTEST = (STATIC / "js" / "workspaces" / "backtest.js").read_text(encoding="utf-8")


def test_atomic_strategy_management_is_schema_driven_and_versioned() -> None:
    for element_id in (
        "strategy-template-list",
        "strategy-draft-form",
        "strategy-parameter-fields",
        "strategy-draft-validate",
        "strategy-draft-publish",
        "strategy-version-list",
        "strategy-version-left",
        "strategy-version-right",
        "strategy-version-compare",
        "strategy-set-form",
        "strategy-set-members",
        "strategy-set-change-note",
        "strategy-audit-list",
    ):
        assert f'id="{element_id}"' in HTML
    assert "template.parameter_schema?.fields" in BACKTEST
    assert "/api/strategy-versions/drafts" in BACKTEST
    assert "/publish`" in BACKTEST
    assert "/api/strategy-sets" in BACKTEST
    assert "/api/strategy-audit-events" in BACKTEST
    assert "/diff/" in BACKTEST
    assert "X-Strategy-CSRF" in BACKTEST
    assert "pendingAtomicMutationKeys" in BACKTEST


def test_atomic_backtest_launcher_uses_exact_set_not_raw_strategy_ids() -> None:
    assert 'id="atomic-backtest-form"' in HTML
    assert 'id="atomic-backtest-set"' in HTML
    assert "/api/backtests/runs/atomic" in BACKTEST
    assert "strategy_set_version_id: atomicBacktestSet.value" in BACKTEST
    assert 'id="atomic-backtest-dataset"' not in HTML
    assert "dataset_id: atomicBacktestDataset.value" not in BACKTEST
    assert 'id="atomic-backtest-dataset-status"' in HTML
    assert 'if (!atomic) {' in BACKTEST
    assert '"atomic-backtest-clone"' in BACKTEST
    assert 'starting_cash: document.getElementById("atomic-backtest-cash").value' in BACKTEST


def test_backtest_qualification_ui_uses_fixed_windows_and_durable_mutation() -> None:
    for element_id in (
        "backtest-qualification-form",
        "qualification-hypothesis",
        "qualification-folds",
        "qualification-add-fold",
        "qualification-change-note",
        "qualification-submit",
        "qualification-list",
    ):
        assert f'id="{element_id}"' in HTML
    assert 'data-qualification-window="primary"' in HTML
    assert 'id="atomic-backtest-baseline"' in HTML
    assert "/api/backtests/qualifications" in BACKTEST
    assert '"backtest-qualification"' in BACKTEST
    assert "attempted_run_ids: attemptedRunIds" not in BACKTEST
    assert "qualification-min-trades" not in HTML
    assert "family_head_sequence" in BACKTEST
    assert "research_baseline_digest" in BACKTEST
    assert "Historical family linkage" in BACKTEST
    assert "Current family linkage" in BACKTEST
    assert "feature_adapter_identity" in BACKTEST
    assert "walk_forward_windows:" in BACKTEST
    assert "只供人工審核，不會自動啟用策略" in BACKTEST


def test_browser_mutation_key_survives_response_loss_and_server_error() -> None:
    module = (STATIC / "js" / "mutation_keys.js").as_uri()
    script = f"""
      import {{ createMutationKeyStore }} from {module!r};
      let sequence = 0;
      const store = createMutationKeyStore((prefix) => `${{prefix}}-${{++sequence}}`);
      const signature = 'POST:/atomic:{{"value":1}}';
      const first = store.keyFor(signature, 'atomic');
      store.failed(signature, undefined);
      if (store.keyFor(signature, 'atomic') !== first) throw new Error('network loss changed key');
      store.failed(signature, 503);
      if (store.keyFor(signature, 'atomic') !== first) throw new Error('5xx changed key');
      store.failed(signature, 409);
      if (store.keyFor(signature, 'atomic') === first) throw new Error('definitive conflict retained key');
      store.complete(signature);
      if (store.keyFor(signature, 'atomic') === first) throw new Error('success retained key');
    """
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
