"""Acceptance tests for the bedroom_precool.yaml v1.3.0 winter manual-run debug dump and its docs (US-15)."""
from datetime import datetime

import pytest
import yaml

from test_bedroom_precool_structure import (
    BP_PATH,
    ROOT,
    TZ,
    HassLoader,
    _env,
    _render_chain,
    _reparse,
    _top_level_steps,
)

NOTICE_ID = "bedroom_precool_debug"

WINTER = dict(
    heating_season=True, season_state="on", phase="PRECOOL", precool_substate="DRIVE",
    winter_target_eff=18, prewarm_offset_eff=0.5, winter_aim=18.5,
    hall_offset=1, ac_min_temp=16, heat_cap=24, ac_temp_step=1,
    coldest_bedroom=16.0, warmest_bedroom=17.0, forecast_low=2.0, heat_stage="DRIVE",
    base_minutes=20, k_indoor=15, heat_delta_in=2.5, k_outdoor=1.0, heat_delta_out=16.5,
    safety_margin_minutes=25, heating_bias=7.0, heat_lead_raw=106, heat_lead=106,
    heat_turn_on_tod="17:44:00", bedtime="19:30:00", wake_time="07:15:00",
    morning_time="06:00:00", weekend_morning_time="07:00:00",
    turn_on_ts=1794500000.0, bedtime_ts=1794508200.0,
)


@pytest.fixture(scope="module")
def bp():
    return yaml.load(BP_PATH.read_text(), Loader=HassLoader)


def at(day, hour=18):
    return datetime(2026, 11, day, hour, tzinfo=TZ)


def _debug_sequence(bp):
    for step in _top_level_steps(bp):
        for branch in (step.get("choose") or []) if isinstance(step, dict) else []:
            seq = branch.get("sequence") or []
            if any((s.get("data") or {}).get("notification_id") == NOTICE_ID for s in seq if isinstance(s, dict)):
                return seq
    raise KeyError(NOTICE_ID)


def _dump(bp, now, **over):
    seq = _debug_sequence(bp)
    ctx = _render_chain(bp, ["heat_hold_sp"], now, dict(WINTER, **over))
    env = _env(now)
    for step in seq:
        for name, template in (step.get("variables") or {}).items():
            ctx[name] = _reparse(env.from_string(template).render(**ctx).strip())
    note = next(s for s in seq if (s.get("data") or {}).get("notification_id") == NOTICE_ID)
    return " ".join(env.from_string(note["data"]["message"]).render(**ctx).split())


def test_us15_manual_run_in_winter_dumps_season_aim_coldest_and_forecast_low(bp):
    text = _dump(bp, at(10))
    assert "**season:** winter (toggle=on)" in text
    assert "**aim:** 18.5°C (18 target + 0.5 offset)" in text
    assert "**Coldest:** 16.0°C" in text
    assert "**forecast_low:** 2.0°C" in text


def test_us15_manual_run_in_winter_dumps_each_lead_term_and_the_heating_bias(bp):
    text = _dump(bp, at(10))
    assert ("**heat lead:** 106 min (raw 106) = base 20 + indoor 15 × 2.5°C + outdoor 1.0 × 16.5°C"
            " + safety 25 + bias 7.0 (no solar term)") in text


def test_us15_manual_run_in_winter_dumps_hold_setpoint_timer_hours_and_planned_start(bp):
    assert "**hold setpoint:** 19.0°C | **timer:** 10 h | **planned start:** 05:30" in _dump(bp, at(10))


def test_us15_timer_hours_use_the_weekend_morning_time_and_never_pass_wake_time(bp):
    assert "**timer:** 11 h | **planned start:** 06:30" in _dump(bp, at(13))
    capped = _dump(bp, at(13), weekend_morning_time="08:30:00")
    assert "**timer:** 11 h | **planned start:** 06:30" in capped


def test_us15_summer_dump_names_the_season_and_omits_the_winter_only_figures(bp):
    text = _dump(bp, at(10), heating_season=False, season_state="off")
    assert "**season:** summer (toggle=off)" in text
    for absent in ("hold setpoint", "planned start", "timer:"):
        assert absent not in text


def test_us15_morning_time_input_explains_the_whole_hour_alignment(bp):
    text = " ".join(bp["blueprint"]["input"]["morning_time"]["description"].split())
    assert "whole number of hours after Bedtime" in text


def test_us15_readme_and_requirements_document_the_v130_winter_heating():
    readme = (ROOT / "README.md").read_text()
    req = (ROOT / "requirements_bedroom_precool.md").read_text()
    assert "Winter Heating (v1.3.0)" in readme and "Morning Time alignment" in readme
    assert "## Winter Heating (v1.3.0)" in req and "**Morning Time alignment:**" in req
    assert "whole number of hours after Bedtime" in readme and "whole number of hours after Bedtime" in req
    assert "planned start" in req
