"""Offline checks for scripts/deploy-blueprint.sh: syntax + the --dry-run input-key validation."""
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "deploy-blueprint.sh"
BP = ROOT / "bathroom_ventilator.yaml"
HA_PATH = "leviemartin/bathroom_ventilator.yaml"
REQUIRED = {
    "fan_switch": "light.x", "humidity_sensor": "sensor.rh", "temperature_sensor": "sensor.t",
    "motion_sensor": "binary_sensor.m", "weather_entity": "weather.w",
}


def run(*args):
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True)


def instance(tmp_path, **extra):
    cfg = {"id": "1774555916056", "alias": "x", "description": "",
           "use_blueprint": {"path": HA_PATH, "input": {**REQUIRED, **extra}}}
    p = tmp_path / "inst.json"
    p.write_text(json.dumps(cfg))
    return p


def test_script_syntax():
    assert subprocess.run(["bash", "-n", str(SCRIPT)]).returncode == 0


def test_dry_run_accepts_valid_instance(tmp_path):
    r = run("--dry-run", str(BP), HA_PATH, str(instance(tmp_path)))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "dry-run: validation passed" in r.stdout
    assert "ok (id 1774555916056" in r.stdout


def test_dry_run_rejects_unknown_key(tmp_path):
    r = run("--dry-run", str(BP), HA_PATH, str(instance(tmp_path, refresh_bogus=1)))
    assert r.returncode == 1
    assert "unknown input keys" in r.stdout


def test_dry_run_rejects_missing_required(tmp_path):
    p = instance(tmp_path)
    cfg = json.loads(p.read_text())
    del cfg["use_blueprint"]["input"]["humidity_sensor"]
    p.write_text(json.dumps(cfg))
    r = run("--dry-run", str(BP), HA_PATH, str(p))
    assert r.returncode == 1
    assert "required inputs missing: humidity_sensor" in r.stdout


def test_dry_run_rejects_bad_ha_path():
    r = run("--dry-run", str(BP), "bogus")
    assert r.returncode == 1
    assert "ha-blueprint-path must look like" in r.stderr
