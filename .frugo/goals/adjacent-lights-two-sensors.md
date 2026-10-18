---
goal: adjacent-lights-two-sensors
title: Adjacent room lights with two motion sensors
status: active
---

## Aim
Either attic motion sensor lights the attic and attic stairs with the shared circadian profile

## Decisions
- Goal: repo Blueprints_Home, slug adjacent-lights-two-sensors, title Adjacent room lights with two motion sensors (Martin, round 1).
- Who it is for: Martin and the household, using the attic and the office. The attic lights come on whether you come up the stairs or leave the office.
- Sensors (amended 2026-10-17 after Martin re-paired them over Matter on the Aqara Hub M100): binary_sensor.attic_atticlaudry_occupancy (attic, seen when leaving the office; old attic_main) and binary_sensor.attic_atticdoor_occupancy (at the stairs door; old attic_stairs). Both are device_class occupancy, not motion. Martin chose to loosen the blueprint picker to accept motion and occupancy (card 3), 2026-10-17.
- Lights (amended 2026-10-17, Martin): light.attic_2, light.attic_3 and light.attic_stairs. light.attic is disabled by the Hue integration; light.attic_3 is unavailable at the time of writing. light.the_office is not included.
- Logic: either sensor on means all lights on. The dim and off timers count from the moment every sensor is clear (Martin, round 1). This matches the living-room v3.0.0 rule.
- Attic timers: first dim 2 min, second dim 4 min, off 5 min, set on the attic instance only. The blueprint defaults stay 5/10/15 (Martin, round 2). These values are within the existing input minimums (1/2/3).
- Watchdog: an unavailable or unknown sensor counts as clear. The lights turn off after 30 min only when every sensor is unavailable or unknown (Martin, round 2).
- Night light: both attic lights use the blueprint's standard profiles, the same as every instance (Martin, round 2).
- Cleanup: 8.1 and 8.2 are disabled at deploy and deleted after both attic live traces pass. The kitchen instance is migrated with its values unchanged (Martin, round 2).
- Blueprint is ~/AI/projects/Blueprints_Home/adjacent_room_lights.yaml, "Adjacent Room Circadian Lights v1.0.0" (motion_on; stage_1/stage_2/stage_off via `to: off` + `for:`; 30-min unavailable/unknown watchdog; mode restart; 5-min update loop; optional lux and override; circadian formula identical to circadian_livingroom.yaml). ~/projects/ceiling-fan-hue-blueprint has no copy of it.
- Decided by orchestrator, Martin can revert: the single motion_sensor input becomes a motion sensor list (entity selector, multiple: true, at least one), and the version becomes v2.0.0. There is no backwards-compatibility shim.
- Decided by orchestrator, Martin can revert: "every sensor clear" means each listed sensor has been off, unavailable or unknown for at least the stage's minutes. The stage triggers fire per sensor, and a condition checks all the others, so a sensor that clears later restarts the countdown.
- Amended 2026-10-17 (live search/related): three live instances use the blueprint, not one: [Kitchen] 1773749905520, [Front Hall] 1773750307485 and [Toilet] 1773750379398, all with the v1 key motion_sensor, so all three are migrated in card 2. The original line follows. The only live instance is [Kitchen] Adjacent Room Circadian Lights v1.0.0 (automation.kitchen_adjacent_room_circadian_lights_v1_0_0, id 1773749905520, state on), per the 2026-10-16 live audit. It shares no entity with the living-room circadian instance.
- 8.1 is automation.8_1_attic_main_motion (id 1727114576587, on as of 2026-09-24) and 8.2 is automation.8_2_attic_stairs_motion (id 1727114932689). Their configs are not on the VPS and are unread. The orchestrator does a GET-only read before the brief, confirms they control the attic lights, and saves them to deploy/ as rollback records.
- Decided by orchestrator, Martin can revert: no lux sensor and no override helper for the attic instance (the HomeKit sensors have no lux; the optional inputs stay in the blueprint). No door input either: the stairs motion sensor sees the door opening.
- Entity facts come from the 2026-09-12 registry snapshot. Before the brief they are rechecked live, along with device_class motion, the HA blueprint path and the attic instance id.
- Cards (amended 2026-10-17): 1) blueprint v2.0.0, done; 3) picker accepts motion and occupancy (Lane 1); 2) live deploy, after card 3. Original expectation: 1) blueprint v2.0.0 plus the structure and render tests, Lane 1; 2) live deploy: kitchen migration, new attic instance, disable 8.1/8.2, traces, then delete 8.1/8.2 under separate OKs; expected Lane 2.
- Visuals: none. This is a blueprint change with no UI, so no mock-up is needed.
- Validation: pytest structure and render tests, deploy-blueprint.sh dry-run for both instance files, live traces at deploy; no multi-day observation.
- Overlap: a live overlap audit and interaction matrix (light.attic, light.attic_stairs, both sensors, 8.1/8.2, Hue bridge or app motion rules) runs before brief approval.
- Budget: track only.

## Done when
- `env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests/test_adjacent_room_lights_structure.py -q` passes. The test checks: v2.0.0; a motion sensor list input (multiple, device_class motion); every trigger covers every listed sensor; the on branch fires on any sensor on; each stage and off branch also requires every sensor to be off (or unavailable/unknown) for at least that stage's minutes; the watchdog fires only when all sensors have been unavailable or unknown for 30 min; default timers stay 5/10/15; the circadian formula block is unchanged from v1.0.0.
- The same pytest file renders the trigger and condition templates for these cases: one sensor on and the other off gives lights on; one sensor clears while the other stays on gives no dim; both clear for 2 min gives stage 1 (attic values); one unavailable with the other clear for 5 min gives off; both unavailable for 30 min gives watchdog off; one unavailable with the other on gives no off.
- `env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests -q` passes (whole suite, including the existing circadian and deploy-script tests).
- `scripts/deploy-blueprint.sh --dry-run adjacent_room_lights.yaml <HA path> deploy/<kitchen instance file>` and the same dry-run for the attic instance file both exit 0 (the HA path and the attic instance id are confirmed live by the orchestrator before the deploy card).
- Live, at deploy: the kitchen instance and the new attic instance are state on. One trace per attic sensor (attic_main alone, attic_stairs alone) shows light.attic and light.attic_stairs turned on. One kitchen motion trace shows the kitchen lights on as before. automation.8_1_attic_main_motion and automation.8_2_attic_stairs_motion are off.
- After both attic traces pass, 8.1 and 8.2 are deleted (each delete under its own OK from Martin), and a final GET shows them gone.

## Out of scope
- Changes to the circadian formula, time profiles or default values (the 5/10/15 timers stay the blueprint defaults).
- Per-light settings (for example a dimmer stairs light at night); both attic lights use the same profiles.
- A door contact sensor input, a lux sensor for the attic, or an attic override helper.
- light.the_office and any office automation.
- circadian_livingroom.yaml, dinner_table_lights.yaml, lg_sleep_movie.yaml and the other blueprints.
- Hue bridge or Hue app rules, unless the overlap audit finds one that conflicts with the attic lights or sensors; in that case it goes to Open questions, not into a fix.
- Changing any kitchen instance value other than converting its sensor to a one-item list.
- Multi-day observation as a gate.

## Remove
- The single `motion_sensor` input is replaced by the sensor list and is not kept as an alias.
- automation.8_1_attic_main_motion (id 1727114576587) and automation.8_2_attic_stairs_motion (id 1727114932689) are disabled at deploy and deleted after both attic live traces pass. Their configs are first saved to deploy/ as a rollback record.
- Nothing else becomes obsolete: the kitchen instance stays and is migrated, and the blueprint's stage, update-loop and watchdog logic stays, only generalised to several sensors.

## Risks
- Lane 1 for the blueprint and test card: lights only, nothing moves, heats or locks. The deploy/migration card reads the HA token and writes live automations (create, migrate, disable, delete), so it is expected to scan as Lane 2 (secrets, persistent changes), as the circadian v3 deploy did. Only Martin can lower it.
- Schema break: the kitchen instance (id 1773749905520) stops loading if the blueprint ships before its input is migrated. Deploy order: save the kitchen config to deploy/<id>.prev.json, push the blueprint and the migrated kitchen config together, then check the kitchen instance is state on.
- Old and new rules running together: while 8.1/8.2 are on, they and the new instance fight over the same lights. They are disabled in the same deploy step, before the attic traces.
- Deleting 8.1/8.2 is hard to reverse. It happens only after the traces pass, from the saved configs, and each delete needs its own OK.
- A dead sensor counts as clear, so one stuck-off or dead sensor can let the lights turn off while someone is in the other area out of its view. Accepted by Martin (round 2). A sensor stuck on keeps the lights on, the same as v1.0.0.
- The `for:` based "both clear" check: a condition that only checks the current state would dim the lights too early when the second sensor cleared later than the first. The render test cases in Done when cover that case.
- Entity facts come from the 2026-09-12 snapshot; they are rechecked live before the brief. The HomeKit sensors must be device_class motion, or the selector rejects them.
- Hidden Hue bridge or app motion rules on light.attic or light.attic_stairs could also switch the lights; the live overlap audit checks for them before brief approval.
- Secrets: the HA token is read only by the orchestrator, never printed, and never written to deploy/ files, notes or tests. Tests run with env -u HASS_TOKEN.

## Budget
- Track only.
