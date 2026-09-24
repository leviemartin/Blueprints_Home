# Requirements: Bathroom Heating Rack Blueprint (v3.0.0)

## Overview
Heats the bathroom heating rack (`climate.heatingrack_bathroom`) by the **room** temperature — never
the rack's own internal sensor — so it is warm for two daily windows (morning, evening) and idles at
a frost-protect setpoint the rest of the day. v3.0.0 replaces v2.0.0's comfort floor and ventilator
pause with a room-sensor on/off thermostat: the blueprint decides when the element runs, the rack's
`drive_setpoint` (24 °C) only caps the element inside the device.

## Goals
1. **Room-sensor thermostat.** A routine window (or boost) heats only while the room sensor is below
   the room target. The rack's own `current_temperature` is never read for any decision.
2. **Restart deadband:** a slot that is not already heating starts only below `target − restart_deadband`
   (default 0.3 °C); once heating it stops at `target`. Guards against sensor noise short-cycling the
   rack.
3. **No room sensor → no heating.** With the primary and every backup sensor non-numeric the rack
   stays idle, a `_blind` priority label is set, and a warning is raised.
4. **Dual slot per phase:** Morning A (primary, every day 06:45→07:45) + Morning B (optional).
   Evening A (every day 18:30→19:30) + Evening B (optional). No fan pause — the ventilator no longer
   blocks heating.
5. **Ad-hoc boost:** user-flipped `input_boolean` heats toward `boost_target_temp` (room-governed) for
   N minutes, then auto-expires.
6. **Idle:** when no window or boost is active the thermostat holds `idle_setpoint` (default 7 °C, the
   device minimum) in `heat_cool`.
7. **Vacation / full-off:** optional `input_boolean` switches the rack off.
8. **Idempotent:** ~1440 ticks/day but only a handful of service calls/day (on transitions only). Every
   setpoint (idle and drive) is rounded to the device `target_temp_step` and clamped to its
   `min_temp`/`max_temp` before comparison and write.

## Hardware
- `climate.heatingrack_bathroom` — Tuya cloud "ECOSO WIFI Element" (category wk). HA state is
  `unknown` while the switch is on and the mode is eco (the normal ON state — the blueprint treats it
  as `heat_cool`) and `off` when the switch is off. `target_temp_step` 1.0, min 7, max 30. **Its own
  sensor is never read by the blueprint** — it only lets the device itself cut the element earlier if
  it ever overshoots the drive setpoint.
- `sensor.temp_sensor_bathroom` — **primary** room sensor: the Aqara AS008 humidity sensor's
  temperature entity. Reports on change (gaps up to several hours while stable).
- `sensor.bathroom_temperature` — **backup** room sensor: the Hue motion sensor's temperature
  (reports ~every 5 min), used while the primary is non-numeric. Reads ~0.8 °C cooler than the Aqara,
  so it heats slightly more while in use. Additional backups may be listed; the first numeric one in
  list order wins.
- `input_boolean.heating_rack_boost`, `input_boolean.heating_rack_vacation` — helpers.
- `notify.mobile_app_martin_fold` — the only push target.

## Control law
```
room          = primary sensor temp if numeric, else the first numeric backup, else UNKNOWN
heating_now   = rack is ON and its setpoint == drive_setpoint_dev (i.e. the rack is currently driving)
latch_ok      = heating_now AND boost is not ON AND boost has been off/never-on for
                >= warmup_max_minutes (i.e. the current drive is slot-started or long-aged, never a
                fresh or still-active boost)

ΔT            = max(0, slot_target − room)   [room = 20 placeholder when UNKNOWN, so ΔT = slot_target − 20
                                               (2 °C for a 22 °C target); the window still opens by that
                                               lead, but heating stays blocked (_blind)]
warmup_lead   = clamp(warmup_base + warmup_per_degree × ΔT, warmup_min_minutes, warmup_max_minutes)
open          = target_warm − (warmup_max_minutes if latch_ok else warmup_lead)
                  [evening slots: lead is 0, and open == target_warm exactly, unless evening_preheat]
in_window     = today in slot's days AND open ≤ now < hold_until

target_source = boost > evening_a > evening_b > morning_a > morning_b > none   (first in-window/active wins)
room_target   = the winning source's target temperature (22 °C for every slot/boost by default)
heat_line     = room_target                    while heating_now
              = room_target − restart_deadband  while not heating_now
call_for_heat = target_source != none AND room is known AND room < heat_line

priority      = P1_vacation                          (vacation toggle ON — hvac off, setpoint untouched)
              > P3_boost / P4_evening / P5_morning    (call_for_heat true — drive_setpoint_dev)
              > P6_idle                               (target_source == none — idle_setpoint_dev)
                a source that is in-window/active but not calling for heat gets `_satisfied`
                (room already at target) or `_blind` (no room sensor) appended to its label
```
`hold_until` at or before `target_warm` is taken as the next day; the slot is evaluated per calendar
day, so such a window runs until midnight. The morning windows' opening edge (and, when
`evening_preheat` is on, the evening windows' too) latches at `target_warm − warmup_max_minutes`
while `latch_ok`, so a warmer sensor report mid-warmup cannot close the window early — but a fresh or
still-active boost can never masquerade as a slot-started heat and force an early open.

**Known residuals of the `latch_ok` gate** (accepted, not fixed in v3.0.0):
- A rack manually set to 24 °C, with the current time inside `[target_warm − warmup_max_minutes, target_warm)`
  and no boost active/recent, is indistinguishable from a slot-started heat and is honoured by the
  latch (opens early) exactly like a real slot restart would.
- With both A and B configured for the same phase (e.g. Morning A and Morning B), a heat still
  running from A at B's target-warm time latches B's opening edge early, the same "sibling hand-off"
  behaviour v2 also carried. The live instance only configures the A slots, so this residual is
  currently unreachable.
- After an HA restart (or an integration reload that takes the boost helper through `unavailable`)
  the boost helper's `last_changed` is fresh, so `latch_ok` stays false for `warmup_max_minutes`.
  A slot-started pre-warm that is still before its ΔT-lead opening time then pauses until that time
  arrives (heat resumes on the first tick at or after it). After `target_warm` the ΔT-lead edge is
  always in the past, so a running window is never closed by this. A missing boost entity counts as
  "never on" (age 100000 min), so the latch still works.

## Priority order (first match wins)
1. Vacation / Off — `hvac_mode: off`, setpoint untouched — `P1_vacation`
2. Ad-hoc Boost — `boost_target_temp` (room-governed) — `P3_boost`
3. Evening routine (A or B) — slot target — `P4_evening`
4. Morning routine (A or B) — slot target — `P5_morning`
5. Idle — `idle_setpoint` — `P6_idle`

A source that is in-window but the room is already at target reads `<label>_satisfied` (no heating,
no restart until the deadband line); one with no room sensor at all reads `<label>_blind`. Labels are
historical: the numeric suffix is not the evaluation order.

## Triggers
Every minute (`periodic`), boost/vacation `on`↔`off` (attribute-only updates ignored), HA start,
climate entity `unavailable` for 5 min (`climate_lost`), primary room sensor unavailable/unknown for
10 min (`temp_lost`; the in-HA warning covers any non-numeric state immediately), backup room
sensor(s) unavailable/unknown for 10 min (`backup_lost`). No fan trigger. `mode: restart`.

## Notifications
- **Climate unavailable** — in-HA warning follows the state (created while unavailable, dismissed when
  back); one push after 5 min (`climate_lost`); the run stops while the entity is unavailable.
- **Room sensor offline** — in-HA warning follows the state (created while the primary is non-numeric,
  dismissed when back) and names whether the backup is in use or the rack is fully blind; one push
  after 10 min (`temp_lost`). If the backup then also goes non-numeric for 10 min while the primary is
  still dead, a second, distinct push fires (`backup_lost`, gated on `not indoor_temp_has_backup`):
  "No room sensor: scheduled heating is blocked." The run continues throughout (scheduled heating is
  simply blocked while blind). **Residual:** a simultaneous double outage (primary and every backup
  going non-numeric together) can fire both the `temp_lost` and `backup_lost` pushes back to back,
  since they are two independently edge-gated 10-minute timers on different entities; accepted, not
  de-duplicated in v3.0.0.
- **Warmup started** — on the tick that raises the setpoint from idle (`enable_notifications` gates
  persistent + push); dismissed on the tick that returns the setpoint to idle. A restart inside the
  same window (after the deadband trips) is a new edge and fires again.
- **Debug** — manual run only: every computed variable (room reading, primary/backup/known, setpoint
  step/range/idle/drive, mode, heating_now, each slot's ΔT/warmup/open/hold_until/in_window, the
  winning source/target/line/call, the priority winner, desired mode and setpoint).

Push fan-out: `notify_targets` entries are filtered to well-formed `notify.<name>` service names before
dispatch; each call carries `continue_on_error: true`, which covers runtime errors from a reachable
service but **not** a missing action — HA aborts the run at a `notify.*` name that does not exist.
Every push therefore runs after the climate calls, and the deploy procedure checks that each target
exists before deploying.

## Known limitations (deferred)
- **`backup_temp_sensors` must stay a list.** The default `[]` is a valid state-trigger target
  (verified with HA `validate_config` 2026-09-24); a blank entry `['']` is rejected and would disable
  the automation. The multi-select entity selector never produces a blank entry.
- **Frozen-but-available primary sensor.** The room sensor is the sole authority; a sensor that has
  stopped updating (e.g. died silently, as the Aqara AS008 did on 2026-08-01) but still reports a
  numeric, in-range value is indistinguishable from a live reading. If that stale value sits below the
  restart line the blueprint heats every window on data that never changes, and the backup never
  engages. This is a non-goal for v3.0.0. **Follow-up:** a `last_reported`/`last_updated` age guard
  that treats a primary older than some threshold as `unknown` and falls back to the backup.

## Testing
`tests/test_bathroom_heating_rack_structure.py` pins the v3 input schema (removed: `fan_switch`,
`comfort_floor_delta`; added: `backup_temp_sensors`, `drive_setpoint`, `restart_deadband`,
`evening_preheat`), the trigger roster (no fan trigger), the action shape (climate validation before
the service calls, every push after the climate calls, boost expiry last, debug manual-only), the
absence of any `current_temperature` reference and any fan remnant, the locale-safe weekday, the
setpoint rounding/clamping rows, the window/target-source/heat-line/call-for-heat templates, and 26+
rendered scenario rows ported from the v3.0.0 design's simulation script (morning/evening open and
close edges, the restart deadband, the latched opening edge, backup-sensor order and fallback,
`evening_preheat`, boost on/satisfied/expired, vacation, and a blind room). It also dry-runs the
deploy script against the migrated instance JSON.
