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
  Number (range roughly -60 to 120, step 1).
- **input_boolean helper (optional):** For the vacation toggle.

## Daily State Machine

The blueprint is stateless: a 1-minute loop derives which phase `now` is in and
acts. Phase boundaries span midnight (bedtime -> wake is an overnight window).

| Phase | Window | AC behaviour | Beeps |
|---|---|---|---|
| DAY-OFF | wake -> turn_on | Ensure AC off; recompute turn-on each tick | 0 (1 at wake) |
| PRECOOL | turn_on -> bedtime − 1 min | Cooling; closed-loop DRIVE / HOLD | many (allowed) |
| BEDTIME-LOCK | bedtime − 1 min -> bedtime | One locking command + auto-learn write | 0–1 |
| NIGHT-HOLD | bedtime -> deep-night check | Holds; blueprint issues nothing | 0 |
| DEEP-NIGHT-CHECK | deep-night check -> +10 min | At most one corrective command | 0 or 1 |
| DEEP-HOLD | deep-night check + 10 min -> wake | Holds; blueprint issues nothing | 0 |

Beep budget after bedtime: 0–2. Turn-on is a one-way latch — once PRECOOL
begins it never reverts to DAY-OFF that day. Cool-day nights (the AC was never
started) are fully no-op.

## Prediction Model

```
warmest_bedroom = aggregate(bedroom sensors, strategy)        # default: max
delta_in        = max(0, warmest_bedroom − ideal_temp)
forecast_max    = max forecast temp over [now -> bedtime]     # fallback: outdoor sensor
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
new_bias      = clamp(lead_bias + learn_gain * bedtime_error * k_indoor, -60, 120)
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
4. Bedtime lock — one deliberate command sets a maintaining setpoint.
5. One optional corrective command at the deep-night checkpoint.
6. AC off at wake.

### Beep Budget
1. Unlimited commands before bedtime; 0–2 after bedtime.
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
3. Forecast unavailable: falls back to the daily forecast, then to the live
   outdoor sensor.
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
