/**
 * Renders every NFL dashboard card's real value from a real
 * /api/nfl/data payload, so the dashboard's own scoring can be verified
 * against production data without guessing.
 *
 * Usage: npx tsx scripts/verifyNflDashboard.ts <payload.json>
 */
import { readFileSync } from "node:fs";

import {
  buildStacks,
  injuryWatch,
  opponentImpliedTotalFor,
  positionHasNoSpread,
  scoreSlate,
  slateReadiness,
  type ScoredPlayer,
} from "../lib/nfl/dashboardMetrics";
import type { NflSlateData } from "../lib/nfl/types";

const slate: NflSlateData = JSON.parse(readFileSync(process.argv[2], "utf8"));
const scored = scoreSlate(slate);
const f = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "—" : v.toFixed(d));

console.log(`SLATE ${slate.draft_group_id} "${(slate.slate_name ?? "").trim()}" ${slate.slate_date}`);
console.log(`  games=${slate.game_count} players=${slate.player_count} status=${slate.data_status} vegas=${slate.vegas_source_provenance}`);
console.log(`  scored players=${scored.length}/${slate.player_count}`);

const priced = slate.games.filter((g) => g.total !== null);
const hi = priced.length ? priced.reduce((a, b) => ((b.total ?? 0) > (a.total ?? 0) ? b : a)) : null;
const lo = priced.length ? priced.reduce((a, b) => ((b.total ?? 0) < (a.total ?? 0) ? b : a)) : null;
const implied = slate.games
  .flatMap((g) => [
    { team: g.lock?.home_team ?? null, total: g.home_implied_total },
    { team: g.lock?.away_team ?? null, total: g.away_implied_total },
  ])
  .filter((r): r is { team: string; total: number } => r.team !== null && r.total !== null);
const hiImp = implied.length ? implied.reduce((a, b) => (b.total > a.total ? b : a)) : null;

console.log("\n-- GAME ENVIRONMENT --");
console.log(`  Highest Game Total        : ${hi ? `${hi.game_description} ${f(hi.total)}` : "AWAITING VEGAS"}`);
console.log(`  Lowest Game Total         : ${lo ? `${lo.game_description} ${f(lo.total)}` : "AWAITING VEGAS"}`);
console.log(`  Highest Implied Team Total: ${hiImp ? `${hiImp.team} ${f(hiImp.total)}` : "AWAITING VEGAS"}`);

const best = (pos: string, key: (p: ScoredPlayer) => number | null) => {
  const pool = scored.filter((p) => p.row.position === pos && key(p) !== null);
  return pool.length ? pool.reduce((a, b) => ((key(b) ?? 0) > (key(a) ?? 0) ? b : a)) : null;
};
const topBy = (key: (p: ScoredPlayer) => number | null) => {
  const pool = scored.filter((p) => key(p) !== null);
  return pool.length ? pool.reduce((a, b) => ((key(b) ?? 0) > (key(a) ?? 0) ? b : a)) : null;
};

console.log("\n-- BEST BY POSITION (Big Money score) --");
for (const pos of ["QB", "RB", "WR", "TE"]) {
  const p = best(pos, (x) => x.bigMoneyScore);
  console.log(`  Best ${pos.padEnd(3)}: ${p ? `${p.row.name} (${p.row.team}) BM=${f(p.bigMoneyScore)} proj=${f(p.projection)} val=${f(p.value, 2)}` : "AWAITING PROJECTION"}`);
}
const dstPool = scored
  .filter((p) => p.row.position === "DST")
  .map((p) => ({ p, opp: opponentImpliedTotalFor(p.row, slate) }))
  .filter((r): r is { p: ScoredPlayer; opp: number } => r.opp !== null);
const bestDst = dstPool.length ? dstPool.reduce((a, b) => (b.opp < a.opp ? b : a)) : null;
console.log(`  Best DST: ${bestDst ? `${bestDst.p.row.name} opp_implied=${f(bestDst.opp)}` : "AWAITING VEGAS"}  [baseline_model=${positionHasNoSpread(scored, "DST")}]`);

console.log("\n-- PLAY TYPES --");
const cash = topBy((p) => p.cashScore);
const gpp = topBy((p) => p.gppScore);
const val = topBy((p) => p.value);
const lev = topBy((p) => p.leverage);
const own = topBy((p) => p.ownership);
console.log(`  Top Cash    : ${cash ? `${cash.row.name} cash=${f(cash.cashScore)} floor=${f(cash.floor)}` : "AWAITING PROJECTION"}`);
console.log(`  Top GPP     : ${gpp ? `${gpp.row.name} gpp=${f(gpp.gppScore)} ceil=${f(gpp.ceiling)}` : "AWAITING PROJECTION"}`);
console.log(`  Top Value   : ${val ? `${val.row.name} ${f(val.value, 2)} pts/$1K` : "AWAITING PROJECTION"}`);
console.log(`  Top Leverage: ${lev ? `${lev.row.name} lev=${f(lev.leverage, 2)} own=${f(lev.ownership)}%` : "AWAITING OWNERSHIP"}`);
console.log(`  Highest Own : ${own ? `${own.row.name} ${f(own.ownership)}%` : "AWAITING OWNERSHIP"}`);

const qbStacks = buildStacks(scored, 1, false);
const gameStacks = buildStacks(scored, 2, true);
console.log("\n-- STACKS --");
console.log(`  QB stacks built: ${qbStacks.length}; game stacks built: ${gameStacks.length}`);
for (const s of qbStacks.slice(0, 2)) {
  console.log(`   QB  ${s.qb.row.name} + ${s.partners.map((p) => p.row.name).join(", ")} | proj=${f(s.combinedProjection)} ceil=${f(s.combinedCeiling)} own=${f(s.combinedOwnership)} tmImp=${f(s.teamImpliedTotal)} gmTot=${f(s.gameTotal)}`);
}
for (const s of gameStacks.slice(0, 2)) {
  console.log(`   GM  ${s.qb.row.name} + ${s.partners.map((p) => p.row.name).join(", ")} + BB ${s.bringBack?.row.name ?? "—"} | proj=${f(s.combinedProjection)} ceil=${f(s.combinedCeiling)} gmTot=${f(s.gameTotal)}`);
}

console.log("\n-- TOP PLAYS BY POSITION (first 3 each) --");
for (const pos of ["QB", "RB", "WR", "TE", "DST"]) {
  const rows = scored.filter((p) => p.row.position === pos).sort((a, b) => (a.bigMoneyRank ?? 9999) - (b.bigMoneyRank ?? 9999));
  console.log(`  ${pos}:`);
  for (const p of rows.slice(0, 3)) {
    console.log(
      `    #${String(p.bigMoneyRank ?? "—").padStart(2)} ${p.row.name.padEnd(22)} sal=${String(p.row.salary).padStart(5)} proj=${f(p.projection).padStart(5)} fl=${f(p.floor).padStart(5)} ce=${f(p.ceiling).padStart(5)} val=${f(p.value, 2).padStart(5)} own=${f(p.ownership).padStart(5)} lev=${f(p.leverage, 2).padStart(6)} tmImp=${f(p.teamImpliedTotal).padStart(5)} gmTot=${f(p.gameTotal).padStart(5)} BM=${f(p.bigMoneyScore).padStart(5)}`,
    );
  }
}

console.log("\n-- INJURY WATCH --");
const inj = injuryWatch(slate);
console.log(`  ${inj.length} non-ACTIVE players`);
for (const p of inj.slice(0, 5)) console.log(`    ${p.name} (${p.position} ${p.team}) ${p.status_info.normalized_status}`);

console.log("\n-- SLATE READINESS --");
for (const r of slateReadiness(slate)) console.log(`  [${r.ok ? "OK " : "!! "}] ${r.label.padEnd(20)} ${r.detail}`);

const nullChecks = scored.filter((p) => p.projection === 0 && p.row.projection?.projection !== 0);
console.log(`\nFABRICATED-ZERO CHECK: ${nullChecks.length === 0 ? "PASS (no synthesized zeros)" : `FAIL (${nullChecks.length})`}`);
