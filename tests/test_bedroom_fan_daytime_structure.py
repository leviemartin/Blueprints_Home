"""Structural and rendered pins for bedroom_fan_daytime.yaml (Bedroom Fan Daytime v1.0.0)
and its two deployed instance configs.

Run: cd <worktree> && ~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q

Contract: docs/superpowers/plans/2026-09-24-bedroom-fan-daytime-v1.0.0.md (C1, C2, C4, C5,
the interaction matrix, acceptance examples 1-12 and 15-20). Expectations come from that
contract, never from the implementation.

Harness notes (C5): the fakes are strict like HA — `is_state` / `state_attr` / `states`
raise TypeError on a non-string entity id, `as_timestamp` (no default) raises on None /
Undefined, and the Jinja environment uses a non-chainable StrictUndefined, so nested access
on a missing `trigger.to_state` raises. The action-level `variables:` step is rendered from
the YAML key by key IN FILE ORDER, and every value is re-parsed (`_reparse`) before the next
key sees it — HA renders each variable separately and hands the next one the literal_eval'd
result, so a State object never survives a variables boundary (pre-cool hotfix 2026-09-07).
"""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, StrictUndefined, Undefined, meta

from test_bedroom_precool_structure import HassLoader, TZ, _Input, _env, _reparse, _var_template
from test_deploy_blueprint_script import run as deploy_run

ROOT = Path(__file__).resolve().parent.parent
BP_PATH = ROOT / "bedroom_fan_daytime.yaml"
HA_PATH = "leviemartin/bedroom_fan_daytime.yaml"
KIDS_INSTANCE = ROOT / "deploy" / "bedroom_fan_daytime_kids.json"
MASTER_INSTANCE = ROOT / "deploy" / "bedroom_fan_daytime_master.json"

KIDS_FAN = "fan.ceiling_fan_light_v2"
MASTER_FAN = "fan.ceiling_fan_light_v2_2"
STAIRS = "binary_sensor.stairs_motion"
PROT = "binary_sensor.samuel_samuel_matthew_fanprotection"
TOGGLE = "input_boolean.kids_nap"
SINCE = "input_datetime.kids_nap_since"
BTN_OFF = "event.baby_room_button_4"
BTN_UP = "event.baby_room_button_2"
BTN_DOWN = "event.baby_room_button_3"
GATE = "light.kids_room_gate"
THIS = {"entity_id": "automation.kids_room_fan_daytime_v1_0_0"}

INPUT_DEFAULTS = {
    "activity_sensors": [], "day_start": "08:00:00", "day_end": "18:00:00",
    "day_end_margin_minutes": 5, "vacancy_minutes": 20, "nap_toggle": [], "nap_since_helper": [],
    "nap_start_button": [], "nap_end_buttons": [], "gate_entity": [], "nap_max_hours": 3,
    "enable_notifications": True,
}
INPUT_NAMES = {"fan", *INPUT_DEFAULTS}
KIDS = {**INPUT_DEFAULTS, "fan": KIDS_FAN, "activity_sensors": [STAIRS, PROT], "nap_toggle": TOGGLE,
        "nap_since_helper": SINCE, "nap_start_button": BTN_OFF, "nap_end_buttons": [BTN_UP, BTN_DOWN],
        "gate_entity": GATE}
MASTER = {**INPUT_DEFAULTS, "fan": MASTER_FAN, "activity_sensors": [STAIRS]}

ALLOWED_SERVICES = {
    "fan.turn_off", "input_boolean.turn_on", "input_boolean.turn_off", "input_datetime.set_datetime",
    "persistent_notification.create", "persistent_notification.dismiss",
}
GLOBAL_CONDITION = (
    "{{ trigger.id is not defined or trigger.id in ['tick', 'ha_start'] or "
    "(trigger.from_state is not none and not (trigger.from_state.attributes.restored | default(false))) }}"
)
NOTICE_ID = "bedroom_fan_daytime_config_{{ this.entity_id | replace('.', '_') }}"


# --- loading ----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def text():
    return BP_PATH.read_text()


@pytest.fixture(scope="module")
def bp(text):
    return yaml.load(text, Loader=HassLoader)


def _norm(s):
    return " ".join(str(s).split())


def _actions(bp):
    return bp.get("actions") or bp.get("action") or []


def _vars_step(bp):
    steps = [s for s in _actions(bp) if isinstance(s, dict) and "variables" in s]
    assert len(steps) == 1, "exactly one action-level variables step (C2)"
    return steps[0]["variables"]


def _walk(node):
    """Yield every dict in the parsed tree."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _svc(step):
    return step.get("service", step.get("action"))


def _service_steps(node):
    return [d for d in _walk(node) if isinstance(_svc(d), str)]


def _target(step):
    t = (step.get("target") or {}).get("entity_id")
    if t is None:
        t = (step.get("data") or {}).get("entity_id")
    return t


def _templates_of(conditions):
    if isinstance(conditions, (str, dict)):
        conditions = [conditions]
    out = []
    for c in conditions:
        if isinstance(c, str):
            out.append(c)
        else:
            assert c.get("condition") == "template", c
            out.append(c["value_template"])
    return out


def _top_step_index(bp, predicate):
    for i, step in enumerate(_actions(bp)):
        if predicate(step):
            return i
    raise AssertionError("no top-level action step matches")


def _top_step_with_service(bp, service, data_key=None, data_value=None):
    def pred(step):
        for s in _service_steps(step):
            if _svc(s) != service:
                continue
            if data_key is None or _norm((s.get("data") or {}).get(data_key)) == _norm(data_value):
                return True
        return False
    return _top_step_index(bp, pred)


# --- strict fakes (C5) -------------------------------------------------------------------

class S:
    """A fake HA State: state, attributes, last_changed (state transitions) and last_updated
    (state OR attribute changes)."""
    def __init__(self, entity_id, state, attributes=None, last_changed=None, last_updated=None):
        self.entity_id = entity_id
        self.state = state
        self.attributes = dict(attributes or {})
        self.last_changed = last_changed or datetime(2026, 9, 24, 6, 0, tzinfo=TZ)
        self.last_updated = max(last_updated or self.last_changed, self.last_changed)


def _need_str(entity_id):
    if not isinstance(entity_id, str):
        raise TypeError(f"entity id must be a string, got {entity_id!r}")


def _strict_as_timestamp(value):
    if value is None or isinstance(value, Undefined):
        raise TypeError(f"as_timestamp without a default got {value!r}")
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, str):
        return datetime.fromisoformat(value).timestamp()
    raise TypeError(f"as_timestamp cannot parse {value!r}")


def _strict_env(now, states):
    env = _env(now)
    env.undefined = StrictUndefined
    by_id = {s.entity_id: s for s in states}

    class _States:
        def __call__(self, entity_id):
            _need_str(entity_id)
            return by_id[entity_id].state if entity_id in by_id else "unknown"

        def __getitem__(self, entity_id):
            _need_str(entity_id)
            return by_id.get(entity_id)

    def is_state(entity_id, value):
        _need_str(entity_id)
        return entity_id in by_id and by_id[entity_id].state == value

    def state_attr(entity_id, attr):
        _need_str(entity_id)
        return by_id[entity_id].attributes.get(attr) if entity_id in by_id else None

    def expand(*ids):
        out = []
        for group in ids:
            for i in ([group] if isinstance(group, str) else group):
                _need_str(i)
                if i in by_id:
                    out.append(by_id[i])
        return out

    env.globals.update(states=_States(), is_state=is_state, state_attr=state_attr, expand=expand,
                       as_timestamp=_strict_as_timestamp)
    return env


def test_the_fakes_are_strict():
    env = _strict_env(datetime(2026, 9, 24, 12, 0, tzinfo=TZ), [S(KIDS_FAN, "on")])
    for tmpl in ("{{ is_state(x, 'on') }}", "{{ state_attr(x, 'a') }}", "{{ states(x) }}", "{{ expand(x) }}"):
        with pytest.raises(TypeError):
            env.from_string(tmpl).render(x=[[KIDS_FAN]])
    with pytest.raises(TypeError):
        env.from_string("{{ as_timestamp(none) }}").render()
    with pytest.raises(Exception):
        env.from_string("{{ trigger.to_state.last_changed }}").render(trigger={"id": "tick"})
    with pytest.raises(Exception):
        env.from_string("{{ never_defined and true }}").render()


# --- world and trigger builders ----------------------------------------------------------

def at(h, m=0, s=0, day=0):
    return datetime(2026, 9, 24, h, m, s, tzinfo=TZ) + timedelta(days=day)


OLD = at(6, 0)
UNSET_SINCE = datetime(1970, 1, 1, tzinfo=TZ)  # a never-written input_datetime (date + time)


def since_state(when):
    when = UNSET_SINCE if when is None else when
    return S(SINCE, when.strftime("%Y-%m-%d %H:%M:%S"),
             {"has_date": True, "has_time": True, "timestamp": when.timestamp()}, last_changed=OLD)


def world(*, fan="on", fan_touch=OLD, stairs="off", stairs_at=OLD, prot="off", prot_at=OLD,
          toggle="off", toggle_at=OLD, since=None, gate="off", gate_at=OLD,
          master_fan="on", master_touch=OLD, drop=()):
    states = [
        S(KIDS_FAN, fan, {"percentage": 1, "direction": "forward"}, last_changed=fan_touch),
        S(MASTER_FAN, master_fan, {"percentage": 1, "direction": "forward"}, last_changed=master_touch),
        S(STAIRS, stairs, {"device_class": "motion"}, last_changed=stairs_at),
        S(PROT, prot, {"device_class": "motion"}, last_changed=prot_at),
        S(TOGGLE, toggle, last_changed=toggle_at),
        since_state(since),
        S(GATE, gate, last_changed=gate_at),
        S(BTN_OFF, OLD.isoformat(), {"event_type": "short_release"}, last_changed=OLD),
        S(BTN_UP, OLD.isoformat(), {"event_type": "short_release"}, last_changed=OLD),
        S(BTN_DOWN, OLD.isoformat(), {"event_type": "short_release"}, last_changed=OLD),
    ]
    return [s for s in states if s.entity_id not in drop]


TICK = {"id": "tick", "idx": "0", "platform": "time_pattern"}
HA_START = {"id": "ha_start", "idx": "1", "platform": "homeassistant", "event": "start"}
MANUAL = {"platform": None}


def button(trigger_id, entity, event_type, when, restored=False, from_none=False):
    attrs = {"event_type": "short_release"}
    if restored:
        attrs["restored"] = True
    frm = None if from_none else S(entity, (when - timedelta(hours=1)).isoformat(), attrs,
                                   last_changed=when - timedelta(hours=1))
    to = S(entity, when.isoformat(), {"event_type": event_type}, last_changed=when)
    return {"id": trigger_id, "platform": "state", "entity_id": entity, "from_state": frm, "to_state": to}


def toggle_flip(frm, to, when):
    return {"id": "nap_toggle", "platform": "state", "entity_id": TOGGLE,
            "from_state": S(TOGGLE, frm, last_changed=when - timedelta(hours=2)),
            "to_state": S(TOGGLE, to, last_changed=when)}


def gate_lit(when):
    return {"id": "gate_on", "platform": "state", "entity_id": GATE,
            "from_state": S(GATE, "off", last_changed=when - timedelta(hours=1)),
            "to_state": S(GATE, "on", last_changed=when)}


# --- the file-order render and a small action interpreter --------------------------------

def _render_vars(bp, env, inputs, trigger):
    ctx = {**inputs, "trigger": trigger, "this": THIS}
    for name, tmpl in _vars_step(bp).items():
        ctx[name] = _reparse(env.from_string(str(tmpl)).render(**ctx).strip())
    return ctx


def _truthy(rendered):
    v = _reparse(rendered.strip()) if isinstance(rendered, str) else rendered
    return v is True or (isinstance(v, str) and v.lower() == "true")


def _calls(bp, env, ctx):
    """Walk the action list after the variables step the way HA would: first matching
    choose option (template conditions, AND), else the default; record service calls with
    their rendered target and data."""
    calls = []

    def render(v):
        return _reparse(env.from_string(str(v)).render(**ctx).strip())

    def cond_ok(conditions):
        return all(_truthy(env.from_string(t).render(**ctx)) for t in _templates_of(conditions))

    def run(seq):
        for step in seq:
            if "variables" in step:
                continue
            if "choose" in step:
                for opt in step["choose"]:
                    if cond_ok(opt["conditions"]):
                        run(opt["sequence"])
                        break
                else:
                    run(step.get("default") or [])
            elif "if" in step:
                run(step["then"] if cond_ok(step["if"]) else (step.get("else") or []))
            elif isinstance(_svc(step), str):
                target = _target(step)
                data = {k: render(v) for k, v in (step.get("data") or {}).items() if k != "entity_id"}
                calls.append((_svc(step), render(target) if target is not None else None, data))
            else:
                raise AssertionError(f"unexpected step {step}")

    run(_actions(bp))
    return calls


def evaluate(bp, now, trigger=TICK, inputs=KIDS, states=None, live=None, **world_kw):
    states = world(**world_kw) if states is None else states
    ctx = _render_vars(bp, _strict_env(now, states), inputs, trigger)
    calls = _calls(bp, _strict_env(now, live if live is not None else states), ctx)
    return ctx, calls


def _svcs(calls, prefix=""):
    return [c[0] for c in calls if c[0].startswith(prefix)]


def _writes(calls):
    return [c for c in calls if not c[0].startswith("persistent_notification.")]


# =========================================================================================
# 1. Structure
# =========================================================================================

def test_metadata_v100_automation(bp):
    assert bp["blueprint"]["name"] == "Bedroom Fan Daytime v1.0.0"
    assert "**Version: 1.0.0**" in bp["blueprint"]["description"]
    assert bp["blueprint"]["domain"] == "automation"


def test_only_fan_is_required_and_every_other_input_has_a_default(bp):
    inputs = bp["blueprint"]["input"]
    assert set(inputs) == INPUT_NAMES
    required = {k for k, v in inputs.items() if "default" not in (v or {})}
    assert required == {"fan"}
    for key, default in INPUT_DEFAULTS.items():
        assert inputs[key]["default"] == default, key
    domains = {
        "fan": ("fan", False), "activity_sensors": ("binary_sensor", True),
        "nap_toggle": ("input_boolean", False), "nap_since_helper": ("input_datetime", False),
        "nap_start_button": ("event", False), "nap_end_buttons": ("event", True),
        "gate_entity": ("light", False),
    }
    for key, (domain, multiple) in domains.items():
        sel = inputs[key]["selector"]["entity"]
        assert sel.get("domain") == domain, key
        assert bool(sel.get("multiple", False)) is multiple, key


def test_every_input_passes_through_top_level_variables(bp):
    top = bp["variables"]
    for name in INPUT_NAMES:
        assert isinstance(top.get(name), _Input) and top[name].name == name, name


def test_mode_queued_max_10_silent(bp):
    assert bp["mode"] == "queued"
    assert bp["max"] == 10
    assert bp["max_exceeded"] == "silent"


def test_trigger_roster_ids_and_restored_guard(bp):
    triggers = bp.get("triggers") or bp.get("trigger")
    by_id = {t["id"]: t for t in triggers}
    assert [t["id"] for t in triggers] == ["tick", "ha_start", "nap_toggle", "nap_start", "nap_end", "gate_on"]
    plat = lambda t: t.get("platform", t.get("trigger"))
    assert plat(by_id["tick"]) == "time_pattern" and str(by_id["tick"]["minutes"]) == "/1"
    assert plat(by_id["ha_start"]) == "homeassistant" and by_id["ha_start"]["event"] == "start"
    for tid, name in (("nap_toggle", "nap_toggle"), ("nap_start", "nap_start_button"),
                      ("nap_end", "nap_end_buttons"), ("gate_on", "gate_entity")):
        t = by_id[tid]
        assert plat(t) == "state", tid
        assert isinstance(t["entity_id"], _Input) and t["entity_id"].name == name, tid
    for tid in ("nap_toggle", "nap_start", "nap_end"):
        assert "to" not in by_id[tid] and "from" not in by_id[tid], tid
    assert by_id["gate_on"]["to"] == "on" and "from" not in by_id["gate_on"]
    conditions = bp.get("conditions") or bp.get("condition")
    assert len(conditions) == 1
    assert _norm(_templates_of(conditions)[0]) == _norm(GLOBAL_CONDITION)


def _global_ok(bp, trigger):
    conditions = bp.get("conditions") or bp.get("condition")
    env = _strict_env(at(12), [])
    return _truthy(env.from_string(_templates_of(conditions)[0]).render(trigger=trigger, this=THIS))


def test_rendered_restored_guard(bp):
    assert _global_ok(bp, TICK) and _global_ok(bp, HA_START) and _global_ok(bp, MANUAL)
    assert _global_ok(bp, button("nap_start", BTN_OFF, "short_release", at(12, 40)))
    assert not _global_ok(bp, button("nap_start", BTN_OFF, "short_release", at(12, 40), restored=True))
    assert not _global_ok(bp, button("nap_end", BTN_UP, "short_release", at(12, 40), from_none=True))
    restored_toggle = toggle_flip("off", "on", at(12, 40))
    restored_toggle["from_state"].attributes["restored"] = True
    assert not _global_ok(bp, restored_toggle)


def test_fan_turn_off_is_the_only_fan_service(bp, text):
    services = [_svc(s) for s in _service_steps(_actions(bp))]
    assert {s for s in services if s.startswith("fan.")} == {"fan.turn_off"}
    raw = set(re.findall(r"\bfan\.(turn_on|turn_off|toggle|set_[a-z_]+|increase_speed|decrease_speed|oscillate)\b", text))
    assert raw == {"turn_off"}, raw
    off_steps = [s for s in _service_steps(_actions(bp)) if _svc(s) == "fan.turn_off"]
    assert len(off_steps) == 1
    step = off_steps[0]
    target = _target(step)
    assert _norm(target) == "{{ fan }}" or (isinstance(target, _Input) and target.name == "fan")
    assert step.get("continue_on_error") is True


def test_service_allowlist(bp, text):
    services = {_svc(s) for s in _service_steps(_actions(bp))}
    assert services == ALLOWED_SERVICES
    assert not re.search(r"\b(homeassistant|script|automation)\.[a-z_]+", text)
    for s in _service_steps(_actions(bp)):
        svc = _svc(s)
        if svc.startswith("input_boolean."):
            assert _norm(_target(s)) == "{{ nap_toggle }}", s
        if svc.startswith("input_datetime."):
            assert _norm(_target(s)) == "{{ nap_since_helper }}", s


def test_helper_writes_target_only_the_nap_helpers(bp, text):
    helper_steps = [s for s in _service_steps(_actions(bp))
                    if _svc(s).split(".")[0] in ("input_boolean", "input_datetime")]
    assert {_svc(s) for s in helper_steps} == {
        "input_boolean.turn_on", "input_boolean.turn_off", "input_datetime.set_datetime"}
    for s in helper_steps:
        assert _norm(_target(s)) in ("{{ nap_toggle }}", "{{ nap_since_helper }}"), s
    # no literal helper entity anywhere in the blueprint (R1-09)
    assert not re.search(r"\binput_(boolean|datetime|number|select|text)\.(?!turn_on\b|turn_off\b|set_datetime\b)[a-z0-9_]+", text)


def test_no_wait_delay_repeat_or_wait_for_trigger(bp, text):
    for d in _walk(_actions(bp)):
        assert not {"wait_template", "delay", "wait_for_trigger", "repeat"} & set(d), d
    assert not re.search(r"^\s*-?\s*(wait_template|delay|wait_for_trigger|repeat)\s*:", text, re.M)


def _fan_option(bp):
    for step in _actions(bp):
        for opt in (step.get("choose") or []) if isinstance(step, dict) else []:
            if any(_svc(s) == "fan.turn_off" for s in _service_steps(opt["sequence"])):
                return opt
    raise AssertionError("no choose option issues fan.turn_off")


def test_turn_off_branch_rechecks_live_state(bp):
    opt = _fan_option(bp)
    cond = _norm(" and ".join(_templates_of(opt["conditions"])))
    assert "off_due" in cond
    assert "is_state(fan, 'on')" in cond
    # rendered: the snapshot says off_due; the live state decides
    base = dict(fan="on", stairs_at=at(10, 0))
    ctx, calls = evaluate(bp, at(13, 0), **base)
    assert ctx["off_due"] is True and _svcs(calls, "fan.") == ["fan.turn_off"]
    _, calls = evaluate(bp, at(13, 0), live=world(**{**base, "fan": "off"}), **base)
    assert _svcs(calls, "fan.") == [], "the fan went off meanwhile"
    _, calls = evaluate(bp, at(13, 0), live=world(**{**base, "stairs": "on"}), **base)
    assert _svcs(calls, "fan.") == [], "somebody came upstairs meanwhile"
    _, calls = evaluate(bp, at(13, 0), live=world(**{**base, "prot": "on"}), **base)
    assert _svcs(calls, "fan.") == [], "the kids-room PIR fired meanwhile"


def test_nap_start_writes_since_before_toggle(bp):
    idx = _top_step_with_service(bp, "input_boolean.turn_on")
    seq = _service_steps(_actions(bp)[idx])
    names = [_svc(s) for s in seq]
    assert names.index("input_datetime.set_datetime") < names.index("input_boolean.turn_on")
    set_step = seq[names.index("input_datetime.set_datetime")]
    assert _norm(set_step["data"]["timestamp"]) == "{{ now_ts }}"


def test_nap_lifecycle_steps_precede_the_fan_step(bp):
    acts = _actions(bp)
    assert "variables" in acts[0]
    start = _top_step_with_service(bp, "input_boolean.turn_on")
    fallback = _top_step_with_service(bp, "input_datetime.set_datetime", "timestamp", "{{ effective_since_ts }}")
    end = _top_step_with_service(bp, "input_boolean.turn_off")
    fan = _top_step_with_service(bp, "fan.turn_off")
    notice = _top_step_with_service(bp, "persistent_notification.create")
    assert 0 < start < fallback < end < fan < notice


def _gate_of(bp, idx):
    step = _actions(bp)[idx]
    assert "choose" in step and len(step["choose"]) == 1 and not step.get("default"), step
    return [_norm(t) for t in _templates_of(step["choose"][0]["conditions"])]


def test_each_action_step_is_gated_on_its_predicate(bp):
    assert _gate_of(bp, _top_step_with_service(bp, "input_boolean.turn_on")) == ["{{ nap_start_due }}"]
    assert _gate_of(bp, _top_step_with_service(
        bp, "input_datetime.set_datetime", "timestamp", "{{ effective_since_ts }}")) == ["{{ since_fallback_due }}"]
    assert _gate_of(bp, _top_step_with_service(bp, "input_boolean.turn_off")) == ["{{ nap_end_due }}"]
    fan_cond = _norm(" and ".join(_gate_of(bp, _top_step_with_service(bp, "fan.turn_off"))))
    assert fan_cond.startswith("{{ off_due and"), fan_cond


HA_GLOBALS = {"now", "states", "is_state", "state_attr", "expand", "as_timestamp", "today_at", "namespace"}


def test_variables_step_defines_every_name_before_use(bp):
    """Design delta-2 R1-01: each key may use only inputs, trigger/this, HA globals and keys
    defined ABOVE it in the same step."""
    known = set(INPUT_NAMES) | {"trigger", "this"} | HA_GLOBALS
    env = Environment()
    for name, tmpl in _vars_step(bp).items():
        used = meta.find_undeclared_variables(env.parse(str(tmpl)))
        assert used <= known, f"{name} uses {sorted(used - known)} before definition"
        known.add(name)
    order = list(_vars_step(bp))
    assert order[0] == "is_real_trigger"
    for a, b in [("trig_to", "gesture"), ("gesture", "since_fallback_due"),
                 ("since_fallback_due", "effective_since_ts"), ("effective_since_ts", "nap_stale"),
                 ("effective_since_ts", "nap_cap"), ("nap_stale", "nap_end_due"), ("nap_cap", "nap_end_due"),
                 ("nap_forced", "nap_end_due"), ("nap_start_due", "exempt"), ("exempt", "off_due"),
                 ("vacant", "off_due")]:
        assert order.index(a) < order.index(b), (a, b)


def test_trigger_to_state_only_through_the_trig_to_guard(bp, text):
    vars_ = _vars_step(bp)
    for name, tmpl in vars_.items():
        if name != "trig_to":
            assert "trigger.to_state" not in str(tmpl), name
    assert text.count("trigger.to_state") == str(vars_["trig_to"]).count("trigger.to_state")
    assert ("trigger is defined and trigger.to_state is defined and trigger.to_state is not none"
            in _norm(vars_["trig_to"]))


def test_rendered_full_action_sequence(bp):
    # R1-01/R2-01: a dashboard off->on at 16:00 with since 11:00 writes since = 16:00 and does
    # NOT end the nap in the same run (the stale since would otherwise trip the cap)
    t = at(16, 0, 1)
    ctx, calls = evaluate(bp, t, trigger=toggle_flip("off", "on", at(16, 0)),
                          toggle="on", toggle_at=at(16, 0), since=at(11, 0))
    assert ctx["since_fallback_due"] is True
    assert ctx["effective_since_ts"] == at(16, 0).timestamp()
    assert ctx["nap_cap"] is False and ctx["nap_end_due"] is False
    assert _writes(calls) == [("input_datetime.set_datetime", SINCE, {"timestamp": at(16, 0).timestamp()})]
    # a fresh helper (never written, 1970) behaves the same
    ctx, calls = evaluate(bp, t, trigger=toggle_flip("off", "on", at(16, 0)),
                          toggle="on", toggle_at=at(16, 0), since=None)
    assert ctx["nap_end_due"] is False
    assert _writes(calls) == [("input_datetime.set_datetime", SINCE, {"timestamp": at(16, 0).timestamp()})]
    # R1-02: a tick (no trigger.to_state), ha_start and a manual Run render without error
    for trig in (TICK, HA_START, MANUAL):
        ctx, _ = evaluate(bp, at(13, 0), trigger=trig)
        assert ctx["trig_to"] is None and ctx["gesture"] == ""
    assert evaluate(bp, at(13, 0))[0]["is_real_trigger"] is True
    assert evaluate(bp, at(13, 0), trigger=HA_START)[0]["is_real_trigger"] is False
    assert evaluate(bp, at(13, 0), trigger=MANUAL)[0]["is_real_trigger"] is False


def test_config_notice_fixed_id_state_driven(bp):
    create = [s for s in _service_steps(_actions(bp)) if _svc(s) == "persistent_notification.create"]
    dismiss = [s for s in _service_steps(_actions(bp)) if _svc(s) == "persistent_notification.dismiss"]
    assert len(create) == 1 and len(dismiss) == 1
    assert _norm(create[0]["data"]["notification_id"]) == NOTICE_ID
    assert _norm(dismiss[0]["data"]["notification_id"]) == NOTICE_ID
    rendered_id = "bedroom_fan_daytime_config_automation_kids_room_fan_daytime_v1_0_0"

    def notices(calls):
        return [(c[0], c[2].get("notification_id")) for c in calls if c[0].startswith("persistent_notification.")]

    bad = {**KIDS, "nap_since_helper": []}
    _, calls = evaluate(bp, at(13, 0), inputs=bad)
    assert notices(calls) == [("persistent_notification.create", rendered_id)]
    _, calls = evaluate(bp, at(13, 0))
    assert notices(calls) == [("persistent_notification.dismiss", rendered_id)]
    _, calls = evaluate(bp, at(13, 0), inputs={**bad, "enable_notifications": False})
    assert notices(calls) == [("persistent_notification.dismiss", rendered_id)]
    # decided by the worker (recorded): ha_start / manual Run and the night write nothing at all
    for trig in (HA_START, MANUAL):
        _, calls = evaluate(bp, at(13, 0), trigger=trig, inputs=bad)
        assert calls == [], trig
    _, calls = evaluate(bp, at(20, 0), inputs=bad)
    assert calls == []


def test_instants_are_timestamps(text, bp):
    offenders = re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\.strftime\(", text)
    assert offenders == [], offenders
    assert not re.search(r"\b\w+_dt\b", text), "datetime-typed variables must not cross steps"
    assert "as_timestamp(today_at(day_start))" in _norm(_var_template(bp, "day_start_ts"))
    assert "as_timestamp(today_at(day_end))" in _norm(_var_template(bp, "day_end_ts"))
    assert re.search(r"state_attr\(\s*\w+\s*,\s*'timestamp'\s*\)\s*\|\s*float\(0\)", _var_template(bp, "since_ts"))
    assert "as_timestamp(states(" not in text


# =========================================================================================
# 2. Rendered behaviour
# =========================================================================================

def test_rendered_day_window(bp):
    for t, inside in ((at(7, 59), False), (at(8, 0), True), (at(17, 59), True), (at(18, 0), False)):
        ctx, _ = evaluate(bp, t)
        assert ctx["in_day"] is inside, t
        assert ctx["wrap_ts"] == at(17, 55).timestamp()
    # ex 8: no fan command 18:00-08:00 even with a running fan in an empty upstairs
    for t in (at(18, 0), at(19, 29), at(23, 0), at(3, 0), at(7, 59)):
        _, calls = evaluate(bp, t, fan="on", fan_touch=at(0, 0, day=-1) if t.hour < 8 else at(12, 0))
        assert _svcs(calls, "fan.") == [], t


def test_rendered_activity_and_vacancy(bp):
    night_write = at(19, 29, day=-1)
    # ex 1: morning sweep, both instances
    ctx, calls = evaluate(bp, at(8, 0), fan_touch=night_write, stairs_at=at(7, 40), prot_at=at(2, 0))
    assert ctx["vacant"] is True and ctx["off_due"] is True
    assert [c for c in calls if c[0] == "fan.turn_off"] == [("fan.turn_off", KIDS_FAN, {})]
    _, calls = evaluate(bp, at(8, 0), inputs=MASTER, master_touch=night_write, stairs_at=at(7, 40))
    assert [c for c in calls if c[0] == "fan.turn_off"] == [("fan.turn_off", MASTER_FAN, {})]
    # ex 2: occupied morning
    for t, off in ((at(8, 0), False), (at(8, 17), False), (at(8, 18), True)):
        _, calls = evaluate(bp, t, fan_touch=night_write, stairs_at=at(7, 58))
        assert (_svcs(calls, "fan.") == ["fan.turn_off"]) is off, t
    # a sensor reading on is occupied now, however old its last change
    ctx, calls = evaluate(bp, at(12, 0), stairs="on", stairs_at=at(9, 0))
    assert ctx["occupied_now"] is True and ctx["vacant"] is False and _svcs(calls, "fan.") == []
    # ex 3: hand-started master fan; its own change is activity
    for t, off in ((at(14, 19), False), (at(14, 20), True)):
        _, calls = evaluate(bp, t, inputs=MASTER, master_touch=at(14, 0), stairs_at=at(10, 0))
        assert (_svcs(calls, "fan.") == ["fan.turn_off"]) is off, t
    for t, off in ((at(14, 40), False), (at(14, 41), True)):
        _, calls = evaluate(bp, t, inputs=MASTER, master_touch=at(14, 21), stairs_at=at(10, 0))
        assert (_svcs(calls, "fan.") == ["fan.turn_off"]) is off, t
    # ex 10: an availability flap delays the off
    ctx, calls = evaluate(bp, at(8, 22), fan="unavailable", fan_touch=at(8, 21), stairs_at=at(7, 0))
    assert ctx["fan_avail"] is False and _svcs(calls, "fan.") == []
    for t, off in ((at(8, 42), False), (at(8, 43), True)):
        _, calls = evaluate(bp, t, fan_touch=at(8, 23), stairs_at=at(7, 0))
        assert (_svcs(calls, "fan.") == ["fan.turn_off"]) is off, t
    # ex 11: the season flip restarts the fan (13:00:04) -> activity
    for t, off in ((at(13, 20), False), (at(13, 20, 4), True)):
        _, calls = evaluate(bp, t, fan_touch=at(13, 0, 4), stairs_at=at(9, 0))
        assert (_svcs(calls, "fan.") == ["fan.turn_off"]) is off, t
    # an absent sensor contributes 0 (the others still count)
    ctx, _ = evaluate(bp, at(12, 0), stairs_at=at(11, 0), drop=(PROT,))
    assert ctx["sensor_ts"] == at(11, 0).timestamp()
    # ex 15: an unavailable sensor contributes the instant it dropped; the fan goes off
    ctx, calls = evaluate(bp, at(9, 20), stairs="unavailable", stairs_at=at(9, 0), prot_at=at(2, 0))
    assert ctx["sensor_ts"] == at(9, 0).timestamp() and ctx["occupied_now"] is False
    assert _svcs(calls, "fan.") == ["fan.turn_off"]
    _, calls = evaluate(bp, at(9, 19), stairs="unavailable", stairs_at=at(9, 0), prot_at=at(2, 0))
    assert _svcs(calls, "fan.") == []
    # activity_ts is the latest of the sensors, the fan touch and the toggle change
    ctx, _ = evaluate(bp, at(12, 0), stairs_at=at(9, 0), fan_touch=at(10, 0), toggle_at=at(11, 0))
    assert ctx["activity_ts"] == at(11, 0).timestamp()


def test_rendered_exempt_and_off_due(bp):
    # ex 4: nap on -> the running fan is left exactly as it is
    nap = dict(toggle="on", toggle_at=at(12, 40), since=at(12, 40), stairs_at=at(12, 41))
    ctx, calls = evaluate(bp, at(13, 30), **nap)
    assert ctx["nap_on"] is True and ctx["exempt"] is True and ctx["off_due"] is False
    assert _svcs(calls, "fan.") == []
    # ex 5: a parent's hold during the nap (fan touched 13:00) -> still left alone
    _, calls = evaluate(bp, at(13, 30), fan_touch=at(13, 0), **nap)
    assert _svcs(calls, "fan.") == []
    # ex 4/5: after the nap end at 14:30 the toggle change is activity -> off at 14:50
    for t, off in ((at(14, 49), False), (at(14, 50), True)):
        _, calls = evaluate(bp, t, fan_touch=at(13, 0), toggle="off", toggle_at=at(14, 30),
                            since=at(12, 40), stairs_at=at(12, 41))
        assert (_svcs(calls, "fan.") == ["fan.turn_off"]) is off, t
    # ex 8 (R1-03): a stale toggle at the 08:00 tick does not exempt; nap end AND fan off
    ctx, calls = evaluate(bp, at(8, 0), toggle="on", toggle_at=at(19, 0, day=-1), since=at(19, 0, day=-1),
                          fan_touch=at(19, 29, day=-1), stairs_at=at(7, 40), prot_at=at(2, 0))
    assert ctx["nap_stale"] is True and ctx["exempt"] is False and ctx["off_due"] is True
    assert _svcs(_writes(calls)) == ["input_boolean.turn_off", "fan.turn_off"]
    # ex 12: the cap ends the nap; the fan is still exempt in that run
    ctx, calls = evaluate(bp, at(15, 30), toggle="on", toggle_at=at(12, 30), since=at(12, 30), stairs_at=at(12, 0))
    assert ctx["nap_cap"] is True and ctx["exempt"] is True
    assert _svcs(_writes(calls)) == ["input_boolean.turn_off"]
    # ex 16: a nap-helper error disables the exemption; the off proceeds
    ctx, calls = evaluate(bp, at(13, 30), inputs={**KIDS, "nap_since_helper": []}, **nap)
    assert ctx["has_nap"] is False and ctx["exempt"] is False and ctx["off_due"] is True
    assert _svcs(calls, "fan.") == ["fan.turn_off"]
    # fan unavailable / unknown -> no command
    for st in ("unavailable", "unknown"):
        ctx, calls = evaluate(bp, at(13, 0), fan=st, stairs_at=at(9, 0))
        assert ctx["off_due"] is False and _svcs(calls, "fan.") == [], st
    # fan already off -> no command
    ctx, calls = evaluate(bp, at(13, 0), fan="off", stairs_at=at(9, 0))
    assert ctx["off_due"] is False and _svcs(calls, "fan.") == []
    # not a real trigger -> no command, no write of any kind
    for trig in (HA_START, MANUAL):
        ctx, calls = evaluate(bp, at(13, 0), trigger=trig, stairs_at=at(9, 0))
        assert ctx["is_real_trigger"] is False and ctx["off_due"] is False and calls == [], trig


def test_rendered_nap_start(bp):
    def press(ev, t=at(12, 40)):
        return button("nap_start", BTN_OFF, ev, t)

    # ex 4: Off tap with the gate lit -> since = now, then toggle on; the fan is untouched
    ctx, calls = evaluate(bp, at(12, 40), trigger=press("short_release"), gate="on", stairs_at=at(12, 39))
    assert ctx["nap_start_due"] is True and ctx["exempt"] is True
    assert _writes(calls) == [("input_datetime.set_datetime", SINCE, {"timestamp": at(12, 40).timestamp()}),
                              ("input_boolean.turn_on", TOGGLE, {})]
    # the fan is never started or changed: the same run with a vacant room and a running fan
    _, calls = evaluate(bp, at(12, 40), trigger=press("short_release"), gate="on", stairs_at=at(9, 0),
                        fan="on", fan_touch=at(9, 0))
    assert _svcs(calls, "fan.") == []
    # ex 20 and the negatives
    negatives = [
        dict(trigger=press("initial_press"), gate="on"),
        dict(trigger=press("long_press"), gate="on"),
        dict(trigger=press("short_release"), gate="off"),
        dict(trigger=press("short_release", at(7, 50)), gate="on", now=at(7, 50)),
        dict(trigger=press("short_release", at(17, 55)), gate="on", now=at(17, 55)),
        dict(trigger=press("short_release"), gate="on", toggle="on", toggle_at=at(12, 0), since=at(12, 0)),
        dict(trigger=press("short_release"), gate="on", inputs={**KIDS, "nap_toggle": []}),
        dict(trigger=press("short_release"), gate="on", inputs=MASTER),
    ]
    for case in negatives:
        now = case.pop("now", at(12, 40))
        ctx, calls = evaluate(bp, now, stairs_at=now - timedelta(minutes=1), **case)
        assert ctx["nap_start_due"] is False, case
        assert not any(c[0] in ("input_datetime.set_datetime", "input_boolean.turn_on") for c in calls), case
    # 17:54 is still a valid start (wrap is 17:55)
    ctx, _ = evaluate(bp, at(17, 54), trigger=press("short_release", at(17, 54)), gate="on", stairs_at=at(17, 53))
    assert ctx["nap_start_due"] is True
    # N's own start: the toggle transition that follows finds since within 60 s -> no rewrite
    ctx, calls = evaluate(bp, at(12, 40, 2), trigger=toggle_flip("off", "on", at(12, 40, 1)),
                          toggle="on", toggle_at=at(12, 40, 1), since=at(12, 40), gate="on")
    assert ctx["since_fallback_due"] is False and _writes(calls) == []


def test_rendered_nap_end(bp):
    nap = dict(toggle="on", toggle_at=at(12, 40), since=at(12, 40), stairs_at=at(14, 29))

    def up(ev="short_release", ent=BTN_UP):
        return button("nap_end", ent, ev, at(14, 30))

    # ex 4: + short_release with the gate dark -> toggle off only
    ctx, calls = evaluate(bp, at(14, 30), trigger=up(), gate="off", **nap)
    assert ctx["nap_end_due"] is True
    assert _writes(calls) == [("input_boolean.turn_off", TOGGLE, {})]
    ctx, _ = evaluate(bp, at(14, 30), trigger=up(ent=BTN_DOWN), gate="off", **nap)
    assert ctx["nap_end_due"] is True
    # + short_release with the gate lit -> no end; other gestures -> no end
    ctx, _ = evaluate(bp, at(14, 30), trigger=up(), gate="on", **nap)
    assert ctx["nap_end_due"] is False
    for ev in ("initial_press", "long_press", "repeat", "long_release"):
        ctx, _ = evaluate(bp, at(14, 30), trigger=up(ev), gate="off", **nap)
        assert ctx["nap_end_due"] is False, ev
    # the gate turning on ends it
    ctx, calls = evaluate(bp, at(14, 30), trigger=gate_lit(at(14, 30)), gate="on", **nap)
    assert ctx["nap_end_due"] is True and _svcs(_writes(calls)) == ["input_boolean.turn_off"]
    # ex 12: cap boundary (since 12:30, 3 h)
    capped = dict(toggle="on", toggle_at=at(12, 30), since=at(12, 30), stairs_at=at(12, 0))
    assert evaluate(bp, at(15, 29), **capped)[0]["nap_end_due"] is False
    assert evaluate(bp, at(15, 30), **capped)[0]["nap_end_due"] is True
    # ex 12: forced end at 17:55 (since 15:10)
    forced = dict(toggle="on", toggle_at=at(15, 10), since=at(15, 10), stairs_at=at(15, 0))
    ctx, _ = evaluate(bp, at(17, 54), **forced)
    assert ctx["nap_forced"] is False and ctx["nap_end_due"] is False
    ctx, calls = evaluate(bp, at(17, 55), **forced)
    assert ctx["nap_forced"] is True and ctx["nap_end_due"] is True
    assert _svcs(_writes(calls)) == ["input_boolean.turn_off"]
    # ex 8: stale since (yesterday 19:00) at 08:00 -> end
    ctx, _ = evaluate(bp, at(8, 0), toggle="on", toggle_at=at(19, 0, day=-1), since=at(19, 0, day=-1))
    assert ctx["nap_stale"] is True and ctx["nap_end_due"] is True
    # since unset (helper present, never written) -> end at the first real tick, not at ha_start
    ctx, calls = evaluate(bp, at(13, 0), toggle="on", toggle_at=at(12, 59), since=None)
    assert ctx["nap_end_due"] is True and "input_boolean.turn_off" in _svcs(calls)
    ctx, calls = evaluate(bp, at(13, 0), trigger=HA_START, toggle="on", toggle_at=at(12, 59), since=None)
    assert ctx["nap_end_due"] is False and calls == []
    # at 03:00 a since of 23:30 is not stale (the 08:00 boundary is today's)
    ctx, _ = evaluate(bp, at(3, 0), toggle="on", toggle_at=at(23, 30, day=-1), since=at(23, 30, day=-1))
    assert ctx["nap_stale"] is False
    ctx, _ = evaluate(bp, at(2, 0), toggle="on", toggle_at=at(23, 30, day=-1), since=at(23, 30, day=-1))
    assert ctx["nap_end_due"] is False
    # ex 8: a toggle switched on at 19:00 -> no fan writes, cap off at 22:00
    evening = dict(toggle="on", toggle_at=at(19, 0), since=at(19, 0), fan="on", fan_touch=at(12, 0),
                   stairs_at=at(12, 0))
    ctx, calls = evaluate(bp, at(21, 59), **evening)
    assert ctx["nap_end_due"] is False and _writes(calls) == []
    ctx, calls = evaluate(bp, at(22, 0), **evening)
    assert _writes(calls) == [("input_boolean.turn_off", TOGGLE, {})]
    # no toggle on -> never an end
    ctx, calls = evaluate(bp, at(14, 30), trigger=up(), gate="off", stairs_at=at(14, 29))
    assert ctx["nap_end_due"] is False and _writes(calls) == []


def test_rendered_since_fallback(bp):
    # ex 18: a dashboard flip on at 16:00 with since from an earlier nap -> since = 16:00
    flip = toggle_flip("off", "on", at(16, 0))
    ctx, calls = evaluate(bp, at(16, 0, 1), trigger=flip, toggle="on", toggle_at=at(16, 0), since=at(11, 0))
    assert ctx["since_fallback_due"] is True
    assert _writes(calls) == [("input_datetime.set_datetime", SINCE, {"timestamp": at(16, 0).timestamp()})]
    # since within 60 s of the flip -> no write
    ctx, calls = evaluate(bp, at(16, 0, 1), trigger=flip, toggle="on", toggle_at=at(16, 0), since=at(15, 59, 30))
    assert ctx["since_fallback_due"] is False and _writes(calls) == []
    # the forced end comes first (17:55 < 19:00 cap) from the persisted 16:00
    ctx, _ = evaluate(bp, at(17, 55), toggle="on", toggle_at=at(16, 0), since=at(16, 0), stairs_at=at(15, 0))
    assert ctx["nap_forced"] is True and ctx["nap_cap"] is False and ctx["nap_end_due"] is True
    # a flip off by hand ends the nap with no other write
    ctx, calls = evaluate(bp, at(14, 0, 1), trigger=toggle_flip("on", "off", at(14, 0)),
                          toggle="off", toggle_at=at(14, 0), since=at(12, 40), fan="on", fan_touch=at(9, 0),
                          stairs_at=at(9, 0))
    assert ctx["since_fallback_due"] is False and _writes(calls) == []
    # an attribute-only toggle update (on -> on) never writes the since
    ctx, _ = evaluate(bp, at(14, 0, 1), trigger=toggle_flip("on", "on", at(14, 0)),
                      toggle="on", toggle_at=at(12, 40), since=at(11, 0))
    assert ctx["since_fallback_due"] is False
    # a replayed restore (from_state restored) is stopped by the global condition
    replay = toggle_flip("off", "on", at(16, 0))
    replay["from_state"].attributes["restored"] = True
    assert not _global_ok(bp, replay)


def test_rendered_restart_mid_nap(bp):
    # ex 9: toggle and since restored; the ha_start run and a manual Run issue nothing
    for since in (at(12, 40), at(9, 0)):
        for trig in (HA_START, MANUAL):
            _, calls = evaluate(bp, at(13, 0), trigger=trig, toggle="on", toggle_at=at(12, 40), since=since,
                                fan="on", fan_touch=at(9, 0), stairs_at=at(9, 0))
            assert calls == [], (since, trig)
    # first tick after boot: a live nap continues (exempt); an over-cap since ends at that tick
    ctx, calls = evaluate(bp, at(13, 1), toggle="on", toggle_at=at(12, 40), since=at(12, 40),
                          fan="on", fan_touch=at(9, 0), stairs_at=at(9, 0))
    assert ctx["exempt"] is True and _writes(calls) == []
    ctx, calls = evaluate(bp, at(13, 1), toggle="on", toggle_at=at(9, 0), since=at(9, 0), stairs_at=at(12, 0))
    assert ctx["nap_cap"] is True and _svcs(_writes(calls)) == ["input_boolean.turn_off"]
    # button, toggle and gate replays at boot are guarded
    assert not _global_ok(bp, button("nap_start", BTN_OFF, "short_release", at(13, 0), from_none=True))
    assert not _global_ok(bp, button("nap_end", BTN_UP, "short_release", at(13, 0), restored=True))
    g = gate_lit(at(13, 0))
    g["from_state"] = None
    assert not _global_ok(bp, g)


def test_rendered_cutoff_hold_and_resume(bp):
    # ex 6: cutoff by day; the PIR clear (13:12) and the resume (13:15) are activity
    _, calls = evaluate(bp, at(13, 10, 30), fan="off", fan_touch=at(13, 10), prot="on", prot_at=at(13, 10),
                        stairs_at=at(13, 9))
    assert _writes(calls) == []
    for t in (at(13, 12, 30), at(13, 14)):
        _, calls = evaluate(bp, t, fan="off", fan_touch=at(13, 10), prot_at=at(13, 12), stairs_at=at(13, 11))
        assert _writes(calls) == [], t
    for m in range(16, 35):
        _, calls = evaluate(bp, at(13, m), fan="on", fan_touch=at(13, 15), prot_at=at(13, 12), stairs_at=at(13, 11))
        assert _writes(calls) == [], m
    _, calls = evaluate(bp, at(13, 35), fan="on", fan_touch=at(13, 15), prot_at=at(13, 12), stairs_at=at(13, 11))
    assert _writes(calls) == [("fan.turn_off", KIDS_FAN, {})]
    # ex 7 (1-min vacancy fixture): the cut has not landed (fan still reads on), vacancy is
    # satisfied inside the hold -> N's off is allowed and is an off, never an on
    one = {**KIDS, "vacancy_minutes": 1}
    _, calls = evaluate(bp, at(13, 13, 30), inputs=one, fan="on", fan_touch=at(13, 5), prot_at=at(13, 12),
                        stairs_at=at(13, 0))
    assert _writes(calls) == [("fan.turn_off", KIDS_FAN, {})]
    # the resume turns the fan on at 13:15 -> activity -> off again only after the timeout
    _, calls = evaluate(bp, at(13, 15, 30), inputs=one, fan="on", fan_touch=at(13, 15), prot_at=at(13, 12),
                        stairs_at=at(13, 0))
    assert _writes(calls) == []
    _, calls = evaluate(bp, at(13, 16), inputs=one, fan="on", fan_touch=at(13, 15), prot_at=at(13, 12),
                        stairs_at=at(13, 0))
    assert _writes(calls) == [("fan.turn_off", KIDS_FAN, {})]
    # while the cutoff PIR reads on, nothing (occupied)
    _, calls = evaluate(bp, at(13, 16), inputs=one, fan="on", fan_touch=at(13, 5), prot="on", prot_at=at(13, 10),
                        stairs_at=at(13, 0))
    assert _writes(calls) == []


def test_rendered_config_error(bp):
    nap = dict(toggle="on", toggle_at=at(12, 40), since=at(12, 40), stairs_at=at(12, 41))
    vacant = dict(fan="on", fan_touch=at(9, 0), stairs_at=at(9, 0))
    ok_ctx, _ = evaluate(bp, at(13, 30), **vacant)
    assert ok_ctx["config_error"] is False and ok_ctx["off_due"] is True
    # ex 16: nap_toggle without nap_since_helper (and the reverse) -> error, nap lifecycle off
    for inputs in ({**KIDS, "nap_since_helper": []}, {**KIDS, "nap_toggle": []}):
        ctx, calls = evaluate(bp, at(13, 30), inputs=inputs, **{**nap, **vacant})
        assert ctx["config_error"] is True and ctx["has_nap"] is False
        assert ctx["off_due"] is True and _svcs(calls, "fan.") == ["fan.turn_off"]
    # ex 16: activity_sensors empty -> error, but valid helpers + an active nap stay exempt
    ctx, calls = evaluate(bp, at(13, 30), inputs={**KIDS, "activity_sensors": []}, **{**vacant, **nap})
    assert ctx["config_error"] is True and ctx["has_nap"] is True and ctx["exempt"] is True
    assert _svcs(calls, "fan.") == []
    ctx, calls = evaluate(bp, at(13, 30), inputs={**KIDS, "activity_sensors": []}, **vacant)
    assert ctx["config_error"] is True and ctx["off_due"] is True and _svcs(calls, "fan.") == ["fan.turn_off"]
    # R1-04 delta / R1-06: the fan absent from the state machine
    ctx, calls = evaluate(bp, at(13, 30), drop=(KIDS_FAN,), **nap)
    assert ctx["fan_avail"] is False and ctx["off_due"] is False and ctx["config_error"] is True
    assert ctx["has_nap"] is True and ctx["exempt"] is True
    assert _svcs(calls, "fan.") == []
    # R1-11: a configured activity sensor absent -> contributes 0, error, off unaffected
    ctx, calls = evaluate(bp, at(13, 30), drop=(PROT,), **vacant)
    assert ctx["config_error"] is True and ctx["off_due"] is True and _svcs(calls, "fan.") == ["fan.turn_off"]
    ctx, calls = evaluate(bp, at(13, 30), drop=(PROT,), **{**vacant, **nap})
    assert ctx["has_nap"] is True and ctx["exempt"] is True and _svcs(calls, "fan.") == []
    # ex 17: the since helper deleted -> notice, no lifecycle writes, no exemption
    ctx, calls = evaluate(bp, at(12, 40), trigger=button("nap_start", BTN_OFF, "short_release", at(12, 40)),
                          gate="on", drop=(SINCE,), **vacant)
    assert ctx["config_error"] is True and ctx["has_nap"] is False and ctx["nap_start_due"] is False
    assert not any(c[0].startswith(("input_boolean.", "input_datetime.")) for c in calls)
    assert "persistent_notification.create" in _svcs(calls)
    ctx, calls = evaluate(bp, at(13, 30), drop=(SINCE,), **{**nap, **vacant})
    assert ctx["exempt"] is False and _svcs(calls, "fan.") == ["fan.turn_off"]
    # ex 17: the toggle deleted -> notice, no crash; also an unavailable helper
    ctx, calls = evaluate(bp, at(13, 30), drop=(TOGGLE,), **vacant)
    assert ctx["config_error"] is True and ctx["has_nap"] is False
    assert "persistent_notification.create" in _svcs(calls)
    ctx, _ = evaluate(bp, at(13, 30), toggle="unavailable", **vacant)
    assert ctx["config_error"] is True and ctx["has_nap"] is False
    # a configuration error never turns off_due false
    for kw in (dict(inputs={**KIDS, "nap_toggle": []}),
               dict(inputs={**KIDS, "activity_sensors": [STAIRS, "binary_sensor.gone"]}),
               dict(drop=(SINCE,))):
        ctx, _ = evaluate(bp, at(13, 30), **{**vacant, **kw})
        assert ctx["config_error"] is True and ctx["off_due"] is True, kw


def test_rendered_master_instance_has_no_nap(bp):
    ctx, calls = evaluate(bp, at(14, 0), inputs=MASTER, master_touch=at(9, 0), stairs_at=at(9, 0),
                          toggle="on", toggle_at=at(13, 0), since=at(13, 0))
    assert ctx["has_nap"] is False and ctx["nap_on"] is False and ctx["exempt"] is False
    assert ctx["config_error"] is False
    assert _writes(calls) == [("fan.turn_off", MASTER_FAN, {})]
    # the kids toggle never counts as master activity
    assert ctx["toggle_ts"] == 0


# =========================================================================================
# 3. Instances
# =========================================================================================

def test_instances_pass_dry_run():
    r = deploy_run("--dry-run", str(BP_PATH), HA_PATH, str(KIDS_INSTANCE), str(MASTER_INSTANCE))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "dry-run: validation passed" in r.stdout
    assert "ok (id bedroom_fan_daytime_kids" in r.stdout
    assert "ok (id bedroom_fan_daytime_master" in r.stdout


def test_instance_values():
    kids = json.loads(KIDS_INSTANCE.read_text())
    master = json.loads(MASTER_INSTANCE.read_text())
    assert kids["id"] == "bedroom_fan_daytime_kids"
    assert kids["alias"] == "Kids room — fan daytime v1.0.0"
    assert master["id"] == "bedroom_fan_daytime_master"
    assert master["alias"] == "Master bedroom — fan daytime v1.0.0"
    for inst in (kids, master):
        assert inst["use_blueprint"]["path"] == HA_PATH
        assert inst["trace"]["stored_traces"] == 60
    assert kids["use_blueprint"]["input"] == {
        "fan": KIDS_FAN,
        "activity_sensors": [STAIRS, PROT],
        "nap_toggle": TOGGLE,
        "nap_since_helper": SINCE,
        "nap_start_button": BTN_OFF,
        "nap_end_buttons": [BTN_UP, BTN_DOWN],
        "gate_entity": GATE,
    }
    assert master["use_blueprint"]["input"] == {"fan": MASTER_FAN, "activity_sensors": [STAIRS]}
