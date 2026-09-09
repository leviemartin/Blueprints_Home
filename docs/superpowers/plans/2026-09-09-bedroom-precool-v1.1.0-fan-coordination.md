# Bedroom Sleep Pre-Cool v1.1.0 — ceiling-fan coordination + fan-only night hold — Implementation Plan (epic #25, session #26)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Fable orchestrates; tasks 1–5 are Sonnet subagent work with an orchestrator review between tasks; task 6 is the orchestrator's own gate/merge/deploy work.

**Goal:** Ship `bedroom_precool.yaml` v1.1.0: a `night_mode` (`ac_hold` | `fan_only`) with pre-chill, a bedroom-fan list written under one edge-triggered rule, a one-beep night guard, day-parity experiment switches, tests, the migrated instance, docs, and a live deploy before a 19:29 CEST lock.

**Architecture:** additive blueprint inputs + STEP 2a/2c variables that compute (a) the bedtime target, (b) the guard predicate and (c) per-window lists of fans DUE for a write under the fan write rule (configured ∧ available ∧ not at target ∧ interlock clear ∧ `last_updated` older than the reference instant). The action side gains one `climate.turn_off` inside the BEDTIME_LOCK branch (fan-only), one top-level guard step, and one top-level fan step that iterates the due lists with `repeat: for_each`. No helpers; the running AC is the guard latch; `last_updated` is the touch detector.

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
- Fan commands always pass `percentage`; the blueprint never writes `direction`; the fan step is the only place `fan.*` services appear; each due-list is consumed by exactly one `repeat: for_each`.
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

### Task 1: inputs, pass-through, parity/target/guard variables, validation

**Model tier:** Sonnet
**Rationale:** Well-specified additive YAML + rendered-chain tests against a fully written spec.
**Effort:** high (checkpoint) — `/effort high`.

**Files:**
- Modify: `bedroom_precool.yaml` — Group 5 inputs after `night_fan:` (line ≈ 373), new Group 7 after Group 6 (after `enable_notifications`, line ≈ 417), top-level `variables:` Group 5/7 pass-through (lines ≈ 459–467), STEP 2a after `vacation_active` (line ≈ 555), STEP 2c after `night_fan_mode:` (line ≈ 804), STEP 3 condition + message (lines ≈ 807–840).
- Test: `tests/test_bedroom_precool_structure.py` (append a `# --- v1.1.0 …` section).

**Interfaces — Produces** (names later tasks use verbatim): inputs `night_mode`, `prechill_offset`, `bedroom_fans`, `interlocked_fans`, `fan_interlocks`, `interlock_clear_minutes`, `night_fans`, `night_fan_percentage`, `fan_assist`, `precool_fan_percentage`, `fan_settle_minutes`, `fans_at_wake`; STEP 2a vars `fan_only_mode`, `interlock_blocked`, `ac_started_ts`; STEP 2c vars `bedtime_target`, `night_parity`, `fan_assist_tonight`, `night_fans_tonight`, `lock_ts`, `settle_end_tod`, `settle_last_tod`, `since_ac_start_min`, `in_wake_window`, `in_fan_settle`, `in_settle_last_tick`, `in_fan_assist_window`, `guard_due`.

- [ ] **Step 1 (RED): append tests**

```python
# --- v1.1.0 fan coordination (design 2026-09-09) ---------------------------------------

V110_INPUTS = {
    "night_mode": "ac_hold", "prechill_offset": 0.5, "bedroom_fans": [], "interlocked_fans": [],
    "fan_interlocks": [], "interlock_clear_minutes": 3, "night_fans": "all", "night_fan_percentage": 1, "fan_assist": "off",
    "precool_fan_percentage": 21, "fan_settle_minutes": 45, "fans_at_wake": "leave",
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
    ctx = dict(ideal_temp=23, tolerance=1.5, prechill_offset=0.5, night_mode="ac_hold",
               fan_assist="off", night_fans="all", fan_settle_minutes=45, bedtime="19:30:00",
               wake_time="07:15:00", wake_tod="07:15:00", lock_tod="19:29:00",
               ac_is_running=False, warmest_bedroom=23.0, ac_started_ts=0.0, phase="NIGHT_HOLD")
    ctx.update(over)
    return ctx


TARGET_CHAIN = ["fan_only_mode", "bedtime_target"]


def test_rendered_bedtime_target_is_ideal_in_ac_hold_and_ideal_minus_offset_in_fan_only(bp):
    now = datetime(2026, 9, 9, 18, 0, tzinfo=TZ)
    assert _render_chain(bp, TARGET_CHAIN, now, _v110_ctx())["bedtime_target"] == 23.0
    assert _render_chain(bp, TARGET_CHAIN, now, _v110_ctx(night_mode="fan_only"))["bedtime_target"] == 22.5
    assert _render_chain(bp, TARGET_CHAIN, now, _v110_ctx(night_mode="fan_only", prechill_offset=0))["bedtime_target"] == 23.0


PARITY_CHAIN = ["night_parity", "fan_assist_tonight", "night_fans_tonight"]


def test_rendered_night_parity_is_shared_across_the_night_and_pivots_at_noon(bp):
    # 2026-09-09 is day 252 of the year (even); 2026-09-10 is 253 (odd)
    evening = datetime(2026, 9, 9, 19, 29, tzinfo=TZ)
    small_hours = datetime(2026, 9, 10, 1, 0, tzinfo=TZ)
    morning = datetime(2026, 9, 10, 7, 15, tzinfo=TZ)
    next_afternoon = datetime(2026, 9, 10, 15, 0, tzinfo=TZ)
    for t in (evening, small_hours, morning):
        assert _render_chain(bp, PARITY_CHAIN, t, _v110_ctx())["night_parity"] == "even", t
    assert _render_chain(bp, PARITY_CHAIN, next_afternoon, _v110_ctx())["night_parity"] == "odd"
    ctx = _render_chain(bp, PARITY_CHAIN, evening, _v110_ctx(fan_assist="even", night_fans="odd"))
    assert ctx["fan_assist_tonight"] is True and ctx["night_fans_tonight"] is False
    ctx = _render_chain(bp, PARITY_CHAIN, evening, _v110_ctx(fan_assist="off", night_fans="all"))
    assert ctx["fan_assist_tonight"] is False and ctx["night_fans_tonight"] is True


WINDOW_CHAIN = ["lock_ts", "settle_end_tod", "settle_last_tod", "since_ac_start_min", "in_wake_window",
                "in_fan_settle", "in_settle_last_tick", "in_fan_assist_window"]


def _windows(bp, hh, mm, **over):
    now = datetime(2026, 9, 9, hh, mm, tzinfo=TZ)
    ctx = _v110_ctx(now_tod=now.strftime("%H:%M:%S"), **over)
    return _render_chain(bp, WINDOW_CHAIN, now, ctx)


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


def test_rendered_guard_due_only_in_night_phases_with_fan_only_ac_off_and_over_band(bp):
    now = datetime(2026, 9, 9, 23, 0, tzinfo=TZ)
    g = lambda **o: _render_chain(bp, ["fan_only_mode", "guard_due"], now, _v110_ctx(**o))["guard_due"]
    hot = dict(night_mode="fan_only", warmest_bedroom=24.6)
    for ph in ("NIGHT_HOLD", "DEEP_NIGHT_CHECK", "DEEP_HOLD"):
        assert g(phase=ph, **hot) is True, ph
    assert g(phase="NIGHT_HOLD", night_mode="fan_only", warmest_bedroom=24.5) is False   # at the band, not over
    assert g(phase="NIGHT_HOLD", night_mode="ac_hold", warmest_bedroom=26.0) is False
    assert g(phase="NIGHT_HOLD", ac_is_running=True, **hot) is False                     # the latch
    for ph in ("PRECOOL", "BEDTIME_LOCK", "DAY_OFF"):
        assert g(phase=ph, **hot) is False, ph


def test_rendered_interlock_blocked_fails_safe(bp):
    now = datetime(2026, 9, 9, 19, 29, tzinfo=TZ)
    render = lambda states, sensors: _reparse(_fan_env(now, states).from_string(
        _var_template(bp, "interlock_blocked")).render(fan_interlocks=sensors, interlock_clear_minutes=3).strip())
    pir = "binary_sensor.samuel_samuel_matthew_fanprotection"
    assert render([_S(pir, "off")], [pir]) is False      # cleared 7.5 h ago (the _S default)
    assert render([_S(pir, "on")], [pir]) is True
    assert render([_S(pir, "unavailable")], [pir]) is True
    assert render([], [pir]) is True                     # sensor missing from the state machine
    assert render([], []) is False                       # no interlock configured
    # the cutoff resumes only after 3 min continuously clear — so do we (spec §2.1)
    assert render([_S(pir, "off", last_updated=now - timedelta(seconds=90))], [pir]) is True
    assert render([_S(pir, "off", last_updated=now - timedelta(minutes=3, seconds=1))], [pir]) is False


def test_config_validation_rejects_a_settle_window_across_midnight_and_a_noon_crossing_schedule(bp):
    now = datetime(2026, 9, 9, 9, 0, tzinfo=TZ)
    base = dict(drive_setpoint=16, ideal_temp=23, hall_offset=2, deep_night_check="01:00:00",
                bedtime="19:30:00", wake_time="07:15:00", lead_cap_minutes=240, fan_settle_minutes=45)
    tmpl = _env(now).from_string(_config_validation_template(bp))
    render = lambda **kw: _reparse(tmpl.render(**{**base, **kw}).strip())
    assert render() is False                                             # live config
    assert render(bedtime="23:30:00", fan_settle_minutes=45) is True     # 00:15 next day
    assert render(bedtime="11:30:00", wake_time="07:15:00") is True      # bedtime before noon
    assert render(wake_time="12:30:00", bedtime="19:30:00") is True      # wake after noon
```

Add the fan-state fakes just above `V110_INPUTS` (Task 4 uses them too):

```python
class _S:
    """A fake HA State object as `expand()` returns it."""
    def __init__(self, entity_id, state, percentage=None, last_updated=None):
        self.entity_id = entity_id
        self.state = state
        self.attributes = {} if percentage is None else {"percentage": percentage}
        self.last_updated = last_updated or datetime(2026, 9, 9, 12, 0, tzinfo=TZ)
        self.last_changed = self.last_updated


def _fan_env(now, states):
    """`_env` plus an `expand()` that resolves entity ids (or lists) to the fakes."""
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
    env.filters["as_timestamp"] = env.globals["as_timestamp"]     # HA offers it as a filter too
    return env
```

- [ ] **Step 2: run → RED** — `~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests/test_bedroom_precool_structure.py -q -k "v110 or rendered_bedtime_target or night_parity or fan_windows or guard_due or interlock_blocked or settle_window"` → failures (KeyError on missing inputs/templates).

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
        bedroom exceeds Ideal + Drift Tolerance at any minute after bedtime the unit is
        switched back on once (one beep — it restores the parked state) and stays on
        until Wake Time.
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
        Ideal Sleep Temperature before the lock, so the rooms start the coast with a
        margin. 0 = drive to ideal exactly. Ignored in AC-hold mode.
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
        sensor is on (e.g. a fan at head height with a height-gated presence sensor).
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
        An interlock sensor that changed within the last N minutes still blocks, so
        this blueprint never resumes an interlocked fan sooner than the safety
        automation's own hold would (3 min on the kids-room cutoff).
      default: 3
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
        Odd/even = day of the year of the night's START date, for A/B comparisons.
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
      # Any interlock sensor on / unavailable / unknown / absent from the state machine
      # blocks the interlocked fans — the same fail-safe direction as the cutoff
      # blueprint — and so does a sensor that changed within the last
      # interlock_clear_minutes: the cutoff resumes its fan only after 3 min
      # continuously clear, and this blueprint must never resume it sooner.
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
      # last_updated, not last_changed). Reference instant for pre-cool fan assist.
      ac_started_ts: >-
        {% set s = expand(ac_climate) | list %}
        {{ as_timestamp(s[0].last_changed) if s | length > 0 else 0 }}
```

STEP 2c — after `night_fan_mode:` (all single-lined; `phase` is defined above):

```yaml
      # --- v1.1.0: night mode, parity, windows, guard ---
      bedtime_target: "{{ (ideal_temp | float - prechill_offset | float) if fan_only_mode else (ideal_temp | float) }}"
      # Parity of the NIGHT: day of the year of the night's start date. The noon pivot
      # makes 19:29 and 01:00 agree (validation requires bedtime after noon, wake before).
      night_parity: "{{ 'odd' if ((now() - timedelta(hours=12)).timetuple().tm_yday % 2) == 1 else 'even' }}"
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
      # Night guard: fan-only, a night phase, unit off, warmest room over the band. The
      # running unit is the latch — once on, guard_due is false until DAY_OFF turns it off.
      guard_due: "{{ fan_only_mode and phase in ['NIGHT_HOLD', 'DEEP_NIGHT_CHECK', 'DEEP_HOLD'] and not ac_is_running and (warmest_bedroom | float) > (ideal_temp | float + tolerance | float) }}"
```

STEP 3 — extend the validation template (same `or` chain, instants compared inside the template) and the message:

```yaml
                 or bedtime <= '12:00:00'
                 or wake_time >= '12:00:00'
                 or (today_at(bedtime) + timedelta(minutes=fan_settle_minutes | int)).date()
                    != today_at(bedtime).date() }}
```

Message: append "Bedtime must be after 12:00 and Wake Time before 12:00, and Bedtime plus the Fan Settle Window ({{ fan_settle_minutes }} min) must not cross midnight."

- [ ] **Step 4: run → GREEN** — the `-k` selection from Step 2 passes; then the full file `pytest tests -q` → **`PASS=N FAIL=M`** (N = 282 + 7 new, M = 0).
- [ ] **Step 5: commit** — `git add bedroom_precool.yaml tests/test_bedroom_precool_structure.py && git commit -m "feat(bedroom-precool): v1.1.0 T1 — night_mode/pre-chill/fan inputs, parity, windows, guard predicate, validation"`.

### Task 2: BEDTIME_LOCK fan-only branch + pre-chill target in DRIVE/HOLD and the learner

**Model tier:** Sonnet
**Rationale:** Two template substitutions and one gated `climate.turn_off` inside an existing branch, pinned by the branch walker.
**Effort:** high (checkpoint) — `/effort high`.

**Files:** Modify `bedroom_precool.yaml` — `precool_substate:` (≈ line 768), BEDTIME_LOCK branch (≈ 1032–1103, `bedtime_error:` ≈ 1089). Test: `tests/test_bedroom_precool_structure.py`.

**Interfaces — Consumes:** `fan_only_mode`, `bedtime_target` (Task 1). **Produces:** the BEDTIME_LOCK branch's service order `[set_hvac_mode, set_temperature, set_fan_mode, climate.turn_off (cond fan_only_mode), input_number.set_value]`.

- [ ] **Step 1 (RED): tests**

```python
def _services_in_phase(bp, phase):
    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
    return [(c, s) for c, s in steps if any(f"phase == '{phase}'" in t for t in c)]


def test_precool_substate_and_learner_use_bedtime_target(bp):
    now = datetime(2026, 9, 9, 18, 0, tzinfo=TZ)
    sub = lambda w, t: _render(bp, "precool_substate", now, warmest_bedroom=w, bedtime_target=t)
    assert sub(23.0, 23.0) == "HOLD" and sub(23.1, 23.0) == "DRIVE"
    assert sub(22.6, 22.5) == "DRIVE" and sub(22.5, 22.5) == "HOLD"       # pre-chill drives below ideal
    assert "ideal_temp" not in _var_template(bp, "precool_substate")
    lock = [s for c, s in _services_in_phase(bp, "BEDTIME_LOCK")]
    learner = [s for s in lock if (s.get("service") or s.get("action")) == "input_number.set_value"]
    assert len(learner) == 1
    # the bedtime_error variable step sits in the same sequence as the learner write
    text = BP_PATH.read_text()
    assert 'bedtime_error: "{{ warmest_bedroom | float - bedtime_target | float }}"' in text


def test_bedtime_lock_switches_the_unit_off_only_in_fan_only_mode_after_parking_it(bp):
    calls = _services_in_phase(bp, "BEDTIME_LOCK")
    names = [(s.get("service") or s.get("action")) for c, s in calls]
    assert names == ["climate.set_hvac_mode", "climate.set_temperature", "climate.set_fan_mode",
                     "climate.turn_off", "input_number.set_value"], names
    off_conds = [c for c, s in calls if (s.get("service") or s.get("action")) == "climate.turn_off"][0]
    assert any(t.strip() == "{{ fan_only_mode }}" for t in off_conds)
    assert any("ac_is_running" in t for t in off_conds)            # cool-day lock stays a no-op
    # ac_hold regression pin: none of the three park calls is gated on fan_only_mode
    for c, s in calls[:3]:
        assert not any("fan_only_mode" in t for t in c)
```

- [ ] **Step 2: run → RED** (`-k "bedtime_target or switches_the_unit_off"`).
- [ ] **Step 3 (GREEN):** `precool_substate` compares `warmest_bedroom | float > bedtime_target | float`; `bedtime_error: "{{ warmest_bedroom | float - bedtime_target | float }}"`; in the BEDTIME_LOCK `ac_is_running` sequence insert, after the `climate.set_fan_mode` choose and before the auto-learn choose:

```yaml
                          # v1.1.0 fan-only: the unit is now PARKED on the maintaining
                          # setpoint + night fan (the calls above ran only if needed), so a
                          # later night-guard turn_on restores exactly this state in one
                          # command. Switch it off and hand the night to the fans.
                          - choose:
                              - conditions:
                                  - condition: template
                                    value_template: "{{ fan_only_mode }}"
                                sequence:
                                  - service: climate.turn_off
                                    target:
                                      entity_id: "{{ ac_climate }}"
```

Update the branch comment (`# ---------- BEDTIME_LOCK: park (+ off in fan-only) + auto-learn write ----------`).
- [ ] **Step 4: run → GREEN** — `pytest tests -q` → **`PASS=N FAIL=M`** (M = 0; N = previous + 2).
- [ ] **Step 5: commit** — `git add bedroom_precool.yaml tests/test_bedroom_precool_structure.py && git commit -m "feat(bedroom-precool): v1.1.0 T2 — fan-only lock parks then switches the unit off; pre-chill target drives DRIVE/HOLD and the learner"`.

### Task 3: night guard step + guard notice

**Model tier:** Sonnet
**Rationale:** One new top-level step gated on a predicate Task 1 already tests; walker pins.
**Effort:** high (checkpoint) — `/effort high`.

**Files:** Modify `bedroom_precool.yaml` — new `STEP 6a` after the STEP 6 `choose` block (before STEP 7a). Test file.

**Interfaces — Consumes:** `guard_due`, `is_real_trigger`, `enable_notifications`, `warmest_bedroom`, `ideal_temp`, `tolerance`, `ac_climate`.

- [ ] **Step 1 (RED): tests**

```python
def _guard_calls(bp):
    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
    return [(c, s) for c, s in steps if any("guard_due" in t for t in c)]


def test_night_guard_is_one_turn_on_with_a_read_back_correction_gated_on_guard_due(bp):
    calls = _guard_calls(bp)
    names = [(s.get("service") or s.get("action")) for c, s in calls]
    assert names == ["climate.turn_on", "climate.set_temperature", "climate.set_fan_mode",
                     "persistent_notification.create"], names
    conds, turn_on = calls[0]
    assert any(t.strip() == "{{ is_real_trigger and guard_due }}" for t in conds)
    assert turn_on["target"]["entity_id"] == "{{ ac_climate }}"
    assert "data" not in turn_on                       # a bare turn_on: the unit restores its parked state
    # corrections fire only on a difference read back AFTER the unit reports running
    assert any("restored_setpoint" in t and "maintaining_setpoint" in t and "abs > 0.1" in t for t in calls[1][0])
    assert calls[1][1]["data"]["temperature"] == "{{ maintaining_setpoint | float }}"
    assert any("restored_fan != night_fan_mode" in t and "enable_fan_control" in t for t in calls[2][0])
    assert calls[2][1]["data"]["fan_mode"] == "{{ night_fan_mode }}"
    seg = BP_PATH.read_text().split("STEP 6a", 1)[1][:4000]
    assert seg.index("climate.turn_on") < seg.index("wait_template") < seg.index("restored_setpoint:") < seg.index("climate.set_temperature")
    assert 'timeout: "00:00:10"' in seg and "continue_on_timeout: true" in seg
    notice = calls[3][1]
    assert notice["data"]["notification_id"] == "bedroom_precool_guard_fired"
    assert any("enable_notifications" in t for t in calls[3][0])
    # the three night branches of STEP 6 stay free of climate calls (guard lives outside)
    for ph in ("NIGHT_HOLD", "DEEP_HOLD"):
        assert _services_in_phase(bp, ph) == []
```

- [ ] **Step 2: run → RED**.
- [ ] **Step 3 (GREEN):** insert after the STEP 6 block:

```yaml
  # =============================================
  # STEP 6a: NIGHT GUARD (v1.1.0, fan-only nights) — at most one command per night.
  # The unit was parked (maintaining setpoint + night fan) and switched off at the
  # lock; if the warmest bedroom drifts over ideal + tolerance at ANY minute after
  # bedtime, one climate.turn_on restores that parked state (one beep). From the next
  # tick ac_is_running is true, so guard_due is false until DAY_OFF turns the unit
  # off at wake — the running unit IS the latch. NIGHT_HOLD / DEEP_HOLD stay empty.
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ is_real_trigger and guard_due }}"
        sequence:
          - service: climate.turn_on
            target:
              entity_id: "{{ ac_climate }}"
          # The unit restores its parked state (verified on this unit: 2 s). Read it
          # back once it reports running and correct ONLY what differs — normally
          # nothing; one or two commands when the park was stale (a manual mid-DRIVE
          # switch-off earlier that day). Same tick, so the deep-night nudge on later
          # ticks works from the corrected setpoint instead of racing it.
          - wait_template: "{{ states(ac_climate) not in ['off', 'unavailable', 'unknown'] }}"
            timeout: "00:00:10"
            continue_on_timeout: true
          - variables:
              restored_setpoint: "{{ state_attr(ac_climate, 'temperature') }}"
              restored_fan: "{{ state_attr(ac_climate, 'fan_mode') }}"
          - choose:
              - conditions:
                  - condition: template
                    value_template: >-
                      {{ restored_setpoint not in [none, 'none', 'unknown', 'unavailable']
                         and (restored_setpoint | float - maintaining_setpoint | float) | abs > 0.1 }}
                sequence:
                  - service: climate.set_temperature
                    target:
                      entity_id: "{{ ac_climate }}"
                    data:
                      temperature: "{{ maintaining_setpoint | float }}"
          - choose:
              - conditions:
                  - condition: template
                    value_template: >-
                      {{ enable_fan_control and ac_fan_modes | length > 0
                         and restored_fan != night_fan_mode }}
                sequence:
                  - service: climate.set_fan_mode
                    target:
                      entity_id: "{{ ac_climate }}"
                    data:
                      fan_mode: "{{ night_fan_mode }}"
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
                        wake time; its restored setpoint and fan are on the climate
                        entity's history.
                      notification_id: "bedroom_precool_guard_fired"
```

- [ ] **Step 4: run → GREEN** — **`PASS=N FAIL=M`**.
- [ ] **Step 5: commit** — `git commit -m "feat(bedroom-precool): v1.1.0 T3 — night guard: one turn_on restoring the parked state, running unit as latch"`.

### Task 4: fan due-lists (the fan write rule as rendered variables)

**Model tier:** Sonnet
**Rationale:** The load-bearing rule of the design, but fully specified; rendered per-fan tests with fake `expand()` states.
**Effort:** high (checkpoint) — `/effort high`.

**Files:** Modify `bedroom_precool.yaml` — STEP 2c, after `guard_due:`. Test file (uses `_S` / `_fan_env` from Task 1).

**Interfaces — Consumes:** Task 1 variables. **Produces:** STEP 2c lists `fans_due_precool`, `fans_due_night`, `fans_unset_night`, `fans_on_at_wake` (lists of entity ids; `[]` when nothing applies).

- [ ] **Step 1 (RED): tests**

```python
KIDS, MASTER = "fan.ceiling_fan_light_v2", "fan.ceiling_fan_light_v2_2"
PIR = "binary_sensor.samuel_samuel_matthew_fanprotection"
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
    assert _due(bp, "fans_due_night", now, [_S(MASTER, "unavailable", None, BEFORE), _S(KIDS, "off", 21, BEFORE)]) == [KIDS]
    assert _due(bp, "fans_due_night", now, [_S(KIDS, "off", 21, BEFORE)]) == [KIDS]      # master absent from the state machine
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


def test_rendered_fans_unset_night_and_fans_on_at_wake(bp):
    now = LOCK + timedelta(minutes=44)
    fans = [_S(MASTER, "on", 1, BEFORE), _S(KIDS, "off", 21, BEFORE)]
    assert _due(bp, "fans_unset_night", now, fans, interlock_blocked=True) == [KIDS]      # still pending at the window's end
    assert _due(bp, "fans_unset_night", now, [_S(MASTER, "on", 1, BEFORE), _S(KIDS, "off", 21, AFTER)]) == []   # touched = not ours
    morning = datetime(2026, 9, 10, 7, 15, tzinfo=TZ)
    assert _due(bp, "fans_on_at_wake", morning, [_S(MASTER, "on", 1, BEFORE), _S(KIDS, "off", 21, BEFORE)]) == [MASTER]
    assert _due(bp, "fans_on_at_wake", morning, fans, fans_at_wake="leave") == []
    assert _due(bp, "fans_on_at_wake", morning, fans, in_wake_window=False) == []


def test_fan_due_lists_are_defined_after_their_inputs(text):
    for name in ("fans_due_precool", "fans_due_night", "fans_unset_night", "fans_on_at_wake"):
        assert _def_index(text, "guard_due") < _def_index(text, name)
        assert _def_index(text, "in_fan_settle") < _def_index(text, name)
```

- [ ] **Step 2: run → RED**.
- [ ] **Step 3 (GREEN):** append to STEP 2c after `guard_due:`:

```yaml
      # --- v1.1.0 fan write rule → per-window lists of fans DUE for one command ---
      # A fan is due when: configured, present and available, not already at the target,
      # not an interlocked fan while the interlock is blocked, and untouched since the
      # reference instant (last_updated older than it — a percentage change bumps
      # last_updated, not last_changed). Our own command bumps last_updated, so a fan is
      # written at most once per reference; a fan the safety cutoff or a person changed
      # is left alone. Lists cross the variables boundary intact.
      fans_due_night: >-
        {% set ns = namespace(out=[]) %}
        {% if night_fans_tonight and in_fan_settle %}
          {% for f in bedroom_fans %}
            {% set st = expand(f) | list %}
            {% if st | length > 0 %}
              {% set s = st[0] %}
              {% set at_target = s.state == 'on' and (s.attributes.percentage | int(-1)) == (night_fan_percentage | int) %}
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
              {% set at_target = s.state == 'on' and (s.attributes.percentage | int(-1)) == (precool_fan_percentage | int) %}
              {% set blocked = (f in interlocked_fans) and interlock_blocked %}
              {% if s.state not in ['unavailable', 'unknown'] and not at_target and not blocked
                    and as_timestamp(s.last_updated) < (ac_started_ts | float) %}
                {% set ns.out = ns.out + [f] %}
              {% endif %}
            {% endif %}
          {% endfor %}
        {% endif %}
        {{ ns.out }}
      # Fans that never got their night setting (blocked or unavailable throughout the
      # settle window) and that nobody touched — reported once, never retried.
      fans_unset_night: >-
        {% set ns = namespace(out=[]) %}
        {% if night_fans_tonight and in_fan_settle %}
          {% for f in bedroom_fans %}
            {% set st = expand(f) | list %}
            {% if st | length > 0 %}
              {% set s = st[0] %}
              {% set at_target = s.state == 'on' and (s.attributes.percentage | int(-1)) == (night_fan_percentage | int) %}
              {% if not at_target and as_timestamp(s.last_updated) < (lock_ts | float) %}
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

- [ ] **Step 4: run → GREEN** — **`PASS=N FAIL=M`**.
- [ ] **Step 5: commit** — `git commit -m "feat(bedroom-precool): v1.1.0 T4 — fan write rule as per-window due lists (touch detection via last_updated, interlock, idempotent)"`.

### Task 5: fan step, skipped notice, debug dump, docs, instance, version

**Model tier:** Sonnet
**Rationale:** Action wiring over lists Task 4 pinned, plus mechanical doc/instance/version edits (the doc parts are Haiku-grade but folded in to keep one commit).
**Effort:** high (checkpoint) — `/effort high`.

**Files:** Modify `bedroom_precool.yaml` (new STEP 6b after STEP 6a; STEP 7d after 7c; STEP 8 dump; `name`/description v1.1.0), `deploy/bedroom_precool_1779553673971.json`, `requirements_bedroom_precool.md`, `README.md` (§Bedroom Sleep Pre-Cool), test file.

**Interfaces — Consumes:** `fans_due_precool`, `fans_due_night`, `fans_unset_night`, `fans_on_at_wake`, `in_settle_last_tick`, `night_fan_percentage`, `precool_fan_percentage`.

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


def test_fan_step_consumes_each_due_list_exactly_once_with_explicit_percentages(bp):
    calls = _fan_service_calls(bp)
    by_list = {}
    for conds, step in calls:
        src = [t for t in conds if t.startswith("for_each=")]
        assert len(src) == 1, "every fan call iterates one due list"
        by_list[src[0]] = (conds, step)
        assert any(t.strip() == "{{ is_real_trigger }}" for t in conds), "manual Run never actuates a fan"
        assert step["target"]["entity_id"] == "{{ repeat.item }}"
    assert set(by_list) == {"for_each={{ fans_due_precool }}", "for_each={{ fans_due_night }}", "for_each={{ fans_on_at_wake }}"}
    pre = by_list["for_each={{ fans_due_precool }}"][1]
    assert pre["service"] == "fan.turn_on" and pre["data"]["percentage"] == "{{ precool_fan_percentage | int }}"
    night = by_list["for_each={{ fans_due_night }}"][1]
    assert night["service"] == "fan.turn_on" and night["data"]["percentage"] == "{{ night_fan_percentage | int }}"
    wake = by_list["for_each={{ fans_on_at_wake }}"][1]
    assert wake["service"] == "fan.turn_off" and "data" not in wake
    assert len(calls) == 3
    assert "fan.set_direction" not in BP_PATH.read_text()


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
    assert i["interlock_clear_minutes"] == 3
    assert i["night_fans"] == "all" and i["fan_assist"] == "off" and i["fans_at_wake"] == "leave"
    assert i["night_fan_percentage"] == 1 and i["precool_fan_percentage"] == 21 and i["fan_settle_minutes"] == 45
    text = BP_PATH.read_text()
    assert "**Version: 1.1.0**" in text
    req = (ROOT / "requirements_bedroom_precool.md").read_text()
    for token in ("fan_only", "Night guard", "settle window", "last_updated", "odd/even"):
        assert token in req, token
    readme = (ROOT / "README.md").read_text()
    assert "Fan-Only Night Hold (v1.1.0)" in readme
```

Update the two existing version pins: `test_version_bumped` → `v1.1.0` / `**Version: 1.1.0**`; `test_precool_instance_keys_exist_and_weather_supports_hourly_forecasts` alias → `v1.1.0`.

- [ ] **Step 2: run → RED**.
- [ ] **Step 3 (GREEN):**

STEP 6b after STEP 6a:

```yaml
  # =============================================
  # STEP 6b: BEDROOM FANS (v1.1.0) — the ONLY place fan services are called.
  # Each list holds the fans DUE under the fan write rule (STEP 2c); iterating it
  # issues one command per fan and the fan's own last_updated then excludes it from
  # every later tick. Empty lists iterate nothing. Direction is never written.
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ is_real_trigger }}"
        sequence:
          - repeat:
              for_each: "{{ fans_due_precool }}"
              sequence:
                - service: fan.turn_on
                  target:
                    entity_id: "{{ repeat.item }}"
                  data:
                    percentage: "{{ precool_fan_percentage | int }}"
          - repeat:
              for_each: "{{ fans_due_night }}"
              sequence:
                - service: fan.turn_on
                  target:
                    entity_id: "{{ repeat.item }}"
                  data:
                    percentage: "{{ night_fan_percentage | int }}"
          - repeat:
              for_each: "{{ fans_on_at_wake }}"
              sequence:
                - service: fan.turn_off
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
                | **guard_due:** {{ guard_due }}

                **night_parity:** {{ night_parity }}
                | fan_assist tonight={{ fan_assist_tonight }} · night fans tonight={{ night_fans_tonight }}
                | interlock blocked={{ interlock_blocked }}

                **fans due:** precool={{ fans_due_precool }} · night={{ fans_due_night }}
                · unset={{ fans_unset_night }} · wake-off={{ fans_on_at_wake }}
```

Blueprint header: `name: "Bedroom Sleep Pre-Cool v1.1.0"`, description `**Version: 1.1.0** — ceiling-fan coordination: night_mode fan_only (park, off at the lock, one-beep night guard with the running unit as latch), pre-chill offset, bedroom fan list written under one edge-triggered rule (last_updated touch detection, interlock sensors), day-parity switches for the fan-assist / night-fan experiments. History: v1.0.3 …` and a Features bullet each for the night mode, the fans and the guard.

Instance JSON `input` additions: `"night_mode": "fan_only", "prechill_offset": 0.5, "bedroom_fans": ["fan.ceiling_fan_light_v2_2", "fan.ceiling_fan_light_v2"], "interlocked_fans": ["fan.ceiling_fan_light_v2"], "fan_interlocks": ["binary_sensor.samuel_samuel_matthew_fanprotection"], "interlock_clear_minutes": 3, "night_fans": "all", "night_fan_percentage": 1, "fan_assist": "off", "precool_fan_percentage": 21, "fan_settle_minutes": 45, "fans_at_wake": "leave"`; alias `Bedroom Sleep Pre-Cool v1.1.0`.

`requirements_bedroom_precool.md`: phase table — BEDTIME-LOCK row gains "fan_only: park then off (≤ 3, typically 1)"; add rows "FAN SETTLE (lock → bedtime + settle) — fans to the night percentage under the fan write rule, at most one command per fan" and "NIGHT GUARD (any minute after bedtime, fan_only) — one `turn_on` restoring the parked state; running unit = latch"; new sections "Night mode & pre-chill", "Bedroom fans — the fan write rule" (configured ∧ available ∧ not at target ∧ interlock clear ∧ `last_updated` older than the reference; never re-asserts the safety cutoff or a manual change; never writes direction), "Experiments (odd/even day-of-year parity)"; beep budget lines for both modes; the Hardware section lists optional ceiling fans + interlock sensor; Out-of-scope adds "learning from guard nights"; the known limitation "a fan the safety cutoff resumed after the lock keeps the cutoff's restored speed" (spec §2.5); "manual-override handling is a v1.1.0 item" → "a v1.2.0 item (#19)".

README §Features: `*   **🌀 Fan-Only Night Hold (v1.1.0):** …` and `*   **🪭 Bedroom Fans:** …` bullets (fan write rule in one sentence, parity experiments), beep bullet updated for fan-only.

- [ ] **Step 4: run → GREEN** — `pytest tests -q` → **`PASS=N FAIL=M`** (M = 0; N ≈ 282 + 19). Then `scripts/deploy-blueprint.sh --dry-run bedroom_precool.yaml leviemartin/bedroom_precool.yaml deploy/bedroom_precool_1779553673971.json` → prints the blueprint name and `instance … ok`, exit 0 (report the exact last line).
- [ ] **Step 5: commit** — `git add bedroom_precool.yaml tests/test_bedroom_precool_structure.py deploy/bedroom_precool_1779553673971.json requirements_bedroom_precool.md README.md && git commit -m "feat(bedroom-precool): v1.1.0 T5 — fan step, skipped notice, debug dump, docs, instance, version"`.
- [ ] **Step 6:** orchestrator review of the whole diff against the spec §2 (single-lined comparison values, ordering, no bare booleans, no datetime crossing a step, `fan.*` only in STEP 6b); push; open the PR with body `Session: #26` + spec/research links (secret-scanned via `gh_scan_body`).

### Task 6: code-time board → merge → deploy → observe

**Model tier:** Opus (board R1) / Fable (orchestration)
**Rationale:** Adversarial review never below Opus; merge/deploy/observe are orchestrator gate work.
**Effort:** xhigh at the [6] gate checkpoint (`/effort xhigh`), `high` after.

- [ ] **Step 1:** TCB `verify "$BASELINE"` (same `TCB_EXTRA`) → rc 0; `review-shipped` → `convene-board` (code-time, standard, CYCLE=1, Codex unpinned); action P0/P1 in-session (delta re-review = fresh dispatch); `gh_post_board` + `gh_post_verdict` on #26; `code-review-gate`; merge (merge commit, keep branch); `#26 → status:in-review`.
- [ ] **Step 2 (deploy, [8]):** `git fetch` + deploy from `main`: `scripts/deploy-blueprint.sh bedroom_precool.yaml leviemartin/bedroom_precool.yaml deploy/bedroom_precool_1779553673971.json`; instance `on`; next tick trace `finished`, `night_mode: fan_only` in the trace variables, 0 errors. Assign the master fan's device to the Master Bedroom area (registry). Add the one-line ownership note to `~/projects/ceiling-fan-hue-blueprint/README.md` (spec §2.6; local repo, no remote — commit there). **Daytime guard live-verify:** copy the instance, set `bedtime` = now + 3 min and `ideal_temp` 20 via the config API, watch: lock tick → park calls if needed → `climate.turn_off` → fans 1 % → next tick NIGHT_HOLD + `guard_due` → `climate.turn_on` → entity shows `cool/21/low`; restore the real instance (POST the saved JSON) and switch the unit off. One house-meter delta reading with a fan at 1 % on/off (fan draw, research contested claim).
- [ ] **Step 3 (observe, ≥ 2 nights):** criteria from the Phase 1 header; on pass → `observe:closed` → [9] closing-session (`gh_finish_session` #26, update the epic checklist, next session JIT for the A/B experiments: `fan_assist: odd` once PRECOOL nights return).

## Self-review (writing-plans)

- Spec coverage: §2.1 inputs → T1; §2.2 variables → T1 (+ T4 lists); §2.3 fan write rule → T4 + T5; §2.4 phases: PRECOOL target → T2, lock → T2, settle window → T4/T5, guard → T3, wake-off → T4/T5, notices → T3/T5, debug → T5; §2.5 restart/cloud cases are properties of the T1/T4 templates (tests: latch, touched, unavailable, missing entity); §2.6 instance/docs/version → T5; §5 acceptance → tests listed per task + T6 live-verify. No gap found.
- Placeholders: none. Every test and YAML block is written out.
- Name consistency: `fans_due_precool` / `fans_due_night` / `fans_unset_night` / `fans_on_at_wake`, `in_settle_last_tick`, `guard_due`, `bedtime_target`, `lock_ts`, `ac_started_ts` used identically in T1/T3/T4/T5; `_S` / `_fan_env` defined in T1 and consumed in T4; `_services_in_phase` defined in T2 and used in T3; the `repeat` walker extension is T5's first step and only T5's tests rely on it.
