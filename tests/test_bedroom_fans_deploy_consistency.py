"""Cross-file consistency for the bedroom-fans v1 deploy set (Session #40).

The daytime blueprint and the nightlight share the nap toggle and gate; the kids
instance must point at the live cutoff's fan and sensor and the live dimmer's
buttons. Those live values are pinned as literals below: they were read from the
Home Assistant configs captured on 2026-09-24 (the cutoff, dimmer and seasonal
automations live in the ceiling-fan-hue-blueprint repo, not here).
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "deploy"

KIDS = json.loads((DEPLOY / "bedroom_fan_daytime_kids.json").read_text())
MASTER = json.loads((DEPLOY / "bedroom_fan_daytime_master.json").read_text())
NIGHT = json.loads((DEPLOY / "nightlight_1766142134972.json").read_text())

# Live automation inputs, 2026-09-24.
LIVE_CUTOFF = {"fan": "fan.ceiling_fan_light_v2", "motion_sensor": "binary_sensor.samuel_samuel_matthew_fanprotection"}
LIVE_DIMMER = {"button_off": "event.baby_room_button_4", "button_up": "event.baby_room_button_2",
               "button_down": "event.baby_room_button_3", "gate_group": "light.kids_room_gate"}
LIVE_SEASONAL = {"fan": "fan.ceiling_fan_light_v2", "season_toggle": "input_boolean.samuel_fan_winter_mode"}


def _inp(inst):
    return inst["use_blueprint"]["input"]


def test_nap_toggle_and_gate_shared_by_daytime_and_nightlight():
    assert _inp(KIDS)["nap_toggle"] == _inp(NIGHT)["nap_toggle"] == "input_boolean.kids_nap"
    assert _inp(KIDS)["nap_since_helper"] == "input_datetime.kids_nap_since"
    assert _inp(KIDS)["gate_entity"] == _inp(NIGHT)["gate_entity"] == LIVE_DIMMER["gate_group"]


def test_kids_instance_matches_the_live_cutoff_and_dimmer():
    k = _inp(KIDS)
    assert k["fan"] == LIVE_CUTOFF["fan"]
    assert LIVE_CUTOFF["motion_sensor"] in k["activity_sensors"]
    assert "binary_sensor.stairs_motion" in k["activity_sensors"]
    assert k["nap_start_button"] == LIVE_DIMMER["button_off"]
    assert sorted(k["nap_end_buttons"]) == sorted([LIVE_DIMMER["button_up"], LIVE_DIMMER["button_down"]])


def test_master_instance_has_no_nap_inputs():
    m = _inp(MASTER)
    assert m["fan"] == "fan.ceiling_fan_light_v2_2"
    assert m["activity_sensors"] == ["binary_sensor.stairs_motion"]
    for key in ("nap_toggle", "nap_since_helper", "nap_start_button", "nap_end_buttons", "gate_entity"):
        assert key not in m


def test_nap_helpers_are_not_used_by_other_automations():
    other = set(LIVE_CUTOFF.values()) | set(LIVE_DIMMER.values()) | set(LIVE_SEASONAL.values())
    for key in ("nap_toggle", "nap_since_helper"):
        assert _inp(KIDS)[key] not in other


def test_instance_ids_distinct_and_safe():
    ids = [KIDS["id"], MASTER["id"], NIGHT["id"]]
    assert len(set(ids)) == 3
    assert all(re.fullmatch(r"[A-Za-z0-9_-]+", i) for i in ids)


def test_day_window_uses_defaults():
    for inst in (KIDS, MASTER):
        assert "day_start" not in _inp(inst) and "day_end" not in _inp(inst)


def test_no_energizing_services_in_the_new_or_changed_blueprints():
    banned = re.compile(r"fan\.turn_on|fan\.set_direction|fan\.set_percentage|fan\.toggle|homeassistant\.turn_on|homeassistant\.toggle")
    for name in ("bedroom_fan_daytime.yaml", "nightlight.yaml"):
        assert not banned.search((ROOT / name).read_text()), name
    assert "fan." not in (ROOT / "nightlight.yaml").read_text()
    daytime = (ROOT / "bedroom_fan_daytime.yaml").read_text()
    assert "wait_template" not in daytime and not re.search(r"^\s*-?\s*delay:", daytime, re.M)
