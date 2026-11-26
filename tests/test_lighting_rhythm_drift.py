"""RFC 2026-11-26 D7/D8: every circadian lighting instance follows one shared rhythm.

Each instance keeps its own inputs (no shared helper), so this test is what stops the rooms
drifting apart. Effective value = the instance input, else the blueprint default. The living
room's values are the reference.
"""
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "deploy"
LIVING = DEPLOY / "circadian_livingroom_1767031159524.json"
ADJACENT = sorted(p for p in DEPLOY.glob("adjacent_room_lights_*.json") if ".live-v" not in p.name)
SHARED_KEYS = [
    "time_dinner", "dinner_kelvin", "dinner_bri",
    "time_toddler", "toddler_kelvin", "toddler_bri",
    "time_evening", "evening_kelvin", "evening_bri",
    "time_night", "night_kelvin", "night_bri",
    "min_kelvin", "max_kelvin",
]
REFERENCE = {
    "time_dinner": "17:45:00", "dinner_kelvin": 2300, "dinner_bri": 90,
    "time_toddler": "18:45:00", "toddler_kelvin": 2100, "toddler_bri": 85,
    "time_evening": "20:00:00", "evening_kelvin": 2000, "evening_bri": 70,
    "time_night": "23:30:00", "night_kelvin": 2000, "night_bri": 29,
    "min_kelvin": 2000, "max_kelvin": 4000,
}


def defaults(blueprint):
    class Loader(yaml.SafeLoader):
        pass

    Loader.add_constructor("!input", lambda loader, node: loader.construct_scalar(node))
    inputs = yaml.load((ROOT / blueprint).read_text(), Loader=Loader)["blueprint"]["input"]
    return {k: v.get("default") for k, v in inputs.items()}


def effective(path):
    cfg = json.loads(path.read_text())
    blueprint = cfg["use_blueprint"]["path"].split("/", 1)[1]
    return {**defaults(blueprint), **cfg["use_blueprint"]["input"]}


def test_adjacent_instance_set_is_the_four_rooms():
    names = {json.loads(p.read_text())["alias"] for p in ADJACENT}
    assert len(ADJACENT) == 4
    assert {n.split("]")[0] + "]" for n in names} == {"[Kitchen]", "[Front Hall]", "[Toilet]", "[Attic]"}


def test_living_room_is_the_reference():
    eff = effective(LIVING)
    assert {k: eff[k] for k in SHARED_KEYS} == REFERENCE


@pytest.mark.parametrize("path", ADJACENT, ids=lambda p: p.stem)
def test_adjacent_rooms_follow_the_living_room(path):
    eff = effective(path)
    drift = {k: (eff.get(k), REFERENCE[k]) for k in SHARED_KEYS if eff.get(k) != REFERENCE[k]}
    assert not drift, drift


@pytest.mark.parametrize("path", [LIVING, *ADJACENT], ids=lambda p: p.stem)
def test_shared_values_set_explicitly(path):
    """Pinning in the instance means a blueprint default change cannot shift one room alone."""
    inp = json.loads(path.read_text())["use_blueprint"]["input"]
    assert [k for k in SHARED_KEYS if k not in inp] == []
