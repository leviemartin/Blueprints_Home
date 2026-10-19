---
id: 2026-10-18-livingroom-music-core
title: Livingroom music core and HA harness
goal: livingroom-background-music
issue: "leviemartin/Blueprints_Home#51"
status: done
lane: 2
coder: codex
step: codex
fix_rounds: 8
---

## Goal
Build the living-room music core: one HA YAML package, ha/packages/livingroom_music.yaml, with the start, pause and resume, quiet-hours, Hands-off and phone-session rules, plus its HA behaviour test harness under ha/tests/ with one test per rule, including the restart case (HA start with music paused). After this, media_player.sonos (grouped with media_player.bedroom) starts Lazy Sunday shuffled at 0.15 when either presence sensor is on, and pauses and resumes on the stop rules. The remote, kids time, volume ladder and approval are card 3; deploy is card 4.

## Done when (runnable)
`env -u HASS_TOKEN ~/.local/share/home-security/ha-test-venv/bin/python -I -m pytest -q -p no:cacheprovider -c ha/tests/pytest-ha.ini ha/tests`
`env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests -q`

## Files likely touched
- `ha/packages/livingroom_music.yaml` (new; top-level keys only from: automation, script, input_boolean, input_number, input_select, timer, input_datetime)
- `ha/tests/pytest-ha.ini` (new; adapted from the read-only input .frugo/inputs/pytest-ha.ini)
- `ha/tests/conftest.py` (new; adapted from the read-only input .frugo/inputs/conftest.py)
- `ha/tests/test_ha_livingroom_music_core.py` (new)
- `.frugo/inputs/conftest.py` (READ-ONLY input, untracked, worktree only; never in the diff)
- `.frugo/inputs/pytest-ha.ini` (READ-ONLY input, untracked, worktree only; never in the diff)

Note: ha/ does not exist in the repo yet. The existing tests/ suite is the only test tree present (635 tests pass at base 8c13406 with the second Done-when command).

## Bad inputs to handle
- media_player.sonos or media_player.bedroom unavailable or unknown: no service call, no error
- One presence sensor on and the other unavailable: counts as occupied
- Both presence sensors on at the same moment: one start, not two
- Both presence sensors unavailable: counts as empty; the 15 min pause timer runs
- media_player.lg_webos_tv_oled65c9pla, media_player.marantz_cinema_50 or alarm_control_panel.house_alarm unknown or unavailable: not blocking
- Alarm in a state outside the blocking list (for example disarmed): does not block
- HA start with music paused and the room occupied: restart case, same start rules and blockers as a presence trigger (resume)
- Sonos source Spotify Connect with a media_content_id that is not x-sonos-vli: is not a phone session
- Hands-off on: any call to media_player.sonos fails the test
- Exact boundary times 22:00, 07:30 and 06:00 (Amsterdam)
- Any call to notify.mobile_app_pixel_9_pro_xl: fails the test

## Risk flags
- secrets: the HA token is read only by the orchestrator; conftest and tests must hold no token or URL, and the tests run with env -u HASS_TOKEN
- workflow rules: media_player.marantz_cinema_50, media_player.mxn10, media_player.lg_webos_tv_oled65c9pla and alarm_control_panel.house_alarm are read only, with no service call; notify.mobile_app_pixel_9_pro_xl is retired and must never be called

## Constraints carried over
- Lane 2 for the whole goal; only Martin lowers a lane.
- Sonos queue only: no Spotify, Spotcast or Music Assistant integration. Lazy Sunday is spotify:playlist:37i9dQZF1DWTc452KG008d (the probe found no favorite for it).
- Speakers: media_player.sonos (Living Room One) grouped with media_player.bedroom (Bedroom One). switch.sonos_alarm_1 (Sonos-app alarm) is outside HA and is not changed.
- Presence: either binary_sensor.presence_sensor_fp2_e863_presence_sensor_1 or binary_sensor.living_room_main_fp300_couch_occupancy_sensor on means occupied; both clear means empty.
- Empty room for 15 min pauses; presence returning resumes the same track where it left off.
- Blockers that pause and block starts: LG on, Marantz on, alarm in armed_away, armed_night, arming, pending or triggered.
- Quiet hours 22:00 to 07:30: no start; music playing pauses at 22:00. Times are Amsterdam.
- Hands-off (input_boolean): no HA service call to the Sonos while on; it turns itself off at 06:00.
- Phone session: detected by Sonos source Spotify Connect plus media_content_id starting x-sonos-vli:. HA never starts or replaces it. It ends when paused or stopped for 10 min; the next start reloads Lazy Sunday fresh, shuffled, at 0.15.
- Start volume 0.15, set with a fixed volume_set on both speakers; no read-modify-write on reported volume.
- The AV chain (MXN10, Marantz, B&W, Tap Dial automations) and its LOCKED levels are untouched.
- Budget: track only, warn line 500,000 tokens per card.

## Out of scope
- The remote, kids time, the volume ladder and approval (card 3).
- Deploy to /config/packages and reload (card 4).
- Any blueprint.
- Removing anything, including the four Samuel automations.
- Changes to the circadian lights, the FP2 or FP300 settings, the home-security package, the Bedroom One Sonos-app alarm or Hue-app routines.
- Dashboard work beyond the Hands-off helper.

## Open questions
none

## Decided by orchestrator
All earlier open questions, decided by orchestrator; Martin can revert.
- Test home: ha/tests/ and ha/packages/ (planner change 2026-10-18 from tests_ha/; reason in the Plan, "Card changes"). The goal text is older.
- Model files outside the repo (home-security tests/pytest-ha.ini and tests/ha/conftest.py, about 10 KB, no token): the orchestrator copies both into the card worktree under untracked .frugo/inputs/ (read only for the planner and coder, never in the diff); the plan names the exact copy.
- Probe results (card 1, reviewed 2026-10-18; note docs/superpowers/research/2026-10-18-livingroom-music-probe.md is on the card 1 branch, not main yet): Lazy Sunday starts by URI spotify:playlist:37i9dQZF1DWTc452KG008d with play_media enqueue replace then shuffle_set (no favorite exists); phone session detection confirmed (source Spotify Connect, media_content_id starts x-sonos-vli:); pause then play keeps the queue and track; media_playlist is empty after a playlist play so HA cannot tell Lazy Sunday from the attributes, the package keeps its own owner helper; sonos.restore returns only the position, so no snapshot/restore in this card (kids time is card 3, fresh-reload fallback).
- Helper ids: input_boolean.livingroom_music_hands_off and input_boolean.livingroom_music_ha_session.
- Restart with the room occupied and music paused: treated like a presence trigger (same start rules, same blockers).
- Both presence sensors unavailable: treated as empty (the 15 min pause timer runs). One on and the other unavailable: occupied.
- LG, Marantz or alarm unknown or unavailable: not blocking (only LG on, Marantz on and the listed alarm states block).
- The HA time zone is Europe/Amsterdam (read live 2026-10-18).
- The 15 min empty timer restarts from zero whenever presence returns and goes empty again; presence returning cancels it.
- The 10 min phone-session timer counts from the moment the Sonos is paused or stopped.
- Design round 3: HA resumes whatever it paused itself. input_boolean.livingroom_music_ha_session (id kept) means "HA paused this": set by an empty-room or blocker pause of non-phone content, cleared at 22:00 and whenever the Sonos changes to playing. Content someone else paused is replaced by a fresh Lazy Sunday on the next start edge.
- Design round 5: "LG on" and "Marantz on" mean powered on: each blocks in any state except off, standby, unknown and unavailable (a Marantz on a network source reports playing or paused). Martin can revert.
- Design round 5: a speaker coming back from unavailable or unknown only resumes HA-paused music (flag on); it never starts a fresh Lazy Sunday. The HA start event keeps the full start rules.
- Design round 4: HA down over 22:00 (so `quiet_reset` never runs and an HA-paused flag survives into the morning) is an accepted rare corner; no input_datetime, no extra rule.
- Design round 3: the pause rules need only media_player.sonos available (media_pause goes only to it); a start needs both speakers available.
- Accepted rare corner (code review, 2026-10-18): music already playing at HA restart while a blocker (LG, Marantz, alarm) is on is not paused until the blocker goes off and on again; there is no restart trigger on the pause automation.

## Plan
Planner: Opus, 2026-10-18. Lane 2 confirmed (alarm entity, goal-wide Lane 2). Coder: `codex`.

### Card changes (planner)
1. Test home moved from tests_ha/ to ha/tests/. Reason: Frugo red-green applies only files that match `ladder.yaml` `checks.test_path_patterns` to the RED tree. `tests_ha/conftest.py` and `tests_ha/pytest-ha.ini` match none of them (`(^|/)tests?/` needs a directory named exactly test or tests), so RED would run without the ini and conftest, pytest would crash instead of reporting `N failed`, and rule 5 would end `not-red`. Under ha/tests/ all three test-side files match, RED runs the real harness against a base with no package, and every test fails with FileNotFoundError. ha/tests/ is also outside `tests`, so the second Done-when command does not collect the async HA tests (no asyncio_mode there). Cards 3 (remote-kids) and 4 (deploy) still say tests_ha/; the orchestrator updates them.
2. The three "expected outcome is an open question" bad inputs now state the outcomes already decided above.
3. The Lazy Sunday "or the favorite" option is removed (the probe found none).
4. Files list paths are backtick-quoted so codex-propose shows the two read-only inputs to the coder.

### The read-only inputs
`.frugo/inputs/conftest.py` and `.frugo/inputs/pytest-ha.ini` are untracked copies of the home-security harness, present only in the card worktree. They are in the Files list only so the coder brief includes their text. The coder never edits, moves or deletes them, and the patch contains no path under `.frugo/`; a reviewer rejects a diff that does. Before the commit the orchestrator does not stage `.frugo/inputs/` (the repo does not ignore it) and removes it after the card closes.

### Files
- `ha/packages/livingroom_music.yaml`: the package.
- `ha/tests/pytest-ha.ini`: the input ini without the two `markers` lines (no lock services here): asyncio_mode auto, python_files test_ha_*.py, log_level WARNING, addopts --strict-markers.
- `ha/tests/conftest.py`: the input conftest, adapted (step 2).
- `ha/tests/test_ha_livingroom_music_core.py`: the tests (test list below).

### Package design (simplest rules)
Shared templates (written inline where used; three short copies beat an abstraction):
- occupied: `is_state(FP2, 'on') or is_state(FP300, 'on')`. Off, unavailable and unknown all count as clear, so both-unavailable is empty and one-on is occupied with no extra rule.
- blocked: `states(LG) not in ['off', 'standby', 'unknown', 'unavailable'] or states(Marantz) not in ['off', 'standby', 'unknown', 'unavailable'] or states(alarm) in ['armed_away', 'armed_night', 'arming', 'pending', 'triggered']`. Unknown and unavailable never block; any other alarm state does not block.
- speakers_ok: neither media_player.sonos nor media_player.bedroom is `unavailable` or `unknown`.
- phone (read on a given state object s, the live one or `trigger.from_state`): `s.attributes.source == 'Spotify Connect' and ((s.attributes.media_content_id or '') | string).startswith('x-sonos-vli:')`. Keep the outer parentheses: without them the filter binds wrongly.
- Phone session rule (works whether a stopped Sonos keeps or clears the attributes; the probe saw pause keep them and did not probe stop): the session is "active" while the Sonos plays with phone attributes, or while timer.livingroom_music_phone runs. The timer starts when the Sonos leaves `playing` and the state it left had phone attributes, so the live attributes after the pause or stop do not matter. HA ends the session only by the timer finishing, or by the Sonos playing something without phone attributes (timer cancelled).

Helpers:
- `input_boolean.livingroom_music_hands_off` (name "Livingroom music Hands-off", icon allowed, no `initial`, so it keeps its state over a restart).
- `input_boolean.livingroom_music_ha_session` ("HA paused this" flag; no `initial`, so it survives a restart). Set only by the pause automation (empty-room or blocker trigger, non-phone content, after the media_pause call). Cleared by `quiet_reset` at 22:00 and by the `phone` automation whenever the Sonos changes state to `playing` from anything else (HA's own resume, a fresh start, app content or a phone session; attribute-only updates while playing do not clear it). The start automation resumes (media_play) when it is on and the Sonos is paused, and otherwise runs the fresh start. Card 3 keeps its own owner helper for its playlist.
- `timer.livingroom_music_empty`: duration 00:15:00.
- `timer.livingroom_music_phone`: duration 00:10:00, `restore: true` (rare-corner guard: a restart inside the 10 min does not end a paused phone session early; not tested).

Script `script.livingroom_music_fresh_start` (card 3 reuses it), mode single, in this order. One shared "may start" guard (security reviews r1-r4): a single `condition: and` step whose `conditions:` list holds the five checks, written once with a YAML anchor (`- &may_start` on that step) and reused as `- *may_start` at the other places, so no nested list appears. The checks: hands_off off; no phone session (timer.livingroom_music_phone idle and not media_player.sonos `playing` with phone attributes); not blocked; time after 07:30:00 and before 22:00:00; speakers_ok. It stands at script entry, directly before step 2 (play_media) and directly before step 3 (shuffle_set). A false condition step stops the script, so a direct call, or Hands-off or a phone session appearing during the sequence, makes no further Sonos call:
1. `media_player.volume_set` on [media_player.sonos, media_player.bedroom], volume_level 0.15.
2. `media_player.play_media` on media_player.sonos: media_content_id spotify:playlist:37i9dQZF1DWTc452KG008d, media_content_type playlist, enqueue replace.
3. `media_player.shuffle_set` on media_player.sonos, shuffle true.

Automations (ids `livingroom_music_<name>`, all with a description). No entity id in any description, alias or comment: the conftest entity scan reads every non-action line and would demand a stub.
1. `start`, mode single. Triggers: template occupied (fires on the false-to-true edge only, so two sensors turning on together give one run); template `not blocked` (blocker cleared); `homeassistant` start event (the restart case); state of media_player.sonos or media_player.bedroom `from: [unavailable, unknown]`, id `reconnect` (the speakers come back after the start event, the usual order on a real restart; also any later reconnect). Give every trigger an `id` and tell triggers apart only by `trigger.id` in every automation (never `trigger.event...`). Conditions, all of them: occupied; not blocked; time after 07:30:00 and before 22:00:00 (HA time condition: after is inclusive, before exclusive, which gives exactly the 22:00 and 07:30 boundaries); hands_off off; speakers_ok; media_player.sonos not `playing` (HA never replaces anything that plays); timer.livingroom_music_phone idle (no phone session; the live phone-and-playing case is already excluded by "not playing"). Action, choose: if ha_session on and sonos `paused`, call `media_player.media_play` on media_player.sonos (resume, no volume_set); otherwise, unless `trigger.id` is `reconnect`, run the fresh-start script (a reconnect only resumes).
2. `pause`, mode single. Triggers: event `timer.finished` for timer.livingroom_music_empty (id empty); template blocked (id blocked); time 22:00:00 (id quiet); state of media_player.sonos `to: playing` (id started; it catches a blocker or 22:00 that arrived while play_media was still running) with the extra condition, for this id only, blocked or the time outside 07:30:00 to 22:00:00. Conditions: hands_off off; sonos `playing` (which implies media_player.sonos is available; Bedroom One's state is not checked). Action: `media_player.media_pause` on media_player.sonos; then, only for id empty or id blocked and only when the live state has no phone attributes, and only when the time, read after the media_pause call, is after 07:30:00 and before 22:00:00 (a time condition), turn ha_session on (so that pause resumes later; a pause during quiet hours never makes a resume). The 22:00 trigger never sets it, so it cannot race `quiet_reset`. A playing phone session is paused too (goal: the stop rules still pause it).
3. `empty_timer`, mode queued. Triggers: template `not occupied` (id empty); template occupied (id occupied); `homeassistant` start (id restart); state of media_player.sonos `to: playing` (id playing). Action, choose: id occupied: `timer.cancel`; id empty: `timer.start` (a new start restarts the 15 min from zero); id restart or id playing, while not occupied and the timer is idle: `timer.start`. The playing branch covers music started in an already empty room (Sonos app, phone, the Sonos-app alarm); the restart branch covers playing into an empty room across a restart. Each has one test.
4. `phone`, mode queued. Trigger: state of media_player.sonos with no to/from (fires on attribute changes too). Action, choose: sonos `playing`: `timer.cancel` timer.livingroom_music_phone, and if `trigger.from_state` is none or its state was not `playing` also turn ha_session off; sonos not `playing` and `trigger.from_state` is not none, its state was `playing` and it had phone attributes: `timer.start` timer.livingroom_music_phone. This automation never calls a media_player service.
5. `hands_off_reset`. Trigger: time 06:00:00. Action: `input_boolean.turn_off` livingroom_music_hands_off.
6. `quiet_reset`. Trigger: time 22:00:00. No conditions. Action: `input_boolean.turn_off` livingroom_music_ha_session. Decided on purpose: the first start after quiet hours is always a fresh Lazy Sunday at 0.15, never last night's track at last night's volume (keeps the 0.15 start rule once card 3's ladder exists). It makes no Sonos call, so it runs whatever Hands-off, the speakers or the pause did.

Deliberately not added (simplest rule; Martin can ask): no start at 07:30 or when Hands-off turns off (the next presence, blocker-clear or speaker-return edge starts music); music still playing in an empty room when Hands-off ends after the 15 min passed pauses only on the next empty edge (rare corner).

No read of the reported volume (the only `volume_level` in the file is the fixed `volume_level: 0.15` data of volume_set), no sonos.snapshot or sonos.restore, no notify call, no service call on the LG, Marantz, MXN10, alarm or switch.sonos_alarm_1.

### Steps
1. Write `ha/tests/pytest-ha.ini` as above.
2. Write `ha/tests/conftest.py` from the input, keeping its shape (load_package, services, settled_teardown, settle, advance) with these changes only:
   - `REPO = Path(__file__).resolve().parents[2]` (unchanged value; ha/tests/ is two levels down).
   - `PACKAGES = {"livingroom_music": {...}}` with stubs (state, friendly name): FP2 binary_sensor off "Presence-Sensor-FP2-E863 Presence Sensor 1"; FP300 binary_sensor off "FP300_Couch Occupancy Sensor"; media_player.sonos idle "Living Room One"; media_player.bedroom idle "Bedroom One"; media_player.lg_webos_tv_oled65c9pla off "LG webOS TV OLED65C9PLA"; media_player.marantz_cinema_50 off "Marantz Cinema 50"; alarm_control_panel.house_alarm disarmed "House Alarm". Stub only entities the package references.
   - `DOMAINS = {"automation", "script", "input_boolean", "input_number", "input_select", "timer", "input_datetime"}`; the existing top-level-key check stays.
   - The referenced-entity regex gets the lookbehind `(?<![.\w])` before the domain group (so `trigger.event.data` is not read as an entity) and its domains become `binary_sensor|media_player|alarm_control_panel|switch|notify|sensor|event|light`, so every external entity the package names must be stubbed (helpers, timers and scripts are defined by the package and are not stubbed).
   - load_package calls `await hass.config.async_set_time_zone("Europe/Amsterdam")` first. Drop the alarm_control_panel panel check and the event_types attribute block (no packages need them here).
   - services fixture: register the recorder for media_player `play_media, media_play, media_pause, media_stop, shuffle_set, volume_set, repeat_set, turn_on, turn_off, select_source, media_next_track, volume_mute, join, unjoin` and sonos `snapshot, restore`; keep `async_mock_service(hass, "notify", "mobile_app_pixel_9_pro_xl")` as the forbidden list (drop the tablet and the lock mocks and the lock marker check). Add `sonos_calls()` = records whose domain is media_player or sonos. Teardown asserts, in this order: no retired Pixel push; no record whose entity_id (string or list) names media_player.lg_webos_tv_oled65c9pla, media_player.marantz_cinema_50, media_player.mxn10 or alarm_control_panel.house_alarm; no log record at ERROR or above in `caplog.get_records("setup") + caplog.get_records("call") + caplog.records` (teardown alone sees only teardown records; the fixture takes `caplog` as a parameter). The ERROR guard catches a call to an unregistered service (ServiceNotFound) and template errors, which is how "no error" and "any call to media_player.sonos" are seen for services the recorder does not cover.
   - Keep settle and advance as they are. Tests set the clock with `freezer.move_to("2026-10-20THH:MM:SS.5+02:00")` before load_package (2026-10-20 is CEST, before the 25 October change), and move it only with `advance(hass, freezer, seconds)`. Starting at .5 s puts a boundary 0.5 s away. Timers (15 min, 10 min) and time triggers (22:00, 06:00) fire only through advance, so no test sleeps or depends on the wall clock.
   - No token, URL or HASS_* variable anywhere.
3. Write `ha/packages/livingroom_music.yaml` per the package design. Modern syntax (`triggers:`/`trigger:`, `conditions:`, `actions:`/`action:`), matching the HA 2026.10.1 test venv.
4. Write the tests (list below). Tests change a speaker state by hand with `hass.states.async_set` (the stub does not react to service calls), for example set media_player.sonos to paused after asserting a media_pause, then `await settle(hass)`. Phone attributes: source "Spotify Connect", media_content_id "x-sonos-vli:RINCON_X:2,spotify:track:x". Every test that loads the package uses the `services` fixture.
5. Run both Done-when commands from the worktree root.

### Test list (`ha/tests/test_ha_livingroom_music_core.py`)
Each test fails before the patch (RED: the package file is missing, so load_package or the file read raises FileNotFoundError and pytest reports N failed) and passes after. Command 1 runs all of them; command 2 runs the unchanged 635-test suite (at least one test, rule 5).
1. `test_package_loads`: only allowed top-level keys; the six automations and the script load enabled; both helpers off; timer durations 0:15:00 and 0:10:00; no service call at load.
2. `test_package_text_rules`: every package line containing `volume_level` matches `^\s*volume_level:\s*0\.15\s*$` (fixed set, no read of the reported volume); the text has no `pixel_9_pro_xl`, `spotcast`, `music_assistant`, `sonos.snapshot` or `sonos.restore`. (Bad input: the retired Pixel; with the services teardown guard.)
3. `test_start_either_sensor[fp2|fp300]`: 12:00, sonos idle, one sensor on: records are volume_set 0.15 on both speakers, play_media with the Lazy Sunday URI, playlist type and enqueue replace, shuffle_set true, in that order; ha_session stays off.
4. `test_both_sensors_at_once_one_start`: both sensors set on in one loop turn: exactly one play_media. (Bad input.)
5. `test_one_on_other_unavailable_is_occupied`: FP300 unavailable, FP2 on: starts; then with sonos playing, FP300 stays unavailable for 16 min: no media_pause. (Bad input.)
6. `test_both_unavailable_is_empty`: playing, both sensors go unavailable: no pause at 899 s, media_pause at 900 s. (Bad input.)
7. `test_empty_room_pauses_and_resumes[ha_started|app_content]`: sonos playing (Lazy Sunday after an HA start, or Sonos-app content with ha_session off), both clear: no pause at 899 s, media_pause at 900 s; set sonos paused; ha_session is on; a sensor on: only media_play on media_player.sonos (no play_media, no volume_set).
8. `test_empty_timer_restarts`: clear, 600 s, sensor on (cancel), clear again, 899 s: no pause; 1 s more: media_pause.
9. `test_blocker_pauses_and_resumes[lg|marantz|marantz_playing|marantz_paused|armed_away|armed_night|arming|pending|triggered]` (each also with Sonos-app content, ha_session off at the start): occupied, sonos playing, blocker set: media_pause and ha_session on; sonos set paused; blocker cleared (LG or Marantz off, or disarmed): media_play.
10. `test_blocker_blocks_start[same params]`: blocker on, sensor on: no sonos call.
11. `test_not_blocking[alarm disarmed|alarm armed_home|lg, marantz × off, standby|lg, marantz, alarm × unknown, unavailable]`: sensor on: fresh start runs. (Bad inputs: blocker unknown or unavailable; alarm outside the list.)
12. `test_speaker_unavailable_no_call[sonos|bedroom × unavailable|unknown]`: sonos idle (or the unavailable state), sensor on, then LG on and off: no sonos call, no ERROR log. Plus one case: bedroom unavailable, sonos playing, LG on: media_pause (pause needs only Living Room One). (Bad input.)
13. `test_quiet_hours_start_boundary[21:59:59.5 starts|22:00:00.0 none|22:00:00.5 none|07:29:59.5 none|07:30:00.0 starts|07:30:00.5 starts]`: `freezer.move_to` that exact instant before load_package, sensor on. (Bad input: boundaries.)
14. `test_quiet_hours_at_22[playing|paused|hands_off_on]`: occupied, ha_session on, at 21:59:59.5 with sonos playing (or paused, or playing with Hands-off on): no call; advance 0.5 s: media_pause only in the playing case, no Sonos call in the other two, and ha_session off in all three; then advance to 07:30:00.5 (Hands-off case: it reset at 06:00), sonos paused, a sensor off and on: fresh start (volume_set 0.15, play_media), not media_play.
15. `test_hands_off_blocks_everything[case]`: each case sets a state that makes a Sonos call with Hands-off off, then turns Hands-off on (restart case: restored on via `restore=`), then makes the trigger; asserts `services.sonos_calls() == []`. Cases (precondition, trigger): presence (sonos idle; sensor on), empty (sonos playing, occupied; both clear, advance 900 s), lg_on (playing, occupied; LG on), lg_off (paused, ha_session on, occupied, LG on; LG off), alarm (playing, occupied; armed_away), disarmed (paused, ha_session on, occupied, armed_away; disarmed), quiet (playing at 21:59:59.5; advance 0.5 s), speaker_back (paused, ha_session on, occupied, sonos unavailable; sonos paused), restart (paused, ha_session on, occupied; `start=True`). (Bad input: Hands-off.)
16. `test_hands_off_resets_at_06`: hands_off on at 05:59:59.5; advance 0.4 s: still on; advance 0.1 s: off. (Bad input: boundary.)
17. `test_phone_session_not_replaced`: ha_session on, sonos paused, then set playing with phone attributes: ha_session turns off; a sensor off-then-on edge gives no sonos call; LG on gives one media_pause (the stop rules still pause it) and ha_session stays off; sonos set paused (same attributes) and LG off within 10 min: no media_play, play_media or volume_set.
18. `test_phone_session_ends_after_10_min[paused_keeps_attrs|idle_keeps_attrs|idle_clears_attrs]`: phone playing, then that state (same attributes, or source and media_content_id removed); sensor off and on at 599 s: no call; at 600 s and later, sensor off and on: fresh start (volume_set 0.15 both, play_media replace, shuffle_set).
19. `test_spotify_connect_without_vli_is_not_phone`: occupied, sonos playing with source Spotify Connect and media_content_id x-sonos-spotify:spotify%3atrack%3ax; LG on: media_pause and ha_session on (not a phone session); sonos set paused (same attributes), LG off: media_play. (Bad input.)
20. `test_restart_occupied_paused_resumes[ha_paused|not_ha_paused]`: `start=True`, sonos paused with Sonos-app attributes, both sensors on, 12:00; ha_session restored on (HA paused it before the restart): exactly one media_play, no play_media; restored off: fresh start. (Bad input: restart case.)
21. `test_restart_follows_start_rules[lg on|23:00|hands_off on]`: same as test 20 with that one change: no sonos call.
22. `test_restart_empty_starts_timer`: `start=True`, sonos playing, sensors off: media_pause at 900 s (rare-corner guard).
23. `test_playing_into_empty_room_pauses`: sensors off, sonos idle; set sonos playing (non-phone attributes): no pause at 899 s, media_pause at 900 s; with the timer already running, a second playing change does not restart it.
24. `test_restart_speakers_come_back`: `start=True`, restore ha_session on, both sensors on, media_player.sonos unavailable at start: no call; set it to paused: exactly one media_play. Same with media_player.bedroom unavailable at start then idle. (Bad input: restart case, live order.)
25. `test_fresh_start_script_hands_off`: hands_off on, call `script.livingroom_music_fresh_start` directly (blocking): `services.sonos_calls() == []`.
26. `test_fresh_start_script_hands_off_mid_sequence`: the test re-registers media_player.volume_set with its own callback that records the call and sets the Hands-off state on (`hass.states.async_set`); call the script: only that volume_set call, no play_media or shuffle_set. (Security P1: the per-call condition.)
27. `test_fresh_start_script_phone_session[playing|timer_active]`: sonos playing with phone attributes, or paused after a phone session with timer.livingroom_music_phone running; call the script directly: no play_media (and no Sonos call at all).
28. `test_fresh_start_script_phone_mid_sequence`: same override technique as test 26, but the volume_set callback sets media_player.sonos playing with phone attributes; call the script: the volume_set call only, no play_media or shuffle_set. (Security r2 P2.)
29. `test_ha_paused_flag`: ha_session on and sonos paused; an attribute-only update while paused keeps it; sonos set playing: off; then playing with an attribute-only update (new track): stays off; LG on: media_pause and on; at 22:00 with sonos playing: media_pause, and the flag ends off.
30. `test_fresh_start_script_may_start_guard[lg_on|marantz_on|marantz_playing|marantz_paused|armed_night|quiet_23:00|sonos_unavailable|bedroom_unavailable]`: call the script directly: no Sonos call. (Security r3 P2.)
31. `test_quiet_hours_pause_sets_no_flag`: 23:00, sonos playing Sonos-app content, both clear: media_pause at 900 s, ha_session stays off; advance to 07:30:00.5, sonos paused, a sensor off and on: fresh start, not media_play. (Correctness r4.)
32. `test_fresh_start_script_phone_before_shuffle`: same override technique as test 26, on media_player.play_media: its callback records the call and sets media_player.sonos playing with phone attributes; call the script: volume_set and play_media only, no shuffle_set. (Security r4.)
33. `test_reconnect_only_resumes`: ha_session off, sonos paused (Sonos-app content), occupied, 12:00; media_player.bedroom set unavailable, then paused: no Sonos call. (Correctness r5.)
34. `test_blocker_during_play_media_pauses`: occupied, sonos idle, 12:00; override media_player.play_media with a callback that records the call and sets the LG on; a sensor edge runs the fresh start (no shuffle_set, the guard stops it); then set sonos playing (non-phone attributes): media_pause, ha_session stays off. (Correctness r5; the 22:00 variant uses the same trigger and condition and is not tested separately.)

### Risks
- The ERROR-log guard may catch a harmless record from the harness itself; if so, the coder narrows it to loggers starting with `homeassistant.components.automation`, `homeassistant.components.script` and `homeassistant.helpers.script`, and says so in the patch notes.
- Template triggers fire only on a false-to-true edge after setup; a test that sets the trigger state before load_package sees no run. Tests set initial states through `states=` and make the edge after loading.
- Grouped Sonos: media_play and media_pause go to media_player.sonos only (coordinator); volume_set goes to both. Live behaviour is checked in card 4.

## Result
Core package and HA harness are built and uncommitted on branch frugo/2026-10-18-livingroom-music-core (worktree Blueprints_Home-wt/lm-core): ha/packages/livingroom_music.yaml plus ha/tests/ (conftest, pytest-ha.ini, behaviour tests). Both Done-when commands pass (104 HA tests; 635 in tests/), red on the clean base. Lane 2: five design-review rounds, three code-review rounds and one code arbiter FIX round; the second arbiter ruled proceed with one P3.
Test home is ha/tests/ (not tests_ha/): red-green only copies files matching its test-path patterns into the RED tree; cards 3 and 4 and the goal Done-when were updated to match. .frugo/inputs/ (harness model copies) is untracked, stays out of the commit and is deleted after the card closes.
Open P3:
- Codex security (arbiter ruling P3): the pause on a late playing edge counts HA starts and resumes only within 30 s; a resume that reports playing after more than 30 s while a blocker arrives is not paused. Follow-up: an explicit "HA playback pending" helper instead of the time window.
- Opus correctness: when a blocker interrupts a resume, the late-playing pause does not set the "HA paused this" flag, so when the blocker clears the start automation loads a fresh Lazy Sunday instead of resuming the track. Fix: allow the started trigger in the flag condition and change the test at ha/tests/test_ha_livingroom_music_core.py:532.
- Accepted rare corners (in the card): HA down over 22:00 (the reset does not run); music already playing at HA restart while a blocker is on is not paused until the blocker goes off and on again.
- Nothing auto-starts at 07:30 or when Hands-off turns off; paused content HA did not pause (for example paused in the Sonos app) is replaced by a fresh Lazy Sunday on the next start edge. Martin may want to confirm.
- Marantz and LG block in any state outside off, standby, unknown and unavailable (so a Marantz playing a network source blocks); Martin to confirm that "on" means powered on.
