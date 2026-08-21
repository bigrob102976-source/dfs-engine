"""Historical Vegas/betting odds adapter.

Milestone 32.0 audit finding: no free, currently-fetchable, up-to-date
historical MLB odds API was confirmed. What was found (report honestly):

- SportsDataIO (this project's existing Vegas provider family --
  SPORTSGAMEODDS_API_KEY is already configured for the LIVE pipeline,
  see research/game_environment/vegas.py) documents a separate
  Historical Odds product: odds older than 30 days move into a
  historical data warehouse, with coverage "from 2019 onward" per their
  public docs. Pricing/access requires a sales conversation or a paid
  plan -- not purchased or tested live during this audit, per the
  explicit "do NOT purchase anything" instruction.
- The Odds API (the-odds-api.com) documents historical MLB odds from
  mid-2020 onward on paid tiers.
- Free, non-current-season archives exist (Kaggle "MLB Odds Data"
  2012-2021; a Princeton DSS-hosted archive covering 2009-2023;
  sports-statistics.com's MLB odds/scores archive 2010-2021) -- useful
  for older backtesting, but none of them cover this milestone's
  required live-test dates' most recent instance (2025) with certainty,
  and freshness/coverage were not independently verified beyond their
  own public descriptions (no file was downloaded/purchased).

This module implements only a defensive PARSER for a human-supplied
odds export (CSV with date/away_team/home_team/moneyline/total columns,
matching the common shape of the free archives above), mirroring
salaries.py's approach: no confirmed live free source to call, but
ready to ingest a real file the moment one is obtained.
"""

import csv
import io
from typing import List


def parse_historical_odds_csv(csv_text: str) -> List[dict]:
    """Pure parsing, no network. Column names are matched
    case-insensitively against a small set of common aliases; any
    column not recognized is ignored (not an error) since historical
    odds archives vary widely in shape."""
    reader = csv.DictReader(io.StringIO(csv_text))
    header = {h.lower(): h for h in (reader.fieldnames or [])}

    def col(*aliases):
        for a in aliases:
            if a in header:
                return header[a]
        return None

    c_date = col("date", "game_date")
    c_away = col("away", "away_team", "visitor")
    c_home = col("home", "home_team")
    c_away_ml = col("away_ml", "away_moneyline", "vis_ml")
    c_home_ml = col("home_ml", "home_moneyline")
    c_total = col("total", "over_under", "ou")

    rows: List[dict] = []
    for raw in reader:
        rows.append({
            "date": raw.get(c_date) if c_date else None,
            "away_team": raw.get(c_away) if c_away else None,
            "home_team": raw.get(c_home) if c_home else None,
            "away_moneyline": raw.get(c_away_ml) if c_away_ml else None,
            "home_moneyline": raw.get(c_home_ml) if c_home_ml else None,
            "total": raw.get(c_total) if c_total else None,
        })
    return rows
