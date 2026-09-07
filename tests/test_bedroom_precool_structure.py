"""Structural pins for bedroom_precool.yaml (Bedroom Sleep Pre-Cool v1.0.1) and its
deployed instance configs.

Run: cd ~/AI/projects/Blueprints_Home && \
     ~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q

Regression background (hotfix 2026-09-07): HA re-parses `variables:` results between
steps (literal_eval), so a template that renders a datetime hands the NEXT step a plain
string. `turn_on_dt.strftime(...)` therefore raised on every 1-minute run and the
automation never reached a climate command. Instants must cross a variables boundary
as UNIX timestamps (floats survive the round-trip) and be formatted with
`timestamp_custom` at the point of use.
"""
import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
BP_PATH = ROOT / "bedroom_precool.yaml"
LG_PATH = ROOT / "lg_ac_climate.yaml"
PRECOOL_INSTANCE = ROOT / "deploy" / "bedroom_precool_1779553673971.json"
LG_INSTANCE = ROOT / "deploy" / "lg_ac_climate_1775578219942.json"


class _Input:
    def __init__(self, name):
        self.name = name


class HassLoader(yaml.SafeLoader):
    pass


HassLoader.add_constructor(
    "!input", lambda loader, node: _Input(loader.construct_scalar(node))
)


@pytest.fixture(scope="module")
def text():
    return BP_PATH.read_text()


@pytest.fixture(scope="module")
def bp(text):
    return yaml.load(text, Loader=HassLoader)


def _inputs(path):
    with path.open() as fh:
        return yaml.load(fh, Loader=HassLoader)["blueprint"]["input"]


# --- the bug class itself -------------------------------------------------------------

def test_no_method_call_on_a_bare_variable_that_crossed_a_variables_boundary(text):
    """`.strftime(` may only follow an expression result (`now()`, `(...)`), never a bare
    variable name: variables are strings on the far side of a `variables:` step."""
    offenders = re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\.strftime\(", text)
    assert offenders == [], f"bare-variable .strftime() calls: {offenders}"


def test_instants_are_carried_as_timestamps_not_datetimes(text):
    assert not re.search(r"\b\w+_dt\b", text), "datetime-typed variables must not cross steps"
    assert re.search(r"bedtime_ts:\s*>-\s*\n.*\n\s*\{\{\s*as_timestamp\(", text)
    assert re.search(r'turn_on_ts:\s*"\{\{\s*as_timestamp\(today_at\(bedtime\)', text)
    assert "turn_on_ts | float | timestamp_custom('%H:%M:%S')" in text
    assert "as_timestamp(fdt) <= bedtime_ts | float" in text


def test_version_bumped(bp):
    assert bp["blueprint"]["name"].endswith("v1.0.1")
    assert "**Version: 1.0.1**" in bp["blueprint"]["description"]


# --- deployed instance configs ---------------------------------------------------------

def test_precool_instance_keys_exist_and_weather_supports_hourly_forecasts():
    inst = json.loads(PRECOOL_INSTANCE.read_text())
    inputs = _inputs(BP_PATH)
    assert inst["use_blueprint"]["path"] == "leviemartin/bedroom_precool.yaml"
    unknown = set(inst["use_blueprint"]["input"]) - set(inputs)
    assert not unknown, f"instance keys absent from blueprint schema: {unknown}"
    # weather.openweathermap reports supported_features None in this HA (no forecast
    # service); weather.home_sm (Met.no) supports hourly forecasts (features 3).
    assert inst["use_blueprint"]["input"]["weather_entity"] == "weather.home_sm"
    assert inst["alias"].endswith("v1.0.1")


def test_lg_ac_instance_escalation_stages_are_ordered_and_in_range():
    inst = json.loads(LG_INSTANCE.read_text())
    inputs = _inputs(LG_PATH)
    i = inst["use_blueprint"]["input"]
    unknown = set(i) - set(inputs)
    assert not unknown, f"instance keys absent from blueprint schema: {unknown}"
    s1, s2 = i["escalation_stage_1_minutes"], i["escalation_stage_2_minutes"]
    # target_fan tests stage 2 before stage 1 (elif chain): s2 <= s1 makes the mid
    # stage unreachable and sends the fan to max after s2 minutes.
    assert s1 < s2, f"stage 1 ({s1}) must fire before stage 2 ({s2})"
    for key, val in (("escalation_stage_1_minutes", s1), ("escalation_stage_2_minutes", s2)):
        sel = inputs[key]["selector"]["number"]
        assert sel["min"] <= val <= sel["max"], f"{key}={val} outside selector range"
