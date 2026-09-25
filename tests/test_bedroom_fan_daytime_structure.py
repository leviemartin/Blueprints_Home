"""Structural and rendered pins for bedroom_fan_daytime.yaml (Bedroom Fan Daytime v1.1.0)
and its two deployed instance configs.

Run: cd <worktree> && ~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q

Contract: docs/superpowers/plans/2026-09-25-bedroom-fan-daytime-v1.1.0.md ("Contract" and
acceptance examples 1-11; example 12 lives in test_bedroom_fans_deploy_consistency.py).
Expectations come from that contract, never from the implementation.

Harness notes: the fakes are strict like HA — `is_state` / `states` raise TypeError on a
non-string entity id, `as_timestamp` (no default) raises on None / Undefined, and the Jinja
environment uses StrictUndefined. The action-level `variables:` step is rendered from the
YAML key by key IN FILE ORDER, and every value is re-parsed (`_reparse`) before the next key
sees it — HA renders each variable separately and hands the next one the literal_eval'd
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
THIS = {"entity_id": "automation.kids_room_fan_daytime_v1_0_0"}

INPUT_DEFAULTS = {"day_start": "08:00:00", "day_end": "18:00:00", "max_run_minutes": 120}
INPUT_NAMES = {"fan", *INPUT_DEFAULTS}
KIDS = {**INPUT_DEFAULTS, "fan": KIDS_FAN}
MASTER = {**INPUT_DEFAULTS, "fan": MASTER_FAN}

VAR_ORDER = ["is_real_trigger", "now_ts", "day_start_ts", "day_end_ts", "in_day", "fan_state",
             "fan_on", "on_since_ts", "from_night", "run_expired", "off_due"]


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
    assert len(steps) == 1, "exactly one action-level variables step"
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


# --- strict fakes ------------------------------------------------------------------------

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

    env.globals.update(states=_States(), is_state=is_state, state_attr=state_attr,
                       as_timestamp=_strict_as_timestamp)
    return env


def test_the_fakes_are_strict():
    env = _strict_env(datetime(2026, 9, 24, 12, 0, tzinfo=TZ), [S(KIDS_FAN, "on")])
    for tmpl in ("{{ is_state(x, 'on') }}", "{{ state_attr(x, 'a') }}", "{{ states(x) }}"):
        with pytest.raises(TypeError):
            env.from_string(tmpl).render(x=[[KIDS_FAN]])
    # Jinja's subscript turns the TypeError into a strict Undefined, which fails the render
    with pytest.raises(Exception):
        env.from_string("{{ states[x] }}").render(x=[[KIDS_FAN]])
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
NIGHT_WRITE = at(19, 29, day=-1)  # pre-cool's evening fan write


def world(*, fan="on", on_since=OLD, touched=None, master="off", master_since=OLD, drop=()):
    states = [
        S(KIDS_FAN, fan, {"percentage": 1, "direction": "forward"}, last_changed=on_since,
          last_updated=touched),
        S(MASTER_FAN, master, {"percentage": 1, "direction": "forward"}, last_changed=master_since),
    ]
    return [s for s in states if s.entity_id not in drop]


TICK = {"id": "tick", "idx": "0", "platform": "time_pattern"}
HA_START = {"id": "ha_start", "idx": "1", "platform": "homeassistant", "event": "start"}
MANUAL = {"platform": None}


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


def evaluate(bp, now, trigger=TICK, inputs=KIDS, states=None, live=None, live_now=None, **world_kw):
    states = world(**world_kw) if states is None else states
    ctx = _render_vars(bp, _strict_env(now, states), inputs, trigger)
    calls = _calls(bp, _strict_env(live_now or now, live if live is not None else states), ctx)
    return ctx, calls


def offs(bp, now, **kw):
    """The fan.turn_off calls of one run."""
    _, calls = evaluate(bp, now, **kw)
    assert all(c[0] == "fan.turn_off" for c in calls), calls
    return calls


OFF_KIDS = [("fan.turn_off", KIDS_FAN, {})]
OFF_MASTER = [("fan.turn_off", MASTER_FAN, {})]


# =========================================================================================
# 1. Structure
# =========================================================================================

def test_metadata_v110_automation(bp):
    assert bp["blueprint"]["name"] == "Bedroom Fan Daytime v1.1.0"
    assert "**Version: 1.1.0**" in bp["blueprint"]["description"]
    assert bp["blueprint"]["domain"] == "automation"


def test_inputs_fan_required_and_defaults(bp):
    inputs = bp["blueprint"]["input"]
    assert set(inputs) == INPUT_NAMES
    required = {k for k, v in inputs.items() if "default" not in (v or {})}
    assert required == {"fan"}
    for key, default in INPUT_DEFAULTS.items():
        assert inputs[key]["default"] == default, key
    fan_sel = inputs["fan"]["selector"]["entity"]
    assert fan_sel.get("domain") == "fan" and not fan_sel.get("multiple", False)
    assert "time" in inputs["day_start"]["selector"] and "time" in inputs["day_end"]["selector"]
    num = inputs["max_run_minutes"]["selector"]["number"]
    assert num["min"] == 15 and num["max"] == 600


def test_every_input_passes_through_top_level_variables(bp):
    top = bp["variables"]
    assert set(top) == INPUT_NAMES
    for name in INPUT_NAMES:
        assert isinstance(top.get(name), _Input) and top[name].name == name, name


def test_mode_queued_max_10_silent(bp):
    assert bp["mode"] == "queued"
    assert bp["max"] == 10
    assert bp["max_exceeded"] == "silent"


def test_triggers_tick_and_ha_start_only(bp):
    triggers = bp.get("triggers") or bp.get("trigger")
    plat = lambda t: t.get("platform", t.get("trigger"))
    assert [t["id"] for t in triggers] == ["tick", "ha_start"]
    tick, start = triggers
    assert plat(tick) == "time_pattern" and str(tick["minutes"]) == "/1"
    assert plat(start) == "homeassistant" and start["event"] == "start"
    assert not any(plat(t) == "state" for t in triggers)
    assert not (bp.get("conditions") or bp.get("condition")), "no global condition is needed"


def test_fan_turn_off_is_the_only_service(bp, text):
    steps = _service_steps(_actions(bp))
    assert [_svc(s) for s in steps] == ["fan.turn_off"], "exactly one service step: fan.turn_off"
    step = steps[0]
    assert _norm(_target(step)) == "{{ fan }}"
    assert step.get("continue_on_error") is True
    raw = set(re.findall(r"\bfan\.(turn_on|turn_off|toggle|set_[a-z_]+|increase_speed|decrease_speed|oscillate)\b", text))
    assert raw == {"turn_off"}, raw
    assert len(re.findall(r"fan\.turn_on|set_direction|set_percentage", text)) == 0
    assert not re.search(r"\b(homeassistant|script|automation|input_[a-z]+|persistent_notification|notify)\.[a-z_]+", text)


def test_no_wait_delay_repeat_or_wait_for_trigger(bp, text):
    for d in _walk(_actions(bp)):
        assert not {"wait_template", "delay", "wait_for_trigger", "repeat"} & set(d), d
    assert not re.search(r"^\s*-?\s*(wait_template|delay|wait_for_trigger|repeat)\s*:", text, re.M)


def test_action_is_variables_then_one_choose(bp):
    acts = _actions(bp)
    assert len(acts) == 2
    assert "variables" in acts[0]
    step = acts[1]
    assert set(step) == {"choose"}, step
    assert len(step["choose"]) == 1 and not step.get("default")


def test_turn_off_branch_rechecks_live_state(bp):
    opt = _actions(bp)[1]["choose"][0]
    cond = _norm(" and ".join(_templates_of(opt["conditions"])))
    assert cond.startswith("{{ off_due and"), cond
    assert "is_state(fan, 'on')" in cond
    assert "as_timestamp(now())" in cond


HA_GLOBALS = {"now", "states", "is_state", "as_timestamp", "today_at"}


def test_variables_step_order_and_names_defined_before_use(bp):
    assert list(_vars_step(bp)) == VAR_ORDER
    known = set(INPUT_NAMES) | {"trigger", "this"} | HA_GLOBALS
    env = Environment()
    for name, tmpl in _vars_step(bp).items():
        used = meta.find_undeclared_variables(env.parse(str(tmpl)))
        assert used <= known, f"{name} uses {sorted(used - known)} before definition"
        known.add(name)


def test_instants_are_timestamps(text, bp):
    assert not re.search(r"\.strftime\(", text)
    assert not re.search(r"\b\w+_dt\b", text), "datetime-typed variables must not cross steps"
    assert "as_timestamp(today_at(day_start))" in _norm(_var_template(bp, "day_start_ts"))
    assert "as_timestamp(today_at(day_end))" in _norm(_var_template(bp, "day_end_ts"))
    assert "last_changed" in _var_template(bp, "on_since_ts")
    assert "last_updated" not in text
    assert "trigger.to_state" not in text and "trigger.from_state" not in text


def test_every_variable_renders_to_a_plain_literal(bp):
    """No State object (or datetime) is stored in a variable: each key re-parses to a
    bool, a number or a short string."""
    for kw in (dict(), dict(fan="off"), dict(fan="unavailable"), dict(drop=(KIDS_FAN,))):
        for trig in (TICK, HA_START, MANUAL):
            ctx, _ = evaluate(bp, at(12, 0), trigger=trig, **kw)
            for name in VAR_ORDER:
                assert isinstance(ctx[name], (bool, int, float, str)), (name, ctx[name], kw)
            assert isinstance(ctx["fan_state"], str) and isinstance(ctx["on_since_ts"], (int, float))
            for name in ("is_real_trigger", "in_day", "fan_on", "from_night", "run_expired", "off_due"):
                assert isinstance(ctx[name], bool), (name, ctx[name])


# =========================================================================================
# 2. Rendered behaviour — acceptance examples
# =========================================================================================

def test_predicates_rendered(bp):
    ctx, _ = evaluate(bp, at(12, 0), on_since=at(10, 0))
    assert ctx["is_real_trigger"] is True
    assert ctx["now_ts"] == at(12, 0).timestamp()
    assert ctx["day_start_ts"] == at(8, 0).timestamp()
    assert ctx["day_end_ts"] == at(18, 0).timestamp()
    assert ctx["in_day"] is True
    assert ctx["fan_state"] == "on" and ctx["fan_on"] is True
    assert ctx["on_since_ts"] == at(10, 0).timestamp()
    assert ctx["from_night"] is False and ctx["run_expired"] is True and ctx["off_due"] is True
    for t, inside in ((at(7, 59, 59), False), (at(8, 0), True), (at(17, 59, 59), True), (at(18, 0), False)):
        assert evaluate(bp, t)[0]["in_day"] is inside, t


def test_ex1_night_fan_off_at_0800(bp):
    assert offs(bp, at(8, 0), on_since=NIGHT_WRITE) == OFF_KIDS
    ctx, calls = evaluate(bp, at(7, 59), on_since=NIGHT_WRITE)
    assert ctx["off_due"] is False and calls == []
    ctx, _ = evaluate(bp, at(8, 0), on_since=NIGHT_WRITE)
    assert ctx["from_night"] is True


def test_ex2_fan_on_0750_is_from_night(bp):
    ctx, calls = evaluate(bp, at(8, 0), on_since=at(7, 50))
    assert ctx["from_night"] is True and ctx["run_expired"] is False
    assert calls == OFF_KIDS
    # a fan turned on exactly at 08:00 is a day run: off two hours later
    assert offs(bp, at(8, 1), on_since=at(8, 0)) == []
    assert offs(bp, at(9, 59), on_since=at(8, 0)) == []
    assert offs(bp, at(10, 0), on_since=at(8, 0)) == OFF_KIDS


def test_ex3_day_run_off_after_two_hours(bp):
    for t in (at(10, 1), at(11, 0), at(11, 59), at(11, 59, 59)):
        assert offs(bp, t, on_since=at(10, 0)) == [], t
    assert offs(bp, at(12, 0), on_since=at(10, 0)) == OFF_KIDS
    # a later tick still switches it off (e.g. the 12:00 command did not land)
    assert offs(bp, at(12, 5), on_since=at(10, 0)) == OFF_KIDS


def test_ex4_late_start_runs_into_the_evening(bp):
    assert offs(bp, at(17, 59), on_since=at(16, 30)) == []
    for t in (at(18, 0), at(18, 29), at(18, 30), at(19, 29), at(23, 59), at(3, 0, day=1), at(7, 59, day=1)):
        ctx, calls = evaluate(bp, t, on_since=at(16, 30))
        assert ctx["off_due"] is False and calls == [], t
    # the next morning it is a night fan: off at 08:00
    assert offs(bp, at(8, 0, day=1), on_since=at(16, 30)) == OFF_KIDS


def test_ex5_speed_change_does_not_restart_or_trigger(bp):
    # on 17:00, speed changed 17:30 (last_updated moves, last_changed does not)
    for t in (at(17, 30), at(17, 59)):
        assert offs(bp, t, on_since=at(17, 0), touched=at(17, 30)) == [], t
    ctx, _ = evaluate(bp, at(17, 59), on_since=at(17, 0), touched=at(17, 30))
    assert ctx["on_since_ts"] == at(17, 0).timestamp()
    # the 2 h counts from the switch-on, not from the speed change
    assert offs(bp, at(12, 0), on_since=at(10, 0), touched=at(11, 30)) == OFF_KIDS


def test_ex6_cutoff_resume_restarts_the_run(bp):
    # on 10:00, cutoff off 11:00 (fan reads off -> nothing), resume 11:03
    assert offs(bp, at(11, 1), fan="off", on_since=at(11, 0)) == []
    assert offs(bp, at(12, 0), on_since=at(11, 3)) == []
    assert offs(bp, at(13, 2), on_since=at(11, 3)) == []
    assert offs(bp, at(13, 3), on_since=at(11, 3)) == OFF_KIDS


def test_ex7_tuya_flap_only_delays(bp):
    ctx, calls = evaluate(bp, at(10, 31), fan="unavailable", on_since=at(10, 30))
    assert ctx["fan_on"] is False and calls == []
    assert offs(bp, at(12, 31), on_since=at(10, 32)) == []
    assert offs(bp, at(12, 32), on_since=at(10, 32)) == OFF_KIDS


def test_ex8_off_unavailable_unknown_absent_issue_nothing(bp):
    for st in ("off", "unavailable", "unknown"):
        for t in (at(8, 0), at(12, 0), at(17, 59)):
            ctx, calls = evaluate(bp, t, fan=st, on_since=NIGHT_WRITE)
            assert ctx["fan_on"] is False and ctx["off_due"] is False and calls == [], (st, t)
            assert ctx["fan_state"] == st
    ctx, calls = evaluate(bp, at(12, 0), drop=(KIDS_FAN,))
    assert ctx["fan_state"] == "absent" and ctx["fan_on"] is False and ctx["on_since_ts"] == 0
    assert ctx["off_due"] is False and calls == []


def test_ex9_ha_start_and_manual_run_issue_nothing(bp):
    for trig in (HA_START, MANUAL):
        for kw in (dict(on_since=NIGHT_WRITE), dict(on_since=at(9, 0))):
            ctx, calls = evaluate(bp, at(12, 0), trigger=trig, **kw)
            assert ctx["is_real_trigger"] is False and ctx["off_due"] is False, trig
            assert ctx["in_day"] is True and ctx["fan_on"] is True
            assert ctx["from_night"] or ctx["run_expired"]
            assert calls == [], trig
    assert evaluate(bp, at(12, 0), on_since=at(9, 0))[0]["is_real_trigger"] is True
    # a trigger with an unexpected id is not a real trigger either
    other = {"id": "something_else", "platform": "event"}
    assert evaluate(bp, at(12, 0), trigger=other, on_since=at(9, 0))[1] == []


def test_ex10_live_recheck(bp):
    base = dict(on_since=at(9, 0))
    ctx, calls = evaluate(bp, at(12, 0), **base)
    assert ctx["off_due"] is True and calls == OFF_KIDS
    for st in ("off", "unavailable", "unknown"):
        _, calls = evaluate(bp, at(12, 0), live=world(fan=st, on_since=at(11, 59)), **base)
        assert calls == [], f"the fan read {st} meanwhile"
    _, calls = evaluate(bp, at(12, 0), live=world(drop=(KIDS_FAN,)), **base)
    assert calls == [], "the fan left the state machine meanwhile"
    ctx, calls = evaluate(bp, at(17, 59), live_now=at(18, 0, 30), **base)
    assert ctx["off_due"] is True and calls == [], "the live clock crossed 18:00"
    ctx, calls = evaluate(bp, at(17, 59, 59), live_now=at(18, 0), **base)
    assert calls == [], "18:00 itself is outside the window"


def test_ex11_instances_independent(bp):
    # kids day run expired, master off -> only the kids fan
    kw = dict(fan="on", on_since=at(10, 0), master="off", master_since=at(10, 0))
    assert offs(bp, at(12, 0), inputs=KIDS, **kw) == OFF_KIDS
    assert offs(bp, at(12, 0), inputs=MASTER, **kw) == []
    # master run expired, kids started later -> only the master fan
    kw = dict(fan="on", on_since=at(11, 0), master="on", master_since=at(10, 0))
    assert offs(bp, at(12, 0), inputs=KIDS, **kw) == []
    assert offs(bp, at(12, 0), inputs=MASTER, **kw) == OFF_MASTER
    # both night fans at 08:00, each instance switches only its own
    kw = dict(fan="on", on_since=NIGHT_WRITE, master="on", master_since=NIGHT_WRITE)
    assert offs(bp, at(8, 0), inputs=KIDS, **kw) == OFF_KIDS
    assert offs(bp, at(8, 0), inputs=MASTER, **kw) == OFF_MASTER
    # the master fan absent does not affect the kids instance
    assert offs(bp, at(12, 0), inputs=KIDS, on_since=at(10, 0), drop=(MASTER_FAN,)) == OFF_KIDS


def test_max_run_minutes_and_window_inputs_are_honoured(bp):
    short = {**KIDS, "max_run_minutes": 15}
    assert offs(bp, at(10, 14), inputs=short, on_since=at(10, 0)) == []
    assert offs(bp, at(10, 15), inputs=short, on_since=at(10, 0)) == OFF_KIDS
    late = {**KIDS, "day_start": "09:00:00", "day_end": "17:00:00"}
    assert offs(bp, at(8, 30), inputs=late, on_since=NIGHT_WRITE) == []
    assert offs(bp, at(9, 0), inputs=late, on_since=at(8, 30)) == OFF_KIDS
    assert offs(bp, at(17, 0), inputs=late, on_since=at(10, 0)) == []


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
    assert kids["alias"] == "Kids room — fan daytime v1.1.0"
    assert master["id"] == "bedroom_fan_daytime_master"
    assert master["alias"] == "Master bedroom — fan daytime v1.1.0"
    for inst in (kids, master):
        assert inst["use_blueprint"]["path"] == HA_PATH
        assert inst["trace"]["stored_traces"] == 60
    assert kids["use_blueprint"]["input"] == {"fan": KIDS_FAN}
    assert master["use_blueprint"]["input"] == {"fan": MASTER_FAN}
