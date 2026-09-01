-- M1: canonical slate + player identity foundation (ADDITIVE ONLY).
--
-- This migration creates the foundation tables described in the M0
-- architecture audit's PROPOSED M1 design. Per the M1 task's explicit
-- constraints:
--   - purely additive: no DROP, no destructive ALTER, no data deletion
--   - nothing in the production serving path (poolCache.ts, the DK
--     worker, the optimizer APIs, dashboard UI) reads or writes these
--     tables yet -- they exist, unused, until a later milestone wires
--     them in
--   - existing slate_status / slate_publish_history / jobs /
--     worker_heartbeats / sports / entitlements / feature_flags are
--     left completely untouched
--
-- Numbered 0010 here (this directory's next number) though its SQLite
-- counterpart is 0009 -- the two migration directories already diverge
-- in numbering (0009_ordering_sequence_columns.sql exists only on the
-- Postgres side, per that migration's own header comment), so this is
-- consistent with established precedent, not a new inconsistency.
--
-- IMPORTANT (M1P/M1S): this repo's Postgres migrations are NOT applied
-- automatically on deploy -- lib/db/executor.ts's own docstring confirms
-- runPostgresMigrations() is an explicit, separate operator step (run
-- via scripts/migrate-postgres-schema.ts), never an implicit side
-- effect of a request or app boot. Pushing this file to origin/main
-- does NOT, by itself, alter the production database; someone must
-- deliberately run the migration script against it afterward.
--
-- players / player_external_ids  Sport-neutral canonical player
--                                 identity (canonical/identity_models.py
--                                 mirrors this shape in Python).
--                                 internal_player_id is Big Money's own,
--                                 minted once, NEVER reused as -- or
--                                 replaced by -- any external identifier
--                                 (DK playerId, MLBAM id, GSIS id,
--                                 SportsDataIO id, ...).
--
--                                 player_external_ids deliberately does
--                                 NOT enforce a permanent
--                                 UNIQUE(internal_player_id, provider):
--                                 a provider may migrate a player's
--                                 external id over time, and this schema
--                                 must keep the old id queryable as
--                                 history. Instead, TWO PARTIAL UNIQUE
--                                 INDEXES (scoped to is_current = 1)
--                                 enforce the two invariants that must
--                                 hold only among CURRENTLY ACTIVE rows:
--                                   1. one (provider, external_id, sport)
--                                      resolves to at most one internal
--                                      player at a time (an external id
--                                      never simultaneously maps to two
--                                      people)
--                                   2. one internal player has at most
--                                      one CURRENT external id per
--                                      provider (no duplicate/ambiguous
--                                      active mapping for the same
--                                      provider)
--                                 Neither index restricts historical
--                                 (is_current = 0) rows at all -- a
--                                 player may accumulate any number of
--                                 retired external ids over time.
--
-- slates / slate_players         Sport-neutral canonical slate + slate-
--                                 player rows (canonical/models.py
--                                 mirrors this shape in Python). ONE ROW
--                                 PER (sport, site, provider,
--                                 provider_slate_id) represents this
--                                 provider slate's CANONICAL/CURRENT
--                                 identity in Postgres -- re-normalizing
--                                 the same DraftGroup updates this row
--                                 in place. This is deliberately
--                                 distinct from R2's immutable NORMALIZED
--                                 artifact history (each fetch/
--                                 normalization produces its own
--                                 immutable R2 object); Postgres here
--                                 holds "the current canonical view,"
--                                 R2 holds "every version that ever
--                                 existed." raw_hash/normalized_hash on
--                                 this row reflect the MOST RECENTLY
--                                 promoted artifact's hashes, not a
--                                 history of every hash seen.
--
--                                 slate_players.internal_player_id is
--                                 NULLABLE -- an unresolved player is
--                                 still a fully valid, servable row (see
--                                 canonical/identity_matching.py).
--                                 provider_draftable_ids preserves ALL
--                                 of a player's per-slate DraftKings
--                                 draftableIds (JSON array) -- never
--                                 used as identity.
--
-- identity_review_queue          One row per identity ambiguity a human
--                                 must resolve (canonical/identity_models.py
--                                 ::IdentityReviewQueueEntry). Never
--                                 blocks a slate from being served --
--                                 see slate_players.identity_status.
--
-- List-shaped columns (game_ids, roster_template, validation_findings,
-- provider_draftable_ids, position_eligibility, roster_slot_eligibility)
-- are stored as JSON-encoded TEXT, matching this schema's existing
-- convention (e.g. slate_status.validation_json) rather than a
-- Postgres-only JSONB type, since these migrations are shared verbatim
-- across the SQLite and PostgreSQL dialects.

CREATE TABLE players (
  internal_player_id  TEXT PRIMARY KEY,
  sport               TEXT NOT NULL,
  canonical_name      TEXT NOT NULL,
  normalized_name     TEXT NOT NULL,
  current_team        TEXT,
  position            TEXT,
  active              INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
  created_at          TEXT NOT NULL,
  updated_at          TEXT NOT NULL
);
CREATE INDEX idx_players_sport ON players(sport);
CREATE INDEX idx_players_sport_normalized_name ON players(sport, normalized_name);

CREATE TABLE player_external_ids (
  id                  TEXT PRIMARY KEY,
  internal_player_id  TEXT NOT NULL REFERENCES players(internal_player_id),
  sport               TEXT NOT NULL,
  provider            TEXT NOT NULL,
  external_id         TEXT NOT NULL,
  external_id_type    TEXT NOT NULL,
  match_method        TEXT NOT NULL,
  match_confidence    REAL NOT NULL,
  review_status       TEXT NOT NULL CHECK (review_status IN ('AUTO_APPROVED','NEEDS_REVIEW','REVIEWED_APPROVED','REVIEWED_REJECTED')) DEFAULT 'AUTO_APPROVED',
  is_current          INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0,1)),
  valid_from          TEXT NOT NULL,
  valid_to            TEXT,
  created_at          TEXT NOT NULL,
  updated_at          TEXT NOT NULL
);
CREATE INDEX idx_player_external_ids_internal_player ON player_external_ids(internal_player_id);
CREATE INDEX idx_player_external_ids_provider_external ON player_external_ids(provider, external_id);
CREATE INDEX idx_player_external_ids_sport ON player_external_ids(sport);
-- Invariant 1: an external id resolves to at most one internal player
-- WHILE CURRENT (historical, is_current=0 rows are exempt).
CREATE UNIQUE INDEX idx_player_external_ids_current_external ON player_external_ids(provider, external_id, sport) WHERE is_current = 1;
-- Invariant 2: one internal player has at most one CURRENT external id
-- per provider (no duplicate active mapping).
CREATE UNIQUE INDEX idx_player_external_ids_current_per_player ON player_external_ids(internal_player_id, provider, sport) WHERE is_current = 1;

CREATE TABLE slates (
  internal_slate_id    TEXT PRIMARY KEY,
  sport                TEXT NOT NULL,
  site                 TEXT NOT NULL,
  provider             TEXT NOT NULL,
  provider_slate_id    TEXT NOT NULL,
  slate_name           TEXT,
  slate_date           TEXT NOT NULL,
  first_game_start_utc TEXT NOT NULL,
  game_count           INTEGER,
  game_ids_json        TEXT,
  salary_cap           INTEGER,
  roster_template_json TEXT,
  source_provenance    TEXT NOT NULL DEFAULT 'UNKNOWN',
  validation_state     TEXT NOT NULL CHECK (validation_state IN ('PENDING','VALID','REJECTED')) DEFAULT 'PENDING',
  validation_findings_json TEXT,
  schema_version       TEXT NOT NULL,
  raw_hash             TEXT,
  normalized_hash      TEXT,
  fetched_at           TEXT,
  created_at           TEXT NOT NULL,
  updated_at           TEXT NOT NULL
);
-- Canonical/current identity for this provider slate -- see this
-- migration's own header comment for why this is NOT a version-history
-- table (R2 holds that).
CREATE UNIQUE INDEX idx_slates_provider_identity ON slates(sport, site, provider, provider_slate_id);
CREATE INDEX idx_slates_sport_date ON slates(sport, slate_date);
CREATE INDEX idx_slates_provider_slate_id ON slates(provider, provider_slate_id);
CREATE INDEX idx_slates_validation_state ON slates(validation_state);

CREATE TABLE slate_players (
  internal_slate_id    TEXT NOT NULL REFERENCES slates(internal_slate_id),
  provider_player_id   TEXT NOT NULL,
  internal_player_id   TEXT REFERENCES players(internal_player_id),
  provider_draftable_ids_json TEXT,
  name                 TEXT NOT NULL,
  team                 TEXT NOT NULL,
  opponent             TEXT,
  game_id              TEXT,
  salary               INTEGER NOT NULL,
  position_eligibility_json TEXT,
  roster_slot_eligibility_json TEXT,
  identity_status      TEXT NOT NULL CHECK (identity_status IN ('RESOLVED','UNRESOLVED','REVIEW_REQUIRED')) DEFAULT 'UNRESOLVED',
  created_at           TEXT NOT NULL,
  updated_at           TEXT NOT NULL,
  PRIMARY KEY (internal_slate_id, provider_player_id)
);
CREATE INDEX idx_slate_players_internal_player ON slate_players(internal_player_id);
CREATE INDEX idx_slate_players_internal_slate ON slate_players(internal_slate_id);
CREATE INDEX idx_slate_players_identity_status ON slate_players(identity_status);
CREATE INDEX idx_slate_players_team ON slate_players(team);

CREATE TABLE identity_review_queue (
  id                          TEXT PRIMARY KEY,
  sport                       TEXT NOT NULL,
  provider                    TEXT NOT NULL,
  external_id                 TEXT NOT NULL,
  provider_player_name        TEXT NOT NULL,
  provider_team               TEXT,
  provider_position           TEXT,
  candidate_internal_player_id TEXT REFERENCES players(internal_player_id),
  reason                      TEXT NOT NULL,
  status                      TEXT NOT NULL CHECK (status IN ('PENDING','RESOLVED','REJECTED')) DEFAULT 'PENDING',
  resolved_internal_player_id TEXT REFERENCES players(internal_player_id),
  resolved_by                 TEXT REFERENCES users(id),
  created_at                  TEXT NOT NULL,
  updated_at                  TEXT NOT NULL,
  resolved_at                 TEXT
);
CREATE INDEX idx_identity_review_queue_status ON identity_review_queue(status);
CREATE INDEX idx_identity_review_queue_sport_provider ON identity_review_queue(sport, provider);
