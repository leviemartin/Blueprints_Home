"""Acceptance tests for the bedroom_precool.yaml v1.3.0 heating auto-learn write at the winter bedtime minute (US-11)."""
import pytest
import yaml

from test_bedroom_precool_heating_bedtime import BASE, RUNNING, TIMER, TOGGLE, _Stop, _run, _winter_steps, on
from test_bedroom_precool_structure import BP_PATH, HassLoader, _service_steps

HELPER = "input_number.heating_lead_bias"
# Fixture: aim 18.5 (target 18 + offset 0.5), k_indoor 15, gain 0.4, helper at 10, coldest 17.5: error 1.0, 10 + 0.4 * 1.0 * 15 = 16.
LEARN = dict(RUNNING, heating_bias_helper=[HELPER], learn_gain=0.4, coldest_bedroom=17.5)


@pytest.fixture(scope="module")
def bp():
    return yaml.load(BP_PATH.read_text(), Loader=HassLoader)


def _learn(bp, now=None, helper="10", helper_min=-60.0, helper_max=120.0, season="on", **over):
    now = now or on(10)
    store = {TOGGLE: season, TIMER: "5.0"}
    if helper is not None:
        store[HELPER] = helper
    attrs = {(TIMER, "max"): 24, (HELPER, "min"): helper_min, (HELPER, "max"): helper_max}
    ctx = dict(BASE, now_tod=now.strftime("%H:%M:%S"), states=lambda e: store.get(e, "unknown"),
               state_attr=lambda e, a: attrs.get((e, a)))
    ctx.update(LEARN)
    ctx.update(over)
    calls = []
    try:
        _run(_winter_steps(bp), ctx, now, calls, store, False)
    except _Stop:
        pass
    return ctx, calls


def _writes(calls):
    return [d for s, d in calls if s == "input_number.set_value"]


def test_us11_a_heating_evening_writes_the_learned_bias_and_still_arms_the_timer(bp):
    ctx, calls = _learn(bp)
    assert ctx["heating_bias"] == 10
    assert _writes(calls) == [{"value": 16.0}]
    assert ("number.set_value", {"value": 10}) in calls


@pytest.mark.parametrize("kwargs,expected", [
    (dict(helper="100", coldest_bedroom=10.0), 120),
    (dict(helper="-58", coldest_bedroom=19.0), -60),
    (dict(helper_min=20.0), 20),
    (dict(helper_max=12.0), 12),
])
def test_us11_the_written_bias_is_clamped_to_the_helpers_range(bp, kwargs, expected):
    assert _writes(_learn(bp, **kwargs)[1]) == [{"value": float(expected)}]


def test_us11_a_helper_range_that_misses_minus_60_to_120_gets_no_write(bp):
    assert _writes(_learn(bp, helper_min=130.0, helper_max=240.0)[1]) == []


@pytest.mark.parametrize("over,written", [
    (dict(current_setpoint=22.5), False),
    (dict(current_setpoint=24.0), True),
    (dict(current_setpoint=21.0), True),
    (dict(current_setpoint=22.5, ac_state_age_sec=60), True),
])
def test_us11_a_setpoint_left_by_hand_skips_the_write(bp, over, written):
    assert bool(_writes(_learn(bp, **over)[1])) is written


@pytest.mark.parametrize("kwargs", [
    dict(heating_bias_helper=[]),
    dict(enable_auto_learn=False),
    dict(helper=None),
    dict(helper="unavailable"),
    dict(ac_is_running=False, current_hvac_mode="off"),
    dict(current_hvac_mode="cool"),
    dict(is_real_trigger=False),
    dict(season="off"),
    dict(now=on(10, 19, 31)),
])
def test_us11_nothing_is_written_without_a_usable_heating_helper_or_a_heated_bedtime_minute(bp, kwargs):
    assert _writes(_learn(bp, **kwargs)[1]) == []


def test_us11_an_empty_heating_helper_gives_a_zero_bias_and_nothing_is_written(bp):
    ctx, calls = _learn(bp, heating_bias_helper=[], lead_bias=50)
    assert (ctx["heating_bias_configured"], ctx["heating_bias"]) == (False, 0)
    assert _writes(calls) == []


def test_us11_the_winter_branch_writes_only_the_heating_helper_and_the_summer_lock_only_its_own(bp):
    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
    writes = [(c, s) for c, s in steps if s.get("service") == "input_number.set_value"]
    by_entity = {s["target"]["entity_id"]: c for c, s in writes}
    assert sorted(by_entity) == ["{{ heating_bias_entity }}", "{{ lead_bias_entity }}"]
    assert any("heat_bedtime_minute" in t for t in by_entity["{{ heating_bias_entity }}"])
    assert any("phase == 'BEDTIME_LOCK'" in t for t in by_entity["{{ lead_bias_entity }}"])
    assert not any("phase == 'BEDTIME_LOCK'" in t for t in by_entity["{{ heating_bias_entity }}"])
