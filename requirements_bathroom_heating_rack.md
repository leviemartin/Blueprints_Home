# Requirements: Bathroom Heating Rack Blueprint

## Overview
Pre-heats the bathroom using the smart heating rack (`climate.heatingrack_bathroom`) so it is at comfort temperature in time for scheduled routines — adult morning and kids bath — while idling in eco the rest of the day.

## Goals
1. **Scheduled pre-heat** with dynamic warmup based on current indoor-to-target ΔT (self-adjusts across seasons without calendar boundaries).
2. **Dual slot per phase:** Morning A (primary, default Mon–Fri) + Morning B (optional, weekend). Evening A (kids bath) + Evening B (optional adult evening).
3. **Predictive motion override:** hall motion pulls morning auto-start forward; stairs motion does the same for evening.
4. **Ad-hoc boost:** user-flipped `input_boolean` gives N minutes at a configurable boost temperature, then auto-expires.
5. **Ventilator coordination:** pause active heating (via `preset=eco`) while the bathroom exhaust fan is running — avoids evicting freshly heated air.
6. **Idle eco:** when no routine is active, hold `preset=eco` so the thermostat stays on a frost-protect floor and resumes quickly.
7. **Vacation / full-off:** optional `input_boolean` cleanly disables the whole blueprint.
8. **Idempotent:** ~1440 ticks/day but only 4–10 service calls/day (only on transitions).

## Hardware
- `climate.heatingrack_bathroom` — generic_thermostat wrapping the heating rack's smart plug (`switch.heating_switch`) with `sensor.bathroom_temperature` as the temp source
- `sensor.bathroom_temperature` (Aqara) — indoor temp for ΔT calculation (primary)
- `binary_sensor.hall_motion` — morning predictive-motion trigger
- `binary_sensor.stairs_motion` — evening predictive-motion trigger
- `light.heater` — ventilator smart plug, observed for coordination

## Warmup Formula
```
ΔT            = max(0, target_temp - indoor_temp)
warmup_min    = clamp(
                  warmup_base + warmup_per_degree * ΔT,
                  warmup_min_minutes, warmup_max_minutes
                )
auto_start    = target_warm − warmup_min minutes
```

## Priority Order
1. Vacation / Off (highest)
2. Ventilator coordination (pause via eco)
3. Ad-hoc Boost
4. Evening Routine (A or B)
5. Morning Routine (A or B)
6. Idle (default — mode=heat_cool, preset=eco)

## Testing & Debugging
Manual "Run" in HA produces a persistent notification dumping all computed variables (indoor temp, ΔT, warmup_min, each slot's auto_start / effective_start / active flags, current priority winner, service-call decisions).

## Mobile Push Notifications (v1.1.0+)

In addition to the persistent notifications always shown inside Home Assistant, the blueprint can fan out a subset of events to any number of HA Companion `notify.mobile_app_*` services (or other `notify.*` services) via the `notify_targets` multi-select input.

**Input:** `notify_targets` — list of full notify service names (e.g. `notify.mobile_app_martin`). Default is empty (push disabled).

**Events that push** (when `notify_targets` is non-empty):
1. **Climate unavailable** — hard error, automation halts. Fires unconditionally.
2. **Temperature sensor warning** — both primary sensor and `climate.current_temperature` unavailable; warmup formula falls back to 20°C and lead time becomes inaccurate. Fires unconditionally.
3. **Warmup started** — transition into an active routine (P3 boost / P4 evening / P5 morning). Gated by the existing `enable_notifications` input (push and persistent share the same gate for this event).

**Events that do NOT push** (stay persistent-notification-only):
- Target reached — fires on many consecutive minute ticks while within 0.5°C of setpoint; pushing would be spam.
- Debug (manual-run dump) — only fires on a manual `automation.trigger` call, when the user is already at the HA UI.

**Failure isolation:** if a single target in the list is mistyped or its device is logged out, that iteration errors in the automation trace but the remaining targets still receive the push and the automation does not halt.
