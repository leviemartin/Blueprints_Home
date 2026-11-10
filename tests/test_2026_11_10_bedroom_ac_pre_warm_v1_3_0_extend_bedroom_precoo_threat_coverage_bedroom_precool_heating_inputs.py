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


def test_us13_extreme_inputs_keep_the_aim_and_every_setpoint_inside_the_caps(bp):
    from datetime import datetime

    from test_bedroom_precool_structure import TZ, _render_chain

    now = datetime(2026, 11, 10, 18, 0, tzinfo=TZ)
    chain = ["winter_target_eff", "prewarm_offset_eff", "winter_aim", "heat_cap", "heating_drive_eff", "heating_hold_eff", "heat_hold_sp"]
    for step in (1, 0.5):
        given = dict(winter_target=25, prewarm_offset=2, tolerance=1.5, hall_offset=5, heating_drive_setpoint=30,
                     ac_min_temp=16, ac_max_temp=22, ac_temp_step=step)
        ctx = _render_chain(bp, chain, now, given)
        assert ctx["winter_aim"] <= 20 + 1.5 - 0.1 + 1e-9, step
        for key in ("heating_drive_eff", "heating_hold_eff", "heat_hold_sp"):
            assert ctx[key] <= min(24, 22), (step, key)
            assert abs(ctx[key] / step - round(ctx[key] / step)) < 1e-6, (step, key)
    allowed = {"{{ heat_target_sp | float }}", "{{ heat_hold_sp | float }}", "{{ night_nudge_sp | float }}"}
    temps = [str(n["data"]["temperature"]).strip() for _, n in _service_steps(_winter_steps(bp), []) if _is_service(n, "climate.set_temperature")]
    assert temps and set(temps) <= allowed


@pytest.mark.parametrize("readings,valid", [
    (["unavailable", "unknown", "abc", ""], []),
    (["unavailable", "17.5", "unknown", "19.0"], [17.5, 19.0]),
    (["none", "18.2"], [18.2]),
])
def test_us07_unusable_sensor_states_are_dropped_and_all_bad_means_sensor_failure(bp, readings, valid):
    from datetime import datetime

    from test_bedroom_precool_structure import TZ, _render_chain

    sensors = [f"sensor.room_{i}" for i in range(len(readings))]
    table = dict(zip(sensors, readings))
    given = dict(bedroom_temp_sensors=sensors, states=lambda e: table.get(e, "unknown"), sensor_strategy="hottest", ideal_temp=23)
    chain = ["bedroom_valid_temps", "bedroom_sensors_ok", "warmest_bedroom", "coldest_bedroom"]
    ctx = _render_chain(bp, chain, datetime(2026, 11, 10, 22, 0, tzinfo=TZ), given)
    assert ctx["bedroom_valid_temps"] == valid
    assert ctx["bedroom_sensors_ok"] is bool(valid)
    if valid:
        assert (ctx["warmest_bedroom"], ctx["coldest_bedroom"]) == (max(valid), min(valid))


def test_us10_a_toggle_that_recovers_to_on_inside_120_seconds_sends_nothing_to_a_heating_unit(bp):
    from test_bedroom_precool_heating_safety import _safety

    for age in (1, 30, 119):
        assert _safety(bp, season="on", season_age=age, current_hvac_mode="heat", timer="10.0") == ([], False), age
    for state in ("unavailable", "unknown"):
        assert _safety(bp, season=state, season_age=5, timer="10.0") == ([], False), state


def test_us10_vacation_in_winter_stops_every_run_before_any_heat_command(bp):
    from test_bedroom_precool_heating_safety import UNIT_OFF, _safety, _sets

    heat_services = ("climate.turn_on", "climate.set_hvac_mode", "climate.set_temperature")
    for timer in ("10.0", "0.0"):
        for over in ({}, UNIT_OFF, dict(bedroom_valid_temps=[16.0])):
            calls, stopped = _safety(bp, vacation_active=True, timer=timer, **over)
            assert stopped, (timer, over)
            assert not [s for s, _ in calls if s in heat_services], (timer, over)
    assert _sets(_safety(bp, vacation_active=True, timer="10.0")[0]) == [{"value": 0}]
    assert _sets(_safety(bp, vacation_active=True, timer="0.0")[0]) == []


def test_us04_timer_hours_hold_their_bounds_across_weekend_boundaries_and_dst_changes(bp):
    from datetime import datetime, timedelta

    from test_bedroom_precool_heating_bedtime import _bedtime, _sets
    from test_bedroom_precool_structure import TZ

    nights = [datetime(2026, 11, day, 19, 30, tzinfo=TZ) for day in range(6, 17)]
    nights += [datetime(2026, 10, 24, 19, 30, tzinfo=TZ), datetime(2026, 10, 25, 19, 30, tzinfo=TZ),
               datetime(2027, 3, 27, 19, 30, tzinfo=TZ), datetime(2027, 3, 28, 19, 30, tzinfo=TZ)]
    mornings = [("06:15:00", "06:45:00"), ("06:30:00", "07:00:00"), ("05:00:00", "05:30:00"), ("07:15:00", "07:15:00"), ("23:00:00", "23:00:00")]
    for now in nights:
        for weekday, weekend in mornings:
            label = (now.date().isoformat(), weekday, weekend)
            ctx, calls, _ = _bedtime(bp, now, morning_time=weekday, weekend_morning_time=weekend)
            hours = ctx["timer_hours"]
            start = ctx["bed_ts"] + hours * 3600
            assert isinstance(hours, int) and hours >= 0, label
            assert start < ctx["wake_next_ts"], label
            assert 0 <= min(ctx["morning_ts"], ctx["wake_next_ts"]) - start <= 3600, label
            picked = weekend if (now + timedelta(days=1)).weekday() >= 5 else weekday
            assert datetime.fromtimestamp(ctx["morning_ts"], TZ).strftime("%H:%M:%S") == picked, label
            assert _sets(calls) == [{"value": hours}], label
    for now, hours in ((datetime(2026, 10, 24, 19, 30, tzinfo=TZ), 12), (datetime(2027, 3, 27, 19, 30, tzinfo=TZ), 10)):
        ctx = _bedtime(bp, now)[0]
        assert (ctx["timer_hours"], ctx["timer_start_tod"]) == (hours, "06:30:00"), now


def test_us05_night_re_heat_matrix_and_budget_hold_for_a_cold_night(bp):
    from datetime import timedelta

    from test_bedroom_precool_heating_night import _commands, _night, at

    assert _commands(_night(bp, at(11, 3), warmest_bedroom=19.6, coldest_bedroom=16.4)[1]) == []
    assert _commands(_night(bp, at(11, 3), warmest_bedroom=17.0, coldest_bedroom=17.0)[1]) == []
    assert _commands(_night(bp, at(11, 3), warmest_bedroom=16.4, coldest_bedroom=16.4)[1]) == [("climate.turn_on", {})]
    state = dict(ac_is_running=False, current_hvac_mode="off", current_setpoint=21.0)
    ticks = sorted([at(10, 19, 40) + timedelta(minutes=10 * i) for i in range(70)] + [at(11, 1, 5)])
    sent = []
    for now in ticks:
        for service, data in _commands(_night(bp, now, room=16.4, **state)[1]):
            sent.append((service, data))
            if service == "climate.turn_on":
                state = dict(ac_is_running=True, current_hvac_mode="heat", current_setpoint=21.0)
            else:
                state["current_setpoint"] = data["temperature"]
    assert sent == [("climate.turn_on", {}), ("climate.set_temperature", {"temperature": 22.5})]


def test_us07_lock_window_exemption_has_hard_edges_and_summer_classification_is_unchanged(bp):
    from datetime import datetime, timedelta

    from test_bedroom_precool_heating_safety import _off_flag
    from test_bedroom_precool_structure import TZ, _manual_off

    edges = [(-3600, True), (-1, True), (0, False), (1, False), (179, False), (180, True), (181, True)]
    winter_lock = datetime(2026, 11, 10, 19, 29, tzinfo=TZ)
    for seconds, manual in edges:
        off_at = winter_lock + timedelta(seconds=seconds)
        assert _off_flag(bp, off_at, True) is manual, seconds
        assert _off_flag(bp, off_at, False) is True, seconds
    summer_lock = datetime(2026, 9, 9, 19, 29, tzinfo=TZ)
    evening = datetime(2026, 9, 9, 19, 35, tzinfo=TZ)
    for seconds, manual in edges:
        off_at = summer_lock + timedelta(seconds=seconds)
        assert _manual_off(bp, "off", off_at, night_mode="fan_only", now=evening)["manual_off"] is manual, seconds


def test_us14_notice_messages_render_with_odd_values_and_stay_bounded(bp):
    from datetime import datetime

    from test_bedroom_precool_structure import TZ, _env

    now = datetime(2026, 11, 10, 18, 0, tzinfo=TZ)
    odd = ("a\"b'{{ 7*7 }}{% x" + "z" * 300)[:255]
    names = ["ac_climate", "current_hvac_mode", "timer_entity", "timer_state", "season_state"]
    fixed = dict(night_start_ts=now.timestamp(), heat_hold_sp=21.0, heating_drive_eff=24.0, current_setpoint=23.5, timer_hours=10,
                 timer_max=8.0, safe_overheat_level=19.5, bedroom_valid_temps=[19.6, 18.0], timer_start_tod="05:30:00")
    nodes = [n for _, n in _service_steps(_top_level_steps(bp), []) if _is_service(n, "persistent_notification.create")
             and (n.get("data") or {}).get("notification_id") in WINTER_NOTICES]
    assert len(nodes) == len(WINTER_NOTICES)
    for node in nodes:
        message = node["data"]["message"]
        template = _env(now).from_string(message)
        for problem in ("empty", "unavailable", "over_max", ""):
            for manual in (True, False):
                given = dict(fixed, timer_problem=problem, manual_off=manual)
                plain = template.render(**given, **{name: "" for name in names})
                rendered = template.render(**given, **{name: odd for name in names})
                assert len(plain) <= 500, node["data"]["notification_id"]
                assert len(rendered) <= len(plain) + 255 * message.count("{{"), node["data"]["notification_id"]


def test_us13_safety_cuts_work_with_unknown_limits_and_read_neither_limit(bp):
    from test_bedroom_precool_heating_safety import SENSORS_DOWN, _acts, _safety, _safety_steps

    block = repr(_safety_steps(bp))
    for name in ("ac_limits_known", "ac_min_temp", "ac_max_temp", "heat_setpoints_allowed", "heat_supported"):
        assert name not in block, name
    unknown = dict(ac_limits_known=False, ac_min_temp="unknown", ac_max_temp=None, ac_hvac_modes=["off", "cool"])
    assert _acts(_safety(bp, bedroom_valid_temps=[19.6], **unknown)[0]) == [("climate.turn_off", {})]
    assert _acts(_safety(bp, **SENSORS_DOWN, **unknown)[0]) == [("climate.turn_off", {})]
    assert _acts(_safety(bp, vacation_active=True, **unknown)[0]) == [("climate.turn_off", {}), ("number.set_value", {"value": 0})]


def test_us01_every_threat_with_a_gap_line_is_named_under_residual_gaps():
    body, residual = THREAT_MAP.read_text().split("## Residual gaps", 1)
    current, gaps = None, []
    for line in body.splitlines():
        heading = HEADING.match(line)
        if heading:
            current = heading.group(1)
        elif line.startswith("Gap") and current:
            gaps.append(current)
    assert gaps
    assert [t for t in gaps if not re.search(rf"\b{t}\b", residual)] == []
