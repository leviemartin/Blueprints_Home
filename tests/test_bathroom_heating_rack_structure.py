"""Structural + rendered-logic pins for bathroom_heating_rack.yaml (Bathroom Heating Rack v3.0.0).

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
WED = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)  # a Wednesday
SAT = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)  # a Saturday


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


ALLWEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def base_ctx(**over):
    ctx = dict(
        entity_climate="climate.rack", sensor_bathroom_temp="sensor.t",
        entity_backup_temps=["sensor.hue"],
        entity_vacation=["input_boolean.vac"], entity_boost="input_boolean.boost",
        drive_setpoint=24, restart_deadband=0.3,
        boost_runtime_min=55, boost_target_temp=22, idle_setpoint=7,
        evening_preheat=False,
        warmup_base_min=10, warmup_per_degree_min=5, warmup_min_minutes=10, warmup_max_minutes=60,
        enable_notifications=True, notify_targets=[],
        morning_a_days=ALLWEEK, morning_a_target_warm="06:45:00", morning_a_hold_until="07:45:00",
        morning_a_target_temp=22,
        morning_b_days=[], morning_b_target_warm="08:30:00", morning_b_hold_until="09:30:00",
        morning_b_target_temp=22,
        evening_a_days=ALLWEEK, evening_a_target_warm="18:30:00", evening_a_hold_until="19:30:00",
        evening_a_target_temp=22,
        evening_b_days=[], evening_b_target_warm="20:30:00", evening_b_hold_until="22:00:00",
        evening_b_target_temp=22,
        trigger={"id": "periodic"},
    )
    ctx.update(over)
    return ctx


def world(room="21.0", hue="20.3", sp=7.0, rack_cur=25.0, boost=("off", 600), vac="off"):
    return _States({
        "sensor.t": _State(room), "sensor.hue": _State(hue),
        "climate.rack": _State("unknown", attrs={"temperature": sp, "current_temperature": rack_cur,
                                                   "target_temp_step": 1.0, "min_temp": 7.0, "max_temp": 30.0}),
        "input_boolean.vac": _State(vac, 600), "input_boolean.boost": _State(boost[0], boost[1]),
    })


def at(hhmm, day=NOW):
    hh, mm = map(int, hhmm.split(":"))
    return day.replace(hour=hh, minute=mm, second=0, microsecond=0)


def decide(bp, ctx, w, when=NOW):
    out = render_vars(bp, ctx, w, "active_priority", when)
    return out["active_priority"], out["desired_setpoint"]


# ---------------------------------------------------------------- structure pins

def test_version_bumped(bp):
    assert bp["blueprint"]["name"] == "Bathroom Heating Rack v3.0.0"
    assert bp["blueprint"]["description"].lstrip().startswith("**Version: 3.0.0**")
    assert "DRAFT" not in bp["blueprint"]["description"]
    assert "room-sensor thermostat" in bp["blueprint"]["description"]


EXPECTED_INPUTS = {
    "heating_climate", "bathroom_temp_sensor", "backup_temp_sensors", "vacation_off", "boost_toggle",
    "drive_setpoint", "restart_deadband", "boost_target_temp", "boost_runtime_min", "idle_setpoint",
    "morning_a_days", "morning_a_target_warm", "morning_a_hold_until", "morning_a_target_temp",
    "morning_b_days", "morning_b_target_warm", "morning_b_hold_until", "morning_b_target_temp",
    "evening_a_days", "evening_a_target_warm", "evening_a_hold_until", "evening_a_target_temp",
    "evening_b_days", "evening_b_target_warm", "evening_b_hold_until", "evening_b_target_temp",
    "evening_preheat",
    "warmup_base_min", "warmup_per_degree_min", "warmup_min_minutes", "warmup_max_minutes",
    "enable_notifications", "notify_targets",
}


def test_input_schema_exact_keys(inputs):
    assert set(inputs) == EXPECTED_INPUTS


def test_removed_inputs_absent(inputs):
    for k in ("fan_switch", "comfort_floor_delta", "hall_motion", "stairs_motion", "enable_predictive_motion"):
        assert k not in inputs


def test_selectors_and_defaults(inputs):
    assert inputs["backup_temp_sensors"]["default"] == []
    assert inputs["backup_temp_sensors"]["selector"]["entity"] == {
        "domain": "sensor", "device_class": "temperature", "multiple": True}
    assert inputs["drive_setpoint"]["default"] == 24
    assert inputs["drive_setpoint"]["selector"]["number"] == {"min": 18, "max": 30, "step": 1, "unit_of_measurement": "°C"}
    assert inputs["restart_deadband"]["default"] == 0.3
    assert inputs["restart_deadband"]["selector"]["number"] == {"min": 0.1, "max": 2, "step": 0.1, "unit_of_measurement": "°C"}
    assert inputs["boost_target_temp"]["default"] == 22
    assert inputs["boost_target_temp"]["selector"]["number"] == {"min": 18, "max": 28, "step": 0.5, "unit_of_measurement": "°C"}
    assert inputs["boost_runtime_min"]["default"] == 30
    assert inputs["vacation_off"]["default"] == []
    assert inputs["vacation_off"]["selector"]["entity"] == {"domain": "input_boolean", "multiple": True}
    assert inputs["boost_toggle"]["selector"]["entity"]["domain"] == "input_boolean"
    assert "default" not in inputs["boost_toggle"]
    assert inputs["idle_setpoint"]["default"] == 7
    assert inputs["evening_preheat"]["default"] is False
    assert inputs["evening_preheat"]["selector"] == {"boolean": {}}
    assert inputs["warmup_min_minutes"]["default"] == 10
    assert inputs["warmup_max_minutes"]["default"] == 60
    assert inputs["enable_notifications"]["default"] is True
    assert inputs["notify_targets"]["default"] == []
    assert inputs["notify_targets"]["selector"] == {"text": {"multiple": True}}
    for slot in ("morning_a", "morning_b", "evening_a", "evening_b"):
        assert inputs[f"{slot}_target_temp"]["selector"]["number"]["step"] == 0.5
        assert inputs[f"{slot}_target_warm"]["selector"] == {"time": {}}
        assert inputs[f"{slot}_hold_until"]["selector"] == {"time": {}}
    assert inputs["morning_a_days"]["default"] == ALLWEEK
    assert inputs["evening_a_days"]["default"] == ALLWEEK
    assert inputs["morning_b_days"]["default"] == []
    assert inputs["evening_b_days"]["default"] == []


def test_every_input_has_a_description(inputs):
    missing = [k for k, v in inputs.items() if not str(v.get("description", "")).strip()]
    assert missing == []


def test_variable_mappings(bp):
    v = bp["variables"]
    assert v["entity_climate"] == _Input("heating_climate")
    assert v["sensor_bathroom_temp"] == _Input("bathroom_temp_sensor")
    assert v["entity_backup_temps"] == _Input("backup_temp_sensors")
    assert v["entity_vacation"] == _Input("vacation_off")
    assert v["entity_boost"] == _Input("boost_toggle")
    assert v["drive_setpoint"] == _Input("drive_setpoint")
    assert v["restart_deadband"] == _Input("restart_deadband")
    assert v["evening_preheat"] == _Input("evening_preheat")
    assert v["notify_targets"] == _Input("notify_targets")
    for k in ("entity_fan", "comfort_floor_delta", "sensor_hall_motion", "sensor_stairs_motion", "enable_predictive_motion"):
        assert k not in v
    passthrough = EXPECTED_INPUTS - {"heating_climate", "bathroom_temp_sensor", "backup_temp_sensors", "vacation_off", "boost_toggle"}
    for k in passthrough:
        assert v[k] == _Input(k), k


def test_mode_restart(bp):
    assert bp["mode"] == "restart"
    assert bp["max_exceeded"] == "silent"


def test_trigger_roster(bp):
    trig = {t["id"]: t for t in bp["trigger"]}
    assert list(trig) == ["periodic", "boost_change", "vacation_change", "ha_start", "climate_lost", "temp_lost", "backup_lost"]
    assert "fan_change" not in trig
    assert trig["periodic"] == {"platform": "time_pattern", "minutes": "/1", "id": "periodic"}
    assert trig["boost_change"] == {"platform": "state", "entity_id": _Input("boost_toggle"), "to": ["on", "off"], "id": "boost_change"}
    assert trig["vacation_change"] == {"platform": "state", "entity_id": _Input("vacation_off"), "to": ["on", "off"], "id": "vacation_change"}
    assert trig["ha_start"] == {"platform": "homeassistant", "event": "start", "id": "ha_start"}
    assert trig["climate_lost"] == {"platform": "state", "entity_id": _Input("heating_climate"), "to": "unavailable",
                                    "for": {"minutes": 5}, "id": "climate_lost"}
    assert trig["temp_lost"] == {"platform": "state", "entity_id": _Input("bathroom_temp_sensor"), "to": ["unavailable", "unknown"],
                                 "for": {"minutes": 10}, "id": "temp_lost"}
    assert trig["backup_lost"] == {"platform": "state", "entity_id": _Input("backup_temp_sensors"), "to": ["unavailable", "unknown"],
                                   "for": {"minutes": 10}, "id": "backup_lost"}


def test_action_shape(bp):
    kinds = [step_kind(s) for s in bp["action"]]
    assert kinds == ["variables", "variables", "variables", "variables",
                      "choose", "choose", "choose", "choose", "choose", "choose", "choose"]
    chooses = choose_steps(bp)
    assert len(chooses) == 7
    # climate validation: unavailable → create + (push on the edge) + stop; available → dismiss
    unavailable, available = chooses[0]["choose"]
    assert branch_cond(unavailable) == "{{ states[entity_climate] is none or states(entity_climate) == 'unavailable' }}"
    assert service_of(unavailable["sequence"]) == "persistent_notification.create"
    assert unavailable["sequence"][-1] == {"stop": "Climate entity unavailable"}
    assert branch_cond(available) == "{{ states[entity_climate] is not none and states(entity_climate) != 'unavailable' }}"
    assert available["sequence"] == [{"service": "persistent_notification.dismiss", "continue_on_error": True,
                                      "data": {"notification_id": "heating_rack_climate_unavailable"}}]
    # climate validation sits before the service calls
    assert service_of(chooses[1]["choose"][0]["sequence"]) == "climate.set_hvac_mode"
    assert service_of(chooses[2]["choose"][0]["sequence"]) == "climate.set_temperature"
    # room-sensor warning sits AFTER the climate calls
    lost, back = chooses[3]["choose"]
    assert branch_cond(lost) == "{{ not indoor_temp_has_primary }}"
    assert service_of(lost["sequence"]) == "persistent_notification.create"
    assert branch_cond(back) == "{{ indoor_temp_has_primary }}"
    assert back["sequence"] == [{"service": "persistent_notification.dismiss", "continue_on_error": True,
                                 "data": {"notification_id": "heating_rack_sensor_warning"}}]
    # every push after the climate calls (indices 3, 4, 5 all come after 1, 2)
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
    for idx, trigger_ids in ((0, ["climate_lost", "temp_lost"]),):
        seq = chooses[idx]["choose"][0]["sequence"]
        nested = [d for d in seq if "choose" in d]
        assert len(nested) == len(trigger_ids)
        for block, trigger_id in zip(nested, trigger_ids):
            (branch,) = block["choose"]
            assert branch_cond(branch) == f"{{{{ trigger.id | default('') == '{trigger_id}' }}}}"
            assert any("repeat" in d for d in walk(branch["sequence"]))
            assert "default" not in block
    assert chooses[0]["choose"][0]["sequence"][-1] == {"stop": "Climate entity unavailable"}


def test_room_sensor_pushes_are_edge_gated(bp):
    # STEP 7's "not indoor_temp_has_primary" branch carries two edge-gated pushes: the primary-lost
    # push (temp_lost) and, when the backup then also dies, the fully-blind push (backup_lost).
    seq = choose_steps(bp)[3]["choose"][0]["sequence"]
    nested = [d for d in seq if "choose" in d]
    assert len(nested) == 2
    temp_block, backup_block = nested
    (temp_branch,) = temp_block["choose"]
    assert branch_cond(temp_branch) == "{{ trigger.id | default('') == 'temp_lost' }}"
    assert any("repeat" in d for d in walk(temp_branch["sequence"]))
    (backup_branch,) = backup_block["choose"]
    assert branch_cond(backup_branch) == "{{ trigger.id | default('') == 'backup_lost' and not indoor_temp_has_backup }}"
    assert any("repeat" in d for d in walk(backup_branch["sequence"]))
    assert "default" not in temp_block
    assert "default" not in backup_block


def test_no_fan_remnants(bp):
    names = [n for b in var_blocks(bp) for n in b]
    assert not any("fan" in n.lower() for n in names)
    text = BP_PATH.read_text()
    assert "fan_switch" not in text
    assert "entity_fan" not in text
    assert "P2_fan_coord" not in text
    assert not re.search(r"\blight\.fan\b|\bfan_is_on\b", text)


def test_no_comfort_floor_remnants(bp):
    text = BP_PATH.read_text()
    assert "comfort_floor" not in text
    names = [n for b in var_blocks(bp) for n in b]
    removed = {f"{p}_{suf}" for p in ("ma", "mb", "ea", "eb") for suf in ("floor", "active", "heating", "target_dev")}
    assert not (set(names) & removed)


def test_no_current_temperature_in_blueprint():
    text = BP_PATH.read_text()
    bad = [l for l in text.splitlines() if "current_temperature" in l and not l.strip().startswith("#")]
    assert bad == [], bad


def test_weekday_locale_safe(bp):
    tpl = norm(get_var(bp, "today_dow"))
    assert tpl == "{{ ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'][now().weekday()] }}"
    assert "strftime('%a')" not in BP_PATH.read_text()


@pytest.mark.parametrize("slot,prefix", [("morning_a", "ma"), ("morning_b", "mb")])
def test_morning_slot_templates(bp, slot, prefix):
    assert norm(get_var(bp, f"{prefix}_in_days")) == f"{{{{ today_dow in {slot}_days }}}}"
    assert norm(get_var(bp, f"{prefix}_hold_until_dt")) == norm(
        f"{{% set w = today_at({slot}_target_warm) %}}{{% set h = today_at({slot}_hold_until) %}}"
        "{{ h + timedelta(days=1) if h <= w else h }}")
    assert norm(get_var(bp, f"{prefix}_delta_T")) == norm(
        f"{{{{ [0, {slot}_target_temp | float - indoor_temp | float] | max }}}}")
    assert norm(get_var(bp, f"{prefix}_warmup_min")) == norm(
        "{{ [warmup_max_minutes | int, [warmup_min_minutes | int, "
        f"(warmup_base_min | int) + (warmup_per_degree_min | int) * ({prefix}_delta_T | float)] | max ] | min | int }}}}")
    assert norm(get_var(bp, f"{prefix}_open_dt")) == norm(
        f"{{{{ as_datetime({prefix}_target_warm_dt) - timedelta(minutes=(warmup_max_minutes | int if latch_ok else {prefix}_warmup_min | int)) }}}}")
    assert norm(get_var(bp, f"{prefix}_in_window")) == norm(
        f"{{{{ {prefix}_in_days and as_datetime({prefix}_open_dt) <= as_datetime(now_dt) "
        f"and as_datetime(now_dt) < as_datetime({prefix}_hold_until_dt) }}}}")


@pytest.mark.parametrize("slot,prefix", [("evening_a", "ea"), ("evening_b", "eb")])
def test_evening_slot_templates(bp, slot, prefix):
    assert norm(get_var(bp, f"{prefix}_in_days")) == f"{{{{ today_dow in {slot}_days }}}}"
    assert norm(get_var(bp, f"{prefix}_warmup_min")) == norm(
        "{% if evening_preheat %}{{ [warmup_max_minutes | int, [warmup_min_minutes | int, "
        f"(warmup_base_min | int) + (warmup_per_degree_min | int) * ({prefix}_delta_T | float)] | max] | min | int }}}}"
        "{% else %}0{% endif %}")
    assert norm(get_var(bp, f"{prefix}_open_dt")) == norm(
        f"{{{{ as_datetime({prefix}_target_warm_dt) - timedelta(minutes=(warmup_max_minutes | int "
        f"if (evening_preheat and latch_ok) else {prefix}_warmup_min | int)) }}}}")
    assert norm(get_var(bp, f"{prefix}_in_window")) == norm(
        f"{{{{ {prefix}_in_days and as_datetime({prefix}_open_dt) <= as_datetime(now_dt) "
        f"and as_datetime(now_dt) < as_datetime({prefix}_hold_until_dt) }}}}")


def test_room_decision_templates(bp):
    assert norm(get_var(bp, "target_source")) == norm(
        "{% if boost_active %}boost{% elif ea_in_window %}evening_a{% elif eb_in_window %}evening_b"
        "{% elif ma_in_window %}morning_a{% elif mb_in_window %}morning_b{% else %}none{% endif %}")
    assert norm(get_var(bp, "room_target")) == norm(
        "{% if target_source == 'boost' %}{{ boost_target_temp | float }}"
        "{% elif target_source == 'evening_a' %}{{ evening_a_target_temp | float }}"
        "{% elif target_source == 'evening_b' %}{{ evening_b_target_temp | float }}"
        "{% elif target_source == 'morning_a' %}{{ morning_a_target_temp | float }}"
        "{% elif target_source == 'morning_b' %}{{ morning_b_target_temp | float }}"
        "{% else %}0{% endif %}")
    assert norm(get_var(bp, "heat_line")) == norm(
        "{{ (room_target | float - (0 if heating_now else restart_deadband | float)) | round(2) }}")
    assert norm(get_var(bp, "call_for_heat")) == norm(
        "{{ target_source != 'none' and room_known and indoor_temp | float | round(2) < heat_line | float }}")


def test_priority_labels_templates(bp):
    assert norm(get_var(bp, "desired_mode")) == "{% if vacation_active %}off{% else %}heat_cool{% endif %}"
    assert norm(get_var(bp, "desired_setpoint")) == norm(
        "{% if vacation_active %}none{% elif call_for_heat %}{{ drive_setpoint_dev }}{% else %}{{ idle_setpoint_dev }}{% endif %}")
    assert norm(get_var(bp, "active_priority")) == norm(
        "{% set base = {'boost': 'P3_boost', 'evening_a': 'P4_evening', 'evening_b': 'P4_evening', "
        "'morning_a': 'P5_morning', 'morning_b': 'P5_morning'} %}"
        "{% if vacation_active %}P1_vacation{% elif target_source == 'none' %}P6_idle"
        "{% elif call_for_heat %}{{ base[target_source] }}{% elif not room_known %}{{ base[target_source] }}_blind"
        "{% else %}{{ base[target_source] }}_satisfied{% endif %}")


def test_setpoint_and_room_sensor_templates(bp):
    assert norm(get_var(bp, "idle_setpoint_dev")) == norm(
        "{{ [setpoint_max | float, [setpoint_min | float, ((((idle_setpoint | float) / (setpoint_step | float) + 0.501) | int) * (setpoint_step | float))] | max] | min | round(2) }}")
    assert norm(get_var(bp, "drive_setpoint_dev")) == norm(
        "{{ [setpoint_max | float, [setpoint_min | float, ((((drive_setpoint | float) / (setpoint_step | float) + 0.501) | int) * (setpoint_step | float))] | max] | min | round(2) }}")
    assert norm(get_var(bp, "setpoint_min")) == "{{ state_attr(entity_climate, 'min_temp') | float(7) }}"
    assert norm(get_var(bp, "setpoint_max")) == "{{ state_attr(entity_climate, 'max_temp') | float(30) }}"
    assert norm(get_var(bp, "setpoint_step")) == norm(
        "{% set s = state_attr(entity_climate, 'target_temp_step') | float(0) %}{{ s if s > 0 else 0.5 }}")
    assert norm(get_var(bp, "heating_now")) == norm(
        "{{ current_hvac_mode_normalized == 'heat_cool' and (current_setpoint | float - drive_setpoint_dev | float) | abs < 0.1 }}")
    assert norm(get_var(bp, "notify_list")) == norm(
        "{{ (notify_targets if (notify_targets is iterable and notify_targets is not string) else ([notify_targets] if notify_targets else [])) | select('match', '^notify[.][a-z0-9_]+$') | list }}")
    assert norm(get_var(bp, "indoor_temp_has_primary")) == "{{ indoor_temp_primary | float(-99) > -50 }}"
    assert norm(get_var(bp, "room_known")) == "{{ indoor_temp_has_primary or indoor_temp_has_backup }}"


def test_latch_ok_template_and_position(bp):
    # latch_ok must be defined after boost_is_on/boost_age_min (STEP 1) and used by STEP 2 instead
    # of heating_now, so a fresh/active boost can never masquerade as a slot-started heat.
    assert norm(get_var(bp, "latch_ok")) == norm(
        "{{ heating_now and not boost_is_on and boost_age_min >= warmup_max_minutes | int }}")
    step1 = var_blocks(bp)[0]
    names = list(step1)
    assert names.index("boost_age_min") < names.index("latch_ok") < len(names)
    assert "latch_ok" in step1
    assert "latch_ok" not in var_blocks(bp)[1]


def test_debug_dump_includes_latch_ok(bp):
    branch = choose_steps(bp)[5]["choose"][0]
    msg = " ".join(str(d.get("message", "")) for d in walk(branch["sequence"]) if "message" in d)
    assert "latch_ok" in msg or "{{ latch_ok }}" in msg


def test_no_bare_boolean_text(bp):
    for block in var_blocks(bp):
        for name, tpl in block.items():
            s = norm(tpl)
            assert not re.search(r"%\}\s*(true|false)\s*\{%", s, re.I), name
            assert not re.search(r"%\}\s*(true|false)\s*$", s, re.I), name


def test_no_bare_condition_steps_anywhere(bp):
    for step in bp["action"]:
        assert step_kind(step) != "condition"


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
    assert len(repeats) == 5
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


def test_debug_block_manual_only(bp):
    branch = choose_steps(bp)[5]["choose"][0]
    assert branch_cond(branch) == "{{ trigger.id | default('manual') == 'manual' }}"
    ids = [d["notification_id"] for d in walk(branch["sequence"]) if "notification_id" in d]
    assert ids == ["heating_rack_debug"]


# ---------------------------------------------------------------- rendered logic

def test_today_dow_rows(bp):
    assert render_tpl(bp, get_var(bp, "today_dow"), world()) == "tue"
    assert render_tpl(bp, get_var(bp, "today_dow"), world(), when=NOW + timedelta(days=5)) == "sun"


@pytest.mark.parametrize("field", ["idle_setpoint_dev", "drive_setpoint_dev"])
@pytest.mark.parametrize("raw,step,expected", [
    (7.0, 1.0, 7.0), (7.0, 0.5, 7.0), (24.0, 1.0, 24.0),
    (22.3, 0.1, 22.3), (21.7, 0.1, 21.7), (22.35, 0.1, 22.4), (22.65, 0.1, 22.7),
])
def test_setpoint_rounding_rows(bp, field, raw, step, expected):
    ctx = base_ctx(**({"idle_setpoint": raw} if field == "idle_setpoint_dev" else {"drive_setpoint": raw}))
    w = world(sp=7.0)
    w.table["climate.rack"].attributes["target_temp_step"] = step
    out = render_vars(bp, ctx, w, field, NOW)
    assert out[field] == pytest.approx(expected)


@pytest.mark.parametrize("field,raw,lo,hi,expected", [
    ("idle_setpoint", 5.0, 7.0, 30.0, 7.0),
    ("idle_setpoint", 31.0, 7.0, 30.0, 30.0),
    ("drive_setpoint", 26.0, 7.0, 25.0, 25.0),
])
def test_setpoint_clamped_to_device_range(bp, field, raw, lo, hi, expected):
    ctx = base_ctx(**{field: raw})
    outname = "idle_setpoint_dev" if field == "idle_setpoint" else "drive_setpoint_dev"
    w = world()
    w.table["climate.rack"].attributes.update({"min_temp": lo, "max_temp": hi})
    out = render_vars(bp, ctx, w, outname, NOW)
    assert out[outname] == pytest.approx(expected)


def test_setpoint_range_defaults_when_attrs_missing(bp):
    w = world()
    w.table["climate.rack"] = _State("unknown", attrs={"temperature": 7.0})
    out = render_vars(bp, base_ctx(), w, "idle_setpoint_dev")
    assert (out["setpoint_min"], out["setpoint_max"], out["idle_setpoint_dev"]) == (7.0, 30.0, 7.0)


@pytest.mark.parametrize("targets,expected", [
    (["notify.mobile_app_martin_fold"], ["notify.mobile_app_martin_fold"]),
    (["notify.mobile_app_martin_fold", "mobile_app_x", "notify.Bad-Name", "script.foo", "notify.a b"], ["notify.mobile_app_martin_fold"]),
    ([], []),
    ("notify.mobile_app_martin_fold", ["notify.mobile_app_martin_fold"]),   # scalar guard
])
def test_notify_list_filters_names(bp, targets, expected):
    assert render_vars(bp, base_ctx(notify_targets=targets), world(), "notify_list")["notify_list"] == expected


def test_heating_now_detection(bp):
    out = render_vars(bp, base_ctx(), world(sp=24.0), "heating_now")
    assert out["heating_now"] is True
    out = render_vars(bp, base_ctx(), world(sp=7.0), "heating_now")
    assert out["heating_now"] is False
    out = render_vars(bp, base_ctx(), world(sp=22.0), "heating_now")
    assert out["heating_now"] is False


def test_hvac_mode_normalisation(bp):
    out = render_vars(bp, base_ctx(), world(), "current_hvac_mode_normalized")
    assert (out["current_hvac_mode"], out["current_hvac_mode_normalized"]) == ("unknown", "heat_cool")


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


@pytest.mark.parametrize("enabled,desired,current,expected", [
    (True, 24.0, 7.0, True),      # the tick that raises the setpoint
    (True, 24.0, 24.0, False),    # already raised
    (True, 7.0, 7.0, False),      # idle
    (True, "none", 7.0, False),   # vacation
    (False, 24.0, 7.0, False),    # notifications disabled
])
def test_warmup_notify_condition_rows(bp, enabled, desired, current, expected):
    tpl = choose_steps(bp)[4]["choose"][0]["conditions"][0]["value_template"]
    got = render_tpl(bp, tpl, world(), enable_notifications=enabled, desired_setpoint=desired,
                     current_setpoint=current, idle_setpoint_dev=7.0)
    assert got is expected


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


@pytest.mark.parametrize("indoor,floor,expected_min,expected_open", [
    (20.0, 10, 20, "06:25"),   # ΔT 2 (target 22) → 10 + 5·2
    (10.0, 10, 60, "05:45"),   # cap 60
])
def test_warmup_lead_rows(bp, indoor, floor, expected_min, expected_open):
    ctx = base_ctx(warmup_min_minutes=floor)
    out = render_vars(bp, ctx, world(room=str(indoor)), "ma_open_dt", WED)
    assert out["ma_warmup_min"] == expected_min
    assert as_datetime(out["ma_open_dt"]).strftime("%H:%M") == expected_open


@pytest.mark.parametrize("warm,hold,hhmm,expected_hold_day,in_window", [
    ("06:45:00", "07:45:00", "07:00", 23, True),    # normal same-day window
    ("23:00:00", "01:00:00", "23:30", 24, True),    # hold before warm → next day; window runs to midnight
    ("23:00:00", "22:00:00", "23:30", 24, True),    # hold before warm → next day
    ("23:00:00", "23:00:00", "23:30", 24, True),    # hold == warm → next day
    ("23:00:00", "01:00:00", "00:30", 24, False),   # before the (same-day) open edge: not in window
])
def test_hold_until_anchor_rows(bp, warm, hold, hhmm, expected_hold_day, in_window):
    ctx = base_ctx(morning_a_target_warm=warm, morning_a_hold_until=hold)
    out = render_vars(bp, ctx, world(room="10.0"), "ma_in_window", at(hhmm, WED))
    assert as_datetime(out["ma_hold_until_dt"]).day == expected_hold_day
    assert out["ma_in_window"] is in_window


def test_priority_vacation(bp):
    w = world(vac="on")
    out = render_vars(bp, base_ctx(), w, "active_priority", at("18:40", WED))
    assert out["vacation_active"] is True
    assert (out["desired_mode"], out["desired_setpoint"], out["active_priority"]) == ("off", "none", "P1_vacation")


def test_vacation_empty_list_is_false(bp):
    out = render_vars(bp, base_ctx(entity_vacation=[]), world(), "vacation_active")
    assert out["vacation_active"] is False


def test_boost_missing_entity_counts_as_never_on(bp):
    # v3 (board R1-D1-01): a missing boost entity is "never on" (age 100000 min), so it can neither
    # boost nor block the window latch.
    w = world()
    del w.table["input_boolean.boost"]
    out = render_vars(bp, base_ctx(), w, "boost_active")
    assert out["boost_age_min"] == 100000
    assert out["boost_active"] is False


def test_indoor_temp_fallback_rows(bp):
    out = render_vars(bp, base_ctx(), world(room="unavailable", hue="unavailable"), "indoor_temp")
    assert (out["room_known"], out["indoor_temp"]) == (False, 20)


def test_target_source_priority_order(bp):
    # boost beats evening beats morning when all are simultaneously in-window/active
    ctx = base_ctx()
    w = world(boost=("on", 5))
    out = render_vars(bp, ctx, w, "target_source", at("18:40", WED))
    assert out["target_source"] == "boost"


# ------------------------------------------------- backup sensor + edge-row additions

def test_backup_sensor_order(bp):
    ctx = base_ctx(entity_backup_temps=["sensor.hue", "sensor.hue2"])
    # first backup dead, second numeric -> second used
    w = world(room="unavailable", hue="unavailable")
    w.table["sensor.hue2"] = _State("20.0")
    out = render_vars(bp, ctx, w, "indoor_temp")
    assert (out["indoor_temp_has_backup"], out["indoor_temp"]) == (True, 20.0)
    # both numeric -> first (list order) wins
    w2 = world(room="unavailable", hue="19.0")
    w2.table["sensor.hue2"] = _State("20.0")
    out2 = render_vars(bp, ctx, w2, "indoor_temp")
    assert out2["indoor_temp"] == 19.0


def test_primary_used_when_backup_dead(bp):
    out = render_vars(bp, base_ctx(), world(room="21.0", hue="unavailable"), "indoor_temp")
    assert (out["indoor_temp_has_primary"], out["indoor_temp"]) == (True, 21.0)
    out2 = render_vars(bp, base_ctx(), world(room="21.0", hue="unavailable"), "active_priority", at("06:40", WED))
    assert out2["active_priority"] == "P5_morning"


def test_evening_preheat_opens_early(bp):
    ctx = base_ctx(evening_preheat=True)
    # room 20.0, target 22 -> ΔT 2 -> lead 20 -> opens 18:10
    out = render_vars(bp, ctx, world(room="20.0"), "ea_in_window", at("18:09", WED))
    assert out["ea_in_window"] is False
    out2 = render_vars(bp, ctx, world(room="20.0"), "ea_in_window", at("18:10", WED))
    assert out2["ea_in_window"] is True


def test_restart_deadband_custom(bp):
    ctx = base_ctx(restart_deadband=0.5)
    out = render_vars(bp, ctx, world(room="21.5"), "call_for_heat", at("06:40", WED))
    assert out["call_for_heat"] is False
    out2 = render_vars(bp, ctx, world(room="21.4"), "call_for_heat", at("06:40", WED))
    assert out2["call_for_heat"] is True


def test_idle_exact_restart_line_no_start(bp):
    # default restart_deadband 0.3, target 22 -> line 21.7; strict < required
    out = render_vars(bp, base_ctx(), world(room="21.7"), "call_for_heat", at("06:40", WED))
    assert out["call_for_heat"] is False


# ------------------------------------------------- R1-01: latch_ok gates the boost off heating_now


def test_latch_ok_closes_window_after_a_recent_boost(bp):
    # rack at 24 from a boost that turned off 5 min ago: not a slot-started heat, so the morning
    # opening edge must NOT latch to warmup_max_minutes (05:45) — it uses the ordinary ΔT lead
    # (ΔT 1 -> 15 min -> opens 06:30), which has not arrived yet at 05:50.
    w = world(sp=24.0, boost=("off", 5))
    out = render_vars(bp, base_ctx(), w, "active_priority", at("05:50", WED))
    assert out["latch_ok"] is False
    assert (out["active_priority"], out["desired_setpoint"]) == ("P6_idle", 7.0)


def test_latch_ok_holds_window_after_an_aged_boost(bp):
    # the boost has been off for 90 min (>= warmup_max_minutes): this is a slot-started heat, so
    # the latch still opens the window at target_warm - warmup_max_minutes (05:45).
    w = world(sp=24.0, room="21.6", boost=("off", 90))
    out = render_vars(bp, base_ctx(), w, "active_priority", at("06:32", WED))
    assert out["latch_ok"] is True
    assert (out["active_priority"], out["desired_setpoint"]) == ("P5_morning", 24.0)


def test_latch_ok_false_while_boost_is_on(bp):
    # an active boost never latches the morning window, whatever the rack currently holds.
    w = world(sp=24.0, boost=("on", 5))
    out = render_vars(bp, base_ctx(), w, "active_priority", at("05:50", WED))
    assert out["latch_ok"] is False
    assert (out["active_priority"], out["desired_setpoint"]) == ("P3_boost", 24.0)


def test_off_mode_not_heating_now_does_not_latch(bp):
    # rack mode 'off' with a stale setpoint of 24: never heating_now, so never latches.
    w = world(sp=24.0)
    w.table["climate.rack"] = _State("off", attrs={"temperature": 24.0, "current_temperature": 25.0,
                                                     "target_temp_step": 1.0, "min_temp": 7.0, "max_temp": 30.0})
    out = render_vars(bp, base_ctx(), w, "latch_ok")
    assert (out["heating_now"], out["latch_ok"]) == (False, False)


# ------------------------------------------------- R1-03: coverage gaps


def test_evening_beats_morning_when_both_in_window(bp):
    ctx = base_ctx(morning_a_hold_until="20:00:00", morning_a_target_temp=21, evening_a_target_temp=23)
    out = render_vars(bp, ctx, world(room="20.0"), "room_target", at("18:40", WED))
    assert (out["ma_in_window"], out["ea_in_window"]) == (True, True)
    assert (out["target_source"], out["room_target"]) == ("evening_a", 23.0)


def test_window_day_filter(bp):
    # a day not in the slot's list stays closed
    out = render_vars(bp, base_ctx(evening_a_days=["mon"]), world(room="20.0"), "ea_in_window", at("19:00", WED))
    assert (out["ea_in_days"], out["ea_in_window"]) == (False, False)
    # an empty days list (the B-slot default) also stays closed
    out_mb = render_vars(bp, base_ctx(), world(room="10.0"), "mb_in_window", at("08:45", WED))
    assert (out_mb["mb_in_days"], out_mb["mb_in_window"]) == (False, False)
    out_eb = render_vars(bp, base_ctx(), world(room="20.0"), "eb_in_window", at("21:00", WED))
    assert (out_eb["eb_in_days"], out_eb["eb_in_window"]) == (False, False)


def test_warmup_eta_rows(bp):
    seq = choose_steps(bp)[4]["choose"][0]["sequence"]
    eta_vars = seq[0]["variables"]
    env = make_env(world(), NOW)
    # v3: the ETA is measured to the ROOM target (22), not to the drive setpoint sent to the rack (24)
    assert "room_target" in norm(eta_vars["eta_delta"]) and "desired_setpoint" not in norm(eta_vars["eta_delta"])
    ctx = dict(base_ctx(), desired_setpoint=24.0, indoor_temp=21.0, room_target=22.0)
    ctx["eta_delta"] = parse(env.from_string(str(eta_vars["eta_delta"])).render(**ctx))
    ctx["eta_min"] = parse(env.from_string(str(eta_vars["eta_min"])).render(**ctx))
    assert (ctx["eta_delta"], ctx["eta_min"]) == (1.0, 15)


# ------------------------------------------------- R1-02: retained from v2 (templates unchanged)


@pytest.mark.parametrize("attr,expected", [(1.0, 1.0), (0.5, 0.5), (None, 0.5), (0, 0.5), ("1", 1.0)])
def test_setpoint_step_rows(bp, attr, expected):
    attrs = {"temperature": 7.0, "current_temperature": 23.4}
    if attr is not None:
        attrs["target_temp_step"] = attr
    w = world()
    w.table["climate.rack"] = _State("unknown", attrs=attrs)
    assert render_vars(bp, base_ctx(), w, "setpoint_step")["setpoint_step"] == expected


@pytest.mark.parametrize("idle,step,attrs,expected", [
    (7, 1.0, {}, 7.0),
    (7.5, 1.0, {}, 8.0),          # off-grid idle is written as 8.0 — every idle comparison must use this value
    (7.5, 0.5, {}, 7.5),
    (5, 1.0, {}, 7.0),            # selector allows 5, device minimum is 7 -> clamped
    (5, 1.0, {"min_temp": 5.0}, 5.0),
    (7, 1.0, {"min_temp": None}, 7.0),
    (5, 1.0, {"min_temp": None}, 7.0),   # None falls back to the 7.0 device default, not the idle 5
])
def test_idle_setpoint_dev_rows(bp, idle, step, attrs, expected):
    a = {"temperature": 7.0, "current_temperature": 23.4, "target_temp_step": step, "min_temp": 7.0, "max_temp": 30.0}
    a.update(attrs)
    w = world()
    w.table["climate.rack"] = _State("unknown", attrs=a)
    out = render_vars(bp, base_ctx(idle_setpoint=idle), w, "idle_setpoint_dev")
    assert out["idle_setpoint_dev"] == expected


def test_warmup_edges_use_the_device_idle_value(bp):
    # idle 7.5 on a 1.0 step is written as 8.0: no phantom push at idle, and the dismiss can clear
    on = choose_steps(bp)[4]["choose"][0]["conditions"][0]["value_template"]
    off = choose_steps(bp)[4]["choose"][1]["conditions"][0]["value_template"]
    assert render_tpl(bp, on, world(), enable_notifications=True, desired_setpoint=8.0, current_setpoint=8.0, idle_setpoint_dev=8.0) is False
    assert render_tpl(bp, on, world(), enable_notifications=True, desired_setpoint=24.0, current_setpoint=8.0, idle_setpoint_dev=8.0) is True
    assert render_tpl(bp, off, world(), desired_setpoint=8.0, current_setpoint=24.0, idle_setpoint_dev=8.0) is True
    assert render_tpl(bp, off, world(), desired_setpoint=8.0, current_setpoint=8.0, idle_setpoint_dev=8.0) is False


# ------------------------------------------------- ported 26 scenario rows (drafts/heating-rack-v3.0.0/sim_v3.py)

SCENARIO_ROWS = [
    ("morning before lead (21.0 → lead 15 → open 06:30)", WED, "06:29", {}, ("P6_idle", 7.0)),
    ("morning lead opens, room 21.0 < 21.7", WED, "06:30", {}, ("P5_morning", 24.0)),
    ("heating, room 21.9 < 22.0", WED, "06:40", dict(room="21.9", sp=24.0), ("P5_morning", 24.0)),
    ("heating, room reaches 22.0 → stop", WED, "06:50", dict(room="22.0", sp=24.0), ("P5_morning_satisfied", 7.0)),
    ("idle, room 21.8 ≥ restart line 21.7 → no restart", WED, "07:00", dict(room="21.8"), ("P5_morning_satisfied", 7.0)),
    ("idle, room 21.6 → restart", WED, "07:00", dict(room="21.6"), ("P5_morning", 24.0)),
    ("already warm 22.3 at 06:45 → never heats", WED, "06:45", dict(room="22.3"), ("P5_morning_satisfied", 7.0)),
    ("window end 07:45 while heating", WED, "07:45", dict(room="21.0", sp=24.0), ("P6_idle", 7.0)),
    ("cold 18 °C → ΔT 4 → lead 30 → open 06:15", WED, "06:15", dict(room="18.0"), ("P5_morning", 24.0)),
    ("cold 18 °C 06:14", WED, "06:14", dict(room="18.0"), ("P6_idle", 7.0)),
    ("latched edge: heating, warmer report shrinks lead", WED, "06:32", dict(room="21.6", sp=24.0), ("P5_morning", 24.0)),
    ("Saturday morning also heats", SAT, "06:40", {}, ("P5_morning", 24.0)),
    ("evening 18:29 no preheat", WED, "18:29", dict(room="20.0"), ("P6_idle", 7.0)),
    ("evening 18:30 start", WED, "18:30", dict(room="20.0"), ("P4_evening", 24.0)),
    ("evening 18:29 while rack at drive (boost just ended) → no early open", WED, "18:29", dict(room="20.0", sp=24.0), ("P6_idle", 7.0)),
    ("evening 19:29 still cold", WED, "19:29", dict(room="21.5", sp=24.0), ("P4_evening", 24.0)),
    ("evening 19:30 end → cool", WED, "19:30", dict(room="21.5", sp=24.0), ("P6_idle", 7.0)),
    ("evening room 22.0 at start → skip", WED, "18:30", dict(room="22.0"), ("P4_evening_satisfied", 7.0)),
    ("rack's own sensor never used: rack reads 30, room 20", WED, "18:40", dict(room="20.0", rack_cur=30.0), ("P4_evening", 24.0)),
    ("primary dead → backup Hue 20.3", WED, "18:40", dict(room="unavailable"), ("P4_evening", 24.0)),
    ("both room sensors dead → blind, idle", WED, "18:40", dict(room="unavailable", hue="unknown"), ("P4_evening_blind", 7.0)),
    ("boost outside window, room 21.0", WED, "14:00", dict(boost=("on", 5)), ("P3_boost", 24.0)),
    ("boost, room 22.0 while heating → stop", WED, "14:00", dict(room="22.0", sp=24.0, boost=("on", 20)), ("P3_boost_satisfied", 7.0)),
    ("boost expired", WED, "14:00", dict(boost=("on", 60)), ("P6_idle", 7.0)),
    ("very cold 10 °C → lead cap 60 → open 05:45", WED, "05:45", dict(room="10.0"), ("P5_morning", 24.0)),
    ("vacation", WED, "18:40", dict(vac="on"), ("P1_vacation", "none")),
]


@pytest.mark.parametrize("name,day,hhmm,kw,expected", SCENARIO_ROWS, ids=[r[0] for r in SCENARIO_ROWS])
def test_scenario_rows(bp, name, day, hhmm, kw, expected):
    when = at(hhmm, day)
    out = render_vars(bp, base_ctx(), world(**kw), "active_priority", when)
    got = (out["active_priority"], out["desired_setpoint"])
    assert got == expected


# ---------------------------------------------------------------- instance + deploy dry-run

def test_instance_json_v3():
    inst = json.loads(INSTANCE_PATH.read_text())
    assert inst["id"] == "1776551429917"
    assert inst["alias"] == "Bathroom Heating Rack v3.0.0"
    assert inst["use_blueprint"]["path"] == HA_BP_PATH
    i = inst["use_blueprint"]["input"]
    assert i["heating_climate"] == "climate.heatingrack_bathroom"
    assert i["bathroom_temp_sensor"] == "sensor.temp_sensor_bathroom"
    assert i["backup_temp_sensors"] == ["sensor.bathroom_temperature"]
    assert i["vacation_off"] == ["input_boolean.heating_rack_vacation"]
    assert i["boost_toggle"] == "input_boolean.heating_rack_boost"
    assert (i["boost_target_temp"], i["boost_runtime_min"]) == (22, 55)
    assert (i["drive_setpoint"], i["restart_deadband"]) == (24, 0.3)
    assert (i["morning_a_days"], i["morning_a_target_warm"], i["morning_a_hold_until"], i["morning_a_target_temp"]) == (
        ALLWEEK, "06:45:00", "07:45:00", 22)
    assert (i["evening_a_days"], i["evening_a_target_warm"], i["evening_a_hold_until"], i["evening_a_target_temp"]) == (
        ALLWEEK, "18:30:00", "19:30:00", 22)
    assert i["evening_preheat"] is False
    assert i["warmup_min_minutes"] == 10
    assert i["notify_targets"] == ["notify.mobile_app_martin_fold"]
    for k in ("fan_switch", "comfort_floor_delta", "hall_motion", "stairs_motion", "enable_predictive_motion"):
        assert k not in i
    assert set(i) <= EXPECTED_INPUTS


def test_instance_json_dry_run_validates():
    r = subprocess.run(["bash", str(DEPLOY_SCRIPT), "--dry-run", str(BP_PATH), HA_BP_PATH, str(INSTANCE_PATH)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ok (id 1776551429917" in r.stdout
    assert "dry-run: validation passed" in r.stdout


# ------------------------------------------------- board 20260924-083742 delta-1 (post-board rows)


def test_latch_ok_without_a_boost_entity(bp):
    # R1-D1-01: a missing boost entity counts as never-on, so a slot-started heat still latches.
    w = world(sp=24.0, room="21.6")
    del w.table["input_boolean.boost"]
    out = render_vars(bp, base_ctx(), w, "active_priority", at("06:32", WED))
    assert (out["boost_age_min"], out["latch_ok"]) == (100000, True)
    assert (out["active_priority"], out["desired_setpoint"]) == ("P5_morning", 24.0)


def test_latch_residual_after_ha_restart(bp):
    # R1-D1-02 (documented residual): HA restart gives the boost helper a fresh last_changed; a
    # slot-started pre-warm before its ΔT-lead edge (room 21.5 -> lead 12 -> opens 06:33) pauses.
    w = world(sp=24.0, room="21.5", boost=("off", 2))
    out = render_vars(bp, base_ctx(), w, "active_priority", at("06:10", WED))
    assert out["latch_ok"] is False
    assert (out["active_priority"], out["desired_setpoint"]) == ("P6_idle", 7.0)
    # ... and resumes at the ΔT-lead edge
    out = render_vars(bp, base_ctx(), world(sp=24.0, room="21.5", boost=("off", 25)), "active_priority", at("06:33", WED))
    assert (out["active_priority"], out["desired_setpoint"]) == ("P5_morning", 24.0)


def test_latch_off_while_boost_on_but_expired(bp):
    # R1-D1-03a: boost still ON but past its runtime at 05:50, rack at 24 -> no latch, no boost -> idle
    w = world(sp=24.0, boost=("on", 60))
    out = render_vars(bp, base_ctx(), w, "active_priority", at("05:50", WED))
    assert (out["boost_active"], out["boost_expired"], out["latch_ok"]) == (False, True, False)
    assert (out["active_priority"], out["desired_setpoint"]) == ("P6_idle", 7.0)


def test_latch_residual_manual_24_is_honoured(bp):
    # R1-D1-03b (documented residual): a manual 24 at 05:50, boost long off, reads as a slot-started heat
    w = world(sp=24.0, boost=("off", 600))
    out = render_vars(bp, base_ctx(), w, "active_priority", at("05:50", WED))
    assert out["latch_ok"] is True
    assert (out["active_priority"], out["desired_setpoint"]) == ("P5_morning", 24.0)


def test_latch_residual_sibling_hand_off(bp):
    # R1-D1-03c (documented residual): with Morning B configured, heat still running when A ends
    # (07:45) latches B's edge to 08:30 - 60 = 07:30 instead of its ΔT-lead edge 08:15.
    ctx = base_ctx(morning_b_days=ALLWEEK)
    out = render_vars(bp, ctx, world(sp=24.0), "active_priority", at("07:45", WED))
    assert (out["ma_in_window"], out["mb_in_window"]) == (False, True)
    assert (out["active_priority"], out["desired_setpoint"]) == ("P5_morning", 24.0)
    out = render_vars(bp, ctx, world(sp=7.0), "active_priority", at("07:45", WED))
    assert (out["mb_in_window"], out["active_priority"]) == (False, "P6_idle")
