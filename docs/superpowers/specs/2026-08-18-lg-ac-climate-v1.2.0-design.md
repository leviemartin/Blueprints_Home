# LG AC Climate Control v1.2.0 — Design Spec

**Date:** 2026-08-18 (rev 3 — after design-board rounds 1+2)
**Version:** v1.2.0 (delta against v1.1.0 — see `2026-08-09-lg-ac-climate-v1.1.0-design.md`)
**Blueprint file:** `lg_ac_climate.yaml`
**Driver:** 2026-08-18 live field finding — the in-range turn-off ("deadzone") is
structurally unreachable while the AC is actively cooling; the unit idles in-mode
all day instead of switching off. Operator decision: real off-periods (silence)
outrank minimum command count; push depth 1.0 °C for the living-room instance.

```
Stakes: standard
Trigger: default-up: automation logic change in lg_ac_climate.yaml, no hard trigger matched
Router: deterministic
```

---

## Root cause (verified live, 2026-08-18)

Living-room instance: comfort 21–23 °C, `comfort_margin` default 0.5, external
sensors averaged 22.75, AC internal sensor 23.0, outdoor 19.3 °C (deadband armed,
maintenance mode NOT active). Traces: every 10-min tick lands in branch 4f (COOL)
and sends zero commands.

Mechanism: v1.1.0 commands the cool setpoint at exactly `temp_high` (23), but the
hysteresis release requires the *external* average to reach `temp_high − margin`
(22.5). The LG stops compressing when *its own* sensor reads the setpoint, so the
room equilibrates at ~22.6–22.9 — above the release threshold — and cool mode
never releases. The off-branch only fires when outdoor conditions passively cool
the room, or at schedule end. Heat mode has the mirror-image defect, made worse by
the wall unit's warm-bias while heating (rising hot air crosses the intake).
Measured cool-mode bias: internal − external ≈ +0.25 °C.

General law: **a release threshold measured on sensor A is unreachable if the
actuator self-limits on sensor B at the same value.** The commanded setpoint must
sit far enough beyond the release threshold to absorb inter-sensor bias.

## Premise & alternatives

Operator decision 2026-08-18 (explicit, after a three-option tradeoff): real
off-periods outrank minimum command count. Alternatives rejected:
- **Keep v1.1.0 idling** — fewest beeps, inverter idle is cheap; rejected by the
  operator (fan noise + all-day-on beats the beep saving).
- **`comfort_margin: 0` per instance** (v1.0.0 cycling, no code change) — zero-width
  band flaps on sensor noise; the beeping this causes is what the margin was
  added to prevent.

**Research-validate: deferred with rationale.** The failure mechanism was verified
*live* this session (traces + states — stronger evidence than community research);
the fix is the canonical thermostat overshoot/hysteresis pattern; and the v1.1.0
research-validation (PROCEED, five HA API facts) covers every HA surface this
change touches — none of the five constraints is contradicted (no new selectors,
no `from_json`, no trigger changes, `min_version` untouched).

## Decision

*(rev 3 wording — board R1R2-5: this paragraph states the implemented rule.)*

Introduce **active-setpoint overshoot with a guaranteed authority depth**: while
actively cooling (heating) and the deadband is active, command the **largest
(smallest) device-grid setpoint at least `deep_pull_depth` below (above) the
release threshold**, where `deep_pull_depth = max(target_temp_step, 0.5 °C)` —
0.5 °C being the bias floor from the live measurement. The unit then keeps
compressing until the *external* sensors cross the release, and the blueprint
genuinely turns it OFF. A strict per-mode feasibility gate falls back to the
v1.1.0 boundary setpoint (with an operator notification) when no such grid point
exists inside the comfort range.

Worked operator example (21–23, margin 1.0, step 0.5): cool release 22.0, depth
max(0.5, 0.5) = 0.5 → command 21.5; OFF when externals ≤ 22.0; room drifts
silently back up; cool re-triggers only above 23.0. Heat mirrors: command 22.5,
OFF at ≥ 22.0, re-trigger below 21.0.

Maintenance mode (extreme-outdoor branch) is **unchanged**: it deliberately holds
at the comfort boundary and lets the internal thermostat cycle quietly. The
overshoot applies only to the active COOL (4f) and HEAT (4g) branches.

## Changes

### C1 — Five new STEP-1 variables (depth, active setpoints, feasibility gates)

*(Redesigned across board rounds 1+2 — B194701-01/-02/-03 killed the round-0
clamp design; R1R2-2/-3 and R2R2-2 killed round 1's minimal-depth + raw-float
compares. Final shape: epsilon-disciplined grid-count quantization against a
depth floor, device-only clamps, gates on the post-clamp value with `round(2)`
on both sides of every compare.)*

Inserted immediately after `setpoint_heat_q`, in this order (each references the
previous; HA renders a `variables:` block in declaration order — R1-8/R1R2-7):

```yaml
deep_pull_depth: "{{ [ac_temp_step, 0.5] | max }}"
setpoint_cool_active_q: >-
  {% set r = temp_high | float - margin | float %}
  {% set q = ((((r - deep_pull_depth) / ac_temp_step) + 0.001) | round(0, 'floor')) * ac_temp_step %}
  {{ ([([q, ac_min_temp] | max), ac_max_temp] | min) | round(1) }}
setpoint_heat_active_q: >-
  {% set r = temp_low | float + margin | float %}
  {% set q = ((((r + deep_pull_depth) / ac_temp_step) - 0.001) | round(0, 'floor') + 1) * ac_temp_step %}
  {{ ([([q, ac_max_temp] | min), ac_min_temp] | max) | round(1) }}
cool_deep_ok: >-
  {{ (setpoint_cool_active_q | float | round(2)) <= ((temp_high | float - margin | float - deep_pull_depth) | round(2))
     and (setpoint_cool_active_q | float | round(2)) > (temp_low | float | round(2)) }}
heat_deep_ok: >-
  {{ (setpoint_heat_active_q | float | round(2)) >= ((temp_low | float + margin | float + deep_pull_depth) | round(2))
     and (setpoint_heat_active_q | float | round(2)) < (temp_high | float | round(2)) }}
```

Semantics, cool: the release is `temp_high − margin` (external sensors). The
command is the largest grid multiple ≤ `release − deep_pull_depth`; the `+0.001`
(in grid-count units ≈ 0.0001–0.001 °C, far above float dust, far below any
selector grid) rescues exact grid hits from binary-float dust — R1R2-3's sweep
showed raw compares silently skip the step on 0.1-grids (216.99999999999997
ceils to the release itself). Clamp to **device bounds only** (`ac_min_temp` /
`ac_max_temp`); grid-valid for devices whose setpoint grid is anchored at a
multiple of `target_temp_step` (true for all LG units observed — R1R2-8; the
non-anchored-grid case is a pre-existing v1.1.0 property of `setpoint_cool_q`).
Then `cool_deep_ok` re-checks, on the **post-clamp** value with `round(2)` on
both sides of each compare (kills dust in both directions): (1) the full
authority depth survives — never a silent v1.1.0-stall reinstatement, including
when a device bound eats into the depth (clamp-thinning); (2) strictly above
`temp_low` — never parked on the heat trigger line (no full-range hunting on
coarse-step devices). Heat mirrors both. When a gate is false the config cannot
deep-pull for that mode: the branch **falls back to the boundary setpoint** and
C7 raises a persistent notification — degradation chosen over a config-error
stop (a stop would kill the safety pierces — R1-4 class). `ac_temp_step ≥ 0.1`
guaranteed by the existing zero-step guard. Both `_deep_ok` gates are `{{ }}`
boolean *expressions* (bare-boolean literal_eval rule).

Existing `setpoint_cool_q` / `setpoint_heat_q` (boundary values) remain, used
by the maintenance branch and as the fallback.

### C2 — Branches 4f/4g command the active setpoints — **only when reachable AND feasible**

```yaml
# 4f
desired_setpoint: "{{ setpoint_cool_active_q if (deadband_active and cool_deep_ok) else setpoint_cool_q }}"
# 4g
desired_setpoint: "{{ setpoint_heat_active_q if (deadband_active and heat_deep_ok) else setpoint_heat_q }}"
```

The overshoot exists to *reach the off-point*. When the deadband is disabled
(extreme outdoor), the blueprint never turns off — it hands over to maintenance
mode at the boundary. An unconditional overshoot would there produce a beeping
setpoint sawtooth (deep-pull → maintenance 23 → deep-pull …) where v1.1.0 idled
silently — a regression in exactly the case maintenance mode exists for.
Conditioning on `deadband_active` preserves v1.1.0 behavior verbatim in extreme
weather, and `*_deep_ok` adds the feasibility fallback. Weather outage ⇒
`deadband_active` true ⇒ overshoot + normal cycling — consistent with the
v1.1.0 fail-safe. Everything downstream (idempotence guard, manual-hold
expected-state JSON) follows `desired_setpoint` automatically.

### C3 — `comfort_margin` description rewritten; **default stays 0.5**; operator instance set to 1.0

*(rev 3 — board R1R2-1/R2R2-1 + R1-4: bumping the default paired every future
gate-false fallback with a deeper release than v1.1.0, and threatened any
narrow-range sibling instance. The operator's actual ask is behavior for the
living-room AC, delivered per-instance.)*

- Blueprint default remains **0.5** — sibling/future instances keep exact v1.1.0
  semantics unless opted in; a gate-false fallback under the default is
  *genuinely* v1.1.0 behavior.
- The living-room instance gets explicit `comfort_margin: 1.0` via the
  automation-config API at deploy (same POST pattern as the v1.1.0
  `weather_entity` migration).
- Description rewritten: margin = release depth into the comfort range; the
  commanded setpoint aims `max(device step, 0.5 °C)` past the release so the
  room sensors — not the unit's internal one — decide when it's done; `0`
  approximates v1.0.0 cycling.

### C4 — Validation operator `>=` → `>`

`{{ (margin | float * 2) > (temp_high | float - temp_low | float) }}`. Equality
(margin·2 = range width) is now legal — required by the operator's 21–23 +
margin 1.0 config. At equality the two *release* thresholds coincide at the
midpoint while the active targets straddle it (cool strictly below, heat
strictly above, enforced by the `_deep_ok` gates — R1R2-6); mode entry still
requires crossing `temp_low`/`temp_high`, so no oscillation. Notification
message updated ("twice the margin must not exceed the range").

### C5 — Version + description

Name/description → 1.2.0. Hysteresis bullet rewritten to describe
deep-hysteresis off-behavior; note added that off/on transitions beep by design
(accepted trade — the "Beep-Silent" steady-state property still holds while a
mode runs).

### C6 — `requirements_lg_ac_climate.md`

Climate-3 rewritten (overshoot + depth floor + feasibility fallback; margin
still defaults 0.5, operator instance 1.0); Safety-3 wording for the relaxed
validation; Climate-6 gains the accepted-beeps note. Docs pillar — untested by
design.

### C7 — Infeasibility notification (STEP 2b hygiene block) *(new in rev 3 — R2R2-1/R1-3)*

Appended to STEP 2b, same self-healing pattern as the sensor warning
(create/dismiss on a fixed `notification_id`, replaced not duplicated each tick):

```yaml
- choose:
    - conditions:
        - condition: template
          value_template: "{{ cool_deep_ok and heat_deep_ok }}"
      sequence:
        - service: persistent_notification.dismiss
          data:
            notification_id: "ac_climate_deep_infeasible"
          continue_on_error: true
  default:
    - service: persistent_notification.create
      data:
        title: "AC Climate Blueprint — Deep-pull infeasible"
        message: >
          The comfort range/margin and this AC's setpoint grid (step
          {{ ac_temp_step }}, min {{ ac_min_temp }}, max {{ ac_max_temp }})
          leave no valid deep setpoint for
          {{ 'cooling and heating' if (not cool_deep_ok and not heat_deep_ok) else ('cooling' if not cool_deep_ok else 'heating') }}.
          That mode falls back to boundary idling (v1.1.0 behavior).
        notification_id: "ac_climate_deep_infeasible"
      continue_on_error: true
```

Config-static condition → fires once per bad config, self-dismisses when the
config or device changes. Placed in STEP 2b so it runs regardless of which
ladder branch a tick takes.

## Edge cases (pinned in rendered tests — all rows validation-legal; verified by
exact-arithmetic simulation 2026-08-18)

Rendered with ac_min 16 / ac_max 30 / tl 21 / th 23 unless stated.
`gate` = the matching `_deep_ok` rendered string. depth = max(step, 0.5).

| Row | Case | setpoint | gate |
|---|---|---|---|
| 1 | cool m 1.0 step 0.5 (operator config) | 21.5 | True |
| 2 | cool m 1.0 step 1.0 (no feasible grid point) | 21.0 | False → boundary |
| 3 | cool th 23.5 tl 21.5 m 1.0 step 1.0 (grid-aligned output; infeasible at depth 1.0) | 21.0 | False → boundary |
| 4 | cool m 1.0 step 0.5 **ac_min 22** (device-limit collapse) | 22.0 | False → boundary |
| 5 | cool m 0.0 step 0.5 | 22.5 | True |
| 6 | cool m 0.9 step 0.5 (thin-depth guard: depth 0.6 ≥ 0.5) | 21.5 | True |
| 7 | cool m 0.7 step 0.1 (float-dust row) | 21.8 | True |
| 8 | cool m 1.0 step 0.5 **ac_min 21.7** (clamp-thinning: depth 0.3 < 0.5) | 21.7 | False → boundary |
| 9 | heat m 1.0 step 0.5 (operator config) | 22.5 | True |
| 10 | heat m 0.5 step 1.0 (depth floor 1.0 → lands on cool trigger) | 23.0 | False → boundary |
| 11 | heat m 1.0 step 1.0 | 23.0 | False → boundary |
| 12 | heat m 1.0 step 0.5 **ac_max 22** (device-limit collapse) | 22.0 | False → boundary |
| 13 | heat m 0.9 step 0.5 | 22.5 | True |
| 14 | heat m 0.7 step 0.1 (R1R2-3 dust row — raw compares rendered 21.7/False) | 22.2 | True |
| 15 | heat m 0.2 step 0.1 (dust row) | 21.7 | True |
| 16 | heat m 0.4 step 0.1 (dust row) | 21.9 | True |

Plus structural pins: target_mode release semantics unchanged (margin-based);
maintenance branch still boundary setpoints (regression pin); 4f/4g
desired_setpoint conditional pins (C2); STEP-1 ordering chain
`ac_temp_step < deep_pull_depth < setpoint_*_active_q < *_deep_ok` (R1-8 +
R1R2-7 — a gate declared before its setpoint is Undefined at runtime and kills
the whole tick including safety pierces, invisible to get_var/render_var);
C7 notification block shape; C4 message wording.

## Residual risks (accepted)

1. **Heat-mode warm bias can exceed the depth floor** (R1R2-2 rewrite): while
   heating, the wall unit's intake reads 1–2 °C warm, so even the guaranteed
   `max(step, 0.5)` depth may not carry the externals across the heat release —
   the unit can still self-idle early in winter. Cool mode is safe for any
   positive depth given the measured +0.25 bias direction. Field-tune with
   winter data before adding any knob; the achievable depth is bounded by the
   comfort range itself.
2. **Stale sensors mid-active-pull**: unit holds the active setpoint until
   sensors recover or a safety pierce fires — bounded inside the comfort range
   by the `_deep_ok` band (strictly above `temp_low` / below `temp_high`).
3. **Cool→heat flip** requires external-vs-internal bias exceeding
   `(command − temp_low)` > 0 (gate-guaranteed); if it ever fires it is a single
   self-correcting heat cycle, not an oscillation (mode entry requires crossing
   the outer bounds).
4. **More command traffic** than v1.1.0 (~2–3 beeps per cycle, a few cycles/day
   in season) — the operator's explicit trade.
5. **Regime-transition discontinuity** (board R2-3/R1-9): when `deadband_active`
   flips while a mode is active, the commanded setpoint switches
   active↔boundary — one beep per crossing, and a maintenance-carried mode that
   regains deadband gets a short deep-pull before OFF. Analysis: the pull is
   bounded by `(current_temp − release)` because the external release always
   cuts it, and it *ends in OFF* — the operator's preferred outcome — where
   "keep boundary until passive drift" could idle indefinitely. Ruled intended
   behavior, surfaced for operator confirmation in the board report. The
   `not weather_ok` disjunct flips the same regime instantly: a weather outage
   during a heatwave replaces maintenance-holding with deep-pull-then-off for
   the outage duration (consistent with the documented v1.1.0 fail-safe
   direction "fall back to normal cycling", now with v1.2.0's cycling shape).
   No cross-run stickiness machinery added for a rare transient (YAGNI).
6. **Manual-hold false-trigger amplification** (board converged R1-5+R2-2, P2 —
   **deferred with reason**): the expected-state helper is written from intended
   state at command time, not on observed convergence, so a dropped/laggy LG
   cloud command reads as a manual change next tick and pauses control for
   `manual_hold_minutes` (pre-existing v1.1.0 Safety-8; v1.2.0 multiplies the
   trigger frequency by adding real off/on cycles). Zero live exposure today —
   the hold helpers do not exist (live-verified 2026-08-18: every trace ends on
   `hold_enabled` false). HARD GATE recorded in the operator checklist: before
   creating/enabling the hold helpers, implement convergence-gated
   expected-state commit (or a one-tick detection suppression after an
   automation-issued command) as v1.2.1.
7. **Deeper pull costs energy per cycle**: each cycle now cools ~`margin +
   depth` below the entry bound (operator config: to 21.5, off at 22.0). The
   operator explicitly chose depth over runtime.

## Migration

No input renamed, added, or removed — stored instance configs survive re-import
(the v1.1.0 `weather_entity` rename lesson checked and not triggered). Default
`comfort_margin` unchanged (0.5) — no implicit behavior change for any instance;
the living-room instance is set to `comfort_margin: 1.0` explicitly at deploy
via `POST /api/config/automation/config/1775578219942` (v1.1.0 migration
pattern).

**Instance blast-radius checklist (R1-4 + R1R2-1, runs at deploy time — never
trust this snapshot):** enumerate every automation instance using
`lg_ac_climate.yaml`; for each, live-read its device's `target_temp_step` /
`min_temp` / `max_temp` and its effective range+margin, then compute the
PREDICTED `cool_deep_ok` / `heat_deep_ok`. Deploy gate FAILS if the living-room
instance predicts either gate False. Any instance with `margin·2 >
(high − low)` would be stopped by the C4 gate (including its safety pierces) —
none may exist post-deploy. Live state 2026-08-18: exactly one instance
(id 1775578219942, range 21–23; device live-probed this session:
target_temp_step 0.5, min 18, max 30 → with margin 1.0 both gates predict True,
setpoints 21.5 / 22.5).

Deployment: push updated YAML via the HA `blueprint/save` WS API (`domain`,
`path`, `yaml`, `allow_override: true` — namespace probed live via
`blueprint/list` 2026-08-18) + automation reload + the instance-config POST.
Proof of the read path is behavioral and branch-independent
(registry-edits-may-be-baked rule): automation stays `on` after reload, and the
next tick's trace `changed_variables` contains `deep_pull_depth` /
`setpoint_cool_active_q` / `cool_deep_ok` with the expected rendered values
(these variables cannot exist in a v1.1.0 render) — then live-verify the
release→OFF once externals reach 22.0.
