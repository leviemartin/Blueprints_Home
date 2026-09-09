"""Structural pins for bedroom_precool.yaml (Bedroom Sleep Pre-Cool v1.1.0) and its
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
    assert bp["blueprint"]["name"].endswith("v1.1.0")
    assert "**Version: 1.1.0**" in bp["blueprint"]["description"]


# --- deployed instance config (board 20260907-163522 R1-04: the deploy dry-run owns the
# schema checks — unknown keys, required inputs, use_blueprint.path, instance-id rule) ---

from test_deploy_blueprint_script import run as deploy_run

HA_PATH = "leviemartin/bedroom_precool.yaml"


def test_precool_instance_passes_the_deploy_dry_run():
    r = deploy_run("--dry-run", str(BP_PATH), HA_PATH, str(PRECOOL_INSTANCE))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "dry-run: validation passed" in r.stdout
    assert "ok (id 1779553673971" in r.stdout


def test_precool_instance_values():
    inst = json.loads(PRECOOL_INSTANCE.read_text())
    # weather.openweathermap supports no forecast type (a get_forecasts call raises);
    # weather.home_sm (Met.no) supports daily + hourly (supported_features 3).
    assert inst["use_blueprint"]["input"]["weather_entity"] == "weather.home_sm"
    assert inst["alias"].endswith("v1.1.0")
    # HA keeps 5 traces by default — ~5 minutes of a 1-minute automation, too few to read
    # the bedtime-lock evidence after the fact ([8] observation)
    assert inst["trace"]["stored_traces"] >= 30


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


_MISSING = object()


def _ha_float(v, d=_MISSING):
    """HA's `float` filter: the default (which may be none) on anything unparsable."""
    try:
        return float(v)
    except (TypeError, ValueError):
        if d is _MISSING:
            raise
        return d


def _env(now):
    env = Environment()
    env.filters["float"] = _ha_float
    env.filters["as_local"] = lambda d: d.astimezone(TZ)
    env.filters["bitwise_and"] = lambda a, b: int(a) & int(b)
    env.filters["timestamp_custom"] = (
        lambda ts, fmt="%Y-%m-%d %H:%M:%S", local=True: datetime.fromtimestamp(float(ts), tz=TZ).strftime(fmt)
    )
    env.globals["now"] = lambda: now
    env.globals["timedelta"] = timedelta
    env.globals["as_timestamp"] = lambda d: d.timestamp() if hasattr(d, "timestamp") else float(d)
    def _as_datetime(s, d=_MISSING):
        try:
            return datetime.fromisoformat(s) if isinstance(s, str) else s
        except ValueError:
            if d is _MISSING:
                raise
            return d
    env.globals["as_datetime"] = _as_datetime
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


# --- phase derivation at wake (hotfix 2026-09-08: DAY_OFF unreachable while the AC ran) ---

PHASE_CHAIN = [
    "earliest_turn_on_tod", "on_day_side", "in_lock_window", "in_deep_check",
    "in_deep_hold", "precool_started", "in_precool_window", "in_day_off", "phase",
]


def _render_chain(bp, names, now, ctx):
    """Render `names` in order, handing each re-parsed result to the next template — the
    variables-boundary model from the 2026-09-07 hotfix, applied to the phase machine."""
    for name in names:
        ctx[name] = _reparse(_render(bp, name, now, **ctx))
    return ctx


def _phase_at(bp, hh, mm, ac_is_running, cooling_needed=False, turn_on_tod="17:43:00", **overrides):
    now = datetime(2026, 9, 8, hh, mm, tzinfo=TZ)
    ctx = dict(
        now_tod=now.strftime("%H:%M:%S"), wake_tod="07:15:00", bedtime_tod="19:30:00",
        lock_tod="19:29:00", deep_tod="01:00:00", deep_end_tod="01:10:00",
        bedtime="19:30:00", wake_time="07:15:00", lead_cap_minutes=240,
        turn_on_tod=turn_on_tod, cooling_needed=cooling_needed, ac_is_running=ac_is_running,
    )
    ctx.update(overrides)
    return _render_chain(bp, PHASE_CHAIN, now, ctx)


def test_rendered_phase_is_day_off_after_wake_while_the_ac_is_still_running(bp):
    """Live trace 2026-09-08 09:08 local (run 907eaf5c…): cooling_needed False, turn_on 17:43,
    AC still running from the night hold -> v1.0.1 derived PRECOOL and re-drove the unit."""
    ctx = _phase_at(bp, 7, 15, ac_is_running=True)
    assert ctx["precool_started"] is False
    assert ctx["phase"] == "DAY_OFF"
    assert _phase_at(bp, 9, 8, ac_is_running=True)["phase"] == "DAY_OFF"


def test_rendered_running_ac_is_adopted_as_precool_only_inside_the_lead_cap_window(bp):
    # bedtime 19:30 - lead cap 240 min = 15:30: before it a running AC is DAY_OFF (turned off);
    # from it on the running AC IS the PRECOOL latch, even when turn_on has moved later.
    assert _phase_at(bp, 15, 29, ac_is_running=True)["phase"] == "DAY_OFF"
    assert _phase_at(bp, 15, 30, ac_is_running=True)["phase"] == "PRECOOL"
    assert _phase_at(bp, 18, 0, ac_is_running=True, turn_on_tod="18:30:00")["phase"] == "PRECOOL"


def test_rendered_precool_still_starts_at_turn_on_when_cooling_is_needed(bp):
    assert _phase_at(bp, 17, 42, ac_is_running=False, cooling_needed=True)["phase"] == "DAY_OFF"
    assert _phase_at(bp, 17, 43, ac_is_running=False, cooling_needed=True)["phase"] == "PRECOOL"
    assert _phase_at(bp, 17, 43, ac_is_running=False, cooling_needed=False)["phase"] == "DAY_OFF"


def test_rendered_night_phases_unchanged(bp):
    assert _phase_at(bp, 19, 29, ac_is_running=True)["phase"] == "BEDTIME_LOCK"
    assert _phase_at(bp, 22, 47, ac_is_running=True)["phase"] == "NIGHT_HOLD"
    assert _phase_at(bp, 1, 5, ac_is_running=True)["phase"] == "DEEP_NIGHT_CHECK"
    assert _phase_at(bp, 3, 0, ac_is_running=True)["phase"] == "DEEP_HOLD"


def test_rendered_earliest_turn_on_tod_is_bedtime_minus_lead_cap(bp):
    now = datetime(2026, 9, 8, 9, 0, tzinfo=TZ)
    assert _render(bp, "earliest_turn_on_tod", now, bedtime="19:30:00", lead_cap_minutes=240) == "15:30:00"
    assert _render(bp, "earliest_turn_on_tod", now, bedtime="21:30:00", lead_cap_minutes=360) == "15:30:00"


def _config_validation_template(bp):
    for step in bp.get("actions") or bp.get("action") or []:
        for branch in (step.get("choose") or []) if isinstance(step, dict) else []:
            seq = branch.get("sequence") or []
            if any(isinstance(s, dict) and s.get("stop") == "Configuration error" for s in seq):
                return branch["conditions"][0]["value_template"]
    raise KeyError("configuration-error branch")


def test_rendered_config_validation_rejects_a_lead_cap_reaching_back_past_wake(bp):
    now = datetime(2026, 9, 8, 9, 0, tzinfo=TZ)
    base = dict(drive_setpoint=16, ideal_temp=23, hall_offset=2, deep_night_check="01:00:00")
    tmpl = _env(now).from_string(_config_validation_template(bp))
    render = lambda **kw: _reparse(tmpl.render(**{**base, **kw}).strip())
    assert render(bedtime="19:30:00", wake_time="07:15:00", lead_cap_minutes=240) is False  # live
    # an adoption window that starts at/before wake would swallow the wake-off again
    assert render(bedtime="11:15:00", wake_time="07:15:00", lead_cap_minutes=240) is True   # exactly at wake
    assert render(bedtime="10:00:00", wake_time="07:15:00", lead_cap_minutes=240) is True   # before wake
    # board 20260908-071936 R2-01/R1-02: bedtime − cap wrapping past midnight renders
    # '23:00:00', which a HH:MM:SS string compare would let through
    assert _render(bp, "earliest_turn_on_tod", now, bedtime="05:00:00", lead_cap_minutes=360) == "23:00:00"
    assert render(bedtime="05:00:00", wake_time="04:00:00", lead_cap_minutes=360) is True


def test_earliest_turn_on_tod_is_defined_before_precool_started_consumes_it(text):
    """HA renders a `variables:` step top to bottom; a reordering would leave
    earliest_turn_on_tod Undefined inside precool_started on every tick (R1-03)."""
    assert text.index("earliest_turn_on_tod:") < text.index("precool_started:")


# --- v1.0.3 night_fan input (design board 20260908-090730) ---------------------------

def _def_index(text, name):
    """Offset of the `<name>:` variable DEFINITION line (not a mention in a comment)."""
    m = re.search(rf"^\s+{re.escape(name)}:", text, re.M)
    assert m, f"no definition line for {name}"
    return m.start()


def test_every_input_is_passed_through_top_level_variables(bp):
    """Board R1-01/R2-01: an input that is not bound in the top-level `variables:` block is
    Undefined in Jinja, so the feature that reads it silently no-ops."""
    inputs = bp["blueprint"]["input"]
    top = bp.get("variables") or {}
    missing = [k for k in inputs if not (isinstance(top.get(k), _Input) and top[k].name == k)]
    assert missing == [], f"inputs not passed through top-level variables: {missing}"


def test_night_fan_input_defaults_to_low_and_names_its_gate(bp):
    inp = bp["blueprint"]["input"]["night_fan"]
    assert inp["default"] == "low"
    assert "Enable Fan Control" in inp["description"]
    assert "low" in [o["value"] for o in inp["selector"]["select"]["options"]]
    assert "Night Fan" in bp["blueprint"]["input"]["enable_fan_control"]["description"]


def _night_fan_chain(bp, ac_fan_modes, night_fan="low", fan_normal="medium"):
    now = datetime(2026, 9, 8, 19, 29, tzinfo=TZ)
    ctx = dict(ac_fan_modes=ac_fan_modes, night_fan=night_fan, fan_normal=fan_normal)
    return _render_chain(bp, ["night_fan_resolved", "night_fan_mode"], now, ctx)


def test_rendered_night_fan_mode_resolves_case_insensitively_and_falls_back(bp):
    assert _night_fan_chain(bp, ["auto", "low", "medium", "high"])["night_fan_mode"] == "low"
    # a unit that reports capitalised modes gets ITS spelling back (board R1-03)
    assert _night_fan_chain(bp, ["Auto", "Low", "Mid", "High"])["night_fan_mode"] == "Low"
    assert _night_fan_chain(bp, ["auto", "low", "medium", "high"], night_fan="HIGH")["night_fan_mode"] == "high"
    ctx = _night_fan_chain(bp, ["auto", "medium", "high"])
    assert ctx["night_fan_resolved"] == "" and ctx["night_fan_mode"] == "medium"
    # a string-form list on the far side of the boundary must not substring-match
    assert _night_fan_chain(bp, "['auto', 'low', 'medium', 'high']")["night_fan_mode"] == "medium"
    # accepted limitation (code board 20260908-091857 R1-02): synonyms are not mapped —
    # a 'Power'/'Mid' unit asked for 'high' gets the fallback (and the STEP 7c notice)
    ctx = _night_fan_chain(bp, ["Low", "Mid", "Power"], night_fan="high", fan_normal="Mid")
    assert ctx["night_fan_resolved"] == "" and ctx["night_fan_mode"] == "Mid"


def test_night_fan_variables_are_defined_after_fan_normal(text):
    """HA renders a `variables:` block top to bottom (board R1-06)."""
    assert _def_index(text, "fan_normal") < _def_index(text, "night_fan_resolved") < _def_index(text, "night_fan_mode")


def _service_steps(node, found, conds=()):
    """Recursive walk of the action tree: (condition templates on the path, service step)."""
    if isinstance(node, list):
        for s in node:
            _service_steps(s, found, conds)
    elif isinstance(node, dict):
        if "choose" in node:
            for br in node["choose"]:
                own = tuple(c.get("value_template", "") for c in br.get("conditions", []) if isinstance(c, dict))
                _service_steps(br.get("sequence", []), found, conds + own)
            _service_steps(node.get("default", []), found, conds)
        elif "service" in node or "action" in node:
            found.append((conds, node))
    return found


def _fan_calls_in_phase(bp, phase):
    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
    return [(c, s) for c, s in steps
            if (s.get("service") or s.get("action")) == "climate.set_fan_mode"
            and any(f"phase == '{phase}'" in t for t in c)]


def test_bedtime_lock_fan_call_targets_night_fan_mode_and_precool_keeps_precool_fan(bp):
    """Board R1-07: resolve the STEP 6 branches by their phase condition, not by raw text."""
    lock = _fan_calls_in_phase(bp, "BEDTIME_LOCK")
    assert len(lock) == 1
    conds, step = lock[0]
    assert step["data"]["fan_mode"] == "{{ night_fan_mode }}"
    assert any("current_fan != night_fan_mode" in t for t in conds)
    precool = _fan_calls_in_phase(bp, "PRECOOL")
    assert len(precool) == 1
    assert precool[0][1]["data"]["fan_mode"] == "{{ precool_fan }}"
    assert not any("night_fan_mode" in t for t in precool[0][0])


def test_night_fan_unsupported_notice_is_gated_on_fan_control_and_resolution(bp):
    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
    notices = [(c, s) for c, s in steps
               if (s.get("service") or s.get("action")) == "persistent_notification.create"
               and (s.get("data") or {}).get("notification_id") == "bedroom_precool_night_fan_unsupported"]
    assert len(notices) == 1
    conds = notices[0][0]
    assert any("night_fan_resolved == ''" in t and "enable_fan_control" in t and "enable_notifications" in t
               for t in conds)


def test_precool_instance_sets_night_fan_low():
    inst = json.loads(PRECOOL_INSTANCE.read_text())
    assert inst["use_blueprint"]["input"]["night_fan"] == "low"


# --- v1.1.0 (issue #19; spec docs/superpowers/specs/2026-09-09-climate-followup-v1.1.0-design.md) ---

class _St:
    """A minimal HA State: `.state` + `.last_changed`."""

    def __init__(self, state, last_changed):
        self.state, self.last_changed = state, last_changed


class _States(dict):
    """`states[entity]` -> State or None (HA semantics); `states(entity)` -> state string."""

    def __getitem__(self, key):
        return self.get(key)

    def __call__(self, key):
        st = self.get(key)
        return st.state if st is not None else "unknown"


def _var_template_deep(bp, name):
    """Template of a `variables:` key anywhere in the action tree (branch-level too)."""
    def walk(node):
        if isinstance(node, dict):
            v = node.get("variables")
            if isinstance(v, dict) and name in v:
                return v[name]
            for val in node.values():
                r = walk(val)
                if r is not None:
                    return r
        elif isinstance(node, list):
            for item in node:
                r = walk(item)
                if r is not None:
                    return r
        return None
    t = walk(bp.get("action") or bp.get("actions"))
    if t is None:
        raise KeyError(name)
    return t


def _notices(bp, notification_id):
    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
    return [(c, s) for c, s in steps
            if (s.get("data") or {}).get("notification_id") == notification_id]


# ---- Task 0: the auto-learn write is clamped to the helper's live range --------------

BIAS_CHAIN = ["bias_helper_min", "bias_helper_max", "bias_floor", "bias_ceiling", "bias_range_valid",
              "bias_helper_range_ok"]


def _bias_chain(bp, helper_min, helper_max, raw):
    now = datetime(2026, 9, 9, 19, 29, tzinfo=TZ)
    attrs = {"min": helper_min, "max": helper_max}
    ctx = dict(lead_bias_entity="input_number.autolearner", state_attr=lambda e, a: attrs.get(a))
    ctx = _render_chain(bp, BIAS_CHAIN, now, ctx)
    ctx["new_bias_raw"] = raw
    ctx["new_bias"] = _reparse(_env(now).from_string(_var_template_deep(bp, "new_bias")).render(**ctx).strip())
    return ctx


def test_rendered_new_bias_is_clamped_to_the_helpers_live_range(bp):
    # 2026-09-08 17:29Z: a helper created with min 60 rejected 58.0 and aborted the lock run
    ctx = _bias_chain(bp, 60.0, 240.0, 58.0)
    assert (ctx["bias_floor"], ctx["bias_ceiling"]) == (60.0, 120.0)
    assert ctx["new_bias"] == 60 and ctx["bias_helper_range_ok"] is False
    ctx = _bias_chain(bp, -60.0, 240.0, 58.0)
    assert ctx["new_bias"] == 58 and ctx["bias_helper_range_ok"] is True
    assert _bias_chain(bp, -60.0, 240.0, -80.0)["new_bias"] == -60
    assert _bias_chain(bp, -60.0, 240.0, 130.0)["new_bias"] == 120
    # attributes missing (helper unavailable / unconfigured '') -> the blueprint's own bounds
    ctx = _bias_chain(bp, None, None, 130.0)
    assert (ctx["bias_floor"], ctx["bias_ceiling"], ctx["new_bias"]) == (-60, 120, 120)
    assert ctx["bias_helper_range_ok"] is True and ctx["bias_range_valid"] is True
    assert _bias_chain(bp, None, None, -80.0)["new_bias"] == -60
    # fractional helper bounds round INWARD so the whole-number write stays inside the helper
    # (board 20260909-113000 R2-A-01/R2-B1-002/R1-04)
    ctx = _bias_chain(bp, -59.5, 119.5, -70.0)
    assert (ctx["bias_floor"], ctx["bias_ceiling"], ctx["new_bias"]) == (-59, 119, -59)
    assert _bias_chain(bp, -59.5, 119.5, 130.0)["new_bias"] == 119
    # a helper that does not overlap -60..120 at all: floor > ceiling -> the write is skipped
    ctx = _bias_chain(bp, 130.0, 240.0, 58.0)
    assert (ctx["bias_floor"], ctx["bias_ceiling"]) == (130, 120)
    assert ctx["bias_range_valid"] is False and ctx["bias_helper_range_ok"] is False


def test_bias_range_variables_are_defined_after_lead_bias_and_before_the_lock(text):
    assert (_def_index(text, "lead_bias") < _def_index(text, "bias_helper_min")
            < _def_index(text, "bias_helper_max") < _def_index(text, "bias_floor")
            < _def_index(text, "bias_ceiling") < _def_index(text, "bias_range_valid")
            < _def_index(text, "bias_helper_range_ok") < text.index("new_bias:"))


def test_bias_helper_range_notice_is_state_driven(bp):
    n = _notices(bp, "bedroom_precool_bias_helper_range")
    kinds = sorted((s.get("service") or s.get("action")) for _, s in n)
    assert kinds == ["persistent_notification.create", "persistent_notification.dismiss"]
    create_conds = next(c for c, s in n if s["service"].endswith("create"))
    assert any("not bias_helper_range_ok" in t and "lead_bias_configured" in t
               and "enable_notifications" in t and "enable_auto_learn" in t for t in create_conds)
    assert all(s.get("continue_on_error") is True for _, s in n)


def test_auto_learn_write_is_clamped_and_skipped_on_an_override_night(bp):
    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
    writes = [(c, s) for c, s in steps if (s.get("service") or s.get("action")) == "input_number.set_value"]
    assert len(writes) == 1
    conds, step = writes[0]
    assert any("phase == 'BEDTIME_LOCK'" in t for t in conds)
    assert any("ac_is_running" in t for t in conds)
    assert any("enable_auto_learn" in t and "lead_bias_configured" in t and "not manual_setpoint" in t
               and "bias_range_valid" in t for t in conds)
    assert step["data"]["value"] == "{{ new_bias | float }}"
    nb = _var_template_deep(bp, "new_bias")
    assert "bias_floor" in nb and "bias_ceiling" in nb and "-60" not in nb and "120" not in nb
    # rounded BEFORE the clamp so the result cannot leave the whole-number bounds
    assert nb.index("round(0)") < nb.index("bias_floor")


def test_auto_learn_write_and_notice_cover_a_missing_helper_entity(bp):
    """Final review #4: a configured helper that was deleted/renamed returns no state — the write
    is skipped (it would raise and abort the lock run) and the STEP 7a notice names it."""
    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
    writes = [(c, s) for c, s in steps if (s.get("service") or s.get("action")) == "input_number.set_value"]
    assert any("states[lead_bias_entity] is not none" in t for t in writes[0][0])
    n = _notices(bp, "bedroom_precool_no_bias_helper")
    assert len(n) == 1
    assert any("states[lead_bias_entity] is none" in t and "not lead_bias_configured" in t for t in n[0][0])


# ---- R1-07: a real daily forecast backs the non-fetch ticks --------------------------

def test_dead_forecast_attribute_read_is_gone(text):
    assert "state_attr(weather_entity, 'forecast')" not in text
    assert "forecast_daily_fallback" not in text


def test_rendered_weather_daily_supported_reads_feature_bit_1(bp):
    now = datetime(2026, 9, 9, 12, 0, tzinfo=TZ)
    r = lambda feat: _reparse(_render(bp, "weather_daily_supported", now,
                                      weather_entity="weather.x", state_attr=lambda e, a: feat))
    assert r(3) is True and r(1) is True and r(5) is True
    assert r(2) is False and r(4) is False and r(0) is False and r(None) is False


def test_rendered_forecast_daily_high_picks_todays_entry_by_local_date(bp):
    now = datetime(2026, 9, 9, 14, 40, tzinfo=TZ)
    lst = [
        {"datetime": "2026-09-08T10:00:00+00:00", "temperature": 30.0, "templow": 20.0},  # stale first entry
        {"datetime": "2026-09-09T10:00:00+00:00", "temperature": 18.1, "templow": 13.4},  # today (live probe shape)
        {"datetime": "2026-09-10T10:00:00+00:00", "temperature": 18.6, "templow": 10.9},
    ]
    assert _reparse(_render(bp, "forecast_daily_high", now, forecast_daily_list=lst)) == 18.1
    # no entry for today -> the first usable entry; nothing usable -> None
    assert _reparse(_render(bp, "forecast_daily_high", now, forecast_daily_list=lst[2:])) == 18.6
    assert _reparse(_render(bp, "forecast_daily_high", now, forecast_daily_list=[])) is None
    assert _reparse(_render(bp, "forecast_daily_high", now,
                            forecast_daily_list=[{"datetime": "2026-09-09T10:00:00+00:00"}])) is None
    # local-date match: 23:30 local on the 9th is 21:30Z, still the 9th's entry
    late = datetime(2026, 9, 9, 23, 30, tzinfo=TZ)
    assert _reparse(_render(bp, "forecast_daily_high", late, forecast_daily_list=lst)) == 18.1
    # malformed entries are skipped, never raised (board R2-B1-001 / R2-A-09): the fetch's
    # continue_on_error does not protect these templates
    bad = [{"datetime": "garbage", "temperature": 30.0}, {"datetime": "2026-09-09T10:00:00+00:00", "temperature": "abc"},
           "not-a-mapping", {"datetime": "2026-09-09T10:00:00+00:00", "temperature": 18.1}]
    assert _reparse(_render(bp, "forecast_daily_high", now, forecast_daily_list=bad)) == 18.1
    # the "first usable" fallback also needs a parsable datetime (board delta R2-C2-01)
    assert _reparse(_render(bp, "forecast_daily_high", now, forecast_daily_list=bad[:3])) is None
    assert _reparse(_render(bp, "forecast_daily_high", now, forecast_daily_list=bad[:1] + lst[2:])) == 18.6


def test_rendered_hourly_window_skips_malformed_entries(bp):
    now = datetime(2026, 9, 7, 18, 0, tzinfo=TZ)
    bedtime_ts = _reparse(_render(bp, "bedtime_ts", now, bedtime="21:30:00"))
    forecast = [
        {"datetime": "garbage", "temperature": 99.0},
        {"datetime": "2026-09-07T19:00:00+02:00", "temperature": "abc"},
        {"datetime": "2026-09-07T19:00:00+02:00", "temperature": 24.0},
        "not-a-mapping",
    ]
    assert _reparse(_render(bp, "forecast_window_temps", now, forecast_list_safe=forecast, bedtime_ts=bedtime_ts)) == [24.0]


def _forecast_max_chain(bp, now, hourly, daily_high, outdoor_now):
    ctx = dict(forecast_window_temps=hourly, forecast_daily_high=daily_high, outdoor_now=outdoor_now)
    return _render_chain(bp, ["forecast_daily_ok", "forecast_max"], now, ctx)


def test_rendered_forecast_max_prefers_hourly_then_daily_then_outdoor(bp):
    now = datetime(2026, 9, 9, 14, 40, tzinfo=TZ)
    assert _forecast_max_chain(bp, now, [24.0, 22.5], 26.0, 22.0)["forecast_max"] == 24.0
    ctx = _forecast_max_chain(bp, now, [], 24.0, 22.0)
    assert ctx["forecast_daily_ok"] is True and ctx["forecast_max"] == 24.0
    assert _forecast_max_chain(bp, now, [], 18.1, 22.0)["forecast_max"] == 22.0   # never below the live reading
    ctx = _forecast_max_chain(bp, now, [], None, 22.0)
    assert ctx["forecast_daily_ok"] is False and ctx["forecast_max"] == 22.0
    # the boundary may hand the daily value over as a string
    assert _forecast_max_chain(bp, now, [], "24.0", 22.0)["forecast_max"] == 24.0


def test_rendered_forecast_daily_due_only_when_the_hourly_window_is_empty_on_the_day_side(bp):
    r = lambda hh, mm, window, supported: _reparse(_render(
        bp, "forecast_daily_due", datetime(2026, 9, 9, hh, mm, tzinfo=TZ),
        forecast_window_temps=window, weather_daily_supported=supported,
        wake_time="07:15:00", bedtime="19:30:00"))
    assert r(14, 40, [], True) is True
    assert r(14, 40, [24.0], True) is False      # the hourly window carries the prediction
    assert r(14, 40, [], False) is False         # entity without FORECAST_DAILY: never call
    assert r(20, 0, [], True) is False           # after bedtime: unused
    assert r(7, 0, [], True) is False            # before wake: unused


def test_daily_forecast_call_is_gated_and_error_tolerant(bp):
    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
    calls = {s["data"]["type"]: (c, s) for c, s in steps
             if (s.get("service") or s.get("action")) == "weather.get_forecasts"}
    assert set(calls) == {"hourly", "daily"}
    for t, (c, s) in calls.items():
        assert s["continue_on_error"] is True, t
        assert s["response_variable"] == f"{t}_forecast_resp", t
    assert any("forecast_daily_due" in t for t in calls["daily"][0])
    assert any("forecast_fetch_due" in t for t in calls["hourly"][0])


def test_forecast_variables_are_defined_in_dependency_order(text):
    assert (_def_index(text, "forecast_window_temps") < _def_index(text, "forecast_daily_due")
            < _def_index(text, "forecast_daily_list") < _def_index(text, "forecast_daily_high")
            < _def_index(text, "forecast_daily_ok") < _def_index(text, "forecast_max"))
    assert _def_index(text, "weather_daily_supported") < _def_index(text, "forecast_daily_due")


def test_forecast_unavailable_notice_also_requires_the_daily_backstop_to_be_absent(bp):
    n = _notices(bp, "bedroom_precool_forecast_warning")
    assert len(n) == 1
    assert any("not forecast_daily_ok" in t and "not outdoor_now_ok" in t for t in n[0][0])


# ---- Manual override (research design C — known-value set; spec §3.2) --------------

OVERRIDE_CHAIN = ["known_setpoints", "setpoint_is_known", "manual_setpoint"]


def _override(bp, current_setpoint, running=True, known=True, age_sec=600, **over):
    now = datetime(2026, 9, 9, 17, 0, tzinfo=TZ)
    ctx = dict(effective_drive=18.0, maintaining_setpoint=21.0, correction_step=1.5,
               ac_min_temp=18.0, ac_max_temp=30.0, ac_temp_step=0.5, current_setpoint=current_setpoint,
               current_setpoint_known=known, ac_is_running=running, ac_climate="climate.bedrooms",
               states=_States({"climate.bedrooms": _St("cool" if running else "off", now - timedelta(seconds=age_sec))}))
    ctx.update(over)
    ctx["ac_state_age_sec"] = _reparse(_render(bp, "ac_state_age_sec", now, **ctx))
    return _render_chain(bp, OVERRIDE_CHAIN, now, ctx)


def test_rendered_manual_setpoint_is_any_value_the_blueprint_could_not_have_commanded(bp):
    # live instance: ideal 23, hall offset 2, drive 16 -> clamped 18, step 1.5
    assert _override(bp, 18.0)["known_setpoints"] == [18.0, 21.0, 19.5, 22.5]
    for v in (18.0, 21.0, 19.5, 22.5, 21.05, 17.95):
        assert _override(bp, v)["manual_setpoint"] is False, v
    for v in (24.0, 20.0, 23.0, 18.5, 30.0):
        assert _override(bp, v)["manual_setpoint"] is True, v
    assert _override(bp, 24.0, running=False)["manual_setpoint"] is False      # off: nothing to respect
    assert _override(bp, 24.0, known=False)["manual_setpoint"] is False        # LG null setpoint
    # two-tick grace (board R1-01): a lagged/lost command on the turn-on tick is re-sent by
    # the next tick's idempotency guard instead of standing PRECOOL down for the evening
    assert _override(bp, 24.0, age_sec=60)["manual_setpoint"] is False
    assert _override(bp, 24.0, age_sec=119)["manual_setpoint"] is False
    assert _override(bp, 24.0, age_sec=120)["manual_setpoint"] is True
    ctx = _override(bp, 24.0, age_sec=60)
    assert ctx["ac_state_age_sec"] == 60.0
    # deep-night values clamp to the device range like the commands themselves
    assert _override(bp, 18.0, ac_max_temp=22.0)["known_setpoints"] == [18.0, 21.0, 19.5, 22.0]


def test_rendered_known_setpoints_are_the_values_the_device_holds(bp):
    """A whole-degree unit receives int(value) from the lg_thinq integration: 21.5 is held as
    21, 20.0 stays 20, 23.0 stays 23 — the set must match what the unit reports, or every
    tick reads as manual (memory: compare against the value the device actually holds)."""
    ctx = _override(bp, 21.0, ac_temp_step=1.0, maintaining_setpoint=21.5)
    assert ctx["known_setpoints"] == [18, 21, 20, 23]
    assert ctx["manual_setpoint"] is False
    assert _override(bp, 22.0, ac_temp_step=1.0, maintaining_setpoint=21.5)["manual_setpoint"] is True
    # a 0.5-step unit holds the blueprint's values as commanded
    assert _override(bp, 21.5, ac_temp_step=0.5, maintaining_setpoint=21.5)["known_setpoints"] == [18.0, 21.5, 20.0, 23.0]


def test_rendered_commanded_setpoints_are_quantised_at_the_source(bp):
    """board R2-B1-005: the idempotency guards compare against the same device-held value as
    the override detection — a whole-degree unit would otherwise be re-sent 21.5 every tick."""
    now = datetime(2026, 9, 9, 17, 0, tzinfo=TZ)
    base = dict(drive_setpoint=16.0, ideal_temp=23.5, hall_offset=2.0, ac_min_temp=18.0, ac_max_temp=30.0)
    r = lambda name, step, **kw: _reparse(_render(bp, name, now, ac_temp_step=step, **{**base, **kw}))
    assert r("maintaining_setpoint", 0.5) == 21.5 and r("maintaining_setpoint", 1.0) == 21
    assert r("effective_drive", 0.5) == 18.0 and r("effective_drive", 1.0) == 18
    assert r("maintaining_setpoint", 1.0, ideal_temp=23.0) == 21
    deep = _env(now).from_string(_var_template_deep(bp, "deep_target_setpoint"))
    row = lambda step, drift: _reparse(deep.render(deep_drift=drift, tolerance=1.5, maintaining_setpoint=21.5 if step < 1 else 21,
                                                   correction_step=1.5, ac_min_temp=18.0, ac_max_temp=30.0, ac_temp_step=step).strip())
    assert row(0.5, 2.0) == 20.0 and row(0.5, -2.0) == 23.0 and row(0.5, 0.0) == 21.5
    assert row(1.0, 2.0) == 19 and row(1.0, -2.0) == 22 and row(1.0, 0.0) == 21


def test_rendered_setpoint_is_known_treats_a_non_list_as_known(bp):
    now = datetime(2026, 9, 9, 17, 0, tzinfo=TZ)
    r = lambda ks: _reparse(_render(bp, "setpoint_is_known", now, known_setpoints=ks, current_setpoint=24.0))
    assert r("[18.0, 21.0]") is True     # a string-form list must not iterate characters
    assert r("") is True
    assert r([18.0, 21.0]) is False


MANUAL_OFF_CHAIN = ["earliest_turn_on_ts", "automation_up_since_ts", "ac_off_since_ts",
                    "vacation_changed_ts", "manual_off"]


def _manual_off(bp, ac_state, ac_last_changed, automation_last_changed=None, vacation=(), unavailable=False):
    now = datetime(2026, 9, 9, 17, 0, tzinfo=TZ)
    vac = [_St("off", t) for t in vacation]
    ctx = dict(bedtime="19:30:00", lead_cap_minutes=240, ac_climate="climate.bedrooms",
               vacation_toggle=["input_boolean.vac"] if vacation else [],
               ac_is_running=ac_state not in ("off", "unavailable", "unknown"),
               ac_unavailable=unavailable,
               states=_States({"climate.bedrooms": _St(ac_state, ac_last_changed)}),
               this=_St("on", automation_last_changed or datetime(2026, 9, 9, 6, 0, tzinfo=TZ)),
               expand=lambda ids: vac)
    return _render_chain(bp, MANUAL_OFF_CHAIN, now, ctx)


def test_rendered_manual_off_only_for_an_off_transition_inside_the_adoption_window(bp):
    t = lambda h, m, s=0: datetime(2026, 9, 9, h, m, s, tzinfo=TZ)
    ctx = _manual_off(bp, "off", t(16, 30))
    assert ctx["earliest_turn_on_ts"] == t(15, 30).timestamp()
    assert ctx["manual_off"] is True                                            # switched off inside 15:30-19:29
    assert _manual_off(bp, "off", t(7, 15))["manual_off"] is False              # the wake turn-off
    assert _manual_off(bp, "off", t(15, 29))["manual_off"] is False             # DAY_OFF ended a manual daytime start
    # board R1-05: a DAY_OFF turn_off issued on the last pre-window tick may be CONFIRMED by the
    # coordinator after the window opens — a 120 s margin keeps it out of the detector
    assert _manual_off(bp, "off", t(15, 30))["manual_off"] is False
    assert _manual_off(bp, "off", t(15, 31, 59))["manual_off"] is False
    assert _manual_off(bp, "off", t(15, 32))["manual_off"] is True
    assert _manual_off(bp, "cool", t(16, 30))["manual_off"] is False            # running
    assert _manual_off(bp, "unavailable", t(16, 30), unavailable=True)["manual_off"] is False
    # HA start / automation reload re-creates the state with a fresh last_changed; a cloud
    # integration may publish its first state minutes later (board R1-02 / R2-B1-004): 600 s
    assert _manual_off(bp, "off", t(16, 30), automation_last_changed=t(16, 29))["manual_off"] is False
    assert _manual_off(bp, "off", t(16, 30), automation_last_changed=t(16, 21))["manual_off"] is False
    assert _manual_off(bp, "off", t(16, 30), automation_last_changed=t(16, 19))["manual_off"] is True
    # the vacation branch's turn_off is not a manual off, even when the coordinator confirms it
    # up to two minutes later (board R2-B1-003)
    assert _manual_off(bp, "off", t(16, 30), vacation=[t(16, 30)])["manual_off"] is False
    assert _manual_off(bp, "off", t(16, 30), vacation=[t(16, 28, 30)])["manual_off"] is False
    assert _manual_off(bp, "off", t(16, 30), vacation=[t(16, 27)])["manual_off"] is True
    # vacation_changed_ts is the toggle's LATEST change: a vacation that ENDS after the unit
    # went off (the blueprint's own turn_off hours earlier) is not a manual off, however late
    # the coordinator confirmed that turn_off (board delta R2-C2-04)
    assert _manual_off(bp, "off", t(16, 0), vacation=[t(16, 30)])["manual_off"] is False
    assert _manual_off(bp, "off", t(12, 0), vacation=[t(16, 30)])["manual_off"] is False


def test_rendered_manual_off_survives_a_missing_climate_state(bp):
    now = datetime(2026, 9, 9, 17, 0, tzinfo=TZ)
    ctx = dict(bedtime="19:30:00", lead_cap_minutes=240, ac_climate="climate.gone", vacation_toggle=[],
               ac_is_running=False, ac_unavailable=True, states=_States({}),
               this=_St("on", datetime(2026, 9, 9, 6, 0, tzinfo=TZ)), expand=lambda ids: [])
    ctx = _render_chain(bp, MANUAL_OFF_CHAIN, now, ctx)
    assert ctx["ac_off_since_ts"] == 0 and ctx["manual_off"] is False


def _climate_calls_in_phase(bp, phase):
    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
    return [(c, s) for c, s in steps
            if (s.get("service") or s.get("action") or "").startswith("climate.")
            and any(f"phase == '{phase}'" in t for t in c)]


def test_precool_commands_are_gated_on_the_override_flags_and_the_boundaries_are_not(bp):
    precool = _climate_calls_in_phase(bp, "PRECOOL")
    assert sorted(s["service"] for _, s in precool) == \
        ["climate.set_fan_mode", "climate.set_hvac_mode", "climate.set_temperature", "climate.turn_on"]
    for c, s in precool:
        assert any("not manual_setpoint and not manual_off" in t for t in c), s["service"]
    # the bedtime lock is the phase boundary that ends the override: its commands are ungated
    lock = _climate_calls_in_phase(bp, "BEDTIME_LOCK")
    assert sorted(s["service"] for _, s in lock) == \
        ["climate.set_fan_mode", "climate.set_hvac_mode", "climate.set_temperature"]
    assert not any("manual" in t for c, _ in lock for t in c)
    # the deep-night check keeps its correction (literal "next phase boundary" reading, spec §3.2)
    deep = _climate_calls_in_phase(bp, "DEEP_NIGHT_CHECK")
    assert [s["service"] for _, s in deep] == ["climate.set_temperature"]
    assert not any("manual" in t for c, _ in deep for t in c)
    # the gate wraps exactly the four climate calls and nothing else (final review #9)
    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
    gated = [s for c, s in steps if any("not manual_setpoint and not manual_off" in t for t in c)]
    assert sorted((s.get("service") or s.get("action")) for s in gated) == \
        ["climate.set_fan_mode", "climate.set_hvac_mode", "climate.set_temperature", "climate.turn_on"]


def test_manual_override_notice_is_state_driven_and_phase_gated(bp):
    n = _notices(bp, "bedroom_precool_manual_override")
    kinds = sorted((s.get("service") or s.get("action")) for _, s in n)
    assert kinds == ["persistent_notification.create", "persistent_notification.dismiss"]
    create_conds = next(c for c, s in n if s["service"].endswith("create"))
    assert any("manual_setpoint or manual_off" in t and "NIGHT_HOLD" in t and "PRECOOL" in t
               and "enable_notifications" in t for t in create_conds)
    assert all(s.get("continue_on_error") is True for _, s in n)


def test_override_variables_are_defined_in_dependency_order(text):
    assert _def_index(text, "ac_temp_step") < _def_index(text, "effective_drive") < _def_index(text, "known_setpoints")
    assert _def_index(text, "ac_state_age_sec") < _def_index(text, "manual_setpoint")
    assert (_def_index(text, "maintaining_setpoint") < _def_index(text, "known_setpoints")
            < _def_index(text, "setpoint_is_known") < _def_index(text, "manual_setpoint"))
    assert (_def_index(text, "earliest_turn_on_tod") < _def_index(text, "earliest_turn_on_ts")
            < _def_index(text, "automation_up_since_ts") < _def_index(text, "ac_off_since_ts")
            < _def_index(text, "vacation_changed_ts") < _def_index(text, "manual_off"))
    # both flags are computed in STEP 2c, before the STEP 6 dispatch that reads them
    assert _def_index(text, "manual_setpoint") < text.index("# STEP 3: RUNTIME (CONFIG) VALIDATION")
    assert _def_index(text, "manual_off") < text.index("# STEP 3: RUNTIME (CONFIG) VALIDATION")
