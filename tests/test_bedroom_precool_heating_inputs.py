"""Acceptance tests for the bedroom_precool.yaml v1.3.0 heating inputs (US-01, US-13)."""
from datetime import datetime

import pytest
import yaml

from test_bedroom_precool_structure import (
    BP_PATH,
    TZ,
    HassLoader,
    _Input,
    _config_validation_template,
    _env,
    _render_chain,
    _reparse,
    _service_steps,
)

NOW = datetime(2026, 11, 10, 18, 0, tzinfo=TZ)
TOGGLE = "input_boolean.heating_season"
SEASON_CHAIN = ["season_entity", "season_state", "heating_season", "season_toggle_invalid"]
# (toggle state, heating_season, season_toggle_invalid)
SEASON_CASES = [
    ("on", True, False),
    ("off", False, False),
    ("unavailable", False, True),
    ("unknown", False, True),
    ("", False, True),
    ("maybe", False, True),
]


@pytest.fixture(scope="module")
def bp():
    return yaml.load(BP_PATH.read_text(), Loader=HassLoader)


def _season(bp, state, toggle=(TOGGLE,)):
    table = {TOGGLE: state}
    ctx = dict(heating_season_toggle=list(toggle), states=lambda e: table.get(e, "unknown"))
    return _render_chain(bp, SEASON_CHAIN, NOW, ctx)


def _creates(bp, notification_id):
    return [
        (conds, step)
        for conds, step in _service_steps(bp.get("action"), [])
        if (step.get("service") or step.get("action")) == "persistent_notification.create"
        and (step.get("data") or {}).get("notification_id") == notification_id
    ]


def _fires(conds, ctx):
    return all(bool(_reparse(_env(NOW).from_string(t).render(**ctx).strip())) for t in conds)


def test_us01_inputs_exist_with_safe_bounds_and_are_bound_at_top_level(bp):
    inputs = bp["blueprint"]["input"]
    top = bp["variables"]
    for key in ("heating_season_toggle", "winter_target", "prewarm_offset", "heating_drive_setpoint", "morning_time"):
        assert key in inputs, key
        assert isinstance(top.get(key), _Input) and top[key].name == key, key
    toggle = inputs["heating_season_toggle"]
    assert toggle["default"] == [] and toggle["selector"]["entity"]["domain"] == "input_boolean"
    winter = inputs["winter_target"]
    assert winter["default"] <= 20 and winter["selector"]["number"]["max"] <= 20
    drive = inputs["heating_drive_setpoint"]
    assert drive["default"] <= 24 and drive["selector"]["number"]["max"] <= 24
    assert inputs["prewarm_offset"]["default"] < inputs["tolerance"]["default"]
    assert inputs["deep_night_check"]["default"] < inputs["morning_time"]["default"] < inputs["wake_time"]["default"]


@pytest.mark.parametrize("state,season,invalid", SEASON_CASES)
def test_us01_season_toggle_resolution(bp, state, season, invalid):
    ctx = _season(bp, state)
    assert ctx["heating_season"] is season
    assert ctx["season_toggle_invalid"] is invalid


def test_us01_empty_toggle_input_acts_as_summer(bp):
    ctx = _season(bp, "on", toggle=())
    assert ctx["heating_season"] is False
    assert ctx["season_toggle_invalid"] is True


def test_us01_invalid_toggle_raises_one_fixed_id_notice(bp):
    found = _creates(bp, "bedroom_precool_season_toggle_invalid")
    assert len(found) == 1
    conds, step = found[0]
    assert "{{" not in step["data"]["notification_id"]
    for state, _, invalid in SEASON_CASES:
        assert _fires(conds, dict(_season(bp, state), enable_notifications=True)) is invalid, state
    assert _fires(conds, dict(_season(bp, "unavailable"), enable_notifications=False)) is False
    assert _fires(conds, dict(_season(bp, "on", toggle=()), enable_notifications=True)) is True


def test_us13_winter_target_is_capped_at_20(bp):
    for stored, expect in ((25, 20), (20.5, 20), (19, 19), (16, 16)):
        ctx = _render_chain(bp, ["winter_target_eff"], NOW, dict(winter_target=stored))
        assert ctx["winter_target_eff"] == pytest.approx(expect)


def test_us13_prewarm_offset_is_used_below_the_tolerance(bp):
    cases = ((2, 1.5, 1.4), (1.5, 1.5, 1.4), (1.0, 1.5, 1.0), (0.5, 0.5, 0.4), (0, 1.5, 0))
    for offset, tolerance, expect in cases:
        given = dict(winter_target=25, prewarm_offset=offset, tolerance=tolerance)
        ctx = _render_chain(bp, ["winter_target_eff", "prewarm_offset_eff", "winter_aim"], NOW, given)
        assert ctx["prewarm_offset_eff"] == pytest.approx(expect)
        assert ctx["winter_aim"] <= 20 + tolerance - 0.1 + 1e-9


@pytest.mark.parametrize(
    "drive,max_temp,step,expect",
    [(30, 30, 0.5, 24.0), (30, 22, 1, 22.0), (23.7, 30, 1, 23.0), (30, 22.5, 1, 22.0), (30, 22.5, 0.5, 22.5), (24, 30, 0.1, 24.0)],
)
def test_us13_heat_drive_setpoint_is_capped_and_rounded_down_to_the_step(bp, drive, max_temp, step, expect):
    given = dict(heating_drive_setpoint=drive, ac_min_temp=16, ac_max_temp=max_temp, ac_temp_step=step)
    ctx = _render_chain(bp, ["heat_cap", "heating_drive_eff"], NOW, given)
    assert ctx["heating_drive_eff"] == pytest.approx(expect)
    assert ctx["heating_drive_eff"] <= min(24, max_temp)


def test_us13_heat_hold_setpoint_follows_the_capped_target(bp):
    for target, max_temp, step, expect in ((25, 30, 0.5, 20.0), (19.5, 30, 1, 19.0), (20, 19, 1, 19.0)):
        given = dict(winter_target=target, ac_min_temp=16, ac_max_temp=max_temp, ac_temp_step=step)
        ctx = _render_chain(bp, ["winter_target_eff", "heat_cap", "heating_hold_eff"], NOW, given)
        assert ctx["heating_hold_eff"] == pytest.approx(expect)


def test_us13_no_heat_setpoint_while_limits_unknown_or_heat_missing(bp):
    base = dict(heating_season=True, ac_limits_known=True, ac_hvac_modes=["off", "cool", "heat"])
    cases = (({}, True), (dict(ac_limits_known=False), False), (dict(ac_hvac_modes=["off", "cool"]), False), (dict(heating_season=False), False))
    for override, allowed in cases:
        ctx = _render_chain(bp, ["heat_supported", "heat_setpoints_allowed"], NOW, dict(base, **override))
        assert ctx["heat_setpoints_allowed"] is allowed, override


def test_us13_unit_without_heat_gets_one_fixed_id_notice(bp):
    found = _creates(bp, "bedroom_precool_heat_unsupported")
    assert len(found) == 1
    conds, step = found[0]
    assert "{{" not in step["data"]["notification_id"]
    base = dict(enable_notifications=True, heating_season=True, ac_unavailable=False)

    def fires(modes, **over):
        ctx = _render_chain(bp, ["heat_supported"], NOW, dict(base, ac_hvac_modes=modes, **over))
        return _fires(conds, ctx)

    assert fires(["off", "cool", "dry"]) is True
    assert fires(["off", "cool", "heat"]) is False
    assert fires(["off", "cool"], heating_season=False) is False
    assert fires(["off", "cool"], ac_unavailable=True) is False


def test_us13_morning_time_order_is_checked_in_winter_only(bp):
    base = dict(drive_setpoint=16, ideal_temp=23, hall_offset=2, bedtime="19:30:00", wake_time="07:15:00",
                deep_night_check="01:00:00", lead_cap_minutes=240, fan_settle_minutes=45)
    template = _env(NOW).from_string(_config_validation_template(bp))
    render = lambda **kw: _reparse(template.render(**{**base, **kw}).strip())
    assert render(heating_season=True, morning_time="05:30:00") is False
    for bad in ("00:30:00", "01:00:00", "07:15:00", "08:00:00"):
        assert render(heating_season=True, morning_time=bad) is True, bad
        assert render(heating_season=False, morning_time=bad) is False, bad
    steps = _service_steps(bp.get("action"), [])
    notice = next(s for _, s in steps if (s.get("data") or {}).get("notification_id") == "bedroom_precool_config_error")
    assert "morning_time" in notice["data"]["message"]
