"""Offline deployment fixtures; live checks and approvals belong to the orchestrator."""
import ast
import json
import re
from pathlib import Path

import pytest
import yaml
from test_deploy_blueprint_script import run

ROOT = Path(__file__).resolve().parent.parent
BP = ROOT / "adjacent_room_lights.yaml"
HA_PATH = "leviemartin/adjacent_room_lights.yaml"
KITCHEN_ID = "1773749905520"
FRONT_HALL_ID = "1773750307485"
TOILET_ID = "1773750379398"
ATTIC_ID = "1792275807786"
R81_ID = "1727114576587"
R82_ID = "1727114932689"
DEPLOY = ROOT / "deploy"
INSTANCES = [
    (iid, DEPLOY / f"adjacent_room_lights_{iid}.live-v1.0.0.json",
     DEPLOY / f"adjacent_room_lights_{iid}.json", sensor, count)
    for iid, sensor, count in [
        (KITCHEN_ID, "binary_sensor.kitchen_motion_sensor", 16),
        (FRONT_HALL_ID, "binary_sensor.frontdoor_hall_motion", 17),
        (TOILET_ID, "binary_sensor.toilet_motion_sensor", 16),
    ]
]
KITCHEN, FRONT_HALL, TOILET = [row[2] for row in INSTANCES]
ATTIC = DEPLOY / f"adjacent_room_lights_{ATTIC_ID}.json"
R81 = DEPLOY / f"8_1_attic_main_motion_{R81_ID}.retired.json"
R82 = DEPLOY / f"8_2_attic_stairs_motion_{R82_ID}.retired.json"
FILES = [p for row in INSTANCES for p in row[1:3]] + [ATTIC, R81, R82]
CREDENTIAL_PATTERNS = [
    r"eyJ[A-Za-z0-9_-]{8,}", r"(?i)bearer\s", r"(?i)https?://", r"\b\d{1,3}(\.\d{1,3}){3}\b",
    r"HASS_(TOKEN|SERVER)\s*=", r"(?i)\b(password|api[_-]?key)\b",
]


def dry(*args):
    return run("--dry-run", *args)


def read(path):
    return json.loads(path.read_text())


def test_all_instances_dry_run_pass():
    result = dry(BP, HA_PATH, KITCHEN, FRONT_HALL, TOILET, ATTIC)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "blueprint: Adjacent Room Circadian Lights v2.0.0" in result.stdout
    for iid, _, _, _, count in INSTANCES:
        assert f"ok (id {iid}, {count} inputs)" in result.stdout
    assert f"ok (id {ATTIC_ID}, 5 inputs)" in result.stdout
    assert "dry-run: validation passed" in result.stdout


@pytest.mark.parametrize("iid,live,migrated,sensor,count", INSTANCES)
def test_migrated_differs_from_live_only_in_sensor_key(iid, live, migrated, sensor, count):
    old, new = read(live), read(migrated)
    old_inputs = old["use_blueprint"].pop("input")
    new_inputs = new["use_blueprint"].pop("input")
    assert old == new
    assert old["id"] == iid
    assert old["use_blueprint"] == {"path": HA_PATH}
    assert len(old_inputs) == len(new_inputs) == count
    assert old_inputs.pop("motion_sensor") == sensor
    assert new_inputs.pop("motion_sensors") == [sensor]
    assert "motion_sensors" not in old_inputs
    assert "motion_sensor" not in new_inputs
    assert old_inputs == new_inputs


@pytest.mark.parametrize("iid,live,migrated,sensor,count", INSTANCES)
def test_live_snapshot_has_no_unknown_keys(iid, live, migrated, sensor, count):
    class Loader(yaml.SafeLoader):
        pass

    Loader.add_constructor("!input", lambda loader, node: loader.construct_scalar(node))
    keys = yaml.load(BP.read_text(), Loader=Loader)["blueprint"]["input"]
    data = read(live)
    assert set(data) == {"id", "alias", "description", "use_blueprint"}
    assert set(data["use_blueprint"]) == {"path", "input"}
    assert set(data["use_blueprint"]["input"]) - {"motion_sensor"} <= set(keys)


@pytest.mark.parametrize("iid,live,migrated,sensor,count", INSTANCES)
def test_live_snapshot_fails_v2_dry_run(iid, live, migrated, sensor, count):
    result = dry(BP, HA_PATH, live)
    assert result.returncode == 1
    assert "unknown input keys (would make the instance unavailable): motion_sensor" in result.stdout
    assert "required inputs missing: motion_sensors" in result.stdout


def test_attic_instance_inputs():
    assert read(ATTIC) == {
        "id": ATTIC_ID,
        "alias": "[Attic] Adjacent Room Circadian Lights v2.0.0",
        "description": "",
        "use_blueprint": {
            "path": HA_PATH,
            "input": {
                "motion_sensors": [
                    "binary_sensor.attic_atticlaudry_occupancy",
                    "binary_sensor.attic_atticdoor_occupancy",
                ],
                "target_lights": ["light.attic_2", "light.attic_3", "light.attic_stairs"],
                "time_to_stage1": 2,
                "time_to_stage2": 4,
                "time_to_off": 5,
            },
        },
    }


def test_attic_does_not_duplicate_existing():
    attic = read(ATTIC)
    assert attic["id"] not in {read(p)["id"] for p in (KITCHEN, FRONT_HALL, TOILET, R81, R82)}
    for _, _, migrated, _, _ in INSTANCES:
        other = read(migrated)["use_blueprint"]["input"]
        for key in ("motion_sensors", "target_lights"):
            assert set(attic["use_blueprint"]["input"][key]).isdisjoint(other[key])


def test_ids_match_filenames():
    for path in FILES:
        match = re.fullmatch(
            r"adjacent_room_lights_(\d+)(?:\.live-v[\d.]+)?\.json"
            r"|8_[12]_.*_(\d+)\.retired\.json", path.name
        )
        assert match, path.name
        assert read(path)["id"] == (match.group(1) or match.group(2))


def test_one_deployable_file_per_instance():
    files = sorted(p.name for p in DEPLOY.glob("adjacent_room_lights_*.json")
                   if ".live-v" not in p.name)
    assert files == sorted(p.name for p in (KITCHEN, FRONT_HALL, TOILET, ATTIC))


def test_retired_files_keep_original_ids_and_aliases():
    for path, iid, alias in (
        (R81, R81_ID, "8.1 Attic_Main Motion"),
        (R82, R82_ID, "8.2 Attic Stairs Motion"),
    ):
        data = read(path)
        assert data["id"] == iid
        assert data["alias"] == alias
        assert set(data) == {"action", "alias", "condition", "description", "id", "mode", "trigger"}
        assert isinstance(data["trigger"], list) and data["trigger"]
        assert isinstance(data["action"], list) and data["action"]


def test_retired_files_device_targets_pinned():
    def objects(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from objects(child)
        elif isinstance(value, list):
            for child in value:
                yield from objects(child)

    for path, expected in (
        (R81, {"c728df20585bd1f127744574a0b8730b", "70ddcd041339e200a0a7a94dedf93ff2"}),
        (R82, {"ba955faf530e4c6c55f1f9ae0ea5a321"}),
    ):
        devices, scenes = [], []
        for obj in objects(read(path)):
            target = obj.get("target", {})
            entities = target.get("entity_id", [])
            if isinstance(entities, str):
                entities = [entities]
            scenes.extend(entity for entity in entities if entity.startswith("scene."))
            if obj.get("action") == "hue.activate_scene":
                assert entities and all(entity.startswith("scene.attic_") for entity in entities)
            if obj.get("action") == "light.turn_off":
                assert set(target) == {"device_id"}
                ids = target["device_id"]
                devices.extend([ids] if isinstance(ids, str) else ids)
        assert scenes and all(scene.startswith("scene.attic_") for scene in scenes)
        assert set(devices) == expected
        assert len(devices) == len(expected)


def test_data_files_canonical_json():
    for path in FILES:
        assert path.read_text() == json.dumps(read(path), indent=2, sort_keys=True) + "\n"


def test_no_credentials_in_deploy_files_or_this_test():
    source = Path(__file__).read_text()
    tree = ast.parse(source)
    declaration = next(node for node in tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "CREDENTIAL_PATTERNS"
                               for t in node.targets))
    scrubbed = source.replace(ast.get_source_segment(source, declaration), "", 1)
    for text in [*(path.read_text() for path in FILES), scrubbed]:
        for pattern in CREDENTIAL_PATTERNS:
            assert not re.search(pattern, text), pattern
    for forbidden in ("hass" + "-cli", "HASS" + "_TOKEN", "." + "config/"):
        assert forbidden not in source


def test_dry_run_rejects_path_without_owner():
    result = dry(BP, "adjacent_room_lights.yaml", KITCHEN)
    assert result.returncode == 1
    assert "ha-blueprint-path must look like" in result.stderr


@pytest.mark.parametrize("kind", ["empty", "no_sensors"])
def test_dry_run_rejects_empty_or_partial_instance(tmp_path, kind):
    path = tmp_path / "instance.json"
    if kind == "empty":
        path.write_text("")
    else:
        data = read(ATTIC)
        del data["use_blueprint"]["input"]["motion_sensors"]
        path.write_text(json.dumps(data))
    result = dry(BP, HA_PATH, path)
    assert result.returncode == 1
    assert "validation passed" not in result.stdout
    assert "ok (id" not in result.stdout
    if kind == "no_sensors":
        assert "required inputs missing: motion_sensors" in result.stdout


def test_every_run_call_passes_dry_run():
    tree = ast.parse(Path(__file__).read_text())
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id == "run"]
    assert calls
    assert all(call.args and isinstance(call.args[0], ast.Constant)
               and call.args[0].value == "--dry-run" for call in calls)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] != "subprocess" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] != "subprocess"
