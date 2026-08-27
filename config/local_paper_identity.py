"""Reviewed, code-owned identity anchor for the Local Paper v2 ledger."""

from __future__ import annotations

import hashlib
import json

from trading.exposure import AccountScopeIdentity, PolicyFamilyIdentity


LOCAL_PAPER_V1_SESSION_ID = "local-paper-runtime-v1"
LOCAL_PAPER_V2_SESSION_ID = "local-paper-runtime-v2"
LOCAL_PAPER_NO_OVERNIGHT_EVIDENCE_SESSION_ID = (
    "local-paper-no-overnight-evidence-v1"
)
LOCAL_PAPER_RUNTIME_IDENTITY_VERSION = "local-paper-runtime-identity-v2"
LOCAL_PAPER_ENTRY_POLICY_VERSION = "local-paper-exposure-policy-v1"

LOCAL_PAPER_ACCOUNT_SCOPE = AccountScopeIdentity(
    account_scope_id="local-paper-main-v1",
    execution_mode="LOCAL_PAPER_SIMULATION",
    ledger_id="local-paper-ledger-v1",
)
LOCAL_PAPER_POLICY_FAMILY = PolicyFamilyIdentity(
    policy_family_id="no-overnight-equity-v1",
    account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
)
LOCAL_PAPER_ENTRY_POLICY_DIGEST = hashlib.sha256(
    json.dumps(
        {
            "account_scope_id": LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
            "policy_family_id": LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
            "policy_version": LOCAL_PAPER_ENTRY_POLICY_VERSION,
            "classification_rule": "EXPLICIT_HORIZON_OR_UNCLASSIFIED_LEGACY",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
).hexdigest()
