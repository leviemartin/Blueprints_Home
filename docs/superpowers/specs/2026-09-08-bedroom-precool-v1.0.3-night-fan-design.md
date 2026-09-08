# Bedroom Sleep Pre-Cool v1.0.3 — `night_fan` input (design)

**Date:** 2026-09-08 · **Repo:** Blueprints_Home · **Entry:** Stack B B (operator-decided feature under epic #18) · **Session:** opened JIT (see the issue link in the plan)
**Research-validate:** DEFERRED by the operator — Martin decided the input and its default ("add night_fan low", 2026-09-08 ~09:40 CEST); it is a fan-level preference on his own unit with no external design question. Recorded here per triple-check Pass 0.

```
Stakes: standard
Trigger: default-up: automation logic change in bedroom_precool.yaml + test + instance JSON + docs; no hard trigger matched (deploy script untouched, pinned)
Router: deterministic
Entry: B
```

## 1. Why

At BEDTIME_LOCK (bedtime − 1 min) v1.0.2 sets the fan to the discovered "normal" mode (`fan_normal` → `medium` on the LG unit). Martin set it to `low` by hand at 22:47 on 2026-09-07 because medium felt too cold/draughty; the warmest bedroom still held 23.2–23.5 °C on low all night. He wants low to be the default night fan without touching the pre-bedtime behaviour (DRIVE = high, HOLD = medium). Accepted trade-off (board R1-08): on a hot night the lock fires while PRECOOL is still in DRIVE, so the fan drops high → low together with the setpoint change and the deep-night check never touches the fan; the per-instance lever is `night_fan: medium` or `high`.

## 2. Design

- **New input `night_fan`** (Group 5 — behaviour): select with options `low` / `medium` / `high` / `auto`, **default `low`**. Description: the fan mode locked in at bedtime and left alone overnight; **only used when Enable Fan Control is on**; matched case-insensitively against the unit's modes; if the unit does not offer it the normal (hold) fan mode is used and a notification says so. `enable_fan_control`'s description gains "…and the Night Fan Mode at bedtime" (board R1-05).
- **Top-level `variables:` pass-through:** `night_fan: !input night_fan` under Group 5 (every input is passed through there; board R1-01/R2-01 — without it the Jinja variable is Undefined and the feature silently no-ops).
- **New STEP 2c variables (single-lined, feed `!=` and `fan_mode:`):** `night_fan_resolved` loops `ac_fan_modes` and returns the unit's own spelling whose `lower` equals `night_fan | lower` (repo convention: case-tolerant fan-mode resolution like `fan_high` / `fan_normal` / lg_ac_climate.yaml; a unit reporting `Low` resolves to `Low`), or `''`; `night_fan_mode` = `night_fan_resolved` if non-empty else `fan_normal`. `ac_fan_modes` is the list already discovered from the entity (lists survive the variables boundary; `fan_normal` consumes it the same way).
- **STEP 7c notice** (after 7b): when `enable_notifications and enable_fan_control and ac_fan_modes | length > 0 and night_fan_resolved == ''`, create `bedroom_precool_night_fan_unsupported` naming the configured mode, the unit's modes and the fallback (board R1-04 — a silent degrade contradicts the STEP 5/7a convention).
- **BEDTIME_LOCK fan step** uses `night_fan_mode` instead of `fan_normal` (guard `current_fan != night_fan_mode`, data `fan_mode: "{{ night_fan_mode }}"`). Everything else is unchanged: PRECOOL DRIVE = `fan_high`, PRECOOL HOLD = `fan_normal`, NIGHT_HOLD/DEEP_HOLD issue nothing, DEEP_NIGHT_CHECK never touches the fan, `enable_fan_control: false` still disables every fan call.
- **Beep accounting (board R1-02/R2-02):** the lock's fan command stays capped at one, but it now fires on every running night — v1.0.2 issued zero fan commands when PRECOOL ended in HOLD (fan already `fan_normal`), v1.0.3 issues one (medium → low). Accepted: Martin's choice. The BEDTIME_LOCK branch can emit up to three commands (mode, setpoint, fan; typically 1–2); the deep-night check at most one. The requirements table and the README beep bullet are corrected to those counts (they read 0–1 / 0–2).
- **Instance** `deploy/bedroom_precool_1779553673971.json`: add `"night_fan": "low"` explicitly (documents the choice; the default would do the same). Alias → v1.0.3.
- **Version** 1.0.3; description history line; requirements table BEDTIME-LOCK row + a sentence; README feature bullet.

## 3. Alternatives considered

1. `enable_fan_control: false` and set the fan by hand — loses the high fan during DRIVE and the deterministic lock. Rejected.
2. Re-order the `fan_normal` candidate list to prefer low — changes the pre-bedtime HOLD fan too and every other instance of the blueprint. Rejected.
3. A dedicated input (chosen) — additive, default-safe, per-instance.

## 4. Live facts (Pass 2.5 probe, 2026-09-08 09:45Z)

`climate.bedrooms` `fan_modes` = `["auto","low","medium","high"]` → the select options are exactly the unit's modes; `current_fan` reads the `fan_mode` attribute.

## 5. Acceptance

- Tests: input exists with default `low`; every declared input is passed through the top-level `variables:` as `!input <name>` (R1-01); rendered `night_fan_resolved`/`night_fan_mode` chain (each value re-parsed): `low` on the LG list, `Low` on a `['Auto','Low','Mid','High']` unit, `fan_normal` when absent, and no substring match when `ac_fan_modes` arrives as a string (R1-03); order pin `fan_normal:` → `night_fan_resolved:` → `night_fan_mode:` (R1-06); a recursive branch walker resolves the STEP 6 branches by their `phase == '…'` condition and asserts the `climate.set_fan_mode` data inside BEDTIME_LOCK is `{{ night_fan_mode }}` and inside PRECOOL is `{{ precool_fan }}` (R1-07); STEP 7c notice present; version + instance pins. Suite green.
- Deploy via `scripts/deploy-blueprint.sh` before 19:29 CEST; instance `on`.
- Observation ([8]): trace at 19:29 CEST shows one `climate.set_fan_mode` → `low` (or none if already low), no fan command afterwards until 07:15; 24 h log clean.
