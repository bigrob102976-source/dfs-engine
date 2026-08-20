# DraftKings Unofficial Development Data Provider (Milestone 31.2)

> **UNOFFICIAL DRAFTKINGS DEVELOPMENT DATA.** Everything in this package
> talks to DraftKings' undocumented public JSON endpoints. There is no
> published contract for these endpoints -- DraftKings can change field
> names, response shapes, or remove an endpoint entirely, at any time,
> without notice. This provider exists **only** to unblock Big Money DFS
> development before a licensed provider is in place. It is never used
> in the automatic production provider cascade, and its data is never
> trusted for a production pool build. See "Removing this provider"
> below for how to delete it once a licensed provider replaces it.

## Why this exists

`dfs/providers/base.py` has a standing rule: never scrape DraftKings
HTML, automate a login, or depend on undocumented endpoints. That rule
protects **production**. Milestone 31.2 explicitly asked for a
separate, clearly-labeled, **opt-in-only** development data source so
Big Money DFS can be built against real, broad, multi-sport DFS data
instead of narrow hand-built fixtures, while no licensed provider is
configured. Two independent gates keep it from ever running by
accident:

1. It is **never** registered in `dfs/providers/config.py`'s automatic
   priority cascade (`get_configured_provider()`) -- only reachable via
   the existing explicit `DFS_SALARY_PROVIDER=draftkings_unofficial`
   override.
2. Even when explicitly named, it refuses to run unless
   `DK_UNOFFICIAL_ENABLED=true` is **also** set.

Its data is always classified `UNOFFICIAL_DEVELOPMENT_SOURCE`
(`dfs/providers/source_provenance.py`), which is **not** in
`TRUSTED_FOR_PRODUCTION` -- `dfs/pool_builder.py::build_pool()` refuses
to build a production pool from it without an explicit dev-mode
override, exactly like `DEVELOPMENT_MOCK`.

## Confirmed-live endpoints (2026-08-20)

All five require no authentication (no login, no cookies, no API key)
and were confirmed with direct live requests during this milestone's
discovery pass -- not assumed from the 2021 unofficial documentation
this milestone started from (see "Known limitations" for where that
documentation was found to be out of date).

| Endpoint | Purpose | Response shape |
|---|---|---|
| `GET api.draftkings.com/sites/US-DK/sports/v1/sports?format=json` | Every sport DK currently exposes | `{"sports": [...]}` |
| `GET www.draftkings.com/lobby/getcontests?sport={CODE}` | Contests + DraftGroups + GameTypes for one sport | `{"Contests": [...], "DraftGroups": [...], "GameTypes": [...], ...}` |
| `GET api.draftkings.com/draftgroups/v1/draftgroups/{id}/draftables` | Players/entities + games for one slate | `{"draftables": [...], "competitions": [...], ...}` |
| `GET api.draftkings.com/lineups/v1/gametypes/{id}/rules` | Roster/salary-cap rules for one game type | `{"gameTypeId": ..., "lineupTemplate": [...], "salaryCap": {...}, ...}` |
| `GET api.draftkings.com/contests/v1/contests/{id}?format=json` | Full contest detail (payouts, etc.) | `{"contestDetail": {...}}` |

404 was directly observed (an invalid `draftGroupId`) and returns
`{"errorStatus": {"code": ..., "developerMessage": ...}}`. 401/403/429/5xx
paths are handled defensively (see `client.py`) even though deliberately
triggering them live would violate this milestone's "small number of
requests" principle.

**Important, confirmed finding: DraftKings does not publicly expose a
points-per-stat scoring formula through any endpoint discovered.** The
game-type rules endpoint only gives roster/salary-cap structure
(`salaryCap`, `lineupTemplate`, `gameCount`, `teamCount`,
`allowLateSwap`, ...) plus a link to a human-readable help page
(`rulesUrl`). The one machine-usable scoring signal found is a roster
slot's multiplier (e.g. Showdown Captain's 1.5x), and even that is only
present as free text (`positionTipSubtext: "1.5x"`), parsed defensively
by `normalizer.py::_parse_multiplier`. **Per this milestone's explicit
instruction, no scoring-rule table is fabricated anywhere in this
package** -- see `models.py::DkRosterRules`'s docstring.

## The data graph

```
Sport (sportId)
  -> Contests (getcontests?sport=X) -- each carries dg (draftGroupId) + gameTypeId
       -> DraftGroup == this milestone's canonical Slate
            (many contests can share one DraftGroup -- deduplicated;
             see normalizer.py::normalize_draft_groups_to_slates)
            -> Draftables endpoint returns, for that DraftGroup:
                 -> competitions (== SlateGame -- one per real-world event)
                 -> draftables (== players/entities, each tagged with
                    competitionId, rosterSlotId, teamId, salary, position)
       -> GameType (gameTypeId) -> /lineups/v1/gametypes/{id}/rules
            -> roster slots (P/C/1B/... or CPT/UTIL for Showdown, or
               sport-specific equivalents), salary cap, scoring multiplier
```

Identifiers that connect each layer: `sportId`, `draftGroupId`
(== slate_id here), `gameTypeId`, `contestId`, `competitionId`
(== game/event id), `draftableId` (one salaried roster-slot record),
`playerId`/`playerDkId` (DraftKings' own player identity -- two
separate fields, both preserved; **`playerDkId`, not the CSV export's
own `ID` column, is what a CSV's numeric ID should be compared against
-- confirmed live they are NOT the same ID space; see "CSV vs API
comparison" below**), `teamId`, `rosterSlotId`.

## Package layout

- `client.py` -- the only module that makes network calls. Five thin
  endpoint wrappers, `urllib.request`-based, no dependencies.
- `models.py` -- normalized dataclasses (`DkSport`, `DkContest`,
  `DkSlate`, `DkSlateGame`, `DkDraftable`, `DkRosterRules`,
  `DkRosterSlot`, `PlayerIdentityMatch`). Every model carries `raw: dict`
  so nothing observed is ever lost, even fields not promoted to a named
  attribute.
- `normalizer.py` -- raw JSON -> the models above. Pure, no network.
  Skips (never crashes on) an individual malformed record, reporting it
  in a `skipped` list rather than raising.
- `schema_guard.py` -- basic schema-change detection. Checks for the
  PRESENCE of the keys each normalizer actually reads; a genuinely
  missing required key returns `SCHEMA_CHANGED` instead of raising --
  the caller decides what to do (skip this payload, report it), the
  whole collection run never crashes over one endpoint's shape change.
- `identity.py` -- MLB reuses `dfs/player_resolver.py`'s exact tiered
  matching against the existing research package. Every other sport
  reports every draftable "unmatched" by design (no canonical identity
  system exists for them yet in this project) -- never guessed.
- `cache.py` -- simple, conservative, per-category, per-process TTL
  cache (sports 1h, rules 1h, contests/draftgroups 60s, draftables 30s).
- `persistence.py` -- immutable, timestamped raw + normalized snapshot
  archive under `data/draftkings_unofficial/` (gitignored). Refuses to
  overwrite an existing snapshot (`FileExistsError`), mirroring
  `research/prediction_snapshot.py`'s pattern.
- `comparison.py` -- compares a parsed DK salary CSV
  (`dfs/draftkings_parser.py`'s `DKSalaryRow` objects) against this
  provider's `DkDraftable` list for the same slate. Never mutates
  either source, never "fixes" a mismatch.
- `quality.py` -- pure data-quality report over an already-collected
  run (coverage, nulls, dupes, unresolved identities).
- `collector.py` -- orchestrates client + normalizer + cache +
  persistence into the actual operations the audit script and the
  provider use. Never raises for an expected failure mode (a status
  string instead), mirroring `fantasypros/build.py`'s discipline.

## Multi-sport / multi-format support

Confirmed live: DraftKings exposes the SAME draftables/rules shape
across every sport and format tested (MLB, NFL, NBA, NAS, GOLF, MMA,
CFB, TEN, LOL, SOC, F1, CS, CFL), including non-athlete draftable
entities (a NASCAR driver has `position: "D"`, `teamId: -3` -- a
sentinel, no real team). Roster-slot multipliers (Showdown Captain's
1.5x) are represented the same way regardless of sport. Salary-less
formats (Tiers, Snake, "Sit & Go", pick'em) were also discovered live
-- their draftables genuinely have no `salary` field at all, and the
normalizer correctly skips every record from those formats (via
`schema_guard`'s per-record check) rather than inventing a salary. See
`scripts/audit_draftkings_unofficial.py`'s representative-slate
selection, which deliberately prefers a `draftType == "SalaryCap"`
game type over a salary-less one when picking which slate to show for
a sport, using each game type's own `draftType` field (from
`getcontests`'s `GameTypes` list) -- never a hardcoded sport
assumption.

## CSV vs API comparison

`comparison.py::compare_csv_to_api()` is tiered: it first tries to
match by DraftKings' own numeric player ID (`playerDkId` on the API
side), falling back to normalized name+team. **Confirmed live: a real
DK CSV export's own `ID` column is NOT the same ID space as the
Draftables API's `playerDkId`/`playerId`** -- every real match in this
milestone's live validation (see the final report) matched by
name+team, zero by ID. This is documented, not silently worked around.

Position comparison also required a fix during this milestone: the
Draftables API can report a multi-position player as ONE slash-joined
string (`"2B/3B"`), while the CSV's own parser already splits its
Position/Roster Position column into a list (`["2B", "3B"]`) --
`comparison.py` splits both sides the same way before comparing, or
every real multi-position player would falsely show as a mismatch.

Picking WHICH DraftGroup to compare a CSV against matters: DraftKings
exposes many same-day Classic DraftGroups at once (Featured/Turbo/
Early/Night/Late Night, spanning 2 games up to the full day). Comparing
a 3-game CSV against the full-day 13-game DraftGroup (or worse, a
Showdown/Tiers DraftGroup for a different game entirely) produces a
misleading result. The audit script resolves this using the CSV's own
distinct Game Info count against each Classic DraftGroup's `game_count`
-- the closest match, not raw row count (a DraftGroup's live roster
size drifts between CSV capture and audit time from adds/scratches).

## The admin Data Explorer

`/admin/draftkings-unofficial` (an admin-only page,
`components/admin/DraftKingsUnofficialExplorer.tsx`) lets you pick a
sport, load its DraftGroups, select one, and browse Slate/Games/
Players/Salaries/Contests/Rules/Raw Data tabs -- backed by
`scripts/dk_unofficial_explorer.py` via
`/api/admin/draftkings-unofficial`. It **never auto-fetches** -- every
live request is an explicit click ("Load Sport Data" / selecting a
slate), and it honestly shows `not_enabled` / `NO ACTIVE SLATE` rather
than fabricating data when the flag is off or a sport has nothing live.

## Cache and snapshots

`cache.py` is a per-process, in-memory TTL cache -- it avoids repeat
live calls within one collection run (e.g. a DraftGroup referenced by
many contests only fetches draftables once). It is NOT the durable
archive; that's `persistence.py`, which writes an immutable, timestamped
copy of every raw response under `data/draftkings_unofficial/raw/
<date>/{sports,contests,draftgroups,draftables,rules,events}/` (the
whole tree is gitignored). This archive exists specifically so a future
schema change can be debugged against exactly what DraftKings returned
at capture time.

## Error handling

`client.py` translates every failure mode into a specific exception
(`DraftKingsUnofficialNotFoundError`, `...AccessRestrictedError`,
`...RateLimitedError`, `...UnavailableError`), which `collector.py`
converts into a status string (`not_found`, `ACCESS_RESTRICTED`,
`rate_limited`, `unavailable`) rather than letting an exception
propagate and crash a whole multi-sport collection run. An HTML
response (login/CAPTCHA wall) is treated as `ACCESS_RESTRICTED`, per
this milestone's explicit "no bypass mechanisms" boundary -- the
collector moves on to the next sport/resource rather than retrying with
credentials.

## Removing this provider

Everything unofficial-DraftKings-specific lives in:

- `draftkings_unofficial/` (this whole package)
- `dfs/providers/draftkings_unofficial_provider.py`
- `scripts/audit_draftkings_unofficial.py`, `scripts/dk_unofficial_explorer.py`
- `dashboard/app/admin/draftkings-unofficial/`, `dashboard/components/admin/DraftKingsUnofficialExplorer.tsx`, `dashboard/app/api/admin/draftkings-unofficial/`, `dashboard/lib/draftKingsUnofficialExplorer.ts`
- One entry in `dfs/providers/config.py::PROVIDER_FACTORIES`
- One constant in `dfs/providers/source_provenance.py` (`UNOFFICIAL_DEVELOPMENT_SOURCE`)
- One nav entry in `dashboard/components/admin/AdminSidebar.tsx`

Deleting these (and the corresponding `tests/test_dk_unofficial_*.py`
files) removes the provider cleanly -- nothing else in the optimizer,
dashboard, or pool pipeline depends on it, by design (see Milestone
31.2's "changing providers should not require rebuilding the optimizer/
dashboard").

## Known limitations

- **No production trust.** Never in the automatic provider cascade;
  always classified `UNOFFICIAL_DEVELOPMENT_SOURCE`, never
  `TRUSTED_FOR_PRODUCTION`.
- **No scoring formula.** DraftKings doesn't publicly expose one; only
  roster/salary-cap rules and (for some slot types) a text-embedded
  multiplier.
- **No historical data.** Every endpoint discovered only returns
  current/upcoming DraftGroups and contests -- see the final report's
  "historical data discovered" finding. The only historical record this
  milestone produces is its own growing raw-snapshot archive going
  forward.
- **Identity matching is MLB-only.** Every other sport's draftables
  report `unmatched` -- no canonical identity system exists for them in
  this project yet.
- **The 2021 unofficial documentation this milestone started from was a
  reasonable starting point but not fully current** -- the five
  endpoints above were independently re-confirmed live rather than
  assumed; some documented fields (e.g. a clean numeric scoring
  multiplier) simply don't exist in the current response and were not
  invented to match outdated docs.
- **Undocumented interface.** DraftKings can change any of this without
  notice. `schema_guard.py` catches a missing required field and reports
  `SCHEMA_CHANGED` rather than crashing, but a sufficiently different
  response shape will still require a normalizer update.
