# LG AC Climate v1.2.0 — Implementation Plan

> **Status: Done (2026-08-18).** All tasks T0–T5 shipped: merged `a7553a6`
> (PR #9, session #8, epic #7 closed), deployed via blueprint/save + instance
> `comfort_margin: 1.0`, read-path trace gate PASSED (deep_pull_depth 0.5 /
> actives 21.5·22.5 / gates true). One observation pending: the first live
> deep-pull→OFF cycle (deploy landed after the 22:30 schedule close; expected
> next daytime the room crosses 23.0).

**Spec:** `docs/superpowers/specs/2026-08-18-lg-ac-climate-v1.2.0-design.md`
**Branch:** `lg-ac-v1.2.0` → PR → `main`

```
Stakes: standard
Trigger: default-up: automation logic change in lg_ac_climate.yaml, no hard trigger matched
Router: deterministic
```

**Execution mode:** inline main-loop (opus-tier driver at effort high) — the diff is
one blueprint file + one test file + one requirements doc; SDD fan-out would cost
more than it saves. Boards per standard stakes: 2 lenses (Claude Opus R1 + Codex
R2) at design-time and code-time, xhigh at the gates.

**Shell invariants:** suite runs from repo root via
`uvx --with pyyaml --with jinja2 pytest tests/ -q` (system python3 has no
pytest; verified 2026-08-18, 53 baseline tests green); never pipe test output
through `tail` (exit-code masking); per-pillar commits, explicit paths only,
no `git add -A`.

---

## T0 — Pre-flight (RED baseline)
Branch `lg-ac-v1.2.0` off up-to-date `main`; full suite green before any edit.

## T1 — Tests first (RED)
Update pins in `tests/test_lg_ac_climate_structure.py`:
1. `test_version_bumped` → `v1.2.0` (name + description).
2. `comfort_margin` input: description pin updated; default pin stays 0.5
   (C3 rev 3 — see item 11).
3. `test_validation_gate_covers_margin` → conds[1] uses `>` not `>=`.
4. `test_cool_heat_desired_values` → cool pins
   `{{ setpoint_cool_active_q if (deadband_active and cool_deep_ok) else setpoint_cool_q }}`,
   heat pins `{{ setpoint_heat_active_q if (deadband_active and heat_deep_ok) else setpoint_heat_q }}`
   (spec C2 — overshoot only when the off-state is reachable AND feasible).
5. `test_setpoint_quantization_variables` → ADD exact-string pins for the five
   new variables (verbatim from spec C1, whitespace-normalized).
6. NEW `test_rendered_active_setpoint_and_gates` — render BOTH the setpoint and
   its `_deep_ok` gate for ALL 16 rows of the spec edge table (validation-legal;
   gates render "True"/"False" strings; expected values verified by
   exact-arithmetic simulation). Coverage classes the board demanded: device-
   limit collapse rows (B194701-01/R2-4), 0.1-step float-dust rows
   (R1R2-3/R2R2-2 — raw-float compares rendered 21.7/False where 22.2/True is
   correct), thin-depth and clamp-thinning rows (R1R2-2), trigger-line rows
   (B194701-03). Rendering context supplies `deep_pull_depth` from its own
   rendered template, not hand-injected.
7. `test_maintenance_desired_values` — UNCHANGED (regression pin: maintenance
   keeps boundary setpoints).
8. `test_description_documents_new_features` — pin a v1.2.0-ONLY token (the
   off/on-transition-beeps sentence) so the pin is RED against v1.1.0 (board
   R1-6); also pin the C4 notification message rewording ("must not exceed").
9. NEW `test_active_setpoint_variable_ordering` — full ordering chain (R1-8 +
   R1R2-7): index(`ac_temp_step`) < index(`deep_pull_depth`) <
   index(`setpoint_cool_active_q`|`setpoint_heat_active_q`) <
   index(`cool_deep_ok`|`heat_deep_ok`), each gate after ITS setpoint.
10. NEW `test_deep_infeasible_notification_block` — STEP 2b gains the C7
    create/dismiss choose on `notification_id: ac_climate_deep_infeasible`,
    condition `{{ cool_deep_ok and heat_deep_ok }}`, `continue_on_error` on
    both services.
11. `test_new_input_schemas` — comfort_margin default pin STAYS 0.5 (C3 rev 3:
    default unchanged; operator instance set per-instance at deploy).
12. C6 (requirements doc) is intentionally untested — docs pillar, no test
    harness reads it (board R1-6 note).

Gate: changed/new pins FAIL against current v1.1.0 file (true RED — satisfies the
pins-blind-in-both-directions rule); all untouched tests stay green.

## T2 — Blueprint edit (GREEN)
Apply spec C1–C5 to `lg_ac_climate.yaml` (formulas verbatim from spec). Gate:
full suite green; `python3 -c "yaml load"` parses; grep confirms maintenance
branch still references `setpoint_cool_q`/`setpoint_heat_q`.

## T3 — Requirements doc
Spec C6 on `requirements_lg_ac_climate.md`.

## T4 — Ship
Per-pillar commits (spec · plan · code+tests · requirements) → PR (`Closes #<session>`)
→ code-time board (review-shipped) → fix waves if any → merge.

## T5 — Deploy + live-verify (operator-visible)
Pre-deploy: run the spec's instance blast-radius checklist (R1-4 + R1R2-1) at
deploy time — re-enumerate instances, live-read each device's
`target_temp_step`/`min_temp`/`max_temp`, compute PREDICTED
`cool_deep_ok`/`heat_deep_ok` per instance; deploy gate FAILS if the
living-room instance predicts either gate False. Also assert each device's
`min_temp` and `max_temp` are exact multiples of its `target_temp_step`
(code board BC-02/R1C-2: a non-step-anchored bound can pass the gate with an
unstorable command → beep-per-tick loop; LG units observed are all anchored). Then: (1) push merged YAML via
HA WS `blueprint/save` (`domain: automation`,
`path: leviemartin/lg_ac_climate.yaml`, `yaml: <file contents>`,
`allow_override: true`); no input renames — instances survive (spec Migration).
(2) Set the living-room instance `comfort_margin: 1.0` via
`POST /api/config/automation/config/1775578219942` (C3 rev 3; v1.1.0 migration
pattern — POST the full config back with only the margin added). (3) Reload /
confirm `automation.lg_ac_climate_control_v1_0_0` stays `on` (NOT
`unavailable`). Read-path proof is behavioral AND branch-independent (R1-10):
the next tick's trace `changed_variables` must contain `deep_pull_depth` /
`setpoint_cool_active_q` / `cool_deep_ok` with expected rendered values
(0.5 / 21.5 / True — these variables cannot exist in a v1.1.0 render); that,
not the file push, is the deploy gate. The commanded active setpoint (21.5) is
secondary confirmation when the tick lands in 4f. Confirm NO
`ac_climate_deep_infeasible` notification exists. Then (time-permitting before
the 22:30 schedule) observe release→OFF once the external average reaches 22.0.
Capture full trace output (never tail). Report observed vs pending honestly.
