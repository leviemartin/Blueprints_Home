# Bathroom Heating Rack v3.0.0 — room-sensor thermostat — Implementation Plan (epic #33, session #34)

> **Status: Deployed 2026-09-24 13:09Z — observing (session #34 open, `<!-- observe:open -->`).** PR #35 merged as `a8bec6f`; code board 20260924-083742 PASS. Tasks 1–3 done; Task 4 deploy and read-path proof done (the rack was Tuya-offline 06:20–13:27Z; manual v3 run clean at 13:33Z). Observation is automated by `heating-rack-v3-observe.timer` (07:53/19:53 Amsterdam) → Telegram topic "Blueprints_Home - Heating rack v3 observation (#34)"; after 6 clean windows it posts READY TO CLOSE, then a Claude session closes #34 and epic #33. Follow-ups filed: #36 (ventilator all-day cycling), #37 (stale-sensor guard), #38 (learned warmup rate).

```text
Driver: claude
Entry: A (new idea; design settled with Martin 2026-09-23/24; no discovery phase opened — no explicit brainstorm, no open coupled material decisions)
Stakes: standard
Trigger: blueprint logic on a live automation that actuates a heating element. The physical-safety envelope is unchanged or reduced versus v2: the device-side drive stays at 24 °C, which v2 already sent; no room sensor now means no heat instead of on-schedule heat; boost drops from 26 °C to a room-governed 22 °C. No auth, secrets, trust boundary or governing-file consequence. The instance config migration is backed up by deploy-blueprint.sh (.prev.json).
Dispatch ledger: /home/martin/AI/reviews/heating-rack-v3-20260924/ledger.json
Dispatch allowance: 24
Review allowance: 3
TCB baseline: /home/martin/AI/reviews/tcb-baseline-heating-rack-v3-20260924.txt
TCB aggregate: b0d08e79fbf363a66992aa30b5f97d7e64151aeec75c7973f6b3b95aa6d6387f
Declared TCB changes: none (TCB_EXTRA = /home/martin/AI/projects/Blueprints_Home/scripts/deploy-blueprint.sh, STACKB_DRIVER=claude on every verify)
Boundaries: none
Plan author: orchestrator (Opus/high)
```

**Spec:** `docs/superpowers/specs/2026-09-23-heating-rack-v3.0.0-design.md` (audit, logic flow, decisions). **Session:** #34 (the brief, acceptance and observation criteria live in its body). **Unresolved product choices:** none. The warmup push fires on every start (Martin, 2026-09-24).

**Baseline (2026-09-24):**
- The repo suite gives 354 passed.
- `scripts/deploy-blueprint.sh --dry-run` passes on the draft YAML and the migrated instance JSON (22 inputs).
- `drafts/heating-rack-v3.0.0/sim_v3.py` gives 26/26 PASS.

**Design gate:** none (standard). **Required review:** stage 6, one fresh Opus R1 chartered for correctness, security and edge cases.

## Invariants (every task)

- The rack's `current_temperature` is never read by the blueprint (comments excepted).
- Heating starts only while room < target − `restart_deadband`, and once heating it stops at room ≥ target. There is no heating at or above 22.0 °C on start.
- Heating happens only inside an open window, during a boost, or not at all. Evening slots open exactly at their start time when `evening_preheat` is false.
- No room sensor (primary and every backup non-numeric) means the idle setpoint, a `_blind` priority label and the sensor warning.
- Every push runs after the climate calls. Boost expiry stays the last step. `mode: restart` stays.
- Every setpoint is rounded to the device step and clamped to min/max before any comparison or write.

## Task 1 — v3.0.0 in place, test-first

- **Route and reason:** delegate. Every bounded-worker condition holds. The behaviour is pinned by the spec, the session acceptance and 26 scenario rows. Interfaces and paths are pinned. The acceptance checks can be run by the worker and re-run by the orchestrator. The pattern is the existing test file plus the draft. Ownership is one component. There is no high-risk consequence (see Trigger). It is not a diagnosis.
- **Owner/model/effort:** Sonnet (`sonnet`), high. Isolated worktree `~/AI/projects/Blueprints_Home-wt/heating-rack-v3` on branch `feat/heating-rack-v3.0.0` from `main` (`adc737a`).
- **Outcome:** `bathroom_heating_rack.yaml` is v3.0.0, as drafted in `drafts/heating-rack-v3.0.0/bathroom_heating_rack.yaml`. The only changes are removing the "DRAFT — Stack B input, not deployed" wording and fixes that a failing acceptance test proves necessary; every such fix is reported. The instance JSON, the requirements doc and the README section describe v3. The `drafts/heating-rack-v3.0.0/` directory is gone, and its scenario rows live in the test suite.
- **Interfaces and consumers:**
  - Blueprint inputs removed: `fan_switch`, `comfort_floor_delta`.
  - Inputs added: `backup_temp_sensors`, `drive_setpoint`, `restart_deadband`, `evening_preheat`.
  - Consumers: the live instance `1776551429917` (migrated by the new `deploy/bathroom_heating_rack_1776551429917.json`), `scripts/deploy-blueprint.sh` (unchanged; the instance JSON is its input), the HA traces/debug dump (new variables `target_source`, `room_target`, `heat_line`, `call_for_heat`, `heating_now`, `drive_setpoint_dev`) and the priority labels (`P3_boost`, `P4_evening`, `P5_morning` with the `_satisfied`/`_blind` suffixes, `P1_vacation`, `P6_idle`; `P2_fan_coord` is gone).
- **Paths (owned):**
  - `bathroom_heating_rack.yaml`
  - `tests/test_bathroom_heating_rack_structure.py`
  - `deploy/bathroom_heating_rack_1776551429917.json`
  - `requirements_bathroom_heating_rack.md`
  - `README.md` ("Bathroom Heating Rack Blueprint" section only)
  - `drafts/heating-rack-v3.0.0/` (deleted)
- **Acceptance checks:**
  1. **RED first.** Rewrite the structure tests for v3 before replacing the YAML and run them against the v2 file. They must fail on the v3 pins: input schema, trigger roster without the fan trigger, the new variables, and the scenario rows. Record the failing count.
  2. **Test coverage.** The tests pin:
     - the exact v3 input keys and defaults;
     - the removed inputs being absent;
     - the trigger roster (T1 periodic, boost, vacation, HA start, `climate_lost` with 5 min, `temp_lost` with 10 min; no fan);
     - the action shape (climate validation before the service calls, pushes after the climate calls, boost expiry last, debug manual-only);
     - no `current_temperature` in any non-comment line;
     - no `fan_switch`/`entity_fan`/`P2_fan_coord`;
     - no bare boolean text;
     - the locale-safe weekday;
     - the setpoint rounding, clamping and step rows (retained from v2 where the templates are unchanged);
     - the notify filter;
     - the warmup-lead rows;
     - the hold-until anchor rows.
  3. **Scenario rows ported.** All 26 rows from `sim_v3.py` become parametrised tests, with expectations copied from the spec/sim and not re-derived from the implementation. Add at least these failure and edge rows:
     - backup-list order (the first numeric backup wins over a later one);
     - the primary numeric while the backup is dead uses the primary;
     - `evening_preheat: true` opens the evening early by the ΔT lead;
     - the restart line with `restart_deadband` 0.5;
     - a room reading of `"21.7"` exactly while idle does **not** start (strict <).
  4. **GREEN.** Copy the draft into `bathroom_heating_rack.yaml` and the draft instance into `deploy/`. The full suite then passes with `~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q`, and no other blueprint's tests change.
  5. **Deploy dry-run.** The existing `test_deploy_dry_run`-style test, pointed at the new instance, passes. `bash scripts/deploy-blueprint.sh --dry-run bathroom_heating_rack.yaml leviemartin/bathroom_heating_rack.yaml deploy/bathroom_heating_rack_1776551429917.json` reports `validation passed`.
  6. **Docs.** `requirements_bathroom_heating_rack.md` describes v3: overview, goals, hardware (Aqara primary, Hue backup), control law with the formula block, priority order, triggers and notifications. The README heating-rack section is updated to match. The version string reads 3.0.0 in the blueprint name, the description, the instance alias and both docs.
  7. `git status` in the worktree shows only the owned paths.
- **Dependencies:** none. It is the only execution task, so no parallel writers.
- **Worker rules:**
  - No commits unless the orchestrator's brief says so. The orchestrator commits on the branch after acceptance.
  - No `git stash`.
  - No nested dispatch, review, research or fan-out; any added work returns to the orchestrator for reservation.
  - Stop and return on ambiguity, a needed change outside the owned paths, or a failing invariant.
  - One targeted self-correction is allowed per acceptance failure.

## Task 2 — integrated code gate (stage 6)

- **Route:** orchestrator, through `review-shipped` → `convene-board`. Standard stakes: one fresh Opus R1 via `claude-leg.sh` at high effort, with `STACKB_DRIVER=claude`, `STACKB_LEDGER`, `STACKB_TASK=heating-rack-v3`, `STACKB_STAGE=6`.
- **Charter:** correctness, security and edge cases, with emphasis on:
  - the latch/deadband interaction with `heating_now` shared across slots and boost;
  - the boost → window hand-off;
  - the input migration versus the live instance;
  - the push ordering;
  - the strict `<` comparisons on 0.1-grid sensor values.
- **Budget:** review allowance 3 = the initial round plus up to two scoped deltas (correction waves ≤ 2).

## Task 3 — completion checks (stage 7)

- **Route:** command, then `code-review-gate`.
- **Checks:**
  - full pytest suite green;
  - deploy dry-run passes;
  - TCB verify rc 0 against the baseline with the same `TCB_EXTRA` and `STACKB_DRIVER=claude`;
  - one PR on `leviemartin/Blueprints_Home` with the body `Session: #34` (deploying).
- **Merge** only with Martin's authorization.

## Task 4 — deploy and observe (stage 8)

- **Pre-deploy:**
  - HA WS `validate_config` on the input-substituted config;
  - confirm `notify.mobile_app_martin_fold` exists;
  - confirm `sensor.temp_sensor_bathroom` and `sensor.bathroom_temperature` are numeric.
- **Deploy:** `scripts/deploy-blueprint.sh bathroom_heating_rack.yaml leviemartin/bathroom_heating_rack.yaml deploy/bathroom_heating_rack_1776551429917.json` from merged main.
- **Read-path proof:**
  - the instance is `on`;
  - a manual run produces the debug dump showing the Aqara reading as the room and `target_source`;
  - the next periodic tick finishes without log errors.
- **Observation:** the criteria (1)–(7) in the #34 body, for at least 3 days. When they pass, set `<!-- observe:closed -->`, run `closing-session`, and close #34 and epic #33.
- **Follow-ups to queue at closing (not in scope):**
  - the ventilator's all-day cycling at 76 % RH (audit A8);
  - a learned warmup rate;
  - a stale-sensor guard.

## Decided by orchestrator (Martin may revert)

1. **Control law:** 24 °C drive while room < line, and 7 °C idle otherwise. The line is 22.0 °C once heating and 21.7 °C to start.
2. **Evening start:** 18:30 exactly (`evening_preheat: false`). The alternative is warm by 18:30.
3. **Backup sensor:** the Hue motion sensor. With no room sensor, nothing heats.
4. **Slot structure:** keep the 4-slot machinery with the B slots empty (smaller diff) rather than collapsing to two slots.
5. **Fan input:** deleted outright rather than kept as a disabled option.
6. **Stakes:** standard, per the Trigger above.
7. **Discovery:** no discovery phase. The 09-23 intake answered the product questions, and the one open point (the warmup push) was asked directly on 09-24.
8. **Stage 5 route:** Sonnet/high bounded worker in an isolated worktree; the orchestrator commits after acceptance.
