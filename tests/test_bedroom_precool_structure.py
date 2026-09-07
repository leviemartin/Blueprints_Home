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


# --- rendered behaviour (board 20260907-163522 R1-01: realized outputs, not name pins) ---

import ast
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from jinja2 import Environment

TZ = ZoneInfo("Europe/Amsterdam")


def _var_template(bp, name):
    """Return the template string of an action-level `variables:` key."""
    for step in bp.get("actions") or bp.get("action") or []:
        if isinstance(step, dict) and name in (step.get("variables") or {}):
            return step["variables"][name]
    raise KeyError(name)


def _reparse(rendered):
    """What HA does to a rendered variables value before the next step sees it."""
    try:
        return ast.literal_eval(rendered)
    except (ValueError, SyntaxError):
        return rendered


def _env(now):
    env = Environment()
    env.filters["float"] = lambda v, d=0.0: float(v) if str(v).strip() not in ("", "None") else d
    env.filters["timestamp_custom"] = (
        lambda ts, fmt="%Y-%m-%d %H:%M:%S", local=True: datetime.fromtimestamp(float(ts), tz=TZ).strftime(fmt)
    )
    env.globals["now"] = lambda: now
    env.globals["timedelta"] = timedelta
    env.globals["as_timestamp"] = lambda d: d.timestamp() if hasattr(d, "timestamp") else float(d)
    env.globals["as_datetime"] = lambda s: datetime.fromisoformat(s) if isinstance(s, str) else s
    env.globals["today_at"] = lambda hhmmss: datetime.combine(now.date(), time.fromisoformat(hhmmss), tzinfo=TZ)
    return env


def _render(bp, name, now, **ctx):
    return _env(now).from_string(_var_template(bp, name)).render(**ctx).strip()


def test_rendered_turn_on_tod_survives_the_variables_boundary(bp):
    now = datetime(2026, 9, 7, 18, 32, tzinfo=TZ)
    ts = _reparse(_render(bp, "turn_on_ts", now, bedtime="21:30:00", lead=194))
    assert isinstance(ts, float), "turn_on_ts must re-parse to a float, not a string"
    assert ts == datetime(2026, 9, 7, 18, 16, tzinfo=TZ).timestamp()
    # the NEXT step receives the re-parsed value (this is where the old .strftime crashed)
    tod = _render(bp, "turn_on_tod", now, turn_on_ts=ts)
    assert tod == "18:16:00"
    # and it still works if the boundary hands over the raw string form
    assert _render(bp, "turn_on_tod", now, turn_on_ts=str(ts)) == "18:16:00"


def test_rendered_bedtime_ts_rolls_to_tomorrow_after_bedtime(bp):
    before = datetime(2026, 9, 7, 18, 0, tzinfo=TZ)
    after = datetime(2026, 9, 7, 23, 0, tzinfo=TZ)
    ts_before = _reparse(_render(bp, "bedtime_ts", before, bedtime="21:30:00"))
    ts_after = _reparse(_render(bp, "bedtime_ts", after, bedtime="21:30:00"))
    assert isinstance(ts_before, float) and isinstance(ts_after, float)
    assert ts_before == datetime(2026, 9, 7, 21, 30, tzinfo=TZ).timestamp()
    assert ts_after == datetime(2026, 9, 8, 21, 30, tzinfo=TZ).timestamp()


def test_rendered_forecast_window_filters_by_reparsed_bedtime_ts(bp):
    now = datetime(2026, 9, 7, 18, 0, tzinfo=TZ)
    bedtime_ts = _reparse(_render(bp, "bedtime_ts", now, bedtime="21:30:00"))
    forecast = [
        {"datetime": "2026-09-07T17:00:00+02:00", "temperature": 25.0},  # past → excluded
        {"datetime": "2026-09-07T19:00:00+02:00", "temperature": 24.0},  # in window
        {"datetime": "2026-09-07T21:00:00+02:00", "temperature": 22.5},  # in window
        {"datetime": "2026-09-07T23:00:00+02:00", "temperature": 19.0},  # after bedtime → excluded
    ]
    out = _render(bp, "forecast_window_temps", now, forecast_list_safe=forecast, bedtime_ts=bedtime_ts)
    assert _reparse(out) == [24.0, 22.5]
    # the string form of the boundary value must behave identically
    out2 = _render(bp, "forecast_window_temps", now, forecast_list_safe=forecast, bedtime_ts=str(bedtime_ts))
    assert _reparse(out2) == [24.0, 22.5]
