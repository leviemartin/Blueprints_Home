# Bathroom Ventilator v2.0.0 — Implementation Plan (epic #10, session #11)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `bathroom_ventilator.yaml` v2.0.0 — outdoor-conditioned adaptive targets, rate-of-rise shower detection, stateless rules, degraded mode, boost toggle, mobile push — with structure/render tests, the migrated instance config, docs, and a live deploy.

**Architecture:** One blueprint YAML. Top-level `variables:` pass every `!input` through; the first `action:` step computes every fact (psychrometrics, timing from entity `last_changed`, a decision label `active_rule`, and `desired_on`); four short side-effect steps follow (edge-triggered notifications, one idempotent fan call, boost expiry, manual-run debug). No `delay`/`repeat until` anywhere, so any trigger can re-decide at any moment. Deployment reuses `scripts/deploy-blueprint.sh` (committed on this branch, `3ec393f`) with `deploy/bathroom_ventilator_1774555916056.json`.

**Tech Stack:** Home Assistant 2026.9 blueprint YAML + Jinja2; pytest 9 + PyYAML + Jinja2 3.1 structure/render tests (repo convention, see `tests/test_lg_ac_climate_structure.py`); bash deploy script; hass-cli + curl against HA.

**Spec:** `docs/superpowers/specs/2026-09-07-bathroom-climate-v2-design.md` (§2, §3, §5, §6, §7)
**Branch:** `bathroom-climate-v2` → PR → `main`. PR body carries `Session: #11` (deploying session — never `Closes`).

```
Stakes: standard
Trigger: default-up: automation logic change in bathroom_ventilator.yaml + new tests/instance JSON/docs; no hard trigger matched (deploy script already committed and pinned)
Router: deterministic
Entry: C
tcb_manifest_sha: 4a438dd869bcabb21e5ca110d95a40a5b33a183ac1c7fb461d2c5ba581372c91
tcb_baseline: /home/martin/AI/reviews/tcb-baseline-16ef53e7f973185a.txt
TCB_EXTRA: /home/martin/AI/projects/Blueprints_Home/scripts/deploy-blueprint.sh
declared_tcb_changes:
```

**Execution mode:** subagent-driven — T1 and T2 to Sonnet subagents (well-specified: the test code and the YAML are in this plan verbatim), T3 to Sonnet, T4 in the main loop (operator-visible live deploy). Boards at standard dial (R1 Opus + R2 Codex) at design-time (before T1) and code-time (after T3, before T4). `/effort xhigh` at both gates, `high` otherwise.

**Shell invariants (plan-wide):** tests run from the repo root via `PY=~/projects/ceiling-fan-hue-blueprint/.venv/bin/python; $PY -m pytest tests -q` (system python3 lacks pytest; venv verified 2026-09-07: pyyaml 6.0.3, jinja2 3.1.6, pytest 9.1.0; baseline 58 green). Never pipe test output through `tail` (exit-code masking). Per-pillar commits, explicit paths, never `git add -A`. The deploy script keeps `set -euo pipefail` deliberately (fail-fast is the correct behaviour for a deploy; it is not an `~/AI/` playbook script) — this plan does not edit it.

## Global Constraints

- Blueprint inputs are removed/renamed → the stored instance MUST be migrated in the same deploy (spec §3.1, §7); an unknown key or a missing required input makes the automation `unavailable` (memory: blueprint-input-rename).
- Every boolean-valued variable is a `{{ … }}` expression, never bare `true`/`false` text (memory: HA bare-boolean text is a truthy string).
- No `delay`, `wait_*`, or `repeat until` in the action; timing comes from `states[x].last_changed` (spec §3.2).
- Fan calls use `homeassistant.turn_on` / `homeassistant.turn_off` and fire only when `desired_on != fan_is_on` (spec §3.4).
- Every `notify.*` call sits in `repeat: for_each: "{{ notify_targets }}"` with `continue_on_error: true` (spec §3.5).
- Version strings: blueprint name `Bathroom Ventilator v2.0.0`, description starts with `**Version: 2.0.0**`.
- Psychrometrics: Magnus a = 17.625, b = 243.04; `rh_floor = 100·exp(a·Td/(b+Td) − a·T/(b+T))` with `Td = outdoor_dp + dew_point_delta_min`, clamped to [0, 100], = 100 when `Td ≥ T` (spec §3.3).

---

## Phase 0 — Pre-flight (Claude)

**Context budget:** ~15k tokens · 0 files edited · shell only · main loop.

- [x] Branch `bathroom-climate-v2` exists off `main` (spec `33e4120`, deploy script `3ec393f`).
- [x] TCB baseline computed with `TCB_EXTRA` = deploy script; `verify` rc=0; ABSENT lines = 0 (2026-09-07).
- [x] HA reachable (2026.9.0); `notify.mobile_app_martin_fold` exists; `weather.home_sm` exposes `dew_point`; `weather.openweathermap` exposes temperature+humidity only.
- [x] Baseline suite green: `PASS=58 FAIL=0`.
- [ ] At T4 time only: re-read `sensor.temp_sensor_bathroom*` entity ids (the Aqara reset may have re-created them) and the current instance config (the deploy script backs it up to `deploy/1774555916056.prev.json`).

**Observation criteria ([8] applies — deploying session; the session issue #11 carries `<!-- observe:open -->`):**
1. `automation.bathroom_ventilator_v1_0_0` (entity id unchanged; alias becomes v2.0.0) is `on` immediately after deploy and still `on` 24 h later.
2. A manual run's `ventilator_debug` notification lists `weather_used`, `outdoor_dp`, `rh_floor`, `stop_target`, `start_threshold`, `active_rule`.
3. First shower after the sensor returns: a trace whose `changed_variables` has `shower_signal: True` and `active_rule: shower`, fan on within one report, off between 15 and 45 min later with `active_rule` in {continue, max_run, idle}.
4. Zero `Action notify.mobile_app_martin_fold not found` / `Error executing script` lines for this automation in the HA log over 48 h.
5. While the Aqara sensor is still offline: fan runs after bathroom motion and stops ≈20 min after the last motion (degraded mode), no notification spam (`ventilator_sensor_warning` created at most once).

---

## Task 1: Tests first (RED) — `tests/test_bathroom_ventilator_structure.py`

**Model tier:** Sonnet
**Rationale:** The test file below is complete; the task is transcription plus running it RED against v1.0.0.
**Effort:** high (operator `/effort high` checkpoint).

**Files:**
- Create: `tests/test_bathroom_ventilator_structure.py`
- Test: itself

**Interfaces:**
- Consumes: `bathroom_ventilator.yaml` (v1.0.0 now, v2.0.0 after Task 2).
- Produces: helpers `get_var`, `render_chain`, `world`, `base_ctx` used by nothing else; the expected variable names Task 2 must emit: `indoor_temp_raw, indoor_rh_raw, sensors_ok, indoor_temp, indoor_rh, weather_candidates, weather_used, outdoor_temp, outdoor_rh, outdoor_dp, indoor_dp, dp_delta, rh_floor, stop_target, start_threshold, fan_is_on, fan_on_minutes, is_night, minutes_since_motion, presence_recent, shower_signal, boost_list, boost_active, boost_expired_list, degraded_on, mold_on, active_rule, desired_on`.

- [ ] **Step 1: Write the test file (verbatim)**

```python
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
    assert [step_kind(s) for s in bp["action"]] == [
        "variables", "choose", "choose", "choose", "repeat", "choose",
    ]
    for s in bp["action"]:
        for d in walk(s):
            assert "delay" not in d and "wait_template" not in d and "wait_for_trigger" not in d
            if "repeat" in d:
                assert "until" not in d["repeat"] and "while" not in d["repeat"]


def test_sensor_loss_branches(bp):
    ch = bp["action"][1]["choose"]
    assert branch_cond(ch[0]) == "{{ trigger.id | default('') == 'sensors_lost' }}"
    assert ch[0]["sequence"][0]["data"]["notification_id"] == "ventilator_sensor_warning"
    assert step_kind(ch[0]["sequence"][0]) == "service:persistent_notification.create"
    assert step_kind(ch[0]["sequence"][1]) == "repeat"
    assert branch_cond(ch[1]) == (
        "{{ trigger.id | default('') == 'sensors_back' and sensors_ok and "
        "trigger.from_state is not none and "
        "(now() - trigger.from_state.last_changed).total_seconds() >= sensor_grace_min | float * 60 }}"
    )
    assert step_kind(ch[1]["sequence"][0]) == "service:persistent_notification.dismiss"
    assert ch[1]["sequence"][0]["data"]["notification_id"] == "ventilator_sensor_warning"


def test_mold_edge_branches(bp):
    ch = bp["action"][2]["choose"]
    assert branch_cond(ch[0]) == "{{ mold_on and not fan_is_on }}"
    assert ch[0]["sequence"][0]["data"]["notification_id"] == "ventilator_mold_warning"
    # create → hour-gate → push: a persisting mold condition must not push every max-run cycle
    assert [step_kind(s) for s in ch[0]["sequence"]] == [
        "service:persistent_notification.create", "condition", "repeat",
    ]
    assert norm(ch[0]["sequence"][1]["value_template"]) == "{{ minutes_since_fan_change | float >= 60 }}"
    assert branch_cond(ch[1]) == "{{ not mold_on }}"
    d = ch[1]["sequence"][0]
    assert step_kind(d) == "service:persistent_notification.dismiss"
    assert d["data"]["notification_id"] == "ventilator_mold_warning"
    assert d["continue_on_error"] is True


def test_fan_call_idempotent(bp):
    ch = bp["action"][3]["choose"]
    assert branch_cond(ch[0]) == "{{ desired_on and not fan_is_on }}"
    on = ch[0]["sequence"][0]
    assert step_kind(on) == "service:homeassistant.turn_on"
    assert on["target"]["entity_id"] == "{{ entity_fan }}"
    assert branch_cond(ch[1]) == "{{ (not desired_on) and fan_is_on }}"
    off = ch[1]["sequence"][0]
    assert step_kind(off) == "service:homeassistant.turn_off"
    assert off["target"]["entity_id"] == "{{ entity_fan }}"
    assert len(ch) == 2 and "default" not in bp["action"][3]


def test_boost_expiry_step(bp):
    rep = bp["action"][4]["repeat"]
    assert rep["for_each"] == "{{ boost_expired_list }}"
    s = rep["sequence"][0]
    assert step_kind(s) == "service:input_boolean.turn_off"
    assert s["target"]["entity_id"] == "{{ repeat.item }}"
    assert s["continue_on_error"] is True


def test_notify_fanout_continue_on_error(bp):
    hits = 0
    for d in walk(bp["action"]):
        if d.get("service") == "{{ repeat.item }}":
            hits += 1
            assert d.get("continue_on_error") is True
    assert hits >= 3   # sensors_lost, sensors_back, mold — each pushes


def test_debug_block_manual_only(bp):
    ch = bp["action"][5]["choose"]
    assert branch_cond(ch[0]) == "{{ trigger.id | default('manual') == 'manual' }}"
    msg = ch[0]["sequence"][0]["data"]["message"]
    for token in ("weather_used", "outdoor_dp", "rh_floor", "stop_target", "start_threshold",
                  "active_rule", "fan_on_minutes", "minutes_since_motion"):
        assert token in msg, token
    assert ch[0]["sequence"][0]["data"]["notification_id"] == "ventilator_debug"


def test_no_bare_boolean_text(bp):
    bare = re.compile(r"%\}\s*(true|false)\s*(\{%|$)")
    for name, tpl in bp["action"][0]["variables"].items():
        assert not bare.search(str(tpl)), name


def test_decision_label_order(bp):
    ar = norm(get_var(bp, "active_rule"))
    order = ["boost", "degraded", "mold", "min_run", "max_run", "shower", "continue", "start", "idle"]
    idx = [ar.index(f"%}}{lbl}") if f"%}}{lbl}" in ar else ar.index(f"%}} {lbl}") for lbl in order]
    assert idx == sorted(idx)
    assert "{% if boost_active %}" in ar
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


def test_rule_degraded(bp):
    w = world(**{"sensor.rh": _State("unavailable"), "binary_sensor.motion": _State("off", minutes_ago=10)})
    assert _decide(bp, base_ctx(), w) == ("degraded", True)
    w = world(**{"sensor.rh": _State("unavailable"), "binary_sensor.motion": _State("off", minutes_ago=30)})
    assert _decide(bp, base_ctx(), w) == ("degraded", False)
    w = world(**{"sensor.t": _State("unknown"), "binary_sensor.motion": _State("on")})
    assert _decide(bp, base_ctx(), w) == ("degraded", True)


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
```

- [ ] **Step 2: Run the file RED against v1.0.0**

Run: `cd ~/AI/projects/Blueprints_Home && ~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests/test_bathroom_ventilator_structure.py -q`
Expected: many FAILs (`test_version_bumped`, schema, triggers, every render test) and zero collection errors. The existing suite must still be green: run `… -m pytest tests -q` and report `PASS=N FAIL=M` (expected `PASS=58 FAIL=<all new tests>`).

- [ ] **Step 3: Commit (tests pillar)**

```bash
git add tests/test_bathroom_ventilator_structure.py
git commit -m "test(ventilator): v2.0.0 structure + rendered-logic pins (RED against v1.0.0)"
```

Step 4: Report `PASS=N FAIL=M` for the full suite.

---

## Task 2: Blueprint v2.0.0 — `bathroom_ventilator.yaml`

**Model tier:** Sonnet
**Rationale:** The YAML below is complete; the task is transcription, then driving Task 1 to green and fixing any pin mismatch by changing the YAML, never the pin's intent.
**Effort:** high.

**Files:**
- Modify: `bathroom_ventilator.yaml` (full replacement)
- Test: `tests/test_bathroom_ventilator_structure.py`

**Interfaces:**
- Consumes: input keys and variable names pinned in Task 1.
- Produces: blueprint path `leviemartin/bathroom_ventilator.yaml` (unchanged in HA); instance inputs consumed by Task 3's JSON.

- [ ] **Step 1: Replace the file with this content (verbatim)**

```yaml
blueprint:
  name: "Bathroom Ventilator v2.0.0"
  description: >
    **Version: 2.0.0** — the stop/start targets follow the outdoor dew point (the fan stops
    where ventilation stops helping instead of chasing an unreachable RH%); showers are detected
    by a humidity jump between two sensor reports plus recent presence, at any hour including
    quiet hours; every run is re-decided from live facts on each trigger (no long delays);
    sensor loss degrades to a motion-timed mode with one mobile push; a boost toggle forces the
    fan on; the timer-driven refresh cycle is gone — the fan is demand-controlled
    (ASHRAE 62.2 / Bbl), trickle vents supply the background air.

    **Requirements:** on/off fan entity (light, switch or fan), indoor temperature + humidity
    sensor, motion sensor, weather entity with temperature + humidity (its dew_point attribute
    is used when present).

  domain: automation
  input:
    # --- DEVICES ---
    fan_switch:
      name: Fan
      description: The exhaust fan entity (a smart plug exposed as light, switch or fan).
      selector:
        entity:
          domain: [light, switch, fan]
    humidity_sensor:
      name: Humidity Sensor
      description: Indoor bathroom humidity sensor.
      selector:
        entity:
          domain: sensor
          device_class: humidity
    temperature_sensor:
      name: Temperature Sensor
      description: Indoor bathroom temperature sensor (dew point calculation).
      selector:
        entity:
          domain: sensor
          device_class: temperature
    motion_sensor:
      name: Motion Sensor
      description: Bathroom motion sensor (presence for shower detection and degraded mode).
      selector:
        entity:
          domain: binary_sensor
          device_class: motion
    weather_entity:
      name: Weather Entity
      description: "Outdoor conditions. A dew_point attribute is used directly; otherwise dew point is computed from temperature + humidity."
      selector:
        entity:
          domain: weather
    weather_fallback:
      name: Weather Fallback (optional)
      description: "Second weather entity, used when the primary is unavailable or lacks temperature/humidity."
      default: []
      selector:
        entity:
          domain: weather
          multiple: true

    # --- HUMIDITY TARGETS ---
    target_humidity:
      name: Target Humidity (%)
      description: "Configured stop target. The effective stop target is this or the outdoor-conditioned floor, whichever is higher."
      default: 60
      selector:
        number:
          min: 40
          max: 80
          step: 5
          unit_of_measurement: "%"
    high_humidity:
      name: High Humidity Start (%)
      description: "Daytime non-shower ventilation starts above this, or above the effective stop target plus hysteresis, whichever is higher."
      default: 75
      selector:
        number:
          min: 60
          max: 90
          step: 5
          unit_of_measurement: "%"
    hysteresis:
      name: Hysteresis (%)
      description: The start threshold sits at least this far above the effective stop target.
      default: 5
      selector:
        number:
          min: 1
          max: 15
          step: 1
          unit_of_measurement: "%"
    mold_humidity:
      name: Mold Safety Threshold (%)
      description: Fan forced on above this at any hour, as long as the outdoor air is drier.
      default: 85
      selector:
        number:
          min: 75
          max: 95
          step: 5
          unit_of_measurement: "%"
    dew_point_delta_min:
      name: Dew Point Margin (°C)
      description: "Margin above the outdoor dew point that defines the effective stop target (ventilation is only worth running while the indoor dew point exceeds outdoor + margin)."
      default: 2.0
      selector:
        number:
          min: 0.5
          max: 5.0
          step: 0.5
          unit_of_measurement: "°C"

    # --- SHOWER DETECTION ---
    shower_rh_jump:
      name: Shower Humidity Jump (%)
      description: "RH rise between two consecutive sensor reports that counts as a shower (Aqara T1 reports instantly on a 6% change)."
      default: 6
      selector:
        number:
          min: 3
          max: 15
          step: 1
          unit_of_measurement: "%"
    presence_window_min:
      name: Presence Window (min)
      description: Motion within this window qualifies a humidity jump as a shower.
      default: 15
      selector:
        number:
          min: 5
          max: 60
          step: 1
          unit_of_measurement: min

    # --- RUN TIMES ---
    min_runtime:
      name: Minimum Run (min)
      description: Every fan run lasts at least this long.
      default: 15
      selector:
        number:
          min: 5
          max: 30
          step: 5
          unit_of_measurement: min
    max_runtime:
      name: Maximum Run (min)
      description: Hard cap per run; in daytime the next evaluation may start a new run.
      default: 45
      selector:
        number:
          min: 15
          max: 90
          step: 5
          unit_of_measurement: min

    # --- BOOST ---
    boost_toggle:
      name: Boost Toggle (optional)
      description: "input_boolean helper(s). Any one ON forces the fan on; it is switched off automatically after the boost runtime."
      default: []
      selector:
        entity:
          domain: input_boolean
          multiple: true
    boost_runtime_min:
      name: Boost Runtime (min)
      default: 20
      selector:
        number:
          min: 5
          max: 60
          step: 5
          unit_of_measurement: min

    # --- DEGRADED MODE ---
    sensor_grace_min:
      name: Sensor Grace (min)
      description: The humidity sensor must be unavailable this long before degraded mode is announced.
      default: 10
      selector:
        number:
          min: 1
          max: 60
          step: 1
          unit_of_measurement: min
    degraded_run_min:
      name: Degraded Run After Motion (min)
      description: With the sensors unavailable, the fan runs this long after the last bathroom motion.
      default: 20
      selector:
        number:
          min: 5
          max: 60
          step: 5
          unit_of_measurement: min

    # --- NOTIFICATIONS ---
    notify_targets:
      name: Mobile Push Targets
      description: "notify services (full name, e.g. notify.mobile_app_martin_fold) for sensor offline/back and mold override. Empty disables push."
      default: []
      selector:
        text:
          multiple: true

    # --- QUIET HOURS ---
    night_start:
      name: Night Start (Quiet Hours)
      description: Non-shower ventilation does not START between night start and night end; showers, mold override and boost still run.
      default: "22:00:00"
      selector:
        time:
    night_end:
      name: Night End (Quiet Hours)
      default: "05:30:00"
      selector:
        time:

mode: queued
max: 3
max_exceeded: silent

trigger:
  - platform: state
    entity_id: !input humidity_sensor
    not_from: [unavailable, unknown]
    not_to: [unavailable, unknown]
    id: humidity_change
  - platform: state
    entity_id: !input motion_sensor
    to: "on"
    id: motion_on
  - platform: time_pattern
    minutes: "/5"
    id: periodic
  - platform: homeassistant
    event: start
    id: ha_start
  - platform: state
    entity_id: !input humidity_sensor
    to: [unavailable, unknown]
    for:
      minutes: !input sensor_grace_min
    id: sensors_lost
  - platform: state
    entity_id: !input humidity_sensor
    from: [unavailable, unknown]
    not_to: [unavailable, unknown]
    id: sensors_back
  - platform: state
    entity_id: !input boost_toggle
    to: ["on", "off"]
    id: boost_change

variables:
  entity_fan: !input fan_switch
  sensor_humidity: !input humidity_sensor
  sensor_temperature: !input temperature_sensor
  sensor_motion: !input motion_sensor
  entity_weather: !input weather_entity
  weather_fallback: !input weather_fallback
  thresh_target: !input target_humidity
  thresh_high: !input high_humidity
  hysteresis: !input hysteresis
  thresh_mold: !input mold_humidity
  dp_delta_min: !input dew_point_delta_min
  shower_rh_jump: !input shower_rh_jump
  presence_window_min: !input presence_window_min
  min_runtime: !input min_runtime
  max_runtime: !input max_runtime
  boost_toggle: !input boost_toggle
  boost_runtime_min: !input boost_runtime_min
  sensor_grace_min: !input sensor_grace_min
  degraded_run_min: !input degraded_run_min
  notify_targets: !input notify_targets
  t_night_start: !input night_start
  t_night_end: !input night_end

action:
  # =============================================
  # STEP 1: COMPUTE EVERY FACT (inside action for trace visibility)
  # Every boolean is a {{ }} expression — bare true/false text is a truthy string in HA.
  # =============================================
  - variables:
      indoor_temp_raw: "{{ states(sensor_temperature) }}"
      indoor_rh_raw: "{{ states(sensor_humidity) }}"
      sensors_ok: "{{ is_number(indoor_temp_raw) and is_number(indoor_rh_raw) }}"
      indoor_temp: "{{ indoor_temp_raw | float(20) }}"
      indoor_rh: "{{ indoor_rh_raw | float(50) }}"

      # --- Weather: first candidate with usable data ---
      weather_candidates: >-
        {{ [entity_weather] + (weather_fallback if (weather_fallback is iterable and weather_fallback is not string) else ([weather_fallback] if weather_fallback else [])) }}
      weather_used: >-
        {% set ns = namespace(w='') %}
        {% for w in weather_candidates %}
          {% if ns.w == '' and states(w) not in ['unavailable', 'unknown', ''] and
                (is_number(state_attr(w, 'dew_point')) or
                 (is_number(state_attr(w, 'temperature')) and is_number(state_attr(w, 'humidity')))) %}
            {% set ns.w = w %}
          {% endif %}
        {% endfor %}
        {{ ns.w }}
      outdoor_temp: "{{ (state_attr(weather_used, 'temperature') | float(15)) if weather_used else 15 }}"
      outdoor_rh: "{{ (state_attr(weather_used, 'humidity') | float(50)) if weather_used else 50 }}"
      outdoor_dp: >-
        {% if weather_used and is_number(state_attr(weather_used, 'dew_point')) %}
          {{ state_attr(weather_used, 'dew_point') | float | round(1) }}
        {% elif weather_used %}
          {% set T = outdoor_temp | float %}
          {% set RH = [outdoor_rh | float, 1] | max %}
          {% set a = 17.625 %}
          {% set b = 243.04 %}
          {% set alpha = (a * T) / (b + T) + log(RH / 100.0) %}
          {{ (b * alpha / (a - alpha)) | round(1) }}
        {% else %}
          {{ 13.0 }}
        {% endif %}

      # --- Psychrometrics (Magnus) ---
      indoor_dp: >-
        {% set T = indoor_temp | float %}
        {% set RH = [indoor_rh | float, 1] | max %}
        {% set a = 17.625 %}
        {% set b = 243.04 %}
        {% set alpha = (a * T) / (b + T) + log(RH / 100.0) %}
        {{ (b * alpha / (a - alpha)) | round(1) }}
      dp_delta: "{{ (indoor_dp | float - outdoor_dp | float) | round(1) }}"
      # Indoor RH at which the indoor dew point equals outdoor dew point + margin: below this,
      # ventilation cannot dry the room any further.
      rh_floor: >-
        {% set T = indoor_temp | float %}
        {% set Td = outdoor_dp | float + dp_delta_min | float %}
        {% if Td >= T %}
          {{ 100.0 }}
        {% else %}
          {% set a = 17.625 %}
          {% set b = 243.04 %}
          {{ ([0.0, [100.0, 100.0 * e ** (a * Td / (b + Td) - a * T / (b + T))] | min] | max) | round(1) }}
        {% endif %}
      stop_target: "{{ [thresh_target | float, rh_floor | float] | max | round(1) }}"
      start_threshold: "{{ [[thresh_high | float, stop_target | float + hysteresis | float] | max, 100.0] | min | round(1) }}"

      # --- Fan and time facts ---
      fan_is_on: "{{ is_state(entity_fan, 'on') }}"
      fan_on_minutes: >-
        {{ (((now() - states[entity_fan].last_changed).total_seconds() / 60) | int) if (fan_is_on and states[entity_fan] is not none) else 0 }}
      minutes_since_fan_change: >-
        {{ (((now() - states[entity_fan].last_changed).total_seconds() / 60) | round(1)) if states[entity_fan] is not none else 9999 }}
      is_night: >-
        {% set t = now().strftime('%H:%M') %}
        {% set s = t_night_start[:5] %}
        {% set e_ = t_night_end[:5] %}
        {{ (t >= s or t < e_) if s > e_ else (s <= t and t < e_) }}
      minutes_since_motion: >-
        {{ (((now() - states[sensor_motion].last_changed).total_seconds() / 60) | round(1)) if states[sensor_motion] is not none else 9999 }}
      presence_recent: "{{ is_state(sensor_motion, 'on') or minutes_since_motion | float < presence_window_min | float }}"

      # --- Shower signature: jump between two consecutive reports + recent presence ---
      shower_signal: >-
        {{ trigger is defined and trigger.id | default('') == 'humidity_change' and
           trigger.from_state is not none and trigger.to_state is not none and
           is_number(trigger.from_state.state) and is_number(trigger.to_state.state) and
           (trigger.to_state.state | float - trigger.from_state.state | float) >= shower_rh_jump | float and
           presence_recent }}

      # --- Boost ---
      boost_list: >-
        {{ boost_toggle if (boost_toggle is iterable and boost_toggle is not string) else ([boost_toggle] if boost_toggle else []) }}
      boost_active: >-
        {% set ns = namespace(a=false) %}
        {% for b in boost_list %}
          {% if is_state(b, 'on') and states[b] is not none and
                ((now() - states[b].last_changed).total_seconds() / 60) < boost_runtime_min | float %}
            {% set ns.a = true %}
          {% endif %}
        {% endfor %}
        {{ ns.a }}
      boost_expired_list: >-
        {% set ns = namespace(x=[]) %}
        {% for b in boost_list %}
          {% if is_state(b, 'on') and states[b] is not none and
                ((now() - states[b].last_changed).total_seconds() / 60) >= boost_runtime_min | float %}
            {% set ns.x = ns.x + [b] %}
          {% endif %}
        {% endfor %}
        {{ ns.x }}

      # --- Degraded mode and mold ---
      degraded_on: "{{ is_state(sensor_motion, 'on') or minutes_since_motion | float < degraded_run_min | float }}"
      mold_on: "{{ sensors_ok and indoor_rh | float >= thresh_mold | float and dp_delta | float > 0 }}"

      # --- Decision: first match wins (spec §3.4) ---
      active_rule: >-
        {% if boost_active %}boost
        {% elif not sensors_ok %}degraded
        {% elif mold_on %}mold
        {% elif fan_is_on and fan_on_minutes | int < min_runtime | int %}min_run
        {% elif fan_is_on and fan_on_minutes | int >= max_runtime | int %}max_run
        {% elif shower_signal %}shower
        {% elif fan_is_on and indoor_rh | float > stop_target | float %}continue
        {% elif not fan_is_on and indoor_rh | float > start_threshold | float and not is_night %}start
        {% else %}idle
        {% endif %}
      desired_on: >-
        {% if active_rule == 'degraded' %}{{ degraded_on }}{% else %}{{ active_rule in ['boost', 'mold', 'min_run', 'shower', 'continue', 'start'] }}{% endif %}

  # =============================================
  # STEP 2: SENSOR OFFLINE / BACK (edge-triggered, once per transition)
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ trigger.id | default('') == 'sensors_lost' }}"
        sequence:
          - service: persistent_notification.create
            data:
              title: "Ventilator — Sensor Offline"
              message: >
                {{ sensor_humidity }} has been {{ states(sensor_humidity) }} for
                {{ sensor_grace_min }} min. Degraded mode: the fan runs
                {{ degraded_run_min }} min after any bathroom motion until the sensor returns.
              notification_id: "ventilator_sensor_warning"
          - repeat:
              for_each: "{{ notify_targets }}"
              sequence:
                - service: "{{ repeat.item }}"
                  continue_on_error: true
                  data:
                    title: "Bathroom fan — sensor offline"
                    message: "Humidity sensor offline for {{ sensor_grace_min }} min. Fan now runs {{ degraded_run_min }} min after motion."
      - conditions:
          - condition: template
            value_template: >-
              {{ trigger.id | default('') == 'sensors_back' and sensors_ok and
                 trigger.from_state is not none and
                 (now() - trigger.from_state.last_changed).total_seconds() >= sensor_grace_min | float * 60 }}
        sequence:
          - service: persistent_notification.dismiss
            continue_on_error: true
            data:
              notification_id: "ventilator_sensor_warning"
          - repeat:
              for_each: "{{ notify_targets }}"
              sequence:
                - service: "{{ repeat.item }}"
                  continue_on_error: true
                  data:
                    title: "Bathroom fan — sensor back"
                    message: "Humidity sensor reporting again ({{ indoor_rh }}% RH). Normal control resumed."

  # =============================================
  # STEP 3: MOLD OVERRIDE NOTIFICATION (edge: only when it takes over from an idle fan)
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ mold_on and not fan_is_on }}"
        sequence:
          - service: persistent_notification.create
            data:
              title: "Ventilator — Mold Safety Override"
              message: >
                Fan forced ON: humidity {{ indoor_rh }}% is at or above {{ thresh_mold }}%.
                Indoor dew point {{ indoor_dp }}°C, outdoor {{ outdoor_dp }}°C ({{ weather_used }}).
              notification_id: "ventilator_mold_warning"
          # Push only when the fan has been untouched for an hour: a persisting mold condition
          # re-enters this branch after every max-run cycle (45 on / 5 off) and would otherwise
          # push every ~50 min. The persistent notification above is refreshed on every edge.
          - condition: template
            value_template: "{{ minutes_since_fan_change | float >= 60 }}"
          - repeat:
              for_each: "{{ notify_targets }}"
              sequence:
                - service: "{{ repeat.item }}"
                  continue_on_error: true
                  data:
                    title: "Bathroom fan — mold override"
                    message: "Bathroom at {{ indoor_rh }}% RH (≥ {{ thresh_mold }}%). Fan forced on."
      - conditions:
          - condition: template
            value_template: "{{ not mold_on }}"
        sequence:
          - service: persistent_notification.dismiss
            continue_on_error: true
            data:
              notification_id: "ventilator_mold_warning"

  # =============================================
  # STEP 4: FAN COMMAND (only when the state actually differs)
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ desired_on and not fan_is_on }}"
        sequence:
          - service: homeassistant.turn_on
            target:
              entity_id: "{{ entity_fan }}"
      - conditions:
          - condition: template
            value_template: "{{ (not desired_on) and fan_is_on }}"
        sequence:
          - service: homeassistant.turn_off
            target:
              entity_id: "{{ entity_fan }}"

  # =============================================
  # STEP 5: BOOST EXPIRY (after the fan call, so the resulting boost_change run sees a settled state)
  # =============================================
  - repeat:
      for_each: "{{ boost_expired_list }}"
      sequence:
        - service: input_boolean.turn_off
          continue_on_error: true
          target:
            entity_id: "{{ repeat.item }}"

  # =============================================
  # STEP 6: DEBUG NOTIFICATION (manual run only)
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ trigger.id | default('manual') == 'manual' }}"
        sequence:
          - service: persistent_notification.create
            data:
              title: "Ventilator Debug — {{ now().strftime('%H:%M:%S') }}"
              message: >
                **Indoor:** {{ indoor_temp }}°C / {{ indoor_rh }}% RH / DP {{ indoor_dp }}°C (sensors_ok={{ sensors_ok }})

                **Outdoor:** weather_used={{ weather_used if weather_used else 'none' }} · {{ outdoor_temp }}°C / {{ outdoor_rh }}% RH / outdoor_dp {{ outdoor_dp }}°C · dp_delta {{ dp_delta }}°C

                **Targets:** rh_floor {{ rh_floor }}% · stop_target {{ stop_target }}% · start_threshold {{ start_threshold }}%

                **Fan:** {{ 'ON' if fan_is_on else 'OFF' }} · fan_on_minutes {{ fan_on_minutes }} · min/max {{ min_runtime }}/{{ max_runtime }}

                **Presence:** motion {{ states(sensor_motion) }} · minutes_since_motion {{ minutes_since_motion }} · presence_recent {{ presence_recent }}

                **Flags:** is_night {{ is_night }} · boost_active {{ boost_active }} · mold_on {{ mold_on }} · degraded_on {{ degraded_on }}

                **Decision:** active_rule {{ active_rule }} → desired_on {{ desired_on }}
              notification_id: "ventilator_debug"
```

- [ ] **Step 2: Run the new suite to GREEN**

Run: `cd ~/AI/projects/Blueprints_Home && ~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests/test_bathroom_ventilator_structure.py -q`
Expected: all PASS. If a rendered-logic pin fails, the YAML template is wrong (fix the template); if a structure pin fails on whitespace only, normalise the YAML to the pinned form.

- [ ] **Step 3: Run the whole suite and confirm nothing else moved**

Run: `… -m pytest tests -q` → expected `PASS=58 + <new> FAIL=0`.

- [ ] **Step 4: Offline deploy validation against the migrated instance shape**

Run: `scripts/deploy-blueprint.sh --dry-run bathroom_ventilator.yaml leviemartin/bathroom_ventilator.yaml deploy/bathroom_ventilator_1774555916056.json` — Task 3 creates that JSON; if Task 3 is not yet done, run with no instance file and expect `dry-run: validation passed`.

- [ ] **Step 5: Commit (code pillar)**

```bash
git add bathroom_ventilator.yaml
git commit -m "feat(ventilator): v2.0.0 — adaptive dew-point targets, rate-of-rise shower detection, stateless rules, degraded mode, boost, push"
```

Step 6: Report `PASS=N FAIL=M` for the full suite.

---

## Task 3: Instance migration JSON + docs

**Model tier:** Sonnet
**Rationale:** The JSON is fully specified; the requirements rewrite and README edit need light judgment to stay faithful to the spec.
**Effort:** high.

**Files:**
- Create: `deploy/bathroom_ventilator_1774555916056.json`
- Modify: `requirements_bathroom_ventilator.md` (full rewrite)
- Modify: `README.md` lines 75–100 (the "Bathroom Ventilator Blueprint" section)

**Interfaces:**
- Consumes: input keys from Task 2.
- Produces: the instance file Task 4 deploys.

- [ ] **Step 1: Write `deploy/bathroom_ventilator_1774555916056.json` (verbatim)**

```json
{
  "id": "1774555916056",
  "alias": "Bathroom Ventilator v2.0.0",
  "description": "",
  "use_blueprint": {
    "path": "leviemartin/bathroom_ventilator.yaml",
    "input": {
      "fan_switch": "light.on_off_plug_1",
      "humidity_sensor": "sensor.temp_sensor_bathroom_humidity_sensor",
      "temperature_sensor": "sensor.temp_sensor_bathroom",
      "motion_sensor": "binary_sensor.bathroom_motion",
      "weather_entity": "weather.home_sm",
      "weather_fallback": ["weather.openweathermap"],
      "boost_toggle": ["input_boolean.bathroom_fan_boost"],
      "notify_targets": ["notify.mobile_app_martin_fold"]
    }
  }
}
```

Met.no (`weather.home_sm`) becomes primary because it exposes `dew_point` natively; OpenWeatherMap stays as fallback (temperature + humidity → Magnus). All numeric inputs use blueprint defaults.

Also append one line to `.gitignore` so the deploy script's pre-deploy backups never get committed:

```
deploy/*.prev.json
```

- [ ] **Step 2: Dry-run the deploy validation**

Run: `scripts/deploy-blueprint.sh --dry-run bathroom_ventilator.yaml leviemartin/bathroom_ventilator.yaml deploy/bathroom_ventilator_1774555916056.json`
Expected: `instance …: ok (id 1774555916056, 8 inputs)` then `dry-run: validation passed`.

- [ ] **Step 3: Rewrite `requirements_bathroom_ventilator.md` (verbatim)**

```markdown
# Requirements: Bathroom Ventilator Blueprint (v2.0.0)

## Overview
Demand-controlled bathroom exhaust fan for the Dutch climate (Laren). An on/off fan on a smart plug is driven by indoor humidity, outdoor dew point, presence and a manual boost. The fan never runs on a timer schedule: trickle vents supply background air, the fan exhausts on demand (ASHRAE 62.2 §5 demand-controlled mode; Bbl art. 3.67 lid 6 is a capacity minimum, met by the TURBOE.125 at 230–345 m³/h).

## Goals
1. **Outdoor-conditioned targets:** the effective stop target is the higher of the configured target (60 % RH) and the indoor RH whose dew point equals outdoor dew point + margin (2 °C). The start threshold sits hysteresis (5 %) above it. The fan stops where ventilation stops helping.
2. **Shower detection at any hour:** a humidity jump of ≥ 6 % between two consecutive sensor reports (the Aqara T1 reports instantly on that change) with bathroom motion within the last 15 min. Quiet hours (22:00–05:30) only block new non-shower starts.
3. **Bounded runs:** every run lasts at least 15 min and at most 45 min; a run continues while RH is above the effective stop target.
4. **Mold safety:** RH ≥ 85 % with drier outdoor air forces the fan on at any hour, with one notification.
5. **Degraded mode:** humidity sensor unavailable ≥ 10 min → one push + persistent notification; the fan then runs 20 min after any motion until the sensor returns (second push on recovery).
6. **Boost:** an `input_boolean` toggle forces the fan on for 20 min, then clears itself.
7. **Stateless:** every trigger re-decides from live entity state; timing comes from `last_changed`; no delays, so boost and sensor loss interrupt instantly.

## Hardware (live 2026-09-07)
- `light.on_off_plug_1` — innr On/Off plug on the Hue bridge, feeds the TURBOE.125 tube fan (25–29 W, 29–34 dBA)
- `sensor.temp_sensor_bathroom` + `sensor.temp_sensor_bathroom_humidity_sensor` — Aqara T1 via Aqara Hub M2 (HomeKit); reports on ΔRH ≥ 6 % / ΔT ≥ 0.5 °C, else hourly
- `binary_sensor.bathroom_motion` — Hue motion sensor (bridge-controlled clear delay)
- `weather.home_sm` (Met.no, has `dew_point`) primary; `weather.openweathermap` fallback
- `input_boolean.bathroom_fan_boost` — dashboard boost toggle
- `notify.mobile_app_martin_fold` — push target

## Decision order (first match wins)
1. boost active → ON
2. sensors unavailable → ON iff motion within the last 20 min
3. mold override (RH ≥ 85 %, indoor dew point above outdoor) → ON
4. fan on for < 15 min → stay ON
5. fan on for ≥ 45 min → OFF
6. shower signature → ON
7. fan on and RH > effective stop target → stay ON
8. fan off, RH > start threshold, not quiet hours → ON
9. otherwise → OFF

## Psychrometrics
Magnus: α = 17.625·T/(243.04+T) + ln(RH/100); Td = 243.04·α/(17.625−α).
Adaptive floor: RH_floor = 100·exp(17.625·Td'/(243.04+Td') − 17.625·T/(243.04+T)) with Td' = outdoor dew point + margin; 100 when Td' ≥ T.
Example: bathroom 22 °C, outdoor dew point 16 °C, margin 2 → floor 78.1 %; the fan stops at 78 % instead of running toward an unreachable 60 %.

## Testing & debugging
Manual "Run" writes a persistent notification with every computed variable (weather entity used, outdoor dew point, floor, stop/start targets, fan minutes, presence, flags, decision). `tests/test_bathroom_ventilator_structure.py` pins the schema, triggers, decision order and renders the psychrometric and decision rows.
```

- [ ] **Step 4: Update the README section (replace the feature bullets + requirements under "## Bathroom Ventilator Blueprint")**

Replace the current bullets with:

```markdown
*   **🌡️ Outdoor-Conditioned Targets (v2.0.0):** The stop target follows the outdoor dew point (Magnus, or the weather entity's native `dew_point`). On a muggy day the fan stops where ventilation stops helping instead of chasing an unreachable RH%.
*   **🚿 Shower Detection, Any Hour:** A humidity jump between two sensor reports plus recent motion — works with sensors that report on change (Aqara T1: 6 %). Quiet hours only block new non-shower starts.
*   **⏱️ Bounded, Stateless Runs:** Minimum 15 / maximum 45 min per run, re-decided on every trigger from live state; boost and sensor loss interrupt instantly.
*   **🛟 Degraded Mode:** Humidity sensor offline → one push, then motion-timed runs until it returns.
*   **🔘 Boost Toggle + 📱 Push:** `input_boolean` boost with auto-expiry; mobile push for sensor offline/back and mold override.
*   **🦠 Mold Safety Override:** RH ≥ 85 % with drier outdoor air forces the fan on.
```

and under requirements: `Fan entity (light, switch or fan) · indoor temperature + humidity sensor · motion sensor · weather entity (dew_point used when present) · optional fallback weather entity, boost input_boolean, notify targets`. Keep the import badge/URL lines unchanged.

- [ ] **Step 5: Run the full suite (docs cannot break it, but the gate is the gate)**

Run: `… -m pytest tests -q` → `PASS=N FAIL=0`.

- [ ] **Step 6: Commit (docs pillar, then deploy-data pillar)**

```bash
git add requirements_bathroom_ventilator.md README.md
git commit -m "docs(ventilator): v2.0.0 requirements + README section"
git add deploy/bathroom_ventilator_1774555916056.json .gitignore
git commit -m "deploy(ventilator): migrated instance config for v2.0.0 (Met.no primary, OWM fallback, boost + push); ignore deploy backups"
```

Step 7: Report `PASS=N FAIL=M`.

---

## Task 4: Deploy + live-verify (main loop, operator-visible)

**Model tier:** Fable (main loop)
**Rationale:** Live house state, irreversible-ish writes and judgment on trace evidence; not delegable.
**Effort:** high. **Preceded by:** code-time board PASS ([6]) and merge ([7]) — do not deploy from the branch.

**Files:** none edited. Uses `scripts/deploy-blueprint.sh` (already pinned in the TCB roster; not modified by this plan).

- [ ] **Step 1: TCB verify + branch freshness** — `TCB_EXTRA=/home/martin/AI/projects/Blueprints_Home/scripts/deploy-blueprint.sh ~/.claude/skills/convene-board/scripts/tcb-manifest.sh verify /home/martin/AI/reviews/tcb-baseline-16ef53e7f973185a.txt` → rc 0 or HALT. Then `git fetch origin && git checkout main && [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ]` — deploy only from a `main` that equals `origin/main` (memory: fetch-origin-before-deploy; a concurrent session's merge must not be reverted by a stale checkout). If the harness classifier blocks the deploy command, render it through `op-templates.sh` (stack-b §4.6) and hand it to Martin — no workaround.
- [ ] **Step 2: Sensor ids** — `curl …/api/states/sensor.temp_sensor_bathroom_humidity_sensor`; if 404 (Aqara reset re-created the device), find the new ids (`config/entity_registry/list` filtered on `original_name` "Humidity Sensor" + device name "Temp Sensor Bathroom") and edit the instance JSON (commit as a deploy-data fix) before continuing.
- [ ] **Step 3: Create the boost helper (idempotent)** — there is NO REST config endpoint for input_boolean (live probe 2026-09-07: `GET /api/config/input_boolean/config/heating_rack_boost` → 404 even for an existing storage helper). Use the WebSocket storage-collection API: first `hass-cli -o json raw ws input_boolean/list | jq '.result[] | select(.id=="bathroom_fan_boost")'` — if it already exists, skip; else `hass-cli -o json raw ws input_boolean/create --json '{"name":"Bathroom fan boost","icon":"mdi:fan-plus"}'` (HA slugifies the name → id `bathroom_fan_boost` → entity `input_boolean.bathroom_fan_boost`; the probe confirmed the schema requires `name`). Then `GET /api/states/input_boolean.bathroom_fan_boost` is `off`.
- [ ] **Step 4: Deploy** — `scripts/deploy-blueprint.sh bathroom_ventilator.yaml leviemartin/bathroom_ventilator.yaml deploy/bathroom_ventilator_1774555916056.json` → expect `blueprint/save: ok`, `instance 1774555916056: config written`, `automation.bathroom_ventilator_v1_0_0 state=on`, `deploy complete`. The backup lands in `deploy/1774555916056.prev.json` (gitignored since Task 3; never commit it).
- [ ] **Step 5: Read-path proof** — `POST /api/services/automation/trigger` with `{"entity_id":"automation.bathroom_ventilator_v1_0_0"}`; read `persistent_notification/get` → `ventilator_debug` must show `weather_used=weather.home_sm`, a numeric `rh_floor`, `stop_target`, `start_threshold`, `active_rule`. Then fetch the latest trace (`trace/list` + `trace/get`) and confirm `changed_variables` contains `active_rule` and `desired_on` (v2-only variables; cannot exist in a v1 render).
- [ ] **Step 6: Degraded-mode check (sensor still offline)** — with the Aqara sensor still `unavailable`, `active_rule` must read `degraded`; walk into the bathroom (or wait for the next real motion) and confirm the fan turns on and off ≈20 min after motion ends. If the sensor is back: skip, and instead confirm `sensors_ok=True` and `active_rule` in {idle, start, continue}.
- [ ] **Step 7: Log gate** — `system_log/list` filtered on `bathroom_ventilator` shows zero errors after the deploy timestamp.
- [ ] **Step 8: Record** — post the deploy evidence (entity state, debug dump excerpt, trace step) on session #11; observation loop per the Phase 0 criteria; `<!-- observe:open -->` stays until criteria 1–5 pass or Martin waives.

Step 9: Report `deploy: PASS=N FAIL=M` over the eight steps above.

---

## Chain notes

- **[4] design-time board** runs on spec + this plan before Task 1 (`triple-check` → `convene-board`, standard dial, R1 Opus + R2 Codex, `/effort xhigh`).
- **[6] code-time board** runs on the branch diff after Task 3 (`review-shipped` → `convene-board`), then `code-review-gate`, PR with `Session: #11`, merge, Task 4.
- **Session 2 (heating rack v2.0.0)** gets its own plan after this session closes; spec §4 is its input.
