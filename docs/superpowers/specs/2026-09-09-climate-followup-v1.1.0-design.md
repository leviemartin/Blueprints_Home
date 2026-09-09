# Climate blueprints follow-up — Bedroom Sleep Pre-Cool v1.1.0 + LG AC Climate Control v1.3.0 (design)

**Date:** 2026-09-09 · **Repo:** Blueprints_Home · **Entry:** Stack B C (epic #18 → session #19; the issue body is the kickoff and carries `<!-- observe:open -->`) · **HA:** Core 2026.9.0 · **Research:** `docs/superpowers/research/2026-09-09-climate-followup-research-validation.md` — verdict **proceed** (noted uncertainty: delta at the guidance ceiling; 10-min debounce single-precedent; override detection by known values with a stated residual).

```
Stakes: standard
Trigger: default-up: automation logic changes in bedroom_precool.yaml + lg_ac_climate.yaml, tests, instance JSON, docs; no hard trigger matched (deploy script pinned via TCB_EXTRA and not edited; no file deleted; no dependency change)
Router: deterministic
Entry: C
```

## 1. Scope (one session, two blueprints — all items locked on #19; not re-opened at the board)

| # | Item | Blueprint |
|---|---|---|
| 0 | Auto-learn write hardening: clamp `new_bias` to the helper's live `min`/`max` ∩ −60…120; state-driven notification while the helper range is narrower than −60…120; render tests; deploy pre-check; requirements doc states the range. Inside v1.1.0, no separate version. | bedroom_precool |
| 1a | R1-07: replace the dead `state_attr(weather,'forecast')` fallback with a real `weather.get_forecasts type: daily` call. | bedroom_precool |
| 1b | R1-04: the instance tests call `scripts/deploy-blueprint.sh --dry-run` on the committed instance JSON instead of re-implementing the schema checks; keep the genuinely new assertions. | tests |
| 1c | Manual-override handling: a user setpoint change on the unit during PRECOOL / NIGHT_HOLD is respected until the next phase boundary; at most one notification per override; keep the rendered boundary tests. | bedroom_precool |
| 2 | Presence gating: away = setback (configurable delta, default 2.0 °C), not off; return = resume the schedule immediately; a NEW `input_boolean.climate_guest_mode` holds comfort; presence from `person.martin_levie` + `person.savannah_levie` and the security helpers. No comfort-band default change. | lg_ac_climate |

Out of scope: comfort-band default changes (Martin declined 20 °C on 2026-09-07); mobile push notifications for pre-cool; hourly fetch cadence changes (kept at /15 — the acceptance criterion on #19 requires a daily forecast on a tick where the hourly fetch is skipped).

## 2. Live facts (probed 2026-09-09 10:40–11:00Z)

- `input_number.autolearner`: min **−60**, max **240**, step 1, state 62 (min widened from 60 on 2026-09-09 07:39Z). Required by the blueprint: min ≤ −60 and max ≥ 120.
- `climate.bedrooms` / `climate.livingroom`: `hvac_modes` off/heat/auto/dry/cool/fan_only, min 18, max 30, `target_temp_step` 0.5, `fan_modes` auto/low/medium/high; `temperature: null` while off.
- `weather.home_sm` (Met.no, `supported_features: 3`): `get_forecasts daily` → 6 entries, keys `condition, datetime (local noon as UTC, e.g. 2026-09-09T10:00:00+00:00), humidity, precipitation, temperature (= day high), templow (= day low), uv_index, wind_bearing, wind_speed`; `hourly` → 48 entries. `weather.openweathermap` supports no forecast type (a call raises). `get_forecasts` serves HA's cached data; Met.no is polled every 55–65 min.
- Persons: `person.martin_levie`, `person.savannah_levie` (states home / not_home / zone / unknown). `input_boolean.security_ev_car_home` (on = EV9 at home, driven by `sec_ev_tracker`), `input_boolean.security_presence_unreliable` (on = presence flapping, driven by `sec_presence_flap_hourly`), `input_boolean.security_guest_mode` (the *security* guest window — not reused). **`input_boolean.security_auto_away` is the security system's auto-arm feature toggle (off since 2026-08-15, "AUTO-AWAY behind input_boolean.security_auto_away" in `script.security_resolve_mode`), not an away state — it is therefore NOT wired as a presence input.** The security resolver's own away rule (adopted here): a person counts as away when its state is not in `home / unknown / unavailable`; unknown fails toward home. `input_boolean.climate_guest_mode` does not exist yet (created at deploy).
- HA `Context` on the climate states written by the automations' time-pattern runs: `parent_id: null, user_id: null` — identical to a cloud-side write (research C13/C14). Context inspection is therefore not a manual-change signal for these automations.
- Setpoint-only changes bump `last_updated`, not `last_changed`; an off/on transition moves `last_changed` (research C15; live: `climate.bedrooms` last_changed 05:15Z, last_updated 07:59Z).
- Traces: HA keeps 5 stored traces per automation by default (a 1-minute automation retains ~5 min). The instance configs gain `trace: {stored_traces: N}` so the [8] evidence survives long enough to be read (precool 30, LG 20).
- Automation entity ids: `automation.bedroom_sleep_pre_cool_v1_0_0` (id 1779553673971), `automation.lg_ac_climate_control_v1_0_0` (id 1775578219942) — unchanged by an alias bump.

## 3. bedroom_precool.yaml v1.1.0

### 3.0 Auto-learn clamp to the helper's live range (Task 0)

STEP 2c, after `lead_bias`:

```
bias_helper_min:      state_attr(lead_bias_entity, 'min') | float(-60)     # '' entity → None → default
bias_helper_max:      state_attr(lead_bias_entity, 'max') | float(120)
bias_floor:           ceil(max(bias_helper_min, -60))      # whole numbers INSIDE the intersection (helper step 1)
bias_ceiling:         floor(min(bias_helper_max, 120))
bias_range_valid:     bias_floor <= bias_ceiling                # false when the helper does not overlap −60…120 at all
bias_helper_range_ok: bias_helper_min <= -60 and bias_helper_max >= 120
```

BEDTIME_LOCK: `new_bias = min(max(round(new_bias_raw), bias_floor), bias_ceiling) | int` (rounded first, the helper has step 1), written only while `bias_range_valid` (board R2-A-01/R2-B1-002/R1-04: a helper above 120 or a fractional bound can no longer produce a rejected value — the write is skipped and the notice says so). The write can no longer be rejected by the helper's range, so a narrow helper floors/ceils the bias instead of aborting the run (2026-09-08 17:29Z: `Invalid value for input_number.autolearner: 58.0 (range 60.0 - 240.0)` aborted the lock run after the setpoint commands).

STEP 7d (new, state-driven, LG STEP 2b pattern): while `enable_notifications and enable_auto_learn and lead_bias_configured and not bias_helper_range_ok` → `persistent_notification.create` id `bedroom_precool_bias_helper_range` naming the helper, its live min/max, the required −60…120 and the effective clamp; otherwise `persistent_notification.dismiss` the same id (`continue_on_error: true`). No push (the blueprint has no notify targets).

Rendered rows (each value re-parsed across the boundary): min 60 / max 240 / raw 58 → floor 60, ceiling 120, **written 60**, `range_ok False`; min −60 / max 240 / raw 58 → 58, `range_ok True`; attrs missing (None) → floor −60, ceiling 120, raw 130 → 120, raw −80 → −60, `range_ok True`; min −60 / max 240 / raw −80 → −60.

Deploy task pre-check: read the live helper attributes; abort before deploying if `min > -60` or `max < 120`. Requirements doc: "min ≤ −60, max ≥ 120, step 1".

### 3.1 Daily forecast fallback (R1-07)

STEP 2b keeps the hourly fetch at minute % 15 == 0 inside wake→bedtime. After `forecast_window_temps` is computed, a second `choose` fires the daily call when the hourly window is empty on a day-side tick and the entity supports daily forecasts:

```
weather_daily_supported: (state_attr(weather_entity, 'supported_features') | int(0)) | bitwise_and(1) > 0
forecast_daily_due:      forecast_window_temps | length == 0 and wake_time <= now_tod < bedtime and weather_daily_supported
→ weather.get_forecasts  type: daily  continue_on_error: true  response_variable: daily_forecast_resp
forecast_daily_list:     daily_forecast_resp[weather_entity].forecast if defined/mapping/present else []
forecast_daily_high:     temperature of the entry whose LOCAL date == today (as_datetime(datetime) | as_local), else the first entry's temperature, else none
forecast_daily_ok:       forecast_daily_high is a number
forecast_max:            hourly window max if non-empty; elif forecast_daily_ok → max(forecast_daily_high, outdoor_now); else outdoor_now
```

`forecast_daily_fallback` and the `state_attr(weather_entity, 'forecast')` read are deleted. The daily `temperature` is the day's high (pyMetno: max of the day's hourly readings), so the fallback is conservative in the afternoon/evening (the peak may be past) — the asymmetric-cost rule (early is cheap) accepts that. An unsupported type would raise; the call is gated on the feature bit AND carries `continue_on_error`. STEP 7b's "forecast & outdoor unavailable" notice additionally requires `not forecast_daily_ok`. The debug dump prints `daily high`.

Consequence on #19's acceptance: on a non-fetch day-side tick the trace's `changed_variables` shows `forecast_daily_high` = today's high and `forecast_max ≥ outdoor_now`.

### 3.2 Manual-override handling (research design C — known-value set; A rejected, B fallback)

Definitions (STEP 2c, after `maintaining_setpoint` / `effective_drive`):

```
ac_temp_step:      max(state_attr(ac_climate,'target_temp_step') | float(0.5), 0.1)
known_setpoints:   [effective_drive, maintaining_setpoint, clamp(maintaining − correction_step), clamp(maintaining + correction_step)]
                   each quantised as the DEVICE holds it: int(v) when ac_temp_step ≥ 1 (lg_thinq sends int() there), else v;
                   effective_drive / maintaining_setpoint / deep_target_setpoint are quantised the same way at their source (R2-B1-005)
setpoint_is_known: any |current_setpoint − k| <= 0.1 over known_setpoints
ac_state_age_sec:  now − states[ac_climate].last_changed              # age of the current running/off spell
manual_setpoint:   ac_is_running and current_setpoint_known and not setpoint_is_known and ac_state_age_sec >= 120
                   # two-tick grace (board R1-01): the first tick after turn-on retries a lagged/lost command as in v1.0.x
automation_up_since_ts: as_timestamp(this.last_changed)        # boot / reload / enable of this automation
ac_off_since_ts:   as_timestamp(states[ac_climate].last_changed)
earliest_turn_on_ts: as_timestamp(today_at(bedtime) − lead_cap)  # the instant form of earliest_turn_on_tod
vacation_changed_ts: newest last_changed over vacation_toggle, else 0
manual_off:        not ac_is_running and not ac_unavailable
                   and ac_off_since_ts >= earliest_turn_on_ts + 120      # went off inside the window (120 s margin: a DAY_OFF turn_off confirmed late — R1-05)
                   and ac_off_since_ts > automation_up_since_ts + 600    # not the state re-created at HA start/reload (cloud setup lag — R1-02/R2-B1-004)
                   and vacation_changed_ts < ac_off_since_ts − 120       # not the vacation turn-off (coordinator lag — R2-B1-003)
```

Behaviour:
- **PRECOOL:** the whole command block (turn_on, mode, setpoint, fan) is skipped while `manual_setpoint or manual_off`. A manual setpoint is left alone; a unit switched off inside the window stays off. Blueprint values (drive 18, maintaining 21, deep 19.5/22.5 on the live instance) are re-asserted as before.
- **BEDTIME_LOCK:** unchanged lock commands on a running unit (the phase boundary ends the override: the lock sets `maintaining_setpoint` + `night_fan`). The auto-learn write is **skipped** when `manual_setpoint` is true at the lock tick — the night's outcome does not reflect the predictor. A manual off leaves the unit off (cool-day no-op semantics).
- **NIGHT_HOLD:** issues nothing (unchanged). **DEEP_NIGHT_CHECK** is the next phase boundary: it keeps its existing correction rule (literal reading of "respected until the next phase boundary"). *Operator question recorded for the board/Martin:* if the deep-night check should also stand down on a manual value, it is a one-line gate (`not manual_setpoint`) — not implemented by default.
- **Notification (STEP 7e, state-driven):** while `enable_notifications and phase in [PRECOOL, BEDTIME_LOCK, NIGHT_HOLD] and (manual_setpoint or manual_off)` → `bedroom_precool_manual_override` (which was detected, the value, and when the blueprint resumes); otherwise dismiss. "One push max" is read as one notification per override episode; the blueprint has no mobile-push inputs.

Residuals (documented in the requirements doc): (1) a manual change *to* one of the blueprint's own values is not detected (v1.0.x behaviour: re-asserted within a minute); (2) if a setpoint command fails at the turn-on tick and the unit comes back with an unknown remembered value, that night reads as a manual override (notification shown; self-heals next day) — the research's B design shares this class; (3) a config edit of `ideal_temp`/`hall_offset` during PRECOOL reloads the automation, which resets `this.last_changed` (manual-off guard) but makes the old setpoint read as manual until the lock; (4) a ThinQ cloud outage that ends inside the window (`unavailable` → `off`) re-stamps `last_changed` and reads as a manual off for that night — the notice names the recovery (switch the unit on by hand; a running unit inside the window is adopted as PRECOOL at once). Triple-check 2026-09-09: (1)–(4) accepted-documented; the device-held quantisation was a P1 fixed pre-board. Board 20260909-113000 (design-time): the two-tick grace (R1-01, P1), the lag margins on the three manual-off guards, the write gate on a non-overlapping helper range, the parsing hardening of both forecast loops (`as_datetime(ts, none)`, `float(none)`) and the STEP 2 validation on the configured LG band were actioned in-session; a reload after a manual off ends that hold (documented).

### 3.3 Dry-run in tests (R1-04)

`test_precool_instance_*` and `test_lg_ac_instance_*` call `run("--dry-run", BP, HA_PATH, INSTANCE)` (the `run` harness from `tests/test_deploy_blueprint_script.py`) and assert rc 0 + "dry-run: validation passed"; the retained Python assertions are: precool `weather_entity == weather.home_sm`, alias endswith v1.1.0; LG `s1 < s2`, selector ranges, alias endswith v1.3.0.

### 3.4 Version, docs, instance

Name "Bedroom Sleep Pre-Cool v1.1.0", description `**Version: 1.1.0**` + history line; feature bullets: daily forecast fallback, manual override, helper-range notice. Requirements doc: helper range, forecast fallback order (hourly → daily high → outdoor sensor), override semantics + residuals, beep table unchanged. README: feature bullets. Instance: alias v1.1.0, `trace.stored_traces: 30`, inputs unchanged.

## 4. lg_ac_climate.yaml v1.3.0 — presence setback

### 4.1 Inputs (all additive with defaults — the stored instance survives re-import)

| Input | Selector | Default | Meaning |
|---|---|---|---|
| `presence_entities` | entity, domain [person, device_tracker], multiple | [] | Everyone listed must be away for the setback. Empty = presence gating off. |
| `home_indicators` | entity, domain [input_boolean, binary_sensor], multiple | [] | Any `on` holds comfort: guest-mode toggle, EV-car-home latch, presence-unreliable guard. |
| `away_setback_delta` | number 0–5 °C, step 0.5 | 2.0 | Band widening while away (0 = never set back). |
| `away_delay_minutes` | number 0–120 min, step 5 | 10 | Every presence entity must have been away at least this long (re-checked every tick — the Better Thermostat blueprint's precedent). |

Top-level `variables:` pass-through: `presence_entities`, `home_indicators`, `away_delta`, `away_delay`; the comfort inputs are renamed **`temp_low_cfg` / `temp_high_cfg`** at top level and the effective `temp_low` / `temp_high` are defined in STEP 1 (see 4.3), so every existing consumer template stays byte-identical.

### 4.2 Triggers (appended, ids after the existing six)

- `presence_return`: state on `!input presence_entities`, `to: home` — immediate resume when someone arrives.
- `indicator_on`: state on `!input home_indicators`, `to: "on"` — guest mode switched on / EV arrives / flap guard raised.

(Empty-list `entity_id` is valid for a state trigger — the `door_sensor` precedent.)

### 4.3 STEP 1 variables (inserted after `current_temp`, before `outdoor_temp_raw`; declaration order is load-bearing)

```
presence_enabled:  presence_entities is a non-empty list
away_delay_sec:    away_delay | int(0) * 60
persons_all_away:  presence_enabled and for every p: states[p] exists, state not in [home, unknown, unavailable], and now − last_changed >= away_delay_sec
                   # the delay measures the CURRENT away state: a zone→zone move re-arms it once (documented; R1-08/R2-B2-02)
home_indicator_on: any of home_indicators is NOT exactly 'off' (on, unknown, unavailable, missing) — fail toward comfort (R2-A-03/R2-B2-01)
away_active:       presence_enabled and persons_all_away and not home_indicator_on and away_delta > 0
temp_low:          temp_low_cfg − (away_delta if away_active else 0)
temp_high:         temp_high_cfg + (away_delta if away_active else 0)
```

Everything downstream (quantised setpoints, deep-pull gates, `target_mode` hysteresis, distances, maintenance midpoint) reads the effective band; the STEP 2 validation gates and their messages read the CONFIGURED band `temp_low_cfg`/`temp_high_cfg` so the widened away band never masks an inverted or too-narrow config (R1-06). Live instance while away: 19.0–25.5 °C.

Behaviour: on leaving, a unit that was heating at 21.5 °C finds itself inside the widened band → `target_mode` off → one `climate.turn_off` (one beep); it re-heats only below 19.0 °C (setback floor), re-cools only above 25.5 °C. On return the band snaps back on the `presence_return` trigger / next tick → normal control (one command if the room is outside 21–23.5). Vacation, schedule window and door-open pierces are unchanged and outrank presence. Manual-hold machinery follows `desired_setpoint` automatically. `unknown`/`unavailable` presence = home (fail toward comfort, the security resolver's rule). HA restart resets `last_changed` → setback re-arms `away_delay_minutes` after boot.

### 4.4 Docs, instance, deploy

Description bullet "Presence Setback (v1.3.0)"; requirements Climate-7 + Overrides-4 + Safety note (unknown = home); README feature bullet. Instance `deploy/lg_ac_climate_1775578219942.json`: alias v1.3.0, `presence_entities: [person.martin_levie, person.savannah_levie]`, `home_indicators: [input_boolean.climate_guest_mode, input_boolean.security_ev_car_home, input_boolean.security_presence_unreliable]`, `away_setback_delta: 2`, `away_delay_minutes: 10`, `trace.stored_traces: 20`. Deploy creates `input_boolean.climate_guest_mode` via WS `input_boolean/create` (name "Climate Guest Mode") when absent and asserts the resulting entity id before pushing the instance (an unknown entity in the input is not fatal for the automation but makes the guest toggle inert).

## 5. Tests (pytest + PyYAML + Jinja2 render harness; every rendered value re-parsed with `ast.literal_eval` between chained renders)

Pre-cool (`tests/test_bedroom_precool_structure.py`): version 1.1.0; helper-range chain rows (3.0); daily fallback: `weather_daily_supported` bit rows (3 → True, 2 → False, None → False), `forecast_daily_high` picks today's entry (not the first) and returns None on an empty list, `forecast_max` chain rows (hourly wins; daily when hourly empty; outdoor when both absent), the daily call's branch condition contains `forecast_window_temps | length == 0` and `weather_daily_supported` and the step carries `continue_on_error: true`, the text no longer contains `state_attr(weather_entity, 'forecast')`; override rows (3.2): `known_setpoints`/`setpoint_is_known`/`manual_setpoint` (18/21/19.5/22.5 known; 24 and 20 manual; off → False; unknown setpoint → False; string-form list across the boundary re-parses), `manual_off` rows (off at 16:30 → True; off at 07:15 → False; automation up since 16:29 → False; vacation toggled at 16:30 → False; running → False); branch walker: PRECOOL climate calls sit under `not manual_setpoint and not manual_off`, the `input_number.set_value` under `not manual_setpoint`, DEEP_NIGHT_CHECK's `climate.set_temperature` carries no manual gate (documented literal boundary), notification ids `bedroom_precool_bias_helper_range` and `bedroom_precool_manual_override` each have a create and a dismiss; ordering pins (`lead_bias` → `bias_helper_min` … → `bias_helper_range_ok`; `maintaining_setpoint` → `known_setpoints` → `setpoint_is_known` → `manual_setpoint`; `earliest_turn_on_ts` → `manual_off`); instance: dry-run rc 0, alias v1.1.0, `night_fan: low`, `stored_traces` 30; the existing phase/boundary tests unchanged.

LG (`tests/test_lg_ac_climate_structure.py`): version 1.3.0; input schemas + defaults; variable mappings (`temp_low_cfg`, `temp_high_cfg`, four new); trigger roster ids `[update_loop, vacation_on, init, door_open, vacation_off, init, presence_return, indicator_on]` + shapes; STEP-1 ordering `current_temp < presence_enabled < away_delay_sec < persons_all_away < home_indicator_on < away_active < temp_low < temp_high < outdoor_temp_raw` and `temp_high < setpoint_cool_q`; rendered rows: `persons_all_away` (both away 15 min → True; one home → False; one unknown → False; away 3 min with delay 10 → False; delay 0 → True; not enabled → False; a string-form list → False), `home_indicator_on` (any on → True; all off → False; empty → False), `away_active` combinations, `temp_low`/`temp_high` (21/23.5 → 19/25.5 away, unchanged home, delta 0 → unchanged); all existing exact-string pins stay green (they name `temp_low`/`temp_high`); description tokens; instance dry-run rc 0 + alias + new keys.

## 6. Rollout ([7] merge → [8] deploy + observe → [9])

1. Merge `origin/main` into the branch, PR with `Session: #19`, merge.
2. Deploy pre-checks: helper range live (min ≤ −60, max ≥ 120); `input_boolean.climate_guest_mode` created/verified; both dry-runs green; HA `validate_config` on the input-substituted configs (`triggers`/`actions` plural).
3. `scripts/deploy-blueprint.sh` for both blueprints with their instance JSON (backs up `deploy/<id>.prev.json`); both automations `on`.
4. Live-verify: manual "Run" of pre-cool → debug dump shows `daily high`, `manual`, helper range fields; next non-fetch day-side tick trace has `forecast_daily_high` and a non-zero `automation_up_since_ts`; LG: a temporary instance variant wired to two throwaway `device_tracker.climate_test_*` entities (created with `device_tracker.see`) and the guest toggle only — everyone-away after the real 10-min debounce → a natural tick traces `away_active: True`, `temp_low: 19.0`; guest on → an `indicator_on`-triggered run with `away_active: False`; a tracker home → a `presence_return`-triggered run. **No production security entity is written** (board R2-A-04: the live EV-charger guard would cut the plug on a faked latch). Immutable pre-deploy copies of both live instance configs and both shipped YAMLs are taken first; rollback is pinned to `5c5a08b` (board R2-A-05).
5. At deploy time, note on #22 and #24 that the live pre-cool moved to v1.1.0 (their observation windows were reading v1.0.3).
6. Observe (24 h): both `on`; the first bedtime lock writes the bias with no log error and no helper-range notification; a non-fetch tick with a non-empty daily forecast; zero log errors.

## 7. Alternatives considered

- Hourly fetch on every tick (cheap cached read) instead of a daily fallback — behaviourally best (no 14/15-tick flicker of `forecast_max`) but outside the locked R1-07 wording and the #19 acceptance criterion; noted as a follow-up.
- Override detection via `Context` (A) — blind for time-pattern automations (verified live); rejected. Expected-state helper (B) — a new helper + a write per commanding tick, same false-positive class; fallback if C's residual bites.
- Separate `guest_mode` input — folded into `home_indicators` (identical semantics: any on holds comfort; the entity name documents the role).
- `alarm_control_panel.alarmo == armed_away` as an away confirmation — not wired (YAGNI); a future `away_indicators` input if wanted.
