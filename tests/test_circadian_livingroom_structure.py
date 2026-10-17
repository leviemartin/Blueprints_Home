"""Contract tests; HA owns state-trigger for timers (not simulated here)."""
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml
from jinja2 import StrictUndefined, UndefinedError

from test_bedroom_precool_structure import HassLoader, TZ, _env, _reparse, _var_template

ROOT = Path(__file__).resolve().parent.parent
FP2, FP300 = "binary_sensor.fp2", "binary_sensor.fp300"
NOTICE = ["fp300_unavailable_30m", "fp300_unknown_30m"]
CLAMP = "{{ [1, [60, late_night_timeout | int(1)] | min] | max }}"
OFF_CHAIN = ["late_night_minutes", "in_late_window", "presence_off_ok"]


@pytest.fixture
def text():
    return (ROOT / "circadian_livingroom.yaml").read_text()


@pytest.fixture
def bp(text):
    return yaml.load(text, Loader=HassLoader)


class _St:
    def __init__(self, state, last_changed):
        self.state, self.last_changed = state, last_changed


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

    states = States()

    def is_state(entity, state):
        need_str(entity)
        return entity in table and table[entity].state == state

    env.globals.update(states=states, is_state=is_state)
    return env


def render(template, now, table=None, **ctx):
    return _reparse(_strict_env(now, table or {}).from_string(template).render(**ctx).strip())


def _chain(bp, names, now, ctx):
    ctx = dict(ctx)
    table = ctx.pop("table", {})
    for name in names:
        ctx[name] = render(_var_template(bp, name), now, table, **ctx)
    return ctx


def off(bp, tid="presence_off_long_fp2", time="14:00:00", age=300,
        state="off", table=None, **changes):
    now = at(time)
    ctx = dict(presence_fp2=FP2, presence_fp300=FP300, presence_timeout=5,
               late_night_timeout=1, late_night_start="23:00:00",
               late_night_end="06:30:00", trigger={"id": tid},
               table=table if table is not None else {
                   FP2: _St(state, now - timedelta(seconds=age)),
                   FP300: _St(state, now - timedelta(seconds=age))})
    ctx.update(changes)
    return _chain(bp, OFF_CHAIN, now, ctx)["presence_off_ok"]


def window(bp, time, start="23:00:00", end="06:30:00"):
    return render(_var_template(bp, "in_late_window"), at(time),
                  late_night_start=start, late_night_end=end)


def triggers(bp):
    return {t["id"]: t for t in bp["trigger"]}


def test_the_fakes_are_strict():
    env = _strict_env(at("14:00:00"), {})
    for call in (lambda: env.globals["is_state"]([], "on"),
                 lambda: env.globals["states"]([]),
                 lambda: env.globals["states"][[]]):
        with pytest.raises(TypeError):
            call()
    with pytest.raises(UndefinedError):
        env.from_string("{{ missing }}").render()


def test_version_is_3_0_0(bp):
    assert bp["blueprint"]["name"].endswith("v3.0.0")
    assert "**Version: 3.0.0" in bp["blueprint"]["description"]


def test_presence_inputs_replace_presence_entity(bp, text):
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


def test_notify_targets_input(bp):
    item = bp["blueprint"]["input"]["notify_targets"]
    assert item["default"] == []
    assert item["selector"] == {"text": {"multiple": True}}


def test_inputs_reach_templates(bp):
    for name in ("presence_fp2", "presence_fp300", "presence_timeout",
                 "late_night_timeout", "late_night_start", "late_night_end", "notify_targets"):
        assert bp["variables"][name].name == name
    assert bp["trigger_variables"]["late_night_timeout"].name == "late_night_timeout"


def test_trigger_table(bp):
    ts = triggers(bp)
    expected_ids = []
    for prefix in ("presence_on", "presence_off_long", "presence_off_short"):
        for sensor in ("fp2", "fp300"):
            tid = prefix + "_" + sensor
            expected_ids.append(tid)
            t = dict(ts[tid])
            assert t.pop("entity_id").name == "presence_" + sensor
            expected = {"platform": "state", "id": tid, "to": "on"}
            if prefix != "presence_on":
                expected["to"] = ["off", "unavailable", "unknown"]
                minutes = t["for"]["minutes"]
                if prefix == "presence_off_long":
                    assert minutes.name == "presence_timeout"
                    t["for"] = {"minutes": "presence_timeout"}
                    minutes = "presence_timeout"
                else:
                    assert minutes == CLAMP
                expected["for"] = {"minutes": minutes}
            assert t == expected
    unchanged = [
        {"platform": "time_pattern", "minutes": "/5", "id": "update_loop"},
        {"platform": "numeric_state", "entity_id": "illuminance_entity",
         "above": "lux_off_threshold", "for": {"minutes": "lux_off_duration"}, "id": "lux_high"},
        {"platform": "numeric_state", "entity_id": "illuminance_entity",
         "below": "lux_on_threshold", "id": "lux_low"},
        {"platform": "state", "entity_id": "override_entity", "to": "off", "id": "override_resume"},
    ]

    def plain(value):
        if hasattr(value, "name"):
            return value.name
        if isinstance(value, dict):
            return {k: plain(v) for k, v in value.items()}
        return value

    for expected in unchanged:
        assert plain(ts[expected["id"]]) == expected
    assert list(ts) == expected_ids + [t["id"] for t in unchanged] + NOTICE
    assert len(bp["trigger"]) == len(ts)
    assert bp["mode"] == "restart"
    assert bp["max_exceeded"] == "silent"


@pytest.mark.parametrize("a,b,expected", [
    ("on", "off", True), ("off", "on", True),
    ("off", "off", False), ("unavailable", "unknown", False)])
def test_either_sensor_on_turns_lights_on(bp, a, b, expected):
    result = render(_var_template(bp, "is_presence_on"), at("14:00:00"),
                    {FP2: _St(a, None), FP300: _St(b, None)},
                    presence_fp2=FP2, presence_fp300=FP300)
    assert result is expected
    branch = bp["action"][2]["choose"][1]
    assert branch["conditions"][0]["value_template"] == "{{ is_presence_on }}"
    assert branch["conditions"][1]["conditions"][0]["conditions"][0] == {
        "condition": "trigger", "id": ["presence_on_fp2", "presence_on_fp300"]}


@pytest.mark.parametrize("empty", [[], "", None])
@pytest.mark.parametrize("side,other,tid", [
    ("presence_fp300", FP2, "presence_off_long_fp2"),
    ("presence_fp2", FP300, "presence_off_long_fp300")])
def test_empty_side_counts_as_clear(bp, empty, side, other, tid):
    ctx = dict(presence_fp2=FP2, presence_fp300=FP300)
    ctx[side] = empty
    for state in ("on", "off"):
        assert render(_var_template(bp, "is_presence_on"), at("14:00:00"),
                      {other: _St(state, None)}, **ctx) is (state == "on")
    assert off(bp, tid=tid, **{side: empty}) is True


@pytest.mark.parametrize("tid", ["presence_off_long_fp2", "presence_off_long_fp300"])
@pytest.mark.parametrize("age,state,expected", [(300, "off", True), (299, "off", False), (600, "on", False)])
def test_off_needs_other_clear_for_presence_timeout(bp, tid, age, state, expected):
    assert off(bp, tid=tid, age=age, state=state) is expected


@pytest.mark.parametrize("state", ["unavailable", "unknown"])
def test_both_unavailable_or_unknown_count_as_clear(bp, state):
    assert off(bp, state=state, age=360) is True
    assert render(_var_template(bp, "is_presence_on"), at("14:00:00"),
                  {FP2: _St(state, None), FP300: _St(state, None)},
                  presence_fp2=FP2, presence_fp300=FP300) is False


@pytest.mark.parametrize("st", [_St("off", None), _NoLc(), None])
def test_other_last_changed_missing_or_none_fails(bp, st):
    assert off(bp, table={FP300: st} if st is not None else {}) is False


def test_short_timer_only_inside_window(bp):
    for sensor in ("fp2", "fp300"):
        tid = "presence_off_short_" + sensor
        assert off(bp, tid, age=7200) is False
        assert off(bp, tid, time="23:30:00", age=60) is True
        assert off(bp, tid, time="23:30:00", age=59) is False
        assert off(bp, tid, time="06:30:00", age=60) is False
        assert off(bp, "presence_off_long_" + sensor, time="23:30:00") is True


@pytest.mark.parametrize("time,expected", [
    ("23:00:00", True), ("00:00:00", True), ("06:29:59", True),
    ("22:59:59", False), ("06:30:00", False), ("12:00:00", False)])
def test_window_edges_cross_midnight(bp, time, expected):
    assert window(bp, time) is expected


def test_window_start_equals_end_is_empty(bp):
    for time in ("23:00:00", "03:00:00", "12:00:00"):
        assert window(bp, time, "23:00:00", "23:00:00") is False
    assert off(bp, "presence_off_short_fp2", time="23:30:00",
               late_night_end="23:00:00") is False


@pytest.mark.parametrize("time,expected", [
    ("01:00:00", True), ("04:59:59", True), ("00:30:00", False),
    ("05:00:00", False), ("23:30:00", False)])
def test_window_not_crossing_midnight(bp, time, expected):
    assert window(bp, time, "01:00:00", "05:00:00") is expected


def test_off_across_midnight(bp):
    assert off(bp, time="00:02:00", age=300) is True
    assert off(bp, "presence_off_short_fp2", time="00:00:30", age=90) is True


@pytest.mark.parametrize("value,expected", [(0, 1), (1, 1), (60, 60), (61, 60), ("abc", 1)])
def test_late_night_timeout_clamped(bp, value, expected):
    templates = [_var_template(bp, "late_night_minutes")] + [
        triggers(bp)["presence_off_short_" + sensor]["for"]["minutes"]
        for sensor in ("fp2", "fp300")]
    assert templates == [CLAMP] * 3
    for template in templates:
        assert render(template, at("23:30:00"), late_night_timeout=value) == expected
    assert off(bp, "presence_off_short_fp2", time="23:30:00",
               late_night_timeout=value, age=expected * 60) is True
    assert off(bp, "presence_off_short_fp2", time="23:30:00",
               late_night_timeout=value, age=expected * 60 - 1) is False


def test_non_off_triggers_never_turn_off(bp):
    for tid in ["presence_on_fp2", "presence_on_fp300", "update_loop", "lux_high", ""] + NOTICE:
        assert off(bp, tid) is False
    assert bp["action"][2]["choose"][0]["conditions"] == [{
        "condition": "or", "conditions": [
            {"condition": "template", "value_template": "{{ presence_off_ok }}"},
            {"condition": "trigger", "id": "lux_high"}]}]


@pytest.mark.parametrize("targets,expected", [
    ([], []),
    (["bad", "light.on", "notify.Bad", "notify.mobile_app_martin_fold"],
     ["notify.mobile_app_martin_fold"]),
    (["notify.phone", "notify.phone"], ["notify.phone", "notify.phone"]),
    ("notify.phone", ["notify.phone"])])
def test_notify_list_filters_targets(bp, targets, expected):
    assert render(_var_template(bp, "notify_list"), at("14:00:00"),
                  notify_targets=targets) == expected


def test_fp300_notice_one_call_per_target(bp):
    ts = triggers(bp)
    for tid, state in zip(NOTICE, ("unavailable", "unknown")):
        t = dict(ts[tid])
        assert t.pop("entity_id").name == "presence_fp300"
        assert t == {"platform": "state", "to": state, "for": {"minutes": 30}, "id": tid}
    branch = bp["action"][-1]["choose"][0]
    condition = branch["conditions"][0]["value_template"]
    for tid in list(ts) + [""]:
        assert render(condition, at("14:00:00"), trigger={"id": tid}) is (tid in NOTICE)
    assert len(branch["sequence"]) == 1
    repeat = branch["sequence"][0]["repeat"]
    assert repeat["for_each"] == "{{ notify_list }}"
    assert len(repeat["sequence"]) == 1
    step = repeat["sequence"][0]
    assert step["service"] == "{{ repeat.item }}"
    assert step["continue_on_error"] is True
    assert step["data"]["title"] == "Living Room Lights - FP300 offline"
    for tid, state in zip(NOTICE, ("unavailable", "unknown")):
        message = render(step["data"]["message"], at("14:00:00"),
                         presence_fp300=FP300, trigger={"id": tid})
        assert all(s in message for s in (FP300, state, "for 30 min", "FP2"))
    for targets, expected in [([], []), (["notify.phone", "notify.phone", "bad"],
                                         ["notify.phone", "notify.phone"])]:
        ctx = _chain(bp, ["notify_list"], at("14:00:00"), {"notify_targets": targets})
        items = render(repeat["for_each"], at("14:00:00"), **ctx)
        assert [render(step["service"], at("14:00:00"), repeat={"item": item})
                for item in items] == expected


def test_notice_runs_after_light_calls_and_through_override(bp):
    assert len(bp["action"]) == 4
    assert "stop" in bp["action"][0]["choose"][0]["sequence"][0]
    assert len(bp["action"][2]["choose"]) == 3
    template = bp["action"][0]["choose"][0]["conditions"][0]["value_template"]
    for tid in NOTICE + ["presence_on_fp2", "presence_off_long_fp2"]:
        assert render(template, at("14:00:00"), {"input_boolean.override": _St("on", None)},
                      entity_override="input_boolean.override", trigger={"id": tid}) is (tid not in NOTICE)
        assert render(template, at("14:00:00"), entity_override=[], trigger={"id": tid}) is False


def test_night_profile_independent_of_window(bp):
    inputs = bp["blueprint"]["input"]
    ctx = {key: inputs[value.name]["default"] for key, value in bp["variables"].items()
           if hasattr(value, "name") and "default" in inputs[value.name]}
    night = _chain(bp, ["mode", "target_brightness"], at("22:30:00"), ctx)
    assert (night["mode"], night["target_brightness"]) == ("night", 20)
    assert window(bp, "22:30:00") is False
    assert _chain(bp, ["mode"], at("06:15:00"), ctx)["mode"] == "day"
    assert window(bp, "06:15:00") is True


def test_lux_unavailable_not_newly_broken(bp):
    assert render(_var_template(bp, "current_lux"), at("14:00:00"),
                  {"sensor.lux": _St("unavailable", None)}, sensor_lux="sensor.lux") == 0.0
    for key, expected in (("lux_on_threshold", 150), ("lux_off_threshold", 400), ("lux_off_duration", 5)):
        assert bp["blueprint"]["input"][key]["default"] == expected
    for tid in ("lux_high", "lux_low"):
        assert triggers(bp)[tid]["entity_id"].name == "illuminance_entity"
    assert bp["variables"]["sensor_lux"].name == "illuminance_entity"
