"""Contract tests for circadian_livingroom.yaml v3.3.0 (RFC 2026-11-26, jobs J2, J3 and J4).

Every trigger recomputes one `decision` (off / on / update / none) from the current state.
HA owns the state-trigger timers; these tests render the templates with fake states.
"""
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml
from jinja2 import StrictUndefined, UndefinedError

from test_bedroom_precool_structure import HassLoader, TZ, _env, _reparse, _var_template

ROOT = Path(__file__).resolve().parent.parent
FP2, FP300, LUX = "binary_sensor.fp2", "binary_sensor.fp300", "sensor.lux"
LIGHTS = ["light.a", "light.b"]
NOTICE = ["fp2_unavailable_30m", "fp2_unknown_30m", "fp300_unavailable_30m", "fp300_unknown_30m"]
CLAMP = "{{ [1, [60, late_night_timeout | int(1)] | min] | max }}"
CHAIN = ["current_lux", "lux_age", "presence_sensors", "missing_sensors", "in_dog_window",
         "window_age", "is_presence_on", "late_night_minutes", "in_late_window", "off_minutes",
         "empty_age", "room_empty", "dim_due", "was_empty", "lights_on", "manual_off", "bright",
         "decision"]
HELPER = "input_boolean.auto_off"


@pytest.fixture
def text():
    return (ROOT / "circadian_livingroom.yaml").read_text()


@pytest.fixture
def bp(text):
    return yaml.load(text, Loader=HassLoader)


class _St:
    def __init__(self, state, last_changed, attributes=None):
        self.state, self.last_changed = state, last_changed
        self.attributes = attributes or {}


class _NoLc:
    state = "off"


def at(time):
    return datetime.fromisoformat("2026-10-16T" + time).replace(tzinfo=TZ)


def _strict_env(now, table):
    env = _env(now)
    env.undefined = StrictUndefined
    env.tests["match"] = lambda value, pattern: re.match(pattern, str(value)) is not None

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


def state(bp, tid="update_loop", time="14:00:00", fp2="off", fp300="off", age=300,
          lux="100", lux_age=3600, lights="on", table=None, gap=3600, helper=None, **changes):
    """Run the decision chain. `age` is how long both sensors have been in their state;
    `gap` is how long the sensor that fired a presence_on trigger had been clear before."""
    now = at(time)
    if table is None:
        table = {FP2: _St(fp2, now - timedelta(seconds=age)),
                 FP300: _St(fp300, now - timedelta(seconds=age)),
                 LUX: _St(lux, now - timedelta(seconds=lux_age))}
        for light in LIGHTS:
            table[light] = _St(lights, now)
        if helper is not None:
            table[HELPER] = _St(helper, now)
    ctx = dict(presence_fp2=FP2, presence_fp300=FP300, sensor_lux=LUX, presence_timeout=5,
               late_night_timeout=1, late_night_start="23:00:00", late_night_end="06:30:00",
               dog_start="01:00:00", dog_end="06:00:00",
               threshold_on=175, threshold_off=250, off_duration=10,
               all_target_lights=LIGHTS, trigger={"id": tid}, table=table,
               auto_off_helper=HELPER if helper is not None else [])
    if tid.startswith("presence_on_"):
        ctx["trigger"] = {"id": tid, "entity_id": FP2 if tid.endswith("fp2") else FP300,
                          "from_state": _St("off", now - timedelta(seconds=gap))}
    ctx.update(changes)
    return _chain(bp, CHAIN, now, ctx)


def decide(bp, *args, **kwargs):
    return state(bp, *args, **kwargs)["decision"]


def window(bp, time, start="23:00:00", end="06:30:00"):
    return render(_var_template(bp, "in_late_window"), at(time),
                  late_night_start=start, late_night_end=end)


def triggers(bp):
    return {t["id"]: t for t in bp["trigger"]}


def plain(value):
    if hasattr(value, "name"):
        return value.name
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    return value


# --- inputs ----------------------------------------------------------------------------

def test_the_fakes_are_strict():
    env = _strict_env(at("14:00:00"), {})
    for call in (lambda: env.globals["is_state"]([], "on"),
                 lambda: env.globals["states"]([]),
                 lambda: env.globals["states"][[]]):
        with pytest.raises(TypeError):
            call()
    with pytest.raises(UndefinedError):
        env.from_string("{{ missing }}").render()


def test_version_is_3_3_0(bp):
    assert bp["blueprint"]["name"].endswith("v3.3.0")
    assert "**Version: 3.3.0" in bp["blueprint"]["description"]


def test_presence_inputs(bp, text):
    assert "presence_entity" not in text
    for name in ("presence_fp2", "presence_fp300"):
        item = bp["blueprint"]["input"][name]
        assert item["selector"] == {"entity": {"domain": "binary_sensor", "device_class": "occupancy"}}
        assert "default" not in item


def test_required_inputs_are_the_two_sensors_and_lux(bp):
    assert {k for k, v in bp["blueprint"]["input"].items() if "default" not in v} == {
        "presence_fp2", "presence_fp300", "illuminance_entity"}


def test_late_night_inputs(bp):
    inputs = bp["blueprint"]["input"]
    assert inputs["late_night_timeout"]["default"] == 1
    assert inputs["late_night_timeout"]["selector"] == {
        "number": {"min": 1, "max": 60, "step": 1, "unit_of_measurement": "min"}}
    for key, value in (("late_night_start", "23:00:00"), ("late_night_end", "06:30:00")):
        assert inputs[key]["default"] == value
        assert inputs[key]["selector"] == {"time": None}


def test_lux_inputs(bp):
    inputs = bp["blueprint"]["input"]
    for key, value in (("lux_on_threshold", 150), ("lux_off_threshold", 400),
                       ("lux_off_duration", 5), ("lux_on_duration", 5)):
        assert inputs[key]["default"] == value, key
    assert inputs["lux_on_duration"]["selector"]["number"]["unit_of_measurement"] == "min"
    assert list(inputs).index("lux_on_duration") == list(inputs).index("lux_off_duration") + 1


def test_notify_targets_input(bp):
    item = bp["blueprint"]["input"]["notify_targets"]
    assert item["default"] == []
    assert item["selector"] == {"text": {"multiple": True}}


def test_inputs_reach_templates(bp):
    for key, name in (("presence_fp2", "presence_fp2"), ("presence_fp300", "presence_fp300"),
                      ("presence_timeout", "presence_timeout"), ("sensor_lux", "illuminance_entity"),
                      ("late_night_timeout", "late_night_timeout"), ("notify_targets", "notify_targets"),
                      ("threshold_on", "lux_on_threshold"), ("threshold_off", "lux_off_threshold"),
                      ("off_duration", "lux_off_duration")):
        assert bp["variables"][key].name == name, key
    for key in ("dog_start", "dog_end"):
        assert bp["variables"][key].name == "fp300_ignore_" + key.split("_")[1]
        assert bp["trigger_variables"][key].name == "fp300_ignore_" + key.split("_")[1]
    assert bp["trigger_variables"]["late_night_timeout"].name == "late_night_timeout"


# --- triggers --------------------------------------------------------------------------

def test_trigger_table(bp):
    ts = triggers(bp)
    expected_ids = []
    for prefix in ("presence_on", "presence_off_long", "presence_off_short"):
        for sensor in ("fp2", "fp300"):
            tid = prefix + "_" + sensor
            expected_ids.append(tid)
            t = plain(dict(ts[tid]))
            assert t.pop("entity_id") == "presence_" + sensor
            expected = {"platform": "state", "id": tid, "to": "on"}
            if prefix != "presence_on":
                expected["to"] = ["off", "unavailable", "unknown"]
                expected["for"] = {"minutes": "presence_timeout" if prefix == "presence_off_long" else CLAMP}
            assert t == expected
    rest = [
        {"platform": "time_pattern", "minutes": "/5", "id": "update_loop"},
        {"platform": "homeassistant", "event": "start", "id": "ha_start"},
        {"platform": "event", "event_type": "automation_reloaded", "id": "reload"},
        {"platform": "numeric_state", "entity_id": "illuminance_entity",
         "above": "lux_off_threshold", "for": {"minutes": "lux_off_duration"}, "id": "lux_high"},
        {"platform": "numeric_state", "entity_id": "illuminance_entity",
         "below": "lux_on_threshold", "for": {"minutes": "lux_on_duration"}, "id": "lux_low"},
        {"platform": "state", "entity_id": "override_entity", "to": "off", "id": "override_resume"},
    ]
    for expected in rest:
        assert plain(ts[expected["id"]]) == expected
    for tid in NOTICE:
        sensor, st = tid.split("_")[0], tid.split("_")[1]
        assert plain(ts[tid]) == {"platform": "state", "entity_id": "presence_" + sensor,
                                  "to": st, "for": {"minutes": 30}, "id": tid}
    t = plain(dict(ts["presence_off_night_fp2"]))
    assert t == {"platform": "state", "entity_id": "presence_fp2", "id": "presence_off_night_fp2",
                 "to": ["off", "unavailable", "unknown"],
                 "for": {"minutes": "{{ [1, [60, late_night_timeout | int(1)] | min] | max + 1 }}"}}
    for tid in ("dog_window_dim", "dog_window_off"):
        assert ts[tid]["platform"] == "template"
    profiles = [("profile_day", "06:00:00"), ("profile_dinner", "time_dinner"),
                ("profile_toddler", "time_toddler"), ("profile_evening", "time_evening"),
                ("profile_night", "time_night")]
    for tid, at_ in profiles:
        assert plain(ts[tid]) == {"platform": "time", "at": at_, "id": tid}
    assert list(ts) == (expected_ids + ["presence_off_night_fp2"] + [t["id"] for t in rest]
                        + ["dog_window_dim", "dog_window_off"] + [t for t, _ in profiles] + NOTICE)
    assert len(bp["trigger"]) == len(ts)
    assert bp["mode"] == "restart"
    assert bp["max_exceeded"] == "silent"


# --- presence ----------------------------------------------------------------------------

@pytest.mark.parametrize("a,b,expected", [
    ("on", "off", True), ("off", "on", True), ("off", "off", False), ("unavailable", "unknown", False)])
def test_either_sensor_on_is_presence(bp, a, b, expected):
    assert state(bp, fp2=a, fp300=b)["is_presence_on"] is expected


@pytest.mark.parametrize("age,expected", [(300, "off"), (299, "update")])
def test_room_empty_after_presence_timeout(bp, age, expected):
    assert decide(bp, age=age) == expected


def test_one_sensor_on_keeps_room_occupied(bp):
    assert decide(bp, fp300="on", age=7200) == "update"
    assert decide(bp, fp2="on", age=7200) == "update"


@pytest.mark.parametrize("st", ["unavailable", "unknown"])
def test_dead_sensors_count_as_clear(bp, st):
    assert decide(bp, fp2=st, fp300=st, age=300) == "off"
    now = at("14:00:00")
    table = {FP2: _St("off", now - timedelta(seconds=300)), FP300: _St(st, now - timedelta(seconds=300)),
             LUX: _St("100", now), "light.a": _St("on", now), "light.b": _St("on", now)}
    assert decide(bp, table=table) == "off"


def test_missing_sensor_counts_as_clear(bp):
    """The 22-26 Nov 2026 bug: a renamed FP300 left no state object and blocked every off."""
    now = at("14:00:00")
    base = {LUX: _St("100", now), "light.a": _St("on", now), "light.b": _St("on", now)}
    table = {**base, FP2: _St("off", now - timedelta(seconds=300))}
    result = state(bp, table=table)
    assert result["missing_sensors"] == [FP300]
    assert result["decision"] == "off"
    assert decide(bp, table={**base, FP2: _St("off", now - timedelta(seconds=299))}) == "update"
    assert decide(bp, table=base) == "off"


def test_present_sensor_without_last_changed_keeps_room_occupied(bp):
    now = at("14:00:00")
    table = {FP2: _St("off", now - timedelta(seconds=900)), FP300: _NoLc(),
             LUX: _St("100", now), "light.a": _St("on", now), "light.b": _St("on", now)}
    assert decide(bp, table=table) == "update"


@pytest.mark.parametrize("empty", [[], "", None])
def test_empty_sensor_input_is_ignored(bp, empty):
    result = state(bp, presence_fp300=empty, fp2="off", age=300)
    assert result["presence_sensors"] == [FP2]
    assert result["missing_sensors"] == []
    assert result["decision"] == "off"
    assert state(bp, presence_fp300=empty, fp2="on")["is_presence_on"] is True


@pytest.mark.parametrize("tid", ["update_loop", "ha_start", "reload", "presence_off_long_fp2",
                                 "presence_off_short_fp300", "lux_high", "lux_low", "override_resume",
                                 "fp2_unknown_30m", ""])
def test_empty_room_turns_lit_lights_off_on_any_trigger(bp, tid):
    assert decide(bp, tid=tid, age=300) == "off"
    assert decide(bp, tid=tid, age=300, lights="off") == "none"


def test_late_window_shortens_the_timeout(bp):
    assert decide(bp, time="23:30:00", age=60) == "off"
    assert decide(bp, time="23:30:00", age=59) == "update"
    assert decide(bp, time="06:30:00", age=60) == "update"
    assert decide(bp, time="00:02:00", age=60) == "off"
    assert state(bp, time="23:30:00")["off_minutes"] == 1
    assert state(bp, time="14:00:00")["off_minutes"] == 5


@pytest.mark.parametrize("time,expected", [
    ("23:00:00", True), ("00:00:00", True), ("06:29:59", True),
    ("22:59:59", False), ("06:30:00", False), ("12:00:00", False)])
def test_window_edges_cross_midnight(bp, time, expected):
    assert window(bp, time) is expected


def test_window_start_equals_end_is_empty(bp):
    for time in ("23:00:00", "03:00:00", "12:00:00"):
        assert window(bp, time, "23:00:00", "23:00:00") is False


@pytest.mark.parametrize("time,expected", [
    ("01:00:00", True), ("04:59:59", True), ("00:30:00", False), ("05:00:00", False)])
def test_window_not_crossing_midnight(bp, time, expected):
    assert window(bp, time, "01:00:00", "05:00:00") is expected


@pytest.mark.parametrize("value,expected", [(0, 1), (1, 1), (60, 60), (61, 60), ("abc", 1)])
def test_late_night_timeout_clamped(bp, value, expected):
    templates = [_var_template(bp, "late_night_minutes")] + [
        triggers(bp)["presence_off_short_" + sensor]["for"]["minutes"] for sensor in ("fp2", "fp300")]
    assert templates == [CLAMP] * 3
    for template in templates:
        assert render(template, at("23:30:00"), late_night_timeout=value) == expected
    assert decide(bp, time="23:30:00", late_night_timeout=value, age=expected * 60) == "off"
    assert decide(bp, time="23:30:00", late_night_timeout=value, age=expected * 60 - 1) == "update"


# --- lux ---------------------------------------------------------------------------------

@pytest.mark.parametrize("lux,lux_age,tid,expected", [
    ("300", 600, "update_loop", "off"),     # stable above for lux_off_duration
    ("300", 599, "update_loop", "update"),  # not yet proven
    ("300", 0, "lux_high", "off"),          # the trigger itself proves the dwell
    ("250", 3600, "update_loop", "update"), # strictly above
    ("251", 0, "ha_start", "off"),
    ("251", 0, "reload", "off"),
    ("unavailable", 3600, "lux_high", "none"),  # no reading: no lux decision
])
def test_daylight_off_needs_dwell(bp, lux, lux_age, tid, expected):
    assert decide(bp, tid=tid, fp2="on", lux=lux, lux_age=lux_age) == expected


@pytest.mark.parametrize("lux,expected", [("174", "on"), ("175", "none"), ("200", "none"),
                                          ("unavailable", "on"), ("", "on")])
def test_presence_turns_on_only_when_dark(bp, lux, expected):
    assert decide(bp, tid="presence_on_fp2", fp2="on", lights="off", lux=lux) == expected
    assert decide(bp, tid="presence_on_fp300", fp300="on", lights="off", lux=lux) == expected


def test_lux_low_turns_on_only_with_presence(bp):
    assert decide(bp, tid="lux_low", fp2="on", lights="off", lux="100") == "on"
    assert decide(bp, tid="lux_low", lights="off", lux="100") == "none"


@pytest.mark.parametrize("tid", ["update_loop", "lux_high"])
def test_tick_never_turns_on(bp, tid):
    assert decide(bp, tid=tid, fp2="on", lights="off", lux="10") == "none"


@pytest.mark.parametrize("tid", ["ha_start", "reload"])
def test_restart_acts_on_current_lux_at_once(bp, tid):
    """HA drops numeric_state `for:` timers on restart/reload (Codex J2 P1)."""
    assert decide(bp, tid=tid, fp2="on", lights="off", lux="100") == "on"
    assert decide(bp, tid=tid, fp2="on", lights="off", lux="200") == "none"
    assert decide(bp, tid=tid, lights="off", lux="100") == "none"
    assert decide(bp, tid=tid, fp2="on", lights="on", lux="300", lux_age=0) == "off"
    assert decide(bp, tid=tid, fp2="on", lights="on", lux="200", lux_age=0) == "update"


def test_dead_band_keeps_the_current_state(bp):
    assert decide(bp, tid="update_loop", fp2="on", lights="on", lux="220") == "update"
    assert decide(bp, tid="presence_on_fp2", fp2="on", lights="off", lux="220") == "none"


def test_override_resume(bp):
    assert decide(bp, tid="override_resume", fp2="on", lights="off", lux="100") == "on"
    assert decide(bp, tid="override_resume", age=300) == "off"
    assert decide(bp, tid="override_resume", fp2="on", lights="off", lux="300") == "none"


def test_presence_on_with_lights_on_refreshes_profile(bp):
    assert decide(bp, tid="presence_on_fp300", fp300="on", lights="on") == "update"


def test_lux_reading(bp):
    assert state(bp, lux="unavailable")["current_lux"] is None
    assert state(bp, lux="123.4")["current_lux"] == 123.4
    assert state(bp, lux_age=42)["lux_age"] == 42
    now = at("14:00:00")
    assert render(_var_template(bp, "lux_age"), now, {}, sensor_lux=LUX) is None


def test_lights_on_is_any_target_light(bp):
    now = at("14:00:00")
    template = _var_template(bp, "lights_on")
    assert render(template, now, {"light.a": _St("off", now), "light.b": _St("on", now)},
                  all_target_lights=LIGHTS) is True
    assert render(template, now, {"light.a": _St("off", now)}, all_target_lights=LIGHTS) is False
    assert render(template, now, {}, all_target_lights=[]) is False


# --- actions -----------------------------------------------------------------------------

def test_light_branches_follow_the_decision(bp):
    assert len(bp["action"]) == 4
    branches = bp["action"][2]["choose"]
    assert [b["conditions"] for b in branches] == [
        [{"condition": "template", "value_template": "{{ decision == 'off' }}"}],
        [{"condition": "template", "value_template": "{{ decision == 'on' }}"}],
        [{"condition": "template", "value_template": "{{ decision == 'update' }}"}],
        [{"condition": "template", "value_template": "{{ decision == 'dim' }}"}],
    ]
    assert branches[0]["sequence"][1]["then"][0]["service"] == "light.turn_off"


def test_override_stops_everything_but_notices(bp):
    assert "stop" in bp["action"][0]["choose"][0]["sequence"][0]
    template = bp["action"][0]["choose"][0]["conditions"][0]["value_template"]
    for tid in NOTICE + ["presence_on_fp2", "update_loop", "ha_start"]:
        assert render(template, at("14:00:00"), {"input_boolean.override": _St("on", None)},
                      entity_override="input_boolean.override", trigger={"id": tid}) is (tid not in NOTICE)
        assert render(template, at("14:00:00"), entity_override=[], trigger={"id": tid}) is False


@pytest.mark.parametrize("targets,expected", [
    ([], []),
    (["bad", "light.on", "notify.Bad", "notify.mobile_app_martin_fold"], ["notify.mobile_app_martin_fold"]),
    (["notify.phone", "notify.phone"], ["notify.phone", "notify.phone"]),
    ("notify.phone", ["notify.phone"])])
def test_notify_list_filters_targets(bp, targets, expected):
    assert render(_var_template(bp, "notify_list"), at("14:00:00"), notify_targets=targets) == expected


def _notice(bp, tid, time="14:00:00", missing=()):
    branch = bp["action"][-1]["choose"][0]
    ctx = dict(trigger={"id": tid}, missing_sensors=list(missing),
               presence_fp2=FP2, presence_fp300=FP300)
    due = render(branch["conditions"][0]["value_template"], at(time), **ctx)
    step = branch["sequence"][0]["repeat"]["sequence"][0]
    message = render(step["data"]["message"], at(time), **ctx) if due else None
    return due, message


def test_offline_notice_for_either_sensor(bp):
    for tid in NOTICE:
        due, message = _notice(bp, tid)
        assert due is True
        sensor = FP2 if tid.startswith("fp2") else FP300
        other = FP300 if sensor == FP2 else FP2
        assert sensor in message and tid.split("_")[1] in message and "30 min" in message
        assert other in message


def test_missing_sensor_notice_hourly_on_the_tick(bp):
    due, message = _notice(bp, "update_loop", time="14:00:00", missing=[FP300])
    assert due is True
    assert FP300 in message and "missing" in message
    assert _notice(bp, "update_loop", time="14:05:00", missing=[FP300])[0] is False
    assert _notice(bp, "update_loop", time="14:00:00", missing=[])[0] is False
    assert _notice(bp, "presence_on_fp2", time="14:00:00", missing=[FP300])[0] is False


def test_notice_pushes_once_per_target(bp):
    branch = bp["action"][-1]["choose"][0]
    assert len(branch["sequence"]) == 1
    repeat = branch["sequence"][0]["repeat"]
    assert repeat["for_each"] == "{{ notify_list }}"
    step = repeat["sequence"][0]
    assert step["service"] == "{{ repeat.item }}"
    assert step["continue_on_error"] is True
    assert step["data"]["title"] == "Living Room Lights - presence sensor offline"


def test_night_profile_independent_of_window(bp):
    inputs = bp["blueprint"]["input"]
    ctx = {key: inputs[value.name]["default"] for key, value in bp["variables"].items()
           if hasattr(value, "name") and "default" in inputs[value.name]}
    night = _chain(bp, ["mode", "target_brightness"], at("22:30:00"), ctx)
    assert (night["mode"], night["target_brightness"]) == ("night", 20)
    assert window(bp, "22:30:00") is False
    assert _chain(bp, ["mode"], at("06:15:00"), ctx)["mode"] == "day"
    assert window(bp, "06:15:00") is True


def test_no_lux_guard_on_updates(bp, text):
    assert "threshold_on + 300" not in text


# --- J3: night window (D9-D11, D18, D19) --------------------------------------------------

def test_night_window_inputs(bp):
    inputs = bp["blueprint"]["input"]
    for key, value in (("fp300_ignore_start", "01:00:00"), ("fp300_ignore_end", "06:00:00")):
        assert inputs[key]["default"] == value
        assert inputs[key]["selector"] == {"time": None}
    keys = list(inputs)
    assert keys.index("fp300_ignore_start") == keys.index("late_night_end") + 1
    assert keys.index("fp300_ignore_end") == keys.index("fp300_ignore_start") + 1


@pytest.mark.parametrize("time,expected", [
    ("01:00:00", True), ("03:00:00", True), ("05:59:59", True),
    ("00:59:59", False), ("06:00:00", False), ("14:00:00", False)])
def test_dog_window_edges(bp, time, expected):
    assert state(bp, time=time)["in_dog_window"] is expected


def test_dog_window_start_equals_end_is_empty(bp):
    assert state(bp, time="03:00:00", dog_start="03:00:00", dog_end="03:00:00")["in_dog_window"] is False


def test_dog_window_can_cross_midnight(bp):
    assert state(bp, time="23:30:00", dog_start="23:00:00", dog_end="02:00:00")["in_dog_window"] is True
    assert state(bp, time="02:30:00", dog_start="23:00:00", dog_end="02:00:00")["in_dog_window"] is False


def test_fp300_ignored_in_window_only(bp):
    assert state(bp, time="03:00:00", fp300="on")["is_presence_on"] is False
    assert state(bp, time="03:00:00", fp2="on")["is_presence_on"] is True
    assert state(bp, time="00:30:00", fp300="on")["is_presence_on"] is True
    assert state(bp, time="06:00:00", fp300="on")["is_presence_on"] is True


def test_fp300_presence_on_cannot_turn_lights_on_in_window(bp):
    assert decide(bp, tid="presence_on_fp300", time="03:00:00", fp300="on", lights="off", lux="0") == "none"
    assert decide(bp, tid="presence_on_fp2", time="03:00:00", fp2="on", lights="off", lux="0") == "on"


@pytest.mark.parametrize("age,expected", [(59, "update"), (60, "dim"), (119, "dim"), (120, "off")])
def test_fp2_clear_dims_then_turns_off(bp, age, expected):
    assert decide(bp, time="03:00:00", age=age, lux="0") == expected
    assert decide(bp, time="03:00:00", age=age, fp300="on", lux="0") == expected


def _held_by_fp300(bp, time, **kw):
    now = at(time)
    table = {FP2: _St("off", now - timedelta(hours=2)), FP300: _St("on", now - timedelta(hours=2)),
             LUX: _St("0", now), "light.a": _St("on", now), "light.b": _St("on", now)}
    return state(bp, time=time, table=table, **kw)


@pytest.mark.parametrize("time,expected", [
    ("00:59:00", "update"), ("01:00:30", "update"), ("01:01:00", "dim"), ("01:01:59", "dim"), ("01:02:00", "off")])
def test_fp300_held_lights_dim_then_off_after_window_start(bp, time, expected):
    """The FP300 stops counting at the window start: dim after late_night_timeout, off a minute later."""
    assert _held_by_fp300(bp, time)["decision"] == expected


def test_fp300_cleared_before_window_counts_its_own_age(bp):
    now = at("01:00:30")
    table = {FP2: _St("off", now - timedelta(hours=2)), FP300: _St("off", now - timedelta(minutes=30)),
             LUX: _St("0", now), "light.a": _St("on", now), "light.b": _St("on", now)}
    assert state(bp, time="01:00:30", table=table)["decision"] == "off"


def test_fp2_return_restores_from_dim(bp):
    assert decide(bp, tid="presence_on_fp2", time="03:00:00", fp2="on", lux="0") == "update"


def test_late_window_outside_dog_window_unchanged(bp):
    assert decide(bp, time="23:30:00", age=60) == "off"
    assert decide(bp, time="06:15:00", age=60) == "off"
    assert decide(bp, time="00:30:00", age=60) == "off"


def test_missing_fp300_in_window(bp):
    now = at("03:00:00")
    table = {FP2: _St("off", now - timedelta(seconds=120)), LUX: _St("0", now),
             "light.a": _St("on", now), "light.b": _St("on", now)}
    assert state(bp, time="03:00:00", table=table)["decision"] == "off"


def test_dim_level_is_thirty_percent_of_target(bp):
    template = _var_template(bp, "dim_pct")
    for target, expected in ((29, 9), (100, 30), (2, 1), (1, 1)):
        assert render(template, at("03:00:00"), target_brightness=target) == expected
    branch = bp["action"][2]["choose"][3]
    services = [step["then"][0] for step in branch["sequence"][1:]]
    assert [s["service"] for s in services] == ["light.turn_on", "light.turn_on"]
    assert services[0]["data"]["brightness_pct"] == "{{ dim_pct }}"
    assert services[1]["data"]["brightness_pct"] == "{{ [1, (dim_pct * c_scale | float) | round(0) | int] | max }}"


@pytest.mark.parametrize("time,dim,off", [
    ("00:59:00", False, False), ("01:00:00", False, False), ("01:01:00", True, False),
    ("01:01:59", True, False), ("01:02:00", False, True), ("01:03:00", False, False), ("13:01:00", False, False)])
def test_dog_window_wake_triggers(bp, time, dim, off):
    ts = triggers(bp)
    ctx = dict(dog_start="01:00:00", dog_end="06:00:00", late_night_timeout=1)
    assert render(ts["dog_window_dim"]["value_template"], at(time), **ctx) is dim
    assert render(ts["dog_window_off"]["value_template"], at(time), **ctx) is off
    assert render(ts["dog_window_dim"]["value_template"], at("01:01:00"),
                  dog_start="01:00:00", dog_end="01:00:00", late_night_timeout=1) is False


@pytest.mark.parametrize("fp300", ["off", "unknown", "unavailable", "on"])
def test_fp300_changes_inside_window_do_not_reset_the_room(bp, fp300):
    """Codex J3 P1: an FP300 flip at 02:59 must not re-brighten a dimmed, FP2-empty room."""
    now = at("03:00:00")
    table = {FP2: _St("off", now - timedelta(seconds=90)), FP300: _St(fp300, now - timedelta(seconds=5)),
             LUX: _St("0", now), "light.a": _St("on", now), "light.b": _St("on", now)}
    assert state(bp, time="03:00:00", table=table)["decision"] == "dim"
    table[FP2] = _St("off", now - timedelta(seconds=120))
    assert state(bp, time="03:00:00", table=table)["decision"] == "off"


def test_window_end_does_not_turn_lights_on_for_a_held_fp300(bp):
    """By design (Codex J3 P1 #2 declined): at 06:00 a still-on FP300 is most likely the dog."""
    assert decide(bp, tid="update_loop", time="06:00:00", fp300="on", lights="off", lux="0") == "none"


# --- J4: manual changes (D6, D12, D20) ---------------------------------------------------

@pytest.mark.parametrize("gap,fp300,expected", [
    (3600, "off", "on"),   # fresh entry: room had been empty for the timeout
    (299, "off", "none"),  # the FP2 only blinked: lights were switched off by hand
    (3600, "on", "none"),  # the FP300 kept the room occupied
])
def test_manual_off_stays_off_until_the_room_was_empty(bp, gap, fp300, expected):
    assert decide(bp, tid="presence_on_fp2", fp2="on", fp300=fp300, lights="off", lux="0", gap=gap,
                  helper="off") == expected


@pytest.mark.parametrize("gap,fp300", [(3600, "off"), (299, "off"), (3600, "on")])
def test_our_own_off_always_relights_on_presence(bp, gap, fp300):
    """Codex J4 P1: after a daylight or timeout off (helper on) any presence relights."""
    assert decide(bp, tid="presence_on_fp2", fp2="on", fp300=fp300, lights="off", lux="0", gap=gap,
                  helper="on") == "on"


@pytest.mark.parametrize("gap,fp300", [(299, "off"), (3600, "on")])
def test_without_helper_presence_relights_as_before(bp, gap, fp300):
    assert decide(bp, tid="presence_on_fp2", fp2="on", fp300=fp300, lights="off", lux="0", gap=gap) == "on"


@pytest.mark.parametrize("tid", ["lux_low", "ha_start", "reload"])
def test_manual_off_survives_lux_low_and_restarts(bp, tid):
    """Codex J4 P1: these paths must not undo a manual off."""
    assert decide(bp, tid=tid, fp2="on", lights="off", lux="0", helper="off") == "none"
    assert decide(bp, tid=tid, fp2="on", lights="off", lux="0", helper="on") == "on"


def test_override_resume_still_relights_after_manual_off(bp):
    assert decide(bp, tid="override_resume", fp2="on", lights="off", lux="0", helper="off") == "on"


def test_manual_off_needs_lights_off_and_helper_off(bp):
    assert state(bp, lights="off", helper="off")["manual_off"] is True
    assert state(bp, lights="off", helper="on")["manual_off"] is False
    assert state(bp, lights="on", helper="off")["manual_off"] is False
    assert state(bp, lights="off")["manual_off"] is False


def test_fresh_entry_in_late_window_uses_its_timeout(bp):
    kw = dict(tid="presence_on_fp2", time="23:30:00", fp2="on", lights="off", lux="0", helper="off")
    assert decide(bp, gap=60, **kw) == "on"
    assert decide(bp, gap=59, **kw) == "none"


def test_fresh_entry_in_dog_window_ignores_the_fp300(bp):
    assert decide(bp, tid="presence_on_fp2", time="03:00:00", fp2="on", fp300="on",
                  lights="off", lux="0", gap=120, helper="off") == "on"


def test_missing_from_state_is_not_a_fresh_entry(bp):
    assert decide(bp, tid="presence_on_fp2", fp2="on", lights="off", lux="0", helper="off",
                  trigger={"id": "presence_on_fp2", "entity_id": FP2, "from_state": None}) == "none"


def test_auto_off_helper_input(bp):
    item = bp["blueprint"]["input"]["auto_off_helper"]
    assert item["default"] == []
    assert item["selector"] == {"entity": {"domain": "input_boolean"}}
    assert bp["variables"]["auto_off_helper"].name == "auto_off_helper"


def test_helper_bookkeeping_in_every_branch(bp):
    branches = bp["action"][2]["choose"]
    first = [b["sequence"][0]["then"][0]["service"] for b in branches]
    assert first == ["input_boolean.turn_on", "input_boolean.turn_off",
                     "input_boolean.turn_off", "input_boolean.turn_off"]
    assert branches[0]["sequence"][1]["then"][0]["service"] == "light.turn_off"


@pytest.mark.parametrize("tid", ["profile_day", "profile_dinner", "profile_toddler",
                                 "profile_evening", "profile_night"])
def test_profile_boundary_refreshes_lit_lights(bp, tid):
    assert decide(bp, tid=tid, fp2="on") == "update"
    assert decide(bp, tid=tid, fp2="on", lights="off") == "none"
    assert decide(bp, tid=tid, age=300) == "off"


def _lit(bri_pct, kelvin=2500, mode="color_temp"):
    return _St("on", at("14:00:00"), {"brightness": round(bri_pct * 2.55),
                                      "color_temp_kelvin": kelvin, "color_mode": mode})


def _update(bp, table, tid="update_loop", bulbs=("light.a",), ceiling=("light.c",), **kw):
    ctx = dict(hue_list_bulbs=list(bulbs), hue_list_ceiling=list(ceiling), target_brightness=50,
               ceiling_bri=30, target_kelvin=2500, dim_pct=15, c_scale=0.6, target_effect="none",
               trigger={"id": tid})
    ctx.update(kw)
    out = _chain(bp, ["force_update", "update_bulbs", "update_ceiling"], at("14:00:00"), {**ctx, "table": table})
    return out["update_bulbs"], out["update_ceiling"]


def test_update_skips_manually_changed_lights(bp):
    table = {"light.a": _lit(50), "light.b": _lit(80), "light.c": _lit(30), "light.d": _lit(30, 3500)}
    bulbs, ceiling = _update(bp, table, bulbs=("light.a", "light.b"), ceiling=("light.c", "light.d"))
    assert bulbs == ["light.a"]
    assert ceiling == ["light.c"]


@pytest.mark.parametrize("bri,kelvin,mode,kept", [
    (54, 2500, "color_temp", True),    # within 5 %
    (56, 2500, "color_temp", False),
    (50, 2640, "color_temp", True),    # within 150 K (day-mode drift between ticks)
    (50, 2660, "color_temp", False),
    (15, 2500, "color_temp", True),    # our own night dim level
    (50, 2500, "xy", False),           # someone picked a colour
    (50, None, "color_temp", True),    # no kelvin reported: brightness decides
])
def test_manual_tolerance(bp, bri, kelvin, mode, kept):
    bulbs, _ = _update(bp, {"light.a": _lit(bri, kelvin, mode)}, ceiling=())
    assert bulbs == (["light.a"] if kept else [])


def test_off_lights_are_not_updated(bp):
    table = {"light.a": _St("off", at("14:00:00")), "light.c": _lit(30)}
    assert _update(bp, table) == ([], ["light.c"])


def test_profile_boundary_overrides_manual_changes(bp):
    table = {"light.a": _lit(90), "light.c": _lit(70, 4000, "xy")}
    for tid in ("profile_dinner", "profile_day"):
        assert _update(bp, table, tid=tid) == (["light.a"], ["light.c"])
    assert _update(bp, table, tid="presence_on_fp2") == ([], [])


def test_update_branch_targets_the_filtered_lists(bp):
    steps = bp["action"][2]["choose"][2]["sequence"][1:]
    assert steps[0]["if"][0]["value_template"] == "{{ update_bulbs | count > 0 }}"
    assert steps[0]["then"][0]["target"]["entity_id"] == "{{ update_bulbs }}"
    assert steps[1]["if"][0]["value_template"] == "{{ update_ceiling | count > 0 }}"
    ceiling_targets = [c["sequence"][0]["target"]["entity_id"] for c in steps[1]["then"][0]["choose"]]
    assert ceiling_targets == ["{{ update_ceiling }}", "{{ update_ceiling }}"]


def test_update_lists_render_after_target_effect(bp):
    """Codex J4 P0: HA renders variables in order; the lists must not read later names."""
    step = next(a for a in bp["action"] if "variables" in a)["variables"]
    names = list(step)
    for later in ("update_bulbs", "update_ceiling"):
        assert names.index("target_effect") < names.index(later)
        assert names.index("dim_pct") < names.index(later)


def test_bulb_colour_counts_as_manual_even_with_an_effect(bp):
    """Codex J4 P2: effects only run on the ceiling, so a bulb in xy was changed by hand."""
    table = {"light.a": _lit(50, 2500, "xy"), "light.c": _lit(30, 2500, "xy")}
    assert _update(bp, table, target_effect="candlelight") == ([], ["light.c"])
