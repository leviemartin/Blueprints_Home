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
