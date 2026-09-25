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


# --- Bedroom Fan Direction v1.0.0 (Session #45, advisory only under amendment A1) ---------

DIRECTION_PATH = DEPLOY / "bedroom_fan_direction_kids.json"
RETIRED_PATH = DEPLOY / "samuel_fan_seasonal_direction.retired.json"
RESTORE_PATH = DEPLOY / "samuel_fan_seasonal_direction.restore-disabled.json"
LIVE_SEASON_TOGGLE = "input_boolean.samuel_fan_winter_mode"


def test_direction_instance_uses_the_cutoff_fan_and_the_season_toggle():
    """Example 16."""
    d = _inp(json.loads(DIRECTION_PATH.read_text()))
    assert d["fan"] == LIVE_CUTOFF["fan"]
    assert d["season_toggle"] == LIVE_SEASON_TOGGLE
    assert d["notify_services"] and all(re.fullmatch(r"notify[.][a-z0-9_]+", n) for n in d["notify_services"])


def test_retired_seasonal_automation_files():
    """Example 16 / R2-03: the retired S carries the same fan and toggle; the restore file is the
    same object plus exactly initial_state: false, so a rollback loads it disabled."""
    retired = json.loads(RETIRED_PATH.read_text())
    restore = json.loads(RESTORE_PATH.read_text())
    assert retired["id"] == "samuel_fan_seasonal_direction"
    assert "initial_state" not in retired
    assert _inp(retired)["fan"] == LIVE_CUTOFF["fan"]
    assert _inp(retired)["season_toggle"] == LIVE_SEASON_TOGGLE
    assert restore["initial_state"] is False
    assert {k: v for k, v in restore.items() if k != "initial_state"} == retired
    assert set(restore) - set(retired) == {"initial_state"}


def test_direction_ids_distinct_from_the_other_instances():
    ids = [KIDS["id"], MASTER["id"], NIGHT["id"], json.loads(DIRECTION_PATH.read_text())["id"]]
    assert len(set(ids)) == 4 and all(re.fullmatch(r"[A-Za-z0-9_-]+", i) for i in ids)


def test_no_energizing_services_in_the_direction_blueprint():
    banned = re.compile(r"fan\.turn_on|fan\.set_direction|fan\.set_percentage|fan\.toggle|homeassistant\.turn_on|homeassistant\.toggle")
    body = (ROOT / "bedroom_fan_direction.yaml").read_text()
    assert not banned.search(body)
    assert not re.search(r"fan\.[a-z_]+", body), "A1: no fan service of any kind"
    assert "wait_template" not in body and not re.search(r"^\s*-?\s*delay:", body, re.M)
