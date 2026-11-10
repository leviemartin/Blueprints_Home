"""Acceptance tests for the bedroom_precool.yaml v1.3.0 winter fan lists: evening assist, bedtime-lock switch-off, nothing in any other heating stage (US-08)."""
from datetime import datetime, timedelta

import pytest
import yaml

from test_bedroom_precool_structure import (
    BP_PATH,
    KIDS,
    MASTER,
    PIR,
    TZ,
    HassLoader,
    _S,
    _fan_env,
    _fan_service_calls,
    _reparse,
    _var_template,
    _windows,
)

START = datetime(2026, 11, 10, 16, 0, tzinfo=TZ)  # the unit started heating
LOCK = datetime(2026, 11, 10, 19, 29, tzinfo=TZ)
MINUTE = timedelta(minutes=1)


@pytest.fixture(scope="module")
def bp():
    return yaml.load(BP_PATH.read_text(), Loader=HassLoader)


def _list(bp, name, states, now=LOCK, **over):
    ctx = dict(
        heating_season=True, bedroom_fans=[MASTER, KIDS], interlocked_fans=[KIDS], interlock_blocked=False,
        night_fans_tonight=True, in_fan_settle=True, night_fan_percentage=1, lock_ts=LOCK.timestamp(),
        fan_assist_tonight=True, in_fan_assist_window=True, precool_fan_percentage=21, ac_started_ts=START.timestamp(),
        fans_at_wake="off", in_wake_window=True, in_lock_window=False,
    )
    ctx.update(over)
    return _reparse(_fan_env(now, states).from_string(_var_template(bp, name)).render(**ctx).strip())


def _lock_off(bp, *fans, **over):
    opts = dict(in_lock_window=True, in_wake_window=False)
    opts.update(over)
    return _list(bp, "fans_on_at_wake", list(fans), **opts)


def test_us08_summer_lists_are_empty_in_winter_in_every_stage(bp):
    old = START - 60 * MINUTE
    fans = [_S(MASTER, "on", 21, old), _S(KIDS, "off", 21, old)]
    assert _list(bp, "fans_due_night", fans, heating_season=False) == [MASTER, KIDS]
    assert _list(bp, "fans_unset_night", fans, heating_season=False, interlock_blocked=True) == [KIDS]
    assert _list(bp, "fans_on_at_wake", fans, heating_season=False) == [MASTER]
    for name in ("fans_due_night", "fans_unset_night", "fans_on_at_wake"):
        assert _list(bp, name, fans, interlock_blocked=True) == [], name


def test_us08_bedtime_lock_switches_off_only_fans_the_blueprint_started_and_nobody_touched(bp):
    t = START + 2 * MINUTE
    ours = _S(MASTER, "on", 21, last_updated=t + timedelta(seconds=5), last_changed=t)
    kids = _S(KIDS, "on", 21, last_updated=t, last_changed=t)
    assert _lock_off(bp, ours, kids) == [MASTER, KIDS]
    assert _lock_off(bp, ours, kids, interlock_blocked=True) == [MASTER, KIDS]
    hand_speed = _S(MASTER, "on", 40, last_updated=START + 90 * MINUTE, last_changed=t)
    hand_back = _S(MASTER, "on", 21, last_updated=START + 90 * MINUTE, last_changed=t)
    older = _S(MASTER, "on", 21, last_updated=START - 60 * MINUTE, last_changed=START - 60 * MINUTE)
    switched_off = _S(MASTER, "off", 21, last_updated=t, last_changed=t)
    for fan in (hand_speed, hand_back, older, switched_off):
        assert _lock_off(bp, fan) == [], fan.state
    assert _lock_off(bp, ours, kids, fan_assist_tonight=False) == []
    assert _lock_off(bp, ours, kids, in_lock_window=False) == []
    assert _lock_off(bp, ours, kids, heating_season=False) == []


def test_us08_evening_assist_lists_fans_for_the_pre_cool_percentage_only_inside_its_window(bp):
    old = START - 60 * MINUTE
    fans = [_S(MASTER, "off", 1, old), _S(KIDS, "on", 21, old)]
    assert _list(bp, "fans_due_precool", fans, START + 5 * MINUTE) == [MASTER]
    assert _list(bp, "fans_due_precool", fans, START + 5 * MINUTE, in_fan_assist_window=False) == []
    assert _list(bp, "fans_due_precool", fans, START + 5 * MINUTE, fan_assist_tonight=False) == []


def test_us08_assist_window_in_winter_needs_the_unit_heating(bp):
    started = datetime(2026, 9, 9, 17, 0, tzinfo=TZ).timestamp()
    on = dict(phase="PRECOOL", ac_is_running=True, ac_started_ts=started, heating_season=True)
    for hh, mm, key in ((17, 30, "in_fan_assist_window"), (17, 46, "in_fan_assist_grace")):
        assert _windows(bp, hh, mm, **dict(on, current_hvac_mode="heat"))[key] is True, key
        assert _windows(bp, hh, mm, **dict(on, current_hvac_mode="cool"))[key] is False, key
        assert _windows(bp, hh, mm, **dict(on, current_hvac_mode="heat", phase="BEDTIME_LOCK"))[key] is False, key


def test_us08_interlock_cut_follows_the_assist_window_in_winter_and_not_the_night_settle(bp):
    now = datetime(2026, 11, 10, 19, 0, tzinfo=TZ)
    states = [_S(KIDS, "on", last_changed=now - timedelta(seconds=30)), _S(PIR, "on")]
    ctx = dict(
        heating_season=True, bedroom_fans=[MASTER, KIDS], interlocked_fans=[KIDS], fan_interlocks=[PIR],
        night_fans_tonight=True, fan_assist_tonight=True, lock_ts=(now - timedelta(seconds=90)).timestamp(),
        ac_started_ts=(now - timedelta(seconds=50)).timestamp(), in_fan_settle_grace=True, in_fan_assist_grace=False,
    )

    def cut(**over):
        return _reparse(_fan_env(now, states).from_string(_var_template(bp, "fans_unsafe_on")).render(**dict(ctx, **over)).strip())

    assert cut() == []
    assert cut(in_fan_settle_grace=False, in_fan_assist_grace=True) == [KIDS]
    assert cut(heating_season=False) == [KIDS]


def test_us08_fan_calls_are_still_the_four_existing_call_sites_and_never_set_direction(bp):
    calls = _fan_service_calls(bp)
    assert sorted(s["service"] for _, s in calls) == ["fan.turn_off", "fan.turn_off", "fan.turn_on", "fan.turn_on"]
