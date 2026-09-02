-- T3 Step 7: distinguishes "source data unchanged" from "source data
-- recently revalidated". Before this, a semantic-no-op re-promotion
-- (the external DK fetch worker successfully re-checked DraftKings and
-- confirmed nothing changed) only touched last_attempt_at -- promoted_at
-- never advanced, so canonicalPostgresBackend.ts's freshness policy
-- treated a perfectly healthy, actively-monitored slate as aging toward
-- "stale_expired" purely because its OWN content happened to be stable
-- for a while (confirmed live, repeatedly, across T1/T2). This is
-- purely additive -- one nullable column, no data migration, no
-- destructive change, and it deliberately does NOT touch fetched_at/
-- promoted_at/raw_hash/normalized_hash (the real, immutable "when was
-- this content acquired" facts) -- see canonicalPromotion.ts's own
-- updated docstring for exactly which write paths set this.

ALTER TABLE slates ADD COLUMN last_validated_at TEXT;
