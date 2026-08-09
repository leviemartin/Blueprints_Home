"""Structural + logic pins for lg_ac_climate.yaml (LG AC Climate Control v1.1.0).

Run: cd ~/AI/projects/Blueprints_Home && \
     ~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q
"""
from pathlib import Path

import pytest
import yaml

BP_PATH = Path(__file__).resolve().parent.parent / "lg_ac_climate.yaml"


class _Input:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"!input {self.name}"

    def __eq__(self, other):
        return isinstance(other, _Input) and other.name == self.name


class HassLoader(yaml.SafeLoader):
    pass


HassLoader.add_constructor(
    "!input", lambda loader, node: _Input(loader.construct_scalar(node))
)


@pytest.fixture(scope="module")
def bp():
    with BP_PATH.open() as fh:
        return yaml.load(fh, Loader=HassLoader)


@pytest.fixture(scope="module")
def inputs(bp):
    return bp["blueprint"]["input"]


def get_var(bp, name):
    for step in bp["action"]:
        if "variables" in step and name in step["variables"]:
            return step["variables"][name]
    raise KeyError(name)


def step_kind(step):
    if "service" in step:
        return f"service:{step['service']}"
    for k in ("choose", "stop", "variables", "condition"):
        if k in step:
            return k
    return "other"


def ladder(bp):
    # STEP 3 = the LAST action step, a choose ladder
    return bp["action"][-1]["choose"]


def branch_cond(branch):
    c = branch["conditions"][0]
    return " ".join(c["value_template"].split())


def seq_kinds(seq):
    return [step_kind(s) for s in seq]


# ---- v1.0.0 invariants that v1.1.0 must not disturb ----

def test_mode_and_overflow(bp):
    assert bp["mode"] == "restart"
    assert bp["max_exceeded"] == "silent"


def test_untouched_inputs_survive(inputs):
    for name in ("climate_entity", "temperature_sensors", "sensor_strategy",
                 "weather_entity", "door_sensor", "temp_range_low",
                 "temp_range_high", "deadband_outdoor_threshold",
                 "vacation_toggle", "fan_speed_low_threshold",
                 "fan_speed_medium_threshold", "escalation_stage_1_minutes",
                 "escalation_stage_2_minutes", "door_off_delay"):
        assert name in inputs, name


def test_door_sensor_stays_multiple(inputs):
    # research §3: empty-list trigger validity requires multiple: true
    assert inputs["door_sensor"]["selector"]["entity"]["multiple"] is True
    assert inputs["door_sensor"]["default"] == []


def test_fan_discovery_untouched(bp):
    assert "state_attr(climate_ac, 'fan_modes')" in get_var(bp, "available_fan_modes")


# ---- v1.1.0 additions ----

def test_version_bumped(bp):
    assert bp["blueprint"]["name"] == "LG AC Climate Control v1.1.0"
    assert "**Version: 1.1.0**" in bp["blueprint"]["description"]


def test_new_input_schemas(inputs):
    cm = inputs["comfort_margin"]
    assert cm["default"] == 0.5
    n = cm["selector"]["number"]
    assert (n["min"], n["max"], n["step"]) == (0.0, 2.0, 0.1)

    st = inputs["sensor_staleness_minutes"]
    assert st["default"] == 90
    n = st["selector"]["number"]
    assert (n["min"], n["max"], n["step"]) == (15, 1440, 5)

    hh = inputs["manual_hold_helper"]
    assert hh["default"] == ""
    assert hh["selector"]["entity"]["domain"] == "input_text"

    hm = inputs["manual_hold_minutes"]
    assert hm["default"] == 60
    n = hm["selector"]["number"]
    assert (n["min"], n["max"], n["step"]) == (15, 360, 5)


def test_variable_mappings_for_new_inputs(bp):
    v = bp["variables"]
    assert v["margin"] == _Input("comfort_margin")
    assert v["sensor_staleness"] == _Input("sensor_staleness_minutes")
    assert v["hold_helper"] == _Input("manual_hold_helper")
    assert v["hold_minutes"] == _Input("manual_hold_minutes")


def test_validation_gate_covers_margin(bp):
    # STEP 2 is the first choose in action (after the variables step)
    gate = bp["action"][1]["choose"]
    conds = [branch_cond(b) for b in gate]
    assert conds[0] == "{{ temp_low | float >= temp_high | float }}"
    assert conds[1] == ("{{ (margin | float * 2) >= "
                        "(temp_high | float - temp_low | float) }}")
    for b in gate:
        assert seq_kinds(b["sequence"]) == ["service:persistent_notification.create", "stop"]


def test_staleness_filter_uses_last_reported(bp):
    vt = get_var(bp, "valid_temps")
    assert "last_reported" in vt
    assert "last_updated" not in vt          # wrong field — unchanged re-reports must count
    assert "sensor_staleness | int * 60" in vt
    assert "states[s] is not none" in vt


def test_weather_ok_and_safe_deadband(bp):
    raw = " ".join(str(get_var(bp, "outdoor_temp_raw")).split())
    assert raw == "{{ state_attr(entity_weather, 'temperature') }}"
    ok = " ".join(get_var(bp, "weather_ok").split())
    assert ok == ("{{ outdoor_temp_raw is not none and "
                  "outdoor_temp_raw | float(none) is not none }}")
    da = " ".join(get_var(bp, "deadband_active").split())
    assert da == ("{{ (not weather_ok) or "
                  "(outdoor_distance | float < deadband_thresh | float) }}")


def test_target_mode_hysteresis(bp):
    tm = " ".join(get_var(bp, "target_mode").split())
    assert tm == (
        "{% if current_temp | float > temp_high | float %} cool "
        "{% elif current_temp | float < temp_low | float %} heat "
        "{% elif current_ac_mode == 'cool' and current_temp | float > "
        "(temp_high | float - margin | float) %} cool "
        "{% elif current_ac_mode == 'heat' and current_temp | float < "
        "(temp_low | float + margin | float) %} heat "
        "{% else %} off {% endif %}"
    )


def test_escalation_distance_gated(bp):
    tf = " ".join(get_var(bp, "target_fan").split())
    # the gate must be the FIRST branch so near-target never escalates
    assert tf.index("dist < fan_low_thresh") < tf.index("esc_stage_2")
    assert "{% if dist < fan_low_thresh | float %} {{ base_fan }}" in tf
