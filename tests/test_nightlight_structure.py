"""Structural + logic tests for nightlight.yaml (Toddler Sleep Trainer v1.3).

Run: cd ~/AI/projects/Blueprints_Home && \
     ~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q
"""
import json
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment

from test_deploy_blueprint_script import run

BP_PATH = Path(__file__).resolve().parent.parent / "nightlight.yaml"
INSTANCE_PATH = (
    Path(__file__).resolve().parent.parent / "deploy" / "nightlight_1766142134972.json"
)


class _Input:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"!input {self.name}"


class HassLoader(yaml.SafeLoader):
    pass


HassLoader.add_constructor(
    "!input", lambda loader, node: _Input(loader.construct_scalar(node))
)


@pytest.fixture(scope="module")
def bp():
    with BP_PATH.open() as fh:
        return yaml.load(fh, Loader=HassLoader)


@pytest.fixture(scope="module")
def inputs(bp):
    return bp["blueprint"]["input"]


def test_version_bumped(bp):
    assert "v1.3" in bp["blueprint"]["name"]


def test_v113_inputs_unchanged(inputs):
    for name in (
        "light_entity", "motion_entity",
        "wakeup_time_mon", "wakeup_time_tue", "wakeup_time_wed",
        "wakeup_time_thu", "wakeup_time_fri", "wakeup_time_sat",
        "wakeup_time_sun",
        "night_color", "wakeup_color",
        "night_brightness", "boost_brightness", "wakeup_brightness",
        "transition_time", "motion_clear_delay",
    ):
        assert name in inputs, f"v1.1.3 input {name} must survive"


def test_new_inputs_optional(inputs):
    assert inputs["gate_entity"]["default"] == []
    assert inputs["nap_start"]["default"] == "00:00:00"
    assert inputs["nap_end"]["default"] == "00:00:00"


def test_nap_toggle_input_optional_default_empty(inputs):
    assert "nap_toggle" in inputs
    assert inputs["nap_toggle"]["default"] == []


def _trigger_ids(bp):
    return [t.get("id") for t in bp["trigger"]]


def test_gate_off_trigger(bp):
    gate_triggers = [t for t in bp["trigger"] if t.get("id") == "gate_off"]
    assert len(gate_triggers) == 1
    t = gate_triggers[0]
    assert t["platform"] == "state"
    assert t["to"] == "off"
    assert repr(t["entity_id"]) == "!input gate_entity"


def test_nap_edge_triggers(bp):
    ids = _trigger_ids(bp)
    assert "nap_start" in ids
    assert "nap_end" in ids


def test_v113_triggers_survive(bp):
    ids = _trigger_ids(bp)
    for tid in ("night_start", "motion_detected", "motion_cleared",
                "wakeup_schedule", "light_off_watchdog", "init"):
        assert tid in ids, f"v1.1.3 trigger {tid} must survive"


def test_nap_toggle_state_triggers_with_restored_guard(bp):
    on_triggers = [t for t in bp["trigger"] if t.get("id") == "nap_toggle_on"]
    off_triggers = [t for t in bp["trigger"] if t.get("id") == "nap_toggle_off"]
    assert len(on_triggers) == 1
    assert len(off_triggers) == 1
    t_on, t_off = on_triggers[0], off_triggers[0]
    assert t_on["platform"] == "state"
    assert t_on["to"] == "on"
    assert repr(t_on["entity_id"]) == "!input nap_toggle"
    assert t_off["platform"] == "state"
    assert t_off["to"] == "off"
    assert repr(t_off["entity_id"]) == "!input nap_toggle"

    conds = bp.get("condition") or []
    assert len(conds) == 2, "v1.3 must add a second global condition, keeping the first"
    assert conds[0]["value_template"].strip() == "{{ not is_gate_on }}", (
        "the v1.2.0 gate condition must stay exactly as-is"
    )
    assert conds[1]["value_template"].strip() == (
        "{{ trigger.id is not defined or trigger.id not in "
        "['nap_toggle_on', 'nap_toggle_off'] or (trigger.from_state is not none "
        "and not (trigger.from_state.attributes.restored | default(false))) }}"
    )


def test_global_gate_condition(bp):
    conds = bp.get("condition") or []
    assert conds, "v1.2 must have a global condition block"
    assert conds[0]["value_template"].strip() == "{{ not is_gate_on }}", (
        "gate condition must PAUSE while gated, not run only while gated"
    )


def test_is_gate_on_renders():
    with BP_PATH.open() as fh:
        bp = yaml.load(fh, Loader=HassLoader)
    tmpl = bp["variables"]["is_gate_on"]
    env = Environment()
    env.globals["is_state"] = lambda e, s: e == "light.kids_room_lights" and s == "on"

    def render(gate):
        return env.from_string(tmpl).render(gate=gate).strip()

    assert render([]) == "False"                          # empty default: never gated
    assert render("light.kids_room_lights") == "True"     # gate on
    env.globals["is_state"] = lambda e, s: False
    assert render("light.kids_room_lights") == "False"    # gate off


def _is_nap_window_template(bp):
    # is_nap_window lives in the action's variables step
    var_steps = [a for a in bp["action"] if "variables" in a]
    assert var_steps, "action must start with a variables step"
    return var_steps[0]["variables"]["is_nap_window"]


def test_rendered_is_nap_window_fixed_window_when_unconfigured(bp):
    # With nap_toggle=[] (unconfigured), is_nap_window must reduce to the
    # exact v1.2.0 fixed-window template (the original test_nap_window_predicate
    # rows), and must never call is_state.
    tmpl = _is_nap_window_template(bp)

    import datetime as dt

    def today_at(s):
        h, m, sec = (int(x) for x in s.split(":"))
        return dt.datetime(2026, 7, 26, h, m, sec)

    def _forbidden_is_state(e, s):
        raise AssertionError("is_state must not be called when nap_toggle is unconfigured")

    env = Environment()
    env.globals["today_at"] = today_at
    env.globals["is_state"] = _forbidden_is_state

    def render(now_hm, start, end):
        env.globals["now"] = lambda: today_at(now_hm)
        return env.from_string(tmpl).render(
            nap_start_t=start, nap_end_t=end, nap_toggle=[]
        ).strip()

    assert render("13:00:00", "12:30:00", "15:30:00") == "True"
    assert render("12:29:59", "12:30:00", "15:30:00") == "False"
    assert render("15:30:00", "12:30:00", "15:30:00") == "False"
    assert render("13:00:00", "00:00:00", "00:00:00") == "False"  # disabled


def test_rendered_is_nap_window_follows_the_toggle_when_configured(bp):
    tmpl = _is_nap_window_template(bp)

    import datetime as dt

    def today_at(s):
        h, m, sec = (int(x) for x in s.split(":"))
        return dt.datetime(2026, 7, 26, h, m, sec)

    env = Environment()
    env.globals["today_at"] = today_at

    def render(now_hm, toggle_state):
        env.globals["now"] = lambda: today_at(now_hm)
        env.globals["is_state"] = lambda e, s: (
            e == "input_boolean.kids_nap" and s == "on" and toggle_state == "on"
        )
        return env.from_string(tmpl).render(
            nap_start_t="12:30:00", nap_end_t="15:30:00",
            nap_toggle="input_boolean.kids_nap",
        ).strip()

    # 11:45 is outside the fixed 12:30-15:30 window, but a configured toggle overrides it
    assert render("11:45:00", "on") == "True"
    # 13:00 is inside the fixed window, but the toggle being off overrides it
    assert render("13:00:00", "off") == "False"


def test_choose_branch_order(bp):
    branches = [a for a in bp["action"] if "choose" in a][0]["choose"]
    assert len(branches) == 3
    templates = [
        b["conditions"][0]["value_template"].strip() for b in branches
    ]
    # Pinned exactly (not just substring) so an inverted "not is_nap_window"
    # or similar can't slip through while still containing the right name.
    assert templates[0] == "{{ is_wakeup_window }}"
    assert templates[1] == "{{ is_night_window }}"
    assert templates[2] == "{{ is_nap_window }}"


def test_nap_branch_uses_night_color_and_boost(bp):
    branches = [a for a in bp["action"] if "choose" in a][0]["choose"]
    nap = branches[2]
    seq = str(nap["sequence"])
    assert "night_color" in seq
    assert "bri_boost if is_motion_active else bri_night" in seq


def test_no_fan_service():
    text = BP_PATH.read_text()
    assert "fan." not in text, "nightlight.yaml must never touch a fan"


def test_instance_passes_dry_run_and_values():
    r = run(
        "--dry-run", str(BP_PATH), "leviemartin/nightlight.yaml", str(INSTANCE_PATH),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip().splitlines()[-1] == "dry-run: validation passed, nothing deployed"

    data = json.loads(INSTANCE_PATH.read_text())
    assert data["alias"].endswith("v1.3 (Samuel)")
    inp = data["use_blueprint"]["input"]
    assert inp["nap_toggle"] == "input_boolean.kids_nap"
    assert inp["gate_entity"] == "light.kids_room_gate"
    assert inp["light_entity"] == "light.samuel_nightlight"
    assert inp["nap_start"] == "12:30:00"
    assert inp["nap_end"] == "15:30:00"
