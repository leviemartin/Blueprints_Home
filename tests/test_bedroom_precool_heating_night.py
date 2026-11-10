"""Acceptance tests for the bedroom_precool.yaml v1.3.0 winter night: re-heat, deep-night nudge and the morning wrong-mode correction (US-05, US-06)."""
from datetime import datetime

import pytest
import yaml

from test_bedroom_precool_heating_bedtime import _Stop, _run, _val, _winter_steps
from test_bedroom_precool_structure import BP_PATH, TZ, HassLoader, _calls_with, _env, _reparse, _var_template

TOGGLE = "input_boolean.heating_season"
NOTICE = "bedroom_precool_heat_wrong_mode"
# Fixture: bedtime 19:30, wake 07:15, weekday morning 06:15 (planned start 05:30), weekend morning 06:45 (planned start 06:30),
# target 18, tolerance 1.5 (re-heat level 16.5), hall offset 3 (hold 21), correction step 1.5, deep-night check 01:00.
BASE = dict(
    winter_target=18, prewarm_offset=0.5, tolerance=1.5, hall_offset=3.0, heating_drive_setpoint=24.0, correction_step=1.5,
    heating_skip_threshold=12, heating_season_toggle=[TOGGLE], heating_bias_helper=[], enable_auto_learn=True,
    base_minutes=20, k_indoor=15, k_outdoor=1.0, safety_margin_minutes=25, lead_cap_minutes=240,
    bedtime="19:30:00", wake_time="07:15:00", wake_tod="07:15:00", bedtime_tod="19:30:00", deep_night_check="01:00:00",
    earliest_turn_on_tod="15:30:00", morning_time="06:15:00", weekend_morning_time="06:45:00", ac_power_on_timer=[],
    outdoor_now=10.0, warmest_bedroom=19.0, coldest_bedroom=19.0, forecast_window_temps=[2.0, 5.0], forecast_daily_list=[],
    ac_climate="climate.hall", ac_is_running=False, current_hvac_mode="off", ac_hvac_modes=["off", "heat", "cool"],
    ac_min_temp=16.0, ac_max_temp=30.0, ac_temp_step=0.5, ac_limits_known=True, current_setpoint=21.0,
    current_setpoint_known=True, ac_state_age_sec=600, ac_started_ts=0, is_real_trigger=True, manual_off=False,
    enable_notifications=True,
)
HEAT = dict(ac_is_running=True, current_hvac_mode="heat", current_setpoint=21.0)
STARTED = datetime(2026, 11, 11, 5, 30, tzinfo=TZ).timestamp()


@pytest.fixture(scope="module")
def bp():
    return yaml.load(BP_PATH.read_text(), Loader=HassLoader)


def at(day, hour, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=TZ)


def _night(bp, now, season="on", room=None, **over):
    table = {TOGGLE: season}
    ctx = dict(BASE, now_tod=now.strftime("%H:%M:%S"), states=lambda e: table.get(e, "unknown"), state_attr=lambda e, a: None)
    if room is not None:
        ctx.update(warmest_bedroom=room, coldest_bedroom=room)
    ctx.update(over)
    for name in ("deep_tod", "deep_end_tod", "in_deep_check"):
        ctx[name] = _val(_var_template(bp, name), ctx, now)
    calls, stopped = [], False
    try:
        _run(_winter_steps(bp), ctx, now, calls, {}, False)
    except _Stop:
        stopped = True
    return ctx, calls, stopped


def _commands(calls):
    return [(s, d) for s, d in calls if s.startswith("climate.")]


def _created(calls):
    return [d["notification_id"] for s, d in calls if s == "persistent_notification.create"]


def test_us05_one_bare_turn_on_goes_out_below_the_re_heat_level_and_nothing_at_it(bp):
    ctx, calls, stopped = _night(bp, at(10, 23), room=16.4)
    assert (ctx["reheat_level"], ctx["heat_hold_sp"], ctx["heat_stage"]) == (16.5, 21.0, "REHEAT")
    assert _commands(calls) == [("climate.turn_on", {})] and stopped
    ctx, calls, _ = _night(bp, at(10, 23), room=16.5)
    assert (ctx["heat_stage"], _commands(calls)) == ("HOLD", [])
    assert _commands(_night(bp, at(10, 19, 30), room=16.4)[1]) == []


@pytest.mark.parametrize("now", [at(10, 19, 31), at(10, 23), at(11, 0), at(11, 3, 30), at(11, 5, 29), at(11, 5, 35), at(11, 7, 14)])
def test_us05_re_heat_can_start_at_any_minute_between_bedtime_and_wake_outside_the_planned_start_wait(bp, now):
    assert _commands(_night(bp, now, room=16.4)[1]) == [("climate.turn_on", {})]


@pytest.mark.parametrize("now,due", [
    (at(11, 5, 29), True), (at(11, 5, 30), False), (at(11, 5, 34), False), (at(11, 5, 35), True),
    (at(13, 5, 31), False), (at(13, 6, 0), True), (at(14, 6, 31), False), (at(14, 6, 36), True),
])
def test_us05_re_heat_waits_five_minutes_after_the_planned_start_on_weekdays_and_weekends(bp, now, due):
    assert _commands(_night(bp, now, room=16.4)[1]) == ([("climate.turn_on", {})] if due else [])


def test_us05_no_turn_off_is_sent_before_wake_time_once_the_unit_runs(bp):
    for now in (at(10, 19, 31), at(10, 23), at(11, 2, 30), at(11, 4), at(11, 6), at(11, 7, 14)):
        for room in (16.4, 16.5, 18.0):
            _, calls, _ = _night(bp, now, room=room, ac_started_ts=STARTED, **HEAT)
            assert "climate.turn_off" not in [s for s, _ in calls], (now, room)


def test_us05_deep_night_check_nudges_up_once_by_the_correction_step(bp):
    ctx, calls, _ = _night(bp, at(11, 1), room=16.4, **HEAT)
    assert (ctx["in_deep_check"], ctx["heat_hold_sp"]) == (True, 21.0)
    assert _commands(calls) == [("climate.set_temperature", {"temperature": 22.5})]
    assert _commands(_night(bp, at(11, 1, 9), room=16.4, **dict(HEAT, current_setpoint=22.5))[1]) == []
    for now, room, over in ((at(11, 0, 59), 16.4, {}), (at(11, 1, 10), 16.4, {}), (at(11, 1), 16.5, {}),
                            (at(11, 1), 16.4, dict(current_setpoint=19.0))):
        assert _commands(_night(bp, now, room=room, **dict(HEAT, **over))[1]) == [], (now, room, over)


@pytest.mark.parametrize("over,expected", [
    (dict(correction_step=4.0), 24.0),
    (dict(ac_max_temp=22.0), 22.0),
    (dict(ac_temp_step=1.0), 22.0),
    (dict(winter_target=20, hall_offset=3.5, current_setpoint=23.5), 24.0),
    (dict(winter_target=20, hall_offset=4.0, current_setpoint=24.0), None),
])
def test_us05_the_nudge_is_capped_at_24_the_unit_max_and_rounded_down_to_the_step(bp, over, expected):
    _, calls, _ = _night(bp, at(11, 1), room=16.4, **dict(HEAT, **over))
    assert _commands(calls) == ([("climate.set_temperature", {"temperature": expected})] if expected else [])


def test_us05_nothing_is_sent_in_summer_on_a_manual_run_without_heat_or_with_unknown_limits(bp):
    assert _night(bp, at(10, 23), season="off", room=16.4)[1:] == ([], False)
    assert _night(bp, at(10, 23), is_real_trigger=False, room=16.4)[1:] == ([], False)
    for over in (dict(ac_hvac_modes=["off", "cool"]), dict(ac_limits_known=False)):
        assert _commands(_night(bp, at(10, 23), room=16.4, **over)[1]) == [], over


def test_us05_heat_backstop_stands_down_in_the_heating_season_so_a_re_heated_unit_is_not_forced_to_cool(bp):
    ((conds, _),) = _calls_with(bp, "heat_backstop_due")
    cond = next(t for t in conds if "heat_backstop_due" in t)
    render = lambda **kw: _reparse(_env(at(11, 2)).from_string(cond).render(is_real_trigger=True, heat_backstop_due=True, **kw))
    assert render(heating_season=False) is True
    assert render(heating_season=True) is False


def test_us06_a_unit_that_comes_on_in_heat_after_the_planned_start_gets_no_climate_or_fan_command(bp):
    for now in (at(11, 5, 31), at(11, 5, 40), at(11, 6, 30)):
        for room in (16.4, 18.0, 19.0):
            _, calls, _ = _night(bp, now, room=room, ac_started_ts=STARTED, **HEAT)
            assert _commands(calls) == [] and _created(calls) == [], (now, room)
            assert not [s for s, _ in calls if s.startswith("fan.")], (now, room)


@pytest.mark.parametrize("mode", ["cool", "dry", "fan_only"])
def test_us06_a_unit_that_comes_on_in_another_mode_gets_one_heat_command_and_one_notice(bp, mode):
    over = dict(ac_is_running=True, current_hvac_mode=mode, current_setpoint=24.0, ac_started_ts=STARTED)
    ctx, calls, stopped = _night(bp, at(11, 5, 34), room=19.0, **over)
    assert _commands(calls) == [("climate.set_temperature", {"hvac_mode": "heat", "temperature": 21.0})]
    assert _created(calls) == [NOTICE] and stopped
    _, calls, _ = _night(bp, at(11, 5, 34), room=19.0, enable_notifications=False, **over)
    assert len(_commands(calls)) == 1 and _created(calls) == []


def test_us06_the_correction_is_single_and_only_for_a_unit_the_timer_just_started(bp):
    cool = dict(ac_is_running=True, current_hvac_mode="cool", current_setpoint=24.0)
    for now, started in ((at(11, 5, 29), at(11, 5, 29)), (at(11, 5, 36), at(11, 5, 30)),
                         (at(11, 5, 34), at(11, 4)), (at(11, 2), at(11, 2))):
        _, calls, _ = _night(bp, now, room=19.0, ac_started_ts=started.timestamp(), **cool)
        assert _commands(calls) == [] and _created(calls) == [], (now, started)
    for over in (dict(ac_hvac_modes=["off", "cool"]), dict(ac_limits_known=False)):
        _, calls, _ = _night(bp, at(11, 5, 34), room=19.0, ac_started_ts=STARTED, **cool, **over)
        assert _commands(calls) == [] and _created(calls) == [], over


def test_us06_wake_time_is_one_turn_off(bp):
    _, calls, _ = _night(bp, at(11, 7, 15), ac_started_ts=STARTED, **HEAT)
    assert _commands(calls) == [("climate.turn_off", {})]
