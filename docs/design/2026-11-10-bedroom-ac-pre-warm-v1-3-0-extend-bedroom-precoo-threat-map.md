# Threat map: Bedroom Pre-Warm v1.3.0

Each threat is mapped to the existing acceptance tests that cover it, by file and test name. The coverage test (tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py) fails when a threat, a test file or a test name listed here is missing. Gaps that the tests do not close are named under the threat and collected under Residual gaps.

## TM-1 Unsafe heat setpoint or aim

- `tests/test_bedroom_precool_heating_inputs.py::test_us13_winter_target_is_capped_at_20`
- `tests/test_bedroom_precool_heating_inputs.py::test_us13_prewarm_offset_is_used_below_the_tolerance`
- `tests/test_bedroom_precool_heating_inputs.py::test_us13_heat_drive_setpoint_is_capped_and_rounded_down_to_the_step`
- `tests/test_bedroom_precool_heating_inputs.py::test_us13_heat_hold_setpoint_follows_the_capped_target`
- `tests/test_bedroom_precool_heating_evening.py::test_us13_heat_setpoints_are_capped_at_24_and_the_unit_max_and_rounded_down_to_the_step`
- `tests/test_bedroom_precool_heating_evening.py::test_us02_no_heat_command_sets_more_than_24`
- `tests/test_bedroom_precool_heating_night.py::test_us05_the_nudge_is_capped_at_24_the_unit_max_and_rounded_down_to_the_step`

## TM-2 A stalled forecast call delays a safety cut

- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_us07_the_winter_safety_cuts_come_before_the_first_forecast_call`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_us07_the_winter_safety_cuts_read_no_forecast_variable`

## TM-3 Bad sensor values accepted as readings

- `tests/test_bedroom_precool_heating_safety.py::test_us07_every_sensor_unavailable_gives_one_turn_off_and_one_notice`
- `tests/test_bedroom_precool_heating_safety.py::test_us07_sensor_failure_with_the_unit_already_off_sends_no_command`
- `tests/test_bedroom_precool_heating_safety.py::test_us07_sensor_failure_cut_is_for_real_winter_ticks_with_a_reachable_unit`

Gap: the sensor filter in bedroom_precool.yaml drops unavailable, unknown and non-numeric states but accepts nan, inf and implausible numbers such as -40 or 0. The same aggregation feeds the summer cooling rules, so a range filter would change summer behaviour and is not part of this task.

## TM-4 Season toggle unavailable, empty or not a boolean

- `tests/test_bedroom_precool_heating_inputs.py::test_us01_season_toggle_resolution`
- `tests/test_bedroom_precool_heating_inputs.py::test_us01_empty_toggle_input_acts_as_summer`
- `tests/test_bedroom_precool_heating_inputs.py::test_us01_invalid_toggle_raises_one_fixed_id_notice`
- `tests/test_bedroom_precool_heating_bedtime.py::test_us04_summer_and_manual_runs_do_not_arm_the_timer`
- `tests/test_bedroom_precool_heating_night.py::test_us05_nothing_is_sent_in_summer_on_a_manual_run_without_heat_or_with_unknown_limits`

## TM-5 Toggle recovery read as a season flip

- `tests/test_bedroom_precool_heating_safety.py::test_us10_a_unit_started_after_the_flip_is_left_to_the_other_rules`
- `tests/test_bedroom_precool_heating_safety.py::test_us10_a_toggle_that_does_not_read_on_or_off_flips_nothing_and_a_manual_run_never_actuates`
- `tests/test_bedroom_precool_heating_safety.py::test_us10_no_timer_reset_when_it_is_already_0_cannot_be_read_or_the_flip_minute_has_passed`

Gap: the flip detector compares the toggle's last_changed with the unit's start and checks the unit's mode against the season; it does not read from_state and to_state. A toggle that goes unavailable and returns to on cannot turn off a unit that is heating, but a return to off within 120 s still zeroes a non-zero timer, which matches the toggle's state.

## TM-6 Stale LG timer starts the unit unattended

- `tests/test_bedroom_precool_heating_safety.py::test_us10_flip_to_summer_switches_off_heat_and_sets_the_timer_to_0_in_that_minute`
- `tests/test_bedroom_precool_heating_safety.py::test_us10_flip_to_summer_zeroes_the_timer_even_when_the_unit_is_off`
- `tests/test_bedroom_precool_heating_safety.py::test_us10_no_timer_reset_when_it_is_already_0_cannot_be_read_or_the_flip_minute_has_passed`
- `tests/test_bedroom_precool_heating_safety.py::test_us10_vacation_in_winter_switches_off_zeroes_the_timer_and_stops_before_any_cut`
- `tests/test_bedroom_precool_heating_safety.py::test_us10_vacation_in_winter_sends_nothing_more_once_the_unit_is_off_and_the_timer_is_0`

Gap: the timer is zeroed in the flip minute and on every Vacation tick in winter. A toggle that is off with a non-zero timer outside the flip minute (a missed minute) is not reset, and Vacation in summer is left to the existing Vacation step. Closing this needs a summer-side change to bedroom_precool.yaml.

## TM-7 Timer hours miss their bounds

- `tests/test_bedroom_precool_heating_bedtime.py::test_us04_morning_time_by_weekday_or_weekend_sets_the_whole_hours`
- `tests/test_bedroom_precool_heating_bedtime.py::test_us04_planned_start_is_never_at_or_after_wake_time`
- `tests/test_bedroom_precool_heating_bedtime.py::test_us14_a_timer_that_cannot_be_set_gives_one_notice_and_no_morning_command`
- `tests/test_bedroom_precool_heating_bedtime.py::test_us14_a_set_that_does_not_read_back_gives_one_notice`
- `tests/test_bedroom_precool_heating_debug.py::test_us15_timer_hours_use_the_weekend_morning_time_and_never_pass_wake_time`

Gap: no test sweeps bedtimes and morning times, and none runs on a DST change date; the hours come from timestamp differences, which the weekday and weekend cases check for 10 to 15 November 2026 only.

## TM-8 The morning start has no verified outcome

- `tests/test_bedroom_precool_heating_bedtime.py::test_us14_a_set_that_does_not_read_back_gives_one_notice`
- `tests/test_bedroom_precool_heating_bedtime.py::test_us14_a_timer_that_cannot_be_set_gives_one_notice_and_no_morning_command`
- `tests/test_bedroom_precool_heating_night.py::test_us06_a_unit_that_comes_on_in_another_mode_gets_one_heat_command_and_one_notice`
- `tests/test_bedroom_precool_heating_night.py::test_us06_a_unit_that_comes_on_in_heat_after_the_planned_start_gets_no_climate_or_fan_command`
- `tests/test_bedroom_precool_heating_night.py::test_us06_the_correction_is_single_and_only_for_a_unit_the_timer_just_started`

Gap: the read-back happens 10 s after the set in the bedtime minute, not in the next minute, and a timer that does not clear after firing is not detected. The live check on the real unit remains a release gate.

## TM-9 Wrong parked-state inference

- `tests/test_bedroom_precool_heating_bedtime.py::test_us04_unit_is_parked_in_heat_at_the_hold_setpoint_before_it_is_switched_off`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_us06_every_winter_command_that_names_a_mode_names_heat`
- `tests/test_bedroom_precool_heating_night.py::test_us06_a_unit_that_comes_on_in_another_mode_gets_one_heat_command_and_one_notice`

Gap: a unit that is already off at bedtime is not parked (the LG unit takes no mode change while off), so its last mode is unknown; an off unit left in cool restarts in cool on a night re-heat, and only the timer start gets the wrong-mode correction. No test pins this, and closing it needs a change to bedroom_precool.yaml.

## TM-10 Night re-heat restores an unknown state

- `tests/test_bedroom_precool_heating_night.py::test_us05_one_bare_turn_on_goes_out_below_the_re_heat_level_and_nothing_at_it`
- `tests/test_bedroom_precool_heating_night.py::test_us05_re_heat_can_start_at_any_minute_between_bedtime_and_wake_outside_the_planned_start_wait`
- `tests/test_bedroom_precool_heating_night.py::test_us05_re_heat_waits_five_minutes_after_the_planned_start_on_weekdays_and_weekends`
- `tests/test_bedroom_precool_heating_night.py::test_us05_deep_night_check_nudges_up_once_by_the_correction_step`
- `tests/test_bedroom_precool_heating_night.py::test_us05_the_nudge_is_capped_at_24_the_unit_max_and_rounded_down_to_the_step`
- `tests/test_bedroom_precool_heating_lead.py::test_us02_night_stage_reheats_below_the_band_and_flags_overheat_above_it`

Gap: the bare turn-on does not correct a restored setpoint above the cap, and it ignores manual_off by design (the bedtime off would read as a person's). The deep-night nudge acts only on a unit holding the hold setpoint. No test simulates a whole night for the budget of one re-heat, one nudge and one restart.

## TM-11 Lock-window exemption hides a manual off

- `tests/test_bedroom_precool_heating_safety.py::test_us07_the_180_second_lock_exemption_covers_heating_nights`
- `tests/test_bedroom_precool_structure.py::test_rendered_manual_off_exempts_only_the_lock_s_own_off_in_fan_only`
- `tests/test_bedroom_precool_structure.py::test_rendered_manual_off_only_for_an_off_transition_inside_the_adoption_window`

Gap: the exemption is keyed to the 180 s window after bedtime, not to a recorded blueprint turn_off. The tests cover an off in the lock minute and an off at 180 s; offs at lock minus 1 s and at 179 s and 181 s are not pinned.

## TM-12 Notification flooding or broken notice text

- `tests/test_bedroom_precool_heating_inputs.py::test_us01_invalid_toggle_raises_one_fixed_id_notice`
- `tests/test_bedroom_precool_heating_inputs.py::test_us13_unit_without_heat_gets_one_fixed_id_notice`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_us14_every_notice_id_is_a_constant_and_each_winter_notice_has_one`
- `tests/test_bedroom_precool_heating_bedtime.py::test_us14_notice_follows_the_notification_switch`

Gap: no test renders the messages with quotes, braces or long entity names, and none bounds message length.

## TM-13 Unknown or unsupported unit capabilities

- `tests/test_bedroom_precool_heating_inputs.py::test_us13_no_heat_setpoint_while_limits_unknown_or_heat_missing`
- `tests/test_bedroom_precool_heating_inputs.py::test_us13_unit_without_heat_gets_one_fixed_id_notice`
- `tests/test_bedroom_precool_heating_bedtime.py::test_us13_no_heat_command_or_timer_at_bedtime_without_heat_mode_or_known_limits`
- `tests/test_bedroom_precool_heating_evening.py::test_us13_no_heat_command_without_heat_mode_or_while_the_limits_are_unknown`
- `tests/test_bedroom_precool_heating_night.py::test_us05_nothing_is_sent_in_summer_on_a_manual_run_without_heat_or_with_unknown_limits`

Gap: no test runs a safety cut with the unit's limits unknown; the cuts read neither limit.

## TM-14 Summer regression through the shared v1.2.1 paths

- `tests/test_bedroom_precool_heating_backstop.py::test_us12_toggle_off_a_unit_found_heating_gets_one_cool_command_at_the_safe_setpoint_when_a_room_is_over_the_level_or_every_sensor_failed`
- `tests/test_bedroom_precool_heating_backstop.py::test_us12_a_heat_run_started_by_hand_with_the_rooms_in_range_gets_no_command`
- `tests/test_bedroom_precool_heating_backstop.py::test_us12_the_level_is_the_winter_target_capped_at_20_plus_the_tolerance`
- `tests/test_bedroom_precool_heating_backstop.py::test_us12_with_the_toggle_on_the_backstop_never_fires`
- `tests/test_bedroom_precool_heating_backstop.py::test_us12_only_a_running_unit_reporting_heat_on_a_real_tick_is_corrected`
- `tests/test_bedroom_precool_heating_backstop.py::test_us12_the_backstop_is_one_set_temperature_call_and_no_turn_off_is_gated_on_it`
- `tests/test_bedroom_precool_heating_night.py::test_us05_heat_backstop_stands_down_in_the_heating_season_so_a_re_heated_unit_is_not_forced_to_cool`
- `tests/test_bedroom_precool_heating_bedtime.py::test_us04_summer_and_manual_runs_do_not_arm_the_timer`
- `tests/test_bedroom_precool_heating_fans.py::test_us08_summer_lists_are_empty_in_winter_in_every_stage`
- `tests/test_bedroom_precool_structure.py::test_rendered_night_phases_unchanged`

Gap: there is no stored v1.2.1 render to compare action lists with; the unchanged v1.2.1 tests are the baseline.

## TM-15 Fan commands on hand-controlled devices

- `tests/test_bedroom_precool_heating_fans.py::test_us08_bedtime_lock_switches_off_only_fans_the_blueprint_started_and_nobody_touched`
- `tests/test_bedroom_precool_heating_fans.py::test_us08_summer_lists_are_empty_in_winter_in_every_stage`
- `tests/test_bedroom_precool_heating_fans.py::test_us08_fan_calls_are_still_the_four_existing_call_sites_and_never_set_direction`
- `tests/test_bedroom_precool_heating_fans.py::test_us08_evening_assist_lists_fans_for_the_pre_cool_percentage_only_inside_its_window`
- `tests/test_bedroom_precool_heating_fans.py::test_us08_assist_window_in_winter_needs_the_unit_heating`
- `tests/test_bedroom_precool_heating_night.py::test_us06_a_unit_that_comes_on_in_heat_after_the_planned_start_gets_no_climate_or_fan_command`

Gap: "never a direction command" is pinned only by the four fan call sites being turn_on and turn_off.

## Residual gaps

- TM-3, TM-6 and TM-9 need a change to bedroom_precool.yaml that also touches summer behaviour or the shared sensor and parked-state paths; they are not closed here.
- TM-7 (DST dates and a bedtime sweep), TM-10 (night budget), TM-11 (window edges) and TM-12 (odd entity names, message length) have partial test coverage.
- TM-8: the live check on the real unit is a release gate.
- TM-14: no stored v1.2.1 render for a differential test.
