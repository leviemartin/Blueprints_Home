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
- **`fan_interlocks`** entity multiple, domain binary_sensor, default `[]`. Any sensor `on`, `unavailable`, `unknown` or missing = blocked (fail-safe, same direction as the cutoff blueprint).
- **`interlock_clear_minutes`** number 0–15, default 5: an interlock sensor that changed state within the last N minutes still blocks. The cutoff blueprint resumes its fan at exactly `sensor cleared + hold_duration` (3 min live); the pre-cool hold must be STRICTLY longer than that plus the Tuya lag, otherwise the two blueprints write the fan within seconds of each other (the cutoff's resume at 21 %, ours at 1 %), and any pre-cool write that lands inside the cutoff's hold cancels its pending resume. **Deploy-time invariant (two repos, no shared validation):** the instance value ≥ the cutoff instance's `hold_duration` + 2 min — checked by the deploy live-verify and stated in both READMEs.
- **`night_fans`** select `all` (default) | `odd` | `even` | `off`: on which nights the listed fans are set to the night percentage at the lock.
- **`night_fan_percentage`** number 1–100, default 1 (app step 1, "very low").
- **`fan_assist`** select `off` (default) | `all` | `odd` | `even`: on which days the fans run at the pre-cool percentage from the moment the AC starts. The experiment switch.
- **`precool_fan_percentage`** number 1–100, default 21 (app step 2, "low").
- **`fan_settle_minutes`** number 5–120, default 45: how long after the lock (and after the AC start) the blueprint may still apply a pending fan setting to a fan nobody has touched.
- **`fans_at_wake`** select `leave` (default) | `off`.

Parity: `odd`/`even` refer to the day of the year of the NIGHT's start date, pivoting at WAKE TIME (not noon): `night_date = today if now_tod >= wake_tod else yesterday`. Every tick from wake through PRECOOL (even a lead window that starts before noon), the lock and the small hours until wake therefore share one parity; the schedule already guarantees wake < bedtime, so no extra validation is needed. STEP 3 validation adds only "the settle window must not cross midnight": `(today_at(bedtime) + timedelta(minutes=fan_settle_minutes)).date() == today_at(bedtime).date()`, compared as instants inside one template (repo lesson: wrapped `HH:MM:SS` strings sort wrong).

Top-level `variables:` pass-through gains one `!input` line per new input (repo rule; board R1-01 on v1.0.3).

### 2.2 Variables (STEP 2a/2c additions, single-lined where they feed comparisons)

- `fan_only_mode = night_mode == 'fan_only'`; `bedtime_target = ideal_temp − prechill_offset if fan_only_mode else ideal_temp`.
- Everything that decides "how far / whether to cool by bedtime" keys on `bedtime_target`: `delta_in = max(0, warmest − bedtime_target)`, `cooling_needed = warmest > bedtime_target or forecast_max > skip_threshold`, `precool_substate` (DRIVE when warmest > bedtime_target), the BEDTIME_LOCK auto-learn `bedtime_error = warmest − bedtime_target`. In `ac_hold` mode `bedtime_target == ideal_temp`, so nothing changes there; in `fan_only` mode the lead term and the learner see the deeper target (no hidden 7.5-minute offset for the shared bias helper to absorb) and a room sitting between the two targets still pre-chills. `maintaining_setpoint`, `effective_drive`, `desired_mode`, `night_fan_mode`, `tolerance` semantics unchanged; the guard keeps `ideal_temp + tolerance`.
- `night_parity` (`odd`/`even`), `fan_assist_tonight`, `night_fans_tonight` (booleans from the selects).
- `interlock_blocked`: any `fan_interlocks` entity missing from the state machine, in `['on','unavailable','unknown']`, or with `last_changed` newer than `now() − interlock_clear_minutes` (`last_changed` = state transitions; an attribute-only update does not restart the hold).
- `lock_ts = as_timestamp(today_at(bedtime) − 1 min)` carried as a float (instants cross the variables boundary as strings); `settle_end_tod = (today_at(bedtime) + fan_settle_minutes).strftime('%H:%M:%S')`; `ac_started_ts = as_timestamp(states[ac_climate].last_changed)` (the unit's off→cool instant; setpoint/fan changes touch `last_updated`, not `last_changed`); `since_ac_start_min = (as_timestamp(now()) − ac_started_ts) / 60`.
- `in_wake_window = wake_tod <= now_tod < wake_tod + 1 min`; `in_fan_settle = lock_tod <= now_tod < settle_end_tod` (starts on the lock tick, never crosses midnight — validated); `in_fan_assist_window = phase == 'PRECOOL' and ac_is_running and since_ac_start_min < fan_settle_minutes`.
- Per fan (rendered inside the fan step, not carried): `fan_touched_ts = as_timestamp(states[fan].last_updated)` — `last_updated`, because a percentage change bumps `last_updated` only (repo note from the dimmer project); `last_changed` moves on on/off transitions alone.
- `night_phase = phase in ['NIGHT_HOLD','DEEP_NIGHT_CHECK','DEEP_HOLD']`.
- `guard_due = fan_only_mode and night_phase and not ac_is_running and warmest_bedroom > ideal_temp + tolerance and now().minute % 5 == 0`. The 5-minute cadence bounds the pathological case of a cloud read that keeps reporting `off` while the unit runs: at most 12 `turn_on` attempts per hour instead of 60, each one notified; in the normal case the fallback lands within 4 minutes of the breach (≈ 0.02 °C of drift).
- `guard_settle_due = fan_only_mode and night_phase and ac_is_running and since_ac_start_min < 15` — the correction window after ANY night start (the guard's, or a manual one): on every tick inside it the blueprint asserts the parked state from LIVE readings, each call only if different: hvac mode → `desired_mode` when `current_hvac_mode` is not `cool`/`dry` (a restored `heat`/`fan_only`/`auto` would "latch" without cooling); setpoint → `maintaining_setpoint` only when `|current_setpoint − maintaining_setpoint| > correction_step + 0.1` (a deep-night nudge sits exactly `correction_step` away and is never fought); fan → `night_fan_mode` when `current_fan` is known and differs. Uses the existing STEP 2a reads (`current_hvac_mode`, `current_setpoint_known`, `current_fan` with its `'unknown'` normalisation), so there is no wait, no timeout path and no null read-back to guard.

### 2.3 Fan write rule (the whole deconfliction, one rule)

A fan is commanded only when ALL hold: the fan is configured; its state is not `unavailable`/`unknown`; it is not already at the wanted percentage-and-state (`state_attr(fan, 'percentage') | int(-1)` — the repo idiom; a missing attribute is `None`, never a Jinja `Undefined` that would kill the whole variables step); if it is in `interlocked_fans`, `interlock_blocked` is false; and **nobody has touched it since the reference instant** — `fan_touched_ts < reference_ts` (i.e. `last_updated` older than the reference) where the reference is `lock_ts` for the night setting and `ac_started_ts` for the pre-cool setting. The rule is evaluated TWICE per command: once in STEP 2c to build the due list, and again LIVE inside the `repeat` iteration immediately before the service call (same conditions on fresh `states()` / `state_attr()` / interlock reads), so an adult entering the room or the cutoff switching the fan off between the snapshot and the call cancels that command. The fan step runs BEFORE the AC dispatch in the tick (no climate call or wait sits between the snapshot and the fan command). Every command passes `percentage` explicitly (`fan.turn_on` with `percentage`; `fan.turn_off` for the wake option) and carries `continue_on_error: true`, so one cloud failure never aborts the other fans or the rest of the tick. Direction is never written (the seasonal blueprint owns it).

Consequences, all by construction: the blueprint never re-asserts a fan that the safety cutoff switched off (the cutoff's `turn_off` updates `last_updated`, so the fan counts as touched); it never commands the kids fan while an adult stands under it (interlock); it never undoes Martin's manual change after the lock (touched); a successful command updates `last_updated`, so a fan is written at most once per reference instant — the per-tick evaluation is edge-triggered by the guard, not by memory. If the Tuya cloud reports late, the identical command may repeat on the next tick until the state lands or the settle window closes (bounded, idempotent on the device). There is no retry outside the settle windows.

### 2.4 Phase behaviour

- **DAY_OFF** — unchanged. When `fans_at_wake = off`: on the wake-window tick, `fan.turn_off` every configured fan that is `on` (no interlock or touched check — off is always safe).
- **PRECOOL** — AC logic unchanged except the DRIVE/HOLD threshold is `bedtime_target`. Fan-assist: while `in_fan_assist_window and fan_assist_tonight`, apply the fan write rule with target `precool_fan_percentage` and reference `ac_started_ts`. The window starts the tick after the AC start (the start tick captured `ac_is_running = false`; the fan follows one minute later, which also lets the Tuya cloud settle).
- **BEDTIME_LOCK** (one tick) — if `ac_is_running`: `ac_hold` = v1.0.3 sequence unchanged (mode / maintaining setpoint / night fan, each only if different) + auto-learn write. `fan_only` = the same three park calls (mode, maintaining setpoint, night fan — each only if different; usually 0 calls because the pre-chill HOLD already parked the unit, up to 3 if the lock lands in DRIVE), then **`climate.turn_off` — only if the warmest room is NOT already above `ideal_temp + tolerance`** (otherwise the guard would fire on the next tick and the night pays an off + on for nothing; on such a hot night the unit simply stays on, i.e. `ac_hold` behaviour), then the auto-learn write with `bedtime_target`. The LG's next `turn_on` restores exactly the parked state (research C5; verified on our unit 09-08).
- **Fan settle window** (`in_fan_settle`, from the lock tick to `bedtime + fan_settle_minutes`, spans NIGHT_HOLD): when `night_fans_tonight`, apply the fan write rule with target `night_fan_percentage` and reference `lock_ts`. This is how the kids fan gets its night speed once the bedtime routine ends and the PIR clears, without a loop and without overriding a manual off.
- **NIGHT_HOLD / DEEP_NIGHT_CHECK / DEEP_HOLD** — **Guard:** when `guard_due`, a bare `climate.turn_on` (one beep; the unit comes back on the parked maintaining setpoint + night fan) plus the notice. Nothing else happens on that tick — no wait, no read-back. **Guard settle:** on the following ticks, while `guard_settle_due` (≤ 15 min after the start), the parked state is asserted from live readings as defined in §2.2 — normally zero commands, one to three only when the restore was wrong (stale park, or a `heat`/`fan_only`/`auto` mode left from manual use days earlier, which `ac_is_running` would otherwise latch without any cooling). A restore that the cloud reports late is corrected on a later tick inside the window instead of being lost. The running unit is the latch: on every later tick `ac_is_running` is true, so the guard cannot fire again, the existing DEEP_NIGHT_CHECK nudge applies as in v1.0.3 (it can add one `set_temperature` if the drift is still outside tolerance in the 01:00 window; the settle correction leaves a nudged setpoint alone because it sits exactly `correction_step` from maintaining), and DAY_OFF switches the unit off at wake. In `ac_hold` mode the guard is dead code (the unit is already running) and the settle window only ever sees the parked state.
- **Notices (STEP 7d, new):** `bedroom_precool_fan_skipped` on the last settle-window tick for a configured fan that is untouched, not at its night percentage AND either interlock-blocked or unavailable (i.e. the set of fans that could not be written; a fan that is merely due on that last tick is commanded, not reported) — informational, no retry. `bedroom_precool_guard_fired` when the guard sends its `turn_on` (trip time, warmest reading, threshold). Both gated on `enable_notifications`.
- **Debug dump (STEP 8):** adds night_mode, bedtime_target, night_parity, fan_assist_tonight / night_fans_tonight, interlock_blocked, guard_due, and per fan: state, percentage, `last_changed` vs lock.

### 2.5 Restart, cloud and edge cases

- **HA restart at night:** the tick recomputes from live state. AC off + over band → guard fires (correct). AC running → hold. Fans: after a restart a Tuya fan's `last_updated` is either the restart instant (later than `lock_ts` → counts as touched → left alone, the safe direction) or a restored earlier value (→ untouched → the pending night setting is applied once, also correct). Neither case loops.
- **Guard restore state:** `turn_on` brings back whatever the unit was parked in. Every `fan_only` lock on a running night parks it in cool / maintaining / night fan; on a cool-day night (lock no-op) or after manual use the restored state can be anything the unit last had — days old, possibly `heat`. The guard-settle window (§2.2) therefore asserts mode, setpoint and fan from live readings for 15 minutes after any night start; an automatic fallback never heats or blows unconditioned air into a child's room. The LG reports a null setpoint while off, so the `bedroom_precool_guard_fired` notice reports the trip time, the warmest reading and the threshold; the restored and corrected state is on the climate entity's history the next morning.
- **Stale cloud `off`:** if the cloud keeps reporting `off` while the unit runs, `guard_due` stays true; the 5-minute cadence bounds the retries (≤ 12/h, each notified) and the settle window keeps asserting the parked state on the ticks where the unit does read as running.
- **Cutoff-restored speed (known limitation):** if the kids fan is running at the pre-cool/dimmer speed when the safety cutoff fires after the lock, the cutoff's own resume restores THAT speed (21 %) and, being a touch after `lock_ts`, the blueprint never lowers it to 1 %. The night runs at the cutoff's restored speed; Martin's hand or the dimmer "–" hold sets very-low. Accepted: the alternative (treating the cutoff's writes as non-human via `context`) is exactly the context-sniffing the research flagged as unreliable.
- **LG cloud `unavailable`:** STEP 5 stops the tick (unchanged), so a flapping read cannot fire the guard. A stale `off` on a running unit costs at most one no-op `turn_on` beep.
- **Sensor failure at night (STEP 5 stop before the guard):** both bedroom sensors dead → no guard, AC stays off all night. Accepted for v1.1.0 (mirrors the existing "AC runs until sensors recover" asymmetry noted for #19); the notice already fires.
- **Manual AC start during the night** (Martin turns the unit on): `ac_is_running` → the guard stays silent, DAY_OFF turns it off at wake. Manual AC off after a guard trip: the guard may fire once more if still over band — one beep; documented.
- **Cool-day nights** (AC never started): lock is a no-op for the AC; the fan settle window still applies the night percentage if `night_fans_tonight` (fans are cheap and the parity switch can turn them off).
- **Beep budget (fan_only):** lock ≤ 4 (mode, setpoint, fan, off — typically 1: `turn_off`; 3 without the off on a night already over the band); guard nights: `turn_on` 1 + settle corrections ≤ 3 (mode, setpoint, fan — normally 0) + deep-night nudge ≤ 1; worst case in the 01:00 window 5, typical guard night 1–2. `ac_hold` unchanged: lock ≤ 3 (typically 1–2), nudge ≤ 1. These numbers are the ones `requirements_bedroom_precool.md` and the README carry.

### 2.6 Instance, docs, version

- `deploy/bedroom_precool_1779553673971.json`: `night_mode: fan_only`, `prechill_offset: 0.5`, `bedroom_fans: [fan.ceiling_fan_light_v2_2, fan.ceiling_fan_light_v2]`, `interlocked_fans: [fan.ceiling_fan_light_v2]`, `fan_interlocks: [binary_sensor.samuel_samuel_matthew_fanprotection]`, `interlock_clear_minutes: 5` (cutoff hold 3 + 2), `night_fans: all`, `night_fan_percentage: 1`, `fan_assist: off`, `precool_fan_percentage: 21`, `fan_settle_minutes: 45`, `fans_at_wake: leave`; alias v1.1.0. Also assign `fan.ceiling_fan_light_v2_2` (device) to the Master Bedroom area (registry edit, no code).
- Adjacent repo `~/projects/ceiling-fan-hue-blueprint` (no remote): one README line under the kids-fan ownership note — "the Bedroom Sleep Pre-Cool blueprint (Blueprints_Home v1.1.0) may also write this fan, once per transition, never while the cutoff sensor is on or within its hold" — done at deploy time. `requirements_bedroom_precool.md`'s "manual-override handling is a v1.1.0 item" becomes "a v1.2.0 item (#19)".
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

- **Structure tests** (`tests/test_bedroom_precool_structure.py`, rendered chains via `_render_chain`): every new input has a default and a `!input` pass-through; `bedtime_target` = ideal in `ac_hold`, ideal − offset in `fan_only`, and `delta_in` / `cooling_needed` / the DRIVE-HOLD substate / the auto-learn error all key on it; `night_parity` is identical from a pre-noon PRECOOL start through 19:29 and 01:00 of the same night and flips at wake; `guard_due` true only in the three night phases with `fan_only`, AC off, warmest above ideal + tolerance and a 5-minute tick, false once the AC runs (latch); `guard_settle_due` true only while the unit runs within 15 min of its start, and the settle corrections fire on a `heat` restore / a stale 18 °C setpoint / a `high` fan and NOT on a nudged setpoint; the fan write rule (rendered per fan with fakes that carry independent `last_changed` / `last_updated`) is false when the fan's percentage changed after the reference even with an older `last_changed`, when interlocked and blocked (including a sensor that cleared inside the hold, keyed on `last_changed`), when unavailable, when already at target, and true otherwise; a fan `on` with no `percentage` attribute renders (no Undefined); `fans_unset_night` and `fans_due_night` are disjoint on every fixture; the branch walker asserts the BEDTIME_LOCK `fan_only` branch orders mode → setpoint → fan → `turn_off` (gated on `not over band`) → auto-learn and the `ac_hold` branch is unchanged from v1.0.3 (regression pin on the rendered service list); the fan step precedes STEP 6 in the action list, every fan call re-checks live state, carries `percentage` and `continue_on_error`; STEP 3 rejects a settle window crossing midnight; the pre-existing validation test gets the new input in its base context; version + instance pins (instance keys ⊆ schema, `deploy-blueprint.sh --dry-run` green). Suite green.
- **Deploy** via `scripts/deploy-blueprint.sh` before 19:29 CEST on a day Martin picks; instance `on`. **Daytime guard live-verify** (beeps are free by day): temporarily set the instance `bedtime` a few minutes ahead and `ideal_temp` 20 → watch PRECOOL → lock (`set_temperature`/`set_fan_mode` if needed, then `turn_off`, fans → 1 %) → NIGHT_HOLD guard `turn_on` restoring `cool/21/low` → restore the instance. Also one house-meter delta reading of a fan at 1 % (research contested claim on fan draw).
- **Observation ([8], ≥ 2 nights):** 19:29 trace shows the park/off/fan sequence, kids fan set within the settle window after the PIR clears (or the skipped notice), zero guard trips on mild nights, warmest ≤ 24.5 at 06:00, one wake command; 24 h log clean. The A/B protocol (research doc) runs afterwards: `fan_assist: odd` when PRECOOL nights return, `night_fans` parity for the fans' own effect.

## Integration addendum (2026-09-09, merged onto main v1.1.0)

Session #26 Task 6i integrated this branch onto `origin/main`, which shipped a
competing pre-cool v1.1.0 (manual override, helper-range clamp, daily-forecast
backstop, quantised setpoints, `stored_traces: 30`) in the interim. Both
feature sets are kept; the fan coordination re-versions as **v1.2.0** and its
night guard / settle now honour main's override semantics. Resolution rulings:

1. **Version → v1.2.0.** Blueprint name, description (ours leads, main's
   v1.1.0 summary sentence kept verbatim, History line combines both),
   instance alias, and every FAN-feature "v1.1.0" reference (Bedroom Fans /
   Fan Interlock Sensor inputs, "Night Mode & Pre-Chill", "Bedroom Fans — The
   Fan Write Rule", "Experiments" sections, README's two fan bullets, the T2–T5
   test-section headers) bumped to v1.2.0. Main's own v1.1.0 references
   (manual override, helper-range clamp, daily-forecast backstop) are
   untouched — two version identities coexist in the same file by design.
2. **The lock's own off is not a manual off.** `lock_ts` moved from after
   `night_fan_mode` to right after `earliest_turn_on_tod` (depends only on
   `bedtime`), so it is defined before main's `earliest_turn_on_ts` /
   `manual_off`. `manual_off` gained: `and not (fan_only_mode and
   ac_off_since_ts | float >= lock_ts | float and ac_off_since_ts | float <
   lock_ts | float + 180)` — an off stamped within 180 s of the lock tick is
   the blueprint's own park-off, not a person's; a person's off in that same
   180 s window is misread as ours (documented, accepted).
3. **Guard respects a manual off.** `guard_due` gained `and not manual_off` —
   a person who switched the unit off during the night is left alone until
   the next phase boundary, exactly as v1.1.0 does for PRECOOL.
4. **Settle respects a manual setpoint.** `guard_settle_due` gained `and not
   manual_setpoint` — `manual_setpoint` already requires `ac_state_age_sec >=
   120`, so the first two ticks after a start are always ours.
5. **`since_ac_start_min` reused from main's `ac_state_age_sec`.** Both key
   off `states[ac_climate].last_changed` — the same quantity — and
   `ac_state_age_sec` is defined in STEP 2a, before our STEP 2c block, so the
   brief's reuse condition is met: `since_ac_start_min: "{{ ((ac_state_age_sec
   | float) / 60) | round(1) }}"`, one age computation instead of two. (Fix
   round 1 corrected an initial over-caution here: the render-chain test
   harness needed `_windows()`/`_guard()` to derive `ac_state_age_sec` from
   each call's own `now` and `ac_started_ts` — `ac_state_age_sec = now.timestamp()
   - float(ac_started_ts)` — rather than skipping the reuse; done, with the
   existing `ac_started_ts`-keyed fixtures unchanged.) `ac_started_ts` stays
   for the due lists and the assist window, which need the timestamp itself,
   not the age.
6. **Main's lock-services test updated.** `test_precool_commands_are_gated_on_the_override_flags_and_the_boundaries_are_not`'s
   BEDTIME_LOCK sorted service list now includes `climate.turn_off`
   (fan-only's own park-off call, gated on `fan_only_mode` / `warmest_bedroom`
   / `tolerance` — never on the override flags, so the "no manual token"
   assertion still holds).
7. **New rendered tests.** `manual_off` lock-window chain (fan_only exempts
   `lock_ts+60`, not `lock_ts+240`; ac_hold exempts neither — v1.1.0
   unchanged); `guard_due` false under `manual_off=True`; `guard_settle_due`
   false under `manual_setpoint=True`. `_v110_ctx` gained `manual_off=False,
   manual_setpoint=False` (read as already-resolved upstream facts, same
   pattern as `ac_is_running`) and `ac_state_age_sec=0.0` (a placeholder that
   `_windows()`/`_guard()` overwrite from `ac_started_ts` + their own `now`,
   per item 5). `MANUAL_OFF_CHAIN` gained `lock_ts` and `fan_only_mode` (both renderable
   from ctx already present in the existing `_manual_off` fixtures) so the
   new clause has what it needs without touching the fixtures' assertions.

Also folded in per the Step 2 addendum (Task 5 review finding): the
NIGHT-HOLD / DEEP-HOLD phase-table rows, the Beep Budget functional
requirements, and the README beep bullet no longer claim unqualified "zero
commands" — fan_only nights may issue one guard `turn_on` plus up to three
settle corrections.

## Code board 20260909-151815 fixes (2026-09-09, cycle 1)

Task 7 actioned the code-time board's cycle-1 findings (F1-F10) against v1.2.0
(the integrated onto-main state above). Each finding, its fix, and the RED
test that reproduced it before the change:

1. **F1 (P0, R2-04) — `lock_ts` re-anchors to tonight after midnight, killing
   the guard.** `lock_ts` gained the same night-start day offset as
   `earliest_turn_on_ts`: `as_timestamp(today_at(bedtime) -
   timedelta(days=(1 if now().strftime('%H:%M:%S') < wake_time else 0),
   minutes=1))` — the inline `now()`/`wake_time` idiom `earliest_turn_on_ts`
   already uses, not the brief's literal `now_tod`/`wake_tod` snippet (both
   are defined earlier in the file and would work too, but the inline form
   needed no new keys in the pre-existing `_manual_off` test fixtures that
   build their own raw context dict without those two variables). Without
   the offset, at 01:00 `lock_ts` rendered TONIGHT's future 19:29, the lock's
   own 19:29:30 off fell outside `manual_off`'s exemption window, and
   `guard_due` stayed False for the rest of the night — reproduced exactly
   in `test_rendered_guard_is_alive_after_midnight_on_a_fan_only_lock_night`
   (RED before the fix) — and the same bug fired a false STEP 7e "Manual
   Override" notice 00:00-01:00 on every fan-only night, now also asserted
   False in `test_rendered_manual_off_exempts_only_the_lock_s_own_off_in_fan_only`.
2. **F2 (P1, R2-02) — the guard must start the unit in the cooling mode.**
   STEP 6a now issues `climate.set_hvac_mode` with `hvac_mode: "{{
   desired_mode }}"` UNCONDITIONALLY right after `climate.turn_on` (2 beeps
   per trip) — a bare `turn_on` alone restores whatever mode the unit last
   held, and the STEP 2 mode read is stale on the guard tick anyway, so the
   call can't be conditioned on a mismatch. `settle_mode_due` (STEP 6b)
   stays for the one case it still covers: a manual night start that never
   went through the guard.
3. **F3 (P1, R2-01) — an interlocked fan that comes on under an active
   interlock is switched off.** New STEP 2c list `fans_unsafe_on`: every fan
   in `interlocked_fans` whose state is `on`, whose `last_updated` is within
   the last 120 s, and while at least one interlock sensor actively reads
   `on` (only `on` — not unavailable/unknown/the clear hold). STEP 5c
   iterates it with `fan.turn_off` FIRST, before any due-list write — the
   live re-check inside the due-list repeats cannot cancel a Tuya command
   already 10-60 s in flight.
4. **F4 (P2, R2-05) — a mode transition or restart must not reopen fan
   assist against a manual off.** `in_fan_assist_window` gained `and
   (as_timestamp(now()) - (automation_up_since_ts | float)) > 600` — the
   same 600 s restart-grace convention `manual_off` already uses.
   `automation_up_since_ts` is defined in STEP 2c before this clause.
   Residual, documented: a bare cool<->dry transition inside a long-up
   automation still moves `ac_started_ts`; both `dry` mode and `fan_assist`
   default off.
5. **F5 (P2, R2-06) — pin the live re-check by rendering it; pin the fan-step
   position by parsed order.** New
   `test_rendered_live_recheck_blocks_unsafe_commands` renders each
   `fan.turn_on` call's live condition (fetched from the walker output, not
   duplicated) against `_fan_env` fakes for PIR-on, PIR-cleared-inside-the-
   hold, touched-after-the-reference, already-at-target, and missing cases
   (all False) and a clean case (True), for both the night and pre-cool
   templates. The old `text.index("STEP 5c") < text.index(...)` string check
   is replaced by a parsed-order check over `bp["action"]`: the top-level
   step containing a `repeat.for_each` (the fan step), the step containing
   `stop: "Vacation active"`, the step containing `stop: "AC entity
   unavailable"`, and the step containing a nested `phase == 'DAY_OFF'`
   condition (the dispatch), asserting `vacation < fan < validation <
   dispatch`.
6. **F6 (P2, R2-03) — ACCEPTED, documented only.** A person's off inside
   `[lock_ts, lock_ts + 180)` on a fan-only night where the lock did not
   itself switch the unit off (already over band) is misread as the
   blueprint's off; the next guard tick may switch it back on once, after
   which a second manual off is respected. Bounded: a manual off stamped
   AFTER `lock_ts + 180` is respected until wake; a stateless blueprint has
   no ownership bit to disambiguate the two within that first 180 s window
   (superseded wording — see cycle 2 G4 below, which replaces the earlier
   "self-healing" characterisation with the honest one-line workaround).
   Documented in the requirements' Night Mode & Pre-Chill section and the
   README beep bullet — no code change.
7. **F7 (P1, R1-02/R1-03) — the settle must not fight the QUANTISED
   deep-night nudge.** New STEP 2c variables `night_hold_setpoints` (the
   list `[maintaining, down-nudge, up-nudge]`, quantised EXACTLY like
   `known_setpoints` — `(v | int) if ac_temp_step | float >= 1 else v`, each
   clamped to `ac_min_temp`/`ac_max_temp`) and `setpoint_is_night_hold`
   (true when `current_setpoint` is within 0.1 of any of them, with the same
   "non-list arrives -> treat as known" guard as `setpoint_is_known`).
   `settle_setpoint_due` is now `guard_settle_due and current_setpoint_known
   and not setpoint_is_night_hold` — a stale DRIVE park (18 on this unit)
   isn't in that list and is still corrected. On a >= 1-degree-step unit the
   old `> correction_step + 0.1` band compared against the unquantised
   19.5, so it fired on the device's actual 19 and STEP 6b re-sent 21 the
   tick after DEEP_NIGHT_CHECK set 19 — an alternating loop whenever the
   settle window overlapped 01:00. The pre-existing guard-settle test now
   derives its nudge fixture from the rendered `night_hold_setpoints` (R1-03)
   instead of a hand-written 19.5.
8. **F8 (P2, R1-05) — extend the dependency-order pin.**
   `test_override_variables_are_defined_in_dependency_order` now also
   asserts `lock_ts < earliest_turn_on_ts`, `fan_only_mode < manual_off`,
   and `night_hold_setpoints < settle_setpoint_due` — HA's chainable
   Undefined would turn an unordered reference into a silent `0.0` rather
   than an error.
9. **F9 (P3, R1-06) — requirements formula blocks.** The Prediction Model
   and Auto-Learn code blocks in `requirements_bedroom_precool.md` now read
   `bedtime_target` (not `ideal_temp`) in `delta_in`, the `cooling_needed`
   gate, and `bedtime_error`, with a `bedtime_target = ideal_temp -
   prechill_offset (fan_only) | ideal_temp (ac_hold)` definition line added
   above the block; `delta_out`'s `ideal_temp` is untouched (by design —
   the outdoor lead term is not pre-chill-relative).
10. **F10 (P3, R1-07) — the fan step and its notice must survive an
    AC-unavailable tick.** STEP 5c (the whole `is_real_trigger`-gated block,
    all four repeats as one unit) moved to sit AFTER STEP 4 (vacation) and
    BEFORE STEP 5 (AC/sensor validation) — a cloud outage or a missing
    bedroom sensor no longer silently skips every fan write and the
    "reported once" notice for the whole settle window. The former STEP 7f
    notice is folded into the end of STEP 5c's sequence (same condition,
    same `notification_id`) and the standalone STEP 7f block is deleted; no
    other step renumbered. New STEP order: `4 < 5c < 5 < 5b < 6 < 6a < 6b <
    7a...7e < 8`.

Beep numbers reconciled everywhere (blueprint description, requirements
phase table + Beep Budget, README, this addendum): fan_only lock stays
`<= 4` (typically 1); guard nights are `turn_on 1 + set_hvac_mode 1 +
settle <= 2 (setpoint, fan) + nudge <= 1` -> typical 2, worst 5 (same
worst-case ceiling as before F2, different composition); `ac_hold`
unchanged.

## Code board 20260909-151815 fixes (Task 8, cycle 2)

Task 8 actioned the code-time board's cycle-2 findings against the cycle-1
state above, with R1's cycle-2 leg amendments overriding the pre-amendment
brief where they overlap (G1, G2). G5 was void (the placeholder the
amendments filled). Each item, its fix, and the RED test that reproduced it
before the change (G6/G8 are test-only additions — the underlying render
logic was already correct, so no RED was reachable for those two):

1. **G1 (now P1 — R2C2-05 ≡ R1C2-01 cross-family, + R1C2-02, R1C2-08).**
   The cycle-1 `fans_unsafe_on` cut fired on EVERY real tick, 24/7, while an
   interlock sensor read `on`, and a person's deliberate `on` restarted its
   120 s window each time — so a deliberate fan start was cut every minute
   for as long as the interlock stayed on, defeating the safety cutoff's
   own documented "manual override wins" contract
   (`~/projects/ceiling-fan-hue-blueprint/fan_safety_motion_cutoff.yaml`).
   Rewritten so the cut can ONLY cancel a write THIS blueprint's own STEP 5c
   could have issued in the CURRENT window: gated on `(in_fan_settle or
   in_fan_assist_window)` (outside those windows the list is always `[]`);
   iterates `bedroom_fans` filtered to `interlocked_fans` (the "blocked"
   idiom, R1C2-08) so a fan listed only in `interlocked_fans` is never
   touched; keys on the fan's ON-TRANSITION (`last_changed`, NOT
   `last_updated` — R1C2-02) being newer than the active window's own
   reference (`lock_ts` while settling, `ac_started_ts` while assisting)
   AND within the last 120 s. Reproduced in
   `test_rendered_fans_unsafe_on_cuts_only_this_blueprints_own_in_flight_write`
   (RED before the fix, cases (a)-(h) from the amendment).
2. **G2 (R2C2-02 + R1C2-04) — implement the restart rule AND document the
   flap residual honestly.** `in_fan_assist_window`'s cycle-1 600 s
   restart-grace only DELAYED the reopen — a restart later in the same
   adoption window still re-opened assist against a manual off. Replaced
   with: the automation must already have been running when TODAY's
   adoption window opened — `(automation_up_since_ts | float) <
   (earliest_turn_on_ts | float)` (main's variable, already defined earlier
   in the same STEP 2c block). Reproduced in `test_rendered_fan_windows`
   (RED before the fix: a restart at 16:00, more than 600 s before the
   17:30 check but still inside the adoption window that opened at 15:30,
   used to leave assist open). Documented residual (requirements
   Experiments section, this addendum, the `in_fan_assist_window`
   comment): `ac_started_ts` is the climate entity's `last_changed`, which
   ALSO moves on an `unavailable -> cool` cloud flap or a `cool <-> dry`
   transition — either can re-open the 45-minute window ONCE with the new
   reference and re-command a fan a person switched off after the ORIGINAL
   start (one 21 % command, interlock still honoured). Accepted: `fan_assist`
   and `dry` mode both default off; the experiment runs on chosen nights
   only.
3. **G3 (P1 residual R2C2-03 -> mitigation) — heat backstop for fan-only
   nights.** New STEP 2c variable `heat_backstop_due = fan_only_mode and
   night_phase and ac_is_running and current_hvac_mode == 'heat'`
   (single-lined) and a new top-level STEP 6c right after STEP 6b: when
   `is_real_trigger and heat_backstop_due`, an unconditional
   `climate.turn_off` — a heater is never the fallback in a child's
   bedroom; the guard's own `turn_on` + `set_hvac_mode` at its next
   5-minute tick restores cooling. Bound: worst case under a cloud that
   lets `set_hvac_mode` fail is <= 1 minute of heat per 5-minute cycle, 3
   commands per cycle (backstop `turn_off` + guard `turn_on` + guard
   `set_hvac_mode`), visible in the trace. Does NOT close R2C2-03: a stale
   cloud `off` while actually heating is unobservable from this automation
   — the residual stays recorded for the operator. Reproduced in
   `test_rendered_heat_backstop_due_only_for_heat_at_night_in_fan_only_while_running`
   and `test_heat_backstop_is_exactly_one_turn_off_gated_on_heat_backstop_due`
   (both RED before the fix — `heat_backstop_due` did not exist).
4. **G4 (R2C2-04) — honest wording for the accepted lock-window misread
   (was cycle-1 F6).** Requirements "Night Mode & Pre-Chill", the README
   beep bullet, and this addendum's F6 entry above no longer claim "one
   beep, self-healing". Replaced with: a person's off stamped inside
   `[lock_ts, lock_ts + 180)` on a fan-only night is treated as the
   blueprint's own off; the guard may switch the unit back on at its next
   5-minute tick (two commands: `turn_on` + cooling mode). A manual off
   stamped AFTER `lock_ts + 180` is respected until wake. To keep the unit
   off in that first three minutes, switch it off again after 19:33 (three
   minutes past the default 19:30 bedtime's 19:29 lock). Docs only, no
   code change.
5. **G6 (R1C2-03, tests) — pin `night_hold_setpoints` against the rendered
   `deep_target_setpoint`.** New
   `test_rendered_night_hold_setpoints_match_the_rendered_deep_target_setpoint`
   mirrors `test_rendered_known_setpoints_are_the_values_the_device_holds`'s
   method: for each drift direction and both `ac_temp_step` 1 and 0.5, it
   renders the REAL production `deep_target_setpoint` template (not a
   hand-written expected list) and asserts the result is in the rendered
   `night_hold_setpoints`, plus the non-list guard case for
   `setpoint_is_night_hold` (mirroring
   `test_rendered_setpoint_is_known_treats_a_non_list_as_known`). No code
   change — the two templates already used identical clamp/quantise
   formulas; this closes a test-methodology gap (hand-written expected
   values vs. a realized-output assertion), not a behavioural bug.
6. **G7 (R1C2-05, R1C2-06, docs) — remove the two leftover "one-beep guard"
   sentences** (README's beep bullet, requirements' Night Mode & Pre-Chill
   Night-guard sentence — both were stale after F2 made the guard two
   commands, `turn_on` + `set_hvac_mode`) **and rewrite the requirements
   settle sentence** to the night-hold-list wording: the setpoint check
   "leaves every night-hold setpoint — maintaining and the two quantised
   nudges — alone"; the mode check "matters only after a manual night
   start" (a guard-triggered start already forces cooling mode). Docs only,
   no code change.
7. **G8 (R1C2-07, tests) — pin the fan-skipped notice's position and
   gate.** `test_fan_skipped_notice_fires_once_on_the_last_settle_tick`
   extended to assert the notice's condition path includes `{{
   is_real_trigger }}` and that its top-level action-list index equals the
   fan step's own index (the step containing the `for_each` repeats),
   strictly before the STEP 5 "AC entity unavailable" validation stop. No
   code change — the notice was already folded inside STEP 5c by cycle-1
   F10; this closes a coverage gap in the F10 regression pin.

STEP order after G3's new STEP 6c: `4 < 5c < 5 < 5b < 6 < 6a < 6b < 6c <
7a...7e < 8` (6c added between 6b and 7a; no other step renumbered).

### Accepted residual — operator decision, 2026-09-09 (board finding R2C2-01)

Codex raised, and Opus confirmed in shape, that no in-blueprint check can
cancel a `fan.turn_on` already in flight to the Tuya cloud (10–60 s delivery):
if an interlock sensor trips inside that lag, the fan can run at its night
speed (1 %) for about one tick plus delivery latency before `fans_unsafe_on`
switches it off on the next tick, and that cut cannot restore a cutoff resume
the late write cancelled. Its recommendation was to stop writing the shared
kids-room fan entirely until a cutoff-owned command path exists.

The operator (Martin) adjudicated on 2026-09-09: **both fans stay in
`bedroom_fans`; the residual is accepted.** Reasoning recorded with the
decision — the interlock and its clear hold block every ordinary case, and
the exposure is one tick at the lowest fan speed. The finding is kept in the
board report at P1 (a safety finding is never killed by a vote); this is an
accepted risk, not a refutation. The escape hatch is one instance key:
removing `fan.ceiling_fan_light_v2` from `bedroom_fans` stops every write to
that fan while the code path stays in place.
