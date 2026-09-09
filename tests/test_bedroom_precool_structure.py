"""Structural pins for bedroom_precool.yaml (Bedroom Sleep Pre-Cool v1.0.3) and its
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
    assert bp["blueprint"]["name"].endswith("v1.0.3")
    assert "**Version: 1.0.3**" in bp["blueprint"]["description"]


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
    assert inst["alias"].endswith("v1.0.3")


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


# --- v1.1.0 fan coordination (design 2026-09-09, board 20260909-130652) --------------

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
    env.filters["as_timestamp"] = env.globals["as_timestamp"]     # HA offers it as a filter too
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
               enable_fan_control=True, ac_fan_modes=["auto", "low", "medium", "high"])
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
    return _render_chain(bp, WINDOW_CHAIN, now, _v110_ctx(now_tod=now.strftime("%H:%M:%S"), **over))


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


GUARD_CHAIN = ["fan_only_mode", "night_phase", "since_ac_start_min", "guard_due", "guard_settle_due",
               "settle_mode_due", "settle_setpoint_due", "settle_fan_due"]


def _guard(bp, now, **over):
    return _render_chain(bp, GUARD_CHAIN, now, _v110_ctx(now_tod=now.strftime("%H:%M:%S"), **over))


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
    assert _guard(bp, t, **base, current_setpoint=19.5)["settle_setpoint_due"] is False        # a deep-night nudge, left alone
    assert _guard(bp, t, **base, current_setpoint_known=False)["settle_setpoint_due"] is False
    assert _guard(bp, t, **base, current_fan="high")["settle_fan_due"] is True
    assert _guard(bp, t, **base, current_fan="unknown")["settle_fan_due"] is False             # null read (board R1-02)
    assert _guard(bp, t, **base, enable_fan_control=False, current_fan="high")["settle_fan_due"] is False
    late = _guard(bp, t, **dict(base, ac_started_ts=(t - timedelta(minutes=16)).timestamp()), current_hvac_mode="heat")
    assert late["guard_settle_due"] is False and late["settle_mode_due"] is False              # window closed
    assert _guard(bp, t, **dict(base, night_mode="ac_hold"), current_hvac_mode="heat")["settle_mode_due"] is False
    assert _guard(bp, t, **dict(base, phase="PRECOOL"), current_hvac_mode="heat")["settle_mode_due"] is False


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


# --- v1.1.0 T2: BEDTIME_LOCK fan-only branch (park, then off unless already over the band) ---

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
