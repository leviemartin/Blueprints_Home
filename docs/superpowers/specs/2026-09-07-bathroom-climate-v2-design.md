# Bathroom Climate v2 — Design Spec

**Date:** 2026-09-07 · **Repo:** Blueprints_Home · **Entry:** Stack B C (mid-epic feature, research-gated)
**Research verdict:** proceed — `~/AI/docs/research/2026-09-07-bathroom-ventilator-v2-research-validation.md`
**Scope:** `bathroom_ventilator.yaml` v1.0.0 → **v2.0.0** (session 1) and `bathroom_heating_rack.yaml` v1.1.1 → **v2.0.0** (session 2), plus `scripts/deploy-blueprint.sh` (session 1) and structure tests for both.

```
Stakes: standard
Trigger: default-up: automation logic change in two blueprint YAMLs + new deploy script + tests; no hard trigger matched
Router: deterministic
Entry: C
```

## 1. Why

Diagnosis 2026-09-07: the ventilator automation fired every 5 minutes but halted at its own sensor guard because the Aqara bathroom sensor died on 2026-08-01 (battery). The audit found the guard has no fail-safe, the shower detector is dead by construction (needs 5 min of continuous Hue motion; 6 such episodes in 10 days versus ~25 real presence clusters), the high-humidity branch short-cycles between 75% and 80% instead of drying to target, night showers get no ventilation, and the 3-hourly refresh cycle is obsolete now that trickle vents are installed. The heating rack sits in a setpoint window 4–5 h/day in September heating a 21–23 °C room, starts evening heat at the first staircase movement up to 90 min early, and its push target `notify.mobile_app_martin` does not exist (3,219 logged errors since 09-04).

## 2. Hardware and entities (live-verified 2026-09-07)

| Role | Entity | Facts |
|---|---|---|
| Exhaust fan | `light.on_off_plug_1` | innr On/Off plug on the Hue bridge (Hue device "Bathroom Heating", user name "Bathroom Vent"). Fan = TURBOE.125 tube fan, 230–345 m³/h (≥ 64 dm³/s ≥ Bbl 14 dm³/s), 25–29 W, 29–34 dBA. `light.heater` is the Hue ROOM group mirroring this plug (~1 s lag); the rack coordinates on the group. |
| Indoor T/RH | `sensor.temp_sensor_bathroom`, `sensor.temp_sensor_bathroom_humidity_sensor` | Aqara AS008 (T1) via Aqara Hub M2 / homekit_controller. Reports instantly on ΔRH ≥ 6% or ΔT ≥ 0.5 °C, else hourly. Offline since 08-01; battery replaced, rejoin pending. Entity ids MAY change after a reset + re-add. |
| Motion | `binary_sensor.bathroom_motion` | Hue motion sensor via bridge; clear delay is bridge-controlled. Also provides `sensor.bathroom_temperature` (rack's room sensor). |
| Weather | `weather.openweathermap` (temperature, humidity; no dew_point) · `weather.home_sm` (Met.no; has `dew_point`) | Either may be primary; the other is the fallback. |
| Rack | `climate.heatingrack_bathroom` | Tuya cloud "ECOSO WIFI Element" (category wk). DPs: switch, mode (eco), temp_set, temp_current, temp_correction. HA state is `unknown` while switch=on & mode=eco, `off` when switch=off (HA core `tuya/climate.py` `hvac_mode`). No `hvac_action`. `target_temp_step` 1.0, min 7, max 30, presets [eco]. |
| Helpers | `input_boolean.heating_rack_boost`, `input_boolean.heating_rack_vacation` (exist) · `input_boolean.bathroom_fan_boost` (NEW, created via `POST /api/config/input_boolean/config/bathroom_fan_boost`) | |
| Push | `notify.mobile_app_martin_fold` | The only target (Martin's choice). |

## 3. Ventilator v2.0.0

### 3.1 Inputs

Kept (same key, same meaning): `fan_switch` (selector domain **[light, switch, fan]**), `humidity_sensor`, `temperature_sensor`, `motion_sensor`, `weather_entity`, `target_humidity` 60, `high_humidity` 75, `mold_humidity` 85, `dew_point_delta_min` 2.0, `night_start` 22:00, `night_end` 05:30.

New:

| Key | Default | Range | Meaning |
|---|---|---|---|
| `weather_fallback` | `[]` | entity, multiple | Optional second weather entity used when the primary lacks usable data. |
| `hysteresis` | 5 | 1–15 % | Start threshold sits this far above the effective stop target. |
| `shower_rh_jump` | 6 | 3–15 % | RH rise between two consecutive sensor reports that counts as a shower signature (Aqara reports on ≥ 6%). |
| `presence_window_min` | 15 | 5–60 min | Motion within this window qualifies a shower signature. |
| `min_runtime` | 15 | 5–30 min | Every fan run lasts at least this long (ADF run-on floor is 15). |
| `max_runtime` | 45 | 15–90 min | Hard cap per run; the next tick may restart it in daytime. |
| `boost_toggle` | `[]` | input_boolean, multiple | Manual boost toggle(s); any `on` forces the fan on. |
| `boost_runtime_min` | 20 | 5–60 min | Boost auto-expires: the toggle is switched off after this long. |
| `sensor_grace_min` | 10 | 1–60 min | Sensor must be unavailable/unknown this long before degraded mode. |
| `degraded_run_min` | 20 | 5–60 min | In degraded mode the fan runs this long after the last motion. |
| `notify_targets` | `[]` | text, multiple | `notify.*` services for push (cloned from the rack convention). Entries are filtered to `^notify[.][a-z0-9_]+$` before dispatch, so a typo or a non-notify service name is dropped rather than called. |

Removed (instance migration drops them): `shower_humidity_rise`, `shower_motion_minutes`, `post_shower_min_runtime` → `min_runtime`, `post_shower_max_runtime` → `max_runtime`, `high_humidity_max_runtime` (unified into `max_runtime`), `enable_refresh_cycles`, `refresh_interval_hours`, `refresh_duration_minutes`, `refresh_skip_below`.

### 3.2 Triggers

| id | Trigger |
|---|---|
| `humidity_change` | state of `humidity_sensor`, `not_from`/`not_to` [unavailable, unknown] |
| `motion_on` | state of `motion_sensor` to `on` |
| `periodic` | time_pattern minutes `/5` |
| `ha_start` | homeassistant start |
| `sensors_lost` | state of `humidity_sensor` to [unavailable, unknown] `for: sensor_grace_min` (humidity only: both sensors are one device, two triggers would double-notify; a temperature-only loss still enters degraded mode via `sensors_ok` on the next tick, silently) |
| `sensors_back` | state of `humidity_sensor` from [unavailable, unknown], `not_to` [unavailable, unknown]; the recovery push additionally requires `sensors_ok` at that moment |
| `boost_change` | state of `boost_toggle` to [on, off] |

`mode: queued`, `max: 3`, `max_exceeded: silent`. Every run is short (no delays); timing is derived from entity `last_changed`, so a restart or a dropped trigger never strands the fan.

### 3.3 Computed variables (all inside `action:` for trace visibility)

- `sensors_ok`: both indoor sensors numeric.
- Weather selection: `w = first of [weather_entity] + weather_fallback whose state is not unavailable/unknown and that has either numeric dew_point or numeric temperature+humidity`. If none: `outdoor_dp` = 15 − 2 (conservative: treats outdoor air as drier than a 60%/22 °C room so ventilation is allowed), flagged in the debug dump.
- `outdoor_dp`: `state_attr(w,'dew_point')` when numeric, else Magnus(T_out, RH_out). `indoor_dp` = Magnus(T_in, RH_in). Magnus: a = 17.625, b = 243.04, α = aT/(b+T) + ln(RH/100), Td = bα/(a−α).
- `dp_delta = indoor_dp − outdoor_dp`.
- `rh_floor` (adaptive floor): RH at `indoor_temp` whose dew point equals `outdoor_dp + dew_point_delta_min`: `100·exp(a·Td/(b+Td) − a·T/(b+T))`, clamped to [0, 100]. Worked example: T_in 22, outdoor_dp 16, delta 2 → Td 18 → 78.1%.
- `stop_target = max(target_humidity, rh_floor)`; `start_threshold = max(high_humidity, stop_target + hysteresis)`; both capped at 100.
- `fan_is_on`, `fan_on_minutes` (from `states[fan].last_changed`), `is_night` (correct for windows that do and do not cross midnight).
- `presence_recent = motion on or (now − motion.last_changed) < presence_window_min`.
- `shower_signal = trigger.id == 'humidity_change' and to − from ≥ shower_rh_jump and presence_recent` (from/to numeric, guarded).
- `boost_active = any toggle on with age < boost_runtime_min`; `boost_expired = toggle on with age ≥ boost_runtime_min`.
- `degraded_on = motion on or (now − motion.last_changed) < degraded_run_min`.
- `mold_on = indoor_rh ≥ mold_humidity and dp_delta > 0`.

### 3.4 Decision (first match wins; result = desired fan state)

| # | Condition | Desired |
|---|---|---|
| 1 | `boost_active` | ON |
| 2 | `not sensors_ok and sensors_lost_minutes ≥ sensor_grace_min` (degraded mode) | `degraded_on` |
| 2b | `not sensors_ok` within the grace window (hold) | unchanged (`fan_is_on`) |
| 3 | `mold_on` (any hour) | ON |
| 4 | `fan_is_on and fan_on_minutes < min_runtime` | ON |
| 5 | `fan_is_on and fan_on_minutes ≥ max_runtime` | OFF |
| 6 | `shower_signal` (any hour) | ON |
| 7 | `fan_is_on and indoor_rh > stop_target` | ON |
| 8 | `not fan_is_on and indoor_rh > start_threshold and not is_night` | ON |
| 9 | otherwise | OFF |

The fan service (`homeassistant.turn_on/off`) is called only when `desired != fan_is_on`. Rule 7 keeps a night shower running until the adaptive target or the cap; rule 8 is the only rule quiet hours block. Rule 5 then rule 8 yields at most a 5-minute pause in a pathological never-dries daytime case; at night rule 5 ends the run.

### 3.5 Side effects

- `boost_expired` → `input_boolean.turn_off` on that toggle (done after the fan call so the resulting `boost_change` run sees a consistent state).
- Sensor warning is **state-driven**: every run creates `ventilator_sensor_warning` while `not sensors_ok and sensors_lost_minutes ≥ sensor_grace_min` (idempotent per id) and dismisses it while `sensors_ok`. That way an outage that is already live when v2 is deployed (the Aqara sensor today) is announced in HA even though no edge fires for it. `sensors_lost_minutes` is derived from the failing sensor's `last_changed`.
- Mobile push is **edge-driven**: `sensors_lost` trigger → one push "Bathroom humidity sensor offline for N min — fan now runs 20 min after motion"; `sensors_back` trigger with `now − trigger.from_state.last_changed ≥ sensor_grace_min` and `sensors_ok` → one push "sensor back, normal control resumed". Shorter blips stay silent; an outage live at (re)load gets no "offline" push but does get the "back" push when it ends.
- `mold_on and not fan_is_on` (edge) → persistent `ventilator_mold_warning` + push. Rule 3 outranks rule 5, so the fan stays on for the whole mold episode and this edge fires once per episode while the fan is commandable. The push is additionally gated on the fan entity existing and not being `unavailable` (code board 20260907-143611 R1-02): with the plug unreachable the turn-on fails, `fan_is_on` stays false and an ungated push would repeat every tick. `not mold_on` → dismiss (no-op when absent).
- Manual OFF on the plug during a run (code board R2-003): shower/high-humidity runs honour it (the fan stays off unless a new start condition arises — the user's intent wins); mold override and degraded mode re-assert on the next evaluation because rules 2 and 3 do not depend on `fan_is_on`.
- Recovery push (`sensors_back`) requires both sensors numeric at that moment; if only the temperature sensor returns later, degraded mode ends silently on the next tick (both live on one Aqara device, so this is theoretical).
- Push fan-out mirrors the rack: `repeat for_each notify_targets` with `continue_on_error: true` on each call.
- Manual run (`trigger.id` missing) → debug persistent notification with every computed variable, including the chosen weather entity and `rh_floor`.

### 3.6 Edge cases

| Case | Behaviour |
|---|---|
| Sensor died with the fan on | For the first `sensor_grace_min` the fan is held as-is (rule 2b); then degraded mode (rule 2) turns it off 20 min after the last motion. |
| Outdoor dew point + delta ≥ indoor temperature | `rh_floor` = 100 → rules 7/8 never fire; mold override still requires `dp_delta > 0`. |
| Both weather entities unavailable | Conservative default outdoor_dp (13 °C) keeps ventilation allowed; debug dump says "weather: none". |
| Manual plug press (Hue button, app) | Plug `last_changed` restarts the run clock. With normal indoor RH a manual ON is held only by rule 4 (`min_runtime`, 15 min) and then falls through to rule 9, so it is switched off after ~15 min; with RH above the stop target it continues under rule 7 up to `max_runtime`. The boost toggle is the intended manual path: rule 1 holds the fan for the full `boost_runtime_min` regardless of RH. |
| HA restart | Hue entities re-enter the state machine at startup, so `last_changed` for the plug and the motion sensor equals the restart time: an already-running fan gets a fresh run budget (bounded by `max_runtime`) and presence reads "recent" for `presence_window_min`. Both are harmless and bounded. |
| HA restart mid-run | `ha_start` re-evaluates; `last_changed` survives for Hue entities within the restart (state restored from the bridge), worst case one extra min-run. |
| Aqara re-pair changes entity ids | Deploy script re-points the instance inputs from a mapping file. |
| Boost pressed at night | Rule 1 runs the fan for `boost_runtime_min`, then the toggle auto-clears and rule 7/5 finish the run. |

## 4. Heating rack v2.0.0

### 4.1 Changes

| Area | Change |
|---|---|
| Comfort floor | New input `comfort_floor_delta` (default 1.0, 0–3 °C). A slot is active only while `indoor_temp < slot_target − comfort_floor_delta`; warmup lead is computed from the same ΔT. When the room is already within the delta the routine does not pre-heat and does not hold. Net effect: during a window the rack keeps the room at or above `target − delta`, heating toward `target` only from below that line; the device thermostat (on its own, ~1.4 °C warmer sensor) still governs while the slot is active. |
| Predictive motion | Removed: inputs `hall_motion`, `stairs_motion`, `enable_predictive_motion`, triggers T2/T3, all `*_motion_*` variables. `effective_start = auto_start`. |
| Warmup-started notification | Fires on the transition only: condition `desired_setpoint > idle_setpoint and current_setpoint ≤ idle_setpoint + 0.1` (the tick that actually raises the setpoint). Dismissed when the setpoint returns to idle. |
| At-target notification | Removed (unreachable dead code today; never observed). |
| Push | `continue_on_error: true` on every notify call; instance target `notify.mobile_app_martin_fold`. |
| Idempotency | `desired_setpoint` rounded to `state_attr(climate,'target_temp_step') | float(0.5)`; temperature selectors keep `step: 0.5` (rounding makes them safe). |
| Triggers | `to: [on, off]` on boost, vacation and fan triggers so attribute-only updates of the Hue group no longer restart runs. |
| Boost expiry | `input_boolean.turn_off` moved after the service-call block (the restart it causes then sees the setpoint already lowered). |
| Preset machinery | Removed (`desired_preset`, `set_preset_mode` block). Idle = `heat_cool` + `idle_setpoint`; proven live (DP temp_set 7, no runaway). `unknown` → `heat_cool` normalisation stays, documented as "switch on, mode eco". |
| Weekday | `now().weekday()` indexed into `[mon..sun]` (locale-safe). |
| Windows | If `hold_until ≤ target_warm` the hold is anchored to the next day. |
| Docs | `requirements_bathroom_heating_rack.md` rewritten against §2; README section updated. |

Refuted audit items (no change): "vacation is a one-way trip" and "off command 1440×/day" — HA's Tuya climate reports `off` whenever the switch DP is off, so the mode guard recovers and does not repeat.

### 4.2 Instance retune (data, applied by the deploy script)

| Slot | Now | New |
|---|---|---|
| Morning A (Mon–Fri) | 06:45 → 08:00, 23 °C | unchanged |
| Morning B (Sat–Sun) | 08:30 → 09:30, 23 °C | unchanged |
| Evening A (Mon–Fri, kids bath) | 18:15 → 19:45, 25 °C | **19:15 → 20:30, 24 °C** |
| Evening B (Sat–Sun) | 18:30 → 20:00, 23 °C | **19:15 → 20:30, 23 °C** |
| `warmup_min_minutes` | 28 | **10** |
| `notify_targets` | `notify.mobile_app_martin` | **`notify.mobile_app_martin_fold`** |
| removed keys | `hall_motion`, `stairs_motion` | dropped |

Basis: 10-day bathroom presence clusters on weekdays 19:19–20:53 local; the current window ended before the bath started.

## 5. Deploy script — `scripts/deploy-blueprint.sh`

`deploy-blueprint.sh [--dry-run] <yaml-file> <ha-blueprint-path> [instance.json ...]`

0. `--dry-run` (first argument) runs step 2 only and exits 0 on success, 1 on any validation problem; no credentials are read and nothing is sent. This is the mode the structure tests and the plan's pre-deploy checks use.
1. Sources `~/.config/hass-cli/env` (never echoes the token); refuses to run without `HASS_SERVER`/`HASS_TOKEN`. The Authorization header is read by curl from a 0600 temp file (`-H @file`, removed on exit) so the token never appears in process listings (code board 20260907-143611 R2-001). Instance ids must match `^[A-Za-z0-9_-]+$` before they are spliced into URLs or backup paths (R2-002).
2. Validates the YAML parses and that every input key referenced by each `instance.json` exists in the blueprint's input schema (catches the "unknown key → unavailable" trap before touching HA).
3. `blueprint/save` (WS, `allow_override: true`) via `hass-cli raw ws`.
4. For each `instance.json`: `POST /api/config/automation/config/<id>` with the full migrated config (the endpoint reloads that automation).
5. Asserts each instance entity is `on` (not `unavailable`) and prints `last_triggered`; non-zero exit on any failure.

The script joins the TCB roster via `TCB_EXTRA` from the moment it exists. Instance JSONs live under `deploy/` in the repo and contain entity ids only (no secrets).

## 6. Tests (pytest, repo convention)

`tests/test_bathroom_ventilator_structure.py` and `tests/test_bathroom_heating_rack_structure.py`, same loader/helpers as the LG AC suite:

- Input schema pins: exact key set, defaults, selector domains; removed keys absent.
- Trigger pins: ids, `not_from/not_to` filters, `for` on `sensors_lost`, `to` filters on the rack triggers.
- Decision-table pins: choose branch order and each condition template string.
- Rendered-Jinja pins (Jinja environment with `now`, `states`, `state_attr`, `is_state` fakes): `rh_floor` for 6 psychrometric rows (incl. Td ≥ T clamp), `stop_target`/`start_threshold`, `shower_signal` true/false rows (jump 6 vs 5; presence 14 vs 16 min), `is_night` for a midnight-crossing and a non-crossing window, rack `comfort_floor` gating rows, rack setpoint rounding rows (23.5 → 24 on step 1.0; 23.5 on step 0.5).
- Version pins: name and description carry `v2.0.0` and a v2-only token.
- Deploy script: `bash -n` + a dry-run unit test of the input-key validation against a fixture instance JSON (no network).

## 7. Migration and rollout

Session 1 (ventilator): merge → create helper → deploy script pushes v2.0.0 + migrated instance `1774555916056` (new keys, renamed keys, dropped keys, sensor ids re-pointed if changed) → assert `on` → observe: first shower trace shows `shower_signal: true` and a rule-6 turn-on; a manual run shows `rh_floor` and the chosen weather entity; degraded-mode drill by forcing a real `unavailable` state on the humidity sensor (Developer Tools → States, or `POST /api/states/<entity>` with `{"state":"unavailable"}`) for the 10-min grace and checking one push — NOT by disabling the entity, which removes it from the state machine (`new_state: None` matches neither `to: [unavailable, unknown]` nor the recovery trigger; code board 20260907-143611 R1-01). A missing entity is handled by `sensors_lost_minutes = 9999` → degraded on the next tick, silently.
Session 2 (rack): merge → deploy v2.0.0 + migrated instance `1776551429917` (dropped keys, retuned slots, fold target) → observe next morning/evening window: warmup notification exactly once, zero `Action ... not found` log lines, setpoint window length and start time in line with §4.2.

Rollback: re-save the previous blueprint YAML from git and POST the previous instance config (kept in `deploy/*.prev.json` by the script).

## 8. Out of scope

Dashboard card placement for the boost toggle (Martin adds the entity), Aqara re-pairing itself (physical), the kitchen Aqara sensor and the degraded ZHA network noted during diagnosis, energy metering of the rack.
