from younggeul_app_kr_seoul_apartment.simulation.nodes.continue_gate import should_continue
from younggeul_core.state.simulation import RoundOutcome


def _outcome(*, market_actions_resolved: int) -> RoundOutcome:
    return RoundOutcome(
        round_no=1,
        cleared_volume={"11680": 1},
        price_changes={"11680": 0.0},
        governance_applied=[],
        market_actions_resolved=market_actions_resolved,
    )


def test_continue_when_below_max_rounds() -> None:
    state = {"round_no": 1, "max_rounds": 3}
    assert should_continue(state) == "continue"


def test_stop_when_max_rounds_reached() -> None:
    state = {"round_no": 3, "max_rounds": 3}
    assert should_continue(state) == "stop"


def test_stop_when_exceeded_max_rounds() -> None:
    state = {"round_no": 5, "max_rounds": 3}
    assert should_continue(state) == "stop"


def test_stop_when_market_frozen() -> None:
    state = {"round_no": 1, "max_rounds": 5, "last_outcome": _outcome(market_actions_resolved=0)}
    assert should_continue(state) == "stop"


def test_continue_when_market_active() -> None:
    state = {"round_no": 1, "max_rounds": 5, "last_outcome": _outcome(market_actions_resolved=3)}
    assert should_continue(state) == "continue"


def test_stop_zero_max_rounds() -> None:
    state = {"round_no": 0, "max_rounds": 0}
    assert should_continue(state) == "stop"


def test_default_max_rounds() -> None:
    state = {"round_no": 3}
    assert should_continue(state) == "stop"


def test_continue_with_no_last_outcome() -> None:
    state = {"round_no": 1, "max_rounds": 5}
    assert should_continue(state) == "continue"
