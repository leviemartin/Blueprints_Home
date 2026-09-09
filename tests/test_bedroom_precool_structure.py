"""Structural pins for bedroom_precool.yaml (Bedroom Sleep Pre-Cool v1.2.0) and its
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
    assert bp["blueprint"]["name"].endswith("v1.2.0")
    assert "**Version: 1.2.0**" in bp["blueprint"]["description"]


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
    assert inst["alias"].endswith("v1.2.0")
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


def _as_timestamp_filter(d, default=_MISSING):
    """HA's `as_timestamp` FILTER form (with a default). Jinja renders `None.last_changed` as
    an Undefined object — float()/.timestamp() raise on it, caught below like any other
    unparsable value."""
    try:
        return d.timestamp() if hasattr(d, "timestamp") else float(d)
    except (TypeError, ValueError, AttributeError):
        if default is _MISSING:
            raise
        return default


def _env(now):
    env = Environment()
    env.filters["float"] = _ha_float
    env.filters["as_local"] = lambda d: d.astimezone(TZ)
    env.filters["bitwise_and"] = lambda a, b: int(a) & int(b)
    env.filters["timestamp_custom"] = (
        lambda ts, fmt="%Y-%m-%d %H:%M:%S", local=True: datetime.fromtimestamp(float(ts), tz=TZ).strftime(fmt)
    )
    env.filters["as_timestamp"] = _as_timestamp_filter
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
    base = dict(drive_setpoint=16, ideal_temp=23, hall_offset=2, deep_night_check="01:00:00",
                fan_settle_minutes=45)
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
        elif "repeat" in node:
            rep = node["repeat"]
            _service_steps(rep.get("sequence", []), found, conds + (f"for_each={rep.get('for_each', '')}",))
        elif "service" in node or "action" in node:
            found.append((conds, node))
    return found


def _top_level_steps(bp):
    return bp.get("action") or bp.get("actions") or []


def _step_contains(step, predicate):
    """Recursive search of one top-level action-tree node for a sub-node matching
    `predicate` (board 20260909-151815 F5: parsed-order checks by top-level action
    index, not string offsets)."""
    if isinstance(step, list):
        return any(_step_contains(s, predicate) for s in step)
    if isinstance(step, dict):
        if predicate(step):
            return True
        if "choose" in step:
            for br in step["choose"]:
                if any(predicate(c) for c in br.get("conditions", []) if isinstance(c, dict)):
                    return True
                if _step_contains(br.get("sequence", []), predicate):
                    return True
            if _step_contains(step.get("default", []), predicate):
                return True
        if "repeat" in step:
            return predicate(step["repeat"]) or _step_contains(step["repeat"].get("sequence", []), predicate)
    return False


def _has_for_each(step):
    return _step_contains(step, lambda n: isinstance(n, dict) and "for_each" in n)


def _has_stop_text(step, text_):
    return _step_contains(step, lambda n: isinstance(n, dict) and n.get("stop") == text_)


def _has_condition_text(step, text_):
    return _step_contains(step, lambda n: isinstance(n, dict) and text_ in (n.get("value_template") or ""))


def _has_notification_id(step, nid):
    return _step_contains(step, lambda n: isinstance(n, dict) and (n.get("data") or {}).get("notification_id") == nid)


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
    now = datetime(2026, 9, 9, 17, 0, tzinfo=TZ)
    step = n[0][1]
    tmpl = _env(now).from_string(step["data"]["message"])
    msg = tmpl.render(lead_bias_configured=False, lead_bias_entity="").strip()
    assert "()" not in msg and "no Lead-Time Bias Helper is configured" in msg
    msg2 = tmpl.render(lead_bias_configured=True, lead_bias_entity="input_number.gone").strip()
    assert "input_number.gone" in msg2 and "does not exist" in msg2


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
    # local date != UTC date (board R2-P3-02): 22:30Z on the 9th is 00:30 local on the 10th — with now on
    # the 10th at 00:30 local that entry is "today"; an implementation without as_local would fall back
    now10 = datetime(2026, 9, 10, 0, 30, tzinfo=TZ)
    cross = [{"datetime": "2026-09-09T10:00:00+00:00", "temperature": 18.1},
             {"datetime": "2026-09-09T22:30:00+00:00", "temperature": 20.5}]
    assert _reparse(_render(bp, "forecast_daily_high", now10, forecast_daily_list=cross)) == 20.5


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


def test_rendered_forecast_lists_are_extracted_from_the_response_or_empty(bp):
    """board 20260909-122828 R2-01 / R2-P3-01: the response -> list extraction, not a hand-fed list."""
    now = datetime(2026, 9, 9, 14, 40, tzinfo=TZ)
    entries = [{"datetime": "2026-09-09T10:00:00+00:00", "temperature": 18.1}]
    for name, var in (("forecast_list_safe", "hourly_forecast_resp"), ("forecast_daily_list", "daily_forecast_resp")):
        r = lambda **kw: _reparse(_render(bp, name, now, weather_entity="weather.x", **kw))
        assert r() == []                                                       # call never ran / failed
        assert r(**{var: {"weather.other": {"forecast": entries}}}) == []      # keyed by another entity
        assert r(**{var: {"weather.x": {"forecast": None}}}) == []             # forecast: null
        assert r(**{var: {"weather.x": {"forecast": 5}}}) == []                # scalar
        assert r(**{var: {"weather.x": {"forecast": "oops"}}}) == []           # string
        assert r(**{var: {"weather.x": {"forecast": {"a": 1}}}}) == []         # mapping
        assert r(**{var: {"weather.x": "oops"}}) == []                         # entity value not a mapping
        assert r(**{var: {"weather.x": {"forecast": entries}}}) == entries


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
    """A whole-degree unit receives int(value) from the lg_thinq integration; the blueprint quantises
    effective_drive / maintaining_setpoint / the deep targets at their source, and the known set must be
    exactly those device-held values (board R2-B1-005; code board R1-05: render them, never hand-feed)."""
    now = datetime(2026, 9, 9, 17, 0, tzinfo=TZ)
    inputs = dict(drive_setpoint=16.0, ideal_temp=23.5, hall_offset=2.0, correction_step=1.5, tolerance=1.5,
                  ac_min_temp=18.0, ac_max_temp=30.0)
    for step, want_known in ((1.0, [18, 21, 19, 22]), (0.5, [18.0, 21.5, 20.0, 23.0])):
        ctx = dict(inputs, ac_temp_step=step)
        ctx = _render_chain(bp, ["effective_drive", "maintaining_setpoint", "known_setpoints"], now, ctx)
        assert ctx["known_setpoints"] == want_known, step
        deep = _env(now).from_string(_var_template_deep(bp, "deep_target_setpoint"))
        for drift in (2.0, -2.0, 0.0):
            target = _reparse(deep.render(**ctx, deep_drift=drift).strip())
            assert target in ctx["known_setpoints"], (step, drift, target)
        # a value one device step away from every known value is manual; the known ones are not
        for v in ctx["known_setpoints"]:
            assert _reparse(_render(bp, "setpoint_is_known", now, known_setpoints=ctx["known_setpoints"], current_setpoint=v)) is True
        assert _reparse(_render(bp, "setpoint_is_known", now, known_setpoints=ctx["known_setpoints"], current_setpoint=24.0)) is False


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


MANUAL_OFF_CHAIN = ["lock_ts", "fan_only_mode", "earliest_turn_on_ts", "automation_up_since_ts",
                    "ac_off_since_ts", "vacation_changed_ts", "manual_off"]


def _manual_off(bp, ac_state, ac_last_changed, automation_last_changed=None, vacation=(), unavailable=False,
                 night_mode="ac_hold", now=None):
    now = now or datetime(2026, 9, 9, 17, 0, tzinfo=TZ)
    vac = [_St("off", t) for t in vacation]
    ctx = dict(bedtime="19:30:00", lead_cap_minutes=240, wake_time="07:15:00", ac_climate="climate.bedrooms",
               night_mode=night_mode,
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
    # after local midnight the night still belongs to YESTERDAY's window (board R1-03 / final review #3)
    late = datetime(2026, 9, 10, 0, 30, tzinfo=TZ)
    ctx = dict(bedtime="19:30:00", lead_cap_minutes=240, wake_time="07:15:00", ac_climate="climate.bedrooms",
               night_mode="ac_hold",
               vacation_toggle=[], ac_is_running=False, ac_unavailable=False,
               states=_States({"climate.bedrooms": _St("off", t(16, 30))}),
               this=_St("on", datetime(2026, 9, 9, 6, 0, tzinfo=TZ)), expand=lambda ids: [])
    ctx = _render_chain(bp, MANUAL_OFF_CHAIN, late, ctx)
    assert ctx["earliest_turn_on_ts"] == t(15, 30).timestamp() and ctx["manual_off"] is True
    ctx["states"] = _States({"climate.bedrooms": _St("off", t(7, 15))})
    assert _render_chain(bp, MANUAL_OFF_CHAIN, late, ctx)["manual_off"] is False
    morning = datetime(2026, 9, 10, 8, 0, tzinfo=TZ)
    ctx = _render_chain(bp, MANUAL_OFF_CHAIN, morning, dict(ctx, states=_States({"climate.bedrooms": _St("off", t(16, 30))})))
    assert ctx["earliest_turn_on_ts"] == datetime(2026, 9, 10, 15, 30, tzinfo=TZ).timestamp() and ctx["manual_off"] is False


def test_rendered_manual_off_exempts_only_the_lock_s_own_off_in_fan_only(bp):
    # lock_ts = today_at(bedtime) - 1 min = 19:29:00 on 2026-09-09 (the default `now` date).
    # `now` must be AFTER the off timestamps under test (17:00 vs. a 19:30/19:33 off is an
    # impossible fixture) — same evening, 19:35.
    t = lambda h, m, s=0: datetime(2026, 9, 9, h, m, s, tzinfo=TZ)
    evening = datetime(2026, 9, 9, 19, 35, tzinfo=TZ)
    assert _manual_off(bp, "off", t(19, 30, 0), night_mode="fan_only", now=evening)["manual_off"] is False   # lock_ts + 30s: ours
    assert _manual_off(bp, "off", t(19, 33, 0), night_mode="fan_only", now=evening)["manual_off"] is True    # lock_ts + 210s: a person's
    # ac_hold: the same lock-window off is unexempted — v1.1.0 behaviour unchanged
    assert _manual_off(bp, "off", t(19, 30, 0), night_mode="ac_hold", now=evening)["manual_off"] is True

    # F1 (P0, board 20260909-151815 R2-04): lock_ts must anchor to TONIGHT's start date
    # after local midnight too, not re-anchor to the coming evening's 19:29 — the bug that
    # put the lock's own off outside the exemption window for the rest of the night and
    # fired the false STEP 7e "Manual Override" notice 00:00-01:00 on every fan-only night.
    lock_off = t(19, 29, 30)
    persons_off = t(23, 0, 0)
    for hh, mm in ((0, 30), (1, 0)):
        small_hours = datetime(2026, 9, 10, hh, mm, tzinfo=TZ)
        ctx = _manual_off(bp, "off", lock_off, night_mode="fan_only", now=small_hours)
        assert ctx["lock_ts"] == t(19, 29, 0).timestamp(), (hh, mm)
        assert ctx["manual_off"] is False, (hh, mm)                       # the lock's own off
        assert _manual_off(bp, "off", lock_off, night_mode="ac_hold", now=small_hours)["manual_off"] is True, (hh, mm)
        assert _manual_off(bp, "off", persons_off, night_mode="fan_only", now=small_hours)["manual_off"] is True, (hh, mm)
        assert _manual_off(bp, "off", persons_off, night_mode="ac_hold", now=small_hours)["manual_off"] is True, (hh, mm)


def test_rendered_guard_is_alive_after_midnight_on_a_fan_only_lock_night(bp):
    """Board 20260909-151815 F1 (P0, R2-04): reproduces the orchestrator's exact evidence —
    at 01:00 the next day `lock_ts` used to render TONIGHT's 19:29 (future), so the lock's
    own 19:29:30 off fell outside the exemption window, `manual_off` rendered True, and
    `guard_due` rendered False for the rest of the night. Rendered end to end
    (lock_ts -> earliest_turn_on_ts -> manual_off -> guard_due) so the test exercises
    production order, not injected facts."""
    t = lambda h, m, s=0: datetime(2026, 9, 9, h, m, s, tzinfo=TZ)
    small_hours = datetime(2026, 9, 10, 1, 0, tzinfo=TZ)
    ctx = dict(bedtime="19:30:00", lead_cap_minutes=240, wake_time="07:15:00", ac_climate="climate.bedrooms",
               night_mode="fan_only", ideal_temp=23, tolerance=1.5, warmest_bedroom=24.6, phase="NIGHT_HOLD",
               vacation_toggle=[], ac_is_running=False, ac_unavailable=False,
               states=_States({"climate.bedrooms": _St("off", t(19, 29, 30))}),
               this=_St("on", datetime(2026, 9, 9, 6, 0, tzinfo=TZ)), expand=lambda ids: [])
    ctx = _render_chain(bp, MANUAL_OFF_CHAIN, small_hours, ctx)
    assert ctx["manual_off"] is False
    ctx["ac_state_age_sec"] = 0.0
    ctx = _render_chain(bp, ["night_phase", "since_ac_start_min", "guard_due"], small_hours, ctx)
    assert ctx["guard_due"] is True


def test_rendered_manual_off_survives_a_missing_climate_state(bp):
    now = datetime(2026, 9, 9, 17, 0, tzinfo=TZ)
    ctx = dict(bedtime="19:30:00", lead_cap_minutes=240, wake_time="07:15:00", ac_climate="climate.gone",
               night_mode="ac_hold",
               vacation_toggle=[], ac_is_running=False, ac_unavailable=True, states=_States({}),
               this=_St("on", datetime(2026, 9, 9, 6, 0, tzinfo=TZ)), expand=lambda ids: [])
    ctx = _render_chain(bp, MANUAL_OFF_CHAIN, now, ctx)
    assert ctx["ac_off_since_ts"] == 0 and ctx["manual_off"] is False


def test_rendered_automation_up_since_ts_tolerates_this_being_none(bp):
    now = datetime(2026, 9, 9, 17, 0, tzinfo=TZ)
    assert _reparse(_render(bp, "automation_up_since_ts", now, this=None)) == 0
    assert _reparse(_render(bp, "automation_up_since_ts", now)) == 0          # undefined
    st = _St("on", datetime(2026, 9, 9, 6, 0, tzinfo=TZ))
    assert _reparse(_render(bp, "automation_up_since_ts", now, this=st)) == st.last_changed.timestamp()


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
    # the bedtime lock is the phase boundary that ends the override: its commands are
    # ungated; v1.2.0 adds the fan-only lock's own turn_off (gated on fan_only_mode /
    # warmest_bedroom / tolerance, never on the override flags)
    lock = _climate_calls_in_phase(bp, "BEDTIME_LOCK")
    assert sorted(s["service"] for _, s in lock) == \
        ["climate.set_fan_mode", "climate.set_hvac_mode", "climate.set_temperature", "climate.turn_off"]
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
    # board 20260909-151815 F8 (R1-05): HA's chainable Undefined would turn an unordered
    # `lock_ts | float` into 0.0 silently — pin the two order requirements F1 depends on.
    assert _def_index(text, "lock_ts") < _def_index(text, "earliest_turn_on_ts")
    assert _def_index(text, "fan_only_mode") < _def_index(text, "manual_off")
    # F7's quantised night-hold list must predate the settle predicate that reads it.
    assert _def_index(text, "night_hold_setpoints") < _def_index(text, "settle_setpoint_due")


# --- v1.2.0 fan coordination (design 2026-09-09, board 20260909-130652) --------------

class _S:
    """A fake HA State object as `expand()` returns it. last_changed (state transitions)
    and last_updated (state OR attribute changes) are independent, as in HA."""
    def __init__(self, entity_id, state, percentage=None, last_updated=None, last_changed=None):
        self.entity_id = entity_id
        self.state = state
        self.attributes = {} if percentage is None else {"percentage": percentage}
        self.last_updated = last_updated or datetime(2026, 9, 9, 12, 0, tzinfo=TZ)
        self.last_changed = last_changed or self.last_updated


def _fan_env(now, states):
    """`_env` plus HA state helpers resolving to the fakes: expand(), state_attr(), states(), is_state()."""
    env = _env(now)
    by_id = {s.entity_id: s for s in states}
    def expand(*ids):
        out = []
        for group in ids:
            for i in ([group] if isinstance(group, str) else group):
                if i in by_id:
                    out.append(by_id[i])
        return out
    env.globals["expand"] = expand
    env.globals["state_attr"] = lambda e, a: by_id[e].attributes.get(a) if e in by_id else None
    env.globals["states"] = lambda e: by_id[e].state if e in by_id else "unknown"
    env.globals["is_state"] = lambda e, v: e in by_id and by_id[e].state == v
    return env


V110_INPUTS = {
    "night_mode": "ac_hold", "prechill_offset": 0.5, "bedroom_fans": [], "interlocked_fans": [],
    "fan_interlocks": [], "interlock_clear_minutes": 5, "night_fans": "all", "night_fan_percentage": 1,
    "fan_assist": "off", "precool_fan_percentage": 21, "fan_settle_minutes": 45, "fans_at_wake": "leave",
}


def test_v110_inputs_exist_with_safe_defaults(bp):
    inputs = bp["blueprint"]["input"]
    for key, default in V110_INPUTS.items():
        assert key in inputs, key
        assert inputs[key]["default"] == default, key
    opts = lambda k: [o["value"] for o in inputs[k]["selector"]["select"]["options"]]
    assert opts("night_mode") == ["ac_hold", "fan_only"]
    assert opts("night_fans") == ["all", "odd", "even", "off"]
    assert opts("fan_assist") == ["off", "all", "odd", "even"]
    assert opts("fans_at_wake") == ["leave", "off"]
    for k in ("bedroom_fans", "interlocked_fans"):
        assert inputs[k]["selector"]["entity"]["domain"] == "fan" and inputs[k]["selector"]["entity"]["multiple"] is True
    assert inputs["fan_interlocks"]["selector"]["entity"]["domain"] == "binary_sensor"
    # the pass-through pin (test_every_input_is_passed_through_top_level_variables) covers the variables block


def _v110_ctx(**over):
    ctx = dict(ideal_temp=23, tolerance=1.5, correction_step=1.5, prechill_offset=0.5, night_mode="ac_hold",
               fan_assist="off", night_fans="all", fan_settle_minutes=45, bedtime="19:30:00",
               wake_time="07:15:00", wake_tod="07:15:00", lock_tod="19:29:00", now_tod="23:00:00",
               ac_is_running=False, warmest_bedroom=23.0, ac_started_ts=0.0, phase="NIGHT_HOLD",
               forecast_max=18.0, skip_threshold=21, maintaining_setpoint=21.0, current_hvac_mode="cool",
               current_setpoint_known=True, current_setpoint=21.0, current_fan="low", night_fan_mode="low",
               enable_fan_control=True, ac_fan_modes=["auto", "low", "medium", "high"],
               # v1.2.0: guard_due / guard_settle_due read these as already-resolved facts
               # (computed upstream, out of scope for these narrower chains) — same pattern
               # as ac_is_running / warmest_bedroom above.
               manual_off=False, manual_setpoint=False,
               # since_ac_start_min derives from this (STEP 2a); default is a huge age (no
               # recent start). _windows()/_guard() overwrite it from ac_started_ts + now.
               ac_state_age_sec=0.0,
               # F4 (board 20260909-151815, cycle 1): the automation's own restart-grace
               # reference — default epoch (a long-up automation) so in_fan_assist_window's
               # existing True assertions are unaffected. Cycle 2 G2: the rule is now
               # automation_up_since_ts < earliest_turn_on_ts (below), not a fixed 600 s
               # grace past the restart.
               automation_up_since_ts=0.0,
               # G2 (board 20260909-151815 cycle 2, R2C2-02): today's adoption-window-open
               # reference fan assist compares the restart timestamp against. Default well
               # after the epoch default above so in_fan_assist_window's existing True
               # assertions are unaffected; overridden to test the restart rule itself.
               earliest_turn_on_ts=datetime(2026, 9, 9, 15, 30, tzinfo=TZ).timestamp(),
               # F7 (board 20260909-151815): night_hold_setpoints' quantisation inputs.
               ac_temp_step=0.5, ac_min_temp=16, ac_max_temp=30)
    ctx.update(over)
    return ctx


TARGET_CHAIN = ["fan_only_mode", "bedtime_target", "delta_in", "cooling_needed", "precool_substate"]


def test_rendered_bedtime_target_drives_lead_term_skip_gate_and_substate(bp):
    now = datetime(2026, 9, 9, 18, 0, tzinfo=TZ)
    hold = _render_chain(bp, TARGET_CHAIN, now, _v110_ctx(warmest_bedroom=22.8))
    assert hold["bedtime_target"] == 23.0 and hold["delta_in"] == 0 and hold["cooling_needed"] is False
    assert hold["precool_substate"] == "HOLD"
    fan = _render_chain(bp, TARGET_CHAIN, now, _v110_ctx(night_mode="fan_only", warmest_bedroom=22.8))
    assert fan["bedtime_target"] == 22.5
    assert abs(fan["delta_in"] - 0.3) < 1e-9           # the lead term sees the deeper target (board R1-08)
    assert fan["cooling_needed"] is True               # a room between the two targets still pre-chills
    assert fan["precool_substate"] == "DRIVE"
    assert _render_chain(bp, TARGET_CHAIN, now, _v110_ctx(night_mode="fan_only", warmest_bedroom=22.5))["precool_substate"] == "HOLD"
    assert _render_chain(bp, TARGET_CHAIN, now, _v110_ctx(night_mode="fan_only", prechill_offset=0))["bedtime_target"] == 23.0
    for name in ("delta_in", "cooling_needed", "precool_substate"):
        assert "ideal_temp" not in _var_template(bp, name), name


PARITY_CHAIN = ["night_parity", "fan_assist_tonight", "night_fans_tonight"]


def _parity(bp, t, **over):
    return _render_chain(bp, PARITY_CHAIN, t, _v110_ctx(now_tod=t.strftime("%H:%M:%S"), **over))


def test_rendered_night_parity_is_shared_from_wake_to_wake(bp):
    # 2026-09-09 is day 252 of the year (even); 2026-09-10 is 253 (odd). Pivot = wake time (board R2-06).
    d9 = lambda hh, mm: datetime(2026, 9, 9, hh, mm, tzinfo=TZ)
    d10 = lambda hh, mm: datetime(2026, 9, 10, hh, mm, tzinfo=TZ)
    for t in (d9(11, 0), d9(15, 30), d9(19, 29), d10(1, 0), d10(7, 14)):    # pre-noon PRECOOL start included
        assert _parity(bp, t)["night_parity"] == "even", t
    assert _parity(bp, d10(7, 15))["night_parity"] == "odd"                 # the next night's date from wake on
    ctx = _parity(bp, d9(19, 29), fan_assist="even", night_fans="odd")
    assert ctx["fan_assist_tonight"] is True and ctx["night_fans_tonight"] is False
    ctx = _parity(bp, d9(19, 29), fan_assist="off", night_fans="all")
    assert ctx["fan_assist_tonight"] is False and ctx["night_fans_tonight"] is True


WINDOW_CHAIN = ["lock_ts", "settle_end_tod", "settle_last_tod", "since_ac_start_min", "in_wake_window",
                "in_fan_settle", "in_settle_last_tick", "in_fan_assist_window"]


def _windows(bp, hh, mm, **over):
    now = datetime(2026, 9, 9, hh, mm, tzinfo=TZ)
    ctx = _v110_ctx(now_tod=now.strftime("%H:%M:%S"), **over)
    # since_ac_start_min now derives from ac_state_age_sec (STEP 2a) — mirror the
    # blueprint's own now() - last_changed so ac_started_ts-based fixtures still work.
    ctx["ac_state_age_sec"] = now.timestamp() - float(ctx["ac_started_ts"])
    return _render_chain(bp, WINDOW_CHAIN, now, ctx)


def test_rendered_fan_windows(bp):
    lock = datetime(2026, 9, 9, 19, 29, tzinfo=TZ)
    assert _windows(bp, 19, 29)["lock_ts"] == lock.timestamp()
    assert _windows(bp, 19, 29)["settle_end_tod"] == "20:15:00"
    assert _windows(bp, 19, 29)["settle_last_tod"] == "20:14:00"
    assert _windows(bp, 19, 28)["in_fan_settle"] is False
    assert _windows(bp, 19, 29)["in_fan_settle"] is True          # the lock tick itself
    assert _windows(bp, 20, 14)["in_fan_settle"] is True
    assert _windows(bp, 20, 14)["in_settle_last_tick"] is True
    assert _windows(bp, 20, 15)["in_fan_settle"] is False
    assert _windows(bp, 7, 15)["in_wake_window"] is True and _windows(bp, 7, 16)["in_wake_window"] is False
    started = datetime(2026, 9, 9, 17, 0, tzinfo=TZ).timestamp()
    on = dict(phase="PRECOOL", ac_is_running=True, ac_started_ts=started)
    assert _windows(bp, 17, 30, **on)["since_ac_start_min"] == 30.0
    assert _windows(bp, 17, 30, **on)["in_fan_assist_window"] is True
    assert _windows(bp, 17, 46, **on)["in_fan_assist_window"] is False   # 46 > 45
    assert _windows(bp, 17, 30, **dict(on, ac_is_running=False))["in_fan_assist_window"] is False
    assert _windows(bp, 17, 30, **dict(on, phase="DAY_OFF"))["in_fan_assist_window"] is False
    # F4 (P2, board 20260909-151815 R2-05, cycle 1): a mode transition (last_changed
    # moves on cool->dry too) or an HA restart must not reopen fan assist against a
    # manual off. G2 (cycle 2, R2C2-02 + R1C2-04): the cycle-1 600 s grace only DELAYED
    # the reopen — a restart later in the same adoption window still re-opened assist.
    # The rule is now: the automation must already have been running when TODAY's
    # adoption window opened (automation_up_since_ts < earliest_turn_on_ts) — a restart
    # ANY time inside today's window disables fan assist for the rest of that night, not
    # just for 600 s past the restart.
    adopted = datetime(2026, 9, 9, 15, 30, tzinfo=TZ).timestamp()
    restart_after_open = datetime(2026, 9, 9, 16, 0, tzinfo=TZ).timestamp()   # inside today's window
    assert _windows(bp, 17, 30, **dict(on, earliest_turn_on_ts=adopted,
                                        automation_up_since_ts=restart_after_open))["in_fan_assist_window"] is False
    restart_before_open = datetime(2026, 9, 9, 6, 0, tzinfo=TZ).timestamp()   # before today's window opened
    assert _windows(bp, 17, 30, **dict(on, earliest_turn_on_ts=adopted,
                                        automation_up_since_ts=restart_before_open))["in_fan_assist_window"] is True


GUARD_CHAIN = ["fan_only_mode", "night_phase", "heat_backstop_due", "since_ac_start_min", "guard_due",
               "guard_settle_due", "settle_mode_due", "night_hold_setpoints", "setpoint_is_night_hold",
               "settle_setpoint_due", "settle_fan_due"]


def _guard(bp, now, **over):
    ctx = _v110_ctx(now_tod=now.strftime("%H:%M:%S"), **over)
    # since_ac_start_min now derives from ac_state_age_sec (STEP 2a) — mirror the
    # blueprint's own now() - last_changed so ac_started_ts-based fixtures still work.
    ctx["ac_state_age_sec"] = now.timestamp() - float(ctx["ac_started_ts"])
    return _render_chain(bp, GUARD_CHAIN, now, ctx)


def test_rendered_guard_due_only_in_night_phases_with_fan_only_ac_off_over_band_on_a_5_minute_tick(bp):
    t = datetime(2026, 9, 9, 23, 0, tzinfo=TZ)
    hot = dict(night_mode="fan_only", warmest_bedroom=24.6)
    for ph in ("NIGHT_HOLD", "DEEP_NIGHT_CHECK", "DEEP_HOLD"):
        assert _guard(bp, t, phase=ph, **hot)["guard_due"] is True, ph
    assert _guard(bp, datetime(2026, 9, 9, 23, 1, tzinfo=TZ), phase="NIGHT_HOLD", **hot)["guard_due"] is False   # cadence (board R2-02)
    assert _guard(bp, t, phase="NIGHT_HOLD", night_mode="fan_only", warmest_bedroom=24.5)["guard_due"] is False   # at the band
    assert _guard(bp, t, phase="NIGHT_HOLD", night_mode="ac_hold", warmest_bedroom=26.0)["guard_due"] is False
    assert _guard(bp, t, phase="NIGHT_HOLD", ac_is_running=True, **hot)["guard_due"] is False                      # the latch
    for ph in ("PRECOOL", "BEDTIME_LOCK", "DAY_OFF"):
        assert _guard(bp, t, phase=ph, **hot)["guard_due"] is False, ph


NIGHT_HOLD_CHAIN = ["maintaining_setpoint", "night_hold_setpoints", "setpoint_is_night_hold", "settle_setpoint_due"]


def _night_hold(bp, current_setpoint, ac_temp_step=1, **over):
    """F7 (board 20260909-151815 R1-02/R1-03): render the settle predicate's own dependency
    chain from the raw inputs, so the test exercises the SAME quantisation the blueprint
    uses for maintaining_setpoint and its two deep-night nudges."""
    now = datetime(2026, 9, 9, 23, 0, tzinfo=TZ)
    ctx = dict(ideal_temp=23, hall_offset=2, correction_step=1.5, ac_min_temp=18, ac_max_temp=30,
               ac_temp_step=ac_temp_step, current_setpoint=current_setpoint, current_setpoint_known=True,
               guard_settle_due=True)
    ctx.update(over)
    return _render_chain(bp, NIGHT_HOLD_CHAIN, now, ctx)


def test_rendered_settle_setpoint_due_leaves_every_quantised_night_hold_value_alone(bp):
    """On a 1-degree-step unit main quantises: maintaining = int(21.0) = 21, the deep-night
    down-nudge = int(21 - 1.5) = 19 (NOT 19.5), up-nudge = int(22.5) = 22. Without matching
    that quantisation, settle_setpoint_due's `> correction_step + 0.1` band (1.6) fired on
    19 (|19-21| = 2.0) and STEP 6b re-sent 21 the tick after DEEP_NIGHT_CHECK set 19 — an
    alternating loop whenever the settle window overlaps 01:00."""
    for current, expected in ((19, False), (22, False), (21, False), (18, True), (24, True)):
        assert _night_hold(bp, current)["settle_setpoint_due"] is expected, current
    assert _night_hold(bp, 19)["night_hold_setpoints"] == [21, 19, 22]
    for current, expected in ((19.5, False), (18, True)):
        assert _night_hold(bp, current, ac_temp_step=0.5)["settle_setpoint_due"] is expected, current
    assert _night_hold(bp, 19.5, ac_temp_step=0.5)["night_hold_setpoints"] == [21.0, 19.5, 22.5]


def test_rendered_night_hold_setpoints_match_the_rendered_deep_target_setpoint(bp):
    """G6 (R1C2-03, board 20260909-151815 cycle 2): pin night_hold_setpoints against the
    REAL production deep_target_setpoint template — mirrors
    test_rendered_known_setpoints_are_the_values_the_device_holds's method (render, don't
    hand-write) instead of the hard-coded expected lists above. For both drift directions
    and no drift, on a 1-degree-step and a 0.5-degree-step unit, the value
    deep_target_setpoint would actually command is IN the rendered night_hold_setpoints."""
    now = datetime(2026, 9, 9, 23, 0, tzinfo=TZ)
    deep = _env(now).from_string(_var_template_deep(bp, "deep_target_setpoint"))
    for ac_temp_step in (1, 0.5):
        ctx = _night_hold(bp, 21.0, ac_temp_step=ac_temp_step)
        for drift in (2.0, -2.0, 0.0):
            target = _reparse(deep.render(**ctx, deep_drift=drift, tolerance=1.5).strip())
            assert target in ctx["night_hold_setpoints"], (ac_temp_step, drift, target)
    # Non-list guard (mirrors test_rendered_setpoint_is_known_treats_a_non_list_as_known):
    # a string-form list crossing the variables boundary is treated as night-hold/known.
    r = lambda ks: _reparse(_render(bp, "setpoint_is_night_hold", now, night_hold_setpoints=ks, current_setpoint=99.0))
    assert r("[21, 19, 22]") is True     # a string-form list must not iterate characters
    assert r("") is True
    assert r([21, 19, 22]) is False


def test_rendered_guard_settle_asserts_the_parked_state_only_after_a_night_start(bp):
    t = datetime(2026, 9, 9, 23, 7, tzinfo=TZ)
    started = (t - timedelta(minutes=2)).timestamp()
    base = dict(night_mode="fan_only", phase="NIGHT_HOLD", ac_is_running=True, ac_started_ts=started)
    ok = _guard(bp, t, **base)
    assert ok["guard_settle_due"] is True
    assert ok["settle_mode_due"] is False and ok["settle_setpoint_due"] is False and ok["settle_fan_due"] is False
    assert _guard(bp, t, **base, current_hvac_mode="heat")["settle_mode_due"] is True         # board R1-03 / R2-04
    assert _guard(bp, t, **base, current_hvac_mode="fan_only")["settle_mode_due"] is True
    assert _guard(bp, t, **base, current_hvac_mode="dry")["settle_mode_due"] is False
    assert _guard(bp, t, **base, current_setpoint=18.0)["settle_setpoint_due"] is True         # stale DRIVE park
    # F7 (P1, board 20260909-151815 R1-02/R1-03): the nudge value is derived from the
    # rendered night_hold_setpoints, not hand-written — it is whatever the blueprint's
    # OWN quantisation produces (int() on a >= 1 ac_temp_step unit), not the raw
    # correction_step arithmetic.
    nudge = ok["night_hold_setpoints"][1]
    assert _guard(bp, t, **base, current_setpoint=nudge)["settle_setpoint_due"] is False       # a deep-night nudge, left alone
    assert _guard(bp, t, **base, current_setpoint_known=False)["settle_setpoint_due"] is False
    assert _guard(bp, t, **base, current_fan="high")["settle_fan_due"] is True
    assert _guard(bp, t, **base, current_fan="unknown")["settle_fan_due"] is False             # null read (board R1-02)
    assert _guard(bp, t, **base, enable_fan_control=False, current_fan="high")["settle_fan_due"] is False
    late = _guard(bp, t, **dict(base, ac_started_ts=(t - timedelta(minutes=16)).timestamp()), current_hvac_mode="heat")
    assert late["guard_settle_due"] is False and late["settle_mode_due"] is False              # window closed
    assert _guard(bp, t, **dict(base, night_mode="ac_hold"), current_hvac_mode="heat")["settle_mode_due"] is False
    assert _guard(bp, t, **dict(base, phase="PRECOOL"), current_hvac_mode="heat")["settle_mode_due"] is False


def test_rendered_guard_due_and_settle_respect_a_manual_override(bp):
    t = datetime(2026, 9, 9, 23, 0, tzinfo=TZ)
    hot = dict(night_mode="fan_only", warmest_bedroom=24.6, phase="NIGHT_HOLD")
    assert _guard(bp, t, **hot)["guard_due"] is True
    assert _guard(bp, t, manual_off=True, **hot)["guard_due"] is False               # a respected manual off
    started = (t - timedelta(minutes=2)).timestamp()
    settling = dict(night_mode="fan_only", phase="NIGHT_HOLD", ac_is_running=True, ac_started_ts=started)
    assert _guard(bp, t, **settling)["guard_settle_due"] is True
    assert _guard(bp, t, manual_setpoint=True, **settling)["guard_settle_due"] is False   # a person's setpoint


# --- G3 (P1 residual R2C2-03 -> mitigation, board 20260909-151815 cycle 2): heat backstop ---

def test_rendered_heat_backstop_due_only_for_heat_at_night_in_fan_only_while_running(bp):
    """A heater is never an acceptable fallback in a child's bedroom. heat_backstop_due
    catches a unit whose LAST-READ mode is 'heat' on any real tick in a night phase,
    fan-only, while ostensibly running — a stale cloud read that reports 'off' while the
    unit is actually still heating is a separate, unobservable residual (documented, not
    closed by this predicate)."""
    t = datetime(2026, 9, 9, 23, 0, tzinfo=TZ)
    hot = dict(night_mode="fan_only", phase="NIGHT_HOLD", ac_is_running=True, current_hvac_mode="heat")
    assert _guard(bp, t, **hot)["heat_backstop_due"] is True
    assert _guard(bp, t, **dict(hot, current_hvac_mode="cool"))["heat_backstop_due"] is False
    assert _guard(bp, t, **dict(hot, current_hvac_mode="fan_only"))["heat_backstop_due"] is False
    assert _guard(bp, t, **dict(hot, night_mode="ac_hold"))["heat_backstop_due"] is False
    assert _guard(bp, t, **dict(hot, ac_is_running=False))["heat_backstop_due"] is False
    for ph in ("PRECOOL", "BEDTIME_LOCK", "DAY_OFF"):
        assert _guard(bp, t, **dict(hot, phase=ph))["heat_backstop_due"] is False, ph
    for ph in ("NIGHT_HOLD", "DEEP_NIGHT_CHECK", "DEEP_HOLD"):
        assert _guard(bp, t, **dict(hot, phase=ph))["heat_backstop_due"] is True, ph


def test_heat_backstop_is_exactly_one_turn_off_gated_on_heat_backstop_due(bp):
    calls = _calls_with(bp, "heat_backstop_due")
    assert len(calls) == 1
    conds, step = calls[0]
    assert step["service"] == "climate.turn_off"
    assert step["target"]["entity_id"] == "{{ ac_climate }}"
    assert any(t.strip() == "{{ is_real_trigger and heat_backstop_due }}" for t in conds)


def test_rendered_interlock_blocked_fails_safe_and_honours_the_clear_hold(bp):
    now = datetime(2026, 9, 9, 19, 29, tzinfo=TZ)
    render = lambda states, sensors: _reparse(_fan_env(now, states).from_string(
        _var_template(bp, "interlock_blocked")).render(fan_interlocks=sensors, interlock_clear_minutes=5).strip())
    pir = "binary_sensor.samuel_samuel_matthew_fanprotection"
    assert render([_S(pir, "off")], [pir]) is False      # cleared 7.5 h ago (the _S default)
    assert render([_S(pir, "on")], [pir]) is True
    assert render([_S(pir, "unavailable")], [pir]) is True
    assert render([], [pir]) is True                     # sensor missing from the state machine
    assert render([], []) is False                       # no interlock configured
    # the cutoff resumes at clear + 3 min; we stay blocked until clear + 5 (spec §2.1, board R1-09)
    assert render([_S(pir, "off", last_changed=now - timedelta(minutes=4))], [pir]) is True
    assert render([_S(pir, "off", last_changed=now - timedelta(minutes=5, seconds=1))], [pir]) is False
    # the hold keys on last_changed (state transitions), not on attribute updates (board R2-05)
    assert render([_S(pir, "off", last_updated=now - timedelta(seconds=30), last_changed=now - timedelta(minutes=9))], [pir]) is False


def test_config_validation_rejects_a_settle_window_across_midnight(bp):
    now = datetime(2026, 9, 9, 9, 0, tzinfo=TZ)
    base = dict(drive_setpoint=16, ideal_temp=23, hall_offset=2, deep_night_check="01:00:00",
                bedtime="19:30:00", wake_time="07:15:00", lead_cap_minutes=240, fan_settle_minutes=45)
    tmpl = _env(now).from_string(_config_validation_template(bp))
    render = lambda **kw: _reparse(tmpl.render(**{**base, **kw}).strip())
    assert render() is False                                             # live config
    assert render(bedtime="23:30:00", fan_settle_minutes=45) is True     # 00:15 next day
    assert render(bedtime="23:00:00", fan_settle_minutes=45) is False    # 23:45, same day


# --- v1.2.0 T2: BEDTIME_LOCK fan-only branch (park, then off unless already over the band) ---

def _services_in_phase(bp, phase):
    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
    return [(c, s) for c, s in steps if any(f"phase == '{phase}'" in t for t in c)]


def test_learner_error_uses_bedtime_target(bp):
    lock = [s for c, s in _services_in_phase(bp, "BEDTIME_LOCK")]
    learner = [s for s in lock if (s.get("service") or s.get("action")) == "input_number.set_value"]
    assert len(learner) == 1
    assert 'bedtime_error: "{{ warmest_bedroom | float - bedtime_target | float }}"' in BP_PATH.read_text()


def test_bedtime_lock_switches_the_unit_off_only_in_fan_only_mode_after_parking_it_and_not_when_over_band(bp):
    calls = _services_in_phase(bp, "BEDTIME_LOCK")
    names = [(s.get("service") or s.get("action")) for c, s in calls]
    assert names == ["climate.set_hvac_mode", "climate.set_temperature", "climate.set_fan_mode",
                     "climate.turn_off", "input_number.set_value"], names
    off_conds = [c for c, s in calls if (s.get("service") or s.get("action")) == "climate.turn_off"][0]
    off_tmpl = [t for t in off_conds if "fan_only_mode" in t][0]
    assert "tolerance" in off_tmpl and "warmest_bedroom" in off_tmpl          # board R1-07
    assert any("ac_is_running" in t for t in off_conds)                        # cool-day lock stays a no-op
    now = datetime(2026, 9, 9, 19, 29, tzinfo=TZ)
    render = lambda **kw: _reparse(_env(now).from_string(off_tmpl).render(**_v110_ctx(**kw)).strip())
    assert render(fan_only_mode=True, warmest_bedroom=23.0) is True
    assert render(fan_only_mode=True, warmest_bedroom=24.6) is False           # already over the band: stay on
    assert render(fan_only_mode=False, warmest_bedroom=23.0) is False
    # ac_hold regression pin: none of the three park calls is gated on fan_only_mode
    for c, s in calls[:3]:
        assert not any("fan_only_mode" in t for t in c)


# --- v1.2.0 T3: night guard + guard settle (board 20260909-130652) ------------------

def _calls_with(bp, marker):
    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
    return [(c, s) for c, s in steps if any(marker in t for t in c)]


def test_night_guard_is_one_bare_turn_on_plus_notice_and_the_settle_step_corrects_from_live_reads(bp):
    guard = _calls_with(bp, "guard_due")
    names = [(s.get("service") or s.get("action")) for c, s in guard]
    assert names == ["climate.turn_on", "climate.set_hvac_mode", "persistent_notification.create"], names
    conds, turn_on = guard[0]
    assert any(t.strip() == "{{ is_real_trigger and guard_due }}" for t in conds)
    assert turn_on["target"]["entity_id"] == "{{ ac_climate }}"
    assert "data" not in turn_on                       # a bare turn_on: the unit restores its parked state
    # F2 (P1, board 20260909-151815 R2-02): the guard tick UNCONDITIONALLY forces cooling
    # mode too — a bare turn_on alone restores whatever mode the unit last held (a cool-day
    # night after manual heat use would restore heat), and the stale STEP 2 read means the
    # guard cannot condition the call on a mismatch, so it always sends it.
    mode_conds, mode_call = guard[1]
    assert mode_conds == conds                          # exactly the guard gate, no extra condition
    assert mode_call["target"]["entity_id"] == "{{ ac_climate }}"
    assert mode_call["data"]["hvac_mode"] == "{{ desired_mode }}"
    assert guard[2][1]["data"]["notification_id"] == "bedroom_precool_guard_fired"
    assert any("enable_notifications" in t for t in guard[2][0])
    assert "wait_template" not in BP_PATH.read_text()  # no same-tick read-back (board R1-01 / R2-03)
    settle_calls = _calls_with(bp, "settle_mode_due") + _calls_with(bp, "settle_setpoint_due") + _calls_with(bp, "settle_fan_due")
    settle = {(s.get("service") or s.get("action")): c for c, s in settle_calls}
    assert set(settle) == {"climate.set_hvac_mode", "climate.set_temperature", "climate.set_fan_mode"}
    assert any(t.strip() == "{{ is_real_trigger and settle_mode_due }}" for t in settle["climate.set_hvac_mode"])
    assert any(t.strip() == "{{ is_real_trigger and settle_setpoint_due }}" for t in settle["climate.set_temperature"])
    assert any(t.strip() == "{{ is_real_trigger and settle_fan_due }}" for t in settle["climate.set_fan_mode"])
    data = {(s.get("service") or s.get("action")): s["data"] for c, s in settle_calls}
    assert data["climate.set_hvac_mode"]["hvac_mode"] == "{{ desired_mode }}"
    assert data["climate.set_temperature"]["temperature"] == "{{ maintaining_setpoint | float }}"
    assert data["climate.set_fan_mode"]["fan_mode"] == "{{ night_fan_mode }}"
    # the two night branches of STEP 6 stay free of climate calls (guard lives outside)
    for ph in ("NIGHT_HOLD", "DEEP_HOLD"):
        assert _services_in_phase(bp, ph) == []


# --- v1.2.0 T4: fan due-lists (the fan write rule as rendered variables) ------------

KIDS, MASTER = "fan.ceiling_fan_light_v2", "fan.ceiling_fan_light_v2_2"
LOCK = datetime(2026, 9, 9, 19, 29, tzinfo=TZ)
BEFORE, AFTER = LOCK - timedelta(hours=2), LOCK + timedelta(seconds=20)


def _due(bp, name, now, states, **ctx):
    base = dict(bedroom_fans=[MASTER, KIDS], interlocked_fans=[KIDS], interlock_blocked=False,
                night_fans_tonight=True, in_fan_settle=True, night_fan_percentage=1, lock_ts=LOCK.timestamp(),
                fan_assist_tonight=True, in_fan_assist_window=True, precool_fan_percentage=21,
                ac_started_ts=(LOCK - timedelta(hours=2, minutes=30)).timestamp(),
                fans_at_wake="off", in_wake_window=True)
    base.update(ctx)
    return _reparse(_fan_env(now, states).from_string(_var_template(bp, name)).render(**base).strip())


def test_rendered_fans_due_night_applies_the_fan_write_rule(bp):
    now = LOCK + timedelta(minutes=5)
    untouched = [_S(MASTER, "on", 1, BEFORE), _S(KIDS, "off", 21, BEFORE)]
    assert _due(bp, "fans_due_night", now, untouched) == [KIDS]                         # master already at 1 %
    assert _due(bp, "fans_due_night", now, [_S(MASTER, "on", 21, BEFORE), _S(KIDS, "off", 21, BEFORE)]) == [MASTER, KIDS]
    assert _due(bp, "fans_due_night", now, untouched, interlock_blocked=True) == []       # kids fan blocked, master at target
    assert _due(bp, "fans_due_night", now, [_S(MASTER, "on", 21, BEFORE), _S(KIDS, "off", 21, BEFORE)],
                interlock_blocked=True) == [MASTER]                                     # interlock only guards the kids fan
    assert _due(bp, "fans_due_night", now, [_S(MASTER, "on", 21, BEFORE), _S(KIDS, "off", 21, AFTER)]) == [MASTER]   # touched since the lock
    # a percentage change bumps last_updated only; it still counts as touched (board R2-05)
    assert _due(bp, "fans_due_night", now, [_S(MASTER, "on", 21, BEFORE), _S(KIDS, "on", 21, last_updated=AFTER, last_changed=BEFORE)]) == [MASTER]
    assert _due(bp, "fans_due_night", now, [_S(MASTER, "unavailable", None, BEFORE), _S(KIDS, "off", 21, BEFORE)]) == [KIDS]
    assert _due(bp, "fans_due_night", now, [_S(KIDS, "off", 21, BEFORE)]) == [KIDS]      # master absent from the state machine
    assert _due(bp, "fans_due_night", now, [_S(MASTER, "on", None, BEFORE), _S(KIDS, "off", 21, BEFORE)]) == [MASTER, KIDS]   # no percentage attribute: renders, not at target (board R1-04)
    assert _due(bp, "fans_due_night", now, untouched, night_fans_tonight=False) == []
    assert _due(bp, "fans_due_night", now, untouched, in_fan_settle=False) == []
    assert _due(bp, "fans_due_night", now, untouched, bedroom_fans=[]) == []


def test_rendered_fans_due_precool_uses_the_ac_start_as_reference(bp):
    now = LOCK - timedelta(hours=2)
    started = LOCK - timedelta(hours=2, minutes=30)
    fans = [_S(MASTER, "on", 1, started - timedelta(hours=3)), _S(KIDS, "on", 21, started - timedelta(hours=3))]
    assert _due(bp, "fans_due_precool", now, fans) == [MASTER]                            # kids already at 21 %
    assert _due(bp, "fans_due_precool", now, [_S(MASTER, "on", 1, started + timedelta(minutes=1))]) == []   # touched after the start
    assert _due(bp, "fans_due_precool", now, fans, fan_assist_tonight=False) == []
    assert _due(bp, "fans_due_precool", now, fans, in_fan_assist_window=False) == []


def test_rendered_fans_unset_night_is_disjoint_from_due_and_fans_on_at_wake(bp):
    now = LOCK + timedelta(minutes=44)
    fixtures = [
        (dict(interlock_blocked=True), [_S(MASTER, "on", 1, BEFORE), _S(KIDS, "off", 21, BEFORE)]),
        (dict(), [_S(MASTER, "on", 1, BEFORE), _S(KIDS, "off", 21, BEFORE)]),               # due on the last tick → commanded, not reported (board R1-06)
        (dict(), [_S(MASTER, "unavailable", None, BEFORE), _S(KIDS, "off", 21, AFTER)]),
        (dict(interlock_blocked=True), [_S(MASTER, "on", 21, BEFORE), _S(KIDS, "off", 21, BEFORE)]),
    ]
    for ctx, states in fixtures:
        due, unset = _due(bp, "fans_due_night", now, states, **ctx), _due(bp, "fans_unset_night", now, states, **ctx)
        assert not (set(due) & set(unset)), (due, unset)
    assert _due(bp, "fans_unset_night", now, fixtures[0][1], interlock_blocked=True) == [KIDS]
    assert _due(bp, "fans_unset_night", now, fixtures[1][1]) == []
    assert _due(bp, "fans_unset_night", now, fixtures[2][1]) == [MASTER]                 # unavailable, untouched
    morning = datetime(2026, 9, 10, 7, 15, tzinfo=TZ)
    fans = [_S(MASTER, "on", 1, BEFORE), _S(KIDS, "off", 21, BEFORE)]
    assert _due(bp, "fans_on_at_wake", morning, fans) == [MASTER]
    assert _due(bp, "fans_on_at_wake", morning, fans, fans_at_wake="leave") == []
    assert _due(bp, "fans_on_at_wake", morning, fans, in_wake_window=False) == []


PIR = "binary_sensor.samuel_samuel_matthew_fanprotection"


def test_rendered_fans_unsafe_on_cuts_only_this_blueprints_own_in_flight_write(bp):
    """G1 (P1, board 20260909-151815 R2C2-05 ≡ R1C2-01 cross-family, + R1C2-02, R1C2-08):
    the cycle-1 cut (F3) fired on EVERY real tick while an interlock read `on`, and a
    person's deliberate `on` restarts the 120 s window each time it is cut — so a
    deliberate fan start was cut every minute for as long as the interlock stayed on,
    defeating the safety cutoff's own documented "manual override wins" contract
    (~/projects/ceiling-fan-hue-blueprint/fan_safety_motion_cutoff.yaml). The cut may now
    ONLY cancel a write THIS blueprint could have issued in the CURRENT window: gated on
    (in_fan_settle or in_fan_assist_window) — outside those windows the list is always
    [] — and keyed on the fan's ON-TRANSITION (last_changed, NOT last_updated — a speed
    change must never be cut) being newer than the active window's own reference
    (lock_ts while settling, ac_started_ts while assisting) AND within the last 120 s.
    Iterates bedroom_fans filtered to interlocked_fans (the "blocked" idiom) so a fan
    listed only in interlocked_fans, never commanded by this blueprint, is never
    touched (R1C2-08)."""
    now = datetime(2026, 9, 9, 21, 0, tzinfo=TZ)
    lock_ts = (now - timedelta(seconds=90)).timestamp()
    ac_started_ts = (now - timedelta(seconds=50)).timestamp()

    def render(states, bedroom_fans=(MASTER, KIDS), interlocked=(KIDS,), sensors=(PIR,),
               in_fan_settle=True, in_fan_assist_window=False):
        ctx = dict(bedroom_fans=list(bedroom_fans), interlocked_fans=list(interlocked),
                   fan_interlocks=list(sensors), in_fan_settle=in_fan_settle,
                   in_fan_assist_window=in_fan_assist_window, lock_ts=lock_ts,
                   ac_started_ts=ac_started_ts)
        return _reparse(_fan_env(now, states).from_string(_var_template(bp, "fans_unsafe_on")).render(**ctx).strip())

    # (a) settle window, fan came on 30 s ago (last_changed) after lock_ts, PIR on -> listed
    assert render([_S(KIDS, "on", last_changed=now - timedelta(seconds=30)), _S(PIR, "on")]) == [KIDS]
    # (b) same but 5 min ago -> not (older than 120 s)
    assert render([_S(KIDS, "on", last_changed=now - timedelta(minutes=5)), _S(PIR, "on")]) == []
    # (c) last_changed BEFORE lock_ts (a fan already on at the lock), still < 120 s old -> not
    before_lock = now - timedelta(seconds=95)
    assert render([_S(KIDS, "on", last_changed=before_lock), _S(PIR, "on")]) == []
    # (d) last_updated 30 s ago but last_changed 2 h ago (a speed change) -> not
    assert render([_S(KIDS, "on", last_updated=now - timedelta(seconds=30),
                       last_changed=now - timedelta(hours=2)), _S(PIR, "on")]) == []
    # (e) outside both windows -> [] even with a fresh on + PIR on
    assert render([_S(KIDS, "on", last_changed=now - timedelta(seconds=30)), _S(PIR, "on")],
                  in_fan_settle=False, in_fan_assist_window=False) == []
    # (f) assist window uses ac_started_ts as its own reference, not lock_ts
    assert render([_S(KIDS, "on", last_changed=now - timedelta(seconds=30)), _S(PIR, "on")],
                  in_fan_settle=False, in_fan_assist_window=True) == [KIDS]
    before_start = now - timedelta(seconds=55)
    assert render([_S(KIDS, "on", last_changed=before_start), _S(PIR, "on")],
                  in_fan_settle=False, in_fan_assist_window=True) == []
    # (g) a fan in interlocked_fans but not in bedroom_fans -> never (R1C2-08)
    assert render([_S(KIDS, "on", last_changed=now - timedelta(seconds=30)), _S(PIR, "on")],
                  bedroom_fans=(MASTER,)) == []
    # (h) PIR unavailable -> not (only an active `on` counts)
    assert render([_S(KIDS, "on", last_changed=now - timedelta(seconds=30)), _S(PIR, "unavailable")]) == []
    assert render([_S(KIDS, "on", last_changed=now - timedelta(seconds=30)), _S(PIR, "off")]) == []    # interlock clear
    both = [_S(MASTER, "on", last_changed=now - timedelta(seconds=30)),
            _S(KIDS, "on", last_changed=now - timedelta(seconds=30)), _S(PIR, "on")]
    assert render(both, interlocked=(KIDS,)) == [KIDS]        # MASTER isn't interlocked — never cut here
    assert render([_S(KIDS, "off", last_changed=now - timedelta(seconds=30)), _S(PIR, "on")]) == []    # fan not on
    assert render([_S(KIDS, "on", last_changed=now - timedelta(seconds=30))], sensors=()) == []        # no interlock configured


def test_fan_due_lists_are_defined_after_their_inputs_and_use_state_attr(text):
    for name in ("fans_due_precool", "fans_due_night", "fans_unset_night", "fans_on_at_wake"):
        assert _def_index(text, "settle_fan_due") < _def_index(text, name)
        assert _def_index(text, "in_fan_settle") < _def_index(text, name)
    assert "s.attributes.percentage" not in text          # Undefined would kill the variables step (board R1-04)


# --- v1.2.0 T5: fan step (before the AC dispatch), skipped notice, docs, instance, version ---

def _fan_service_calls(bp):
    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
    return [(c, s) for c, s in steps if str(s.get("service") or s.get("action")).startswith("fan.")]


def _live_recheck_templates(bp):
    """The two fan.turn_on calls' live re-check condition template, keyed by due list —
    fetched from the walker output rather than duplicated (board 20260909-151815 F5)."""
    tmpls = {}
    for conds, step in _fan_service_calls(bp):
        src = [t for t in conds if t.startswith("for_each=")]
        live = [t for t in conds if "states(repeat.item)" in t]
        if src and live:
            tmpls[src[0]] = live[0]
    return tmpls["for_each={{ fans_due_night }}"], tmpls["for_each={{ fans_due_precool }}"]


def test_fan_step_runs_before_the_ac_dispatch_and_rechecks_live_state_per_call(bp, text):
    calls = _fan_service_calls(bp)
    by_list = {}
    for conds, step in calls:
        src = [t for t in conds if t.startswith("for_each=")]
        assert len(src) == 1, "every fan call iterates one due list"
        by_list[src[0]] = (conds, step)
        assert any(t.strip() == "{{ is_real_trigger }}" for t in conds), "manual Run never actuates a fan"
        assert step["target"]["entity_id"] == "{{ repeat.item }}"
        assert step.get("continue_on_error") is True                                 # board R2-07
    assert set(by_list) == {"for_each={{ fans_unsafe_on }}", "for_each={{ fans_due_precool }}",
                             "for_each={{ fans_due_night }}", "for_each={{ fans_on_at_wake }}"}
    # F3 (board 20260909-151815): the unsafe-on cut runs FIRST, before any due-list write
    assert [t for t in calls[0][0] if t.startswith("for_each=")][0] == "for_each={{ fans_unsafe_on }}"
    unsafe = by_list["for_each={{ fans_unsafe_on }}"][1]
    assert unsafe["service"] == "fan.turn_off" and "data" not in unsafe
    pre_c, pre = by_list["for_each={{ fans_due_precool }}"]
    assert pre["service"] == "fan.turn_on" and pre["data"]["percentage"] == "{{ precool_fan_percentage | int }}"
    night_c, night = by_list["for_each={{ fans_due_night }}"]
    assert night["service"] == "fan.turn_on" and night["data"]["percentage"] == "{{ night_fan_percentage | int }}"
    for conds, ref in ((pre_c, "ac_started_ts"), (night_c, "lock_ts")):                 # live re-check (board R2-01)
        live = [t for t in conds if "states(repeat.item)" in t]
        assert len(live) == 1 and "last_updated" in live[0] and ref in live[0] and "interlock" in live[0]
    wake = by_list["for_each={{ fans_on_at_wake }}"][1]
    assert wake["service"] == "fan.turn_off" and "data" not in wake
    assert len(calls) == 4
    assert "fan.set_direction" not in text
    # F10 (board 20260909-151815): the fan step moved before STEP 5's AC/sensor validation
    # so an AC-unavailable tick still writes fans and reports the skipped notice — parsed
    # by top-level action-list order (F5), not string offsets (a moved comment can lie).
    steps = _top_level_steps(bp)
    fan_idx = next(i for i, s in enumerate(steps) if _has_for_each(s))
    vac_idx = next(i for i, s in enumerate(steps) if _has_stop_text(s, "Vacation active"))
    validation_idx = next(i for i, s in enumerate(steps) if _has_stop_text(s, "AC entity unavailable"))
    dispatch_idx = next(i for i, s in enumerate(steps) if _has_condition_text(s, "phase == 'DAY_OFF'"))
    assert vac_idx < fan_idx < validation_idx < dispatch_idx


def test_rendered_live_recheck_blocks_unsafe_commands(bp):
    """F5 (P2, board 20260909-151815 R2-06): pin the live re-check by RENDERING it (not
    token-matching), for both the night and pre-cool templates."""
    night_tmpl, precool_tmpl = _live_recheck_templates(bp)
    pir = "binary_sensor.pir"

    def render(tmpl, ref_key, ref_ts, states, **over):
        base = dict(interlocked_fans=[], fan_interlocks=[], interlock_clear_minutes=5,
                    night_fan_percentage=1, precool_fan_percentage=21, **{ref_key: ref_ts})
        base.update(over)
        return _reparse(_fan_env(LOCK, states).from_string(tmpl).render(repeat={"item": KIDS}, **base).strip())

    for tmpl, ref_key, target_key in ((night_tmpl, "lock_ts", "night_fan_percentage"),
                                       (precool_tmpl, "ac_started_ts", "precool_fan_percentage")):
        ref_ts = LOCK.timestamp()
        target = {"night_fan_percentage": 1, "precool_fan_percentage": 21}[target_key]
        before = LOCK - timedelta(hours=1)
        after = LOCK + timedelta(seconds=20)
        assert render(tmpl, ref_key, ref_ts, [_S(KIDS, "off", target, before), _S(pir, "on")],
                      interlocked_fans=[KIDS], fan_interlocks=[pir]) is False               # PIR on
        assert render(tmpl, ref_key, ref_ts, [_S(KIDS, "off", target, before),
                                               _S(pir, "off", last_changed=LOCK - timedelta(minutes=2))],
                      interlocked_fans=[KIDS], fan_interlocks=[pir]) is False               # cleared inside the hold
        assert render(tmpl, ref_key, ref_ts, [_S(KIDS, "off", target, after)]) is False     # touched after the reference
        assert render(tmpl, ref_key, ref_ts, [_S(KIDS, "on", target, before)]) is False     # already at target
        assert render(tmpl, ref_key, ref_ts, []) is False                                   # missing from the state machine
        assert render(tmpl, ref_key, ref_ts, [_S(KIDS, "off", target, before)]) is True     # clean


def test_fan_skipped_notice_fires_once_on_the_last_settle_tick(bp):
    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
    notices = [(c, s) for c, s in steps
               if (s.get("service") or s.get("action")) == "persistent_notification.create"
               and (s.get("data") or {}).get("notification_id") == "bedroom_precool_fan_skipped"]
    assert len(notices) == 1
    conds = notices[0][0]
    assert any("in_settle_last_tick" in t and "fans_unset_night | length > 0" in t and "enable_notifications" in t for t in conds)
    # G8 (R1C2-07, board 20260909-151815 cycle 2): the notice lives INSIDE the fan step
    # (same top-level index as the fan repeats), gated on is_real_trigger like every fan
    # write, and sits before STEP 5's AC/sensor validation stop — never a separate STEP
    # 7f that STEP 5 could pre-empt.
    assert any(t.strip() == "{{ is_real_trigger }}" for t in conds)
    steps_top = _top_level_steps(bp)
    fan_idx = next(i for i, s in enumerate(steps_top) if _has_for_each(s))
    notice_idx = next(i for i, s in enumerate(steps_top) if _has_notification_id(s, "bedroom_precool_fan_skipped"))
    validation_idx = next(i for i, s in enumerate(steps_top) if _has_stop_text(s, "AC entity unavailable"))
    assert notice_idx == fan_idx < validation_idx


def test_v110_version_docs_and_instance():
    inst = json.loads(PRECOOL_INSTANCE.read_text())
    i = inst["use_blueprint"]["input"]
    assert inst["alias"].endswith("v1.2.0")
    assert i["night_mode"] == "fan_only" and i["prechill_offset"] == 0.5
    assert i["bedroom_fans"] == ["fan.ceiling_fan_light_v2_2", "fan.ceiling_fan_light_v2"]
    assert i["interlocked_fans"] == ["fan.ceiling_fan_light_v2"]
    assert i["fan_interlocks"] == ["binary_sensor.samuel_samuel_matthew_fanprotection"]
    assert i["interlock_clear_minutes"] == 5                # cutoff hold 3 + 2 (spec §2.1)
    assert i["night_fans"] == "all" and i["fan_assist"] == "off" and i["fans_at_wake"] == "leave"
    assert i["night_fan_percentage"] == 1 and i["precool_fan_percentage"] == 21 and i["fan_settle_minutes"] == 45
    text = BP_PATH.read_text()
    assert "**Version: 1.2.0**" in text
    req = (ROOT / "requirements_bedroom_precool.md").read_text()
    for token in ("fan_only", "Night guard", "settle window", "last_updated", "odd/even", "interlock_clear_minutes"):
        assert token in req, token
    readme = (ROOT / "README.md").read_text()
    assert "Fan-Only Night Hold (v1.2.0)" in readme
