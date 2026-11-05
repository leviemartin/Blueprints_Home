"""Heating-season model and safety guards; no heating-start commands in this card."""
from datetime import datetime, timedelta
import re

import pytest
import yaml

from test_bedroom_precool_structure import (
    _render, _render_chain, _reparse, _env, _var_template, _service_steps,
    _top_level_steps, _calls_with, _step_contains, _has_condition_text,
    _has_stop_text, _States, _St, HassLoader, _Input, BP_PATH, TZ,
)


@pytest.fixture(scope="module")
def text():
    return BP_PATH.read_text()


@pytest.fixture(scope="module")
def bp(text):
    return yaml.load(text, Loader=HassLoader)


def at(day="2026-11-12", time="23:00"):
    return datetime.fromisoformat(f"{day}T{time}").replace(tzinfo=TZ)


HEAT = """season_mode_safe heat_threshold_safe evening_target_safe morning_target_safe
night_floor_safe heat_hall_offset_safe heat_window_ok heat_eligible heat_on_day_side
heat_phase_target heat_evening_setpoint heat_morning_setpoint heat_setpoint heat_overheat
heat_hard_stop heat_stop_due heat_safe_cool_setpoint heat_offseason_cool_due heat_guard_tick""".split()
SEASON = ["heat_latched", "cool_latched", "season"]
ALLOW = ["heating_allowed", "heat_start_correct_ok"]
KNOWN = ["effective_drive", "maintaining_setpoint", "known_setpoints",
         "setpoint_is_known", "manual_setpoint"]
MANUAL = """lock_ts fan_only_mode earliest_turn_on_ts automation_up_since_ts
ac_off_since_ts vacation_changed_ts manual_off""".split()


def ctx(**over):
    result = dict(
        season_mode="auto", heat_threshold=19, evening_target=20, morning_target=20,
        night_floor=17, heat_hall_offset=2, bedtime="19:30:00", wake_time="07:15:00",
        ideal_temp=23, hall_offset=2, tolerance=1.5, ac_min_temp=16, ac_max_temp=30,
        ac_temp_step=0.5, bedroom_valid_temps=[18], bedroom_sensors_ok=True,
        coldest_bedroom=18, warmest_bedroom=18, current_hvac_mode="off",
        ac_is_running=False, ac_unavailable=False, current_setpoint=22,
        current_setpoint_known=True, cooling_needed=False, forecast_low=19.5,
        vacation_active=False, manual_setpoint=False, manual_off=False,
        drive_setpoint=16, correction_step=1.5, ac_limits_known=True,
        ac_state_age_sec=600, phase="NIGHT_HOLD", fan_only_mode=True,
        night_phase=True, night_mode="fan_only", lead_cap_minutes=240,
        vacation_toggle=[], ac_climate="climate.bedrooms",
    )
    result.update(over)
    return result


def model(bp, now=None, **over):
    return _render_chain(bp, HEAT + SEASON + ALLOW, now or at(), ctx(**over))


def value(bp, name, now=None, **over):
    return _reparse(_render(bp, name, now or at(), **over))


def test_inputs_and_bad_values(bp):
    defaults = dict(season_mode="auto", heat_threshold=19, evening_target=20,
                    morning_target=20, night_floor=17, heat_hall_offset=2)
    for name, default in defaults.items():
        assert bp["blueprint"]["input"][name]["default"] == default
        assert isinstance(bp["variables"][name], _Input)
        assert bp["variables"][name].name == name
    assert bp["blueprint"]["input"]["season_mode"]["selector"]["select"]["options"] == ["auto", "cool", "heat"]
    assert bp["blueprint"]["input"]["heat_hall_offset"]["selector"]["number"]["max"] == 4
    bad = model(bp, season_mode="summer", heat_threshold="abc", evening_target=None,
                morning_target="", night_floor="x", heat_hall_offset="x")
    for name, default in defaults.items():
        assert bad[name + "_safe"] == default
    for raw, expected in [(6, 4), (-1, 0), ("x", 2)]:
        assert model(bp, heat_hall_offset=raw)["heat_hall_offset_safe"] == expected
    for name, default in list(defaults.items())[1:5]:
        for raw in ("", None, "bad"):
            assert model(bp, **{name: raw})[name + "_safe"] == default


def test_window_uses_night_start(bp):
    for day, time, expected in [
        ("2026-04-30", "23:00", True), ("2026-05-01", "03:00", True),
        ("2026-05-01", "12:00", False), ("2026-09-30", "20:00", False),
        ("2026-10-01", "03:00", False), ("2026-10-01", "12:00", True),
    ]:
        assert model(bp, at(day, time))["heat_window_ok"] is expected
    for mode, day, expected in [
        ("heat", "2026-07-12", True), ("cool", "2026-11-12", False),
        ("auto", "2026-07-12", False),
    ]:
        assert model(bp, at(day), season_mode=mode)["heat_eligible"] is expected


def test_season_rules_forcing_and_latches(bp):
    for day, cold, low, cooling, expected in [
        ("2026-07-12", 18, 14, False, "neutral"),
        ("2026-11-12", 18.9, 19.5, False, "heat"),
        ("2026-10-15", 20, 19.5, False, "neutral"),
        ("2026-11-12", 18, 19.5, True, "cool"),
        ("2026-11-12", 20, 18.9, False, "heat"),
        ("2026-11-12", 19.5, 19.5, False, "neutral"),
    ]:
        assert model(bp, at(day), coldest_bedroom=cold, forecast_low=low,
                     cooling_needed=cooling)["season"] == expected
    assert model(bp, at("2026-07-12"), season_mode="heat", cooling_needed=True)["season"] == "heat"
    assert model(bp, season_mode="cool", coldest_bedroom=15)["season"] == "cool"
    for mode, day, cooling, age, expected in [
        ("heat", "2026-11-12", True, 600, "heat"),
        ("heat", "2026-07-12", False, 600, "neutral"),
        ("cool", "2026-10-15", True, 600, "cool"),
        ("cool", "2026-10-15", False, 600, "cool"),
        ("cool", "2026-10-15", False, 5, "cool"),
        ("dry", "2026-10-15", False, 600, "cool"),
        ("fan_only", "2026-10-15", False, 600, "heat"),
    ]:
        assert model(bp, at(day), current_hvac_mode=mode, ac_is_running=True,
                     cooling_needed=cooling, ac_state_age_sec=age, forecast_low=10)["season"] == expected


def test_overnight_forecast_shapes_window_and_fallback(bp):
    now = at(time="18:00")
    names = ["overnight_list_safe", "overnight_end_ts", "overnight_window_temps",
             "forecast_low", "forecast_low_ok"]
    base = ctx(weather_entity="weather.home", outdoor_now=12, outdoor_now_ok=True)
    entries = [
        {"datetime": (now + timedelta(hours=h)).isoformat(), "temperature": temp}
        for h, temp in [(-1, -5), (0, 18), (12, 9), (13.25, 8), (14, -10)]
    ] + [{}, {"datetime": "bad", "temperature": 0},
         {"datetime": now.isoformat(), "temperature": "bad"}, {"temperature": 1}]
    responses = [None, 5, "x", {}, {"weather.home": {}}]
    responses += [{"weather.home": {"forecast": f}} for f in (None, 5, "x", {}, [])]
    for response in responses:
        for available in (True, False):
            out = _render_chain(bp, names, now, dict(base, overnight_forecast_resp=response,
                                                     outdoor_now_ok=available))
            assert out["forecast_low"] == (12 if available else None)
            assert out["forecast_low_ok"] is False
            if not available:
                assert model(bp, coldest_bedroom=20, forecast_low=out["forecast_low"])["season"] == "neutral"
    out = _render_chain(bp, names, now, dict(base, overnight_forecast_resp={"weather.home": {"forecast": entries}}))
    assert out["overnight_window_temps"] == [18, 9, 8]
    assert out["forecast_low"] == 8 and out["forecast_low_ok"] is True


def test_fetch_gate_and_order(bp):
    calls = [(c, s) for c, s in _service_steps(bp["action"], [])
             if s.get("response_variable") == "overnight_forecast_resp"]
    assert len(calls) == 1
    conditions, call = calls[0]
    assert "{{ overnight_fetch_due }}" in conditions
    assert call["service"] == "weather.get_forecasts"
    assert call["continue_on_error"] is True and call["data"] == {"type": "hourly"}
    for day, time, mode, expected in [
        ("2026-11-12", "17:00", "auto", True), ("2026-11-12", "23:00", "auto", False),
        ("2026-07-12", "17:00", "auto", False), ("2026-11-12", "17:00", "cool", False),
    ]:
        now = at(day, time)
        assert value(bp, "overnight_fetch_due", now, **model(bp, now, season_mode=mode)) is expected


def test_phase_targets_and_setpoint_caps(bp):
    for time, target in [("16:00", 21), ("19:28", 21), ("19:29", 19.5),
                         ("23:00", 19.5), ("03:00", 19.5)]:
        for ideal in (19, 23):
            assert model(bp, at(time=time), evening_target=21, morning_target=19.5,
                         ideal_temp=ideal)["heat_phase_target"] == target
    for overrides, expected in [
        ({}, 22), ({"hall_offset": 6}, 22), ({"heat_hall_offset": 4}, 24),
        ({"evening_target": 29}, 30), ({"evening_target": 13, "heat_hall_offset": 0}, 16),
        ({"evening_target": 15, "ac_min_temp": 18}, 18),
        ({"evening_target": 20.3}, 22), ({"ac_temp_step": 1}, 22),
        ({"ac_max_temp": 21}, 21),
    ]:
        out = model(bp, at(time="16:00"), **overrides)
        assert out["heat_setpoint"] == expected
        if overrides.get("ac_temp_step") == 1:
            assert type(out["heat_setpoint"]) is int
    for time, expected in [("16:00", 23), ("23:00", 21)]:
        out = model(bp, at(time=time), evening_target=21, morning_target=19)
        assert (out["heat_evening_setpoint"], out["heat_morning_setpoint"], out["heat_setpoint"]) == (23, 21, expected)


def test_hard_stop_and_failed_sensors(bp):
    for time, temps, stop in [
        ("23:00", [21.6, 18], True), ("23:00", [21.5, 18], False),
        ("19:28", [23], False), ("19:29", [23], True),
    ]:
        for strategy in ("max", "average"):
            out = model(bp, at(time=time), evening_target=22, bedroom_valid_temps=temps,
                        sensor_strategy=strategy, ac_is_running=True, current_hvac_mode="heat")
            assert out["heat_hard_stop"] is stop and out["heat_stop_due"] is stop
            assert out["heat_offseason_cool_due"] is False
    for day, mode, stop in [("2026-11-12", "auto", True), ("2026-07-12", "auto", False),
                            ("2026-11-12", "cool", False)]:
        for readings in (["unavailable"], ["unknown"], []):
            states = _States({f"sensor.b{i}": _St(s, at()) for i, s in enumerate(readings)})
            temps = value(bp, "bedroom_valid_temps", states=states,
                          bedroom_temp_sensors=["sensor.b0", "sensor.missing"])
            assert temps == []
            out = model(bp, at(day), season_mode=mode, bedroom_valid_temps=temps,
                        bedroom_sensors_ok=False, ac_is_running=True, current_hvac_mode="heat",
                        night_mode="ac_hold")
            assert out["heat_stop_due"] is stop
            assert out["heat_offseason_cool_due"] is (not stop)
            assert out["heating_allowed"] is False
        out = model(bp, at(day), season_mode=mode, bedroom_sensors_ok=False,
                    bedroom_valid_temps=[], ac_is_running=True, current_hvac_mode="cool")
        assert not out["heat_stop_due"] and not out["heat_offseason_cool_due"]


def test_offseason_retries_and_cooling_fallthrough(bp):
    for day, mode in [("2026-07-12", "auto"), ("2026-11-12", "cool")]:
        for night in ("ac_hold", "fan_only"):
            for minute, setpoint, known, sensors, reported, due in [
                (1, 30, True, True, "heat", True), (2, 30, True, True, "heat", True),
                (3, 30, True, True, "heat", True), (1, 21, True, True, "heat", False),
                (5, 21, True, True, "heat", True), (0, 21, True, True, "heat", True),
                (1, 21, True, False, "heat", False), (5, 21, True, False, "heat", True),
                (1, 21, False, True, "heat", True), (5, 21, True, True, "cool", False),
            ]:
                now = at(day, f"23:{minute:02}")
                for step in (0.5, 1):
                    out = model(bp, now, season_mode=mode, night_mode=night,
                                fan_only_mode=night == "fan_only", ac_is_running=True,
                                current_hvac_mode=reported, current_setpoint=setpoint,
                                current_setpoint_known=known, bedroom_sensors_ok=sensors,
                                bedroom_valid_temps=[24] if sensors else [], ac_temp_step=step)
                    assert out["heat_offseason_cool_due"] is due
                    assert out["heat_stop_due"] is False
                    assert out["heat_safe_cool_setpoint"] == value(bp, "maintaining_setpoint", now, **out) == 21
                    assert value(bp, "heat_backstop_due", now, **out) is (
                        night == "fan_only" and reported == "heat" and not due)
            now = at(day, "23:05")
            out = model(bp, now, season_mode=mode, night_mode=night, ac_is_running=True,
                        current_hvac_mode="cool", current_setpoint=21, ac_state_age_sec=30,
                        states=_States({"climate.bedrooms": _St("cool", now - timedelta(seconds=30))}),
                        expand=lambda ids: [])
            _render_chain(bp, MANUAL + KNOWN + ["guard_due"], now, out)
            assert not any(out[k] for k in ("heat_offseason_cool_due", "manual_off",
                                           "manual_setpoint", "guard_due", "heating_allowed"))


def test_permission_gates_and_known_setpoints(bp):
    assert model(bp)["heating_allowed"] is True
    for flag in ("vacation_active", "manual_setpoint", "manual_off", "heat_hard_stop"):
        out = dict(model(bp), **{flag: True})
        assert value(bp, "heating_allowed", **out) is False
        assert value(bp, "heat_start_correct_ok", **out) is False
    assert not model(bp, bedroom_sensors_ok=False)["heat_start_correct_ok"]
    assert not model(bp, at("2026-07-12"))["heat_start_correct_ok"]
    assert not model(bp, coldest_bedroom=20)["heating_allowed"]
    out = model(bp, ac_is_running=True, current_hvac_mode="cool", ac_state_age_sec=30)
    assert out["season"] == "cool" and not out["heating_allowed"] and out["heat_start_correct_ok"]
    for day, mode, expected in [
        ("2026-11-12", "heat", [18, 21, 19.5, 22.5, 22, 22]),
        ("2026-11-12", "cool", [18, 21, 19.5, 22.5, 22, 22]),
        ("2026-07-12", "cool", [18, 21, 19.5, 22.5]),
    ]:
        now = at(day)
        for setpoint in (22, 25):
            out = model(bp, now, ac_min_temp=18, ac_is_running=True,
                        current_hvac_mode=mode, current_setpoint=setpoint)
            _render_chain(bp, KNOWN, now, out)
            assert out["known_setpoints"] == expected
            assert out["manual_setpoint"] is (setpoint not in expected)
    for season in ("heat", "cool", "neutral"):
        for fan_only in (True, False):
            out = ctx(season=season, heat_guard_tick=False, fan_only_mode=fan_only,
                      ac_is_running=True, current_hvac_mode="heat")
            assert value(bp, "heat_backstop_due", **out) is (season != "heat" and fan_only)


def test_guard_action_order_and_payloads(bp):
    steps = _top_level_steps(bp)
    index = lambda pred: next(i for i, s in enumerate(steps) if pred(s))
    vacation = index(lambda s: _has_stop_text(s, "Vacation active"))
    guard = index(lambda s: _has_condition_text(s, "{{ is_real_trigger and heat_stop_due }}"))
    fetches = [i for i, s in enumerate(steps) if _step_contains(s, lambda n: n.get("service") == "weather.get_forecasts")]
    fans = index(lambda s: _step_contains(s, lambda n: "for_each" in n))
    backstop = index(lambda s: _has_condition_text(s, "{{ is_real_trigger and heat_backstop_due }}"))
    stop = index(lambda s: _has_stop_text(s, "Heating guard tick"))
    validation = index(lambda s: _has_stop_text(s, "AC entity unavailable"))
    assert vacation < guard < min(fetches) <= max(fetches) < fans < backstop < stop < validation
    assert fetches[0] < index(lambda s: "forecast_fetch_due" in s.get("variables", {}))
    for name, service, data in [
        ("heat_stop_due", "climate.turn_off", None),
        ("heat_offseason_cool_due", "climate.set_temperature",
         {"temperature": "{{ heat_safe_cool_setpoint | float }}", "hvac_mode": "cool"}),
    ]:
        branches = [b for b in steps[guard]["choose"]
                    if b["conditions"] == [{"condition": "template", "value_template": "{{ is_real_trigger and " + name + " }}"}]]
        assert len(branches) == 1
        expected = dict(service=service, target={"entity_id": "{{ ac_climate }}"}, continue_on_error=True)
        if data is not None:
            expected["data"] = data
        assert branches[0]["sequence"] == [expected]
    assert steps[stop]["choose"] == [{
        "conditions": [{"condition": "template", "value_template": "{{ is_real_trigger and heat_guard_tick }}"}],
        "sequence": [{"stop": "Heating guard tick"}],
    }]
    assert not _step_contains(steps[fans], lambda n: any(
        key in str(n.get("value_template", "")) for key in ("heat_guard_tick", "heat_stop_due", "heat_offseason_cool_due")))
    assert all(s.get("data", {}).get("hvac_mode") != "heat" for _, s in _service_steps(bp["action"], []))
    assert not any(s["service"] == "climate.turn_off" for _, s in _calls_with(bp, "heat_offseason_cool_due"))


def test_guard_ticks_keep_fan_safety(bp):
    # A fresh in-flight fan on each tick is inside the real settle window.
    for minute in (31, 32, 33):
        now = at("2026-07-12", f"19:{minute}")
        out = model(bp, now, night_mode="ac_hold", current_hvac_mode="heat",
                    ac_is_running=True, current_setpoint=30, bedroom_valid_temps=[24])
        assert out["heat_offseason_cool_due"] and out["heat_guard_tick"]
        fan = _St("on", now - timedelta(seconds=30))
        interlock = _St("on", now - timedelta(minutes=5))
        out.update(now_tod=now.strftime("%H:%M:%S"), lock_tod="19:29:00",
                   night_fans_tonight=True, fan_assist_tonight=False, in_fan_assist_grace=False,
                   fan_settle_minutes=45, bedroom_fans=["fan.bedroom"],
                   interlocked_fans=["fan.bedroom"], fan_interlocks=["binary_sensor.interlock"],
                   expand=lambda ids: [fan] if ids == "fan.bedroom" else [interlock])
        _render_chain(bp, ["lock_ts", "settle_grace_tod", "in_fan_settle_grace", "fans_unsafe_on"], now, out)
        assert out["fans_unsafe_on"] == ["fan.bedroom"]
    now = at(time="07:15")
    out = model(bp, now, ac_is_running=True, current_hvac_mode="heat", bedroom_valid_temps=[24])
    assert out["heat_stop_due"] and out["heat_guard_tick"]
    out.update(now_tod="07:15:00", wake_tod="07:15:00", fans_at_wake="off",
               bedroom_fans=["fan.bedroom"], expand=lambda ids: [_St("on", now)])
    _render_chain(bp, ["in_wake_window", "fans_on_at_wake"], now, out)
    assert out["fans_on_at_wake"] == ["fan.bedroom"]


def test_values_after_heat_season_stop(bp):
    for stamp, time, hot, manual, allowed, guard in [
        ("19:29:20", "23:00", 21, False, True, False),
        ("23:00:20", "23:05", 21, True, False, False),
        ("23:00:20", "23:05", 25, True, False, False),
        ("19:29:20", "23:05", 25, False, False, True),
    ]:
        now = at(time=time)
        out = model(bp, now, evening_target=22, morning_target=20,
                    bedroom_valid_temps=[hot, 18], warmest_bedroom=hot, forecast_low=5,
                    states=_States({"climate.bedrooms": _St("off", at(time=stamp))}),
                    expand=lambda ids: [])
        _render_chain(bp, MANUAL + ALLOW + ["guard_due"], now, out)
        assert (out["manual_off"], out["heating_allowed"], out["guard_due"]) == (manual, allowed, guard)


def test_debug_notice_and_dependency_order(bp, text):
    messages = {s.get("data", {}).get("notification_id"): s.get("data", {}).get("message", "")
                for _, s in _service_steps(bp["action"], []) if "message" in s.get("data", {})}
    for name in ("season", "forecast_low", "heating_allowed", "heat_offseason_cool_due"):
        assert "{{ " + name + " }}" in messages["bedroom_precool_debug"]
    assert "by the heating guard" in messages["bedroom_precool_manual_override"]
    pos = lambda name: re.search(r"^      " + name + ":", text, re.M).start()
    for chain in [
        ["heat_guard_tick", "overnight_fetch_due"],
        ["heat_stop_due", "overnight_fetch_due", "forecast_window_temps"],
        ["forecast_low", "season", "known_setpoints"],
        ["manual_setpoint", "heating_allowed", "heat_backstop_due"],
        ["manual_setpoint", "heat_start_correct_ok"],
    ]:
        assert [pos(n) for n in chain] == sorted(pos(n) for n in chain)


def test_nonfinite_heating_inputs_use_defaults(bp):
    defaults = dict(heat_threshold=19, evening_target=20, morning_target=20,
                    night_floor=17, heat_hall_offset=2)
    for name, default in defaults.items():
        for raw in ("nan", "inf", "-inf", float("nan"), float("inf"), -float("inf")):
            out = model(bp, **{name: raw}, ac_is_running=True,
                        current_hvac_mode="heat", bedroom_valid_temps=[24])
            assert out[name + "_safe"] == default
            assert out["heat_stop_due"] is True
            assert out["heating_allowed"] is False


def test_hard_stop_is_disabled_outside_heat_eligibility(bp):
    for day, mode in [("2026-07-12", "auto"), ("2026-11-12", "cool")]:
        out = model(bp, at(day), season_mode=mode, bedroom_valid_temps=[25],
                    current_hvac_mode="heat", ac_is_running=True)
        assert out["heat_overheat"] is True
        assert out["heat_hard_stop"] is False
        assert out["heat_stop_due"] is False
        assert out["heat_offseason_cool_due"] is True


def test_offseason_correction_pauses_on_recovery_and_resumes_on_overheat(bp):
    for day, mode in [("2026-07-12", "auto"), ("2026-11-12", "cool")]:
        for initial in ([24], []):
            first = model(bp, at(day, "23:00"), season_mode=mode,
                          bedroom_valid_temps=initial, bedroom_sensors_ok=bool(initial),
                          current_hvac_mode="heat", ac_is_running=True, current_setpoint=30)
            assert first["heat_guard_tick"] is True
            for minute, temp, setpoint, reported, expected in [
                (1, 21.4, 30, "heat", False), (2, 21.4, 30, "heat", False),
                (3, 24, 30, "heat", True), (1, 21.4, 21, "heat", False),
                (5, 21.4, 21, "heat", False), (1, 24, 21, "heat", False),
                (5, 24, 21, "heat", True), (5, 24, 30, "cool", False),
                (5, 24, 30, "dry", False), (5, 24, 30, "off", False),
            ]:
                out = model(bp, at(day, f"23:{minute:02}"), season_mode=mode,
                            bedroom_valid_temps=[temp], bedroom_sensors_ok=True,
                            current_hvac_mode=reported, ac_is_running=reported != "off",
                            current_setpoint=setpoint)
                assert out["heat_overheat"] is (temp > 21.5)
                assert out["heat_offseason_cool_due"] is expected
                assert out["heat_guard_tick"] is expected


def test_naive_forecast_timestamps_skip_hourly_but_preserve_daily(bp):
    now = at(time="18:00")
    malformed = [
        {"datetime": "2026-11-12T19:00:00", "temperature": -10},
        {"datetime": "2026-11-12", "temperature": -20},
    ]
    for entries, expected in [
        (malformed, []),
        (malformed + [{"datetime": (now + timedelta(hours=1)).isoformat(),
                       "temperature": 15}], [15]),
    ]:
        for available in (True, False):
            base = ctx(weather_entity="weather.home", outdoor_now=12,
                       outdoor_now_ok=available)
            response = {"weather.home": {"forecast": entries}}
            out = _render_chain(bp, [
                "overnight_list_safe", "overnight_end_ts", "overnight_window_temps",
                "forecast_low", "forecast_low_ok",
            ], now, dict(base, overnight_forecast_resp=response))
            assert out["overnight_window_temps"] == expected
            assert out["forecast_low"] == (15 if expected else 12 if available else None)
            assert out["forecast_low_ok"] is bool(expected)
            out = _render_chain(bp, [
                "forecast_list_safe", "bedtime_ts", "forecast_window_temps",
                "forecast_daily_list", "forecast_daily_high", "forecast_daily_ok",
                "forecast_max",
            ], now, dict(base, hourly_forecast_resp=response, daily_forecast_resp=response))
            assert out["forecast_window_temps"] == expected
            assert out["forecast_daily_high"] == -10
            assert out["forecast_daily_ok"] is True
            assert out["forecast_max"] == (15 if expected else 12)


def test_offseason_correction_quantises_fractional_whole_degree_setpoint(bp):
    now = at("2026-07-12", "23:01")
    out = model(bp, now, hall_offset=1.5, ac_temp_step=1,
                current_hvac_mode="heat", ac_is_running=True,
                current_setpoint=21, bedroom_valid_temps=[24])
    assert out["heat_safe_cool_setpoint"] == 21
    assert type(out["heat_safe_cool_setpoint"]) is int
    assert value(bp, "maintaining_setpoint", now, **out) == 21
    assert out["heat_offseason_cool_due"] is False
