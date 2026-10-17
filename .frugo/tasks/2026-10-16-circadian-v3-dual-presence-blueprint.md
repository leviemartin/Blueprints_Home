---
id: 2026-10-16-circadian-v3-dual-presence-blueprint
title: Circadian living room v3 dual presence
goal: livingroom-fp300-dual-presence
issue: none
status: done
lane: 2
coder: codex
step: codex
fix_rounds: 0
---

## Goal
Living room circadian lights (v3.0.0) treat the FP2 and the FP300 as one presence room. Either sensor on turns the lights on. The lights go off only after both sensors are clear: after presence_timeout normally, and after late_night_timeout (1 min) inside 23:00 to 06:30. An FP300 that is unavailable or unknown for 30 min sends one notify call per configured target.

## Done when (runnable)
- `env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests/test_circadian_livingroom_structure.py -q`
- `env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests -q`

## Files likely touched
- circadian_livingroom.yaml (edit in place, to v3.0.0)
- tests/test_circadian_livingroom_structure.py (new)
- tests/test_circadian_livingroom_deploy.py (edit: one xfail marker)
- Read only, as the pattern to follow: tests/test_bedroom_precool_structure.py, bathroom_heating_rack.yaml (notify convention)

## Bad inputs to handle
- presence_fp2 or presence_fp300 empty or unset (no sensor on one side)
- Both sensors unavailable or unknown (both count as clear, so the off timers run)
- FP300 unavailable or unknown for less than 30 min (no notice yet)
- FP300 unavailable or unknown for 30 min or more (one notice per target)
- late_night_timeout outside 1-60 min (0 or 61)
- late_night_start equal to late_night_end (empty window)
- late_night_start later than late_night_end (crosses midnight: start <= now or now < end)
- notify_targets empty (no notify call) or holding an entry that is not notify.<name> (filtered out, as in bathroom_heating_rack.yaml)
- last_changed missing or None on the other sensor (the re-check must not pass on a missing value)
- Lux sensor unavailable (unchanged v2.2.0 behaviour; the test pins only that it is not newly broken)

## Risk flags
- deploy: the live instance still uses presence_entity and is not migrated here (next card, 2026-10-16-circadian-v3-instance-migration); no HA write in this card
- data/migrations: breaking input change (presence_entity removed, no compatibility alias)
- workflow rules: test-first; the new test must fail on v2.2.0 before the edit; tests/test_circadian_livingroom_deploy.py must not be deleted (xfail only, with a reason naming card 2026-10-16-circadian-v3-instance-migration, and only if it fails from the input mismatch)

## Constraints carried over
- Lane 2 (risk scan). Only Martin may lower it.
- Lux stays FP2 illuminance only, with the blueprint defaults unchanged (150 lx on, 400 lx off, 5 min). The live instance overrides them with 394/611; that is the migration card's concern, not this card's. FP300 lux is not read.
- FP300 counts like FP2 at all times, including the late-night window. This is the accepted dog-guard stay-on. No cap or zone logic.
- Off path: each sensor's own short or long timer fires, then the other sensor must be clear (off, unavailable or unknown) for at least the same duration by last_changed. A both-clear already running when the window opens finishes on presence_timeout. A clear whose 1-min mark falls after 06:30 also finishes on presence_timeout. No extra boundary trigger.
- Unchanged: Night profile 22:00 to 06:00 at 20 percent, independent of the late-night window; profiles, Kelvin and brightness maths; 5-min update loop; the override stop before any light call; transitions; mode: restart. Timers that expire while the override is on are not replayed.
- Notify: selector text, multiple, default []; filter with the notify_list regex ^notify[.][a-z0-9_]+$ as bathroom_heating_rack.yaml does. The notify calls run after the light calls and are sent even while the override is on.
- Tests reuse HassLoader, TZ, _env, _reparse and _var_template from tests/test_bedroom_precool_structure.py. Import those names explicitly, not the module, so its test functions are not collected again. Expectations come from the v3.0.0 contract, not from the implementation. HA's own for: timer is not simulated.

## Out of scope
- Dog cap, time window or zone exclusion; FP300 lux or other readings; zone split; night quiet window; TV or media_player input
- Replaying timers after the override
- Writing FP300 or device settings from the blueprint
- Other blueprints (adjacent_room_lights.yaml, dinner_table_lights.yaml, lg_sleep_movie.yaml)
- README and requirements_circadian.md (next card)
- The deploy instance file and any deploy dry-run (next card)
- Any HA write
- The live overlap audit

## Live facts and decisions (orchestrator, 2026-10-16)
- Live read (GET-only): FP2 presence `binary_sensor.presence_sensor_fp2_e863_presence_sensor_1`, FP300 presence `binary_sensor.living_room_main_fp300_couch_occupancy_sensor`; both device_class `occupancy`. `notify.mobile_app_martin_fold` exists. Full facts: docs/superpowers/research/2026-10-16-livingroom-fp300-live-audit.md and tests/test_circadian_livingroom_deploy.py in the worktree.
- Decided by orchestrator, Martin can revert: selectors for presence_fp2 and presence_fp300 are `entity` with domain binary_sensor and device_class occupancy, the same shape as presence_entity today (the live FP300 reports occupancy, so no list is needed). Neither has a default.
- Decided by orchestrator, Martin can revert: trigger ids as proposed by the drafter: presence_on_fp2, presence_on_fp300, presence_off_long_fp2, presence_off_long_fp300, presence_off_short_fp2, presence_off_short_fp300, fp300_unavailable_30m, fp300_unknown_30m.
- Decided by orchestrator, Martin can revert: the card-1 test file exists (c40839f), so the xfail applies now. Only `test_live_dry_run_pins_four_stale_keys` is xfailed; the missing-required test was written not to depend on key names.
- Decided by orchestrator, Martin can revert: the new test wraps _env in its own Environment with StrictUndefined and adds is_state and a states fake; tests/test_bedroom_precool_structure.py is not edited. Duplicate notify_targets entries each get a call (no dedupe), as in the bathroom blueprint.
- Test-first: red-green runs the new test against the unpatched base, so no extra check is needed.

## Open questions
- none

## Plan
<!-- Planner only: exact files incl. test files, steps, and the test list (one test per
     "Done when" item and per bad input). -->
Planner: Opus, Lane 2 confirmed (physical-world home automation, breaking input change). Coder: `codex` (the orchestrator falls back to Claude if Codex is over its usage limit).

### Files (exactly these three)
1. `tests/test_circadian_livingroom_structure.py`: new.
2. `tests/test_circadian_livingroom_deploy.py`: one decorator only, on `test_live_dry_run_pins_four_stale_keys`: `@pytest.mark.xfail(strict=True, raises=AssertionError, reason="v3.0.0 drops presence_entity; card 2026-10-16-circadian-v3-instance-migration migrates the live instance and removes this test")`. No other line changes.
3. `circadian_livingroom.yaml`: edit in place to v3.0.0.

Read only: `tests/test_bedroom_precool_structure.py` (import `HassLoader, TZ, _env, _reparse, _var_template` by name), `tests/test_bedroom_fan_daytime_structure.py` (the `_strict_env` pattern to copy, not import), `bathroom_heating_rack.yaml` (notify_list and fan-out).

### Steps (test-first)
1. Write the new test file (test list below). It must FAIL on v2.2.0 by assertion, not by a collection error: load the blueprint only inside a `bp` fixture (`yaml.load(..., Loader=HassLoader)`), never at module level; a missing variable is a `KeyError` inside a test body (= failed).
2. Add the strict xfail to the deploy test.
3. Edit the blueprint as designed below. Keep everything not named here byte-identical: the 5-min update loop branch, profiles and the `mode`/`target_kelvin`/`target_brightness`/`ceiling_bri`/`target_effect` maths, lux triggers and thresholds, transitions, `mode: restart`, `max_exceeded: silent`, legacy `trigger:`/`platform:`/`action:`/`service:` keys.
4. Run both Done-when commands. Both were checked on the base tree inside the Frugo check sandbox (bwrap, `--mode check`, export of c40839f): command 1 exits 4 (file missing), command 2 is 420 passed.

### Design v3.0.0

**Header.** `name: "Circadian Living Room Lights v3.0.0"`; description starts `**Version: 3.0.0 - Dual presence (FP2 + FP300)**`; feature bullets add: either sensor on turns lights on; lights off only when both are clear (presence_timeout, or late_night_timeout inside the late-night window); FP300 offline 30 min sends a push to each notify target. Remove the old single-sensor wording.

**Inputs.** Delete `presence_entity` (no alias). Insert, in this order after `ceiling_brightness_scale`:
- `presence_fp2`: name "Presence Sensor (FP2)", selector `entity: {domain: binary_sensor, device_class: occupancy}`, NO default.
- `presence_fp300`: name "Presence Sensor (FP300)", same selector, NO default.
- `presence_timeout`: unchanged (default 5, number 0-60 min); description now "after both presence sensors are clear".
- `late_night_timeout`: name "Late-Night Timeout", default 1, selector `number: {min: 1, max: 60, step: 1, unit_of_measurement: min}`.
- `late_night_start`: default "23:00:00", selector `time:`.
- `late_night_end`: default "06:30:00", selector `time:`.
Append after `min_kelvin`: `notify_targets`: name "Mobile Push Targets", description as the bathroom one (full `notify.` name, others ignored, empty disables, a missing service aborts at the push step), default `[]`, selector `text: {multiple: true}`.
Inputs without default after the edit: exactly `presence_fp2`, `presence_fp300`, `illuminance_entity`. All other input blocks unchanged.

**trigger_variables** (new top-level block, before `trigger:`): `late_night_timeout: !input late_night_timeout` (needed because a trigger `for:` template can only see trigger variables). ALSO add `late_night_timeout: !input late_night_timeout` to the top-level `variables:` block: it is not shown that trigger_variables are readable in action templates, and HA's forgiving `int(1)` would otherwise turn the value into 1 in the re-check (design review P2).

**Triggers** (ids decided; keep this order):
| id | platform/entity | to | for |
|---|---|---|---|
| presence_on_fp2 | state, `!input presence_fp2` | "on" | none |
| presence_on_fp300 | state, `!input presence_fp300` | "on" | none |
| presence_off_long_fp2 | state, `!input presence_fp2` | ["off", "unavailable", "unknown"] | `minutes: !input presence_timeout` |
| presence_off_long_fp300 | state, `!input presence_fp300` | same list | `minutes: !input presence_timeout` |
| presence_off_short_fp2 | state, `!input presence_fp2` | same list | `minutes: "{{ [1, [60, late_night_timeout \| int(1)] \| min] \| max }}"` |
| presence_off_short_fp300 | state, `!input presence_fp300` | same list | same template, identical text |
| update_loop, lux_high, lux_low, override_resume | unchanged | | |
| fp300_unavailable_30m | state, `!input presence_fp300` | "unavailable" | `minutes: 30` |
| fp300_unknown_30m | state, `!input presence_fp300` | "unknown" | `minutes: 30` |
(`\|` in the table is Markdown escaping only; the YAML uses a plain `|`.) No `from:` on any presence trigger: every move into the clear set (including unavailable to off) re-arms that sensor's own timer, and that is the same event that sets its `last_changed`, so timer and re-check stay in step.

**Top-level variables.** Replace `sensor_presence` with `presence_fp2: !input presence_fp2`, `presence_fp300: !input presence_fp300`; add `presence_timeout: !input presence_timeout`, `late_night_start: !input late_night_start`, `late_night_end: !input late_night_end`, `notify_targets: !input notify_targets`. Everything else unchanged.

**Action step 1 (override stop, still first, still before any light call).** Only the condition changes, so the notice still runs while the override is on:
`"{{ entity_override != [] and is_state(entity_override, 'on') and trigger.id | default('') not in ['fp300_unavailable_30m', 'fp300_unknown_30m'] }}"`. Off timers that expire while the override is on hit the stop and are not replayed.

**Action step 2 (variables).** `current_lux` unchanged. Replace `is_presence_on`, then add, in this order, before `mode:`:
- `is_presence_on: "{{ (presence_fp2 is string and presence_fp2 | length > 0 and is_state(presence_fp2, 'on')) or (presence_fp300 is string and presence_fp300 | length > 0 and is_state(presence_fp300, 'on')) }}"` (an empty side is `[]`, `''` or none and is never passed to `is_state`).
- `late_night_minutes: "{{ [1, [60, late_night_timeout | int(1)] | min] | max }}"` (same clamp text as the trigger).
- `in_late_window`: `{% set t = now().strftime('%H:%M:%S') %}` then: start < end gives `start <= t and t < end`; start > end (crosses midnight) gives `start <= t or t < end`; start == end gives `{{ false }}` (empty window). End is exclusive at one-second resolution.
- `presence_off_ok` (the off re-check):
  ```
  {% set tid = trigger.id | default('') %}
  {% set short_ids = ['presence_off_short_fp2', 'presence_off_short_fp300'] %}
  {% set off_ids = ['presence_off_long_fp2', 'presence_off_long_fp300'] + short_ids %}
  {% if tid not in off_ids or (tid in short_ids and not in_late_window) %}{{ false }}
  {% else %}
    {% set other = presence_fp300 if tid in ['presence_off_long_fp2', 'presence_off_short_fp2'] else presence_fp2 %}
    {% set minutes = late_night_minutes if tid in short_ids else presence_timeout %}
    {% if not (other is string and other | length > 0) %}{{ true }}
    {% else %}
      {% set st = states[other] %}
      {% set lc = st.last_changed if (st is not none and st.last_changed is defined) else none %}
      {{ states(other) in ['off', 'unavailable', 'unknown'] and lc is not none
         and as_timestamp(now()) - as_timestamp(lc) >= (minutes | float(0)) * 60 }}
    {% endif %}
  {% endif %}
  ```
  Booleans must be `{{ true }}`/`{{ false }}`, never bare text (bare `false` renders the truthy string "false"). The long trigger acts at any time of day (so a both-clear already running when the window opens finishes on presence_timeout); the short trigger acts only when `in_late_window` is true at the moment it fires (so a 1-min mark at or after 06:30:00 finishes on presence_timeout). Inside the window the effective timeout is therefore min(presence_timeout, late_night_timeout). The firing sensor itself needs no re-check: HA's `for:` already held it clear.
- `notify_list`: exactly the bathroom text `"{{ (notify_targets if (notify_targets is iterable and notify_targets is not string) else ([notify_targets] if notify_targets else [])) | select('match', '^notify[.][a-z0-9_]+$') | list }}"` (no dedupe).

**Action step 3 (light choose).** SCENARIO 1 TURN OFF: `or` of template `"{{ presence_off_ok }}"` and trigger `lux_high`; sequence unchanged. SCENARIO 2 TURN ON: the `presence_on` trigger condition becomes `id: ["presence_on_fp2", "presence_on_fp300"]`; rest unchanged. SCENARIO 3 unchanged.

**Action step 4 (new, last top-level step).** `choose` with one branch: condition template `"{{ trigger.id | default('') in ['fp300_unavailable_30m', 'fp300_unknown_30m'] }}"`; sequence: `repeat: for_each: "{{ notify_list }}"` with one step `service: "{{ repeat.item }}"`, `continue_on_error: true`, data `title: "Living Room Lights - FP300 offline"`, `message` naming `{{ presence_fp300 }}`, its state from the trigger id (unavailable or unknown), "for 30 min", and that the lights follow the FP2 alone until it returns. No persistent notification.

### Off-path correctness notes (documented, not fixed)
- Convergence: each sensor's timer fires T after its own last move into the clear set and checks the other's `last_changed`. Of two clears at tA <= tB, A's check fails and B's passes at tB + T, so lights go off exactly T after the later clear. A flapping sensor re-arms its own timer and moves its `last_changed`, so the same rule holds. Equal instants cannot happen (separate state writes).
- mode: restart: actions take milliseconds; an on-event racing an off-run either sees the sensor on (no off) or restarts/follows the off-run with a turn-on.
- Midnight: the window test crosses midnight by string compare; `last_changed` maths uses timestamps, so it is DST-safe; the Night profile (22:00-06:00) stays independent of the window.
- HA restart or automation reload drops running `for:` timers, and sensors already clear at start never arm one (same as v2.2.0). The 30-min notice also needs a transition while the automation runs.
- Unavailable and unknown are separate notice triggers (decided ids), so a sensor alternating between them resets the 30 min and sends nothing.
- A configured other sensor with no state object or no `last_changed` never passes the re-check (contract), so the lights stay on; that sensor also never sends the notice.
- An empty side given as `''` passes the template guards, but HA rejects `''` as a trigger `entity_id`, making the whole automation invalid; only `[]` works as "no sensor" (null is also probably rejected as a trigger entity_id). Not testable here (HA config validation is not simulated).

### Test list (`tests/test_circadian_livingroom_structure.py`)
Harness: `bp` and `text` fixtures; `_strict_env(now, table)` = `_env(now)` + `env.undefined = StrictUndefined` + `env.tests["match"]` (HA's match test) + strict `states` (callable and subscript) and `is_state` that raise `TypeError` on a non-string id; a `_St(state, last_changed)` fake and a `_NoLc` fake without `last_changed`; `_chain(bp, names, now, ctx)` renders each `_var_template` in order and feeds the `_reparse`d value forward. Ids: `FP2 = "binary_sensor.fp2"`, `FP300 = "binary_sensor.fp300"`. Dates in TZ.
1. `test_the_fakes_are_strict`: is_state/states/states[] raise on a list id; undefined names raise.
2. `test_version_is_3_0_0`: name ends `v3.0.0`, description contains `**Version: 3.0.0`.
3. `test_presence_inputs_replace_presence_entity`: no `presence_entity` anywhere in the text; `presence_fp2`/`presence_fp300` selectors equal `{"entity": {"domain": "binary_sensor", "device_class": "occupancy"}}`, no `default`.
4. `test_required_inputs_are_the_two_sensors_and_lux` (bad input: sensor unset): no-default set == {presence_fp2, presence_fp300, illuminance_entity}.
5. `test_late_night_inputs`: late_night_timeout default 1, number min 1 max 60; start "23:00:00", end "06:30:00", time selectors.
6. `test_notify_targets_input`: default `[]`, selector `{"text": {"multiple": True}}`.
7. `test_inputs_reach_templates`: top-level variables map presence_fp2, presence_fp300, presence_timeout, late_night_start, late_night_end, notify_targets and late_night_timeout to `!input` of the same name; trigger_variables maps late_night_timeout too (both places pinned).
8. `test_trigger_table`: ids, entity inputs, `to` and `for` exactly as the table; update_loop/lux_high/lux_low/override_resume equal their v2.2.0 shapes; `mode == "restart"`.
9. `test_either_sensor_on_turns_lights_on`: is_presence_on for (on, off), (off, on) True; (off, off), (unavailable, unknown) False; TURN ON condition ids == both presence_on ids.
10. `test_empty_side_counts_as_clear` (bad input: empty): with FP300 in `[]`, `''`, None (template behaviour only; HA accepts just `[]` as an empty entity list): is_presence_on follows FP2 alone; presence_off_ok True for long_fp2 with no other sensor; mirror with FP2 empty and long_fp300.
11. `test_off_needs_other_clear_for_presence_timeout` (14:00): long_fp2 with FP300 off for 5:00 True, 4:59 False, on for 10 min False; symmetric long_fp300.
12. `test_both_unavailable_or_unknown_count_as_clear` (bad input): FP300 unavailable / unknown for 6 min, long_fp2 True; is_presence_on False with both unavailable.
13. `test_other_last_changed_missing_or_none_fails` (bad input): `_St("off", None)`, `_NoLc`, and FP300 absent from the table each give False, and nothing raises.
14. `test_short_timer_only_inside_window`: short_fp2 at 14:00 with FP300 clear 2 h False; at 23:30 with FP300 clear 1:00 True, 0:59 False; long_fp2 at 23:30 with 5 min True.
15. `test_window_edges_cross_midnight` (bad input: start > end): in at 23:00:00, 00:00:00, 06:29:59; out at 22:59:59, 06:30:00, 12:00.
16. `test_window_start_equals_end_is_empty` (bad input): 23:00/23:00 never in (23:00:00, 03:00, 12:00); short_fp2 False at 23:30.
17. `test_window_not_crossing_midnight`: 01:00-05:00: in at 01:00:00, 04:59:59; out at 00:30, 05:00:00, 23:30.
18. `test_off_across_midnight`: long_fp2 at 00:02 with FP300 clear since 23:57 the day before True; short_fp2 at 00:00:30 with FP300 clear since 23:59:00 True.
19. `test_late_night_timeout_clamped` (bad input 0 / 61): late_night_minutes and the rendered short-trigger `for.minutes` agree: 0 gives 1, 1 gives 1, 60 gives 60, 61 gives 60, "abc" gives 1; the two template texts are identical.
20. `test_non_off_triggers_never_turn_off`: presence_off_ok False for presence_on_fp2, update_loop, lux_high, fp300_unavailable_30m and ''; TURN OFF still also matches lux_high.
21. `test_notify_list_filters_targets` (bad input: notify): `[]` gives []; mixed list keeps only `notify.mobile_app_martin_fold`; duplicates kept twice; scalar string wrapped.
22. `test_fp300_notice_one_call_per_target` (bad inputs: >= 30 min and < 30 min): notice triggers are `to` unavailable / unknown with `for: {minutes: 30}` (HA times the 30 min; < 30 min means the trigger has not fired, so no other trigger id reaches the notice); the branch condition renders True only for the two notice ids; the repeat is `for_each: "{{ notify_list }}"`, one `service: "{{ repeat.item }}"` step with `continue_on_error: true`; with targets `[a, a, "bad"]` the for_each renders 2 items.
23. `test_notice_runs_after_light_calls_and_through_override`: top-level index override stop (0) < light choose < notice step (last); rendered override condition with override on is False for both notice ids and True for presence_on_fp2 and presence_off_long_fp2; with override `[]` False.
24. `test_night_profile_independent_of_window`: `mode` renders night at 22:30 (window not open) with brightness 20, day at 06:15 (window open).
25. `test_lux_unavailable_not_newly_broken` (bad input): current_lux renders 0.0 for an unavailable lux sensor; lux inputs default 150/400/5; lux triggers read only `illuminance_entity`.
26. `test_deploy_dry_run_pin_is_xfailed_for_the_migration_card` (Done when 2: keeps the full suite green): AST of the deploy test file shows exactly one xfail marker, on `test_live_dry_run_pins_four_stale_keys`, `strict=True`, reason containing `2026-10-16-circadian-v3-instance-migration`.
Done when 1 is the file above (tests 1-26; test 26 needs the xfail edit in the deploy test file, step 2); Done when 2 is the full suite, where the other deploy tests stay green against v3.0.0 (bad id, missing required input and owner-less path still fail the dry-run for their own reason).

### Gaps reported to the orchestrator (no decision reopened)
- late_night_timeout 0 / 61 had no stated outcome. Decided by planner: clamp to 1-60 in both the short-trigger `for:` (via trigger_variables) and the re-check, so the two stay equal.
- "empty or unset" sensor vs "no default": unset is a required-input error (the dry-run and HA refuse the instance); empty is `[]` (works); null and `''` are template-only cases that HA probably rejects as a trigger entity_id.
- Accepted risk (design review P3): the 30-min FP300 notice fires once; if another trigger restarts the run (mode: restart) while the notify calls run, that push is lost. The window is milliseconds. Documented in the Result, not fixed.
- The notice-through-override rule needs the override stop condition to exclude the two notice ids; the stop stays first and before any light call.

## Result
Passed Lane 2 review: v3.0.0 dual-presence blueprint, 26+ structure tests and the single strict xfail are applied in worktree Blueprints_Home-wt/circadian-v3 (branch frugo/circadian-v3-blueprint, uncommitted, based on c40839f). Coder: Codex. Red-green: both Done-when commands RED on the base (58 and 477 tests), GREEN after. Full suite run by the orchestrator on the patched tree: 477 passed, 1 xfailed (the planned xfail). Reviews: Opus correctness FINDINGS (one P2 = missing green evidence, resolved by that run; two P3) and Codex security FINDINGS (two P3). Design reviews were PASS (Codex) and FINDINGS fixed (Opus).
Note: the coder's diff lacked the `new file mode` line for the new test file, which git apply rejects; the orchestrator added that one header line to a copy of the diff (c2-coder1-fixed.md) before red-green and apply.
Open P3:
- Window edge: the short timer checks only that it fires inside 23:00-06:30, not that the both-clear began inside it. A clear that began at 22:59:30 with the other sensor clear since 22:50 turns the lights off at 23:00:30 instead of 23:04:30, which contradicts the card's "a both-clear already running when the window opens finishes on presence_timeout" (the lights go off earlier, not later). Fix: also require now() - late_night_minutes to fall inside the window, plus a test.
- mode: restart can cancel the 30-min FP300 notice during delivery (another trigger restarts the run while the notify calls run). The window is milliseconds and no retry exists; accepted, documented. A separate queued script for delivery would remove it.
- Whether null or an empty string for presence_fp2/presence_fp300 is rejected by HA as a trigger entity_id is untested (only an empty list is safe); the blueprint's required-input rule already blocks unset values.
