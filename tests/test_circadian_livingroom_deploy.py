"""Live audit of the Livingroom FP300 dual-presence work: the live v2.2.0 instance snapshot and the audit note.

Read-only: the deploy script is only ever run with --dry-run (see test_every_run_call_passes_dry_run).
"""
import ast
import json
import re
from pathlib import Path

import pytest
from test_deploy_blueprint_script import run

ROOT = Path(__file__).resolve().parent.parent
BP = ROOT / "circadian_livingroom.yaml"
HA_PATH = "leviemartin/circadian_livingroom.yaml"
INSTANCE_ID = "1767031159524"
SNAPSHOT = ROOT / "deploy" / f"circadian_livingroom_{INSTANCE_ID}.live-v2.2.0.json"
NOTE = ROOT / "docs" / "superpowers" / "research" / "2026-10-16-livingroom-fp300-live-audit.md"
STALE_KEYS = ["govee_brightness_scale", "govee_lights", "hue_lights", "light_entity"]
FP2_PRESENCE = "binary_sensor.presence_sensor_fp2_e863_presence_sensor_1"
FP2_LUX = "sensor.presence_sensor_fp2_e863_light_sensor_light_level"
FP300_PRESENCE = "binary_sensor.living_room_main_fp300_couch_occupancy_sensor"
FP300_BATTERY = "sensor.living_room_main_fp300_couch_battery_sensor"
ENTITY_IDS = [FP2_PRESENCE, FP2_LUX, FP300_PRESENCE, FP300_BATTERY]
CREDENTIAL_PATTERNS = [
    r"eyJ[A-Za-z0-9_-]{8,}", r"(?i)bearer\s", r"(?i)https?://", r"\b\d{1,3}(\.\d{1,3}){3}\b",
    r"HASS_(TOKEN|SERVER)\s*=", r"(?i)\b(password|api[_-]?key)\b",
]
# the live config exactly as read; key order is part of the pin
LIVE_INPUT = {
    "light_entity": ["light.hue_ambiance_spot_1", "light.hue_ambiance_spot_2", "light.hall_1", "light.hall_3", "light.living_1", "light.living_3", "light.living_4", "light.studio_3", "light.hue_play_gradient_lightstrip_1", "light.ceiling_table", "light.ceiling_tv"],
    "presence_entity": FP2_PRESENCE,
    "illuminance_entity": FP2_LUX,
    "min_kelvin": 2000,
    "time_dinner": "17:45:00",
    "time_toddler": "18:45:00",
    "time_night": "23:30:00",
    "dinner_bri": 90,
    "dinner_kelvin": 2300,
    "toddler_bri": 85,
    "evening_kelvin": 2000,
    "evening_bri": 70,
    "lux_off_threshold": 611,
    "lux_on_threshold": 394,
    "toddler_kelvin": 2100,
    "govee_lights": ["light.ceiling_table", "light.ceiling_tv"],
    "hue_lights": ["light.studio_3", "light.living_3", "light.living_4"],
    "night_kelvin": 2000,
    "govee_brightness_scale": 0.2,
    "hue_bulbs": ["light.living_3", "light.living_4", "light.studio_3"],
    "hue_ceiling": ["light.hue_infuse_ceiling_1", "light.hue_infuse_ceiling_2"],
    "max_kelvin": 4000,
    "night_bri": 29,
}


def dry(*args):
    return run("--dry-run", *args)


def snapshot_with(tmp_path, mutate):
    cfg = json.loads(SNAPSHOT.read_text())
    mutate(cfg)
    p = tmp_path / "inst.json"
    p.write_text(json.dumps(cfg))
    return str(p)


def test_snapshot_is_the_live_config_unchanged():
    data = json.loads(SNAPSHOT.read_text())
    assert set(data) == {"id", "alias", "description", "use_blueprint"}
    assert data["id"] == INSTANCE_ID
    assert data["alias"] == "Circadian Living Room Lights v2.1.1"
    assert data["description"] == ""
    assert data["use_blueprint"] == {"path": HA_PATH, "input": LIVE_INPUT}
    assert list(data["use_blueprint"]["input"]) == list(LIVE_INPUT)


def test_snapshot_keeps_v2_inputs_and_live_lux():
    inp = json.loads(SNAPSHOT.read_text())["use_blueprint"]["input"]
    assert inp["presence_entity"] == FP2_PRESENCE
    assert inp["illuminance_entity"] == FP2_LUX
    assert not {"presence_fp2", "presence_fp300", "notify_targets"} & set(inp)
    assert (inp["lux_on_threshold"], inp["lux_off_threshold"]) == (394, 611)


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="v3.0.0 drops presence_entity; card 2026-10-16-circadian-v3-instance-migration migrates the live instance and removes this test")
def test_live_dry_run_pins_four_stale_keys():
    """Holds for the v2.2.0 blueprint only: the v3.0.0 card marks it xfail, the migration card (2026-10-16-circadian-v3-instance-migration) removes it."""
    r = dry(str(BP), HA_PATH, str(SNAPSHOT))
    assert r.returncode == 1, r.stdout + r.stderr
    assert "blueprint: Circadian Living Room Lights v2.2.0" in r.stdout
    problems = [l for l in r.stdout.splitlines() if l.startswith("  - ")]
    assert problems == ["  - unknown input keys (would make the instance unavailable): " + ", ".join(STALE_KEYS)]


@pytest.mark.parametrize("bad_id", [None, "", "../" + INSTANCE_ID, "1767 031159524"])
def test_dry_run_rejects_bad_instance_id(tmp_path, bad_id):
    def mutate(cfg):
        if bad_id is None:
            del cfg["id"]
        else:
            cfg["id"] = bad_id

    r = dry(str(BP), HA_PATH, snapshot_with(tmp_path, mutate))
    assert r.returncode == 1
    assert "instance id must match" in r.stdout


def test_dry_run_reports_missing_required_input(tmp_path):
    p = snapshot_with(tmp_path, lambda cfg: cfg["use_blueprint"]["input"].pop("presence_entity"))
    r = dry(str(BP), HA_PATH, p)
    assert r.returncode == 1
    assert "required inputs missing: " in r.stdout


def test_dry_run_rejects_ha_path_without_owner():
    assert re.fullmatch(r"[^/]+/[^/]+\.yaml", HA_PATH)
    r = dry(str(BP), "circadian_livingroom.yaml", str(SNAPSHOT))
    assert r.returncode == 1
    assert "ha-blueprint-path must look like" in r.stderr


def test_one_export_per_instance_id():
    files = sorted((ROOT / "deploy").glob("circadian_livingroom_*.json"))
    assert files
    ids = set()
    for f in files:
        m = re.fullmatch(r"circadian_livingroom_(\d+)(\.live-v[\d.]+)?\.json", f.name)
        assert m, f.name
        assert json.loads(f.read_text())["id"] == m.group(1), f.name
        ids.add(m.group(1))
    assert ids == {INSTANCE_ID}


def test_no_credentials_in_snapshot_or_note():
    for path in (SNAPSHOT, NOTE):
        text = path.read_text()
        for pat in CREDENTIAL_PATTERNS:
            assert not re.search(pat, text), (path.name, pat)


def test_audit_note_entity_table():
    note = NOTE.read_text()
    assert note.strip()
    for needle in (*ENTITY_IDS, INSTANCE_ID, HA_PATH, "notify.mobile_app_martin_fold"):
        assert needle in note, needle
    rows = [l for l in note.splitlines() if l.lstrip().startswith("|")]
    for eid in ENTITY_IDS:
        assert any(eid in l and "yes" in l for l in rows), eid


def test_audit_note_records_dry_run_and_lux():
    note = NOTE.read_text()
    for needle in (*STALE_KEYS, "394", "611"):
        assert needle in note, needle


def test_audit_note_overlap_matrix():
    note = NOTE.read_text()
    for needle in ("1767830683624", "1773749905520", "lg_sleep_movie", "not readable via API",
                   "YAML grep", "presence_sensor_2", "157", "115", "42"):
        assert needle in note, needle
    assert re.search(r"^Conclusion: no conflict found\.$", note, re.M)
    assert note.rstrip("\n").splitlines()[-1] == "Conclusion: no conflict found."


def test_every_run_call_passes_dry_run():
    """The host can read the HA env file, so a call of run() without --dry-run could POST to live HA."""
    tree = ast.parse(Path(__file__).read_text())
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "run"]
    assert calls
    assert all(c.args and isinstance(c.args[0], ast.Constant) and c.args[0].value == "--dry-run" for c in calls)
