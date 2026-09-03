"""CLI entry point: generate mathematically valid DraftKings Classic MLB
lineups (OR-Tools CP-SAT) from a saved, unified DFS player pool
(dfs_input/<date>/dk_player_pool_<timestamp>.json, built by
scripts/build_dk_player_pool.py).

    Unified DFS Player Pool -> Optimizer Config -> CP-SAT -> Legal Lineups
        -> independent validation -> Saved Lineup Set (JSON + CSV)

Usage:
    python scripts/optimize_dk_lineups.py --date YYYY-MM-DD --pool PATH --lineups 1
    python scripts/optimize_dk_lineups.py --date YYYY-MM-DD --pool PATH --lineups 20 \
        --objective balanced --min-unique 2 --stack-size 5 --stack-team PHI \
        --lock "Paul Skenes" --exclude "Some Player" --max-exposure "Kyle Schwarber=0.5" \
        --min-confidence 60 --min-season-pa 50 --max-player-risk 70
    python scripts/optimize_dk_lineups.py --date YYYY-MM-DD --pool PATH \
        --ownership ownership_predictions/YYYY-MM-DD/ownership_<timestamp>.json \
        --lineups 20 --objective leverage --stack-size 5 --max-total-ownership 150

--ownership is optional (Milestone 10). Every objective mode and
constraint that existed before it behaves identically without it --
only --objective leverage and the --*-ownership filters/constraint
require it.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.optimizer_config import INTERACTIVE_SOLVER_MAX_TIME_SECONDS, OPTIMIZER_VERSION
from optimizer.constraints import OptimizerConfigError, pre_solve_diagnostics
from optimizer.lineup_generator import generate_lineups
from optimizer.models import OptimizerPlayer, OptimizerSettings
from optimizer.persistence import build_lineup_set_document, save_lineup_set_csv, save_lineup_set_json
from optimizer.validator import validate_lineup_set
from research.artifact_storage import ARTIFACT_ROOT, resolve_artifact_storage, to_artifact_key
from research.prediction_snapshot import timestamp_tag


def _load_persisted_json(path: Path, not_found_message: str):
    """Mirrors research/adapters/pitcher_input.py's _load_json_list
    object-storage fallback -- both the DFS pool
    (build_dfs_pool_from_provider.py's save_pool()) and the ownership
    snapshot (project_dk_ownership.py's save_ownership_document()) are
    persisted artifacts written exclusively through
    research.storage.save_json() (object storage is the source of
    truth), so a fresh container/process has no local copy until this
    pulls one down."""
    if not path.exists():
        storage = resolve_artifact_storage(ARTIFACT_ROOT)
        data = storage.read_bytes(to_artifact_key(path))
        if data is None:
            raise FileNotFoundError(not_found_message)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_pool(pool_path: str):
    path = Path(pool_path)
    return _load_persisted_json(path, f"DFS pool artifact not found locally ({path}) or in object storage.")


def _load_projection_overrides(path: str):
    """{"<mlb_player_id>": {"projection": x, "ceiling": y, "floor": z}, ...}
    -- an ephemeral, dashboard-generated file (Milestone 17's Projection
    Source selector), never a persisted artifact. Substitutes these
    values in place of the pool's own projection/ceiling/floor for
    matching players, for THIS solve only -- the pool file on disk is
    never touched, so Big Money Independent projections are never
    modified by selecting a different projection source."""
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def _is_probable_starter(record: dict) -> bool:
    """PROBABLE FIX milestone: real, evidence-based probable starter
    (dfs/eligibility.py's own PROBABLE_HITTER status for hitters, or a
    STARTING_PITCHER whose lineup_confirmation is still "PROBABLE" for
    pitchers) -- distinct from a CONFIRMED starter either way."""
    status = record.get("eligibility_status")
    if status == "PROBABLE_HITTER":
        return True
    if status == "STARTING_PITCHER" and record.get("lineup_confirmation") == "PROBABLE":
        return True
    return False


def _build_optimizer_players(pool_doc: dict, projection_overrides: dict = None, strict_source: bool = False, exclude_probable_starters: bool = False):
    """`strict_source=True` (Milestone 32.4 -- Big Money ML) enforces
    SOURCE PURITY: a player with no entry in `projection_overrides` (or
    whose override has no projection value) is excluded from the
    optimizer pool entirely, rather than silently falling back to the
    pool's own independent projection like every other Projection
    Source selector (native/ai/fantasypros/external/adjusted) does.
    "ML-only means ML-only" -- a lineup built with strict_source=True
    can never contain a hidden mixture of projection sources for the
    PROJECTION value itself. Ceiling/floor still fall back to the pool's
    own independent value in strict mode too (same as the existing
    FantasyPros precedent) -- the frozen Big Money ML models don't
    estimate ceiling/floor, only a point projection, so there is no ML
    ceiling/floor to be strict about; this is a documented, deliberate
    choice, not an oversight."""
    projection_overrides = projection_overrides or {}
    players = []
    skipped = []
    excluded_missing_source = []
    for record in pool_doc.get("players", []):
        # Milestone 30.1: optimizer_eligible (confirmed starting pitcher /
        # confirmed starting hitter, see dfs/eligibility.py) is now the
        # sole selection gate -- replaces the old lineup_status=="active"
        # check, which conflated match/projection-availability status
        # with real starter confirmation.
        if not record.get("optimizer_eligible"):
            continue
        # PROBABLE FIX milestone: "Use Probable Starters" optimizer
        # setting, ON by default (this branch is only reached when the
        # user has explicitly turned it OFF) -- excludes a real,
        # evidence-based probable starter from THIS build only; a
        # CONFIRMED starter is never affected either way.
        if exclude_probable_starters and _is_probable_starter(record):
            continue

        override = projection_overrides.get(record.get("mlb_player_id")) if record.get("mlb_player_id") else None

        if strict_source:
            if override is None or override.get("projection") is None:
                excluded_missing_source.append(record["name"])
                continue
            projection = override.get("projection")
        else:
            projection = override.get("projection") if override and override.get("projection") is not None else record.get("projection")

        ceiling = override.get("ceiling") if override and override.get("ceiling") is not None else record.get("ceiling")
        floor = override.get("floor") if override and override.get("floor") is not None else record.get("floor")

        if projection is None or ceiling is None:
            skipped.append(record["name"])
            continue
        players.append(OptimizerPlayer(
            key=record["dk_player_id"], mlb_player_id=record.get("mlb_player_id"), name=record["name"],
            team=record["team"], opponent=record.get("opponent"), game_id=record.get("game_id"),
            player_type=record["player_type"], dk_positions=list(record.get("dk_positions") or []),
            salary=record["salary"], projection=projection, ceiling=ceiling,
            floor=floor, risk_score=record.get("risk_score"), confidence=record.get("confidence"),
            season_sample_size=record.get("season_sample_size"),
        ))
    return players, skipped, excluded_missing_source


def _coverage_summary(pool_doc: dict, players: list, skipped: list, excluded_missing_source: list, projection_source: str, strict_source: bool) -> dict:
    """Milestone 32.6 Part 2: the counts `--validate-only` needs to show a
    real Stage/Reason diagnostic instead of the generic per-position
    "Only 0 eligible P player(s) available" wall of text -- those numbers
    (skipped/excluded) were already computed by _build_optimizer_players
    but, before this milestone, were only ever printed as plain stdout
    text and ONLY in the non-validate-only branch, so the dashboard's
    pre-flight check (which always runs --validate-only) never saw them
    at all. Also doubles as the Projection Source dropdown's
    "Coverage: X/Y eligible players" indicator (Part 3)."""
    pool_size = len(pool_doc.get("players", []))
    optimizer_eligible = len(players) + len(skipped) + len(excluded_missing_source)
    return {
        "pool_size": pool_size,
        "optimizer_eligible": optimizer_eligible,
        "usable_for_build": len(players),
        "skipped_missing_projection": len(skipped),
        "excluded_missing_source": len(excluded_missing_source),
        "projection_source": projection_source,
        "strict_source": strict_source,
    }


def _coverage_diagnostics(coverage: dict) -> list:
    """A leading, human-readable Stage/Reason line for each way the
    player pool shrank before it ever reached position/salary/stack
    checks -- prepended to pre_solve_diagnostics()'s generic roster-slot
    counts (which, on their own, just say "0 eligible P available" with
    no indication WHY), never replacing them."""
    reasons = []
    if coverage["excluded_missing_source"] > 0:
        reasons.append(
            f"Stage: Projection Source / Reason: {coverage['excluded_missing_source']} otherwise-eligible "
            f"player(s) have no {coverage['projection_source']} projection for this slate -- strict source "
            f"selected, never mixed with another source. Choose a different Projection Source or wait for "
            f"{coverage['projection_source']} to be generated for this slate."
        )
    if coverage["skipped_missing_projection"] > 0:
        reasons.append(
            f"Stage: Player Pool / Reason: {coverage['skipped_missing_projection']} otherwise-eligible player(s) "
            f"have no projection/ceiling at all for this slate yet -- research has not been generated for this "
            f"date. Run Admin Refresh Data for this slate's date first."
        )
    if coverage["usable_for_build"] == 0 and coverage["optimizer_eligible"] == 0:
        reasons.append(
            f"Stage: Player Pool / Reason: 0 of {coverage['pool_size']} pool player(s) are optimizer-eligible "
            f"(confirmed starting pitcher / confirmed starting hitter) yet -- lineups have not been posted for "
            f"this slate's games."
        )
    return reasons


def _validate_only_errors(coverage: dict, solve_errors: list) -> list:
    """Hotfix: `--validate-only`'s final error list used to be
    `_coverage_diagnostics(coverage) + solve_errors` unconditionally --
    meaning ANY strict-source exclusion or missing-projection skip
    (`coverage["excluded_missing_source"] > 0` /
    `coverage["skipped_missing_projection"] > 0`), even a single player
    out of hundreds, refused to build at all, regardless of whether the
    REMAINING players (already correctly excluded by
    _build_optimizer_players) were more than enough to satisfy the
    roster. Confirmed live against a real DRAFTKINGS_UNOFFICIAL_LIVE
    slate: Big Money ML excluded 20 of 122 eligible players for missing
    ML coverage, leaving 102 -- objectively plenty -- yet the build was
    refused solely because the excluded count was nonzero.

    `solve_errors` (leverage-mode config errors + pre_solve_diagnostics()
    -- the REAL, authoritative roster/salary/stack feasibility check
    against the ALREADY-shrunken player list) is the only thing that
    should ever refuse a build. The coverage-shrinkage explanation from
    _coverage_diagnostics() is prepended ONLY when solve_errors is
    already non-empty, i.e. only when the shrunken pool actually turned
    out to be infeasible -- giving a combined, honest message ("N
    players excluded for missing source coverage, leaving 0 catchers
    available") instead of either a silent block or a confusing
    solver-only message with no explanation of why the pool shrank.
    When the shrunken pool is still feasible, this returns [] and the
    build proceeds -- the exact counts remain visible either way via
    `coverage` itself (excluded_missing_source / skipped_missing_projection
    / usable_for_build), which the dashboard's Projection Source dropdown
    already surfaces regardless of whether `errors` is empty."""
    if not solve_errors:
        return []
    return _coverage_diagnostics(coverage) + solve_errors


def _load_ownership(ownership_path: str):
    path = Path(ownership_path)
    return _load_persisted_json(path, f"Ownership snapshot not found locally ({path}) or in object storage.")


def _merge_ownership(players, ownership_doc: dict):
    """Attaches projected_ownership / leverage_score / ownership_confidence
    onto each OptimizerPlayer by dk_player_id (mlb_player_id fallback).
    Never touches projection/ceiling/floor -- ownership is joined data,
    not a re-score. Players absent from the ownership snapshot simply
    keep their default None ownership fields."""
    by_dk_id = {r["dk_player_id"]: r for r in ownership_doc.get("players", [])}
    by_mlb_id = {r["mlb_player_id"]: r for r in ownership_doc.get("players", []) if r.get("mlb_player_id")}
    matched = 0
    for p in players:
        record = by_dk_id.get(p.key) or (by_mlb_id.get(p.mlb_player_id) if p.mlb_player_id else None)
        if record is None:
            continue
        p.projected_ownership = record.get("projected_ownership")
        p.leverage_score = record.get("leverage_score")
        p.ownership_confidence = record.get("ownership_confidence")
        matched += 1
    return matched


def _parse_key_value(arg: str, flag: str):
    if "=" not in arg:
        raise SystemExit(f"{flag} expects NAME=FRACTION (e.g. \"Paul Skenes=0.5\"), got {arg!r}")
    name, _, value = arg.rpartition("=")
    try:
        fraction = float(value)
    except ValueError:
        raise SystemExit(f"{flag} fraction must be numeric, got {value!r} in {arg!r}")
    return name, fraction


def _fmt(value, digits=1):
    return f"{value:.{digits}f}" if value is not None else "--"


def _print_lineup(lineup) -> None:
    print(f"LINEUP {lineup.index}")
    print()
    for a in lineup.assignments:
        print(f"{a.slot:<4}{a.name}")
    print()
    print(f"Salary: {lineup.salary}")
    print(f"Projection: {_fmt(lineup.projection)}")
    print(f"Ceiling: {_fmt(lineup.ceiling)}")
    print(f"Average Confidence: {_fmt(lineup.average_confidence)}")
    print(f"Average Risk: {_fmt(lineup.average_risk)}")
    if lineup.sum_ownership is not None:
        print(f"Sum Ownership: {_fmt(lineup.sum_ownership)}%")
        print(f"Average Ownership: {_fmt(lineup.average_ownership)}%")
        print(f"Max Ownership: {_fmt(lineup.max_ownership)}%")
        print(f"Players Above Chalk Threshold: {lineup.players_above_chalk_threshold}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate legal DraftKings Classic MLB lineups from a saved DFS player pool.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--pool", required=True, help="Path to a dk_player_pool_<timestamp>.json file")
    parser.add_argument("--ownership", default=None, help="Optional path to an ownership_<timestamp>.json snapshot")
    parser.add_argument(
        "--projection-overrides", default=None,
        help="Optional path to a {mlb_player_id: {projection, ceiling, floor}} JSON file (Milestone 17 Projection "
             "Source selector) -- substitutes these values for matching players for THIS solve only; never "
             "modifies the pool file on disk.",
    )
    parser.add_argument(
        "--strict-projection-source", action="store_true",
        help="Milestone 32.4 (Big Money ML): a player with no --projection-overrides entry is EXCLUDED from the "
             "optimizer pool entirely instead of falling back to the pool's own independent projection. Never "
             "used by the existing native/ai/fantasypros/external/adjusted sources -- ML-only.",
    )
    parser.add_argument("--projection-source", default="independent", help="Provenance label persisted on the saved lineup set (e.g. 'big_money_ml', 'native', 'ai', 'independent').")
    parser.add_argument("--pitcher-model-version", default=None, help="Provenance only -- Big Money ML Pitcher Model version used, if --projection-source=big_money_ml.")
    parser.add_argument("--hitter-model-version", default=None, help="Provenance only -- Big Money ML Hitter Model version used, if --projection-source=big_money_ml.")
    parser.add_argument("--pitcher-projection-snapshot-generated-at", default=None, help="Provenance only -- generated_at of the Big Money ML pitcher snapshot consumed for this build.")
    parser.add_argument("--hitter-projection-snapshot-generated-at", default=None, help="Provenance only -- generated_at of the Big Money ML hitter snapshot consumed for this build.")
    parser.add_argument("--lineups", type=int, default=1)
    parser.add_argument("--objective", choices=["projection", "ceiling", "balanced", "leverage"], default="projection")
    parser.add_argument("--min-unique", type=int, default=1)
    parser.add_argument("--stack-size", type=int, default=None)
    parser.add_argument("--stack-team", default=None)
    parser.add_argument("--lock", action="append", default=[])
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--max-exposure", action="append", default=[])
    parser.add_argument("--max-exposure-default", type=float, default=1.0)
    parser.add_argument("--min-exposure", action="append", default=[])
    parser.add_argument("--min-confidence", type=float, default=None)
    parser.add_argument("--min-season-pa", type=float, default=None)
    parser.add_argument("--max-player-risk", type=float, default=None)
    parser.add_argument("--max-total-ownership", type=float, default=None)
    parser.add_argument("--max-player-ownership", type=float, default=None)
    parser.add_argument("--min-player-ownership", type=float, default=None)
    parser.add_argument("--min-salary", type=int, default=None, help="Minimum total lineup salary (a spend floor; the cap is always enforced separately)")
    parser.add_argument(
        "--allow-pitcher-vs-hitter", action="store_true",
        help="Allow rostering a hitter against one of the lineup's own pitchers (off by default)",
    )
    parser.add_argument(
        "--exclude-probable-starters", action="store_true",
        help="PROBABLE FIX: exclude real, evidence-based probable starters from this build -- 'Use Probable "
             "Starters' is ON by default (probable starters included); pass this flag to turn it off.",
    )
    parser.add_argument(
        "--time-limit-seconds", type=float, default=None,
        help="Override the CP-SAT per-lineup time budget (default: config.optimizer_config.SOLVER_MAX_TIME_SECONDS)",
    )
    parser.add_argument(
        "--interactive", action="store_true",
        help="Use config.optimizer_config.INTERACTIVE_SOLVER_MAX_TIME_SECONDS instead of the batch default "
             "(ignored if --time-limit-seconds is also given)",
    )
    parser.add_argument(
        "--validate-only", action="store_true",
        help="Skip solving/saving entirely -- print {\"errors\": [...]} for pre-solve validation (dashboard use)",
    )
    parser.add_argument("--output-root", default="lineups")
    args = parser.parse_args()

    pool_doc = _load_pool(args.pool)
    projection_overrides = _load_projection_overrides(args.projection_overrides) if args.projection_overrides else None
    players, skipped, excluded_missing_source = _build_optimizer_players(
        pool_doc, projection_overrides, strict_source=args.strict_projection_source,
        exclude_probable_starters=args.exclude_probable_starters,
    )

    if not args.validate_only:
        print("=" * 70)
        print("DRAFTKINGS LINEUP OPTIMIZER")
        print("=" * 70)
        print(f"\nSlate date: {args.date}")
        print(f"Player pool: {args.pool}")
        print(f"Projection source: {args.projection_source}")
        print(f"Active players available: {len(players)}")
        if projection_overrides:
            print(f"Projection overrides: {args.projection_overrides} ({len(projection_overrides)} player(s))")
        if skipped:
            print(f"Skipped (active but missing projection/ceiling -- never invented): {len(skipped)}")
        if excluded_missing_source:
            print(f"Excluded (strict {args.projection_source} source -- no ML projection, never mixed with another source): {len(excluded_missing_source)}")

    ownership_doc = None
    if args.ownership:
        ownership_doc = _load_ownership(args.ownership)
        matched = _merge_ownership(players, ownership_doc)
        if not args.validate_only:
            print(f"Ownership snapshot: {args.ownership} ({matched}/{len(players)} players matched)")
    if not args.validate_only:
        print()

    time_limit_seconds = args.time_limit_seconds
    if time_limit_seconds is None and args.interactive:
        time_limit_seconds = INTERACTIVE_SOLVER_MAX_TIME_SECONDS

    settings = OptimizerSettings(
        objective_mode=args.objective, num_lineups=args.lineups, min_unique=args.min_unique,
        stack_size=args.stack_size, stack_team=args.stack_team, locks=list(args.lock), excludes=list(args.exclude),
        max_exposure=dict(_parse_key_value(a, "--max-exposure") for a in args.max_exposure),
        max_exposure_default=args.max_exposure_default,
        min_exposure=dict(_parse_key_value(a, "--min-exposure") for a in args.min_exposure),
        min_confidence=args.min_confidence, min_season_pa=args.min_season_pa, max_player_risk=args.max_player_risk,
        max_total_ownership=args.max_total_ownership, max_player_ownership=args.max_player_ownership,
        min_player_ownership=args.min_player_ownership, min_salary=args.min_salary,
        allow_pitcher_vs_hitter=args.allow_pitcher_vs_hitter, time_limit_seconds=time_limit_seconds,
    )

    leverage_errors = []
    if args.objective == "leverage" and not any(p.leverage_score is not None for p in players):
        leverage_errors.append("--objective leverage requires --ownership (no player has a leverage_score).")

    if args.validate_only:
        coverage = _coverage_summary(pool_doc, players, skipped, excluded_missing_source, args.projection_source, args.strict_projection_source)
        solve_errors = list(leverage_errors) + pre_solve_diagnostics(players, settings)
        errors = _validate_only_errors(coverage, solve_errors)
        print(json.dumps({"errors": errors, "coverage": coverage}))
        return

    if leverage_errors:
        print(f"CONFIGURATION ERROR: {leverage_errors[0]}")
        return

    try:
        output = generate_lineups(players, settings)
    except OptimizerConfigError as e:
        print(f"CONFIGURATION ERROR: {e}")
        return

    result = output.result
    for lineup in result.lineups:
        _print_lineup(lineup)

    print(f"Generated {result.generated} / {result.requested} requested lineup(s).")
    if result.stopped_reason:
        print(f"NOTE: {result.stopped_reason}")
    print()

    if result.lineups:
        violations = validate_lineup_set(
            result.lineups, output.players_by_key, settings, output.locked_keys, output.excluded_keys,
            output.exposure_caps, settings.min_unique,
        )
        bad = {idx: v for idx, v in violations.items() if v}
        if bad:
            print("INDEPENDENT VALIDATION FAILED (this should never happen -- reporting anyway):")
            for idx, probs in bad.items():
                for p in probs:
                    print(f"  Lineup {idx}: {p}")
        else:
            print(f"Independent validation: all {len(result.lineups)} lineup(s) PASSED.")
        print()

        exposure_counts = {}
        for lineup in result.lineups:
            for key in lineup.player_keys():
                exposure_counts[key] = exposure_counts.get(key, 0) + 1
        print("Exposure table:")
        for key, count in sorted(exposure_counts.items(), key=lambda kv: -kv[1]):
            player = output.players_by_key[key]
            pct = 100.0 * count / len(result.lineups)
            print(f"  {player.name:<28} {count}/{len(result.lineups)} ({pct:.0f}%)")
        print()

        stack_counts = {}
        for lineup in result.lineups:
            if lineup.primary_stack_team:
                key = f"{lineup.primary_stack_team} ({lineup.primary_stack_size})"
                stack_counts[key] = stack_counts.get(key, 0) + 1
        print("Stack distribution:")
        for key, count in sorted(stack_counts.items(), key=lambda kv: -kv[1]):
            print(f"  {key}: {count} lineup(s)")
        print()

    generated_at = datetime.now(timezone.utc).isoformat()
    ts = timestamp_tag(generated_at)
    document = build_lineup_set_document(
        args.date, generated_at, args.pool, pool_doc.get("pitcher_snapshot_path"), pool_doc.get("batter_snapshot_path"),
        OPTIMIZER_VERSION, settings.to_dict(), result, output.players_by_key,
        ownership_snapshot_path=args.ownership,
        projection_source=args.projection_source,
        slate_id=pool_doc.get("selected_slate_id"),
        pitcher_model_version=args.pitcher_model_version,
        hitter_model_version=args.hitter_model_version,
        pitcher_projection_snapshot_generated_at=args.pitcher_projection_snapshot_generated_at,
        hitter_projection_snapshot_generated_at=args.hitter_projection_snapshot_generated_at,
        excluded_missing_projection_source=excluded_missing_source,
    )
    json_path = save_lineup_set_json(document, args.date, ts, output_root=args.output_root)
    csv_path = save_lineup_set_csv(document, args.date, ts, output_root=args.output_root)

    print("Files written:")
    print(f"  - {json_path}")
    print(f"  - {csv_path}")


if __name__ == "__main__":
    main()
