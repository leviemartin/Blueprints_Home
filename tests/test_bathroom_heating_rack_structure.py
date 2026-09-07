"""Structural + rendered-logic pins for bathroom_heating_rack.yaml (Bathroom Heating Rack v2.0.0).

Run: cd ~/AI/projects/Blueprints_Home && \
     ~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q
"""
import ast
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment

ROOT = Path(__file__).resolve().parent.parent
BP_PATH = ROOT / "bathroom_heating_rack.yaml"
INSTANCE_PATH = ROOT / "deploy" / "bathroom_heating_rack_1776551429917.json"
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy-blueprint.sh"
HA_BP_PATH = "leviemartin/bathroom_heating_rack.yaml"


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


def var_blocks(bp):
    """Every top-level `variables:` step of the action, in file order."""
    return [step["variables"] for step in bp["action"] if "variables" in step]


def get_var(bp, name):
    for block in var_blocks(bp):
        if name in block:
            return block[name]
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


def choose_steps(bp):
    return [s for s in bp["action"] if "choose" in s]


def service_of(seq):
    """The first `service:` name inside a sequence (searching nested dicts)."""
    for d in walk(seq):
        if "service" in d:
            return d["service"]
    return None


# ---------------------------------------------------------------- render harness
NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)   # a Tuesday


class _State:
    def __init__(self, state, minutes_ago=0.0, attrs=None):
        self.state = state
        self.minutes_ago = minutes_ago
        self.last_changed = NOW - timedelta(minutes=minutes_ago)
        self.attributes = attrs or {}


class _States:
    """HA `states`: callable -> state string; item access -> state object or None."""

    def __init__(self, table):
        self.table = table

    def __call__(self, eid):
        s = self.table.get(eid)
        return s.state if s else "unknown"

    def __getitem__(self, eid):
        return self.table.get(eid)

    def rebase(self, when):
        """Make every `minutes_ago` relative to `when` (a test that moves `now` must not turn
        "boost 5 min ago" into "boost 7 h ago")."""
        for s in self.table.values():
            s.last_changed = when - timedelta(minutes=s.minutes_ago)
        return self


def parse(s):
    s = s.strip()
    try:
        return ast.literal_eval(s)
    except (ValueError, SyntaxError):
        return s


def as_datetime(v):
    return v if isinstance(v, datetime) else datetime.fromisoformat(str(v).strip())


def make_env(states, when):
    env = Environment()
    env.tests["match"] = lambda v, pattern: re.match(pattern, str(v)) is not None   # HA's `match` test

    def today_at(hhmmss):
        parts = [int(p) for p in str(hhmmss).split(":")] + [0, 0]
        return when.replace(hour=parts[0], minute=parts[1], second=parts[2], microsecond=0)

    def expand(ids):
        ids = [ids] if isinstance(ids, str) else list(ids)
        return [states[e] for e in ids if states[e]]

    env.globals.update(
        states=states,
        now=lambda: when,
        today_at=today_at,
        timedelta=timedelta,
        as_datetime=as_datetime,
        expand=expand,
        is_state=lambda eid, s: states(eid) == s,
        state_attr=lambda eid, a: (states[eid].attributes.get(a) if states[eid] else None),
    )
    return env


def render_vars(bp, ctx, states, upto, when=NOW):
    """Render every action-level `variables:` template in file order up to and including `upto`."""
    env = make_env(states.rebase(when), when)
    out = dict(ctx)
    for block in var_blocks(bp):
        for name, tpl in block.items():
            out[name] = parse(env.from_string(str(tpl)).render(**out))
            if name == upto:
                return out
    raise KeyError(upto)


def render_tpl(bp, tpl, states, when=NOW, **ctx):
    env = make_env(states.rebase(when), when)
    return parse(env.from_string(str(tpl)).render(**ctx))


WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"]


def base_ctx(**over):
    ctx = dict(
        entity_climate="climate.rack", sensor_bathroom_temp="sensor.t", entity_fan="light.fan",
        entity_vacation=["input_boolean.vac"], entity_boost="input_boolean.boost",
        boost_runtime_min=30, boost_target_temp=26, idle_setpoint=7, comfort_floor_delta=1.0,
        warmup_base_min=10, warmup_per_degree_min=5, warmup_min_minutes=10, warmup_max_minutes=60,
        enable_notifications=True, notify_targets=[],
        morning_a_days=WEEKDAYS, morning_a_target_warm="06:45:00", morning_a_hold_until="08:00:00",
        morning_a_target_temp=23,
        morning_b_days=[], morning_b_target_warm="08:30:00", morning_b_hold_until="10:00:00",
        morning_b_target_temp=23,
        evening_a_days=[], evening_a_target_warm="19:15:00", evening_a_hold_until="20:30:00",
        evening_a_target_temp=24,
        evening_b_days=[], evening_b_target_warm="20:30:00", evening_b_hold_until="22:00:00",
        evening_b_target_temp=23,
        trigger={"id": "periodic"},
    )
    ctx.update(over)
    return ctx


def world(**kw):
    table = {
        "sensor.t": _State("22.0"),
        "climate.rack": _State("unknown", attrs={"temperature": 7.0, "current_temperature": 23.4,
                                                 "target_temp_step": 1.0}),
        "light.fan": _State("off", minutes_ago=180),
        "input_boolean.vac": _State("off", minutes_ago=600),
        "input_boolean.boost": _State("off", minutes_ago=600),
    }
    table.update(kw)
    return _States(table)


def at(hhmm, day=NOW):
    hh, mm = map(int, hhmm.split(":"))
    return day.replace(hour=hh, minute=mm, second=0, microsecond=0)


def decide(bp, ctx, w, when=NOW):
    out = render_vars(bp, ctx, w, "active_priority", when)
    return out["active_priority"], out["desired_setpoint"]


# ---------------------------------------------------------------- structure pins

def test_version_bumped(bp):
    assert bp["blueprint"]["name"] == "Bathroom Heating Rack v2.0.0"
    assert bp["blueprint"]["description"].lstrip().startswith("**Version: 2.0.0**")
    assert "comfort floor" in bp["blueprint"]["description"]


EXPECTED_INPUTS = {
    "heating_climate", "bathroom_temp_sensor", "fan_switch", "vacation_off", "boost_toggle",
    "boost_target_temp", "boost_runtime_min", "idle_setpoint", "comfort_floor_delta",
    "morning_a_days", "morning_a_target_warm", "morning_a_hold_until", "morning_a_target_temp",
    "morning_b_days", "morning_b_target_warm", "morning_b_hold_until", "morning_b_target_temp",
    "evening_a_days", "evening_a_target_warm", "evening_a_hold_until", "evening_a_target_temp",
    "evening_b_days", "evening_b_target_warm", "evening_b_hold_until", "evening_b_target_temp",
    "warmup_base_min", "warmup_per_degree_min", "warmup_min_minutes", "warmup_max_minutes",
    "enable_notifications", "notify_targets",
}


def test_input_schema_exact_keys(inputs):
    assert set(inputs) == EXPECTED_INPUTS


def test_removed_inputs_absent(inputs):
    for k in ("hall_motion", "stairs_motion", "enable_predictive_motion"):
        assert k not in inputs


def test_selectors_and_defaults(inputs):
    cf = inputs["comfort_floor_delta"]
    assert cf["default"] == 1.0
    assert cf["selector"]["number"] == {"min": 0, "max": 3, "step": 0.5, "unit_of_measurement": "°C"}
    assert inputs["fan_switch"]["selector"]["entity"]["domain"] == "light"
    assert inputs["vacation_off"]["default"] == []
    assert inputs["vacation_off"]["selector"]["entity"] == {"domain": "input_boolean", "multiple": True}
    assert inputs["boost_toggle"]["selector"]["entity"]["domain"] == "input_boolean"
    assert "default" not in inputs["boost_toggle"]
    assert inputs["idle_setpoint"]["default"] == 7
    assert inputs["warmup_min_minutes"]["default"] == 10
    assert inputs["warmup_max_minutes"]["default"] == 60
    assert inputs["enable_notifications"]["default"] is True
    assert inputs["notify_targets"]["default"] == []
    assert inputs["notify_targets"]["selector"] == {"text": {"multiple": True}}
    for slot in ("morning_a", "morning_b", "evening_a", "evening_b"):
        assert inputs[f"{slot}_target_temp"]["selector"]["number"]["step"] == 0.5
        assert inputs[f"{slot}_target_warm"]["selector"] == {"time": {}}
        assert inputs[f"{slot}_hold_until"]["selector"] == {"time": {}}
    assert inputs["morning_a_days"]["default"] == WEEKDAYS
    assert inputs["evening_a_days"]["default"] == []


def test_every_input_has_a_description(inputs):
    missing = [k for k, v in inputs.items() if not str(v.get("description", "")).strip()]
    assert missing == []


def test_variable_mappings(bp):
    v = bp["variables"]
    assert v["entity_climate"] == _Input("heating_climate")
    assert v["sensor_bathroom_temp"] == _Input("bathroom_temp_sensor")
    assert v["entity_fan"] == _Input("fan_switch")
    assert v["entity_vacation"] == _Input("vacation_off")
    assert v["entity_boost"] == _Input("boost_toggle")
    assert v["comfort_floor_delta"] == _Input("comfort_floor_delta")
    assert v["notify_targets"] == _Input("notify_targets")
    for k in ("sensor_hall_motion", "sensor_stairs_motion", "enable_predictive_motion"):
        assert k not in v
    # every input except the entity roles is passed through under its own name
    passthrough = EXPECTED_INPUTS - {"heating_climate", "bathroom_temp_sensor", "fan_switch", "vacation_off", "boost_toggle"}
    for k in passthrough:
        assert v[k] == _Input(k), k


def test_mode_restart(bp):
    assert bp["mode"] == "restart"
    assert bp["max_exceeded"] == "silent"


def test_trigger_roster(bp):
    trig = {t["id"]: t for t in bp["trigger"]}
    assert list(trig) == ["periodic", "boost_change", "vacation_change", "fan_change", "ha_start", "climate_lost", "temp_lost"]
    assert trig["periodic"] == {"platform": "time_pattern", "minutes": "/1", "id": "periodic"}
    assert trig["boost_change"] == {"platform": "state", "entity_id": _Input("boost_toggle"), "to": ["on", "off"], "id": "boost_change"}
    assert trig["vacation_change"] == {"platform": "state", "entity_id": _Input("vacation_off"), "to": ["on", "off"], "id": "vacation_change"}
    assert trig["fan_change"] == {"platform": "state", "entity_id": _Input("fan_switch"), "to": ["on", "off"], "id": "fan_change"}
    assert trig["ha_start"] == {"platform": "homeassistant", "event": "start", "id": "ha_start"}
    assert trig["climate_lost"] == {"platform": "state", "entity_id": _Input("heating_climate"), "to": "unavailable",
                                    "for": {"minutes": 5}, "id": "climate_lost"}
    assert trig["temp_lost"] == {"platform": "state", "entity_id": _Input("bathroom_temp_sensor"), "to": ["unavailable", "unknown"],
                                 "for": {"minutes": 10}, "id": "temp_lost"}


def test_action_shape(bp):
    kinds = [step_kind(s) for s in bp["action"]]
    assert kinds == ["variables", "variables", "choose", "variables", "choose", "choose", "choose", "choose", "choose", "choose"]
    chooses = choose_steps(bp)
    # climate validation: unavailable → create + (push on the edge) + stop; available → dismiss
    unavailable, available = chooses[0]["choose"]
    assert branch_cond(unavailable) == "{{ states[entity_climate] is none or states(entity_climate) == 'unavailable' }}"
    assert service_of(unavailable["sequence"]) == "persistent_notification.create"
    assert unavailable["sequence"][-1] == {"stop": "Climate entity unavailable"}
    assert branch_cond(available) == "{{ states[entity_climate] is not none and states(entity_climate) != 'unavailable' }}"
    assert available["sequence"] == [{"service": "persistent_notification.dismiss", "continue_on_error": True,
                                      "data": {"notification_id": "heating_rack_climate_unavailable"}}]
    assert service_of(chooses[1]["choose"][0]["sequence"]) == "climate.set_hvac_mode"
    assert service_of(chooses[2]["choose"][0]["sequence"]) == "climate.set_temperature"
    # room-sensor warning sits AFTER the climate calls
    lost, back = chooses[3]["choose"]
    assert branch_cond(lost) == "{{ not indoor_temp_has_primary }}"
    assert service_of(lost["sequence"]) == "persistent_notification.create"
    assert branch_cond(back) == "{{ indoor_temp_has_primary }}"
    assert back["sequence"] == [{"service": "persistent_notification.dismiss", "continue_on_error": True,
                                 "data": {"notification_id": "heating_rack_sensor_warning"}}]
    assert service_of(chooses[4]["choose"][0]["sequence"]) == "persistent_notification.create"
    assert service_of(chooses[4]["choose"][1]["sequence"]) == "persistent_notification.dismiss"
    assert service_of(chooses[5]["choose"][0]["sequence"]) == "persistent_notification.create"
    assert service_of(chooses[6]["choose"][0]["sequence"]) == "input_boolean.turn_off"
    for c in chooses:
        assert "default" not in c


def test_boost_expiry_is_the_last_step(bp):
    # the turn_off restarts the automation (mode: restart); anything after it would be aborted
    last = bp["action"][-1]
    assert branch_cond(last["choose"][0]) == "{{ boost_expired }}"
    assert service_of(last["choose"][0]["sequence"]) == "input_boolean.turn_off"
    kinds = [service_of(s["choose"][0]["sequence"]) if "choose" in s else None for s in bp["action"]]
    assert kinds.index("climate.set_temperature") < kinds.index("input_boolean.turn_off")


def test_outage_pushes_are_edge_gated(bp):
    chooses = choose_steps(bp)
    # climate-unavailable branch: climate_lost push + the temp_lost push it would otherwise swallow; sensor branch: temp_lost only
    for idx, trigger_ids in ((0, ["climate_lost", "temp_lost"]), (3, ["temp_lost"])):
        seq = chooses[idx]["choose"][0]["sequence"]
        nested = [d for d in seq if "choose" in d]
        assert len(nested) == len(trigger_ids)
        for block, trigger_id in zip(nested, trigger_ids):
            (branch,) = block["choose"]
            assert branch_cond(branch) == f"{{{{ trigger.id | default('') == '{trigger_id}' }}}}"
            assert any("repeat" in d for d in walk(branch["sequence"]))
            assert "default" not in block
    assert chooses[0]["choose"][0]["sequence"][-1] == {"stop": "Climate entity unavailable"}


def test_no_preset_machinery(bp):
    names = [n for b in var_blocks(bp) for n in b]
    assert not any("preset" in n for n in names)
    assert all(d.get("service") != "climate.set_preset_mode" for d in walk(bp["action"]))
    assert "preset" not in BP_PATH.read_text().split("action:", 1)[1]


def test_no_predictive_motion_remnants(bp):
    names = [n for b in var_blocks(bp) for n in b]
    assert not any("motion" in n for n in names)
    assert "motion" not in BP_PATH.read_text().split("domain: automation", 1)[1]


def test_weekday_locale_safe(bp):
    tpl = norm(get_var(bp, "today_dow"))
    assert tpl == "{{ ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'][now().weekday()] }}"
    assert "strftime('%a')" not in BP_PATH.read_text()


@pytest.mark.parametrize("slot,prefix", [("morning_a", "ma"), ("morning_b", "mb"), ("evening_a", "ea"), ("evening_b", "eb")])
def test_slot_templates(bp, slot, prefix):
    assert norm(get_var(bp, f"{prefix}_hold_until_dt")) == norm(
        f"{{% set w = today_at({slot}_target_warm) %}}{{% set h = today_at({slot}_hold_until) %}}"
        "{{ h + timedelta(days=1) if h <= w else h }}")
    assert norm(get_var(bp, f"{prefix}_target_dev")) == norm(
        f"{{{{ [setpoint_max | float, [setpoint_min | float, (((({slot}_target_temp | float) / (setpoint_step | float) + 0.501) | int) * (setpoint_step | float))] | max] | min | round(2) }}}}")
    assert norm(get_var(bp, f"{prefix}_heating")) == norm(
        f"{{{{ not boost_active and current_hvac_mode_normalized == 'heat_cool' and (current_setpoint | float - {prefix}_target_dev | float) | abs < 0.1 }}}}")
    assert norm(get_var(bp, f"{prefix}_open_dt")) == norm(
        f"{{{{ as_datetime({prefix}_target_warm_dt) - timedelta(minutes=(warmup_max_minutes | int if {prefix}_heating else {prefix}_warmup_min | int)) }}}}")
    assert norm(get_var(bp, f"{prefix}_in_window")) == norm(
        f"{{{{ {prefix}_in_days and as_datetime({prefix}_open_dt) <= as_datetime(now_dt) "
        f"and as_datetime(now_dt) < as_datetime({prefix}_hold_until_dt) }}}}")
    assert norm(get_var(bp, f"{prefix}_floor")) == norm(
        f"{{{{ ({slot}_target_temp | float - comfort_floor_delta | float + (0.5 if {prefix}_heating else 0)) | round(2) }}}}")
    assert norm(get_var(bp, f"{prefix}_active")) == norm(
        f"{{{{ {prefix}_in_window and (not indoor_temp_has_primary or indoor_temp | float | round(2) < {prefix}_floor | float) }}}}")
    assert norm(get_var(bp, f"{prefix}_auto_start_dt")) == norm(
        f"{{{{ as_datetime({prefix}_target_warm_dt) - timedelta(minutes={prefix}_warmup_min | int) }}}}")


def test_setpoint_rounding_template(bp):
    assert norm(get_var(bp, "desired_setpoint")) == norm(
        "{% if desired_setpoint_raw == 'none' %}none{% else %}"
        "{{ [setpoint_max | float, [setpoint_min | float, ((((desired_setpoint_raw | float) / (setpoint_step | float) + 0.501) | int) * (setpoint_step | float))] | max] | min | round(2) }}{% endif %}")
    assert norm(get_var(bp, "idle_setpoint_dev")) == norm(
        "{{ [setpoint_max | float, [setpoint_min | float, ((((idle_setpoint | float) / (setpoint_step | float) + 0.501) | int) * (setpoint_step | float))] | max] | min | round(2) }}")
    assert norm(get_var(bp, "setpoint_min")) == "{{ state_attr(entity_climate, 'min_temp') | float(7) }}"
    assert norm(get_var(bp, "setpoint_max")) == "{{ state_attr(entity_climate, 'max_temp') | float(30) }}"
    assert norm(get_var(bp, "notify_list")) == norm(
        "{{ (notify_targets if (notify_targets is iterable and notify_targets is not string) else ([notify_targets] if notify_targets else [])) | select('match', '^notify[.][a-z0-9_]+$') | list }}")
    assert "floor_hysteresis" not in BP_PATH.read_text()
    assert norm(get_var(bp, "setpoint_step")) == norm(
        "{% set s = state_attr(entity_climate, 'target_temp_step') | float(0) %}{{ s if s > 0 else 0.5 }}")


def test_service_calls_idempotent(bp):
    chooses = choose_steps(bp)
    assert branch_cond(chooses[1]["choose"][0]) == "{{ current_hvac_mode_normalized != desired_mode }}"
    assert branch_cond(chooses[2]["choose"][0]) == norm(
        "{{ desired_setpoint != 'none' and (current_setpoint | float - desired_setpoint | float) | abs > 0.1 }}")
    call = chooses[2]["choose"][0]["sequence"][0]
    assert call["data"] == {"temperature": "{{ desired_setpoint | float }}"}
    assert call["target"] == {"entity_id": "{{ entity_climate }}"}


def test_climate_calls_continue_on_error(bp):
    chooses = choose_steps(bp)
    for idx in (1, 2):
        call = chooses[idx]["choose"][0]["sequence"][0]
        assert call["continue_on_error"] is True, call["service"]


def test_notify_fanout_continue_on_error(bp):
    repeats = [d["repeat"] for d in walk(bp["action"]) if "repeat" in d]
    assert len(repeats) == 4
    assert "{{ notify_targets }}" not in BP_PATH.read_text().split("action:", 1)[1]
    for r in repeats:
        assert r["for_each"] == "{{ notify_list }}"
        (call,) = r["sequence"]
        assert call["service"] == "{{ repeat.item }}"
        assert call["continue_on_error"] is True
    for d in walk(bp["action"]):
        if str(d.get("service", "")).startswith("persistent_notification."):
            assert d.get("continue_on_error") is True, d["service"]


def test_warmup_notification_edge_shape(bp):
    branch_on, branch_off = choose_steps(bp)[4]["choose"]
    assert branch_cond(branch_on) == norm(
        "{{ enable_notifications and desired_setpoint != 'none' and desired_setpoint | float > idle_setpoint_dev | float + 0.1 "
        "and current_setpoint | float <= idle_setpoint_dev | float + 0.1 }}")
    ids = [d["notification_id"] for d in walk(branch_on["sequence"]) if "notification_id" in d]
    assert ids == ["heating_rack_warmup_started"]
    assert any("repeat" in d for d in walk(branch_on["sequence"]))
    assert branch_cond(branch_off) == norm(
        "{{ desired_setpoint != 'none' and desired_setpoint | float <= idle_setpoint_dev | float + 0.1 "
        "and current_setpoint | float > idle_setpoint_dev | float + 0.1 }}")
    assert branch_off["sequence"] == [{"service": "persistent_notification.dismiss", "continue_on_error": True,
                                       "data": {"notification_id": "heating_rack_warmup_started"}}]


def test_at_target_notification_removed(bp):
    text = BP_PATH.read_text()
    assert "heating_rack_target_reached" not in text
    assert "At Target" not in text


def test_debug_block_manual_only(bp):
    branch = choose_steps(bp)[5]["choose"][0]
    assert branch_cond(branch) == "{{ trigger.id | default('manual') == 'manual' }}"
    ids = [d["notification_id"] for d in walk(branch["sequence"]) if "notification_id" in d]
    assert ids == ["heating_rack_debug"]


def test_no_bare_boolean_text(bp):
    for block in var_blocks(bp):
        for name, tpl in block.items():
            s = norm(tpl)
            assert not re.search(r"%\}\s*(true|false)\s*\{%", s, re.I), name
            assert not re.search(r"%\}\s*(true|false)\s*$", s, re.I), name


def test_no_bare_condition_steps_anywhere(bp):
    for step in bp["action"]:
        assert step_kind(step) != "condition"


# ---------------------------------------------------------------- rendered logic

def test_today_dow_rows(bp):
    assert render_tpl(bp, get_var(bp, "today_dow"), world()) == "tue"
    assert render_tpl(bp, get_var(bp, "today_dow"), world(), when=NOW + timedelta(days=5)) == "sun"


@pytest.mark.parametrize("raw,step,expected", [
    (23.5, 1.0, 24.0), (23.5, 0.5, 23.5), (23.2, 1.0, 23.0), (22.5, 1.0, 23.0),
    (7.0, 1.0, 7.0), (7.0, 0.5, 7.0), (26.0, 1.0, 26.0),
    # non-dyadic rows (0.1 grid): raw/step is not binary-exact — the epsilon nudge must hold
    (22.3, 0.1, 22.3), (21.7, 0.1, 21.7), (22.35, 0.1, 22.4), (22.64, 0.1, 22.6), (22.65, 0.1, 22.7),
    (22.9, 0.1, 22.9), (22.4, 0.1, 22.4),
])
def test_setpoint_rounding_rows(bp, raw, step, expected):
    got = render_tpl(bp, get_var(bp, "desired_setpoint"), world(), desired_setpoint_raw=raw, setpoint_step=step,
                     setpoint_min=7.0, setpoint_max=30.0)
    assert got == pytest.approx(expected)


@pytest.mark.parametrize("raw,lo,hi,expected", [(5.0, 7.0, 30.0, 7.0), (31.0, 7.0, 30.0, 30.0), (26.0, 7.0, 25.0, 25.0), (24.0, 7.0, 30.0, 24.0)])
def test_setpoint_clamped_to_device_range(bp, raw, lo, hi, expected):
    got = render_tpl(bp, get_var(bp, "desired_setpoint"), world(), desired_setpoint_raw=raw, setpoint_step=1.0,
                     setpoint_min=lo, setpoint_max=hi)
    assert got == pytest.approx(expected)


@pytest.mark.parametrize("idle,step,attrs,expected", [
    (7, 1.0, {}, 7.0),
    (7.5, 1.0, {}, 8.0),          # off-grid idle is written as 8.0 — every idle comparison must use this value
    (7.5, 0.5, {}, 7.5),
    (5, 1.0, {}, 7.0),            # selector allows 5, device minimum is 7 → clamped
    (5, 1.0, {"min_temp": 5.0}, 5.0),
    (7, 1.0, {"min_temp": None}, 7.0),
])
def test_idle_setpoint_dev_rows(bp, idle, step, attrs, expected):
    a = {"temperature": 7.0, "current_temperature": 23.4, "target_temp_step": step, "min_temp": 7.0, "max_temp": 30.0}
    a.update(attrs)
    out = render_vars(bp, base_ctx(idle_setpoint=idle), world(**{"climate.rack": _State("unknown", attrs=a)}), "idle_setpoint_dev")
    assert out["idle_setpoint_dev"] == expected


def test_setpoint_range_defaults_when_attrs_missing(bp):
    out = render_vars(bp, base_ctx(), world(), "idle_setpoint_dev")
    assert (out["setpoint_min"], out["setpoint_max"], out["idle_setpoint_dev"]) == (7.0, 30.0, 7.0)


@pytest.mark.parametrize("targets,expected", [
    (["notify.mobile_app_martin_fold"], ["notify.mobile_app_martin_fold"]),
    (["notify.mobile_app_martin_fold", "mobile_app_x", "notify.Bad-Name", "script.foo", "notify.a b"], ["notify.mobile_app_martin_fold"]),
    ([], []),
    ("notify.mobile_app_martin_fold", ["notify.mobile_app_martin_fold"]),   # scalar guard (ventilator parity)
])
def test_notify_list_filters_names(bp, targets, expected):
    assert render_vars(bp, base_ctx(notify_targets=targets), world(), "notify_list")["notify_list"] == expected


def _rack(setpoint, step=1.0, current=23.4):
    return {"climate.rack": _State("unknown", attrs={"temperature": setpoint, "current_temperature": current, "target_temp_step": step})}


@pytest.mark.parametrize("indoor,active", [
    (23.0, True),     # at the line but this slot is heating → deadband keeps it active
    (23.4, True),
    (23.5, False),    # line + 0.5 → released
    (22.9, True),
])
def test_comfort_floor_hysteresis_rows(bp, indoor, active):
    # the device holds this slot's setpoint (24) → the slot is heating: floor 23.5
    out = render_vars(bp, _evening_ctx(), world(**_rack(24.0), **{"sensor.t": _State(str(indoor))}), "ea_active", at("19:30"))
    assert (out["ea_target_dev"], out["ea_heating"], out["ea_floor"]) == (24.0, True, 23.5)
    assert out["ea_active"] is active
    # setpoint at idle: strict floor
    out = render_vars(bp, _evening_ctx(), world(**{"sensor.t": _State(str(indoor))}), "ea_active", at("19:30"))
    assert (out["ea_heating"], out["ea_floor"]) == (False, 23.0)
    assert out["ea_active"] is (indoor < 23.0)


def test_deadband_is_keyed_to_the_slot_not_any_raised_setpoint(bp):
    # boost (26) expiring inside the evening window at 23.3 °C must hand over to idle, not to P4_evening
    out = render_vars(bp, _evening_ctx(), world(**_rack(26.0), **{"sensor.t": _State("23.3")}), "active_priority", at("19:30"))
    assert (out["ea_heating"], out["ea_floor"], out["ea_active"]) == (False, 23.0, False)
    assert out["active_priority"] == "P6_idle"
    # a manual/other setpoint of 8.0 does not widen the floor either
    out = render_vars(bp, _evening_ctx(), world(**_rack(8.0), **{"sensor.t": _State("23.2")}), "ea_active", at("19:30"))
    assert (out["ea_heating"], out["ea_active"]) == (False, False)


def test_opening_edge_latches_while_heating(bp):
    # indoor 22.0 → ΔT 2 → lead 20 → auto_start 18:55. A warmer report (22.4 → lead 18 → 18:57) must not
    # close a window that is already heating; the latched edge is target_warm − warmup_max = 18:15.
    out = render_vars(bp, _evening_ctx(), world(**{"sensor.t": _State("22.4")}), "ea_active", at("18:56"))
    assert as_datetime(out["ea_auto_start_dt"]).strftime("%H:%M") == "18:57"
    assert (out["ea_heating"], out["ea_in_window"], out["ea_active"]) == (False, False, False)
    out = render_vars(bp, _evening_ctx(), world(**_rack(24.0), **{"sensor.t": _State("22.4")}), "ea_active", at("18:56"))
    assert as_datetime(out["ea_open_dt"]).strftime("%H:%M") == "18:15"
    assert (out["ea_heating"], out["ea_in_window"], out["ea_active"]) == (True, True, True)
    # but not before the latched edge, and never past hold_until
    out = render_vars(bp, _evening_ctx(), world(**_rack(24.0), **{"sensor.t": _State("22.4")}), "ea_active", at("18:10"))
    assert out["ea_in_window"] is False
    out = render_vars(bp, _evening_ctx(), world(**_rack(24.0), **{"sensor.t": _State("22.4")}), "ea_active", at("20:30"))
    assert out["ea_in_window"] is False


def test_floor_suspended_without_room_sensor(bp):
    # room sensor dead, rack's own sensor 23.4 (> floor 23.0): the slot still heats on schedule
    w = world(**{"sensor.t": _State("unavailable")})
    out = render_vars(bp, _evening_ctx(), w, "active_priority", at("19:30"))
    assert (out["indoor_temp_has_primary"], out["indoor_temp"]) == (False, 23.4)
    assert (out["ea_warmup_min"], out["ea_active"], out["active_priority"], out["desired_setpoint"]) == (13, True, "P4_evening", 24.0)
    # both sources gone: 20 °C lead, still on schedule
    w = world(**{"sensor.t": _State("unavailable"), "climate.rack": _State("unknown", attrs={"temperature": 7.0, "target_temp_step": 1.0})})
    out = render_vars(bp, _evening_ctx(), w, "active_priority", at("19:30"))
    assert (out["indoor_temp_both_unavailable"], out["indoor_temp"], out["ea_active"], out["active_priority"]) == (True, 20, True, "P4_evening")
    # with the sensor back at 23.4 the same slot is satisfied
    out = render_vars(bp, _evening_ctx(), world(**{"sensor.t": _State("23.4")}), "active_priority", at("19:30"))
    assert (out["ea_active"], out["active_priority"]) == (False, "P6_idle")


def test_comfort_floor_non_dyadic_rows(bp):
    # target 23.5, delta 0.5 → floor 23.0; indoor 22.9 from a "22.9" state string
    ctx = _evening_ctx(evening_a_target_temp=23.5, comfort_floor_delta=0.5)
    out = render_vars(bp, ctx, world(**{"sensor.t": _State("22.9")}), "ea_active", at("19:30"))
    assert (out["ea_floor"], out["ea_active"]) == (23.0, True)
    out = render_vars(bp, ctx, world(**{"sensor.t": _State("23.0")}), "ea_active", at("19:30"))
    assert out["ea_active"] is False


def test_setpoint_rounding_vacation_passthrough(bp):
    assert render_tpl(bp, get_var(bp, "desired_setpoint"), world(), desired_setpoint_raw="none", setpoint_step=1.0,
                      setpoint_min=7.0, setpoint_max=30.0) == "none"


@pytest.mark.parametrize("attr,expected", [(1.0, 1.0), (0.5, 0.5), (None, 0.5), (0, 0.5), ("1", 1.0)])
def test_setpoint_step_rows(bp, attr, expected):
    attrs = {"temperature": 7.0, "current_temperature": 23.4}
    if attr is not None:
        attrs["target_temp_step"] = attr
    w = world(**{"climate.rack": _State("unknown", attrs=attrs)})
    assert render_vars(bp, base_ctx(), w, "setpoint_step")["setpoint_step"] == expected


@pytest.mark.parametrize("indoor,floor,expected_min,expected_start", [
    (20.0, 10, 25, "06:20"),   # ΔT 3 → 10 + 5·3
    (22.5, 10, 12, "06:33"),   # ΔT 0.5 → 12.5 → int 12
    (22.5, 28, 28, "06:17"),   # floor wins (the old instance value)
    (10.0, 10, 60, "05:45"),   # cap 60
    (25.0, 10, 10, "06:35"),   # ΔT clamps at 0 → floor
])
def test_warmup_lead_rows(bp, indoor, floor, expected_min, expected_start):
    ctx = base_ctx(warmup_min_minutes=floor)
    out = render_vars(bp, ctx, world(**{"sensor.t": _State(str(indoor))}), "ma_auto_start_dt")
    assert out["ma_warmup_min"] == expected_min
    assert as_datetime(out["ma_auto_start_dt"]).strftime("%H:%M") == expected_start


def _evening_ctx(**over):
    return base_ctx(evening_a_days=["tue"], **over)


@pytest.mark.parametrize("indoor,delta,active,priority,setpoint", [
    (22.0, 1.0, True, "P4_evening", 24.0),
    (22.9, 1.0, True, "P4_evening", 24.0),
    (23.0, 1.0, False, "P6_idle", 7.0),     # at the floor line → satisfied
    (23.9, 0.0, True, "P4_evening", 24.0),  # delta 0: heat until target
    (24.0, 0.0, False, "P6_idle", 7.0),
    (21.0, 3.0, False, "P6_idle", 7.0),     # delta 3 → floor at 21
    (20.9, 3.0, True, "P4_evening", 24.0),
])
def test_comfort_floor_rows(bp, indoor, delta, active, priority, setpoint):
    ctx = _evening_ctx(comfort_floor_delta=delta)
    out = render_vars(bp, ctx, world(**{"sensor.t": _State(str(indoor))}), "active_priority", at("19:30"))
    assert out["ea_in_window"] is True
    assert out["ea_active"] is active
    assert (out["active_priority"], out["desired_setpoint"]) == (priority, setpoint)


@pytest.mark.parametrize("hhmm,in_window", [
    ("18:54", False), ("18:55", True), ("19:15", True), ("20:29", True), ("20:30", False), ("21:00", False),
])
def test_window_bounds_rows(bp, hhmm, in_window):
    # indoor 22 / target 24 → ΔT 2 → lead 20 min → auto_start 18:55
    out = render_vars(bp, _evening_ctx(), world(), "ea_active", at(hhmm))
    assert out["ea_warmup_min"] == 20
    assert as_datetime(out["ea_auto_start_dt"]).strftime("%H:%M") == "18:55"
    assert out["ea_in_window"] is in_window
    assert out["ea_active"] is in_window


def test_window_day_filter(bp):
    out = render_vars(bp, base_ctx(evening_a_days=["mon"]), world(), "ea_active", at("19:30"))
    assert out["ea_in_days"] is False
    assert out["ea_in_window"] is False


@pytest.mark.parametrize("warm,hold,hhmm,expected_hold_day,in_window", [
    ("06:45:00", "08:00:00", "07:00", 8, True),    # normal same-day window
    ("23:00:00", "01:00:00", "23:30", 9, True),    # hold before warm → next day; window runs to midnight
    ("23:00:00", "22:00:00", "23:30", 9, True),    # hold before warm → next day
    ("23:00:00", "23:00:00", "23:30", 9, True),    # hold == warm → next day
    ("23:00:00", "01:00:00", "22:30", 9, False),   # before auto_start (22:40 for ΔT 1)
    ("23:00:00", "01:00:00", "00:30", 9, False),   # after midnight the slot is evaluated on the new day: not in window
])
def test_hold_until_anchor_rows(bp, warm, hold, hhmm, expected_hold_day, in_window):
    ctx = base_ctx(morning_a_days=["tue"], morning_a_target_warm=warm, morning_a_hold_until=hold)
    out = render_vars(bp, ctx, world(), "ma_active", at(hhmm))
    assert as_datetime(out["ma_hold_until_dt"]).day == expected_hold_day
    assert out["ma_in_window"] is in_window


def test_priority_vacation(bp):
    w = world(**{"input_boolean.vac": _State("on", minutes_ago=30)})
    out = render_vars(bp, _evening_ctx(), w, "active_priority", at("19:30"))
    assert out["vacation_active"] is True
    assert (out["desired_mode"], out["desired_setpoint"], out["active_priority"]) == ("off", "none", "P1_vacation")


def test_vacation_empty_list_is_false(bp):
    out = render_vars(bp, base_ctx(entity_vacation=[]), world(), "vacation_active")
    assert out["vacation_active"] is False


def test_priority_boost_and_expiry(bp):
    w = world(**{"input_boolean.boost": _State("on", minutes_ago=5)})
    assert decide(bp, base_ctx(), w) == ("P3_boost", 26.0)
    w = world(**{"input_boolean.boost": _State("on", minutes_ago=35)})
    out = render_vars(bp, base_ctx(), w, "active_priority")
    assert out["boost_expired"] is True
    assert out["active_priority"] == "P6_idle"


def test_boost_missing_entity_age_zero(bp):
    w = world()
    del w.table["input_boolean.boost"]
    out = render_vars(bp, base_ctx(), w, "boost_active")
    assert out["boost_age_min"] == 0
    assert out["boost_active"] is False


def test_priority_fan_coordination(bp):
    fan_on = {"light.fan": _State("on", minutes_ago=2)}
    assert decide(bp, _evening_ctx(), world(**fan_on), at("19:30")) == ("P2_fan_coord", 7.0)
    assert decide(bp, base_ctx(), world(**fan_on), at("12:00")) == ("P6_idle", 7.0)
    w = world(**fan_on, **{"input_boolean.boost": _State("on", minutes_ago=5)})
    assert decide(bp, _evening_ctx(), w, at("19:30")) == ("P3_boost", 26.0)


def test_evening_beats_morning(bp):
    ctx = base_ctx(morning_a_days=["tue"], morning_a_target_warm="19:00:00", morning_a_hold_until="21:00:00",
                   evening_a_days=["tue"])
    out = render_vars(bp, ctx, world(**{"sensor.t": _State("21.0")}), "active_priority", at("19:30"))
    assert out["morning_active"] is True and out["evening_active"] is True
    assert (out["active_priority"], out["desired_setpoint"]) == ("P4_evening", 24.0)


def test_morning_slot_setpoint_rounds_to_device_step(bp):
    ctx = base_ctx(morning_a_days=["tue"], morning_a_target_temp=23.5)
    assert decide(bp, ctx, world(), at("07:00")) == ("P5_morning", 24.0)
    w = world(**{"climate.rack": _State("unknown", attrs={"temperature": 7.0, "current_temperature": 23.4, "target_temp_step": 0.5})})
    assert decide(bp, ctx, w, at("07:00")) == ("P5_morning", 23.5)


def test_indoor_temp_fallback_rows(bp):
    out = render_vars(bp, base_ctx(), world(**{"sensor.t": _State("unavailable")}), "indoor_temp")
    assert (out["indoor_temp_has_primary"], out["indoor_temp"]) == (False, 23.4)
    w = world(**{"sensor.t": _State("unavailable"),
                 "climate.rack": _State("unknown", attrs={"temperature": 7.0, "target_temp_step": 1.0})})
    out = render_vars(bp, base_ctx(), w, "indoor_temp")
    assert (out["indoor_temp_both_unavailable"], out["indoor_temp"]) == (True, 20)


def test_hvac_mode_normalisation(bp):
    out = render_vars(bp, base_ctx(), world(), "current_hvac_mode_normalized")
    assert (out["current_hvac_mode"], out["current_hvac_mode_normalized"]) == ("unknown", "heat_cool")
    w = world(**{"climate.rack": _State("off", attrs={"temperature": 7.0, "target_temp_step": 1.0})})
    assert render_vars(bp, base_ctx(), w, "current_hvac_mode_normalized")["current_hvac_mode_normalized"] == "off"


@pytest.mark.parametrize("enabled,desired,current,expected", [
    (True, 24.0, 7.0, True),      # the tick that raises the setpoint
    (True, 24.0, 24.0, False),    # already raised
    (True, 24.0, 23.0, False),    # setpoint change between two active targets is not a warmup start
    (True, 7.0, 7.0, False),      # idle
    (True, "none", 7.0, False),   # vacation
    (False, 24.0, 7.0, False),    # notifications disabled
])
def test_warmup_notify_condition_rows(bp, enabled, desired, current, expected):
    tpl = choose_steps(bp)[4]["choose"][0]["conditions"][0]["value_template"]
    got = render_tpl(bp, tpl, world(), enable_notifications=enabled, desired_setpoint=desired,
                     current_setpoint=current, idle_setpoint_dev=7.0)
    assert got is expected


def test_warmup_edges_use_the_device_idle_value(bp):
    # idle 7.5 on a 1.0 step is written as 8.0: no phantom push at idle, and the dismiss can clear
    on = choose_steps(bp)[4]["choose"][0]["conditions"][0]["value_template"]
    off = choose_steps(bp)[4]["choose"][1]["conditions"][0]["value_template"]
    assert render_tpl(bp, on, world(), enable_notifications=True, desired_setpoint=8.0, current_setpoint=8.0, idle_setpoint_dev=8.0) is False
    assert render_tpl(bp, on, world(), enable_notifications=True, desired_setpoint=24.0, current_setpoint=8.0, idle_setpoint_dev=8.0) is True
    assert render_tpl(bp, off, world(), desired_setpoint=8.0, current_setpoint=24.0, idle_setpoint_dev=8.0) is True
    assert render_tpl(bp, off, world(), desired_setpoint=8.0, current_setpoint=8.0, idle_setpoint_dev=8.0) is False


@pytest.mark.parametrize("desired,current,expected", [
    (7.0, 24.0, True),      # the tick that lowers the setpoint
    (7.0, 7.0, False),      # already idle
    (24.0, 24.0, False),    # still active
    ("none", 24.0, False),  # vacation: hvac off, setpoint untouched
])
def test_warmup_dismiss_condition_rows(bp, desired, current, expected):
    tpl = choose_steps(bp)[4]["choose"][1]["conditions"][0]["value_template"]
    got = render_tpl(bp, tpl, world(), desired_setpoint=desired, current_setpoint=current, idle_setpoint_dev=7.0)
    assert got is expected


def test_warmup_eta_rows(bp):
    seq = choose_steps(bp)[4]["choose"][0]["sequence"]
    eta_vars = seq[0]["variables"]
    env = make_env(world(), NOW)
    ctx = dict(base_ctx(), desired_setpoint=24.0, indoor_temp=22.0)
    ctx["eta_delta"] = parse(env.from_string(str(eta_vars["eta_delta"])).render(**ctx))
    ctx["eta_min"] = parse(env.from_string(str(eta_vars["eta_min"])).render(**ctx))
    assert (ctx["eta_delta"], ctx["eta_min"]) == (2.0, 20)


@pytest.mark.parametrize("climate,expected", [
    (_State("unavailable", attrs={}), True),
    (_State("unknown", attrs={"temperature": 7.0}), False),   # the Tuya device's normal ON state
    (_State("off", attrs={"temperature": 7.0}), False),
    (None, True),                                               # entity deleted/renamed: HA reads 'unknown', must still hard-stop
])
def test_climate_hard_stop_rows(bp, climate, expected):
    w = world()
    if climate is None:
        del w.table["climate.rack"]
    else:
        w.table["climate.rack"] = climate
    tpl = choose_steps(bp)[0]["choose"][0]["conditions"][0]["value_template"]
    assert render_tpl(bp, tpl, w, entity_climate="climate.rack") is expected
    tpl_ok = choose_steps(bp)[0]["choose"][1]["conditions"][0]["value_template"]
    assert render_tpl(bp, tpl_ok, w, entity_climate="climate.rack") is (not expected)


def test_boost_does_not_alias_slot_heating(bp):
    # blueprint defaults: boost_target_temp 23 == morning target 23 — an active boost must not latch the slot
    ctx = base_ctx(morning_a_days=["tue"], boost_target_temp=23)
    w = world(**_rack(23.0), **{"input_boolean.boost": _State("on", minutes_ago=5)})
    out = render_vars(bp, ctx, w, "ma_active", at("07:00"))
    assert (out["boost_active"], out["ma_heating"], out["ma_floor"]) == (True, False, 22.0)
    # once the boost has expired and the device still holds 23, the slot adopts it
    w = world(**_rack(23.0), **{"input_boolean.boost": _State("off", minutes_ago=1)})
    out = render_vars(bp, ctx, w, "ma_active", at("07:00"))
    assert (out["boost_active"], out["ma_heating"], out["ma_floor"]) == (False, True, 22.5)


def test_target_dev_clamped_to_device_range(bp):
    attrs = {"temperature": 25.0, "current_temperature": 23.4, "target_temp_step": 1.0, "min_temp": 7.0, "max_temp": 25.0}
    ctx = base_ctx(morning_a_days=["tue"], morning_a_target_temp=28)
    out = render_vars(bp, ctx, world(**{"climate.rack": _State("unknown", attrs=attrs)}), "ma_active", at("07:00"))
    assert (out["ma_target_dev"], out["ma_heating"]) == (25.0, True)


def test_vacation_retained_setpoint_does_not_latch(bp):
    # vacation leaves the device OFF with the morning target still set; the slot must not treat that as "heating"
    ctx = base_ctx(morning_a_days=["tue"])
    off = {"climate.rack": _State("off", attrs={"temperature": 23.0, "current_temperature": 23.4, "target_temp_step": 1.0})}
    out = render_vars(bp, ctx, world(**off, **{"sensor.t": _State("22.3")}), "ma_active", at("06:00"))
    assert (out["ma_heating"], out["ma_in_window"]) == (False, False)          # strict edge: auto_start 06:35 for ΔT 0.7
    out = render_vars(bp, ctx, world(**_rack(23.0), **{"sensor.t": _State("22.3")}), "ma_active", at("06:00"))
    assert (out["ma_heating"], out["ma_in_window"]) == (True, True)            # device ON at the slot target: latched at 05:45


def test_sibling_slot_with_same_target_shares_latch(bp):
    # documented residual (code board 20260907-172334 R1-01): morning A 06:45→08:00 @23 and morning B 08:30→10:00 @23
    # on the same day — after A ends, the device still holds 23, so B latches its opening edge at 07:30
    ctx = base_ctx(morning_a_days=["tue"], morning_b_days=["tue"])
    out = render_vars(bp, ctx, world(**_rack(23.0), **{"sensor.t": _State("22.3")}), "morning_active", at("08:05"))
    assert out["ma_in_window"] is False
    assert (out["mb_heating"], as_datetime(out["mb_open_dt"]).strftime("%H:%M"), out["mb_in_window"]) == (True, "07:30", True)


# ---------------------------------------------------------------- instance + deploy dry-run

def test_instance_json_retune():
    inst = json.loads(INSTANCE_PATH.read_text())
    assert inst["id"] == "1776551429917"
    assert inst["alias"] == "Bathroom Heating Rack v2.0.0"
    assert inst["use_blueprint"]["path"] == HA_BP_PATH
    i = inst["use_blueprint"]["input"]
    assert i["heating_climate"] == "climate.heatingrack_bathroom"
    assert i["bathroom_temp_sensor"] == "sensor.bathroom_temperature"
    assert i["fan_switch"] == "light.heater"
    assert i["vacation_off"] == ["input_boolean.heating_rack_vacation"]
    assert i["boost_toggle"] == "input_boolean.heating_rack_boost"
    assert (i["boost_target_temp"], i["boost_runtime_min"]) == (26, 55)
    assert "morning_a_days" not in i and "morning_a_target_warm" not in i     # blueprint defaults: Mon–Fri 06:45→08:00 @ 23
    assert (i["morning_b_days"], i["morning_b_hold_until"]) == (["sat", "sun"], "09:30:00")
    assert (i["evening_a_days"], i["evening_a_target_warm"], i["evening_a_hold_until"], i["evening_a_target_temp"]) == (WEEKDAYS, "19:15:00", "20:30:00", 24)
    assert (i["evening_b_days"], i["evening_b_target_warm"], i["evening_b_hold_until"]) == (["sat", "sun"], "19:15:00", "20:30:00")
    assert "evening_b_target_temp" not in i                                     # blueprint default 23
    assert i["warmup_min_minutes"] == 10
    assert i["notify_targets"] == ["notify.mobile_app_martin_fold"]
    for k in ("hall_motion", "stairs_motion", "enable_predictive_motion"):
        assert k not in i
    assert set(i) <= EXPECTED_INPUTS


def test_instance_json_dry_run_validates():
    r = subprocess.run(["bash", str(DEPLOY_SCRIPT), "--dry-run", str(BP_PATH), HA_BP_PATH, str(INSTANCE_PATH)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ok (id 1776551429917" in r.stdout
    assert "dry-run: validation passed" in r.stdout
