# Bedroom Sleep Pre-Cool Blueprint — Design Spec

**Date:** 2026-05-22
**Version:** v1.0.0
**Blueprint file:** `bedroom_precool.yaml`
**Approach:** New standalone blueprint — single instance for one hall AC cooling multiple bedrooms indirectly
**Tracking:** Epic #1 (Blueprints_Home) → session sub-issue (this work)

---

## Overview

A Home Assistant blueprint that drives a single LG air conditioner — located in the
upstairs hall — to bring the **bedrooms** to an ideal sleep temperature (default 19 °C)
by a fixed bedtime (default 19:30), then holds the room quietly overnight while issuing
the absolute minimum number of commands.

The constraint that shapes the entire design: LG ACs **beep on every command** received
over ThinQ or IR (a firmware confirmation tone that cannot be silenced in software — see
`guides/lg_ac_disable_beep.md`). The blueprint therefore treats AC commands as a scarce
resource after bedtime: it adjusts freely *before* bedtime, locks a maintaining setpoint
*at* bedtime, permits at most one corrective command at a deep-night checkpoint (~01:00),
and turns the AC off at wake (~07:15).

The AC is **not in the bedrooms** — it cools the hall and cold air migrates through open
doors. This makes cooling indirect, laggy, and load-dependent, which is why the turn-on
time must be *predicted* from outdoor temperature, weather forecast, and solar gain
rather than reacted to.

This blueprint is beep-safe by design for the current ThinQ setup. When the household
later adopts the ESPHome wired controller (silent commands — see the beep guide), the
beep budget becomes a non-constraint; a "silent mode" that tracks temperature all night
is noted as a V2 enhancement.

## Requirements Summary

- One LG AC in the hall, cooling 2+ bedrooms via open doors (indirect cooling).
- Control variable = the **bedrooms** (Aqara temp sensors in the rooms), aggregated;
  the AC's own hall thermistor is not the target.
- Reach `ideal_temp` (default 19 °C) in the warmest bedroom by `bedtime` (default 19:30).
- **Beep budget:** unlimited commands before bedtime; after bedtime, at most one
  corrective command, at the `deep_night_check` time (~01:00), and only if the room has
  drifted out of tolerance; AC off at `wake_time` (~07:15).
- **Predict** the daily turn-on time from indoor gap + outdoor temperature + hourly
  weather forecast + solar gain — so cool days skip cooling entirely and hot days start
  earlier.
- Humidity-aware mode: use the AC's `dry` mode on muggy nights, `cool` when there is a
  real temperature gap. Mode is only ever chosen while beeps are free.
- Stateless, idempotent, restart-safe. ThinQ now; ESPHome-ready later.

## Hardware & Topology

```
                 ┌───────────────┐
   outdoor ──────┤  HALL  (LG AC) ├────── cold air migrates through open doors
   weather       └───┬────────┬──┘
   sun.sun           │        │
                 ┌───▼──┐ ┌───▼──┐
                 │ Bed 1│ │ Bed 2│   ← Aqara temp + humidity sensors here
                 └──────┘ └──────┘      (the control target)
```

| Device | Role | Blueprint input |
|---|---|---|
| LG AC `climate` entity (hall) | The single unit under control (ThinQ integration) | `ac_climate` |
| Aqara bedroom temperature sensors | Control variable — the rooms we actually care about | `bedroom_temp_sensors` (multiple) |
| Aqara bedroom humidity sensors | Drives cool-vs-dry mode selection | `bedroom_humidity_sensors` (multiple, optional) |
| Outdoor temperature sensor | Heat-load term; forecast fallback | `outdoor_temp_sensor` |
| Weather entity | Hourly forecast for anticipatory prediction | `weather_entity` |
| `sun.sun` (built-in) | Solar-gain term — no hardware needed | `sun_entity` (default `sun.sun`) |
| LG AC sound `switch` (optional) | Kept muted (matches `lg_ac_climate`) | `ac_sound_switch` (multiple, optional) |
| `input_boolean` (optional) | Vacation / full-off | `vacation_toggle` (multiple, optional) |

**Operating assumption (V1):** bedroom doors are open during the pre-cool window. With no
door/window contact sensors (deliberately out of scope), a closed door means that room
will not cool and the blueprint cannot detect it. Documented, not guarded.

## Daily State Machine

The blueprint is stateless: a 1-minute loop derives which **phase** `now` is in and acts.
Phase boundaries span midnight (bedtime → wake is an overnight window).

```
  07:15            ~15:00–18:00       19:28  19:30        01:00   01:10          07:15
   │                     │              │     │             │      │              │
   ▼                     ▼              ▼     ▼             ▼      ▼              ▼
 ┌──────── DAY-OFF ──────┬─── PRECOOL ──┬LOCK┬─ NIGHT-HOLD ─┬CHECK─┬── DEEP-HOLD ──┐
 │ AC off; predict       │ AC cooling;  │set │ AC holds;    │0-1   │ AC holds;     │
 │ turn-on each tick     │ closed-loop, │main│ blueprint    │beep  │ blueprint     │
 │                       │ beeps free   │tain│ issues       │      │ issues        │
 │                       │ (DRIVE/HOLD) │ 1  │ nothing      │      │ nothing       │
 │                       │              │beep│              │      │               │
 └───────────────────────┴──────────────┴────┴──────────────┴──────┴───────────────┘
```

| Phase | Window | AC behaviour | Beeps |
|---|---|---|---|
| **DAY-OFF** | `wake_time` → `turn_on` | Ensure AC off (one `off` command fires at wake via idempotency). Recompute `turn_on` each tick. | 0 (1 at wake transition) |
| **PRECOOL** | `turn_on` → `bedtime − 2 min` | AC cooling; closed-loop on warmest bedroom; DRIVE / HOLD sub-states. Adjust freely. | many (allowed) |
| **BEDTIME-LOCK** | `bedtime − 2 min` → `bedtime` | If the AC is running: one deliberate command — set `maintaining_setpoint` + locked mode. If the AC is off (cool day): no-op. | 0–1 |
| **NIGHT-HOLD** | `bedtime` → `deep_night_check` | AC holds locked setpoint; blueprint issues *nothing*. | 0 |
| **DEEP-NIGHT-CHECK** | `deep_night_check` → `+10 min` | If the AC is running and the warmest bedroom drifted outside `ideal ± tolerance`: one corrective command. AC off, or in-band: nothing. | 0 or 1 |
| **DEEP-HOLD** | `deep_night_check + 10 min` → `wake_time` | AC holds; blueprint issues *nothing*, regardless of drift — enforces the "once" rule. | 0 |

**Beep budget after bedtime: 0–2** — a cool-day no-op night is 0; a cooling night is the
deep-night check (0–1) plus the wake-off (1). The bedtime lock fires 2 minutes early so
it is unambiguously inside the beeps-allowed window.

**Cool-day / AC-off nights:** if `cooling_needed` stayed `false` all day and the AC was
never started, BEDTIME-LOCK and all night phases are no-ops — the AC remains off until
the next DAY-OFF. The night phases and the deep-night correction only act on an
already-running AC (`current_hvac_mode != 'off'`); the blueprint never *starts* cooling
after bedtime, because that would spend a beep the budget does not allow.

Two constants are fixed in code rather than exposed as inputs: bedtime-lock lead
(`2 min`) and the deep-night check window (`10 min`).

## Prediction Model

### Cooling-needed gate (cool-day skip)

Evaluated every tick during DAY-OFF, before any lead-time math:

```
cooling_needed =  warmest_bedroom > ideal_temp
               OR forecast_max > skip_threshold
```

If `false`, the blueprint stays in DAY-OFF and the AC never starts — the 17 °C-day case.
Continuous re-evaluation means a day that starts mild but heats up flips this `true`
mid-afternoon and proceeds normally. The gate is consulted during DAY-OFF only; once
PRECOOL has started the AC, the phase machine manages the rest of the cycle.

### Lead-time formula

Recomputed every tick during DAY-OFF:

```
warmest_bedroom = aggregate(bedroom_temp_sensors, sensor_strategy)   # default: max
ΔT_in        = max(0, warmest_bedroom − ideal_temp)
forecast_max = max forecast temp over [now → bedtime]   # fallback: live outdoor sensor
outdoor      = max(forecast_max, outdoor_now)            # most conservative
ΔT_out       = max(0, outdoor − ideal_temp)
solar        = solar_load(sun elevation, azimuth)        # 0..1; see below

lead =  base_minutes
      + k_indoor          * ΔT_in
      + k_outdoor         * ΔT_out
      + solar_max_minutes * solar
lead =  clamp(lead + safety_margin_minutes, 0, lead_cap_minutes)

turn_on = bedtime − lead          →  enter PRECOOL when now >= turn_on
```

Asymmetric cost — being early is cheap (room sits at ideal a little longer), being late
misses bedtime — so `safety_margin_minutes` biases the estimate early.

### Solar-gain factor

`solar_load` is a 0..1 factor derived from `sun.sun` `elevation` and `azimuth`:
- `0` when the sun is below the horizon.
- Rises with the radiant load on the house. West-facing bedrooms bake under low
  evening sun (NL daylight to ~22:00 in June), so the factor must be **high for an
  up sun in the afternoon/evening** (azimuth roughly 180–300°), not just for a high sun.
- `solar_afternoon_only` (default `true`) restricts the contribution to post-solar-noon
  azimuths.

The exact `solar_load` curve is a **research-validate target** — see below. V1 ships a
transparent, tunable approximation; it must not be a black box.

### Forecast handling

The hourly forecast is fetched via the `weather.get_forecasts` action into a response
variable, then templated to derive `forecast_max` (max temp over `now → bedtime`), used
by both the lead-time formula and the cooling-needed skip gate. To limit load on the
weather integration, the forecast is refreshed periodically during DAY-OFF (≈ every
15 min, not every tick); between refreshes the prediction uses the live
`outdoor_temp_sensor`. Exact cadence is an implementation detail for the plan.

If the weather entity supports only daily forecasts, fall back to the daily high; if
forecast is entirely unavailable, fall back to the live outdoor sensor.

## Control Logic

### Closed-loop pre-cool (DRIVE / HOLD)

PRECOOL has two sub-states, switching freely (beeps allowed):

| Sub-state | Condition | Action |
|---|---|---|
| **DRIVE** | warmest bedroom `> ideal_temp` | hall setpoint = `drive_setpoint` (default 16 °C), fan high |
| **HOLD** | warmest bedroom `<= ideal_temp` | hall setpoint = `maintaining_setpoint`, normal fan |

`maintaining_setpoint = ideal_temp − hall_offset` (default 19 − 2 = 17 °C). The
`hall_offset` is the configurable answer to indirect cooling: the hall must run colder
than the bedroom target. The debug notification reports overnight bedroom drift so the
value can be tuned over a few nights. An auto-learned offset is a V2 enhancement.

The closed loop on the bedroom sensors auto-discovers how hard to push; the user never
has to measure the offset for the *drive* phase.

### Bedtime lock

At `bedtime − 2 min`, if the AC is running, the blueprint sends one command setting
`maintaining_setpoint` and the locked mode. **It always locks `maintaining_setpoint`**,
even if PRECOOL did not finish (hot day, warmest bedroom still above ideal). On a miss,
the rooms simply coast down toward ideal over the following hour or two under the
maintaining setpoint — a graceful degradation that costs zero extra beeps. If the AC is
off (cool-day no-op), the bedtime lock does nothing.

### Cool vs dry mode

Mode is chosen **only while beeps are free** — during PRECOOL and at the bedtime lock —
and never switched during the quiet window.

```
if warmest_bedroom > ideal_temp + tolerance      → cool   # real gap: hitting 19 °C wins
elif room_humidity > humidity_threshold          → dry
else                                             → cool
```

`room_humidity` = max across `bedroom_humidity_sensors` (empty list → dry mode disabled,
always `cool`). The mode locked at bedtime applies the same rule to the bedtime snapshot.

**Caveat:** LG `dry`-mode target-temperature behaviour is model-specific (some units
ignore the setpoint in dry mode). This is a research-validate + on-unit-testing item; if
`dry` proves unpredictable on the actual unit, the feature degrades cleanly to cool-only.

### Deep-night correction

In the `DEEP-NIGHT-CHECK` window (`deep_night_check` → `+10 min`):

```
# precondition: AC is running (current_hvac_mode != 'off'); if off, skip
drift = warmest_bedroom − ideal_temp
if drift >  tolerance   → one command: setpoint −= correction_step   # too warm
if drift < -tolerance   → one command: setpoint += correction_step   # overcooled
else                    → nothing
```

Defaults: `tolerance` ±1.5 °C, `correction_step` 1.5 °C. The correction is idempotent and
the window is only 10 minutes wide — together these hard-guarantee at most one beep. After
the window, DEEP-HOLD issues nothing regardless of further drift.

## Inputs

~28 inputs in 6 groups. Most have sensible defaults; a minimal setup configures only the
~6 entity selectors in Group 1.

### Group 1 — Devices & Sensors (7)

| Input | Selector | Default |
|---|---|---|
| `ac_climate` | `entity` domain `climate` | required |
| `bedroom_temp_sensors` | `entity` domain `sensor`, device_class `temperature`, multiple | required |
| `bedroom_humidity_sensors` | `entity` domain `sensor`, device_class `humidity`, multiple | `[]` (empty disables dry mode) |
| `outdoor_temp_sensor` | `entity` domain `sensor`, device_class `temperature` | required |
| `weather_entity` | `entity` domain `weather` | required |
| `ac_sound_switch` | `entity` domain `switch`, multiple | `[]` |
| `sun_entity` | `entity` domain `sun` | `sun.sun` |

### Group 2 — Target Temperatures (7)

| Input | Selector | Default |
|---|---|---|
| `ideal_temp` | `number` 14–25 °C, step 0.5 | 19.0 |
| `hall_offset` | `number` 0–6 °C, step 0.5 | 2.0 |
| `drive_setpoint` | `number` 14–22 °C, step 0.5 | 16.0 |
| `tolerance` | `number` 0.5–4 °C, step 0.5 | 1.5 |
| `correction_step` | `number` 0.5–4 °C, step 0.5 | 1.5 |
| `skip_threshold` | `number` 16–28 °C, step 0.5 | 22.0 |
| `humidity_threshold` | `number` 40–80 %, step 1 | 65 |

### Group 3 — Schedule (3)

| Input | Selector | Default |
|---|---|---|
| `bedtime` | `time` | 19:30 |
| `wake_time` | `time` | 07:15 |
| `deep_night_check` | `time` | 01:00 |

### Group 4 — Prediction Tuning (7)

| Input | Selector | Default |
|---|---|---|
| `base_minutes` | `number` 0–120 | 30 |
| `k_indoor` | `number` 0–60 min/°C | 15 |
| `k_outdoor` | `number` 0–30 min/°C | 6 |
| `solar_max_minutes` | `number` 0–120 | 45 |
| `safety_margin_minutes` | `number` 0–60 | 20 |
| `lead_cap_minutes` | `number` 60–360 | 240 |
| `solar_afternoon_only` | `boolean` | true |

### Group 5 — Behaviour (2)

| Input | Selector | Default |
|---|---|---|
| `sensor_strategy` | `select` (`max` / `average`) | `max` |
| `enable_fan_control` | `boolean` | true |

### Group 6 — Global Controls (2)

| Input | Selector | Default |
|---|---|---|
| `vacation_toggle` | `entity` domain `input_boolean`, multiple | `[]` |
| `enable_notifications` | `boolean` | true |

## Triggers

```
mode: restart
max_exceeded: silent
```

| ID | Type | Purpose |
|---|---|---|
| `periodic` | `time_pattern` every 1 min | Main loop — phase derivation, prediction, transitions |
| `vacation_change` | `state` on `vacation_toggle` | Instant disable / re-enable |
| `ha_start` | `homeassistant` start event | Reconcile phase after a restart |

No motion or per-time triggers — the 1-minute tick catches every transition with enough
precision for the dynamic turn-on time and the 10-minute deep-night window
(`bathroom_heating_rack` pattern).

## Action Structure

Sequential steps; all variables computed inside `action:` so HA generates traces on any
template failure (`bathroom_ventilator` / `bathroom_heating_rack` convention).

1. **Mute sound switch** — standalone `choose`, if `ac_sound_switch` configured and on.
2. **Compute variables** — includes the periodic `weather.get_forecasts` fetch; derives
   phase, `warmest_bedroom`, `room_humidity`, `ΔT_*`, `solar_load`, `lead`, `turn_on`,
   `precool_substate`, `cooling_needed`, `maintaining_setpoint`, desired mode/setpoint/fan.
3. **Runtime validation** — bad config (`drive_setpoint >= ideal_temp`, negative
   `hall_offset`, `bedtime` == `wake_time`) → persistent notification + `stop`.
4. **Vacation override** — `vacation_active` → AC off, `stop`. Placed before sensor
   validation: turning the AC off does not depend on bedroom-sensor health.
5. **Sensor validation** — no valid bedroom temp sensor, or AC entity unavailable →
   persistent notification + `stop`.
6. **Phase dispatch `choose`** — exactly one of the 6 phases acts. NIGHT-HOLD and
   DEEP-HOLD are deliberately **empty branches** (zero service calls).
7. **Debug notification** — manual-run only; full variable dump.

### Idempotency — a correctness requirement

Every climate service call is guarded by a current-vs-desired comparison; a call fires
only on a real delta:

```
if current_hvac_mode != desired_mode               → climate.set_hvac_mode
if abs(current_setpoint − desired_setpoint) > 0.1  → climate.set_temperature
if enable_fan_control and current_fan != desired_fan  → climate.set_fan_mode
```

In this blueprint a stray redundant command is a stray **beep** in the quiet window.
Idempotency is therefore a correctness invariant, not a performance optimisation — it is
what makes NIGHT-HOLD / DEEP-HOLD truly silent and the PRECOOL→LOCK→HOLD path
beep-minimal.

## Computed Variables (key)

| Variable | Logic |
|---|---|
| `warmest_bedroom` | Aggregate `bedroom_temp_sensors` per `sensor_strategy`; skip unavailable |
| `room_humidity` | Max across available `bedroom_humidity_sensors`; none → dry disabled |
| `outdoor_now` | Live reading of `outdoor_temp_sensor` |
| `forecast_max` | Max forecast temp over `now → bedtime` from `weather.get_forecasts`; fallback to `outdoor_now` |
| `solar_load` | 0..1 from `sun.sun` elevation/azimuth; `solar_afternoon_only` gate |
| `lead` | Lead-time formula, clamped |
| `turn_on` | `bedtime − lead` |
| `phase` | Derived from `now` vs the phase boundaries (overnight-wrap aware) |
| `precool_substate` | `DRIVE` / `HOLD` from `warmest_bedroom` vs `ideal_temp` |
| `cooling_needed` | The cool-day skip gate (DAY-OFF only) |
| `maintaining_setpoint` | `ideal_temp − hall_offset` |
| `desired_mode` / `desired_setpoint` / `desired_fan` | Phase + sub-state outputs, clamped to the AC's `min_temp`/`max_temp` |
| `vacation_active` | Any `vacation_toggle` entity is `on` |

## Error Handling & Edge Cases

| Scenario | Behaviour |
|---|---|
| Some bedroom temp sensors unavailable | Aggregate the remaining valid ones |
| All bedroom temp sensors unavailable | Hold state + persistent notification; quiet phases issue nothing regardless |
| AC `climate` entity unavailable | Skip tick, retry next minute, idempotent persistent notification |
| Forecast unavailable | Fall back to daily forecast, then to live `outdoor_temp_sensor` |
| Outdoor sensor and forecast both unavailable | `ΔT_out` → 0; prediction leans on indoor + solar; persistent notification |
| `sun.sun` unavailable | `solar_load` → 0 (guarded; `sun.sun` is effectively always present) |
| `drive_setpoint` / `maintaining_setpoint` below the AC's `min_temp` | Clamp to `state_attr(ac_climate,'min_temp')` at runtime |
| HA restart mid-cycle | `ha_start` + stateless phase derivation; quiet phases issue nothing → no spurious beep |
| Human changes the AC during the quiet window | Blueprint issues nothing in NIGHT/DEEP-HOLD — the human wins; it reasserts at the next phase boundary |
| Misconfiguration | Runtime validation step → persistent notification, skip cycle |
| Heatwave — `lead_cap` reached | Start at the cap, coast toward ideal; debug notification flags the projected miss |
| Bedroom doors closed | Documented operating assumption — not detectable without contact sensors |
| Vacation toggled on | AC off immediately; toggled off → resumes on next tick |

## Testing Approach

- **Manual-run debug notification** — full state dump: phase, `warmest_bedroom`,
  `room_humidity`, `ΔT_in`/`ΔT_out`, `solar_load`, `forecast_max`, `lead`, `turn_on`,
  `precool_substate`, `maintaining_setpoint`, mode/setpoint/fan decision, idempotency
  decisions. Matches `nightlight` / ventilator / heating-rack convention.
- **Time-manipulation** — set `bedtime` to `now + few min` to watch
  PRECOOL → LOCK → HOLD; set `deep_night_check` soon to exercise the correction window.
- **Mental-simulation checklist** (for the `blueprint-architect` agent's state-machine
  traversal during implementation validation):
  - [ ] Cool day (forecast peak < `skip_threshold`) → `cooling_needed` false, AC never starts, night fully no-op
  - [ ] Warm day → lead computed, turn-on mid-afternoon, room hits 19 °C by bedtime
  - [ ] Hot day, PRECOOL unfinished at bedtime → locks `maintaining_setpoint`, coasts down
  - [ ] Heatwave → `lead_cap` hit, projected-miss notification
  - [ ] Restart in each of the 6 phases → correct reconciliation, no spurious beep
  - [ ] Deep-night drift warm → one corrective command; overcooled → one command; in-band → none
  - [ ] Deep-night drift *after* the 10-min window → no command
  - [ ] Deep-night check with AC off (cool-day night) → no command
  - [ ] Vacation on at any phase → AC off
  - [ ] Forecast unavailable → outdoor-sensor fallback
  - [ ] Humidity > threshold, small `ΔT_in` → dry mode; large `ΔT_in` → cool mode
- **On-unit testing** — `dry`-mode behaviour and `hall_offset` calibration genuinely
  need a few real nights of observation; this cannot be fully validated by simulation.

## Blueprint Metadata

```yaml
blueprint:
  name: "Bedroom Sleep Pre-Cool v1.0.0"
  description: >
    Predictive pre-cooling of bedrooms via a single hall LG AC. Reaches an ideal sleep
    temperature by bedtime, then holds quietly overnight within a strict beep budget.
  domain: automation
mode: restart
max_exceeded: silent
```

## Conventions (from existing repo blueprints)

- Variables computed inside `action:` for HA trace visibility — `bathroom_ventilator`.
- Priority/phase `choose` dispatch — `bathroom_routine`, `lg_ac_climate`.
- Idempotent service calls — here a correctness invariant.
- Stateless re-evaluation on every tick — `bathroom_heating_rack`.
- Manual-run debug notification + deterministic `notification_id`s — `nightlight`, ventilator.
- `mode: restart`, `max_exceeded: silent` — `lg_ac_climate`, heating rack.
- Semantic version in the blueprint name.
- LG fan modes: discover via `state_attr(ac_climate,'fan_modes')` and map high/normal —
  `lg_ac_climate` (LG ThinQ typically exposes capitalised `"Low"`/`"Mid"`/`"High"`).

## Research-Validate Targets

Flagged for the Stack A research-validate phase (run after this spec is approved). The
user explicitly asked for thorough research:

1. **Lead-time formula** — structure and coefficients (`base_minutes`, `k_indoor`,
   `k_outdoor`, `safety_margin`, `lead_cap`) against HA-community predictive-precool
   patterns and basic building-thermal (RC) heuristics. Is a linear sum adequate, or is
   an exponential-approach term warranted?
2. **Solar-gain model** — the `solar_load` elevation/azimuth curve for west-room evening
   load; whether `sun.sun` alone suffices or a solar-radiation/lux sensor is worth it.
3. **LG `dry`-mode behaviour** — does it honour a target temperature? how does the LG
   ThinQ `climate` entity expose it? (also a triple-check live-probe item).
4. **`weather.get_forecasts` shape** — response structure and hourly-vs-daily support
   across NL weather integrations (Buienradar / KNMI / Met.no) (triple-check live-probe).
5. **`hall_offset` magnitude** — realistic hall→bedroom offset for indirect cooling, to
   set a sane default.

## Deferred / V2

- Per-day or weekday/weekend `bedtime` / `wake_time`.
- Mobile push notifications (`notify_targets` fan-out — `bathroom_heating_rack` v1.1.0 pattern).
- Auto-learned `hall_offset` from observed overnight drift.
- Window/door contact sensors to detect unreachable rooms.
- Self-learning / adaptive prediction coefficients.
- **ESPHome silent mode** — once the wired controller is installed, commands are silent;
  the beep budget becomes a non-constraint and the AC can track temperature all night.
