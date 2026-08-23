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
PREGAME_PACKAGE_DIRS = ["agents", "research", "models", "services", "dfs", "optimizer", "ownership", "projection_engine", "native_projections", "big_money_ml", "player_identity"]
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
    "scripts/run_ml_hitter_shadow_inference.py",
    "scripts/refresh_player_identity.py",
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
    _check(PROJECT_ROOT / "scripts" / "run_ml_hitter_shadow_inference.py")


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


def test_big_money_ml_source_key_is_admin_gated_in_optimizer_projection_source_type():
    """Milestone 32.4 DELIBERATELY supersedes M32.2B/M32.3B's shadow-only
    guarantee: "big_money_ml" IS now a selectable ProjectionSource, for
    ADMIN/OWNER users only. Python-side proxy for the TypeScript check
    (see dashboard/lib/__tests__/architectureSeparation.test.ts) --
    proves the source exists in the union AND that both optimizer API
    routes enforce server-side admin gating (never trust the UI alone)."""
    import re

    types_ts = PROJECT_ROOT / "dashboard" / "lib" / "optimizerWorkspace" / "types.ts"
    text = types_ts.read_text(encoding="utf-8")
    match = re.search(r"export type ProjectionSource\s*=\s*([^;]+);", text)
    assert match is not None, "Could not find the ProjectionSource type union in types.ts -- check this test still matches its shape."
    union = match.group(1)
    assert "big_money_ml" in union, "big_money_ml must appear in the ProjectionSource union as of Milestone 32.4."

    for route in ("build", "validate"):
        route_text = (PROJECT_ROOT / "dashboard" / "app" / "api" / "optimizer" / route / "route.ts").read_text(encoding="utf-8")
        assert "userCanSelectBigMoneyMlOptimizerSource" in route_text, f"{route}/route.ts must enforce Big Money ML admin gating server-side."
        assert 'projectionSource === "big_money_ml"' in route_text


def test_big_money_ml_optimizer_feature_flag_seeded_admin_only():
    """The 'mlb.big_money_ml_optimizer' feature flag must default
    ADMIN_ONLY, not PRODUCTION/BETA -- shipping this migration must
    cause zero behavior change for any current member."""
    migration = (PROJECT_ROOT / "dashboard" / "lib" / "db" / "migrations" / "0006_big_money_ml_optimizer_flag.sql").read_text(encoding="utf-8")
    assert "mlb.big_money_ml_optimizer" in migration
    assert "ADMIN_ONLY" in migration


def test_optimize_dk_lineups_strict_source_never_falls_back_to_independent_projection():
    """Structural proof of the "no mixed-source fallback" guarantee:
    scripts/optimize_dk_lineups.py's strict_source path must exclude a
    player with no override entry rather than reading the pool's own
    independent projection for them."""
    script_text = (PROJECT_ROOT / "scripts" / "optimize_dk_lineups.py").read_text(encoding="utf-8")
    assert "strict_source" in script_text
    assert "--strict-projection-source" in script_text
    assert "excluded_missing_source" in script_text


# ---------------------------------------------------------------------------
# Milestone 32.5 -- forward RESULTS + LINEUP GRADING is evaluation-only.
# The generic pregame-file scan above already proves no pregame package
# ever imports evaluation.* at all (including these new modules, by
# directory-scan construction); these tests add the narrower, explicit
# "never retrains" guarantee this milestone's own instructions require.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_file", [
    "evaluation/ml_forward_grading.py",
    "evaluation/ml_forward_persistence.py",
    "evaluation/ml_forward_history.py",
    "scripts/collect_ml_forward_results.py",
])
def test_ml_forward_grading_never_imports_training_modules(module_file):
    """Milestone 32.5 is evaluation-only: none of its new modules may
    import historical_models.*.train, and none may call .fit(/
    fit_transform( -- the frozen Pitcher/Hitter Model V1 artifacts are
    read-only inputs here, never retrained or refit."""
    text = (PROJECT_ROOT / module_file).read_text(encoding="utf-8")
    imported = _imported_module_names(PROJECT_ROOT / module_file)
    assert "historical_models.pitcher_v1.train" not in imported
    assert "historical_models.hitter_v1.train" not in imported
    for forbidden in ("fit(", "fit_transform"):
        assert forbidden not in text, f"{module_file} contains {forbidden!r} -- M32.5 must never retrain/refit a model."


def test_ml_forward_grading_never_imports_optimizer_ownership_or_native_ai_internals():
    """Evaluation-only: this module reads already-persisted snapshots
    (big_money_ml/, results/, lineups/) but never reaches into the
    optimizer's or ownership's own internal solving/scoring logic."""
    forbidden_prefixes = ("optimizer.constraints", "optimizer.lineup_generator", "ownership.")
    for module_file in ("evaluation/ml_forward_grading.py", "evaluation/ml_forward_persistence.py", "evaluation/ml_forward_history.py"):
        imported = _imported_module_names(PROJECT_ROOT / module_file)
        forbidden = {name for name in imported if any(name == p or name.startswith(p) for p in forbidden_prefixes)}
        assert not forbidden, f"{module_file} imports forbidden module(s): {forbidden}"


# ---------------------------------------------------------------------------
# Milestone 32.3B -- Big Money ML HITTER shadow inference isolation.
#
# All the generic big_money_ml/ checks above already cover every file in
# this package by directory scan (eligible_hitters.py, hitter_artifact.py,
# hitter_feature_parity.py, live_hitter_features.py,
# hitter_shadow_inference.py) -- these tests add narrower, hitter-specific
# assertions the generic scans don't already express.
# ---------------------------------------------------------------------------


def test_big_money_ml_hitter_persistence_uses_a_separate_filename_stream_from_pitcher():
    """Hitter and pitcher ML snapshots share the SAME
    ml_projection_snapshots/<date>/ root by design, but must never be
    able to collide/overwrite each other -- proven by distinct filename
    prefixes, not just convention."""
    from big_money_ml.persistence import _FILENAME_PREFIX, _HITTER_FILENAME_PREFIX

    assert _FILENAME_PREFIX != _HITTER_FILENAME_PREFIX
    assert not _HITTER_FILENAME_PREFIX.startswith(_FILENAME_PREFIX + "_")


def test_big_money_ml_hitter_modules_never_import_research_prediction_snapshot_save_functions():
    """big_money_ml (hitter or pitcher) must never write into Native's
    or AI's own snapshot streams -- it has its own persistence.py and
    never touches research.prediction_snapshot's save path."""
    hitter_files = [
        PROJECT_ROOT / "big_money_ml" / "hitter_shadow_inference.py",
        PROJECT_ROOT / "big_money_ml" / "live_hitter_features.py",
        PROJECT_ROOT / "big_money_ml" / "eligible_hitters.py",
        PROJECT_ROOT / "big_money_ml" / "hitter_artifact.py",
        PROJECT_ROOT / "big_money_ml" / "hitter_feature_parity.py",
    ]
    for path in hitter_files:
        text = path.read_text(encoding="utf-8")
        assert "save_snapshot" not in text, f"{path.relative_to(PROJECT_ROOT)} must never call research.prediction_snapshot.save_snapshot (Native/AI's own snapshot writer)."


def test_big_money_ml_hitter_never_retrains_or_refits_the_frozen_model():
    """M32.3B's explicit 'do not retrain' constraint, structurally
    enforced: no hitter-side big_money_ml file may call .fit(/
    fit_transform( or import the training-only historical_models.
    hitter_v1.train module."""
    hitter_files = [
        PROJECT_ROOT / "big_money_ml" / "hitter_shadow_inference.py",
        PROJECT_ROOT / "big_money_ml" / "live_hitter_features.py",
        PROJECT_ROOT / "big_money_ml" / "hitter_artifact.py",
    ]
    for path in hitter_files:
        text = path.read_text(encoding="utf-8")
        for forbidden in ("fit(", "fit_transform"):
            assert forbidden not in text, f"{path.relative_to(PROJECT_ROOT)} contains {forbidden!r} -- the frozen hitter model must never be retrained/refit live."
        imported = _imported_module_names(path)
        assert "historical_models.hitter_v1.train" not in imported, f"{path.relative_to(PROJECT_ROOT)} imports the training-only historical_models.hitter_v1.train module."
