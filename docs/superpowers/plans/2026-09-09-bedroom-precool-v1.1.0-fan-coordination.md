# Bedroom Sleep Pre-Cool v1.1.0 — ceiling-fan coordination + fan-only night hold — Implementation Plan (epic #25, session #26)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Fable orchestrates; tasks 1–5 are Sonnet subagent work with an orchestrator review between tasks; task 6 is the orchestrator's own gate/merge/deploy work.

**Goal:** Ship `bedroom_precool.yaml` v1.1.0: a `night_mode` (`ac_hold` | `fan_only`) with pre-chill, a bedroom-fan list written under one edge-triggered rule, a one-beep night guard, day-parity experiment switches, tests, the migrated instance, docs, and a live deploy before a 19:29 CEST lock.

**Architecture:** additive blueprint inputs + STEP 2a/2c variables that compute (a) the bedtime target, (b) the guard predicate and (c) per-window lists of fans DUE for a write under the fan write rule (configured ∧ available ∧ not at target ∧ interlock clear ∧ `last_updated` older than the reference instant). The action side gains one `climate.turn_off` inside the BEDTIME_LOCK branch (fan-only, skipped when already over the band), a fan step BEFORE the AC dispatch that iterates the due lists with `repeat: for_each` and re-checks the rule live per call, a bare-`turn_on` night guard on 5-minute ticks, and a 15-minute guard-settle step that asserts the parked mode/setpoint/fan from live reads. No helpers; the running AC is the guard latch; `last_updated` is the touch detector.

**Tech Stack:** HA 2026.9 blueprint YAML + Jinja2; pytest + PyYAML + Jinja2 render harness in `tests/test_bedroom_precool_structure.py` (`_render_chain`, `_service_steps`); `scripts/deploy-blueprint.sh` (untouched).

**Spec:** `docs/superpowers/specs/2026-09-09-bedroom-precool-v1.1.0-fan-coordination-design.md` · **Research:** `docs/superpowers/research/2026-09-09-fan-ac-coordination-research-validation.md`
**Branch:** `feat/bedroom-fan-ac-coordination` (worktree `~/AI/projects/Blueprints_Home-fans`) → PR → `main`. PR body carries `Session: #26` (deploying session — never `Closes`).

**Stakes:** standard — default-up: automation logic in `bedroom_precool.yaml` + tests + instance JSON + docs; no hard trigger (deploy script untouched, pinned).

```
Stakes: standard
Trigger: default-up: automation logic in bedroom_precool.yaml + tests + instance JSON + requirements + README; no hard trigger matched (scripts/deploy-blueprint.sh untouched, pinned)
Router: deterministic
Entry: A
tcb_manifest_sha: 294e5c97c5ac2afffe1100b83cc41aa99f3c7b6805edb572a2e3fffaf0a63aea
tcb_baseline: /home/martin/AI/reviews/tcb-baseline-e47dda9f8b1e8bcb.txt
TCB_EXTRA: /home/martin/AI/projects/Blueprints_Home-fans/scripts/deploy-blueprint.sh
declared_tcb_changes:            # none — no TCB file is edited by this plan
```

**Execution mode:** Fable orchestrates; tasks 1–5 dispatched to Sonnet subagents one at a time (fresh context each, `/effort high`), orchestrator reviews the diff + test output between tasks. Boards at standard dial (R1 Opus + R2 Codex unpinned): design-time before Task 1 (triple-check → convene-board on spec + this plan), code-time after Task 5 (review-shipped → convene-board). `/effort xhigh` at both gates, back to `high` after.

**Shell invariants:** tests from the worktree root via `~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q` (baseline **282 green** on 5c5a08b, 2026-09-09). Explicit paths on `git add`. The deploy script is not edited. No `git stash` (shared stash stack across worktrees).

## Global constraints (from the spec)

- Additive inputs only, every new input has a default; the stored instance must stay valid (a removed/renamed input makes it `unavailable`).
- Every new input appears in the top-level `variables:` as `<name>: !input <name>`.
- Values that feed `==`/`!=`/`in` comparisons or service data are SINGLE-LINED (`"{{ … }}"`), never folded scalars.
- No bare boolean text: booleans render from expressions (`{{ a and b }}`), never the literal word `false`.
- No datetime crosses a `variables:` boundary — carry `as_timestamp(...)` floats, format with `timestamp_custom` or `.strftime` inside the same template.
- `variables:` blocks render top to bottom — define before use (order pins in tests).
- Fan commands always pass `percentage` and `continue_on_error: true`; the blueprint never writes `direction`; the fan step (STEP 5c, before STEP 6) is the only place `fan.*` services appear; each due-list is consumed by exactly one `repeat: for_each` whose iteration re-checks the rule on live state.
- No `wait_template` / same-tick read-back anywhere: corrections happen on later ticks from the STEP 2a reads.
- v1.0.3 behaviour with `night_mode: ac_hold` and `bedroom_fans: []` is byte-for-byte unchanged on the rendered service sequence (regression pins).

## Phase 0 — Pre-flight (Claude)

- [x] Worktree `~/AI/projects/Blueprints_Home-fans` on `feat/bedroom-fan-ac-coordination` off `origin/main` 5c5a08b; `.stack-b` marker `repo=leviemartin/Blueprints_Home epic=25` (untracked).
- [x] TCB baseline computed (`e47dda9f8b1e8bcb`, 0 ABSENT, deploy script pinned, `verify` rc=0); re-verify at [4], [6] and on every resume with the same `TCB_EXTRA`.
- [x] Session #26 `status:in-progress`; research verdict + spec committed (b688484, 9d3d889).
- [x] Live facts probed 2026-09-09 (spec §4): LG modes/fan modes/min 18; `turn_on` restores the parked state; fans `percentage_step` 1.0; cutoff sensor `binary_sensor.samuel_samuel_matthew_fanprotection`; dimmer speeds 21/1.
- [ ] Before Task 1: `~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q` → `PASS=282 FAIL=0` on the worktree HEAD.

## Phase 1 — v1.1.0 (one session, one PR)

**Context budget:** ~60k tokens · 6 files (`bedroom_precool.yaml` ~1.3k LOC, `tests/test_bedroom_precool_structure.py` ~390 LOC, instance JSON, `requirements_bedroom_precool.md`, `README.md` §Pre-Cool, spec) · ~+450 LOC net · fits one Sonnet subagent window per task (each task is handed the spec section + the blueprint + the test file).

**Observation criteria ([8], deploying phase):** `<!-- observe:open -->` is already in the #26 kickoff. Exit criteria: (1) deploy-day daytime live-verify shows lock → park/off → fans 1 % → guard `turn_on` restoring `cool/21/low`; (2) first real 19:29 lock trace: `climate.turn_off` after ≤ 2 park calls, fans set within the settle window or the `bedroom_precool_fan_skipped` notice; (3) zero guard trips on a mild night, warmest ≤ 24.5 at 06:00, one wake command; (4) ≥ 2 nights, 24 h log clean of blueprint errors; then `observe:closed` → finish-session.

---

### Task 1: inputs, pass-through, target / parity / window / guard variables, validation

**Model tier:** Sonnet
**Rationale:** Well-specified additive YAML + rendered-chain tests against a fully written spec.
**Effort:** high (checkpoint) — `/effort high`.

**Files:**
- Modify: `bedroom_precool.yaml` — Group 5 inputs after `night_fan:` (line ≈ 373), new Group 7 after Group 6 (after `enable_notifications`, line ≈ 417), top-level `variables:` Group 5/7 pass-through (lines ≈ 459–467), STEP 2a after `vacation_active` (line ≈ 555), STEP 2c: `delta_in` (≈ 682), `cooling_needed` (≈ 710), `precool_substate` (≈ 768), new block after `night_fan_mode:` (≈ 804), STEP 3 condition + message (≈ 807–840).
- Test: `tests/test_bedroom_precool_structure.py` (append a `# --- v1.1.0 …` section; one edit to an existing test).

**Interfaces — Produces** (names later tasks use verbatim): inputs `night_mode`, `prechill_offset`, `bedroom_fans`, `interlocked_fans`, `fan_interlocks`, `interlock_clear_minutes`, `night_fans`, `night_fan_percentage`, `fan_assist`, `precool_fan_percentage`, `fan_settle_minutes`, `fans_at_wake`; STEP 2a vars `fan_only_mode`, `bedtime_target`, `interlock_blocked`, `ac_started_ts`; STEP 2c vars `night_parity`, `fan_assist_tonight`, `night_fans_tonight`, `lock_ts`, `settle_end_tod`, `settle_last_tod`, `since_ac_start_min`, `in_wake_window`, `in_fan_settle`, `in_settle_last_tick`, `in_fan_assist_window`, `night_phase`, `guard_due`, `guard_settle_due`, `settle_mode_due`, `settle_setpoint_due`, `settle_fan_due`; test helpers `_S`, `_fan_env`, `_v110_ctx`.

- [ ] **Step 1 (RED): append tests**

Fakes first (Task 4 uses them too):

```python
# --- v1.1.0 fan coordination (design 2026-09-09, board 20260909-130652) --------------

class _S:
    """A fake HA State object as `expand()` returns it. last_changed (state transitions)
    and last_updated (state OR attribute changes) are independent, as in HA."""
    def __init__(self, entity_id, state, percentage=None, last_updated=None, last_changed=None):
        self.entity_id = entity_id
        self.state = state
        self.attributes = {} if percentage is None else {"percentage": percentage}
        self.last_updated = last_updated or datetime(2026, 9, 9, 12, 0, tzinfo=TZ)
        self.last_changed = last_changed or self.last_updated


def _fan_env(now, states):
    """`_env` plus HA state helpers resolving to the fakes: expand(), state_attr(), states(), is_state()."""
    env = _env(now)
    by_id = {s.entity_id: s for s in states}
    def expand(*ids):
        out = []
        for group in ids:
            for i in ([group] if isinstance(group, str) else group):
                if i in by_id:
                    out.append(by_id[i])
        return out
    env.globals["expand"] = expand
    env.globals["state_attr"] = lambda e, a: by_id[e].attributes.get(a) if e in by_id else None
    env.globals["states"] = lambda e: by_id[e].state if e in by_id else "unknown"
    env.globals["is_state"] = lambda e, v: e in by_id and by_id[e].state == v
    env.filters["as_timestamp"] = env.globals["as_timestamp"]     # HA offers it as a filter too
    return env


V110_INPUTS = {
    "night_mode": "ac_hold", "prechill_offset": 0.5, "bedroom_fans": [], "interlocked_fans": [],
    "fan_interlocks": [], "interlock_clear_minutes": 5, "night_fans": "all", "night_fan_percentage": 1,
    "fan_assist": "off", "precool_fan_percentage": 21, "fan_settle_minutes": 45, "fans_at_wake": "leave",
}


def test_v110_inputs_exist_with_safe_defaults(bp):
    inputs = bp["blueprint"]["input"]
    for key, default in V110_INPUTS.items():
        assert key in inputs, key
        assert inputs[key]["default"] == default, key
    opts = lambda k: [o["value"] for o in inputs[k]["selector"]["select"]["options"]]
    assert opts("night_mode") == ["ac_hold", "fan_only"]
    assert opts("night_fans") == ["all", "odd", "even", "off"]
    assert opts("fan_assist") == ["off", "all", "odd", "even"]
    assert opts("fans_at_wake") == ["leave", "off"]
    for k in ("bedroom_fans", "interlocked_fans"):
        assert inputs[k]["selector"]["entity"]["domain"] == "fan" and inputs[k]["selector"]["entity"]["multiple"] is True
    assert inputs["fan_interlocks"]["selector"]["entity"]["domain"] == "binary_sensor"
    # the pass-through pin (test_every_input_is_passed_through_top_level_variables) covers the variables block


def _v110_ctx(**over):
    ctx = dict(ideal_temp=23, tolerance=1.5, correction_step=1.5, prechill_offset=0.5, night_mode="ac_hold",
               fan_assist="off", night_fans="all", fan_settle_minutes=45, bedtime="19:30:00",
               wake_time="07:15:00", wake_tod="07:15:00", lock_tod="19:29:00", now_tod="23:00:00",
               ac_is_running=False, warmest_bedroom=23.0, ac_started_ts=0.0, phase="NIGHT_HOLD",
               forecast_max=18.0, skip_threshold=21, maintaining_setpoint=21.0, current_hvac_mode="cool",
               current_setpoint_known=True, current_setpoint=21.0, current_fan="low", night_fan_mode="low",
               enable_fan_control=True, ac_fan_modes=["auto", "low", "medium", "high"])
    ctx.update(over)
    return ctx


TARGET_CHAIN = ["fan_only_mode", "bedtime_target", "delta_in", "cooling_needed", "precool_substate"]


def test_rendered_bedtime_target_drives_lead_term_skip_gate_and_substate(bp):
    now = datetime(2026, 9, 9, 18, 0, tzinfo=TZ)
    hold = _render_chain(bp, TARGET_CHAIN, now, _v110_ctx(warmest_bedroom=22.8))
    assert hold["bedtime_target"] == 23.0 and hold["delta_in"] == 0 and hold["cooling_needed"] is False
    assert hold["precool_substate"] == "HOLD"
    fan = _render_chain(bp, TARGET_CHAIN, now, _v110_ctx(night_mode="fan_only", warmest_bedroom=22.8))
    assert fan["bedtime_target"] == 22.5
    assert abs(fan["delta_in"] - 0.3) < 1e-9           # the lead term sees the deeper target (board R1-08)
    assert fan["cooling_needed"] is True               # a room between the two targets still pre-chills
    assert fan["precool_substate"] == "DRIVE"
    assert _render_chain(bp, TARGET_CHAIN, now, _v110_ctx(night_mode="fan_only", warmest_bedroom=22.5))["precool_substate"] == "HOLD"
    assert _render_chain(bp, TARGET_CHAIN, now, _v110_ctx(night_mode="fan_only", prechill_offset=0))["bedtime_target"] == 23.0
    for name in ("delta_in", "cooling_needed", "precool_substate"):
        assert "ideal_temp" not in _var_template(bp, name), name


PARITY_CHAIN = ["night_parity", "fan_assist_tonight", "night_fans_tonight"]


def _parity(bp, t, **over):
    return _render_chain(bp, PARITY_CHAIN, t, _v110_ctx(now_tod=t.strftime("%H:%M:%S"), **over))


def test_rendered_night_parity_is_shared_from_wake_to_wake(bp):
    # 2026-09-09 is day 252 of the year (even); 2026-09-10 is 253 (odd). Pivot = wake time (board R2-06).
    d9 = lambda hh, mm: datetime(2026, 9, 9, hh, mm, tzinfo=TZ)
    d10 = lambda hh, mm: datetime(2026, 9, 10, hh, mm, tzinfo=TZ)
    for t in (d9(11, 0), d9(15, 30), d9(19, 29), d10(1, 0), d10(7, 14)):    # pre-noon PRECOOL start included
        assert _parity(bp, t)["night_parity"] == "even", t
    assert _parity(bp, d10(7, 15))["night_parity"] == "odd"                 # the next night's date from wake on
    ctx = _parity(bp, d9(19, 29), fan_assist="even", night_fans="odd")
    assert ctx["fan_assist_tonight"] is True and ctx["night_fans_tonight"] is False
    ctx = _parity(bp, d9(19, 29), fan_assist="off", night_fans="all")
    assert ctx["fan_assist_tonight"] is False and ctx["night_fans_tonight"] is True


WINDOW_CHAIN = ["lock_ts", "settle_end_tod", "settle_last_tod", "since_ac_start_min", "in_wake_window",
                "in_fan_settle", "in_settle_last_tick", "in_fan_assist_window"]


def _windows(bp, hh, mm, **over):
    now = datetime(2026, 9, 9, hh, mm, tzinfo=TZ)
    return _render_chain(bp, WINDOW_CHAIN, now, _v110_ctx(now_tod=now.strftime("%H:%M:%S"), **over))


def test_rendered_fan_windows(bp):
    lock = datetime(2026, 9, 9, 19, 29, tzinfo=TZ)
    assert _windows(bp, 19, 29)["lock_ts"] == lock.timestamp()
    assert _windows(bp, 19, 29)["settle_end_tod"] == "20:15:00"
    assert _windows(bp, 19, 29)["settle_last_tod"] == "20:14:00"
    assert _windows(bp, 19, 28)["in_fan_settle"] is False
    assert _windows(bp, 19, 29)["in_fan_settle"] is True          # the lock tick itself
    assert _windows(bp, 20, 14)["in_fan_settle"] is True
    assert _windows(bp, 20, 14)["in_settle_last_tick"] is True
    assert _windows(bp, 20, 15)["in_fan_settle"] is False
    assert _windows(bp, 7, 15)["in_wake_window"] is True and _windows(bp, 7, 16)["in_wake_window"] is False
    started = datetime(2026, 9, 9, 17, 0, tzinfo=TZ).timestamp()
    on = dict(phase="PRECOOL", ac_is_running=True, ac_started_ts=started)
    assert _windows(bp, 17, 30, **on)["since_ac_start_min"] == 30.0
    assert _windows(bp, 17, 30, **on)["in_fan_assist_window"] is True
    assert _windows(bp, 17, 46, **on)["in_fan_assist_window"] is False   # 46 > 45
    assert _windows(bp, 17, 30, **dict(on, ac_is_running=False))["in_fan_assist_window"] is False
    assert _windows(bp, 17, 30, **dict(on, phase="DAY_OFF"))["in_fan_assist_window"] is False


GUARD_CHAIN = ["fan_only_mode", "night_phase", "guard_due", "guard_settle_due", "settle_mode_due",
               "settle_setpoint_due", "settle_fan_due"]


def _guard(bp, now, **over):
    return _render_chain(bp, GUARD_CHAIN, now, _v110_ctx(now_tod=now.strftime("%H:%M:%S"), **over))


def test_rendered_guard_due_only_in_night_phases_with_fan_only_ac_off_over_band_on_a_5_minute_tick(bp):
    t = datetime(2026, 9, 9, 23, 0, tzinfo=TZ)
    hot = dict(night_mode="fan_only", warmest_bedroom=24.6)
    for ph in ("NIGHT_HOLD", "DEEP_NIGHT_CHECK", "DEEP_HOLD"):
        assert _guard(bp, t, phase=ph, **hot)["guard_due"] is True, ph
    assert _guard(bp, datetime(2026, 9, 9, 23, 1, tzinfo=TZ), phase="NIGHT_HOLD", **hot)["guard_due"] is False   # cadence (board R2-02)
    assert _guard(bp, t, phase="NIGHT_HOLD", night_mode="fan_only", warmest_bedroom=24.5)["guard_due"] is False   # at the band
    assert _guard(bp, t, phase="NIGHT_HOLD", night_mode="ac_hold", warmest_bedroom=26.0)["guard_due"] is False
    assert _guard(bp, t, phase="NIGHT_HOLD", ac_is_running=True, **hot)["guard_due"] is False                      # the latch
    for ph in ("PRECOOL", "BEDTIME_LOCK", "DAY_OFF"):
        assert _guard(bp, t, phase=ph, **hot)["guard_due"] is False, ph


def test_rendered_guard_settle_asserts_the_parked_state_only_after_a_night_start(bp):
    t = datetime(2026, 9, 9, 23, 7, tzinfo=TZ)
    started = (t - timedelta(minutes=2)).timestamp()
    base = dict(night_mode="fan_only", phase="NIGHT_HOLD", ac_is_running=True, ac_started_ts=started)
    ok = _guard(bp, t, **base)
    assert ok["guard_settle_due"] is True
    assert ok["settle_mode_due"] is False and ok["settle_setpoint_due"] is False and ok["settle_fan_due"] is False
    assert _guard(bp, t, **base, current_hvac_mode="heat")["settle_mode_due"] is True         # board R1-03 / R2-04
    assert _guard(bp, t, **base, current_hvac_mode="fan_only")["settle_mode_due"] is True
    assert _guard(bp, t, **base, current_hvac_mode="dry")["settle_mode_due"] is False
    assert _guard(bp, t, **base, current_setpoint=18.0)["settle_setpoint_due"] is True         # stale DRIVE park
    assert _guard(bp, t, **base, current_setpoint=19.5)["settle_setpoint_due"] is False        # a deep-night nudge, left alone
    assert _guard(bp, t, **base, current_setpoint_known=False)["settle_setpoint_due"] is False
    assert _guard(bp, t, **base, current_fan="high")["settle_fan_due"] is True
    assert _guard(bp, t, **base, current_fan="unknown")["settle_fan_due"] is False             # null read (board R1-02)
    assert _guard(bp, t, **base, enable_fan_control=False, current_fan="high")["settle_fan_due"] is False
    late = _guard(bp, t, **dict(base, ac_started_ts=(t - timedelta(minutes=16)).timestamp()), current_hvac_mode="heat")
    assert late["guard_settle_due"] is False and late["settle_mode_due"] is False              # window closed
    assert _guard(bp, t, **dict(base, night_mode="ac_hold"), current_hvac_mode="heat")["settle_mode_due"] is False
    assert _guard(bp, t, **dict(base, phase="PRECOOL"), current_hvac_mode="heat")["settle_mode_due"] is False


def test_rendered_interlock_blocked_fails_safe_and_honours_the_clear_hold(bp):
    now = datetime(2026, 9, 9, 19, 29, tzinfo=TZ)
    render = lambda states, sensors: _reparse(_fan_env(now, states).from_string(
        _var_template(bp, "interlock_blocked")).render(fan_interlocks=sensors, interlock_clear_minutes=5).strip())
    pir = "binary_sensor.samuel_samuel_matthew_fanprotection"
    assert render([_S(pir, "off")], [pir]) is False      # cleared 7.5 h ago (the _S default)
    assert render([_S(pir, "on")], [pir]) is True
    assert render([_S(pir, "unavailable")], [pir]) is True
    assert render([], [pir]) is True                     # sensor missing from the state machine
    assert render([], []) is False                       # no interlock configured
    # the cutoff resumes at clear + 3 min; we stay blocked until clear + 5 (spec §2.1, board R1-09)
    assert render([_S(pir, "off", last_changed=now - timedelta(minutes=4))], [pir]) is True
    assert render([_S(pir, "off", last_changed=now - timedelta(minutes=5, seconds=1))], [pir]) is False
    # the hold keys on last_changed (state transitions), not on attribute updates (board R2-05)
    assert render([_S(pir, "off", last_updated=now - timedelta(seconds=30), last_changed=now - timedelta(minutes=9))], [pir]) is False


def test_config_validation_rejects_a_settle_window_across_midnight(bp):
    now = datetime(2026, 9, 9, 9, 0, tzinfo=TZ)
    base = dict(drive_setpoint=16, ideal_temp=23, hall_offset=2, deep_night_check="01:00:00",
                bedtime="19:30:00", wake_time="07:15:00", lead_cap_minutes=240, fan_settle_minutes=45)
    tmpl = _env(now).from_string(_config_validation_template(bp))
    render = lambda **kw: _reparse(tmpl.render(**{**base, **kw}).strip())
    assert render() is False                                             # live config
    assert render(bedtime="23:30:00", fan_settle_minutes=45) is True     # 00:15 next day
    assert render(bedtime="23:00:00", fan_settle_minutes=45) is False    # 23:45, same day
```

And one edit to the EXISTING test `test_rendered_config_validation_rejects_a_lead_cap_reaching_back_past_wake` (board R1-05): its `base` dict gains `fan_settle_minutes=45` (the validation template now reads that input; an Undefined would raise on the first assertion).

- [ ] **Step 2: run → RED** — `~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests/test_bedroom_precool_structure.py -q -k "v110 or bedtime_target or night_parity or fan_windows or guard_due or guard_settle or interlock_blocked or settle_window"` → failures (KeyError on missing inputs/templates).

- [ ] **Step 3 (GREEN): blueprint edits**

Group 5, after the `night_fan:` input:

```yaml
    night_mode:
      name: Night Mode
      description: >
        What happens to the AC at bedtime. 'AC hold' (default) locks the maintaining
        setpoint and the Night Fan Mode and lets the unit run until Wake Time (the
        v1.0.x behaviour). 'Fan-only' parks the unit on that same state, switches it
        OFF at the bedtime lock and hands the night to the Bedroom Fans; if the warmest
        bedroom exceeds Ideal + Drift Tolerance after bedtime the unit is switched back
        on (one beep — it restores the parked state, which the blueprint re-checks for
        15 minutes) and stays on until Wake Time.
      default: "ac_hold"
      selector:
        select:
          options:
            - label: "AC hold — unit runs all night (v1.0.x)"
              value: "ac_hold"
            - label: "Fan-only — unit off at bedtime, back on only if too warm"
              value: "fan_only"
    prechill_offset:
      name: Pre-Chill Offset (°C)
      description: >
        Fan-only nights only: PRECOOL drives the warmest bedroom this far BELOW the
        Ideal Sleep Temperature before the lock (the lead-time prediction, the
        cool-day skip and the auto-learn all aim at that deeper target), so the rooms
        start the coast with a margin. 0 = drive to ideal exactly. Ignored in AC-hold
        mode.
      default: 0.5
      selector:
        number:
          min: 0.0
          max: 2.0
          step: 0.1
          unit_of_measurement: "°C"
```

New Group 7 after `enable_notifications` (end of Group 6):

```yaml
    # =======================================================
    # GROUP 7 — BEDROOM FANS (optional)
    # =======================================================
    bedroom_fans:
      name: Bedroom Fans (Optional)
      description: >
        Ceiling fans in the bedrooms, one per room. Leave empty to keep the v1.0.x
        behaviour (no fan is ever commanded). The blueprint writes a fan at most once
        per transition and only if nobody has touched it since — a fan a safety
        automation switched off, or one you changed by hand, is left alone.
      default: []
      selector:
        entity:
          domain: fan
          multiple: true
    interlocked_fans:
      name: Interlocked Fans (Optional)
      description: >
        The subset of Bedroom Fans that must never be commanded while a Fan Interlock
        sensor is on or has just cleared (e.g. a fan at head height with a
        height-gated presence sensor).
      default: []
      selector:
        entity:
          domain: fan
          multiple: true
    fan_interlocks:
      name: Fan Interlock Sensors (Optional)
      description: >
        Binary sensors that block commands to the Interlocked Fans while 'on'. An
        unavailable or missing sensor also blocks (fail-safe).
      default: []
      selector:
        entity:
          domain: binary_sensor
          multiple: true
    interlock_clear_minutes:
      name: Interlock Clear Hold (min)
      description: >
        An interlock sensor that changed state within the last N minutes still blocks.
        Set this LONGER than the safety automation's own resume hold on the same fan
        (kids-room cutoff: 3 min → 5 here), so this blueprint never writes the fan in
        the same minute the safety automation resumes it, and never inside its hold.
      default: 5
      selector:
        number:
          min: 0
          max: 15
          step: 1
          unit_of_measurement: "min"
    night_fans:
      name: Night Fans — Which Nights
      description: >
        On which nights the Bedroom Fans are set to the Night Fan Percentage at the
        bedtime lock (applied inside the Fan Settle Window to any fan nobody touched).
        Odd/even = day of the year of the night's START date (the date at wake time),
        for A/B comparisons.
      default: "all"
      selector:
        select:
          options:
            - label: "Every night"
              value: "all"
            - label: "Odd days of the year"
              value: "odd"
            - label: "Even days of the year"
              value: "even"
            - label: "Never"
              value: "off"
    night_fan_percentage:
      name: Night Fan Percentage
      description: The fan speed for the night (1 = the lowest step on a Tuya ceiling fan).
      default: 1
      selector:
        number:
          min: 1
          max: 100
          step: 1
          unit_of_measurement: "%"
    fan_assist:
      name: Pre-Cool Fan Assist — Which Days
      description: >
        On which days the Bedroom Fans run at the Pre-Cool Fan Percentage from the
        moment the AC starts (experiment: does a fan in the room speed the measured
        drop?). Default off. Odd/even as for Night Fans.
      default: "off"
      selector:
        select:
          options:
            - label: "Off"
              value: "off"
            - label: "Every day"
              value: "all"
            - label: "Odd days of the year"
              value: "odd"
            - label: "Even days of the year"
              value: "even"
    precool_fan_percentage:
      name: Pre-Cool Fan Percentage
      description: The fan speed during pre-cool fan assist (21 = step 2 on a Tuya ceiling fan).
      default: 21
      selector:
        number:
          min: 1
          max: 100
          step: 1
          unit_of_measurement: "%"
    fan_settle_minutes:
      name: Fan Settle Window (min)
      description: >
        How long after the bedtime lock (and after the AC start) a pending fan setting
        may still be applied to a fan nobody has touched. Must end before midnight.
      default: 45
      selector:
        number:
          min: 5
          max: 120
          step: 5
          unit_of_measurement: "min"
    fans_at_wake:
      name: Fans At Wake
      description: Leave the Bedroom Fans as they are at Wake Time (default) or switch them off.
      default: "leave"
      selector:
        select:
          options:
            - label: "Leave as they are"
              value: "leave"
            - label: "Switch off"
              value: "off"
```

Top-level `variables:` — add under `# --- Group 5: behaviour ---` after `night_fan: !input night_fan`:

```yaml
  night_mode: !input night_mode
  prechill_offset: !input prechill_offset
```

and a new block after Group 6:

```yaml
  # --- Group 7: bedroom fans ---
  bedroom_fans: !input bedroom_fans
  interlocked_fans: !input interlocked_fans
  fan_interlocks: !input fan_interlocks
  interlock_clear_minutes: !input interlock_clear_minutes
  night_fans: !input night_fans
  night_fan_percentage: !input night_fan_percentage
  fan_assist: !input fan_assist
  precool_fan_percentage: !input precool_fan_percentage
  fan_settle_minutes: !input fan_settle_minutes
  fans_at_wake: !input fans_at_wake
```

STEP 2a — after `vacation_active`:

```yaml
      # --- v1.1.0 fan coordination: live facts ---
      fan_only_mode: "{{ night_mode == 'fan_only' }}"
      # The bedtime target: ideal in AC-hold mode, ideal − pre-chill in fan-only mode.
      # Defined HERE, before STEP 2c, because delta_in, cooling_needed, the DRIVE/HOLD
      # substate and the auto-learn error all key on it (board R1-08).
      bedtime_target: "{{ (ideal_temp | float - prechill_offset | float) if fan_only_mode else (ideal_temp | float) }}"
      # Any interlock sensor on / unavailable / unknown / absent from the state machine
      # blocks the interlocked fans — the same fail-safe direction as the cutoff
      # blueprint — and so does a sensor whose STATE changed within the last
      # interlock_clear_minutes (last_changed, not last_updated): the cutoff resumes its
      # fan at clear + its hold, and this blueprint must never write the fan in that
      # minute or inside the hold (board R1-09).
      interlock_blocked: >-
        {% if fan_interlocks is iterable and fan_interlocks is not string
              and fan_interlocks | length > 0 %}
          {% set found = expand(fan_interlocks) | list %}
          {% set recent = as_timestamp(now()) - (interlock_clear_minutes | float) * 60 %}
          {{ found | length < fan_interlocks | length
             or found | selectattr('state', 'in', ['on', 'unavailable', 'unknown']) | list | length > 0
             or found | map(attribute='last_changed') | map('as_timestamp') | select('gt', recent) | list | length > 0 }}
        {% else %}
          {{ false }}
        {% endif %}
      # The unit's last off<->on transition as a timestamp (setpoint/fan edits touch
      # last_updated, not last_changed). Reference instant for pre-cool fan assist and
      # for the guard-settle window.
      ac_started_ts: >-
        {% set s = expand(ac_climate) | list %}
        {{ as_timestamp(s[0].last_changed) if s | length > 0 else 0 }}
```

STEP 2c — three EXISTING variables change their reference from `ideal_temp` to `bedtime_target` (`ac_hold` mode: identical values):

```yaml
      delta_in: "{{ [0, warmest_bedroom | float - bedtime_target | float] | max }}"
      ...
      cooling_needed: >-
        {{ warmest_bedroom | float > bedtime_target | float
           or forecast_max | float > skip_threshold | float }}
      ...
      precool_substate: >-
        {% if warmest_bedroom | float > bedtime_target | float %}DRIVE{% else %}HOLD{% endif %}
```

STEP 2c — new block after `night_fan_mode:` (all single-lined; `phase`, `now_tod`, `wake_tod`, `lock_tod` and the STEP 2a reads are defined above):

```yaml
      # --- v1.1.0: parity, windows, guard ---
      # Parity of the NIGHT = day of the year of the night's start date, pivoting at
      # WAKE TIME: from wake through PRECOOL and the lock it is today, in the small
      # hours before wake it is yesterday — one value from a pre-noon PRECOOL start to
      # the last tick before wake (board R2-06).
      night_parity: "{{ 'odd' if (((now() if now_tod >= wake_tod else now() - timedelta(days=1)).timetuple().tm_yday) % 2) == 1 else 'even' }}"
      fan_assist_tonight: "{{ fan_assist == 'all' or fan_assist == night_parity }}"
      night_fans_tonight: "{{ night_fans == 'all' or night_fans == night_parity }}"
      # Reference instant for the night fan setting; consumed only inside the settle
      # window (same evening), so today_at() always refers to the right lock.
      lock_ts: "{{ as_timestamp(today_at(bedtime) - timedelta(minutes=1)) }}"
      settle_end_tod: "{{ (today_at(bedtime) + timedelta(minutes=fan_settle_minutes | int)).strftime('%H:%M:%S') }}"
      settle_last_tod: "{{ (today_at(bedtime) + timedelta(minutes=(fan_settle_minutes | int) - 1)).strftime('%H:%M:%S') }}"
      since_ac_start_min: "{{ ((as_timestamp(now()) - (ac_started_ts | float)) / 60) | round(1) }}"
      in_wake_window: "{{ wake_tod <= now_tod and now_tod < (today_at(wake_time) + timedelta(minutes=1)).strftime('%H:%M:%S') }}"
      in_fan_settle: "{{ lock_tod <= now_tod and now_tod < settle_end_tod }}"
      in_settle_last_tick: "{{ settle_last_tod <= now_tod and now_tod < settle_end_tod }}"
      in_fan_assist_window: "{{ phase == 'PRECOOL' and ac_is_running and (since_ac_start_min | float) < (fan_settle_minutes | float) }}"
      night_phase: "{{ phase in ['NIGHT_HOLD', 'DEEP_NIGHT_CHECK', 'DEEP_HOLD'] }}"
      # Night guard: fan-only, a night phase, unit off, warmest room over the band, on a
      # 5-minute tick (bounds a stuck cloud 'off' to ≤ 12 attempts/h, board R2-02). The
      # running unit is the latch — once on, guard_due is false until DAY_OFF turns it
      # off at wake.
      guard_due: "{{ fan_only_mode and night_phase and not ac_is_running and (warmest_bedroom | float) > (ideal_temp | float + tolerance | float) and (now().minute | int) % 5 == 0 }}"
      # Guard settle: for 15 min after ANY night start the parked state is asserted from
      # live reads, each call only if different (board R1-01/R1-03/R2-03/R2-04). The
      # setpoint check leaves a deep-night nudge (exactly correction_step away) alone.
      guard_settle_due: "{{ fan_only_mode and night_phase and ac_is_running and (since_ac_start_min | float) < 15 }}"
      settle_mode_due: "{{ guard_settle_due and current_hvac_mode not in ['cool', 'dry'] }}"
      settle_setpoint_due: "{{ guard_settle_due and current_setpoint_known and ((current_setpoint | float - maintaining_setpoint | float) | abs) > (correction_step | float + 0.1) }}"
      settle_fan_due: "{{ guard_settle_due and enable_fan_control and ac_fan_modes | length > 0 and current_fan != 'unknown' and current_fan != night_fan_mode }}"
```

STEP 3 — extend the validation template (same `or` chain; instants compared inside one template) and the message:

```yaml
                 or (today_at(bedtime) + timedelta(minutes=fan_settle_minutes | int)).date()
                    != today_at(bedtime).date() }}
```

Message: append "Bedtime plus the Fan Settle Window ({{ fan_settle_minutes }} min) must not cross midnight."

- [ ] **Step 4: run → GREEN** — the `-k` selection from Step 2 passes; then the full file `pytest tests -q` → **`PASS=N FAIL=M`** (N = 282 + 9 new, M = 0; the edited pre-existing validation test still passes).
- [ ] **Step 5: commit** — `git add bedroom_precool.yaml tests/test_bedroom_precool_structure.py && git commit -m "feat(bedroom-precool): v1.1.0 T1 — night_mode/pre-chill/fan inputs, bedtime_target-keyed lead terms, parity, windows, guard + settle predicates, validation"`.

### Task 2: BEDTIME_LOCK fan-only branch (park, then off unless already over the band)

**Model tier:** Sonnet
**Rationale:** One template substitution and one gated `climate.turn_off` inside an existing branch, pinned by the branch walker.
**Effort:** high (checkpoint) — `/effort high`.

**Files:** Modify `bedroom_precool.yaml` — BEDTIME_LOCK branch (≈ 1032–1103, `bedtime_error:` ≈ 1089). Test: `tests/test_bedroom_precool_structure.py`.

**Interfaces — Consumes:** `fan_only_mode`, `bedtime_target`, `warmest_bedroom`, `ideal_temp`, `tolerance` (Task 1). **Produces:** the BEDTIME_LOCK branch's service order `[set_hvac_mode, set_temperature, set_fan_mode, climate.turn_off (cond fan_only_mode ∧ not over band), input_number.set_value]`; helper `_services_in_phase`.

- [ ] **Step 1 (RED): tests**

```python
def _services_in_phase(bp, phase):
    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
    return [(c, s) for c, s in steps if any(f"phase == '{phase}'" in t for t in c)]


def test_learner_error_uses_bedtime_target(bp):
    lock = [s for c, s in _services_in_phase(bp, "BEDTIME_LOCK")]
    learner = [s for s in lock if (s.get("service") or s.get("action")) == "input_number.set_value"]
    assert len(learner) == 1
    assert 'bedtime_error: "{{ warmest_bedroom | float - bedtime_target | float }}"' in BP_PATH.read_text()


def test_bedtime_lock_switches_the_unit_off_only_in_fan_only_mode_after_parking_it_and_not_when_over_band(bp):
    calls = _services_in_phase(bp, "BEDTIME_LOCK")
    names = [(s.get("service") or s.get("action")) for c, s in calls]
    assert names == ["climate.set_hvac_mode", "climate.set_temperature", "climate.set_fan_mode",
                     "climate.turn_off", "input_number.set_value"], names
    off_conds = [c for c, s in calls if (s.get("service") or s.get("action")) == "climate.turn_off"][0]
    off_tmpl = [t for t in off_conds if "fan_only_mode" in t][0]
    assert "tolerance" in off_tmpl and "warmest_bedroom" in off_tmpl          # board R1-07
    assert any("ac_is_running" in t for t in off_conds)                        # cool-day lock stays a no-op
    now = datetime(2026, 9, 9, 19, 29, tzinfo=TZ)
    render = lambda **kw: _reparse(_env(now).from_string(off_tmpl).render(**_v110_ctx(**kw)).strip())
    assert render(fan_only_mode=True, warmest_bedroom=23.0) is True
    assert render(fan_only_mode=True, warmest_bedroom=24.6) is False           # already over the band: stay on
    assert render(fan_only_mode=False, warmest_bedroom=23.0) is False
    # ac_hold regression pin: none of the three park calls is gated on fan_only_mode
    for c, s in calls[:3]:
        assert not any("fan_only_mode" in t for t in c)
```

- [ ] **Step 2: run → RED** (`-k "learner_error or switches_the_unit_off"`).
- [ ] **Step 3 (GREEN):** `bedtime_error: "{{ warmest_bedroom | float - bedtime_target | float }}"`; in the BEDTIME_LOCK `ac_is_running` sequence insert, after the `climate.set_fan_mode` choose and before the auto-learn choose:

```yaml
                          # v1.1.0 fan-only: the unit is now PARKED on the maintaining
                          # setpoint + night fan (the calls above ran only if needed), so a
                          # later night-guard turn_on restores exactly this state in one
                          # command. Switch it off and hand the night to the fans — unless
                          # the warmest room is already over the guard band, in which case
                          # the guard would only switch it back on next tick (board R1-07):
                          # then the unit simply stays on, as in AC-hold mode.
                          - choose:
                              - conditions:
                                  - condition: template
                                    value_template: "{{ fan_only_mode and not ((warmest_bedroom | float) > (ideal_temp | float + tolerance | float)) }}"
                                sequence:
                                  - service: climate.turn_off
                                    target:
                                      entity_id: "{{ ac_climate }}"
```

Update the branch comment (`# ---------- BEDTIME_LOCK: park (+ off in fan-only) + auto-learn write ----------`).
- [ ] **Step 4: run → GREEN** — `pytest tests -q` → **`PASS=N FAIL=M`** (M = 0; N = previous + 2).
- [ ] **Step 5: commit** — `git add bedroom_precool.yaml tests/test_bedroom_precool_structure.py && git commit -m "feat(bedroom-precool): v1.1.0 T2 — fan-only lock parks then switches the unit off unless already over the band; learner uses bedtime_target"`.

### Task 3: night guard + guard settle steps + guard notice

**Model tier:** Sonnet
**Rationale:** Two new top-level steps gated on predicates Task 1 already tests; walker pins.
**Effort:** high (checkpoint) — `/effort high`.

**Files:** Modify `bedroom_precool.yaml` — new `STEP 6a` (guard) and `STEP 6b` (settle) after the STEP 6 `choose` block (before STEP 7a). Test file.

**Interfaces — Consumes:** `guard_due`, `settle_mode_due`, `settle_setpoint_due`, `settle_fan_due`, `is_real_trigger`, `enable_notifications`, `warmest_bedroom`, `ideal_temp`, `tolerance`, `ac_climate`, `desired_mode`, `maintaining_setpoint`, `night_fan_mode`.

- [ ] **Step 1 (RED): tests**

```python
def _calls_with(bp, marker):
    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
    return [(c, s) for c, s in steps if any(marker in t for t in c)]


def test_night_guard_is_one_bare_turn_on_plus_notice_and_the_settle_step_corrects_from_live_reads(bp):
    guard = _calls_with(bp, "guard_due")
    names = [(s.get("service") or s.get("action")) for c, s in guard]
    assert names == ["climate.turn_on", "persistent_notification.create"], names
    conds, turn_on = guard[0]
    assert any(t.strip() == "{{ is_real_trigger and guard_due }}" for t in conds)
    assert turn_on["target"]["entity_id"] == "{{ ac_climate }}"
    assert "data" not in turn_on                       # a bare turn_on: the unit restores its parked state
    assert guard[1][1]["data"]["notification_id"] == "bedroom_precool_guard_fired"
    assert any("enable_notifications" in t for t in guard[1][0])
    assert "wait_template" not in BP_PATH.read_text()  # no same-tick read-back (board R1-01 / R2-03)
    settle = {(s.get("service") or s.get("action")): c for c, s in _calls_with(bp, "settle_")}
    assert set(settle) == {"climate.set_hvac_mode", "climate.set_temperature", "climate.set_fan_mode"}
    assert any(t.strip() == "{{ is_real_trigger and settle_mode_due }}" for t in settle["climate.set_hvac_mode"])
    assert any(t.strip() == "{{ is_real_trigger and settle_setpoint_due }}" for t in settle["climate.set_temperature"])
    assert any(t.strip() == "{{ is_real_trigger and settle_fan_due }}" for t in settle["climate.set_fan_mode"])
    data = {(s.get("service") or s.get("action")): s["data"] for c, s in _calls_with(bp, "settle_")}
    assert data["climate.set_hvac_mode"]["hvac_mode"] == "{{ desired_mode }}"
    assert data["climate.set_temperature"]["temperature"] == "{{ maintaining_setpoint | float }}"
    assert data["climate.set_fan_mode"]["fan_mode"] == "{{ night_fan_mode }}"
    # the two night branches of STEP 6 stay free of climate calls (guard lives outside)
    for ph in ("NIGHT_HOLD", "DEEP_HOLD"):
        assert _services_in_phase(bp, ph) == []
```

- [ ] **Step 2: run → RED**.
- [ ] **Step 3 (GREEN):** insert after the STEP 6 block:

```yaml
  # =============================================
  # STEP 6a: NIGHT GUARD (v1.1.0, fan-only nights) — one bare turn_on per trip.
  # The unit was parked (maintaining setpoint + night fan) and switched off at the
  # lock; if the warmest bedroom drifts over ideal + tolerance after bedtime, one
  # climate.turn_on restores that parked state (one beep). From the next tick
  # ac_is_running is true, so guard_due is false until DAY_OFF turns the unit off at
  # wake — the running unit IS the latch. Nothing else happens on this tick: the
  # read-back lives in STEP 6b on the following ticks. NIGHT_HOLD / DEEP_HOLD stay empty.
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ is_real_trigger and guard_due }}"
        sequence:
          - service: climate.turn_on
            target:
              entity_id: "{{ ac_climate }}"
          - choose:
              - conditions:
                  - condition: template
                    value_template: "{{ enable_notifications }}"
                sequence:
                  - service: persistent_notification.create
                    data:
                      title: "Bedroom Pre-Cool — Night Guard"
                      message: >
                        {{ now().strftime('%H:%M') }}: the warmest bedroom read
                        {{ warmest_bedroom }}°C, above {{ ideal_temp | float + tolerance | float }}°C
                        (ideal + tolerance). The AC was switched back on and holds until
                        wake time; the blueprint re-checks its mode, setpoint and fan for
                        15 minutes. The restored state is on the climate entity's history.
                      notification_id: "bedroom_precool_guard_fired"

  # =============================================
  # STEP 6b: GUARD SETTLE (v1.1.0) — for 15 min after ANY night start in fan-only
  # mode, assert the parked state from LIVE reads, each call only if different: a
  # restored heat/fan_only/auto mode would "latch" without cooling (board R1-03/R2-04);
  # a stale DRIVE park restores 18 °C / high; a cloud restore reported late is
  # corrected on a later tick instead of lost (board R1-01/R2-03). Normally 0 calls.
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ is_real_trigger and settle_mode_due }}"
        sequence:
          - service: climate.set_hvac_mode
            target:
              entity_id: "{{ ac_climate }}"
            data:
              hvac_mode: "{{ desired_mode }}"
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ is_real_trigger and settle_setpoint_due }}"
        sequence:
          - service: climate.set_temperature
            target:
              entity_id: "{{ ac_climate }}"
            data:
              temperature: "{{ maintaining_setpoint | float }}"
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ is_real_trigger and settle_fan_due }}"
        sequence:
          - service: climate.set_fan_mode
            target:
              entity_id: "{{ ac_climate }}"
            data:
              fan_mode: "{{ night_fan_mode }}"
```

- [ ] **Step 4: run → GREEN** — **`PASS=N FAIL=M`** (M = 0; N = previous + 1).
- [ ] **Step 5: commit** — `git commit -m "feat(bedroom-precool): v1.1.0 T3 — night guard (bare turn_on on 5-min ticks) + 15-min guard settle from live reads"`.

### Task 4: fan due-lists (the fan write rule as rendered variables)

**Model tier:** Sonnet
**Rationale:** The load-bearing rule of the design, fully specified; rendered per-fan tests with fake `expand()` / `state_attr()` states.
**Effort:** high (checkpoint) — `/effort high`.

**Files:** Modify `bedroom_precool.yaml` — STEP 2c, after `settle_fan_due:`. Test file (uses `_S` / `_fan_env` from Task 1).

**Interfaces — Consumes:** Task 1 variables. **Produces:** STEP 2c lists `fans_due_precool`, `fans_due_night`, `fans_unset_night`, `fans_on_at_wake` (lists of entity ids; `[]` when nothing applies; `fans_unset_night ∩ fans_due_night = ∅` by construction).

- [ ] **Step 1 (RED): tests**

```python
KIDS, MASTER = "fan.ceiling_fan_light_v2", "fan.ceiling_fan_light_v2_2"
LOCK = datetime(2026, 9, 9, 19, 29, tzinfo=TZ)
BEFORE, AFTER = LOCK - timedelta(hours=2), LOCK + timedelta(seconds=20)


def _due(bp, name, now, states, **ctx):
    base = dict(bedroom_fans=[MASTER, KIDS], interlocked_fans=[KIDS], interlock_blocked=False,
                night_fans_tonight=True, in_fan_settle=True, night_fan_percentage=1, lock_ts=LOCK.timestamp(),
                fan_assist_tonight=True, in_fan_assist_window=True, precool_fan_percentage=21,
                ac_started_ts=(LOCK - timedelta(hours=2, minutes=30)).timestamp(),
                fans_at_wake="off", in_wake_window=True)
    base.update(ctx)
    return _reparse(_fan_env(now, states).from_string(_var_template(bp, name)).render(**base).strip())


def test_rendered_fans_due_night_applies_the_fan_write_rule(bp):
    now = LOCK + timedelta(minutes=5)
    untouched = [_S(MASTER, "on", 1, BEFORE), _S(KIDS, "off", 21, BEFORE)]
    assert _due(bp, "fans_due_night", now, untouched) == [KIDS]                         # master already at 1 %
    assert _due(bp, "fans_due_night", now, [_S(MASTER, "on", 21, BEFORE), _S(KIDS, "off", 21, BEFORE)]) == [MASTER, KIDS]
    assert _due(bp, "fans_due_night", now, untouched, interlock_blocked=True) == []       # kids fan blocked, master at target
    assert _due(bp, "fans_due_night", now, [_S(MASTER, "on", 21, BEFORE), _S(KIDS, "off", 21, BEFORE)],
                interlock_blocked=True) == [MASTER]                                     # interlock only guards the kids fan
    assert _due(bp, "fans_due_night", now, [_S(MASTER, "on", 21, BEFORE), _S(KIDS, "off", 21, AFTER)]) == [MASTER]   # touched since the lock
    # a percentage change bumps last_updated only; it still counts as touched (board R2-05)
    assert _due(bp, "fans_due_night", now, [_S(MASTER, "on", 21, BEFORE), _S(KIDS, "on", 21, last_updated=AFTER, last_changed=BEFORE)]) == [MASTER]
    assert _due(bp, "fans_due_night", now, [_S(MASTER, "unavailable", None, BEFORE), _S(KIDS, "off", 21, BEFORE)]) == [KIDS]
    assert _due(bp, "fans_due_night", now, [_S(KIDS, "off", 21, BEFORE)]) == [KIDS]      # master absent from the state machine
    assert _due(bp, "fans_due_night", now, [_S(MASTER, "on", None, BEFORE), _S(KIDS, "off", 21, BEFORE)]) == [MASTER, KIDS]   # no percentage attribute: renders, not at target (board R1-04)
    assert _due(bp, "fans_due_night", now, untouched, night_fans_tonight=False) == []
    assert _due(bp, "fans_due_night", now, untouched, in_fan_settle=False) == []
    assert _due(bp, "fans_due_night", now, untouched, bedroom_fans=[]) == []


def test_rendered_fans_due_precool_uses_the_ac_start_as_reference(bp):
    now = LOCK - timedelta(hours=2)
    started = LOCK - timedelta(hours=2, minutes=30)
    fans = [_S(MASTER, "on", 1, started - timedelta(hours=3)), _S(KIDS, "on", 21, started - timedelta(hours=3))]
    assert _due(bp, "fans_due_precool", now, fans) == [MASTER]                            # kids already at 21 %
    assert _due(bp, "fans_due_precool", now, [_S(MASTER, "on", 1, started + timedelta(minutes=1))]) == []   # touched after the start
    assert _due(bp, "fans_due_precool", now, fans, fan_assist_tonight=False) == []
    assert _due(bp, "fans_due_precool", now, fans, in_fan_assist_window=False) == []


def test_rendered_fans_unset_night_is_disjoint_from_due_and_fans_on_at_wake(bp):
    now = LOCK + timedelta(minutes=44)
    fixtures = [
        (dict(interlock_blocked=True), [_S(MASTER, "on", 1, BEFORE), _S(KIDS, "off", 21, BEFORE)]),
        (dict(), [_S(MASTER, "on", 1, BEFORE), _S(KIDS, "off", 21, BEFORE)]),               # due on the last tick → commanded, not reported (board R1-06)
        (dict(), [_S(MASTER, "unavailable", None, BEFORE), _S(KIDS, "off", 21, AFTER)]),
        (dict(interlock_blocked=True), [_S(MASTER, "on", 21, BEFORE), _S(KIDS, "off", 21, BEFORE)]),
    ]
    for ctx, states in fixtures:
        due, unset = _due(bp, "fans_due_night", now, states, **ctx), _due(bp, "fans_unset_night", now, states, **ctx)
        assert not (set(due) & set(unset)), (due, unset)
    assert _due(bp, "fans_unset_night", now, fixtures[0][1], interlock_blocked=True) == [KIDS]
    assert _due(bp, "fans_unset_night", now, fixtures[1][1]) == []
    assert _due(bp, "fans_unset_night", now, fixtures[2][1]) == [MASTER]                 # unavailable, untouched
    morning = datetime(2026, 9, 10, 7, 15, tzinfo=TZ)
    fans = [_S(MASTER, "on", 1, BEFORE), _S(KIDS, "off", 21, BEFORE)]
    assert _due(bp, "fans_on_at_wake", morning, fans) == [MASTER]
    assert _due(bp, "fans_on_at_wake", morning, fans, fans_at_wake="leave") == []
    assert _due(bp, "fans_on_at_wake", morning, fans, in_wake_window=False) == []


def test_fan_due_lists_are_defined_after_their_inputs_and_use_state_attr(text):
    for name in ("fans_due_precool", "fans_due_night", "fans_unset_night", "fans_on_at_wake"):
        assert _def_index(text, "settle_fan_due") < _def_index(text, name)
        assert _def_index(text, "in_fan_settle") < _def_index(text, name)
    assert "s.attributes.percentage" not in text          # Undefined would kill the variables step (board R1-04)
```

- [ ] **Step 2: run → RED**.
- [ ] **Step 3 (GREEN):** append to STEP 2c after `settle_fan_due:`:

```yaml
      # --- v1.1.0 fan write rule → per-window lists of fans DUE for one command ---
      # A fan is due when: configured, present and available, not already at the target
      # (state_attr | int(-1): a missing attribute is None, never an Undefined that
      # would abort this whole variables step), not an interlocked fan while the
      # interlock is blocked, and untouched since the reference instant (last_updated
      # older than it — a percentage change bumps last_updated, not last_changed). Our
      # own command bumps last_updated, so a fan is written at most once per reference;
      # a fan the safety cutoff or a person changed is left alone. The action step
      # (STEP 5c) re-checks the same rule live before each call. Lists cross the
      # variables boundary intact.
      fans_due_night: >-
        {% set ns = namespace(out=[]) %}
        {% if night_fans_tonight and in_fan_settle %}
          {% for f in bedroom_fans %}
            {% set st = expand(f) | list %}
            {% if st | length > 0 %}
              {% set s = st[0] %}
              {% set at_target = s.state == 'on' and (state_attr(f, 'percentage') | int(-1)) == (night_fan_percentage | int) %}
              {% set blocked = (f in interlocked_fans) and interlock_blocked %}
              {% if s.state not in ['unavailable', 'unknown'] and not at_target and not blocked
                    and as_timestamp(s.last_updated) < (lock_ts | float) %}
                {% set ns.out = ns.out + [f] %}
              {% endif %}
            {% endif %}
          {% endfor %}
        {% endif %}
        {{ ns.out }}
      fans_due_precool: >-
        {% set ns = namespace(out=[]) %}
        {% if fan_assist_tonight and in_fan_assist_window %}
          {% for f in bedroom_fans %}
            {% set st = expand(f) | list %}
            {% if st | length > 0 %}
              {% set s = st[0] %}
              {% set at_target = s.state == 'on' and (state_attr(f, 'percentage') | int(-1)) == (precool_fan_percentage | int) %}
              {% set blocked = (f in interlocked_fans) and interlock_blocked %}
              {% if s.state not in ['unavailable', 'unknown'] and not at_target and not blocked
                    and as_timestamp(s.last_updated) < (ac_started_ts | float) %}
                {% set ns.out = ns.out + [f] %}
              {% endif %}
            {% endif %}
          {% endfor %}
        {% endif %}
        {{ ns.out }}
      # Fans that COULD NOT be written this tick (blocked or unavailable), untouched and
      # not at target — disjoint from fans_due_night by construction; reported once on
      # the last settle tick, never retried.
      fans_unset_night: >-
        {% set ns = namespace(out=[]) %}
        {% if night_fans_tonight and in_fan_settle %}
          {% for f in bedroom_fans %}
            {% set st = expand(f) | list %}
            {% if st | length > 0 %}
              {% set s = st[0] %}
              {% set at_target = s.state == 'on' and (state_attr(f, 'percentage') | int(-1)) == (night_fan_percentage | int) %}
              {% set blocked = (f in interlocked_fans) and interlock_blocked %}
              {% if (s.state in ['unavailable', 'unknown'] or blocked) and not at_target
                    and as_timestamp(s.last_updated) < (lock_ts | float) %}
                {% set ns.out = ns.out + [f] %}
              {% endif %}
            {% endif %}
          {% endfor %}
        {% endif %}
        {{ ns.out }}
      fans_on_at_wake: >-
        {% set ns = namespace(out=[]) %}
        {% if fans_at_wake == 'off' and in_wake_window %}
          {% for f in bedroom_fans %}
            {% set st = expand(f) | list %}
            {% if st | length > 0 and st[0].state == 'on' %}
              {% set ns.out = ns.out + [f] %}
            {% endif %}
          {% endfor %}
        {% endif %}
        {{ ns.out }}
```

- [ ] **Step 4: run → GREEN** — **`PASS=N FAIL=M`** (M = 0; N = previous + 4).
- [ ] **Step 5: commit** — `git commit -m "feat(bedroom-precool): v1.1.0 T4 — fan write rule as per-window due lists (state_attr idiom, last_updated touch detection, interlock, disjoint unset list)"`.

### Task 5: fan step (before the AC dispatch, live re-check), skipped notice, debug dump, docs, instance, version

**Model tier:** Sonnet
**Rationale:** Action wiring over lists Task 4 pinned, plus mechanical doc/instance/version edits (folded in to keep one commit).
**Effort:** high (checkpoint) — `/effort high`.

**Files:** Modify `bedroom_precool.yaml` (new STEP 5c between STEP 5b and STEP 6; STEP 7d after 7c; STEP 8 dump; `name`/description v1.1.0), `deploy/bedroom_precool_1779553673971.json`, `requirements_bedroom_precool.md`, `README.md` (§Bedroom Sleep Pre-Cool), test file.

**Interfaces — Consumes:** `fans_due_precool`, `fans_due_night`, `fans_unset_night`, `fans_on_at_wake`, `in_settle_last_tick`, `night_fan_percentage`, `precool_fan_percentage`, `lock_ts`, `ac_started_ts`, `interlocked_fans`, `fan_interlocks`, `interlock_clear_minutes`.

- [ ] **Step 1 (RED): tests** — first extend the walker so it descends into `repeat` blocks (additive edit to `_service_steps`, right after the `choose` branch):

```python
        elif "repeat" in node:
            rep = node["repeat"]
            _service_steps(rep.get("sequence", []), found, conds + (f"for_each={rep.get('for_each', '')}",))
```

then:

```python
def _fan_service_calls(bp):
    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
    return [(c, s) for c, s in steps if str(s.get("service") or s.get("action")).startswith("fan.")]


def test_fan_step_runs_before_the_ac_dispatch_and_rechecks_live_state_per_call(bp, text):
    calls = _fan_service_calls(bp)
    by_list = {}
    for conds, step in calls:
        src = [t for t in conds if t.startswith("for_each=")]
        assert len(src) == 1, "every fan call iterates one due list"
        by_list[src[0]] = (conds, step)
        assert any(t.strip() == "{{ is_real_trigger }}" for t in conds), "manual Run never actuates a fan"
        assert step["target"]["entity_id"] == "{{ repeat.item }}"
        assert step.get("continue_on_error") is True                                 # board R2-07
    assert set(by_list) == {"for_each={{ fans_due_precool }}", "for_each={{ fans_due_night }}", "for_each={{ fans_on_at_wake }}"}
    pre_c, pre = by_list["for_each={{ fans_due_precool }}"]
    assert pre["service"] == "fan.turn_on" and pre["data"]["percentage"] == "{{ precool_fan_percentage | int }}"
    night_c, night = by_list["for_each={{ fans_due_night }}"]
    assert night["service"] == "fan.turn_on" and night["data"]["percentage"] == "{{ night_fan_percentage | int }}"
    for conds, ref in ((pre_c, "ac_started_ts"), (night_c, "lock_ts")):                 # live re-check (board R2-01)
        live = [t for t in conds if "states(repeat.item)" in t]
        assert len(live) == 1 and "last_updated" in live[0] and ref in live[0] and "interlock" in live[0]
    wake = by_list["for_each={{ fans_on_at_wake }}"][1]
    assert wake["service"] == "fan.turn_off" and "data" not in wake
    assert len(calls) == 3
    assert "fan.set_direction" not in text
    assert text.index("STEP 5c") < text.index("STEP 6: PHASE DISPATCH")               # before any climate call or wait


def test_fan_skipped_notice_fires_once_on_the_last_settle_tick(bp):
    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
    notices = [(c, s) for c, s in steps
               if (s.get("service") or s.get("action")) == "persistent_notification.create"
               and (s.get("data") or {}).get("notification_id") == "bedroom_precool_fan_skipped"]
    assert len(notices) == 1
    conds = notices[0][0]
    assert any("in_settle_last_tick" in t and "fans_unset_night | length > 0" in t and "enable_notifications" in t for t in conds)


def test_v110_version_docs_and_instance():
    inst = json.loads(PRECOOL_INSTANCE.read_text())
    i = inst["use_blueprint"]["input"]
    assert inst["alias"].endswith("v1.1.0")
    assert i["night_mode"] == "fan_only" and i["prechill_offset"] == 0.5
    assert i["bedroom_fans"] == ["fan.ceiling_fan_light_v2_2", "fan.ceiling_fan_light_v2"]
    assert i["interlocked_fans"] == ["fan.ceiling_fan_light_v2"]
    assert i["fan_interlocks"] == ["binary_sensor.samuel_samuel_matthew_fanprotection"]
    assert i["interlock_clear_minutes"] == 5                # cutoff hold 3 + 2 (spec §2.1)
    assert i["night_fans"] == "all" and i["fan_assist"] == "off" and i["fans_at_wake"] == "leave"
    assert i["night_fan_percentage"] == 1 and i["precool_fan_percentage"] == 21 and i["fan_settle_minutes"] == 45
    text = BP_PATH.read_text()
    assert "**Version: 1.1.0**" in text
    req = (ROOT / "requirements_bedroom_precool.md").read_text()
    for token in ("fan_only", "Night guard", "settle window", "last_updated", "odd/even", "interlock_clear_minutes"):
        assert token in req, token
    readme = (ROOT / "README.md").read_text()
    assert "Fan-Only Night Hold (v1.1.0)" in readme
```

Update the two existing version pins: `test_version_bumped` → `v1.1.0` / `**Version: 1.1.0**`; `test_precool_instance_keys_exist_and_weather_supports_hourly_forecasts` alias → `v1.1.0`.

- [ ] **Step 2: run → RED**.
- [ ] **Step 3 (GREEN):**

STEP 5c, inserted between STEP 5b (overcooling fault) and STEP 6 — BEFORE any climate call, so nothing sits between the STEP 2c snapshot and the fan command; each call re-checks the rule live (board R2-01):

```yaml
  # =============================================
  # STEP 5c: BEDROOM FANS (v1.1.0) — the ONLY place fan services are called, and
  # deliberately BEFORE the AC dispatch: no climate call sits between the STEP 2c
  # snapshot and the fan command. Each list holds the fans DUE under the fan write
  # rule; every iteration re-checks the rule on LIVE state (availability, target,
  # interlock incl. the clear hold, untouched since the reference) so an adult who
  # entered or a cutoff that fired since the snapshot cancels the command. Empty lists
  # iterate nothing. Direction is never written. continue_on_error: one cloud failure
  # never aborts the other fans or the rest of the tick.
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ is_real_trigger }}"
        sequence:
          - repeat:
              for_each: "{{ fans_due_precool }}"
              sequence:
                - choose:
                    - conditions:
                        - condition: template
                          value_template: >-
                            {{ states(repeat.item) not in ['unavailable', 'unknown']
                               and not (is_state(repeat.item, 'on')
                                        and (state_attr(repeat.item, 'percentage') | int(-1)) == (precool_fan_percentage | int))
                               and not ((repeat.item in interlocked_fans) and fan_interlocks | length > 0
                                        and (expand(fan_interlocks) | list | length < fan_interlocks | length
                                             or expand(fan_interlocks) | selectattr('state', 'in', ['on', 'unavailable', 'unknown']) | list | length > 0
                                             or expand(fan_interlocks) | map(attribute='last_changed') | map('as_timestamp')
                                                | select('gt', as_timestamp(now()) - (interlock_clear_minutes | float) * 60) | list | length > 0))
                               and as_timestamp((expand(repeat.item) | first).last_updated) < (ac_started_ts | float) }}
                      sequence:
                        - service: fan.turn_on
                          continue_on_error: true
                          target:
                            entity_id: "{{ repeat.item }}"
                          data:
                            percentage: "{{ precool_fan_percentage | int }}"
          - repeat:
              for_each: "{{ fans_due_night }}"
              sequence:
                - choose:
                    - conditions:
                        - condition: template
                          value_template: >-
                            {{ states(repeat.item) not in ['unavailable', 'unknown']
                               and not (is_state(repeat.item, 'on')
                                        and (state_attr(repeat.item, 'percentage') | int(-1)) == (night_fan_percentage | int))
                               and not ((repeat.item in interlocked_fans) and fan_interlocks | length > 0
                                        and (expand(fan_interlocks) | list | length < fan_interlocks | length
                                             or expand(fan_interlocks) | selectattr('state', 'in', ['on', 'unavailable', 'unknown']) | list | length > 0
                                             or expand(fan_interlocks) | map(attribute='last_changed') | map('as_timestamp')
                                                | select('gt', as_timestamp(now()) - (interlock_clear_minutes | float) * 60) | list | length > 0))
                               and as_timestamp((expand(repeat.item) | first).last_updated) < (lock_ts | float) }}
                      sequence:
                        - service: fan.turn_on
                          continue_on_error: true
                          target:
                            entity_id: "{{ repeat.item }}"
                          data:
                            percentage: "{{ night_fan_percentage | int }}"
          - repeat:
              for_each: "{{ fans_on_at_wake }}"
              sequence:
                - service: fan.turn_off
                  continue_on_error: true
                  target:
                    entity_id: "{{ repeat.item }}"
```

STEP 7d after 7c:

```yaml
  # =============================================
  # STEP 7d: NIGHT FAN NOT APPLIED — informational notice (last settle tick only)
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ enable_notifications and in_settle_last_tick and fans_unset_night | length > 0 }}"
        sequence:
          - service: persistent_notification.create
            data:
              title: "Bedroom Pre-Cool — Night Fan Not Applied"
              message: >
                {{ fans_unset_night | join(', ') }} did not get the night fan setting
                ({{ night_fan_percentage }}%) within {{ fan_settle_minutes }} min of the
                lock — an interlock stayed on or the fan was unavailable. Nothing will
                retry; set it by hand if you want it on.
              notification_id: "bedroom_precool_fan_skipped"
```

STEP 8 dump — add after the `night fan` line:

```
                **night_mode:** {{ night_mode }} (fan_only={{ fan_only_mode }})
                | **bedtime_target:** {{ bedtime_target }}°C
                | **guard_due:** {{ guard_due }} · settle={{ guard_settle_due }}

                **night_parity:** {{ night_parity }}
                | fan_assist tonight={{ fan_assist_tonight }} · night fans tonight={{ night_fans_tonight }}
                | interlock blocked={{ interlock_blocked }}

                **fans due:** precool={{ fans_due_precool }} · night={{ fans_due_night }}
                · unset={{ fans_unset_night }} · wake-off={{ fans_on_at_wake }}
```

Blueprint header: `name: "Bedroom Sleep Pre-Cool v1.1.0"`, description `**Version: 1.1.0** — ceiling-fan coordination: night_mode fan_only (park, off at the lock unless already over the band, one-beep night guard with the running unit as latch and a 15-minute settle check), pre-chill offset that the lead prediction and the learner aim at, bedroom fan list written under one edge-triggered rule (last_updated touch detection, interlock sensors with a clear hold, live re-check before every call), day-parity switches for the fan-assist / night-fan experiments. History: v1.0.3 …` and a Features bullet each for the night mode, the fans and the guard.

Instance JSON `input` additions: `"night_mode": "fan_only", "prechill_offset": 0.5, "bedroom_fans": ["fan.ceiling_fan_light_v2_2", "fan.ceiling_fan_light_v2"], "interlocked_fans": ["fan.ceiling_fan_light_v2"], "fan_interlocks": ["binary_sensor.samuel_samuel_matthew_fanprotection"], "interlock_clear_minutes": 5, "night_fans": "all", "night_fan_percentage": 1, "fan_assist": "off", "precool_fan_percentage": 21, "fan_settle_minutes": 45, "fans_at_wake": "leave"`; alias `Bedroom Sleep Pre-Cool v1.1.0`.

`requirements_bedroom_precool.md`: phase table — BEDTIME-LOCK row gains "fan_only: park then off unless already over the band (≤ 4 commands: mode, setpoint, fan, off — typically 1)"; add rows "FAN SETTLE (lock → bedtime + settle) — fans to the night percentage under the fan write rule, at most one command per fan, live re-check before each call" and "NIGHT GUARD (any 5-minute tick after bedtime, fan_only) — one bare `turn_on` restoring the parked state; running unit = latch; GUARD SETTLE for 15 min after any night start asserts mode / setpoint (outside ± correction_step) / fan from live reads, normally 0 commands"; new sections "Night mode & pre-chill" (bedtime_target keys delta_in, cooling_needed, DRIVE/HOLD, the learner), "Bedroom fans — the fan write rule" (configured ∧ available ∧ not at target ∧ interlock clear incl. `interlock_clear_minutes` ∧ `last_updated` older than the reference; never re-asserts the safety cutoff or a manual change; never writes direction; deploy-time invariant `interlock_clear_minutes ≥ cutoff hold + 2`), "Experiments (odd/even day-of-year parity of the night's start date, pivot at wake time)"; beep budget lines for both modes: fan_only lock ≤ 4 (typically 1), guard nights turn_on 1 + settle ≤ 3 + nudge ≤ 1 (typical 1–2, worst 5); ac_hold unchanged (lock ≤ 3, nudge ≤ 1); the Hardware section lists optional ceiling fans + interlock sensor; Out-of-scope adds "learning from guard nights"; the known limitation "a fan the safety cutoff resumed after the lock keeps the cutoff's restored speed" (spec §2.5); "manual-override handling is a v1.1.0 item" → "a v1.2.0 item (#19)".

README §Features: `*   **🌀 Fan-Only Night Hold (v1.1.0):** …` and `*   **🪭 Bedroom Fans:** …` bullets (fan write rule in one sentence, parity experiments, the interlock clear-hold invariant), beep bullet updated for fan-only with the numbers above.

- [ ] **Step 4: run → GREEN** — `pytest tests -q` → **`PASS=N FAIL=M`** (M = 0; N ≈ 282 + 19). Then `scripts/deploy-blueprint.sh --dry-run bedroom_precool.yaml leviemartin/bedroom_precool.yaml deploy/bedroom_precool_1779553673971.json` → prints the blueprint name and `instance … ok`, exit 0 (report the exact last line).
- [ ] **Step 5: commit** — `git add bedroom_precool.yaml tests/test_bedroom_precool_structure.py deploy/bedroom_precool_1779553673971.json requirements_bedroom_precool.md README.md && git commit -m "feat(bedroom-precool): v1.1.0 T5 — fan step before the AC dispatch with live re-check, skipped notice, debug dump, docs, instance, version"`.
- [ ] **Step 6:** orchestrator review of the whole diff against the spec §2 (single-lined comparison values, ordering, no bare booleans, no datetime crossing a step, `fan.*` only in STEP 5c, `wait_template` absent); push; open the PR with body `Session: #26` + spec/research/board links (secret-scanned via `gh_scan_body`).

### Task 6: code-time board → merge → deploy → observe

**Model tier:** Opus (board R1) / Fable (orchestration)
**Rationale:** Adversarial review never below Opus; merge/deploy/observe are orchestrator gate work.
**Effort:** xhigh at the [6] gate checkpoint (`/effort xhigh`), `high` after.

- [ ] **Step 1:** TCB `verify "$BASELINE"` (same `TCB_EXTRA`) → rc 0; `review-shipped` → `convene-board` (code-time, standard, CYCLE=1, Codex unpinned); action P0/P1 in-session (delta re-review = fresh dispatch); `gh_post_board` + `gh_post_verdict` on #26; `code-review-gate`; merge (merge commit, keep branch); `#26 → status:in-review`.
- [ ] **Step 2 (deploy, [8]):** `git fetch` + deploy from `main`: `scripts/deploy-blueprint.sh bedroom_precool.yaml leviemartin/bedroom_precool.yaml deploy/bedroom_precool_1779553673971.json`; instance `on`; next tick trace `finished`, `night_mode: fan_only` in the trace variables, 0 errors. Assign the master fan's device to the Master Bedroom area (registry). Add the one-line ownership note to `~/projects/ceiling-fan-hue-blueprint/README.md` (spec §2.6; local repo, no remote — commit there). **Daytime guard live-verify:** copy the instance, set `bedtime` = now + 3 min and `ideal_temp` 20 via the config API, watch: lock tick → park calls if needed → `climate.turn_off` → fans 1 % → next tick NIGHT_HOLD + `guard_due` → `climate.turn_on` → entity shows `cool/21/low`; restore the real instance (POST the saved JSON) and switch the unit off. One house-meter delta reading with a fan at 1 % on/off (fan draw, research contested claim). **Interlock invariant check:** read the cutoff instance's `hold_duration` (3 min) and assert the pre-cool instance's `interlock_clear_minutes` (5) ≥ hold + 2 — record both in the deploy log.
- [ ] **Step 3 (observe, ≥ 2 nights):** criteria from the Phase 1 header; on pass → `observe:closed` → [9] closing-session (`gh_finish_session` #26, update the epic checklist, next session JIT for the A/B experiments: `fan_assist: odd` once PRECOOL nights return).

## Design board 20260909-130652 (design-time, standard, CYCLE=1) — actioned in this plan

R1 (Opus) 10 findings + R2 (Codex gpt-6-astra) 7 findings, cross-family convergence on the guard read-back (R1-01 ≡ R2-03) and the non-cooling restore (R1-03 ≡ R2-04). Every P1/P2 is actioned above: guard settle window replaces the wait/read-back (R1-01, R1-02, R1-03, R2-03, R2-04); fan step moved before STEP 6 with a live per-call re-check (R2-01); 5-minute guard cadence (R2-02); `state_attr | int(-1)` idiom + no-percentage test (R1-04); pre-existing validation test base (R1-05); `fans_unset_night` disjoint from due (R1-06); lock turn_off skipped when over band (R1-07); `delta_in`/`cooling_needed`/substate/learner keyed on `bedtime_target` (R1-08); `interlock_clear_minutes` 5 + deploy invariant (R1-09); beep numbers reconciled (R1-10); fixtures with independent `last_changed`/`last_updated` and split tests (R2-05); wake-pivot parity (R2-06); `continue_on_error` on fan calls (R2-07). Report: `reviews/board-20260909-130652.md`.

## Self-review (writing-plans)

- Spec coverage: §2.1 inputs → T1; §2.2 variables (target-keyed lead terms, parity, windows, guard + settle predicates) → T1 (+ T4 lists); §2.3 fan write rule → T4 + T5 (live re-check); §2.4 phases: PRECOOL target → T1, lock → T2, settle window → T4/T5, guard + guard settle → T3, wake-off → T4/T5, notices → T3/T5, debug → T5; §2.5 restart/cloud cases are properties of the T1/T4 templates (tests: latch, touched, unavailable, missing entity); §2.6 instance/docs/version → T5; §5 acceptance → tests listed per task + T6 live-verify. No gap found.
- Placeholders: none. Every test and YAML block is written out.
- Name consistency: `fans_due_precool` / `fans_due_night` / `fans_unset_night` / `fans_on_at_wake`, `in_settle_last_tick`, `guard_due`, `guard_settle_due`, `settle_mode_due` / `settle_setpoint_due` / `settle_fan_due`, `bedtime_target` (STEP 2a), `lock_ts`, `ac_started_ts` used identically in T1/T3/T4/T5; `_S` / `_fan_env` / `_v110_ctx` defined in T1 and consumed in T2/T4; `_services_in_phase` defined in T2 and used in T3; `_calls_with` defined in T3; the `repeat` walker extension is T5's first step and only T5's tests rely on it.

## Integration addendum (2026-09-09, merged onto main v1.1.0)

Task 6i (Session #26) merged `origin/main` (pre-cool v1.1.0 — manual override,
helper-range clamp, daily-forecast backstop, quantised setpoints — shipped by
the parallel session #19/#28 while this branch was in flight) onto
`feat/bedroom-fan-ac-coordination` and re-versioned the fan coordination as
**v1.2.0**. See the design spec's own "Integration addendum" section for the
full ruling on each item; summary:

1. Version → v1.2.0 everywhere the FAN feature is named (blueprint name/desc,
   instance alias, requirements sections, README bullets, test headers);
   main's own v1.1.0 references (override / helper-range / backstop)
   untouched.
2. `lock_ts` moved before `earliest_turn_on_ts`/`manual_off`; `manual_off`
   gained a clause exempting an off inside `[lock_ts, lock_ts+180)` on a
   fan-only night (the lock's own park-off, not a person's).
3. `guard_due` gained `and not manual_off`.
4. `guard_settle_due` gained `and not manual_setpoint`.
5. `since_ac_start_min` kept re-deriving from `now()` rather than reusing
   main's `ac_state_age_sec` — that value is captured before the STEP 2b
   forecast fetch (stale by the fetch's latency) and reusing it would have
   broken the render-chain test harness's per-call `now()`-relative fixtures
   (`test_rendered_fan_windows`, the guard-settle window test) without a
   broader rewrite. Documented in-line; `ac_started_ts` stays for the due
   lists.
6. `test_precool_commands_are_gated_on_the_override_flags_and_the_boundaries_are_not`'s
   BEDTIME_LOCK service list updated to include `climate.turn_off`.
7. New tests: the `manual_off` lock-window exemption (fan_only vs. ac_hold),
   `guard_due`/`guard_settle_due` under a manual override; `_v110_ctx` gained
   `manual_off=False, manual_setpoint=False`; `MANUAL_OFF_CHAIN` gained
   `lock_ts`, `fan_only_mode`.
8. Docs (Step 2 addendum, Task 5 review finding): NIGHT-HOLD/DEEP-HOLD rows,
   Beep Budget requirements, and the README beep bullet no longer claim
   unqualified "zero commands" in fan_only mode.

Merge commit resolved the five conflicting files (`bedroom_precool.yaml`,
`tests/test_bedroom_precool_structure.py`, the instance JSON, requirements,
README) keeping both sides everywhere, per the task-6i brief's Step 1 rules
(target-keyed variables ours, quantised setpoints main's, our notice renamed
STEP 7d → STEP 7f after main's 7d/7e, main's test section kept first).
