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
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_us13_extreme_inputs_keep_the_aim_and_every_setpoint_inside_the_caps`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_tm01_unsafe_heat_setpoint_or_aim_is_mapped_to_an_existing_test`

## TM-2 A stalled forecast call delays a safety cut

- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_us07_the_winter_safety_cuts_come_before_the_first_forecast_call`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_us07_the_winter_safety_cuts_read_no_forecast_variable`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_tm02_stalled_forecast_call_threat_is_mapped_to_an_existing_test`

## TM-3 Bad sensor values accepted as readings

- `tests/test_bedroom_precool_heating_safety.py::test_us07_every_sensor_unavailable_gives_one_turn_off_and_one_notice`
- `tests/test_bedroom_precool_heating_safety.py::test_us07_sensor_failure_with_the_unit_already_off_sends_no_command`
- `tests/test_bedroom_precool_heating_safety.py::test_us07_sensor_failure_cut_is_for_real_winter_ticks_with_a_reachable_unit`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_us07_unusable_sensor_states_are_dropped_and_all_bad_means_sensor_failure`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_tm03_bad_sensor_values_threat_is_mapped_to_an_existing_test`

Gap (not closed, raised to the lead): the sensor filter in bedroom_precool.yaml drops unavailable, unknown and non-numeric states but accepts nan, inf and implausible numbers such as -40 or 0, so a bogus low reading can start or sustain heating and a bogus high one can trigger a cut. The same aggregation feeds the summer cooling rules, so a range filter would change summer behaviour and is not part of this task. The mapped tests cover only the unavailable, unknown and non-numeric cases.

## TM-4 Season toggle unavailable, empty or not a boolean

- `tests/test_bedroom_precool_heating_inputs.py::test_us01_season_toggle_resolution`
- `tests/test_bedroom_precool_heating_inputs.py::test_us01_empty_toggle_input_acts_as_summer`
- `tests/test_bedroom_precool_heating_inputs.py::test_us01_invalid_toggle_raises_one_fixed_id_notice`
- `tests/test_bedroom_precool_heating_bedtime.py::test_us04_summer_and_manual_runs_do_not_arm_the_timer`
- `tests/test_bedroom_precool_heating_night.py::test_us05_nothing_is_sent_in_summer_on_a_manual_run_without_heat_or_with_unknown_limits`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_tm04_season_toggle_threat_is_mapped_to_an_existing_test`

## TM-5 Toggle recovery read as a season flip

- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_us10_a_toggle_that_recovers_to_on_inside_120_seconds_sends_nothing_to_a_heating_unit`
- `tests/test_bedroom_precool_heating_safety.py::test_us10_a_unit_started_after_the_flip_is_left_to_the_other_rules`
- `tests/test_bedroom_precool_heating_safety.py::test_us10_a_toggle_that_does_not_read_on_or_off_flips_nothing_and_a_manual_run_never_actuates`
- `tests/test_bedroom_precool_heating_safety.py::test_us10_no_timer_reset_when_it_is_already_0_cannot_be_read_or_the_flip_minute_has_passed`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_tm05_toggle_recovery_threat_is_mapped_to_an_existing_test`

Gap (partial): the new test pins the mitigation's scenario (the toggle returns to on within 120 s while the unit heats: no turn_off, no timer reset). The detector itself still compares the toggle's last_changed with the unit's start and the unit's mode with the season; it does not read from_state and to_state. A return to off within 120 s still zeroes a non-zero timer, which matches the toggle's state.

## TM-6 Stale LG timer starts the unit unattended

- `tests/test_bedroom_precool_heating_safety.py::test_us10_flip_to_summer_switches_off_heat_and_sets_the_timer_to_0_in_that_minute`
- `tests/test_bedroom_precool_heating_safety.py::test_us10_flip_to_summer_zeroes_the_timer_even_when_the_unit_is_off`
- `tests/test_bedroom_precool_heating_safety.py::test_us10_no_timer_reset_when_it_is_already_0_cannot_be_read_or_the_flip_minute_has_passed`
- `tests/test_bedroom_precool_heating_safety.py::test_us10_vacation_in_winter_switches_off_zeroes_the_timer_and_stops_before_any_cut`
- `tests/test_bedroom_precool_heating_safety.py::test_us10_vacation_in_winter_sends_nothing_more_once_the_unit_is_off_and_the_timer_is_0`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_us10_vacation_in_winter_stops_every_run_before_any_heat_command`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_tm06_stale_timer_threat_is_mapped_to_an_existing_test`

Gap (not closed, raised to the lead): the timer is zeroed in the flip minute and on every Vacation tick in winter, and no heat command follows while Vacation is on. A toggle that is off with a non-zero timer outside the flip minute (a missed minute) is not reset, and Vacation in summer is left to the existing Vacation step. Closing this needs a summer-side change to bedroom_precool.yaml.

## TM-7 Timer hours miss their bounds

- `tests/test_bedroom_precool_heating_bedtime.py::test_us04_morning_time_by_weekday_or_weekend_sets_the_whole_hours`
- `tests/test_bedroom_precool_heating_bedtime.py::test_us04_planned_start_is_never_at_or_after_wake_time`
- `tests/test_bedroom_precool_heating_bedtime.py::test_us14_a_timer_that_cannot_be_set_gives_one_notice_and_no_morning_command`
- `tests/test_bedroom_precool_heating_bedtime.py::test_us14_a_set_that_does_not_read_back_gives_one_notice`
- `tests/test_bedroom_precool_heating_debug.py::test_us15_timer_hours_use_the_weekend_morning_time_and_never_pass_wake_time`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_us04_timer_hours_hold_their_bounds_across_weekend_boundaries_and_dst_changes`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_tm07_timer_hours_threat_is_mapped_to_an_existing_test`

## TM-8 The morning start has no verified outcome

- `tests/test_bedroom_precool_heating_bedtime.py::test_us14_a_set_that_does_not_read_back_gives_one_notice`
- `tests/test_bedroom_precool_heating_bedtime.py::test_us14_a_timer_that_cannot_be_set_gives_one_notice_and_no_morning_command`
- `tests/test_bedroom_precool_heating_night.py::test_us06_a_unit_that_comes_on_in_another_mode_gets_one_heat_command_and_one_notice`
- `tests/test_bedroom_precool_heating_night.py::test_us06_a_unit_that_comes_on_in_heat_after_the_planned_start_gets_no_climate_or_fan_command`
- `tests/test_bedroom_precool_heating_night.py::test_us06_the_correction_is_single_and_only_for_a_unit_the_timer_just_started`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_tm08_unverified_morning_start_threat_is_mapped_to_an_existing_test`

Gap: the read-back happens 10 s after the set in the bedtime minute, not in the next minute, and a timer that does not clear after firing is not detected. The live check on the real unit remains a release gate.

## TM-9 Wrong parked-state inference

- `tests/test_bedroom_precool_heating_bedtime.py::test_us04_unit_is_parked_in_heat_at_the_hold_setpoint_before_it_is_switched_off`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_us06_every_winter_command_that_names_a_mode_names_heat`
- `tests/test_bedroom_precool_heating_night.py::test_us06_a_unit_that_comes_on_in_another_mode_gets_one_heat_command_and_one_notice`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_tm09_parked_state_threat_is_mapped_to_an_existing_test`

Gap: a unit that is already off at bedtime is not parked (the LG unit takes no mode change while off), so its last mode is unknown; an off unit left in cool restarts in cool on a night re-heat, and only the timer start gets the wrong-mode correction. No test pins this, and closing it needs a change to bedroom_precool.yaml.

## TM-10 Night re-heat restores an unknown state

- `tests/test_bedroom_precool_heating_night.py::test_us05_one_bare_turn_on_goes_out_below_the_re_heat_level_and_nothing_at_it`
- `tests/test_bedroom_precool_heating_night.py::test_us05_re_heat_can_start_at_any_minute_between_bedtime_and_wake_outside_the_planned_start_wait`
- `tests/test_bedroom_precool_heating_night.py::test_us05_re_heat_waits_five_minutes_after_the_planned_start_on_weekdays_and_weekends`
- `tests/test_bedroom_precool_heating_night.py::test_us05_deep_night_check_nudges_up_once_by_the_correction_step`
- `tests/test_bedroom_precool_heating_night.py::test_us05_the_nudge_is_capped_at_24_the_unit_max_and_rounded_down_to_the_step`
- `tests/test_bedroom_precool_heating_lead.py::test_us02_night_stage_reheats_below_the_band_and_flags_overheat_above_it`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_us05_night_re_heat_matrix_and_budget_hold_for_a_cold_night`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_tm10_night_re_heat_threat_is_mapped_to_an_existing_test`

Gap (not closed, raised to the lead): the bare turn-on does not correct a restored setpoint above the cap, and it ignores manual_off by design (the bedtime off would read as a person's), so a manual setpoint above 24 survives a night re-heat. The deep-night nudge acts only on a unit holding the hold setpoint. The new test pins the overheat and re-heat matrix and a night budget of one re-heat and one nudge; the restart after an overheat cut is pinned at the stage level only.

## TM-11 Lock-window exemption hides a manual off

- `tests/test_bedroom_precool_heating_safety.py::test_us07_the_180_second_lock_exemption_covers_heating_nights`
- `tests/test_bedroom_precool_structure.py::test_rendered_manual_off_exempts_only_the_lock_s_own_off_in_fan_only`
- `tests/test_bedroom_precool_structure.py::test_rendered_manual_off_only_for_an_off_transition_inside_the_adoption_window`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_us07_lock_window_exemption_has_hard_edges_and_summer_classification_is_unchanged`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_tm11_lock_window_exemption_threat_is_mapped_to_an_existing_test`

Gap (partial): the exemption is keyed to the 180 s window after the lock minute, not to a recorded blueprint turn_off, so a person's off inside that window is still read as the blueprint's. The new test pins the edges at lock minus 1 s, plus 179 s, plus 180 s and plus 181 s and the unchanged summer classification.

## TM-12 Notification flooding or broken notice text

- `tests/test_bedroom_precool_heating_inputs.py::test_us01_invalid_toggle_raises_one_fixed_id_notice`
- `tests/test_bedroom_precool_heating_inputs.py::test_us13_unit_without_heat_gets_one_fixed_id_notice`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_us14_every_notice_id_is_a_constant_and_each_winter_notice_has_one`
- `tests/test_bedroom_precool_heating_bedtime.py::test_us14_notice_follows_the_notification_switch`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_us14_notice_messages_render_with_odd_values_and_stay_bounded`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_tm12_notification_flooding_threat_is_mapped_to_an_existing_test`

## TM-13 Unknown or unsupported unit capabilities

- `tests/test_bedroom_precool_heating_inputs.py::test_us13_no_heat_setpoint_while_limits_unknown_or_heat_missing`
- `tests/test_bedroom_precool_heating_inputs.py::test_us13_unit_without_heat_gets_one_fixed_id_notice`
- `tests/test_bedroom_precool_heating_bedtime.py::test_us13_no_heat_command_or_timer_at_bedtime_without_heat_mode_or_known_limits`
- `tests/test_bedroom_precool_heating_evening.py::test_us13_no_heat_command_without_heat_mode_or_while_the_limits_are_unknown`
- `tests/test_bedroom_precool_heating_night.py::test_us05_nothing_is_sent_in_summer_on_a_manual_run_without_heat_or_with_unknown_limits`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_us13_safety_cuts_work_with_unknown_limits_and_read_neither_limit`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_tm13_unknown_unit_capabilities_threat_is_mapped_to_an_existing_test`

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
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_tm14_summer_regression_threat_is_mapped_to_an_existing_test`

Gap: there is no stored v1.2.1 render to compare action lists with; the unchanged v1.2.1 tests are the baseline.

## TM-15 Fan commands on hand-controlled devices

- `tests/test_bedroom_precool_heating_fans.py::test_us08_bedtime_lock_switches_off_only_fans_the_blueprint_started_and_nobody_touched`
- `tests/test_bedroom_precool_heating_fans.py::test_us08_summer_lists_are_empty_in_winter_in_every_stage`
- `tests/test_bedroom_precool_heating_fans.py::test_us08_fan_calls_are_still_the_four_existing_call_sites_and_never_set_direction`
- `tests/test_bedroom_precool_heating_fans.py::test_us08_evening_assist_lists_fans_for_the_pre_cool_percentage_only_inside_its_window`
- `tests/test_bedroom_precool_heating_fans.py::test_us08_assist_window_in_winter_needs_the_unit_heating`
- `tests/test_bedroom_precool_heating_night.py::test_us06_a_unit_that_comes_on_in_heat_after_the_planned_start_gets_no_climate_or_fan_command`
- `tests/test_2026_11_10_bedroom_ac_pre_warm_v1_3_0_extend_bedroom_precoo_threat_coverage_bedroom_precool_heating_inputs.py::test_tm15_fan_commands_threat_is_mapped_to_an_existing_test`

Gap: "never a direction command" is pinned only by the four fan call sites being turn_on and turn_off.

## Residual gaps

- Not closed, raised to the lead as blockers (each needs a change to bedroom_precool.yaml that this task does not make): TM-3 (nan, inf and implausible readings are accepted), TM-6 (a stale timer outside the flip minute is not reset), TM-9 (an off unit left in cool is not detected as unparked) and TM-10 (the bare re-heat turn-on does not cap a restored setpoint).
- Partly closed: TM-5 (the flip detector reads last_changed, not an on/off transition), TM-11 (the exemption is keyed to the window, not to a recorded turn_off), TM-15 ("never a direction command" is pinned only by the four fan call sites) and TM-14 (below).
- TM-8: the read-back happens 10 s after the set in the bedtime minute and a timer that does not clear after firing is not detected; the live check on the real unit is a release gate.
- TM-14: no stored v1.2.1 render for a differential test.
