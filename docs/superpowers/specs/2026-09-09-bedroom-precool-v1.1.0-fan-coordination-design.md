# Bedroom Sleep Pre-Cool v1.1.0 — ceiling-fan coordination + fan-only night hold (design)

**Date:** 2026-09-09 · **Repo:** Blueprints_Home · **Entry:** Stack B A (epic #25, session #26) · **Worktree:** `~/AI/projects/Blueprints_Home-fans`
**Research-validate:** `docs/superpowers/research/2026-09-09-fan-ac-coordination-research-validation.md` — verdict **proceed** (night hold reframed as AC-off coast + guard; fan-assist demoted to an experiment).

```
Stakes: standard
Trigger: default-up: automation logic in bedroom_precool.yaml + tests + instance JSON + requirements + README; no hard trigger matched (scripts/deploy-blueprint.sh untouched, pinned)
Router: deterministic
Entry: A
tcb_manifest_sha: 294e5c97c5ac2afffe1100b83cc41aa99f3c7b6805edb572a2e3fffaf0a63aea
tcb_baseline: /home/martin/AI/reviews/tcb-baseline-e47dda9f8b1e8bcb.txt
```

## 1. Why

Martin (2026-09-08): investigate coordinating the bedroom ceiling fans with the hall AC to bring the rooms down quicker, or switch the AC off at night and keep the fans on low. Brainstorm decisions (2026-09-09): both bedrooms in scope with one shared target (a third room joins later); fan-assist judged on the measured sensor drop, the night hold on comfort inside ideal + 1.5 °C; AC fallback at any minute after bedtime; night speed ceiling = very low (1 %); AC off at the bedtime lock after a small pre-chill; optimise for AC-off nights, mindful that the warm season is ending.

Research found the night hold works because the AC is off and the rooms coast on the house mass (our own 100-night history: flat with the AC off, +0.3…+1.4 °C rebound after an evening run, inside the band with a pre-chill on September nights), not because of the fans — the upstairs hall is warmer than the bedrooms once the compressor stops and fans cool people, not rooms. Fan-assist during PRECOOL has no physical evidence behind it and becomes a measured experiment. Two device facts drive the mechanics: the LG restores its last mode/setpoint/fan in one `turn_on` (one beep) and Tuya cloud fans lag 10–60 s.

## 2. Design

### 2.1 Inputs (all new inputs have defaults; an existing instance keeps v1.0.3 behaviour byte-for-byte)

Group 5 — behaviour:
- **`night_mode`** select `ac_hold` (default, today's lock: park the maintaining setpoint + night fan, AC runs all night) | `fan_only` (new: park, then switch the AC OFF at the lock; a continuous guard brings it back).
- **`prechill_offset`** number 0.0–2.0 step 0.1, default 0.5 °C. Only used when `night_mode = fan_only`: PRECOOL drives to `bedtime_target = ideal_temp − prechill_offset` so the coast starts below ideal.

Group 7 — bedroom fans (new group, all optional):
- **`bedroom_fans`** entity multiple, domain fan, default `[]`. Empty = no fan command is ever issued.
- **`interlocked_fans`** entity multiple, domain fan, default `[]`. Subset of `bedroom_fans` that must never be commanded while an interlock sensor is active (the kids fan with its height-gated PIR).
- **`fan_interlocks`** entity multiple, domain binary_sensor, default `[]`. Any sensor `on`, `unavailable` or `unknown` = blocked (fail-safe, same direction as the cutoff blueprint).
- **`night_fans`** select `all` (default) | `odd` | `even` | `off`: on which nights the listed fans are set to the night percentage at the lock.
- **`night_fan_percentage`** number 1–100, default 1 (app step 1, "very low").
- **`fan_assist`** select `off` (default) | `all` | `odd` | `even`: on which days the fans run at the pre-cool percentage from the moment the AC starts. The experiment switch.
- **`precool_fan_percentage`** number 1–100, default 21 (app step 2, "low").
- **`fan_settle_minutes`** number 5–120, default 45: how long after the lock (and after the AC start) the blueprint may still apply a pending fan setting to a fan nobody has touched.
- **`fans_at_wake`** select `leave` (default) | `off`.

Parity: `odd`/`even` refer to the day of the year of the NIGHT's start date, `(now() − 12 h).timetuple().tm_yday % 2`, so the lock at 19:29 and everything until 07:15 share one parity. STEP 3 validation adds `bedtime > 12:00:00 and wake_time < 12:00:00` (one config error message) and "the settle window must not cross midnight": `(today_at(bedtime) + timedelta(minutes=fan_settle_minutes)).date() == today_at(bedtime).date()`, compared as instants inside one template (repo lesson: wrapped `HH:MM:SS` strings sort wrong).

Top-level `variables:` pass-through gains one `!input` line per new input (repo rule; board R1-01 on v1.0.3).

### 2.2 Variables (STEP 2a/2c additions, single-lined where they feed comparisons)

- `fan_only_mode = night_mode == 'fan_only'`; `bedtime_target = ideal_temp − prechill_offset if fan_only_mode else ideal_temp`.
- `precool_substate` compares `warmest_bedroom` against `bedtime_target` (was `ideal_temp`); the BEDTIME_LOCK auto-learn `bedtime_error = warmest_bedroom − bedtime_target`. `maintaining_setpoint`, `effective_drive`, `desired_mode`, `night_fan_mode` unchanged.
- `night_parity` (`odd`/`even`), `fan_assist_tonight`, `night_fans_tonight` (booleans from the selects).
- `interlock_blocked`: any `fan_interlocks` entity in `['on','unavailable','unknown']`.
- `lock_ts = as_timestamp(today_at(bedtime) − 1 min)` carried as a float (instants cross the variables boundary as strings); `settle_end_tod = (today_at(bedtime) + fan_settle_minutes).strftime('%H:%M:%S')`; `ac_started_ts = as_timestamp(states[ac_climate].last_changed)` (the unit's off→cool instant; setpoint/fan changes touch `last_updated`, not `last_changed`); `since_ac_start_min = (as_timestamp(now()) − ac_started_ts) / 60`.
- `in_wake_window = wake_tod <= now_tod < wake_tod + 1 min`; `in_fan_settle = lock_tod <= now_tod < settle_end_tod` (starts on the lock tick, never crosses midnight — validated); `in_fan_assist_window = phase == 'PRECOOL' and ac_is_running and since_ac_start_min < fan_settle_minutes`.
- Per fan (rendered inside the fan step, not carried): `fan_touched_ts = as_timestamp(states[fan].last_updated)` — `last_updated`, because a percentage change bumps `last_updated` only (repo note from the dimmer project); `last_changed` moves on on/off transitions alone.
- `guard_due = fan_only_mode and phase in ['NIGHT_HOLD','DEEP_NIGHT_CHECK','DEEP_HOLD'] and not ac_is_running and warmest_bedroom > ideal_temp + tolerance`.

### 2.3 Fan write rule (the whole deconfliction, one rule)

A fan is commanded only when ALL hold: the fan is configured; its state is not `unavailable`/`unknown`; it is not already at the wanted percentage-and-state; if it is in `interlocked_fans`, `interlock_blocked` is false; and **nobody has touched it since the reference instant** — `fan_touched_ts < reference_ts` (i.e. `last_updated` older than the reference) where the reference is `lock_ts` for the night setting and `ac_started_ts` for the pre-cool setting. Every command passes `percentage` explicitly (`fan.turn_on` with `percentage`; `fan.turn_off` for the wake option). Direction is never written (the seasonal blueprint owns it).

Consequences, all by construction: the blueprint never re-asserts a fan that the safety cutoff switched off (the cutoff's `turn_off` updates `last_updated`, so the fan counts as touched); it never commands the kids fan while an adult stands under it (interlock); it never undoes Martin's manual change after the lock (touched); a successful command updates `last_updated`, so a fan is written at most once per reference instant — the per-tick evaluation is edge-triggered by the guard, not by memory. If the Tuya cloud reports late, the identical command may repeat on the next tick until the state lands or the settle window closes (bounded, idempotent on the device). There is no retry outside the settle windows.

### 2.4 Phase behaviour

- **DAY_OFF** — unchanged. When `fans_at_wake = off`: on the wake-window tick, `fan.turn_off` every configured fan that is `on` (no interlock or touched check — off is always safe).
- **PRECOOL** — AC logic unchanged except the DRIVE/HOLD threshold is `bedtime_target`. Fan-assist: while `in_fan_assist_window and fan_assist_tonight`, apply the fan write rule with target `precool_fan_percentage` and reference `ac_started_ts`. The window starts the tick after the AC start (the start tick captured `ac_is_running = false`; the fan follows one minute later, which also lets the Tuya cloud settle).
- **BEDTIME_LOCK** (one tick) — if `ac_is_running`: `ac_hold` = v1.0.3 sequence unchanged (mode / maintaining setpoint / night fan, each only if different) + auto-learn write. `fan_only` = the same three park calls (mode, maintaining setpoint, night fan — each only if different; usually 0 calls because the pre-chill HOLD already parked the unit, up to 3 if the lock lands in DRIVE), then **`climate.turn_off`**, then the auto-learn write with `bedtime_target`. The LG's next `turn_on` restores exactly the parked state (research C5; verified on our unit 09-08).
- **Fan settle window** (`in_fan_settle`, from the lock tick to `bedtime + fan_settle_minutes`, spans NIGHT_HOLD): when `night_fans_tonight`, apply the fan write rule with target `night_fan_percentage` and reference `lock_ts`. This is how the kids fan gets its night speed once the bedtime routine ends and the PIR clears, without a loop and without overriding a manual off.
- **NIGHT_HOLD / DEEP_NIGHT_CHECK / DEEP_HOLD** — **Guard:** when `guard_due`, `climate.turn_on` (one beep; the unit comes back on the parked maintaining setpoint + night fan). The running unit is the latch: on every later tick `ac_is_running` is true, so the guard cannot fire again, the existing DEEP_NIGHT_CHECK nudge applies as in v1.0.3 (it can add one `set_temperature` if the drift is still outside tolerance in the 01:00 window — documented ≤ 2 commands in that window on a guard night), and DAY_OFF switches the unit off at wake. In `ac_hold` mode the guard is dead code (the unit is already running).
- **Notices (STEP 7d, new):** `bedroom_precool_fan_skipped` on the last settle-window tick if a configured fan is still not at its night percentage and untouched (interlock stayed on or the fan was unavailable) — informational, no retry. `bedroom_precool_guard_fired` when the guard turns the AC on (informational; lets Martin see the night on his phone in the morning). Both gated on `enable_notifications`.
- **Debug dump (STEP 8):** adds night_mode, bedtime_target, night_parity, fan_assist_tonight / night_fans_tonight, interlock_blocked, guard_due, and per fan: state, percentage, `last_changed` vs lock.

### 2.5 Restart, cloud and edge cases

- **HA restart at night:** the tick recomputes from live state. AC off + over band → guard fires (correct). AC running → hold. Fans: after a restart a Tuya fan's `last_updated` is either the restart instant (later than `lock_ts` → counts as touched → left alone, the safe direction) or a restored earlier value (→ untouched → the pending night setting is applied once, also correct). Neither case loops.
- **Guard restore state:** `turn_on` brings back whatever the unit was parked in. Every `fan_only` lock parks it in cool / maintaining / night fan, so the restore is right unless the unit was used by hand in another mode between the lock and the guard (e.g. `dry`, or `heat` out of season). The guard does not re-assert the mode (that would fight a deliberate manual change and cost a beep on every trip). The LG reports a null setpoint while off, so the `bedroom_precool_guard_fired` notice reports the trip time, the warmest reading and the threshold; the restored mode/setpoint/fan is visible on the climate entity's history the next morning.
- **LG cloud `unavailable`:** STEP 5 stops the tick (unchanged), so a flapping read cannot fire the guard. A stale `off` on a running unit costs at most one no-op `turn_on` beep.
- **Sensor failure at night (STEP 5 stop before the guard):** both bedroom sensors dead → no guard, AC stays off all night. Accepted for v1.1.0 (mirrors the existing "AC runs until sensors recover" asymmetry noted for #19); the notice already fires.
- **Manual AC start during the night** (Martin turns the unit on): `ac_is_running` → the guard stays silent, DAY_OFF turns it off at wake. Manual AC off after a guard trip: the guard may fire once more if still over band — one beep; documented.
- **Cool-day nights** (AC never started): lock is a no-op for the AC; the fan settle window still applies the night percentage if `night_fans_tonight` (fans are cheap and the parity switch can turn them off).
- **Beep budget (fan_only):** lock ≤ 3 (typically 1: `turn_off`); guard ≤ 1; deep-night nudge ≤ 1 (guard nights only). `ac_hold` unchanged: lock ≤ 3 (typically 1–2), nudge ≤ 1.

### 2.6 Instance, docs, version

- `deploy/bedroom_precool_1779553673971.json`: `night_mode: fan_only`, `prechill_offset: 0.5`, `bedroom_fans: [fan.ceiling_fan_light_v2_2, fan.ceiling_fan_light_v2]`, `interlocked_fans: [fan.ceiling_fan_light_v2]`, `fan_interlocks: [binary_sensor.samuel_samuel_matthew_fanprotection]`, `night_fans: all`, `night_fan_percentage: 1`, `fan_assist: off`, `precool_fan_percentage: 21`, `fan_settle_minutes: 45`, `fans_at_wake: leave`; alias v1.1.0. Also assign `fan.ceiling_fan_light_v2_2` (device) to the Master Bedroom area (registry edit, no code).
- Version 1.1.0; description history line; `requirements_bedroom_precool.md`: phase table rows for the fan-only lock, the guard and the settle window, the fan write rule, the beep budget, the parity experiments; README feature bullets + the A/B protocol pointer.

## 3. Alternatives considered

1. **Per-tick "ensure fan on"** — cancels the kids-room safety cutoff within a minute and overrides manual control. Rejected (research anti-pattern 1).
2. **A helper (`input_select` phase latch / `input_boolean` override)** — the community's default persistence idiom; unnecessary here because the running AC is the guard latch and `last_changed` gives touch detection for free. Rejected to keep the blueprint helper-free; revisit only if the `last_changed` rule proves brittle on Tuya.
3. **LG `fan_only` mode at night instead of ceiling fans** — 30 W, one command, but it circulates the hall, which is warmer than the bedrooms once the compressor is off. Rejected.
4. **No fans at all: AC-off + guard only** — the credible contrarian read of the evidence. Kept one input away: `bedroom_fans: []` or `night_fans: off` gives exactly that arm, and the parity switch measures the difference.
5. **AC off at the 01:00 check instead of the lock** — fewer AC-off hours; Martin chose the lock with pre-chill.

## 4. Live facts (probed 2026-09-09)

`climate.bedrooms` hvac_modes `off/heat/auto/dry/cool/fan_only`, fan_modes `auto/low/medium/high`, min 18; `turn_on` on 09-08 14:51:02Z reported `cool/21/medium` two seconds before the blueprint's own setpoint/fan calls. Fans: `fan.ceiling_fan_light_v2` (Samuel area, off, pct 21, `forward`) and `fan.ceiling_fan_light_v2_2` (no area, on at 1 % for ≥ 10 days), both Tuya `ceiling fan/Light v2`, `percentage_step` 1.0, supported_features 53 (speed + direction + on/off, no presets). Cutoff instance: sensor `binary_sensor.samuel_samuel_matthew_fanprotection`, hold 3 min; it fired several times a day in the last 10 days. Dimmer instance: `speed_low_pct` 21, `speed_very_low_pct` 1. Forecast 09-09…09-14 highs 17–21 °C: no PRECOOL expected this week at `skip_threshold` 21.

## 5. Acceptance

- **Structure tests** (`tests/test_bedroom_precool_structure.py`, rendered chains via `_render_chain`): every new input has a default and a `!input` pass-through; `bedtime_target` = ideal in `ac_hold`, ideal − offset in `fan_only`; the DRIVE/HOLD substate and the auto-learn error use `bedtime_target`; `night_parity` is identical at 19:29 and 01:00 of the same night and flips across the 12:00 pivot; `guard_due` true only in the three night phases with `fan_only`, AC off and warmest above ideal + tolerance, and false once the AC runs (latch); the fan write rule (rendered per fan) is false when the fan is touched after the reference, when interlocked and blocked, when unavailable, or already at target, and true otherwise; the branch walker asserts the BEDTIME_LOCK `fan_only` branch orders `set_temperature` → `set_fan_mode` → `turn_off` → auto-learn and the `ac_hold` branch is unchanged from v1.0.3 (regression pin on the rendered service list); the settle window's fan call carries `percentage: night_fan_percentage`, the PRECOOL one `precool_fan_percentage`; STEP 3 rejects a settle window reaching the deep-night check and a bedtime before noon; version + instance pins (instance keys ⊆ schema, `deploy-blueprint.sh --dry-run` green). Suite green.
- **Deploy** via `scripts/deploy-blueprint.sh` before 19:29 CEST on a day Martin picks; instance `on`. **Daytime guard live-verify** (beeps are free by day): temporarily set the instance `bedtime` a few minutes ahead and `ideal_temp` 20 → watch PRECOOL → lock (`set_temperature`/`set_fan_mode` if needed, then `turn_off`, fans → 1 %) → NIGHT_HOLD guard `turn_on` restoring `cool/21/low` → restore the instance. Also one house-meter delta reading of a fan at 1 % (research contested claim on fan draw).
- **Observation ([8], ≥ 2 nights):** 19:29 trace shows the park/off/fan sequence, kids fan set within the settle window after the PIR clears (or the skipped notice), zero guard trips on mild nights, warmest ≤ 24.5 at 06:00, one wake command; 24 h log clean. The A/B protocol (research doc) runs afterwards: `fan_assist: odd` when PRECOOL nights return, `night_fans` parity for the fans' own effect.
