# Bedroom Sleep Pre-Cool v1.2.1 — PRECOOL setpoint gated on known AC limits (bug #30) — Implementation Plan (epic #18, session #31)

> **Status: Done — merged as PR #32 (`88719d0`), deployed 2026-09-15 21:50Z, observation closed 2026-09-16 19:43 local (session #31, bug #30 and epic #18 closed). Code board 20260915-213915 PASS (R1 Opus initial + delta-1; wave 1 + post-board fixes); report in `reviews/board-20260915-213915.md`.** Model exception recorded on #31: Martin approved running this chain on the Fable session; the standard code gate (fresh Opus R1 through the board wrapper) still applied.

```text
Driver: claude
Entry: B (queued bug #30)
Stakes: standard
Trigger: blueprint logic on a live automation that actuates the bedroom AC; no auth/secrets/destructive-data/governing-file consequence; scripts/deploy-blueprint.sh is executed, not edited
Dispatch ledger: /home/martin/AI/reviews/precool-v121-20260915/ledger.json
Dispatch allowance: 24
Review allowance: 3
TCB baseline: /home/martin/AI/reviews/tcb-baseline-precool-v121-20260915.txt
TCB aggregate: 8808b0066f03beb79382749e04dbc60530427f3e7c314fcbb7bca20c8552a723
Declared TCB changes: none (TCB_EXTRA = /home/martin/AI/projects/Blueprints_Home/scripts/deploy-blueprint.sh, STACKB_DRIVER=claude on every verify)
```

**Source:** bug #30 (observation of #19/#26, 2026-09-15). **Unresolved product choices:** none.

## Defect

`ac_min_temp: "{{ state_attr(ac_climate, 'min_temp') | float(16) }}"` (STEP 2a) falls back to 16 °C when the LG ThinQ entity has not reported `min_temp`, which happens on the tick that turns the unit on. `effective_drive = max(drive_setpoint 16, ac_min_temp)` then evaluates to 16 and the PRECOOL `climate.set_temperature` call is rejected by Home Assistant ("Accepted range is 18 to 30"), aborting that tick's run. Seen 2026-09-14 17:02 local; the next tick set 18 °C.

## Task 1 — gate the PRECOOL setpoint command on known AC limits (TDD)

- **Route and reason:** orchestrator inline; recorded exception: handing off costs more than the remainder (one variable, one condition, one test).
- **Owner/model/effort:** this session (Fable, per the #31 exception).
- **Outcome:** a new STEP 2a variable `ac_limits_known` is true only when both `min_temp` and `max_temp` attributes are present; the PRECOOL `climate.set_temperature` call runs only when `ac_limits_known` is true (on top of its existing idempotency condition). With limits unknown the tick still turns the unit on and sets the mode and fan; the setpoint follows on the next tick, as the 13 and 15 September starts already showed. No other step changes; the fallback constants stay (they only feed clamps that are now never commanded blind).
- **Interfaces and consumers:** `bedroom_precool.yaml` PRECOOL branch (STEP 6); consumers are the live instance `1779553673971` and the structure tests. The manual-override detection (`known_setpoints`) is unchanged.
- **Paths:** `bedroom_precool.yaml`, `tests/test_bedroom_precool_structure.py`, `deploy/bedroom_precool_1779553673971.json` (alias v1.2.1), `README.md` (one sentence in the pre-cool section), `requirements_bedroom_precool.md` (one line in Functional Requirements).
- **Acceptance checks:** (1) new structure test `test_precool_setpoint_command_is_gated_on_known_ac_limits` fails before the change (RED) and passes after (GREEN): the PRECOOL `set_temperature` call carries `ac_limits_known` in its condition chain, `turn_on`/`set_hvac_mode`/`set_fan_mode` do not, `ac_limits_known` renders false when either attribute is `None` and true when both are numbers, and it is defined before STEP 3; (2) the existing 350 tests stay green (`~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q`); (3) `scripts/deploy-blueprint.sh --dry-run bedroom_precool.yaml leviemartin/bedroom_precool.yaml deploy/bedroom_precool_1779553673971.json` passes; (4) version 1.2.1 in the blueprint name/description and the instance alias.
- **Dependencies:** none.

## Task 2 — integrated code gate, merge, deploy, observe

- **Route:** orchestrator + `convene-board` (standard: one fresh Opus R1 via `claude-leg.sh`, `STACKB_DRIVER=claude`, ledger `STACKB_LEDGER`/`STACKB_TASK`/`STACKB_STAGE`), then `code-review-gate`.
- **Stage 7 verification:** pytest suite, dry-run deploy, TCB verify rc 0 against the baseline above, PR `Session: #31` on `leviemartin/Blueprints_Home` (one PR), merge authorised by Martin ("fix bug #30 and deploy it", 2026-09-15).
- **Stage 8 deploy:** `scripts/deploy-blueprint.sh bedroom_precool.yaml leviemartin/bedroom_precool.yaml deploy/bedroom_precool_1779553673971.json` from merged main over the Tailscale route; instance `on`; first tick `finished`.
- **Stage 8 observation (`<!-- observe:open -->` on #31):** at the next pre-cool start (turn-on tick ≈ 17:00 local on 2026-09-16) the system log shows no "Provided temperature … is not valid" error for `automation.bedroom_sleep_pre_cool_v1_0_0`; the setpoint reaches the clamped drive value (18 °C) within two ticks; the 19:29 lock, fan settle and bias write proceed as on 10–15 September. Pass → `<!-- observe:closed -->`, `gh_finish_session`, close #31 and bug #30, close epic #18 again.

## Rollback

Redeploy the previous instance config from `~/AI/reviews/deploy-31-live-before-<ts>/` (the deploy script backs up the live instance) or check out `dbeda3b` and rerun the deploy script.
