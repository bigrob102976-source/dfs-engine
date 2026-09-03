-- MLB FINISH MODE Phase B/D -- canonical CURRENT projection/ownership
-- serving state, additive to the existing shadow-CURRENT tables (M2/M6).
-- Reuses the SAME "immutable R2 artifact is the source of truth, this
-- table is a Postgres-served snapshot of its CURRENT state" pattern as
-- canonicalEligibility.ts -- the real Big Money Native model
-- (native_projections/*.py) and the real ownership model
-- (ownership/*.py) are completely unchanged; this only persists their
-- already-computed, already-immutable-artifact-backed output so the
-- canonical serving backend can read it without a second Python call
-- per request.
--
-- Keyed by (internal_slate_id, provider_player_id, source) rather than
-- internal_player_id -- M7H/M8's own identity-gap findings make clear a
-- meaningful fraction of real players never resolve identity at all
-- (bench/depth players), and a real, live DK player must remain
-- servable with real projection/ownership data even when historical
-- identity resolution hasn't happened (this milestone's own explicit
-- Phase E instruction: "Do not exclude a valid live player solely
-- because historical identity is unresolved"). internal_player_id is
-- NOT stored here at all -- the join FROM mlbPlayerId/dkPlayerId TO
-- these rows always happens through slate_players.provider_player_id,
-- exactly like eligibility already does.
--
-- `source` is deliberately a column, not a fixed assumption of "always
-- native" -- Big Money Native is the only automatic source this
-- milestone wires in (rule #1: "Big Money Native is the public/default
-- projection source"), but the column exists so a future admin-only
-- comparison source (already-existing AI/FantasyPros/BlueCollar) could
-- reuse the same table without a schema change, mirroring how
-- PoolPlayerRow already carries multiple named projection fields side
-- by side.

CREATE TABLE canonical_slate_player_projections (
  id                  TEXT PRIMARY KEY,
  internal_slate_id   TEXT NOT NULL REFERENCES slates(internal_slate_id),
  provider_player_id  TEXT NOT NULL,
  source              TEXT NOT NULL,
  model_version       TEXT,
  projection          REAL,
  ceiling             REAL,
  floor               REAL,
  generated_at        TEXT,
  created_at          TEXT NOT NULL,
  updated_at          TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_canonical_slate_player_projections_current
  ON canonical_slate_player_projections(internal_slate_id, provider_player_id, source);
CREATE INDEX idx_canonical_slate_player_projections_slate
  ON canonical_slate_player_projections(internal_slate_id);

-- Ownership is its own table (not folded into the projections table
-- above) -- it is a genuinely separate model, computed by a separate
-- script, on its own real dependency (a usable projection must already
-- exist for a player to even be considered -- see
-- ownership/*.py's own real input gate), and can fail/be stale
-- independently of projections (Phase J: "ownership failure: last good
-- ownership retained or ownership shown unavailable, never fake 0").
CREATE TABLE canonical_slate_player_ownership (
  id                    TEXT PRIMARY KEY,
  internal_slate_id     TEXT NOT NULL REFERENCES slates(internal_slate_id),
  provider_player_id    TEXT NOT NULL,
  model_version         TEXT,
  projected_ownership   REAL,
  ownership_tier        TEXT,
  leverage_score        REAL,
  chalk_score           REAL,
  generated_at          TEXT,
  created_at            TEXT NOT NULL,
  updated_at            TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_canonical_slate_player_ownership_current
  ON canonical_slate_player_ownership(internal_slate_id, provider_player_id);
CREATE INDEX idx_canonical_slate_player_ownership_slate
  ON canonical_slate_player_ownership(internal_slate_id);
