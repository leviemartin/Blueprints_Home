"""Contract tests for adjacent_room_lights.yaml v2.1.0 (RFC 2026-11-26, job J5).

Every trigger recomputes one `decision` (off / stage_2 / stage_1 / on / update / none) from
current state, mirroring circadian_livingroom.yaml. HA owns the timers; templates are rendered
here with fake states.
"""
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml
from jinja2 import StrictUndefined

from test_bedroom_precool_structure import HassLoader, TZ, _env, _reparse, _var_template

ROOT = Path(__file__).resolve().parent.parent
A, B, LUX = "binary_sensor.attic_main", "binary_sensor.attic_stairs", "sensor.hall_lux"
LIGHTS = ["light.x", "light.y"]
HELPER = "input_boolean.room_auto_off"
CHAIN = ["current_lux", "lux_age", "missing_sensors", "is_motion_on", "empty_age", "lights_on",
         "manual_off", "was_empty", "bright", "decision"]

# Literal v1.0.0 formulas: independent of git and the version under test.
EXPECTED = yaml.safe_load("""
mode: >
  {% set t_now = now().strftime('%H:%M:%S') %}
  {% if t_now >= t_night %} night
  {% elif t_now >= t_evening %} evening
  {% elif t_now >= t_toddler %} toddler
  {% elif t_now >= t_dinner %} dinner
  {% elif t_now >= '06:00:00' %} day
  {% else %} night {% endif %}
target_kelvin: >
  {% if mode == 'dinner' %} {{ k_dinner | int }}
  {% elif mode == 'toddler' %} {{ k_toddler | int }}
  {% elif mode == 'evening' %} {{ k_evening | int }}
  {% elif mode == 'night' %} {{ k_night | int }}
  {% else %}
    {# Day Mode: Use Sun Elevation #}
    {% set elev = state_attr('sun.sun', 'elevation') | float(0) %}
    {% set pct = (elev + 6) / 51 %}
    {% set k = (val_max_k - val_min_k) * pct + val_min_k %}
    {{ [val_min_k, [val_max_k, k] | min] | max | int }}
  {% endif %}
target_brightness: >
  {% if mode == 'dinner' %} {{ b_dinner | int }}
  {% elif mode == 'toddler' %} {{ b_toddler | int }}
  {% elif mode == 'evening' %} {{ b_evening | int }}
  {% elif mode == 'night' %} {{ b_night | int }}
  {% else %} 100 {% endif %}
""")


@pytest.fixture
def text():
    return (ROOT / "adjacent_room_lights.yaml").read_text()


@pytest.fixture
def bp(text):
    return yaml.load(text, Loader=HassLoader)


class _St:
    def __init__(self, state, last_changed, attributes=None):
        self.state, self.last_changed = state, last_changed
        self.attributes = attributes or {}


def at(time):
    return datetime.fromisoformat("2026-11-27T" + time).replace(tzinfo=TZ)


def _strict_env(now, table):
    env = _env(now)
    env.undefined = StrictUndefined

    def need_str(entity):
        if not isinstance(entity, str):
            raise TypeError("entity id must be a string")

    class States:
        def __getitem__(self, entity):
            need_str(entity)
            return table.get(entity)

        def __call__(self, entity):
            need_str(entity)
            st = table.get(entity)
            return st.state if st is not None else "unknown"

    def is_state(entity, state):
        need_str(entity)
        return entity in table and table[entity].state == state

    env.globals.update(states=States(), is_state=is_state)
    return env


def render(template, now, table=None, **ctx):
    return _reparse(_strict_env(now, table or {}).from_string(template).render(**ctx).strip())


def _chain(bp, names, now, ctx):
    ctx = dict(ctx)
    table = ctx.pop("table", {})
    for name in names:
        ctx[name] = render(_var_template(bp, name), now, table, **ctx)
    return ctx


def state(bp, tid="update_loop", time="14:00:00", a="off", b="off", age=300, lux=None,
          lux_age=3600, lights="on", helper=None, gap=3600, table=None, **changes):
    """`age` = seconds both sensors have been in their state; `gap` = how long the sensor that
    fired motion_on had been clear before; lux=None means no lux sensor configured."""
    now = at(time)
    if table is None:
        table = {A: _St(a, now - timedelta(seconds=age)), B: _St(b, now - timedelta(seconds=age))}
        for light in LIGHTS:
            table[light] = _St(lights, now - timedelta(seconds=3600))
        if lux is not None:
            table[LUX] = _St(lux, now - timedelta(seconds=lux_age))
        if helper is not None:
            table[HELPER] = _St(helper, now)
    ctx = dict(sensor_motion=[A, B], mins_stage1=2, mins_stage2=4, mins_off=5,
               sensor_lux=LUX if lux is not None else [], lux_enabled=lux is not None,
               threshold_on=150, threshold_off=220, lux_off_mins=10, light_list=LIGHTS,
               auto_off_helper=HELPER if helper is not None else [],
               trigger={"id": tid}, table=table)
    if tid == "motion_on":
        ctx["trigger"] = {"id": tid, "entity_id": A, "from_state": _St("off", now - timedelta(seconds=gap))}
    ctx.update(changes)
    return _chain(bp, CHAIN, now, ctx)


def decide(bp, *args, **kwargs):
    return state(bp, *args, **kwargs)["decision"]


def triggers(bp):
    return {t["id"]: t for t in bp["trigger"]}


def plain(value):
    if hasattr(value, "name"):
        return value.name
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


# --- inputs and triggers -------------------------------------------------------------------

def test_version(bp):
    assert bp["blueprint"]["name"] == "Adjacent Room Circadian Lights v2.1.0"
    assert "**Version: 2.1.0" in bp["blueprint"]["description"]


def test_required_multiple_motion_input(bp, text):
    item = bp["blueprint"]["input"]["motion_sensors"]
    assert item["selector"] == {"entity": {"domain": "binary_sensor",
                                           "device_class": ["motion", "occupancy"], "multiple": True}}
    assert "default" not in item
    assert "motion_sensor:" not in text


def test_new_inputs(bp):
    inputs = bp["blueprint"]["input"]
    assert inputs["lux_on_duration"]["default"] == 5
    assert list(inputs).index("lux_on_duration") == list(inputs).index("lux_off_duration") + 1
    assert inputs["auto_off_helper"]["default"] == []
    assert inputs["auto_off_helper"]["selector"] == {"entity": {"domain": "input_boolean"}}
    assert bp["variables"]["auto_off_helper"].name == "auto_off_helper"
    assert "warning_kelvin" in inputs


def test_trigger_table(bp):
    ts = triggers(bp)
    assert plain(ts["motion_on"]) == {"platform": "state", "entity_id": "motion_sensors", "to": "on", "id": "motion_on"}
    for tid, key in (("stage_1", "time_to_stage1"), ("stage_2", "time_to_stage2"), ("stage_off", "time_to_off")):
        assert plain(ts[tid]) == {"platform": "state", "entity_id": "motion_sensors",
                                  "to": ["off", "unavailable", "unknown"], "for": {"minutes": key}, "id": tid}
    assert plain(ts["update_loop"]) == {"platform": "time_pattern", "minutes": "/5", "id": "update_loop"}
    assert plain(ts["ha_start"]) == {"platform": "homeassistant", "event": "start", "id": "ha_start"}
    assert plain(ts["reload"]) == {"platform": "event", "event_type": "automation_reloaded", "id": "reload"}
    assert plain(ts["override_resume"]) == {"platform": "state", "entity_id": "override_entity", "to": "off", "id": "override_resume"}
    for tid, key in (("lux_high", "lux_off_duration"), ("lux_low", "lux_on_duration")):
        assert ts[tid]["platform"] == "template"
        assert plain(ts[tid]["for"]) == {"minutes": key}
    for tid, at_ in (("profile_day", "06:00:00"), ("profile_dinner", "time_dinner"), ("profile_toddler", "time_toddler"),
                     ("profile_evening", "time_evening"), ("profile_night", "time_night")):
        assert plain(ts[tid]) == {"platform": "time", "at": at_, "id": tid}
    watchdogs = [plain(t) for t in bp["trigger"] if t["id"] == "sensor_watchdog"]
    assert watchdogs == [{"platform": "state", "entity_id": "motion_sensors", "to": st, "for": {"minutes": 30},
                          "id": "sensor_watchdog"} for st in ("unavailable", "unknown")]
    assert bp["mode"] == "restart"


@pytest.mark.parametrize("tid,lux,expected", [
    ("lux_high", "221", True), ("lux_high", "220", False), ("lux_high", "unavailable", False),
    ("lux_low", "149", True), ("lux_low", "150", False), ("lux_low", "unavailable", False)])
def test_lux_template_triggers(bp, tid, lux, expected):
    template = triggers(bp)[tid]["value_template"]
    ctx = dict(t_lux=LUX, t_on=150, t_off=220)
    assert render(template, at("14:00:00"), {LUX: _St(lux, at("14:00:00"))}, **ctx) is expected
    assert render(template, at("14:00:00"), {}, t_lux=[], t_on=150, t_off=220) is False


@pytest.mark.parametrize("name", ["mode", "target_kelvin", "target_brightness"])
def test_v1_formulas_unchanged(bp, name):
    assert _var_template(bp, name) == EXPECTED[name]


# --- presence and stages -------------------------------------------------------------------

@pytest.mark.parametrize("age,expected", [(119, "update"), (120, "stage_1"), (239, "stage_1"),
                                          (240, "stage_2"), (299, "stage_2"), (300, "off")])
def test_stages_follow_how_long_the_room_was_empty(bp, age, expected):
    assert decide(bp, age=age) == expected


def test_any_sensor_on_keeps_the_room_occupied(bp):
    assert decide(bp, a="on", age=7200) == "update"
    assert decide(bp, b="on", age=7200) == "update"


@pytest.mark.parametrize("st", ["unavailable", "unknown"])
def test_dead_sensors_count_as_clear(bp, st):
    assert decide(bp, a=st, b=st, age=300) == "off"
    now = at("14:00:00")
    table = {A: _St("off", now - timedelta(seconds=300)), B: _St(st, now - timedelta(seconds=300)),
             "light.x": _St("on", now), "light.y": _St("on", now)}
    assert decide(bp, table=table) == "off"


def test_missing_sensor_counts_as_clear(bp):
    now = at("14:00:00")
    table = {A: _St("off", now - timedelta(seconds=300)), "light.x": _St("on", now), "light.y": _St("on", now)}
    result = state(bp, table=table)
    assert result["missing_sensors"] == [B]
    assert result["decision"] == "off"


def test_motion_restores_from_a_stage(bp):
    assert decide(bp, tid="motion_on", a="on", age=0) == "update"


@pytest.mark.parametrize("tid", ["stage_1", "stage_2", "stage_off", "update_loop", "sensor_watchdog", "ha_start"])
def test_stage_decision_is_the_same_for_any_trigger(bp, tid):
    assert decide(bp, tid=tid, age=130) == "stage_1"
    assert decide(bp, tid=tid, age=300) == "off"
    assert decide(bp, tid=tid, age=300, lights="off") == "none"


def test_lights_on_with_motion(bp):
    assert decide(bp, tid="motion_on", a="on", lights="off") == "on"
    assert decide(bp, tid="update_loop", a="on", lights="off") == "none"


# --- lux -----------------------------------------------------------------------------------

def test_no_lux_sensor_means_always_dark(bp):
    assert state(bp)["current_lux"] is None
    assert decide(bp, tid="motion_on", a="on", lights="off") == "on"


@pytest.mark.parametrize("lux,expected", [("149", "on"), ("150", "none"), ("unavailable", "on")])
def test_motion_turns_on_only_when_dark(bp, lux, expected):
    assert decide(bp, tid="motion_on", a="on", lights="off", lux=lux) == expected


@pytest.mark.parametrize("lux,lux_age,tid,expected", [
    ("230", 600, "update_loop", "off"), ("230", 599, "update_loop", "update"),
    ("230", 0, "lux_high", "off"), ("220", 3600, "update_loop", "update"),
    ("230", 0, "ha_start", "off"), ("unavailable", 3600, "lux_high", "none")])
def test_daylight_off(bp, lux, lux_age, tid, expected):
    assert decide(bp, tid=tid, a="on", lux=lux, lux_age=lux_age) == expected


def test_lux_low_relights_with_motion_only(bp):
    assert decide(bp, tid="lux_low", a="on", lights="off", lux="100") == "on"
    assert decide(bp, tid="lux_low", lights="off", lux="100") == "none"


# --- manual changes ------------------------------------------------------------------------

@pytest.mark.parametrize("gap,b,expected", [(3600, "off", "on"), (299, "off", "none"), (3600, "on", "none")])
def test_manual_off_stays_off_until_the_room_was_empty(bp, gap, b, expected):
    assert decide(bp, tid="motion_on", a="on", b=b, lights="off", gap=gap, helper="off") == expected


def test_our_own_off_relights_on_any_motion(bp):
    assert decide(bp, tid="motion_on", a="on", b="on", lights="off", gap=10, helper="on") == "on"


@pytest.mark.parametrize("tid", ["lux_low", "ha_start", "reload"])
def test_manual_off_survives_lux_low_and_restarts(bp, tid):
    assert decide(bp, tid=tid, a="on", lights="off", lux="100", helper="off") == "none"
    assert decide(bp, tid=tid, a="on", lights="off", lux="100", helper="on") == "on"


def test_manual_on_and_off_after_our_off_counts_as_manual(bp):
    now = at("14:00:00")
    def table(light_age, helper_age):
        t = {A: _St("on", now - timedelta(seconds=300)), B: _St("off", now - timedelta(seconds=300)),
             HELPER: _St("on", now - timedelta(seconds=helper_age))}
        for light in LIGHTS:
            t[light] = _St("off", now - timedelta(seconds=light_age))
        return t
    assert state(bp, table=table(590, 600), helper="on")["manual_off"] is False
    assert state(bp, table=table(60, 600), helper="on")["manual_off"] is True


def _lit(bri_pct, kelvin=2500, mode="color_temp"):
    return _St("on", at("14:00:00"), {"brightness": round(bri_pct * 2.55),
                                      "color_temp_kelvin": kelvin, "color_mode": mode})


def _update(bp, table, tid="update_loop", lights=("light.x",), **kw):
    ctx = dict(light_list=list(lights), target_brightness=50, target_kelvin=2500,
               b_stage1=40, b_stage2=20, val_warn_k=2000, trigger={"id": tid})
    ctx.update(kw)
    return _chain(bp, ["force_update", "lit_lights", "update_lights"], at("14:00:00"), {**ctx, "table": table})


@pytest.mark.parametrize("bri,kelvin,mode,kept", [
    (54, 2500, "color_temp", True), (56, 2500, "color_temp", False),
    (50, 2640, "color_temp", True), (50, 2660, "color_temp", False),
    (40, 2000, "color_temp", True),   # our stage 1 level
    (20, 2000, "color_temp", True),   # our stage 2 level
    (40, 2400, "color_temp", False),  # stage brightness but not the warning colour
    (50, 2500, "xy", False), (50, None, "color_temp", True)])
def test_manual_tolerance(bp, bri, kelvin, mode, kept):
    out = _update(bp, {"light.x": _lit(bri, kelvin, mode)})
    assert out["update_lights"] == (["light.x"] if kept else [])


def test_profile_start_overrides_manual_changes(bp):
    table = {"light.x": _lit(90, 4000, "xy"), "light.y": _St("off", at("14:00:00"))}
    out = _update(bp, table, tid="profile_night", lights=("light.x", "light.y"))
    assert out["lit_lights"] == ["light.x"]
    assert out["update_lights"] == ["light.x"]


# --- actions -------------------------------------------------------------------------------

def test_branches_follow_the_decision(bp):
    branches = bp["action"][2]["choose"]
    assert [b["conditions"][0]["value_template"] for b in branches] == [
        "{{ decision == 'off' }}", "{{ decision == 'stage_1' }}", "{{ decision == 'stage_2' }}",
        "{{ decision == 'on' }}", "{{ decision == 'update' }}"]
    first = [b["sequence"][0]["then"][0]["service"] for b in branches]
    assert first == ["input_boolean.turn_on", "input_boolean.turn_off", "input_boolean.turn_off",
                     "light.turn_on", "input_boolean.turn_off"]
    assert branches[0]["sequence"][1]["service"] == "light.turn_off"
    assert branches[3]["sequence"][-1]["then"][0]["service"] == "input_boolean.turn_off"
    for i, key in ((1, "b_stage1"), (2, "b_stage2")):
        call = branches[i]["sequence"][1]
        assert call["target"]["entity_id"] == "{{ lit_lights }}"
        assert call["data"]["brightness_pct"] == "{{ %s | int }}" % key
        assert call["data"]["color_temp_kelvin"] == "{{ val_warn_k | int }}"
    assert branches[4]["sequence"][1]["if"][0]["value_template"] == "{{ update_lights | count > 0 }}"
    assert branches[4]["sequence"][1]["then"][0]["target"]["entity_id"] == "{{ update_lights }}"


def test_no_kelvin_guard_left(text):
    """The v2.0.0 update skipped any light near warning_kelvin, so 2000 K rooms never got the
    23:30 night dim. Stages now come from how long the room was empty."""
    assert "in_warning" not in text
    assert "threshold_on + 300" not in text


def test_override_stops_the_run(bp):
    assert "stop" in bp["action"][0]["choose"][0]["sequence"][0]


def _notice(bp, tid, time="14:00:00", missing=()):
    branch = bp["action"][-1]["choose"][0]
    ctx = dict(trigger={"id": tid}, missing_sensors=list(missing), sensor_motion=[A, B],
               this={"entity_id": "automation.kitchen"})
    due = render(branch["conditions"][0]["value_template"], at(time), **ctx)
    data = branch["sequence"][0]["data"]
    rendered = {k: render(v, at(time), **ctx) for k, v in data.items()} if due else None
    return due, rendered, branch["sequence"][0]["service"]


def test_dead_sensor_notice_is_a_persistent_notification(bp):
    due, data, service = _notice(bp, "sensor_watchdog")
    assert due is True and service == "persistent_notification.create"
    assert data["notification_id"] == "adjacent_lights_automation_kitchen"
    assert "30 min" in data["message"]


def test_missing_sensor_notice_hourly(bp):
    due, data, _ = _notice(bp, "update_loop", missing=[B])
    assert due is True and B in data["message"]
    assert _notice(bp, "update_loop", time="14:05:00", missing=[B])[0] is False
    assert _notice(bp, "update_loop", missing=[])[0] is False
