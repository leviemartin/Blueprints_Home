"""Structural and rendered pins for bedroom_fan_direction.yaml (Bedroom Fan Direction v1.0.0)
and its kids instance config.

Run: cd <worktree> && ~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q

Contract: docs/superpowers/plans/2026-09-25-bedroom-fan-direction-v1.0.0.md ("Behaviour
contract", "Invariants", "Acceptance examples" and the binding post-wave-2 fold-ins F1-F10),
under amendment A1: the blueprint sends NO fan command of any kind. Expectations come from
that contract, never from the implementation. Example 16 lives in
test_bedroom_fans_deploy_consistency.py.

Harness (extends the daytime harness): strict fakes and StrictUndefined; the action list is
interpreted step by step, so every action-level `variables:` step renders at its position
against the live world, key by key in file order, each value re-parsed (`_reparse`) before the
next key sees it. `weather.get_forecasts` injects a fake response per type (a list, a raw
mapping, or RAISE, which leaves the response variable unassigned); an `input_boolean` call
updates the fake toggle before the next step; `repeat.for_each` iterates the rendered list with
`repeat.item` bound. Choose-option and repeat sequences run in a block scope (HA >= 2025.4): a
name first assigned inside the branch (e.g. an undeclared response_variable) is gone after it,
while a pre-declared outer variable is updated (F3). A service that is not registered is fatal
even under continue_on_error (HA re-raises ServiceNotFound, F6).
"""
import copy
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, meta

from test_bedroom_precool_structure import HassLoader, TZ, _Input, _reparse
from test_bedroom_fan_daytime_structure import S, _norm, _strict_env, _svc, _templates_of, _truthy, _walk
from test_deploy_blueprint_script import run as deploy_run

ROOT = Path(__file__).resolve().parent.parent
BP_PATH = ROOT / "bedroom_fan_direction.yaml"
HA_PATH = "leviemartin/bedroom_fan_direction.yaml"
KIDS_INSTANCE = ROOT / "deploy" / "bedroom_fan_direction_kids.json"

FAN = "fan.ceiling_fan_light_v2"
TOGGLE = "input_boolean.samuel_fan_winter_mode"
WEATHER = "weather.home_sm"
OUTDOOR = "sensor.openweathermap_temperature"
PUSH = "notify.mobile_app_martin_fold"
THIS = {"entity_id": "automation.kids_room_fan_direction_v1_0_0"}

INPUT_DEFAULTS = {
    "outdoor_sensor": [], "notify_services": [], "fan_name": "the fan",
    "summer_direction": "forward", "winter_direction": "reverse",
    "outdoor_cold": 8.0, "outdoor_warm": 14.0,
    "decide_time": "18:00:00", "night_start": "19:30:00", "night_end": "07:15:00",
    "write_toggle": True,
}
REQUIRED = {"fan", "season_toggle", "weather_entity"}
INPUT_NAMES = REQUIRED | set(INPUT_DEFAULTS)
KIDS = {**INPUT_DEFAULTS, "fan": FAN, "season_toggle": TOGGLE, "weather_entity": WEATHER,
        "outdoor_sensor": [OUTDOOR], "notify_services": [PUSH], "fan_name": "kids fan"}

ALLOWED_SERVICES = {"input_boolean.turn_on", "input_boolean.turn_off", "weather.get_forecasts",
                    "persistent_notification.create", "persistent_notification.dismiss"}
NOTIFY_RE = "^notify[.][a-z0-9_]+$"

# Predicate names per action-level variables step, in the contract's order (Steps 1, 3, 5, 7),
# with decide_ok / decide_misconfig_due (F10) and the response pre-declarations (F3).
STEP1 = ["is_tick", "now_ts", "decide_start_ts", "decide_ok", "stage_a_ticks", "stage_a_index",
         "stage_a_due", "first_tick", "decide_misconfig_due", "quarter_tick", "night_start_ts",
         "night_end_ts", "weather_ok", "weather_daily_supported", "notify_list", "fan_name_safe",
         "hourly_resp"]
STEP3 = ["hourly_list_safe", "night_low_hourly", "daily_due", "daily_resp"]
STEP5 = ["daily_list_safe", "night_low_daily", "outdoor_now", "night_low", "night_low_source",
         "toggle_state", "toggle_known", "toggle_changed_ts", "season_target", "toggle_write_due",
         "forecast_degraded"]
STEP7 = ["toggle_now", "toggle_now_known", "toggle_changed_now", "season", "target_direction",
         "fan_state", "fan_available", "fan_direction", "direction_ok", "advice_reason",
         "advice_due", "dismiss_due", "night_low_known", "fan_state_word", "fan_direction_word"]
VAR_STEPS = [STEP1, STEP3, STEP5, STEP7]
RESPONSE_VARS = {"hourly_resp", "daily_resp"}

# B6: the only names a title/message may reference. advice_reason (an enum word from fixed
# literals) is added because Step 8 words the message "per reason".
MESSAGE_NAMES = {"night_low", "night_low_known", "season", "target_direction", "fan_direction_word",
                 "fan_state_word", "fan_name_safe", "night_low_source", "advice_reason"}


# --- loading ----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def text():
    return BP_PATH.read_text()


@pytest.fixture(scope="module")
def bp(text):
    return yaml.load(text, Loader=HassLoader)


def _actions(bp):
    return bp.get("actions") or bp.get("action") or []


def _action_text(text):
    m = re.search(r"^actions?:\s*$", text, re.M)
    assert m, "no top-level action block"
    return text[m.end():]


def _var_steps(bp):
    return [s["variables"] for s in _actions(bp) if isinstance(s, dict) and "variables" in s]


def _step_nodes(seq):
    """Every action node: top-level steps, choose options' sequences, repeat sequences."""
    for step in seq:
        yield step
        if "choose" in step:
            for opt in step["choose"]:
                yield from _step_nodes(opt.get("sequence") or [])
            yield from _step_nodes(step.get("default") or [])
        if "repeat" in step:
            yield from _step_nodes(step["repeat"].get("sequence") or [])


def _choose_options(seq):
    for step in _step_nodes(seq):
        if "choose" in step:
            yield from step["choose"]


def _cond(opt):
    return _norm(" and ".join(_templates_of(opt["conditions"])))


def _service_nodes(bp):
    return [s for s in _step_nodes(_actions(bp)) if isinstance(_svc(s), str)]


def _nid(stem):
    return f"bedroom_fan_direction_{stem}_{THIS['entity_id']}"


# --- strict world ------------------------------------------------------------------------

def at(h, m=0, s=0, day=0):
    return datetime(2026, 9, 24, h, m, s, tzinfo=TZ) + timedelta(days=day)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def world(now, *, toggle="off", toggle_since=None, fan="off", direction="forward",
          weather="partlycloudy", weather_unit="°C", weather_age=600, features=3,
          outdoor="11.0", outdoor_unit="°C", outdoor_age=600, drop=()):
    fan_attrs = {"percentage": 1}
    if direction is not None:
        fan_attrs["direction"] = direction
    w_at = now - timedelta(seconds=weather_age)
    o_at = now - timedelta(seconds=outdoor_age)
    states = [
        S(FAN, fan, fan_attrs, last_changed=now - timedelta(hours=5)),
        S(TOGGLE, toggle, {}, last_changed=toggle_since or (now - timedelta(days=1))),
        S(WEATHER, weather, {"temperature_unit": weather_unit, "supported_features": features,
                             "temperature": 12.0}, last_changed=w_at, last_updated=w_at),
        S(OUTDOOR, outdoor, {"unit_of_measurement": outdoor_unit}, last_changed=o_at, last_updated=o_at),
    ]
    return [s for s in states if s.entity_id not in drop]


def hourly(low, *, day=0, n=12, start=(20, 0), step=3600, rest=None, bad=None, times=None):
    """In-window rows from `start` (local, evening of `day`) every `step` seconds; the minimum
    `low` sits in row n // 2, the others read `rest` (default low + 3). Out-of-window rows at 19:00
    and 08:00 the next morning read -30 °C (they must never count). `bad` maps a row index to a
    replacement temperature. `times` overrides the in-window instants."""
    base = at(start[0], start[1], day=day)
    instants = times or [base + timedelta(seconds=step * i) for i in range(n)]
    rows = []
    for i, t in enumerate(instants):
        temp = low if i == len(instants) // 2 else (rest if rest is not None else low + 3)
        if bad and i in bad:
            temp = bad[i]
        rows.append({"datetime": iso(t), "temperature": temp, "condition": "<script>", "humidity": 80})
    rows.insert(0, {"datetime": iso(at(19, 0, day=day)), "temperature": -30, "condition": "<script>"})
    rows.append({"datetime": iso(at(8, 0, day=day + 1)), "temperature": -30, "condition": "<script>"})
    return rows


def daily(tomorrow_low, *, today_low=20.0, day=0):
    return [
        {"datetime": iso(at(12, 0, day=day)), "temperature": 22, "templow": today_low, "condition": "<script>"},
        {"datetime": iso(at(12, 0, day=day + 1)), "temperature": 18, "templow": tomorrow_low, "condition": "<script>"},
        {"datetime": iso(at(12, 0, day=day + 2)), "temperature": 15, "templow": -30, "condition": "<script>"},
    ]


RAISE = object()
TICK = {"id": "tick", "idx": "0", "platform": "time_pattern"}
HA_START = {"id": "ha_start", "idx": "1", "platform": "homeassistant", "event": "start"}
MANUAL = {"platform": None}


class ServiceNotFound(Exception):
    def __init__(self, service, calls):
        super().__init__(service)
        self.service = service
        self.calls = calls


def _env_for(now, states):
    env = _strict_env(now, states)
    env.tests["match"] = lambda v, pattern: re.match(pattern, str(v)) is not None  # HA's `match`
    return env


def evaluate(bp, now, *, trigger=TICK, inputs=KIDS, hourly_fc=(), daily_fc=(), services=(PUSH,),
             states=None, **world_kw):
    """Run the whole action list once. Returns (ctx, calls); calls are
    (service, rendered target, rendered data)."""
    states = world(now, **world_kw) if states is None else states
    env = _env_for(now, states)
    by_id = {s.entity_id: s for s in states}
    ctx = {**inputs, "trigger": trigger, "this": THIS}
    calls = []
    forecasts = {"hourly": hourly_fc, "daily": daily_fc}

    def render(v):
        if isinstance(v, str):
            return _reparse(env.from_string(v).render(**ctx).strip())
        if isinstance(v, dict):
            return {k: render(x) for k, x in v.items()}
        if isinstance(v, list):
            return [render(x) for x in v]
        return copy.deepcopy(v)

    def cond_ok(conditions):
        return all(_truthy(env.from_string(t).render(**ctx)) for t in _templates_of(conditions))

    def scoped(seq):
        before = set(ctx)
        run(seq)
        for k in set(ctx) - before:
            del ctx[k]

    def call(step):
        svc = render(_svc(step))
        tgt = (step.get("target") or {}).get("entity_id")
        tgt = render(tgt) if tgt is not None else None
        data = render(step.get("data") or {})
        if svc not in ALLOWED_SERVICES and svc not in services:
            raise ServiceNotFound(svc, list(calls))
        calls.append((svc, tgt, data))
        if svc == "weather.get_forecasts":
            resp = forecasts[data["type"]]
            if resp is RAISE:
                assert step.get("continue_on_error") is True, "an unguarded fetch aborts the run"
                return
            if isinstance(resp, (list, tuple)):
                resp = {tgt: {"forecast": copy.deepcopy(list(resp))}}
            ctx[step["response_variable"]] = resp
        elif svc in ("input_boolean.turn_on", "input_boolean.turn_off"):
            s = by_id[tgt]
            new = "on" if svc.endswith("turn_on") else "off"
            if s.state != new:
                s.state, s.last_changed, s.last_updated = new, now, now

    def run(seq):
        for step in seq:
            if "variables" in step:
                for name, tmpl in step["variables"].items():
                    ctx[name] = render(tmpl)
            elif "choose" in step:
                for opt in step["choose"]:
                    if cond_ok(opt["conditions"]):
                        scoped(opt["sequence"])
                        break
                else:
                    scoped(step.get("default") or [])
            elif "repeat" in step:
                items = render(step["repeat"]["for_each"])
                assert isinstance(items, list), items
                for i, item in enumerate(items):
                    ctx["repeat"] = {"item": item, "index": i + 1, "first": i == 0,
                                     "last": i == len(items) - 1}
                    scoped(step["repeat"]["sequence"])
                ctx.pop("repeat", None)
            elif isinstance(_svc(step), str):
                call(step)
            else:
                raise AssertionError(f"unexpected step {step}")

    run(_actions(bp))
    return ctx, calls


def label(c):
    svc, _, data = c
    if svc == "weather.get_forecasts":
        return f"get_forecasts({data['type']})"
    if svc.startswith("persistent_notification."):
        for stem in ("forecast", "advice"):
            if data.get("notification_id") == _nid(stem):
                return f"{svc.split('.')[1]}({stem})"
        return f"{svc}:{data.get('notification_id')}"
    return svc


def labels(calls):
    return [label(c) for c in calls]


def created(calls, stem):
    found = [c[2] for c in calls if label(c) == f"create({stem})"]
    assert len(found) == 1, labels(calls)
    return found[0]


def pushes(calls):
    return [c for c in calls if c[0].startswith("notify.")]


def run_ticks(bp, times, states, lows, **kw):
    """Several ticks of one evening against one mutable world; `lows` gives the hourly low
    per tick (None = no forecast)."""
    out = []
    for t, low in zip(times, lows):
        fc = hourly(low) if low is not None else []
        out.append(evaluate(bp, t, states=states, hourly_fc=fc, **kw))
    return out


def test_the_harness_models_block_scope_and_missing_services():
    fake = {"action": [
        {"choose": [{"conditions": [{"condition": "template", "value_template": "{{ true }}"}],
                     "sequence": [{"service": "weather.get_forecasts", "continue_on_error": True,
                                   "target": {"entity_id": WEATHER}, "data": {"type": "hourly"},
                                   "response_variable": "undeclared"}]}]},
        {"variables": {"seen": "{{ undeclared is defined }}"}},
    ]}
    ctx, _ = evaluate(fake, at(18, 0), hourly_fc=hourly(4))
    assert ctx["seen"] is False
    fake["action"].insert(0, {"variables": {"undeclared": {}}})
    ctx, _ = evaluate(fake, at(18, 0), hourly_fc=hourly(4))
    assert ctx["seen"] is True and WEATHER in ctx["undeclared"]
    with pytest.raises(ServiceNotFound):
        evaluate({"action": [{"service": "notify.gone", "continue_on_error": True}]}, at(18, 0))


# =========================================================================================
# 1. Structure (invariants 1-8)
# =========================================================================================

def test_metadata_v100_automation(bp):
    assert bp["blueprint"]["name"] == "Bedroom Fan Direction v1.0.0"
    assert "**Version: 1.0.0**" in bp["blueprint"]["description"]
    assert bp["blueprint"]["domain"] == "automation"


def test_inputs_exact_defaults_and_required(bp):
    inputs = bp["blueprint"]["input"]
    assert set(inputs) == INPUT_NAMES
    required = {k for k, v in inputs.items() if "default" not in (v or {})}
    assert required == REQUIRED
    for key, default in INPUT_DEFAULTS.items():
        assert inputs[key]["default"] == default, key
    assert inputs["outdoor_warm"]["default"] > inputs["outdoor_cold"]["default"]
    ent = lambda k: inputs[k]["selector"]["entity"]
    assert ent("fan").get("domain") == "fan" and not ent("fan").get("multiple", False)
    assert ent("season_toggle").get("domain") == "input_boolean"
    assert ent("weather_entity").get("domain") == "weather"
    assert ent("outdoor_sensor").get("domain") == "sensor" and ent("outdoor_sensor").get("multiple") is True
    assert inputs["notify_services"]["selector"]["text"].get("multiple") is True
    assert "text" in inputs["fan_name"]["selector"]
    for k in ("summer_direction", "winter_direction"):
        opts = inputs[k]["selector"]["select"]["options"]
        vals = {o["value"] if isinstance(o, dict) else o for o in opts}
        assert vals == {"forward", "reverse"}, k
    cold = inputs["outdoor_cold"]["selector"]["number"]
    warm = inputs["outdoor_warm"]["selector"]["number"]
    assert (cold["min"], cold["max"], cold["step"]) == (-10, 20, 0.5)
    assert (warm["min"], warm["max"], warm["step"]) == (0, 30, 0.5)
    for k in ("decide_time", "night_start", "night_end"):
        assert "time" in inputs[k]["selector"], k
    assert "boolean" in inputs["write_toggle"]["selector"]
    desc = _norm(inputs["decide_time"]["description"])
    assert "12:00" in desc and "21:00" in desc, "F10: the valid range is documented"
    for k in ("interlock", "apply_start", "apply_end", "verify", "retry"):
        assert not any(k in name for name in inputs), k


def test_every_input_passes_through_top_level_variables(bp):
    top = bp["variables"]
    assert set(top) == INPUT_NAMES
    for name in INPUT_NAMES:
        assert isinstance(top.get(name), _Input) and top[name].name == name, name


def test_mode_single_silent(bp):
    assert bp["mode"] == "single"
    assert bp["max_exceeded"] == "silent"
    assert "max" not in bp


def test_triggers_tick_and_ha_start_only(bp):
    triggers = bp.get("triggers") or bp.get("trigger")
    plat = lambda t: t.get("platform", t.get("trigger"))
    assert [t["id"] for t in triggers] == ["tick", "ha_start"]
    tick, start = triggers
    assert plat(tick) == "time_pattern" and str(tick["minutes"]) == "/1"
    assert plat(start) == "homeassistant" and start["event"] == "start"
    assert not any(plat(t) == "state" for t in triggers)
    assert not (bp.get("conditions") or bp.get("condition")), "no global condition"
    assert "trigger is defined and trigger.id is defined" in _norm(_var_steps(bp)[0]["is_tick"])


def test_service_allowlist_over_the_parsed_tree(bp):
    values = [_svc(d) for d in _walk(_actions(bp)) if isinstance(_svc(d), str)]
    literal = [v for v in values if "{{" not in v]
    templated = [v for v in values if "{{" in v]
    assert set(literal) <= ALLOWED_SERVICES, set(literal) - ALLOWED_SERVICES
    assert not any(v.startswith("notify.") for v in literal)
    assert [_norm(v) for v in templated] == ["{{ repeat.item }}"]
    repeats = [d["repeat"] for d in _walk(_actions(bp)) if "repeat" in d]
    assert len(repeats) == 1
    r = repeats[0]
    assert _norm(r["for_each"]) == "{{ notify_list }}"
    assert len(r["sequence"]) == 1
    step = r["sequence"][0]
    assert _norm(_svc(step)) == "{{ repeat.item }}" and step.get("continue_on_error") is True
    assert NOTIFY_RE in _var_steps(bp)[0]["notify_list"]


def test_action_block_raw_text_bans(text):
    """F5: the ban list applies to the action block (the trigger's `event: start` is outside)."""
    act = _action_text(text)
    for pat in (r"fan\.(turn_on|turn_off|toggle|set_[a-z_]+|increase_speed|decrease_speed|oscillate)",
                r"set_direction", r"set_percentage", r"homeassistant\.", r"script\.", r"automation\.",
                r"device_id", r"scene:", r"event:"):
        assert not re.search(pat, act), pat
    # acceptance check 3 runs over the whole file
    assert not re.search(r"fan\.(turn_on|turn_off|toggle|set_[a-z_]+)|set_direction", text)
    for absent in ("sensor.temperature_sensor_3", "fanprotection"):
        assert absent not in text, absent


def test_toggle_steps_target_the_toggle_under_toggle_write_due(bp):
    """Invariant 4 and F4."""
    steps = {_svc(s): s for s in _service_nodes(bp) if _svc(s).startswith("input_boolean.")}
    assert set(steps) == {"input_boolean.turn_on", "input_boolean.turn_off"}
    for s in steps.values():
        assert _norm(s["target"]["entity_id"]) == "{{ season_toggle }}"
    opts = {}
    for opt in _choose_options(_actions(bp)):
        for s in opt["sequence"]:
            if _svc(s) in steps:
                opts[_svc(s)] = _cond(opt)
    assert "toggle_write_due" in opts["input_boolean.turn_on"]
    assert "season_target == 'winter'" in opts["input_boolean.turn_on"]
    assert "toggle_write_due" in opts["input_boolean.turn_off"]
    assert "season_target == 'summer'" in opts["input_boolean.turn_off"]


def test_forecast_steps_are_guarded(bp):
    fetches = [s for s in _service_nodes(bp) if _svc(s) == "weather.get_forecasts"]
    assert [f["data"]["type"] for f in fetches] == ["hourly", "daily"]
    for f in fetches:
        assert f.get("continue_on_error") is True
        assert f.get("response_variable") in RESPONSE_VARS
        assert _norm(f["target"]["entity_id"]) == "{{ weather_entity }}"
    conds = {}
    for opt in _choose_options(_actions(bp)):
        for s in opt["sequence"]:
            if _svc(s) == "weather.get_forecasts":
                conds[s["data"]["type"]] = _cond(opt)
    assert conds["hourly"] == "{{ stage_a_due and weather_ok }}"
    assert conds["daily"] == "{{ daily_due }}"


def test_response_variables_are_predeclared_before_each_fetch(bp):
    """F3: the variables step right before each fetch choose declares its response variable."""
    acts = _actions(bp)
    for i, step in enumerate(acts):
        if "choose" not in step:
            continue
        fetch = [s for opt in step["choose"] for s in opt["sequence"] if _svc(s) == "weather.get_forecasts"]
        if not fetch:
            continue
        name = fetch[0]["response_variable"]
        prev = acts[i - 1]
        assert "variables" in prev, "a variables step precedes the fetch choose"
        assert list(prev["variables"])[-1] == name and prev["variables"][name] == {}, name


def test_advice_option_shape_and_last_steps(bp):
    """Invariant 4 and F6: persistent create first, the push loop last, Step 8 last action."""
    last = _actions(bp)[-1]
    assert set(last) == {"choose"} and not last.get("default")
    advice, dismiss = last["choose"]
    assert _cond(advice) == "{{ advice_due }}"
    seq = advice["sequence"]
    assert len(seq) == 2
    assert _svc(seq[0]) == "persistent_notification.create"
    assert _norm(seq[0]["data"]["notification_id"]) == "bedroom_fan_direction_advice_{{ this.entity_id }}"
    assert set(seq[1]) == {"repeat"}, "the repeat is the last step of the advice option"
    assert _cond(dismiss) == "{{ dismiss_due }}"
    assert [_svc(s) for s in dismiss["sequence"]] == ["persistent_notification.dismiss"]
    push = seq[1]["repeat"]["sequence"][0]
    assert push["data"] == {k: v for k, v in seq[0]["data"].items() if k != "notification_id"}
    assert seq[0]["data"]["title"] == "Bedroom fan direction"


FORBIDDEN_STEP_KEYS = {"wait_template", "delay", "wait_for_trigger", "stop", "if", "parallel",
                       "condition", "event", "scene", "device_id", "type"}


def test_step_kind_allowlist_and_forbidden_keys(bp):
    """Invariant 5: never descending into data/target."""
    for step in _step_nodes(_actions(bp)):
        kinds = {k for k in ("service", "action", "choose", "variables", "repeat") if k in step}
        assert len(kinds) == 1, step
        assert not FORBIDDEN_STEP_KEYS & set(step), step
    for opt in _choose_options(_actions(bp)):
        assert not FORBIDDEN_STEP_KEYS & set(opt), opt
        assert set(opt) == {"conditions", "sequence"}, opt


def test_instants_are_timestamps(bp, text):
    """Invariant 6."""
    assert not re.search(r"\.strftime\(", text)
    assert not re.search(r"\b\w+_dt\b", text)
    assert "trigger.to_state" not in text and "trigger.from_state" not in text
    users = {name for vs in _var_steps(bp) for name, t in vs.items() if "last_updated" in str(t)}
    assert users == {"weather_ok", "outdoor_now"}
    var_maps = {id(vs) for vs in _var_steps(bp)}
    other = [d for d in _walk(_actions(bp)) if id(d) not in var_maps
             and any(isinstance(v, str) and "last_updated" in v for v in d.values())]
    assert other == []
    assert "as_timestamp(today_at(decide_time))" in _norm(_var_steps(bp)[0]["decide_start_ts"])
    assert "last_changed" in _var_steps(bp)[2]["toggle_changed_ts"]


HA_GLOBALS = {"now", "states", "is_state", "state_attr", "as_timestamp", "today_at", "as_datetime",
              "timedelta", "namespace"}


def test_variables_steps_order_and_names_defined_before_use(bp):
    steps = _var_steps(bp)
    assert [list(s) for s in steps] == VAR_STEPS
    known = set(INPUT_NAMES) | {"trigger", "this", "repeat"} | HA_GLOBALS
    env = _env_for(at(12, 0), [])  # parse with HA's filters and tests registered
    for vs in steps:
        for name, tmpl in vs.items():
            if isinstance(tmpl, str):
                used = meta.find_undeclared_variables(env.parse(tmpl))
                assert used <= known, f"{name} uses {sorted(used - known)} before definition"
            known.add(name)
    # every template anywhere in the action list uses only defined names
    for d in _walk(_actions(bp)):
        for v in d.values():
            if isinstance(v, str) and "{" in v:
                used = meta.find_undeclared_variables(env.parse(v))
                assert used <= known, sorted(used - known)


def test_notification_ids_two_stems(bp):
    ids = {_norm(d["notification_id"]) for d in _walk(_actions(bp)) if "notification_id" in d}
    assert ids == {"bedroom_fan_direction_forecast_{{ this.entity_id }}",
                   "bedroom_fan_direction_advice_{{ this.entity_id }}"}


def test_message_hygiene(bp):
    """Invariant 8 / B6: fixed wording, validated numbers and enum words only."""
    env = _env_for(at(12, 0), [])
    seen = 0
    for d in _walk(_actions(bp)):
        for key in ("title", "message"):
            if key in d:
                seen += 1
                used = meta.find_undeclared_variables(env.parse(str(d[key])))
                assert used <= MESSAGE_NAMES, (key, sorted(used - MESSAGE_NAMES))
                assert "resp" not in str(d[key]) and "list" not in str(d[key])
    assert seen >= 6


PLAIN = (bool, int, float, str, list)


def test_every_rendered_key_is_plain(bp):
    names = [n for step in VAR_STEPS for n in step if n not in RESPONSE_VARS]
    cases = [
        dict(now=at(18, 0), hourly_fc=hourly(4)),
        dict(now=at(18, 0), hourly_fc=RAISE, daily_fc=daily(5)),
        dict(now=at(18, 0), weather="unavailable"),
        dict(now=at(18, 0), fan="unavailable", direction=None, drop=(OUTDOOR,)),
        dict(now=at(12, 1)), dict(now=at(12, 15), drop=(FAN, TOGGLE)),
    ]
    for case in cases:
        now = case.pop("now")
        for trig in (TICK, HA_START, MANUAL):
            ctx, _ = evaluate(bp, now, trigger=trig, **case)
            for n in names:
                v = ctx[n]
                assert isinstance(v, PLAIN) or v is None, (n, v)
                if isinstance(v, str):
                    assert len(v) <= 64, (n, v)
            for n in ("is_tick", "stage_a_due", "first_tick", "quarter_tick", "weather_ok",
                      "toggle_known", "toggle_write_due", "advice_due", "dismiss_due", "direction_ok",
                      "decide_ok", "decide_misconfig_due", "daily_due", "forecast_degraded"):
                assert isinstance(ctx[n], bool), (n, ctx[n])


# =========================================================================================
# 2. Rendered behaviour — acceptance examples
# =========================================================================================

def test_predicates_rendered(bp):
    ctx, _ = evaluate(bp, at(18, 0), hourly_fc=hourly(4))
    assert ctx["is_tick"] is True and ctx["decide_ok"] is True
    assert ctx["decide_start_ts"] == at(18, 0).timestamp()
    assert ctx["stage_a_ticks"] == [at(18, m).timestamp() for m in (0, 15, 30, 45)]
    assert ctx["stage_a_index"] == 0 and ctx["stage_a_due"] and ctx["first_tick"] and ctx["quarter_tick"]
    assert ctx["night_start_ts"] == at(19, 30).timestamp()
    assert ctx["night_end_ts"] == at(7, 15, day=1).timestamp()
    assert ctx["weather_ok"] is True and ctx["weather_daily_supported"] is True
    assert ctx["notify_list"] == [PUSH] and ctx["fan_name_safe"] == "kids fan"
    assert ctx["night_low_hourly"] == 4.0 and ctx["night_low_source"] == "hourly"
    for t, idx in ((at(17, 59), -1), (at(18, 1), -1), (at(18, 15), 1), (at(18, 30), 2),
                   (at(18, 45), 3), (at(19, 0), -1)):
        ctx, _ = evaluate(bp, t)
        assert ctx["stage_a_index"] == idx, t
        assert ctx["stage_a_due"] is (idx >= 0) and ctx["first_tick"] is (idx == 0)


def test_ex1_winter_night_sets_toggle_and_advises_reverse(bp):
    ctx, calls = evaluate(bp, at(18, 0), hourly_fc=hourly(4), toggle="off", fan="off", direction="forward")
    assert labels(calls) == ["get_forecasts(hourly)", "input_boolean.turn_on", "dismiss(forecast)",
                             "create(advice)", PUSH]
    assert calls[1][1] == TOGGLE
    msg = created(calls, "advice")["message"]
    for part in ("4.0 °C", "reverse", "winter", "forward"):
        assert part in msg, (part, msg)
    assert "set kids fan to reverse (winter) while it is off" in msg
    assert ctx["advice_reason"] == "differs"
    # same world, fan already reverse: no push
    _, calls = evaluate(bp, at(18, 0), hourly_fc=hourly(4), toggle="off", direction="reverse")
    assert labels(calls) == ["get_forecasts(hourly)", "input_boolean.turn_on", "dismiss(forecast)",
                             "dismiss(advice)"]


def test_f4_summer_night_clears_toggle(bp):
    kw = dict(hourly_fc=hourly(16), toggle="on")
    _, calls = evaluate(bp, at(18, 0), direction="reverse", **kw)
    assert labels(calls) == ["get_forecasts(hourly)", "input_boolean.turn_off", "dismiss(forecast)",
                             "create(advice)", PUSH]
    msg = created(calls, "advice")["message"]
    for part in ("forward", "summer", "reverse"):
        assert part in msg, part
    _, calls = evaluate(bp, at(18, 0), direction="forward", **kw)
    assert labels(calls) == ["get_forecasts(hourly)", "input_boolean.turn_off", "dismiss(forecast)",
                             "dismiss(advice)"]


def test_ex2_matching_direction_only_dismisses(bp):
    kw = dict(hourly_fc=hourly(11), toggle="off", direction="forward")
    assert labels(evaluate(bp, at(18, 0), **kw)[1]) == ["get_forecasts(hourly)", "dismiss(forecast)",
                                                         "dismiss(advice)"]
    for t in (at(12, 15), at(20, 30)):
        assert labels(evaluate(bp, t, **kw)[1]) == ["dismiss(advice)"], t
    for t in (at(12, 1), at(10, 0, 0) + timedelta(minutes=1)):
        assert evaluate(bp, t, **kw)[1] == [], t
    for t in (at(12, 1), at(12, 15), at(10, 0), at(19, 0)):
        assert not any(c[0] == "weather.get_forecasts" for c in evaluate(bp, t, **kw)[1]), t


def test_ex3_hold_band_advises_from_the_toggle(bp):
    _, calls = evaluate(bp, at(18, 0), hourly_fc=hourly(10), toggle="on", direction="forward")
    assert not any(c[0].startswith("input_boolean.") for c in calls)
    assert labels(calls) == ["get_forecasts(hourly)", "dismiss(forecast)", "create(advice)", PUSH]
    assert "reverse (winter)" in created(calls, "advice")["message"]


def test_ex4_winter_already_set_no_write(bp):
    _, calls = evaluate(bp, at(18, 0), hourly_fc=hourly(5), toggle="on", direction="reverse")
    assert not any(c[0].startswith("input_boolean.") for c in calls)
    assert labels(calls) == ["get_forecasts(hourly)", "dismiss(forecast)", "dismiss(advice)"]


def test_ex5_warm_lows_write_nothing_and_band_is_8_14(bp):
    for low in (16, 17, 15, 14):
        ctx, calls = evaluate(bp, at(18, 0), hourly_fc=hourly(low), toggle="off", direction="forward")
        assert not any(c[0].startswith("input_boolean.") for c in calls), low
        assert ctx["season_target"] == "summer"
    for low, target in ((8.0, "winter"), (8.5, "hold"), (13.5, "hold"), (14.0, "summer"), (7.9, "winter")):
        assert evaluate(bp, at(18, 0), hourly_fc=hourly(low))[0]["season_target"] == target, low


def test_ex6_running_fan_gets_advice_never_a_command(bp):
    _, calls = evaluate(bp, at(18, 0), hourly_fc=hourly(4), fan="on", direction="forward")
    assert labels(calls) == ["get_forecasts(hourly)", "input_boolean.turn_on", "dismiss(forecast)",
                             "create(advice)", PUSH]
    assert not any(c[0].startswith("fan.") for c in calls)
    _, calls = evaluate(bp, at(19, 0), fan="on", direction="forward", toggle="on",
                        toggle_since=at(18, 0))
    assert calls == []


def test_ex7_at_most_two_advices_per_evening(bp):
    ticks = [at(18, 0), at(18, 15), at(18, 30), at(18, 45)]
    # lows 4/16/4/16, toggle off since yesterday: one write, one advice, the latch holds
    w = world(at(18, 0), toggle="off", direction="forward")
    runs = run_ticks(bp, ticks, w, [4, 16, 4, 16])
    assert labels(runs[0][1]) == ["get_forecasts(hourly)", "input_boolean.turn_on", "dismiss(forecast)",
                                  "create(advice)", PUSH]
    for _, calls in runs[1:]:
        assert labels(calls) == ["get_forecasts(hourly)", "dismiss(forecast)"]
    # hand flip at 18:05: no Stage A write and no push that evening
    for state in ("on", "off"):
        w = world(at(18, 15), toggle=state, toggle_since=at(18, 5), direction="forward")
        for _, calls in run_ticks(bp, ticks[1:], w, [4, 16, 4]):
            assert not any(c[0].startswith("input_boolean.") or c[0].startswith("notify.") for c in calls)
            assert "create(advice)" not in labels(calls)
    # 18:00 no change (hold) + 18:15 band-edge change: advice at both, none later
    w = world(at(18, 0), toggle="off", direction=None)
    runs = run_ticks(bp, ticks, w, [10, 8.0, 16, 4])
    assert labels(runs[0][1]) == ["get_forecasts(hourly)", "dismiss(forecast)", "create(advice)", PUSH]
    assert labels(runs[1][1]) == ["get_forecasts(hourly)", "input_boolean.turn_on", "dismiss(forecast)",
                                  "create(advice)", PUSH]
    for _, calls in runs[2:]:
        assert labels(calls) == ["get_forecasts(hourly)", "dismiss(forecast)"]
    total = sum(len(pushes(c)) for _, c in runs)
    assert total == 2


def test_ex8_unavailable_or_directionless_fan(bp):
    for st in ("unavailable", "unknown"):
        ctx, calls = evaluate(bp, at(18, 0), hourly_fc=hourly(11), fan=st, direction=None)
        assert ctx["advice_reason"] == "fan_unavailable", st
        assert labels(calls) == ["get_forecasts(hourly)", "dismiss(forecast)", "create(advice)", PUSH]
        assert f"is {st}" in created(calls, "advice")["message"]
    ctx, calls = evaluate(bp, at(18, 0), hourly_fc=hourly(11), drop=(FAN,))
    assert ctx["advice_reason"] == "fan_unavailable" and ctx["fan_state"] == "absent"
    assert "is absent" in created(calls, "advice")["message"]
    ctx, calls = evaluate(bp, at(18, 0), hourly_fc=hourly(11), fan="off", direction=None)
    assert ctx["advice_reason"] == "direction_unknown"
    msg = created(calls, "advice")["message"]
    assert "reports no direction (state off)" in msg and "forward (summer)" in msg
    # 18:15: the fan is back and matching
    _, calls = evaluate(bp, at(18, 15), hourly_fc=hourly(11), fan="off", direction="forward")
    assert labels(calls) == ["get_forecasts(hourly)", "dismiss(forecast)", "dismiss(advice)"]


def test_ex9_other_room_sensors_never_read(bp, text):
    assert "sensor.temperature_sensor_3" not in text
    assert "fanprotection" not in text
    assert not any("fanprotection" in str(v) or "temperature_sensor_3" in str(v) for v in KIDS.values())


def test_ex10_forecast_validation_and_precedence(bp):
    t = at(18, 0)
    src = lambda **kw: evaluate(bp, t, **kw)[0]
    # >= 10 distinct in-window timestamps: hourly min (out-of-window -30 rows ignored)
    ctx = src(hourly_fc=hourly(4))
    assert (ctx["night_low"], ctx["night_low_source"]) == (4.0, "hourly")
    # a NaN row is dropped; hourly stays valid while >= 10 valid distinct remain
    ctx = src(hourly_fc=hourly(4, bad={2: float("nan")}))
    assert (ctx["night_low"], ctx["night_low_source"]) == (4.0, "hourly")
    for bad in ({1: float("inf")}, {1: float("-inf")}, {1: 46}, {1: -41}, {1: "3"}, {1: None}):
        ctx = src(hourly_fc=hourly(4, bad=bad))
        assert (ctx["night_low"], ctx["night_low_source"]) == (4.0, "hourly"), bad
    ctx = src(hourly_fc=hourly(4, n=11, bad={2: float("nan")}))
    assert ctx["night_low_source"] == "hourly"
    # three invalid of twelve -> 9 valid -> daily (tomorrow's templow, not today's row)
    bad3 = {1: float("nan"), 3: "x", 9: 99}
    ctx, calls = evaluate(bp, t, hourly_fc=hourly(4, bad=bad3), daily_fc=daily(6.5))
    assert (ctx["night_low"], ctx["night_low_source"]) == (6.5, "daily")
    assert labels(calls)[:2] == ["get_forecasts(hourly)", "get_forecasts(daily)"]
    # 12 rows sharing 3 timestamps -> daily
    same = [at(20, 0)] * 4 + [at(2, 0, day=1)] * 4 + [at(7, 0, day=1)] * 4
    assert src(hourly_fc=hourly(4, times=same), daily_fc=daily(6.5))["night_low_source"] == "daily"
    # endpoint rules: 10 rows all in 20:00-01:00; 10 rows starting 22:00
    assert src(hourly_fc=hourly(4, n=10, step=1800), daily_fc=daily(6.5))["night_low_source"] == "daily"
    assert src(hourly_fc=hourly(4, n=10, start=(22, 0)), daily_fc=daily(6.5))["night_low_source"] == "daily"
    assert src(hourly_fc=hourly(4, n=10, start=(21, 0)), daily_fc=daily(6.5))["night_low_source"] == "hourly"
    # weather not usable -> no fetch at all -> live outdoor reading
    for kw in (dict(weather_unit="°F"), dict(weather="unavailable"), dict(weather="unknown"),
               dict(weather_age=4 * 3600), dict(drop=(WEATHER,))):
        ctx, calls = evaluate(bp, t, hourly_fc=hourly(4), daily_fc=daily(6.5), **kw)
        assert not any(c[0] == "weather.get_forecasts" for c in calls), kw
        assert (ctx["night_low"], ctx["night_low_source"]) == (11.0, "live"), kw
        assert labels(calls) == ["create(forecast)", "create(advice)", PUSH] or \
            labels(calls) == ["create(forecast)", "dismiss(advice)"], (kw, labels(calls))
        assert "live outdoor reading" in created(calls, "forecast")["message"]
    # outdoor stale / °F / NaN / inf / out of range -> absent
    for kw in (dict(outdoor_age=3 * 3600), dict(outdoor_unit="°F"), dict(outdoor="nan"),
               dict(outdoor="inf"), dict(outdoor="50"), dict(outdoor="unavailable")):
        assert src(weather="unavailable", **kw)["night_low_source"] == "none", kw
    # hourly raise or [] -> tomorrow's daily templow; no daily fetch when hourly is valid
    for fc in (RAISE, [], {WEATHER: {"forecast": "x"}}, {WEATHER: 5}, {}):
        ctx, calls = evaluate(bp, t, hourly_fc=fc, daily_fc=daily(6.5, today_low=2.0))
        assert (ctx["night_low"], ctx["night_low_source"]) == (6.5, "daily"), fc
        assert labels(calls)[:2] == ["get_forecasts(hourly)", "get_forecasts(daily)"]
    _, calls = evaluate(bp, t, hourly_fc=hourly(4), daily_fc=daily(6.5))
    assert labels(calls).count("get_forecasts(daily)") == 0
    # daily unsupported -> no daily fetch
    _, calls = evaluate(bp, t, hourly_fc=[], daily_fc=daily(6.5), features=2)
    assert "get_forecasts(daily)" not in labels(calls)
    # all absent -> no toggle write, the forecast notice says no decision was made
    ctx, calls = evaluate(bp, t, hourly_fc=RAISE, daily_fc=RAISE, toggle="off", direction="reverse",
                          drop=(OUTDOOR,))
    assert ctx["night_low_source"] == "none" and ctx["season_target"] == "hold"
    assert not any(c[0].startswith("input_boolean.") for c in calls)
    assert "no season decision" in created(calls, "forecast")["message"]
    assert created(calls, "advice")["message"].startswith("Night low unknown: set kids fan to forward (summer)")
    # message bodies never carry forecast strings
    for kw in (dict(hourly_fc=hourly(4)), dict(hourly_fc=[], daily_fc=daily(3)), dict(weather="unavailable")):
        _, calls = evaluate(bp, t, **kw)
        assert "<script>" not in json.dumps([c[2] for c in calls], ensure_ascii=False), kw


def test_ex11_hand_flip_outside_the_evening(bp):
    w = world(at(10, 0), toggle="on", toggle_since=at(10, 0), direction="forward")
    for t in (at(10, 0), at(10, 1), at(10, 15)):
        assert evaluate(bp, t, states=w)[1] == [], t
    # flip at 21:00: nothing until the next day's 18:00, where the latch permits a write
    w = world(at(21, 0), toggle="on", toggle_since=at(21, 0), direction="forward")
    for t in (at(21, 0), at(21, 15), at(23, 0), at(3, 0, day=1), at(17, 45, day=1)):
        assert evaluate(bp, t, states=w, hourly_fc=hourly(16, day=1))[1] == [], t
    w = world(at(18, 0, day=1), toggle="on", toggle_since=at(21, 0), direction="forward")
    _, calls = evaluate(bp, at(18, 0, day=1), states=w, hourly_fc=hourly(16, day=1))
    assert "input_boolean.turn_off" in labels(calls)


def test_ex12_ha_start_and_manual_run_issue_nothing(bp):
    worlds = [dict(), dict(toggle="on"), dict(fan="unavailable", direction=None), dict(drop=(TOGGLE,)),
              dict(weather="unavailable", drop=(OUTDOOR,))]
    for trig in (HA_START, MANUAL, {"id": "other", "platform": "event"}):
        for t in (at(18, 0), at(18, 15), at(12, 0)):
            for kw in worlds:
                ctx, calls = evaluate(bp, t, trigger=trig, hourly_fc=hourly(4), **kw)
                assert ctx["is_tick"] is False and calls == [], (trig, t, kw)
    # toggle absent from the state machine: no call off-evening, no render error at 18:00
    for t in (at(12, 0), at(12, 15), at(20, 30)):
        assert evaluate(bp, t, drop=(TOGGLE,))[1] == [], t
    ctx, calls = evaluate(bp, at(18, 0), hourly_fc=hourly(4), drop=(TOGGLE,))
    assert ctx["toggle_changed_ts"] == 0 and ctx["toggle_known"] is False
    assert labels(calls) == ["get_forecasts(hourly)", "dismiss(forecast)"]


def test_ex13_flip_off_before_the_decision(bp):
    _, calls = evaluate(bp, at(18, 0), hourly_fc=hourly(4), toggle="off", toggle_since=at(17, 0))
    assert "input_boolean.turn_on" in labels(calls)
    ctx, calls = evaluate(bp, at(18, 0), hourly_fc=hourly(11), toggle="off", toggle_since=at(17, 0),
                          direction="reverse")
    assert ctx["season_target"] == "hold" and not any(c[0].startswith("input_boolean.") for c in calls)
    assert "forward (summer)" in created(calls, "advice")["message"]


def test_ex14_decide_time_moves_all_four_ticks(bp):
    inputs = {**KIDS, "decide_time": "18:10:00"}
    stage = {at(18, 10): 0, at(18, 25): 1, at(18, 40): 2, at(18, 55): 3}
    for m in range(0, 60):
        ctx, calls = evaluate(bp, at(18, m), inputs=inputs, hourly_fc=hourly(4), direction="reverse",
                              toggle="on")
        idx = stage.get(at(18, m), -1)
        assert ctx["stage_a_index"] == idx and ctx["stage_a_due"] is (idx >= 0), m
        assert ctx["first_tick"] is (idx == 0), m
        assert ("get_forecasts(hourly)" in labels(calls)) is (idx >= 0), m
    _, calls = evaluate(bp, at(18, 15), inputs=inputs, direction="reverse", toggle="on")
    assert labels(calls) == ["dismiss(advice)"]
    _, calls = evaluate(bp, at(18, 0), inputs=inputs, direction="reverse", toggle="on")
    assert labels(calls) == ["dismiss(advice)"]


@pytest.mark.parametrize("services,expected", [
    ([], []),
    ([PUSH], [PUSH]),
    ([PUSH, "mobile_app_x", "notify.a b", "fan.turn_on", "notify.x; fan.turn_on", "notify.Bad-Name"], [PUSH]),
    (PUSH, [PUSH]),
])
def test_ex15_notify_filter(bp, services, expected):
    ctx, calls = evaluate(bp, at(18, 0), inputs={**KIDS, "notify_services": services},
                          hourly_fc=hourly(4), direction="forward")
    assert ctx["notify_list"] == expected
    assert [c[0] for c in pushes(calls)] == expected
    assert "create(advice)" in labels(calls)


def test_ex15_fan_name_charset(bp):
    for name, safe in (("kids fan", "kids fan"), ("<b>x</b>", "the fan"), ("", "the fan"),
                       ("x" * 33, "the fan"), ("a{{b}}", "the fan"), ("Kids_fan-2", "Kids_fan-2")):
        ctx, _ = evaluate(bp, at(12, 0), inputs={**KIDS, "fan_name": name})
        assert ctx["fan_name_safe"] == safe, name


def test_ex17_stage_a_present(bp):
    svcs = {_svc(s) for s in _service_nodes(bp)}
    assert {"input_boolean.turn_on", "input_boolean.turn_off", "weather.get_forecasts"} <= svcs


def test_f2_write_toggle_false_suppresses_only_the_write(bp):
    inputs = {**KIDS, "write_toggle": False}
    ctx, calls = evaluate(bp, at(18, 0), inputs=inputs, hourly_fc=hourly(4), toggle="off", direction="reverse")
    assert ctx["season_target"] == "winter" and ctx["toggle_write_due"] is False
    assert not any(c[0].startswith("input_boolean.") for c in calls)
    assert labels(calls) == ["get_forecasts(hourly)", "dismiss(forecast)", "create(advice)", PUSH]
    assert "forward (summer)" in created(calls, "advice")["message"]


def test_t7_forced_check_config(bp):
    """T7 4b: hold-band thresholds and write_toggle false; toggle ON by hand, fan off forward."""
    inputs = {**KIDS, "decide_time": "14:15:00", "outdoor_cold": -10, "outdoor_warm": 30,
              "write_toggle": False}
    w = world(at(14, 15), toggle="on", toggle_since=at(13, 50), fan="off", direction="forward")
    ctx, calls = evaluate(bp, at(14, 15), inputs=inputs, states=w, hourly_fc=hourly(4))
    assert labels(calls) == ["get_forecasts(hourly)", "dismiss(forecast)", "create(advice)", PUSH]
    assert ctx["night_low_source"] == "hourly"
    assert "set kids fan to reverse (winter)" in created(calls, "advice")["message"]
    # 4c: the real config again, toggle back OFF by hand -> next quarter only dismiss(advice)
    w = world(at(14, 30), toggle="off", toggle_since=at(14, 20), fan="off", direction="forward")
    assert labels(evaluate(bp, at(14, 30), states=w)[1]) == ["dismiss(advice)"]


def test_f6_missing_notify_service_never_loses_the_notice(bp):
    inputs = {**KIDS, "notify_services": ["notify.gone", PUSH]}
    with pytest.raises(ServiceNotFound) as exc:
        evaluate(bp, at(18, 0), inputs=inputs, hourly_fc=hourly(4), direction="forward")
    assert labels(exc.value.calls)[-1] == "create(advice)"


def test_f3_the_predeclaration_is_what_carries_the_response(bp):
    stripped = copy.deepcopy(bp)
    for vs in _var_steps(stripped):
        for name in RESPONSE_VARS:
            vs.pop(name, None)
    ctx, _ = evaluate(stripped, at(18, 0), hourly_fc=hourly(4), daily_fc=daily(6.5))
    assert ctx["night_low_source"] != "hourly"
    ctx, _ = evaluate(bp, at(18, 0), hourly_fc=hourly(4), daily_fc=daily(6.5))
    assert ctx["night_low_source"] == "hourly"


def test_f9_outdoor_sensor_normalised(bp):
    ctx, calls = evaluate(bp, at(18, 0), inputs={**KIDS, "outdoor_sensor": []}, weather="unavailable")
    assert ctx["outdoor_now"] is None and ctx["night_low_source"] == "none"
    assert "create(forecast)" in labels(calls)
    ctx, _ = evaluate(bp, at(18, 0), inputs={**KIDS, "outdoor_sensor": OUTDOOR}, weather="unavailable")
    assert (ctx["outdoor_now"], ctx["night_low_source"]) == (11.0, "live")
    ctx, _ = evaluate(bp, at(18, 0), inputs={**KIDS, "outdoor_sensor": [OUTDOOR, "sensor.other"]},
                      weather="unavailable", outdoor="7")
    assert ctx["outdoor_now"] == 7.0 and ctx["season_target"] == "winter"


def test_f10_decide_time_out_of_range(bp):
    for dt, ok in (("23:50:00", False), ("11:59:00", False), ("12:00:00", True), ("21:00:00", True),
                   ("21:01:00", False), ("06:00:00", False)):
        ctx, _ = evaluate(bp, at(12, 0), inputs={**KIDS, "decide_time": dt})
        assert ctx["decide_ok"] is ok, dt
    inputs = {**KIDS, "decide_time": "23:50:00"}
    ctx, calls = evaluate(bp, at(23, 50), inputs=inputs, hourly_fc=hourly(4), toggle="off", direction="reverse")
    assert ctx["stage_a_due"] is False
    assert labels(calls) == ["create(forecast)"]
    assert "12:00" in created(calls, "forecast")["message"]
    for t in (at(18, 0), at(0, 5, day=1), at(0, 20, day=1)):
        _, calls = evaluate(bp, t, inputs=inputs, hourly_fc=hourly(4), toggle="off", direction="reverse")
        assert calls == [], t


def test_f10_morning_forced_check_is_misconfig_only(bp):
    # R1-C-01: a forced check with a morning decide_time is rejected by F10 (runbook window is 12:00-16:00).
    inputs = {**KIDS, "decide_time": "10:15:00", "outdoor_cold": -10.0, "outdoor_warm": 30.0, "write_toggle": False}
    _, calls = evaluate(bp, at(10, 15), inputs=inputs, hourly_fc=hourly(4), toggle="on", direction="forward")
    assert labels(calls) == ["create(forecast)"]


def test_warm_not_above_cold_never_yields_both(bp):
    inputs = {**KIDS, "outdoor_cold": 10.0, "outdoor_warm": 10.0}
    assert evaluate(bp, at(18, 0), inputs=inputs, hourly_fc=hourly(10))[0]["season_target"] == "winter"
    inputs = {**KIDS, "outdoor_cold": 12.0, "outdoor_warm": 6.0}
    for low in (5, 9, 13):
        target = evaluate(bp, at(18, 0), inputs=inputs, hourly_fc=hourly(low))[0]["season_target"]
        assert target == ("winter" if low <= 12 else "summer"), low


def test_direction_inputs_outside_forward_reverse_suppress_advice(bp):
    inputs = {**KIDS, "winter_direction": "sideways"}
    ctx, calls = evaluate(bp, at(18, 0), inputs=inputs, hourly_fc=hourly(10), toggle="on", direction="forward")
    assert ctx["target_direction"] == "" and ctx["advice_reason"] == ""
    assert "create(advice)" not in labels(calls) and "dismiss(advice)" not in labels(calls)


def test_stage_a_never_on_non_tick_runs(bp):
    for trig in (HA_START, MANUAL):
        ctx, _ = evaluate(bp, at(18, 0), trigger=trig, hourly_fc=hourly(4))
        assert not (ctx["stage_a_due"] or ctx["first_tick"] or ctx["quarter_tick"] or ctx["toggle_write_due"])


# =========================================================================================
# 3. Instance
# =========================================================================================

def test_instance_passes_dry_run():
    r = deploy_run("--dry-run", str(BP_PATH), HA_PATH, str(KIDS_INSTANCE))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "dry-run: validation passed" in r.stdout
    assert "ok (id bedroom_fan_direction_kids" in r.stdout


def test_instance_values():
    inst = json.loads(KIDS_INSTANCE.read_text())
    assert inst["id"] == "bedroom_fan_direction_kids"
    assert inst["alias"] == "Kids room — fan direction v1.0.0"
    assert inst["use_blueprint"]["path"] == HA_PATH
    assert inst["trace"]["stored_traces"] == 60
    assert inst["use_blueprint"]["input"] == {
        "fan": FAN, "season_toggle": TOGGLE, "weather_entity": WEATHER, "outdoor_sensor": [OUTDOOR],
        "notify_services": [PUSH], "fan_name": "kids fan"}
