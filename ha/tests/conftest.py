import asyncio
from datetime import timedelta
from pathlib import Path
import re
from types import SimpleNamespace

import pytest
from homeassistant.config import merge_packages_config
from homeassistant.core import CoreState, callback
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed_exact,
    async_mock_service,
    mock_restore_cache,
)

pytest_plugins = "pytest_homeassistant_custom_component"

REPO = Path(__file__).resolve().parents[2]
PACKAGES = {
    "livingroom_music": {
        "binary_sensor.presence_sensor_fp2_e863_presence_sensor_1": ("off", "Presence-Sensor-FP2-E863 Presence Sensor 1"),
        "binary_sensor.living_room_main_fp300_couch_occupancy_sensor": ("off", "FP300_Couch Occupancy Sensor"),
        "event.kitchen_button_1": ("2026-10-20T08:00:00.000+00:00", "Music Remote button 1"),
        "event.kitchen_button_2": ("2026-10-20T08:00:00.000+00:00", "Music Remote button 2"),
        "event.kitchen_button_3": ("2026-10-20T08:00:00.000+00:00", "Music Remote button 3"),
        "event.kitchen_button_4": ("2026-10-20T08:00:00.000+00:00", "Music Remote button 4"),
        "media_player.sonos": ("idle", "Living Room One"),
        "media_player.bedroom": ("idle", "Bedroom One"),
        "media_player.lg_webos_tv_oled65c9pla": ("off", "LG webOS TV OLED65C9PLA"),
        "media_player.marantz_cinema_50": ("off", "Marantz Cinema 50"),
        "alarm_control_panel.house_alarm": ("disarmed", "House Alarm"),
    },
}
DOMAINS = {
    "automation", "script", "input_boolean", "input_number",
    "input_select", "timer", "input_datetime", "input_text",
}


@pytest.fixture
def load_package(hass):
    async def load(*names, states=None, omit=(), attrs=None, start=False, restore=None):
        await hass.config.async_set_time_zone("Europe/Amsterdam")
        packages, stubs, texts = {}, {}, []
        for name in names:
            if name not in PACKAGES:
                raise ValueError(f"unknown package: {name}")
            path = REPO / "ha/packages" / f"{name}.yaml"
            if not path.is_file():
                raise FileNotFoundError(f"package file missing: {path}")
            config = load_yaml(str(path))
            if not isinstance(config, dict) or config.keys() - DOMAINS:
                raise ValueError(f"unsupported package top-level keys: {path}")
            stubs.update(PACKAGES[name])
            texts.append("\n".join(
                line for line in path.read_text().splitlines()
                if not line.strip().startswith(("action:", "service:", "- action:", "- service:"))
            ))
            packages[name] = config
        merged = {"homeassistant": {"packages": packages}}

        def merge_error(hass, name, domain, config, message):
            raise ValueError(f"package {name}, {domain}: {message}")

        await merge_packages_config(hass, merged, packages, _log_pkg_error=merge_error)
        package = {domain: config for domain, config in merged.items()
                   if domain != "homeassistant"}
        ids = [item["id"] for item in package.get("automation", [])]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate automation id")
        referenced = set(re.findall(
            r"(?<![.\w])(?:binary_sensor|media_player|alarm_control_panel|switch|notify|sensor|event|light)"
            r"\.[a-z0-9_]+\b", "\n".join(texts)
        ))
        missing = referenced - stubs.keys()
        if missing:
            raise ValueError(f"unstubbed entity: {', '.join(sorted(missing))}")
        states, attrs = states or {}, attrs or {}
        if (states.keys() | set(omit) | attrs.keys()) - stubs.keys():
            raise ValueError("unknown stub override or omission")
        for entity, (initial, friendly_name) in stubs.items():
            if entity not in omit:
                attributes = {"friendly_name": friendly_name}
                attributes.update(attrs.get(entity, {}))
                hass.states.async_set(entity, states.get(entity, initial), attributes)
        if restore is not None:
            mock_restore_cache(hass, restore)
        hass.set_state(CoreState.not_running if start else CoreState.running)
        assert await async_setup_component(hass, "homeassistant", {})
        for domain, config in package.items():
            assert await async_setup_component(hass, domain, {domain: config}), domain
        await hass.async_block_till_done()
        if start:
            await hass.async_start()
            await settle(hass)
        automations = hass.states.async_all("automation")
        for automation in package.get("automation", []):
            identifier = automation["id"]
            assert any(
                state.attributes.get("id") == identifier and state.state == "on"
                for state in automations
            ), f"missing enabled automation: {identifier}"
        return package

    return load


@pytest.fixture
def services(hass, caplog):
    records = []

    @callback
    def record(call):
        data = dict(call.data)
        entity = data.get("entity_id")
        if isinstance(entity, list) and len(entity) == 1:
            data["entity_id"] = entity[0]
        records.append(SimpleNamespace(domain=call.domain, service=call.service, data=data))

    for domain, names in (
        ("media_player", (
            "play_media", "media_play", "media_pause", "media_stop", "shuffle_set",
            "volume_set", "repeat_set", "turn_on", "turn_off", "select_source",
            "media_next_track", "volume_mute", "join", "unjoin",
        )),
        ("sonos", ("snapshot", "restore")),
        ("notify", ("mobile_app_martin_fold", "mobile_app_savannah_s25_ultra")),
    ):
        for name in names:
            hass.services.async_register(domain, name, record)
    forbidden = [async_mock_service(hass, "notify", "mobile_app_pixel_9_pro_xl")]
    observed = SimpleNamespace(
        records=records,
        record=record,
        sonos_calls=lambda: [c for c in records if c.domain in ("media_player", "sonos")],
    )
    yield observed
    assert all(not calls for calls in forbidden), "unexpected retired Pixel push"
    protected = {
        "media_player.lg_webos_tv_oled65c9pla", "media_player.marantz_cinema_50",
        "media_player.mxn10", "alarm_control_panel.house_alarm",
    }
    for call in records:
        entities = call.data.get("entity_id", [])
        if isinstance(entities, str):
            entities = entities.split(",")
        assert not protected.intersection(e.strip() for e in entities)
    errors = [
        record for record in (
            caplog.get_records("setup") + caplog.get_records("call") + caplog.records
        ) if record.levelno >= 40
    ]
    assert not errors, "\n".join(record.getMessage() for record in errors)


@pytest.fixture
async def settled_teardown(hass, services):
    # Drain pending actions before the service and error guards.
    yield
    await settle(hass)


async def settle(hass, rounds=200):
    # ponytail: bounded loop turns; increase rounds for deeper service chains.
    # Draining HA tasks would also wait for frozen-clock delays and lock waits.
    loop = asyncio.get_running_loop()
    for _ in range(rounds):
        future = loop.create_future()
        loop.call_soon(future.set_result, None)
        await future


async def advance(hass, freezer, seconds):
    freezer.tick(timedelta(seconds=seconds))
    # Fire only through the requested instant; the padded helper adds 0.5 s.
    async_fire_time_changed_exact(hass)
    await settle(hass)
