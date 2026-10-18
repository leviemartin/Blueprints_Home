---
id: 2026-10-17-adjacent-lights-v2-blueprint
title: 'Adjacent lights: two motion sensors'
goal: adjacent-lights-two-sensors
issue: "leviemartin/Blueprints_Home#47"
status: done
lane: 1
lane_lowered_by: "2026-10-17T20:14:27.674559Z"
scan_min_lane: 2
coder: codex
step: codex
fix_rounds: 0
---

## Goal
Change the adjacent-room blueprint (`adjacent_room_lights.yaml`) from v1.0.0 to v2.0.0 so one instance accepts several motion sensors. Any listed sensor turns the lights on. The dim and off stages run only after every listed sensor has been clear for that stage's minutes. No Home Assistant write.

## Done when (runnable)
- `env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests/test_adjacent_room_lights_structure.py -q`
- `env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests -q`

## Files likely touched
- adjacent_room_lights.yaml (changed)
- tests/test_adjacent_room_lights_structure.py (new)

## Bad inputs to handle
- Empty sensor list: the input must have no default. The test asserts this. See Open questions for the guard.
- A sensor in state `unknown`: it counts as clear for the stage conditions and as unavailable/unknown for the watchdog.
- A sensor whose `last_changed` is in the future: treated as not yet clear.
- The same sensor listed twice: not in the request; see Open questions.

## Risk flags
- data/migrations: removing the `motion_sensor` input (no alias) breaks the live kitchen instance (id 1773749905520) until card 2 migrates it. This card does not deploy it.
- deploy: none in this card. It makes no HA write, deploy or reload. Card 2 does those.

## Constraints carried over
- Red first: the structure test must fail on the unpatched tree before the YAML patch.
- Inputs, time-profile defaults (5/10/15), the override stop, the lux logic, the warning-stage brightness and colour, the 5-min update loop, `mode: restart`, and the circadian mode/kelvin/brightness templates stay character-for-character from v1.0.0. The test embeds the circadian block as an expected string.
- Use the style of tests/test_circadian_livingroom_structure.py and tests/test_bathroom_ventilator_structure.py (`!input` constructor, structure checks, Jinja rendering with fake states).
- Read only: circadian_livingroom.yaml (the either-on/all-clear reference), scripts/deploy-blueprint.sh.
- Secrets: none. Tests run with `env -u HASS_TOKEN`.
- Stage conditions use `now() - last_changed` per sensor. A sensor that clears later restarts the countdown for the others.
- Watchdog: 30 min, every listed sensor unavailable or unknown.
- motion_on: lux check kept, and at least one listed sensor must be on.
- Decided by orchestrator, Martin can revert: no extra empty-list guard (the input is required with no default; every instance has at least one sensor); a sensor listed twice is accepted and counts once; README.md stays untouched; card 1 may land in the repo before card 2 because nothing deploys until card 2 and Martin's per-action OKs.

## Out of scope
- Any HA write, deploy, reload, or instance file. The kitchen and attic instance configs.
- Automations 8.1 and 8.2.
- Per-light settings, a door or lux input for the attic, profile or formula changes.
- circadian_livingroom.yaml and the other blueprints.
- README.md: a grep for "adjacent" finds no adjacent-room section, so it is not touched (see Open questions).

## Open questions
none

## Plan
<!-- Planner only: exact files incl. test files, steps, and the test list (one test per
     "Done when" item and per bad input). -->
Planner: Sonnet (lane 1, lowered by Martin 2026-10-17). Coder: codex. Two files change: `adjacent_room_lights.yaml`, `tests/test_adjacent_room_lights_structure.py` (new). Nothing else.

### Design (adjacent_room_lights.yaml)
1. Header: `name: "Adjacent Room Circadian Lights v2.0.0"`, description line `**Version: 2.0.0 - HA 2026.3 Compatibility**`, and one sentence that several motion sensors may be listed (any on = lights on; dim/off timers start once every listed sensor has been clear that long; the watchdog fires only when every sensor has been unavailable/unknown for 30 min). Keep every other description line.
2. Input: rename `motion_sensor` to `motion_sensors`: name "Motion Sensors", description says one or more, selector `entity: {domain: binary_sensor, device_class: motion, multiple: true}`, NO `default` key. Delete `motion_sensor` everywhere (no alias).
3. Triggers: keep the 7 triggers and ids exactly (motion_on, stage_1, stage_2, stage_off, update_loop, sensor_watchdog twice); only change `entity_id: !input motion_sensor` to `entity_id: !input motion_sensors`. Do not touch `to:`, `for:` or ids.
4. Top-level `variables:` — replace `sensor_motion: !input motion_sensor` with `sensor_motion: !input motion_sensors` (now a list). Add `mins_stage1: !input time_to_stage1`, `mins_stage2: !input time_to_stage2`, `mins_off: !input time_to_off`.
5. Action-level `variables:` (the step that defines `current_lux`/`is_motion_on`): replace `is_motion_on` with `{{ sensor_motion | select('is_state', 'on') | list | count > 0 }}` (or an equivalent loop over `states[e]`; must be true iff any listed sensor is on). Add four variables right after it, all loops over `sensor_motion` using `states[entity]` (a missing entity, `states[e] is none`, counts as not clear):
   - `clear_stage1`, `clear_stage2`, `clear_off`: true iff for EVERY sensor `s.state in ['off','unavailable','unknown']` and `s.last_changed <= now() - timedelta(minutes=<mins_stageN|mins_off> | float)`. A `last_changed` in the future therefore fails the check.
   - `all_dead_30`: true iff for EVERY sensor `s.state in ['unavailable','unknown']` and `s.last_changed <= now() - timedelta(minutes=30)`.
   Render each as a namespace loop that ends with `{{ ns.ok }}` (`ns.ok` starts true; with an empty list it must end false).
6. Main `choose`:
   - Branch A (turn off): split the `or` into two: `stage_off` with an added `condition: template` `"{{ clear_off }}"`, and `sensor_watchdog` with `"{{ all_dead_30 }}"`. Write it as `condition: or` of two `condition: and` blocks. Same `light.turn_off` sequence, unchanged.
   - Branch B (stage_1): add `condition: template` `"{{ clear_stage1 }}"` after the existing two conditions. Branch C (stage_2): add `"{{ clear_stage2 }}"`.
   - Branch D (motion_on): the existing `{{ is_motion_on }}` condition stays (now "any sensor on"). Branch E (update_loop): unchanged.
7. Byte-identical from v1.0.0: all inputs other than `motion_sensor`, `mode`, `target_kelvin`, `target_brightness`, `current_lux`, the override stop, the lux conditions, the warning-stage service data, the 5-min loop, `mode: restart`, `max_exceeded: silent`.

### Tests (tests/test_adjacent_room_lights_structure.py, new)
Imports as in tests/test_circadian_livingroom_structure.py (`HassLoader, TZ, _env, _reparse, _var_template` from `test_bedroom_precool_structure`). Local `_St(state, last_changed)`, a `_strict_env`/States fake like the circadian test (`states[entity]`, `states(entity)`, `is_state`), a `render(bp, name, now, table, **ctx)` helper that renders action-level variables in order (`is_motion_on`, then the `clear_*`/`all_dead_30` ones) with `sensor_motion`, `mins_stage1/2/off` in ctx. NO git, subprocess or network in the tests (red-green runs them in copies without `.git`, and after commit HEAD is v2). For the unchanged-formula check embed the v1.0.0 text of the `mode`, `target_kelvin`, `target_brightness` and `current_lux` action variables as literal expected strings, copied character for character from the v1.0.0 `adjacent_room_lights.yaml` (the worktree file before the patch). Fix round 1 changed this: the previous patch used `git show HEAD:` and failed red-green; produce the complete patch (both files) again against the unpatched worktree.
- Structure: (1) `name` contains `v2.0.0`; (2) input `motion_sensors` exists, selector entity `multiple` true, `device_class` motion, domain binary_sensor, and has NO `default`; (3) no `motion_sensor` key as an input and no `!input motion_sensor` (exact) anywhere in the file text (regex `!input motion_sensor\b(?!s)`); (4) trigger ids are exactly motion_on, stage_1, stage_2, stage_off, update_loop, sensor_watchdog x2, and every state trigger's entity_id is the `motion_sensors` input; (5) defaults of time_to_stage1/2/off are 5/10/15; (6) the parsed `mode`, `target_kelvin`, `target_brightness` and `current_lux` action variables equal the embedded v1.0.0 literals; (7) the stage_off branch conditions reference `clear_off`, stage_1 → `clear_stage1`, stage_2 → `clear_stage2`, watchdog → `all_dead_30`, motion_on still references `is_motion_on`.
- Rendered (two sensors A=binary_sensor.attic_main, B=binary_sensor.attic_stairs; mins 2/4/5 unless stated): (8) A on, B off: `is_motion_on` true; (9) both off: `is_motion_on` false; (10) A cleared 6 min ago, B still on: `clear_stage1` and `clear_off` false; (11) A cleared 6 min ago, B 1 min ago: `clear_stage1` false; (12) both cleared >= 2 min: `clear_stage1` true, `clear_stage2` false at 3 min and true at 4 min; (13) A unavailable 10 min, B off 5 min: `clear_off` true; (14) A unavailable 30 min, B on: `all_dead_30` false; (15) A unavailable 30 min, B unknown 31 min: `all_dead_30` true; (16) single-sensor list off for 5 min with defaults 5/10/15: `clear_stage1` true, `clear_stage2` false (same as v1.0.0).
- Bad inputs: (17) sensor state `unknown` for 5 min counts as clear (`clear_off` true) and as dead for `all_dead_30` at 30 min; (18) `last_changed` in the future: `clear_stage1` false; (19) a missing entity (table has no entry) makes every `clear_*` false; (20) the empty list renders `clear_*` false.
RED check: tests 1, 2, 4, 7 and all rendered cases fail on the unpatched tree (no `motion_sensors`, no `clear_*` variables). Run `red-green`.

### Plan amendment, fix round 3 (watchdog edge; Martin: "fix the watchdog edge now", 2026-10-17)
The worktree is reset to the clean base, so return the COMPLETE patch for both files against it (the test file is new: include `new file mode 100644`). Everything above stays, with these changes:
- YAML, main-choose branch A: the `sensor_watchdog` arm's template condition is `{{ clear_off or all_dead_30 }}` (not `{{ all_dead_30 }}`). Meaning: a sensor dead 30 minutes while every other sensor is off or dead for at least the off-timer turns the lights off; a sensor still ON keeps them on.
- YAML description: the watchdog sentence says the lights go off when every listed sensor has been unavailable/unknown for 30 minutes, or when a sensor has been dead 30 minutes and every other sensor has been clear for the off time.
- Structure test 7: the watchdog arm references both `clear_off` and `all_dead_30`.
- Extra rendered cases (attic timers 2/4/5, evaluate the arm as `clear_off or all_dead_30` from the rendered variables): A unavailable 30 min, B off 6 min -> true; A unavailable 30 min, B off 1 min -> false; A unavailable 30 min, B on -> false.
- Both Done-when commands pass on the patched tree; the file still fails on the base.

### Steps
1. Write the tests. 2. Patch the YAML as designed. 3. Run the two Done-when commands. The existing suite must stay green; no other file changes.

## Result
Passed Lane 1 review: blueprint v2.0.0 and 40 structure/render tests are applied in worktree Blueprints_Home-wt/adjacent-lights-v2 (branch frugo/2026-10-17-adjacent-lights-v2-blueprint, uncommitted, based on 2d5c00d). Coder: Codex, after 3 fix rounds (round 1: the test used `git show HEAD:`, which fails in red-green copies, so the v1.0.0 text is now embedded; round 2: the diff lacked the `new file mode` line; round 3, at Martin's request: the watchdog arm is now `clear_off or all_dead_30`, so a sensor that dies mid-cycle no longer leaves the lights on, with three render cases). Red-green: RED on the base (structure file 36 failed, 4 passed; full suite 36 failed, 577 passed), GREEN patched (40 passed; full suite 613 passed). Review: Sonnet correctness PASS (bare reply); the orchestrator also read the YAML diff.
Open P3:
none
