# Bedroom Sleep Pre-Cool — Requirements

## Overview

Predictive pre-cooling of bedrooms via a single LG air conditioner located in
the upstairs hall. The blueprint brings the warmest bedroom to an ideal sleep
temperature (default 19 °C) by a fixed bedtime (default 19:30), then holds the
room quietly overnight while issuing the absolute minimum number of commands.

LG ACs emit a confirmation beep on every command received over ThinQ — a
firmware tone that cannot be silenced in software. The blueprint therefore
treats AC commands as a scarce resource after bedtime: it adjusts freely
*before* bedtime, locks a maintaining setpoint *at* bedtime, permits at most
one corrective command at a deep-night checkpoint (~01:00), and turns the AC
off at wake (~07:15).

The AC is not in the bedrooms — it cools the hall and cold air migrates through
open doors. Cooling is therefore indirect, laggy, and load-dependent, so the
turn-on time is *predicted* from the indoor gap, an hourly weather forecast,
and solar gain, with a self-learning bias that auto-corrects from each night's
observed outcome.

## Hardware Requirements

- **AC Unit:** One LG air conditioner in the hall, connected via the LG ThinQ
  integration (exposes a `climate` entity).
- **Bedroom Temperature Sensors:** One or more in-room sensors (e.g., Aqara) —
  these are the control target.
- **Bedroom Humidity Sensors (optional):** Only needed if dry mode is enabled.
- **Outdoor Temperature Sensor:** Any sensor with `device_class: temperature`.
- **Weather Entity:** Must provide an **hourly** forecast — Met.no (HA default,
  keyless) or Open-Meteo. **Buienradar provides only a daily forecast and will
  not work as the weather entity** (it may still serve the outdoor sensor).
- **AC Sound Switch (optional):** The `switch` entity for the AC beep, if
  exposed — kept muted.

## Home Assistant Requirements

- **Home Assistant Core 2025.7 or newer** — required for the LG ThinQ
  `set_temperature` fix (PR #147008).
- **input_number helper:** Persists the self-learned lead-time bias across
  restarts. Create one via Settings -> Devices & Services -> Helpers ->
  Number with **min −60 (or lower), max 120 (or higher), step 1**. The
  blueprint clamps its write to the whole numbers inside the helper's live
  range intersected with −60…120, skips the write when the two do not overlap
  at all, and raises a persistent notification while the helper is narrower
  (v1.1.0 — a helper created with min 60 used to reject the write and abort
  the lock run).
- **input_boolean helper (optional):** For the vacation toggle.

## Daily State Machine

The blueprint is stateless: a 1-minute loop derives which phase `now` is in and
acts. Phase boundaries span midnight (bedtime -> wake is an overnight window).

| Phase | Window | AC behaviour | Beeps |
|---|---|---|---|
| DAY-OFF | wake -> min(turn_on, bedtime − lead_cap) | Ensure AC off — any running unit is switched off on the next tick; recompute turn-on each tick | 1 at wake (+1 per manual daytime turn-on) |
| PRECOOL | turn_on -> bedtime − 1 min | Cooling; closed-loop DRIVE / HOLD; stands down while a manual setpoint or a manual off is active (v1.1.0) | many (allowed) |
| BEDTIME-LOCK | bedtime − 1 min -> bedtime | Lock mode, maintaining setpoint and the night fan (`night_fan`, default low) + auto-learn write | ≤ 3 (typically 1–2) |
| NIGHT-HOLD | bedtime -> deep-night check | Holds; blueprint issues nothing | 0 |
| DEEP-NIGHT-CHECK | deep-night check -> +10 min | At most one corrective command | 0 or 1 |
| DEEP-HOLD | deep-night check + 10 min -> wake | Holds; blueprint issues nothing | 0 |

Beep budget after bedtime: lock ≤ 3 (typically 1–2) + deep-night check ≤ 1. Turn-on is a one-way latch — once PRECOOL
begins it never reverts to DAY-OFF that day. The latch is bounded: a running
AC counts as "PRECOOL has started" only from `bedtime − lead_cap_minutes`
onward; earlier on the day side (from wake) a running unit is a leftover
night hold and DAY-OFF turns it off. Consequence: a unit switched on by hand
between wake and `bedtime − lead_cap_minutes` is switched off again within a
minute (one beep) — to use it manually during the day, disable the
automation. Configuration
validation rejects a lead cap whose earliest turn-on is at or before wake
time, comparing instants so a cap that wraps past midnight is caught too.
Cool-day nights (the AC was never started) are fully no-op.

## Manual Override (v1.1.0)

A person's change on the unit during the pre-cool is respected until the next
phase boundary:

- **Manual setpoint.** The blueprint can only ever have commanded four
  setpoints (drive, maintaining, and the two deep-night corrections, each as
  the device holds it). A unit that has been running for at least two ticks
  and whose setpoint is none of them (±0.1 °C) was set by a person:
  PRECOOL issues no command at all (mode, setpoint, fan) until the bedtime
  lock, which re-applies the maintaining setpoint and the night fan as usual;
  that night's auto-learn update is skipped when the override is still active
  at the lock. A manual setpoint during NIGHT-HOLD is untouched until the
  deep-night check, which keeps its correction rule.
- **Manual off.** The blueprint never switches the unit off between
  `bedtime − lead_cap_minutes` and the lock (only the vacation branch can), so
  an `off` transition stamped more than two minutes into that window came from
  a person: the unit stays off for the night (no lock, no deep-night check).
  The state re-created at an HA start / automation reload (up to ten minutes
  after it) and the vacation turn-off (confirmed up to two minutes after the
  toggle) are recognised and not treated as manual; a reload made after a
  manual off ends that hold.
- One persistent notification per override episode, dismissed at the boundary.
- HA state contexts cannot distinguish this automation's own writes from the
  remote's (both carry no parent/user on a time-pattern run), so detection is
  by value, not authorship (the values as the device holds them — a
  whole-degree unit stores 21 for a commanded 21.5, and the blueprint commands
  the same quantised values). Known limits: a manual change *to* one of the
  blueprint's own values is re-asserted within a minute; a manual change made
  within the first two minutes after the unit switched on is re-asserted once
  (that grace is what lets a lagged or lost command on the turn-on tick be
  retried by the next tick instead of reading as manual — the effective
  acknowledgement timeout is therefore 120 s); two consecutive lost commands,
  or a coordinator acknowledgement delayed past those 120 s, can still leave a
  remembered unknown value that reads as manual for that night; a cloud outage that ends inside the window re-stamps the `off`
  state and reads as a manual off for that night (the notification says so;
  switching the unit on by hand resumes the pre-cool at once).

## Prediction Model

```
warmest_bedroom = aggregate(bedroom sensors, strategy)        # default: max
delta_in        = max(0, warmest_bedroom − ideal_temp)
forecast_max    = max hourly forecast temp over [now -> bedtime]
                  # hourly fetched every 15 min; other ticks use the day's
                  # forecast high (never below the live outdoor reading);
                  # without either: the live outdoor sensor
delta_out       = max(0, max(forecast_max, outdoor_now) − ideal_temp)
solar_load      = 0..1 from sun elevation + azimuth
lead_bias       = self-learned correction (minutes)

lead = clamp(
         base_minutes
         + k_indoor          * delta_in
         + k_outdoor         * delta_out
         + solar_max_minutes * solar_load
         + safety_margin_minutes
         + lead_bias,
         0, lead_cap_minutes)

turn_on = bedtime − lead          # enter PRECOOL when now >= turn_on
```

The AC starts only when `cooling_needed` is true:
`warmest_bedroom > ideal_temp  OR  forecast_max > skip_threshold`.

## Auto-Learn

The blueprint self-learns one scalar — the lead-time bias — persisted in an
`input_number` helper:

```
# at BEDTIME-LOCK, only if the AC was running this night:
bedtime_error = warmest_bedroom − ideal_temp
new_bias      = clamp(lead_bias + learn_gain * bedtime_error * k_indoor,
                      max(helper.min, -60), min(helper.max, 120))
```

Room too warm at bedtime -> bias rises (start earlier tomorrow); overcooled ->
bias falls. The helper write is beep-free (it is an `input_number`, not the
AC). Converges over ~3–6 nights. Cool-day no-ops are skipped.

A single glitchy-but-valid bedroom reading at the bedtime lock skews that one
night's auto-learn write, but the `[-60, 120]` clamp bounds how far it can move
the bias and subsequent nights wash the outlier out.

## Functional Requirements

### Climate Control
1. 6-phase stateless daily state machine, phase derived from `now`.
2. Predictive turn-on from a transparent linear lead-time formula.
3. Closed-loop pre-cool on the warmest bedroom (DRIVE / HOLD sub-states).
4. Bedtime lock — locks the maintaining setpoint and the night fan mode (`night_fan`, default low, matched case-insensitively to the unit's modes; falls back to the normal fan with a notice if the unit lacks it).
5. One optional corrective command at the deep-night checkpoint.
6. AC off at wake.

### Beep Budget
1. Unlimited commands before bedtime; after bedtime the lock issues ≤ 3 (mode, setpoint, night fan — typically 1–2) and the deep-night check ≤ 1.
2. Every climate service call guarded by a current-vs-desired comparison.
3. NIGHT-HOLD and DEEP-HOLD issue zero service calls.

### Mode Selection
1. `cool` is the proven default path.
2. Optional `dry` mode (default off) — only chosen while beeps are free, and
   only when humid with a small temperature gap.

### Overrides
1. Vacation toggle: forces the AC off and stands the blueprint down.
2. Sound mute: keeps the AC beep switch off.

### Safety
1. Bedroom sensor failure: holds state, fires a persistent notification.
2. AC entity unavailable: skips the tick, retries next minute.
3. Forecast: the hourly window (fetched every 15 minutes) feeds the
   prediction; every other daytime tick uses the day's forecast high
   (`weather.get_forecasts type: daily`, gated on the entity's
   FORECAST_DAILY feature); without either, the live outdoor sensor.
4. `ideal_temp` is bounded >= 16 °C (child-safety floor); a bedroom reading
   below 16 °C raises an overcooling-fault notification.
5. Every setpoint clamped to the AC's discovered `min_temp` / `max_temp`.
6. Configuration validation: blocks operation on an invalid setup.

## Testing & Debugging

Manual "Run" in HA produces a persistent notification dumping all computed
state: phase, warmest/coldest bedroom, ΔT terms, solar load, forecast_max,
lead_bias, lead, turn_on, cooling_needed, AC mode/setpoint/fan, the discovered
AC limits, and the resolved setpoints. Set `bedtime` to a few minutes ahead to
watch PRECOOL -> BEDTIME-LOCK -> NIGHT-HOLD live.

## Out of Scope (V2)

- Auto-learned `hall_offset` (V1 auto-learns the lead-time bias only).
- Per-day or weekday/weekend `bedtime` / `wake_time`.
- Mobile push notifications.
- Window/door contact sensors to detect unreachable rooms.
- ESPHome silent-mode controller (makes the beep budget a non-constraint).
