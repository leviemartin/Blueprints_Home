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
- **Bedroom Fans (optional, v1.1.0):** Ceiling fans, one per room. Leave empty
  to keep the pre-v1.1.0 behaviour (no fan is ever commanded).
- **Fan Interlock Sensor (optional, v1.1.0):** A `binary_sensor` (e.g. a
  height-gated presence sensor) that blocks commands to the interlocked fans
  while on or unavailable, plus a clear hold (`interlock_clear_minutes`).

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
| DAY-OFF | wake -> min(turn_on, bedtime − lead_cap) | Ensure AC off — any running unit is switched off on the next tick; recompute turn-on each tick | 1 at wake (+1 per manual daytime turn-on) |
| PRECOOL | turn_on -> bedtime − 1 min | Cooling; closed-loop DRIVE / HOLD | many (allowed) |
| BEDTIME-LOCK | bedtime − 1 min -> bedtime | Lock mode, maintaining setpoint and the night fan (`night_fan`, default low) + auto-learn write; `fan_only`: park then off unless already over the band (≤ 4 commands: mode, setpoint, fan, off — typically 1) | ≤ 3 (typically 1–2); `fan_only` ≤ 4 (typically 1) |
| FAN SETTLE (lock -> bedtime + settle) | lock -> bedtime + `fan_settle_minutes` | Bedroom Fans to the night percentage under the fan write rule, at most one command per fan, live re-check before each call | — |
| NIGHT-HOLD | bedtime -> deep-night check | Holds; blueprint issues nothing | 0 |
| NIGHT GUARD (any 5-minute tick after bedtime, `fan_only`) | any night phase | One bare `turn_on` restoring the parked state; the running unit is the latch. GUARD SETTLE, for 15 min after any night start, asserts mode / setpoint (outside ± `correction_step`) / fan from live reads — normally 0 commands | turn_on 1 + settle ≤ 3 (typical 1–2, worst 5) |
| DEEP-NIGHT-CHECK | deep-night check -> +10 min | At most one corrective command | 0 or 1 |
| DEEP-HOLD | deep-night check + 10 min -> wake | Holds; blueprint issues nothing | 0 |

Beep budget after bedtime: `ac_hold` — lock ≤ 3 (typically 1–2) + deep-night
check ≤ 1 (unchanged). `fan_only` — lock ≤ 4 (typically 1) + guard nights
turn_on 1 + settle ≤ 3 + deep-night nudge ≤ 1 (typical 1–2, worst 5). Turn-on
is a one-way latch — once PRECOOL begins it never reverts to DAY-OFF that
day. The latch is bounded: a running AC counts as "PRECOOL has started" only
from `bedtime − lead_cap_minutes` onward; earlier on the day side (from
wake) a running unit is a leftover night hold and DAY-OFF turns it off.
Consequence: a unit switched on by hand between wake and
`bedtime − lead_cap_minutes` is switched off again within a minute (one
beep) — to use it manually during the day, disable the automation
(manual-override handling is a v1.2.0 item (#19)). Configuration validation
rejects a lead cap whose earliest turn-on is at or before wake time,
comparing instants so a cap that wraps past midnight is caught too. Cool-day
nights (the AC was never started) are fully no-op.

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

## Night Mode & Pre-Chill (v1.1.0)

```
bedtime_target = ideal_temp − prechill_offset   (night_mode: fan_only)
                = ideal_temp                     (night_mode: ac_hold)
```

`bedtime_target` is the value the rest of the prediction actually aims at:
it replaces `ideal_temp` in `delta_in` (the indoor lead term), in
`cooling_needed` (the cool-day skip gate) and in the PRECOOL `DRIVE`/`HOLD`
sub-state test, and the BEDTIME-LOCK auto-learn write keys its error off it
too (`bedtime_error = warmest_bedroom − bedtime_target`). In `ac_hold` mode
`bedtime_target == ideal_temp`, so v1.0.x behaviour is unchanged. In
`fan_only` mode PRECOOL drives the warmest bedroom `prechill_offset` °C below
`ideal_temp` before the lock, so the room starts the coast with a margin
before the AC goes off and the Bedroom Fans take over for the night.

At the BEDTIME-LOCK, `fan_only` parks the unit on the maintaining setpoint
and night fan (the same calls as `ac_hold`), then switches it off — unless
the warmest bedroom is already over `ideal_temp + tolerance`, in which case
it stays on exactly as in `ac_hold` (the Night guard would only turn it back
on next tick otherwise). After the lock, the **Night guard** watches every
5-minute tick in any night phase: if `fan_only` and the AC is off and the
warmest bedroom drifts over `ideal_temp + tolerance`, one bare `turn_on`
restores the parked state (one beep) — the running unit is the latch, so the
guard does not fire again until DAY-OFF turns the unit off at wake. For 15
minutes after any night start (guard or otherwise), GUARD SETTLE
re-asserts mode / setpoint (only outside ± `correction_step`, so it never
undoes a deep-night correction) / fan from live reads, each only if it
differs from the parked state — normally 0 commands.

## Bedroom Fans — The Fan Write Rule (v1.1.0)

A configured bedroom fan gets a command only when ALL of the following hold,
evaluated first as a per-tick due list and then re-checked live immediately
before the call:

1. Configured (listed in `bedroom_fans`) and available — not `unavailable`
   or `unknown`.
2. Not already at the target percentage (the night or pre-cool percentage).
3. Interlock clear: not one of `interlocked_fans` while any `fan_interlocks`
   sensor is on, unavailable, unknown, absent from the state machine, or
   changed state within `interlock_clear_minutes` — the clear hold.
4. Untouched since the reference instant: `last_updated` (not
   `last_changed` — a percentage change bumps the former, not the latter)
   older than the lock (night list) or the AC start (pre-cool list).

The night list is only evaluated inside the fan settle window
(`fan_settle_minutes` after the lock); anything still unmet when the settle
window closes is reported once (`fans_unset_night`) and never retried. The
rule never re-asserts the safety cutoff's own restore and never overrides a
fan changed by hand — both show up as a touch on `last_updated`, so the fan
is simply left alone. Direction is never written.

**Deploy-time invariant:** `interlock_clear_minutes` must be set `>=` the
safety cutoff's own resume hold + 2 minutes, so this blueprint never writes
an interlocked fan in the same minute the cutoff resumes it, nor inside its
hold.

**Known limitation:** a fan the safety cutoff resumed after the lock keeps
the cutoff's restored speed — the fan write rule only fires while the fan is
untouched since the reference, so the cutoff's own resume (which touches
`last_updated`) leaves that fan at whatever percentage the cutoff restored
it to, not the night percentage (spec §2.5).

## Experiments (v1.1.0)

`night_fans` and `fan_assist` each independently gate the Bedroom Fans by
odd/even day-of-year parity of the night's START date (the calendar date at
wake time) — `all`/`off` bypass parity entirely. Parity pivots at wake time,
so one value covers a pre-noon PRECOOL start through the last tick before
wake, rather than flipping at midnight mid-night. This supports A/B
comparison of whether a fan in the room speeds the measured pre-cool
(`fan_assist`) and whether the night fan reduces overnight drift
(`night_fans`), independent of the AC's own beep budget.

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
- Learning from guard nights (the night guard and its settle correction do
  not feed the auto-learn bias).
