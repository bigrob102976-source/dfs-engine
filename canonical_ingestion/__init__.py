"""M2 -- parallel/shadow canonical ingestion pipeline.

Real DK fetch -> RAW capture -> canonical normalization -> validation ->
NORMALIZED artifact -> canonical Postgres shadow-CURRENT write.

Everything in this package is SHADOW/PARALLEL to the legacy production
path (draftkings_unofficial/ -> dfs/providers/draftkings_unofficial_provider.py
-> scripts/fetch_dfs_slate.py -> dfs_input/{date}/provider_slate_*.json
-> poolCache.ts -> customer). The legacy path is untouched by this
package and remains the sole customer-facing source of truth during M2.

This package only performs the Python-side half of the pipeline (RAW +
NORMALIZED, both R2/object-storage artifacts). The Postgres shadow-
CURRENT write is deliberately NOT done from Python -- this codebase's
Postgres access has always lived exclusively in dashboard/lib/db/*.ts
(see player_identity/persistence.py's own documented reason for never
adding a Python-to-Postgres dependency). The NORMALIZED artifact this
package writes is the handoff point: dashboard/scripts/promote-canonical-slate.ts
reads it and performs the actual transactional Postgres upsert.
"""
