"""NFL M5 -- joins M2 canonical NflPlayer records with M5 NflGameContext
records. NFLPlayer + NFLGameContext = NFLPlayerResearchContext.

Matching key: NflPlayer.game_id == NflGameContext.canonical_game_id --
both are DraftKings' own real competitionId already, so no separate
matching logic is needed here at all (unlike DK-to-odds-provider
matching, which genuinely needs team normalization -- see
nfl/odds_matching.py). Never overwrites any NflPlayer field: this
module only ever returns a new, read-only joined view.

DST resolves correctly automatically: a DST's game_id is already real
and correct from M2 (e.g. a team's defense carries the same
competitionId as every other player in that game), so no special-casing
is needed here either.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from nfl.game_context_models import NflGameContext
from nfl.models import NflPlayer


@dataclass
class NflPlayerResearchContext:
    player: NflPlayer
    game: Optional[NflGameContext]  # None when no game-context record exists yet for this player's game

    def to_dict(self) -> dict:
        return {
            "player": self.player.to_dict(),
            "game": self.game.to_dict() if self.game else None,
        }


def attach_game_context(players: List[NflPlayer], games: List[NflGameContext]) -> List[NflPlayerResearchContext]:
    games_by_id: Dict[str, NflGameContext] = {g.canonical_game_id: g for g in games}
    return [NflPlayerResearchContext(player=p, game=games_by_id.get(p.game_id)) for p in players]
