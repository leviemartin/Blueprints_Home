"""Threat coverage for the bedroom_precool.yaml v1.3.0 threat map: every threat points at an existing acceptance test, plus the safety-order, mode and notice-id pins that had no test of their own (US-01, US-06, US-07, US-14)."""
import ast
import re

import pytest
import yaml

from test_bedroom_precool_heating_bedtime import _winter_steps
from test_bedroom_precool_structure import (
    BP_PATH,
    HassLoader,
    _has_notification_id,
    _service_steps,
    _top_level_steps,
)

THREAT_MAP = BP_PATH.parent / "docs" / "design" / "2026-11-10-bedroom-ac-pre-warm-v1-3-0-extend-bedroom-precoo-threat-map.md"
THREATS = [f"TM-{n}" for n in range(1, 16)]
HEADING = re.compile(r"^## (TM-\d+)\b")
ENTRY = re.compile(r"^- `([\w./-]+\.py)::(\w+)`")
CUT_NOTICES = [
    "bedroom_precool_heat_vacation",
    "bedroom_precool_heat_season_flip",
    "bedroom_precool_heat_sensors_failed",
    "bedroom_precool_heat_overheat",
]
WINTER_NOTICES = CUT_NOTICES + [
    "bedroom_precool_heat_timer_not_armed",
    "bedroom_precool_heat_wrong_mode",
    "bedroom_precool_heat_manual_override",
    "bedroom_precool_heat_unsupported",
    "bedroom_precool_season_toggle_invalid",
]


@pytest.fixture(scope="module")
def bp():
    return yaml.load(BP_PATH.read_text(), Loader=HassLoader)


def _is_service(node, name):
    return (node.get("service") or node.get("action")) == name


def _parse(text):
    mapping, current = {}, None
    for line in text.splitlines():
        heading = HEADING.match(line)
        if heading:
            current = heading.group(1)
            mapping[current] = []
        elif line.startswith("## "):
            current = None
        elif current:
            entry = ENTRY.match(line)
            if entry:
                mapping[current].append(entry.groups())
    return mapping


def _problems(mapping):
    found = []
    for threat in THREATS:
        entries = mapping.get(threat) or []
        if not entries:
            found.append(f"{threat}: no mapped test")
        for rel, name in entries:
            path = BP_PATH.parent / rel
            if not path.is_file():
                found.append(f"{threat}: missing test file {rel}")
                continue
            defined = {n.name for n in ast.parse(path.read_text()).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            if name not in defined:
                found.append(f"{threat}: no test {name} in {rel}")
    return found


def test_us01_every_threat_is_mapped_to_an_existing_acceptance_test():
    assert THREAT_MAP.is_file(), "the threat map document is missing"
    text = THREAT_MAP.read_text()
    assert re.search(r"^## Residual gaps$", text, re.M)
    assert _problems(_parse(text)) == []


def test_us01_the_coverage_check_fails_for_a_missing_threat_file_or_test_name():
    mapping = _parse(THREAT_MAP.read_text())
    assert _problems({k: v for k, v in mapping.items() if k != "TM-7"}) == ["TM-7: no mapped test"]
    assert _problems({**mapping, "TM-1": [("tests/test_nope.py", "test_us13_x")]}) == [
        "TM-1: missing test file tests/test_nope.py"
    ]
    wrong = ("tests/test_bedroom_precool_heating_inputs.py", "test_us13_nope")
    assert _problems({**mapping, "TM-1": [wrong]}) == [f"TM-1: no test {wrong[1]} in {wrong[0]}"]


def test_us07_the_winter_safety_cuts_come_before_the_first_forecast_call(bp):
    steps = _top_level_steps(bp)
    first_forecast = next(i for i, s in enumerate(steps) if any(_is_service(n, "weather.get_forecasts") for _, n in _service_steps(s, [])))
    for notice in CUT_NOTICES:
        cut = next(i for i, s in enumerate(steps) if _has_notification_id(s, notice))
        assert cut < first_forecast, notice
        assert any(_is_service(n, "climate.turn_off") for _, n in _service_steps(steps[cut], [])), notice


def test_us07_the_winter_safety_cuts_read_no_forecast_variable(bp):
    steps = _top_level_steps(bp)
    first = next(i for i, s in enumerate(steps) if "safe_overheat_due" in (s.get("variables") or {}))
    last = next(i for i, s in enumerate(steps) if _has_notification_id(s, "bedroom_precool_heat_overheat"))
    assert first < last
    assert "forecast" not in repr(steps[first : last + 1])


def test_us06_every_winter_command_that_names_a_mode_names_heat(bp):
    modes = [(n.get("data") or {}).get("hvac_mode") for _, n in _service_steps(_winter_steps(bp), [])]
    modes = [m for m in modes if m is not None]
    assert len(modes) >= 3 and set(modes) == {"heat"}


def test_us14_every_notice_id_is_a_constant_and_each_winter_notice_has_one(bp):
    creates = [n for _, n in _service_steps(_top_level_steps(bp), []) if _is_service(n, "persistent_notification.create")]
    ids = [str((n.get("data") or {}).get("notification_id", "")) for n in creates]
    assert not [i for i in ids if "{" in i]
    for notice in WINTER_NOTICES:
        assert ids.count(notice) == 1, notice
