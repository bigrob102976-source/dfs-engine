"""M1 -- sport-neutral canonical slate + player identity foundation.

This package is ADDITIVE FOUNDATION ONLY (M1 milestone). Nothing in
dfs/, dashboard/, or the production serving path (poolCache.ts, the DK
worker, the optimizer APIs) imports from here yet -- see each module's
own docstring for the specific future milestone that will wire it in.

Every model here is deliberately sport-agnostic (MLB today, NFL/NBA/
future sports later) and provider-agnostic (DraftKings today, a future
licensed provider such as SportsDataIO later) -- see dfs/providers/
models.py for the existing provider-normalized shapes this package's
CanonicalSlate/CanonicalSlatePlayer sit downstream of.
"""
