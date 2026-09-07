"""NFL M6A -- historical NFL statistical data ingestion, sourced from
nflverse (via nflreadpy). Entirely separate from nfl/ (the live
DraftKings-facing slate/pool/optimizer package) -- this package builds
the offline historical foundation that later milestones (M6B identity
crosswalk, M6C usage, M6D injuries/depth charts, M6E weather, M6F
feature/target warehouse) will consume. No projections, no ownership,
no dashboard code -- ingestion only.
"""
