"""Historical data source adapters. Each module is a thin, honest wrapper
around exactly one external source -- it never invents a field the
source doesn't actually provide, and every live-network function has a
`save_snapshot`-free, pure-parsing counterpart that unit tests exercise
against a saved fixture payload instead (see M32.0's Part 16 "no live
network calls in unit tests" rule)."""
