"""Offline checks for scripts/deploy-blueprint.sh: syntax + the --dry-run input-key validation."""
import json
import os
import re
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


def test_dry_run_rejects_unsafe_instance_id(tmp_path):
    # code board 20260907-143611 R2-002: the id is spliced into URLs and backup paths
    p = instance(tmp_path)
    cfg = json.loads(p.read_text())
    cfg["id"] = "../1774555916056"
    p.write_text(json.dumps(cfg))
    r = run("--dry-run", str(BP), HA_PATH, str(p))
    assert r.returncode == 1
    assert "instance id must match" in r.stdout


def test_token_never_in_curl_argv():
    # code board 20260907-143611 R2-001: the Authorization header comes from a 0600 temp file
    src = SCRIPT.read_text()
    # no curl header argument may carry the token in any spelling ($HASS_TOKEN, ${HASS_TOKEN}, …)
    assert not re.search(r"-H\s+[\"']?Authorization:[^\n]*HASS_TOKEN", src)
    # the token is referenced exactly twice: the presence guard and the 0600 header file write
    token_lines = [l for l in src.splitlines() if "HASS_TOKEN" in l and not l.lstrip().startswith("#")]
    assert len(token_lines) == 2, token_lines
    assert any("${HASS_TOKEN:-}" in l for l in token_lines)
    assert any('"$HASS_TOKEN" > "$HDR"' in l for l in token_lines)
    assert "-H @\"$HDR\"" in src and "chmod 600" in src and "trap 'rm -f \"$HDR\"' EXIT" in src


def test_dry_run_rejects_bad_ha_path():
    r = run("--dry-run", str(BP), "bogus")
    assert r.returncode == 1
    assert "ha-blueprint-path must look like" in r.stderr


# --- RFC 2026-11-26 D2: refuse instances whose entities do not exist ----------------------
# Offline seam: DEPLOY_STATES_FILE names a file shaped like /api/states. When it is set,
# --dry-run also runs the entity check against it; a live deploy fetches /api/states.

def states_file(tmp_path, entity_ids):
    p = tmp_path / "states.json"
    p.write_text(json.dumps([{"entity_id": e, "state": "on"} for e in entity_ids]))
    return p


def run_with_states(states, *args):
    env = dict(os.environ, DEPLOY_STATES_FILE=str(states))
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env)


def test_entity_check_passes_when_all_entities_exist(tmp_path):
    states = states_file(tmp_path, REQUIRED.values())
    r = run_with_states(states, "--dry-run", str(BP), HA_PATH, str(instance(tmp_path)))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "entities: ok" in r.stdout


def test_entity_check_rejects_missing_entity(tmp_path):
    states = states_file(tmp_path, [v for k, v in REQUIRED.items() if k != "motion_sensor"])
    r = run_with_states(states, "--dry-run", str(BP), HA_PATH, str(instance(tmp_path)))
    assert r.returncode == 1
    assert "entities missing in HA: binary_sensor.m" in r.stdout
    assert "validation passed" not in r.stdout


def test_entity_check_reads_lists_and_ignores_services_and_plain_values(tmp_path):
    states = states_file(tmp_path, [*REQUIRED.values(), "switch.b1", "switch.b2"])
    p = instance(tmp_path, notify_targets=["notify.mobile_app_x"], night_start="22:00:00",
                 target_humidity=60, boost_toggle=["switch.b1", "switch.b2"])
    r = run_with_states(states, "--dry-run", str(BP), HA_PATH, str(p))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "entities missing" not in r.stdout


def test_entity_check_reports_missing_list_member(tmp_path):
    states = states_file(tmp_path, [*REQUIRED.values(), "switch.b1"])
    p = instance(tmp_path, boost_toggle=["switch.b1", "switch.gone"])
    r = run_with_states(states, "--dry-run", str(BP), HA_PATH, str(p))
    assert r.returncode == 1
    assert "entities missing in HA: switch.gone" in r.stdout


def test_entity_check_reads_target_selector_mappings(tmp_path):
    # Codex J1 P2: target selectors store {"entity_id": [...]}
    states = states_file(tmp_path, [*REQUIRED.values(), "switch.b1"])
    p = instance(tmp_path, boost_toggle={"entity_id": ["switch.b1", "switch.gone"]})
    r = run_with_states(states, "--dry-run", str(BP), HA_PATH, str(p))
    assert r.returncode == 1
    assert "entities missing in HA: switch.gone" in r.stdout


def test_dry_run_without_states_file_stays_offline(tmp_path):
    r = run("--dry-run", str(BP), HA_PATH, str(instance(tmp_path)))
    assert r.returncode == 0
    assert "entities:" not in r.stdout


def test_live_deploy_checks_entities_before_any_write():
    src = SCRIPT.read_text()
    backup = src.index("# --- 3. back up")
    assert "check_entities" in src[src.index("# --- 2. credentials"):backup]
    assert "/api/states" in src[src.index("# --- 2. credentials"):backup]
