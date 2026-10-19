---
id: 2026-10-19-livingroom-music-start-volume
title: "Start 0.07 and approval above 0.20"
goal: livingroom-background-music
issue: "leviemartin/Blueprints_Home#55"
status: done
lane: 2
coder: codex
step: codex
fix_rounds: 3
---

## Goal
Martin (2026-10-19, after listening live): the background music starts too loud at 0.15. Change the livingroom_music package on main (deployed live) so that music starts at 0.07, the free ladder outside kids time is 0.07, 0.10, 0.15, 0.20, and 0.25 and 0.30 are only possible inside kids time after one approval. The ladder keeps six indices: [0.07, 0.10, 0.15, 0.20, 0.25, 0.30]. Index 0 (0.07) is the start, the dim floor and the default for every fallback. Brighten at index 3 (0.20) inside kids time without an approval sends the approval push (this was index 4); Approve sets index 4 (0.25) and the next brighten gives index 5 (0.30). Dim always works inside an approved kids time: a dim press from 0.30 or 0.25 goes down even when presence is off or a phone session is on. Outside an approved kids time the free ladder is 0.07 to 0.20, and a stale or forced step above 3 is dropped. This card changes constants and thresholds, plus one `down` variable that lets a real approved dim skip the presence and `*may_start` checks: no new helpers or guards.

## Done when (runnable)
`env -u HASS_TOKEN ~/.local/share/home-security/ha-test-venv/bin/python -I -m pytest -q -p no:cacheprovider -c ha/tests/pytest-ha.ini ha/tests`
`env -u HASS_TOKEN ~/.local/share/home-security/ha-test-venv/bin/python -I -m pytest -q -p no:cacheprovider -c ha/tests/pytest-ha.ini ha/tests/test_ha_livingroom_music_core.py ha/tests/test_ha_livingroom_music_remote_volume.py ha/tests/test_ha_livingroom_music_remote_kids.py`
`env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests -q`

## Files likely touched
- `ha/packages/livingroom_music.yaml` (about 20 changed lines, Plan step 1)
- `ha/tests/test_ha_livingroom_music_core.py` (one line, Plan step 2)
- `ha/tests/test_ha_livingroom_music_remote_volume.py` (Plan step 3)
- `ha/tests/test_ha_livingroom_music_remote_kids.py` (Plan step 4)
- `.frugo/goals/livingroom-background-music.md` (untracked, Plan step 5; one line)
- `ha/tests/conftest.py`, `ha/tests/pytest-ha.ini`: read only, unchanged

## Bad inputs to handle
- Brighten at index 3 (0.20) outside kids time, or in the cooldown: no push, no volume_set, step stays 3.
- Brighten at index 3 inside kids time without a live approval: exactly one approval push to both phones, no volume_set; a second press while the push is pending sends nothing.
- Step helper forced to 4 or 5 without a live approval (outside kids time, approval forced on with another session, kids timer idle): the volume script drops it, no volume_set.
- Restart: the step helper has `initial`, so it comes back at 0 (0.07) whatever value it had; the speakers keep their last level until the next press or fresh start (existing rare corner).
- Restart with the pre-kids helper restored at an old value of 4 (possible from the old ladder): its new max is 3, and HA's input_number restore rejects an out-of-range value and uses min (0), so the reset level is 0.07 (checked in the venv: `homeassistant/components/input_number/__init__.py`, `async_added_to_hass`).
- Pre-kids step unknown, unavailable or out of 0..3 at kids start, kids end or a cleanup write: written as 0; the reset sends 0.07.
- Dim at index 0 (0.07): nothing.
- Dim from index 5 (0.30) or 4 (0.25) inside an approved kids time (kids on, kids timer active, approved on, approval session equals kids session) with presence off or a phone session on: goes down one step each press (0.25, then 0.20). Hands-off, an unavailable speaker, a stale press session or an out-of-range step still drop a dim.
- Dim from a forced or stale step 5 outside kids time, or in kids time whose approval belongs to another session or whose timer is idle: dropped, no volume_set (from a forced 4 the dim lands on the free 0.20).
- Mixed arguments `step` plus `delta` (for example `step: 5, delta: -1` or `step: 4, delta: -1`): `step` wins, the run is never a dim, and without a live approval it sends nothing.
- Kids start with the step forced to 4 or 5: pre-kids recorded as 0.
- Index 6 and above, or a non-integer step: dropped (unchanged `s in [0..5]` check).
- The fresh start's 0.07 still passes the volume script's free-cap check (`s <= 3`), its `*may_start` checks and Hands-off.
- Approve, Deny, timeout, stale or unknown id, late approve after kids end, answer during delivery: unchanged rules; only the granted level changes (0.25 instead of 0.30).
- Hands-off, phone session, Off, unavailable speakers, quiet hours: unchanged.

## Risk flags
- physical safety: speaker volume; the free cap drops to 0.20 and tests assert that no path, dims and mixed `step`/`delta` calls included, sends 0.25 or 0.30 without the live approval.
- product change in approval: Approve now gives 0.25 (was 0.30); 0.30 needs one more brighten after Approve. Martin asked for this (orchestrator relays it).
- deploy: out of scope; the package is live, so the change takes effect only after a separate deploy with Martin's OK.
- workflow rules: Lane 2 for the goal.

## Constraints carried over
- Lane 2 for the whole goal; only Martin lowers a lane.
- Base: current main (cfd4c14 or later). Branch `frugo/2026-10-19-livingroom-music-start-volume`, worktree `Blueprints_Home-wt/lm-start07` (the orchestrator creates them).
- Sonos queue only. Speakers media_player.sonos and media_player.bedroom get the same fixed volume_set; no read-modify-write on reported volume.
- Every volume write still goes through `script.livingroom_music_volume` or `script.livingroom_music_volume_reset`.
- Read only, never a service call: media_player.marantz_cinema_50, media_player.mxn10, media_player.lg_webos_tv_oled65c9pla, alarm_control_panel.house_alarm.
- Tests run with env -u HASS_TOKEN; tests hold no token and no URL. New or changed tests live under ha/tests/.
- Budget: track only, warn line 500,000 tokens per card.

## Out of scope
- Deploying to HA, reloading, or any live call.
- Any new helper, script, automation, guard or test file; any change to the approval lifecycle (only inside kids time, lasts until kids time ends, kids-end reset to the pre-kids level).
- The start, pause, resume, quiet-hours, Hands-off and phone-session rules.

## Open questions
none

## Decided by orchestrator
- Martin, 2026-10-19 (typed, after listening live, replaces his earlier "start at 0.05"): start 0.07 at index 0; ladder [0.07, 0.10, 0.15, 0.20, 0.25, 0.30]; dim floor 0.07; free indices 0..3; one approval unlocks both 0.25 and 0.30, only inside kids time, until kids time ends; brighten at index 3 inside kids time without approval opens the push; Approve writes index 4 (0.25).
- Planner: one default everywhere: every fallback that wrote step 2 (or level 0.15) now writes step 0 (level 0.07). This includes the pre-kids fallbacks at kids start, at kids end and in the volume script's cleanup write, and the reset's `restore_level` fallback.
- Planner: the pre-kids helper's max drops from 4 to 3 and its valid set to [0, 1, 2, 3], because a kids session can only start from a free step; the reset list shrinks to the four free levels.
- Planner: the approval encoding stays "approved on + approval session equals kids session"; the threshold that needs it moves from `s <= 4` / `level <= 0.25` to `s <= 3` / `level <= 0.20`, so both 4 and 5 need it. The start-guard's no-`*may_start` shortcut for remote presses moves from `s <= 4` to `s <= 3` as well, so approved 0.25 presses take the same `*may_start` path that 0.30 presses took (consistent: both are approval levels). The debt-clear branch's `level <= 0.25` becomes `level <= 0.20` (free presses only).
- Orchestrator, design round 1 (P1, consistent with the goal's 'dim always works'), narrowed in design round 2 (security P1, correctness P2): a real approved dim skips the presence and `*may_start` parts of the approval-level checks. Encoding: the volume script gets one variable `down`, true only for a `delta < 0` run without `step`, inside an approved kids time (kids on when the run started, kids timer active, approved on, approval session equals kids session; the existing expressions of the approval condition minus presence). The three approval-level checks (approval condition, start guard, final level condition) each accept `down` as an alternative. A dim still passes Hands-off, both-speakers-available, the `s in [0..5]` range and the press-session checks. A `step` call (even with a `delta`), a forced step or a dim outside an approved kids time is never `down`, so nothing above 0.20 is sent without the live approval.
- Planner (round 2): `down` also requires the kids timer to be active, as the approval condition does, so a forced kids-on/approved state with an idle timer cannot send 0.25 on a dim (the `approved_forced_timer_idle` case of test 33).
- Orchestrator, design round 1 (P2 both reviewers): the four `max(volumes(services)) <= 0.25` asserts in the kids tests become `<= 0.20`. P3s: steps 4 and 5 join `test_step_invalid_at_on`; a restored pre-kids 4 and invalid pre-kids values at kids end get cases in `test_volume_restore_retry`; the approval_request description is reworded.
- Planner: no quiet-hours dim case: the 22:00 pause ends kids time and resets the volume, so kids time cannot run in quiet hours (the existing quiet tests cover that path).
- Planner: tests are updated in place; three tests are renamed or re-parametrized because the old case no longer exists (Plan step 3 and 4).

## Plan
Planner: Opus, 2026-10-19, revision 3 (final) (design round 2 fixes: one P1, one P2, one P3: `down` narrowed to a real approved dim with no `step` (item 4a); item 33 adds mixed-argument and forced-step dim checks. The scratch runs were repeated: 311 HA tests and 780 in tests/ pass; 116 HA tests fail against the unchanged main package (RED); with revision 2's broad `down`, 8 cases of test 33 fail; no further design rounds). Revision 2 (design round 1 fixes: one P1, three P2s, three P3s: dims skip the approval-level checks (items 5, 6, 8, 4a), four test bounds go to 0.20 (item 42), new test cases (items 27, 29, 43, 44), description wording (item 13a)). Revision 1: first plan. Lane 2. Coder: `codex`. The planner ran revision 2 on a scratch copy of main: all three Done-when commands pass (311 HA tests, 780 in tests/). The HA suite with the changed tests fails 116 tests against the unchanged main package (RED). Without the `down` rule, two of the new `test_dim_always_works` cases fail. These are planner scratch runs; the code-phase checks are the evidence.

### Coder scope
The coder implements the numbered changes (Steps 1 to 5) and the numbered test edits exactly as written. BLOCKED is only for a contradiction inside the plan that makes a numbered test or rule impossible to satisfy. A concern outside the numbered edits goes in a DONE_WITH_CONCERNS note, not into extra code.

### Step 1: package `ha/packages/livingroom_music.yaml` (exact replacements, nothing else)
1. `input_number.livingroom_music_volume_step`: `initial: 2` becomes `initial: 0` (max stays 5).
2. `input_number.livingroom_music_pre_kids_step`: `max: 4` becomes `max: 3`.
3. `script.livingroom_music_fresh_start`: the volume call's `step: 2` becomes `step: 0`.
4. Volume script `level:` list `[0.05, 0.10, 0.15, 0.20, 0.25, 0.30]` becomes `[0.07, 0.10, 0.15, 0.20, 0.25, 0.30]` (the `s in [0, 1, 2, 3, 4, 5]` checks stay).
4a. In the same `variables:` step, directly after `k0:` (it uses `kids_was_on`), add exactly:
`down: "{{ step is not defined and delta is defined and (delta | int) < 0 and kids_was_on and is_state('timer.livingroom_music_kids', 'active') and is_state('input_boolean.livingroom_music_approved', 'on') and (states('input_number.livingroom_music_approval_session') | int(-2)) == (states('input_number.livingroom_music_kids_session') | int(-1)) }}"`
5. Volume script approval condition `"{{ s <= 4 or (is_state('input_boolean.livingroom_music_kids', ...` becomes `s <= 3 or down or (` (rest unchanged).
6. Volume script anchor `&volume_start_guard`: `{{ step is not defined and s <= 4 }}` becomes `{{ step is not defined and (s <= 3 or down) }}`.
7. Volume script cleanup write, kids_start pre-kids write and kids_end step write (three places): the valid set `in [0, 1, 2, 3, 4] else 2` becomes `in [0, 1, 2, 3] else 0`.
8. Volume script final condition: `and (level <= 0.25 or (` becomes `and (level <= 0.20 or down or (`.
9. Volume script debt-clear branch: `and end_was_off and level <= 0.25 and` becomes `level <= 0.20`.
10. `script.livingroom_music_volume_reset` `restore_level`: `[0.05, 0.10, 0.15, 0.20, 0.25][p | int] if p in [0, 1, 2, 3, 4] else 0.15` becomes `[0.07, 0.10, 0.15, 0.20][p | int] if p in [0, 1, 2, 3] else 0.07`.
11. `script.livingroom_music_approval_request` and the approval_answer grant check (two places): `float(-1) == 4 }}` becomes `float(-1) == 3 }}`.
12. approval_answer grant call to the volume script: `step: 5` becomes `step: 4` (session unchanged). Approve now sends 0.25.
13. Remote `up` branch: `{{ s == 4 and is_state('input_boolean.livingroom_music_kids', 'on')` becomes `s == 3`.
13a. `script.livingroom_music_approval_request` description: `the final kids volume step` becomes `the kids volume steps above 0.20`.
After the step: `0.05`, `0.25]` and `else 2` no longer occur in the file; `0.30` occurs once; `0.25` occurs only in the six-entry list.

### Step 2: `ha/tests/test_ha_livingroom_music_core.py`
14. Helper `fresh`: `observed[0][1]["volume_level"] == 0.15` becomes `== 0.07` (RED on main; 32 core and kids cases use it).

### Step 3: `ha/tests/test_ha_livingroom_music_remote_volume.py`
15. `test_volume_text_rules`: the six-entry literal becomes `"[0.07, 0.10, 0.15, 0.20, 0.25, 0.30]"`; the five-entry literal becomes the four-entry `"[0.07, 0.10, 0.15, 0.20]"` (count 1 each). The `<= 0.30` and `0.30` count-1 rules stay.
16. Step-after-load asserts `float(hass.states.get(STEP).state) == 2` become `== 0` in `test_volume_package_loads`, `test_hands_off_ignores_remote`, `test_volume_script_guards`, `test_speakers_unavailable`.
17. `test_brighten_dim_ladder`: buttons `[2] * 4 + [3] * 3` from step 0; volumes `[0.10, 0.15, 0.20, 0.15, 0.10, 0.07]` (the fourth brighten at 0.20 sends nothing); final step 0.
18. `test_off_queued_behind_hands_off`: `[0.20]` becomes `[0.10]`.
19. `test_brighten_cap`: preset step 3 (was 4), final step 3, still no calls (free cap 0.20, also in phone session).
20. `test_volume_in_phone_session`: up gives `[0.10]`, step 1; dim gives `[0.10, 0.07]`, step 0.
21. `test_fresh_start_and_press_ordering`: the held direct run uses `{"step": 1}` (was 0); expected `[0.10, 0.15, 0.07]` for press_then_fresh and `[0.10, 0.07, 0.10]` for fresh_then_press; the fresh call is found by `volume_level == 0.07`; final step `0 if press_then_fresh else 1`.
22. `test_guard_change_during_step_write`: final step `== 1` (was 3).
23. `test_fresh_start_guard_in_queue`: preset step 2 (was 3); after the held up press step is 3 (was 4); final volumes `[0.20]` (was 0.25) and step 3 (was 4).

### Step 4: `ha/tests/test_ha_livingroom_music_remote_kids.py`
24. Fixture `music`: for `approved or pending` the preset before the up press is `"value": 3` (was 4). Approved sessions now sit at step 4 (0.25).
25. Every `step=4` argument to `music(...)` becomes `step=3` (11 calls).
26. `test_brighten_cap_in_cooldown`: preset `"value": 3` (was 4).
27. `test_dim_always_works` (no new fixture args): cases `["kids_approved", "cooldown", "at_030", "presence_off", "phone_session"]`. kids_approved expects `[0.20]` (was 0.25); cooldown stays `[0.15]`. For the three new cases: after `music(kids=True, approved=True)` press 2 and assert STEP `"5.0"`; then presence_off does `put(FP2, "off")` and phone_session does `put(SONOS, "playing", PHONE)`; clear records; press 3 twice; assert volumes `[0.25, 0.20]`, STEP `"3.0"`, KIDS on.
28. `test_kids_package_loads`, `test_volume_restore_retry[restart_with_debt]`, `test_on_speakers_unavailable`: STEP `"2.0"` becomes `"0.0"`.
29. `test_step_invalid_at_on`: parametrization adds `"4"` and `"5"` (now `["unknown", "unavailable", "-1", "4", "5", "6", "2.5"]`); PRE `"2.0"` becomes `"0.0"`. `test_kids_time_from_silence`: first volume_set `0.07` (was 0.15), PRE `"0.0"`.
30. `test_approve_gives_030` renamed `test_approve_unlocks_025_and_030`, cases `["at_step_3", "after_dim"]`: Approve sends `[0.25]` for at_step_3 (none for after_dim); then buttons `[2, 3]` (at_step_3) give `[0.30, 0.25]`, buttons `[2, 2, 2]` (after_dim) give `[0.20, 0.25, 0.30]`; no pushes.
31. `test_first_answer_wins` and `test_answer_during_delivery[approve]`: `[0.30]` becomes `[0.25]`.
32. `test_late_grant_after_kids_end` and `test_pending_cleared_at_kids_end`: `assert 0.30 not in volumes(services)` becomes `assert max(volumes(services), default=0) <= 0.20`.
33. `test_no_030_without_approval`: `all(v <= 0.25 ...)` becomes `<= 0.20`; the forced-step tail runs for `"4"` and `"5"` in a loop: records cleared, `put(STEP, forced)`, `volume_direct(hass)`, `volume_direct(hass, step=int(forced), delta=-1)`, assert no volumes; then `press(hass, 3)` and assert `max(volumes(services), default=0) <= 0.20`. Its cases already cover outside kids time, kids without an answer, after Deny or timeout, the cooldown and the forced approvals (outside kids, timer idle, other session).
34. `test_reset_after_delayed_030` and `test_paused_approval_obeys_stop_rules`: delete the `await press(hass, 3)` right after `music(...)` (the approved session already sits at 4, so the next brighten is the 0.30 step).
35. `test_kids_end_playback_fails[delayed_015]`: `[0.15, 0.05, 0.05]` becomes `[0.15, 0.07, 0.07]`.
36. `test_kids_start_waits_for_fresh_start`: case `dim_not_held` becomes `press_not_held` and presses button 2 (was 3): `[0.07, 0.10]`, STEP `"1.0"`; final volumes `[0.07, 0.10]` for press_not_held else `[0.07]`; PRE `"1.0"` for press_not_held else `"0.0"`.
37. `test_press_races_kids_end`: the held level is `0.20` (was 0.25); `level = 0.10 if pre else 0.07`.
38. `test_kids_end_during_step_write`: the interrupt fires on step value `4` (was 5).
39. `test_press_inside_kids_end_cleanup[write_held]`: the held write is value `3` (was 4).
40. `test_disconnect_during_volume_dispatch[ladder]`: after `music(...)`, set STEP to 2 (`input_number.set_value`, blocking) before starting RT, so the dim still sends 0.10 and the reconnect resets at 0.20.
42. `max(volumes(services)) <= 0.25` becomes `<= 0.20` in all four places: `test_restart_mid_cleanup`, `test_press_races_kids_end`, `test_kids_end_during_step_write`, `test_press_inside_kids_end_cleanup`.
43. `test_volume_restore_retry`: add cases `"restart_old_pre_4"`, `"end_pre_unknown"`, `"end_pre_4"`. The restart branch runs for `restart_with_debt` (restored PRE `"3"`: `[0.20, 0.20]`) and `restart_old_pre_4` (restored PRE `"4"`: `[0.07, 0.07]`); both assert STEP `"0.0"` and both debts off, then return.
44. Same test, `end_pre_*` branch: `music(kids=True, approved=True)`, `put(PRE, "unknown" or "4")`, clear records, `advance(1800)`; assert volumes `[0.07, 0.07]`, STEP `"0.0"`, both debts off, then return.

### Step 5: goal file (untracked)
41. In `.frugo/goals/livingroom-background-music.md`, the line starting `- Volume: start 0.15;` becomes: `- Volume: start 0.07; free steps 0.10, 0.15, 0.20; 0.25 and 0.30 only inside kids time after one approval (Approve gives 0.25, the next brighten 0.30); approval lasts until kids time ends, then volume returns to its pre-kids level. Fixed volume_set on both Ones, ladder index in a helper, no read-modify-write on reported volume.` Also: the Remote line's `floor 0.05` becomes `floor 0.07`; `at 0.15` in the Phone play line and `at 0.15` in the Done-when summary become `at 0.07`, and that summary's `volume ladder 0.05 to 0.25 and no 0.30 outside kids time or without approval` becomes `free ladder 0.07 to 0.20 and no 0.25 or 0.30 outside kids time or without approval`; the Loud volume risk line becomes `0.25 and 0.30 are reachable only inside kids time with a live approval. The tests assert that no path sets more than 0.20 otherwise, ...` (rest unchanged).

### Rare corners (accepted, no extra rule)
- After deploy and restart the step is 0 while the speakers keep the old level until the next press or fresh start resyncs both.
- A kids session started while the step is somehow 4 or 5 (not reachable outside kids time) records pre-kids 0, so its reset goes to 0.07 (test 29).
- A dim that was queued before Hands-off or a speaker drop is still dropped by those checks. An approved dim only lowers the level, and only inside the approved kids time.

### Risks
- A failing test outside the edits listed here means a package edit went beyond Step 1.

## Result
<!-- First line: the result. Then "Open P3:" followed by "- " bullets for Martin, or "none". -->
The music now starts at 0.07 (step 0 of [0.07, 0.10, 0.15, 0.20, 0.25, 0.30]); the free steps are 0.07 to 0.20, and 0.25 and 0.30 need one live Approve inside kids time. It is built and uncommitted on branch frugo/2026-10-19-livingroom-music-start-volume (worktree Blueprints_Home-wt/lm-start07, based on main cfd4c14): about 20 changed lines in ha/packages/livingroom_music.yaml plus updates to the three existing HA test files. All three Done-when commands pass (319 HA tests, 215 in the two changed modules, 780 in tests/); the HA commands are red on the clean base. Lane 2: two design rounds (the design arbiter could not run because the Claude login was due for renewal; Martin's earlier decision for card 3 was reused: one final narrow revision, then build), 1 code fix round, 2 code-review rounds (Codex security PASS, Opus correctness P3 only).
Product consequences (Martin chose these): Approve now gives 0.25, and one more brighten gives 0.30; the remote stops at 0.20 outside kids time; inside kids time, brighten at 0.20 opens the Approve/Deny push; dimming from 0.30 or 0.25 inside an approved kids time works without presence or the stop-rule guard.
Open P3:
- The final volume check differs from plan item 8 as written: the `down` shortcut skips only presence and the stop-rule guard, while kids on, kids timer active, approved on and the approval session are re-checked right before the volume_set (this closes a Codex security P1 from review round 1; test_dim_rechecks_approval_during_step_write covers it). Do not "fix" it back to the plan text.
- The goal file (untracked, .frugo/goals/livingroom-background-music.md) was updated by the orchestrator with the new Volume decision; it is not part of the commit until the bookkeeping commit.
- The live package on HA still starts at 0.15 until this card is deployed (a deploy run and an HA restart, each under Martin's OK).
