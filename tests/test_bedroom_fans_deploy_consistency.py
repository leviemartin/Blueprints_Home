"""Cross-file consistency for the bedroom-fans deploy set (Session #42, daytime v1.1.0).

v1.1.0 drops the nap lifecycle: the daytime instances take the fan only, and the
nightlight instance no longer references the nap toggle, so the helpers
input_boolean.kids_nap and input_datetime.kids_nap_since can be deleted. The kids
instance must point at the live cutoff's fan. Live values are pinned as literals below:
they were read from the Home Assistant configs captured on 2026-09-24 (the cutoff, dimmer
and seasonal automations live in the ceiling-fan-hue-blueprint repo, not here).
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "deploy"

KIDS_PATH = DEPLOY / "bedroom_fan_daytime_kids.json"
MASTER_PATH = DEPLOY / "bedroom_fan_daytime_master.json"
NIGHT_PATH = DEPLOY / "nightlight_1766142134972.json"
KIDS = json.loads(KIDS_PATH.read_text())
MASTER = json.loads(MASTER_PATH.read_text())
NIGHT = json.loads(NIGHT_PATH.read_text())

# Live automation inputs, 2026-09-24.
LIVE_CUTOFF = {"fan": "fan.ceiling_fan_light_v2", "motion_sensor": "binary_sensor.samuel_samuel_matthew_fanprotection"}
LIVE_DIMMER_GATE = "light.kids_room_gate"
NAP_HELPERS = ("input_boolean.kids_nap", "input_datetime.kids_nap_since")


def _inp(inst):
    return inst["use_blueprint"]["input"]


def test_nightlight_instance_has_no_nap_toggle():
    """Example 12: without nap_toggle the nightlight v1.3.0 paints the fixed nap window."""
    n = _inp(NIGHT)
    assert "nap_toggle" not in n
    assert n["nap_start"] == "12:30:00" and n["nap_end"] == "15:30:00"
    assert n["gate_entity"] == LIVE_DIMMER_GATE


def test_daytime_instances_take_the_fan_only():
    assert _inp(KIDS) == {"fan": LIVE_CUTOFF["fan"]}
    assert _inp(MASTER) == {"fan": "fan.ceiling_fan_light_v2_2"}


def test_no_instance_references_the_nap_helpers():
    for path in (KIDS_PATH, MASTER_PATH, NIGHT_PATH):
        body = path.read_text()
        for helper in NAP_HELPERS:
            assert helper not in body, (path.name, helper)


def test_instance_ids_distinct_and_safe():
    ids = [KIDS["id"], MASTER["id"], NIGHT["id"]]
    assert len(set(ids)) == 3
    assert all(re.fullmatch(r"[A-Za-z0-9_-]+", i) for i in ids)


def test_no_energizing_services_in_the_daytime_or_nightlight_blueprints():
    banned = re.compile(r"fan\.turn_on|fan\.set_direction|fan\.set_percentage|fan\.toggle|homeassistant\.turn_on|homeassistant\.toggle")
    for name in ("bedroom_fan_daytime.yaml", "nightlight.yaml"):
        assert not banned.search((ROOT / name).read_text()), name
    assert "fan." not in (ROOT / "nightlight.yaml").read_text()
    daytime = (ROOT / "bedroom_fan_daytime.yaml").read_text()
    assert "wait_template" not in daytime and not re.search(r"^\s*-?\s*delay:", daytime, re.M)
