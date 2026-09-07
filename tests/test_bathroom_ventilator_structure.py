"""Structural + rendered-logic pins for bathroom_ventilator.yaml (Bathroom Ventilator v2.0.0).

Run: cd ~/AI/projects/Blueprints_Home && \
     ~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q
"""
import ast
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment

BP_PATH = Path(__file__).resolve().parent.parent / "bathroom_ventilator.yaml"


class _Input:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"!input {self.name}"

    def __eq__(self, other):
        return isinstance(other, _Input) and other.name == self.name


class HassLoader(yaml.SafeLoader):
    pass


HassLoader.add_constructor("!input", lambda loader, node: _Input(loader.construct_scalar(node)))


@pytest.fixture(scope="module")
def bp():
    with BP_PATH.open() as fh:
        return yaml.load(fh, Loader=HassLoader)


@pytest.fixture(scope="module")
def inputs(bp):
    return bp["blueprint"]["input"]


def norm(s):
    return " ".join(str(s).split())


def get_var(bp, name):
    for step in bp["action"]:
        if "variables" in step and name in step["variables"]:
            return step["variables"][name]
    raise KeyError(name)


def step_kind(step):
    if "service" in step:
        return f"service:{step['service']}"
    for k in ("choose", "stop", "variables", "condition", "repeat"):
        if k in step:
            return k
    return "other"


def branch_cond(branch):
    return norm(branch["conditions"][0]["value_template"])


def walk(node):
    """Yield every dict inside a nested YAML structure."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)


# ---------------------------------------------------------------- render harness
NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


class _State:
    def __init__(self, state, minutes_ago=0.0, attrs=None):
        self.state = state
        self.last_changed = NOW - timedelta(minutes=minutes_ago)
        self.attributes = attrs or {}


class _States:
    """HA `states`: callable -> state string; item access -> state object or None."""

    def __init__(self, table):
        self.table = table

    def __call__(self, eid):
        s = self.table.get(eid)
        return s.state if s else "unavailable"

    def __getitem__(self, eid):
        return self.table.get(eid)


def is_number(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return not (math.isnan(f) or math.isinf(f))


def parse(s):
    s = s.strip()
    try:
        return ast.literal_eval(s)
    except (ValueError, SyntaxError):
        return s


def make_env(states):
    env = Environment()
    env.tests["match"] = lambda v, pattern: re.match(pattern, str(v)) is not None   # HA's `match` test
    env.globals.update(
        states=states,
        now=lambda: NOW,
        log=math.log,
        e=math.e,
        is_number=is_number,
        is_state=lambda eid, s: states(eid) == s,
        state_attr=lambda eid, a: (states[eid].attributes.get(a) if states[eid] else None),
    )
    return env


def render_chain(bp, ctx, states, upto):
    """Render action[0] variables in file order up to and including `upto`; returns the context."""
    env = make_env(states)
    out = dict(ctx)
    for name, tpl in bp["action"][0]["variables"].items():
        out[name] = parse(env.from_string(str(tpl)).render(**out))
        if name == upto:
            return out
    raise KeyError(upto)


def base_ctx(**over):
    ctx = dict(
        entity_fan="light.fan", sensor_humidity="sensor.rh", sensor_temperature="sensor.t",
        sensor_motion="binary_sensor.motion", entity_weather="weather.primary",
        weather_fallback=["weather.backup"],
        thresh_target=60, thresh_high=75, hysteresis=5, thresh_mold=85, dp_delta_min=2.0,
        shower_rh_jump=6, presence_window_min=15, min_runtime=15, max_runtime=45,
        boost_toggle=["input_boolean.boost"], boost_runtime_min=20,
        sensor_grace_min=10, degraded_run_min=20, notify_targets=[],
        t_night_start="22:00:00", t_night_end="05:30:00",
        trigger={"id": "periodic"},
    )
    ctx.update(over)
    return ctx


def world(**kw):
    table = {
        "sensor.t": _State("22.0"),
        "sensor.rh": _State("50.0"),
        "binary_sensor.motion": _State("off", minutes_ago=120),
        "light.fan": _State("off", minutes_ago=180),
        "weather.primary": _State("cloudy", attrs={"temperature": 20.0, "humidity": 60.0}),
        "weather.backup": _State("sunny", attrs={"temperature": 19.0, "humidity": 70.0, "dew_point": 13.5}),
        "input_boolean.boost": _State("off", minutes_ago=600),
    }
    table.update(kw)
    return _States(table)


def at(w, when):
    """Shift every state's last_changed so `minutes_ago` values are relative to `when` instead of NOW.

    Any test that overrides `now` MUST pass its world through this, or "motion 2 min ago"
    silently becomes "motion 11 h ago" (caught by the scratch run on 2026-09-07).
    """
    delta = when - NOW
    for s in w.table.values():
        s.last_changed = s.last_changed + delta
    return w


def render_at(bp, ctx, w, when, upto="desired_on"):
    env = make_env(at(w, when))
    env.globals["now"] = lambda: when
    out = dict(ctx)
    for name, tpl in bp["action"][0]["variables"].items():
        out[name] = parse(env.from_string(str(tpl)).render(**out))
        if name == upto:
            return out
    raise KeyError(upto)


def primary(dew_point=None, temperature=20.0, humidity=60.0, state="cloudy"):
    attrs = {"temperature": temperature, "humidity": humidity}
    if dew_point is not None:
        attrs["dew_point"] = dew_point
    return _State(state, attrs=attrs)


# ---------------------------------------------------------------- structure pins

def test_version_bumped(bp):
    assert bp["blueprint"]["name"] == "Bathroom Ventilator v2.0.0"
    assert bp["blueprint"]["description"].lstrip().startswith("**Version: 2.0.0**")
    assert "demand-controlled" in bp["blueprint"]["description"]


EXPECTED_INPUTS = {
    "fan_switch", "humidity_sensor", "temperature_sensor", "motion_sensor", "weather_entity",
    "weather_fallback", "target_humidity", "high_humidity", "hysteresis", "mold_humidity",
    "dew_point_delta_min", "shower_rh_jump", "presence_window_min", "min_runtime", "max_runtime",
    "boost_toggle", "boost_runtime_min", "sensor_grace_min", "degraded_run_min", "notify_targets",
    "night_start", "night_end",
}


def test_input_schema_exact_keys(inputs):
    assert set(inputs) == EXPECTED_INPUTS


def test_removed_inputs_absent(inputs):
    for gone in ("shower_humidity_rise", "shower_motion_minutes", "post_shower_min_runtime",
                 "post_shower_max_runtime", "high_humidity_max_runtime", "enable_refresh_cycles",
                 "refresh_interval_hours", "refresh_duration_minutes", "refresh_skip_below"):
        assert gone not in inputs, gone


def test_selectors_and_defaults(inputs):
    assert inputs["fan_switch"]["selector"]["entity"]["domain"] == ["light", "switch", "fan"]
    for opt in ("weather_fallback", "boost_toggle"):
        assert inputs[opt]["default"] == []
        assert inputs[opt]["selector"]["entity"]["multiple"] is True
    assert inputs["weather_fallback"]["selector"]["entity"]["domain"] == "weather"
    assert inputs["boost_toggle"]["selector"]["entity"]["domain"] == "input_boolean"
    assert inputs["notify_targets"]["default"] == []
    assert inputs["notify_targets"]["selector"]["text"]["multiple"] is True
    numeric = {
        "target_humidity": (60, 40, 80, 5), "high_humidity": (75, 60, 90, 5),
        "hysteresis": (5, 1, 15, 1), "mold_humidity": (85, 75, 95, 5),
        "dew_point_delta_min": (2.0, 0.5, 5.0, 0.5), "shower_rh_jump": (6, 3, 15, 1),
        "presence_window_min": (15, 5, 60, 1), "min_runtime": (15, 5, 30, 5),
        "max_runtime": (45, 15, 90, 5), "boost_runtime_min": (20, 5, 60, 5),
        "sensor_grace_min": (10, 1, 60, 1), "degraded_run_min": (20, 5, 60, 5),
    }
    for key, (default, lo, hi, step) in numeric.items():
        n = inputs[key]["selector"]["number"]
        assert inputs[key]["default"] == default, key
        assert (n["min"], n["max"], n["step"]) == (lo, hi, step), key
    assert inputs["night_start"]["default"] == "22:00:00"
    assert inputs["night_end"]["default"] == "05:30:00"


def test_variable_mappings(bp):
    v = bp["variables"]
    expected = {
        "entity_fan": "fan_switch", "sensor_humidity": "humidity_sensor",
        "sensor_temperature": "temperature_sensor", "sensor_motion": "motion_sensor",
        "entity_weather": "weather_entity", "weather_fallback": "weather_fallback",
        "thresh_target": "target_humidity", "thresh_high": "high_humidity",
        "hysteresis": "hysteresis", "thresh_mold": "mold_humidity",
        "dp_delta_min": "dew_point_delta_min", "shower_rh_jump": "shower_rh_jump",
        "presence_window_min": "presence_window_min", "min_runtime": "min_runtime",
        "max_runtime": "max_runtime", "boost_toggle": "boost_toggle",
        "boost_runtime_min": "boost_runtime_min", "sensor_grace_min": "sensor_grace_min",
        "degraded_run_min": "degraded_run_min", "notify_targets": "notify_targets",
        "t_night_start": "night_start", "t_night_end": "night_end",
    }
    for var, inp in expected.items():
        assert v[var] == _Input(inp), var
    assert set(v) == set(expected)


def test_mode_queued(bp):
    assert bp["mode"] == "queued"
    assert bp["max"] == 3
    assert bp["max_exceeded"] == "silent"


def test_trigger_roster(bp):
    trigs = bp["trigger"]
    assert [t["id"] for t in trigs] == [
        "humidity_change", "motion_on", "periodic", "ha_start", "sensors_lost", "sensors_back",
        "boost_change",
    ]
    h = trigs[0]
    assert h["platform"] == "state" and h["entity_id"] == _Input("humidity_sensor")
    assert h["not_from"] == ["unavailable", "unknown"] and h["not_to"] == ["unavailable", "unknown"]
    m = trigs[1]
    assert (m["platform"], m["entity_id"], m["to"]) == ("state", _Input("motion_sensor"), "on")
    assert (trigs[2]["platform"], trigs[2]["minutes"]) == ("time_pattern", "/5")
    assert (trigs[3]["platform"], trigs[3]["event"]) == ("homeassistant", "start")
    lost = trigs[4]
    assert lost["entity_id"] == _Input("humidity_sensor")
    assert lost["to"] == ["unavailable", "unknown"]
    assert lost["for"] == {"minutes": _Input("sensor_grace_min")}
    back = trigs[5]
    assert back["entity_id"] == _Input("humidity_sensor")
    assert back["from"] == ["unavailable", "unknown"] and back["not_to"] == ["unavailable", "unknown"]
    b = trigs[6]
    assert b["entity_id"] == _Input("boost_toggle") and b["to"] == ["on", "off"]
    for t in trigs:
        assert "device_id" not in t


def test_action_shape(bp):
    # variables · sensor warning (state) · pushes (edge) · mold · fan · boost expiry · debug
    assert [step_kind(s) for s in bp["action"]] == [
        "variables", "choose", "choose", "choose", "choose", "repeat", "choose",
    ]
    for s in bp["action"]:
        for d in walk(s):
            assert "delay" not in d and "wait_template" not in d and "wait_for_trigger" not in d
            if "repeat" in d:
                assert "until" not in d["repeat"] and "while" not in d["repeat"]


def test_sensor_warning_is_state_driven(bp):
    # board R1-03: the Aqara outage is already live at deploy, so an edge trigger alone would never
    # announce it; the persistent warning follows state (create past grace / dismiss when ok).
    ch = bp["action"][1]["choose"]
    assert branch_cond(ch[0]) == (
        "{{ (not sensors_ok) and sensors_lost_minutes | float >= sensor_grace_min | float }}"
    )
    c = ch[0]["sequence"][0]
    assert step_kind(c) == "service:persistent_notification.create"
    assert c["data"]["notification_id"] == "ventilator_sensor_warning"
    assert c["continue_on_error"] is True
    assert [step_kind(s) for s in ch[0]["sequence"]] == ["service:persistent_notification.create"]
    assert branch_cond(ch[1]) == "{{ sensors_ok }}"
    d = ch[1]["sequence"][0]
    assert step_kind(d) == "service:persistent_notification.dismiss"
    assert d["data"]["notification_id"] == "ventilator_sensor_warning"
    assert d["continue_on_error"] is True


def test_sensor_push_branches_are_edge_triggered(bp):
    ch = bp["action"][2]["choose"]
    assert branch_cond(ch[0]) == "{{ trigger.id | default('') == 'sensors_lost' }}"
    assert [step_kind(s) for s in ch[0]["sequence"]] == ["repeat"]
    assert branch_cond(ch[1]) == (
        "{{ trigger.id | default('') == 'sensors_back' and sensors_ok and "
        "trigger.from_state is not none and "
        "(now() - trigger.from_state.last_changed).total_seconds() >= sensor_grace_min | float * 60 }}"
    )
    assert [step_kind(s) for s in ch[1]["sequence"]] == ["repeat"]


def test_mold_edge_branches(bp):
    ch = bp["action"][3]["choose"]
    assert branch_cond(ch[0]) == "{{ mold_on and not fan_is_on }}"
    c = ch[0]["sequence"][0]
    assert c["data"]["notification_id"] == "ventilator_mold_warning"
    assert c["continue_on_error"] is True
    # create → push gated on a commandable fan (code board 20260907-143611 R1-02: an unavailable
    # plug keeps fan_is_on false, so an ungated push would repeat every tick); no bare condition step
    assert [step_kind(s) for s in ch[0]["sequence"]] == ["service:persistent_notification.create", "choose"]
    gate = ch[0]["sequence"][1]["choose"]
    assert branch_cond(gate[0]) == "{{ states[entity_fan] is not none and not is_state(entity_fan, 'unavailable') }}"
    assert [step_kind(s) for s in gate[0]["sequence"]] == ["repeat"]
    assert gate[0]["sequence"][0]["repeat"]["for_each"] == "{{ notify_list }}"
    assert branch_cond(ch[1]) == "{{ not mold_on }}"
    d = ch[1]["sequence"][0]
    assert step_kind(d) == "service:persistent_notification.dismiss"
    assert d["data"]["notification_id"] == "ventilator_mold_warning"
    assert d["continue_on_error"] is True


def test_fan_call_idempotent(bp):
    ch = bp["action"][4]["choose"]
    assert branch_cond(ch[0]) == "{{ desired_on and not fan_is_on }}"
    on = ch[0]["sequence"][0]
    assert step_kind(on) == "service:homeassistant.turn_on"
    assert on["target"]["entity_id"] == "{{ entity_fan }}"
    assert on["continue_on_error"] is True          # a bridge hiccup must not abort boost expiry/debug
    assert branch_cond(ch[1]) == "{{ (not desired_on) and fan_is_on }}"
    off = ch[1]["sequence"][0]
    assert step_kind(off) == "service:homeassistant.turn_off"
    assert off["target"]["entity_id"] == "{{ entity_fan }}"
    assert off["continue_on_error"] is True
    assert len(ch) == 2 and "default" not in bp["action"][4]


def test_no_bare_condition_steps_anywhere(bp):
    # a bare `condition:` action inside a choose stops that choose's remaining actions (HA docs);
    # this blueprint expresses every gate as a choose branch instead
    for d in walk(bp["action"]):
        if "condition" in d and "conditions" not in d and "value_template" in d:
            for step in bp["action"]:
                for seq_holder in walk(step):
                    if "sequence" in seq_holder:
                        assert d not in seq_holder["sequence"]


def test_boost_expiry_step(bp):
    rep = bp["action"][5]["repeat"]
    assert rep["for_each"] == "{{ boost_expired_list }}"
    s = rep["sequence"][0]
    assert step_kind(s) == "service:input_boolean.turn_off"
    assert s["target"]["entity_id"] == "{{ repeat.item }}"
    assert s["continue_on_error"] is True


def test_notify_fanout_continue_on_error_and_filtered_list(bp):
    hits = 0
    for d in walk(bp["action"]):
        if d.get("service") == "{{ repeat.item }}":
            hits += 1
            assert d.get("continue_on_error") is True
        if "repeat" in d and d["repeat"].get("for_each") != "{{ boost_expired_list }}":
            # board R2-001: only the filtered notify list may be dispatched as a service name
            assert d["repeat"]["for_each"] == "{{ notify_list }}"
    assert hits >= 3   # sensors_lost, sensors_back, mold — each pushes


def test_debug_block_manual_only(bp):
    ch = bp["action"][6]["choose"]
    assert branch_cond(ch[0]) == "{{ trigger.id | default('manual') == 'manual' }}"
    assert ch[0]["sequence"][0]["continue_on_error"] is True
    msg = ch[0]["sequence"][0]["data"]["message"]
    for token in ("weather_used", "outdoor_dp", "rh_floor", "stop_target", "start_threshold",
                  "active_rule", "fan_on_minutes", "minutes_since_motion", "sensors_lost_minutes"):
        assert token in msg, token
    assert ch[0]["sequence"][0]["data"]["notification_id"] == "ventilator_debug"


def test_no_bare_boolean_text(bp):
    bare = re.compile(r"%\}\s*(true|false)\s*(\{%|$)")
    for name, tpl in bp["action"][0]["variables"].items():
        assert not bare.search(str(tpl)), name


def test_decision_label_order(bp):
    ar = norm(get_var(bp, "active_rule"))
    order = ["boost", "degraded", "hold", "mold", "min_run", "max_run", "shower", "continue", "start", "idle"]
    idx = [ar.index(f"%}}{lbl}") if f"%}}{lbl}" in ar else ar.index(f"%}} {lbl}") for lbl in order]
    assert idx == sorted(idx)
    assert "{% if boost_active %}" in ar
    assert "{% elif not sensors_ok and sensors_lost_minutes | float >= sensor_grace_min | float %}" in ar
    assert "{% elif not sensors_ok %}" in ar
    assert "{% elif mold_on %}" in ar
    assert "{% elif fan_is_on and fan_on_minutes | int < min_runtime | int %}" in ar
    assert "{% elif fan_is_on and fan_on_minutes | int >= max_runtime | int %}" in ar
    assert "{% elif shower_signal %}" in ar
    assert "{% elif fan_is_on and indoor_rh | float > stop_target | float %}" in ar
    assert "{% elif not fan_is_on and indoor_rh | float > start_threshold | float and not is_night %}" in ar


# ---------------------------------------------------------------- rendered logic

@pytest.mark.parametrize("t,rh,expected", [(22, 50, 11.1), (22, 80, 18.4), (30.8, 61, 22.4), (24, 90, 22.3)])
def test_indoor_dew_point_rows(bp, t, rh, expected):
    ctx = render_chain(bp, base_ctx(), world(**{"sensor.t": _State(str(t)), "sensor.rh": _State(str(rh))}), "indoor_dp")
    assert ctx["indoor_dp"] == expected


def test_outdoor_dp_prefers_native_dew_point(bp):
    ctx = render_chain(bp, base_ctx(), world(**{"weather.primary": primary(dew_point=16.0)}), "outdoor_dp")
    assert ctx["weather_used"] == "weather.primary"
    assert ctx["outdoor_dp"] == 16.0


def test_outdoor_dp_magnus_when_no_native(bp):
    ctx = render_chain(bp, base_ctx(), world(**{"weather.primary": primary(temperature=26.9, humidity=50.0)}), "outdoor_dp")
    assert ctx["weather_used"] == "weather.primary"
    assert ctx["outdoor_dp"] == 15.6


def test_outdoor_dp_falls_back_to_second_entity(bp):
    w = world(**{"weather.primary": _State("unavailable")})
    ctx = render_chain(bp, base_ctx(), w, "outdoor_dp")
    assert ctx["weather_used"] == "weather.backup"
    assert ctx["outdoor_dp"] == 13.5


def test_outdoor_dp_default_when_no_weather(bp):
    w = world(**{"weather.primary": _State("unavailable"), "weather.backup": _State("unknown")})
    ctx = render_chain(bp, base_ctx(), w, "outdoor_dp")
    assert ctx["weather_used"] == ""
    assert ctx["outdoor_dp"] == 13.0


@pytest.mark.parametrize("t_in,odp,delta,floor", [
    (22, 16, 2.0, 78.1), (22, 5, 2.0, 37.9), (22, 21, 2.0, 100.0), (22, 19.5, 2.0, 97.0),
    (25, 16, 2.0, 65.1), (20, 16, 2.0, 88.3), (22, 16, 0.5, 71.0),
])
def test_rh_floor_rows(bp, t_in, odp, delta, floor):
    w = world(**{"sensor.t": _State(str(t_in)), "weather.primary": primary(dew_point=odp)})
    ctx = render_chain(bp, base_ctx(dp_delta_min=delta), w, "rh_floor")
    assert ctx["rh_floor"] == floor


@pytest.mark.parametrize("t_in,odp,stop,start", [
    (22, 16, 78.1, 83.1), (22, 5, 60, 75), (22, 21, 100.0, 100), (22, 19.5, 97.0, 100),
    (25, 16, 65.1, 75), (20, 16, 88.3, 93.3),
])
def test_stop_and_start_targets(bp, t_in, odp, stop, start):
    w = world(**{"sensor.t": _State(str(t_in)), "weather.primary": primary(dew_point=odp)})
    ctx = render_chain(bp, base_ctx(), w, "start_threshold")
    assert ctx["stop_target"] == stop
    assert ctx["start_threshold"] == start


@pytest.mark.parametrize("hhmm,start,end,expected", [
    ("23:00", "22:00:00", "05:30:00", True), ("03:00", "22:00:00", "05:30:00", True),
    ("12:00", "22:00:00", "05:30:00", False), ("05:30", "22:00:00", "05:30:00", False),
    ("03:00", "00:00:00", "06:00:00", True), ("12:00", "00:00:00", "06:00:00", False),
    ("06:00", "00:00:00", "06:00:00", False),
])
def test_is_night_rows(bp, hhmm, start, end, expected, monkeypatch):
    hh, mm = map(int, hhmm.split(":"))
    fixed = NOW.replace(hour=hh, minute=mm)
    env = make_env(world())
    env.globals["now"] = lambda: fixed
    tpl = env.from_string(str(get_var(bp, "is_night")))
    assert parse(tpl.render(t_night_start=start, t_night_end=end)) is expected


def _shower_ctx(from_rh, to_rh, motion_minutes_ago, trigger_id="humidity_change", window=15):
    trig = {"id": trigger_id, "from_state": _State(str(from_rh)), "to_state": _State(str(to_rh))}
    w = world(**{"sensor.rh": _State(str(to_rh)), "binary_sensor.motion": _State("off", minutes_ago=motion_minutes_ago)})
    return base_ctx(trigger=trig, presence_window_min=window), w


@pytest.mark.parametrize("frm,to,motion_ago,tid,expected", [
    (55, 61, 5, "humidity_change", True),
    (55, 60, 5, "humidity_change", False),
    (55, 61, 14, "humidity_change", True),    # presence window boundary (15): just inside
    (55, 61, 16, "humidity_change", False),   # just outside
    (55, 61, 20, "humidity_change", False),
    (55, 61, 5, "periodic", False),
    (61, 55, 5, "humidity_change", False),
])
def test_shower_signal_rows(bp, frm, to, motion_ago, tid, expected):
    ctx, w = _shower_ctx(frm, to, motion_ago, tid)
    assert render_chain(bp, ctx, w, "shower_signal")["shower_signal"] is expected


def test_shower_signal_with_motion_currently_on(bp):
    ctx, w = _shower_ctx(55, 62, 40)
    w.table["binary_sensor.motion"] = _State("on", minutes_ago=1)
    assert render_chain(bp, ctx, w, "shower_signal")["shower_signal"] is True


def test_shower_signal_manual_run_is_false(bp):
    ctx = base_ctx(trigger={"platform": None})
    assert render_chain(bp, ctx, world(), "shower_signal")["shower_signal"] is False


def _decide(bp, ctx, w):
    out = render_chain(bp, ctx, w, "desired_on")
    return out["active_rule"], out["desired_on"]


def test_rule_boost(bp):
    w = world(**{"input_boolean.boost": _State("on", minutes_ago=5)})
    assert _decide(bp, base_ctx(), w) == ("boost", True)
    w = world(**{"input_boolean.boost": _State("on", minutes_ago=25)})
    assert _decide(bp, base_ctx(), w)[0] != "boost"
    assert render_chain(bp, base_ctx(), w, "boost_expired_list")["boost_expired_list"] == ["input_boolean.boost"]


def test_rule_degraded_after_grace(bp):
    # sensor unavailable for 30 min (> grace 10): degraded, fan follows motion recency
    w = world(**{"sensor.rh": _State("unavailable", minutes_ago=30), "binary_sensor.motion": _State("off", minutes_ago=10)})
    assert _decide(bp, base_ctx(), w) == ("degraded", True)
    w = world(**{"sensor.rh": _State("unavailable", minutes_ago=30), "binary_sensor.motion": _State("off", minutes_ago=30)})
    assert _decide(bp, base_ctx(), w) == ("degraded", False)
    w = world(**{"sensor.t": _State("unknown", minutes_ago=45), "binary_sensor.motion": _State("on")})
    out = render_chain(bp, base_ctx(), w, "desired_on")
    assert out["sensors_lost_minutes"] == 45.0
    assert (out["active_rule"], out["desired_on"]) == ("degraded", True)


def test_missing_humidity_entity_is_degraded_not_flapping(bp):
    # code board 20260907-143611 R1-04: an absent entity (renamed / re-paired) must not fall through
    # to the still-reporting temperature sensor's clock
    w = world()
    del w.table["sensor.rh"]
    out = render_chain(bp, base_ctx(), w, "desired_on")
    assert out["sensors_ok"] is False
    assert out["sensors_lost_minutes"] == 9999
    assert out["active_rule"] == "degraded"


def test_every_input_has_a_description(inputs):
    missing = [k for k, v in inputs.items() if not str(v.get("description", "")).strip()]
    assert missing == []


def test_rule_hold_within_grace(bp):
    # board R2-002: a 5-min blip (< grace 10) must not flip the fan either way
    w = world(**{"sensor.rh": _State("unavailable", minutes_ago=5), "binary_sensor.motion": _State("on")})
    assert _decide(bp, base_ctx(), w) == ("hold", False)          # fan was off → stays off
    w = world(**{"sensor.rh": _State("unavailable", minutes_ago=5), "light.fan": _State("on", minutes_ago=3)})
    assert _decide(bp, base_ctx(), w) == ("hold", True)           # fan was on → stays on
    out = render_chain(bp, base_ctx(), w, "sensors_lost_minutes")
    assert out["sensors_lost_minutes"] == 5.0


def test_notify_list_filters_non_notify_services(bp):
    ctx = base_ctx(notify_targets=["notify.mobile_app_martin_fold", "homeassistant.restart",
                                   "mobile_app_pixel", "notify.bad-name", "notify.ok_2"])
    out = render_chain(bp, ctx, world(), "notify_list")
    assert out["notify_list"] == ["notify.mobile_app_martin_fold", "notify.ok_2"]
    out = render_chain(bp, base_ctx(notify_targets=[]), world(), "notify_list")
    assert out["notify_list"] == []


def test_rule_mold_requires_drier_outdoor_air(bp):
    w = world(**{"sensor.rh": _State("90"), "weather.primary": primary(dew_point=10.0)})
    assert _decide(bp, base_ctx(), w) == ("mold", True)
    w = world(**{"sensor.rh": _State("90"), "weather.primary": primary(dew_point=25.0)})
    rule, on = _decide(bp, base_ctx(), w)
    assert rule != "mold" and on is False


def test_rule_min_and_max_run(bp):
    w = world(**{"light.fan": _State("on", minutes_ago=5), "sensor.rh": _State("50")})
    assert _decide(bp, base_ctx(), w) == ("min_run", True)
    w = world(**{"light.fan": _State("on", minutes_ago=50), "sensor.rh": _State("80"), "weather.primary": primary(dew_point=5.0)})
    assert _decide(bp, base_ctx(), w) == ("max_run", False)


def test_rule_continue_until_adaptive_target(bp):
    w = world(**{"light.fan": _State("on", minutes_ago=20), "sensor.rh": _State("70"), "weather.primary": primary(dew_point=5.0)})
    assert _decide(bp, base_ctx(), w) == ("continue", True)
    w = world(**{"light.fan": _State("on", minutes_ago=20), "sensor.rh": _State("70"), "weather.primary": primary(dew_point=16.0)})
    assert _decide(bp, base_ctx(), w) == ("idle", False)   # 70 < adaptive stop 78.1


def test_rule_start_daytime_only(bp):
    w = world(**{"sensor.rh": _State("80"), "weather.primary": primary(dew_point=5.0)})
    assert _decide(bp, base_ctx(), w) == ("start", True)
    w = world(**{"sensor.rh": _State("80"), "weather.primary": primary(dew_point=5.0)})
    out = render_at(bp, base_ctx(), w, NOW.replace(hour=23))
    assert (out["active_rule"], out["desired_on"]) == ("idle", False)


def test_rule_shower_turns_on_at_night(bp):
    ctx, w = _shower_ctx(55, 63, 2)
    out = render_at(bp, ctx, w, NOW.replace(hour=23))
    assert out["is_night"] is True and out["presence_recent"] is True
    assert (out["active_rule"], out["desired_on"]) == ("shower", True)


def test_rule_continue_at_night_after_shower(bp):
    # a run started by a shower keeps going past 22:00 while RH is above the adaptive stop target
    w = world(**{"light.fan": _State("on", minutes_ago=20), "sensor.rh": _State("70"),
                 "weather.primary": primary(dew_point=5.0)})
    out = render_at(bp, base_ctx(), w, NOW.replace(hour=23))
    assert (out["active_rule"], out["desired_on"]) == ("continue", True)


def test_idle_when_dry(bp):
    assert _decide(bp, base_ctx(), world()) == ("idle", False)
