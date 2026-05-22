# Bedroom Sleep Pre-Cool Blueprint — Design Spec

**Date:** 2026-05-22 (revised post-research-validate)
**Version:** v1.0.0
**Blueprint file:** `bedroom_precool.yaml`
**Approach:** New standalone blueprint — single instance for one hall AC cooling multiple bedrooms indirectly
**Tracking:** Epic #1 → session #2 (Blueprints_Home)
**Validated by:** `docs/superpowers/research/2026-05-22-bedroom-precool-research-validation.md` — verdict **PROCEED**
**Requires:** Home Assistant Core **≥ 2025.7** (LG ThinQ `set_temperature` fix, PR #147008)

---

## Overview

A Home Assistant blueprint that drives a single LG air conditioner — located in the
upstairs hall — to bring the **bedrooms** to an ideal sleep temperature (default 19 °C)
by a fixed bedtime (default 19:30), then holds the room quietly overnight while issuing
the absolute minimum number of commands.

The constraint that shapes the entire design: LG ACs **beep on every command** received
over ThinQ or IR (a firmware confirmation tone that cannot be silenced in software —
research-confirmed, see `guides/lg_ac_disable_beep.md`). The blueprint therefore treats AC
commands as a scarce resource after bedtime: it adjusts freely *before* bedtime, locks a
maintaining setpoint *at* bedtime, permits at most one corrective command at a deep-night
checkpoint (~01:00), and turns the AC off at wake (~07:15).

The AC is **not in the bedrooms** — it cools the hall and cold air migrates through open
doors. This makes cooling indirect, laggy, and load-dependent, which is why the turn-on
time must be *predicted* from outdoor temperature, weather forecast, and solar gain. The
prediction is a transparent linear lead-time formula plus a **self-learning bias** that
auto-corrects from each night's observed outcome — so the predictor improves itself rather
than relying on hand-tuned coefficients forever.

Humidity-aware `dry` mode is included but **opt-in (default off)**: research found LG
`dry`-mode target-temperature behaviour unreliable and model-dependent, so `cool` is the
proven V1 path and `dry` is enabled only after on-unit testing.

This blueprint is beep-safe by design for the current ThinQ setup. When the household
later adopts the ESPHome wired controller (silent commands), the beep budget becomes a
non-constraint; a "silent mode" is noted as a V2 enhancement.

## Requirements Summary

- One LG AC in the hall, cooling 2+ bedrooms via open doors (indirect cooling).
- Control variable = the **bedrooms** (Aqara temp sensors in the rooms), aggregated.
- Reach `ideal_temp` (default 19 °C) in the warmest bedroom by `bedtime` (default 19:30).
- **Beep budget:** unlimited commands before bedtime; after bedtime, at most one
  corrective command at `deep_night_check` (~01:00); AC off at `wake_time` (~07:15).
- **Predict** the turn-on time from indoor gap + hourly forecast + solar gain, with a
  **self-learning lead-time bias** that corrects from each night's result.
- Humidity-aware `dry` mode — opt-in, default off.
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
| Aqara bedroom humidity sensors | Drives cool-vs-dry mode (only when `enable_dry_mode`) | `bedroom_humidity_sensors` (multiple, optional) |
| Outdoor temperature sensor | Heat-load term; forecast fallback | `outdoor_temp_sensor` |
| Weather entity (**hourly forecast**) | Anticipatory prediction — Met.no or Open-Meteo (**not Buienradar — no hourly**) | `weather_entity` |
| `sun.sun` (built-in) | Solar-gain term — no hardware needed | `sun_entity` (default `sun.sun`) |
| `input_number` helper | Persists the self-learned lead-time bias across restarts | `lead_bias_helper` |
| LG AC sound `switch` (optional) | Kept muted (matches `lg_ac_climate`) | `ac_sound_switch` (multiple, optional) |
| `input_boolean` (optional) | Vacation / full-off | `vacation_toggle` (multiple, optional) |

**Operating assumption (V1):** bedroom doors are open during the pre-cool window. With no
door/window contact sensors (deliberately out of scope), a closed door means that room
will not cool and the blueprint cannot detect it. Documented, not guarded.

**Indirect-cooling note (research):** HVAC consensus is that room-to-room cooling through a
doorway is thermally weak — the hall must run materially colder than the bedroom target.
The closed-loop pre-cool discovers how hard to drive; `hall_offset` (default 3 °C, range
0–10 °C) is the configurable hold offset. On the hottest days the AC's `min_temp` may cap
how cold the hall can go, so bedrooms may not reach 19 °C — the heatwave-degradation path
and the auto-learn bias both absorb this.

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
 │                       │ (DRIVE/HOLD) │+   │ nothing      │      │ nothing       │
 │                       │              │learn│             │      │               │
 └───────────────────────┴──────────────┴────┴──────────────┴──────┴───────────────┘
```

| Phase | Window | AC behaviour | Beeps |
|---|---|---|---|
| **DAY-OFF** | `wake_time` → `turn_on` | Ensure AC off (one `off` command fires at wake via idempotency). Recompute `turn_on` each tick. | 0 (1 at wake transition) |
| **PRECOOL** | `turn_on` → `bedtime − 1 min` | AC cooling; closed-loop on warmest bedroom; DRIVE / HOLD sub-states. Adjust freely. | many (allowed) |
| **BEDTIME-LOCK** | `bedtime − 1 min` → `bedtime` | If AC running: one deliberate command — set `maintaining_setpoint` + locked mode. Also runs the auto-learn update (beep-free helper write). If AC off (cool day): no-op. | 0–1 |
| **NIGHT-HOLD** | `bedtime` → `deep_night_check` | AC holds locked setpoint; blueprint issues *nothing*. | 0 |
| **DEEP-NIGHT-CHECK** | `deep_night_check` → `+10 min` | If AC running and the warmest bedroom drifted outside `ideal ± tolerance`: one corrective command. AC off, or in-band: nothing. | 0 or 1 |
| **DEEP-HOLD** | `deep_night_check + 10 min` → `wake_time` | AC holds; blueprint issues *nothing*, regardless of drift — enforces the "once" rule. | 0 |

**Beep budget after bedtime: 0–2** — a cool-day no-op night is 0; a cooling night is the
deep-night check (0–1) plus the wake-off (1). The bedtime lock fires 1 minute early so it
is unambiguously inside the beeps-allowed window. The 1-minute window means exactly one
periodic tick lands in BEDTIME-LOCK, which is what keeps the auto-learn helper write
single-shot — a 2-minute window would land two ticks and double-apply the read-modify-write
correction. A restart inside that minute re-applies the write once, but the result is
bounded by the [−60, 120] bias clamp.

**Turn-on is a one-way latch.** Once `now ≥ turn_on` and PRECOOL begins, the blueprint does
not revert to DAY-OFF for the rest of the day even if a recomputed `lead` would move
`turn_on` later — `lead` is used only to *start* cooling, never to stop it. This prevents
sensor-jitter flapping (research anti-pattern).

**Cool-day / AC-off nights:** if `cooling_needed` stayed `false` all day and the AC was
never started, BEDTIME-LOCK and all night phases are no-ops — the AC remains off until the
next DAY-OFF. The night phases and the deep-night correction only act on an already-running
AC (`current_hvac_mode != 'off'`); the blueprint never *starts* cooling after bedtime.

Two constants are fixed in code rather than exposed as inputs: bedtime-lock lead (`1 min`)
and the deep-night check window (`10 min`).

## Prediction Model

### Cooling-needed gate (cool-day skip)

Evaluated every tick during DAY-OFF, before any lead-time math:

```
cooling_needed =  warmest_bedroom > ideal_temp
               OR forecast_max > skip_threshold
```

If `false`, the blueprint stays in DAY-OFF and the AC never starts — the 17 °C-day case.
Continuous re-evaluation means a day that starts mild but heats up flips this `true`
mid-afternoon. The gate is consulted during DAY-OFF only.

### Lead-time formula

Recomputed every tick during DAY-OFF:

```
warmest_bedroom = aggregate(bedroom_temp_sensors, sensor_strategy)   # default: max
ΔT_in        = max(0, warmest_bedroom − ideal_temp)
forecast_max = max forecast temp over [now → bedtime]   # fallback: live outdoor sensor
outdoor      = max(forecast_max, outdoor_now)            # most conservative
ΔT_out       = max(0, outdoor − ideal_temp)
solar        = solar_load(sun elevation, azimuth)        # 0..1; see below
lead_bias    = self-learned correction, minutes (see Auto-Learn)

lead =  base_minutes
      + k_indoor          * ΔT_in
      + k_outdoor         * ΔT_out
      + solar_max_minutes * solar
      + safety_margin_minutes
      + lead_bias
lead =  clamp(lead, 0, lead_cap_minutes)

turn_on = bedtime − lead          →  enter PRECOOL when now >= turn_on
```

The formula structure (transparent linear indoor+outdoor blend) is research-validated as a
mainstream HA pattern. Coefficients are **calibration starting points**, not claims of
accuracy — `k_outdoor` is deliberately small (a secondary heat-leak correction, not a
co-equal term). The `lead_bias` term and the debug notification converge the prediction
over the first week of use. Asymmetric cost — early is cheap, late misses bedtime — so
`safety_margin_minutes` biases the estimate early.

### Solar-gain factor

`solar_load` is a 0..1 factor derived from `sun.sun` `elevation` and `azimuth`:
- `0` when the sun is below the horizon.
- Rises with the radiant load on the house. West-facing bedrooms bake under low evening
  sun (NL daylight to ~22:00 in June), so the factor is **high for an up sun in the
  afternoon/evening** (azimuth roughly 180–300°), not just for a high sun.
- `solar_afternoon_only` (default `true`) restricts the contribution to post-solar-noon
  azimuths. The azimuth-window pattern is research-validated (HA sun-protection blueprints).

### Forecast handling

The hourly forecast is fetched via the `weather.get_forecasts` action (plural — the
singular `weather.get_forecast` is deprecated) into a response variable, then templated to
derive `forecast_max` (max temp over `now → bedtime`), used by both the lead-time formula
and the cooling-needed gate.

The `weather_entity` **must support an hourly forecast**: Met.no (HA default, keyless) or
Open-Meteo. **Buienradar does not provide an hourly forecast** (research-verified) — it may
serve `outdoor_temp_sensor` (current temp / irradiance) but not `weather_entity`.

To limit load on the weather integration, the forecast is refreshed periodically during
DAY-OFF (≈ every 15 min, not every tick); between refreshes the prediction uses the live
`outdoor_temp_sensor`. If the entity has no hourly forecast, fall back to its daily high;
if forecast is entirely unavailable, fall back to the live outdoor sensor.

### Auto-learn — self-correcting lead-time bias

Research finding: static-coefficient predictors get abandoned; a predictor that corrects
from its own error is the load-bearing feature. V1 therefore self-learns **one** scalar:

```
lead_bias = states(lead_bias_helper) | float(0)        # read every tick if enable_auto_learn

# updated once per cooling night, at the BEDTIME-LOCK phase:
bedtime_error = warmest_bedroom − ideal_temp           # >0 too warm, <0 overcooled
new_bias      = clamp(lead_bias + learn_gain * bedtime_error * k_indoor, -60, 120)
→ input_number.set_value(lead_bias_helper, new_bias)   # beep-free (HA helper, not the AC)
```

- One persisted scalar in a user-created `input_number` helper (the blueprint is stateless;
  the helper survives restarts).
- Room too warm at bedtime → bias rises (start earlier tomorrow); overcooled → bias falls.
- Updated only on a cooling night (AC was running at bedtime); cool-day no-ops are skipped.
- Transparent and debuggable — one number the user can see, graph, and reset; the debug
  notification shows it and the last `bedtime_error`. Converges over ~3–6 nights.
- A single glitchy-but-valid bedroom reading at the bedtime lock skews that one night's
  `new_bias` write, but the `clamp(…, -60, 120)` bounds how far one outlier can move the
  bias and subsequent nights wash it out.
- `hall_offset` is **not** auto-learned in V1 (manual input, tuned via the 1 am check +
  debug notification) — auto-learning it is a documented V2 fast-follow.

## Control Logic

### Closed-loop pre-cool (DRIVE / HOLD)

PRECOOL has two sub-states, switching freely (beeps allowed):

| Sub-state | Condition | Action |
|---|---|---|
| **DRIVE** | warmest bedroom `> ideal_temp` | hall setpoint = `effective_drive`, fan high |
| **HOLD** | warmest bedroom `<= ideal_temp` | hall setpoint = `maintaining_setpoint`, normal fan |

- `effective_drive = max(drive_setpoint, ac_min_temp)` — the most aggressive setpoint the
  AC allows. Set `drive_setpoint` to the AC's minimum for the fastest pre-cool.
- `maintaining_setpoint = max(ideal_temp − hall_offset, ac_min_temp)`. The `hall_offset`
  (default 3 °C, range 0–10 °C) is the configurable answer to indirect cooling. The debug
  notification reports overnight bedroom drift so it can be tuned.
- `ac_min_temp = state_attr(ac_climate, 'min_temp')` — all setpoints clamped to it.

The closed loop on the bedroom sensors auto-discovers how hard to push for the *drive*
phase; the user does not measure the offset.

### Bedtime lock

At `bedtime − 1 min`, if the AC is running, the blueprint sends one command setting
`maintaining_setpoint` and the locked mode. **It always locks `maintaining_setpoint`**,
even if PRECOOL did not finish — on a hot-day miss the rooms coast down toward ideal over
the following hour or two, zero extra beeps. The auto-learn update also runs here. If the
AC is off (cool-day no-op), the bedtime lock does nothing. The lock window is exactly
1 minute so that only one periodic tick lands in BEDTIME-LOCK — this is what keeps the
read-modify-write auto-learn correction single-shot rather than double-applied; a restart
within that minute re-applies it once but stays bounded by the [−60, 120] bias clamp.

### Cool vs dry mode

Mode is chosen **only while beeps are free** (during PRECOOL and at the bedtime lock) and
never switched during the quiet window.

```
if not enable_dry_mode                           → cool   # V1 default path
elif warmest_bedroom > ideal_temp + tolerance    → cool   # real gap: hitting 19 °C wins
elif room_humidity > humidity_threshold          → dry
else                                             → cool
```

`enable_dry_mode` defaults **off** (research: LG `dry`-mode setpoint behaviour is
model-dependent and unreliable; `cool` is the proven path). When off, `dry` is never
selected and `bedroom_humidity_sensors` is unused. When on, `room_humidity` = max across
available humidity sensors. `dry` is selected only if the AC advertises `dry` in its
discovered `hvac_modes` — otherwise the choice falls through to `cool`. Enable `dry` only
after verifying on the actual unit that it honours a target temperature. When `dry` is
used, the blueprint guards the setpoint read against `null` (LG returns `null` setpoints
in some non-`cool` modes).

### Deep-night correction

In the `DEEP-NIGHT-CHECK` window (`deep_night_check` → `+10 min`):

```
# precondition: AC is running (current_hvac_mode != 'off'); if off, skip
drift = warmest_bedroom − ideal_temp
# the corrective target is keyed off the STABLE maintaining_setpoint,
# never the moving current_setpoint:
if drift >  tolerance   → one command: setpoint = maintaining_setpoint − correction_step  # too warm
if drift < -tolerance   → one command: setpoint = maintaining_setpoint + correction_step  # overcooled
else                    → nothing
# all targets clamped to ac_min_temp / ac_max_temp
```

Defaults: `tolerance` ±1.5 °C, `correction_step` 1.5 °C. The periodic trigger runs this
branch ~10 times across the 10-minute window. The corrective target is computed from the
**stable `maintaining_setpoint`** — `maintaining_setpoint ∓ correction_step` — *not* the
live `current_setpoint`: a target keyed off the moving `current_setpoint` would ratchet the
setpoint by `correction_step` on every one of those ticks, blowing the beep budget.
Because `maintaining_setpoint` is deterministic on every tick, the idempotency guard plus
the 10-minute window hard-guarantee at most one beep. After the window, DEEP-HOLD issues
nothing.

## Inputs

~32 inputs in 6 groups. Most have sensible defaults; a minimal setup configures the entity
selectors in Group 1.

### Group 1 — Devices & Sensors (8)

| Input | Selector | Default |
|---|---|---|
| `ac_climate` | `entity` domain `climate` | required |
| `bedroom_temp_sensors` | `entity` domain `sensor`, device_class `temperature`, multiple | required |
| `bedroom_humidity_sensors` | `entity` domain `sensor`, device_class `humidity`, multiple | `[]` (used only if `enable_dry_mode`) |
| `outdoor_temp_sensor` | `entity` domain `sensor`, device_class `temperature` | required |
| `weather_entity` | `entity` domain `weather` (must support hourly forecast) | required |
| `sun_entity` | `entity` domain `sun` | `sun.sun` |
| `lead_bias_helper` | `entity` domain `input_number` | required if `enable_auto_learn` |
| `ac_sound_switch` | `entity` domain `switch`, multiple | `[]` |

### Group 2 — Target Temperatures (7)

| Input | Selector | Default |
|---|---|---|
| `ideal_temp` | `number` 16–25 °C, step 0.5 | 19.0 |
| `hall_offset` | `number` 0–10 °C, step 0.5 | 3.0 |
| `drive_setpoint` | `number` 14–22 °C, step 0.5 (clamped to `ac_min_temp`) | 16.0 |
| `tolerance` | `number` 0.5–4 °C, step 0.5 | 1.5 |
| `correction_step` | `number` 0.5–4 °C, step 0.5 | 1.5 |
| `skip_threshold` | `number` 16–28 °C, step 0.5 | 22.0 |
| `humidity_threshold` | `number` 40–80 %, step 1 | 65 |

`ideal_temp` minimum is 16 °C — a child-safety floor (see Safety Notes).

### Group 3 — Schedule (3)

| Input | Selector | Default |
|---|---|---|
| `bedtime` | `time` | 19:30 |
| `wake_time` | `time` | 07:15 |
| `deep_night_check` | `time` | 01:00 |

### Group 4 — Prediction Tuning (8)

| Input | Selector | Default |
|---|---|---|
| `base_minutes` | `number` 0–120 | 20 |
| `k_indoor` | `number` 0–60 min/°C | 15 |
| `k_outdoor` | `number` 0–15 min/°C | 1.0 |
| `solar_max_minutes` | `number` 0–120 | 45 |
| `safety_margin_minutes` | `number` 0–60 | 25 |
| `lead_cap_minutes` | `number` 60–360 | 240 |
| `solar_afternoon_only` | `boolean` | true |
| `learn_gain` | `number` 0–1, step 0.05 | 0.4 |

### Group 5 — Behaviour (4)

| Input | Selector | Default |
|---|---|---|
| `sensor_strategy` | `select` (`max` / `average`) | `max` |
| `enable_fan_control` | `boolean` | true |
| `enable_dry_mode` | `boolean` | false |
| `enable_auto_learn` | `boolean` | true |

### Group 6 — Global Controls (2)

| Input | Selector | Default |
|---|---|---|
| `vacation_toggle` | `entity` domain `input_boolean`, multiple | `[]` |
| `enable_notifications` | `boolean` | true |

Two fiddly constants are fixed in code: bedtime-lock lead (1 min), deep-night check window
(10 min).

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

No motion or per-time triggers — the 1-minute tick catches every transition.

## Action Structure

Sequential steps; all variables computed inside `action:` so HA generates traces on
template failure.

1. **Mute sound switch** — standalone `choose`, if `ac_sound_switch` configured and on.
2. **Compute variables** — includes the periodic `weather.get_forecasts` fetch; derives
   phase, `warmest_bedroom`, `room_humidity`, `ΔT_*`, `solar_load`, `lead_bias`, `lead`,
   `turn_on`, `precool_substate`, `cooling_needed`, `ac_min_temp`, `maintaining_setpoint`,
   desired mode/setpoint/fan.
3. **Runtime validation** — bad config (`drive_setpoint >= ideal_temp`, negative
   `hall_offset`, `bedtime == wake_time`, `wake_time` not before `bedtime`,
   `deep_night_check` not before `wake_time`) → persistent notification + `stop`.
4. **Vacation override** — `vacation_active` → AC off, `stop`. Before sensor validation:
   turning the AC off does not depend on bedroom-sensor health.
5. **Sensor validation** — no valid bedroom temp sensor, or AC entity unavailable →
   persistent notification + `stop`.
6. **Phase dispatch `choose`** — exactly one of the 6 phases acts. NIGHT-HOLD and
   DEEP-HOLD are deliberately **empty branches**. BEDTIME-LOCK additionally performs the
   auto-learn helper write. The whole 6-branch dispatch runs **only on a real trigger**
   (`periodic` / `vacation_change` / `ha_start`): a manual "Run" has no `trigger.id`, so
   it computes every variable and emits the debug dump but actuates nothing — a manual
   Run is debug-inspect-only and cannot double-apply the BEDTIME-LOCK auto-learn write.
7. **Debug notification** — manual-run only; full variable dump including `lead_bias`.

### LG service-call discipline (research)

- Set HVAC **mode** and **temperature** as **two sequenced calls** (mode first, then
  temperature) — the combined single call was unreliable on LG ThinQ before HA 2025.7.
- Set mode only while the unit is already running — `set_hvac_mode` fails with "command not
  supported in POWER OFF" on a powered-off unit. Mode is therefore established during
  PRECOOL, when the unit is on and beeps are free.
- Guard every setpoint read (`state_attr(ac_climate,'temperature')`) against `null`.
- Discover `fan_modes` / `hvac_modes` / `min_temp` from entity attributes — never hard-code.

### Idempotency — a correctness requirement

Every climate service call is guarded by a current-vs-desired comparison; a call fires only
on a real delta:

```
if current_hvac_mode != desired_mode               → climate.set_hvac_mode
if abs(current_setpoint − desired_setpoint) > 0.1  → climate.set_temperature
if enable_fan_control and current_fan != desired_fan  → climate.set_fan_mode
```

A stray redundant command is a stray **beep** in the quiet window. Idempotency is a
correctness invariant — it is what makes NIGHT-HOLD / DEEP-HOLD truly silent.

## Computed Variables (key)

| Variable | Logic |
|---|---|
| `warmest_bedroom` | Aggregate `bedroom_temp_sensors` per `sensor_strategy`; skip unavailable |
| `room_humidity` | Max across available `bedroom_humidity_sensors` (only if `enable_dry_mode`) |
| `outdoor_now` | Live reading of `outdoor_temp_sensor` |
| `forecast_max` | Max forecast temp over `now → bedtime`; fallback to `outdoor_now` |
| `solar_load` | 0..1 from `sun.sun` elevation/azimuth; `solar_afternoon_only` gate |
| `ac_min_temp` | `state_attr(ac_climate, 'min_temp')` — clamps all setpoints |
| `lead_bias` | `states(lead_bias_helper) \| float(0)` if `enable_auto_learn`, else 0 |
| `lead` | Lead-time formula incl. `lead_bias`, clamped |
| `turn_on` | `bedtime − lead` |
| `phase` | Derived from `now` vs the phase boundaries (overnight-wrap aware) |
| `precool_substate` | `DRIVE` / `HOLD` from `warmest_bedroom` vs `ideal_temp` |
| `cooling_needed` | The cool-day skip gate (DAY-OFF only) |
| `maintaining_setpoint` | `max(ideal_temp − hall_offset, ac_min_temp)` |
| `desired_mode` / `desired_setpoint` / `desired_fan` | Phase + sub-state outputs, clamped to `ac_min_temp`/`max_temp` |
| `vacation_active` | Any `vacation_toggle` entity is `on` |

## Error Handling & Edge Cases

| Scenario | Behaviour |
|---|---|
| Some bedroom temp sensors unavailable | Aggregate the remaining valid ones |
| All bedroom temp sensors unavailable | Hold state + persistent notification; quiet phases issue nothing regardless |
| AC `climate` entity unavailable | Skip tick, retry next minute, idempotent persistent notification |
| Forecast unavailable | Fall back to daily forecast, then to live `outdoor_temp_sensor` |
| Outdoor sensor and forecast both unavailable | `ΔT_out` → 0; prediction leans on indoor + solar + bias; persistent notification |
| `sun.sun` unavailable | `solar_load` → 0 |
| `lead_bias_helper` unavailable / unconfigured | `lead_bias` → 0; one-time persistent notification if `enable_auto_learn`; blueprint still runs |
| LG setpoint attribute is `null` (non-`cool` mode) | Guarded read; treat as "unknown", skip the idempotency delta for that tick |
| `set_hvac_mode` on a powered-off unit | Avoided by design — mode is only set during PRECOOL while the unit runs |
| Setpoint below the AC's `min_temp` | Clamp to `ac_min_temp` at runtime |
| Bedroom sensor reads < 16 °C | Overcooling fault — persistent notification (child-safety floor); the 1 am check corrects upward if in window |
| HA restart mid-cycle | `ha_start` + stateless phase derivation; quiet phases issue nothing → no spurious beep |
| Human changes the AC during the quiet window | Blueprint issues nothing in NIGHT/DEEP-HOLD — the human wins; reasserts at the next phase boundary |
| Misconfiguration | Runtime validation step → persistent notification, skip cycle |
| `wake_time` not before `bedtime` | Rejected by config validation (phase derivation assumes a daytime wake→bedtime envelope) → persistent notification, skip cycle |
| `deep_night_check` not in the small hours before `wake_time` | Rejected by config validation (phase logic assumes the deep-night check precedes wake) → persistent notification, skip cycle |
| Heatwave — `lead_cap` reached, or `ac_min_temp` too high to reach 19 °C | Start at the cap / drive at `ac_min_temp`; coast as close as possible; debug notification flags the projected miss |
| Bedroom doors closed | Documented operating assumption — not detectable without contact sensors |
| Vacation toggled on | AC off immediately; toggled off → resumes on next tick |

## Safety Notes

- **Minimum-temperature floor.** `ideal_temp` is bounded ≥ 16 °C; a bedroom sensor reading
  below 16 °C raises an overcooling fault notification. 19 °C is within the recommended
  child sleep range (research: The Lullaby Trust, 16–20 °C).
- **Airflow.** Cold air from the hall AC should not blow directly onto a child's bed — a
  placement concern the blueprint cannot see. The README must advise on AC vane direction.
- **Dry air.** Extended `cool` operation lowers humidity; the README should note this. (V2
  could add a low-humidity warning.)

## Testing Approach

- **Manual-run debug notification** — full state dump: phase, `warmest_bedroom`,
  `room_humidity`, `ΔT_in`/`ΔT_out`, `solar_load`, `forecast_max`, `lead_bias`, last
  `bedtime_error`, `lead`, `turn_on`, `precool_substate`, `maintaining_setpoint`,
  mode/setpoint/fan decision, idempotency decisions.
- **Time-manipulation** — set `bedtime` to `now + few min` to watch PRECOOL → LOCK → HOLD;
  set `deep_night_check` soon to exercise the correction window.
- **Mental-simulation checklist** (for the `blueprint-architect` agent):
  - [ ] Cool day → `cooling_needed` false, AC never starts, night fully no-op, no auto-learn update
  - [ ] Warm day → lead computed, turn-on mid-afternoon, room hits 19 °C by bedtime
  - [ ] Hot day, PRECOOL unfinished at bedtime → locks `maintaining_setpoint`, coasts down
  - [ ] Heatwave / `ac_min_temp` too high → projected-miss notification
  - [ ] Auto-learn: room warm at bedtime → `lead_bias` increases; overcooled → decreases; clamped
  - [ ] Auto-learn: `lead_bias_helper` unavailable → bias 0, blueprint still runs
  - [ ] Restart in each of the 6 phases → correct reconciliation, no spurious beep
  - [ ] Deep-night drift warm / overcooled / in-band / after-window / AC-off
  - [ ] Vacation on at any phase → AC off
  - [ ] `enable_dry_mode` off → `dry` never selected; on + humid + small ΔT → `dry`
  - [ ] Turn-on latch: recomputed later `turn_on` does not revert PRECOOL to DAY-OFF
- **On-unit testing** — `dry`-mode behaviour and `hall_offset` calibration genuinely need
  a few real nights; this cannot be fully validated by simulation.

## Blueprint Metadata

```yaml
blueprint:
  name: "Bedroom Sleep Pre-Cool v1.0.0"
  description: >
    Predictive pre-cooling of bedrooms via a single hall LG AC. Reaches an ideal sleep
    temperature by bedtime, then holds quietly overnight within a strict beep budget,
    with a self-learning lead-time prediction. Requires Home Assistant Core 2025.7+.
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
- LG fan modes: discover via `state_attr(ac_climate,'fan_modes')` — `lg_ac_climate`.

## Research-Validate Outcomes

Research-validate (Deep mode) returned **PROCEED** — see
`docs/superpowers/research/2026-05-22-bedroom-precool-research-validation.md`. Its
adjustments are folded into this revision: forecast source (Met.no/Open-Meteo, not
Buienradar), coefficient defaults (`k_outdoor` reduced), `drive_setpoint`/`hall_offset`
handling, child-safety floor, LG service-call discipline, `dry` mode opt-in, and the V1
auto-learn bias. Items that genuinely need **on-unit testing** (not desk research):
LG `dry`-mode target-temperature behaviour; the realistic `hall_offset` magnitude.

## Deferred / V2

- Auto-learned `hall_offset` from observed overnight drift (V1 auto-learns lead-time only).
- Per-day or weekday/weekend `bedtime` / `wake_time`.
- Mobile push notifications (`notify_targets` fan-out — `bathroom_heating_rack` v1.1.0).
- Window/door contact sensors to detect unreachable rooms.
- Low-humidity (dry-air) warning.
- **ESPHome silent mode** — once the wired controller is installed, commands are silent;
  the beep budget becomes a non-constraint and the AC can track temperature all night.
