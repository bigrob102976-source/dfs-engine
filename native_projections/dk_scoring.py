"""DraftKings Scoring conversion: turns regressed event RATES
(hitter_rates.py / pitcher_rates.py) plus expected opportunity counts
(playing_time.py) into DK-point-denominated ComponentValue objects.

Third pipeline stage (Expected Baseball Outcomes -> DraftKings Scoring ->
Native Fantasy Projection). Uses ONLY the existing authoritative
DK_HITTER_SCORING (config.batter_scoring_config) / DK_SCORING
(config.scoring_config) dicts -- this module never defines its own copy of
a DK point value, per the milestone's explicit "never duplicate the
scoring constants" instruction.

--------------------------------------------------------------------------
Runs / RBI approximation (hitters)
--------------------------------------------------------------------------
Neither the existing Independent Projection nor any other part of this
codebase models Runs/RBI -- there is no lineup base-state simulation to
draw from. This is a DOCUMENTED, simple linear-weights-style approximation,
explicitly NOT a full simulation (see config.native_projection_config's
"Runs / RBI approximation" section for the exact coefficients):

    obp_proxy  = walk_rate + hbp_rate + single_rate + double_rate + triple_rate + home_run_rate
    power_proxy = double_rate + 2*triple_rate + 3*home_run_rate   (extra bases per PA)
    expected_runs = expected_pa * obp_proxy   * RUNS_PER_PA_OBP_COEFFICIENT * lineup_slot_multiplier
    expected_rbi  = expected_pa * power_proxy * RBI_PER_PA_ISO_COEFFICIENT  * lineup_slot_multiplier

Deliberately built from the SAME already-regressed rates hitter_rates.py
produces (not raw, unregressed season.obp/season.iso) so a tiny-sample
hitter's Runs/RBI approximation inherits the same shrinkage as every other
component -- reintroducing the Pinckney-class bug here by reading an
unregressed rate would defeat the point of the rest of this model.

--------------------------------------------------------------------------
Pitcher win probability
--------------------------------------------------------------------------
PitcherComponents.win_probability is left None in V1 -- DraftKings' win
bonus is informational/postgame-only (config.scoring_config's own DK_SCORING
docstring makes the same call for the Independent Projection), and a
defensible win-probability model needs real Vegas moneylines, which this
codebase only has mock data for today. Documented V1 limitation, not
silently omitted.
"""

from typing import Optional

from config import native_projection_config as cfg
from config.batter_scoring_config import DK_HITTER_SCORING
from config.scoring_config import DK_SCORING

from native_projections.hitter_rates import HitterRates
from native_projections.models import ComponentValue, HitterComponents, PitcherComponents
from native_projections.pitcher_rates import PitcherRates
from native_projections.playing_time import PitcherOpportunity


def _component(expected_count: float, dk_value: float, reason: Optional[str] = None) -> ComponentValue:
    dk_points = expected_count * dk_value
    return ComponentValue(
        expected_count=round(expected_count, 3),
        dk_points_per_event=dk_value,
        dk_points=round(dk_points, 3),
        reason=reason,
    )


def hitter_components(rates: HitterRates, expected_pa: float, batting_order: Optional[int]) -> HitterComponents:
    singles = _component(expected_pa * rates.single_rate, DK_HITTER_SCORING["single"])
    doubles = _component(expected_pa * rates.double_rate, DK_HITTER_SCORING["double"])
    triples = _component(expected_pa * rates.triple_rate, DK_HITTER_SCORING["triple"])
    home_runs = _component(expected_pa * rates.home_run_rate, DK_HITTER_SCORING["home_run"])
    walks = _component(expected_pa * rates.walk_rate, DK_HITTER_SCORING["walk"])
    hit_by_pitch = _component(expected_pa * rates.hit_by_pitch_rate, DK_HITTER_SCORING["hit_by_pitch"])
    stolen_bases = _component(expected_pa * rates.stolen_base_rate, DK_HITTER_SCORING["stolen_base"])

    slot_multiplier = cfg.RUNS_RBI_LINEUP_SLOT_MULTIPLIER.get(batting_order, cfg.DEFAULT_RUNS_RBI_LINEUP_SLOT_MULTIPLIER)
    obp_proxy = rates.walk_rate + rates.hit_by_pitch_rate + rates.single_rate + rates.double_rate + rates.triple_rate + rates.home_run_rate
    power_proxy = rates.double_rate + 2 * rates.triple_rate + 3 * rates.home_run_rate

    expected_runs = expected_pa * obp_proxy * cfg.RUNS_PER_PA_OBP_COEFFICIENT * slot_multiplier
    expected_rbi = expected_pa * power_proxy * cfg.RBI_PER_PA_ISO_COEFFICIENT * slot_multiplier

    runs = _component(
        expected_runs,
        DK_HITTER_SCORING["run"],
        reason=f"Linear approximation from on-base rate {obp_proxy:.3f}/PA and lineup slot multiplier {slot_multiplier:.2f} (not a lineup base-state simulation)",
    )
    rbi = _component(
        expected_rbi,
        DK_HITTER_SCORING["rbi"],
        reason=f"Linear approximation from extra-base rate {power_proxy:.3f}/PA and lineup slot multiplier {slot_multiplier:.2f} (not a lineup base-state simulation)",
    )

    strikeouts_expected = expected_pa * rates.strikeout_rate  # informational only -- DK does not score hitter strikeouts

    return HitterComponents(
        singles=singles,
        doubles=doubles,
        triples=triples,
        home_runs=home_runs,
        walks=walks,
        hit_by_pitch=hit_by_pitch,
        stolen_bases=stolen_bases,
        runs=runs,
        rbi=rbi,
        strikeouts_expected=round(strikeouts_expected, 3),
    )


def pitcher_components(rates: PitcherRates, opportunity: PitcherOpportunity) -> PitcherComponents:
    innings_pitched = _component(opportunity.expected_innings, DK_SCORING["innings_pitched"])
    strikeouts = _component(opportunity.expected_batters_faced * rates.strikeout_rate, DK_SCORING["strikeout"])
    walks = _component(opportunity.expected_batters_faced * rates.walk_rate, DK_SCORING["walk"])
    hit_batsmen = _component(opportunity.expected_batters_faced * rates.hit_by_pitch_rate, DK_SCORING["hit_batsman"])
    hits_allowed = _component(opportunity.expected_batters_faced * rates.hit_rate, DK_SCORING["hit_against"])
    earned_runs = _component(opportunity.expected_innings * rates.earned_run_rate_per_inning, DK_SCORING["earned_run"])

    return PitcherComponents(
        innings_pitched=innings_pitched,
        strikeouts=strikeouts,
        walks=walks,
        hit_batsmen=hit_batsmen,
        hits_allowed=hits_allowed,
        earned_runs=earned_runs,
        win_probability=None,
        win_probability_is_mock=None,
    )


def hitter_base_projection(components: HitterComponents) -> float:
    return round(
        components.singles.dk_points
        + components.doubles.dk_points
        + components.triples.dk_points
        + components.home_runs.dk_points
        + components.walks.dk_points
        + components.hit_by_pitch.dk_points
        + components.stolen_bases.dk_points
        + components.runs.dk_points
        + components.rbi.dk_points,
        3,
    )


def pitcher_base_projection(components: PitcherComponents) -> float:
    return round(
        components.innings_pitched.dk_points
        + components.strikeouts.dk_points
        + components.walks.dk_points
        + components.hit_batsmen.dk_points
        + components.hits_allowed.dk_points
        + components.earned_runs.dk_points,
        3,
    )
