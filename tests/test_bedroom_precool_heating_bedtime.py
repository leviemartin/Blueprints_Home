"""Acceptance tests for the bedroom_precool.yaml v1.3.0 winter bedtime minute: park in heat, switch off, arm the LG timer (US-04, US-13, US-14)."""
from datetime import datetime

import pytest
import yaml

from test_bedroom_precool_structure import (
    BP_PATH,
    TZ,
    HassLoader,
    _Input,
    _env,
    _has_condition_text,
    _has_notification_id,
    _has_stop_text,
    _reparse,
    _top_level_steps,
)

TOGGLE = "input_boolean.heating_season"
TIMER = "number.hall_ac_power_on_timer"
NOTICE = "bedroom_precool_heat_timer_not_armed"
# Fixture: bedtime 19:30, wake 07:15, weekday morning 06:15, weekend morning 06:45, target 18 + hall offset 3 = hold 21.
BASE = dict(
    winter_target=18, prewarm_offset=0.5, tolerance=1.5, hall_offset=3.0, heating_drive_setpoint=24.0,
    heating_skip_threshold=12, heating_season_toggle=[TOGGLE], heating_bias_helper=[], enable_auto_learn=True,
    base_minutes=20, k_indoor=15, k_outdoor=1.0, safety_margin_minutes=25, lead_cap_minutes=240,
    bedtime="19:30:00", wake_time="07:15:00", wake_tod="07:15:00", bedtime_tod="19:30:00",
    earliest_turn_on_tod="15:30:00", morning_time="06:15:00", weekend_morning_time="06:45:00",
    ac_power_on_timer=[TIMER], outdoor_now=10.0, warmest_bedroom=19.0, coldest_bedroom=19.0,
    forecast_window_temps=[2.0, 5.0], forecast_daily_list=[], ac_climate="climate.hall", ac_is_running=False,
    current_hvac_mode="off", ac_hvac_modes=["off", "heat", "cool"], ac_min_temp=16.0, ac_max_temp=30.0,
    ac_temp_step=0.5, ac_limits_known=True, current_setpoint=19.5, current_setpoint_known=True,
    ac_state_age_sec=600, is_real_trigger=True, manual_off=False, enable_notifications=True,
)
RUNNING = dict(ac_is_running=True, current_hvac_mode="heat", current_setpoint=21.0)


class _Stop(Exception):
    pass


@pytest.fixture(scope="module")
def bp():
    return yaml.load(BP_PATH.read_text(), Loader=HassLoader)


def on(day, hour=19, minute=30):
    return datetime(2026, 11, day, hour, minute, tzinfo=TZ)


def _val(template, ctx, now):
    return _reparse(_env(now).from_string(str(template)).render(**ctx).strip())


def _run(nodes, ctx, now, calls, store, fail_set):
    """Execute an action list the way HA does: variables in order, the first matching choose branch, services
    recorded. A number.set_value lands in the store (what the read-back sees) unless the set is made to fail."""
    for node in nodes:
        if "variables" in node:
            for key, template in node["variables"].items():
                ctx[key] = _val(template, ctx, now)
        elif "choose" in node:
            for branch in node["choose"]:
                if all(_val(c["value_template"], ctx, now) for c in branch["conditions"]):
                    _run(branch["sequence"], ctx, now, calls, store, fail_set)
                    break
            else:
                _run(node.get("default", []), ctx, now, calls, store, fail_set)
        elif "service" in node:
            data = {k: _val(v, ctx, now) for k, v in (node.get("data") or {}).items()}
            calls.append((node["service"], data))
            if node["service"] == "number.set_value" and not fail_set:
                store[_val(node["target"]["entity_id"], ctx, now)] = f"{float(data['value'])}"
        elif "stop" in node:
            raise _Stop(node["stop"])


def _winter_steps(bp):
    steps = _top_level_steps(bp)
    overcool = next(i for i, s in enumerate(steps) if _has_notification_id(s, "bedroom_precool_overcool_fault"))
    end = next(i for i in range(overcool + 1, len(steps)) if _has_stop_text(steps[i], "Heating season"))
    assert _has_condition_text(steps[end + 1], "phase == 'DAY_OFF'"), "the winter block must sit before the phase dispatch"
    derived = next(s for s in steps if "heat_stage" in (s.get("variables") or {}))
    return [derived] + steps[overcool + 1 : end + 1]


def _bedtime(bp, now, season="on", timer="5.0", timer_max=24, fail_set=False, **over):
    store = {TOGGLE: season, TIMER: timer}
    ctx = dict(
        BASE,
        now_tod=now.strftime("%H:%M:%S"),
        states=lambda e: store.get(e, "unknown"),
        state_attr=lambda e, a: timer_max if (e, a) == (TIMER, "max") else None,
    )
    ctx.update(over)
    calls, stopped = [], False
    try:
        _run(_winter_steps(bp), ctx, now, calls, store, fail_set)
    except _Stop:
        stopped = True
    return ctx, calls, stopped


def _acts(calls):
    return [(s, d) for s, d in calls if s.startswith(("climate.", "number."))]


def _created(calls):
    return [d["notification_id"] for s, d in calls if s == "persistent_notification.create"]


def _sets(calls):
    return [d for s, d in calls if s == "number.set_value"]


def test_us04_bedtime_minute_turns_off_once_and_arms_a_10_hour_timer(bp):
    ctx, calls, stopped = _bedtime(bp, on(10), **RUNNING)
    assert (ctx["timer_hours"], ctx["timer_start_tod"]) == (10, "05:30:00")
    assert _acts(calls) == [("climate.turn_off", {}), ("number.set_value", {"value": 10})] and stopped
    assert _created(calls) == []


@pytest.mark.parametrize("day,morning,weekend,hours,start", [
    (10, "06:15:00", "06:45:00", 10, "05:30:00"),
    (10, "06:30:00", "06:45:00", 11, "06:30:00"),
    (12, "06:15:00", "06:45:00", 10, "05:30:00"),
    (13, "06:15:00", "06:45:00", 11, "06:30:00"),
    (14, "06:15:00", "06:45:00", 11, "06:30:00"),
    (15, "06:15:00", "06:45:00", 10, "05:30:00"),
])
def test_us04_morning_time_by_weekday_or_weekend_sets_the_whole_hours(bp, day, morning, weekend, hours, start):
    ctx, calls, _ = _bedtime(bp, on(day), morning_time=morning, weekend_morning_time=weekend)
    assert (ctx["timer_hours"], ctx["timer_start_tod"]) == (hours, start)
    assert _acts(calls) == [("number.set_value", {"value": hours})]


def test_us04_unit_already_off_at_bedtime_still_gets_the_timer_once(bp):
    _, calls, _ = _bedtime(bp, on(10))
    assert _acts(calls) == [("number.set_value", {"value": 10})]


def test_us04_planned_start_is_never_at_or_after_wake_time(bp):
    for morning in ("06:30:00", "07:15:00", "08:00:00", "23:00:00"):
        ctx, calls, _ = _bedtime(bp, on(10), morning_time=morning)
        assert (ctx["timer_hours"], ctx["timer_start_tod"]) == (11, "06:30:00"), morning
        assert _sets(calls) == [{"value": 11}], morning


@pytest.mark.parametrize("over,expected", [
    (dict(current_hvac_mode="cool", current_setpoint=24.0), [
        ("climate.set_hvac_mode", {"hvac_mode": "heat"}), ("climate.set_temperature", {"temperature": 21.0})]),
    (dict(current_setpoint=24.0), [("climate.set_temperature", {"temperature": 21.0})]),
    (dict(current_setpoint=21.0), []),
    (dict(winter_target=20, current_setpoint=24.0, ac_max_temp=22.0), [("climate.set_temperature", {"temperature": 22.0})]),
])
def test_us04_unit_is_parked_in_heat_at_the_hold_setpoint_before_it_is_switched_off(bp, over, expected):
    _, calls, _ = _bedtime(bp, on(10), **dict(RUNNING, **over))
    assert _acts(calls) == expected + [("climate.turn_off", {}), ("number.set_value", {"value": 10})]


@pytest.mark.parametrize("now", [on(10, 19, 29), on(10, 19, 31), on(10, 18, 0), on(10, 7, 30)])
def test_us04_no_timer_is_set_outside_the_bedtime_minute(bp, now):
    _, calls, _ = _bedtime(bp, now, **RUNNING)
    assert _sets(calls) == [] and _created(calls) == []


def test_us04_summer_and_manual_runs_do_not_arm_the_timer(bp):
    assert _bedtime(bp, on(10), season="off", **RUNNING)[1:] == ([], False)
    assert _bedtime(bp, on(10), is_real_trigger=False, **RUNNING)[1:] == ([], False)


@pytest.mark.parametrize("over", [
    dict(ac_power_on_timer=[]),
    dict(timer="unavailable"),
    dict(timer="unknown"),
    dict(timer_max=8),
])
def test_us14_a_timer_that_cannot_be_set_gives_one_notice_and_no_morning_command(bp, over):
    _, calls, _ = _bedtime(bp, on(10), **dict(RUNNING, **over))
    assert _created(calls) == [NOTICE]
    assert _sets(calls) == []
    assert _acts(calls) == [("climate.turn_off", {})]


def test_us14_a_set_that_does_not_read_back_gives_one_notice(bp):
    _, calls, _ = _bedtime(bp, on(10), fail_set=True)
    assert _sets(calls) == [{"value": 10}] and _created(calls) == [NOTICE]
    assert _created(_bedtime(bp, on(10))[1]) == []
    assert _created(_bedtime(bp, on(10), timer_max=10)[1]) == []


def test_us14_notice_follows_the_notification_switch(bp):
    for over in (dict(fail_set=True), dict(ac_power_on_timer=[])):
        assert _created(_bedtime(bp, on(10), enable_notifications=False, **over)[1]) == [], over


def test_us13_no_heat_command_or_timer_at_bedtime_without_heat_mode_or_known_limits(bp):
    for over in (dict(ac_hvac_modes=["off", "cool"]), dict(ac_limits_known=False)):
        _, calls, _ = _bedtime(bp, on(10), **dict(RUNNING, current_hvac_mode="cool", current_setpoint=24.0, **over))
        assert _acts(calls) == [("climate.turn_off", {})] and _created(calls) == [], over


def test_us14_timer_and_weekend_inputs_exist_with_safe_defaults_and_are_bound(bp):
    inputs, top = bp["blueprint"]["input"], bp["variables"]
    for key in ("weekend_morning_time", "ac_power_on_timer"):
        assert isinstance(top.get(key), _Input) and top[key].name == key, key
    timer = inputs["ac_power_on_timer"]
    assert timer["default"] == [] and timer["selector"]["entity"]["domain"] == "number"
    assert inputs["deep_night_check"]["default"] < inputs["weekend_morning_time"]["default"] < inputs["wake_time"]["default"]
