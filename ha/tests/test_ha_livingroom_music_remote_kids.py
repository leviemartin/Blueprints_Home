import asyncio
import gc
from itertools import count

import pytest
from homeassistant.core import State, callback
from homeassistant.exceptions import HomeAssistantError, ServiceNotFound

from conftest import REPO, advance, settle
from test_ha_livingroom_music_core import (
    boot, put, edge, calls, only, fresh, direct,
    FP2, FP300, SONOS, BEDROOM, LG, MARANTZ, ALARM, HANDS, OWNED, PHONE, APP, BLOCKERS,
)

pytestmark = [
    pytest.mark.usefixtures("settled_teardown"),
    pytest.mark.parametrize("expected_lingering_timers", [True]),
]
PREFIX = "livingroom_music_"
STEP = "input_number." + PREFIX + "volume_step"
PRE = "input_number." + PREFIX + "pre_kids_step"
SESSION = "input_number." + PREFIX + "kids_session"
AS = "input_number." + PREFIX + "approval_session"
KIDS = "input_boolean." + PREFIX + "kids"
APPROVED = "input_boolean." + PREFIX + "approved"
SENDING = "input_boolean." + PREFIX + "approval_sending"
DEBTS = ["input_boolean." + PREFIX + "restore_" + s for s in ("sonos", "bedroom")]
RID = "input_text." + PREFIX + "approval_id"
KT, CT, AT, RT = ["timer." + PREFIX + s for s in ("kids", "cooldown", "approval", "restore_retry")]
MARTIN, SAVANNAH = "mobile_app_martin_fold", "mobile_app_savannah_s25_ultra"
PAIR = "spotify:playlist:4IzLPBPewQ4PCOF3qMYgDT"
LAZY = "spotify:playlist:37i9dQZF1DWTc452KG008d"
EVENTS = count(1)


async def volume_direct(hass, **data):
    await hass.services.async_call("script", PREFIX + "volume", data, blocking=True)
    await settle(hass)


async def press(hass, button, kind="short_release", settle_after=True):
    hass.states.async_set(f"event.kitchen_button_{button}",
                          f"2026-10-20T10:00:00.{next(EVENTS):06d}+00:00",
                          {"event_type": kind})
    if settle_after:
        await settle(hass)


def volumes(services):
    return [c.data["volume_level"] for c in services.sonos_calls() if c.service == "volume_set"]


def pushes(services):
    return [c for c in services.records if c.domain == "notify"]


async def answer(hass, action):
    hass.bus.async_fire("mobile_app_notification_action", {"action": action})
    await settle(hass)


@pytest.fixture
def music(hass, boot, services):
    async def load(kids=False, approved=False, pending=False, step=3, **kwargs):
        if kids:
            kwargs.setdefault("states", {FP2: "on", SONOS: "playing"})
            kwargs.setdefault("attrs", {SONOS: APP})
        package = await boot(**kwargs)
        assert hass.states.get("script." + PREFIX + "kids_start") is not None
        if kids:
            await hass.services.async_call("input_number", "set_value",
                                           {"entity_id": STEP, "value": step}, blocking=True)
            await press(hass, 1)
            await put(hass, SONOS, "playing", APP)
            if approved or pending:
                await hass.services.async_call("input_number", "set_value",
                                               {"entity_id": STEP, "value": 4}, blocking=True)
                await press(hass, 2)
                if approved:
                    await answer(hass, "LRM_APPROVE_" + hass.states.get(RID).state)
        return package
    return load


async def test_kids_package_loads(hass, music, services):
    package = await music(extra=[State(RID, "old-request")])
    assert {PREFIX + s for s in ("approval_answer", "kids_end", "volume_restore_retry")} <= {
        a["id"] for a in package["automation"]}
    for name in ("volume_reset", "clear_pushes", "kids_start", "kids_end", "approval_request"):
        assert hass.states.is_state("script." + PREFIX + name, "off")
    assert package["script"][PREFIX + "volume_reset"]["mode"] == "restart"
    assert hass.states.get(STEP).state == "2.0"
    assert all(hass.states.is_state(e, "off") for e in [KIDS, APPROVED, SENDING, *DEBTS])
    assert hass.states.get(RID).state == ""
    assert [hass.states.get(e).attributes["duration"] for e in (KT, CT, AT, RT)] == [
        "0:30:00", "0:30:00", "0:02:00", "0:00:30"]
    assert not calls(services)


async def test_rapid_on(hass, music, services):
    await music(states={FP2: "on", SONOS: "playing"}, attrs={SONOS: APP})
    starts = []
    remove = hass.bus.async_listen("call_service", lambda e: starts.append(e.data)
        if e.data.get("domain") == "timer" and e.data.get("service") == "start" else None)
    await press(hass, 1, settle_after=False)
    await press(hass, 1, settle_after=False)
    await settle(hass)
    remove()
    assert sum(c.service == "play_media" and c.data["media_content_id"] == PAIR
               for c in services.sonos_calls()) == 1
    assert sum(KT in str(e["service_data"]) for e in starts) == 1


async def test_brighten_cap_in_cooldown(hass, music, services):
    await music()
    await hass.services.async_call("timer", "start", {"entity_id": CT}, blocking=True)
    await hass.services.async_call("input_number", "set_value", {"entity_id": STEP, "value": 4}, blocking=True)
    for _ in range(3):
        await press(hass, 2)
    assert not volumes(services) and not pushes(services)


@pytest.mark.parametrize("case", ["kids_approved", "cooldown"])
async def test_dim_always_works(hass, music, services, case):
    await music(kids=True, approved=True)
    if case == "cooldown":
        hass.bus.async_fire("timer.finished", {"entity_id": KT})
        await settle(hass)
    services.records.clear()
    await press(hass, 3)
    assert volumes(services) == ([0.25] if case == "kids_approved" else [0.15])


@pytest.mark.parametrize("kind", ["initial_press", "repeat", "long_press", "long_release", "double_press",
                                   "from_unknown", "from_unavailable", "to_unknown", "to_unavailable"])
async def test_on_non_press_events(hass, music, services, kind):
    await music(states={FP2: "on", SONOS: "playing"})
    if kind.startswith("from_"):
        await put(hass, "event.kitchen_button_1", kind[5:])
        await press(hass, 1)
    elif kind.startswith("to_"):
        await put(hass, "event.kitchen_button_1", kind[3:], {"event_type": "short_release"})
    else:
        await press(hass, 1, kind)
    assert not calls(services) and not pushes(services)


@pytest.mark.parametrize("state", ["unknown", "unavailable", "-1", "6", "2.5"])
async def test_step_invalid_at_on(hass, music, services, state):
    await music(states={FP2: "on", SONOS: "playing"}, attrs={SONOS: APP})
    await put(hass, STEP, state)
    await press(hass, 1)
    assert hass.states.is_state(KIDS, "on") and hass.states.get(PRE).state == "2.0"


async def test_kids_time_from_playing(hass, music, services):
    await music(states={FP2: "on", SONOS: "playing"}, attrs={SONOS: APP})
    session = int(float(hass.states.get(SESSION).state))
    await hass.services.async_call("input_number", "set_value", {"entity_id": STEP, "value": 3}, blocking=True)
    await press(hass, 1)
    assert calls(services) == [
        ("play_media", {"entity_id": SONOS, "media_content_id": PAIR, "media_content_type": "playlist", "enqueue": "replace"}),
        ("shuffle_set", {"entity_id": SONOS, "shuffle": True}),
        ("repeat_set", {"entity_id": SONOS, "repeat": "all"})]
    assert hass.states.is_state(KIDS, "on") and hass.states.is_state(KT, "active")
    assert hass.states.get(PRE).state == "3.0"
    assert int(float(hass.states.get(SESSION).state)) == session + 1


async def test_kids_time_from_silence(hass, music, services):
    await music(states={FP2: "on"})
    await press(hass, 1)
    observed = calls(services)
    assert [n for n, _ in observed] == ["volume_set", "play_media", "shuffle_set", "play_media", "shuffle_set", "repeat_set"]
    assert observed[0][1] == {"entity_id": [SONOS, BEDROOM], "volume_level": 0.15}
    assert observed[1][1] == {"entity_id": SONOS, "media_content_id": LAZY, "media_content_type": "playlist", "enqueue": "replace"}
    assert observed[2][1] == {"entity_id": SONOS, "shuffle": True}
    assert observed[3][1]["media_content_id"] == PAIR
    assert hass.states.get(PRE).state == "2.0"


async def test_kids_time_ends_after_30_min(hass, music, services, freezer):
    await music(kids=True)
    services.records.clear()
    await advance(hass, freezer, 1799)
    assert not calls(services)
    await advance(hass, freezer, 1)
    assert volumes(services) == [0.20, 0.20]
    assert {c.data["entity_id"] for c in services.sonos_calls()[:2]} == {SONOS, BEDROOM}
    assert calls(services)[2:] == [
        ("play_media", {"entity_id": SONOS, "media_content_id": LAZY, "media_content_type": "playlist", "enqueue": "replace"}),
        ("shuffle_set", {"entity_id": SONOS, "shuffle": True})]
    assert all(hass.states.is_state(e, "off") for e in [KIDS, APPROVED, OWNED, *DEBTS])
    assert hass.states.is_state(CT, "active") and hass.states.get(STEP).state == "3.0"


@pytest.mark.parametrize("case", ["timer_empty_room", "restart_unoccupied"])
async def test_kids_end_unoccupied(hass, music, services, freezer, case):
    if case == "restart_unoccupied":
        await music(start=True, extra=[State(KIDS, "on"), State(PRE, "3")],
                    states={SONOS: "playing"}, attrs={SONOS: APP})
    else:
        await music(kids=True)
        await advance(hass, freezer, 1799)
        await put(hass, FP2, "off")
        services.records.clear()
        await advance(hass, freezer, 1)
    assert sorted(n for n, _ in calls(services)) == ["media_pause", "volume_set", "volume_set"]
    assert hass.states.is_state(OWNED, "off")
    await put(hass, SONOS, "paused", APP)
    services.records.clear()
    await put(hass, FP2, "on")
    fresh(services)


@pytest.mark.parametrize("case", ["timer_end", "lg_on", "empty_room"])
async def test_kids_end_phone_session(hass, music, services, freezer, case):
    await music(kids=True)
    await put(hass, SONOS, "playing", PHONE)
    services.records.clear()
    if case == "timer_end":
        await advance(hass, freezer, 1800)
    elif case == "lg_on":
        await put(hass, LG, "on")
    else:
        await put(hass, FP2, "off")
        await advance(hass, freezer, 900)
    assert volumes(services) == [0.20, 0.20]
    assert sum(n == "media_pause" for n, _ in calls(services)) == (case != "timer_end")
    assert not any(n == "play_media" for n, _ in calls(services))
    assert hass.states.is_state(OWNED, "off")


async def test_kids_end_app_paused(hass, music, services, freezer):
    await music(kids=True)
    await put(hass, SONOS, "paused", APP)
    services.records.clear()
    await advance(hass, freezer, 1800)
    assert [n for n, _ in calls(services)] == ["volume_set", "volume_set"]


async def test_on_ignored_in_kids_and_cooldown(hass, music, services, freezer):
    await music(kids=True)
    services.records.clear()
    await press(hass, 1)
    assert not calls(services)
    await advance(hass, freezer, 1800)
    services.records.clear()
    await advance(hass, freezer, 1799)
    await press(hass, 1)
    assert not calls(services)
    await advance(hass, freezer, 1)
    await press(hass, 1)
    assert hass.states.is_state(KIDS, "on")
    assert calls(services)[0][1]["media_content_id"] == PAIR


@pytest.mark.parametrize("blocker", [*BLOCKERS, "quiet", "hands", "empty_room", "phone_session"])
async def test_on_blocked(hass, music, services, blocker):
    states = {FP2: "on", SONOS: "playing"}
    if isinstance(blocker, tuple):
        states.update([blocker])
    if blocker == "empty_room":
        states[FP2] = "off"
    await music(states=states, attrs={SONOS: PHONE if blocker == "phone_session" else APP},
                hands=blocker == "hands", time="23:00:00.5" if blocker == "quiet" else "12:00:00.5")
    await press(hass, 1)
    assert not calls(services) and hass.states.is_state(KIDS, "off")


@pytest.mark.parametrize("case", ["empty", "lg", "marantz", "armed_away", "armed_night", "arming", "pending", "triggered", "quiet"])
async def test_kids_cut_short(hass, music, services, freezer, case):
    await music(kids=True, approved=True, time="21:59:59.5" if case == "quiet" else "12:00:00.5")
    services.records.clear()
    if case == "quiet":
        await advance(hass, freezer, 0.5)
    elif case == "empty":
        await put(hass, FP2, "off")
        await advance(hass, freezer, 900)
    else:
        await put(hass, {"lg": LG, "marantz": MARANTZ}.get(case, ALARM),
                  "on" if case in ("lg", "marantz") else case)
    assert sorted(n for n, _ in calls(services)) == ["media_pause", "volume_set", "volume_set"]
    assert volumes(services) == [0.20, 0.20]
    assert all(hass.states.is_state(e, "off") for e in [KIDS, APPROVED, OWNED])
    assert hass.states.is_state(CT, "active")
    if case == "lg":
        await put(hass, SONOS, "paused", APP)
        services.records.clear()
        await put(hass, LG, "off")
        fresh(services)


async def test_kids_end_hands_off(hass, music, services):
    await music(kids=True, approved=True)
    services.records.clear()
    await put(hass, HANDS, "on")
    assert [n for n, _ in calls(services)] == ["volume_set", "volume_set"]
    assert volumes(services) == [0.20, 0.20]
    assert hass.states.is_state(KIDS, "off") and hass.states.is_state(APPROVED, "off")
    assert hass.states.is_state(CT, "active")


async def test_kids_end_pause_fails(hass, music, services, caplog):
    await music(kids=True, pending=True)
    await put(hass, APPROVED, "on")
    await volume_direct(hass, step=5, session=hass.states.get(SESSION).state)
    services.records.clear()
    @callback
    def fail(call):
        services.record(call)
        raise HomeAssistantError("pause failed")
    hass.services.async_register("media_player", "media_pause", fail)
    await put(hass, LG, "on")
    assert {c.service for c in pushes(services) if c.data["message"] == "clear_notification"} == {MARTIN, SAVANNAH}
    assert all(hass.states.is_state(e, "off") for e in [KIDS, APPROVED])
    assert hass.states.is_state(AT, "idle") and hass.states.is_state(CT, "active")
    assert volumes(services) == [0.20, 0.20]
    assert any(r.levelno >= 40 for r in caplog.records)
    caplog.clear()


@pytest.mark.parametrize("case", ["bedroom_unavailable_then_back", "bedroom_raises", "restart_with_debt", "never_gives_up"])
async def test_volume_restore_retry(hass, music, services, freezer, caplog, case):
    if case == "restart_with_debt":
        await music(start=True, extra=[State(e, "on") for e in DEBTS] + [State(PRE, "3")])
        assert volumes(services) == [0.20, 0.20]
        assert hass.states.get(STEP).state == "2.0"
        assert all(hass.states.is_state(e, "off") for e in DEBTS)
        return
    await music(kids=True, approved=True)
    @callback
    def fail(call):
        services.record(call)
        if call.data.get("entity_id") in (BEDROOM, [BEDROOM]):
            raise HomeAssistantError("bedroom reset failed")
    if case == "bedroom_unavailable_then_back":
        await put(hass, BEDROOM, "unavailable")
    else:
        hass.services.async_register("media_player", "volume_set", fail)
    services.records.clear()
    await advance(hass, freezer, 1800)
    assert hass.states.is_state(DEBTS[0], "off") and hass.states.is_state(DEBTS[1], "on")
    assert volumes(services)[0] == 0.20
    if case == "bedroom_unavailable_then_back":
        assert volumes(services) == [0.20]
        services.records.clear()
        await put(hass, BEDROOM, "idle")
    else:
        assert any(r.levelno >= 40 for r in caplog.records)
        caplog.clear()
        if case == "never_gives_up":
            for seconds in [30] * 12 + [29, 1, 30, 30]:
                services.records.clear()
                await advance(hass, freezer, seconds)
                assert volumes(services) == ([] if seconds == 29 else [0.20])
                assert all(c.data["entity_id"] == BEDROOM for c in services.sonos_calls())
                assert hass.states.is_state(RT, "active") and hass.states.is_state(DEBTS[1], "on")
                assert hass.states.get(STEP).state == "3.0"
                if seconds != 29:
                    assert any(r.levelno >= 40 for r in caplog.records)
                    caplog.clear()
        hass.services.async_register("media_player", "volume_set", services.record)
        services.records.clear()
        await advance(hass, freezer, 30)
    assert volumes(services) == [0.20]
    assert all(hass.states.is_state(e, "off") for e in DEBTS)
    assert hass.states.is_state(RT, "idle")
    services.records.clear()
    await advance(hass, freezer, 60)
    assert not calls(services)


async def test_off_skips_in_kids(hass, music, services):
    await music(kids=True)
    services.records.clear()
    await press(hass, 4)
    only(services, "media_next_track")


async def test_hands_off_ignores_on(hass, music, services):
    await music(hands=True)
    await press(hass, 1)
    assert not calls(services) and not pushes(services)


async def test_approval_push(hass, music, services):
    await music(kids=True, step=4)
    services.records.clear()
    @callback
    def record(call):
        if "actions" in call.data.get("data", {}):
            assert hass.states.is_state(AT, "active")
            assert hass.states.get(RID).state
            assert hass.states.get(AS).state == hass.states.get(SESSION).state
        services.record(call)
    hass.services.async_register("notify", MARTIN, record)
    await press(hass, 2)
    rid = hass.states.get(RID).state
    assert [c.service for c in pushes(services)] == [MARTIN, SAVANNAH]
    for c in pushes(services):
        assert c.data["data"] == {"tag": "livingroom_music_approval", "actions": [
            {"action": "LRM_APPROVE_" + rid, "title": "Approve"},
            {"action": "LRM_DENY_" + rid, "title": "Deny"}]}
    await press(hass, 2)
    assert len(pushes(services)) == 2 and not volumes(services)


@pytest.mark.parametrize("case", ["at_step_4", "after_dim"])
async def test_approve_gives_030(hass, music, services, case):
    await music(kids=True, step=4, pending=True)
    rid = hass.states.get(RID).state
    if case == "after_dim":
        await press(hass, 3)
    services.records.clear()
    await answer(hass, "LRM_APPROVE_" + rid)
    assert volumes(services) == ([0.30] if case == "at_step_4" else [])
    assert len(pushes(services)) == 2 and all(c.data["message"] == "clear_notification" for c in pushes(services))
    assert hass.states.is_state(APPROVED, "on")
    services.records.clear()
    if case == "at_step_4":
        await press(hass, 3)
    else:
        await press(hass, 2)
    await press(hass, 2)
    assert volumes(services) == [0.25, 0.30] and not pushes(services)
    assert all(set(c.data["entity_id"]) == {SONOS, BEDROOM} for c in services.sonos_calls())


async def test_deny(hass, music, services):
    await music(kids=True, step=4, pending=True)
    rid = hass.states.get(RID).state
    services.records.clear()
    await answer(hass, "LRM_DENY_" + rid)
    assert not volumes(services) and len(pushes(services)) == 2
    assert hass.states.is_state(APPROVED, "off")
    await press(hass, 2)
    assert hass.states.get(RID).state not in ("", rid)
    new_id = hass.states.get(RID).state
    assert {c.service for c in pushes(services)
            if any(a["action"] == "LRM_APPROVE_" + new_id
                   for a in c.data.get("data", {}).get("actions", []))} == {MARTIN, SAVANNAH}


async def test_timeout_is_deny(hass, music, services, freezer):
    await music(kids=True, step=4, pending=True)
    rid = hass.states.get(RID).state
    services.records.clear()
    await advance(hass, freezer, 119)
    assert hass.states.is_state(AT, "active") and not pushes(services)
    await advance(hass, freezer, 1)
    assert hass.states.get(RID).state == "" and len(pushes(services)) == 2
    await answer(hass, "LRM_APPROVE_" + rid)
    assert not volumes(services)
    await press(hass, 2)
    assert hass.states.get(RID).state not in ("", rid)
    new_id = hass.states.get(RID).state
    assert {c.service for c in pushes(services)
            if any(a["action"] == "LRM_APPROVE_" + new_id
                   for a in c.data.get("data", {}).get("actions", []))} == {MARTIN, SAVANNAH}


@pytest.mark.parametrize("case", ["bogus", "previous_request", "wrong_prefix", "empty_id"])
async def test_stale_or_unknown_id(hass, music, services, case):
    await music(kids=True, step=4, pending=True)
    old = hass.states.get(RID).state
    if case == "previous_request":
        await answer(hass, "LRM_DENY_" + old)
        await press(hass, 2)
    rid = hass.states.get(RID).state
    services.records.clear()
    await answer(hass, {"bogus": "LRM_APPROVE_unknown", "previous_request": "LRM_APPROVE_" + old,
                        "wrong_prefix": "APPROVE_" + rid, "empty_id": "LRM_APPROVE_"}[case])
    assert hass.states.get(RID).state == rid and hass.states.is_state(AT, "active")
    assert not calls(services) and not pushes(services)


@pytest.mark.parametrize("case", ["approve_then_deny", "deny_then_approve", "approve_twice"])
async def test_first_answer_wins(hass, music, services, case):
    await music(kids=True, step=4, pending=True)
    rid = hass.states.get(RID).state
    services.records.clear()
    for action in {"approve_then_deny": ["APPROVE", "DENY"], "deny_then_approve": ["DENY", "APPROVE"],
                   "approve_twice": ["APPROVE", "APPROVE"]}[case]:
        hass.bus.async_fire("mobile_app_notification_action", {"action": "LRM_" + action + "_" + rid})
    await settle(hass)
    assert volumes(services) == ([] if case == "deny_then_approve" else [0.30])
    assert len(pushes(services)) == 2


@pytest.mark.parametrize("decision", ["deny", "approve"])
async def test_answer_during_delivery(hass, music, services, decision):
    await music(kids=True, step=4)
    @callback
    def deliver(call):
        services.record(call)
        if "actions" in call.data.get("data", {}):
            hass.bus.async_fire("mobile_app_notification_action",
                               {"action": "LRM_" + decision.upper() + "_" + hass.states.get(RID).state})
    hass.services.async_register("notify", MARTIN, deliver)
    services.records.clear()
    await press(hass, 2)
    assert not volumes(services)
    if decision == "deny":
        assert hass.states.is_state(AT, "idle")
        last_push = max(i for i, c in enumerate(pushes(services)) if "actions" in c.data.get("data", {}))
        assert {c.service for c in pushes(services)[last_push + 1:] if c.data["message"] == "clear_notification"} == {MARTIN, SAVANNAH}
    else:
        assert hass.states.is_state(AT, "active")
        await answer(hass, "LRM_APPROVE_" + hass.states.get(RID).state)
        assert volumes(services) == [0.30]


@pytest.mark.parametrize("case", ["late_approve", "stale_grant"])
async def test_late_grant_after_kids_end(hass, music, services, freezer, case):
    await music(kids=True, step=4, pending=True)
    rid, old_session = hass.states.get(RID).state, hass.states.get(AS).state
    await advance(hass, freezer, 1800)
    services.records.clear()
    if case == "late_approve":
        await answer(hass, "LRM_APPROVE_" + rid)
        assert hass.states.is_state(APPROVED, "off")
    else:
        await put(hass, APPROVED, "on")
        await put(hass, AS, old_session)
        await advance(hass, freezer, 1800)
        await press(hass, 1)
        await press(hass, 2)
        assert any("actions" in c.data.get("data", {}) for c in pushes(services))
    assert 0.30 not in volumes(services)


@pytest.mark.parametrize("case", ["martin_missing", "martin_raises", "savannah_missing", "savannah_raises"])
async def test_notify_failure(hass, music, services, caplog, case):
    await music(kids=True, step=4)
    name = MARTIN if case.startswith("martin") else SAVANNAH
    @callback
    def fail(call):
        services.record(call)
        if "actions" in call.data.get("data", {}):
            raise HomeAssistantError("delivery failed")
    if case.endswith("missing"):
        hass.services.async_remove("notify", name)
    else:
        hass.services.async_register("notify", name, fail)
    services.records.clear()
    loop = asyncio.get_running_loop()
    original_handler = loop.get_exception_handler()
    caught = []
    def expected_exception(loop, context):
        exc = context.get("exception")
        if ((case.endswith("missing") and isinstance(exc, ServiceNotFound)
             and exc.domain == "notify" and exc.service == name)
                or (case.endswith("raises") and type(exc) is HomeAssistantError
                    and str(exc) == "delivery failed")):
            caught.append(exc)
        elif original_handler is not None:
            original_handler(loop, context)
        else:
            loop.default_exception_handler(context)
    loop.set_exception_handler(expected_exception)
    try:
        await press(hass, 2)
        assert hass.states.is_state(SENDING, "off") and hass.states.is_state(AT, "idle")
        assert hass.states.get(RID).state == "" and not volumes(services)
        for c in list(pushes(services)):
            if "actions" in c.data.get("data", {}):
                await answer(hass, c.data["data"]["actions"][0]["action"])
        assert not volumes(services)
        if case.startswith("savannah"):
            assert any(c.service == MARTIN and c.data["message"] == "clear_notification" for c in pushes(services))
        assert any(r.levelno >= 40 and r.name.startswith("homeassistant.components.script")
                   and (name in r.getMessage() if case.endswith("missing") else "delivery failed" in r.getMessage())
                   for r in caplog.records)
        caplog.clear()
        gc.collect()
        await settle(hass)
        assert caught
    finally:
        loop.set_exception_handler(original_handler)


async def test_pending_cleared_at_kids_end(hass, music, services):
    await music(kids=True, step=4, pending=True)
    rid = hass.states.get(RID).state
    services.records.clear()
    hass.bus.async_fire("timer.finished", {"entity_id": KT})
    await settle(hass)
    assert {c.service for c in pushes(services) if c.data["message"] == "clear_notification"} == {MARTIN, SAVANNAH}
    await answer(hass, "LRM_APPROVE_" + rid)
    assert 0.30 not in volumes(services)


@pytest.mark.parametrize("case", ["outside_kids", "kids_no_answer", "after_deny", "after_timeout", "cooldown",
                                   "approved_forced_outside_kids", "approved_forced_timer_idle", "approved_forced_other_session"])
async def test_no_030_without_approval(hass, music, services, freezer, case):
    kids = case not in ("outside_kids", "approved_forced_outside_kids")
    await music(kids=kids, step=4, pending=case in ("after_deny", "after_timeout"))
    if case == "after_deny":
        await answer(hass, "LRM_DENY_" + hass.states.get(RID).state)
    if case == "after_timeout":
        await advance(hass, freezer, 120)
    if case == "cooldown":
        await advance(hass, freezer, 1800)
    if case.startswith("approved_forced"):
        await put(hass, APPROVED, "on")
        await put(hass, AS, "-1" if case.endswith("other_session") else hass.states.get(SESSION).state)
        if case.endswith("timer_idle"):
            await hass.services.async_call("timer", "cancel", {"entity_id": KT}, blocking=True)
    services.records.clear()
    for _ in range(8):
        await press(hass, 2)
    assert all(v <= 0.25 for v in volumes(services))
    services.records.clear()
    await put(hass, STEP, "5")
    await volume_direct(hass)
    assert not volumes(services)


@pytest.mark.parametrize("speaker", [SONOS, BEDROOM])
async def test_on_speakers_unavailable(hass, music, services, speaker):
    await music(states={FP2: "on", SONOS: "playing", speaker: "unavailable"})
    await press(hass, 1)
    assert not calls(services) and hass.states.get(STEP).state == "2.0"
    assert hass.states.is_state(KIDS, "off")


async def test_restart_ends_kids_time(hass, music, services):
    await music(start=True, states={FP2: "on", SONOS: "playing"}, attrs={SONOS: APP},
                extra=[State(KIDS, "on"), State(PRE, "3"), State(APPROVED, "on"), State(SENDING, "on"), State(RID, "old-request")])
    assert volumes(services)[-2:] == [0.20, 0.20]
    assert [n for n, _ in calls(services) if n != "volume_set"] == ["play_media", "shuffle_set"]
    assert ("play_media", {"entity_id": SONOS, "media_content_id": LAZY,
                           "media_content_type": "playlist", "enqueue": "replace"}) in calls(services)
    assert hass.states.get(STEP).state == "3.0" and hass.states.get(RID).state == ""
    assert hass.states.is_state(KIDS, "off") and hass.states.is_state(APPROVED, "off")
    assert hass.states.is_state(CT, "active")
    services.records.clear()
    await answer(hass, "LRM_APPROVE_old-request")
    assert not calls(services)


async def test_restart_one_speaker_absent(hass, music, services):
    await music(start=True, states={FP2: "on", SONOS: "playing", BEDROOM: "unavailable"}, attrs={SONOS: APP},
                extra=[State(KIDS, "on"), State(PRE, "3"), State(APPROVED, "on"), State(RID, "old-request")])
    assert volumes(services) == [0.20] and len(calls(services)) == 1
    assert hass.states.is_state(KIDS, "off") and hass.states.is_state(DEBTS[1], "on")
    services.records.clear()
    await put(hass, BEDROOM, "idle")
    assert volumes(services) == [0.20] and hass.states.is_state(DEBTS[1], "off")


async def test_start_waits_for_kids(hass, music, services):
    await music(kids=True)
    await put(hass, SONOS, "paused", APP)
    await put(hass, LG, "on")
    services.records.clear()
    await edge(hass)
    await put(hass, LG, "off")
    assert not calls(services)


async def test_reset_after_delayed_030(hass, music, services, freezer):
    await music(kids=True, approved=True)
    await press(hass, 3)
    release = asyncio.Event()
    async def hold(call):
        services.record(call)
        if call.data["volume_level"] == 0.30:
            await release.wait()
    hass.services.async_register("media_player", "volume_set", hold)
    services.records.clear()
    try:
        await press(hass, 2)
        assert volumes(services) == [0.30]
        await advance(hass, freezer, 1800)
    finally:
        release.set()
        await settle(hass)
    assert volumes(services) == [0.30, 0.20, 0.20]


@pytest.mark.parametrize("case", ["pause_missing", "play_media_stalled", "delayed_015"])
async def test_kids_end_playback_fails(hass, music, services, freezer, caplog, case):
    await music(kids=True, approved=case != "delayed_015", step=0 if case == "delayed_015" else 3)
    release = asyncio.Event()
    async def hold(call):
        if case == "delayed_015":
            if call.data["volume_level"] == 0.15:
                await release.wait()
            services.record(call)
        else:
            services.record(call)
            await release.wait()
    if case == "pause_missing":
        hass.services.async_remove("media_player", "media_pause")
    elif case == "play_media_stalled":
        hass.services.async_register("media_player", "play_media", hold)
    else:
        for _ in range(3):
            await press(hass, 2)
        hass.services.async_register("media_player", "volume_set", hold)
    services.records.clear()
    try:
        if case == "delayed_015":
            await press(hass, 3)
        if case == "pause_missing":
            await put(hass, LG, "on")
        else:
            await advance(hass, freezer, 1800)
        if case != "delayed_015":
            assert volumes(services) == [0.20, 0.20]
            assert all(hass.states.is_state(e, "off") for e in DEBTS)
            assert hass.states.is_state(RT, "idle")
            before = calls(services)
            await advance(hass, freezer, 30)
            assert calls(services) == before
    finally:
        release.set()
        await settle(hass)
    assert volumes(services) == ([0.15, 0.05, 0.05] if case == "delayed_015" else [0.20, 0.20])
    if case == "play_media_stalled":
        assert calls(services)[-1] == ("shuffle_set", {"entity_id": SONOS, "shuffle": True})
    if case == "pause_missing":
        assert any(r.levelno >= 40 for r in caplog.records)
        caplog.clear()
    assert all(hass.states.is_state(e, "off") for e in DEBTS) and hass.states.is_state(RT, "idle")
    before = volumes(services)
    await advance(hass, freezer, 60)
    assert volumes(services) == before


async def test_retry_keeps_later_dims(hass, music, services, freezer, caplog):
    await music(kids=True, approved=True)
    @callback
    def fail(call):
        services.record(call)
        if call.data.get("entity_id") in (BEDROOM, [BEDROOM]):
            raise HomeAssistantError("bedroom reset failed")
    hass.services.async_register("media_player", "volume_set", fail)
    await advance(hass, freezer, 1800)
    assert hass.states.is_state(DEBTS[1], "on")
    assert ("volume_set", {"entity_id": SONOS, "volume_level": 0.20}) in calls(services)
    assert hass.states.is_state(DEBTS[0], "off")
    assert any(r.levelno >= 40 for r in caplog.records)
    caplog.clear()
    hass.services.async_register("media_player", "volume_set", services.record)
    services.records.clear()
    await press(hass, 3)
    assert all(hass.states.is_state(e, "off") for e in DEBTS) and hass.states.is_state(RT, "idle")
    await press(hass, 3)
    assert volumes(services) == [0.15, 0.10]
    services.records.clear()
    await advance(hass, freezer, 30)
    await advance(hass, freezer, 60)
    assert not calls(services) and hass.states.get(STEP).state == "1.0"


@pytest.mark.parametrize("case", ["released", "stuck", "dim_not_held"])
async def test_kids_start_waits_for_fresh_start(hass, music, services, freezer, case):
    await music()
    release = asyncio.Event()
    async def hold(call):
        services.record(call)
        await release.wait()
    hass.services.async_register("media_player", "play_media", hold)
    try:
        await edge(hass)
        await press(hass, 1)
        assert hass.states.is_state(KIDS, "off")
        assert [c.data["media_content_id"] for c in services.sonos_calls() if c.service == "play_media"] == [LAZY]
        if case == "stuck":
            await advance(hass, freezer, 31)
            assert hass.states.is_state(KIDS, "off")
        elif case == "dim_not_held":
            await press(hass, 3)
            assert volumes(services) == [0.15, 0.10] and hass.states.get(STEP).state == "1.0"
        else:
            await put(hass, SONOS, "playing", APP)
    finally:
        release.set()
        await settle(hass)
    assert volumes(services) == ([0.15, 0.10] if case == "dim_not_held" else [0.15])
    plays = [c.data["media_content_id"] for c in services.sonos_calls() if c.service == "play_media"]
    assert plays == ([LAZY] if case == "stuck" else [LAZY, PAIR])
    if case != "stuck":
        assert hass.states.is_state(KIDS, "on")
        assert hass.states.get(PRE).state == ("1.0" if case == "dim_not_held" else "2.0")
        assert [n for n, _ in calls(services)[-3:]] == ["play_media", "shuffle_set", "repeat_set"]


async def test_kids_end_cleanup_debt_first(hass, music, services, freezer):
    await music(kids=True, approved=True)
    services.records.clear()
    snapshots = []
    @callback
    def changed(event):
        if not volumes(services):
            snapshots.append([hass.states.get(e).state for e in [KIDS, *DEBTS, RT]])
    remove = hass.bus.async_listen("state_changed", changed)
    await advance(hass, freezer, 1800)
    remove()
    assert snapshots
    assert all(k == "on" or (a == b == "on" and t == "active") for k, a, b, t in snapshots)
    assert any(k == "on" and a == b == "on" for k, a, b, _ in snapshots)


@pytest.mark.parametrize("kids", ["on", "off"])
async def test_restart_mid_cleanup(hass, music, services, kids):
    await music(start=True, states={SONOS: "paused"},
                extra=[State(KIDS, kids), State(PRE, "3"), State(STEP, "5"), State(APPROVED, "on"),
                       *[State(e, "on") for e in DEBTS]])
    assert volumes(services)[-2:] == [0.20, 0.20] and max(volumes(services)) <= 0.25
    assert all(hass.states.is_state(e, "off") for e in [KIDS, *DEBTS])
    assert hass.states.is_state(RT, "idle")


@pytest.mark.parametrize("case", ["press_first", "end_first", "queued_behind"])
async def test_press_races_kids_end(hass, music, services, freezer, case):
    pre = 1 if case == "queued_behind" else 0
    await music(kids=True, approved=True, step=pre)
    release = asyncio.Event()
    held = False
    async def hold(call):
        nonlocal held
        if call.data["volume_level"] == 0.25 and not held:
            held = True
            await release.wait()
        services.record(call)
    services.records.clear()
    try:
        if case == "queued_behind":
            hass.services.async_register("media_player", "volume_set", hold)
            await press(hass, 3, settle_after=False)
            await press(hass, 3, settle_after=False)
            await settle(hass)
            assert held
            await advance(hass, freezer, 1800)
        else:
            if case == "press_first":
                await press(hass, 3, settle_after=False)
            hass.bus.async_fire("timer.finished", {"entity_id": KT})
            if case == "end_first":
                await press(hass, 3, settle_after=False)
            await settle(hass)
    finally:
        release.set()
        await settle(hass)
    level = 0.10 if pre else 0.05
    assert volumes(services)[-2:] == [level, level] and max(volumes(services)) <= 0.25
    before = volumes(services)
    await advance(hass, freezer, 60)
    assert volumes(services) == before and float(hass.states.get(STEP).state) == pre
    assert all(hass.states.is_state(e, "off") for e in [KIDS, *DEBTS])
    assert hass.states.is_state(RT, "idle")


async def test_reset_stall_recovers(hass, music, services, freezer):
    await music(kids=True, approved=True)
    release = asyncio.Event()
    async def hold(call):
        services.record(call)
        if call.data.get("entity_id") in (BEDROOM, [BEDROOM]) and call.data["volume_level"] == 0.20:
            await release.wait()
    hass.services.async_register("media_player", "volume_set", hold)
    services.records.clear()
    try:
        await advance(hass, freezer, 1800)
        assert volumes(services) == [0.20, 0.20]
        assert hass.states.is_state(DEBTS[0], "off") and hass.states.is_state(DEBTS[1], "on")
        for _ in range(3):
            services.records.clear()
            await advance(hass, freezer, 30)
            assert volumes(services) == [0.20]
            assert [c.data["entity_id"] for c in services.sonos_calls() if c.service == "volume_set"] == [BEDROOM]
            assert hass.states.is_state(RT, "active") and hass.states.is_state(DEBTS[1], "on")
            assert hass.states.is_state("script." + PREFIX + "volume", "off")
    finally:
        release.set()
        await settle(hass)
    assert hass.states.is_state(DEBTS[1], "off") and hass.states.is_state(RT, "idle")
    assert hass.states.is_state("script." + PREFIX + "volume_reset", "off")
    services.records.clear()
    await advance(hass, freezer, 60)
    assert not calls(services)


async def test_kids_end_during_step_write(hass, music, services):
    await music(kids=True, pending=True)
    rid = hass.states.get(RID).state
    await press(hass, 3)
    await answer(hass, "LRM_APPROVE_" + rid)
    await press(hass, 2)
    original = hass.services.async_services()["input_number"]["set_value"]
    writes = []
    async def interrupt(call):
        if STEP in call.data.get("entity_id", []):
            if float(call.data["value"]) == 5:
                hass.bus.async_fire("timer.finished", {"entity_id": KT})
                while hass.states.is_state(KIDS, "on"):
                    await settle(hass, 1)
            writes.append(float(call.data["value"]))
        return await original.job.target(call)
    hass.services.async_register("input_number", "set_value", interrupt, schema=original.schema)
    services.records.clear()
    await press(hass, 2)
    assert max(volumes(services)) <= 0.25 and volumes(services)[-2:] == [0.20, 0.20]
    assert writes[-1] == 3 and hass.states.get(STEP).state == "3.0"
    assert all(hass.states.is_state(e, "off") for e in [KIDS, APPROVED, *DEBTS])


@pytest.mark.parametrize("case", ["kids_off", "session_bump", "write_held"])
async def test_press_inside_kids_end_cleanup(hass, music, services, freezer, case):
    await music(kids=True, approved=True, step=1)
    original = hass.services.async_services()["input_number"]["set_value"]
    release, held = asyncio.Event(), asyncio.Event()
    writes, cleared = [], []
    fired = False
    async def record(call):
        if STEP in call.data.get("entity_id", []):
            if case == "write_held" and float(call.data["value"]) == 4:
                held.set()
                await release.wait()
            writes.append(float(call.data["value"]))
        return await original.job.target(call)
    @callback
    def changed(event):
        nonlocal fired
        entity, state = event.data["entity_id"], event.data["new_state"]
        if state is None:
            return
        if entity in DEBTS and state.state == "off":
            cleared.append((entity, list(calls(services))))
        trigger = entity == (SESSION if case == "session_bump" else KIDS)
        if trigger and not fired and (entity == SESSION or state.state == "off"):
            fired = True
            if case == "write_held":
                release.set()
            else:
                hass.states.async_set("event.kitchen_button_3",
                    f"2026-10-20T10:00:00.{next(EVENTS):06d}+00:00", {"event_type": "short_release"})
    hass.services.async_register("input_number", "set_value", record, schema=original.schema)
    services.records.clear()
    remove = hass.bus.async_listen("state_changed", changed)
    try:
        if case == "write_held":
            await press(hass, 3)
            assert held.is_set()
        await advance(hass, freezer, 1800)
    finally:
        release.set()
        await settle(hass)
        remove()
    await advance(hass, freezer, 60)
    assert fired and volumes(services)[-2:] == [0.10, 0.10]
    if case != "write_held":
        assert writes and set(writes) == {1}
    for debt, speaker in zip(DEBTS, (SONOS, BEDROOM)):
        final_reset = max(i for i, (n, d) in enumerate(calls(services))
                          if n == "volume_set" and d == {"entity_id": speaker, "volume_level": 0.10})
        last_clear = [snapshot for e, snapshot in cleared if e == debt][-1]
        assert len(last_clear) > final_reset
    assert hass.states.get(STEP).state == "1.0" and hass.states.is_state(RT, "idle")
    assert all(hass.states.is_state(e, "off") for e in [KIDS, *DEBTS])
    assert max(volumes(services)) <= 0.25


async def test_on_during_kids_end_cleanup(hass, music, services, freezer):
    await music(kids=True, approved=True)
    n = int(float(hass.states.get(SESSION).state))
    fired = False
    @callback
    def changed(event):
        nonlocal fired
        if event.data["entity_id"] == KIDS and event.data["new_state"].state == "off" and not fired:
            fired = True
            hass.states.async_set("event.kitchen_button_1",
                f"2026-10-20T10:00:00.{next(EVENTS):06d}+00:00", {"event_type": "short_release"})
    before = len(services.records)
    remove = hass.bus.async_listen("state_changed", changed)
    await advance(hass, freezer, 1800)
    remove()
    await advance(hass, freezer, 60)
    assert fired and sum(c.service == "play_media" and c.data["media_content_id"] == PAIR
                         for c in services.sonos_calls()) == 1
    assert int(float(hass.states.get(SESSION).state)) == n + 1
    assert hass.states.get(PRE).state == hass.states.get(STEP).state == "3.0"
    assert [c.data["volume_level"] for c in services.records[before:] if c.service == "volume_set"] == [0.20, 0.20]
    assert all(hass.states.is_state(e, "off") for e in [KIDS, *DEBTS])
    assert hass.states.is_state(RT, "idle") and hass.states.is_state(CT, "active")


@pytest.mark.parametrize("blocker", ["lg", "quiet", "empty"])
@pytest.mark.parametrize("timing", ["before_press", "during_step_write"])
async def test_paused_approval_obeys_stop_rules(hass, music, services, freezer, blocker, timing):
    # Cross only the quiet-hours boundary; keep the kids timer from expiring.
    await music(kids=True, approved=True,
                time="21:59:59.5" if blocker == "quiet" else "12:00:00.5")
    await press(hass, 3)
    await put(hass, SONOS, "paused", APP)

    def block():
        if blocker == "quiet":
            freezer.move_to("2026-10-20T22:00:00+02:00")
        else:
            hass.states.async_set(LG if blocker == "lg" else FP2,
                                  "on" if blocker == "lg" else "off")

    if timing == "during_step_write":
        original = hass.services.async_services()["input_number"]["set_value"]

        async def interrupt(call):
            result = await original.job.target(call)
            if STEP in call.data.get("entity_id", []) and float(call.data["value"]) == 5:
                block()
            return result

        hass.services.async_register("input_number", "set_value", interrupt, schema=original.schema)
    else:
        block()
        await settle(hass)
    services.records.clear()
    await press(hass, 2)
    assert not volumes(services)
    assert hass.states.is_state(KIDS, "on") and hass.states.is_state(APPROVED, "on")
    assert hass.states.is_state(KT, "active")
    assert all(hass.states.is_state(e, "off") for e in DEBTS)
    assert hass.states.get(STEP).state == ("4.0" if timing == "before_press" else "5.0")


@pytest.mark.parametrize("path", ["reset", "ladder"])
@pytest.mark.parametrize("speaker", [SONOS, BEDROOM])
async def test_disconnect_during_volume_dispatch(hass, music, services, freezer, path, speaker):
    if path == "reset":
        await music(kids=True, approved=True)
    else:
        await music(extra=[State(e, "on") for e in DEBTS] + [State(PRE, "3")])
        await hass.services.async_call("timer", "start", {"entity_id": RT}, blocking=True)

    @callback
    def disconnect(call):
        entities = call.data.get("entity_id", [])
        if speaker == entities or speaker in entities:
            hass.states.async_set(speaker, "unavailable")
            return
        services.record(call)

    hass.services.async_register("media_player", "volume_set", disconnect)
    services.records.clear()
    if path == "reset":
        await advance(hass, freezer, 1800)
    else:
        await press(hass, 3)
    debt = DEBTS[[SONOS, BEDROOM].index(speaker)]
    assert hass.states.is_state(debt, "on") and hass.states.is_state(RT, "active")
    assert not any(c.service == "volume_set" and c.data["entity_id"] == speaker
                   for c in services.sonos_calls())
    hass.services.async_register("media_player", "volume_set", services.record)
    services.records.clear()
    await put(hass, speaker, "idle")
    resets = services.sonos_calls()
    assert len(resets) == (1 if path == "reset" else 2)
    assert {c.data["entity_id"] for c in resets} == ({speaker} if path == "reset" else {SONOS, BEDROOM})
    assert all(c.service == "volume_set" and c.data["volume_level"] == 0.20 for c in resets)
    assert all(hass.states.is_state(e, "off") for e in DEBTS)
    assert hass.states.is_state(RT, "idle")
