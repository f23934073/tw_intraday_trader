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
        "strategy-draft-clone",
        "strategy-draft-validate",
        "strategy-draft-publish",
        "strategy-version-list",
        "strategy-version-left",
        "strategy-version-right",
        "strategy-version-compare",
        "strategy-set-form",
        "strategy-set-members",
        "strategy-set-change-note",
        "strategy-set-save",
        "strategy-set-cancel",
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


def test_strategy_management_uses_accessible_workflow_tabs() -> None:
    for tab_name in ("editor", "library", "sets", "audit"):
        assert f'id="strategy-tab-{tab_name}"' in HTML
        assert f'aria-controls="strategy-panel-{tab_name}"' in HTML
        assert f'data-strategy-tab="{tab_name}"' in HTML
        assert f'id="strategy-panel-{tab_name}"' in HTML
        assert f'aria-labelledby="strategy-tab-{tab_name}"' in HTML
        assert f'data-strategy-panel="{tab_name}"' in HTML
    assert 'role="tablist" aria-label="策略管理工作流程"' in HTML
    assert "setStrategyManagementView" in BACKTEST
    assert "handleStrategyTabKeydown" in BACKTEST
    assert '["ArrowLeft", "ArrowRight", "Home", "End"]' in BACKTEST


def test_switching_atomic_template_clears_stale_draft_status() -> None:
    selection_start = BACKTEST.index(
        'button.addEventListener("click", () => {', BACKTEST.index("function renderAtomicTemplates")
    )
    selection_end = BACKTEST.index("renderAtomicManagement();", selection_start)
    selection_handler = BACKTEST[selection_start:selection_end]
    assert 'strategyDraftMessage.textContent = "";' in selection_handler


def test_selecting_or_cloning_draft_keeps_library_open_with_editor_on_right() -> None:
    assert 'id="strategy-editor-mount"' in HTML
    assert 'id="strategy-draft-editor-card"' in HTML
    assert 'id="strategy-library-editor-mount"' in HTML
    assert HTML.index('id="strategy-library-editor-mount"') < HTML.index(
        'id="strategy-version-list"'
    )
    assert 'viewName === "library" && activeAtomicDraft()' in BACKTEST

    draft_handler = BACKTEST[
        BACKTEST.index("function renderAtomicDrafts") : BACKTEST.index(
            "function renderAtomicVersions"
        )
    ]
    clone_handler = BACKTEST[
        BACKTEST.index("async function cloneAtomicVersion") : BACKTEST.index(
            "async function submitAtomicStrategySet"
        )
    ]
    assert "renderAtomicManagement();" in draft_handler
    assert 'setStrategyManagementView("editor"' not in draft_handler
    assert 'setStrategyManagementView("editor"' not in clone_handler


def test_sealed_draft_offers_clone_instead_of_editing_original() -> None:
    assert 'id="strategy-draft-clone" type="button" hidden' in HTML
    editor = BACKTEST[
        BACKTEST.index("function renderAtomicParameterEditor") : BACKTEST.index(
            "function readAtomicParameters"
        )
    ]
    assert "control.disabled = sealed" in editor
    assert "strategyChangeNote.readOnly = sealed" in editor
    assert "strategyDraftClone.hidden = !sealed" in editor
    assert "strategyDraftSave.hidden = sealed" in editor
    assert "draft?.published_strategy_version_id" in editor
    assert 'strategyDraftClone?.addEventListener("click", cloneActiveAtomicDraft)' in BACKTEST
    assert "await cloneAtomicVersion(draft.published_strategy_version_id)" in BACKTEST
    assert "strategyDraftClone.disabled = false" in BACKTEST


def test_strategy_set_minimum_is_editable_and_selects_at_least_n_policy() -> None:
    minimum = '<input id="strategy-set-minimum" type="number" min="1" value="1" aria-describedby="strategy-set-minimum-help">'
    assert minimum in HTML
    assert 'id="strategy-set-minimum-help"' in HTML
    assert 'strategySetMinimum?.addEventListener("input"' in BACKTEST
    assert 'strategySetPolicy.value = "AT_LEAST_N"' in BACKTEST
    assert "strategySetMinimum.disabled" not in BACKTEST


def test_strategy_set_cards_can_create_revisions_and_archive_with_confirmation() -> None:
    assert "data-strategy-set-edit" in BACKTEST
    assert "data-strategy-set-delete" in BACKTEST
    assert "/revisions`" in BACKTEST
    assert '"DELETE"' in BACKTEST
    assert "window.confirm" in BACKTEST
    assert "歷史快照仍會保留" in BACKTEST
    assert "resetStrategySetEditor" in BACKTEST
    assert "最新版本" not in BACKTEST or "latestVersionByFamily" in BACKTEST
    assert "latestVersionByFamily" in BACKTEST


def test_atomic_backtest_launcher_uses_exact_set_not_raw_strategy_ids() -> None:
    assert 'id="atomic-backtest-form"' in HTML
    assert 'id="atomic-backtest-set"' in HTML
    assert "/api/backtests/runs/atomic" in BACKTEST
    assert "strategy_set_version_id: atomicBacktestSet.value" in BACKTEST
    assert 'id="atomic-backtest-dataset"' not in HTML
    assert "dataset_id: atomicBacktestDataset.value" not in BACKTEST
    assert 'id="atomic-backtest-dataset-status"' in HTML
    assert "if (!atomic) {" in BACKTEST
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
    assert "display_status" in BACKTEST
    assert "persisted verdict" in BACKTEST
    assert "NO_QUALIFYING_STRATEGY" in BACKTEST
    assert "Formal v3" in BACKTEST


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
