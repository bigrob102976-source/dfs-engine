// NFL dashboard scoring. Every number here is derived ONLY from real
// backend values (Big Money Native projection/floor/ceiling, Big Money
// Native ownership, real SportsGameOdds game context, DraftKings salary
// and status). Nothing is invented and nothing is defaulted to zero: a
// player missing an input a score depends on is EXCLUDED from that
// score and reported through an honest reason, never ranked on a
// fabricated 0. See UNAVAILABLE_REASONS below.

import type { NflPlayerRow, NflSlateData } from "./types";

export type UnavailableReason =
  | "AWAITING_PROJECTION"
  | "AWAITING_OWNERSHIP"
  | "AWAITING_VEGAS"
  | "INJURY_STATUS_PENDING"
  | "NOT_APPLICABLE";

export interface ScoredPlayer {
  row: NflPlayerRow;
  projection: number;
  floor: number | null;
  ceiling: number | null;
  ownership: number | null;
  /** Points per $1,000 of salary. */
  value: number;
  /** Ceiling points per $1,000 of salary. */
  ceilingValue: number | null;
  /** Team implied total from real odds, null when Vegas is unavailable. */
  teamImpliedTotal: number | null;
  gameTotal: number | null;
  leverage: number | null;
  cashScore: number | null;
  gppScore: number | null;
  bigMoneyScore: number | null;
  bigMoneyRank: number | null;
}

/** Points per $1,000 -- the standard DFS value unit. */
export function perThousand(points: number, salary: number): number | null {
  if (!Number.isFinite(points) || !Number.isFinite(salary) || salary <= 0) return null;
  return (points / salary) * 1000;
}

/** Which side of the game this player's team is on, from real odds only. */
export function teamImpliedTotalFor(row: NflPlayerRow, slate: NflSlateData): number | null {
  const game = slate.games.find((g) => g.game_id === row.game_id);
  if (!game || !game.lock) return null;
  if (game.home_implied_total === null && game.away_implied_total === null) return null;
  if (game.lock.home_team && row.team === game.lock.home_team) return game.home_implied_total;
  if (game.lock.away_team && row.team === game.lock.away_team) return game.away_implied_total;
  return null;
}

/**
 * The opposing team's implied total, from real odds only.
 *
 * This is the ONLY honest way to rank DST on this slate. The Big Money
 * Native DST artifact is a declared positional_mean_baseline (see
 * data/models/nfl/dst/v2/metadata.json: model_family
 * "positional_mean_baseline", positional_mean 5.969), so it returns the
 * same projection, floor and ceiling for every defense -- verified on
 * 2026-09-13, where all 16 DST scored an identical 5.97/0/13.3. Ranking
 * defenses by that number would present a constant as an opinion.
 * Opponent implied total is real SportsGameOdds data and genuinely
 * separates spots; the UI says so wherever it is used.
 */
export function opponentImpliedTotalFor(row: NflPlayerRow, slate: NflSlateData): number | null {
  const game = slate.games.find((g) => g.game_id === row.game_id);
  if (!game || !game.lock) return null;
  if (game.home_implied_total === null && game.away_implied_total === null) return null;
  if (game.lock.home_team && row.team === game.lock.home_team) return game.away_implied_total;
  if (game.lock.away_team && row.team === game.lock.away_team) return game.home_implied_total;
  return null;
}

/**
 * True when every scored player at this position shares one projection,
 * i.e. the underlying artifact is a positional baseline rather than a
 * discriminating model. Used to refuse a "best at position" ranking that
 * would be meaningless.
 */
export function positionHasNoSpread(scored: ScoredPlayer[], position: string): boolean {
  const vals = scored.filter((p) => p.row.position === position).map((p) => p.projection);
  if (vals.length < 2) return false;
  return new Set(vals.map((v) => Math.round(v * 100))).size === 1;
}

function mean(xs: number[]): number {
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}

function stdev(xs: number[], mu: number): number {
  if (xs.length < 2) return 0;
  return Math.sqrt(xs.reduce((a, b) => a + (b - mu) * (b - mu), 0) / (xs.length - 1));
}

/**
 * Z-score within a comparison group. Returns 0 only when the group has
 * no spread at all (every player identical), which is a genuine "no
 * signal" case rather than missing data.
 */
function zScores(values: number[]): number[] {
  const mu = mean(values);
  const sd = stdev(values, mu);
  if (sd === 0) return values.map(() => 0);
  return values.map((v) => (v - mu) / sd);
}

/**
 * Leverage: ceiling-per-dollar weighed against projected ownership.
 * A player with real ceiling value that the field is under-rostering
 * scores highest. Requires BOTH a ceiling and an ownership projection --
 * null otherwise, never 0.
 *
 * ownership is a percentage (0-100). The +5 damping keeps very low
 * ownership from producing a near-infinite score off a rounding artifact.
 */
export function computeLeverage(ceilingValue: number | null, ownership: number | null): number | null {
  if (ceilingValue === null || ownership === null) return null;
  return (ceilingValue * 10) / (ownership + 5);
}

/**
 * Cash score -- rewards floor, salary efficiency, a good scoring
 * environment and role certainty, in that order of weight. Deliberately
 * ignores ownership: in cash games the field's roster rates do not
 * change what wins.
 *
 * Weights (documented so a reader can reproduce the ranking):
 *   0.45  floor per $1,000        -- the stability term
 *   0.35  median projection per $1,000 -- the efficiency term
 *   0.12  team implied total      -- scoring environment
 *   0.08  role certainty          -- ACTIVE vs questionable
 * Scaled to a 0-100 display via a logistic on the weighted z-sum.
 */
const CASH_WEIGHTS = { floor: 0.45, value: 0.35, environment: 0.12, certainty: 0.08 };

/**
 * GPP score -- rewards ceiling, spike upside over the median, game
 * environment and leverage against the field.
 *
 *   0.38  ceiling per $1,000
 *   0.20  spike upside (ceiling above median, relative)
 *   0.15  game total            -- shootout environment
 *   0.27  leverage              -- ceiling the field is under-owning
 */
const GPP_WEIGHTS = { ceiling: 0.38, upside: 0.2, gameTotal: 0.15, leverage: 0.27 };

/** Squash a weighted z-sum into a readable 0-100 score. */
function toDisplayScore(z: number): number {
  return Math.round(1000 / (1 + Math.exp(-z))) / 10;
}

function certaintyOf(row: NflPlayerRow): number {
  switch (row.status_info.normalized_status) {
    case "ACTIVE":
      return 1;
    case "QUESTIONABLE":
      return 0.6;
    case "DOUBTFUL":
      return 0.2;
    case "OUT":
    case "INACTIVE":
    case "IR":
      return 0;
    default:
      // UNKNOWN means DraftKings sent a status this project has not seen.
      // Treated as reduced certainty, never as "assumed healthy".
      return 0.5;
  }
}

/**
 * Scores every player that has the inputs a score needs. Players are
 * compared WITHIN their own position, because raw fantasy points are not
 * comparable across QB and DST.
 */
export function scoreSlate(slate: NflSlateData): ScoredPlayer[] {
  const base: ScoredPlayer[] = [];

  for (const row of slate.players) {
    const projection = row.projection?.projection ?? null;
    if (projection === null) continue; // AWAITING_PROJECTION -- never scored as 0
    const value = perThousand(projection, row.salary);
    if (value === null) continue;

    const ceiling = row.projection?.ceiling ?? null;
    const floor = row.projection?.floor ?? null;
    const ownership = row.ownership?.ownership_projection ?? null;
    const ceilingValue = ceiling === null ? null : perThousand(ceiling, row.salary);
    const teamImpliedTotal = teamImpliedTotalFor(row, slate);
    const gameTotal = row.matchup?.total ?? null;

    base.push({
      row,
      projection,
      floor,
      ceiling,
      ownership,
      value,
      ceilingValue,
      teamImpliedTotal,
      gameTotal,
      leverage: computeLeverage(ceilingValue, ownership),
      cashScore: null,
      gppScore: null,
      bigMoneyScore: null,
      bigMoneyRank: null,
    });
  }

  // Score within position so the comparison is apples to apples.
  const byPosition = new Map<string, ScoredPlayer[]>();
  for (const p of base) {
    const list = byPosition.get(p.row.position) ?? [];
    list.push(p);
    byPosition.set(p.row.position, list);
  }

  for (const group of byPosition.values()) {
    // A term only contributes for players that actually have it. Players
    // missing a term are scored on the remaining terms with the weights
    // renormalised, rather than being handed a 0 for the missing piece.
    const floorZ = partialZ(group, (p) => (p.floor === null ? null : perThousand(p.floor, p.row.salary)));
    const valueZ = partialZ(group, (p) => p.value);
    const envZ = partialZ(group, (p) => p.teamImpliedTotal);
    const ceilZ = partialZ(group, (p) => p.ceilingValue);
    const upsideZ = partialZ(group, (p) =>
      p.ceiling === null || p.projection <= 0 ? null : (p.ceiling - p.projection) / p.projection,
    );
    const totalZ = partialZ(group, (p) => p.gameTotal);
    const levZ = partialZ(group, (p) => p.leverage);

    group.forEach((p, i) => {
      const certainty = certaintyOf(p.row);
      p.cashScore = weighted([
        [CASH_WEIGHTS.floor, floorZ[i]],
        [CASH_WEIGHTS.value, valueZ[i]],
        [CASH_WEIGHTS.environment, envZ[i]],
        // certainty is already 0-1; centre it so it behaves like a z term
        [CASH_WEIGHTS.certainty, certainty * 2 - 1],
      ]);
      p.gppScore = weighted([
        [GPP_WEIGHTS.ceiling, ceilZ[i]],
        [GPP_WEIGHTS.upside, upsideZ[i]],
        [GPP_WEIGHTS.gameTotal, totalZ[i]],
        [GPP_WEIGHTS.leverage, levZ[i]],
      ]);
      p.bigMoneyScore =
        p.cashScore === null && p.gppScore === null
          ? null
          : Math.round(((p.cashScore ?? p.gppScore ?? 0) * 0.5 + (p.gppScore ?? p.cashScore ?? 0) * 0.5) * 10) / 10;
    });

    group
      .filter((p) => p.bigMoneyScore !== null)
      .sort((a, b) => (b.bigMoneyScore ?? 0) - (a.bigMoneyScore ?? 0))
      .forEach((p, i) => {
        p.bigMoneyRank = i + 1;
      });
  }

  return base;
}

/** z-scores over only the players that have the term; null preserved. */
function partialZ(group: ScoredPlayer[], pick: (p: ScoredPlayer) => number | null): (number | null)[] {
  const idx: number[] = [];
  const vals: number[] = [];
  group.forEach((p, i) => {
    const v = pick(p);
    if (v !== null && Number.isFinite(v)) {
      idx.push(i);
      vals.push(v);
    }
  });
  const out: (number | null)[] = group.map(() => null);
  if (vals.length === 0) return out;
  const zs = zScores(vals);
  idx.forEach((gi, k) => {
    out[gi] = zs[k];
  });
  return out;
}

/** Weighted sum over available terms only, renormalised by their weight. */
function weighted(terms: [number, number | null][]): number | null {
  let acc = 0;
  let wsum = 0;
  for (const [w, z] of terms) {
    if (z === null) continue;
    acc += w * z;
    wsum += w;
  }
  if (wsum === 0) return null;
  return toDisplayScore(acc / wsum);
}

export interface StackCandidate {
  qb: ScoredPlayer;
  partners: ScoredPlayer[];
  bringBack: ScoredPlayer | null;
  combinedProjection: number;
  combinedCeiling: number | null;
  combinedOwnership: number | null;
  leverage: number | null;
  gameTotal: number | null;
  teamImpliedTotal: number | null;
}

/**
 * QB + pass-catcher stacks with an optional opposing bring-back, ranked
 * by combined ceiling. Only real teammates in the same real game are
 * paired; a QB with no scored pass catchers yields no stack rather than
 * a padded one.
 */
export function buildStacks(scored: ScoredPlayer[], partnerCount: number, withBringBack: boolean): StackCandidate[] {
  const qbs = scored.filter((p) => p.row.position === "QB" && p.ceiling !== null);
  const out: StackCandidate[] = [];

  for (const qb of qbs) {
    const partners = scored
      .filter(
        (p) =>
          p.row.team === qb.row.team &&
          p.row.game_id === qb.row.game_id &&
          (p.row.position === "WR" || p.row.position === "TE") &&
          p.ceiling !== null,
      )
      .sort((a, b) => (b.ceiling ?? 0) - (a.ceiling ?? 0))
      .slice(0, partnerCount);
    if (partners.length < partnerCount) continue;

    let bringBack: ScoredPlayer | null = null;
    if (withBringBack) {
      bringBack =
        scored
          .filter(
            (p) =>
              p.row.game_id === qb.row.game_id &&
              p.row.team !== qb.row.team &&
              (p.row.position === "WR" || p.row.position === "TE" || p.row.position === "RB") &&
              p.ceiling !== null,
          )
          .sort((a, b) => (b.ceiling ?? 0) - (a.ceiling ?? 0))[0] ?? null;
      if (!bringBack) continue;
    }

    const members = [qb, ...partners, ...(bringBack ? [bringBack] : [])];
    const owns = members.map((m) => m.ownership).filter((o): o is number => o !== null);

    out.push({
      qb,
      partners,
      bringBack,
      combinedProjection: Math.round(members.reduce((a, m) => a + m.projection, 0) * 10) / 10,
      combinedCeiling: members.every((m) => m.ceiling !== null)
        ? Math.round(members.reduce((a, m) => a + (m.ceiling ?? 0), 0) * 10) / 10
        : null,
      combinedOwnership: owns.length === members.length ? Math.round(owns.reduce((a, o) => a + o, 0) * 10) / 10 : null,
      leverage: qb.leverage,
      gameTotal: qb.gameTotal,
      teamImpliedTotal: qb.teamImpliedTotal,
    });
  }

  return out.sort((a, b) => (b.combinedCeiling ?? 0) - (a.combinedCeiling ?? 0));
}

/** Players whose real DraftKings status is anything but ACTIVE. */
export function injuryWatch(slate: NflSlateData): NflPlayerRow[] {
  return slate.players
    .filter((p) => !p.is_team_entity && p.status_info.normalized_status !== "ACTIVE")
    .sort((a, b) => b.salary - a.salary);
}

export interface ReadinessItem {
  label: string;
  ok: boolean;
  detail: string;
}

/** Honest slate readiness -- every line states what is actually true. */
export function slateReadiness(slate: NflSlateData): ReadinessItem[] {
  const posList = ["QB", "RB", "WR", "TE", "DST"];
  const projTotal = posList.reduce((a, p) => a + (slate.projection_coverage[p]?.total ?? 0), 0);
  const projDone = posList.reduce((a, p) => a + (slate.projection_coverage[p]?.projected ?? 0), 0);
  const gamesWithTotal = slate.games.filter((g) => g.total !== null).length;

  return [
    {
      label: "DraftKings pool",
      ok: slate.player_count > 0,
      detail: `${slate.player_count} players across ${slate.game_count} games`,
    },
    {
      label: "Pool freshness",
      ok: slate.data_status === "fresh",
      detail:
        slate.data_status === "fresh"
          ? "Fresh (within 15 minutes)"
          : `STALE — reused snapshot${slate.pool_generated_at_utc ? ` from ${new Date(slate.pool_generated_at_utc).toUTCString()}` : ""}`,
    },
    {
      label: "Projections",
      ok: projTotal > 0 && projDone === projTotal,
      detail: projTotal === 0 ? "AWAITING PROJECTION" : `${projDone}/${projTotal} players (${Math.round((100 * projDone) / projTotal)}%)`,
    },
    {
      label: "Ownership",
      ok: slate.ownership_missing === 0 && slate.ownership_generated > 0,
      detail:
        slate.ownership_generated === 0
          ? "AWAITING OWNERSHIP"
          : `${slate.ownership_generated} generated, ${slate.ownership_missing} without a usable projection`,
    },
    {
      label: "Vegas",
      ok: slate.vegas_configured && gamesWithTotal === slate.games.length && slate.games.length > 0,
      detail: slate.vegas_configured
        ? `${gamesWithTotal}/${slate.games.length} games priced (${slate.vegas_source_provenance})`
        : "AWAITING VEGAS — odds provider not configured",
    },
    {
      label: "Identity resolution",
      ok: slate.identity.unresolved === 0,
      detail: `${slate.identity.resolved}/${slate.identity.total} resolved, ${slate.identity.unresolved} unresolved`,
    },
  ];
}
