"""Acceptance tests for the bedroom_precool.yaml v1.3.0 heating lead time and stages (US-02, US-03, US-11)."""
import re
from datetime import datetime

import pytest
import yaml

from test_bedroom_precool_structure import (
    BP_PATH,
    TZ,
    HassLoader,
    _Input,
    _render_chain,
    _service_steps,
)

HELPER = "input_number.heating_lead_bias"
HEAT_CHAIN = [
    "forecast_daily_low", "forecast_daily_low_ok", "forecast_low",
    "winter_target_eff", "prewarm_offset_eff", "winter_aim",
    "heat_outdoor_for_lead", "heat_delta_in", "heat_delta_out",
    "heating_bias_entity", "heating_bias_configured", "heating_bias",
    "heat_lead_raw", "heat_lead", "heat_needed", "overheat_level", "reheat_level",
    "heat_turn_on_ts", "heat_turn_on_tod", "heat_running", "heat_stage",
]
# US-02 fixture: toggle on, target 18, offset 0.5, tolerance 1.5, bedtime 19:30, coldest 16.0.
BASE = dict(
    heating_season=True, winter_target=18, prewarm_offset=0.5, tolerance=1.5,
    base_minutes=20, k_indoor=15, k_outdoor=1.0, solar_max_minutes=45, solar_load=1.0,
    safety_margin_minutes=25, lead_cap_minutes=240, heating_skip_threshold=12,
    bedtime="19:30:00", wake_tod="07:15:00", bedtime_tod="19:30:00", earliest_turn_on_tod="15:30:00",
    enable_auto_learn=True, heating_bias_helper=[], lead_bias=50,
    ac_is_running=False, current_hvac_mode="off", outdoor_now=10.0,
    warmest_bedroom=17.0, coldest_bedroom=16.0, forecast_window_temps=[2.0, 5.0], forecast_daily_list=[],
)


@pytest.fixture(scope="module")
def bp():
    return yaml.load(BP_PATH.read_text(), Loader=HassLoader)


def at(hour, minute=0):
    return datetime(2026, 11, 10, hour, minute, tzinfo=TZ)


def _heat(bp, now=None, helper=None, **over):
    now = now or at(18)
    table = {} if helper is None else {HELPER: helper}
    ctx = dict(BASE, now_tod=now.strftime("%H:%M:%S"), states=lambda e: table.get(e, "unknown"))
    if helper is not None:
        ctx["heating_bias_helper"] = [HELPER]
    ctx.update(over)
    return _render_chain(bp, HEAT_CHAIN, now, ctx)


def test_us02_lead_is_the_mirrored_formula_aimed_at_the_winter_aim_with_no_solar_term(bp):
    ctx = _heat(bp)
    assert ctx["forecast_low"] == 2.0
    assert ctx["winter_aim"] == 18.5
    assert (ctx["heat_delta_in"], ctx["heat_delta_out"]) == (2.5, 16.5)
    assert ctx["heat_lead_raw"] == 20 + 15 * 2.5 + 1.0 * 16.5 + 25
    assert ctx["heat_lead"] == 99
    assert ctx["heat_turn_on_tod"] == "17:51:00"
    assert _heat(bp, solar_load=0.0)["heat_lead"] == 99
    assert _heat(bp, coldest_bedroom=1.0, forecast_window_temps=[-30.0])["heat_lead"] == 240


def test_us02_forecast_low_falls_back_to_the_daily_low_then_the_live_outdoor_reading(bp):
    daily = [
        {"datetime": "2026-11-11T12:00:00+01:00", "temperature": 9.0, "templow": 0.0},
        {"datetime": "2026-11-10T12:00:00+01:00", "temperature": 8.0, "templow": 3.0},
    ]
    assert _heat(bp, forecast_window_temps=[], forecast_daily_list=daily, outdoor_now=5.0)["forecast_low"] == 3.0
    assert _heat(bp, forecast_window_temps=[], forecast_daily_list=daily, outdoor_now=1.0)["forecast_low"] == 1.0
    assert _heat(bp, forecast_window_temps=[], outdoor_now=4.5)["forecast_low"] == 4.5


def test_us02_evening_stage_waits_for_the_turn_on_instant_drives_then_holds_at_the_aim(bp):
    assert _heat(bp, at(17, 50))["heat_stage"] == "WAIT"
    assert _heat(bp, at(17, 51))["heat_stage"] == "DRIVE"
    running = dict(ac_is_running=True, current_hvac_mode="heat")
    assert _heat(bp, at(18), coldest_bedroom=18.4, **running)["heat_stage"] == "DRIVE"
    assert _heat(bp, at(18), coldest_bedroom=18.5, **running)["heat_stage"] == "HOLD"
    assert _heat(bp, at(18), heating_season=False)["heat_stage"] == "OFF"


def test_us02_night_stage_reheats_below_the_band_and_flags_overheat_above_it(bp):
    night = at(23)
    ctx = _heat(bp, night, coldest_bedroom=17.5, warmest_bedroom=18.5)
    assert (ctx["overheat_level"], ctx["reheat_level"], ctx["heat_stage"]) == (19.5, 16.5, "HOLD")
    assert _heat(bp, night, coldest_bedroom=16.0, warmest_bedroom=18.5)["heat_stage"] == "REHEAT"
    assert _heat(bp, night, coldest_bedroom=17.5, warmest_bedroom=20.0)["heat_stage"] == "OVERHEAT"


def test_us03_mild_evening_produces_no_heat_and_a_colder_room_starts_the_pre_warm(bp):
    mild = dict(forecast_window_temps=[13.0, 14.0], warmest_bedroom=19.0)
    ctx = _heat(bp, at(19), coldest_bedroom=18.0, **mild)
    assert (ctx["forecast_low"], ctx["heat_needed"], ctx["heat_stage"]) == (13.0, False, "SKIP")
    cold = _heat(bp, at(19), coldest_bedroom=17.5, **mild)
    assert (cold["heat_needed"], cold["heat_stage"]) == (True, "DRIVE")
    running = dict(ac_is_running=True, current_hvac_mode="heat", coldest_bedroom=18.0)
    assert _heat(bp, at(19), **mild, **running)["heat_stage"] == "DRIVE"


def test_us11_heating_bias_is_read_from_its_own_helper_and_never_from_the_summer_one(bp):
    assert _heat(bp, helper="7")["heating_bias"] == 7.0
    assert _heat(bp, helper="7")["heat_lead"] == 106
    empty = _heat(bp)
    assert (empty["heating_bias_configured"], empty["heating_bias"], empty["heat_lead"]) == (False, 0, 99)
    assert _heat(bp, helper="7", enable_auto_learn=False)["heating_bias"] == 0
    assert _heat(bp, helper="unavailable")["heating_bias"] == 0


def test_us11_heating_bias_helper_and_skip_threshold_inputs_are_bound_at_top_level(bp):
    inputs = bp["blueprint"]["input"]
    for key in ("heating_bias_helper", "heating_skip_threshold"):
        assert key in inputs, key
        assert isinstance(bp["variables"].get(key), _Input) and bp["variables"][key].name == key, key
    helper = inputs["heating_bias_helper"]
    assert helper["default"] == [] and helper["selector"]["entity"]["domain"] == "input_number"
    assert inputs["heating_skip_threshold"]["default"] == 12


def test_us02_debug_output_shows_each_lead_term(bp):
    debug = next(
        s for _, s in _service_steps(bp.get("action"), [])
        if (s.get("data") or {}).get("notification_id") == "bedroom_precool_debug"
    )
    message = debug["data"]["message"]
    terms = ("heat_stage", "winter_aim", "overheat_level", "reheat_level", "heat_needed", "heat_lead", "heat_lead_raw",
             "base_minutes", "k_indoor", "heat_delta_in", "k_outdoor", "heat_delta_out", "safety_margin_minutes",
             "heating_bias", "forecast_low", "heat_turn_on_tod")
    for term in terms:
        assert re.search(r"\{\{\s*" + term + r"\s*\}\}", message), term
