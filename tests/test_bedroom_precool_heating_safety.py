"""Acceptance tests for the bedroom_precool.yaml v1.3.0 winter safety block: overheat and sensor-failure cuts, season flip and Vacation in winter (US-07, US-10)."""
from datetime import datetime, timedelta

import pytest
import yaml

from test_bedroom_precool_heating_bedtime import _Stop, _run
from test_bedroom_precool_structure import (
    BP_PATH,
    MANUAL_OFF_CHAIN,
    TZ,
    HassLoader,
    _St,
    _States,
    _render_chain,
    _top_level_steps,
)

TOGGLE = "input_boolean.heating_season"
TIMER = "number.hall_ac_power_on_timer"
OVERHEAT = "bedroom_precool_heat_overheat"
SENSORS = "bedroom_precool_heat_sensors_failed"
FLIP = "bedroom_precool_heat_season_flip"
VACATION = "bedroom_precool_heat_vacation"
# Fixture: target 18 + tolerance 1.5 = overheat level 19.5; a unit heating since an hour ago; the toggle last changed a day ago.
NOW = datetime(2026, 11, 10, 14, 0, 30, tzinfo=TZ)
BASE = dict(
    winter_target=18, tolerance=1.5, heating_season_toggle=[TOGGLE], ac_power_on_timer=[TIMER], is_real_trigger=True,
    vacation_active=False, enable_notifications=True, ac_climate="climate.hall", ac_is_running=True, ac_unavailable=False,
    current_hvac_mode="heat", bedroom_valid_temps=[18.0, 19.0], bedroom_sensors_ok=True,
)
SENSORS_DOWN = dict(bedroom_valid_temps=[], bedroom_sensors_ok=False)
UNIT_OFF = dict(ac_is_running=False, current_hvac_mode="off")


@pytest.fixture(scope="module")
def bp():
    return yaml.load(BP_PATH.read_text(), Loader=HassLoader)


def _safety_steps(bp):
    steps = _top_level_steps(bp)
    live = next(i for i, s in enumerate(steps) if "bedroom_valid_temps" in (s.get("variables") or {}))
    fetch = next(i for i, s in enumerate(steps) if "forecast_fetch_due" in (s.get("variables") or {}))
    block = steps[live + 1 : fetch]
    assert block, "the winter safety block must sit between the live-state variables and the forecast fetch"
    return block


def _safety(bp, season="on", season_age=86400, ac_age=3600, timer="10.0", **over):
    """Run the block on a real tick. season_age / ac_age: seconds since the toggle changed / the unit last changed state."""
    table = _States({
        TOGGLE: _St(season, NOW - timedelta(seconds=season_age)),
        TIMER: _St(timer, NOW - timedelta(days=1)),
    })
    ctx = dict(BASE, states=table, ac_started_ts=(NOW - timedelta(seconds=ac_age)).timestamp())
    ctx.update(over)
    calls, stopped = [], False
    try:
        _run(_safety_steps(bp), ctx, NOW, calls, {}, False)
    except _Stop:
        stopped = True
    return calls, stopped


def _acts(calls):
    return [(s, d) for s, d in calls if s.startswith(("climate.", "number."))]


def _created(calls):
    return [d["notification_id"] for s, d in calls if s == "persistent_notification.create"]


def _sets(calls):
    return [d for s, d in calls if s == "number.set_value"]


def _off_flag(bp, off_at, season):
    now = datetime(2026, 11, 10, 19, 35, tzinfo=TZ)
    ctx = dict(
        bedtime="19:30:00", lead_cap_minutes=240, wake_time="07:15:00", ac_climate="climate.hall", night_mode="ac_hold",
        heating_season=season, vacation_toggle=[], ac_is_running=False, ac_unavailable=False, expand=lambda ids: [],
        states=_States({"climate.hall": _St("off", off_at)}), this=_St("on", datetime(2026, 11, 10, 6, 0, tzinfo=TZ)),
    )
    return _render_chain(bp, MANUAL_OFF_CHAIN, now, ctx)["manual_off"]


def test_us07_overheat_turns_the_unit_off_once_with_one_notice_judged_on_any_room(bp):
    calls, stopped = _safety(bp, bedroom_valid_temps=[18.0, 19.6], warmest_bedroom=18.8)
    assert _acts(calls) == [("climate.turn_off", {})]
    assert _created(calls) == [OVERHEAT] and not stopped


@pytest.mark.parametrize("over", [
    dict(bedroom_valid_temps=[18.0, 19.5]),
    dict(bedroom_valid_temps=[19.6], **UNIT_OFF),
    dict(bedroom_valid_temps=[19.6], current_hvac_mode="cool"),
    dict(bedroom_valid_temps=[19.6], is_real_trigger=False),
    dict(bedroom_valid_temps=[19.6], season="off"),
])
def test_us07_no_overheat_cut_at_the_level_itself_or_when_not_heating_on_a_manual_run_or_in_summer(bp, over):
    assert _safety(bp, **over)[0] == []


def test_us07_overheat_level_is_the_winter_target_capped_at_20_plus_the_tolerance(bp):
    assert _safety(bp, winter_target=21, bedroom_valid_temps=[21.4])[0] == []
    assert _acts(_safety(bp, winter_target=21, bedroom_valid_temps=[21.6])[0]) == [("climate.turn_off", {})]


def test_us07_overheat_turn_off_follows_the_notification_switch(bp):
    calls, _ = _safety(bp, enable_notifications=False, bedroom_valid_temps=[19.6])
    assert _acts(calls) == [("climate.turn_off", {})] and _created(calls) == []


def test_us07_every_sensor_unavailable_gives_one_turn_off_and_one_notice(bp):
    calls, stopped = _safety(bp, **SENSORS_DOWN)
    assert _acts(calls) == [("climate.turn_off", {})]
    assert _created(calls) == [SENSORS] and not stopped


def test_us07_sensor_failure_with_the_unit_already_off_sends_no_command(bp):
    calls, _ = _safety(bp, **SENSORS_DOWN, **UNIT_OFF)
    assert _acts(calls) == [] and _created(calls) == [SENSORS]


@pytest.mark.parametrize("over", [
    dict(season="off"),
    dict(is_real_trigger=False),
    dict(ac_unavailable=True, ac_is_running=False, current_hvac_mode="unavailable"),
])
def test_us07_sensor_failure_cut_is_for_real_winter_ticks_with_a_reachable_unit(bp, over):
    assert _safety(bp, **SENSORS_DOWN, **over)[0] == []


def test_us07_the_180_second_lock_exemption_covers_heating_nights(bp):
    lock_off, late_off = datetime(2026, 11, 10, 19, 30, tzinfo=TZ), datetime(2026, 11, 10, 19, 33, tzinfo=TZ)
    assert _off_flag(bp, lock_off, True) is False
    assert _off_flag(bp, lock_off, False) is True
    assert _off_flag(bp, late_off, True) is True


def test_us10_flip_to_winter_switches_off_a_unit_that_was_running_in_cool_before_the_flip(bp):
    calls, stopped = _safety(bp, season_age=30, current_hvac_mode="cool")
    assert _acts(calls) == [("climate.turn_off", {})] and _created(calls) == [FLIP] and not stopped


def test_us10_flip_to_summer_switches_off_heat_and_sets_the_timer_to_0_in_that_minute(bp):
    calls, _ = _safety(bp, season="off", season_age=30)
    assert _acts(calls) == [("climate.turn_off", {}), ("number.set_value", {"value": 0})]
    assert _created(calls) == [FLIP]


def test_us10_flip_to_summer_zeroes_the_timer_even_when_the_unit_is_off(bp):
    calls, _ = _safety(bp, season="off", season_age=30, **UNIT_OFF)
    assert _acts(calls) == [("number.set_value", {"value": 0})] and _created(calls) == [FLIP]


@pytest.mark.parametrize("over", [dict(timer="0.0"), dict(timer="unavailable"), dict(ac_power_on_timer=[]), dict(season_age=600)])
def test_us10_no_timer_reset_when_it_is_already_0_cannot_be_read_or_the_flip_minute_has_passed(bp, over):
    calls, _ = _safety(bp, **dict(dict(season="off", season_age=30), **over))
    assert _sets(calls) == []


def test_us10_a_unit_started_after_the_flip_is_left_to_the_other_rules(bp):
    assert _safety(bp, season_age=600, ac_age=300, current_hvac_mode="cool")[0] == []
    assert _safety(bp, season="off", season_age=600, ac_age=300)[0] == []
    assert _safety(bp, season_age=30)[0] == []
    assert ("climate.turn_off", {}) not in _acts(_safety(bp, season="off", season_age=30, current_hvac_mode="cool")[0])


def test_us10_a_toggle_that_does_not_read_on_or_off_flips_nothing_and_a_manual_run_never_actuates(bp):
    for state in ("unavailable", "unknown"):
        assert _safety(bp, season=state, season_age=30)[0] == [], state
    assert _safety(bp, heating_season_toggle=[], season_age=30)[0] == []
    assert _safety(bp, season="off", season_age=30, is_real_trigger=False)[0] == []


def test_us10_vacation_in_winter_switches_off_zeroes_the_timer_and_stops_before_any_cut(bp):
    calls, stopped = _safety(bp, vacation_active=True, bedroom_valid_temps=[19.6])
    assert _acts(calls) == [("climate.turn_off", {}), ("number.set_value", {"value": 0})]
    assert _created(calls) == [VACATION] and stopped


def test_us10_vacation_in_winter_sends_nothing_more_once_the_unit_is_off_and_the_timer_is_0(bp):
    calls, stopped = _safety(bp, vacation_active=True, timer="0.0", **UNIT_OFF)
    assert _acts(calls) == [] and stopped


def test_us10_vacation_in_summer_and_on_a_manual_run_is_left_to_the_existing_vacation_step(bp):
    assert _safety(bp, season="off", vacation_active=True) == ([], False)
    assert _safety(bp, vacation_active=True, is_real_trigger=False) == ([], False)
