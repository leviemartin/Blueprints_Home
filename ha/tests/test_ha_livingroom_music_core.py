import re

import pytest
from homeassistant.core import State, callback

from conftest import REPO, advance, settle

FP2 = "binary_sensor.presence_sensor_fp2_e863_presence_sensor_1"
FP300 = "binary_sensor.living_room_main_fp300_couch_occupancy_sensor"
SONOS = "media_player.sonos"
BEDROOM = "media_player.bedroom"
LG = "media_player.lg_webos_tv_oled65c9pla"
MARANTZ = "media_player.marantz_cinema_50"
ALARM = "alarm_control_panel.house_alarm"
HANDS = "input_boolean.livingroom_music_hands_off"
OWNED = "input_boolean.livingroom_music_ha_session"
EMPTY = "timer.livingroom_music_empty"
PHONE_TIMER = "timer.livingroom_music_phone"
SCRIPT = "livingroom_music_fresh_start"
PHONE = {"source": "Spotify Connect", "media_content_id": "x-sonos-vli:RINCON_X:2,spotify:track:x"}
APP = {"source": "Queue", "media_content_id": "app-track"}
BLOCKERS = [(LG, "on"), (MARANTZ, "on"), (MARANTZ, "playing"), (MARANTZ, "paused")] + [
    (ALARM, state) for state in ("armed_away", "armed_night", "arming", "pending", "triggered")
]
pytestmark = [
    pytest.mark.usefixtures("settled_teardown"),
    pytest.mark.parametrize("expected_lingering_timers", [True]),
]


@pytest.fixture
def boot(hass, freezer, load_package, services, monkeypatch):
    async def load(time="12:00:00.5", owned=False, hands=False, extra=(), **kwargs):
        # Remove HA's random daily-trigger jitter so exact boundaries are testable.
        monkeypatch.setattr("homeassistant.helpers.event.randint", lambda a, b: 0)
        freezer.move_to(f"2026-10-20T{time}+02:00")
        result = await load_package(
            "livingroom_music",
            restore=[State(OWNED, "on" if owned else "off"),
                     State(HANDS, "on" if hands else "off"), *extra],
            **kwargs,
        )
        await settle(hass)
        return result
    return load


async def put(hass, entity, state, attrs=None):
    hass.states.async_set(entity, state, attrs or {})
    await settle(hass)


async def edge(hass):
    await put(hass, FP2, "off")
    await put(hass, FP2, "on")


def calls(services):
    return [(c.service, c.data) for c in services.sonos_calls()]


def only(services, service):
    assert calls(services) == [(service, {"entity_id": SONOS})]


def fresh(services):
    observed = calls(services)
    assert [name for name, _ in observed] == ["volume_set", "play_media", "shuffle_set"]
    assert set(observed[0][1]["entity_id"]) == {SONOS, BEDROOM}
    assert observed[0][1]["volume_level"] == 0.07
    assert observed[1][1] == {
        "entity_id": SONOS,
        "media_content_id": "spotify:playlist:37i9dQZF1DWTc452KG008d",
        "media_content_type": "playlist", "enqueue": "replace",
    }
    assert observed[2][1] == {"entity_id": SONOS, "shuffle": True}


async def direct(hass):
    await hass.services.async_call("script", SCRIPT, {}, blocking=True)
    await settle(hass)


async def test_package_loads(hass, boot, services):
    package = await boot()
    assert set(package) <= {"automation", "script", "input_boolean", "input_number",
                            "input_select", "timer", "input_datetime", "input_text"}
    assert {a["id"] for a in package["automation"]} == {
        f"livingroom_music_{name}" for name in
        ("start", "pause", "empty_timer", "phone", "hands_off_reset", "quiet_reset", "remote",
         "approval_answer", "kids_end", "volume_restore_retry")
    }
    assert hass.states.get(f"script.{SCRIPT}").state == "off"
    assert hass.states.is_state(HANDS, "off")
    assert hass.states.is_state(OWNED, "off")
    assert hass.states.get(EMPTY).attributes["duration"] == "0:15:00"
    assert hass.states.get(PHONE_TIMER).attributes["duration"] == "0:10:00"
    assert not calls(services)


def test_package_text_rules():
    text = (REPO / "ha/packages/livingroom_music.yaml").read_text()
    levels = [line for line in text.splitlines() if "volume_level" in line]
    assert sorted(line.strip() for line in levels) == sorted([
        'volume_level: "{{ level }}"', *['volume_level: "{{ restore_level }}"'] * 2,
    ])
    assert all(word not in text for word in (
        "pixel_9_pro_xl", "spotcast", "music_assistant", "sonos.snapshot", "sonos.restore",
    ))


@pytest.mark.parametrize("sensor", [FP2, FP300])
async def test_start_either_sensor(hass, boot, services, sensor):
    await boot()
    await put(hass, sensor, "on")
    fresh(services)
    assert hass.states.is_state(OWNED, "off")


async def test_both_sensors_at_once_one_start(hass, boot, services):
    await boot()
    hass.states.async_set(FP2, "on")
    hass.states.async_set(FP300, "on")
    await settle(hass)
    fresh(services)


async def test_one_on_other_unavailable_is_occupied(hass, boot, services, freezer):
    await boot(states={FP300: "unavailable"})
    await put(hass, FP2, "on")
    fresh(services)
    await put(hass, SONOS, "playing")
    services.records.clear()
    await advance(hass, freezer, 960)
    assert not calls(services)


@pytest.mark.parametrize("content", ["ha_started", "app_content", "both_unavailable"])
async def test_empty_room_pauses_and_resumes(hass, boot, services, freezer, content):
    await boot(states={FP2: "on", SONOS: "playing"}, attrs={SONOS: APP})
    if content == "ha_started":
        await put(hass, SONOS, "idle")
        await edge(hass)
        fresh(services)
        await put(hass, SONOS, "playing")
        services.records.clear()
    await put(hass, FP2, "unavailable" if content == "both_unavailable" else "off")
    if content == "both_unavailable":
        await put(hass, FP300, "unavailable")
    await advance(hass, freezer, 899)
    assert not calls(services)
    await advance(hass, freezer, 1)
    only(services, "media_pause")
    assert hass.states.is_state(OWNED, "on")
    await put(hass, SONOS, "paused", APP)
    services.records.clear()
    await put(hass, FP2, "on")
    only(services, "media_play")


async def test_empty_timer_restarts(hass, boot, services, freezer):
    await boot(states={FP2: "on", SONOS: "playing"})
    await put(hass, FP2, "off")
    await advance(hass, freezer, 600)
    await put(hass, FP2, "on")
    assert hass.states.is_state(EMPTY, "idle")
    await put(hass, FP2, "off")
    await advance(hass, freezer, 899)
    assert not calls(services)
    await advance(hass, freezer, 1)
    only(services, "media_pause")


@pytest.mark.parametrize("entity,state", BLOCKERS)
async def test_blocker_pauses_and_resumes(hass, boot, services, entity, state):
    await boot(states={FP2: "on", SONOS: "playing"}, attrs={SONOS: APP})
    await put(hass, entity, state)
    only(services, "media_pause")
    assert hass.states.is_state(OWNED, "on")
    await put(hass, SONOS, "paused", APP)
    services.records.clear()
    await put(hass, entity, "disarmed" if entity == ALARM else "off")
    only(services, "media_play")


@pytest.mark.parametrize("entity,state", BLOCKERS)
async def test_blocker_blocks_start(hass, boot, services, entity, state):
    await boot(states={entity: state})
    await put(hass, FP2, "on")
    assert not calls(services)


@pytest.mark.parametrize("entity,state", [
    (ALARM, "disarmed"), (ALARM, "armed_home"),
    *[(e, s) for e in (LG, MARANTZ) for s in ("off", "standby")],
    *[(e, s) for e in (LG, MARANTZ, ALARM) for s in ("unknown", "unavailable")],
])
async def test_not_blocking(hass, boot, services, entity, state):
    await boot(states={entity: state})
    await put(hass, FP2, "on")
    fresh(services)


@pytest.mark.parametrize("entity", [SONOS, BEDROOM])
@pytest.mark.parametrize("state", ["unknown", "unavailable"])
async def test_speaker_unavailable_no_call(hass, boot, services, entity, state):
    await boot(states={entity: state})
    await put(hass, FP2, "on")
    await put(hass, LG, "on")
    await put(hass, LG, "off")
    assert not calls(services)


async def test_pause_only_needs_coordinator(hass, boot, services):
    await boot(states={BEDROOM: "unavailable", SONOS: "playing", FP2: "on"})
    await put(hass, LG, "on")
    only(services, "media_pause")


@pytest.mark.parametrize("time,starts", [
    ("21:59:59.5", True), ("22:00:00.0", False), ("22:00:00.5", False),
    ("07:29:59.5", False), ("07:30:00.0", True), ("07:30:00.5", True),
])
async def test_quiet_hours_start_boundary(hass, boot, services, time, starts):
    await boot(time=time)
    await put(hass, FP2, "on")
    if starts:
        fresh(services)
    else:
        assert not calls(services)


@pytest.mark.parametrize("case", ["playing", "paused", "hands_off_on"])
async def test_quiet_hours_at_22(hass, boot, services, freezer, case):
    await boot(time="21:59:59.5", owned=True, hands=case == "hands_off_on",
               states={FP2: "on", SONOS: "paused" if case == "paused" else "playing"})
    assert not calls(services)
    await advance(hass, freezer, 0.5)
    if case == "playing":
        only(services, "media_pause")
    else:
        assert not calls(services)
    assert hass.states.is_state(OWNED, "off")
    await put(hass, SONOS, "paused")
    services.records.clear()
    await advance(hass, freezer, 34200.5)
    await edge(hass)
    fresh(services)


@pytest.mark.parametrize("case", [
    "presence", "empty", "lg_on", "lg_off", "alarm", "disarmed",
    "quiet", "speaker_back", "restart", "started",
])
async def test_hands_off_blocks_everything(hass, boot, services, freezer, case):
    states = {FP2: "on", SONOS: "playing"}
    if case == "presence":
        states = {}
    if case == "started":
        states[SONOS] = "idle"
    if case in ("lg_off", "disarmed", "speaker_back", "restart"):
        states[SONOS] = "paused"
    if case == "lg_off":
        states[LG] = "on"
    if case == "disarmed":
        states[ALARM] = "armed_away"
    if case == "speaker_back":
        states[SONOS] = "unavailable"
    time = "12:00:00.5"
    await boot(time="21:59:59.5" if case == "quiet" else time,
               states=states, owned=True, hands=case != "started", start=case == "restart")
    if case == "presence":
        await put(hass, FP2, "on")
    elif case == "empty":
        await put(hass, FP2, "off")
        await advance(hass, freezer, 900)
    elif case in ("lg_on", "lg_off"):
        await put(hass, LG, "on" if case == "lg_on" else "off")
    elif case in ("alarm", "disarmed"):
        await put(hass, ALARM, "armed_away" if case == "alarm" else "disarmed")
    elif case == "quiet":
        await advance(hass, freezer, 0.5)
    elif case == "speaker_back":
        await put(hass, SONOS, "paused")
    elif case == "started":
        @callback
        def start_then_block(call):
            services.record(call)
            hass.states.async_set(HANDS, "on")
            hass.states.async_set(LG, "on")

        hass.services.async_register("media_player", "play_media", start_then_block)
        await direct(hass)
        await put(hass, SONOS, "playing", APP)
        assert [c.service for c in services.sonos_calls()] == ["volume_set", "play_media"]
        return
    assert services.sonos_calls() == []


async def test_hands_off_resets_at_06(hass, boot, freezer):
    await boot(time="05:59:59.5", hands=True)
    await advance(hass, freezer, 0.4)
    assert hass.states.is_state(HANDS, "on")
    await advance(hass, freezer, 0.1)
    assert hass.states.is_state(HANDS, "off")


async def test_phone_session_not_replaced(hass, boot, services):
    await boot(owned=True, states={SONOS: "paused", FP2: "on"})
    await put(hass, SONOS, "playing", PHONE)
    assert hass.states.is_state(OWNED, "off")
    await edge(hass)
    assert not calls(services)
    await put(hass, LG, "on")
    only(services, "media_pause")
    assert hass.states.is_state(OWNED, "off")
    await put(hass, SONOS, "paused", PHONE)
    services.records.clear()
    await put(hass, LG, "off")
    assert not calls(services)


@pytest.mark.parametrize("state,attrs", [("paused", PHONE), ("idle", PHONE), ("idle", {})])
async def test_phone_session_ends_after_10_min(hass, boot, services, freezer, state, attrs):
    await boot(states={SONOS: "playing", FP2: "on"}, attrs={SONOS: PHONE})
    await put(hass, SONOS, state, attrs)
    assert hass.states.is_state(PHONE_TIMER, "active")
    await advance(hass, freezer, 599)
    await edge(hass)
    assert not calls(services)
    await advance(hass, freezer, 1)
    await edge(hass)
    fresh(services)


async def test_spotify_connect_without_vli_is_not_phone(hass, boot, services):
    attrs = {"source": "Spotify Connect", "media_content_id": "x-sonos-spotify:spotify%3atrack%3ax"}
    await boot(states={SONOS: "playing", FP2: "on"}, attrs={SONOS: attrs})
    await put(hass, LG, "on")
    only(services, "media_pause")
    assert hass.states.is_state(OWNED, "on")
    await put(hass, SONOS, "paused", attrs)
    services.records.clear()
    await put(hass, LG, "off")
    only(services, "media_play")


@pytest.mark.parametrize("owned", [True, False])
async def test_restart_occupied_paused_resumes(hass, boot, services, owned):
    await boot(start=True, owned=owned, states={SONOS: "paused", FP2: "on", FP300: "on"},
               attrs={SONOS: APP})
    if owned:
        only(services, "media_play")
    else:
        fresh(services)


@pytest.mark.parametrize("case", ["lg", "quiet", "hands"])
async def test_restart_follows_start_rules(hass, boot, services, case):
    await boot(start=True, owned=True, hands=case == "hands",
               time="23:00:00.5" if case == "quiet" else "12:00:00.5",
               states={SONOS: "paused", FP2: "on", LG: "on" if case == "lg" else "off"})
    assert not calls(services)


@pytest.mark.parametrize("restart", [True, False])
async def test_empty_playback_starts_timer(hass, boot, services, freezer, restart):
    await boot(start=restart, states={SONOS: "playing" if restart else "idle"})
    if not restart:
        await put(hass, SONOS, "playing", APP)
    await advance(hass, freezer, 450)
    await put(hass, SONOS, "paused", APP)
    await put(hass, SONOS, "playing", APP)
    await advance(hass, freezer, 449)
    assert not calls(services)
    await advance(hass, freezer, 1)
    only(services, "media_pause")


@pytest.mark.parametrize("speaker", [SONOS, BEDROOM])
async def test_restart_speakers_come_back(hass, boot, services, speaker):
    await boot(start=True, owned=True,
               states={FP2: "on", FP300: "on", SONOS: "paused", speaker: "unavailable"})
    assert not calls(services)
    await put(hass, speaker, "paused" if speaker == SONOS else "idle")
    only(services, "media_play")


@pytest.mark.parametrize("case", ["hands", "phone_playing", "phone_timer", "lg", "marantz",
                                  "marantz_playing", "marantz_paused", "alarm", "quiet",
                                  "sonos_unavailable", "bedroom_unavailable"])
async def test_fresh_start_script_guards(hass, boot, services, case):
    states = {}
    changes = {
        "phone_playing": (SONOS, "playing"), "phone_timer": (SONOS, "playing"),
        "lg": (LG, "on"), "marantz": (MARANTZ, "on"),
        "marantz_playing": (MARANTZ, "playing"), "marantz_paused": (MARANTZ, "paused"),
        "alarm": (ALARM, "armed_night"), "sonos_unavailable": (SONOS, "unavailable"),
        "bedroom_unavailable": (BEDROOM, "unavailable"),
    }
    if case in changes:
        states.update([changes[case]])
    await boot(hands=case == "hands", time="23:00:00.5" if case == "quiet" else "12:00:00.5",
               states=states, attrs={SONOS: PHONE} if case.startswith("phone") else {})
    if case == "phone_timer":
        await put(hass, SONOS, "paused", PHONE)
        assert hass.states.is_state(PHONE_TIMER, "active")
    await direct(hass)
    assert not calls(services)


@pytest.mark.parametrize("service,change", [
    ("volume_set", "hands"), ("volume_set", "phone"), ("play_media", "phone"),
])
async def test_fresh_start_guard_between_calls(hass, boot, services, service, change):
    await boot()

    @callback
    def interrupt(call):
        services.record(call)
        if change == "hands":
            hass.states.async_set(HANDS, "on")
        else:
            hass.states.async_set(SONOS, "playing", PHONE)

    hass.services.async_register("media_player", service, interrupt)
    await direct(hass)
    assert [c.service for c in services.sonos_calls()] == (
        ["volume_set"] if service == "volume_set" else ["volume_set", "play_media"]
    )


async def test_ha_paused_flag(hass, boot, services, freezer):
    await boot(time="21:59:58.5", owned=True, states={SONOS: "paused", FP2: "on"})
    await put(hass, SONOS, "paused", APP)
    assert hass.states.is_state(OWNED, "on")
    await put(hass, SONOS, "playing", APP)
    assert hass.states.is_state(OWNED, "off")
    await put(hass, SONOS, "playing", {**APP, "media_title": "Next"})
    assert hass.states.is_state(OWNED, "off")
    await put(hass, LG, "on")
    only(services, "media_pause")
    assert hass.states.is_state(OWNED, "on")
    services.records.clear()
    await advance(hass, freezer, 1.5)
    only(services, "media_pause")
    assert hass.states.is_state(OWNED, "off")


async def test_quiet_hours_pause_sets_no_flag(hass, boot, services, freezer):
    await boot(time="23:00:00.5", states={SONOS: "playing", FP2: "on"}, attrs={SONOS: APP})
    await put(hass, FP2, "off")
    await advance(hass, freezer, 900)
    only(services, "media_pause")
    assert hass.states.is_state(OWNED, "off")
    await put(hass, SONOS, "paused", APP)
    services.records.clear()
    await advance(hass, freezer, 29700)
    await put(hass, FP2, "on")
    fresh(services)


async def test_reconnect_only_resumes(hass, boot, services):
    await boot(states={SONOS: "paused", FP2: "on"}, attrs={SONOS: APP})
    await put(hass, BEDROOM, "unavailable")
    await put(hass, BEDROOM, "paused")
    assert not calls(services)


async def test_blocker_during_play_media_pauses(hass, boot, services):
    await boot()

    @callback
    def block(call):
        services.record(call)
        hass.states.async_set(LG, "on")

    hass.services.async_register("media_player", "play_media", block)
    await put(hass, FP2, "on")
    assert [c.service for c in services.sonos_calls()] == ["volume_set", "play_media"]
    services.records.clear()
    await put(hass, SONOS, "playing", APP)
    only(services, "media_pause")
    assert hass.states.is_state(OWNED, "off")


@pytest.mark.parametrize("attrs", [APP, PHONE])
@pytest.mark.parametrize("blocked", [False, True])
async def test_personal_playback_is_not_paused(hass, boot, services, attrs, blocked):
    await boot(time="12:00:00.5" if blocked else "23:00:00.5",
               states={FP2: "on", LG: "on" if blocked else "off"})
    await put(hass, SONOS, "playing", attrs)
    assert not calls(services)


async def test_phone_pause_clearing_attributes_keeps_flag_off(hass, boot, services, freezer):
    await boot(states={SONOS: "playing", FP2: "on"}, attrs={SONOS: PHONE})

    @callback
    def pause(call):
        services.record(call)
        hass.states.async_set(SONOS, "paused", {})

    hass.services.async_register("media_player", "media_pause", pause)
    await put(hass, LG, "on")
    only(services, "media_pause")
    assert hass.states.is_state(OWNED, "off")
    assert hass.states.is_state(PHONE_TIMER, "active")
    services.records.clear()
    await put(hass, LG, "off")
    assert not calls(services)
    await advance(hass, freezer, 600)
    await edge(hass)
    fresh(services)


@pytest.mark.parametrize("entity,state", [(LG, "on"), (ALARM, "arming")])
async def test_blocker_during_resume_pauses(hass, boot, services, freezer, entity, state):
    await boot(owned=True, states={SONOS: "paused", FP2: "on", entity: state},
               attrs={SONOS: APP})

    @callback
    def block(call):
        services.record(call)
        hass.states.async_set(entity, state)

    hass.services.async_register("media_player", "media_play", block)
    await put(hass, entity, "disarmed" if entity == ALARM else "off")
    only(services, "media_play")
    assert hass.states.is_state(SONOS, "paused")
    services.records.clear()
    await advance(hass, freezer, 5)
    await put(hass, SONOS, "playing", APP)
    only(services, "media_pause")
    assert hass.states.is_state(OWNED, "off")
