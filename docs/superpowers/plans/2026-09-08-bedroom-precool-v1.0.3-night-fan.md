# Bedroom Sleep Pre-Cool v1.0.3 — `night_fan` input — Implementation Plan (epic #18)

> **Status: Done — deployed 2026-09-08 09:28Z, session #24 closed 2026-09-09.** T1 shipped as 1662e85 + board fix 70d3b8d, merged via PR #27 (`563167b`), deployed with `scripts/deploy-blueprint.sh` (instance `night_fan: low`, alias v1.0.3). Design board 20260908-090730 PASS · code board 20260908-091857 PASS. Observation: 19:29 CEST lock set the fan to low with one command, no fan command overnight, 07:15 turn-off; the 24 h clean-log criterion was waived by Martin (single pre-existing `input_number.autolearner` range error, helper min fixed 60 → −60 on 2026-09-09).

> **For agentic workers:** small single-task change executed in the main loop (Fable); no subagents needed. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `bedroom_precool.yaml` v1.0.3 with a `night_fan` input (default `low`) applied at BEDTIME_LOCK, with tests, the migrated instance config, docs, and a live deploy before tonight's 19:29 CEST lock.

**Architecture:** additive blueprint input + one STEP 2c variable + one changed service-call target in the BEDTIME_LOCK branch. Deployment reuses `scripts/deploy-blueprint.sh` with `deploy/bedroom_precool_1779553673971.json`.

**Tech Stack:** HA 2026.9 blueprint YAML + Jinja2; pytest + PyYAML + Jinja2 render harness in `tests/test_bedroom_precool_structure.py`.

**Spec:** `docs/superpowers/specs/2026-09-08-bedroom-precool-v1.0.3-night-fan-design.md`
**Branch:** `feat/bedroom-precool-v1.0.3-night-fan` → PR → `main`. PR body carries `Session: #<N>` (deploying session — never `Closes`).

```
Stakes: standard
Trigger: default-up: automation logic change in bedroom_precool.yaml + test + instance JSON + docs; no hard trigger matched
Router: deterministic
Entry: B
tcb_manifest_sha: dc110c47de26fc65a046de31d918f4202236a801b20120fdf01abd22dee962cd
tcb_baseline: /home/martin/AI/reviews/tcb-baseline-2555a51858c49bad.txt
TCB_EXTRA: /home/martin/AI/projects/Blueprints_Home-nightfan/scripts/deploy-blueprint.sh
```

**Execution mode:** main loop (Fable) — one task of ~40 lines; boards at standard dial (R1 Opus + R2 Codex) at design-time (before T1) and code-time (after T1, before T2). `/effort xhigh` at both gates.

**Shell invariants:** tests from the worktree root via `~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q` (baseline 275 green on 4bd8041). Explicit paths on `git add`. The deploy script is not edited.

## Global constraints

- Additive input only (a removed/renamed input makes the stored instance `unavailable`).
- `night_fan_mode` is single-lined (feeds `!=` and `fan_mode:`; a folded scalar would leave trailing whitespace on the token).
- No boolean text literals; no datetime crosses a variables boundary.

---

### Task 1: blueprint + tests + instance + docs (RED → GREEN)

**Files:** Modify `bedroom_precool.yaml`, `tests/test_bedroom_precool_structure.py`, `deploy/bedroom_precool_1779553673971.json`, `requirements_bedroom_precool.md`, `README.md`.

- [x] **Step 1 (RED):** add tests — `night_fan` input default `low`; pass-through pin: every key of `blueprint.input` appears in top-level `variables` as `!input <key>` (design board R1-01/R2-01); rendered chain `night_fan_resolved` → `night_fan_mode` (re-parsed between renders): `['auto','low','medium','high']` → `low`; `['Auto','Low','Mid','High']` → `Low`; `['auto','medium','high']` → `''` → `fan_normal`; string-form `"['auto', 'low']"` → no substring match → fallback (R1-03); order pin `fan_normal:` < `night_fan_resolved:` < `night_fan_mode:` (R1-06); recursive walker over the STEP 6 `choose` tree resolving branches by their `phase == 'BEDTIME_LOCK'` / `phase == 'PRECOOL'` condition and asserting every `climate.set_fan_mode` inside them carries `fan_mode: "{{ night_fan_mode }}"` / `"{{ precool_fan }}"` and that the BEDTIME_LOCK guard compares `current_fan != night_fan_mode` (R1-07); STEP 7c notice `bedroom_precool_night_fan_unsupported` present; version pins 1.0.3; instance has `night_fan: low`. Run → fails.
- [x] **Step 2 (GREEN):** blueprint: input (Group 5, description names its gate), `enable_fan_control` description, **`night_fan: !input night_fan` in the top-level `variables:`**, `night_fan_resolved` + `night_fan_mode` after `fan_normal`, BEDTIME_LOCK fan step, STEP 7c notice, version 1.0.3 + history line; instance JSON key + alias; requirements table (BEDTIME-LOCK row ≤ 3, after-bedtime total, night-fan sentence); README beep bullet + feature bullet. Run → all green; `scripts/deploy-blueprint.sh --dry-run` green.
- [x] **Step 3:** commit (`feat(bedroom-precool): v1.0.3 — night_fan input (default low) at BEDTIME_LOCK`), push, PR with `Session: #<N>`.

### Task 2: code-time board → merge → deploy → observe

- [x] **Step 1:** `review-shipped` → `convene-board` (code-time, standard, CYCLE=1); action findings; `code-review-gate`; merge (merge commit, keep branch).
- [x] **Step 2:** deploy live with `scripts/deploy-blueprint.sh`; verify instance `on`, next trace `finished`, `night_fan_mode: low` in the trace variables, no log errors.
- [x] **Step 3 ([8] observe):** tonight 19:29 CEST → one `set_fan_mode low` (or none), no fan command until 07:15; tomorrow 07:15 one turn-off; 24 h log clean → `observe:closed` → finish the session.
