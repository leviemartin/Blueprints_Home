# LG AC Climate Control v1.1.0 — Design Spec

**Date:** 2026-08-09
**Version:** v1.1.0 (delta against v1.0.0 — see `2026-03-19-lg-ac-climate-control-design.md`)
**Blueprint file:** `lg_ac_climate.yaml`
**Driver:** 2026-08-09 audit (9 findings) + LG beep research (no API-level beep disable exists for
LG split units; command-frequency reduction is the only software lever).

```
Stakes: standard
Trigger: default-up: automation logic change in lg_ac_climate.yaml, no hard trigger matched
Router: deterministic
```

**Decision log (operator-locked 2026-08-09):**
- Escalation fix = distance gate (no helper-based time-failing tracking).
- Manual hold = auto-detect via optional per-floor `input_text` helper.
- Hold scope = safety pierces (vacation / schedule-end / door still force off during a hold).
- Process = Stack B, standard stakes (2-lens board both gates, PonyTail full).
- Defaults accepted: comfort margin 0.5 °C · staleness 90 min · weather outage degrades silently ·
  no door-close trigger · no schedule-edge triggers · hold window fixed (non-extending).

---

## Goals

1. **Silence the automation** — a steady-state control tick must send zero commands (LG units beep
   on every accepted command, including API ones; v1.0.0 re-sends setpoint+fan every 10 min).
2. **Stop boundary cycling** — hysteresis so reaching the comfort bound doesn't flip off/on.
3. **Fail safe** — weather outage and silently-stale sensors must not steer the AC wrongly.
4. **Respect humans** — a manual remote/app change holds for a configurable window instead of
   being reverted (with a beep) within 10 minutes.
5. Exact-time door shut-off, instant vacation resume, correct overnight windows, self-clearing
   notifications.

## New inputs (all defaulted; existing instances work unreconfigured)

| Input | Selector | Default | Item |
|---|---|---|---|
| `comfort_margin` | number 0.0–2.0 °C, step 0.1 | 0.5 | 4 |
| `sensor_staleness_minutes` | number 15–1440 min, step 5 | 90 | 5 |
| `manual_hold_helper` | entity (domain: `input_text`), optional | unset → feature off | 9 |
| `manual_hold_minutes` | number 15–360 min, step 5 | 60 | 9 |

## The nine changes

### 1. Idempotence guards (beep elimination)

Each acting branch (maintenance / cool / heat) computes its desired `(mode, setpoint, fan)` in
variables, then wraps **each** service call in its own `choose`:

- `set_temperature` fires iff `current_ac_mode != desired_mode` **or**
  `|state_attr(climate, 'temperature')|float − desired_setpoint| > 0.05`.
- `set_fan_mode` fires iff `state_attr(climate, 'fan_mode') != desired_fan`.

Per-call `choose`, never sequence-level `condition:` — a skipped setpoint must not abort a needed
fan change. The off-branches keep their existing `current_ac_mode != 'off'` guards.

**Acceptance:** a tick where live state already equals desired issues zero `climate.*` calls.

### 2. Weather-outage safe default

`outdoor_temp_raw = state_attr(weather, 'temperature')`. If `none`/non-numeric → `weather_ok:
false` → `deadband_active` forced `true` (normal cycling — never maintenance mode on missing
data). Silent degradation: no notification (weather blips are frequent and self-heal; behavior
stays safe). `outdoor_temp`/`outdoor_distance` are only consulted when `weather_ok`.

**Acceptance:** weather entity unavailable + room in range → AC turns off (deadband path), never
holds maintenance.

### 3. Escalation distance gate

`target_fan` applies the time ladder **only** when `distance_from_target ≥ fan_low_threshold`;
below that it is always `base_fan`. Known residual (accepted): after hours in one hvac mode, a
new ≥-threshold excursion starts escalated rather than working up from low.

**Acceptance:** distance 0.4 °C with 3 h in-mode → fan = low (v1.0.0: max).

### 4. Hysteresis (`comfort_margin`)

```
target_mode :=
  cool                          if temp > high
  heat                          if temp < low
  cool  (continue)              if current_ac_mode == 'cool' and temp > high − margin
  heat  (continue)              if current_ac_mode == 'heat' and temp < low + margin
  off                           otherwise
```

From `off`, nothing changes inside the range (no early start). While continuing, the setpoint is
unchanged (guards ⇒ no re-sends) and `distance_from_target = 0` ⇒ fan low, escalation gated.
Validation gate extended: `2 × margin < (high − low)` else config-error notification + stop.

**Acceptance:** cooling at high=24, margin=0.5: room 23.8 → still `cool`; 23.4 → `off`.
AC off, room 23.8 → stays `off`.

### 5. Sensor staleness cutoff

`valid_temps` additionally requires `(now() − states[s].last_reported) <
sensor_staleness_minutes`. `last_reported`, **not** `last_updated`: unchanged-value re-reports
must refresh liveness (Aqara heartbeats ~hourly ⇒ 90 min default avoids false stales). All
sensors stale/invalid → existing sensor-warning stop path. *(Contingency if research-validate
finds `last_reported` not template-accessible: fall back to `last_updated` and raise the default
to 180 min, documented.)*

**Acceptance:** sensor with numeric state but last report 2 h ago is excluded from aggregation.

### 6. Reactive triggers

Add:
- door state trigger `to: "on"` with `for:` = `door_off_delay` minutes (exact-time shut-off;
  the existing tick-time `door_is_open` computation is retained and stays consistent with it);
- vacation state trigger `to: "off"` (instant resume).

Deliberately not added: door-close trigger (lazy ≤10-min resume avoids off/on churn on brief
door cycles); per-day schedule-edge triggers (requirements wording updated to "within one
control tick" instead).

**Acceptance:** door opens at T, delay 5 min → `climate.turn_off` at T+5 (±trigger latency),
not T+5..15.

### 7. Cross-midnight window correctness

```
today_active     := (start ≤ end) ? (start ≤ now < end) : (now ≥ start)
yesterday_active := y_start > y_end and now < y_end
in_operating_window := today_active or yesterday_active
```

An overnight window belongs to the day it starts. This also fixes the latent v1.0.0 bug where
today's overnight window claimed *this* morning's tail (`or t_now < t_end` against today's own
end). No behavior change for start<end windows.

**Acceptance:** Sat 22:00→06:00, Sun 07:00→23:00: Sun 01:00 → in window (yesterday's tail);
Sun 06:30 → out; Sat 21:00 → out.

### 8. Notification auto-dismiss

After the validation gate passes: dismiss `ac_climate_config_error`. When `sensors_available`:
dismiss `ac_climate_sensor_warning`. (`persistent_notification.dismiss` on an absent id is
expected to be a no-op — research-validate confirms.)

### 9. Manual-override hold (auto-detect, safety pierces)

**Helper contract:** optional per-floor `input_text` storing JSON (≤255 chars, well within):

```json
{"mode": "cool", "temp": 24.0, "fan": "low", "hold_until": 0}
```

`mode/temp/fan` = last state this automation commanded ("expected"); `hold_until` = epoch
seconds, `0` = no hold. Helper unset ⇒ every hold codepath inert (like the optional door input).

**Rules:**

1. **Expected-write:** every branch that commands the AC — comfort *and* safety-off — finishes by
   writing the helper with what it commanded (off-branches: `mode: "off"`, `temp`/`fan` null).
   Writes preserve the current `hold_until` except where a rule below sets/clears it.
   Unconditional write (local helper; no beep, negligible recorder churn).
2. **Detection** (each run, after safety branches, before comfort branches; requires helper
   configured, parsed expected present, no active hold): manual ⇔ `mode ≠ expected.mode`, or —
   when expected mode ≠ off — `|setpoint − expected.temp| > 0.3` or `fan ≠ expected.fan`.
   On detection: write helper `{expected: live snapshot, hold_until: now + hold_minutes}` and
   end the run (comfort branches skipped).
3. **During hold** (`hold_until > now`): comfort branches skipped; detection skipped (a fixed,
   non-extending window — extending on the user's own further tweaks would compare against
   pre-hold expected and never release). Safety still pierces: vacation, out-of-window, and
   door-open sit **above** the hold check in the ladder and still force off (rule 1 writes apply,
   `hold_until` preserved — the hold rides out its clock).
4. **Expiry:** first run past `hold_until` resumes computed control (one beep) and rewrites
   expected.
5. **Restart guard:** on the `homeassistant: start` trigger, write `{expected: live snapshot,
   hold_until: 0}` **before** the ladder runs (STEP 2c), then continue the run — the restart
   control pass is preserved, and detection cannot fire because expected now equals live. State
   may drift legitimately during downtime; a false hold per restart would be worse than missing
   one manual change. A `hold_until` in the past is equivalent to `0` everywhere.
6. **Corrupt/empty helper JSON** → treat as no-expectation: write live snapshot, `hold_until: 0`,
   continue the run normally (no hold, no detection this tick).

**Acceptance:** (a) user bumps setpoint 24→22 on the remote → next tick detects, no revert for
60 min, revert+resume after; (b) during hold, vacation ON still turns the AC off; (c) HA restart
during a hold clears it without a false detection; (d) helper unset → byte-identical control
behavior to items 1–8 alone.

## Action-flow order (v1.1.0 ladder)

```
STEP 1  variables (extended: staleness filter · weather_ok · hysteresis target_mode ·
        gated escalation · schedule w/ yesterday-tail · hold parse/detect inputs)
STEP 2  validation gate (low<high AND 2×margin<high−low) → notify+stop on fail
STEP 2b dismiss config-error · dismiss sensor-warning (iff sensors_available)
STEP 2c restart-init → seed helper (rule 5), then continue   [only when helper configured]
STEP 3  choose ladder:
  1. sensors unavailable → notify + stop
  2. AC entity unavailable → stop
  3. vacation ON  → off (guarded) + expected-write
  4. out of window → off (guarded) + expected-write
  5. door open     → off (guarded) + expected-write
  6. manual detected → start hold (rule 2) + stop
  7. hold active     → stop
  8. in range → deadband on: off (guarded) + write │ deadband off: maintenance (guarded) + write
  9. cool / 10. heat → guarded set_temperature + guarded set_fan_mode + expected-write
```

Ladder branches 3–5 are the pierce set; 6–7 shield only 8–10. STEP 2c precedes the ladder so a
restart never reads as a manual change yet still gets its control pass.

## Degradation matrix

| Failure | v1.1.0 behavior |
|---|---|
| Weather entity unavailable | Deadband forced active (normal cycling); silent |
| Some sensors stale | Excluded from aggregation |
| All sensors stale/unavailable | Notify + hold state (existing path) |
| AC entity unavailable | Stop, retry next tick (existing path) |
| Helper JSON corrupt/empty | Re-seed from live state, no hold, control continues |
| Helper unset | Items 1–8 behavior only; hold feature inert |
| HA restart mid-hold | Hold cleared, expected re-seeded, no false detection |

## Testing

`tests/test_lg_ac_climate_structure.py` on the existing nightlight harness (yaml `!input`
loader + pytest, venv `~/projects/ceiling-fan-hue-blueprint/.venv`):

- **Input-schema pins:** the four new inputs (selector types, ranges, defaults); untouched v1.0.0
  inputs unchanged.
- **Exact-equality template pins** on load-bearing conditions: hysteresis `target_mode`,
  staleness filter (pins `last_reported`), `weather_ok`/deadband fallback, escalation gate,
  manual-detection predicate, window formula (incl. yesterday-tail term).
- **Positional whole-sequence shape pins** (kind-tagged exact lists) on the STEP-3 ladder order
  and on each acting branch's guarded-call choreography — membership asserts are vacuous for
  sequence order (kids-room lesson: positional pins are the only shape that binds YAML
  choreography).
- **Guard-presence pins:** every `climate.*` call in branches 9–11 sits inside a per-call guard;
  every commanding branch ends with an expected-write.
- Reviewers run hash-verified apply/revert mutation probes per
  `feedback_mutation_that_fails_to_apply_reads_as_survivor`.

**Live verification (operator, post-import):** one steady-state tick with zero beeps; one manual
setpoint change honored for the hold window; door-open shut-off at the exact delay.

## Docs riding along

`requirements_lg_ac_climate.md`: add the four inputs + hold semantics; fix v1.0 drift — remove
the sound-mute requirement (research: no such entity can exist for LG splits), outdoor "sensor
entity" → weather entity, window-end "immediately" → "within one control tick". Blueprint
description block: version 1.1.0 + feature bullets.

## Out of scope

Blueprint-syntax modernization (`triggers:`/`actions:` plural keys stay legacy), 
`lg_sleep_movie.yaml` (suspect trigger syntax tracked separately), LG native Sleep Mode
integration, beep hardware modification, schedule-edge time triggers, door-close trigger.

## Research-validate resolutions (2026-08-09 — PROCEED; see
`../research/2026-08-09-lg-ac-v1.1.0-research-validation.md`)

1. `states[x].last_reported`: available since HA 2024.4; unchanged-value re-reports bump it.
   Use unconditionally — the §5 fallback contingency is void.
2. `for: {minutes: !input …}`: valid on **state** triggers (schema coerces); never move the door
   trigger to a `device` trigger.
3. `entity_id: []` state trigger: valid + silently inert — but only because `door_sensor` is
   `multiple: true`. Constraint: the input stays `multiple: true`.
4. `input_text`: 255-char hard cap (JSON doc ≈80 chars, fine); rule-6 guard is
   `| from_json(default={})` — never a bare `from_json`.
5. Dismiss on absent id: no-op in practice but weakest-sourced — dismiss steps carry
   `continue_on_error: true`.
