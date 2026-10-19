import asyncio
from itertools import count
import re

import pytest
from homeassistant.core import callback
from homeassistant.util.yaml import load_yaml

from conftest import REPO, advance, settle as settle_loop
from test_ha_livingroom_music_core import (
    boot, put, edge, calls, only, fresh, direct,
    SONOS, BEDROOM, HANDS, OWNED, PHONE, APP, FP2, FP300, LG,
)

pytestmark = [
    pytest.mark.usefixtures("settled_teardown"),
    pytest.mark.parametrize("expected_lingering_timers", [True]),
]
STEP = "input_number.livingroom_music_volume_step"
VOLUME = "livingroom_music_volume"
EVENTS = count(1)


async def volume_direct(hass, **data):
    await hass.services.async_call("script", VOLUME, data, blocking=True)
    await settle_loop(hass)


async def press(hass, button, kind="short_release", settle=True):
    hass.states.async_set(
        f"event.kitchen_button_{button}",
        f"2026-10-20T10:00:00.{next(EVENTS):06d}+00:00",
        {"event_type": kind},
    )
    if settle:
        await settle_loop(hass)


def volumes(services):
    return [c.data["volume_level"] for c in services.sonos_calls()
            if c.service == "volume_set"]


@pytest.fixture
def music(hass, boot):
    async def load(**kwargs):
        package = await boot(**kwargs)
        assert hass.states.get(STEP) is not None
        return package
    return load


async def test_volume_package_loads(hass, music, services):
    package = await music()
    assert "livingroom_music_remote" in {a["id"] for a in package["automation"]}
    assert hass.states.is_state("script." + VOLUME, "off")
    assert float(hass.states.get(STEP).state) == 2
    assert not calls(services)


def test_volume_text_rules():
    path = REPO / "ha/packages/livingroom_music.yaml"
    text = path.read_text()
    assert text.count("[0.05, 0.10, 0.15, 0.20, 0.25, 0.30]") == 1
    assert text.count("[0.05, 0.10, 0.15, 0.20, 0.25]") == 1
    assert all(float(n) <= 0.30 for n in re.findall(r"\b\d+\.\d+\b", text))
    assert text.count("0.30") == 1
    assert "volume_up" not in text and "volume_down" not in text
    levels = [line.strip() for line in text.splitlines() if "volume_level:" in line]
    assert sorted(levels) == sorted([
        'volume_level: "{{ level }}"', *['volume_level: "{{ restore_level }}"'] * 2,
    ])
    for line in text.splitlines():
        if re.match(r"\s*delta:", line) and line.split(":", 1)[1].strip():
            assert line.split(":", 1)[1].strip() in ("1", "-1")
    pending = [load_yaml(str(path))]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            if "action" in node or "service" in node:
                data = node.get("data", {})
                if "step" in data:
                    assert type(data["step"]) is int and 0 <= data["step"] <= 5
                if "delta" in data:
                    assert type(data["delta"]) is int and data["delta"] in (-1, 1)
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)


async def test_brighten_dim_ladder(hass, music, services):
    await music()
    await hass.services.async_call("input_number", "set_value",
                                   {"entity_id": STEP, "value": 0}, blocking=True)
    for button in [2] * 4 + [3] * 4:
        await press(hass, button)
    assert volumes(services) == [0.10, 0.15, 0.20, 0.25, 0.20, 0.15, 0.10, 0.05]
    assert all(c.service == "volume_set" and set(c.data["entity_id"]) == {SONOS, BEDROOM}
               for c in services.sonos_calls())
    assert float(hass.states.get(STEP).state) == 0


async def test_rapid_presses(hass, music, services):
    await music()
    await hass.services.async_call("input_number", "set_value",
                                   {"entity_id": STEP, "value": 0}, blocking=True)
    for _ in range(3):
        await press(hass, 2, settle=False)
    await settle_loop(hass)
    assert volumes(services) == [0.10, 0.15, 0.20]
    assert float(hass.states.get(STEP).state) == 3


async def test_off_queued_behind_hands_off(hass, music, services):
    await music(states={SONOS: "playing"}, attrs={SONOS: APP})

    @callback
    def block(call):
        services.record(call)
        hass.states.async_set(HANDS, "on")

    hass.services.async_register("media_player", "volume_set", block)
    await press(hass, 2, settle=False)
    await press(hass, 4, settle=False)
    await settle_loop(hass)
    assert volumes(services) == [0.20]
    assert [c.service for c in services.sonos_calls()] == ["volume_set"]


@pytest.mark.parametrize("case", ["plain", "phone_session"])
async def test_brighten_cap(hass, music, services, case):
    await music(states={SONOS: "playing"}, attrs={SONOS: PHONE if case == "phone_session" else APP})
    await hass.services.async_call("input_number", "set_value",
                                   {"entity_id": STEP, "value": 4}, blocking=True)
    for _ in range(3):
        await press(hass, 2)
    assert not calls(services)
    assert float(hass.states.get(STEP).state) == 4


async def test_dim_floor(hass, music, services):
    await music()
    await hass.services.async_call("input_number", "set_value",
                                   {"entity_id": STEP, "value": 0}, blocking=True)
    await press(hass, 3)
    assert not calls(services)
    assert float(hass.states.get(STEP).state) == 0


async def test_volume_in_phone_session(hass, music, services):
    await music(states={SONOS: "playing"}, attrs={SONOS: PHONE})
    await press(hass, 2)
    assert volumes(services) == [0.20]
    assert float(hass.states.get(STEP).state) == 3
    await press(hass, 3)
    assert volumes(services) == [0.20, 0.15]
    assert float(hass.states.get(STEP).state) == 2
    assert [c.service for c in services.sonos_calls()] == ["volume_set"] * 2


@pytest.mark.parametrize("button", [2, 3, 4])
@pytest.mark.parametrize("kind", ["initial_press", "repeat", "long_press", "long_release", "double_press"])
async def test_non_press_events(hass, music, services, button, kind):
    await music(states={SONOS: "playing"}, attrs={SONOS: APP})
    await press(hass, button, kind)
    assert not calls(services)


@pytest.mark.parametrize("button", [2, 3, 4])
@pytest.mark.parametrize("case", ["from_unavailable", "from_unknown", "to_unavailable", "to_unknown", "re_added"])
async def test_event_entity_unavailable(hass, music, services, caplog, button, case):
    await music(states={SONOS: "playing"}, attrs={SONOS: APP})
    entity = f"event.kitchen_button_{button}"
    if case == "re_added":
        hass.states.async_remove(entity)
        await settle_loop(hass)
        assert not calls(services)
        assert not [r for r in caplog.records if r.levelno >= 40]
        await press(hass, button)
    elif case.startswith("from_"):
        await put(hass, entity, case.removeprefix("from_"))
        await press(hass, button)
    else:
        await put(hass, entity, case.removeprefix("to_"), {"event_type": "short_release"})
    assert not calls(services)
    assert not [r for r in caplog.records if r.levelno >= 40]


@pytest.mark.parametrize("state", ["unknown", "unavailable", "-1", "6", "2.5"])
@pytest.mark.parametrize("action", ["up", "down", "direct"])
async def test_step_invalid(hass, music, services, state, action):
    await music()
    await put(hass, STEP, state)
    if action == "direct":
        await volume_direct(hass)
    else:
        await press(hass, 2 if action == "up" else 3)
    assert not calls(services)
    assert hass.states.get(STEP).state == state
    await volume_direct(hass, step=5)
    assert not calls(services)
    assert hass.states.get(STEP).state == state


async def test_off_skips(hass, music, services):
    await music(states={SONOS: "playing"}, attrs={SONOS: APP})
    await press(hass, 4)
    only(services, "media_next_track")


@pytest.mark.parametrize("case", ["phone_session", "paused", "bedroom_unavailable"])
async def test_off_ignored(hass, music, services, case):
    await music(states={SONOS: "paused" if case == "paused" else "playing",
                        BEDROOM: "unavailable" if case == "bedroom_unavailable" else "idle"},
                attrs={SONOS: PHONE if case == "phone_session" else APP})
    await press(hass, 4)
    assert not calls(services)


@pytest.mark.parametrize("button", [2, 3, 4], ids=["up", "down", "off"])
async def test_hands_off_ignores_remote(hass, music, services, button):
    await music(hands=True, states={SONOS: "playing"}, attrs={SONOS: APP})
    await press(hass, button)
    assert not calls(services)
    assert float(hass.states.get(STEP).state) == 2


@pytest.mark.parametrize("case", ["hands", "sonos_unavailable", "bedroom_unavailable"])
async def test_volume_script_guards(hass, music, services, case):
    states = {SONOS: "unavailable"} if case == "sonos_unavailable" else {}
    if case == "bedroom_unavailable":
        states[BEDROOM] = "unavailable"
    await music(hands=case == "hands", states=states)
    await volume_direct(hass)
    assert not calls(services)
    assert float(hass.states.get(STEP).state) == 2


@pytest.mark.parametrize("speaker", [SONOS, BEDROOM])
@pytest.mark.parametrize("button", [2, 3, 4], ids=["up", "down", "off"])
async def test_speakers_unavailable(hass, music, services, caplog, speaker, button):
    await music(states={SONOS: "playing", speaker: "unavailable"}, attrs={SONOS: APP})
    await press(hass, button)
    assert not calls(services)
    assert float(hass.states.get(STEP).state) == 2
    assert not [r for r in caplog.records if r.levelno >= 40]


@pytest.mark.parametrize("order", ["press_then_fresh", "fresh_then_press"])
async def test_fresh_start_and_press_ordering(hass, music, services, order):
    await music()
    await hass.services.async_call("input_number", "set_value",
                                   {"entity_id": STEP, "value": 3}, blocking=True)
    release, entered = asyncio.Event(), asyncio.Event()

    async def hold(call):
        if not entered.is_set():
            entered.set()
            await release.wait()
        services.record(call)

    hass.services.async_register("media_player", "volume_set", hold)
    try:
        await hass.services.async_call("script", "turn_on",
                                       {"entity_id": "script." + VOLUME, "variables": {"step": 0}},
                                       blocking=True)
        await settle_loop(hass)
        assert entered.is_set()
        if order == "press_then_fresh":
            await press(hass, 2)
            await edge(hass)
        else:
            await edge(hass)
            await press(hass, 2)
        assert hass.states.get("script." + VOLUME).attributes["current"] == 3
    finally:
        release.set()
        await settle_loop(hass)
    expected = [0.05, 0.10, 0.15] if order == "press_then_fresh" else [0.05, 0.15, 0.20]
    assert volumes(services) == expected
    observed = calls(services)
    assert len(observed) == 5
    assert all(set(data["entity_id"]) == {SONOS, BEDROOM}
               for name, data in observed if name == "volume_set")
    fresh_index = next(i for i, (name, data) in enumerate(observed)
                       if name == "volume_set" and data["volume_level"] == 0.15)
    play_index = next(i for i, (name, _) in enumerate(observed) if name == "play_media")
    shuffle_index = next(i for i, (name, _) in enumerate(observed) if name == "shuffle_set")
    assert fresh_index < play_index < shuffle_index
    assert observed[play_index][1] == {
        "entity_id": SONOS, "media_content_id": "spotify:playlist:37i9dQZF1DWTc452KG008d",
        "media_content_type": "playlist", "enqueue": "replace",
    }
    assert observed[shuffle_index][1] == {"entity_id": SONOS, "shuffle": True}
    assert float(hass.states.get(STEP).state) == (2 if order == "press_then_fresh" else 3)


@pytest.mark.parametrize("change", ["hands_off", "bedroom_unavailable"])
async def test_guard_change_during_step_write(hass, music, services, caplog, change):
    await music()
    original = hass.services.async_services()["input_number"]["set_value"]

    async def interrupt(call):
        entities = call.data.get("entity_id", [])
        if STEP == entities or STEP in entities:
            hass.states.async_set(HANDS if change == "hands_off" else BEDROOM,
                                  "on" if change == "hands_off" else "unavailable")
        return await original.job.target(call)

    hass.services.async_register("input_number", "set_value", interrupt, schema=original.schema)
    await press(hass, 2)
    assert not calls(services)
    assert float(hass.states.get(STEP).state) == 3
    assert not [r for r in caplog.records if r.levelno >= 40]


@pytest.mark.parametrize("change", ["phone_session", "lg_on"])
async def test_fresh_start_guard_in_queue(hass, music, services, change):
    await music()
    await hass.services.async_call("input_number", "set_value",
                                   {"entity_id": STEP, "value": 3}, blocking=True)
    release, entered = asyncio.Event(), asyncio.Event()

    async def hold(call):
        if not entered.is_set():
            entered.set()
            await release.wait()
        services.record(call)

    hass.services.async_register("media_player", "volume_set", hold)
    try:
        await press(hass, 2)
        assert entered.is_set()
        assert float(hass.states.get(STEP).state) == 4
        await edge(hass)
        assert hass.states.get("script." + VOLUME).attributes["current"] == 2
        if change == "phone_session":
            await put(hass, SONOS, "playing", PHONE)
        else:
            await put(hass, LG, "on")
    finally:
        release.set()
        await settle_loop(hass)
    assert hass.states.is_state("script." + VOLUME, "off")
    assert hass.states.is_state("script.livingroom_music_fresh_start", "off")
    assert volumes(services) == [0.25]
    assert [c.service for c in services.sonos_calls()] == ["volume_set"]
    assert set(services.sonos_calls()[0].data["entity_id"]) == {SONOS, BEDROOM}
    assert float(hass.states.get(STEP).state) == 4
