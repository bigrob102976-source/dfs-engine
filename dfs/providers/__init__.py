"""Pluggable DFS salary/slate data providers (Milestone 13).

The rest of the application never talks to a specific provider directly
-- it only consumes the normalized `ProviderPlayer`/`ProviderSlateResult`
shapes in dfs/providers/models.py. This keeps DraftKings scraping,
login automation, and undocumented-endpoint dependence entirely out of
scope: see dfs/providers/base.py's module docstring for the exact rule.
"""
