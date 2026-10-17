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


INSTANCE = ROOT / "deploy" / f"circadian_livingroom_{INSTANCE_ID}.json"
V3_ALIAS = "Circadian Living Room Lights v3.0.0"
NOTIFY_TARGET = "notify.mobile_app_martin_fold"
DROPPED_KEYS = ["presence_entity", *STALE_KEYS]
KEPT_KEYS = [
    "illuminance_entity", "min_kelvin", "time_dinner", "time_toddler", "time_night",
    "dinner_bri", "dinner_kelvin", "toddler_bri", "evening_kelvin", "evening_bri",
    "lux_off_threshold", "lux_on_threshold", "toddler_kelvin", "night_kelvin",
    "hue_bulbs", "hue_ceiling", "max_kelvin", "night_bri",
]
MIGRATED_KEYS = ["presence_fp2", "presence_fp300", *KEPT_KEYS, "notify_targets"]
LATE_NIGHT_KEYS = ["late_night_start", "late_night_end", "late_night_timeout"]
V2_2_0_KEYS = [
    "hue_bulbs", "hue_ceiling", "ceiling_brightness_scale", "presence_entity",
    "presence_timeout", "illuminance_entity", "override_entity", "lux_on_threshold",
    "lux_off_threshold", "lux_off_duration", "time_dinner", "dinner_kelvin",
    "dinner_bri", "time_toddler", "toddler_kelvin", "toddler_bri", "time_evening",
    "evening_kelvin", "evening_bri", "evening_effect", "time_night", "night_kelvin",
    "night_bri", "night_effect", "max_kelvin", "min_kelvin",
]
UNKNOWN = "  - unknown input keys (would make the instance unavailable): "
MISSING = "  - required inputs missing: "
ID_LINE = "  - instance id must match ^[A-Za-z0-9_-]+$ (it is used in URLs and backup paths)"


def problems(r):
    return [line for line in r.stdout.splitlines() if line.startswith("  - ")]


def migrated_with(tmp_path, mutate):
    cfg = json.loads(INSTANCE.read_text())
    mutate(cfg)
    p = tmp_path / "inst.json"
    p.write_text(json.dumps(cfg))
    return str(p)


def test_migrated_instance_dry_run_passes():
    r = dry(str(BP), HA_PATH, str(INSTANCE))
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.splitlines() == [
        "blueprint: Circadian Living Room Lights v3.0.0",
        f"instance {INSTANCE}: ok (id {INSTANCE_ID}, 21 inputs)",
        "dry-run: validation passed, nothing deployed",
    ]
    assert r.stderr == ""


def test_migrated_instance_shape():
    data = json.loads(INSTANCE.read_text())
    assert set(data) == {"id", "alias", "description", "use_blueprint"}
    assert data["id"] == INSTANCE_ID
    assert data["alias"] == V3_ALIAS
    assert data["description"] == ""
    bp = data["use_blueprint"]
    assert set(bp) == {"path", "input"}
    assert bp["path"] == HA_PATH
    assert re.fullmatch(r"[^/]+/[^/]+\.yaml", bp["path"])
    assert list(bp["input"]) == MIGRATED_KEYS


def test_migration_drops_presence_entity_and_stale_keys():
    inp = json.loads(INSTANCE.read_text())["use_blueprint"]["input"]
    assert not set(DROPPED_KEYS) & set(inp)
    assert "presence_entity" not in INSTANCE.read_text()
    assert [k for k in LIVE_INPUT if k not in DROPPED_KEYS] == KEPT_KEYS


def test_presence_inputs_are_the_audited_entities():
    inp = json.loads(INSTANCE.read_text())["use_blueprint"]["input"]
    assert inp["presence_fp2"] == FP2_PRESENCE == LIVE_INPUT["presence_entity"]
    assert inp["presence_fp300"] == FP300_PRESENCE
    rows = [line for line in NOTE.read_text().splitlines() if line.lstrip().startswith("|")]
    for eid in (FP2_PRESENCE, FP300_PRESENCE):
        assert any(eid in line and "yes" in line for line in rows), eid


def test_notify_targets_is_the_audited_fold_service():
    inp = json.loads(INSTANCE.read_text())["use_blueprint"]["input"]
    assert inp["notify_targets"] == [NOTIFY_TARGET]
    assert re.fullmatch(r"notify[.][a-z0-9_]+", NOTIFY_TARGET)
    assert "`notify.mobile_app_martin_fold` exists" in NOTE.read_text()


def test_non_presence_inputs_keep_audit_literals():
    inp = json.loads(INSTANCE.read_text())["use_blueprint"]["input"]
    for key in KEPT_KEYS:
        assert inp[key] == LIVE_INPUT[key], key
        assert type(inp[key]) is type(LIVE_INPUT[key]), key
    assert (inp["lux_on_threshold"], inp["lux_off_threshold"]) == (394, 611)


def test_late_night_inputs_left_unset():
    inp = json.loads(INSTANCE.read_text())["use_blueprint"]["input"]
    assert not set(LATE_NIGHT_KEYS) & set(inp)


def test_unmigrated_snapshot_fails_v3_dry_run():
    r = dry(str(BP), HA_PATH, str(SNAPSHOT))
    assert r.returncode == 1, r.stdout + r.stderr
    assert "blueprint: Circadian Living Room Lights v3.0.0" in r.stdout
    assert problems(r) == [
        UNKNOWN + "govee_brightness_scale, govee_lights, hue_lights, light_entity, presence_entity",
        MISSING + "presence_fp2, presence_fp300",
    ]


@pytest.mark.parametrize("kind", ["absent", "empty"])
def test_dry_run_rejects_absent_or_empty_export(tmp_path, kind):
    p = tmp_path / f"circadian_livingroom_{INSTANCE_ID}.json"
    if kind == "empty":
        p.write_text("")
    r = dry(str(BP), HA_PATH, str(p))
    assert r.returncode == 1
    assert "validation passed" not in r.stdout
    assert "ok (id" not in r.stdout
    if kind == "absent":
        assert "instance file not found" in r.stderr


@pytest.mark.parametrize("bad_id", [None, "", "../" + INSTANCE_ID, "1767 031159524"])
def test_migrated_dry_run_rejects_bad_instance_id(tmp_path, bad_id):
    def mutate(cfg):
        if bad_id is None:
            del cfg["id"]
        else:
            cfg["id"] = bad_id

    r = dry(str(BP), HA_PATH, migrated_with(tmp_path, mutate))
    assert r.returncode == 1
    assert problems(r) == [ID_LINE]


def test_migrated_dry_run_rejects_presence_entity(tmp_path):
    p = migrated_with(tmp_path, lambda cfg: cfg["use_blueprint"]["input"].update(
        presence_entity=FP2_PRESENCE))
    r = dry(str(BP), HA_PATH, p)
    assert r.returncode == 1
    assert problems(r) == [UNKNOWN + "presence_entity"]


@pytest.mark.parametrize("key", ["presence_fp2", "presence_fp300", "illuminance_entity"])
def test_migrated_dry_run_rejects_missing_required_input(tmp_path, key):
    p = migrated_with(tmp_path, lambda cfg: cfg["use_blueprint"]["input"].pop(key))
    r = dry(str(BP), HA_PATH, p)
    assert r.returncode == 1
    assert problems(r) == [MISSING + key]


def test_migrated_dry_run_rejects_key_outside_v3_schema(tmp_path):
    p = migrated_with(tmp_path, lambda cfg: cfg["use_blueprint"]["input"].update(
        govee_lights=LIVE_INPUT["govee_lights"]))
    r = dry(str(BP), HA_PATH, p)
    assert r.returncode == 1
    assert problems(r) == [UNKNOWN + "govee_lights"]


def test_migrated_dry_run_rejects_path_without_owner(tmp_path):
    p = migrated_with(tmp_path, lambda cfg: cfg["use_blueprint"].update(
        path="circadian_livingroom.yaml"))
    r = dry(str(BP), HA_PATH, p)
    assert r.returncode == 1
    assert problems(r) == [
        "  - use_blueprint.path 'circadian_livingroom.yaml' != 'leviemartin/circadian_livingroom.yaml'"
    ]


def test_single_deployable_circadian_instance():
    files = sorted(p for p in (ROOT / "deploy").glob("circadian_livingroom_*.json")
                   if ".live-v" not in p.name)
    assert files == [INSTANCE]
    assert isinstance(json.loads(INSTANCE.read_text()), dict)


def test_no_credentials_in_migrated_instance_or_this_test():
    source = Path(__file__).read_text()
    tree = ast.parse(source)
    declaration = next(node for node in tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "CREDENTIAL_PATTERNS"
                               for t in node.targets))
    scrubbed = source.replace(ast.get_source_segment(source, declaration), "", 1)
    for text in (INSTANCE.read_text(), scrubbed):
        for pattern in CREDENTIAL_PATTERNS:
            assert not re.search(pattern, text), pattern
    for forbidden in ("hass" + "-cli", "HASS" + "_TOKEN", "." + "config/"):
        assert forbidden not in source


def test_migrated_instance_fails_against_v2_2_0_blueprint(tmp_path):
    # ponytail: synthetic old schema; extend only if validation reads more than inputs.
    # The real version guard is test_migrated_instance_dry_run_passes's exact name line.
    stub = tmp_path / "circadian_livingroom.yaml"
    stub.write_text(json.dumps({"blueprint": {
        "name": "Circadian Living Room Lights v2.2.0",
        "input": {key: {} if key in ("presence_entity", "illuminance_entity")
                  else {"default": 0} for key in V2_2_0_KEYS},
    }}))
    r = dry(str(stub), HA_PATH, str(INSTANCE))
    assert r.returncode == 1
    assert "validation passed" not in r.stdout
    assert problems(r) == [
        UNKNOWN + "notify_targets, presence_fp2, presence_fp300",
        MISSING + "presence_entity",
    ]


def test_v2_2_0_pin_removed():
    tree = ast.parse(Path(__file__).read_text())
    assert not any(isinstance(node, ast.FunctionDef)
                   and node.name == "test_live_dry_run_pins_four_stale_keys"
                   for node in ast.walk(tree))
    assert not any(isinstance(node, ast.Attribute) and node.attr == "xfail"
                   for node in ast.walk(tree))
