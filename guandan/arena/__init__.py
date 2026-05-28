"""Arena: scenario-based AI testing and benchmarking."""

from .scenarios import (
    ALL_SCENARIOS,
    DEDUCTION_SCENARIOS,
    ENDGAME_SCENARIOS,
    OPENING_SCENARIOS,
    SAMPLING_SCENARIOS,
    Scenario,
    get_scenario_by_id,
    get_scenarios_by_category,
    list_categories,
)
