---
id: 2026-10-17-adjacent-lights-picker-occupancy
title: Adjacent lights occupancy sensors
goal: adjacent-lights-two-sensors
issue: "leviemartin/Blueprints_Home#48"
status: done
lane: 1
lane_lowered_by: "2026-10-17T22:12:31.783805Z"
scan_min_lane: 2
coder: codex
step: codex
fix_rounds: 0
---

## Goal
The `motion_sensors` input of the adjacent-lights blueprint (`adjacent_room_lights.yaml`, v2.0.0) accepts both motion and occupancy binary sensors, so the re-paired attic sensors, which now report occupancy, can be selected. Only the selector's `device_class` changes; the version stays v2.0.0 and no trigger or condition logic changes.

## Done when (runnable)
`env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests/test_adjacent_room_lights_structure.py -q`
`env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests -q`

## Files likely touched
- adjacent_room_lights.yaml
- tests/test_adjacent_room_lights_structure.py

## Bad inputs to handle
A binary_sensor with device_class motion is still accepted as a `motion_sensors` value.
A binary_sensor with device_class occupancy is accepted as a `motion_sensors` value.
A binary_sensor with another device_class (for example door) is rejected by the selector.
A non-binary_sensor entity (for example a light) is rejected by the selector.
Several sensors mixing motion and occupancy are accepted together because `multiple: true` stays.
An empty selection is handled as before, since no default was added.

## Risk flags
none

## Constraints carried over
Decided by orchestrator, Martin can revert: the input description on line 39 also names occupancy sensors (text only).
The version stays v2.0.0 because v2.0.0 is not yet deployed live.
No trigger, condition, action or variable logic changes.
The `illuminance_entity` selector stays as it is.
No other blueprint or test file changes, and no new files are added.
No Home Assistant write and no live step in this card.

## Out of scope
Trigger and condition logic (the description text on line 39 is the only other change), the timers, the override and lux inputs, other inputs, other blueprints, the version number, any deploy or Home Assistant write, and any new test files.

## Open questions
none

## Plan
Files: `adjacent_room_lights.yaml`, `tests/test_adjacent_room_lights_structure.py` (no new files, no other edits).

Steps:
1. `adjacent_room_lights.yaml` line 39: description becomes "Select one or more motion or occupancy sensors (binary_sensor) for this room."
2. `adjacent_room_lights.yaml` line 43: `device_class: motion` becomes `device_class: [motion, occupancy]` (flow list). `domain: binary_sensor` and `multiple: true` stay. The `illuminance_entity` selector is not touched.
3. `tests/test_adjacent_room_lights_structure.py`, `test_required_multiple_motion_input`: the expected selector becomes `{"entity": {"domain": "binary_sensor", "device_class": ["motion", "occupancy"], "multiple": True}}`.
4. Keep the existing assertions in that test (no default, no `motion_sensor` alias, `sensor_motion` variable).

Tests: `test_required_multiple_motion_input` covers the new selector (accepts motion and occupancy together, domain binary_sensor so lights are rejected, `multiple: true` kept, no default so empty selection is unchanged). The unpatched file fails it (device_class is still `motion`). Every other test is unchanged and must still pass, so no logic changed.

Checks: the two commands under Done when.

## Result
The `motion_sensors` picker now accepts motion and occupancy sensors, and the input description names both; 613 tests pass in red-green and in the worktree, and the Sonnet code review found 0 P0-P2.
Open P3:
- The blueprint header and the input name "Motion Sensors" still say motion only (the card limited edits to the selector and its description).
