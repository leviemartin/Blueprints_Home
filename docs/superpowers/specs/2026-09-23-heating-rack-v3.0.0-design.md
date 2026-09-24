# Bathroom Heating Rack v3.0.0 — room-sensor thermostat (DRAFT, Stack B input)

Status: draft, 2026-09-23. Nothing is deployed or committed. The live blueprint (`bathroom_heating_rack.yaml`, v2.0.0) and `deploy/` are untouched.

Draft artifacts:
- `drafts/heating-rack-v3.0.0/bathroom_heating_rack.yaml` — revised blueprint
- `drafts/heating-rack-v3.0.0/bathroom_heating_rack_1776551429917.json` — migrated instance config

## Goal (Martin's brief, 2026-09-23)

- Heat by the room humidity sensor's temperature, never by the rack's internal sensor.
- Morning: room at target by 06:45 (wake 07:00), held until 07:45. Evening: heat 18:30–19:30, then let the room cool.
- Room target 22 °C (24 °C only if needed). Do not heat at or above 22 °C. Economy over comfort.
- Precedence on conflict: no rack sensor → the two windows only → economic target.

## Decisions

Martin (2026-09-23):
1. Keep heating through the ventilator inside the windows. The fan pause is removed.
2. Every day, same times. The weekend morning slot is dropped.
3. The morning window ends at 07:45.
4. Keep the boost toggle, room-governed at 22 °C.

Decided by orchestrator (Martin may revert any of these):
- **Control law:** HA is the thermostat. While the room is below the line the rack gets `drive_setpoint` 24 °C, and at the line it gets idle (7 °C). Heating stops at 22.0 °C and restarts only below 21.7 °C (`restart_deadband` 0.3). The brief's "24 °C only if needed" becomes the device-side cap: the rack's own sensor can only cut the element earlier, never extend heating.
- **Evening has no pre-heat:** heating may start at 18:30 exactly, because the brief says "start at 6:30 p.m.". To have the room warm *by* 18:30 instead, set `evening_preheat: true`.
- **Sensors:** primary `sensor.temp_sensor_bathroom` (the Aqara AS008 humidity sensor's temperature). Backup `sensor.bathroom_temperature` (Hue motion sensor), which reads about 0.8 °C cooler, so it heats slightly more while it is in use. With no room sensor nothing heats, and a warning plus a push fire. The rack's `current_temperature` is never read.
- **Structure:** the 4-slot schedule machinery stays, with the B slots empty, to keep the diff small. The fan input, trigger and priority are deleted outright. `comfort_floor_delta` becomes `restart_deadband` with new semantics.
- **Major version 3.0.0:** inputs are removed and renamed, so the instance must be migrated in the same deploy (see the blueprint-rename lesson).

## Evidence (live HA, 2026-09-23 ~21:50Z)

| Source | Reading |
|---|---|
| Aqara humidity sensor `sensor.temp_sensor_bathroom` | 21.1 °C / 76 % RH; reports on change (67 changes in 48 h, gaps up to ~4.5 h while stable) |
| Hue `sensor.bathroom_temperature` (current v2 input) | 20.3 °C; reports ~every 5 min |
| Rack `climate.heatingrack_bathroom` `current_temperature` | 21.9 °C, the warmest of the three |
| Rack setpoint history 09-21…23 | Mornings: 23 °C for 3–31 min, then 7. Evenings: 24 °C from ~18:48 local, cut by fan pauses, back on ~20:00, off at 20:30 |
| Fan `light.heater` 09-23 | ~50 min on / 5 min off from 05:30 to 21:35 local |

## Audit of v2.0.0 against the brief

| # | Finding | Effect |
|---|---|---|
| A1 | The instance decides on the Hue motion sensor, not the humidity sensor. | Violates the brief. |
| A2 | The rack's own sensor governs the element. The blueprint only gates the window on the room sensor and then sends 23/24 °C, and the rack stops when *its* sensor reaches that. The warmup lead also falls back to the rack's `current_temperature`, and with the room sensor offline the slots heat "on schedule" bounded only by the rack. | Violates "do not use the rack's internal sensor". |
| A3 | The ventilator pause (P2) blocks heating whenever the fan runs. The fan ran almost all of today, so this morning heated 06:21–06:24 local only. | The windows barely heat. This is the main reason the room is not warm. |
| A4 | The schedule does not match the brief. Evening is warm by 19:15, holds until 20:30 at 24 °C, and pre-heats from ~18:15. Morning A is weekdays only, 23 °C, until 08:00. Morning B is Sat/Sun until 09:30. | Violates the windows. |
| A5 | The comfort floor skips heating at `target − 1` (22 °C for morning, 23 °C for evening) and releases at `target − 0.5`, so the evening runs to ~23.5 °C on the room sensor. | Overshoots the economic target. |
| A6 | The warmup lead (10 min + 5 min/°C, cap 60) has never been calibrated on this rack. The fan pauses left no clean heat-up data. | The morning may not reach 22 °C by 06:45. This is unverified. |
| A7 | There is no stale-sensor guard. `unavailable` is caught, but a frozen-but-available value is not, and the Aqara sensor already died silently once (2026-08-01). | Could heat on a stale reading. |
| A8 | Outside scope: the ventilator cycled ~50/5 min all day at 76 % RH. It exhausts heated air and runs the fan for hours. | This belongs to a separate ventilator session. |
| A9 | Cosmetic: the debug dump printed a raw float ΔT (carried over from s13). | Fixed in the draft with `round(1)`. |

## Logic flow (v3.0.0)

```
every minute / boost / vacation / HA start
 ├─ room = primary humidity-sensor temp → else first numeric backup → else UNKNOWN
 ├─ heating_now = rack ON and rack setpoint == drive (24)
 ├─ windows (schedule only):
 │    morning: open = 06:45 − lead(ΔT)  [lead latched at 60 min while heating_now]
 │             close 07:45, every day
 │    evening: open 18:30 (no lead), close 19:30, every day
 ├─ target source: boost > evening > morning > none   (room target 22 for all)
 ├─ line = 22.0 if heating_now else 21.7
 ├─ call_for_heat = source ≠ none AND room known AND room < line
 ├─ priority: vacation → off | call_for_heat → set 24 | else → set 7
 │            labels: P3_boost / P4_evening / P5_morning, with _satisfied or _blind, P6_idle
 ├─ climate unavailable → warn + one push, stop
 ├─ idempotent set_hvac_mode / set_temperature
 ├─ room-sensor warning (backup in use / blind) + one push on temp_lost
 ├─ warmup-started notification on the idle→drive edge
 └─ boost expiry (last step)
```

## Verification done (draft only)

- 26 scenario rows, rendered with the repo's own Jinja harness against the draft YAML and the migrated instance inputs: **26/26 pass**. They cover the morning lead edge, the stop at 22.0, no restart at 21.8, restart at 21.6, no heating when already at 22.3, the 07:45 end, a cold room (lead 30 and cap 60), latched-edge stability, Saturday, evening 18:29/18:30/19:29/19:30, no early evening open after a boost, rack reading 30 while the room reads 20 (the room decides), the backup sensor, both sensors dead (idle), boost on/satisfied/expired, and vacation. Script: `drafts/heating-rack-v3.0.0/sim_v3.py` (run with the repo venv). It should be ported into the test suite during execution.
- All 96 templates parse with Jinja. The draft has no `current_temperature` reference outside comments and no fan remnants.
- **Not done:** no update to the existing structure tests (`tests/test_bathroom_heating_rack_structure.py` pins v2 and will fail by design), no HA `validate_config`, and no live run.

## Open points for the design gate

1. **Warmup push per heat cycle.** The idle→drive edge now fires on each restart inside a window, so up to ~2 pushes per window. Options: keep it; push only on the first edge after the window opens; or push nothing (persistent notification only).
2. **Tuya cloud write latency.** Stop and restart cost one cloud write each. At a 0.3 °C deadband, expect 1–3 writes per window. Measure this in observation.
3. **Aqara reporting cadence during heating.** Heating stops only when the sensor *reports* 22.0. Overshoot is bounded by the reporting lag, the rack's thermal mass and the 24 °C device cap. Measure it in observation, and raise `restart_deadband` or add an early-stop margin if overshoot exceeds 0.5 °C.
4. **HA stall with the rack at drive.** The rack keeps 24 °C on its own sensor (~22.5–23 °C room) until the next tick. That is the same worst case as v2, which also sent 24 °C.

## Feature ideas (not in the draft)

- **Learned warmup rate:** log °C/min per heat-up and replace the fixed 5 min/°C with a rolling median. This gives the most accurate "ready by 06:45" at the lowest cost.
- **Stale-sensor guard:** use HA `last_reported` age (if the HomeKit Aqara refreshes it) to treat a silent sensor as unknown.
- **Early-stop anticipation:** stop at `target − k × (°C/min)` to absorb the rack's thermal overshoot.
- **Ventilator coordination, reversed:** during a heating window, ask the ventilator to skip non-shower RH cycles. Heating lowers RH anyway, which is cheaper than extraction. This belongs to a ventilator session and would fix A8.
- **Presence/away skip:** skip windows when nobody is home (`person.*` / security away).
- **Energy telemetry:** a template sensor for rack on-minutes per day, to verify the economic goal and cost it at €0.254/kWh.
- **Outdoor-temperature seasonal gate:** skip heating in summer months without touching the schedule. The room-target check already covers most of this.

## Stack B recommendations

- **Entry:** new idea on Blueprints_Home, whose epic #10 is closed. Open a new epic plus session via `github-sync` (search first). Use this spec as the discovery input. Martin's four decisions above are settled and should not be re-asked.
- **Stakes: standard, with a recorded consequence assessment.** The change controls a heating element (physical safety), but the device-side cap (24 °C) and the HA-stall worst case are unchanged from v2, and the no-sensor path heats *less* than v2. If the assessment cannot close that, route it high-risk (design gate R1 Fable/xhigh trial + R2 Codex security).
- **Execution:** Sonnet/high bounded worker. The brief pins behaviour (the 26 scenario rows), the interfaces (input schema above) and the acceptance checks (structure tests rewritten for v3, the scenario rows ported, deploy-script dry run against the migrated instance JSON). Order the work TDD-first: tests, then YAML, then instance JSON.
- **Code gate:** one fresh Opus review chartered for correctness, security and edge cases. Focus areas: the latch/deadband interaction, the boost→window hand-off, the input migration and push ordering.
- **Deploy:** via `scripts/deploy-blueprint.sh` with the migrated instance in the same deploy. Run HA `validate_config` first and check that `notify.mobile_app_martin_fold` exists.
- **Observation (≥ 3 days):**
  - Morning: the room reaches ≥ 22.0 °C by 06:45, or the lead shortfall is recorded.
  - Morning: no heating at or above 22.0 °C.
  - Evening: the setpoint leaves idle no earlier than 18:30 and is at idle by 19:31.
  - Setpoint writes per window are ≤ 3.
  - Overshoot on the Aqara stays ≤ 0.5 °C.
  - Zero log errors.
  - No `current_temperature` use in traces.
