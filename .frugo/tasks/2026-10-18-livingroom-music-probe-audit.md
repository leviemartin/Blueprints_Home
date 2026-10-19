---
id: 2026-10-18-livingroom-music-probe-audit
title: Livingroom music live probe note
goal: livingroom-background-music
issue: "leviemartin/Blueprints_Home#50"
status: done
lane: 2
coder: codex
step: codex
fix_rounds: 4
---

## Goal
Record the live Sonos, presence, TV, alarm and remote facts that the livingroom music package depends on, in one research note, pinned by a test. The note answers every probe question and states plainly any probe that failed. No HA write, no package code.

## Done when (runnable)
`env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests/test_livingroom_music_probe_note.py -q`
`env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests -q`

## Files likely touched
- `docs/superpowers/research/2026-10-18-livingroom-music-probe.md` (new)
- `tests/test_livingroom_music_probe_note.py` (new)
- `.frugo/probe/2026-10-18-livingroom-music-probe-audit.results.md` (orchestrator-supplied live results; read only for the coder, untracked, never in the diff, deleted before any commit)
- `docs/superpowers/research/2026-10-16-livingroom-fp300-live-audit.md` (style model, read only, not edited)
- `tests/test_circadian_livingroom_deploy.py` (style model for credential patterns and structure, read only, not edited)

## Bad inputs to handle
- Note file missing or empty
- A required section heading missing or out of order: Source, Entities, Probe results, Phone session attributes, Remote event types, Overlap matrix, Outside-HA controls, Open questions
- An Entities row whose present cell is not yes or no, or an entity marked no that is not named under Open questions
- A probe step id missing or repeated in the Probe results table
- A play step failed with UPnP 800 or 714 but the favorite-fallback row is not run or records no FV id
- Phone session detection line missing or repeated
- A required entity id missing from the note: media_player.sonos, media_player.bedroom, event.kitchen_button_1 to event.kitchen_button_4, binary_sensor.presence_sensor_fp2_e863_presence_sensor_1, binary_sensor.living_room_main_fp300_couch_occupancy_sensor, media_player.lg_webos_tv_oled65c9pla, media_player.marantz_cinema_50, media_player.mxn10, alarm_control_panel.house_alarm, switch.sonos_alarm_1, notify.mobile_app_savannah_s25_ultra
- A playlist URI missing: spotify:playlist:37i9dQZF1DWTc452KG008d or spotify:playlist:4IzLPBPewQ4PCOF3qMYgDT
- A Samuel automation id missing from the overlap matrix: 1701294514096, 1701295072034, 1701295128408, 1701294978959
- Conclusion line missing, not the last line, or repeated
- Probe row with no result recorded
- Snapshot or restore failure recorded without the fresh-reload fallback statement
- Credential-like text: eyJ tokens, "Bearer ", http:// or https:// URLs, IPv4 addresses, HASS_TOKEN=, password or api_key

## Risk flags
- secrets: the HA token is read by the orchestrator only; the note and test must hold no token, URL, IP or credential
- workflow rules: probe step (b) writes to live Sonos (sonos.snapshot, play_media, sonos.restore, pause and play, favorite fallback) and each step needs Martin's OK; the coder makes no HA write
- workflow rules: the phone Spotify Connect check needs Martin to start Spotify from his phone while the orchestrator reads the session

## Constraints carried over
- The coder writes the note from the orchestrator's live results only; the coder does not call HA.
- Note sections, in order: Source; Entities (role | entity_id | present); Probe results (one row per step); Phone session attributes; Remote event types; Overlap matrix (automation | id | state | shared entities); Outside-HA controls; Open questions; final line "Conclusion: <one line>". Exact layouts are in the Plan.
- Probe steps: sonos.snapshot, play spotify:playlist:37i9dQZF1DWTc452KG008d with play_media replace and shuffle_set true, read queue_size, media_playlist, shuffle, source, media_content_id; sonos.snapshot again, play spotify:playlist:4IzLPBPewQ4PCOF3qMYgDT, sonos.restore; check whether the Lazy Sunday track and position come back; pause then play to check the queue is kept; read the phone session source and media_content_id; restore the start state. On UPnP 800 or 714, retry as My Sonos favorites (favorite_item_id) and record the FV ids.
- If snapshot or restore fails, the note says so and card 3 uses the fresh-reload fallback.
- Phone session detection uses source Spotify Connect and media_content_id x-sonos-vli:, to be confirmed by the probe.
- The alarm entities and the TV, Marantz and MXN10 entities are read only.
- The test's credential patterns match tests/test_circadian_livingroom_deploy.py, so the note must contain no URLs.

## Out of scope
- Any package code: ha/packages/livingroom_music.yaml and tests_ha/ belong to later cards.
- Fixing any conflict found by the overlap audit; conflicts go to Open questions.
- Changing switch.sonos_alarm_1, the Bedroom One Sonos-app alarm, or Hue-app routines.
- Deleting anything, including the four Samuel automations (their export and deletion is a later deploy card).
- Writing to the AV chain (MXN10, Marantz, B&W speakers, Tap Dial automations); they stay read only.
- Circadian lights, FP2 and FP300 settings, the home-security package.
- Spotify, Spotcast or Music Assistant integrations.

## Open questions
none

## Decided by orchestrator
All earlier open questions, decided by orchestrator; Martin can revert.
- Live probe writes (snapshot, play_media, restore, pause, play, favorite fallback): the orchestrator asks Martin before each live HA write; the coder makes none.
- Source of live results: the orchestrator reads HA and Sonos live (inventory, probe rows, Savannah notify check, Bedroom One area, switch.sonos_alarm_1) and hands them to the coder as a results file.
- Paths: use the card's paths (docs/superpowers/research/2026-10-18-livingroom-music-probe.md, tests/test_livingroom_music_probe_note.py); the goal text is older.
- Phone session: Martin starts Spotify on the grouped speakers when the orchestrator asks.
- notify.mobile_app_savannah_s25_ultra: the probe checks it live; if absent the note says so and lists it under Open questions.
- Snapshot or restore failure is recorded and card 3 uses the fresh-reload fallback (goal Decisions, first card).
- An overlap conflict (for example the Samuel On automation pointing at the missing media_player.living_room) goes under Open questions only, no change (goal Out of scope).
- Baseline: the whole tests suite passes before the card starts (635 passed, run 2026-10-18).
- Card order, confirmed against the goal in the main checkout (.frugo/goals/livingroom-background-music.md, untracked, not visible from the worktree): probe-audit (1), core (2), remote-kids (3), deploy (4); so "card 3" is 2026-10-18-livingroom-music-remote-kids.
- Arbiter design decision (Martin, 2026-10-18): queue-loss consent covers any nonempty Ones queue whatever the source. Before the first write the orchestrator reads queue_size on both Ones independently of media_content_id; a nonempty queue needs his explicit yes before play-lazy-sunday; an unreadable queue state skips the destructive steps (not run: queue state unknown).
- Martin (2026-10-18): design phase ends with one final planner edit and no further design review: queue gate covers every queue-replacing step (play, favorite, phone-session, restore-start-state), declined or unknown means read-only observation; positions compared as effective position; corner-case rules cut. Martin chose the next coder step: codex after that edit.

## Plan
Planner: Opus, 2026-10-18. Lane 2 confirmed (live Sonos writes with Martin's OK, secrets risk, goal is Lane 2). Coder: `codex`.

**Card edits by the planner (revertible):** Files list entries are now backtick-quoted, because `file_entries` takes the whole line as the path otherwise and the coder would get no file contents. The results file and both style models are listed as read-only inputs so their contents reach the coder. Two sections were added to the note: Remote event types (card 2026-10-18-livingroom-music-remote-kids asks for the event_type values) and Open questions (the Decided section sends a missing Savannah notify and overlap conflicts there). Bad inputs gained the matching items.

**Order of work**
1. Orchestrator, live (each write only after Martin's OK; reads need no OK). First read `start-state`, before any write, including queue_size on both Ones whatever their source (Martin's decision in Decided). Queue gate: queue_size 0 on both: carry on. Nonempty on either: before `play-lazy-sunday` tell Martin plainly "The Ones hold a queue of <n> tracks; the probe, your phone session and the end-state replay can replace it, and it cannot be brought back. OK to lose it?" and run the gated steps only on his explicit yes. Unreadable on either (or `start-state` not `ok:`): no question, the gated steps are skipped. The eleven gated steps (every step that can replace the queue, plus the reads that depend on them) are `play-lazy-sunday`, `read-lazy-sunday`, `snapshot-2`, `play-pairilijst`, `read-pairilijst`, `restore`, `restore-check`, `pause-play`, `favorite-fallback`, `phone-session` and `restore-start-state`. When skipped, each result cell starts exactly `not run: queue-loss not approved` (Martin said no) or `not run: queue state unknown`, optionally followed by `; observed <current state>` from a read-only look; an Open questions bullet containing `queue` is added. For `snapshot-2`, get Martin's OK before `read-lazy-sunday`, then run the read and the snapshot back to back. Before each position read (`read-lazy-sunday`, `restore-check`) run `homeassistant.update_entity` on media_player.sonos, or record the effective position `media_position + (read time - media_position_updated_at)` while playing; the 10 s comparison uses effective positions. Then run the probe steps below on the grouped Ones and the read-only inventory (entities, event_types of the four remote buttons, the four Samuel automations, switch.sonos_alarm_1, the Bedroom One area, Hue-app button assignments as far as HA shows them, the Savannah notify service). Martin starts Spotify from his phone for `phone-session` (only when the gate allows it).
2. Orchestrator writes the results file (format below) in the card worktree, then runs, from the worktree root, `rg -q -P 'eyJ[A-Za-z0-9_-]{8,}|(?i)bearer\s|(?i)https?://|\b\d{1,3}(\.\d{1,3}){3}\b|HASS_(TOKEN|SERVER)\s*=|(?i)\b(password|api[_-]?key)\b' .frugo/probe/2026-10-18-livingroom-music-probe-audit.results.md` and requires exit status exactly 1. Exit 0 (a hit) or 2 (scanner error) means stop: report only "results-file credential gate failed", never echo the match, fix the file and re-run. Only then set `status: ready` and run the coder.
3. Coder writes the test file first (RED on base), then the note, from the results file only.
4. Checks and the two code reviews run with the results file present (red-green's clean check allows untracked files under `.frugo/`; the reviewers see it as untracked context and check the note against it).
5. After the reviews pass and before asking for the commit OK, the orchestrator deletes the results file in the card worktree (`rm` of that one file, which the orchestrator created) and re-runs both Done-when commands; they must still pass, which proves the test does not read it. Commits stage explicit paths only, so it cannot enter the diff. It is never created in the main checkout.

**Results file** `.frugo/probe/2026-10-18-livingroom-music-probe-audit.results.md` (untracked, orchestrator-written, read only for the coder)
- First line `# Livingroom music probe results (orchestrator, <YYYY-MM-DD>, Amsterdam time)`.
- Then the same `##` sections, table headers and row rules as the note below, filled from the live reads, except: no Conclusion line, and an extra last section `## Raw readings` holding `key: value` lines per step (for example `read-lazy-sunday queue_size: 52`) that the coder may summarise in the note. Positions in the results file are effective positions (see Order of work step 1).
- Redaction, applied by the orchestrator before writing: no server name, URL, IP, token, Sonos household id or file path from the host. Leave out `entity_picture` and `media_image_url`. A value containing `://` is written as `redacted-url`; a value matching the IPv4 pattern, including version-like dotted values with three dots (for example a firmware `16.2.1.3`), is written as `redacted-ip` or left out. A long opaque id inside `media_content_id` may be cut after its scheme and kind with `...` (for example `x-sonos-vli:RINCON_...:2,spotify:...`). No `|` inside a cell (use `/`). Avoid the words password and api_key.

**Note layout** `docs/superpowers/research/2026-10-18-livingroom-music-probe.md`
- Line 1 `# Livingroom music live probe`. Then exactly these `##` headings, in this order, and no other `##` heading: `Source`, `Entities`, `Probe results`, `Phone session attributes`, `Remote event types`, `Overlap matrix`, `Outside-HA controls`, `Open questions`. The very last line is `Conclusion: <one line>` (after Open questions), and it appears once.
- Table parsing rule (the test uses it): a table row is a line in that section starting with `|`; cells are `line.strip().strip("|").split("|")`, each stripped of spaces and then of backticks. The first row is the header (exact cells below); the separator row (only `-`, `:` and spaces) is skipped. Every cell is non-empty.
- Source: prose. Who ran it (orchestrator), date, which steps were live writes with Martin's OK, and for a nonempty or unreadable start queue exactly one gate sentence: `Martin approved the loss of the start queue.`, `Martin did not approve the loss of the start queue.` or `The start queue state could not be read; the gated steps were not run.` (none of the three for an empty queue). It says how the end state was restored (re-applying the start-state readings; sonos.snapshot keeps one snapshot per speaker, so snapshot-2 replaced snapshot-1) and contains `end state matched start-state` when `restore-start-state` starts `ok:`, `end state differed` when it starts `FAILED:`, neither when it was not run. No server, URL, IP or token.
- Entities: header `Role | entity_id | present`. One row per entity, each exactly once in the entity_id column: `media_player.sonos`, `media_player.bedroom`, `event.kitchen_button_1`, `event.kitchen_button_2`, `event.kitchen_button_3`, `event.kitchen_button_4`, `binary_sensor.presence_sensor_fp2_e863_presence_sensor_1`, `binary_sensor.living_room_main_fp300_couch_occupancy_sensor`, `media_player.lg_webos_tv_oled65c9pla`, `media_player.marantz_cinema_50`, `media_player.mxn10`, `alarm_control_panel.house_alarm`, `switch.sonos_alarm_1`, `notify.mobile_app_savannah_s25_ultra`. present is `yes` or `no`; every `no` entity id also appears in the Open questions section.
- Probe results: header `# | step | result`. The step column lists exactly these ids, once each, in this order: `start-state` (state, volume_level, source, media_content_id, group_members, queue_size, media_title, media_artist, media_playlist of both Ones, and the My Sonos favorites list with FV ids), `snapshot-1`, `play-lazy-sunday` (play_media spotify:playlist:37i9dQZF1DWTc452KG008d, enqueue replace, then shuffle_set true), `read-lazy-sunday`, `snapshot-2`, `play-pairilijst` (spotify:playlist:4IzLPBPewQ4PCOF3qMYgDT), `read-pairilijst`, `restore`, `restore-check`, `pause-play`, `favorite-fallback`, `phone-session`, `restore-start-state`. The `#` column is exactly 1 to 13 in row order.
  - Snapshot note: sonos.snapshot keeps one snapshot per speaker, so `snapshot-2` overwrites `snapshot-1` and `restore` returns to the Lazy Sunday state only. `restore-start-state` uses no snapshot: re-join or unjoin to the `start-state` group_members, set each One's volume_level, replay the start media if it was playing or paused, pause or stop to match, then read the same attributes again (including queue_size, media_title, media_artist, media_playlist) and compare with `start-state`. No extra sonos.restore from snapshot-1 (decided by planner, simplest; the HA Sonos snapshot does not save the queue anyway).
  - Result grammar ("no result recorded" rule): every result cell matches `^(ok|FAILED|not run): \S`. Anything else, including an empty cell, `-`, `n/a`, `TBD` or `?`, counts as no result. Attribute values are written `<name> <value>`, separated by `, ` (for example `queue_size 52`).
  - Required names when the row is `ok:`: `start-state` names `queue_size`, `media_title`, `media_artist`, `media_playlist`, `media_content_id` (its queue_size is the larger of the two Ones' values, or `unknown`); `read-lazy-sunday` and `read-pairilijst` name `queue_size`, `media_playlist`, `shuffle`, `source`, `media_content_id`, and `read-lazy-sunday` also `media_title` and `media_position`; `restore-check` names `media_title` and `media_position`; `pause-play` names `queue_size` and `media_playlist`.
  - `restore-check` is `ok:` only when the title matches the `read-lazy-sunday` title and the effective position is within 10 s of it (the orchestrator judges this; the test checks the names only); anything else is `FAILED: <what differed>` or `not run: <reason>`.
  - `restore-start-state` is one of three alternatives: (a) `ok: re-applied start-state readings; end state matched start-state ...`; (b) `FAILED: re-applied start-state readings; end state differed: <attributes>`; (c) matches `^FAILED: .+; end state differed: \S` (a step failed part-way). Or the gate's `not run:` value.
  - Queue gate rule (test helper `gate(text)` returns `empty`, `approved`, `declined` or `unknown`): `unknown` when `start-state` is not `ok:` or its queue_size is `unknown`; else `empty` when queue_size is 0; else `declined` when `play-lazy-sunday` starts `not run: queue-loss not approved`; else `approved`. For `declined` and `unknown`, all eleven gated rows start with the matching `not run:` value and Open questions has a bullet containing `queue`. For `approved`, if a play replaced the queue (`play-lazy-sunday` or `play-pairilijst` starts `ok:` or contains `played in place via FV:`), `restore-start-state` starts `FAILED:` and contains `queue` and Open questions has a bullet containing `queue`; otherwise the normal forms apply. For `empty`, nothing extra.
  - Fallback rule: if any of `snapshot-1`, `snapshot-2`, `restore`, `restore-check` is not `ok:`, the section has this line, exactly once, on its own line after the table: `Snapshot or restore failed: card 2026-10-18-livingroom-music-remote-kids uses the fresh-reload fallback.` If all four are `ok:`, the line is absent.
  - Favorite rule (basics only): trigger = a `play-lazy-sunday` or `play-pairilijst` cell that is `FAILED:` and matches `\bUPnP (Error )?(800|714)\b`. The orchestrator then plays that playlist's My Sonos favorite (from the `start-state` favorites list) in place and runs the remaining steps against it, writing `; played in place via FV:<id>` in the play cell, or `; no favorite for <uri>` when there is none (plus an Open questions bullet naming the URI). On a trigger, `favorite-fallback` is `ok:` or `FAILED:` and contains `FV:` or `no favorite for` for each triggered play. Without a trigger it is `not run: no UPnP 800 or 714`, or the gate's `not run:` value when the gate skipped it.
- Phone session attributes: header `attribute | value`; rows include `source` and `media_content_id` (others optional), values non-empty (`not read` when the step did not run). After the table, exactly one line matching `^Detection rule: (confirmed|not confirmed)\.$` Rule: `confirmed` exactly when the `phone-session` probe row starts `ok:`, the `source` value is `Spotify Connect` and the `media_content_id` value starts `x-sonos-vli:`; otherwise `not confirmed` (always when `phone-session` is not `ok:`).
- Remote event types: header `entity_id | event_types`; one row each for `event.kitchen_button_1` to `event.kitchen_button_4`, the event_types list as read.
- Overlap matrix: header `Automation | id | state | shared entities`; the id column holds `1701294514096`, `1701295072034`, `1701295128408` and `1701294978959` (other rows allowed, for example the circadian instance). A conflict found (such as the Samuel On automation targeting the missing media_player.living_room) is stated in its row and also under Open questions.
- Outside-HA controls: header `control | finding`; rows for `switch.sonos_alarm_1`, `Bedroom One area` and `Hue-app button assignments`, plus `Phone Spotify Connect` if useful.
- Open questions: blank lines are ignored; the remaining lines are either exactly one line `none`, or one or more `- ` bullet lines and nothing else (a stray prose line fails).

**Tests** `tests/test_livingroom_music_probe_note.py` (no `__init__.py`; copy the model's style: module constants, `ROOT = Path(__file__).resolve().parent.parent`, read NOTE inside each test, never at import time)
- Constants: NOTE, SECTIONS, ENTITY_IDS, PLAYLISTS, SAMUEL_IDS, STEP_IDS, CONTROLS, FALLBACK_LINE, RESULT_RE, and `CREDENTIAL_PATTERNS` copied verbatim from tests/test_circadian_livingroom_deploy.py (it covers the card's `HASS_TOKEN=` item via `HASS_(TOKEN|SERVER)\s*=`).
- Helpers: `section(text, heading)` (lines after `## heading` up to the next `## ` heading or the Conclusion line) and `rows(lines)` (the parsing rule above, returning header and data rows). Each rule is a function `check_<name>(text)` that raises AssertionError; the positive tests call it on the real note.
1. `test_note_exists_and_not_empty`: NOTE exists and `text.strip()` is non-empty. Covers Done when 1; bad input "missing or empty".
2. `test_sections_in_order` (`check_sections`): the `^## (.+)$` headings equal SECTIONS. Bad input "heading missing or out of order".
3. `test_entities_table` (`check_entities`): header, each ENTITY_ID exactly once in the entity_id column, present in {yes, no}. Bad inputs "entity id missing" and "present cell".
4. `test_absent_entities_under_open_questions` (`check_absent_named`): each `no` id must match `(?<![\w.])` + `re.escape(id)` + `(?!\w)(?!\.\w)` in the Open questions section (whole id; a trailing sentence period is accepted, while `media_player.sonos_beam` or `media_player.sonos.x` do not count for `media_player.sonos`). Bad input "entity marked no".
5. `test_playlist_uris_recorded` (`check_playlists`): both URIs in the note. Bad input "playlist URI missing".
6. `test_probe_steps_once_in_order` (`check_steps`): step column == STEP_IDS and the `#` column == `[str(n) for n in range(1, 14)]`. Bad input "step id missing or repeated".
7. `test_every_probe_row_has_a_result` (`check_results`): RESULT_RE on every result cell, the required names, the three `restore-start-state` alternatives, and the queue gate rule. Bad input "no result recorded".
7b. `test_check_results_accepts_each_restore_start_state_form`, parametrized over `ok: re-applied start-state readings; end state matched start-state`, `FAILED: re-applied start-state readings; end state differed: volume_level` and `FAILED: unjoin; end state differed: group_members`: first replace the `start-state` cell with the fixed non-queue cell `ok: state paused, volume_level 0.15, source Sonos, media_content_id none, queue_size 0, media_title none, media_artist none, media_playlist none`, then put the form in the `restore-start-state` cell; `check_results` passes.
7c. `test_source_agrees_with_restore_start_state` (`check_source`): the Source rule (gate sentence matches `gate(text)`; end-state phrase matches the row).
7d. `test_skipped_note_passes`, parametrized over `declined` and `unknown`: from the real note, set `start-state` to the 7b cell with `queue_size 40` or `queue_size unknown`, set all eleven gated rows to the matching `not run:` value, put the matching gate sentence in Source (removing the other two and both end-state phrases), make FALLBACK_LINE present once, and make the Open questions body (a lone `none` replaced) contain `- Start queue: probe not run (queue).`; then `check_results`, `check_favorite`, `check_fallback`, `check_source` and `check_open_questions` all pass.
8. `test_fallback_line_matches_snapshot_restore_results` (`check_fallback`). Bad input "failure without fallback statement".
9. `test_favorite_fallback_after_upnp_error` (`check_favorite`). Bad input "UPnP 800/714 without FV id".
10. `test_phone_session_attributes` (`check_phone`): header, source and media_content_id rows, exactly one Detection rule line agreeing with the rule above. Bad input "detection line missing or repeated".
11. `test_remote_event_types` (`check_remote`): four rows, non-empty event_types.
12. `test_overlap_matrix_has_samuel_automations` (`check_overlap`). Bad input "Samuel id missing".
13. `test_outside_ha_controls` (`check_controls`): the three CONTROLS rows with non-empty findings.
14. `test_open_questions_form` (`check_open_questions`): ignoring blank lines, `none` alone, or only `- ` bullets.
15. `test_conclusion_single_and_last` (`check_conclusion`): `re.findall(r"^Conclusion: .+$", text, re.M)` has length 1 and equals `text.rstrip("\n").splitlines()[-1]`. Bad input "Conclusion missing, not last, or repeated".
16. `test_no_credentials_in_note` (`check_credentials`): no CREDENTIAL_PATTERNS match. Bad input "credential-like text".
17. `test_check_rejects_mutated_note`, parametrized `(check, mutate)`; each mutation changes the real note text and `pytest.raises(AssertionError)` from the named check. Mutations find a row by an exact cell match (step column, entity_id column, id column) within its own section, never by substring over the whole note. One mutation per bad input or rule: empty text and dropping `## Remote event types` (check_sections); deleting the `media_player.bedroom` row and setting a present cell to `maybe` (check_entities); setting the `media_player.sonos` row to `no`, removing any whole-id mention of it and a lone `none` from Open questions, then appending `- media_player.sonos_beam is missing` (check_absent_named); adding a stray prose line `See above.` after a bullet (check_open_questions); replacing both playlist URIs with `spotify:playlist:x` (check_playlists); duplicating the `pause-play` row (check_steps); setting the `restore-start-state` cell to `TBD` (check_results); with the 7b cell at `queue_size 40`, `play-lazy-sunday` `ok: played`, an Open questions bullet `- Start queue lost (queue).` and `restore-start-state` alternative (a) (check_results, approved gate); with `queue_size 40`, all eleven gated rows `not run: queue-loss not approved` except `pause-play` set to `ok: queue_size 40, media_playlist C` (check_results, declined gate); with `queue_size 40` and `play-lazy-sunday` `ok: played`, removing all gate sentences from Source (check_source); toggling FALLBACK_LINE (check_fallback); `play-lazy-sunday` `FAILED: UPnP Error 800 received` with `favorite-fallback` `not run: no UPnP 800 or 714` (check_favorite); flipping the Detection rule line (check_phone); deleting the `1701294978959` row (check_overlap); appending a second Conclusion line (check_conclusion); inserting each credential sample, a URL, `192.0.2.1`, `Bearer x`, a JWT-like `eyJ` string, `HASS_TOKEN=x`, `password`, `api_key` (check_credentials). Build every credential sample by string concatenation (as the model does with `"HASS" + "_TOKEN"`) so this file's own source passes test 18.
18. `test_no_credentials_or_live_access_in_this_test`: copy the model's `test_no_credentials_in_migrated_instance_or_this_test` (scrub the CREDENTIAL_PATTERNS assignment, scan the rest, forbid `"hass" + "-cli"`, `"HASS" + "_TOKEN"`, `"." + "config/"`), and also forbid `"." + "frugo"` in the source (the test must never read the results file) and, via `ast`, any import of `requests`, `urllib`, `http`, `socket`, `subprocess` or `aiohttp` (the test needs no live HA).
- Done when 2 (whole `tests` suite) runs these plus the existing 635.
- RED on base: red-green applies only the test file, so the note is absent. Tests 1 to 17 fail on the missing file; test 18 passes. Reading NOTE inside each test (and inside the parametrized test body, not in the parametrize list) keeps collection working.

**Not done here:** no HA call by the coder, no package code, no `tests_ha/`, no change to the style models, no `.prev.json`, no deploy file.

## Result
Probe note and its 58-test file are written and uncommitted on branch frugo/2026-10-18-livingroom-music-probe-audit (worktree Blueprints_Home-wt/lm-probe); both Done-when commands pass with the results file deleted (58 passed; 693 passed), red on the clean base, both Lane 2 code reviews done (Opus PASS, Codex security P3 only). Probe: sonos.restore returns the position but not the track or queue (fresh-reload fallback for card 3); phone session confirmed (Spotify Connect, x-sonos-vli:); media_playlist is empty after a playlist play (card 3 needs its own owner helper); Samuel On targets missing media_player.living_room.
Open P3:
- Codex security: full-suite success lacked evidence in the review input (the red-green output was truncated); the full suite was re-run after deleting the results file: 693 passed.
- Hue-app button assignments for the Music Remote cannot be read from HA; Martin to confirm there are none.
- Music Remote battery sensor reads 15 percent.
