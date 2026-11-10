"""Acceptance tests for the bedroom_precool.yaml v1.3.0 heat backstop (2026-11-03 rule): toggle off only, one cool command at the safe setpoint, never a turn-off (US-12)."""
from datetime import datetime, timedelta

import pytest
import yaml

from test_bedroom_precool_heating_bedtime import _run, _val
from test_bedroom_precool_structure import (
    BP_PATH,
    TZ,
    HassLoader,
    _calls_with,
    _guard,
    _has_condition_text,
    _service_steps,
    _top_level_steps,
    _var_template,
)

# Fixture: winter target 18 + tolerance 1.5 = level 19.5; maintaining (safe) setpoint 21; toggle off; a unit running in heat.
NOW = datetime(2026, 9, 9, 23, 0, tzinfo=TZ)
BASE = dict(
    winter_target=18, tolerance=1.5, maintaining_setpoint=21.0, ac_climate="climate.hall", is_real_trigger=True,
    heating_season=False, ac_is_running=True, current_hvac_mode="heat",
)
COOL_AT_SAFE = [("climate.set_temperature", {"hvac_mode": "cool", "temperature": 21.0})]


@pytest.fixture(scope="module")
def bp():
    return yaml.load(BP_PATH.read_text(), Loader=HassLoader)


def _backstop(bp, temps, **over):
    """Render the real predicate templates, then run the real STEP 5d on one tick; returns the recorded calls."""
    ctx = dict(BASE, bedroom_valid_temps=list(temps), bedroom_sensors_ok=len(temps) > 0)
    ctx.update(over)
    for name in ("safe_overheat_level", "heat_backstop_due"):
        ctx[name] = _val(_var_template(bp, name), ctx, NOW)
    step = next(s for s in _top_level_steps(bp) if _has_condition_text(s, "is_real_trigger and heat_backstop_due"))
    calls = []
    _run([step], ctx, NOW, calls, {}, False)
    return calls


@pytest.mark.parametrize("temps", [[19.6], [18.0, 19.6], [25.0], []])
def test_us12_toggle_off_a_unit_found_heating_gets_one_cool_command_at_the_safe_setpoint_when_a_room_is_over_the_level_or_every_sensor_failed(bp, temps):
    assert _backstop(bp, temps) == COOL_AT_SAFE


@pytest.mark.parametrize("temps", [[19.5], [17.0, 18.0], [10.0]])
def test_us12_a_heat_run_started_by_hand_with_the_rooms_in_range_gets_no_command(bp, temps):
    assert _backstop(bp, temps) == []


def test_us12_the_level_is_the_winter_target_capped_at_20_plus_the_tolerance(bp):
    assert _backstop(bp, [21.4], winter_target=21) == []
    assert _backstop(bp, [21.6], winter_target=21) == COOL_AT_SAFE


@pytest.mark.parametrize("temps", [[25.0], [19.6], []])
def test_us12_with_the_toggle_on_the_backstop_never_fires(bp, temps):
    assert _backstop(bp, temps, heating_season=True) == []


@pytest.mark.parametrize("over", [
    dict(current_hvac_mode="cool"),
    dict(current_hvac_mode="fan_only"),
    dict(ac_is_running=False, current_hvac_mode="off"),
    dict(is_real_trigger=False),
])
def test_us12_only_a_running_unit_reporting_heat_on_a_real_tick_is_corrected(bp, over):
    assert _backstop(bp, [25.0], **over) == []


def test_us12_the_backstop_is_one_set_temperature_call_and_no_turn_off_is_gated_on_it(bp):
    ((conds, step),) = _calls_with(bp, "heat_backstop_due")
    assert step["service"] == "climate.set_temperature"
    assert step["target"]["entity_id"] == "{{ ac_climate }}"
    assert step["data"] == {"hvac_mode": "cool", "temperature": "{{ maintaining_setpoint | float }}"}
    turn_offs = [c for c, s in _service_steps(_top_level_steps(bp), []) if s.get("service") == "climate.turn_off"]
    assert not any("heat_backstop_due" in t for c in turn_offs for t in c)


def test_us12_settle_leaves_a_heat_read_alone_and_stands_down_while_the_backstop_is_due(bp):
    t = datetime(2026, 9, 9, 23, 7, tzinfo=TZ)
    base = dict(
        night_mode="fan_only", phase="NIGHT_HOLD", ac_is_running=True, ac_started_ts=(t - timedelta(minutes=2)).timestamp(),
        safe_overheat_level=19.5, current_setpoint=18.0, bedroom_sensors_ok=True,
    )
    hot = _guard(bp, t, **base, current_hvac_mode="heat", bedroom_valid_temps=[24.0])
    assert hot["heat_backstop_due"] is True
    assert hot["settle_mode_due"] is False and hot["settle_setpoint_due"] is False
    calm = _guard(bp, t, **base, current_hvac_mode="heat", bedroom_valid_temps=[19.0])
    assert calm["heat_backstop_due"] is False and calm["settle_mode_due"] is False
    for mode in ("fan_only", "auto"):
        other = _guard(bp, t, **base, current_hvac_mode=mode, bedroom_valid_temps=[24.0])
        assert other["heat_backstop_due"] is False and other["settle_mode_due"] is True, mode
