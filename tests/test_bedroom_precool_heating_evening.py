"""Acceptance tests for the bedroom_precool.yaml v1.3.0 winter evening dispatch (US-02, US-03, US-09, US-13)."""
from datetime import datetime

import pytest
import yaml

from test_bedroom_precool_structure import (
    BP_PATH,
    TZ,
    HassLoader,
    _env,
    _has_condition_text,
    _has_notification_id,
    _has_stop_text,
    _reparse,
    _top_level_steps,
)

TOGGLE = "input_boolean.heating_season"
NOTICE = "bedroom_precool_heat_manual_override"
# US-02 fixture: toggle on, target 18, offset 0.5, hall offset 3, tolerance 1.5, bedtime 19:30, coldest 16.0,
# forecast low 2: aim 18.5, lead 99 min, heat turn-on 17:51.
BASE = dict(
    winter_target=18, prewarm_offset=0.5, tolerance=1.5, hall_offset=3.0, heating_drive_setpoint=24.0,
    heating_skip_threshold=12, heating_season_toggle=[TOGGLE], heating_bias_helper=[], enable_auto_learn=True,
    base_minutes=20, k_indoor=15, k_outdoor=1.0, safety_margin_minutes=25, lead_cap_minutes=240,
    bedtime="19:30:00", wake_tod="07:15:00", bedtime_tod="19:30:00", earliest_turn_on_tod="15:30:00",
    outdoor_now=10.0, warmest_bedroom=17.0, coldest_bedroom=16.0, forecast_window_temps=[2.0, 5.0],
    forecast_daily_list=[], ac_climate="climate.hall", ac_is_running=False, current_hvac_mode="off",
    ac_hvac_modes=["off", "heat", "cool"], ac_min_temp=16.0, ac_max_temp=30.0, ac_temp_step=0.5,
    ac_limits_known=True, current_setpoint=19.5, current_setpoint_known=True, ac_state_age_sec=600,
    is_real_trigger=True, manual_off=False, enable_notifications=True,
)
START = [
    ("climate.turn_on", {}),
    ("climate.set_hvac_mode", {"hvac_mode": "heat"}),
    ("climate.set_temperature", {"temperature": 24.0}),
]
RUNNING = dict(ac_is_running=True, current_hvac_mode="heat", current_setpoint=24.0)


class _Stop(Exception):
    pass


@pytest.fixture(scope="module")
def bp():
    return yaml.load(BP_PATH.read_text(), Loader=HassLoader)


def at(hour, minute=0):
    return datetime(2026, 11, 10, hour, minute, tzinfo=TZ)


def _val(template, ctx, now):
    return _reparse(_env(now).from_string(str(template)).render(**ctx).strip())


def _run(nodes, ctx, now, calls):
    """Execute an action list the way HA does: variables in order, the first matching choose branch, services recorded."""
    for node in nodes:
        if "variables" in node:
            for key, template in node["variables"].items():
                ctx[key] = _val(template, ctx, now)
        elif "choose" in node:
            for branch in node["choose"]:
                if all(_val(c["value_template"], ctx, now) for c in branch["conditions"]):
                    _run(branch["sequence"], ctx, now, calls)
                    break
            else:
                _run(node.get("default", []), ctx, now, calls)
        elif "service" in node:
            data = {k: _val(v, ctx, now) for k, v in (node.get("data") or {}).items()}
            calls.append((node["service"], data))
        elif "stop" in node:
            raise _Stop(node["stop"])


def _winter_steps(bp):
    steps = _top_level_steps(bp)
    overcool = next(i for i, s in enumerate(steps) if _has_notification_id(s, "bedroom_precool_overcool_fault"))
    end = next(i for i in range(overcool + 1, len(steps)) if _has_stop_text(steps[i], "Heating season"))
    assert _has_condition_text(steps[end + 1], "phase == 'DAY_OFF'"), "the winter block must sit before the phase dispatch"
    derived = next(s for s in steps if "heat_stage" in (s.get("variables") or {}))
    return [derived] + steps[overcool + 1 : end + 1]


def _winter(bp, now, season="on", **over):
    table = {TOGGLE: season}
    ctx = dict(BASE, now_tod=now.strftime("%H:%M:%S"), states=lambda e: table.get(e, "unknown"))
    ctx.update(over)
    calls, stopped = [], False
    try:
        _run(_winter_steps(bp), ctx, now, calls)
    except _Stop:
        stopped = True
    return ctx, calls, stopped


def _commands(calls):
    return [(s, d) for s, d in calls if s.startswith("climate.")]


def _created(calls):
    return [d["notification_id"] for s, d in calls if s == "persistent_notification.create"]


def test_us02_pre_warm_starts_at_the_turn_on_instant_with_one_command_each(bp):
    ctx, calls, stopped = _winter(bp, at(17, 51))
    assert (ctx["heat_turn_on_tod"], ctx["heat_stage"]) == ("17:51:00", "DRIVE")
    assert _commands(calls) == START and stopped
    assert _commands(_winter(bp, at(17, 50))[1]) == []


def test_us02_hold_sets_21_once_when_the_coldest_room_reaches_the_aim(bp):
    ctx, calls, _ = _winter(bp, at(18, 30), coldest_bedroom=18.5, **RUNNING)
    assert ctx["heat_stage"] == "HOLD"
    assert _commands(calls) == [("climate.set_temperature", {"temperature": 21.0})]
    assert _commands(_winter(bp, at(18, 30), coldest_bedroom=18.4, **RUNNING)[1]) == []
    held = dict(RUNNING, current_setpoint=21.0)
    assert _commands(_winter(bp, at(18, 30), coldest_bedroom=18.5, **held)[1]) == []


def test_us02_wake_switches_a_running_unit_off_until_the_earliest_turn_on(bp):
    _, calls, stopped = _winter(bp, at(7, 30), **RUNNING)
    assert _commands(calls) == [("climate.turn_off", {})] and stopped
    assert _commands(_winter(bp, at(7, 30))[1]) == []
    assert _commands(_winter(bp, at(16), **RUNNING)[1]) == []


def test_us02_block_ends_in_stop_on_a_real_winter_tick_only(bp):
    assert _winter(bp, at(18))[2] is True
    assert _winter(bp, at(18), season="off")[1:] == ([], False)
    assert _winter(bp, at(18), is_real_trigger=False)[1:] == ([], False)


@pytest.mark.parametrize("max_temp,step,drive,expect_drive,expect_hold", [
    (30.0, 0.5, 24.0, 24.0, 21.0),
    (22.5, 0.5, 24.0, 22.5, 21.0),
    (22.0, 1.0, 24.0, 22.0, 21.0),
    (20.0, 0.5, 24.0, 20.0, 20.0),
    (30.0, 1.0, 23.5, 23.0, 21.0),
])
def test_us13_heat_setpoints_are_capped_at_24_and_the_unit_max_and_rounded_down_to_the_step(
    bp, max_temp, step, drive, expect_drive, expect_hold
):
    ctx, calls, _ = _winter(bp, at(18), ac_max_temp=max_temp, ac_temp_step=step, heating_drive_setpoint=drive)
    assert (ctx["heating_drive_eff"], ctx["heat_hold_sp"]) == (expect_drive, expect_hold)
    assert _commands(calls)[-1] == ("climate.set_temperature", {"temperature": expect_drive})


def test_us02_no_heat_command_sets_more_than_24(bp):
    for hall_offset, max_temp in ((3.0, 30.0), (10.0, 30.0), (10.0, 23.0)):
        ctx, calls, _ = _winter(bp, at(18), winter_target=20, hall_offset=hall_offset, ac_max_temp=max_temp)
        assert ctx["heat_hold_sp"] == min(24.0, max_temp, 20 + hall_offset)
        sent = [d["temperature"] for s, d in calls if s == "climate.set_temperature"]
        assert sent and max(sent) <= min(24, max_temp)


def test_us03_mild_evening_sends_nothing_and_a_colder_room_starts_the_pre_warm(bp):
    mild = dict(forecast_window_temps=[13.0, 14.0], warmest_bedroom=19.0)
    ctx, calls, _ = _winter(bp, at(19), coldest_bedroom=18.0, **mild)
    assert (ctx["heat_stage"], _commands(calls)) == ("SKIP", [])
    ctx, calls, _ = _winter(bp, at(19), coldest_bedroom=17.5, **mild)
    assert (ctx["heat_stage"], _commands(calls)) == ("DRIVE", START)


def test_us09_a_setpoint_changed_by_hand_is_left_alone_with_one_notice(bp):
    ctx, calls, _ = _winter(bp, at(18), **dict(RUNNING, current_setpoint=22.0))
    assert ctx["manual_heat_setpoint"] is True
    assert _commands(calls) == [] and _created(calls) == [NOTICE]
    for ours in (24.0, 21.0):
        ctx, calls, _ = _winter(bp, at(18), **dict(RUNNING, current_setpoint=ours))
        assert ctx["manual_heat_setpoint"] is False and _created(calls) == []
    assert ("persistent_notification.dismiss", {"notification_id": NOTICE}) in calls
    _, calls, _ = _winter(bp, at(18), **dict(RUNNING, current_setpoint=22.0, ac_state_age_sec=60))
    assert _commands(calls) == [("climate.set_temperature", {"temperature": 24.0})] and _created(calls) == []


def test_us09_a_manual_off_ends_the_evening_pre_warm_and_raises_one_notice(bp):
    ctx, calls, stopped = _winter(bp, at(18), manual_off=True)
    assert ctx["heat_stage"] == "DRIVE" and stopped
    assert _commands(calls) == [] and _created(calls) == [NOTICE]
    assert _commands(_winter(bp, at(18, 40), manual_off=True)[1]) == []
    assert _created(_winter(bp, at(18), manual_off=True, enable_notifications=False)[1]) == []


def test_us13_no_heat_command_without_heat_mode_or_while_the_limits_are_unknown(bp):
    for over in (dict(ac_hvac_modes=["off", "cool"]), dict(ac_limits_known=False)):
        ctx, calls, stopped = _winter(bp, at(18), **over)
        assert ctx["heat_setpoints_allowed"] is False, over
        assert _commands(calls) == [] and _created(calls) == [] and stopped, over
