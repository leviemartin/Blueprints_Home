"""Documentation contract for Circadian Living Room Lights v3.0.0."""
import json
import re
from pathlib import Path

import pytest
import yaml

from test_bedroom_precool_structure import HassLoader

ROOT = Path(__file__).resolve().parent.parent
HEADING = "## Circadian Living Room Lights Blueprint"


def _read(path):
    assert path.is_file(), f"Missing file: {path}"
    text = path.read_text()
    assert text.strip(), f"Empty file: {path}"
    return text


def _section(text, heading):
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.rstrip() == heading]
    assert len(starts) == 1, f"Expected exactly one {heading!r}"
    level = len(heading.split()[0])
    start = starts[0] + 1
    end = next(
        (i for i in range(start, len(lines))
         if re.match(rf"^#{{1,{level}}} ", lines[i])),
        len(lines),
    )
    body = "\n".join(lines[start:end]).strip()
    assert body, f"Empty section: {heading}"
    return body


def _inputs(path):
    try:
        data = yaml.load(_read(path), Loader=HassLoader)
    except yaml.YAMLError as exc:
        raise AssertionError(f"Invalid blueprint YAML: {path}: {exc}") from exc
    assert isinstance(data, dict), "Blueprint document must be a mapping"
    blueprint = data.get("blueprint")
    assert isinstance(blueprint, dict), "Missing blueprint mapping"
    inputs = blueprint.get("input")
    assert isinstance(inputs, dict) and inputs, "Missing or empty blueprint inputs"
    return inputs


def _readme():
    return _section(_read(ROOT / "README.md"), HEADING)


def _req():
    return _read(ROOT / "requirements_circadian.md")


def _bp():
    return _inputs(ROOT / "circadian_livingroom.yaml")


def _docs():
    return (_readme(), _req())


def _fmt(inp):
    if "default" not in inp:
        return "required"
    default = inp["default"]
    return f"`{json.dumps(default) if isinstance(default, list) else default}`"


def _has_min(text, n):
    return re.search(rf"\b{n} min\b", text)


def test_readme_section_slice_is_strict(tmp_path):
    with pytest.raises(AssertionError):
        _read(tmp_path / "README.md")
    for text in ("No heading", f"{HEADING}\nx\n{HEADING}\ny",
                 f"{HEADING}\n## Next"):
        with pytest.raises(AssertionError):
            _section(text, HEADING)
    body = _readme()
    assert not any(re.match(r"^## ", line) for line in body.splitlines())
    assert "### Overview" in body
    assert "LG AC Sleep & Movie Mode Blueprint" not in body


def test_requirements_file_must_exist_and_have_text(tmp_path):
    path = tmp_path / "requirements_circadian.md"
    with pytest.raises(AssertionError):
        _read(path)
    path.write_text(" \n\t")
    with pytest.raises(AssertionError):
        _read(path)
    assert _req()


def test_blueprint_must_load_with_hassloader(tmp_path):
    path = tmp_path / "circadian_livingroom.yaml"
    with pytest.raises(AssertionError):
        _inputs(path)
    for text in ("blueprint:\n  input: [unclosed\n",
                 "blueprint:\n  input:\n    x: !secret y\n"):
        path.write_text(text)
        with pytest.raises(AssertionError):
            _inputs(path)
    assert _bp()


def test_blueprint_without_inputs_fails(tmp_path):
    path = tmp_path / "circadian_livingroom.yaml"
    for text in ("blueprint: {name: x}", "blueprint: {input: {}}",
                 "blueprint: {input: null}"):
        path.write_text(text)
        with pytest.raises(AssertionError):
            _inputs(path)


def test_version_3_0_0_in_both_docs():
    _bp()
    data = yaml.load(_read(ROOT / "circadian_livingroom.yaml"), Loader=HassLoader)
    assert data["blueprint"]["name"].endswith("v3.0.0")
    for text in _docs():
        assert "v3.0.0" in text


def test_no_stale_text():
    for text in _docs():
        assert not re.search(r"(?i)\b300\s*(lux|lx)\b", text)
        assert not re.search(r"\blux_threshold\b", text)
        assert "Presence:** Aqara FP2 (binary_sensor)" not in text
        assert "utilizes the Aqara FP2 (or any lux+presence sensor)" not in text
    assert "presence_entity" not in _req()


def test_every_blueprint_input_key_is_in_requirements():
    text = _req()
    missing = [key for key in _bp() if f"`{key}`" not in text]
    assert not missing, f"Undocumented inputs: {missing}"


def test_requirements_inputs_table_matches_blueprint():
    rows = re.findall(
        r"^\|\s*`([a-z0-9_]+)`\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$",
        _section(_req(), "### 4.1. Inputs"), re.MULTILINE,
    )
    keys = [key for key, _, _ in rows]
    inputs = _bp()
    assert len(keys) == len(set(keys)), "Duplicate input rows"
    assert keys == list(inputs), "Input table keys/order differ from blueprint"
    for key, default, meaning in rows:
        assert default == _fmt(inputs[key]), f"Wrong default for {key}"
        assert meaning.strip(), f"Missing meaning for {key}"


def test_both_presence_inputs_documented():
    for text in _docs():
        for key in ("presence_fp2", "presence_fp300"):
            assert key in text
        assert "either sensor" in text.lower()
        assert "both sensors are clear" in text.lower()


def test_late_night_defaults_match_blueprint_and_docs():
    inputs = _bp()
    expected = {
        "late_night_start": "23:00:00", "late_night_end": "06:30:00",
        "late_night_timeout": 1, "presence_timeout": 5,
    }
    for key, value in expected.items():
        assert inputs[key]["default"] == value, key
    for text in _docs():
        for key in expected:
            assert key in text
        for key in ("late_night_start", "late_night_end"):
            assert inputs[key]["default"][:5] in text
        for key in ("late_night_timeout", "presence_timeout"):
            assert _has_min(text, inputs[key]["default"])


def test_boundary_behaviour_documented():
    inputs = _bp()
    start = inputs["late_night_start"]["default"][:5]
    end = inputs["late_night_end"]["default"][:5]
    for text in _docs():
        for phrase in (f"before {start}", f"just after {start}",
                       f"at or after {end}", "no extra trigger",
                       "independent of the late-night window"):
            assert phrase in text
        assert "already running at" not in text


def test_dog_stay_on_note():
    for text in _docs():
        lines = [line for line in text.splitlines()
                 if "dog" in line.lower() and "bench" in line.lower()
                 and "FP300" in line]
        assert lines, "Missing dog/bench/FP300 stay-on note"
        if text == _readme():
            assert any("still being tested" in line for line in lines)


def test_fp300_setup_documented():
    for text in _docs():
        for phrase in ("Zigbee2MQTT", "mmWave", "PIR",
                       "absence_delay_timer", "60 s"):
            assert phrase in text
        assert _has_min(text, 2)


def test_lux_defaults_and_per_instance():
    inputs = _bp()
    for key, value in (("lux_on_threshold", 150), ("lux_off_threshold", 400),
                       ("lux_off_duration", 5)):
        assert inputs[key]["default"] == value, key
    for text in _docs():
        for key in ("lux_on_threshold", "lux_off_threshold"):
            assert key in text
            assert f'{inputs[key]["default"]} lx' in text
        assert "FP300 lux is not read" in text
        assert "per instance" in text.lower()


def test_notify_targets_and_offline_notice():
    for text in _docs():
        for phrase in ("notify_targets", "notify.", "after the light calls"):
            assert phrase in text
        assert _has_min(text, 30)


def test_readme_install_uses_deploy_script():
    payload = "deploy/circadian_livingroom_1767031159524.json"
    assert (ROOT / payload).is_file(), f"Missing migration dependency: {payload}"
    text = _readme()
    for phrase in (
        "scripts/deploy-blueprint.sh circadian_livingroom.yaml "
        f"leviemartin/circadian_livingroom.yaml {payload}",
        "--dry-run", "hass-cli", "jq", "PyYAML", "PYTHON",
        "~/.config/hass-cli/env",
        "https://raw.githubusercontent.com/leviemartin/Blueprints_Home/main/"
        "circadian_livingroom.yaml",
        "requirements_circadian.md",
    ):
        assert phrase in text


def test_docs_hold_no_credentials():
    patterns = (
        r"eyJ[A-Za-z0-9_-]{8,}", r"(?i)bearer\s",
        r"HASS_(TOKEN|SERVER)\s*=", r"\b\d{1,3}(\.\d{1,3}){3}\b",
        r"(?i)\b(password|api[_-]?key)\b",
    )
    for text in _docs():
        for pattern in patterns:
            assert not re.search(pattern, text), f"Credential pattern: {pattern}"
