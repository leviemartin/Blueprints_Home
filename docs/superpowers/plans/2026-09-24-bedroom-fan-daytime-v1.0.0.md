# Bedroom Fan Daytime v1.0.0 — vacancy-off, parent-signalled nap, manual-change detector, pre-cool v1.3.0, nightlight v1.3.0 — Implementation Plan (epic #39, session #40)

> **Status: planned 2026-09-24 — stage 4 design gate pending (high-risk). No task started.**

```text
Driver: claude
Entry: A
Stakes: high-risk
Trigger: physical safety — a second automatic starter and a stop-reverse-restart sequence on a head-height ceiling fan above a sleeping child, coexisting with the safety cutoff whose pending resume any fan.turn_on cancels — plus a new shared trust point: the per-fan since/stamp helper records written by the detector and read by two writers (pre-cool and the daytime blueprint), where a wrong "not manual" verdict lets pre-cool write 1 % over a person's change inside its settle window.
Dispatch ledger: /home/martin/AI/reviews/bedroom-fans-20260924/ledger.json
Dispatch allowance: 24 (5 native used at planning time, including the plan dispatch 74b2562c)
Review allowance: 12 (0 used; 4 required: design R1+R2, code R1+R2)
TCB baseline: /home/martin/AI/reviews/tcb-baseline-bedroom-fans-20260924.txt
TCB aggregate: 1fe8932ea50f3810179840963bf5082c2538f3577772b6b2c4fde24e37b7745b
TCB_EXTRA: /home/martin/AI/projects/Blueprints_Home-bedfans/scripts/deploy-blueprint.sh (STACKB_DRIVER=claude on every verify)
Declared TCB changes: 8aa081a95f27cc5ea807c3c6f4e1a32ca654f906bcd36b7c039166288af36bf6 /home/martin/.claude/agents/stackb-discovery.md
Boundaries:
  trust boundaries — (1) the per-fan record helpers input_datetime.*_manual_since (written only by the detector) and input_text.*_expected (written only by pre-cool and the daytime blueprint), a single-slot "latest writer" register that two writers and one detector share; (2) the Tuya cloud state feed, the only feedback channel for every fan command, with a 10–60 s lag and availability flaps; (3) the safety cutoff automation, authoritative and unchanged, whose resume any turn_on cancels.
  concurrency paths — seven actors on the kids fan (cutoff mode single with a 3-min hold; seasonal direction mode single; Hue dimmer mode restart; pre-cool 1-min tick; nightlight; the new daytime blueprint mode restart with state triggers; the new detector mode queued); pre-cool and daytime stamping the same input_text (windows disjoint except fan-assist, resolved by the ownership rule); two parallel execution workers in isolated worktrees; the detector classifying events that the writers' own commands produce.
  authorization steps — Martin authorizes: the temporary `ideal_temp` lowering on the kids instance during live step c and its restore; creation of five helpers in the live HA (stage 8 step 1); saving four blueprint versions and creating four new automations; redeploying the two live instances (pre-cool, nightlight); every live actuation of the real fans during verification a–e and any HA restart used for probe e; flipping the kids instance from cooling_only to both_with_reversal (step d); commit, push, PR merge.
Plan author: Claude driver: discovery-model subagent
```

**Governing spec:** the approved discovery brief `/home/martin/AI/reviews/bedroom-fans-20260924/discovery-phases/d1-fans-occupancy-nap-resolved-brief.md` (sha d8c5a274…, canonical Epic #39 comment); fuller non-authoritative wording in `discovery-r3-full-evidence.md` next to it. Task 0 copies the brief bytes into `docs/superpowers/specs/2026-09-24-bedroom-fan-daytime-v1.0.0-discovery-brief.md` so the repo carries its spec. **Unresolved product choices:** none. The seven refinements listed under the pre-gate consistency check are implementation choices; Martin may revert any of them before the design board.

**Baseline (2026-09-24):** worktree `/home/martin/AI/projects/Blueprints_Home-bedfans`, branch `feat/bedroom-fan-occupancy-nap` at `ac0ce83` = `main`, clean. Live: bedroom_precool.yaml v1.2.1 (instance 1779553673971), nightlight.yaml v1.2.0 (instance 1766142134972, alias "… v1.2 (Samuel)"), the cutoff (hold 3 min), seasonal (coast 4 s, toggle input_boolean.samuel_fan_winter_mode) and dimmer (Off = event.baby_room_button_4, + = _2, − = _3, gate light.kids_room_gate, speeds 21/1) instances as saved under `~/AI/reviews/bedroom-fans-20260924/overlap/`. Task 0 records the repo suite count and confirms the two existing dry-runs pass before any worker starts.

**Design gate:** required (high-risk): pre-gate consistency check → batched question to Martin → `triple-check` → `convene-board` with R1 Fable/xhigh (trial gate 2 of 5, `r1-model: fable`; Opus/high only as the policy fallback) and R2 fresh Codex security. **Code gate:** R1 fresh Opus/high + R2 fresh Codex security. **Deploy:** stage 8 with `<!-- observe:open -->` on Session #40.

## Shared contract (every task, every worker brief repeats the parts it touches)

### C1. Helpers (HA configuration, created in stage 8, never by a blueprint)

| Entity | Type | Written by | Read by |
|---|---|---|---|
| `input_boolean.kids_nap` | toggle | daytime kids instance (N); Martin via dashboard | N, nightlight (T) |
| `input_datetime.kids_fan_manual_since`, `input_datetime.master_fan_manual_since` | date + time | the fan's watcher (M) only | P, N |
| `input_text.kids_fan_expected`, `input_text.master_fan_expected` | max 255 | P and N only | M, P, N |

Consumers read the since instant as `state_attr(<since>, 'timestamp') | float(0)` (the helper's own unix-seconds attribute; never `as_timestamp(states(...))`, whose naive-string parse is timezone-ambiguous). A helper that is absent from the state machine or `unavailable`/`unknown` makes the record unavailable: the consumer skips every command to that fan and raises one fixed-id notice (`…_record_missing`); it never issues an unstamped command.

### C2. Stamp format and writer invariant

```text
<writer>|<state>|<pct>|<dir>|<ts>
writer ∈ {precool, daytime}; state ∈ {on, off}; pct = integer percentage or *; dir ∈ {forward, reverse, *}; ts = unix seconds (int) at stamping
examples: precool|on|1|*|1790000000   daytime|off|*|*|1790000600   daytime|off|*|reverse|1790000660 (direction intent)
```

Writer invariant ("no stamp, no command"): the writer calls `input_text.set_value` on the fan's stamp helper immediately before every `fan.turn_on`, `fan.turn_off` and `fan.set_direction`, including its own safety cut; the stamp write carries no `continue_on_error`, so a failed stamp aborts the run before the command; a fan whose record is unavailable is skipped with the notice. A stamp with fewer than five fields, an unknown writer or a non-numeric ts is "no stamp". `*` means "not asserted".

### C3. Consumer predicates (exact definitions; variable names are the test names' vocabulary)

- `record_ok`: both helpers exist and are not `unavailable`/`unknown`.
- `since_ts`: the since helper's timestamp attribute, 0 when unset.
- `stamp_*`: parsed latest stamp (`stamp_writer`, `stamp_state`, `stamp_pct`, `stamp_dir`, `stamp_ts`), or "no stamp".
- `stamp_matches`: the fan's live state equals `stamp_state`, and its live percentage equals `stamp_pct` when asserted. **Direction is not part of ownership** (a seasonal flip keeps a fan ours; direction correctness belongs to the reversal envelope). Direction is matched only by the watcher's own-write rule.
- `ours` (per writer W): `record_ok` and `stamp_writer == W` and `stamp_matches` and `since_ts < stamp_ts`.
- `manual_in_window(start_ts)`: `since_ts >= start_ts`.
- `owned_by_other(ref_ts)`: `stamp_writer` is the other writer and `stamp_ts >= ref_ts`.
- `already_written` (per writer): `stamp_writer == W` and `now_ts - stamp_ts <= lag_seconds`. A failed command is therefore retried at most once per lag (120 s), never per tick; a landed command is idempotent through the "at target" checks.
- Interlock rule (kids instances, identical to pre-cool's `interlock_blocked`): blocked while any configured interlock sensor is `on`, `unavailable`, `unknown`, absent, or has `last_changed` within `interlock_clear_minutes` (5 ≥ cutoff hold 3 + 2). No `turn_on`, `turn_off` or `set_direction` while blocked, with one exception: the writer's own safety cut (`fan on` and my latest stamp says on with `stamp_ts` within lag and the fan's on-transition ≥ `stamp_ts` while an interlock sensor reads `on` → stamp `W|off|*|*` then `turn_off`).

### C4. Watcher classification order (fan_manual_watch.yaml), evaluated on every fan state event with `event_ts = trigger.to_state.last_updated`

| # | Verdict | Condition (first match wins) |
|---|---|---|
| 1 | replay | `trigger.to_state` is none, or `trigger.from_state` is none, or `from_state.attributes.restored` is true |
| 2 | recovery | from-state or to-state in `unavailable`/`unknown` |
| 3 | no-op | state, percentage and direction all unchanged (other attributes only) |
| 4 | own write | a stamp exists, `stamp_ts <= event_ts <= stamp_ts + lag_seconds`, to-state equals `stamp_state`, percentage equals `stamp_pct` when asserted, direction equals `stamp_dir` when asserted |
| 5 | cutoff / resume (kids instance only) | off-branch: on→off while the cutoff automation's `current` attribute ≥ 1 and the cutoff sensor is `on` or changed state within lag before `event_ts`. resume-branch: off→on with the sensor `off` for ≥ hold − 15 s at `event_ts` and the cutoff automation either ended within lag (`current` 0 and its `last_updated` within lag) or still active. Any other off→on while `current` ≥ 1 is the cancel path = manual. |
| 6 | seasonal (kids instance only) | any change with `event_ts` within `lag_seconds + coast_seconds` after the seasonal automation's `last_triggered` |
| 7 | manual | everything else → `input_datetime.set_datetime` on the since helper with `timestamp: event_ts` |

The watcher never writes a stamp, never calls a `fan.*` service, and notifies only when its since helper is missing (`fan_manual_watch_<fan>_helper_missing`).

### C5. Blueprint idioms (from the pre-cool lineage; tests pin them)

Every input appears in top-level `variables:` as `<name>: !input <name>`; logic variables live in action-level `variables:` steps (so `_var_template` reaches them) and are defined before use; instants cross steps as unix timestamps (floats), never datetimes; values feeding `==`/`in`/service data are single-lined; no bare boolean literals; every `fan.*` call carries `continue_on_error: true` and `percentage` on `turn_on`; live re-check immediately before each call; persistent notifications only, fixed ids per condition, state-driven create/dismiss so each condition notifies at most once per episode; `mode: restart` + `max_exceeded: silent` on N and T, `mode: queued` (max 10) on M; restored-trigger guard (`trigger.from_state is not none and not restored`) on every state trigger of N, M and T's new toggle triggers; `ha_start` re-evaluates only. No `wait_template`/`delay` in N: the reversal envelope is tick- and state-driven (C6).

### C6. Daytime blueprint (bedroom_fan_daytime.yaml) behavioural contract

Windows: `day_start` 08:00, `day_end` 18:00, `day_end_margin` 5 → `wrap_ts` = 17:55. Normal writes (vacancy-off, nap band, envelope) only in `[day_start, wrap_ts)`; wrap-up writes (nap-end off and direction restore of a nap N itself ended) until `wrap_end` = `day_end` + `wrap_grace_minutes` (30 → 18:30; Martin 2026-09-24, consistency-check Q2), each still interlock-gated and stamped (rule 4, never manual; before P's 19:29 lock); nothing else at or after `day_end`, and nothing at all after `wrap_end`, until `day_start`. No reversal may start within 10 min of `wrap_ts` (17:45). The nap-toggle lifecycle (start, end, 3 h cap, stale reset) runs 24 h; only fan commands are day-gated.

Vacancy: `activity_ts` = max of every activity sensor's `last_changed` (either state), `since_ts`, and the nap toggle's `last_changed` while on. `vacancy_due` = in day window, fan available and on, `record_ok`, `now_ts - activity_ts >= vacancy_minutes·60`, not blocked, not `already_written`, and not exempt. Exempt = `stamp_writer == precool and stamp_ts >= day_start_ts` (fan-assist, example 26), or the nap fan while `nap_active` and `ours`. Master instance: activity = stairs PIR only (hand-started fan limitation, example 3).

Nap (kids instance; empty `nap_toggle` disables everything below): start when the Off button (`nap_start_button`) reports `short_release` while the gate entity is `on`, inside the day window, toggle off, temperature valid → `input_boolean.turn_on`. Reference `nap_on_ts` = toggle `last_changed`; a toggle that is on with `nap_on_ts < day_start_ts` on a day tick is stale → switched off before any fan logic. End on: any `nap_end_buttons` entity `short_release` while the gate is `off`; the gate turning `on`; cap (`now_ts - nap_on_ts >= nap_max_hours·3600`, any hour); forced end at `wrap_ts`; the toggle switched off by hand. Nap end = toggle off first (the nightlight follows within a minute), then for `nap_end_retry_minutes` after the toggle went off (a forced end at `wrap_ts` retries until `wrap_end`): if the fan is `ours` and on and not blocked → stamp off + `turn_off`; once the fan reads off and `direction_mode != cooling_only` and live direction ≠ rest direction → stamp `daytime|off|*|<rest>` + `set_direction`. Still ours-on after the retry window → one notice.

Band: `need_cool_start` = temp ≥ ideal + tolerance (24.5); `need_warm_start` = temp ≤ ideal − tolerance (21.5); `cool_hold` = temp > ideal + tolerance − hysteresis (23.5); `warm_hold` = temp < ideal − tolerance + hysteresis (22.5). Regime from the live fan while `ours`: on + cooling direction = cooling; on + warming direction = warming; else idle. `desired` = cool if (cooling and cool_hold) or (not cooling and need_cool_start); warm if direction_mode ≠ cooling_only and ((warming and warm_hold) or (not warming and need_warm_start)); else off. Temperature `unavailable`/`unknown`/non-numeric: no nap start; an ours fan running → off + notice; temp < `floor_temp` (16) → desired off + overcooling notice. Writes only when `nap_active` and the fan is `ours`, or the fan is off and untouched since the nap started (`since_ts < nap_on_ts` and not `owned_by_other(nap_on_ts)` and not `already_written`). A fan on but not ours (manual, pre-cool) is the parent's or pre-cool's for that nap: no band writes, no nap-end off (example 37); vacancy-off still applies to a manual fan. First start of a nap allowed only within `blocked_notice_minutes` (10) of `nap_on_ts`; blocked for the whole 10 min → one notice, no further first-start attempts that nap; restarts after a band-off (my stamp with ts ≥ `nap_on_ts` exists) are allowed at any time.

Direction: cooling direction = `summer_direction` (forward), warming = `winter_direction` (reverse), rest direction = winter if `season_toggle` is on else summer, read live at use. `direction_mode`: `cooling_only` — never writes direction; starts only when the fan's live direction already equals the cooling direction (a fan resting in the warming direction gets one state-driven notice and no nap fan); `both_at_start` — sets direction only while the fan is off (nap start, band restart, nap-end restore), never reverses a running fan; `both_with_reversal` — additionally runs the envelope. Envelope (stateless, one step per tick or per fan state event, each step live re-checked and interlock-gated): (1) fan ours-on with direction ≠ needed, `now_ts - fan.last_updated >= reversal_dwell·60`, before 17:45 → stamp `daytime|off|*|<target>` + `turn_off`; (2) fan off, my latest stamp is an off with an asserted direction, live direction ≠ target, stamp age ≤ `direction_wait_seconds` (90) → re-stamp same + `set_direction`; (3) fan off, live direction = target, stamp age ≤ 90 s, desired still set → stamp `daytime|on|<pct>|<target>` + `turn_on`. Abort = a step's expected state not reached within 90 s of its stamp, or an interlock trip: no further step, fan left off (an off that never landed leaves a non-matching fan that is no longer ours), one notice, no retry that nap (the aborted off-with-direction stamp older than 90 s blocks first-start logic until the toggle cycles). At most one reversal per dwell by construction (our own off moves `last_updated`).

Cut (kids): `cut_due` = fan on, `stamp_writer == daytime`, `stamp_state == on`, `now_ts - stamp_ts <= lag_seconds`, fan `last_changed >= stamp_ts`, any interlock sensor reads `on` → stamp off + `turn_off` (the only command allowed while blocked).

Notifications (fixed ids `bedroom_fan_daytime_<condition>_<this.entity_id with '.' → '_'>`): `blocked`, `reversal_aborted`, `nap_end_failed`, `sensor` (invalid or < floor), `fan_unavailable` (nap start only), `record_missing`, `direction_mode` (cooling_only with a warming rest direction). Each is created while its condition holds and dismissed at the next nap boundary or day boundary.

### C7. Pre-cool v1.3.0 contract (bedroom_precool.yaml)

New inputs: `fan_manual_records` (object selector, default `{}`: fan entity → `{since: <input_datetime>, stamp: <input_text>}`), `manual_window_start` (time selector, default `00:00:00` = unset → the reference is `lock_ts` exactly as v1.2.1). Three states per configured fan: **no entry** → v1.2.1 `last_updated` rule, unstamped commands, one notice `bedroom_precool_record_unmapped` while `fan_manual_records` is non-empty and a listed fan lacks an entry; **entry, helpers present** → record rule below; **entry, helper missing/unavailable** → skip every command to that fan, notice `bedroom_precool_record_missing`. Record rule: `fans_due_night` replaces "`last_updated < lock_ts`" with "not `manual_in_window(window_start_ts)` and not `owned_by_other(lock_ts)` and not `already_written`", where `window_start_ts` = the night-anchored `today_at(manual_window_start)` (yesterday's before wake time, same day-offset idiom as `lock_ts`) or `lock_ts` when unset; `fans_due_precool` uses `since_ts < ac_started_ts` and not `owned_by_other(ac_started_ts)` (example 27) and not `already_written`; `fans_unset_night` mirrors `fans_due_night`'s untouched test; `fans_unsafe_on` for a recorded fan = my own stamp on within 120 s and the fan's on-transition ≥ stamp ts while an interlock reads `on` (v1.2.1 window/grace rule kept for unrecorded fans). STEP 5c stamps before every command for recorded fans (`precool|on|<pct>|*|ts`, `precool|off|*|*|ts` for the cut) and its live re-check repeats the record rule. Nothing else changes: with `fan_manual_records` empty every existing rendered test passes unchanged (v1.2.1 behaviour byte-for-byte on the service sequence). Direction is never written (test: `fan.set_direction` absent from the file).

### C8. Nightlight v1.3.0 contract (nightlight.yaml)

New input `nap_toggle` (input_boolean, default `[]`). `is_nap_window` = `is_state(nap_toggle, 'on')` when configured, else the v1.2.0 fixed window; two new state triggers on the toggle (`nap_toggle_on`, `nap_toggle_off`) guarded against restored replays through the global condition; branch order unchanged (wakeup, night, nap), so a toggle on at night paints the night colour (example 30); the `nap_start`/`nap_end` time triggers remain (fixed window fallback, harmless repaint when a toggle is configured). Everything else byte-for-byte v1.2.0 with the input empty.

### C9. Test harness

pytest from the worktree root: `~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q`. New modules import `_env`, `_reparse`, `_var_template`, `_service_steps`, `_step_contains`, `_def_index` from `tests/test_bedroom_precool_structure.py` and `run` from `tests/test_deploy_blueprint_script.py` (the existing cross-module import convention) and define their own fake state class with arbitrary attributes (`percentage`, `direction`, `restored`, `current`, `last_triggered`) and a fake `trigger` object. Expectations are copied from the brief's examples, never derived from the implementation. RED first: every test that pins new behaviour is written and shown failing before the YAML change.

### C10. Worker rules (repeated in every brief)

Owned paths only; no commits unless the brief says so (the orchestrator commits on the task branch after acceptance); no `git stash`; no nested dispatch, review, research or fan-out — added work returns to the orchestrator for reservation; stop and return on ambiguity, a needed change outside the owned paths, a new interface, or a failing invariant; one targeted self-correction per acceptance failure; report changed files, commands with outcomes (test counts as `PASS=N FAIL=M`, the dry-run's last line), unresolved issues and artifact paths.

## Execution schedule (stage 5)

| Task | Component | Route | Owner | Worktree / branch | Depends on | Independent of |
|---|---|---|---|---|---|---|
| 0 | pre-flight, spec copy, baseline | command / orchestrator | Opus/high inline | chain worktree | — | — |
| 1 | fan_manual_watch.yaml (M) | delegate | Opus/high | `~/AI/projects/Blueprints_Home-wt/bedfans-m`, `feat/bedfans-m` | 0, design gate | 2, 3, 4 |
| 2a | bedroom_fan_daytime.yaml core (N, cooling_only) | delegate | Opus/high | `…-wt/bedfans-n`, `feat/bedfans-n` | 0, design gate | 1, 3, 4 |
| 2b | N direction modes + reversal envelope | delegate | Opus/high (fresh dispatch, same worktree) | as 2a | 2a accepted | 1, 3, 4 |
| 3 | bedroom_precool.yaml v1.3.0 (P) | delegate | Opus/high | `…-wt/bedfans-p`, `feat/bedfans-p` | 0, design gate | 1, 2, 4 |
| 4 | nightlight.yaml v1.3.0 (T) | delegate | Sonnet/high | `…-wt/bedfans-t`, `feat/bedfans-t` | 0, design gate | 1, 2, 3 |
| 5 | integration: merges, README, consistency test, full suite, six dry-runs | orchestrator (recorded exception) | Opus/high | chain worktree | 1–4 | — |

At most two active delegates. Order: start 2a and 1 together (the two Opus tasks with the longest paths); when 1 returns, start 3; when 2a is accepted, start 2b; when 3 returns, start 4. Every worker worktree branches from the chain branch at Task 0's commit; workers never touch `README.md` (Task 5 owns it) and return their README bullet text in the report. The orchestrator merges each task branch into `feat/bedroom-fan-occupancy-nap` after acceptance (explicit paths, per-pillar commits: code+tests, deploy JSON, docs).

## Stage 4 — design gate

### Task A — pre-gate consistency check

- **Route and reason:** delegate — bounded read-only extraction with one concrete question and a checkable result (policy: required before every high-risk `triple-check`).
- **Owner/model/effort:** Sonnet/high, time box 20 min (`--timebox-min 20`), kind native, class required, task `bedfans-consistency`, stage 4.
- **Question:** which brief requirements (sections 2, 2a, 4, 4a, 5, 7) contradict which plan acceptance lines? Output: a list, each entry with both quotes. **Stop rule:** every acceptance example 1–37 and matrix row checked once. Input: the brief and this plan only.
- **Known candidates the orchestrator adds to the same batched question for Martin** (implementation refinements of the brief's literal wording): (1) the reversal envelope runs tick- and state-driven with a 90 s per-step timeout instead of in-run `wait` steps (mode restart would abort a wait silently on any trigger; the observable sequence, timeouts and abort-to-off are unchanged); (2) ownership matches state and percentage only, not direction, so a seasonal flip keeps the fan ours (example 20); (3) watcher rule 5 accepts the cutoff's off when the sensor is on or changed within lag, and the resume when the sensor has been clear ≥ hold − 15 s even if the run has not yet reported ended, with the cancel path as "any other on while the run is active"; (4) the fan command window is [08:00, 18:00) with normal writes stopping at 17:55 and only the nap wrap-up (off + restore) allowed 17:55–18:00; (5) derived example D1: a fan a parent started before a nap is switched off by vacancy-off (the toggle-on counts as activity, so 20 min after it) and may then be started by the nap band at 1 % — a consequence of "any fan off after the vacancy timeout" plus "fan off, untouched since nap start"; (6) example 17's "no nap start" on a bad temperature sensor also means no nightlight nap colour, since the toggle is not set; (7) in cooling_only, a fan resting in the warming direction gets one notice and no nap fan. Fold the answers into this plan before `triple-check`.

- **Triple-check local pass (2026-09-24, orchestrator):** one finding, TC-1 (P2): stage 8 step 1 prescribed REST helper creation, which HA does not offer for storage helpers (memory: HA ops cluster, 2026-09-07 ventilator chain) → fixed to WS create + id read-back. Premise, robustness (stamp register, lag, restart replays, wrap-up extension vs P's 19:29 lock and fan-assist), interfaces (`timestamp` attribute of date+time input_datetime, automation `current`/`last_triggered`, POST create for new automations), past evidence (datetime-as-string, bare booleans, input renames, restored replays) and task completeness otherwise clean.
- **Outcome (2026-09-24, ledger 404dec9a):** 6 findings, none among candidates (1)–(7). Martin's answers (one batched question): vacancy counts from the activity sensor's last clear, not its start (finding 1 — brief §7 "on-transitions" refined, Decided #13 confirmed); nap wrap-up extended to 18:30 (D3, see C6); candidates (1)–(7) accepted; local feature-branch commits authorized (no push/PR/merge without asking). Orchestrator dispositions: finding 2 (cooling_only first) is the brief's own §5 d; finding 3 ("by hand") = service calls Martin triggers from outside the room; finding 4 added to the authorization steps; finding 5 kept (additive check); finding 6 fixed (section 7 in scope).

### Task B — design board

- **Route:** orchestrator, `triple-check` on brief + plan, then `convene-board` (design-time, high-risk, CYCLE=1) with `STACKB_DRIVER=claude`, `STACKB_LEDGER`, `STACKB_TASK=bedfans-design`, `STACKB_STAGE=4`; R1 Fable/xhigh via `r1-trial-open.sh` (trial gate 2 of 5, `r1-model: fable`), R2 fresh Codex dedicated security.
- **Charter emphasis:** the interlock and cut under Tuya lag; the envelope's fail-to-off guarantee on every abort path; the cutoff-cancel interaction (no turn_on while blocked); the shared stamp register (single slot, two writers, lag-bounded own-write matching); attribution residuals i–vi and their consequence direction; restart replays; the 08:00 stale-toggle reset; P's default path preservation; the nightlight branch order.
- **Budget:** two required initial legs plus up to two correction waves of scoped deltas (≤ 4 review dispatches). Contradictions Martin resolved in Task A are folded in before the board, not after.

## Stage 5 — tasks

### Task 0 — pre-flight (command / orchestrator)

- **Route and reason:** command and orchestrator bookkeeping; no design judgement.
- **Steps:** (1) copy the approved brief bytes to `docs/superpowers/specs/2026-09-24-bedroom-fan-daytime-v1.0.0-discovery-brief.md` and this plan to `docs/superpowers/plans/2026-09-24-bedroom-fan-daytime-v1.0.0.md`; commit as two pillar commits on the chain branch (local feature-branch commits authorized by Martin 2026-09-24; no push until asked). (2) `pytest tests -q` → record `PASS=N FAIL=0` (N is the baseline count). (3) `bash scripts/deploy-blueprint.sh --dry-run bedroom_precool.yaml leviemartin/bedroom_precool.yaml deploy/bedroom_precool_1779553673971.json` → `dry-run: validation passed`. (4) TCB `verify` rc 0 with the header's `TCB_EXTRA` and `STACKB_DRIVER=claude`. (5) create the four worker worktrees from the chain branch's head only when their task is dispatched.
- **Acceptance:** the two files exist with the recorded sha (brief sha d8c5a274… re-hashed on the copy); baseline numbers recorded in the session record.

### Task 1 — fan_manual_watch.yaml (the manual-change detector, M)

- **Route and reason:** delegate — substantial implementation with a reasoning loop; it creates the chain's new trust point (attribution feeding two writers), so it is high-risk execution and cannot route to a Sonnet bounded worker.
- **Owner/model/effort:** Opus/high, native, class required, task `bedfans-m`, stage 5, worktree `~/AI/projects/Blueprints_Home-wt/bedfans-m` on `feat/bedfans-m`.
- **Outcome:** a blueprint that, one instance per fan, writes the fan's since helper only for genuine user power/speed/direction changes and never for replays, cloud recoveries, no-ops, a writer's own stamped write, the cutoff's off/resume, or the seasonal automation's writes (C4). Kids instance configured with the cutoff automation, cutoff sensor, hold 3 min, tolerance 15 s, seasonal automation, coast 4 s; master instance plain.
- **Interfaces and consumers:** inputs `fan` (required), `since_helper` (input_datetime, required), `stamp_helper` (input_text, required), `lag_seconds` 120, `cutoff_automation` [] , `cutoff_sensor` [], `cutoff_hold_minutes` 3, `cutoff_tolerance_seconds` 15, `seasonal_automation` [], `seasonal_coast_seconds` 4, `enable_notifications` true. Writes `input_datetime.set_datetime` (timestamp) and `persistent_notification.create/dismiss` only. Consumers: P (Task 3) and N (Task 2) read the since helper; stage 8 live probe e reads it; the consistency test (Task 5) reads the instance JSONs. Reads: the fan's state/percentage/direction, the cutoff automation's `current`/`last_updated`, the seasonal automation's `last_triggered`, the cutoff sensor's state/`last_changed`.
- **Paths (owned):** `fan_manual_watch.yaml`, `tests/test_fan_manual_watch_structure.py`, `requirements_fan_manual_watch.md`, `deploy/fan_manual_watch_kids.json` (id `fan_manual_watch_kids`, alias "Kids fan — manual change watch v1.0.0"), `deploy/fan_manual_watch_master.json` (id `fan_manual_watch_master`).
- **Acceptance checks (tests RED before the YAML exists, then GREEN):**
  1. `test_inputs_and_defaults`; `test_every_input_is_passed_through_top_level_variables`; `test_mode_queued_max_10_and_one_state_trigger_without_to_or_from`.
  2. `test_rendered_stamp_parsing`: the five-field parse, `*` handling, a four-field or non-numeric-ts string is "no stamp", an empty/unknown helper is "no stamp".
  3. `test_rendered_classification_order_and_verdicts`: one `verdict` variable rendered against a fake `trigger` for each rule with the brief's examples: replay (from_state none; restored) → example 19; recovery → examples 18, 23, 33; no-op (attribute-only change); own write on `daytime|on|1|forward` landing on at 1 % forward within lag → examples 4, 11; own write off-target intermediate (on at 21 % against a stamp of 1 %) → manual (residual i, documented in the test name); stamp older than lag → manual (residual v); cutoff off (run active, sensor on) → example 9; cutoff off with the sensor cleared 20 s earlier → still cutoff; resume (run ended within lag, sensor clear 2:50) → examples 9, 24; an on during the run with the sensor clear only 60 s → manual (example 34); seasonal window (flip at 20:00, event 20:01 → seasonal; 20:05 → manual) → examples 31, 36; direction-only change while off within the seasonal window → seasonal (example 35); dimmer press unstamped → manual with since = event instant → examples 3, 12, 13, 14, 37; the master instance (no cutoff/seasonal inputs) reaches rules 5–6 as "not applicable".
  4. `test_since_is_the_only_helper_write_and_no_fan_service_exists`: exactly one `input_datetime.set_datetime`, gated on `verdict == 'manual'`, `timestamp` from `event_ts`; no `input_text.set_value`; no `fan.` service anywhere; `test_verdict_uses_event_timestamps_not_now`: `now()` does not appear in the verdict templates.
  5. `test_missing_helper_notice_is_the_only_notice` (example 21, 32): fixed id, state-driven create/dismiss.
  6. Deploy dry-run for both instance files passes (`ok (id fan_manual_watch_kids`, `… master`); `test_instances_values`: kids instance carries `automation.samuel_fan_safety_motion_cutoff`, `binary_sensor.samuel_samuel_matthew_fanprotection`, `automation.samuel_fan_seasonal_direction`, the kids since/stamp helpers; master carries only the master helpers; each fan appears in exactly one watcher file.
  7. `requirements_fan_manual_watch.md`: purpose, the record helpers and how to create them (exact REST bodies for stage 8), the stamp format, the seven rules, residuals i–vi with their consequence direction, deploy invariant "one watcher per fan, helper mapping identical in every consumer".
  8. Full suite green; `git status` shows only owned paths.
- **Dependencies:** Task 0 and the design gate. Independent of Tasks 2–4 (the contract C1–C4 is pinned here, not negotiated).

### Task 2a — bedroom_fan_daytime.yaml core (N, cooling_only)

- **Route and reason:** delegate — consequential physical-safety execution (starts and stops the kids fan under the interlock); Opus only.
- **Owner/model/effort:** Opus/high, native, class required, task `bedfans-n-core`, stage 5, worktree `~/AI/projects/Blueprints_Home-wt/bedfans-n` on `feat/bedfans-n`.
- **Outcome:** the daytime blueprint per C6 with `direction_mode` present but only `cooling_only` implemented (the other two options are accepted by the selector and behave as `cooling_only` until Task 2b; a structure test pins that no `fan.set_direction` exists yet). Vacancy-off for both rooms, the nap lifecycle, band writes at `nap_pct` in the cooling direction, the cut, notices, the 08:00 stale reset, the forced 17:55 end, nap-end retry, sensor and record failure paths.
- **Interfaces and consumers:** inputs `fan`, `since_helper`, `stamp_helper` (required); `activity_sensors` [] ; `day_start` 08:00:00, `day_end` 18:00:00, `day_end_margin` 5, `wrap_grace_minutes` 30, `vacancy_minutes` 20, `lag_seconds` 120; `nap_toggle` [], `temperature_sensor` [], `nap_start_button` [], `nap_end_buttons` [], `gate_entity` []; `nap_pct` 1, `ideal_temp` 23, `tolerance` 1.5, `hysteresis` 1.0, `floor_temp` 16, `nap_max_hours` 3, `nap_end_retry_minutes` 15, `blocked_notice_minutes` 10; `direction_mode` cooling_only, `season_toggle` [], `summer_direction` forward, `winter_direction` reverse, `reversal_dwell_minutes` 30, `direction_wait_seconds` 90, `reversal_guard_minutes` 10; `interlock_sensors` [], `interlock_clear_minutes` 5; `enable_notifications` true. Triggers: `time_pattern /1` (`periodic`), state on the fan, the nap toggle, each dimmer button entity, the gate, every activity sensor, every interlock sensor, `homeassistant start`. Writes: `fan.turn_on/turn_off` (`set_direction` in 2b), `input_boolean.turn_on/turn_off` on the nap toggle, `input_text.set_value` on the stamp helper, notifications. Consumers: T (toggle), M (stamps), P (stamps via ownership), stage 8 verification, the observation criteria.
- **Paths (owned):** `bedroom_fan_daytime.yaml`, `tests/test_bedroom_fan_daytime_structure.py`, `requirements_bedroom_fan_daytime.md`, `deploy/bedroom_fan_daytime_kids.json` (id `bedroom_fan_daytime_kids`, alias "Kids room — fan daytime v1.0.0"; fan.ceiling_fan_light_v2; kids helpers; activity [binary_sensor.stairs_motion, binary_sensor.samuel_samuel_matthew_fanprotection]; nap_toggle input_boolean.kids_nap; temperature sensor.temperature_sensor_3; Off button event.baby_room_button_4; end buttons [event.baby_room_button_2, event.baby_room_button_3]; gate light.kids_room_gate; season toggle input_boolean.samuel_fan_winter_mode; interlock [fanprotection], clear 5; `direction_mode: cooling_only`), `deploy/bedroom_fan_daytime_master.json` (id `bedroom_fan_daytime_master`; fan.ceiling_fan_light_v2_2; master helpers; activity [binary_sensor.stairs_motion]; no nap inputs).
- **Acceptance checks (RED first):**
  1. Structure: inputs/defaults; pass-through; trigger roster with restored guards; `mode: restart`; every `fan.*` call has `continue_on_error`, `percentage` on turn_on, and an `input_text.set_value` on the stamp helper immediately preceding it in the same sequence (`test_stamp_precedes_every_fan_call`); no fan call reachable when `record_ok` is false (`test_no_unstamped_path`, example 32); `fan.set_direction` absent (2a only).
  2. Rendered predicates against fixtures copied from the examples: `test_rendered_day_windows_and_wrap` (examples 15, 22: no normal write at 17:55; nap wrap-up allowed until 18:30 only for a nap N ended and only when unblocked; no other write at 18:00–08:00; nothing after 18:30; D3 row: forced end 17:55 blocked until 18:04 → off + restore land 18:04–18:30); `test_rendered_activity_ts_and_vacancy_due` (examples 1, 2, 3, 14, 33, D1); `test_rendered_ownership_predicates` (`ours`, `manual_in_window`, `owned_by_other`, `already_written`; examples 18, 19, 26, 27, 37); `test_rendered_vacancy_exemptions` (precool stamp newer than day_start exempt, older not; nap fan ours exempt, manual nap fan not; examples 1, 26, 37); `test_rendered_nap_reference_and_stale_toggle` (example 30: on since 19:00 → no fan write; still on at 08:00 → switched off first); `test_rendered_band_and_hysteresis` (24.8 on, 23.4 off, 22.8 nothing, 21.3 no write in cooling_only, floor 15.9 off + notice, non-numeric → no start and off if ours; examples 4, 5, 6, 17); `test_rendered_interlock_blocked_and_cut` (examples 9, 10, 11, 25, 34: no command while blocked or within the 5-min hold; cut only on own stamp within lag under a sensor reading on; the cutoff-resumed fan at 1 % matches the stamp → ours); `test_rendered_first_start_window_and_blocked_notice` (example 10: write on the first tick after 12:47, notice at 12:50 when still blocked, no first start after that; a band restart at 14:00 allowed); `test_rendered_nap_end_retry` (example 25: zero commands 14:29–14:35, off on the first clear tick, none after 14:45); `test_rendered_forced_end_and_cap` (examples 15, 16); `test_rendered_sensor_and_fan_failure_paths` (examples 17, 18); `test_rendered_hand_started_before_nap` (D1).
  3. Lifecycle actions: `test_nap_start_and_end_signals` (Off short_release with gate on inside the window starts; long_press does not; +/− short_release with gate off ends; gate on ends; a signal outside 08:00–17:55 changes nothing; examples 4, 28, 37); `test_toggle_off_precedes_fan_wrap_up`; `test_notices_fixed_ids_state_driven`; `test_escape_paths` (example 21: empty `nap_toggle` → no nap logic, vacancy-off intact; the vacancy path itself needs no nap inputs).
  4. Both instance dry-runs pass; `test_instances_values` pins the entity ids above and `direction_mode == cooling_only` for the initial deploy, and `interlock_clear_minutes == 5`.
  5. `requirements_bedroom_fan_daytime.md`: overview, actors and the ownership rule, windows, vacancy, nap lifecycle, band, direction modes (2b fills in), interlock and cut, notices, residuals (hand-started fan, Tuya lag, residual i–vi inherited), the deploy order and the live-verification steps.
  6. Full suite green; `git status` shows only owned paths.
- **Dependencies:** Task 0 and the design gate. Independent of Tasks 1, 3, 4.

### Task 2b — N direction modes and reversal envelope

- **Route and reason:** delegate — the highest-risk logic (stop-reverse-restart above a sleeping child); Opus only; a fresh dispatch so the envelope is written and reviewed on top of an accepted core.
- **Owner/model/effort:** Opus/high, native, class required, task `bedfans-n-direction`, stage 5, same worktree as 2a after the orchestrator accepted 2a.
- **Outcome:** `both_at_start` and `both_with_reversal` implemented per C6: direction chosen while the fan is off, the nap-end rest-direction restore, the tick/state-driven envelope with 90 s per-step timeout, abort to off with one notice and no retry that nap, the 17:45 bound, dwell 30 from the fan's `last_updated`, the season-flip case, and the cooling_only direction notice.
- **Interfaces and consumers:** adds `fan.set_direction` (stamped `daytime|off|*|<dir>`), the `reversal_aborted` and `direction_mode` notices; no new inputs beyond those 2a declared. Consumers: stage 8 steps a, b, d; observation.
- **Paths (owned):** `bedroom_fan_daytime.yaml`, `tests/test_bedroom_fan_daytime_structure.py`, `requirements_bedroom_fan_daytime.md` (direction section).
- **Acceptance checks (RED first):** `test_rendered_direction_targets_and_rest_direction` (cooling = summer, warming = winter, rest from the live toggle, empty toggle → summer); `test_rendered_start_from_off_sets_direction_first_then_turns_on` (example 6: cold room, fan off forward → stamp off|reverse + set_direction; after read-back → stamp on|1|reverse + turn_on; 90 s timeout → abort notice); `test_rendered_nap_end_restores_rest_direction_after_confirmed_off` (example 6 end; example 20 end restores the toggle's current value); `test_rendered_envelope_steps_dwell_and_time_bound` (example 7: 13:45 warming fan ours since 13:00, room 24.6 → step 1; step 2 only when off is read; step 3 only when direction is read and desired still cool; dwell 20 → no step 1; 17:46 → no step 1; blocked → no step); `test_rendered_envelope_abort_paths` (example 8: PIR trip mid-envelope → no further step, notice; off never landed after 90 s → non-matching fan, notice, no retry; aborted stamp blocks a first start until the toggle cycles); `test_rendered_season_flip_keeps_ours_and_reverses_back_once_after_dwell` (example 20); `test_rendered_both_at_start_never_reverses_a_running_fan`; `test_rendered_cooling_only_never_writes_direction_and_notices_a_warming_rest_direction`; `test_set_direction_only_while_fan_off_and_never_while_blocked` (structure: every `fan.set_direction` call's conditions contain the off check and the interlock rule); example 15's "no reversal after 17:45"; every 2a test still green; full suite green.
- **Dependencies:** 2a accepted. Independent of Tasks 1, 3, 4.

### Task 3 — bedroom_precool.yaml v1.3.0 (P)

- **Route and reason:** delegate — rewrites the safety-relevant unsafe-on cut and the night/assist due rules on a live automation in the children's rooms; Opus only.
- **Owner/model/effort:** Opus/high, native, class required, task `bedfans-p`, stage 5, worktree `~/AI/projects/Blueprints_Home-wt/bedfans-p` on `feat/bedfans-p`.
- **Outcome:** C7 exactly; version 1.3.0 in the name, description, instance alias and docs; live instance JSON carries both records and `manual_window_start: "18:00:00"`; STEP 8 debug dump adds the per-fan record verdicts.
- **Interfaces and consumers:** inputs `fan_manual_records` and `manual_window_start`; the two stamp helpers (written), the since helpers (read); new notices `bedroom_precool_record_missing`, `bedroom_precool_record_unmapped`; consumers: M (matches P's stamps), N (exempts P-stamped fans), stage 8, observation (19:29 write on the latch night).
- **Paths (owned):** `bedroom_precool.yaml`, `tests/test_bedroom_precool_structure.py`, `deploy/bedroom_precool_1779553673971.json`, `requirements_bedroom_precool.md` (sections "Bedroom Fans — The Fan Write Rule", the Safety subsection, a new "Manual-change records (v1.3.0)" section).
- **Acceptance checks (RED first):** `test_v130_inputs_exist_with_safe_defaults` (object selector default `{}`, time default `00:00:00`); `test_rendered_record_state_per_fan` (no entry / entry+present / entry+missing; examples 21, 32); `test_rendered_window_start_ts_anchors_to_the_night_and_falls_back_to_lock_ts` (18:00 today at 19:29; yesterday's 18:00 at 01:00; unset → `lock_ts`); `test_rendered_fans_due_night_uses_the_record_rule` (examples 12, 13, 14, 23, 24, 36: manual 18:30 skipped, manual 17:50 written, flapped fan written, cutoff-resumed 21 % written, a seasonal flip at 19:40 leaves the fan at target so nothing is written, N's stamp newer than lock_ts → skipped, own stamp within 120 s → skipped, own stamp older with the fan not at target → due again); `test_rendered_fans_due_precool_uses_since_and_the_other_writer` (examples 26, 27); `test_rendered_fans_unset_night_record_rule_disjoint_from_due`; `test_rendered_fans_unsafe_on_keys_on_own_stamp` (own stamped on landing under a tripped sensor → cut; a person's on in the window without a stamp → not cut; stamp older than 120 s → not cut; unrecorded fan → v1.2.1 rule); `test_fan_step_stamps_before_every_command_and_skips_missing_records` (walker: each of the four `fan.*` calls is preceded by the stamp write in its sequence for recorded fans, the unrecorded branch keeps the v1.2.1 unstamped call, and the live re-check repeats the record rule); `test_record_notices_state_driven`; `test_default_path_is_v121`: every pre-existing rendered test passes unchanged with `fan_manual_records = {}` (do not edit their fixtures except to add the two new context keys with their defaults); version pins to 1.3.0 (`test_version_bumped`, `test_precool_instance_values`, `test_v110_version_docs_and_instance` alias); instance test pins both record entries and the window start; `fan.set_direction` absent; `wait_template` absent; dry-run passes with the migrated instance; docs updated; full suite green; owned paths only.
- **Dependencies:** Task 0 and the design gate. Independent of Tasks 1, 2, 4.

### Task 4 — nightlight.yaml v1.3.0 (T)

- **Route and reason:** delegate — every bounded-worker condition holds: behaviour pinned by C8 and examples 28–30 including the default path; interfaces and paths pinned; acceptance the worker runs and the orchestrator re-runs; pattern named (nightlight.yaml v1.2.0 and its test file); one component; no high-risk consequence (a light, no fan, no authorization, no trust boundary, no data); not a diagnosis.
- **Owner/model/effort:** Sonnet/high, native, class required, task `bedfans-t`, stage 5, worktree `~/AI/projects/Blueprints_Home-wt/bedfans-t` on `feat/bedfans-t`.
- **Outcome:** C8; blueprint name "Toddler Sleep Trainer & Nightlight v1.3.0", description gains a 1.3.0 paragraph; the live instance JSON is added to the repo with `nap_toggle: input_boolean.kids_nap`, alias "Toddler Sleep Trainer & Nightlight v1.3.0 (Samuel)", the existing fixed window kept as the documented fallback.
- **Interfaces and consumers:** input `nap_toggle`; reads `input_boolean.kids_nap`; consumers: N (sets the toggle), stage 8 step f, observation.
- **Paths (owned):** `nightlight.yaml`, `tests/test_nightlight_structure.py`, `deploy/nightlight_1766142134972.json` (new; the live config from the overlap capture plus the toggle), `requirements.md` (sections 4.1 and 5.1 gain the toggle).
- **Acceptance checks (RED first):** `test_version_bumped` → "v1.3"; `test_nap_toggle_input_optional_default_empty`; `test_nap_toggle_state_triggers_with_restored_guard` (ids `nap_toggle_on`/`nap_toggle_off`, the global condition rejects a replayed/restored toggle event and still passes every other trigger); `test_rendered_is_nap_window_follows_the_toggle_when_configured` (11:45 on → True outside the fixed window; 19:00 on → True but the night branch precedes it; off → False; examples 28, 30); `test_rendered_is_nap_window_fixed_window_when_unconfigured` (the existing 13:00/12:29:59/15:30/disabled rows unchanged; example 29); `test_choose_branch_order` unchanged; `test_instance_dry_run_and_values` (`run("--dry-run", nightlight.yaml, "leviemartin/nightlight.yaml", instance)` → `ok (id 1766142134972`; pins `nap_toggle`, `gate_entity`, `nap_start`/`nap_end` 12:30/15:30, alias v1.3.0); every v1.2 test still green; full suite green; owned paths only.
- **Dependencies:** Task 0 and the design gate. Independent of Tasks 1–3.

### Task 5 — integration (orchestrator)

- **Route and reason:** orchestrator inline, recorded exception "handoff costs more than the tiny remainder": merges, one shared file, one small cross-file test, and the combined verification the root must own anyway.
- **Steps:** merge `feat/bedfans-m`, `feat/bedfans-n`, `feat/bedfans-p`, `feat/bedfans-t` into `feat/bedroom-fan-occupancy-nap` (no conflicts by ownership; `tests/test_bedroom_precool_structure.py` is touched only by Task 3); write `tests/test_bedroom_fans_deploy_consistency.py`: each fan entity appears in exactly one watcher JSON; P's `fan_manual_records`, N's since/stamp inputs and the watcher's helpers agree per fan; N kids `nap_toggle` == T `nap_toggle` == `input_boolean.kids_nap`; N kids `interlock_sensors` == P `fan_interlocks` == the kids watcher's `cutoff_sensor`; `interlock_clear_minutes` 5 on N kids and P; N `day_end` 18:00:00 == P `manual_window_start`; all six instance ids distinct and matching `^[A-Za-z0-9_-]+$`; the kids watcher names the live cutoff and seasonal automation entity ids; `README.md`: new sections "Fan Manual-Change Watch Blueprint" and "Bedroom Fan Daytime Blueprint" (overview, features, requirements, installation URLs), a "Manual-change records (v1.3.0)" bullet under Bedroom Sleep Pre-Cool, a "Nap toggle (v1.3.0)" bullet under the nightlight (texts from the worker reports); `requirements_bedroom_fan_daytime.md` gains the deploy-order and helper-creation section if Task 2 left it to here.
- **Acceptance:** full suite green with the count recorded; the six dry-runs (`bedroom_precool` + its instance; `nightlight` + its instance; `fan_manual_watch` + 2; `bedroom_fan_daytime` + 2) each end `dry-run: validation passed`; grep gates: `fan.set_direction` only in `bedroom_fan_daytime.yaml`; no `fan.` service in `fan_manual_watch.yaml` or `nightlight.yaml`; `wait_template` absent from `bedroom_precool.yaml` and `bedroom_fan_daytime.yaml`; `git status` clean; per-pillar commits on the chain branch.

## Stage 6 — integrated code gate

- **Route:** orchestrator, `review-shipped` → `convene-board` (code-time, high-risk, CYCLE=1): R1 fresh Opus/high correctness (`claude-leg.sh`), R2 fresh Codex dedicated security; `STACKB_DRIVER=claude`, `STACKB_LEDGER`, `STACKB_TASK=bedfans-code`, `STACKB_STAGE=6`, `STACKB_RETRY_REASON` empty on the initial launch.
- **Charter emphasis:** stamp-before-command on every path including cuts and direction writes; the interlock rule on `set_direction`; the envelope's abort paths; the cut's own-stamp keying in P and N; ownership under the cutoff resume; the watcher's rule order and event-timestamp use; P's unconfigured path; T's branch order; restored-trigger guards; notification bounds; deploy JSON consistency; no secrets in outbound bodies.
- **Budget:** two required legs plus up to two correction waves of scoped deltas (≤ 4). On a P0/P1 that sits on a declared boundary the correction record enumerates every same-class path (file:line) with one regression expectation each.

## Stage 7 — completion checks

- **Route:** command, then `code-review-gate`.
- **Checks:** full pytest suite green; the six dry-runs; TCB `verify` rc 0 against the baseline with the header's `TCB_EXTRA` and `STACKB_DRIVER=claude`; the grep gates of Task 5; one PR on `leviemartin/Blueprints_Home` from `feat/bedroom-fan-occupancy-nap` with the body `Session: #40` (deploying: never `Closes`), links to the spec copy, the plan, both board reports and verdict pointers, body secret-scanned; merge only with Martin's authorization (merge commit, `--match-head-commit`, keep the branch); `#40 → status:in-review`.

## Stage 8 — deploy, live verification, observation

Order (helpers → watchers → pre-cool → nightlight → daytime), every live write authorized by Martin, from merged `main` after `git fetch`:

1. **Helpers (authorization step).** Create via the HA WebSocket commands `input_boolean/create`, `input_datetime/create`, `input_text/create` (storage helpers have no REST config endpoint — `/api/config/input_boolean/config/<id>` returns 404; triple-check finding TC-1), choosing each `name` so its slug yields the fixed id, then read back the entity id and fail the step on any mismatch; ids fixed: `input_boolean.kids_nap` (name "Kids nap"); `input_datetime.kids_fan_manual_since` and `master_fan_manual_since` (`has_date: true, has_time: true`); `input_text.kids_fan_expected` and `master_fan_expected` (`max: 255`). Verify the five entities exist and are not `unavailable` before step 2. Record the exact bodies in the deploy log (no secrets; the token stays in the script's 0600 header file idiom or hass-cli's env).
2. **Blueprints.** `scripts/deploy-blueprint.sh fan_manual_watch.yaml leviemartin/fan_manual_watch.yaml` and `… bedroom_fan_daytime.yaml leviemartin/bedroom_fan_daytime.yaml` with no instance arguments (blueprint/save only, `deploy complete`).
3. **Watchers.** The script cannot create a new instance (it backs up the current config first and dies on 404), so create each with one authorized POST to `/api/config/automation/config/<id>` carrying the deploy JSON (hass-cli raw post, or the script's curl idiom with the 0600 header file; verify the tool's exact syntax first), then run `scripts/deploy-blueprint.sh fan_manual_watch.yaml leviemartin/fan_manual_watch.yaml deploy/fan_manual_watch_kids.json deploy/fan_manual_watch_master.json` to back up, migrate and assert both `state=on`.
4. **Pre-cool.** `scripts/deploy-blueprint.sh bedroom_precool.yaml leviemartin/bedroom_precool.yaml deploy/bedroom_precool_1779553673971.json` → instance `on`; next tick trace `finished`, the debug dump shows both records resolved.
5. **Nightlight.** `scripts/deploy-blueprint.sh nightlight.yaml leviemartin/nightlight.yaml deploy/nightlight_1766142134972.json` → instance `on`.
6. **Daytime.** Create both instances as in step 3 (kids with `direction_mode: cooling_only`), then the script run with both JSONs → both `on`; the next tick trace finishes without errors; invariant check recorded: the cutoff instance's `hold_duration` (3 min) + 2 ≤ N kids and P `interlock_clear_minutes` (5).
7. **Live verification (kids room empty, Martin outside; each actuation authorized):** a) `fan.set_direction` on the off kids fan is accepted, reads back within 90 s, does not switch the fan on, and the watcher records nothing manual; b) one full reversal by service calls from outside (turn_on 1 % → turn_off → confirmed off → set_direction → confirmed → turn_on 1 %), the watcher's since helper unchanged; c) cutoff path with a nap fan: toggle on, `ideal_temp` temporarily lowered on the kids instance so the band starts the fan at 1 %, Martin enters → cutoff off; leaves, 3 min → resume at 1 %; N issues no call for 5 min after the clear (trace audit) and does not re-assert; the since helper unchanged; restore `ideal_temp`; d) only after a–c pass: set `direction_mode: both_with_reversal` in `deploy/bedroom_fan_daytime_kids.json`, POST it through the script, and commit that JSON change on `main` as a follow-up config commit with Martin's go-ahead (otherwise the instance stays `cooling_only`); e) attribution probe with the live watcher: a stamped `turn_on` from off → since unchanged (checks residual i's Tuya publish shape); one remote press → exactly one since move; an HA restart (authorized) or an observed cloud flap → none; a person's on during a hold → one; f) with the gate dark, flip `input_boolean.kids_nap` → the nightlight paints nap colour within a minute, flip back → off within a minute. Record every result with trace ids in the deploy log.
8. **Observation** (`<!-- observe:open -->` on #40 already, criteria below), ≥ 3 weekdays and ≥ 3 nights including one deliberate latch night (a remote change after 18:00) and, if possible, one flap or cutoff night: fans off within 20 min of the last upstairs activity every morning; ≥ 1 dimmer nap with fan on/off matching the band and the nightlight matching the toggle; ≥ 1 mild nap with zero fan writes; pre-cool's 19:29 write lands on untouched, flapped or cutoff-resumed fans and skips only the hand-changed fan; since helpers move only on real presses (against Martin's log); zero daytime fan calls 18:00–08:00 (trace audit); ≤ 1 notification per condition per day; no fight loop in any trace. On pass → `<!-- observe:closed -->`, `closing-session`, close #40 and epic #39. Follow-ups to file at closing (deferred in the brief): native stamping in the cutoff and seasonal blueprints; fans_at_wake off under the detector rule; humidity circulation; night circulation tuning; kids-room camera (privacy decision first); second upstairs presence sensor; fan power measurement.

## Traceability — brief acceptance examples 1–37 and derived examples

| Ex | Proved by task(s) | Tests / live / observe |
|---|---|---|
| 1 | 2a | `test_rendered_vacancy_exemptions` (precool stamp older than day_start), `test_rendered_activity_ts_and_vacancy_due`; observe mornings |
| 2 | 2a | `test_rendered_activity_ts_and_vacancy_due` |
| 3 | 1, 2a | rule 7 in `test_rendered_classification_order_and_verdicts`; activity uses `since_ts` |
| 4 | 2a, 1 | `test_nap_start_and_end_signals`, `test_rendered_band_and_hysteresis`, `test_stamp_precedes_every_fan_call`; rule 4; live e |
| 5 | 2a | `test_rendered_band_and_hysteresis` (zero writes); observe mild nap |
| 6 | 2b | `test_rendered_start_from_off_sets_direction_first_then_turns_on`, `…nap_end_restores_rest_direction…`; live a |
| 7 | 2b | `test_rendered_envelope_steps_dwell_and_time_bound`; live b |
| 8 | 2b | `test_rendered_envelope_abort_paths` |
| 9 | 1, 2a | rule 5 off/resume; `test_rendered_interlock_blocked_and_cut` (resumed fan ours); live c |
| 10 | 2a | `test_rendered_first_start_window_and_blocked_notice` |
| 11 | 2a, 1 | cut in `test_rendered_interlock_blocked_and_cut`; rule 4 |
| 12 | 1, 3 | rule 7; `test_rendered_fans_due_night_uses_the_record_rule`; observe latch night |
| 13 | 3 | `test_rendered_window_start_ts…`, due-night test row 17:50 |
| 14 | 1, 2a | rule 7; vacancy on a manual fan |
| 15 | 2a, 2b | `test_rendered_day_windows_and_wrap`, `test_rendered_forced_end_and_cap`; 17:45 bound |
| 16 | 2a | `test_rendered_forced_end_and_cap` |
| 17 | 2a | `test_rendered_sensor_and_fan_failure_paths`, band floor row |
| 18 | 2a, 1 | failure paths; rule 2; ownership after a flap |
| 19 | 2a, 1 | restored guards in the trigger test; rule 1; ownership persists |
| 20 | 1, 2b | rule 6; `test_rendered_season_flip_keeps_ours_and_reverses_back_once_after_dwell` |
| 21 | 2a, 1, 3, 4 | `test_escape_paths`; missing-helper notice; `test_default_path_is_v121`; fixed-window default |
| 22 | 2a | `test_rendered_day_windows_and_wrap`; observe trace audit |
| 23 | 1, 3 | rule 2; due-night flapped row |
| 24 | 1, 3 | rule 5; due-night cutoff-resumed 21 % row |
| 25 | 2a | `test_rendered_nap_end_retry` |
| 26 | 2a, 3 | vacancy exemption; P stamps in the fan step test |
| 27 | 3 | `test_rendered_fans_due_precool_uses_since_and_the_other_writer` |
| 28 | 4 | toggle test; live f |
| 29 | 4 | fixed-window default test |
| 30 | 2a, 4 | stale-toggle test; `test_choose_branch_order` |
| 31 | 1 | rule 6 rows 20:01 / 20:05 |
| 32 | 3, 2a | record-missing tests, `test_no_unstamped_path` |
| 33 | 1, 2a | rule 2; activity untouched row |
| 34 | 1, 2a | rule 5 cancel; not-ours hand-off |
| 35 | 1 | rule 6 direction-only row (cutoff and seasonal unchanged; documented, not tested here) |
| 36 | 1, 3 | rule 6; due-night "at target after flip" and "off fan set_direction only" rows |
| 37 | 1, 2a | rule 7; `test_rendered_ownership_predicates`, vacancy on the manual fan |
| D1 | 2a | `test_rendered_hand_started_before_nap` |
| D2 | 2a, 3 | `already_written` rows (retry once per lag) |
| D3 | 2a, 2b | forced end at 17:55 while blocked: wrap-up (off, then rest-direction restore) lands once unblocked, until 18:30; still blocked at 18:30 → one notice, fan left (documented residual) |
| D4 | 2b | cooling_only warming-rest-direction notice |

Interaction matrix rows map through their proof column: C–S (35), C–D (34), C–P (11, 24), C–N (8–11, 25), C–M (9, 24, 34), S–D (31), S–P (36), S–N (20), S–M (36), D–P (12, 13), D–T (28), D–N (4, 6, 37), D–M (12, 34), P–N (1, 15, 22, 26, 27), P–M (12, 14, 23, 24, 32), T–N (28–30), N–M (3, 18, 19, 33, 37). Release criteria of brief section 5 map to Tasks 1–5 and Stage 7; live a–f to Stage 8 step 7; observation to Stage 8 step 8.

## Ledger accounting (allowance 24 total, 12 review)

Used 5. Planned required: Task A 1; design R1 + R2 2; workers 1, 2a, 2b, 3, 4 = 5; code R1 + R2 2 → 15 committed. Reserved for corrections: up to 2 waves × 2 reviewers per gate = 8 review deltas (review sub-allowance 4 + 8 = 12). Remaining 1 for a worker retry or escalation. No optional dispatch is planned; before any optional reservation the orchestrator protects the remaining required legs plus one complete delta for the open P0/P1 set (`require-review`). A second bounded-worker escalation with the same mechanism suspends that route for the chain.

## Decided by orchestrator (Martin may revert)

1. Reversal envelope is tick- and fan-state-driven with per-step stamps and a 90 s timeout instead of in-run waits (restart-safe, matches the no-wait idiom).
2. Ownership ignores direction; direction is the envelope's concern.
3. Watcher rule 5 refinements (sensor on or changed within lag for the off; resume accepted while the run is still active once the sensor has been clear ≥ hold − 15 s).
4. Fan command window [08:00, 18:00) with normal writes ending at 17:55 and only the nap wrap-up allowed after.
5. Since instant read from `state_attr(since, 'timestamp')`; stamp ts as integer unix seconds.
6. `manual_window_start` default `00:00:00` means unset (falls back to `lock_ts`); `fan_manual_records` is an object selector mapping fan → {since, stamp}.
7. Failed commands retry once per `lag_seconds`, never per tick (`already_written`).
8. Instance ids readable (`bedroom_fan_daytime_kids`, `bedroom_fan_daytime_master`, `fan_manual_watch_kids`, `fan_manual_watch_master`) and file names without a numeric suffix; the nightlight instance keeps its numeric id.
9. Kids daytime instance ships with `direction_mode: cooling_only`; the flip to `both_with_reversal` is a stage 8 step after live a–c, committed as a config follow-up.
10. New automations are created with one authorized POST each; the deploy script is not edited (TCB-pinned).
11. Notification ids per instance use `this.entity_id` with dots replaced; state-driven create/dismiss.
12. First nap start allowed only within 10 min of nap start; band restarts allowed any time.
13. Activity age uses each activity sensor's `last_changed` regardless of state; a restart therefore delays the first vacancy-off by up to 20 min (conservative).
14. cooling_only with a warming rest direction: no nap fan, one notice.
15. New test modules import the pre-cool harness rather than extracting a shared module; the cross-file consistency test is a new small module.
16. The approved brief is copied into `docs/superpowers/specs/` as the repo's spec; Task 5 owns `README.md`.
17. Task 2 is split into 2a/2b (core, then direction) as sequential dispatches in one worktree.
18. Task 4 routes to Sonnet/high; Tasks 1, 2a, 2b, 3 to Opus/high; Task 5 inline (recorded exception).
19. Nap-end retry window 15 min keyed on the toggle's off instant; forced end at 17:55 with wrap-up commands until 18:00.
20. Stage 8 step c lowers `ideal_temp` on the kids instance temporarily to force a nap fan for the cutoff test; restored immediately after (listed as an authorization step).
21. Martin 2026-09-24: vacancy activity counts from each sensor's last clear (`last_changed` in either state), refining the brief's "on-transitions".
22. Martin 2026-09-24: `wrap_grace_minutes` 30 — only the wrap-up of a nap N ended may land 18:00–18:30, interlock-gated and stamped.
23. Martin 2026-09-24: plan refinements (1)–(7) of Task A accepted; local commits on the chain and worker branches authorized, no push/PR/merge without asking.

## Residuals carried (documented in requirements, not fixed here)

Brief residuals i–vi (Tuya intermediate publish latching a fan for the night, checked live e; a person's change landing on the stamped value within lag reads ours; a person's change within ~2 min of a season flip or a cutoff resume attributed to that automation; renaming the cutoff/seasonal automation degrades to manual; a stale stamp after a writer crash expires after 120 s; deploy-time helper-mapping consistency), the inherited 10–60 s command lag, the hand-started master fan seen only through the watcher, D3 (a nap wrap-up still blocked at 18:30 leaves the fan on with the nap direction; one notice), and the watcher's conservative manual verdict in the rare race where a resume state event precedes the cutoff run's end while the sensor cleared less than 2:45 ago.

