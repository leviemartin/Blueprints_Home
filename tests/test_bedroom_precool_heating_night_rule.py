"""bedroom_precool.yaml v1.4.0 winter night rule: start level, stop level, fan cap and manual-off memory.

Fixture (from test_bedroom_precool_heating_night): bedtime 19:30, wake 07:15, weekday planned start 05:30.
"""
import json
from pathlib import Path

import pytest

from test_bedroom_precool_heating_night import BASE, TOGGLE, _commands, _night, at, bp  # noqa: F401

HELPER = "input_boolean.bedroom_night_manual_off"
RULE = dict(night_reheat_on_temp=15.5, night_reheat_off_temp=18.0, night_heat_fan="medium",
            night_manual_off_helper=[HELPER], ac_fan_modes=["auto", "low", "medium", "high"], current_fan="high")
INSTANCE = Path(__file__).resolve().parent.parent / "deploy" / "bedroom_precool_1779553673971.json"


def run(bp, now, room, helper="off", **over):
    table = {TOGGLE: "on", HELPER: helper}
    guards = dict(ac_unavailable=False, ac_off_since_ts=now.timestamp() - 30, automation_up_since_ts=0,
                  vacation_changed_ts=0, vacation_active=False, bedroom_sensors_ok=True,
                  bedroom_valid_temps=[room], safe_overheat_level=19.5, ac_state_age_sec=720)
    return _night(bp, now, room=room, states=lambda e: table.get(e, "unknown"), **{**RULE, **guards, **over})


def _helper_calls(calls):
    return [s for s, d in calls if s.startswith("input_boolean.")]


def test_start_level_replaces_target_minus_tolerance(bp):
    ctx, calls, _ = run(bp, at(10, 23), 15.4)
    assert (ctx["reheat_level"], ctx["heat_stage"]) == (15.5, "REHEAT")
    assert _commands(calls) == [("climate.turn_on", {}), ("climate.set_fan_mode", {"fan_mode": "medium"})]
    ctx, calls, _ = run(bp, at(10, 23), 16.0)
    assert (ctx["heat_stage"], _commands(calls)) == ("HOLD", [])


def test_left_at_zero_the_v130_level_and_bare_turn_on_stay(bp):
    ctx, calls, _ = run(bp, at(10, 23), 16.4, night_reheat_on_temp=0, night_heat_fan="leave")
    assert ctx["reheat_level"] == 16.5
    assert _commands(calls) == [("climate.turn_on", {})]


@pytest.mark.parametrize("room,expected", [(18.0, [("climate.turn_off", {})]), (18.4, [("climate.turn_off", {})]), (17.9, [])])
def test_a_heating_unit_stops_at_the_stop_level(bp, room, expected):
    _, calls, _ = run(bp, at(11, 2), room, ac_is_running=True, current_hvac_mode="heat", current_fan="medium")
    assert _commands(calls) == expected


@pytest.mark.parametrize("over", [dict(night_reheat_off_temp=0), dict(ac_state_age_sec=60)])
def test_no_stop_when_left_at_zero_or_just_started(bp, over):
    _, calls, _ = run(bp, at(11, 2), 18.5, ac_is_running=True, current_hvac_mode="heat", current_fan="medium", **over)
    assert _commands(calls) == []


def test_after_the_planned_morning_start_the_unit_runs_on_untouched(bp):
    _, calls, _ = run(bp, at(11, 5, 45), 18.5, ac_is_running=True, current_hvac_mode="heat", current_fan="high")
    assert _commands(calls) == []


@pytest.mark.parametrize("fan,expected", [("high", [("climate.set_fan_mode", {"fan_mode": "medium"})]),
                                          ("auto", [("climate.set_fan_mode", {"fan_mode": "medium"})]),
                                          ("medium", []), ("low", [])])
def test_fan_cap_brings_faster_fans_down_and_leaves_slower_ones(bp, fan, expected):
    _, calls, _ = run(bp, at(11, 1, 30), 16.5, ac_is_running=True, current_hvac_mode="heat", current_fan=fan)
    assert _commands(calls) == expected


def test_low_cap_allows_only_low(bp):
    _, calls, _ = run(bp, at(11, 1, 30), 16.5, ac_is_running=True, current_hvac_mode="heat", current_fan="medium",
                      night_heat_fan="low")
    assert _commands(calls) == [("climate.set_fan_mode", {"fan_mode": "low"})]


def test_a_manual_night_off_is_remembered_and_blocks_re_heat(bp):
    _, calls, _ = run(bp, at(10, 23, 2), 15.0, ac_state_age_sec=30)
    assert _helper_calls(calls) == ["input_boolean.turn_on"] and _commands(calls) == []
    _, calls, _ = run(bp, at(11, 3), 15.0, helper="on")
    assert _commands(calls) == [] and _helper_calls(calls) == []


@pytest.mark.parametrize("now,room", [(at(10, 19, 31), 15.0),   # the bedtime minute's own off
                                      (at(11, 2), 18.0)])       # this rule's own stop
def test_the_blueprints_own_offs_are_not_read_as_manual(bp, now, room):
    _, calls, _ = run(bp, now, room, ac_state_age_sec=30)
    assert "input_boolean.turn_on" not in _helper_calls(calls)


def test_the_memory_is_cleared_outside_the_night(bp):
    _, calls, _ = run(bp, at(11, 10), 18.0, helper="on")
    assert _helper_calls(calls) == ["input_boolean.turn_off"]


def test_no_helper_keeps_v130_manual_off_behaviour(bp):
    _, calls, _ = run(bp, at(10, 23, 2), 15.0, ac_state_age_sec=30, night_manual_off_helper=[])
    assert _helper_calls(calls) == [] and _commands(calls)[0] == ("climate.turn_on", {})


def test_bedroom_instance_wires_the_night_rule():
    i = json.loads(INSTANCE.read_text())["use_blueprint"]["input"]
    assert (i["night_reheat_on_temp"], i["night_reheat_off_temp"], i["night_heat_fan"]) == (15.5, 18, "medium")
    assert i["night_manual_off_helper"] == [HELPER]


@pytest.mark.parametrize("over", [dict(automation_up_since_ts=10**10),             # HA just restarted / re-stamped
                                  dict(ac_unavailable=True), dict(vacation_active=True),
                                  dict(bedroom_sensors_ok=False), dict(bedroom_valid_temps=[15.0, 20.0])])  # overheat off
def test_restart_vacation_sensor_and_overheat_offs_are_not_read_as_manual(bp, over):
    _, calls, _ = run(bp, at(10, 23, 2), 15.0, ac_state_age_sec=30, **over)
    assert "input_boolean.turn_on" not in _helper_calls(calls)


def test_stop_below_start_plus_one_never_switches_off(bp):
    _, calls, _ = run(bp, at(11, 2), 18.5, ac_is_running=True, current_hvac_mode="heat", current_fan="medium",
                      night_reheat_on_temp=18.0, night_reheat_off_temp=18.5)
    assert _commands(calls) == []


@pytest.mark.parametrize("age,due", [(720, True), (780, False), (1320, True), (1380, False)])
def test_fan_and_stop_retry_only_every_ten_minutes(bp, age, due):
    _, calls, _ = run(bp, at(11, 1, 30), 16.5, ac_is_running=True, current_hvac_mode="heat", current_fan="high",
                      ac_state_age_sec=age)
    assert bool(_commands(calls)) is due
    _, calls, _ = run(bp, at(11, 2), 18.2, ac_is_running=True, current_hvac_mode="heat", current_fan="medium",
                      ac_state_age_sec=age)
    assert bool(_commands(calls)) is due


def test_an_unknown_fan_reading_gets_no_command(bp):
    _, calls, _ = run(bp, at(11, 1, 30), 16.5, ac_is_running=True, current_hvac_mode="heat", current_fan="unknown")
    assert _commands(calls) == []
