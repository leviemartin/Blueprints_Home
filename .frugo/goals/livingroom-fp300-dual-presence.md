---
goal: livingroom-fp300-dual-presence
title: 'Circadian living room: add FP300 couch sensor'
status: done
---

## Aim
Living room lights treat the FP2 and the FP300 as one room so the couch and dog bed count as presence

## Decisions
- Repo: ~/AI/projects/Blueprints_Home. Slug: livingroom-fp300-dual-presence. Aim: Living room lights treat the FP2 and the FP300 as one room so the couch and dog bed count as presence.
- Edit circadian_livingroom.yaml in place as v3.0.0. No new file and no v2 copy (Martin, round 1).
- Presence combine: either sensor on means presence. Lights go off only after both sensors are clear for the off delay (Martin, round 1).
- Lux: FP2 lux only, as today. FP300 illuminance is ignored, with thresholds unchanged at 150 lx on and 400 lx off for 5 min (Martin, round 1).
- Dog guard: accept and test (Martin, round 2). The FP300 counts like the FP2 at all times, including the late-night window. The stay-on is documented, and no cap logic is in this goal.
- Night profile: keep as today (Martin, round 2). Presence still turns lights on at the Night values (22:00 to 06:00, 20 percent), and there is no quiet window.
- Zones: all lights together (Martin, round 2).
- FP300 unavailable or unknown: treated as clear (Martin, round 2). One notice is sent after 30 min unavailable or unknown, as a push to notify.mobile_app_martin_fold through an optional notify.* list input, where an empty list disables it (Martin, round 3). The push runs after the light calls.
- Override: keep override_entity exactly as today, and add no TV or media_player input (Martin, round 3).
- FP300 setup: Zigbee2MQTT, presence source mmWave+PIR, absence_delay_timer 60 s, set by hand and documented in the README (Martin, round 3).
- Lane 1, budget track only (Martin, round 3).
- Late-night fast off (Martin, new requirement; window read as 23:00 to 06:30, across midnight, 6:30 pm taken as a slip for am): inside the window, once both sensors are clear the off delay is late_night_timeout (default 1 min). Outside it, presence_timeout (5 min) is unchanged.
- Decided by orchestrator, Martin can revert: late_night_start (23:00:00), late_night_end (06:30:00) and late_night_timeout (1 min) are blueprint inputs. The window is independent of the Night brightness profile. Dog-guard behaviour is unchanged. Night off comes about 2 min after the last motion (60 s device delay plus 1 min).
- Decided by intake, routine detail, Martin can revert: off timing uses a short (late_night_timeout) and a long (presence_timeout) state trigger per sensor, each to off, unavailable or unknown. On firing, each re-checks that the other sensor has been clear for at least the same duration (last_changed). The short trigger acts only inside the window, where the test is start <= now or now < end. There is no extra boundary trigger: a clear already running at 23:00, or one whose 1-min mark falls after 06:30, finishes on presence_timeout (at most 4 min later than ideal). This is documented and tested.
- Pre-existing behaviour kept: off timers that expire while the override is on are not replayed after resume.
- The planner must read live from HA: the circadian instance config (id, alias, use_blueprint.path and input), the FP2 presence and lux entity IDs, the FP300 presence entity ID, and its device_class (occupancy or presence). These decide the selector.
- No backwards-compatibility shims. presence_entity and its single presence_off trigger are replaced.
- Gap: deploy/ has no circadian instance JSON, and tests/ has no circadian test. A card exports the live instance, migrates it through scripts/deploy-blueprint.sh (dry-run first; backup in deploy/*.prev.json), and adds tests/test_circadian_livingroom_structure.py following the existing pytest pattern (HassLoader, rendered variables, expectations from the contract).
- Drift: requirements_circadian.md gives 300 lx; the code uses 150/400. The requirements file is updated to match the decisions.
- Run a live overlap audit and interaction matrix before brief approval: dinner_table_lights.yaml, lg_sleep_movie.yaml, adjacent_room_lights.yaml (same circadian formula, unchanged here), the override helper, and any automation using the FP2 or FP300 entities or the living room lights.
- Validation: pytest structure and render tests, the deploy dry-run, the live deploy state=on assert, and one live FP300-only trace. No multi-day observation as a gate.
- Visuals: no rendered mock-up needed.

## Done when
- `cd ~/AI/projects/Blueprints_Home && ~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests/test_circadian_livingroom_structure.py -q` passes. The new test file pins the v3.0.0 contract, with expectations taken from the contract, not the code. Its structure and rendered cases cover: the name ends in v3.0.0; inputs include the FP2 presence, the FP300 presence, late_night_start (default 23:00:00), late_night_end (default 06:30:00) and late_night_timeout (default 1 min); presence_entity is gone.
- Same test file, either-on: FP2 on with FP300 off, and FP2 off with FP300 on, each turn all hue_bulbs and hue_ceiling on while lux is below 150.
- Same test file, off timing: both clear outside the late-night window (e.g. 21:00) switch the lights off only after presence_timeout (5 min), never at 1 min. Both clear inside the window switch them off after late_night_timeout (1 min), at 23:30, 02:00 and 06:29 but not at 06:31 or 22:59. The both-clear duration counts from the later sensor's clear: one sensor's timer expiring while the other cleared seconds ago or is still on switches nothing off.
- Same test file, boundaries: a both-clear that started before the window opens finishes on presence_timeout, and a clear whose 1-min mark falls after 06:30 waits for presence_timeout. Both are pinned as specified behaviour.
- Same test file, FP300 down: unavailable or unknown counts as clear in both timers, so the FP2 alone decides. After 30 min unavailable or unknown, one notify call goes to each configured notify.* target after the light calls; an empty list sends nothing.
- Same test file, unchanged parts: lux decisions read only the FP2 illuminance input (150 lx on, 400 lx off for 5 min). With override_entity on the run stops before any light call, and switching it off re-applies the lights when presence is on, with no late-night special case. The Night profile (22:00 to 06:00, 20 percent) is unchanged and independent of the late-night window; presence at 03:00 still turns lights on at the Night values.
- `cd ~/AI/projects/Blueprints_Home && ~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q` passes (whole suite, no regressions).
- `cd ~/AI/projects/Blueprints_Home && bash scripts/deploy-blueprint.sh --dry-run circadian_livingroom.yaml <ha-blueprint-path read live> deploy/circadian_livingroom_<instance id>.json` exits 0. The instance file is exported live and migrated: no unknown keys, all required inputs present, notify targets set to [notify.mobile_app_martin_fold], late-night inputs at their defaults.
- After Martin's deploy OK: `bash scripts/deploy-blueprint.sh circadian_livingroom.yaml <ha-blueprint-path> deploy/circadian_livingroom_<instance id>.json` exits 0. The script asserts the instance reads state=on after the reload; the previous config is saved to deploy/<id>.prev.json.
- Live check at deploy, once, no multi-day observation: one presence-on trace from the FP300 alone (sit on the couch out of FP2 view) shows the turn-on branch.
- README.md and requirements_circadian.md describe v3.0.0: both sensors, the either-on/both-clear rule, the late-night 1-min off window and its boundary behaviour, FP2-only lux, the FP300-down notice, the documented dog stay-on behaviour, and an FP300 setup note (Zigbee2MQTT, mmWave+PIR, absence_delay_timer 60 s, so about 2 min from last motion to off at night).
- The repo has no yamllint or HA config-check tooling; the deploy-blueprint.sh dry-run parse and schema check is the YAML gate.

## Out of scope
- Any dog-guard cap, time window or distance-zone exclusion. The dog on the bench still keeps the lights on at night through the FP300. Martin tests this over a few evenings and decides in a later goal.
- An extra trigger at the window start or end to shorten a both-clear that is already running. The boundary behaviour is documented instead.
- Using FP300 illuminance, temperature, humidity, target_distance or battery level.
- Splitting lights by zone. All lights stay one group.
- A night quiet window or a separate night brightness. The Night profile is unchanged.
- Any TV or media_player input. The override input stays exactly as today.
- Pre-existing behaviour: off timers that expire while the override is on are not replayed when it is switched off.
- Writing FP300 device settings from the blueprint. absence_delay_timer and the presence source are set by hand in Zigbee2MQTT and recorded in the docs.
- A light watchdog for when both sensors are unavailable.
- Changes to adjacent_room_lights.yaml, dinner_table_lights.yaml or lg_sleep_movie.yaml.
- Cleaning up the existing v2.2.0 logic beyond what the two-sensor and late-night changes need.

## Remove
- The single presence_entity input, its sensor_presence variable, and the single presence_off trigger with its one for: duration. They are replaced by the two sensor inputs and the per-sensor short and long off triggers, with no compatibility alias.
- The README wording that describes the blueprint as single-sensor ("utilizes the Aqara FP2 (or any lux+presence sensor)").
- The requirements_circadian.md lines that list the FP2 as the only presence sensor, and the stale 300 lx threshold (the code uses 150/400).
- The v2.2.0 description header in circadian_livingroom.yaml, replaced by v3.0.0.
- The presence_entity key in the live instance config, replaced during the migration. The old config survives only as deploy/<id>.prev.json, the deploy script's backup.

## Risks
- Lane 1. Home lighting automations only: nothing moves, heats or locks. No trust-boundary or auth change, and the HA instance write is reversible through deploy/<id>.prev.json. The planner may raise the lane; only Martin may lower it.
- Accepted behaviour: the dog on its bench keeps the lights on after everyone has left, at night as well, for as long as the FP300 reads presence. Documented, not fixed.
- Late-night 1 min is aggressive. Someone sitting still out of FP300 mmWave view, or in an FP2 dead spot, gets lights off about 2 min after the last detection (60 s device delay plus 1 min). Mitigated by mmWave holding still people, and the timeout is an input.
- Timer design: HA state-trigger for: timers are not tied to mode: restart. With two sensors, the off path must fire on each sensor's own clear timer, then re-check that the other sensor is clear (off, unavailable or unknown) for at least the same duration, using last_changed. Without that re-check the earlier sensor's timer switches lights off while the later one cleared only seconds ago. Both a 1-min and a presence_timeout trigger exist per sensor; the short one acts only inside the window. Covered by rendered tests.
- HA restart resets last_changed, which can lengthen one both-clear after a restart. Accepted as harmless (lights stay on longer, never shorter).
- The window crosses midnight (start later than end). The in-window test must be start <= now or now < end, and a rendered test pins both sides.
- Breaking input change: an instance that is not migrated becomes unavailable. Mitigation: export the live instance, run the dry-run schema check, then the deploy script's state=on assert.
- Live-only facts: entity IDs, the FP300 device_class (occupancy or presence, which decides the selector) and the HA blueprint path must be read from HA by the planner, never guessed.
- FP300 reliability: early firmware reportedly misses updates and the battery state can take 24 h to first report. The unavailable path treats it as clear and sends one push, so a flapping FP300 can shorten a hold, never keep the lights on.
- A notify target that does not exist aborts the run at the push step (heating-rack lesson). The push runs after the light calls, and the target is checked live before deploy.
- Overlap audit: before plan approval, run a live check of other automations touching the living room lights, the FP2 or the FP300.

## Budget
- Track only. No warn line; token use is logged and reported per card.
