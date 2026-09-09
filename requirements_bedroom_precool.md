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
- **Bedroom Fans (optional, v1.2.0):** Ceiling fans, one per room. Leave empty
  to keep the pre-v1.2.0 behaviour (no fan is ever commanded).
- **Fan Interlock Sensor (optional, v1.2.0):** A `binary_sensor` (e.g. a
  height-gated presence sensor) that blocks commands to the interlocked fans
  while on or unavailable, plus a clear hold (`interlock_clear_minutes`).

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
| BEDTIME-LOCK | bedtime − 1 min -> bedtime | Lock mode, maintaining setpoint and the night fan (`night_fan`, default low) + auto-learn write; `fan_only`: park then off unless already over the band (≤ 4 commands: mode, setpoint, fan, off — typically 1) | ≤ 3 (typically 1–2); `fan_only` ≤ 4 (typically 1) |
| FAN SETTLE (lock -> bedtime + settle) | lock -> bedtime + `fan_settle_minutes` | Bedroom Fans to the night percentage under the fan write rule, at most one command per fan, live re-check before each call | — |
| NIGHT-HOLD | bedtime -> deep-night check | Holds; blueprint issues nothing (ac_hold). fan_only: the night guard may switch the unit back on once (a 5-minute tick, warmest > ideal + tolerance, not during a respected manual off), then the guard settle asserts the parked state for 15 min | 0 (ac_hold) · fan_only: ≤ 1 guard turn_on + 1 guard mode + ≤ 2 settle (normally 0) |
| NIGHT GUARD (any 5-minute tick after bedtime, `fan_only`) | any night phase | `turn_on` + an unconditional `set_hvac_mode` restoring the parked state in cooling mode; the running unit is the latch. HEAT BACKSTOP: any real tick that finds the unit running in `heat` mode gets an unconditional `climate.turn_off` (v1.2.0 — a heater is never the fallback in a child's bedroom); the guard's own turn_on + set_hvac_mode restores cooling on the next 5-minute tick. GUARD SETTLE, for 15 min after any night start, asserts setpoint (outside every quantised night-hold value) / fan from live reads — normally 0 commands (`settle_mode_due` only matters after a manual night start) | turn_on 1 + set_hvac_mode 1 + settle ≤ 2 (setpoint, fan) + nudge ≤ 1 (typical 2, worst 5); heat backstop ≤ 1 `turn_off` per tick, worst case ≤ 1 min of heat and 3 commands per 5-minute backstop+guard cycle |
| DEEP-NIGHT-CHECK | deep-night check -> +10 min | At most one corrective command | 0 or 1 |
| DEEP-HOLD | deep-night check + 10 min -> wake | Holds; blueprint issues nothing (ac_hold). fan_only: the night guard may switch the unit back on once (a 5-minute tick, warmest > ideal + tolerance, not during a respected manual off), then the guard settle asserts the parked state for 15 min | 0 (ac_hold) · fan_only: ≤ 1 guard turn_on + 1 guard mode + ≤ 2 settle (normally 0) |

Beep budget after bedtime: `ac_hold` — lock ≤ 3 (typically 1–2) + deep-night
check ≤ 1 (unchanged). `fan_only` — lock ≤ 4 (typically 1) + guard nights
turn_on 1 + set_hvac_mode 1 + settle ≤ 2 (setpoint, fan) + nudge ≤ 1
(typical 2, worst 5). Turn-on
is a one-way latch — once PRECOOL begins it never reverts to DAY-OFF that
day. The latch is bounded: a running AC counts as "PRECOOL has started" only
from `bedtime − lead_cap_minutes` onward; earlier on the day side (from
wake) a running unit is a leftover night hold and DAY-OFF turns it off.
Consequence: a unit switched on by hand between wake and
`bedtime − lead_cap_minutes` is switched off again within a minute (one
beep) — to use it manually during the day, disable the automation.
Configuration validation rejects a lead cap whose earliest turn-on is at or
before wake time, comparing instants so a cap that wraps past midnight is
caught too. Cool-day nights (the AC was never started) are fully no-op.

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
  a person: the unit stays off for the night (no lock, no deep-night check);
  before wake time the flag still refers to the previous evening's window, so
  the notice stays until the deep-night check.
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
bedtime_target  = ideal_temp − prechill_offset (fan_only) | ideal_temp (ac_hold)
warmest_bedroom = aggregate(bedroom sensors, strategy)        # default: max
delta_in        = max(0, warmest_bedroom − bedtime_target)
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
`warmest_bedroom > bedtime_target  OR  forecast_max > skip_threshold`.

## Auto-Learn

The blueprint self-learns one scalar — the lead-time bias — persisted in an
`input_number` helper:

```
# at BEDTIME-LOCK, only if the AC was running this night:
bedtime_error = warmest_bedroom − bedtime_target
raw           = lead_bias + learn_gain * bedtime_error * k_indoor
floor         = ceil(max(helper.min, -60))      # whole numbers inside helper ∩ [-60, 120]
ceiling       = floor(min(helper.max, 120))
new_bias      = clamp(round(raw), floor, ceiling)   # written only if floor <= ceiling
```

Room too warm at bedtime -> bias rises (start earlier tomorrow); overcooled ->
bias falls. The helper write is beep-free (it is an `input_number`, not the
AC). Converges over ~3–6 nights. Cool-day no-ops are skipped.

A single glitchy-but-valid bedroom reading at the bedtime lock skews that one
night's auto-learn write, but the `[-60, 120]` clamp bounds how far it can move
the bias and subsequent nights wash the outlier out.

## Night Mode & Pre-Chill (v1.2.0)

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
warmest bedroom drifts over `ideal_temp + tolerance`, a bare `turn_on` plus
an unconditional `set_hvac_mode` restores the parked state AND forces
cooling mode — the running unit is the latch, so the guard does not fire
again until DAY-OFF turns the unit off at wake — not while a manual off is
being respected (v1.1.0 semantics); the lock's own off inside lock + 180 s
is the blueprint's, not a person's. **Heat backstop (v1.2.0, board
20260909-151815 cycle 2 G3):** on any real tick, fan-only, in a night phase,
if the unit is found running in `heat` mode it is switched off unconditionally
— a heater is never an acceptable fallback in a child's bedroom — and the
guard's own turn_on + set_hvac_mode restores cooling on the next 5-minute
tick. For 15 minutes after any night start (guard or otherwise), GUARD
SETTLE re-asserts mode / setpoint / fan from live reads, each only if it
differs from the parked state — the setpoint check leaves every night-hold
setpoint (maintaining and the two quantised nudges) alone; the mode check
matters only after a manual night start, since a guard-triggered start
already forced cooling mode — normally 0 commands, and never while a manual
setpoint is active.

**Honest note on the lock-window misread (code board 20260909-151815 cycle 2
G4, was cycle 1 F6):** a person's off stamped inside `[lock_ts, lock_ts +
180s)` on a fan-only night is treated as the blueprint's own off; the guard
may switch the unit back on at its next 5-minute tick (two commands:
`turn_on` + cooling mode). A manual off stamped **after** `lock_ts + 180s`
is respected until wake. To keep the unit off in that first three minutes,
switch it off again after 19:33 (three minutes past the default 19:30
bedtime's 19:29 lock).

## Bedroom Fans — The Fan Write Rule (v1.2.0)

A configured bedroom fan gets a command only when ALL of the following hold,
evaluated first as a per-tick due list and then re-checked live immediately
before the call:

0. An interlocked fan whose ON-TRANSITION (`last_changed`) is newer than the
   reference of the write window currently active (`lock_ts` while settling,
   `ac_started_ts` while assisting) and within the last 120 s, while an
   interlock sensor actively reads `on`, is switched off unconditionally —
   this can only cancel a write THIS blueprint itself could have issued in
   that window (code board 20260909-151815 F3, narrowed by cycle 2 G1 after
   the cycle-1 version was found firing on every tick, defeating the safety
   cutoff's own "manual override wins" contract). Outside the fan-settle /
   fan-assist windows, or a fan already on before the window opened, or a
   fan started more than two minutes ago, this cut never touches it — a
   deliberate fan start is cut at most once, only if it lands inside this
   blueprint's own write window; the person keeps the fan by starting it
   after the interlock sensor clears, or outside those windows.
1. Configured (listed in `bedroom_fans`) and available — not `unavailable`
   or `unknown`.
2. Not already at the target percentage (the night or pre-cool percentage).
3. Interlock clear: not one of `interlocked_fans` while any `fan_interlocks`
   sensor is on, unavailable, unknown, absent from the state machine, or
   changed state within `interlock_clear_minutes` — the clear hold.
4. Untouched since the reference instant: `last_updated` (not
   `last_changed` — a percentage change bumps the former, not the latter)
   older than the lock (night list) or the AC start (pre-cool list). The
   pre-cool assist window additionally requires the automation to already
   have been running when TODAY's adoption window opened
   (`automation_up_since_ts < earliest_turn_on_ts`, code board
   20260909-151815 cycle 2 G2 — a restart inside today's window disables
   fan assist for the rest of that night, not just for 600 s past the
   restart as cycle 1's F4 had it) — the AC start reference also moves on a
   cool<->dry mode transition and at an HA restart, and either can still
   re-open assist ONCE against a fan a person switched off after the
   ORIGINAL start (see Experiments below for the accepted residual). A bare
   mode transition inside a long-up automation is a documented residual
   case: `dry` mode and `fan_assist` are both off by default.

The fan step runs before STEP 5's AC/sensor validation (code board
20260909-151815 F10), so fan writes and the skipped-fan notice fire on
every real tick even while the AC entity is unavailable; they are skipped
only during vacation (STEP 4, ahead of the fan step).

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

**Accepted residual (operator decision, 2026-09-09 — code board
20260909-151815, R2C2-01):** a `fan.turn_on` this blueprint issues reaches
the Tuya cloud 10–60 s after the call, so if an interlock sensor trips
inside that lag the fan can run at its night speed (1 %) for roughly one
tick plus delivery latency before `fans_unsafe_on` cuts it on the next
tick; that cut cannot restore a cutoff resume the late write already
cancelled. The operator accepted this bounded exposure rather than removing
the kids-room fan from the instance, because the interlock and its clear
hold block every ordinary case and the exposure is at the lowest fan speed.
Escape hatch: removing that fan from `bedroom_fans` in the instance
disables every write to it while leaving the code path intact.

## Experiments (v1.2.0)

`night_fans` and `fan_assist` each independently gate the Bedroom Fans by
odd/even day-of-year parity of the night's START date (the calendar date at
wake time) — `all`/`off` bypass parity entirely. Parity pivots at wake time,
so one value covers a pre-noon PRECOOL start through the last tick before
wake, rather than flipping at midnight mid-night. This supports A/B
comparison of whether a fan in the room speeds the measured pre-cool
(`fan_assist`) and whether the night fan reduces overnight drift
(`night_fans`), independent of the AC's own beep budget.

**Accepted residual (code board 20260909-151815 cycle 2 G2, R1C2-04):** the
fan-assist reference `ac_started_ts` is the climate entity's `last_changed`,
which also moves on an `unavailable -> cool` cloud flap or a `cool <-> dry`
mode transition — either can re-open the 45-minute assist window ONCE with
the new reference and re-command a fan a person switched off after the
ORIGINAL start (one 21 % command, interlock still honoured). Accepted
because `fan_assist` and `dry` mode both default off and the experiment
only runs on chosen nights.

## Functional Requirements

### Climate Control
1. 6-phase stateless daily state machine, phase derived from `now`.
2. Predictive turn-on from a transparent linear lead-time formula.
3. Closed-loop pre-cool on the warmest bedroom (DRIVE / HOLD sub-states).
4. Bedtime lock — locks the maintaining setpoint and the night fan mode (`night_fan`, default low, matched case-insensitively to the unit's modes; falls back to the normal fan with a notice if the unit lacks it).
5. One optional corrective command at the deep-night checkpoint.
6. AC off at wake.

### Beep Budget
1. Unlimited commands before bedtime; after bedtime the lock issues ≤ 3 in ac_hold (mode, setpoint, night fan — typically 1–2) and ≤ 4 in fan_only (… + off — typically 1); the deep-night check ≤ 1.
2. Every climate service call guarded by a current-vs-desired comparison.
3. NIGHT-HOLD and DEEP-HOLD issue zero service calls in ac_hold mode; in fan_only mode only the night guard (`turn_on` + unconditional `set_hvac_mode`, restoring the parked state in cooling mode regardless of what the stale read shows), the heat backstop (`turn_off`, worst case ≤ 1 min of heat and 3 commands per 5-minute backstop+guard cycle — v1.2.0), and the guard's settle corrections (setpoint, fan — normally 0) may fire, and the fan step writes each configured fan at most once per transition.

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
- Learning from guard nights (the night guard and its settle correction do
  not feed the auto-learn bias).
