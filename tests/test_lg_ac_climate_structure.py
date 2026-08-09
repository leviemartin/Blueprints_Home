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


def test_yesterday_schedule_variables(bp):
    # exact-equality: a copy-paste of start-lists into the end variable would make
    # y_tail structurally `X > X` = dead code with a green suite (board R1-5)
    sy = " ".join(get_var(bp, "schedule_start_yesterday").split())
    assert sy == ("{{ [t_start_mon, t_start_tue, t_start_wed, t_start_thu, t_start_fri, "
                  "t_start_sat, t_start_sun][(now().weekday() - 1) % 7] }}")
    ey = " ".join(get_var(bp, "schedule_end_yesterday").split())
    assert ey == ("{{ [t_end_mon, t_end_tue, t_end_wed, t_end_thu, t_end_fri, "
                  "t_end_sat, t_end_sun][(now().weekday() - 1) % 7] }}")


def test_window_formula_owns_overnight_tail(bp):
    w = " ".join(get_var(bp, "in_operating_window").split())
    assert w == (
        "{% set t_now = now().strftime('%H:%M:%S') %} "
        "{% set today = (schedule_start_today <= t_now < schedule_end_today) "
        "if schedule_start_today <= schedule_end_today "
        "else (t_now >= schedule_start_today) %} "
        "{% set y_tail = schedule_start_yesterday > schedule_end_yesterday "
        "and t_now < schedule_end_yesterday %} "
        "{{ today or y_tail }}"
    )


def test_trigger_roster(bp):
    trigs = bp["trigger"]
    ids = [t.get("id") for t in trigs]
    assert ids == ["update_loop", "vacation_on", "init", "door_open", "vacation_off", "init"]
    reload_t = trigs[5]
    # reloads don't fire homeassistant:start (board R2-2); same id → same seed semantics.
    # If the event name were ever wrong, the trigger is inert — safe either way.
    assert (reload_t["platform"], reload_t["event_type"]) == ("event", "automation_reloaded")
    door = trigs[3]
    assert door["platform"] == "state"          # research §2: never a device trigger
    assert door["entity_id"] == _Input("door_sensor")
    assert door["to"] == "on"
    assert door["for"] == {"minutes": _Input("door_off_delay")}
    vac = trigs[4]
    assert (vac["platform"], vac["to"]) == ("state", "off")
    assert vac["entity_id"] == _Input("vacation_toggle")


def test_dismiss_steps(bp):
    d1 = bp["action"][2]
    assert step_kind(d1) == "service:persistent_notification.dismiss"
    assert d1["data"]["notification_id"] == "ac_climate_config_error"
    assert d1["continue_on_error"] is True
    d2 = bp["action"][3]
    assert step_kind(d2) == "choose"
    b = d2["choose"][0]
    assert branch_cond(b) == "{{ sensors_available }}"
    inner = b["sequence"][0]
    assert inner["data"]["notification_id"] == "ac_climate_sensor_warning"
    assert inner["continue_on_error"] is True


def test_door_is_open_no_sensor_branch_is_boolean(bp):
    d = get_var(bp, "door_is_open")
    assert "{{ false }}" in d and d.find("{{ false }}") < d.find("{% else %}")


# ---- Task 7: idempotence guards (beep elimination) ----

GUARD_SETPOINT = ("{{ current_ac_mode != desired_mode or "
                  "(state_attr(climate_ac, 'temperature') | float(-99) - "
                  "desired_setpoint | float) | abs > 0.05 }}")
GUARD_FAN = "{{ state_attr(climate_ac, 'fan_mode') != desired_fan }}"


def _acting_branches(bp):
    """cool + heat + the two in-range sub-branches, keyed for messages."""
    lad = ladder(bp)
    in_range = next(b for b in lad if "target_mode == 'off'" in branch_cond(b))
    sub = in_range["sequence"][-1]["choose"]      # deadband choose
    cool = next(b for b in lad if branch_cond(b) == "{{ target_mode == 'cool' }}")
    heat = next(b for b in lad if branch_cond(b) == "{{ target_mode == 'heat' }}")
    return {"maintenance": sub[1], "cool": cool, "heat": heat}


def test_comfort_branches_guard_every_call(bp):
    for name, b in _acting_branches(bp).items():
        kinds = seq_kinds(b["sequence"])
        assert kinds[:3] == ["variables", "choose", "choose"], (name, kinds)
        guard_temp = branch_cond(b["sequence"][1]["choose"][0])
        guard_fan = branch_cond(b["sequence"][2]["choose"][0])
        assert guard_temp == GUARD_SETPOINT, name
        assert guard_fan == GUARD_FAN, name
        inner_t = b["sequence"][1]["choose"][0]["sequence"]
        assert seq_kinds(inner_t) == ["service:climate.set_temperature"], name
        inner_f = b["sequence"][2]["choose"][0]["sequence"]
        assert seq_kinds(inner_f) == ["service:climate.set_fan_mode"], name
        # a cloud error must not abort the branch before its expected-write (board R1-3)
        assert inner_t[0]["continue_on_error"] is True, name
        assert inner_f[0]["continue_on_error"] is True, name


def test_cool_heat_desired_values(bp):
    br = _acting_branches(bp)
    cv = br["cool"]["sequence"][0]["variables"]
    assert cv["desired_mode"] == "cool"
    assert " ".join(cv["desired_setpoint"].split()) == "{{ temp_high | float }}"
    assert " ".join(cv["desired_fan"].split()) == "{{ target_fan }}"
    hv = br["heat"]["sequence"][0]["variables"]
    assert hv["desired_mode"] == "heat"
    assert " ".join(hv["desired_setpoint"].split()) == "{{ temp_low | float }}"


def test_off_branches_wrap_turn_off_in_guard(bp):
    lad = ladder(bp)
    for marker in ("is_vacation", "not in_operating_window", "door_is_open"):
        b = next(x for x in lad if marker in branch_cond(x))
        first = b["sequence"][0]
        assert step_kind(first) == "choose", marker
        g = branch_cond(first["choose"][0])
        assert g == "{{ current_ac_mode != 'off' }}", marker
        assert seq_kinds(first["choose"][0]["sequence"]) == ["service:climate.turn_off"], marker
        # symmetry with the comfort calls (board R2R-8): a pierce must reach its
        # expected-write even when the cloud call errors
        assert first["choose"][0]["sequence"][0]["continue_on_error"] is True, marker
