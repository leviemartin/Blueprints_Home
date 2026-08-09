"""Structural + logic pins for lg_ac_climate.yaml (LG AC Climate Control v1.1.0).

Run: cd ~/AI/projects/Blueprints_Home && \
     ~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q
"""
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment

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
    assert d2["default"][0]["data"]["notification_id"] == "ac_climate_sensor_warning"
    assert step_kind(d2["default"][0]) == "service:persistent_notification.create"


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
        assert seq_kinds(b["sequence"]) == ["variables", "choose", "choose", "choose"], (name, kinds)
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
    assert " ".join(cv["desired_setpoint"].split()) == "{{ setpoint_cool_q }}"
    assert " ".join(cv["desired_fan"].split()) == "{{ target_fan }}"
    hv = br["heat"]["sequence"][0]["variables"]
    assert hv["desired_mode"] == "heat"
    assert " ".join(hv["desired_setpoint"].split()) == "{{ setpoint_heat_q }}"


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
        assert seq_kinds(b["sequence"]) == ["choose", "choose"], marker


# ---- Task 8: manual-override hold ----

EXPECTED_WRITE_VALUE = ("{{ {'mode': desired_mode, 'temp': desired_setpoint | float(none), "
                        "'fan': desired_fan, 'hold_until': 0} | to_json }}")
OFF_WRITE_VALUE = ("{{ {'mode': 'off', 'temp': none, 'fan': none, "
                   "'hold_until': 0} | to_json }}")
# Only the hold-start branch writes a nonzero hold_until (board R1-2/R1-7: a pierce ends the
# hold; stale STEP-1 hold_until must never be re-written).
REFRESH_WRITE_VALUE = ("{{ {'mode': current_ac_mode, 'temp': current_setpoint | float(none), "
                       "'fan': current_fan, 'hold_until': hold_until | float(0) | int} "
                       "| to_json }}")
# Boolean branches MUST be {{ true }}/{{ false }} expressions, never bare text: HA parses
# variable renders via literal_eval, and the bare text 'false' survives as a TRUTHY STRING
# (board round-2 P0 R2R-1).
MANUAL_DETECTED = (
    "{% if not hold_enabled or hold_active or expected.get('mode') is none "
    "or expected.get('mode') in ['unavailable', 'unknown'] %} {{ false }} "
    "{% elif current_ac_mode != expected.get('mode') %} {{ true }} "
    "{% elif expected.get('mode') != 'off' and expected.get('temp') is not none "
    "and (current_setpoint | float(-99) - expected.get('temp') | float(-99)) | abs > 0.3 %} {{ true }} "
    "{% elif expected.get('mode') != 'off' and expected.get('fan') is not none "
    "and current_fan != expected.get('fan') %} {{ true }} "
    "{% else %} {{ false }} {% endif %}"
)


def test_hold_variables(bp):
    assert " ".join(get_var(bp, "hold_enabled").split()) == \
        "{{ hold_helper not in ['', none] }}"
    exp = " ".join(get_var(bp, "expected").split())
    assert exp == ("{% set e = (states(hold_helper) | from_json(default={})) "
                   "if hold_enabled else {} %} {{ e if e is mapping else {} }}")
    ha = " ".join(get_var(bp, "hold_active").split())
    assert ha == ("{{ hold_enabled and expected.get('mode') is not none "
                  "and expected.get('mode') not in ['unavailable', 'unknown'] "
                  "and hold_until | float(0) > as_timestamp(now()) "
                  "and hold_until | float(0) <= as_timestamp(now()) + hold_minutes | int * 60 }}")
    # full exact-equality pin — substring pins let an inverted predicate ship green
    # (board converged finding R1-6 + R2-4)
    md = " ".join(get_var(bp, "manual_detected").split())
    assert md == MANUAL_DETECTED


def test_step2c_restart_seed(bp):
    s2c = bp["action"][4]          # after the two dismiss steps
    assert step_kind(s2c) == "choose"
    b = s2c["choose"][0]
    assert [c["condition"] for c in b["conditions"]] == ["trigger", "template"]
    assert b["conditions"][0]["id"] == "init"
    assert seq_kinds(b["sequence"]) == ["service:input_text.set_value"]
    val = " ".join(b["sequence"][0]["data"]["value"].split())
    assert "'hold_until': 0" in val and "current_ac_mode" in val


def test_ladder_order_full(bp):
    conds = [branch_cond(b) for b in ladder(bp)]
    assert conds == [
        "{{ current_ac_mode in ['unavailable', 'unknown'] }}",
        "{{ is_vacation }}",
        "{{ not in_operating_window }}",
        "{{ door_is_open or (trigger is defined and trigger.id == 'door_open') }}",
        "{{ not sensors_available }}",
        "{{ manual_detected and not (trigger is defined and trigger.id == 'init') }}",
        "{{ hold_active and not (trigger is defined and trigger.id == 'init') }}",
        "{{ target_mode == 'off' }}",
        "{{ target_mode == 'cool' }}",
        "{{ target_mode == 'heat' }}",
    ]


def test_pierces_precede_sensor_stop(bp):
    conds = [branch_cond(b) for b in ladder(bp)]
    i_sens = conds.index("{{ not sensors_available }}")
    for marker in ("is_vacation", "not in_operating_window", "door_is_open"):
        assert next(i for i, c in enumerate(conds) if marker in c) < i_sens, marker


def test_sensor_stop_branch_is_bare_stop(bp):
    b = next(x for x in ladder(bp) if branch_cond(x) == "{{ not sensors_available }}")
    assert seq_kinds(b["sequence"]) == ["stop"]


def test_hold_start_branch_snapshots_and_stops(bp):
    b = ladder(bp)[5]
    assert seq_kinds(b["sequence"]) == ["service:input_text.set_value", "choose", "stop"]
    val = " ".join(b["sequence"][0]["data"]["value"].split())
    # floor, not round-half: rounding up would let sub-second trigger latency stretch a
    # 60-min hold to the NEXT tick (~70 min) at expiry (board R2R-5)
    assert "(as_timestamp(now()) + hold_minutes | int * 60) | int" in val
    assert "| round(" not in val
    assert "current_ac_mode" in val
    assert "ac_climate_hold_helper_error" in " ".join(str(b["sequence"][1]).split())
    verify = b["sequence"][1]
    assert branch_cond(verify["choose"][0]) == \
        ("{{ (states(hold_helper) | from_json(default={})).get('hold_until', 0) "
         "| float(0) <= as_timestamp(now()) }}")
    assert verify["default"][0]["data"]["notification_id"] == "ac_climate_hold_helper_error"
    assert step_kind(verify["default"][0]) == "service:persistent_notification.dismiss"


def test_hold_active_branch_refreshes_and_stops(bp):
    # rule 3: refresh expected to live (hold_until preserved) so expiry compares
    # against the user's LATEST state (board R1-8), then stop
    b = ladder(bp)[6]
    assert seq_kinds(b["sequence"]) == ["service:input_text.set_value", "stop"]
    val = " ".join(b["sequence"][0]["data"]["value"].split())
    assert val == REFRESH_WRITE_VALUE


def _expected_write_step(step):
    return (step_kind(step) == "choose"
            and branch_cond(step["choose"][0]) == "{{ hold_enabled }}"
            and seq_kinds(step["choose"][0]["sequence"]) == ["service:input_text.set_value"])


def test_every_commanding_branch_ends_with_expected_write(bp):
    lad = ladder(bp)
    # off-branches: vacation, window, door, and in-range deadband-active sub-branch
    for i in (1, 2, 3):
        assert _expected_write_step(lad[i]["sequence"][-1]), i
        val = " ".join(lad[i]["sequence"][-1]["choose"][0]["sequence"][0]["data"]["value"].split())
        assert val == OFF_WRITE_VALUE, i
    in_range = lad[7]["sequence"][-1]["choose"]
    assert _expected_write_step(in_range[0]["sequence"][-1])          # deadband off-branch
    assert _expected_write_step(in_range[1]["sequence"][-1])          # maintenance
    for i in (8, 9):                                                  # cool, heat
        assert _expected_write_step(lad[i]["sequence"][-1]), i
        val = " ".join(lad[i]["sequence"][-1]["choose"][0]["sequence"][0]["data"]["value"].split())
        assert val == EXPECTED_WRITE_VALUE, i


def test_in_range_deadband_off_subbranch_shape(bp):
    in_range = ladder(bp)[7]["sequence"][-1]["choose"]
    sub = in_range[0]                       # deadband ACTIVE → guarded off
    assert seq_kinds(sub["sequence"]) == ["choose", "choose"]
    g = sub["sequence"][0]["choose"][0]
    assert branch_cond(g) == "{{ current_ac_mode != 'off' }}"
    assert seq_kinds(g["sequence"]) == ["service:climate.turn_off"]
    val = " ".join(sub["sequence"][-1]["choose"][0]["sequence"][0]["data"]["value"].split())
    assert val == OFF_WRITE_VALUE


def test_maintenance_desired_values(bp):
    sub = ladder(bp)[7]["sequence"][-1]["choose"][1]      # deadband DISABLED → maintenance
    mv = sub["sequence"][0]["variables"]
    assert " ".join(mv["desired_setpoint"].split()) == \
        "{{ setpoint_cool_q if desired_mode == 'cool' else setpoint_heat_q }}"
    assert " ".join(mv["desired_fan"].split()) == "{{ fan_mode_low }}"
    dm = " ".join(mv["desired_mode"].split())
    assert dm.startswith("{% if current_ac_mode in ['cool', 'heat'] %}")
    assert "((temp_low | float + temp_high | float) / 2)" in dm


def test_setpoint_quantization_variables(bp):
    assert " ".join(get_var(bp, "ac_min_temp").split()) == \
        "{{ state_attr(climate_ac, 'min_temp') | float(16) }}"
    assert " ".join(get_var(bp, "ac_max_temp").split()) == \
        "{{ state_attr(climate_ac, 'max_temp') | float(30) }}"
    assert " ".join(get_var(bp, "ac_temp_step").split()) == \
        "{{ [state_attr(climate_ac, 'target_temp_step') | float(0.5), 0.1] | max }}"
    q = " ".join(get_var(bp, "setpoint_cool_q").split())
    assert q == ("{{ ([([(((temp_high | float / ac_temp_step) | round(0, 'floor')) * ac_temp_step), "
                 "ac_min_temp] | max), ac_max_temp] | min) | round(1) }}")
    h = " ".join(get_var(bp, "setpoint_heat_q").split())
    assert h == ("{{ ([([(((temp_low | float / ac_temp_step) | round(0, 'ceil')) * ac_temp_step), "
                 "ac_min_temp] | max), ac_max_temp] | min) | round(1) }}")


# ---- Task 8b: rendered behavior tests ----

def _float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def render_var(bp, name, ctx, now=None):
    """Render a STEP-1 variable template with HA-ish stubs."""
    env = Environment()
    env.filters["float"] = _float
    # jinja2's built-in "round" filter already supports the ('floor'/'ceil') method
    # argument used by setpoint_cool_q/setpoint_heat_q — no override needed.
    env.globals["as_timestamp"] = lambda d: d.timestamp() if hasattr(d, "timestamp") else float(d)
    tpl = env.from_string(get_var(bp, name))
    base = {"now": (lambda: now)} if now else {}
    return tpl.render(**base, **ctx).strip()


def test_rendered_setpoint_quantization(bp):
    ctx = dict(ac_min_temp=16.0, ac_max_temp=30.0)
    cool = lambda th, step: render_var(bp, "setpoint_cool_q",
                                       {**ctx, "temp_high": th, "ac_temp_step": step})
    heat = lambda tl, step: render_var(bp, "setpoint_heat_q",
                                       {**ctx, "temp_low": tl, "ac_temp_step": step})
    # cool floors: never above temp_high
    assert cool(23.5, 1.0) == "23.0"
    assert cool(22.5, 1.0) == "22.0"
    assert cool(23.5, 0.5) == "23.5"
    assert cool(24.0, 1.0) == "24.0"
    assert cool(15.0, 0.5) == "16.0"      # clamped to device min
    # heat ceils: never below temp_low
    assert heat(20.5, 1.0) == "21.0"
    assert heat(21.5, 1.0) == "22.0"
    assert heat(20.0, 1.0) == "20.0"
    # zero step must not raise (floored to 0.1)
    assert cool(23.5, 0.1) == "23.5"


def test_rendered_target_mode_hysteresis(bp):
    ctx = dict(temp_low=20.0, temp_high=24.0, margin=0.5)
    cases = [
        (23.8, "cool", "cool"),   # continue zone, actively cooling → keep cooling
        (23.4, "cool", "off"),    # past high − margin → off
        (23.8, "off", "off"),     # in range from off → stay off
        (24.1, "off", "cool"),    # above high → cool
        (19.8, "off", "heat"),    # below low → heat
        (20.3, "heat", "heat"),   # heat continue zone
    ]
    for temp, mode, want in cases:
        got = render_var(bp, "target_mode", {**ctx, "current_temp": temp, "current_ac_mode": mode})
        assert got == want, (temp, mode, got)


def test_rendered_target_fan_distance_gate(bp):
    # four DISTINCT fan levels — max=="high" would make stage-1 and stage-2 outputs
    # indistinguishable for base "mid" (board R2R-7)
    ctx = dict(fan_low_thresh=1.0, fan_med_thresh=3.0, esc_stage_1=20, esc_stage_2=40,
               fan_mode_low="low", fan_mode_mid="mid", fan_mode_high="high",
               fan_mode_max="turbo", base_fan="low")
    # spec item-3 acceptance: dist 0.4 with 3 h in-mode → low (v1.0.0 gave max)
    got = render_var(bp, "target_fan",
                     {**ctx, "minutes_in_current_mode": 180, "distance_from_target": 0.4})
    assert got == "low"
    # stage-1 bump: base mid → high (not turbo)
    got = render_var(bp, "target_fan",
                     {**ctx, "base_fan": "mid", "minutes_in_current_mode": 25,
                      "distance_from_target": 2.0})
    assert got == "high"
    # stage-2: → turbo regardless of base
    got = render_var(bp, "target_fan",
                     {**ctx, "base_fan": "mid", "minutes_in_current_mode": 45,
                      "distance_from_target": 2.0})
    assert got == "turbo"


def test_rendered_hold_active_bounds(bp):
    # the R2-1 bounded-window check has behavioral coverage here: a minutes-vs-seconds
    # transcription slip would reject every legitimate hold (board R2R-9)
    t0 = datetime(2026, 8, 9, 12, 0)
    base = dict(hold_enabled=True, hold_minutes=60, expected={"mode": "cool"})
    mk = lambda hu: render_var(bp, "hold_active", {**base, "hold_until": hu}, now=t0)
    assert mk(t0.timestamp() + 1800) == "True"       # mid-hold
    assert mk(t0.timestamp() - 10) == "False"        # expired
    assert mk(t0.timestamp() + 90 * 24 * 3600) == "False"   # hand-edited far future → rejected
    assert mk(0) == "False"

    mk2 = lambda hu, exp: render_var(bp, "hold_active",
                                     {**base, "hold_until": hu, "expected": exp}, now=t0)
    assert mk2(t0.timestamp() + 1800, {}) == "False"                     # hold_until-only doc
    assert mk2(t0.timestamp() + 1800, {"mode": "unavailable"}) == "False"  # sentinel


def test_rendered_door_is_open_no_sensor(bp):
    assert render_var(bp, "door_is_open", {"sensor_door": []}) == "False"


def test_rendered_window_owns_overnight_tail(bp):
    # Sat 22:00→06:00 overnight, Sun 07:00→23:00 (spec item-7 acceptance)
    sun = dict(schedule_start_today="07:00:00", schedule_end_today="23:00:00",
               schedule_start_yesterday="22:00:00", schedule_end_yesterday="06:00:00")
    assert render_var(bp, "in_operating_window", sun, now=datetime(2026, 8, 9, 1, 0)) == "True"
    assert render_var(bp, "in_operating_window", sun, now=datetime(2026, 8, 9, 6, 30)) == "False"
    sat = dict(schedule_start_today="22:00:00", schedule_end_today="06:00:00",
               schedule_start_yesterday="07:00:00", schedule_end_yesterday="23:00:00")
    assert render_var(bp, "in_operating_window", sat, now=datetime(2026, 8, 8, 21, 0)) == "False"
    assert render_var(bp, "in_operating_window", sat, now=datetime(2026, 8, 8, 22, 30)) == "True"


def test_description_documents_new_features(bp):
    d = bp["blueprint"]["description"]
    for token in ("Beep-Silent", "Hysteresis", "Manual-Override Hold", "Fail-Safe"):
        assert token in d


def test_door_elapsed_comparator_pinned(bp):
    d = get_var(bp, "door_is_open")
    assert "opened_sec >= (door_delay | int * 60)" in " ".join(d.split())


def test_blueprint_min_version(bp):
    assert bp["blueprint"]["homeassistant"]["min_version"] == "2024.8.0"


def test_step2c_write_continues_on_error(bp):
    b = bp["action"][4]["choose"][0]
    assert b["sequence"][0]["continue_on_error"] is True


def test_rendered_manual_detected(bp):
    base = dict(hold_enabled=True, hold_active=False,
                current_ac_mode="cool", current_setpoint=22.0, current_fan="low")
    exp_full = {"mode": "cool", "temp": 24.0, "fan": "low", "hold_until": 0}
    exp_match = {"mode": "cool", "temp": 22.0, "fan": "low", "hold_until": 0}
    # "True"/"False" (capitalized): the template branches are {{ true }}/{{ false }}
    # expressions so HA's literal_eval yields real booleans (board R2R-1) — a bare-text
    # lowercase "false" here would mean the P0 regressed.
    cases = [
        ({**base, "expected": exp_full}, "True"),                       # 2° off → manual
        ({**base, "expected": exp_match}, "False"),                     # matches → no
        ({**base, "expected": {}}, "False"),                            # empty → no-expectation
        ({**base, "expected": {"mode": "unavailable"}}, "False"),       # rule-5 sentinel
        ({**base, "expected": {"mode": "cool"}}, "False"),              # partial mapping (R1-4)
        ({**base, "current_fan": "high", "expected": exp_match}, "True"),  # fan change → manual
        ({**base, "hold_active": True, "expected": exp_full}, "False"), # during hold → no
        ({**base, "hold_enabled": False, "expected": exp_full}, "False"),  # feature off
    ]
    for ctx, want in cases:
        assert render_var(bp, "manual_detected", ctx) == want, ctx
