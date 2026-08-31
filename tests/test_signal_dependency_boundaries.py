"""Architecture-boundary tests for the ``signals`` / ``strategy_catalog`` edge.

Slice 2 keeps the dependency strictly one-way: ``signals`` may reach into
``strategy_catalog`` (for :func:`strategy_catalog.parameter_schema.canonical_digest`,
now via the private ``signals._contract_wire`` helper), but ``strategy_catalog``
must never import ``signals``. These tests statically forbid a reverse edge in
every tracked ``strategy_catalog`` module and dynamically prove that importing
the two packages in either order never trips a cycle.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from collections.abc import Mapping
from itertools import permutations
from pathlib import Path
from typing import NamedTuple


REPO_ROOT = Path(__file__).resolve().parents[1]


def _tracked_strategy_catalog_modules() -> tuple[Path, ...]:
    result = subprocess.run(
        ["git", "ls-files", "strategy_catalog"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    paths = tuple(
        REPO_ROOT / line
        for line in result.stdout.splitlines()
        if line.endswith(".py")
    )
    assert paths, "expected at least one tracked strategy_catalog module"
    return paths


# Literal module -> the dynamic-import callable it exposes. Used for the
# ``from <module> import <callable>`` seed, for the canonical identity of a
# ``import <module> [as <alias>]`` binding and for the literal
# ``getattr(<module-name>, "<callable>")`` spelling of the same callable.
_DYNAMIC_IMPORT_CALLABLES: dict[str, str] = {
    "importlib": "import_module",
    "builtins": "__import__",
}
_DYNAMIC_IMPORT_CALLABLE_NAMES = frozenset(_DYNAMIC_IMPORT_CALLABLES.values())
# The bare module names always denote themselves, so a literal
# ``getattr(importlib, ...)`` resolves with or without a visible ``import``.
_CANONICAL_DYNAMIC_IMPORT_MODULES: Mapping[str, frozenset[str]] = {
    name: frozenset((name,)) for name in _DYNAMIC_IMPORT_CALLABLES
}


class _DynamicImportBindings(NamedTuple):
    """Local names the firewall resolves back to a literal dynamic import.

    ``modules`` maps a local name to every canonical dynamic-import module it
    denotes anywhere in the tree: the bare ``importlib``/``builtins`` names
    plus every alias bound by ``import importlib as il`` /
    ``import builtins as bi``. The immutable identity sets make repeated
    bindings a flow-insensitive union instead of a last-write-wins map.
    ``callables`` holds local names bound to ``importlib.import_module`` /
    ``builtins.__import__`` (see :func:`_dynamic_import_bindings`).
    """

    modules: Mapping[str, frozenset[str]]
    callables: frozenset[str]


_NO_LOCAL_BINDINGS = _DynamicImportBindings(_CANONICAL_DYNAMIC_IMPORT_MODULES, frozenset())


def _is_literal_getattr_dynamic_import(
    node: ast.AST, modules: Mapping[str, frozenset[str]]
) -> bool:
    """``getattr(importlib, "import_module")`` / ``getattr(builtins, "__import__")``.

    Only the fully literal spelling is resolved: a bare ``getattr`` name, a
    bare module name whose canonical identity (``modules``) is ``importlib``
    or ``builtins`` — the canonical name itself or an alias bound by
    ``import importlib as il`` / ``import builtins as bi`` — and a
    string-constant callable name matching that module (an optional third
    ``default`` argument is tolerated). Non-literal module or attribute
    expressions are out of scope.
    """
    if not isinstance(node, ast.Call) or node.keywords or len(node.args) not in (2, 3):
        return False
    module, attr = node.args[0], node.args[1]
    if not (
        isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and isinstance(module, ast.Name)
        and isinstance(attr, ast.Constant)
    ):
        return False
    canonical_identities = modules.get(module.id, frozenset())
    return any(
        _DYNAMIC_IMPORT_CALLABLES[canonical] == attr.value
        for canonical in canonical_identities
    )


def _is_dynamic_import_callable(expr: ast.AST, bindings: _DynamicImportBindings) -> bool:
    """Whether ``expr`` literally denotes ``import_module``/``__import__``.

    Recognised spellings: the bare callable name or a local alias of it
    (``bindings.callables``), an ``*.import_module`` / ``*.__import__``
    attribute, or a literal ``getattr(<module-name>, "<callable>")`` whose
    module name resolves through ``bindings.modules`` to ``importlib`` /
    ``builtins``.
    """
    if isinstance(expr, ast.Name):
        return expr.id in _DYNAMIC_IMPORT_CALLABLE_NAMES or expr.id in bindings.callables
    if isinstance(expr, ast.Attribute):
        return expr.attr in _DYNAMIC_IMPORT_CALLABLE_NAMES
    return _is_literal_getattr_dynamic_import(expr, bindings.modules)


def _dynamic_import_bindings(tree: ast.AST) -> _DynamicImportBindings:
    """Local names bound to the dynamic-import modules or callables.

    ``modules`` starts from the canonical ``importlib``/``builtins`` names and
    unions every ``import importlib [as il]`` / ``import builtins [as bi]``
    (``ast.Import``) binding into the local name's canonical identity set, so a
    repeated alias keeps every recognized identity instead of whichever import
    happens to be visited last. A paired literal ``getattr`` matches any
    retained identity.

    ``callables`` is seeded from aliased ``from`` imports such as
    ``from importlib import import_module as load`` and
    ``from builtins import __import__ as load``, then a bounded fixed-point
    over simple assignments (``Assign``/``AnnAssign`` to plain names) whose
    right-hand side literally denotes a dynamic-import callable —
    ``load = importlib.import_module``, ``load = import_module``,
    ``load = builtins.__import__``, ``load = getattr(importlib, "import_module")``,
    ``load = getattr(il, "import_module")`` or ``other = load`` — so the
    firewall maps every such local binding back to the underlying callable
    instead of recognising only the bare names.

    Bounded by design: only literal module aliases, literal callables and
    literal module names are resolved (no general data flow, no dynamic
    strings, no non-literal ``getattr``), and the resolution is
    flow-insensitive, so a name is treated as a dynamic importer (or as the
    dynamic-import module) anywhere in the module once it is bound to one.
    """
    module_identities: dict[str, set[str]] = {
        name: set(identities)
        for name, identities in _CANONICAL_DYNAMIC_IMPORT_MODULES.items()
    }
    aliases: set[str] = set()
    assignments: list[tuple[tuple[str, ...], ast.expr]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _DYNAMIC_IMPORT_CALLABLES:
                    local_name = alias.asname or alias.name
                    module_identities.setdefault(local_name, set()).add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0:
                continue
            wanted = _DYNAMIC_IMPORT_CALLABLES.get(node.module or "")
            if wanted is None:
                continue
            for alias in node.names:
                if alias.name == wanted:
                    aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign):
            names = tuple(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
            if names:
                assignments.append((names, node.value))
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.value is not None:
                assignments.append(((node.target.id,), node.value))

    modules = {
        name: frozenset(identities)
        for name, identities in module_identities.items()
    }

    # Fixed point: each pass either binds at least one new name or terminates,
    # so the loop runs at most ``len(assignments) + 1`` times.
    changed = True
    while changed:
        changed = False
        bindings = _DynamicImportBindings(modules, frozenset(aliases))
        for names, value in assignments:
            if not _is_dynamic_import_callable(value, bindings):
                continue
            for name in names:
                if name not in aliases:
                    aliases.add(name)
                    changed = True
    return _DynamicImportBindings(modules, frozenset(aliases))


def _imports_signals_literal(
    node: ast.AST, bindings: _DynamicImportBindings = _NO_LOCAL_BINDINGS
) -> bool:
    """Detect a literal ``import_module``/``__import__`` of ``signals``.

    ``bindings`` carries local names bound to a dynamic-import callable or
    module (see :func:`_dynamic_import_bindings`); a ``Call`` through such a
    callable alias, an ``*.import_module``/``*.__import__`` attribute, or an
    immediate literal ``getattr(<module-name>, "<callable>")(...)`` whose
    module name is ``importlib``/``builtins`` or an ``import ... as`` alias of
    one is resolved to the underlying import so every literal spelling is
    rejected. The module target
    is read from positional argument 0 *or* the keyword argument ``name`` —
    both ``importlib.import_module`` and ``__import__`` accept the target as
    ``name=`` — so a literal keyword import cannot slip past.
    """
    if not isinstance(node, ast.Call):
        return False
    if not _is_dynamic_import_callable(node.func, bindings):
        return False
    target: ast.expr | None = None
    if node.args:
        target = node.args[0]
    else:
        for keyword in node.keywords:
            if keyword.arg == "name":
                target = keyword.value
                break
    if not isinstance(target, ast.Constant) or not isinstance(target.value, str):
        return False
    return target.value == "signals" or target.value.startswith("signals.")


def _run_import_probe(statements: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPYCACHEPREFIX"] = str(tmp_path / "pycache")
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO_ROOT), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    return subprocess.run(
        [sys.executable, "-c", statements],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def test_strategy_catalog_never_imports_signals_statically():
    for path in _tracked_strategy_catalog_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        bindings = _dynamic_import_bindings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    assert root != "signals", (
                        f"{path} imports signals via `import {alias.name}`"
                    )
            elif isinstance(node, ast.ImportFrom):
                # Absolute imports only: a relative import has module None/level>0.
                if node.level == 0 and (node.module or "").split(".")[0] == "signals":
                    assert False, f"{path} imports signals via `from {node.module}`"
            else:
                assert not _imports_signals_literal(node, bindings), (
                    f"{path} performs a dynamic import of signals"
                )


def test_both_import_orders_are_acyclic(tmp_path):
    signal_modules = (
        "signals.entry_specification",
        "signals.gate_taxonomy",
        "signals.selection",
        "signals.decision_evidence",
    )
    catalog_first = "import strategy_catalog.parameter_schema\n" + "".join(
        f"import {name}\n" for name in signal_modules
    )
    signals_first = "".join(
        f"import {name}\n" for name in signal_modules
    ) + "import strategy_catalog.parameter_schema\n"

    for statements in (catalog_first, signals_first):
        completed = _run_import_probe(statements, tmp_path)
        assert completed.returncode == 0, (
            f"import-order probe failed:\n{statements}\n{completed.stderr}"
        )


def test_firewall_rejects_aliased_dynamic_imports():
    """Regression: aliased literal dynamic imports of ``signals`` are rejected.

    Oscar task069 P2 — the firewall resolved only bare
    ``import_module``/``__import__`` names and ``*.import_module`` attributes,
    so an aliased dynamic import could slip a reverse ``strategy_catalog ->
    signals`` edge past
    :func:`test_strategy_catalog_never_imports_signals_statically`. Alias
    resolution now maps the local binding back to the underlying callable.
    """
    rejected_sources = (
        '__import__("signals")',
        'import_module("signals.selection")',
        'importlib.import_module("signals.selection")',
        'builtins.__import__("signals.selection")',
        'from importlib import import_module as load\nload("signals.selection")',
        'from builtins import __import__ as load\nload("signals.selection")',
    )
    for source in rejected_sources:
        tree = ast.parse(source)
        bindings = _dynamic_import_bindings(tree)
        assert any(
            _imports_signals_literal(node, bindings) for node in ast.walk(tree)
        ), f"firewall failed to reject aliased dynamic import: {source!r}"

    allowed_sources = (
        # Alias resolves to a dynamic import, but not of ``signals``.
        'from importlib import import_module as load\n'
        'load("strategy_catalog.parameter_schema")',
        # ``load`` is not bound to a dynamic-import callable -> not an import.
        'load("signals.selection")',
    )
    for source in allowed_sources:
        tree = ast.parse(source)
        bindings = _dynamic_import_bindings(tree)
        assert not any(
            _imports_signals_literal(node, bindings) for node in ast.walk(tree)
        ), f"firewall wrongly rejected benign source: {source!r}"


def test_firewall_rejects_keyword_dynamic_imports():
    """Regression: literal dynamic imports of ``signals`` via keyword ``name=``.

    Oscar task069 P2 — the firewall bailed on empty ``node.args`` and only ever
    read positional argument 0, so ``import_module(name="signals...")`` and
    ``__import__(name="signals")`` (both accept the target as the keyword
    ``name``) slipped a reverse ``strategy_catalog -> signals`` edge past
    :func:`test_strategy_catalog_never_imports_signals_statically`. The target is
    now resolved from positional arg 0 *or* keyword ``name``.
    """
    rejected_sources = (
        # Direct keyword forms for both callables and the ``*.import_module`` /
        # ``*.__import__`` attribute spellings.
        '__import__(name="signals")',
        'import_module(name="signals.selection")',
        'importlib.import_module(name="signals.selection")',
        'builtins.__import__(name="signals.selection")',
        # Aliased keyword forms for import_module and __import__.
        'from importlib import import_module as load\nload(name="signals.selection")',
        'from builtins import __import__ as load\nload(name="signals")',
    )
    for source in rejected_sources:
        tree = ast.parse(source)
        bindings = _dynamic_import_bindings(tree)
        assert any(
            _imports_signals_literal(node, bindings) for node in ast.walk(tree)
        ), f"firewall failed to reject keyword dynamic import: {source!r}"

    allowed_sources = (
        # Benign keyword target that is not ``signals``.
        'importlib.import_module(name="math")',
        # Aliased keyword import of a non-signals module.
        'from importlib import import_module as load\n'
        'load(name="strategy_catalog.parameter_schema")',
        # ``load`` is not bound to a dynamic-import callable -> not an import.
        'load(name="signals.selection")',
    )
    for source in allowed_sources:
        tree = ast.parse(source)
        bindings = _dynamic_import_bindings(tree)
        assert not any(
            _imports_signals_literal(node, bindings) for node in ast.walk(tree)
        ), f"firewall wrongly rejected benign keyword source: {source!r}"


def test_firewall_rejects_assignment_rebound_and_getattr_dynamic_imports():
    """Regression: assignment-rebound and literal-``getattr`` dynamic imports.

    Amy task071 P2 — alias resolution only recorded names introduced directly
    by an aliased ``from`` import, so rebinding the callable through an
    ordinary assignment (``load = importlib.import_module``) or spelling it as
    ``getattr(importlib, "import_module")`` slipped a reverse
    ``strategy_catalog -> signals`` edge past
    :func:`test_strategy_catalog_never_imports_signals_statically`. The alias
    set is now a bounded fixed-point over simple assignments, and the literal
    ``getattr`` spelling is resolved both when called immediately and when
    bound to a name first.
    """
    rejected_sources = (
        # Amy's four confirmed false negatives, verbatim.
        'import importlib\nload = importlib.import_module\nload("signals.selection")',
        'from importlib import import_module\nload = import_module\n'
        'load("signals.selection")',
        'import builtins\nload = builtins.__import__\nload(name="signals")',
        'import importlib\ngetattr(importlib, "import_module")("signals.selection")',
        # Bare builtin ``__import__`` rebound without any import statement.
        'load = __import__\nload("signals")',
        # Immediate literal getattr on ``builtins`` and with a ``default`` arg.
        'import builtins\ngetattr(builtins, "__import__")("signals")',
        'import importlib\ngetattr(importlib, "import_module", None)("signals.selection")',
        # Literal getattr bound to a name, then called (positional and keyword).
        'import importlib\nload = getattr(importlib, "import_module")\n'
        'load("signals.selection")',
        'import builtins\nload = getattr(builtins, "__import__")\nload(name="signals")',
        # Chained rebinding, aliased-import seed rebound, annotated and multi-target.
        'import importlib\nfirst = importlib.import_module\nsecond = first\n'
        'second("signals.gate_taxonomy")',
        'from importlib import import_module as load\nrun = load\n'
        'run("signals.selection")',
        'import importlib\nload: object = importlib.import_module\n'
        'load("signals.selection")',
        'import importlib\nload = run = importlib.import_module\nrun("signals")',
    )
    for source in rejected_sources:
        tree = ast.parse(source)
        bindings = _dynamic_import_bindings(tree)
        assert any(
            _imports_signals_literal(node, bindings) for node in ast.walk(tree)
        ), f"firewall failed to reject rebound/getattr dynamic import: {source!r}"

    allowed_sources = (
        # Rebound dynamic importer, but the target is not ``signals``.
        'import importlib\nload = importlib.import_module\nload("math")',
        'import builtins\nload = builtins.__import__\n'
        'load(name="strategy_catalog.parameter_schema")',
        'import importlib\nload = getattr(importlib, "import_module")\n'
        'load("strategy_catalog.parameter_schema")',
        'import importlib\ngetattr(importlib, "import_module")("math")',
        # Literal getattr of a non-import attribute / mismatched module-callable pair.
        'import importlib\ngetattr(importlib, "reload")("signals")',
        'import builtins\ngetattr(builtins, "import_module")("signals")',
        # Rebinding something that is not a dynamic-import callable.
        'import importlib\nload = importlib.util\nload("signals.selection")',
        'load = helper\nload("signals.selection")',
        'load = helper()\nload("signals.selection")',
        # ``signals`` appearing only as data, never as an import target.
        'import importlib\nload = importlib.import_module\nname = "signals"',
    )
    for source in allowed_sources:
        tree = ast.parse(source)
        bindings = _dynamic_import_bindings(tree)
        assert not any(
            _imports_signals_literal(node, bindings) for node in ast.walk(tree)
        ), f"firewall wrongly rejected benign rebound/getattr source: {source!r}"


def test_firewall_rejects_aliased_module_base_getattr_dynamic_imports():
    """Regression: literal ``getattr`` through an ``import ... as`` module alias.

    Oscar task176 P2 — the literal ``getattr`` resolver accepted only the bare
    ``importlib``/``builtins`` module names and the binding collector never
    looked at ``ast.Import``, so ``import importlib as il`` /
    ``import builtins as bi`` followed by ``getattr(il, "import_module")`` or
    ``getattr(bi, "__import__")`` — immediate or assignment-rebound,
    positional or ``name=`` — slipped a reverse ``strategy_catalog ->
    signals`` edge past
    :func:`test_strategy_catalog_never_imports_signals_statically`. The
    ``import`` alias is now recorded under its canonical module identity and
    the literal ``getattr`` resolves through it. Resolution stays bounded to a
    literal module alias, a literal callable name and a literal module target.
    """
    rejected_sources = (
        # Oscar's three confirmed false negatives, verbatim.
        'import importlib as il\ngetattr(il, "import_module")("signals.selection")',
        'import importlib as il\nload=getattr(il, "import_module")\nload(name="signals")',
        'import builtins as bi\ngetattr(bi, "__import__")("signals")',
        # Full matrix: {importlib, builtins} x {immediate, assigned} x
        # {positional, name=} through an aliased module base.
        'import importlib as il\ngetattr(il, "import_module")(name="signals.selection")',
        'import importlib as il\nload = getattr(il, "import_module")\n'
        'load("signals.selection")',
        'import builtins as bi\ngetattr(bi, "__import__")(name="signals")',
        'import builtins as bi\nload = getattr(bi, "__import__")\nload("signals")',
        'import builtins as bi\nload = getattr(bi, "__import__")\nload(name="signals")',
        # Aliased base with a ``default`` argument, annotated / multi-target /
        # chained rebinding, and multi-name ``import`` statements.
        'import importlib as il\ngetattr(il, "import_module", None)("signals.selection")',
        'import importlib as il\nload: object = getattr(il, "import_module")\n'
        'load("signals.gate_taxonomy")',
        'import builtins as bi\nload = run = getattr(bi, "__import__")\nrun("signals")',
        'import importlib as il\nfirst = getattr(il, "import_module")\nsecond = first\n'
        'second("signals.selection")',
        'import os, importlib as il\ngetattr(il, "import_module")("signals.selection")',
        'import importlib as il, builtins as bi\ngetattr(bi, "__import__")("signals")',
        # Un-aliased ``import`` still resolves through its canonical identity.
        'import importlib\ngetattr(importlib, "import_module")("signals.selection")',
        'import builtins\nload = getattr(builtins, "__import__")\nload(name="signals")',
    )
    for source in rejected_sources:
        tree = ast.parse(source)
        bindings = _dynamic_import_bindings(tree)
        assert any(
            _imports_signals_literal(node, bindings) for node in ast.walk(tree)
        ), f"firewall failed to reject aliased-module getattr dynamic import: {source!r}"

    allowed_sources = (
        # Aliased base resolves to a dynamic import, but not of ``signals``.
        'import importlib as il\ngetattr(il, "import_module")("math")',
        'import importlib as il\ngetattr(il, "import_module")(name="strategy_catalog")',
        'import builtins as bi\nload = getattr(bi, "__import__")\n'
        'load("strategy_catalog.parameter_schema")',
        'import builtins as bi\nload = getattr(bi, "__import__")\nload(name="math")',
        # Aliased base with a mismatched or non-import callable name.
        'import importlib as il\ngetattr(il, "__import__")("signals")',
        'import builtins as bi\ngetattr(bi, "import_module")("signals")',
        'import importlib as il\ngetattr(il, "reload")("signals")',
        # The alias is not bound to ``importlib``/``builtins`` (other module,
        # submodule, or never imported at all) -> not resolved, by design.
        'import os as il\ngetattr(il, "import_module")("signals")',
        'import importlib.util as il\ngetattr(il, "import_module")("signals")',
        'getattr(il, "import_module")("signals")',
        # Non-literal callable name or non-literal target stay out of scope.
        'import importlib as il\ngetattr(il, name)("signals")',
        'import importlib as il\ngetattr(il, "import_module")(target)',
        # ``signals`` appearing only as data, never as an import target.
        'import importlib as il\nload = getattr(il, "import_module")\nname = "signals"',
    )
    for source in allowed_sources:
        tree = ast.parse(source)
        bindings = _dynamic_import_bindings(tree)
        assert not any(
            _imports_signals_literal(node, bindings) for node in ast.walk(tree)
        ), f"firewall wrongly rejected benign aliased-module getattr source: {source!r}"


def test_firewall_rejects_repeated_module_alias_collisions():
    """Regression: repeated recognized aliases retain every module identity.

    Oscar task181 P2 — a local module name mapped to one canonical string, so a
    later recognized import overwrote the earlier identity. The paired literal
    ``getattr`` then missed an import that occurred immediately before the
    rebinding, or a callable captured before the rebinding and invoked after
    it. Both source orders, call shapes and target argument spellings must be
    detected, including a collision with a canonical module name.
    """
    oscar_reproducers = (
        'import importlib as dyn\ngetattr(dyn, "import_module")'
        '("signals.selection")\nimport builtins as dyn',
        'import builtins as dyn\ngetattr(dyn, "__import__")'
        '("signals")\nimport importlib as dyn',
        'import importlib as dyn\nload=getattr(dyn, "import_module")\n'
        'import builtins as dyn\nload(name="signals")',
        'import importlib\ngetattr(importlib, "import_module")'
        '("signals")\nimport builtins as importlib',
    )
    for source in oscar_reproducers:
        tree = ast.parse(source)
        bindings = _dynamic_import_bindings(tree)
        assert any(
            _imports_signals_literal(node, bindings) for node in ast.walk(tree)
        ), f"firewall failed to reject repeated-alias reproducer: {source!r}"

    # Complete bounded collision matrix: both binding orders x immediate or
    # captured literal getattr x positional or ``name=`` literal target.
    for first_module, second_module in (
        ("importlib", "builtins"),
        ("builtins", "importlib"),
    ):
        callable_name = _DYNAMIC_IMPORT_CALLABLES[first_module]
        target = "signals.selection" if first_module == "importlib" else "signals"
        for captured in (False, True):
            for argument in (f'"{target}"', f'name="{target}"'):
                lines = [f"import {first_module} as dyn"]
                if captured:
                    lines.append(f'load = getattr(dyn, "{callable_name}")')
                    lines.append(f"import {second_module} as dyn")
                    lines.append(f"load({argument})")
                else:
                    lines.append(f'getattr(dyn, "{callable_name}")({argument})')
                    lines.append(f"import {second_module} as dyn")
                source = "\n".join(lines)
                tree = ast.parse(source)
                bindings = _dynamic_import_bindings(tree)
                assert any(
                    _imports_signals_literal(node, bindings)
                    for node in ast.walk(tree)
                ), f"firewall failed repeated-alias collision matrix: {source!r}"

    allowed_sources = (
        # The same collisions remain benign for non-signals literal targets.
        'import importlib as dyn\ngetattr(dyn, "import_module")'
        '("math")\nimport builtins as dyn',
        'import builtins as dyn\nload = getattr(dyn, "__import__")\n'
        'import importlib as dyn\nload(name="strategy_catalog")',
        # A single recognized identity does not validate the other callable.
        'import importlib as dyn\ngetattr(dyn, "__import__")("signals")',
        'import builtins as dyn\ngetattr(dyn, "import_module")("signals")',
        # Unrecognized module bindings never enter the identity set.
        'import os as dyn\ngetattr(dyn, "import_module")("signals")',
        'import importlib.util as dyn\ngetattr(dyn, "import_module")("signals")',
    )
    for source in allowed_sources:
        tree = ast.parse(source)
        bindings = _dynamic_import_bindings(tree)
        assert not any(
            _imports_signals_literal(node, bindings) for node in ast.walk(tree)
        ), f"firewall wrongly rejected repeated-alias benign source: {source!r}"


def test_dynamic_import_module_bindings_are_monotonic_across_permutations():
    """Recognized module identities form an order-independent monotonic union."""
    scenarios = (
        (
            "dyn",
            (
                ("import importlib as dyn", "importlib"),
                ("import builtins as dyn", "builtins"),
                ("import os as dyn", None),
            ),
        ),
        (
            "importlib",
            (
                ("import importlib", "importlib"),
                ("import builtins as importlib", "builtins"),
                ("import os as importlib", None),
            ),
        ),
    )
    expected_final = frozenset(_DYNAMIC_IMPORT_CALLABLES)

    for local_name, declarations in scenarios:
        orders = tuple(permutations(declarations))
        assert len(orders) == 6
        initial = _dynamic_import_bindings(ast.parse("")).modules.get(
            local_name, frozenset()
        )
        for order in orders:
            retained = initial
            expected = set(initial)
            for length in range(1, len(order) + 1):
                source = "\n".join(statement for statement, _ in order[:length])
                identities = _dynamic_import_bindings(ast.parse(source)).modules.get(
                    local_name, frozenset()
                )
                identity = order[length - 1][1]
                if identity is not None:
                    expected.add(identity)
                assert retained <= identities
                assert identities == frozenset(expected)
                retained = identities
            assert retained == expected_final

            # Either canonical pairing is recognized after every permutation,
            # proving that no final traversal/write order can erase the other.
            imports = "\n".join(statement for statement, _ in order)
            for canonical, callable_name in _DYNAMIC_IMPORT_CALLABLES.items():
                target = "signals.selection" if canonical == "importlib" else "signals"
                source = (
                    f'{imports}\ngetattr({local_name}, "{callable_name}")'
                    f'(name="{target}")'
                )
                tree = ast.parse(source)
                bindings = _dynamic_import_bindings(tree)
                assert any(
                    _imports_signals_literal(node, bindings)
                    for node in ast.walk(tree)
                ), f"firewall lost identity across import permutation: {source!r}"


# Literal AST equivalence classes the firewall must resolve, enumerated as a
# cross-product so a new spelling cannot slip through one class at a time:
# (a) ``ast.Import`` and ``ast.ImportFrom`` bindings, (b) ``as`` aliases of the
# module or of the callable, (c) simple ``Assign``/``AnnAssign`` rebinding of
# the callable, (d) call targets spelled as a ``Name``, an ``Attribute`` or a
# literal ``getattr(<module-name>, "<callable>")``, (e) both dynamic-import
# sources (``importlib.import_module`` and ``builtins.__import__``) and (f)
# positional versus ``name=`` literal targets.
_MATRIX_SIGNALS_TARGETS = ("signals", "signals.selection")
_MATRIX_BENIGN_TARGETS = ("strategy_catalog.parameter_schema", "math")


def _literal_dynamic_import_matrix(target: str) -> tuple[str, ...]:
    """Every literal spelling of a dynamic import of ``target`` (classes a-f)."""
    sources: list[str] = []
    for module, callable_name in _DYNAMIC_IMPORT_CALLABLES.items():  # (e)
        # (preamble, callable expression) pairs: how the callable is reached.
        forms: list[tuple[str, str]] = []
        for base, preamble in (
            (module, f"import {module}"),  # (a) Import
            ("mod_alias", f"import {module} as mod_alias"),  # (b) module alias
        ):
            forms.append((preamble, f"{base}.{callable_name}"))  # (d) Attribute
            forms.append((preamble, f'getattr({base}, "{callable_name}")'))  # (d) getattr
        # (a) ImportFrom -> (d) Name, and (b) callable alias.
        forms.append((f"from {module} import {callable_name}", callable_name))
        forms.append((f"from {module} import {callable_name} as fn_alias", "fn_alias"))
        if module == "builtins":
            forms.append(("", callable_name))  # bare builtin ``__import__``
        for preamble, expr in forms:
            prefix = f"{preamble}\n" if preamble else ""
            for arg in (f'"{target}"', f'name="{target}"'):  # (f)
                sources.append(f"{prefix}{expr}({arg})")  # (c) no rebinding
                sources.append(f"{prefix}load = {expr}\nload({arg})")  # (c) Assign
                sources.append(f"{prefix}load: object = {expr}\nload({arg})")  # (c) AnnAssign
    return tuple(sources)


def test_firewall_literal_dynamic_import_matrix():
    """Cross-product of the six literal equivalence classes (task180 R2).

    Every generated spelling of a literal dynamic import of ``signals`` /
    ``signals.*`` must be rejected, and the identical spelling with a
    non-``signals`` literal target must be accepted, so the matrix doubles as
    its own benign control set.
    """
    rejected = tuple(
        source
        for target in _MATRIX_SIGNALS_TARGETS
        for source in _literal_dynamic_import_matrix(target)
    )
    allowed = tuple(
        source
        for target in _MATRIX_BENIGN_TARGETS
        for source in _literal_dynamic_import_matrix(target)
    )
    # 2 modules x (4 Import/alias attribute+getattr forms + 2 ImportFrom forms)
    # + 1 bare ``__import__``, x 2 target spellings x 3 rebinding shapes, x 2 targets.
    assert len(rejected) == len(allowed) == 13 * 2 * 3 * 2

    for source in rejected:
        tree = ast.parse(source)
        bindings = _dynamic_import_bindings(tree)
        assert any(
            _imports_signals_literal(node, bindings) for node in ast.walk(tree)
        ), f"firewall failed to reject literal dynamic import: {source!r}"
    for source in allowed:
        tree = ast.parse(source)
        bindings = _dynamic_import_bindings(tree)
        assert not any(
            _imports_signals_literal(node, bindings) for node in ast.walk(tree)
        ), f"firewall wrongly rejected benign literal source: {source!r}"
