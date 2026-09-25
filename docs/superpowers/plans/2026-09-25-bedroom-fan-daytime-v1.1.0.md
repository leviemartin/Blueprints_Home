# Bedroom Fan Daytime v1.1.0 — 08:00 off + 2-hour daytime run limit (Session #42, epic #39)

```text
Driver: claude
Entry: C (mid-epic change; direction settled by Martin 2026-09-25)
Stakes: standard (Martin 2026-09-25: off-only timer)
Trigger: simplify the deployed v1.0.0 (Session #40) at Martin's request — fewer moving parts, same off-only safety property
Dispatch ledger: /home/martin/AI/reviews/bedroom-fans-v11-20260925/ledger.json
Dispatch allowance: 24
Review allowance: 3
TCB baseline: /home/martin/AI/reviews/tcb-baseline-bedroom-fans-v11-20260925.txt
TCB aggregate: 0a93e62d511a30b295befd7d06dea361cb5e87982d30ccaae1e0e984340ce8ad
TCB_EXTRA: /home/martin/AI/projects/Blueprints_Home/scripts/deploy-blueprint.sh (unchanged)
Declared TCB changes: none
Boundaries: none (off-only; the only concurrency is fan.turn_off against the unchanged cutoff, dimmer, pre-cool and seasonal writers — an off can never cancel the cutoff's pending resume)
Plan author: orchestrator (Opus/high)
```

## Behaviour (Martin, 2026-09-25 — governing)

1. At 08:00 any running bedroom fan is switched off.
2. Between 08:00 and 18:00 a fan that is turned on (by anyone or anything) runs for `max_run_minutes` (120), then is switched off.
3. From 18:00 to 08:00 nothing is switched off; pre-cool and manual control work as today. A fan started at 17:00 keeps running past 18:00.
4. Removed from v1.0.0: nap toggle lifecycle, dimmer gestures, gate, vacancy/activity sensors, config notice. The nightlight instance drops `nap_toggle` (the v1.3.0 blueprint with the input empty is exactly the v1.2.0 fixed 12:30–15:30 window — already tested). Helpers `input_boolean.kids_nap` and `input_datetime.kids_nap_since` are deleted after the instances no longer reference them.
5. Off-only: the blueprint's only fan service is `fan.turn_off`.

## Contract — bedroom_fan_daytime.yaml v1.1.0

- **Inputs:** `fan` (required); `day_start` 08:00:00; `day_end` 18:00:00; `max_run_minutes` 120 (number, 15–600). All through top-level `variables:`.
- **Triggers:** `time_pattern` minutes `/1` (id `tick`); `homeassistant` start (id `ha_start`). No state triggers. `mode: queued`, `max: 10`, `max_exceeded: silent`.
- **Predicates** (one action-level `variables:` step, defined in this order, instants as unix timestamps; HA renders each key separately and literal_evals it, so no State objects cross keys):
  - `is_real_trigger = trigger is defined and trigger.id is defined and trigger.id == 'tick'` (ha_start and a manual Run write nothing).
  - `now_ts`; `day_start_ts`, `day_end_ts` via `as_timestamp(today_at(...))`; `in_day = day_start_ts <= now_ts < day_end_ts`.
  - `fan_state` = the fan's state string, `'absent'` when not in the state machine; `fan_on = fan_state == 'on'`; `on_since_ts` = `as_timestamp(states[fan].last_changed)` when present else 0 (for a fan reading on, `last_changed` is the instant it turned on; a speed change does not move it).
  - `from_night = on_since_ts < day_start_ts` (running since before 08:00 today); `run_expired = now_ts - on_since_ts >= max_run_minutes*60`.
  - `off_due = is_real_trigger and in_day and fan_on and (from_night or run_expired)`.
- **Action:** one `choose`; branch condition re-checks live: `off_due and is_state(fan, 'on') and day_start_ts <= as_timestamp(now()) < day_end_ts`; sequence: exactly one `fan.turn_off` (target `{{ fan }}`, `continue_on_error: true`). Nothing else; no notifications, no helpers, no wait/delay/repeat.
- **Instances:** `deploy/bedroom_fan_daytime_kids.json` (id `bedroom_fan_daytime_kids`, fan.ceiling_fan_light_v2) and `_master.json` (id `bedroom_fan_daytime_master`, fan.ceiling_fan_light_v2_2); inputs = `fan` only (defaults for the rest); aliases "… fan daytime v1.1.0"; `stored_traces` 60.

## Acceptance examples (tests pin each)

1. Night fan at 08:00: on since 19:29 yesterday → 08:00 tick → one `fan.turn_off`. 07:59 → nothing.
2. Fan turned on 07:50 → still `from_night` → off at 08:00.
3. Fan turned on 10:00 → no off at 11:59; off at 12:00.
4. Fan turned on 16:30 → off at 18:29? No: 17:59 no off; 18:00 and later nothing (window closed); runs into the evening.
5. Fan on at 17:00 speed changed at 17:30 (last_changed unchanged) → nothing before 18:00.
6. Cutoff during a run: on 10:00, cutoff off 11:00, resume 11:03 → on_since 11:03 → off at 13:03 (documented: a resume restarts the 2 h).
7. Tuya flap: unavailable 10:30 → on 10:32 → on_since 10:32 → off at 12:32 (a flap only delays).
8. Fan off, unavailable, unknown or absent → no command, no error.
9. `ha_start` and manual Run → no service call even when `off_due` conditions hold.
10. Live re-check: snapshot due but the fan read off meanwhile, or the live clock crossed 18:00 → no command.
11. Master and kids instances independent.
12. Nightlight: instance without `nap_toggle` → fixed window (existing v1.3.0 tests cover the empty-input path).

## Tasks

- **T1 (delegate, Opus/high, worker; route reason: settled standard coding on a safety-adjacent live automation — Opus rather than Sonnet by orchestrator choice):** rewrite `bedroom_fan_daytime.yaml` to v1.1.0, rewrite `tests/test_bedroom_fan_daytime_structure.py` for this contract (RED first; keep the strict fakes and the per-key literal_eval model; structure test that the only fan service is one `fan.turn_off`; service allowlist = {`fan.turn_off`}), update `deploy/bedroom_fan_daytime_{kids,master}.json`, `deploy/nightlight_1766142134972.json` (drop `nap_toggle`), `tests/test_bedroom_fans_deploy_consistency.py` (remove nap/gate/button assertions; assert the nightlight instance has no `nap_toggle` and no daytime instance input beyond `fan`), `requirements_bedroom_fan_daytime.md` (v1.1.0 contract, residuals: resume/flap restart the timer; evening runs), README daytime section. Acceptance: full suite green; dry-runs for daytime (2 instances) and nightlight pass; `grep -c "fan\.turn_on\|set_direction\|set_percentage" bedroom_fan_daytime.yaml` = 0.
- **T2 (orchestrator):** standard code review — one fresh Opus leg, combined correctness/security/edge charter, via `claude-leg.sh`.
- **T3 (command, Martin authorized the deploy flow):** PR, merge; deploy blueprint + both instances (script migrates them), nightlight instance; then run HA `search/related` for both helpers and remove any remaining reference (code review R1-02), delete them via WS (`input_boolean/delete`, `input_datetime/delete`) and verify they are gone; rollback = recreate both helpers (no initial), redeploy v1.0.0 from 14ae934 (`git show 14ae934:bedroom_fan_daytime.yaml` + its instance JSONs) and the 14ae934 nightlight instance with `nap_toggle` (R1-01).

## Stage 8 observation (≥ 3 days)

Measured from logbook/history (fan off transitions whose context parent is the automation run), not traces — 60 traces cover only the last hour (R1-03). Every morning both fans off at 08:00 (± 1 min + Tuya lag) when they were on; any daytime manual run switched off 2 h after switch-on; zero daytime-blueprint fan calls 18:00–08:00; pre-cool's 19:29 write lands; no errors in traces. Session #40's observation is closed as superseded by this session.

## Decided by orchestrator

1. `on_since` = the fan's `last_changed` while on; cutoff resumes and Tuya flaps restart the 2 h (documented, fail toward longer run, never an on).
2. The nightlight blueprint stays v1.3.0 (empty toggle = v1.2.0 behaviour); only the instance changes.
3. No notifications in v1.1.0.
4. Instance ids unchanged so the live automations are migrated in place; entity ids stay `automation.kids_room_fan_daytime_v1_0_0` / `automation.master_bedroom_fan_daytime_v1_0_0` (alias change does not rename).
