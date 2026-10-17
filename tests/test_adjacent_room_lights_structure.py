"""Contract tests; Home Assistant owns the state-trigger timers."""
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml
from jinja2 import StrictUndefined

from test_bedroom_precool_structure import HassLoader, TZ, _env, _reparse, _var_template

ROOT = Path(__file__).resolve().parent.parent
A, B = "binary_sensor.attic_main", "binary_sensor.attic_stairs"
NOW = datetime(2026, 10, 17, 14, tzinfo=TZ)
CHECKS = ("is_motion_on", "clear_stage1", "clear_stage2", "clear_off", "all_dead_30")

# Literal v1.0.0 formulas: independent of git and the version under test.
EXPECTED = yaml.safe_load("""
current_lux: "{{ states(sensor_lux) | float(0) if lux_enabled else 0 }}"
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
    def __init__(self, state, last_changed):
        self.state, self.last_changed = state, last_changed


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

    env.globals.update(states=States(), is_state=is_state, timedelta=timedelta)
    env.tests["is_state"] = is_state
    return env


def render(bp, name, now, table, **ctx):
    values = dict(sensor_motion=[A, B], mins_stage1=2, mins_stage2=4, mins_off=5)
    values.update(ctx)
    env = _strict_env(now, table)
    for key in CHECKS:
        values[key] = _reparse(
            env.from_string(_var_template(bp, key)).render(**values).strip()
        )
        if key == name:
            return values[key]
    raise KeyError(name)


def table(a_state, a_age, b_state, b_age):
    return {
        A: _St(a_state, NOW - timedelta(minutes=a_age)),
        B: _St(b_state, NOW - timedelta(minutes=b_age)),
    }


def test_version(bp):
    assert bp["blueprint"]["name"].endswith("v2.0.0")
    assert "**Version: 2.0.0" in bp["blueprint"]["description"]


def test_required_multiple_motion_input(bp, text):
    inputs = bp["blueprint"]["input"]
    item = inputs["motion_sensors"]
    assert item["selector"] == {
        "entity": {"domain": "binary_sensor", "device_class": "motion", "multiple": True}
    }
    assert "default" not in item
    assert "motion_sensor" not in inputs
    assert not re.search(r"!input motion_sensor\b(?!s)", text)
    assert bp["variables"]["sensor_motion"].name == "motion_sensors"


def test_triggers_and_timers(bp):
    triggers = bp["trigger"]
    assert [t["id"] for t in triggers] == [
        "motion_on", "stage_1", "stage_2", "stage_off",
        "update_loop", "sensor_watchdog", "sensor_watchdog",
    ]
    for trigger, state in zip(
        triggers, ("on", "off", "off", "off", None, "unavailable", "unknown")
    ):
        if state is None:
            assert trigger == {
                "platform": "time_pattern", "minutes": "/5", "id": "update_loop"
            }
        else:
            assert trigger["platform"] == "state"
            assert trigger["entity_id"].name == "motion_sensors"
            assert trigger["to"] == state
    for index, suffix, default, variable in (
        (1, "stage1", 5, "mins_stage1"),
        (2, "stage2", 10, "mins_stage2"),
        (3, "off", 15, "mins_off"),
    ):
        name = "time_to_" + suffix
        assert triggers[index]["for"]["minutes"].name == name
        assert bp["variables"][variable].name == name
        assert bp["blueprint"]["input"][name]["default"] == default
    assert all(t["for"] == {"minutes": 30} for t in triggers[5:])
    assert bp["mode"] == "restart"
    assert bp["max_exceeded"] == "silent"


@pytest.mark.parametrize("name", EXPECTED)
def test_v1_formulas_unchanged(bp, name):
    assert _var_template(bp, name) == EXPECTED[name]


def test_branch_guards(bp):
    branches = bp["action"][2]["choose"]
    assert branches[0]["conditions"] == [{
        "condition": "or",
        "conditions": [
            {"condition": "and", "conditions": [
                {"condition": "trigger", "id": "stage_off"},
                {"condition": "template", "value_template": "{{ clear_off }}"},
            ]},
            {"condition": "and", "conditions": [
                {"condition": "trigger", "id": "sensor_watchdog"},
                {"condition": "template",
                 "value_template": "{{ clear_off or all_dead_30 }}"},
            ]},
        ],
    }]
    for index, tid, variable in (
        (1, "stage_1", "clear_stage1"), (2, "stage_2", "clear_stage2"),
        (3, "motion_on", "is_motion_on"),
    ):
        conditions = branches[index]["conditions"]
        assert conditions[0] == {"condition": "trigger", "id": tid}
        assert {"condition": "template",
                "value_template": "{{ " + variable + " }}"} in conditions
    assert {"condition": "template",
            "value_template": "{{ not lux_enabled or current_lux < threshold_on }}"} in branches[3]["conditions"]


@pytest.mark.parametrize("name,a_state,a_age,b_state,b_age,expected", [
    ("is_motion_on", "on", 0, "off", 6, True),
    ("is_motion_on", "off", 6, "on", 0, True),
    ("is_motion_on", "off", 6, "off", 6, False),
    ("clear_stage1", "off", 6, "on", 0, False),
    ("clear_off", "off", 6, "on", 0, False),
    ("clear_stage1", "off", 6, "off", 1, False),
    ("clear_stage1", "off", 6, "off", 2, True),
    ("clear_stage2", "off", 6, "off", 3, False),
    ("clear_stage2", "off", 6, "off", 4, True),
    ("clear_off", "unavailable", 10, "off", 5, True),
    ("all_dead_30", "unavailable", 30, "on", 0, False),
    ("all_dead_30", "unavailable", 30, "unknown", 31, True),
    ("all_dead_30", "unavailable", 30, "unknown", 29, False),
    ("clear_off", "unknown", 5, "off", 5, True),
    ("all_dead_30", "unknown", 30, "unknown", 30, True),
    ("clear_stage1", "off", -1, "off", 6, False),
])
def test_sensor_timing(bp, name, a_state, a_age, b_state, b_age, expected):
    assert render(bp, name, NOW, table(a_state, a_age, b_state, b_age)) is expected


@pytest.mark.parametrize("name,expected", [
    ("clear_stage1", True), ("clear_stage2", False), ("clear_off", False),
])
def test_single_sensor_with_v1_defaults(bp, name, expected):
    assert render(
        bp, name, NOW, table("off", 5, "on", 0), sensor_motion=[A],
        mins_stage1=5, mins_stage2=10, mins_off=15,
    ) is expected


@pytest.mark.parametrize("name", CHECKS[1:])
@pytest.mark.parametrize("sensors", [[A, B], []])
def test_missing_or_empty_sensors_are_not_clear(bp, name, sensors):
    assert render(
        bp, name, NOW, {A: _St("off", NOW - timedelta(hours=1))},
        sensor_motion=sensors,
    ) is False


def test_duplicate_sensor_is_harmless(bp):
    states = table("off", 5, "on", 0)
    for name in CHECKS:
        assert render(bp, name, NOW, states, sensor_motion=[A, A]) == render(
            bp, name, NOW, states, sensor_motion=[A]
        )


@pytest.mark.parametrize("b_state,b_age,expected", [
    ("off", 6, True), ("off", 1, False), ("on", 0, False),
    ("unknown", 31, True),
])
def test_watchdog_arm(bp, b_state, b_age, expected):
    states = table("unavailable", 30, b_state, b_age)
    values = {
        name: render(bp, name, NOW, states)
        for name in ("clear_off", "all_dead_30")
    }
    arm = bp["action"][2]["choose"][0]["conditions"][0]["conditions"][1]
    assert arm["condition"] == "and"
    template = arm["conditions"][1]["value_template"]
    assert _reparse(_strict_env(NOW, states).from_string(template).render(**values)) is expected
