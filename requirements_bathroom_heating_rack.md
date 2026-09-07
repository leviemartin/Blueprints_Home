# Requirements: Bathroom Heating Rack Blueprint (v2.0.0)

## Overview
Pre-heats the bathroom with the heating rack (`climate.heatingrack_bathroom`) so it is warm in time for scheduled routines — adult morning and kids bath — and idles at a frost-protect setpoint the rest of the day. v2.0.0 adds a comfort floor (no heating when the room is already warm), removes predictive motion, and makes every notification edge-triggered.

## Goals
1. **Scheduled pre-heat** with a dynamic warmup lead based on the indoor-to-target ΔT (self-adjusts across seasons without calendar boundaries).
2. **Comfort floor:** a slot heats only while the room is below `target − comfort_floor_delta` (default 1 °C). A bathroom that is already warm gets no pre-heat and no hold. While the device holds that slot's setpoint the slot is "heating": it stays active until the room is 0.5 °C above the line (release deadband — the room sensor swings ±0.3 °C between reports) and its opening edge is latched at `target_warm − warmup_max` (the ΔT lead moves with sensor noise). Without the room sensor the floor is suspended: slots heat on schedule (v1 behaviour, the device thermostat bounds the temperature) and a warning is raised.
3. **Dual slot per phase:** Morning A (primary, default Mon–Fri) + Morning B (optional, weekend). Evening A (kids bath) + Evening B (optional adult evening).
4. **Ad-hoc boost:** user-flipped `input_boolean` gives N minutes at a configurable boost temperature, then auto-expires.
5. **Ventilator coordination:** scheduled routines pause (setpoint → `idle_setpoint`) while the bathroom exhaust fan is running — avoids evicting freshly heated air. Boost is explicit user intent and is not paused.
6. **Idle:** when no routine is active the thermostat holds `idle_setpoint` (default 7 °C, the device minimum) in `heat_cool`.
7. **Vacation / full-off:** optional `input_boolean` switches the rack off.
8. **Idempotent:** ~1440 ticks/day but only a handful of service calls/day (on transitions only). The setpoint is rounded to the device `target_temp_step` and clamped to its `min_temp`/`max_temp` so the comparison is exact and HA never rejects the value.

## Hardware (live 2026-09-07)
- `climate.heatingrack_bathroom` — Tuya cloud "ECOSO WIFI Element" (category wk). HA state is `unknown` while the switch is on and the mode is eco (the normal ON state — the blueprint treats it as `heat_cool`) and `off` when the switch is off. No `hvac_action`. `target_temp_step` 1.0, min 7, max 30. Its own sensor reads ~1.4 °C warmer than the room sensor and governs the element while a slot is active.
- `sensor.bathroom_temperature` — the Hue motion sensor's temperature (reports every ~5 min, 0.1 °C); primary input for ΔT and the comfort floor. Fallback: the climate entity's `current_temperature`.
- `light.heater` — Hue room group mirroring the exhaust-fan plug (`light.on_off_plug_1`, the ventilator blueprint's target); observed for coordination.
- `input_boolean.heating_rack_boost`, `input_boolean.heating_rack_vacation` — helpers.
- `notify.mobile_app_martin_fold` — the only push target.

## Warmup formula
```
ΔT            = max(0, target_temp − indoor_temp)
warmup_min    = clamp(warmup_base + warmup_per_degree × ΔT, warmup_min_minutes, warmup_max_minutes)
auto_start    = target_warm − warmup_min
heating       = device setpoint == this slot's rounded target
open          = target_warm − (warmup_max_minutes if heating else warmup_min)
in_window     = today in days AND open ≤ now < hold_until
floor         = target_temp − comfort_floor_delta (+ 0.5 while heating)
active        = in_window AND (room sensor offline OR indoor_temp < floor)
```
`hold_until` at or before `target_warm` is taken as the next day; the slot is evaluated per calendar day, so such a window runs until midnight.

## Priority order (first match wins)
1. Vacation / Off — `hvac_mode: off`, setpoint untouched
2. Ad-hoc Boost — `boost_target_temp`
3. Ventilator coordination (scheduled routines only) — `idle_setpoint`
4. Evening routine (A or B) — slot target
5. Morning routine (A or B) — slot target
6. Idle — `idle_setpoint`

Labels in traces (`P1_vacation`, `P3_boost`, `P2_fan_coord`, `P4_evening`, `P5_morning`, `P6_idle`) are historical: the numeric suffix is not the evaluation order.

## Triggers
Every minute (`periodic`), boost/vacation/fan `on`↔`off` (attribute-only updates ignored), HA start, climate entity `unavailable` for 5 min (`climate_lost`), room sensor unavailable/unknown for 10 min (`temp_lost`; the in-HA warning covers any non-numeric state). `mode: restart`.

## Notifications
- **Climate unavailable** — in-HA warning follows the state (created while unavailable, dismissed when back); one push after 5 min (`climate_lost`); the run stops while the entity is unavailable.
- **Room sensor offline** — in-HA warning follows the state (created while `sensor.bathroom_temperature` is non-numeric, dismissed when back) and names the fallback in use (the rack's own sensor, or 20 °C); one push after 10 min (`temp_lost`). The comfort floor is suspended meanwhile; the run continues.
- **Warmup started** — once per transition, on the tick that raises the setpoint from idle (`enable_notifications` gates persistent + push); dismissed on the tick that returns the setpoint to idle. Idle is compared as the device holds it (rounded to the step, clamped to the range). A fan pause and resume inside a window is a new transition.
- **Debug** — manual run only: every computed variable (indoor temp, step/range/idle, push list, each slot's ΔT / warmup / auto_start / open / hold_until / heating / floor / in_window / active, the priority winner, desired mode and setpoint).

Push fan-out: `notify_targets` entries are filtered to well-formed `notify.<name>` service names before dispatch; each call carries `continue_on_error: true`, which covers runtime errors from a reachable service but **not** a missing action — HA aborts the run at a `notify.*` name that does not exist (verified live 2026-09-07 with a throwaway script). Every push therefore runs after the climate calls, and the deploy step checks that each target exists.

## Testing
`tests/test_bathroom_heating_rack_structure.py` pins the input schema, the trigger roster (`to:` filters, the two `for:` outage triggers), the action shape (pushes after the climate calls, edge-gated outage pushes, boost expiry last, no preset calls, no motion remnants), and renders the templates for weekday, setpoint rounding and clamping, the device idle value, the notify filter, warmup lead, comfort-floor gating with the slot-keyed deadband and latched opening edge, the suspended floor without the room sensor, window bounds, hold-until anchoring, priority rows and both notification edges; it also dry-runs the deploy script against the instance JSON.
