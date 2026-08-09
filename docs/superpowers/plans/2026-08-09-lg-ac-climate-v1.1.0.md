# LG AC Climate v1.1.0 Implementation Plan

**Stakes:** standard — automation logic change in `lg_ac_climate.yaml`; no hard trigger (no deps/auth/CI/migrations/skills), not docs-only, default-up.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `lg_ac_climate.yaml` v1.1.0 — beep-silent idempotent control, hysteresis, fail-safe degradation, exact door timing, cross-midnight windows, self-dismissing notifications, and an auto-detected manual-override hold — with a structural pytest harness.

**Architecture:** Single-blueprint delta on v1.0.0. All logic is Jinja templates inside one YAML file; tests are structural pins (yaml `!input` loader + exact-equality template/shape assertions), NOT template execution. Spec: `docs/superpowers/specs/2026-08-09-lg-ac-climate-v1.1.0-design.md` (read it first — the ladder diagram and rules 1–6 govern Task 8).

**Tech Stack:** HA blueprint YAML (legacy `trigger:`/`service:` keys — do NOT modernize), Jinja2, pytest + PyYAML.

## Global Constraints

- Branch: `lg-ac-v1.1.0` in `~/AI/projects/Blueprints_Home` (already exists, spec committed).
- Test cmd: `cd ~/AI/projects/Blueprints_Home && ~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q`
- `door_sensor` input stays `multiple: true` (empty-list trigger validity depends on it — research §3).
- Door trigger stays `platform: state` (never `device` — `for: !input` breaks there — research §2).
- Helper JSON parse is always `| from_json(default={})`, never bare (research §4).
- Both dismiss steps carry `continue_on_error: true` (research §5).
- Setpoint idempotence tolerance 0.05; manual-detection tolerance 0.3.
- Every `climate.*` call in maintenance/cool/heat sits inside its own per-call `choose` guard.
- Every branch that commands the AC ends with an expected-write (guarded by `hold_enabled`).
- Commit per task; message prefix `feat(lg-ac):` / `test(lg-ac):` as shown.

## File Structure

- Modify: `lg_ac_climate.yaml` (only production file)
- Create: `tests/test_lg_ac_climate_structure.py` (all tasks add to it)
- Modify (Task 9): blueprint `description` block only

## Phase 0 — Pre-flight (Claude)

- `cd ~/AI/projects/Blueprints_Home && git status -sb` → on `lg-ac-v1.1.0`, clean tree.
- `~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest --version` → pytest available (the harness venv lives in a DIFFERENT repo — if missing, stop and surface; do not pip-install into a new venv).
- `~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q` → existing nightlight suite green baseline; report `baseline: PASS=N FAIL=M`.

No shell scripts are touched by any task — the Shell-invariants block is intentionally absent throughout.

## Phase 1 — Implementation (Tasks 1–9, one session, one PR)

**Context budget:** ~55k tokens · 2 files (`lg_ac_climate.yaml` ~610→~800 LOC, test file ~0→~350 LOC) · fits one Sonnet subagent window per task (SDD: each task subagent gets its own task text + the two files).

Test-file helpers established in Task 1 and reused by every later task:

```python
BP = yaml.load(...)                       # module fixture "bp"
get_var(bp, name)   -> str                # STEP-1 variables template text
step_kind(step)     -> str                # 'service:<name>' | 'choose' | 'stop' | 'variables' | 'condition'
ladder(bp)          -> list[dict]         # STEP-3 choose branches
branch_cond(branch) -> str                # first condition's value_template text, stripped
seq_kinds(seq)      -> list[str]          # [step_kind(s) for s in seq]
```

---

### Task 1: Harness bootstrap + v1.0.0 invariant pins

**Model tier:** Sonnet
**Rationale:** Well-specified port of the existing nightlight harness pattern with given test code.
**Effort:** high

**Files:**
- Create: `tests/test_lg_ac_climate_structure.py`

**Interfaces:**
- Produces: fixtures `bp`, `inputs`; helpers `get_var(bp, name)`, `step_kind(step)`, `ladder(bp)`, `branch_cond(branch)`, `seq_kinds(seq)` — exact signatures above; all later tasks import nothing, they extend this file.

- [ ] **Step 1: Write the harness + invariant pins**

```python
"""Structural + logic pins for lg_ac_climate.yaml (LG AC Climate Control v1.1.0).

Run: cd ~/AI/projects/Blueprints_Home && \
     ~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q
"""
from pathlib import Path

import pytest
import yaml

BP_PATH = Path(__file__).resolve().parent.parent / "lg_ac_climate.yaml"


class _Input:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"!input {self.name}"

    def __eq__(self, other):
        return isinstance(other, _Input) and other.name == self.name


class HassLoader(yaml.SafeLoader):
    pass


HassLoader.add_constructor(
    "!input", lambda loader, node: _Input(loader.construct_scalar(node))
)


@pytest.fixture(scope="module")
def bp():
    with BP_PATH.open() as fh:
        return yaml.load(fh, Loader=HassLoader)


@pytest.fixture(scope="module")
def inputs(bp):
    return bp["blueprint"]["input"]


def get_var(bp, name):
    for step in bp["action"]:
        if "variables" in step and name in step["variables"]:
            return step["variables"][name]
    raise KeyError(name)


def step_kind(step):
    if "service" in step:
        return f"service:{step['service']}"
    for k in ("choose", "stop", "variables", "condition"):
        if k in step:
            return k
    return "other"


def ladder(bp):
    # STEP 3 = the LAST action step, a choose ladder
    return bp["action"][-1]["choose"]


def branch_cond(branch):
    c = branch["conditions"][0]
    return " ".join(c["value_template"].split())


def seq_kinds(seq):
    return [step_kind(s) for s in seq]


# ---- v1.0.0 invariants that v1.1.0 must not disturb ----

def test_mode_and_overflow(bp):
    assert bp["mode"] == "restart"
    assert bp["max_exceeded"] == "silent"


def test_untouched_inputs_survive(inputs):
    for name in ("climate_entity", "temperature_sensors", "sensor_strategy",
                 "weather_entity", "door_sensor", "temp_range_low",
                 "temp_range_high", "deadband_outdoor_threshold",
                 "vacation_toggle", "fan_speed_low_threshold",
                 "fan_speed_medium_threshold", "escalation_stage_1_minutes",
                 "escalation_stage_2_minutes", "door_off_delay"):
        assert name in inputs, name


def test_door_sensor_stays_multiple(inputs):
    # research §3: empty-list trigger validity requires multiple: true
    assert inputs["door_sensor"]["selector"]["entity"]["multiple"] is True
    assert inputs["door_sensor"]["default"] == []


def test_fan_discovery_untouched(bp):
    assert "state_attr(climate_ac, 'fan_modes')" in get_var(bp, "available_fan_modes")
```

- [ ] **Step 2: Run tests — all PASS against v1.0.0**

Run: `cd ~/AI/projects/Blueprints_Home && ~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests/test_lg_ac_climate_structure.py -q`
Expected: all PASS (these pin what must not change; the file is still v1.0.0). Report `pytest: PASS=N FAIL=M`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_lg_ac_climate_structure.py
git commit -m "test(lg-ac): harness + v1.0.0 invariant pins"
```

---

### Task 2: New inputs, version bump, validation extension

**Model tier:** Sonnet
**Rationale:** Spec-given input schemas and validation branch, code provided verbatim.
**Effort:** high

**Files:**
- Modify: `lg_ac_climate.yaml` (blueprint.name, description version line, input section, variables mapping, STEP 2)
- Test: `tests/test_lg_ac_climate_structure.py`

**Interfaces:**
- Produces: inputs `comfort_margin`, `sensor_staleness_minutes`, `manual_hold_helper`, `manual_hold_minutes`; variables `margin`, `sensor_staleness`, `hold_helper`, `hold_minutes` (used by Tasks 3, 4, 8).

- [ ] **Step 1: Write failing tests**

```python
def test_version_bumped(bp):
    assert bp["blueprint"]["name"] == "LG AC Climate Control v1.1.0"
    assert "**Version: 1.1.0**" in bp["blueprint"]["description"]


def test_new_input_schemas(inputs):
    cm = inputs["comfort_margin"]
    assert cm["default"] == 0.5
    n = cm["selector"]["number"]
    assert (n["min"], n["max"], n["step"]) == (0.0, 2.0, 0.1)

    st = inputs["sensor_staleness_minutes"]
    assert st["default"] == 90
    n = st["selector"]["number"]
    assert (n["min"], n["max"], n["step"]) == (15, 1440, 5)

    hh = inputs["manual_hold_helper"]
    assert hh["default"] == ""
    assert hh["selector"]["entity"]["domain"] == "input_text"

    hm = inputs["manual_hold_minutes"]
    assert hm["default"] == 60
    n = hm["selector"]["number"]
    assert (n["min"], n["max"], n["step"]) == (15, 360, 5)


def test_variable_mappings_for_new_inputs(bp):
    v = bp["variables"]
    assert v["margin"] == _Input("comfort_margin")
    assert v["sensor_staleness"] == _Input("sensor_staleness_minutes")
    assert v["hold_helper"] == _Input("manual_hold_helper")
    assert v["hold_minutes"] == _Input("manual_hold_minutes")


def test_validation_gate_covers_margin(bp):
    # STEP 2 is the first choose in action (after the variables step)
    gate = bp["action"][1]["choose"]
    conds = [branch_cond(b) for b in gate]
    assert conds[0] == "{{ temp_low | float >= temp_high | float }}"
    assert conds[1] == ("{{ (margin | float * 2) >= "
                        "(temp_high | float - temp_low | float) }}")
    for b in gate:
        assert seq_kinds(b["sequence"]) == ["service:persistent_notification.create", "stop"]
```

- [ ] **Step 2: Run — new tests FAIL, Task-1 pins PASS**

- [ ] **Step 3: Implement**

In `lg_ac_climate.yaml`:
1. `name: "LG AC Climate Control v1.1.0"`; description version line → `**Version: 1.1.0**`.
2. Append to `input:` (after `door_off_delay`):

```yaml
    # --- HYSTERESIS / ROBUSTNESS (v1.1.0) ---
    comfort_margin:
      name: Comfort Margin (°C)
      description: "Hysteresis: an actively heating/cooling AC continues until the room is this far inside the comfort range. 0 = v1.0.0 cycling behavior."
      default: 0.5
      selector:
        number:
          min: 0.0
          max: 2.0
          step: 0.1
          unit_of_measurement: "°C"
    sensor_staleness_minutes:
      name: Sensor Staleness Cutoff (min)
      description: "Ignore temperature sensors whose last report is older than this. Must exceed the sensors' periodic report interval (Aqara ≈ 60 min)."
      default: 90
      selector:
        number:
          min: 15
          max: 1440
          step: 5
          unit_of_measurement: min

    # --- MANUAL OVERRIDE HOLD (v1.1.0, optional) ---
    manual_hold_helper:
      name: Manual Override State Helper (Optional)
      description: "An input_text helper storing the last automation-commanded state. When set, manual remote/app changes pause comfort control for the hold duration. Leave empty to disable."
      default: ""
      selector:
        entity:
          domain: input_text
    manual_hold_minutes:
      name: Manual Hold Duration (min)
      description: "How long comfort control pauses after a manual change is detected."
      default: 60
      selector:
        number:
          min: 15
          max: 360
          step: 5
          unit_of_measurement: min
```

3. Append to top-level `variables:`:

```yaml
  margin: !input comfort_margin
  sensor_staleness: !input sensor_staleness_minutes
  hold_helper: !input manual_hold_helper
  hold_minutes: !input manual_hold_minutes
```

4. In STEP 2's `choose`, append a second branch after the low>=high branch:

```yaml
      - conditions:
          - condition: template
            value_template: "{{ (margin | float * 2) >= (temp_high | float - temp_low | float) }}"
        sequence:
          - service: persistent_notification.create
            data:
              title: "AC Climate Blueprint — Configuration Error"
              message: >
                Comfort margin ({{ margin }}°C) is too large for the comfort
                range ({{ temp_low }}–{{ temp_high }}°C): twice the margin must
                fit inside the range. AC control is paused until corrected.
              notification_id: "ac_climate_config_error"
          - stop: "Comfort margin misconfigured"
```

- [ ] **Step 4: Run the suite and report `pytest: PASS=N FAIL=M` — FAIL must be 0**
- [ ] **Step 5: Commit** — `feat(lg-ac): v1.1.0 inputs + margin validation`

---

### Task 3: Weather safe default + sensor staleness filter

**Model tier:** Sonnet
**Rationale:** Template replacements fully specified; correctness is pinned by exact-equality tests.
**Effort:** high

**Files:**
- Modify: `lg_ac_climate.yaml` STEP 1 variables `valid_temps`, `outdoor_temp`, (new) `outdoor_temp_raw`, `weather_ok`, `deadband_active`
- Test: `tests/test_lg_ac_climate_structure.py`

**Interfaces:**
- Produces: `weather_ok` (bool template) — consumed by `deadband_active`; `valid_temps` staleness clause pinned by tests.

- [ ] **Step 1: Write failing tests**

```python
def test_staleness_filter_uses_last_reported(bp):
    vt = get_var(bp, "valid_temps")
    assert "last_reported" in vt
    assert "last_updated" not in vt          # wrong field — unchanged re-reports must count
    assert "sensor_staleness | int * 60" in vt
    assert "states[s] is not none" in vt


def test_weather_ok_and_safe_deadband(bp):
    raw = " ".join(str(get_var(bp, "outdoor_temp_raw")).split())
    assert raw == "{{ state_attr(entity_weather, 'temperature') }}"
    ok = " ".join(get_var(bp, "weather_ok").split())
    assert ok == ("{{ outdoor_temp_raw is not none and "
                  "outdoor_temp_raw | float(none) is not none }}")
    da = " ".join(get_var(bp, "deadband_active").split())
    assert da == ("{{ (not weather_ok) or "
                  "(outdoor_distance | float < deadband_thresh | float) }}")
```

- [ ] **Step 2: Run — FAIL**
- [ ] **Step 3: Implement** — replace the three variables in STEP 1:

```yaml
      valid_temps: >
        {% set ns = namespace(vals=[]) %}
        {% set cutoff = sensor_staleness | int * 60 %}
        {% for s in sensors_temp %}
          {% set v = states(s) %}
          {% if v not in ['unavailable', 'unknown', none] and v | float(none) is not none
                and states[s] is not none
                and (as_timestamp(now()) - as_timestamp(states[s].last_reported)) < cutoff %}
            {% set ns.vals = ns.vals + [v | float] %}
          {% endif %}
        {% endfor %}
        {{ ns.vals }}
```

```yaml
      outdoor_temp_raw: "{{ state_attr(entity_weather, 'temperature') }}"
      weather_ok: "{{ outdoor_temp_raw is not none and outdoor_temp_raw | float(none) is not none }}"
      outdoor_temp: "{{ outdoor_temp_raw | float(0) if weather_ok else 0 }}"
```

`deadband_active` (leave `outdoor_distance` itself untouched):

```yaml
      deadband_active: "{{ (not weather_ok) or (outdoor_distance | float < deadband_thresh | float) }}"
```

- [ ] **Step 4: Run the suite and report `pytest: PASS=N FAIL=M` — FAIL must be 0**
- [ ] **Step 5: Commit** — `feat(lg-ac): weather-outage safe default + last_reported staleness filter`

---

### Task 4: Hysteresis + escalation distance gate

**Model tier:** Sonnet
**Rationale:** Both templates given verbatim in the plan; tests pin them exactly.
**Effort:** high

**Files:**
- Modify: `lg_ac_climate.yaml` STEP 1 `target_mode`, `target_fan`
- Test: `tests/test_lg_ac_climate_structure.py`

- [ ] **Step 1: Write failing tests**

```python
def test_target_mode_hysteresis(bp):
    tm = " ".join(get_var(bp, "target_mode").split())
    assert tm == (
        "{% if current_temp | float > temp_high | float %} cool "
        "{% elif current_temp | float < temp_low | float %} heat "
        "{% elif current_ac_mode == 'cool' and current_temp | float > "
        "(temp_high | float - margin | float) %} cool "
        "{% elif current_ac_mode == 'heat' and current_temp | float < "
        "(temp_low | float + margin | float) %} heat "
        "{% else %} off {% endif %}"
    )


def test_escalation_distance_gated(bp):
    tf = " ".join(get_var(bp, "target_fan").split())
    # the gate must be the FIRST branch so near-target never escalates
    assert tf.index("dist < fan_low_thresh") < tf.index("esc_stage_2")
    assert "{% if dist < fan_low_thresh | float %} {{ base_fan }}" in tf
```

- [ ] **Step 2: Run — FAIL**
- [ ] **Step 3: Implement**

```yaml
      target_mode: >
        {% if current_temp | float > temp_high | float %}
          cool
        {% elif current_temp | float < temp_low | float %}
          heat
        {% elif current_ac_mode == 'cool' and current_temp | float > (temp_high | float - margin | float) %}
          cool
        {% elif current_ac_mode == 'heat' and current_temp | float < (temp_low | float + margin | float) %}
          heat
        {% else %}
          off
        {% endif %}
```

(`current_ac_mode` is already defined above `target_mode` in v1.0.0 — keep that ordering.)

```yaml
      target_fan: >
        {% set mins = minutes_in_current_mode | int %}
        {% set dist = distance_from_target | float %}
        {% set fan_levels = [fan_mode_low, fan_mode_mid, fan_mode_high, fan_mode_max] %}
        {% set base_idx = fan_levels.index(base_fan) if base_fan in fan_levels else 0 %}
        {% if dist < fan_low_thresh | float %}
          {{ base_fan }}
        {% elif mins >= esc_stage_2 | int %}
          {{ fan_mode_max }}
        {% elif mins >= esc_stage_1 | int %}
          {{ fan_levels[[base_idx + 1, fan_levels | length - 1] | min] }}
        {% else %}
          {{ base_fan }}
        {% endif %}
```

- [ ] **Step 4: Run the suite and report `pytest: PASS=N FAIL=M` — FAIL must be 0**
- [ ] **Step 5: Commit** — `feat(lg-ac): hysteresis target_mode + distance-gated escalation`

---

### Task 5: Cross-midnight operating window

**Model tier:** Sonnet
**Rationale:** Formula given verbatim; single-variable rewrite with exact-equality pin.
**Effort:** high

**Files:**
- Modify: `lg_ac_climate.yaml` STEP 1 schedule variables (add `schedule_start_yesterday`, `schedule_end_yesterday`; rewrite `in_operating_window`)
- Test: `tests/test_lg_ac_climate_structure.py`

- [ ] **Step 1: Write failing tests**

```python
def test_yesterday_schedule_variables(bp):
    sy = " ".join(get_var(bp, "schedule_start_yesterday").split())
    assert "(now().weekday() - 1) % 7" in sy
    ey = " ".join(get_var(bp, "schedule_end_yesterday").split())
    assert "(now().weekday() - 1) % 7" in ey


def test_window_formula_owns_overnight_tail(bp):
    w = " ".join(get_var(bp, "in_operating_window").split())
    assert w == (
        "{% set t_now = now().strftime('%H:%M:%S') %} "
        "{% set today = (schedule_start_today <= t_now < schedule_end_today) "
        "if schedule_start_today <= schedule_end_today "
        "else (t_now >= schedule_start_today) %} "
        "{% set y_tail = schedule_start_yesterday > schedule_end_yesterday "
        "and t_now < schedule_end_yesterday %} "
        "{{ today or y_tail }}"
    )
```

- [ ] **Step 2: Run — FAIL**
- [ ] **Step 3: Implement** — after `schedule_end_today`, add:

```yaml
      schedule_start_yesterday: >
        {{ [t_start_mon, t_start_tue, t_start_wed, t_start_thu, t_start_fri, t_start_sat, t_start_sun][(now().weekday() - 1) % 7] }}
      schedule_end_yesterday: >
        {{ [t_end_mon, t_end_tue, t_end_wed, t_end_thu, t_end_fri, t_end_sat, t_end_sun][(now().weekday() - 1) % 7] }}
```

Replace `in_operating_window`:

```yaml
      in_operating_window: >
        {% set t_now = now().strftime('%H:%M:%S') %}
        {% set today = (schedule_start_today <= t_now < schedule_end_today)
              if schedule_start_today <= schedule_end_today
              else (t_now >= schedule_start_today) %}
        {% set y_tail = schedule_start_yesterday > schedule_end_yesterday
              and t_now < schedule_end_yesterday %}
        {{ today or y_tail }}
```

- [ ] **Step 4: Run the suite and report `pytest: PASS=N FAIL=M` — FAIL must be 0**
- [ ] **Step 5: Commit** — `feat(lg-ac): overnight windows belong to their start day`

---

### Task 6: Reactive triggers + notification auto-dismiss

**Model tier:** Sonnet
**Rationale:** YAML additions given verbatim; research constraints (state platform, multiple:true) are pinned by tests.
**Effort:** high

**Files:**
- Modify: `lg_ac_climate.yaml` `trigger:` list; insert STEP 2b (two dismiss steps) after the validation choose
- Test: `tests/test_lg_ac_climate_structure.py`

**Interfaces:**
- Produces: trigger ids `door_open`, `vacation_off`; STEP 2b occupies `bp["action"][2]` and `bp["action"][3]` (Task 8 inserts STEP 2c after these).

- [ ] **Step 1: Write failing tests**

```python
def test_trigger_roster(bp):
    trigs = bp["trigger"]
    ids = [t.get("id") for t in trigs]
    assert ids == ["update_loop", "vacation_on", "init", "door_open", "vacation_off"]
    door = trigs[3]
    assert door["platform"] == "state"          # research §2: never a device trigger
    assert door["entity_id"] == _Input("door_sensor")
    assert door["to"] == "on"
    assert door["for"] == {"minutes": _Input("door_off_delay")}
    vac = trigs[4]
    assert (vac["platform"], vac["to"]) == ("state", "off")
    assert vac["entity_id"] == _Input("vacation_toggle")


def test_dismiss_steps(bp):
    d1 = bp["action"][2]
    assert step_kind(d1) == "service:persistent_notification.dismiss"
    assert d1["data"]["notification_id"] == "ac_climate_config_error"
    assert d1["continue_on_error"] is True
    d2 = bp["action"][3]
    assert step_kind(d2) == "choose"
    b = d2["choose"][0]
    assert branch_cond(b) == "{{ sensors_available }}"
    inner = b["sequence"][0]
    assert inner["data"]["notification_id"] == "ac_climate_sensor_warning"
    assert inner["continue_on_error"] is True
```

Note: `branch_cond` expects `conditions: [{condition: template, value_template: ...}]` — write the sensor-dismiss guard in that full form, not shorthand.

- [ ] **Step 2: Run — FAIL**
- [ ] **Step 3: Implement**

Append to `trigger:`:

```yaml
  # 4. Door left open (exact-time shut-off)
  - platform: state
    entity_id: !input door_sensor
    to: "on"
    for:
      minutes: !input door_off_delay
    id: "door_open"

  # 5. Vacation Mode OFF (instant resume)
  - platform: state
    entity_id: !input vacation_toggle
    to: "off"
    id: "vacation_off"
```

Insert after the STEP 2 validation choose (before the main ladder):

```yaml
  # =============================================
  # STEP 2b: NOTIFICATION HYGIENE
  # =============================================
  - service: persistent_notification.dismiss
    data:
      notification_id: "ac_climate_config_error"
    continue_on_error: true
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ sensors_available }}"
        sequence:
          - service: persistent_notification.dismiss
            data:
              notification_id: "ac_climate_sensor_warning"
            continue_on_error: true
```

- [ ] **Step 4: Run the suite and report `pytest: PASS=N FAIL=M` — FAIL must be 0**
- [ ] **Step 5: Commit** — `feat(lg-ac): door/vacation-off triggers + self-dismissing notifications`

---

### Task 7: Idempotence guards (beep elimination)

**Model tier:** Sonnet
**Rationale:** Structural restructure fully specified with target shapes; positional shape pins catch drift (kids-room pattern: Sonnet implements, Opus reviews at SDD review stage).
**Effort:** high

**Files:**
- Modify: `lg_ac_climate.yaml` STEP 3 branches: in-range (both sub-branches), cool, heat, and the three off-branches (vacation / window / door)
- Test: `tests/test_lg_ac_climate_structure.py`

**Interfaces:**
- Consumes: ladder helpers from Task 1.
- Produces: every acting branch shaped as `variables → choose(set_temperature) → choose(set_fan_mode)` (comfort) or `choose(turn_off)` (off-branches); Task 8 appends one expected-write step to each of these branches — do not collapse the shapes.

- [ ] **Step 1: Write failing tests**

```python
GUARD_SETPOINT = ("{{ current_ac_mode != desired_mode or "
                  "(state_attr(climate_ac, 'temperature') | float(-99) - "
                  "desired_setpoint | float) | abs > 0.05 }}")
GUARD_FAN = "{{ state_attr(climate_ac, 'fan_mode') != desired_fan }}"


def _acting_branches(bp):
    """cool + heat + the two in-range sub-branches, keyed for messages."""
    lad = ladder(bp)
    in_range = next(b for b in lad if "target_mode == 'off'" in branch_cond(b))
    sub = in_range["sequence"][-1]["choose"]      # deadband choose
    cool = next(b for b in lad if branch_cond(b) == "{{ target_mode == 'cool' }}")
    heat = next(b for b in lad if branch_cond(b) == "{{ target_mode == 'heat' }}")
    return {"maintenance": sub[1], "cool": cool, "heat": heat}


def test_comfort_branches_guard_every_call(bp):
    for name, b in _acting_branches(bp).items():
        kinds = seq_kinds(b["sequence"])
        assert kinds[:3] == ["variables", "choose", "choose"], (name, kinds)
        guard_temp = branch_cond(b["sequence"][1]["choose"][0])
        guard_fan = branch_cond(b["sequence"][2]["choose"][0])
        assert guard_temp == GUARD_SETPOINT, name
        assert guard_fan == GUARD_FAN, name
        inner_t = b["sequence"][1]["choose"][0]["sequence"]
        assert seq_kinds(inner_t) == ["service:climate.set_temperature"], name
        inner_f = b["sequence"][2]["choose"][0]["sequence"]
        assert seq_kinds(inner_f) == ["service:climate.set_fan_mode"], name


def test_cool_heat_desired_values(bp):
    br = _acting_branches(bp)
    cv = br["cool"]["sequence"][0]["variables"]
    assert cv["desired_mode"] == "cool"
    assert " ".join(cv["desired_setpoint"].split()) == "{{ temp_high | float }}"
    assert " ".join(cv["desired_fan"].split()) == "{{ target_fan }}"
    hv = br["heat"]["sequence"][0]["variables"]
    assert hv["desired_mode"] == "heat"
    assert " ".join(hv["desired_setpoint"].split()) == "{{ temp_low | float }}"


def test_off_branches_wrap_turn_off_in_guard(bp):
    lad = ladder(bp)
    for marker in ("is_vacation", "not in_operating_window", "door_is_open"):
        b = next(x for x in lad if marker in branch_cond(x))
        first = b["sequence"][0]
        assert step_kind(first) == "choose", marker
        g = branch_cond(first["choose"][0])
        assert g == "{{ current_ac_mode != 'off' }}", marker
        assert seq_kinds(first["choose"][0]["sequence"]) == ["service:climate.turn_off"], marker
```

- [ ] **Step 2: Run — FAIL**
- [ ] **Step 3: Implement**

Cool branch becomes (heat branch mirrors with `heat`/`temp_low`):

```yaml
      # --- COOL ---
      - conditions:
          - condition: template
            value_template: "{{ target_mode == 'cool' }}"
        sequence:
          - variables:
              desired_mode: "cool"
              desired_setpoint: "{{ temp_high | float }}"
              desired_fan: "{{ target_fan }}"
          - choose:
              - conditions:
                  - condition: template
                    value_template: "{{ current_ac_mode != desired_mode or (state_attr(climate_ac, 'temperature') | float(-99) - desired_setpoint | float) | abs > 0.05 }}"
                sequence:
                  - service: climate.set_temperature
                    target:
                      entity_id: "{{ climate_ac }}"
                    data:
                      hvac_mode: "{{ desired_mode }}"
                      temperature: "{{ desired_setpoint }}"
          - choose:
              - conditions:
                  - condition: template
                    value_template: "{{ state_attr(climate_ac, 'fan_mode') != desired_fan }}"
                sequence:
                  - service: climate.set_fan_mode
                    target:
                      entity_id: "{{ climate_ac }}"
                    data:
                      fan_mode: "{{ desired_fan }}"
```

Maintenance sub-branch (deadband disabled): same three-step shape with

```yaml
          - variables:
              desired_mode: >
                {% if current_ac_mode in ['cool', 'heat'] %}
                  {{ current_ac_mode }}
                {% elif current_temp | float >= ((temp_low | float + temp_high | float) / 2) %}
                  cool
                {% else %}
                  heat
                {% endif %}
              desired_setpoint: "{{ temp_high | float if desired_mode == 'cool' else temp_low | float }}"
              desired_fan: "{{ fan_mode_low }}"
```

(the old inline mode/temperature templates collapse into `desired_*`; the guarded calls are identical to the cool branch).

Off-branches (vacation / out-of-window / door / in-range-deadband-active) each become:

```yaml
        sequence:
          - choose:
              - conditions:
                  - condition: template
                    value_template: "{{ current_ac_mode != 'off' }}"
                sequence:
                  - service: climate.turn_off
                    target:
                      entity_id: "{{ climate_ac }}"
```

(the old sequence-level `condition:` step is removed — Task 8 appends an expected-write after the choose, and a sequence condition would abort it).

- [ ] **Step 4: Run the suite and report `pytest: PASS=N FAIL=M` — FAIL must be 0**
- [ ] **Step 5: Commit** — `feat(lg-ac): per-call idempotence guards — steady-state ticks send zero commands`

---

### Task 8: Manual-override hold

**Model tier:** Sonnet
**Rationale:** The state machine's judgment lives in the spec (rules 1–6); this task transcribes given YAML/Jinja — the SDD Opus reviewer carries the adversarial load.
**Effort:** high

**Files:**
- Modify: `lg_ac_climate.yaml` STEP 1 (hold variables), new STEP 2c, ladder (insert detect/hold branches after door; append expected-writes to all commanding branches)
- Modify: `docs/superpowers/specs/2026-08-09-lg-ac-climate-v1.1.0-design.md` rule 6 (one line — see Step 3.6)
- Test: `tests/test_lg_ac_climate_structure.py`

**Interfaces:**
- Consumes: branch shapes from Task 7 (appends one step to each acting branch).
- Produces: helper JSON contract `{"mode","temp","fan","hold_until"}`.

- [ ] **Step 1: Write failing tests**

```python
EXPECTED_WRITE_VALUE = ("{{ {'mode': desired_mode, 'temp': desired_setpoint | float(none), "
                        "'fan': desired_fan, 'hold_until': hold_until | float(0)} | to_json }}")
OFF_WRITE_VALUE = ("{{ {'mode': 'off', 'temp': none, 'fan': none, "
                   "'hold_until': hold_until | float(0)} | to_json }}")


def test_hold_variables(bp):
    assert " ".join(get_var(bp, "hold_enabled").split()) == \
        "{{ hold_helper not in ['', none] }}"
    exp = " ".join(get_var(bp, "expected").split())
    assert exp == "{{ states(hold_helper) | from_json(default={}) if hold_enabled else {} }}"
    ha = " ".join(get_var(bp, "hold_active").split())
    assert ha == "{{ hold_enabled and hold_until | float(0) > as_timestamp(now()) }}"
    md = " ".join(get_var(bp, "manual_detected").split())
    assert "expected.mode" in md and "> 0.3" in md and "expected.fan" in md
    assert md.startswith("{% if not hold_enabled or hold_active or expected == {} "
                         "or 'mode' not in expected %} false")


def test_step2c_restart_seed(bp):
    s2c = bp["action"][4]          # after the two dismiss steps
    assert step_kind(s2c) == "choose"
    b = s2c["choose"][0]
    assert [c["condition"] for c in b["conditions"]] == ["trigger", "template"]
    assert b["conditions"][0]["id"] == "init"
    assert seq_kinds(b["sequence"]) == ["service:input_text.set_value"]
    val = " ".join(b["sequence"][0]["data"]["value"].split())
    assert "'hold_until': 0" in val and "current_ac_mode" in val


def test_ladder_order_full(bp):
    conds = [branch_cond(b) for b in ladder(bp)]
    assert conds == [
        "{{ not sensors_available }}",
        "{{ current_ac_mode in ['unavailable', 'unknown'] }}",
        "{{ is_vacation }}",
        "{{ not in_operating_window }}",
        "{{ door_is_open }}",
        "{{ manual_detected and not (trigger is defined and trigger.id == 'init') }}",
        "{{ hold_active and not (trigger is defined and trigger.id == 'init') }}",
        "{{ target_mode == 'off' }}",
        "{{ target_mode == 'cool' }}",
        "{{ target_mode == 'heat' }}",
    ]


def test_hold_start_branch_snapshots_and_stops(bp):
    b = ladder(bp)[5]
    assert seq_kinds(b["sequence"]) == ["service:input_text.set_value", "stop"]
    val = " ".join(b["sequence"][0]["data"]["value"].split())
    assert "as_timestamp(now()) + hold_minutes | int * 60" in val
    assert "current_ac_mode" in val


def test_hold_active_branch_stops(bp):
    assert seq_kinds(ladder(bp)[6]["sequence"]) == ["stop"]


def _expected_write_step(step):
    return (step_kind(step) == "choose"
            and branch_cond(step["choose"][0]) == "{{ hold_enabled }}"
            and seq_kinds(step["choose"][0]["sequence"]) == ["service:input_text.set_value"])


def test_every_commanding_branch_ends_with_expected_write(bp):
    lad = ladder(bp)
    # off-branches: vacation, window, door, and in-range deadband-active sub-branch
    for i in (2, 3, 4):
        assert _expected_write_step(lad[i]["sequence"][-1]), i
        val = " ".join(lad[i]["sequence"][-1]["choose"][0]["sequence"][0]["data"]["value"].split())
        assert val == OFF_WRITE_VALUE, i
    in_range = lad[7]["sequence"][-1]["choose"]
    assert _expected_write_step(in_range[0]["sequence"][-1])          # deadband off-branch
    assert _expected_write_step(in_range[1]["sequence"][-1])          # maintenance
    for i in (8, 9):                                                  # cool, heat
        assert _expected_write_step(lad[i]["sequence"][-1]), i
        val = " ".join(lad[i]["sequence"][-1]["choose"][0]["sequence"][0]["data"]["value"].split())
        assert val == EXPECTED_WRITE_VALUE, i
```

- [ ] **Step 2: Run — FAIL**
- [ ] **Step 3: Implement**

3.1 STEP 1 variables (after the fan/escalation block):

```yaml
      # --- Manual Hold (v1.1.0) ---
      current_setpoint: "{{ state_attr(climate_ac, 'temperature') }}"
      current_fan: "{{ state_attr(climate_ac, 'fan_mode') }}"
      hold_enabled: "{{ hold_helper not in ['', none] }}"
      expected: "{{ states(hold_helper) | from_json(default={}) if hold_enabled else {} }}"
      hold_until: "{{ expected.get('hold_until', 0) | float(0) }}"
      hold_active: "{{ hold_enabled and hold_until | float(0) > as_timestamp(now()) }}"
      manual_detected: >
        {% if not hold_enabled or hold_active or expected == {} or 'mode' not in expected %}
          false
        {% elif current_ac_mode != expected.mode %}
          true
        {% elif expected.mode != 'off' and expected.temp is not none
              and (current_setpoint | float(-99) - expected.temp | float(-99)) | abs > 0.3 %}
          true
        {% elif expected.mode != 'off' and expected.fan is not none
              and current_fan != expected.fan %}
          true
        {% else %}
          false
        {% endif %}
```

3.2 STEP 2c after the dismiss steps:

```yaml
  # =============================================
  # STEP 2c: RESTART SEED (no false hold after HA restart)
  # =============================================
  - choose:
      - conditions:
          - condition: trigger
            id: "init"
          - condition: template
            value_template: "{{ hold_enabled }}"
        sequence:
          - service: input_text.set_value
            target:
              entity_id: "{{ hold_helper }}"
            data:
              value: >
                {{ {'mode': current_ac_mode, 'temp': current_setpoint | float(none),
                    'fan': current_fan, 'hold_until': 0} | to_json }}
```

3.3 Ladder: insert after the door branch:

```yaml
      # --- MANUAL CHANGE DETECTED → START HOLD ---
      - conditions:
          - condition: template
            value_template: "{{ manual_detected and not (trigger is defined and trigger.id == 'init') }}"
        sequence:
          - service: input_text.set_value
            target:
              entity_id: "{{ hold_helper }}"
            data:
              value: >
                {{ {'mode': current_ac_mode, 'temp': current_setpoint | float(none),
                    'fan': current_fan,
                    'hold_until': as_timestamp(now()) + hold_minutes | int * 60} | to_json }}
          - stop: "Manual change detected — holding"

      # --- HOLD ACTIVE ---
      - conditions:
          - condition: template
            value_template: "{{ hold_active and not (trigger is defined and trigger.id == 'init') }}"
        sequence:
          - stop: "Manual hold active"
```

3.4 Append to the three off-branches and the in-range deadband-active sub-branch (last step):

```yaml
          - choose:
              - conditions:
                  - condition: template
                    value_template: "{{ hold_enabled }}"
                sequence:
                  - service: input_text.set_value
                    target:
                      entity_id: "{{ hold_helper }}"
                    data:
                      value: >
                        {{ {'mode': 'off', 'temp': none, 'fan': none,
                            'hold_until': hold_until | float(0)} | to_json }}
```

3.5 Append to maintenance/cool/heat branches (last step) — same shape with:

```yaml
                      value: >
                        {{ {'mode': desired_mode, 'temp': desired_setpoint | float(none),
                            'fan': desired_fan, 'hold_until': hold_until | float(0)} | to_json }}
```

3.6 Spec rule 6 amendment (lazy seeding — one-line edit in the spec file): corrupt/empty helper
JSON is treated as no-expectation (detection off); the baseline is (re)established by the next
commanding branch or restart seed, not by a dedicated write.

- [ ] **Step 4: Run the suite and report `pytest: PASS=N FAIL=M` — FAIL must be 0**
- [ ] **Step 5: Commit** — `feat(lg-ac): auto-detected manual-override hold (safety pierces)` (include the spec one-liner in this commit)

---

### Task 9: Description block, YAML lint, full suite

**Model tier:** Haiku
**Rationale:** Mechanical description-text edit plus a suite run; output fully determined by the instruction.
**Effort:** high

**Files:**
- Modify: `lg_ac_climate.yaml` description bullets
- Test: full suite + YAML parse

- [ ] **Step 1: Update description feature bullets** — under `**Features:**` add:

```
    - **Beep-Silent Control:** Commands are sent only when they change
      something — steady state sends nothing (LG units beep per command).
    - **Hysteresis:** Configurable margin stops off/on cycling at the
      comfort-range edges.
    - **Manual-Override Hold:** Optional input_text helper detects remote/app
      changes and pauses comfort control for a configurable window (vacation,
      schedule end, and door-open still force off).
    - **Fail-Safe Degradation:** Weather outage falls back to normal cycling;
      silently-stale sensors are excluded.
```

and update the Requirements list: `input_text helper (optional) for manual-override hold`.

- [ ] **Step 2: Verify description** — add test:

```python
def test_description_documents_new_features(bp):
    d = bp["blueprint"]["description"]
    for token in ("Beep-Silent", "Hysteresis", "Manual-Override Hold", "Fail-Safe"):
        assert token in d
```

- [ ] **Step 3: Full suite + parse check**

Run: `~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -c "import yaml; yaml.SafeLoader; print('parse ok')"` is insufficient — use the harness loader: `~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q` (must be 100% PASS, including the untouched nightlight suite). Report `pytest: PASS=N FAIL=M`.

- [ ] **Step 4: Commit** — `feat(lg-ac): v1.1.0 description + docs polish`

---

## Plan Self-Review (done at write time)

- **Spec coverage:** items 1→T7, 2→T3, 3→T4, 4→T2+T4, 5→T3, 6→T6, 7→T5, 8→T6, 9→T8; version/docs→T2+T9; degradation matrix behaviors are properties of T3/T7/T8; ladder diagram → `test_ladder_order_full` (T8).
- **Type consistency:** `desired_mode/desired_setpoint/desired_fan` (T7) consumed verbatim by T8's `EXPECTED_WRITE_VALUE`; helper JSON keys `mode/temp/fan/hold_until` consistent across T8 variables, seeds, and writes; `hold_until | float(0)` everywhere.
- **Known divergence recorded:** spec rule 6 lazy-seeding amendment (T8 step 3.6) — deliberate, committed with T8.
- **Index caveat:** tests pin `bp["action"]` indices (0 variables, 1 validation, 2–3 dismiss, 4 seed, 5 ladder→`action[-1]`) — T6 and T8 each update `test_dismiss_steps`/`test_step2c_restart_seed` positions if steps land differently; `ladder()` uses `action[-1]` so it is position-proof.
