"""Guards the lookahead-bias boundary: nothing in the PREGAME path
(agents/, research/ [except nothing -- see below], models/, services/,
config/scoring_config.py, the two pregame CLI scripts) may import
anything from evaluation/, which only exists to read POSTGAME results.

This is a static check (parses import statements via `ast`, never
actually runs postgame code) so it catches the mistake even before any
test exercises the offending code path, and it automatically covers new
files added to these packages later -- nobody has to remember to update
a hardcoded list.
"""

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Every package/file that makes up the PREGAME path. evaluation/ and the
# two postgame CLI scripts (collect_pitcher_results.py, evaluate_pitcher_slate.py)
# are legitimately allowed to import research/models/config -- that
# direction (postgame depending on pregame code) is fine. Only the
# reverse is forbidden.
PREGAME_PACKAGE_DIRS = ["agents", "research", "models", "services", "dfs", "optimizer", "ownership", "projection_engine", "native_projections", "big_money_ml"]
PREGAME_EXTRA_FILES = [
    "config/scoring_config.py",
    "config/evaluation_config.py",  # config-only, no imports either way, but check anyway
    "config/batter_scoring_config.py",
    "config/dk_roster_config.py",
    "config/optimizer_config.py",
    "config/ownership_config.py",
    "scripts/run_real_pitcher_agent.py",
    "scripts/run_pitcher_agent.py",
    "scripts/build_research_package.py",
    "scripts/run_real_batter_agent.py",
    "scripts/build_dk_player_pool.py",
    "scripts/optimize_dk_lineups.py",
    "scripts/project_dk_ownership.py",
    "scripts/fetch_dfs_slate.py",
    "scripts/build_dfs_pool_from_provider.py",
    "scripts/list_dfs_slates.py",
    "config/projection_engine_config.py",
    "scripts/run_ai_projection_engine.py",
    "config/native_projection_config.py",
    "scripts/run_native_projection_engine.py",
    "scripts/run_ml_shadow_inference.py",
]


def _pregame_python_files():
    files = []
    for package_dir in PREGAME_PACKAGE_DIRS:
        files.extend(sorted((PROJECT_ROOT / package_dir).rglob("*.py")))
    for extra in PREGAME_EXTRA_FILES:
        files.append(PROJECT_ROOT / extra)
    return [f for f in files if "__pycache__" not in f.parts]


def _imported_module_names(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


_PREGAME_FILES = _pregame_python_files()


def test_at_least_the_expected_pregame_files_were_found():
    # A sanity check on the discovery mechanism itself: if this drops to
    # zero, the glob is broken and every other test in this file is
    # vacuously passing.
    assert len(_PREGAME_FILES) >= 15


@pytest.mark.parametrize("path", _PREGAME_FILES, ids=lambda p: str(p.relative_to(PROJECT_ROOT)))
def test_pregame_file_never_imports_evaluation_package(path: Path):
    imported = _imported_module_names(path)
    forbidden = {name for name in imported if name == "evaluation" or name.startswith("evaluation.")}
    assert not forbidden, (
        f"{path.relative_to(PROJECT_ROOT)} imports from evaluation/ ({forbidden}) -- "
        f"postgame results must never reach the pregame Pitcher Agent pipeline."
    )


def test_evaluation_package_is_allowed_to_import_pregame_modules():
    """The reverse direction is fine and expected -- evaluation/ reuses
    research/models/config code on purpose (e.g. DK_SCORING, innings
    helpers). This isn't a real risk test, just documents the asymmetry
    so a future reader doesn't "fix" it by accident."""
    results_collector = PROJECT_ROOT / "evaluation" / "results_collector.py"
    imported = _imported_module_names(results_collector)
    assert any(name.startswith("research") for name in imported)


def test_batter_agent_never_imports_pitcher_agent():
    """Milestone 7's specific boundary: the Batter Agent may read
    normalized pitcher RESEARCH (models.pitcher, research.*) but must
    never import agents.pitcher_agent itself -- the module that produces
    the Pitcher Agent's own scores/tags/ranking. Opposing-pitcher context
    is built from raw research in research/opposing_pitcher_context.py,
    never from another agent's conclusions."""
    for relative_path in ("agents/batter_agent.py", "research/opposing_pitcher_context.py", "research/adapters/batter_input.py"):
        imported = _imported_module_names(PROJECT_ROOT / relative_path)
        forbidden = {name for name in imported if name == "agents.pitcher_agent" or name.startswith("agents.pitcher_agent.")}
        assert not forbidden, f"{relative_path} imports agents.pitcher_agent directly: {forbidden}"


def test_batter_agent_module_itself_never_imports_agents_package_at_all():
    """Stronger check on the scoring module specifically: it shouldn't
    import ANYTHING from agents/ (including a future sibling agent) --
    all cross-agent context arrives pre-computed on BatterInput."""
    imported = _imported_module_names(PROJECT_ROOT / "agents" / "batter_agent.py")
    forbidden = {name for name in imported if name == "agents" or name.startswith("agents.")}
    assert not forbidden, f"agents/batter_agent.py imports from agents/: {forbidden}"


def test_dfs_package_never_imports_agents_scoring_modules():
    """Milestone 8's boundary: the DK ingestion layer only reads already
    -scored, immutable prediction snapshot JSON -- it must never import
    agents.pitcher_agent or agents.batter_agent directly, which would let
    it recompute or invent scores instead of joining what was already
    predicted pregame."""
    dfs_dir = PROJECT_ROOT / "dfs"
    for path in sorted(dfs_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        imported = _imported_module_names(path)
        forbidden = {name for name in imported if name == "agents" or name.startswith("agents.")}
        assert not forbidden, f"{path.relative_to(PROJECT_ROOT)} imports from agents/: {forbidden}"


def test_optimizer_package_never_imports_agents_or_dfs_ingestion_internals():
    """Milestone 9's boundary: the optimizer only reads an already-saved,
    immutable player pool JSON (dfs_input/.../dk_player_pool_*.json) --
    it must never import agents.pitcher_agent/batter_agent (recomputing
    scores) or dfs.draftkings_parser/player_resolver (re-deriving
    matches). It's allowed to reuse dfs.name_normalization and
    research.prediction_snapshot, which are pure utilities, not scoring
    or matching logic."""
    optimizer_dir = PROJECT_ROOT / "optimizer"
    forbidden_prefixes = ("agents", "dfs.draftkings_parser", "dfs.player_resolver", "dfs.slate_validation")
    for path in sorted(optimizer_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        imported = _imported_module_names(path)
        forbidden = {name for name in imported if any(name == p or name.startswith(p + ".") for p in forbidden_prefixes)}
        assert not forbidden, f"{path.relative_to(PROJECT_ROOT)} imports forbidden module(s): {forbidden}"


def test_ownership_package_never_imports_agents_or_optimizer():
    """Milestone 10's boundary: the ownership model only reads a saved DK
    player pool JSON (projection/ceiling/salary/etc. already computed by
    the Pitcher/Batter Agents) -- it must never import agents.pitcher_agent
    /batter_agent (recomputing scores) or optimizer.* (ownership is
    computed BEFORE and independently of any lineup construction; the
    optimizer reads ownership snapshots, never the reverse)."""
    ownership_dir = PROJECT_ROOT / "ownership"
    forbidden_prefixes = ("agents", "optimizer")
    for path in sorted(ownership_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        imported = _imported_module_names(path)
        forbidden = {name for name in imported if any(name == p or name.startswith(p + ".") for p in forbidden_prefixes)}
        assert not forbidden, f"{path.relative_to(PROJECT_ROOT)} imports forbidden module(s): {forbidden}"


def test_evaluation_ownership_modules_allowed_to_import_pregame_ownership_package():
    """Milestone 11's reverse-direction sanity check (documents the
    asymmetry, mirrors test_evaluation_package_is_allowed_to_import_pregame_modules):
    evaluation/ownership_evaluator.py legitimately reuses
    ownership.slate_normalization (pure rank/percentile math) and
    evaluation/actual_ownership_resolver.py legitimately reuses
    dfs.name_normalization -- postgame depending on pregame utility code
    is fine, only the reverse is forbidden."""
    evaluator = _imported_module_names(PROJECT_ROOT / "evaluation" / "ownership_evaluator.py")
    assert any(name.startswith("ownership") for name in evaluator)
    resolver = _imported_module_names(PROJECT_ROOT / "evaluation" / "actual_ownership_resolver.py")
    assert any(name.startswith("dfs") for name in resolver)


def test_no_pregame_file_ever_imports_actual_ownership_modules():
    """Milestone 11's explicit lookahead-bias guard: actual (post-lock)
    ownership must never reach the pregame ownership model or optimizer.
    Already covered by the glob-based test_pregame_file_never_imports_evaluation_package
    above (evaluation.actual_ownership_* and evaluation.ownership_evaluator
    are both under evaluation/), but this test names the specific modules
    explicitly so the intent can't be missed by a future reader."""
    forbidden_modules = {
        "evaluation.actual_ownership_models", "evaluation.actual_ownership_parser",
        "evaluation.actual_ownership_resolver", "evaluation.actual_ownership_persistence",
        "evaluation.ownership_evaluator", "evaluation.ownership_evaluation_persistence",
    }
    for path in _PREGAME_FILES:
        imported = _imported_module_names(path)
        forbidden = imported & forbidden_modules
        assert not forbidden, f"{path.relative_to(PROJECT_ROOT)} imports post-lock module(s): {forbidden}"


def test_native_projections_never_imports_ownership_external_projections_or_agents():
    """Milestone 23's explicit independence requirement: the Native
    Projection Model must never use ownership to move its expected-points
    output (see native_projections/matchup.py's module docstring), must
    be usable with NO external projection provider configured (never
    imports external_projections/, structurally proving it doesn't need
    BlueCollar or any other external CSV/API), and must never import
    agents.pitcher_agent/agents.batter_agent (it re-derives its own
    projections from research data -- models.pitcher/models.batter --
    not from another model's already-computed 0-100 scores)."""
    native_projections_dir = PROJECT_ROOT / "native_projections"
    forbidden_prefixes = ("ownership", "external_projections", "agents")
    for path in sorted(native_projections_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        imported = _imported_module_names(path)
        forbidden = {name for name in imported if any(name == p or name.startswith(p + ".") for p in forbidden_prefixes)}
        assert not forbidden, f"{path.relative_to(PROJECT_ROOT)} imports forbidden module(s): {forbidden}"

    script_path = PROJECT_ROOT / "scripts" / "run_native_projection_engine.py"
    imported = _imported_module_names(script_path)
    forbidden = {name for name in imported if any(name == p or name.startswith(p + ".") for p in forbidden_prefixes)}
    assert not forbidden, f"scripts/run_native_projection_engine.py imports forbidden module(s): {forbidden}"


def test_optimizer_dataclasses_have_no_actual_ownership_field():
    """Structural guard (not just an import check): the optimizer's own
    data models must never grow a field for actual/observed ownership --
    only projected_ownership (a pregame model prediction) belongs on
    OptimizerPlayer/Lineup. If this test ever needs updating, that's a
    sign actual ownership is leaking into the pre-lock optimizer, which
    the milestone explicitly forbids."""
    import dataclasses

    from optimizer.models import Lineup, LineupPlayerAssignment, OptimizerPlayer, OptimizerSettings

    for cls in (OptimizerPlayer, OptimizerSettings, LineupPlayerAssignment, Lineup):
        field_names = {f.name for f in dataclasses.fields(cls)}
        assert not any("actual_ownership" in name for name in field_names), (
            f"{cls.__name__} has a field referencing actual_ownership: {field_names}"
        )


# ---------------------------------------------------------------------------
# Milestone 32.2B -- Big Money ML (big_money_ml/) SHADOW-MODE isolation.
#
# big_money_ml/ is a live evaluation competitor to Native/AI, not a
# production projection source: nothing may consume its output yet, and
# it must never reach into any package it isn't allowed to influence.
# ---------------------------------------------------------------------------

_BIG_MONEY_ML_CONSUMER_FORBIDDEN_DIRS = ["native_projections", "projection_engine", "ownership", "optimizer"]


@pytest.mark.parametrize("package_dir", _BIG_MONEY_ML_CONSUMER_FORBIDDEN_DIRS)
def test_production_packages_never_import_big_money_ml(package_dir):
    """Native, AI, Ownership, and the Optimizer must never import
    big_money_ml -- this is what makes M32.2B genuinely shadow-only:
    a bug or failure in the ML model can never propagate into any of
    these production packages."""
    for path in sorted((PROJECT_ROOT / package_dir).rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        imported = _imported_module_names(path)
        forbidden = {name for name in imported if name == "big_money_ml" or name.startswith("big_money_ml.")}
        assert not forbidden, f"{path.relative_to(PROJECT_ROOT)} imports big_money_ml ({forbidden}) -- shadow ML must never be consumed by production code."


def test_big_money_ml_never_imports_ownership_optimizer_native_or_ai_projections():
    """The reverse direction: big_money_ml must never reach INTO the
    packages it's forbidden from influencing either -- it re-derives its
    own live features independently (big_money_ml.live_features), never
    by reading ownership/optimizer/native/AI internals.

    ONE documented, narrow exception: projection_engine.persistence.
    load_latest_dfs_pool is a shared, read-only DK-pool-salary lookup
    utility -- scripts/run_native_projection_engine.py already imports
    this exact same function for the exact same purpose (see that
    script's own `from projection_engine.persistence import
    load_latest_dfs_pool`), and it never touches AI's own scoring/model
    logic or AI's saved projection snapshots. Every OTHER projection_engine
    submodule (scoring, models, the AI snapshot loaders) stays forbidden."""
    big_money_ml_dir = PROJECT_ROOT / "big_money_ml"
    forbidden_prefixes = ("ownership", "optimizer", "native_projections", "projection_engine")
    allowed_exceptions = {"projection_engine.persistence"}

    def _check(path: Path):
        imported = _imported_module_names(path)
        forbidden = {
            name for name in imported
            if any(name == p or name.startswith(p + ".") for p in forbidden_prefixes) and name not in allowed_exceptions
        }
        assert not forbidden, f"{path.relative_to(PROJECT_ROOT)} imports forbidden module(s): {forbidden}"

    for path in sorted(big_money_ml_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        _check(path)

    _check(PROJECT_ROOT / "scripts" / "run_ml_shadow_inference.py")


def test_big_money_ml_never_references_ai_projection_snapshot_loader():
    """Narrower than the module-level check above: proves big_money_ml
    never even NAMES load_latest_ai_projection_snapshot (the one AI-
    specific symbol also living in projection_engine.persistence,
    alongside the shared load_latest_dfs_pool utility that IS allowed)."""
    big_money_ml_dir = PROJECT_ROOT / "big_money_ml"
    for path in sorted(big_money_ml_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        assert "load_latest_ai_projection_snapshot" not in text, f"{path.relative_to(PROJECT_ROOT)} references the AI projection snapshot loader."


def test_big_money_ml_never_imports_historical_mlb_modules_that_pull_in_evaluation():
    """big_money_ml is part of the LIVE PREGAME path and must never
    import evaluation, even transitively. historical_mlb.pitcher_features,
    historical_mlb.hitter_features, historical_mlb.scoring, and
    historical_mlb.sources.mlb_stats all import evaluation.* at module
    scope (they build POSTGAME warehouse rows) -- big_money_ml must go
    through the evaluation-free leaf modules instead (historical_mlb.
    rolling, historical_mlb.statcast_aggregation, historical_mlb.sources.
    statcast, research.collector) and reimplement the handful of tiny
    pure helpers it needs rather than importing these four."""
    big_money_ml_dir = PROJECT_ROOT / "big_money_ml"
    forbidden_modules = {
        "historical_mlb.pitcher_features", "historical_mlb.hitter_features",
        "historical_mlb.scoring", "historical_mlb.sources.mlb_stats", "historical_mlb.warehouse_builder",
    }
    for path in sorted(big_money_ml_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        imported = _imported_module_names(path)
        forbidden = imported & forbidden_modules
        assert not forbidden, f"{path.relative_to(PROJECT_ROOT)} imports {forbidden}, which transitively pulls in evaluation/."


def test_big_money_ml_source_key_never_appears_in_optimizer_projection_source_type():
    """Python-side proxy for the TypeScript check (see
    dashboard/lib/__tests__/architectureSeparation.test.ts): the
    optimizer's ProjectionSource union in
    dashboard/lib/optimizerWorkspace/types.ts must never list
    "big_money_ml" as a selectable value -- shadow mode means the
    optimizer cannot select this source yet."""
    import re

    types_ts = PROJECT_ROOT / "dashboard" / "lib" / "optimizerWorkspace" / "types.ts"
    text = types_ts.read_text(encoding="utf-8")
    match = re.search(r"export type ProjectionSource\s*=\s*([^;]+);", text)
    assert match is not None, "Could not find the ProjectionSource type union in types.ts -- check this test still matches its shape."
    union = match.group(1)
    assert "big_money_ml" not in union, "big_money_ml must not appear in the ProjectionSource union -- the optimizer must not be able to select the ML shadow source yet."
