---
id: 2026-10-18-livingroom-music-remote-volume
title: "Music remote: brighten, dim, off"
goal: livingroom-background-music
issue: "leviemartin/Blueprints_Home#54"
status: done
lane: 2
coder: codex
step: codex
fix_rounds: 3
---

## Goal
Add three Hue Music Remote buttons (event.kitchen_button_2 = brighten, event.kitchen_button_3 = dim, event.kitchen_button_4 = Off) to the livingroom_music package from card 2026-10-18-livingroom-music-core. Brighten and dim step the volume along the 0.05 to 0.25 ladder through one queued volume script and a step helper; Off skips to the next track. Only a short press acts. When this is done, the remote changes volume only through fixed volume_set calls on both speakers, and no path of the package can send a volume above 0.25. Button 1 (On, kids time), the 0.30 step and the approval push follow in card 2026-10-18-livingroom-music-remote-kids, which builds on this one.

## Done when (runnable)
`env -u HASS_TOKEN ~/.local/share/home-security/ha-test-venv/bin/python -I -m pytest -q -p no:cacheprovider -c ha/tests/pytest-ha.ini ha/tests`
`env -u HASS_TOKEN ~/.local/share/home-security/ha-test-venv/bin/python -I -m pytest -q -p no:cacheprovider -c ha/tests/pytest-ha.ini ha/tests/test_ha_livingroom_music_remote_volume.py`
`env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests -q`

## Files likely touched
- `ha/packages/livingroom_music.yaml` (from the core card, 12 KB; this card adds one input_number, one script and one automation, and changes the fresh start's volume step)
- `ha/tests/conftest.py` (from the core card, 7 KB; three state stubs for event.kitchen_button_2 to 4)
- `ha/tests/test_ha_livingroom_music_core.py` (from the core card, 20 KB; two small edits, Plan step 4)
- `ha/tests/test_ha_livingroom_music_remote_volume.py` (new)
- `ha/tests/pytest-ha.ini` (from the core card, read only, unchanged)

## Bad inputs to handle
- Remote event with an event_type other than short_release (initial_press, repeat, long_press, long_release, or unknown): no action
- event.kitchen_button_2 to 4 in state unknown or unavailable, or replaying a restored event: no action
- Repeated rapid presses: each press moves exactly one step, no skipped steps
- Brighten at the 0.25 cap: no volume_set
- Dim at the 0.05 floor: no volume_set
- Step helper unknown, unavailable or out of range: no volume_set, no step write
- media_player.sonos or media_player.bedroom unavailable: no service call, no step change, no error
- Hands-off on: brighten, dim and Off make no Sonos call
- Off during a phone Spotify session, or with the Sonos not playing: no call

## Risk flags
- physical safety: speaker volume; the ladder stops at 0.25 and tests assert no path sends more
- deploy: out of scope; this card writes no live config and does no reload
- workflow rules: Lane 2 for the goal; the AV chain and its LOCKED levels stay read only

## Constraints carried over
- Lane 2 for the whole goal; only Martin lowers a lane.
- Starts only after card 2026-10-18-livingroom-music-core is done; builds on its commit 2bd5012 (branch frugo/2026-10-18-livingroom-music-core). Branch `frugo/2026-10-18-livingroom-music-remote-volume`, worktree `lm-vol` (the orchestrator creates them).
- Sonos queue only: no Spotify, Spotcast or Music Assistant integration.
- Speakers: media_player.sonos (Living Room One) grouped with media_player.bedroom (Bedroom One). Both get the same fixed volume_set; no read-modify-write on reported volume.
- Volume: start 0.15; ladder 0.05 to 0.25 in 0.05 steps. Nothing above 0.25 in this card.
- Phone session: HA never replaces it; remote volume still works; Off is ignored.
- Read only, never a service call: media_player.marantz_cinema_50, media_player.mxn10, media_player.lg_webos_tv_oled65c9pla, alarm_control_panel.house_alarm.
- Tests run with env -u HASS_TOKEN. conftest and tests hold no token and no URL.
- Budget: track only, warn line 500,000 tokens per card.

## Out of scope
- Button 1 (On), kids time, Pairilijst, cooldown, the 0.30 step, approval pushes, reset debts and retries (card 2026-10-18-livingroom-music-remote-kids).
- Deploy to /config/packages and reload (deploy card), and removing anything in HA, including the four Samuel remote automations.
- Changing the core card's start, pause, resume, quiet-hours, Hands-off or phone-session rules; the only core edit is the fresh start's volume step (Plan step 2). The `*may_start` re-check that the volume script runs for the fresh start's `step: 2` (Plan step 3) is a guard inside the volume script, not a change to the core start rules.
- The AV chain, circadian lights, FP2 and FP300 settings, the home-security package, switch.sonos_alarm_1, Hue-app routines, blueprints and dashboards.

## Open questions
none

## Decided by orchestrator
Split from card 2026-10-18-livingroom-music-remote-kids on 2026-10-19 (Martin: that card was too large to finish); the decisions below are carried from it.
- Martin: while Hands-off is on, dim and brighten are ignored too (HA makes no Sonos call at all).
- Martin: during a phone Spotify session Off is ignored (volume buttons still work).
- Base: builds on the core card's committed branch (commit 2bd5012); the core package, the ha_session flag, timers and the guarded fresh-start script already exist.
- Button events: a press is event_type short_release (probe: initial_press, repeat, short_release, long_press, long_release); every other type does nothing, so a long press never acts. Map from the retired Samuel automations: 2 = brighten, 3 = dim, 4 = Off (1 = On belongs to the kids card).
- Helper ids are the planner's; the step starts at the 0.15 step after a restart.
- Test home is ha/tests/ (core card decision).
- Planner (from r6/r8/r9): every volume write of the package goes through one queued volume script, including the core fresh start's 0.15 (it passes `step: 2`), so a press queued before a fresh start can never land after it; the remote never writes the step itself; up and down check that both speakers are available before any step write.
- Planner r2 (design round 1): the remote passes only `delta: 1` or `delta: -1`; the volume script computes the target from the step helper inside its queued `variables:` step, so a press queued behind a fresh start (or any other queued run) moves exactly one step from the result of that run. The fresh start still passes `step: 2`. The volume script re-checks Hands-off and both speakers directly before the volume_set; a failing re-check leaves the step written and sends nothing.
- Planner r3 (design round 2, final): when `step` is given (the fresh-start path), the volume script also checks the core `*may_start` anchor before its step write and again before the volume_set, so a fresh start that waited in the queue sends no 0.15 and writes no step once a phone session, a blocker or quiet hours began; `delta` runs keep the plain Hands-off and speaker checks.
- Planner (split): the only core edit is the fresh start's volume step, strictly needed so the step helper and the speakers agree after a fresh start.

## Plan
Planner: Opus, 2026-10-19, revision 3 (final) (design round 2 fixes: two P2s, one P3: the fresh-start path re-checks `*may_start` inside the volume queue, test 17 checks each chain separately, test 2 names its keys; test 19; no further design rounds). Revision 2 (design round 1 fixes: two P1s, two P2s, one P3: the remote passes `delta` and the volume script computes the target step in its queue, Hands-off and speakers are re-checked right before the volume_set, `trigger.to_state` is checked, test 2 is RED on the base, `press(settle=False)`; tests 17 and 18). Revision 1: Split out of card 2026-10-18-livingroom-music-remote-kids r15 (its design rounds 1 to 8 covered these rules); no design rounds of its own unless the orchestrator asks. Lane 2 (goal-wide). Coder: `codex`.

### Coder scope
The coder implements the numbered package changes (Steps 1 to 5) and the 19 numbered tests exactly as written. A race or interleaving that no numbered test covers and that is not listed under Rare corners is NOT a reason to return BLOCKED: the coder implements the plan as written and lists the concern in its DONE_WITH_CONCERNS note. BLOCKED is only for a contradiction inside the plan that makes a numbered test or rule impossible to satisfy.

### Facts the coder needs (probe, core card, HA 2026.10.1 venv)
- Remote: event.kitchen_button_2..4; only `event_type` short_release acts. An event entity's state is the last event time (ISO, milliseconds); `event_type` is an attribute. State triggers accept `not_from` and `not_to`.
- Core harness: `load_package`, `services` (records; `sonos_calls()`), `settled_teardown`, `settle`, `advance` in conftest; the `boot` fixture, `put`, `edge`, `calls`, `only`, `fresh`, `direct` and the constants (SONOS, BEDROOM, HANDS, OWNED, PHONE, APP, FP2, FP300) in the core test module.
- A queued automation renders its top-level `variables:` and evaluates its `conditions:` at trigger time, before the run waits in the queue. Script-level `variables:` render when the script is called, also before a queued run waits. So every helper read that must see an earlier run's result is a `variables:` or condition step inside `actions:` / `sequence:`.
- input_number with `initial` starts at that value at every start and is never restored.
- `continue_on_error` does not catch ServiceNotFound; errors are logged at ERROR.
- The core `*may_start` anchor checks Hands-off off, no phone session, no blocker, 07:30 to 22:00 and both speakers available.

### Helpers and ids
- `input_number.livingroom_music_volume_step`: ladder index, min 0, max 4, step 1, `initial: 2`. Levels 0..4 = 0.05, 0.10, 0.15, 0.20, 0.25. (The kids card raises max to 5 for 0.30.)
- `script.livingroom_music_volume`, `automation` id `livingroom_music_remote`.

### The 0.25 rule
Only `script.livingroom_music_volume` sends a volume, and its level comes from the five-entry ladder list, so 0.25 is the highest level the package can send. Tests 2, 3, 6, 11 and 18 prove it.

### Steps
1. `ha/tests/conftest.py`: add to `PACKAGES["livingroom_music"]` three stubs `event.kitchen_button_N: ("2026-10-20T08:00:00.000+00:00", "Music Remote button N")` for N = 2, 3, 4. Nothing else changes.
2. Package, core edit (the only one): in `script.livingroom_music_fresh_start`, the direct volume_set step (0.15 on both) is replaced by `action: script.livingroom_music_volume` with `data: {step: 2}` (blocking). The volume script writes step 2 and sends 0.15 to both speakers in queue order. The `*may_start` steps, play_media and shuffle_set stay, so the core call list is unchanged.
3. Package, new script `livingroom_music_volume`, mode queued, max 20. The only place the package sends a volume and the only place the step is written. Fields `step` (optional absolute target index; the fresh start passes `step: 2`) and `delta` (optional `1` or `-1`; the remote passes it). Sequence:
   - a `variables:` step (first step, so it renders when the queued run starts, after every earlier queued run has finished): `cur` = the step state as `float(-1)`; `s` = `step | float(-1)` when `step` is given; else, when `delta` is given, `cur + (delta | int)` when `cur in [0, 1, 2, 3, 4]`, else -1; else `cur`. `level` = `[0.05, 0.10, 0.15, 0.20, 0.25][s | int]` when `s in [0, 1, 2, 3, 4]`, else none. (So a press at the cap gives 5 and at the floor -1, both dropped below.)
   - condition steps: Hands-off off; both speakers not unknown or unavailable; `s in [0, 1, 2, 3, 4]`; and, only when `step` is given (the fresh-start path): the core anchor `*may_start` (as one `condition: or` of a template `{{ step is not defined }}` and `*may_start`, so a `delta` run is not affected). The script is placed after `livingroom_music_fresh_start` in the file so the anchor is already defined. A fresh start whose queued run starts after a phone session, a blocker or quiet hours began therefore writes no step and sends nothing.
   - when `step` or `delta` is given: `input_number.set_value` the step to `s`.
   - directly before the call, after the awaited step write, condition steps again: Hands-off off; both speakers not unknown or unavailable; and the same `step`-only `*may_start` check. If any fails the run stops with no volume_set and the step is left at `s` (not reverted; the next press resyncs, see Rare corners).
   - volume_set on [media_player.sonos, media_player.bedroom], `volume_level: "{{ level }}"`.
4. Package, new automation `livingroom_music_remote` (with a description; no entity id in any description, alias or comment), mode queued, max 10. Three state triggers, ids `up` (button 2), `down` (3), `skip` (4), each with `not_from: [unknown, unavailable]` and `not_to: [unknown, unavailable]`. Automation conditions read trigger data only: `trigger.from_state is not none and trigger.to_state is not none` (checked before any attribute read: a removed entity fires with no new state) and then `trigger.to_state.attributes.event_type == 'short_release'`. Actions begin with a condition step Hands-off off. The remote never reads the step. Then choose on `trigger.id`:
   - up and down each begin with a condition step: both speakers not unknown or unavailable.
   - up: run the volume script (blocking) with `delta: 1`.
   - down: run the volume script (blocking) with `delta: -1`.
   - skip: condition steps directly before the call: Hands-off off; no phone session (as in `*may_start`); media_player.sonos playing; both speakers available. Then media_next_track on media_player.sonos.
5. `ha/tests/test_ha_livingroom_music_core.py`, edits only: `test_package_loads` adds `remote` to the automation id set; `test_package_text_rules` allows exactly one `volume_level` line, `volume_level: "{{ level }}"` (the core `volume_level: 0.15` line is gone; forbidden words kept). The core `fresh` helper stays as it is. Then write the new test module and run the three Done-when commands from the worktree root.

### Test module rules
- `pytestmark` exactly as in the core module (`settled_teardown` plus `expected_lingering_timers` True).
- Import `REPO, advance, settle` from conftest and `boot, put, edge, calls, only, fresh, direct` plus the constants from `test_ha_livingroom_music_core`. No copies.
- New local helpers only: `volume_direct(hass, **data)` (calls `script.livingroom_music_volume` blocking with `data` and settles); `press(hass, button, kind="short_release", settle=True)` (sets the event entity to a new unique timestamp, a module counter in the microseconds, with `{"event_type": kind}`, and settles unless `settle=False`; tests 4 and 5 press with `settle=False` and then call `settle` once, so the presses really land in one loop turn); `volumes(services)` (volume_level of each volume_set record); a `music` fixture that calls `boot(...)` and asserts `input_number.livingroom_music_volume_step` exists, so every "nothing happens" test is RED on the core-only base. Set the step with `input_number.set_value`; force bad states with `hass.states.async_set`.
- The imported `fresh(services)` asserts the WHOLE Sonos call list is the three fresh-start calls; use it only where nothing else is recorded, else check a slice inline.

### Test list (`ha/tests/test_ha_livingroom_music_remote_volume.py`)
Each test fails before the patch (the core-only package has no step helper, volume script or remote automation) and passes after. Command 1 runs these plus the core tests; command 2 this module; command 3 the unchanged tests/ suite.
1. `test_volume_package_loads`: the remote automation and the volume script load; step 2.0; no Sonos call at load.
2. `test_volume_text_rules`: in the package file the exact literal `[0.05, 0.10, 0.15, 0.20, 0.25]` appears exactly once (RED on the core base); no decimal above 0.25 appears; `volume_up` and `volume_down` do not appear; every `volume_level:` line holds only `"{{ level }}"`; every `delta:` value is `1` or `-1`; every `step:` key inside a `data:` block of a call is an integer from 0 to 4. The input_number definition (its `step: 1`, `max: 4`, `initial: 2`) is not checked by this rule. (Safety; the kids card changes this test.)
3. `test_brighten_dim_ladder`: from step 0, four up: [0.10, 0.15, 0.20, 0.25], each on both speakers; four down: [0.20, 0.15, 0.10, 0.05]; step ends 0.0.
4. `test_rapid_presses`: three up from step 0 in one loop turn: exactly [0.10, 0.15, 0.20]; step 3.0. (Bad input.)
5. `test_off_queued_behind_hands_off`: music playing; the volume_set callback records and turns Hands-off on; an up press and an Off press in one loop turn: the volume_set is recorded, no media_next_track.
6. `test_brighten_cap[plain|phone_session]`: step 4, three up: no volume_set, step 4.0. (Bad input.)
7. `test_dim_floor`: step 0, down: no volume_set. (Bad input.)
8. `test_volume_in_phone_session`: sonos playing with PHONE attributes: up then down give one volume_set each, one step apart; no media call.
9. `test_non_press_events[button 2..4 × initial_press|repeat|long_press|long_release|double_press]`: no Sonos call. (Bad input.)
10. `test_event_entity_unavailable[from_unavailable|from_unknown|to_unavailable|re_added]`: no call. re_added: the entity is removed (`hass.states.async_remove`), settle, no ERROR record at that point, then added back with a short_release state: still no call and no ERROR. (Bad input.)
11. `test_step_invalid[unknown|unavailable|-1|6|2.5 × up|down|direct]`: no volume_set; `volume_direct(step=5)` also gives no volume_set. (Bad input, safety.)
12. `test_off_skips`: Lazy Sunday playing (APP): Off gives exactly media_next_track on media_player.sonos.
13. `test_off_ignored[phone_session|paused|bedroom_unavailable]`: no call. (Bad input.)
14. `test_hands_off_ignores_remote[up|down|off]`: no Sonos call, step unchanged. (Martin's decision.)
15. `test_volume_script_guards[hands|sonos_unavailable|bedroom_unavailable]`: `volume_direct()` at a valid step: no Sonos call.
16. `test_speakers_unavailable[sonos|bedroom × up|down|off]`: from step 2, no call, no ERROR, step still 2.0. (Bad input.)
17. `test_fresh_start_and_press_ordering[press_then_fresh|fresh_then_press]`: sonos idle, occupied off, step 3; volume_set overridden with an async handler that records each call when it completes and holds the first call on an Event; a volume script run started with `script.turn_on` and `step: 0` (writes step 0, its volume_set held). press_then_fresh: an up press (its `delta: 1` run waits in the queue), then an occupancy edge starts the core fresh start (its `step: 2` run queues behind); after the Event is set and the test settles, the volume_level values are 0.05, 0.10, 0.15, each on both speakers, and nothing after; step 2.0. fresh_then_press: the occupancy edge first, then the up press; each chain is checked on its own: the volume_level values are 0.05, 0.15, 0.20 in that order and nothing after; step 3.0 (one step above the fresh start's 2, never a skipped step); play_media Lazy Sunday and then shuffle_set are recorded after the 0.15 pair (their order against the 0.20 pair is not checked). press_then_fresh: play_media and then shuffle_set are recorded after the 0.15 pair.
18. `test_guard_change_during_step_write[hands_off|bedroom_unavailable]`: step 2; `input_number.set_value` wrapped so that, for the volume step only, it first turns Hands-off on (hands_off) or sets media_player.bedroom unavailable (bedroom_unavailable), then delegates to the original; an up press, then settle: no volume_set recorded, the step is 3.0 (left at the written value), no ERROR. (Security r1 P1.)
19. `test_fresh_start_guard_in_queue[phone_session|lg_on]`: sonos idle, occupied off, step 3; volume_set overridden with an async handler that records each call when it completes and holds the first call on an Event; an up press (its 0.25 call is held, step 4.0); an occupancy edge starts the core fresh start (its `*may_start` passes; its `step: 2` run waits in the volume queue); then media_player.sonos is set playing with PHONE attributes (phone_session) or media_player.lg_webos_tv_oled65c9pla is set on (lg_on); then the Event is set and the test settles: no volume_set at 0.15 is recorded, step still 4.0 (no step write), no play_media. (Correctness and security r2 P2.)

### Rare corners (accepted, no extra rule)
- The first press after an event entity is newly added or restored is ignored.
- A volume_set that raises after the step was written leaves the step one ahead of the speakers; the next press sends the same fixed level to both and resyncs them.
- After a restart the step comes back at 2 while the speakers keep their last level; the next press resyncs both.
- Hands-off turning on, or a speaker dropping, during the step write leaves the step one step ahead with no volume_set; the next press after it clears moves one step from there and resyncs both speakers.

### Risks
- The core tests must stay green after step 2; the fresh start's 0.15 now comes from the volume script's `{{ level }}` (rendered as the float 0.15), so the core `fresh` helper and the core start tests see the same call list. A failing core test means an edit went beyond the listed changes.

## Result
<!-- First line: the result. Then "Open P3:" followed by "- " bullets for Martin, or "none". -->
Hue Music Remote buttons 2 (brighten), 3 (dim) and 4 (Off) are built and uncommitted on branch frugo/2026-10-18-livingroom-music-remote-volume (worktree Blueprints_Home-wt/lm-vol, based on core commit 2bd5012): the queued volume script and step helper in ha/packages/livingroom_music.yaml, the fresh start's 0.15 now sent through that script, and ha/tests/test_ha_livingroom_music_remote_volume.py (19 tests, 76 cases). All three Done-when commands pass (180 HA tests, 76 in the new module, 635 in tests/); the HA commands are red on the clean base. Lane 2: two design rounds, two code-review rounds (one coder fix round) and one code arbiter (proceed, the one security P2 ruled P3).
Open P3:
- Codex security (arbiter ruling P3): a second press waiting in the remote automation queue can land after a fresh start's 0.15 reset, because the remote queue and the volume queue are separate. The result stays on the 0.05 to 0.25 ladder and follows a real press, but the plan's "a press queued before a fresh start can never land after it" is not literally true. Follow-up: one shared queue, or a test with two pending presses (for example in the kids card).
- Opus correctness: the second step-only `*may_start` check right before the volume_set is not tested; add a phone_session or lg_on variant of test 18 for the fresh-start path.
- Opus correctness: test 2's `step`/`delta` text rule reads `data:` only on action nodes; also check `variables:` of `script.turn_on` calls.
- Hue-app button assignments for the Music Remote cannot be read from HA (Martin to confirm there are none); the Music Remote battery reads 15 percent (card 1 findings).
