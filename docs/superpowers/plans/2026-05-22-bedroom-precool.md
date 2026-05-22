# Bedroom Sleep Pre-Cool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Home Assistant blueprint (`bedroom_precool.yaml`) that drives a single hall LG air conditioner to bring the bedrooms to an ideal sleep temperature by a fixed bedtime, then holds the room quietly overnight within a strict beep budget — using a transparent, self-learning lead-time prediction.

**Architecture:** Single-file HA blueprint, `mode: restart`, `max_exceeded: silent`. Top-level `variables:` block does `!input` pass-through. The `action:` block is an 8-stage pipeline: mute sound -> live-state variables -> forecast fetch -> prediction/phase variables -> config validation -> vacation override -> sensor validation -> 6-phase dispatch `choose`. The state machine is stateless per 1-minute tick: the phase is derived purely from `now`-vs-boundary time-of-day comparisons (overnight-wrap-aware). Turn-on is a one-way latch keyed off the AC's own running state. Every climate service call is guarded by a current-vs-desired idempotency comparison — a stray call is a stray beep over a sleeping child. `NIGHT_HOLD` and `DEEP_HOLD` are genuinely empty branches (zero service calls).

**Tech Stack:** Home Assistant Core 2025.7+ blueprint YAML, Jinja2 templates, `python3` + `pyyaml` for local syntax + structural validation. No live HA in the build environment — HA import and behavioural testing are delegated to the user (Task 14).

**Reference spec:** `docs/superpowers/specs/2026-05-22-bedroom-precool-design.md` (validated by `docs/superpowers/research/2026-05-22-bedroom-precool-research-validation.md`, verdict PROCEED).

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `bedroom_precool.yaml` | **Create** | The blueprint — metadata, 32 inputs, 3 triggers, top-level `!input` variables, 8-stage action pipeline |
| `requirements_bedroom_precool.md` | **Create** | User-facing requirements doc (mirrors `requirements_lg_ac_climate.md` style) |
| `README.md` | **Modify** | Add a blueprint section under the existing index, matching the existing entry format |

**Conventions carried from the existing repo blueprints (`bathroom_heating_rack.yaml`, `lg_ac_climate.yaml`):**
- Top-level `variables:` block for all `!input` pass-through (resolves at automation-creation time; available everywhere below).
- All runtime variables computed *inside* `action:` so HA generates a trace entry on any template failure.
- `choose` dispatch for phase / priority logic.
- Idempotent service calls — here a hard correctness invariant.
- Stateless re-evaluation every tick.
- Manual-run debug persistent notification with a deterministic `notification_id`.
- `mode: restart`, `max_exceeded: silent`.
- Semantic version in the blueprint `name`.
- Climate-entity capabilities (`min_temp`, `max_temp`, `fan_modes`, `hvac_modes`) discovered from attributes — never hard-coded.

**Build environment notes:**
- All commands in this plan run from the **repo root** (cwd-relative). Do **not** hardcode any absolute or macOS path.
- Work is on git branch `feat/bedroom-precool` (already checked out).
- **YAML validation command (used at the end of every YAML task):**
  ```bash
  python3 -c "import yaml; yaml.SafeLoader.add_multi_constructor('!', lambda l,s,n: None); yaml.safe_load(open('bedroom_precool.yaml'))" && echo VALID
  ```
  The `add_multi_constructor('!', ...)` call teaches stock `pyyaml` to treat HA's `!input` custom tag as a no-op — without it, `yaml.safe_load` raises `ConstructorError: could not determine a constructor for the tag '!input'`. Home Assistant's own YAML loader registers `!input` natively; this shim only makes offline linting possible. Expected output: `VALID`. Any `yaml.YAMLError` fails the step.

---

## Phase 0 — Pre-flight (Claude)

Operator-Claude work that must run before any execution handoff:

1. **Branch** — `feat/bedroom-precool` is already created and checked out (done during the research-validate batch). Verify: `git branch --show-current`.
2. **Commit the upstream Stack A artifacts** — the revised spec, `research-validation.md`, and this annotated plan are uncommitted on the branch. Commit them so the build tasks start from a clean working tree:
   ```bash
   git add docs/superpowers/specs/2026-05-22-bedroom-precool-design.md \
           docs/superpowers/research/2026-05-22-bedroom-precool-research-validation.md \
           docs/superpowers/plans/2026-05-22-bedroom-precool.md
   git commit -m "docs(bedroom-precool): research-validation + Stack A implementation plan"
   ```
3. **No live-API / auth / env setup** is needed for the build — every build task is local file edits + `python3` YAML validation.

**Codex sandbox caveat:** the `/codex:rescue` wrapper runs with a read-only `.git` — Codex can apply the file edits but cannot `git commit`. If the plan is handed to Codex, the per-task commits are applied by operator-Claude after Codex returns. If executed by the `blueprint-architect` agent or inline by Claude, commits run normally per task.

---

## Stack A Routing

- **Executor balance:** 11 of 11 file-edit tasks routed to Codex (100%) — no balance warning. Routing is honest: every build task applies verbatim YAML/markdown from the plan and validates deterministically with `python3`. The one Claude task (Task 13) is mental-simulation + user-facing HA steps — genuine judgment/interaction work.
- **Shell invariants block:** not applicable — no task creates or edits a shell script. The `python3` and `git` commands are inline, not committed shell files.
- **PASS-count gate:** adapted — no task runs a multi-test suite, so there is no `PASS=N FAIL=M` line. The per-task `python3` YAML-syntax check and the Task 11 structural-assertion script are the equivalent gates; the executor MUST report each one's literal terminal output (`VALID` / `STRUCTURAL VALIDATION PASSED`) so a mid-stream reader can confirm the gate ran.

---

## Task 1: Write the requirements doc

**Executor:** Codex
**Rationale:** Creates a markdown file with content given verbatim in the task — no judgment, no live API.

**Files:**
- Create: `requirements_bedroom_precool.md`

- [ ] **Step 1: Create `requirements_bedroom_precool.md`**

````markdown
# Bedroom Sleep Pre-Cool — Requirements

## Overview

Predictive pre-cooling of bedrooms via a single LG air conditioner located in
the upstairs hall. The blueprint brings the warmest bedroom to an ideal sleep
temperature (default 19 °C) by a fixed bedtime (default 19:30), then holds the
room quietly overnight while issuing the absolute minimum number of commands.

LG ACs emit a confirmation beep on every command received over ThinQ — a
firmware tone that cannot be silenced in software. The blueprint therefore
treats AC commands as a scarce resource after bedtime: it adjusts freely
*before* bedtime, locks a maintaining setpoint *at* bedtime, permits at most
one corrective command at a deep-night checkpoint (~01:00), and turns the AC
off at wake (~07:15).

The AC is not in the bedrooms — it cools the hall and cold air migrates through
open doors. Cooling is therefore indirect, laggy, and load-dependent, so the
turn-on time is *predicted* from the indoor gap, an hourly weather forecast,
and solar gain, with a self-learning bias that auto-corrects from each night's
observed outcome.

## Hardware Requirements

- **AC Unit:** One LG air conditioner in the hall, connected via the LG ThinQ
  integration (exposes a `climate` entity).
- **Bedroom Temperature Sensors:** One or more in-room sensors (e.g., Aqara) —
  these are the control target.
- **Bedroom Humidity Sensors (optional):** Only needed if dry mode is enabled.
- **Outdoor Temperature Sensor:** Any sensor with `device_class: temperature`.
- **Weather Entity:** Must provide an **hourly** forecast — Met.no (HA default,
  keyless) or Open-Meteo. **Buienradar provides only a daily forecast and will
  not work as the weather entity** (it may still serve the outdoor sensor).
- **AC Sound Switch (optional):** The `switch` entity for the AC beep, if
  exposed — kept muted.

## Home Assistant Requirements

- **Home Assistant Core 2025.7 or newer** — required for the LG ThinQ
  `set_temperature` fix (PR #147008).
- **input_number helper:** Persists the self-learned lead-time bias across
  restarts. Create one via Settings -> Devices & Services -> Helpers ->
  Number (range roughly -60 to 120, step 1).
- **input_boolean helper (optional):** For the vacation toggle.

## Daily State Machine

The blueprint is stateless: a 1-minute loop derives which phase `now` is in and
acts. Phase boundaries span midnight (bedtime -> wake is an overnight window).

| Phase | Window | AC behaviour | Beeps |
|---|---|---|---|
| DAY-OFF | wake -> turn_on | Ensure AC off; recompute turn-on each tick | 0 (1 at wake) |
| PRECOOL | turn_on -> bedtime − 1 min | Cooling; closed-loop DRIVE / HOLD | many (allowed) |
| BEDTIME-LOCK | bedtime − 1 min -> bedtime | One locking command + auto-learn write | 0–1 |
| NIGHT-HOLD | bedtime -> deep-night check | Holds; blueprint issues nothing | 0 |
| DEEP-NIGHT-CHECK | deep-night check -> +10 min | At most one corrective command | 0 or 1 |
| DEEP-HOLD | deep-night check + 10 min -> wake | Holds; blueprint issues nothing | 0 |

Beep budget after bedtime: 0–2. Turn-on is a one-way latch — once PRECOOL
begins it never reverts to DAY-OFF that day. Cool-day nights (the AC was never
started) are fully no-op.

## Prediction Model

```
warmest_bedroom = aggregate(bedroom sensors, strategy)        # default: max
delta_in        = max(0, warmest_bedroom − ideal_temp)
forecast_max    = max forecast temp over [now -> bedtime]     # fallback: outdoor sensor
delta_out       = max(0, max(forecast_max, outdoor_now) − ideal_temp)
solar_load      = 0..1 from sun elevation + azimuth
lead_bias       = self-learned correction (minutes)

lead = clamp(
         base_minutes
         + k_indoor          * delta_in
         + k_outdoor         * delta_out
         + solar_max_minutes * solar_load
         + safety_margin_minutes
         + lead_bias,
         0, lead_cap_minutes)

turn_on = bedtime − lead          # enter PRECOOL when now >= turn_on
```

The AC starts only when `cooling_needed` is true:
`warmest_bedroom > ideal_temp  OR  forecast_max > skip_threshold`.

## Auto-Learn

The blueprint self-learns one scalar — the lead-time bias — persisted in an
`input_number` helper:

```
# at BEDTIME-LOCK, only if the AC was running this night:
bedtime_error = warmest_bedroom − ideal_temp
new_bias      = clamp(lead_bias + learn_gain * bedtime_error * k_indoor, -60, 120)
```

Room too warm at bedtime -> bias rises (start earlier tomorrow); overcooled ->
bias falls. The helper write is beep-free (it is an `input_number`, not the
AC). Converges over ~3–6 nights. Cool-day no-ops are skipped.

A single glitchy-but-valid bedroom reading at the bedtime lock skews that one
night's auto-learn write, but the `[-60, 120]` clamp bounds how far it can move
the bias and subsequent nights wash the outlier out.

## Functional Requirements

### Climate Control
1. 6-phase stateless daily state machine, phase derived from `now`.
2. Predictive turn-on from a transparent linear lead-time formula.
3. Closed-loop pre-cool on the warmest bedroom (DRIVE / HOLD sub-states).
4. Bedtime lock — one deliberate command sets a maintaining setpoint.
5. One optional corrective command at the deep-night checkpoint.
6. AC off at wake.

### Beep Budget
1. Unlimited commands before bedtime; 0–2 after bedtime.
2. Every climate service call guarded by a current-vs-desired comparison.
3. NIGHT-HOLD and DEEP-HOLD issue zero service calls.

### Mode Selection
1. `cool` is the proven default path.
2. Optional `dry` mode (default off) — only chosen while beeps are free, and
   only when humid with a small temperature gap.

### Overrides
1. Vacation toggle: forces the AC off and stands the blueprint down.
2. Sound mute: keeps the AC beep switch off.

### Safety
1. Bedroom sensor failure: holds state, fires a persistent notification.
2. AC entity unavailable: skips the tick, retries next minute.
3. Forecast unavailable: falls back to the daily forecast, then to the live
   outdoor sensor.
4. `ideal_temp` is bounded >= 16 °C (child-safety floor); a bedroom reading
   below 16 °C raises an overcooling-fault notification.
5. Every setpoint clamped to the AC's discovered `min_temp` / `max_temp`.
6. Configuration validation: blocks operation on an invalid setup.

## Testing & Debugging

Manual "Run" in HA produces a persistent notification dumping all computed
state: phase, warmest/coldest bedroom, ΔT terms, solar load, forecast_max,
lead_bias, lead, turn_on, cooling_needed, AC mode/setpoint/fan, the discovered
AC limits, and the resolved setpoints. Set `bedtime` to a few minutes ahead to
watch PRECOOL -> BEDTIME-LOCK -> NIGHT-HOLD live.

## Out of Scope (V2)

- Auto-learned `hall_offset` (V1 auto-learns the lead-time bias only).
- Per-day or weekday/weekend `bedtime` / `wake_time`.
- Mobile push notifications.
- Window/door contact sensors to detect unreachable rooms.
- ESPHome silent-mode controller (makes the beep budget a non-constraint).
````

- [ ] **Step 2: Commit**

```bash
git add requirements_bedroom_precool.md
git commit -m "docs(bedroom-precool): add requirements document"
```

---

## Task 2: Scaffold the blueprint — metadata + Group 1 & 2 inputs

**Executor:** Codex
**Rationale:** Creates the YAML file with verbatim content plus a deterministic `python3` syntax check.

**Files:**
- Create: `bedroom_precool.yaml`

Create the blueprint file with the metadata block and the first two input groups: Group 1 (Devices & Sensors, 8 inputs) and Group 2 (Target Temperatures, 7 inputs). The `input:` mapping is left open — Task 3 appends Groups 3–6.

- [ ] **Step 1: Create `bedroom_precool.yaml` with metadata + Group 1 & 2 inputs**

```yaml
blueprint:
  name: "Bedroom Sleep Pre-Cool v1.0.0"
  description: >
    **Version: 1.0.0**

    Predictive pre-cooling of bedrooms via a single hall LG air conditioner.
    Reaches an ideal sleep temperature by a fixed bedtime, then holds the room
    quietly overnight within a strict beep budget, with a self-learning
    lead-time prediction.

    LG ACs beep on every command sent over ThinQ — a firmware tone that cannot
    be silenced in software. This blueprint therefore treats AC commands as a
    scarce resource after bedtime: it adjusts freely *before* bedtime, locks a
    maintaining setpoint *at* bedtime, permits at most one corrective command at
    a deep-night checkpoint, and turns the AC off at wake.

    The AC is in the hall, not the bedrooms — cold air migrates through open
    doors. Cooling is therefore indirect and laggy, so the turn-on time is
    *predicted* from indoor gap, hourly weather forecast, and solar gain, with a
    self-learning bias that auto-corrects from each night's observed outcome.

    **Features:**
    - 6-phase stateless daily state machine (DAY-OFF, PRECOOL, BEDTIME-LOCK,
      NIGHT-HOLD, DEEP-NIGHT-CHECK, DEEP-HOLD)
    - Predictive turn-on: transparent linear lead-time formula
      (indoor gap + forecast outdoor + solar) recomputed every minute
    - Self-learning lead-time bias persisted in an input_number helper
    - Closed-loop pre-cool on the warmest bedroom (DRIVE / HOLD sub-states)
    - Strict beep budget: 0-2 commands after bedtime
    - Opt-in humidity-aware dry mode (default off — cool is the proven path)
    - Idempotent service calls — a stray command is a stray beep
    - Vacation toggle, manual-run debug notification

    **Requirements:**
    - Home Assistant Core 2025.7+ (LG ThinQ set_temperature fix, PR #147008)
    - One LG AC connected via the LG ThinQ integration (a `climate` entity)
    - Bedroom temperature sensors (e.g., Aqara) — the control target
    - An outdoor temperature sensor
    - A weather entity that provides an HOURLY forecast — Met.no or Open-Meteo
      (Buienradar has no hourly forecast and will not work)
    - An input_number helper to persist the self-learned lead-time bias

  domain: automation
  input:
    # =======================================================
    # GROUP 1 — DEVICES & SENSORS
    # =======================================================
    ac_climate:
      name: LG AC Climate Entity
      description: The climate entity for the hall LG air conditioner (LG ThinQ integration).
      selector:
        entity:
          domain: climate
    bedroom_temp_sensors:
      name: Bedroom Temperature Sensors
      description: >
        One or more in-room temperature sensors (e.g., Aqara). These are the
        control target — the blueprint cools until the warmest bedroom reaches
        the ideal temperature.
      selector:
        entity:
          domain: sensor
          device_class: temperature
          multiple: true
    bedroom_humidity_sensors:
      name: Bedroom Humidity Sensors (Optional)
      description: >
        In-room humidity sensors. Only used when Enable Dry Mode is on; drives
        the cool-vs-dry choice. Leave empty if not using dry mode.
      default: []
      selector:
        entity:
          domain: sensor
          device_class: humidity
          multiple: true
    outdoor_temp_sensor:
      name: Outdoor Temperature Sensor
      description: An outdoor temperature sensor entity — heat-load term and forecast fallback.
      selector:
        entity:
          domain: sensor
          device_class: temperature
    weather_entity:
      name: Weather Entity (hourly forecast)
      description: >
        A weather entity that supports an HOURLY forecast — Met.no (HA default,
        keyless) or Open-Meteo. Buienradar provides only a daily forecast and
        must NOT be used here. The forecast anticipates the evening heat load.
      selector:
        entity:
          domain: weather
    sun_entity:
      name: Sun Entity
      description: The built-in sun entity — provides the solar-gain term. Leave as the default.
      default: sun.sun
      selector:
        entity:
          domain: sun
    lead_bias_helper:
      name: Lead-Time Bias Helper (input_number)
      description: >
        An input_number helper the blueprint uses to persist its self-learned
        lead-time correction (minutes) across restarts. Create one via
        Settings -> Devices & Services -> Helpers -> Number, range roughly
        -60 to 120, step 1. Required when Enable Auto-Learn is on.
      default: []
      selector:
        entity:
          domain: input_number
          multiple: true
    ac_sound_switch:
      name: AC Sound Switch (Optional)
      description: >
        The switch entity for the LG AC beep sound, if exposed. The blueprint
        keeps it muted. Leave empty if not available.
      default: []
      selector:
        entity:
          domain: switch
          multiple: true

    # =======================================================
    # GROUP 2 — TARGET TEMPERATURES
    # =======================================================
    ideal_temp:
      name: Ideal Sleep Temperature (°C)
      description: >
        The target temperature for the warmest bedroom by bedtime. 19 °C is
        within the recommended child sleep range (16-20 °C, The Lullaby Trust).
        The minimum is a 16 °C child-safety floor.
      default: 19.0
      selector:
        number:
          min: 16.0
          max: 25.0
          step: 0.5
          unit_of_measurement: "°C"
    hall_offset:
      name: Hall Cooling Offset (°C)
      description: >
        How much colder the hall AC must hold than the bedroom ideal, to push
        cold air through the doorway. Indirect room-to-room cooling is
        thermally weak, so this is typically 3-6 °C. Tune it using the overnight
        drift reported in the debug notification.
      default: 3.0
      selector:
        number:
          min: 0.0
          max: 10.0
          step: 0.5
          unit_of_measurement: "°C"
    drive_setpoint:
      name: Drive Setpoint (°C)
      description: >
        The aggressive hall setpoint used while actively driving the bedrooms
        down (DRIVE sub-state). Set this to the AC's minimum for the fastest
        pre-cool — it is clamped to the AC's real min_temp at runtime.
      default: 16.0
      selector:
        number:
          min: 14.0
          max: 22.0
          step: 0.5
          unit_of_measurement: "°C"
    tolerance:
      name: Drift Tolerance (°C)
      description: >
        The dead band around the ideal temperature for the deep-night check
        and the cool-vs-dry decision. A drift larger than this triggers the
        single deep-night correction.
      default: 1.5
      selector:
        number:
          min: 0.5
          max: 4.0
          step: 0.5
          unit_of_measurement: "°C"
    correction_step:
      name: Deep-Night Correction Step (°C)
      description: How far to nudge the hall setpoint at the single deep-night corrective command.
      default: 1.5
      selector:
        number:
          min: 0.5
          max: 4.0
          step: 0.5
          unit_of_measurement: "°C"
    skip_threshold:
      name: Cool-Day Skip Threshold (°C)
      description: >
        If the forecast peak stays below this and the bedrooms are already at
        or below ideal, the AC never starts — the mild-day skip.
      default: 22.0
      selector:
        number:
          min: 16.0
          max: 28.0
          step: 0.5
          unit_of_measurement: "°C"
    humidity_threshold:
      name: Humidity Threshold (%)
      description: >
        Above this room humidity, dry mode is preferred over cool — only when
        Enable Dry Mode is on and the temperature gap is small.
      default: 65
      selector:
        number:
          min: 40
          max: 80
          step: 1
          unit_of_measurement: "%"

# Remaining input groups (3-6), mode, variables, triggers and action
# are added in later tasks.
```

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.SafeLoader.add_multi_constructor('!', lambda l,s,n: None); yaml.safe_load(open('bedroom_precool.yaml'))" && echo VALID
```

Expected: `VALID`.

- [ ] **Step 3: Commit**

```bash
git add bedroom_precool.yaml
git commit -m "feat(bedroom-precool): scaffold blueprint metadata and device/temperature inputs"
```

---

## Task 3: Remaining inputs — Groups 3–6

**Executor:** Codex
**Rationale:** Mechanical YAML append of verbatim content plus a deterministic input-count assertion.

**Files:**
- Modify: `bedroom_precool.yaml`

Append the remaining four input groups under the open `input:` mapping: Group 3 (Schedule, 3 inputs), Group 4 (Prediction Tuning, 8 inputs), Group 5 (Behaviour, 3 inputs), Group 6 (Global Controls, 2 inputs). Total inputs after this task: **32**.

- [ ] **Step 1: Replace the trailing scaffold comment with Groups 3–6**

Replace this comment block at the end of the file:

```yaml
# Remaining input groups (3-6), mode, variables, triggers and action
# are added in later tasks.
```

with:

```yaml
    # =======================================================
    # GROUP 3 — SCHEDULE
    # =======================================================
    bedtime:
      name: Bedtime
      description: The time the warmest bedroom should be at the ideal temperature.
      default: "19:30:00"
      selector:
        time: {}
    wake_time:
      name: Wake Time
      description: The time the AC is turned off in the morning.
      default: "07:15:00"
      selector:
        time: {}
    deep_night_check:
      name: Deep-Night Check Time
      description: >
        The single overnight checkpoint (e.g., 01:00). If the warmest bedroom
        has drifted outside ideal +/- tolerance, one corrective command fires
        within a fixed 10-minute window after this time.
      default: "01:00:00"
      selector:
        time: {}

    # =======================================================
    # GROUP 4 — PREDICTION TUNING
    # =======================================================
    base_minutes:
      name: Base Lead Minutes
      description: The fixed baseline lead time before any temperature or solar terms are added.
      default: 20
      selector:
        number:
          min: 0
          max: 120
          step: 1
          unit_of_measurement: "min"
    k_indoor:
      name: Indoor Coefficient (min per °C)
      description: >
        Lead minutes added per °C the warmest bedroom is above ideal. This is
        the dominant term — the indoor gap is what the AC must actually close.
      default: 15
      selector:
        number:
          min: 0
          max: 60
          step: 1
          unit_of_measurement: "min/°C"
    k_outdoor:
      name: Outdoor Coefficient (min per °C)
      description: >
        Lead minutes added per °C the outdoor peak is above ideal. Deliberately
        small — outdoor heat is a secondary leak correction, not a co-equal term.
      default: 1.0
      selector:
        number:
          min: 0
          max: 15
          step: 0.5
          unit_of_measurement: "min/°C"
    solar_max_minutes:
      name: Solar Maximum Minutes
      description: The maximum lead contribution from solar gain, at peak radiant load.
      default: 45
      selector:
        number:
          min: 0
          max: 120
          step: 1
          unit_of_measurement: "min"
    safety_margin_minutes:
      name: Safety Margin Minutes
      description: >
        A fixed early bias. Starting early is cheap; missing bedtime is not —
        so the estimate is biased early.
      default: 25
      selector:
        number:
          min: 0
          max: 60
          step: 1
          unit_of_measurement: "min"
    lead_cap_minutes:
      name: Lead Cap Minutes
      description: The hard upper bound on total lead time — the earliest the AC can ever start before bedtime.
      default: 240
      selector:
        number:
          min: 60
          max: 360
          step: 10
          unit_of_measurement: "min"
    solar_afternoon_only:
      name: Solar — Afternoon Azimuths Only
      description: >
        When on, solar gain only contributes for post-solar-noon sun positions
        (azimuth roughly 180-300°), capturing the low evening sun on west-facing
        bedrooms while ignoring the morning sun.
      default: true
      selector:
        boolean: {}
    learn_gain:
      name: Auto-Learn Gain
      description: >
        How aggressively the lead-time bias self-corrects each night. Higher
        converges faster but overshoots more. 0.4 converges over ~3-6 nights.
      default: 0.4
      selector:
        number:
          min: 0
          max: 1
          step: 0.05

    # =======================================================
    # GROUP 5 — BEHAVIOUR
    # =======================================================
    sensor_strategy:
      name: Bedroom Sensor Strategy
      description: >
        How to aggregate multiple bedroom sensors. 'max' (the warmest room)
        guarantees every room reaches ideal; 'average' is gentler but can leave
        the warmest room above ideal.
      default: "max"
      selector:
        select:
          options:
            - label: "Warmest room (max)"
              value: "max"
            - label: "Average of rooms"
              value: "average"
    enable_fan_control:
      name: Enable Fan Control
      description: When on, the blueprint sets a high fan while driving and a normal fan while holding.
      default: true
      selector:
        boolean: {}
    enable_dry_mode:
      name: Enable Dry Mode
      description: >
        When on, the blueprint may pick dry mode over cool when the room is
        humid and the temperature gap is small. Default OFF — LG dry-mode
        target-temperature behaviour is model-dependent; enable only after
        verifying on the actual unit.
      default: false
      selector:
        boolean: {}
    enable_auto_learn:
      name: Enable Auto-Learn
      description: >
        When on, the blueprint reads and updates the lead-time bias helper,
        self-correcting the prediction from each cooling night's outcome.
      default: true
      selector:
        boolean: {}

    # =======================================================
    # GROUP 6 — GLOBAL CONTROLS
    # =======================================================
    vacation_toggle:
      name: Vacation Toggle (Optional)
      description: "Optional input_boolean. When ON, the AC is forced off and the blueprint stands down."
      default: []
      selector:
        entity:
          domain: input_boolean
          multiple: true
    enable_notifications:
      name: Enable Persistent Notifications
      description: When on, fault and status persistent notifications are created.
      default: true
      selector:
        boolean: {}
```

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.SafeLoader.add_multi_constructor('!', lambda l,s,n: None); yaml.safe_load(open('bedroom_precool.yaml'))" && echo VALID
```

Expected: `VALID`.

- [ ] **Step 3: Confirm the input count is 32**

```bash
python3 -c "import yaml; yaml.SafeLoader.add_multi_constructor('!', lambda l,s,n: None); bp=yaml.safe_load(open('bedroom_precool.yaml')); n=len(bp['blueprint']['input']); assert n==32, f'expected 32 inputs, got {n}'; print('inputs OK:', n)"
```

Expected: `inputs OK: 32`.

- [ ] **Step 4: Commit**

```bash
git add bedroom_precool.yaml
git commit -m "feat(bedroom-precool): add schedule, prediction, behaviour and global inputs"
```

---

## Task 4: `mode` / `max_exceeded`, top-level `!input` variables, and triggers

**Executor:** Codex
**Rationale:** Mechanical YAML append of verbatim content plus a deterministic `python3` syntax check.

**Files:**
- Modify: `bedroom_precool.yaml`

Append `mode` / `max_exceeded`, the top-level `variables:` block (one `!input` pass-through line per input — matches `bathroom_heating_rack.yaml` and `lg_ac_climate.yaml`), and the three triggers. `trigger:` ends with `action: []` as a placeholder that Task 5 replaces.

- [ ] **Step 1: Append `mode`, `variables:`, `trigger:`, and the `action: []` placeholder**

Append to the end of the file (after the `enable_notifications` input):

```yaml

mode: restart
max_exceeded: silent

# =============================================
# TOP-LEVEL VARIABLES — !input pass-through
# (matches bathroom_heating_rack / lg_ac_climate; guarantees every
#  !input resolves at automation-creation time and is available
#  everywhere below — including the action block)
# =============================================
variables:
  # --- Group 1: devices & sensors ---
  ac_climate: !input ac_climate
  bedroom_temp_sensors: !input bedroom_temp_sensors
  bedroom_humidity_sensors: !input bedroom_humidity_sensors
  outdoor_temp_sensor: !input outdoor_temp_sensor
  weather_entity: !input weather_entity
  sun_entity: !input sun_entity
  lead_bias_helper: !input lead_bias_helper
  ac_sound_switch: !input ac_sound_switch
  # --- Group 2: target temperatures ---
  ideal_temp: !input ideal_temp
  hall_offset: !input hall_offset
  drive_setpoint: !input drive_setpoint
  tolerance: !input tolerance
  correction_step: !input correction_step
  skip_threshold: !input skip_threshold
  humidity_threshold: !input humidity_threshold
  # --- Group 3: schedule ---
  bedtime: !input bedtime
  wake_time: !input wake_time
  deep_night_check: !input deep_night_check
  # --- Group 4: prediction tuning ---
  base_minutes: !input base_minutes
  k_indoor: !input k_indoor
  k_outdoor: !input k_outdoor
  solar_max_minutes: !input solar_max_minutes
  safety_margin_minutes: !input safety_margin_minutes
  lead_cap_minutes: !input lead_cap_minutes
  solar_afternoon_only: !input solar_afternoon_only
  learn_gain: !input learn_gain
  # --- Group 5: behaviour ---
  sensor_strategy: !input sensor_strategy
  enable_fan_control: !input enable_fan_control
  enable_dry_mode: !input enable_dry_mode
  enable_auto_learn: !input enable_auto_learn
  # --- Group 6: global controls ---
  vacation_toggle: !input vacation_toggle
  enable_notifications: !input enable_notifications

trigger:
  # T1: Periodic 1-minute tick — phase derivation, prediction, transitions
  - platform: time_pattern
    minutes: "/1"
    id: periodic
  # T2: Vacation toggle state change — instant disable / re-enable
  - platform: state
    entity_id: !input vacation_toggle
    id: vacation_change
  # T3: HA restart — reconcile phase after a restart
  - platform: homeassistant
    event: start
    id: ha_start

action: []
```

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.SafeLoader.add_multi_constructor('!', lambda l,s,n: None); yaml.safe_load(open('bedroom_precool.yaml'))" && echo VALID
```

Expected: `VALID`.

- [ ] **Step 3: Commit**

```bash
git add bedroom_precool.yaml
git commit -m "feat(bedroom-precool): add mode, !input variables and 3 triggers"
```

---

## Task 5: Action — mute sound pre-step + live-state variables

**Executor:** Codex
**Rationale:** Replaces the `action: []` placeholder with verbatim YAML plus a deterministic `python3` syntax check.

**Files:**
- Modify: `bedroom_precool.yaml`

Replace the `action: []` placeholder with the start of the action pipeline: STEP 1 (standalone mute-sound `choose`) and STEP 2a (the live-state variables block). All runtime variables are computed *inside* `action:` so HA produces a trace entry on any template failure.

- [ ] **Step 1: Replace `action: []` with STEP 1 + STEP 2a**

Replace the single line `action: []` with:

```yaml
action:
  # =============================================
  # STEP 1: MUTE SOUND SWITCH (standalone pre-step)
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: >-
              {{ ac_sound_switch not in [[], none, ''] and
                 expand(ac_sound_switch) | selectattr('state', 'eq', 'on')
                 | list | count > 0 }}
        sequence:
          - service: switch.turn_off
            target:
              entity_id: "{{ ac_sound_switch }}"

  # =============================================
  # STEP 2a: LIVE-STATE VARIABLES
  # All variables computed inside action: so HA generates a trace
  # entry on any template failure.
  # =============================================
  - variables:
      now_dt: "{{ now() }}"
      # True only on a real trigger (periodic / vacation_change / ha_start);
      # a manual "Run" has no trigger.id. STEP 6's phase dispatch is gated on
      # this so a manual Run is debug-inspect-only — it never actuates the AC
      # nor double-applies the BEDTIME_LOCK auto-learn write. Matches the
      # STEP 8 debug gate's `trigger.id | default('manual')` logic.
      is_real_trigger: "{{ trigger.id is defined }}"
      # --- Bedroom temperature aggregation (skip unavailable sensors) ---
      bedroom_valid_temps: >-
        {% set ns = namespace(vals=[]) %}
        {% for s in bedroom_temp_sensors %}
          {% set v = states(s) %}
          {% if v not in ['unavailable', 'unknown', 'none', none]
                and v | float(none) is not none %}
            {% set ns.vals = ns.vals + [v | float] %}
          {% endif %}
        {% endfor %}
        {{ ns.vals }}
      bedroom_sensors_ok: "{{ bedroom_valid_temps | length > 0 }}"
      warmest_bedroom: >-
        {% if bedroom_valid_temps | length == 0 %}
          {{ ideal_temp | float }}
        {% elif sensor_strategy == 'average' %}
          {{ ((bedroom_valid_temps | sum) / (bedroom_valid_temps | length)) | round(2) }}
        {% else %}
          {{ bedroom_valid_temps | max }}
        {% endif %}
      coldest_bedroom: >-
        {% if bedroom_valid_temps | length == 0 %}
          {{ ideal_temp | float }}
        {% else %}
          {{ bedroom_valid_temps | min }}
        {% endif %}
      # --- Bedroom humidity (only meaningful when dry mode enabled) ---
      bedroom_valid_humidity: >-
        {% set ns = namespace(vals=[]) %}
        {% for s in bedroom_humidity_sensors %}
          {% set v = states(s) %}
          {% if v not in ['unavailable', 'unknown', 'none', none]
                and v | float(none) is not none %}
            {% set ns.vals = ns.vals + [v | float] %}
          {% endif %}
        {% endfor %}
        {{ ns.vals }}
      room_humidity: >-
        {% if bedroom_valid_humidity | length == 0 %}
          0
        {% else %}
          {{ bedroom_valid_humidity | max }}
        {% endif %}
      # --- Outdoor live reading ---
      outdoor_now_raw: "{{ states(outdoor_temp_sensor) }}"
      outdoor_now_ok: >-
        {{ outdoor_now_raw not in ['unavailable', 'unknown', 'none', none]
           and outdoor_now_raw | float(none) is not none }}
      outdoor_now: "{{ outdoor_now_raw | float(ideal_temp | float) }}"
      # --- AC live state ---
      current_hvac_mode: "{{ states(ac_climate) }}"
      ac_unavailable: "{{ current_hvac_mode in ['unavailable', 'unknown'] }}"
      ac_is_running: "{{ current_hvac_mode not in ['off', 'unavailable', 'unknown'] }}"
      # LG returns null setpoints in some non-cool modes — guard the read.
      current_setpoint_raw: "{{ state_attr(ac_climate, 'temperature') }}"
      current_setpoint_known: "{{ current_setpoint_raw not in [none, 'none', 'unknown', 'unavailable'] }}"
      current_setpoint: "{{ current_setpoint_raw | float(ideal_temp | float) }}"
      current_fan: "{{ state_attr(ac_climate, 'fan_modes') and state_attr(ac_climate, 'fan_mode') or 'unknown' }}"
      # --- AC capability discovery (never hard-code) ---
      ac_min_temp: "{{ state_attr(ac_climate, 'min_temp') | float(16) }}"
      ac_max_temp: "{{ state_attr(ac_climate, 'max_temp') | float(30) }}"
      ac_fan_modes: "{{ state_attr(ac_climate, 'fan_modes') | default([], true) }}"
      ac_hvac_modes: "{{ state_attr(ac_climate, 'hvac_modes') | default([], true) }}"
      # --- Vacation ---
      vacation_active: >-
        {% if vacation_toggle is iterable and vacation_toggle | length > 0 %}
          {{ expand(vacation_toggle) | selectattr('state', 'eq', 'on')
             | list | length > 0 }}
        {% else %}
          false
        {% endif %}
```

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.SafeLoader.add_multi_constructor('!', lambda l,s,n: None); yaml.safe_load(open('bedroom_precool.yaml'))" && echo VALID
```

Expected: `VALID`.

- [ ] **Step 3: Commit**

```bash
git add bedroom_precool.yaml
git commit -m "feat(bedroom-precool): add mute-sound pre-step and live-state variables"
```

---

## Task 6: Action — forecast fetch + prediction / phase variables

**Executor:** Codex
**Rationale:** Mechanical YAML append of verbatim content plus a deterministic `python3` syntax check.

**Files:**
- Modify: `bedroom_precool.yaml`

Append STEP 2b (the periodic `weather.get_forecasts` fetch + `forecast_max` derivation) and STEP 2c (solar, lead-time formula, auto-learn bias read, phase derivation, sub-state, setpoints, mode, fan-mode discovery). `weather.get_forecasts` is the **plural** current action — the singular `weather.get_forecast` is deprecated. It is called with a `response_variable` and only near a 15-minute boundary, to limit load on the weather integration.

- [ ] **Step 1: Append STEP 2b + STEP 2c after the STEP 2a `variables:` block**

After the `variables:` block ending with `vacation_active:`, append:

```yaml

  # =============================================
  # STEP 2b: FORECAST FETCH (periodic, ~every 15 min during DAY-OFF)
  # weather.get_forecasts is the PLURAL current action — the singular
  # weather.get_forecast was deprecated. Fetched into a response
  # variable, then forecast_max is templated from it.
  # =============================================
  - variables:
      # Fetch only near a 15-minute boundary (minute mod 15 == 0) AND only
      # during the daytime wake -> bedtime window — the forecast result is
      # consumed by DAY_OFF alone, so fetching it overnight is pure waste.
      # Between fetches the live outdoor sensor carries the prediction.
      forecast_fetch_due: >-
        {{ (now().minute | int) % 15 == 0
           and now().strftime('%H:%M:%S') >= wake_time
           and now().strftime('%H:%M:%S') < bedtime }}
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ forecast_fetch_due }}"
        sequence:
          # continue_on_error: a weather-entity failure must not abort the
          # whole action run — the forecast_daily_fallback -> outdoor_now
          # chain below handles a missing/empty response.
          - service: weather.get_forecasts
            continue_on_error: true
            target:
              entity_id: "{{ weather_entity }}"
            data:
              type: hourly
            response_variable: hourly_forecast_resp
  - variables:
      # Source the forecast list straight from the service response_variable —
      # a response_variable has well-defined run scope, so no choose-branch
      # variable leaks across the boundary. On a non-fetch tick the fetch
      # branch never ran, so hourly_forecast_resp is simply undefined; the
      # `is defined` guard then yields the empty-list path. Filter forecast
      # entries to the window now -> bedtime, take the max temperature.
      forecast_list_safe: >-
        {{ hourly_forecast_resp[weather_entity].forecast
           if hourly_forecast_resp is defined
              and hourly_forecast_resp is mapping
              and weather_entity in hourly_forecast_resp
              and hourly_forecast_resp[weather_entity].forecast is defined
           else [] }}
      bedtime_dt: >-
        {% set bt = today_at(bedtime) %}
        {{ bt if bt >= now() else bt + timedelta(days=1) }}
      forecast_window_temps: >-
        {% set ns = namespace(vals=[]) %}
        {% for f in forecast_list_safe %}
          {% set ts = f.datetime | default(none) %}
          {% set tp = f.temperature | default(none) %}
          {% if ts is not none and tp is not none %}
            {% set fdt = as_datetime(ts) %}
            {% if fdt is not none and fdt >= now() and fdt <= bedtime_dt %}
              {% set ns.vals = ns.vals + [tp | float] %}
            {% endif %}
          {% endif %}
        {% endfor %}
        {{ ns.vals }}
      forecast_daily_fallback: >-
        {% set d = state_attr(weather_entity, 'forecast') %}
        {% if d is iterable and d is not string and d | length > 0 %}
          {{ d[0].temperature | float(outdoor_now | float) }}
        {% else %}
          {{ outdoor_now | float }}
        {% endif %}
      forecast_max: >-
        {% if forecast_window_temps | length > 0 %}
          {{ forecast_window_temps | max }}
        {% else %}
          {{ [forecast_daily_fallback | float, outdoor_now | float] | max }}
        {% endif %}

  # =============================================
  # STEP 2c: PREDICTION & PHASE VARIABLES
  # =============================================
  - variables:
      # --- Solar-gain factor (0..1 from sun elevation + azimuth) ---
      sun_elevation: "{{ state_attr(sun_entity, 'elevation') | float(0) }}"
      sun_azimuth: "{{ state_attr(sun_entity, 'azimuth') | float(0) }}"
      solar_elevation_factor: >-
        {{ [1.0, [0.0, (sun_elevation | float) / 35.0] | max] | min }}
      solar_azimuth_ok: >-
        {% if not solar_afternoon_only %}
          true
        {% else %}
          {{ sun_azimuth | float >= 180 and sun_azimuth | float <= 300 }}
        {% endif %}
      solar_load: >-
        {% if sun_elevation | float <= 0 or not solar_azimuth_ok %}
          0
        {% else %}
          {{ solar_elevation_factor | float | round(3) }}
        {% endif %}
      # --- Lead-time inputs ---
      delta_in: "{{ [0, warmest_bedroom | float - ideal_temp | float] | max }}"
      outdoor_for_lead: "{{ [forecast_max | float, outdoor_now | float] | max }}"
      delta_out: "{{ [0, outdoor_for_lead | float - ideal_temp | float] | max }}"
      # --- Auto-learn bias: read the helper every tick when enabled ---
      lead_bias_entity: >-
        {% if lead_bias_helper is iterable and lead_bias_helper is not string
              and lead_bias_helper | length > 0 %}
          {{ lead_bias_helper[0] }}
        {% else %}
          {{ '' }}
        {% endif %}
      lead_bias_configured: "{{ lead_bias_entity != '' }}"
      lead_bias: >-
        {% if enable_auto_learn and lead_bias_configured %}
          {{ states(lead_bias_entity) | float(0) }}
        {% else %}
          0
        {% endif %}
      # --- Lead-time formula (transparent linear blend), then clamp ---
      lead_raw: >-
        {{ (base_minutes | float)
           + (k_indoor | float) * (delta_in | float)
           + (k_outdoor | float) * (delta_out | float)
           + (solar_max_minutes | float) * (solar_load | float)
           + (safety_margin_minutes | float)
           + (lead_bias | float) }}
      lead: "{{ [[lead_raw | float, 0] | max, lead_cap_minutes | float] | min | round(0) | int }}"
      # --- Cool-day skip gate (consulted in DAY-OFF only) ---
      cooling_needed: >-
        {{ warmest_bedroom | float > ideal_temp | float
           or forecast_max | float > skip_threshold | float }}
      # --- Schedule boundaries as time-of-day strings (HH:MM:SS).
      # Phase derivation compares time-of-day so the overnight window
      # (bedtime -> wake, spanning midnight) is handled without any
      # date arithmetic. turn_on is the only moving boundary; it is
      # carried as a same-day datetime purely for the debug dump. ---
      now_tod: "{{ now().strftime('%H:%M:%S') }}"
      wake_tod: "{{ wake_time }}"
      bedtime_tod: "{{ bedtime }}"
      lock_tod: >-
        {{ (today_at(bedtime) - timedelta(minutes=1)).strftime('%H:%M:%S') }}
      deep_tod: "{{ deep_night_check }}"
      deep_end_tod: >-
        {{ (today_at(deep_night_check) + timedelta(minutes=10)).strftime('%H:%M:%S') }}
      turn_on_dt: "{{ today_at(bedtime) - timedelta(minutes=lead | int) }}"
      turn_on_tod: "{{ turn_on_dt.strftime('%H:%M:%S') }}"
      # --- Phase derivation (all time-of-day string comparisons) ---
      # The "day side" of the schedule runs wake -> bedtime_lock.
      on_day_side: "{{ wake_tod <= now_tod and now_tod < lock_tod }}"
      in_lock_window: "{{ lock_tod <= now_tod and now_tod < bedtime_tod }}"
      in_deep_check: "{{ deep_tod <= now_tod and now_tod < deep_end_tod }}"
      in_deep_hold: "{{ deep_end_tod <= now_tod and now_tod < wake_tod }}"
      # NIGHT_HOLD is the phase-derivation else branch (after bedtime, before
      # the deep-night check) — no explicit variable is needed for it.
      # PRECOOL begins only when cooling is needed AND now >= turn_on;
      # once the AC is running it STAYS PRECOOL (one-way latch) even if a
      # recomputed lead pushes turn_on later. The running AC IS the
      # persisted "PRECOOL has started" bit — stateless and restart-safe.
      precool_started: "{{ (cooling_needed and now_tod >= turn_on_tod) or ac_is_running }}"
      in_precool_window: "{{ on_day_side and precool_started }}"
      in_day_off: "{{ on_day_side and not precool_started }}"
      # Single-lined: a folded scalar leaves trailing whitespace between a
      # token and the next tag, and this value feeds == comparisons.
      phase: "{% if in_lock_window %}BEDTIME_LOCK{% elif in_precool_window %}PRECOOL{% elif in_deep_check %}DEEP_NIGHT_CHECK{% elif in_deep_hold %}DEEP_HOLD{% elif in_day_off %}DAY_OFF{% else %}NIGHT_HOLD{% endif %}"
      # --- PRECOOL sub-state ---
      precool_substate: >-
        {% if warmest_bedroom | float > ideal_temp | float %}DRIVE{% else %}HOLD{% endif %}
      # --- Setpoints, all clamped to the AC's discovered min/max ---
      effective_drive: >-
        {{ [[drive_setpoint | float, ac_min_temp | float] | max,
            ac_max_temp | float] | min }}
      maintaining_setpoint: >-
        {{ [[ideal_temp | float - hall_offset | float, ac_min_temp | float] | max,
            ac_max_temp | float] | min }}
      # --- Cool vs dry mode (only chosen while beeps are free) ---
      # Single-lined: this value feeds == comparisons and hvac_mode:; a
      # folded scalar would leave trailing whitespace on the rendered token.
      # The dry branch additionally requires the AC to advertise 'dry' in its
      # discovered hvac_modes — otherwise it falls through to cool.
      desired_mode: "{% if not enable_dry_mode %}cool{% elif warmest_bedroom | float > ideal_temp | float + tolerance | float %}cool{% elif room_humidity | float > humidity_threshold | float and 'dry' in ac_hvac_modes %}dry{% else %}cool{% endif %}"
      # --- Fan modes discovered from the entity ---
      fan_high: >-
        {% set m = ac_fan_modes %}
        {% set ns = namespace(found='') %}
        {% for c in ['Power', 'Turbo', 'High', 'high', '4', '3'] if c in m %}
          {% if ns.found == '' %}{% set ns.found = c %}{% endif %}
        {% endfor %}
        {{ ns.found if ns.found != '' else (m[-1] if m | length > 0 else 'high') }}
      fan_normal: >-
        {% set m = ac_fan_modes %}
        {% set ns = namespace(found='') %}
        {% for c in ['Mid', 'Medium', 'mid', 'medium', 'Auto', 'auto', '2'] if c in m %}
          {% if ns.found == '' %}{% set ns.found = c %}{% endif %}
        {% endfor %}
        {{ ns.found if ns.found != '' else (m[0] if m | length > 0 else 'auto') }}
```

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.SafeLoader.add_multi_constructor('!', lambda l,s,n: None); yaml.safe_load(open('bedroom_precool.yaml'))" && echo VALID
```

Expected: `VALID`.

- [ ] **Step 3: Commit**

```bash
git add bedroom_precool.yaml
git commit -m "feat(bedroom-precool): add forecast fetch and prediction/phase variables"
```

---

## Task 7: Action — config validation, vacation override, sensor validation

**Executor:** Codex
**Rationale:** Mechanical YAML append of verbatim content plus a deterministic `python3` syntax check.

**Files:**
- Modify: `bedroom_precool.yaml`

Append three guard stages: STEP 3 (config validation — `stop` on an invalid setup), STEP 4 (vacation override — turn the AC off then `stop`, placed *before* sensor validation because turning the AC off does not depend on bedroom-sensor health), STEP 5 (sensor / entity validation — `stop` if the AC entity is unavailable or no bedroom sensor is valid), and STEP 5b (the child-safety overcooling fault notification — informational, does not stop).

- [ ] **Step 1: Append STEP 3, STEP 4, STEP 5 and STEP 5b**

After the STEP 2c `variables:` block (ending with the `fan_normal:` template), append:

```yaml

  # =============================================
  # STEP 3: RUNTIME (CONFIG) VALIDATION
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: >-
              {{ drive_setpoint | float >= ideal_temp | float
                 or hall_offset | float < 0
                 or bedtime == wake_time
                 or wake_time >= bedtime
                 or deep_night_check >= wake_time }}
        sequence:
          - choose:
              - conditions:
                  - condition: template
                    value_template: "{{ enable_notifications }}"
                sequence:
                  - service: persistent_notification.create
                    data:
                      title: "Bedroom Pre-Cool — Configuration Error"
                      message: >
                        Invalid configuration detected. Check that Drive
                        Setpoint ({{ drive_setpoint }}°C) is below Ideal
                        Temperature ({{ ideal_temp }}°C), Hall Offset
                        ({{ hall_offset }}°C) is not negative, and the schedule
                        is ordered correctly: Wake Time ({{ wake_time }}) must
                        be before Bedtime ({{ bedtime }}), and the Deep-Night
                        Check ({{ deep_night_check }}) must fall in the small
                        hours before Wake Time. Control is paused until
                        corrected.
                      notification_id: "bedroom_precool_config_error"
          - stop: "Configuration error"

  # =============================================
  # STEP 4: VACATION OVERRIDE
  # Before sensor validation — turning the AC off does not depend on
  # bedroom-sensor health.
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ vacation_active }}"
        sequence:
          - choose:
              - conditions:
                  - condition: template
                    value_template: "{{ not ac_unavailable and ac_is_running }}"
                sequence:
                  - service: climate.turn_off
                    target:
                      entity_id: "{{ ac_climate }}"
          - stop: "Vacation active"

  # =============================================
  # STEP 5: SENSOR / ENTITY VALIDATION
  # =============================================
  - choose:
      # AC entity unavailable — skip this tick, retry next minute.
      - conditions:
          - condition: template
            value_template: "{{ ac_unavailable }}"
        sequence:
          - choose:
              - conditions:
                  - condition: template
                    value_template: "{{ enable_notifications }}"
                sequence:
                  - service: persistent_notification.create
                    data:
                      title: "Bedroom Pre-Cool — AC Unavailable"
                      message: >
                        {{ ac_climate }} is {{ current_hvac_mode }}. Skipping
                        this cycle; will retry next minute.
                      notification_id: "bedroom_precool_ac_unavailable"
          - stop: "AC entity unavailable"
      # No valid bedroom temperature sensor — hold state, warn.
      - conditions:
          - condition: template
            value_template: "{{ not bedroom_sensors_ok }}"
        sequence:
          - choose:
              - conditions:
                  - condition: template
                    value_template: "{{ enable_notifications }}"
                sequence:
                  - service: persistent_notification.create
                    data:
                      title: "Bedroom Pre-Cool — No Bedroom Sensor"
                      message: >
                        All bedroom temperature sensors are unavailable. The
                        blueprint is holding the current AC state until a
                        sensor recovers.
                      notification_id: "bedroom_precool_sensor_warning"
          - stop: "No valid bedroom temperature sensor"

  # =============================================
  # STEP 5b: OVERCOOLING FAULT (child-safety floor)
  # Informational only — does not stop the cycle.
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ enable_notifications and coldest_bedroom | float < 16 }}"
        sequence:
          - service: persistent_notification.create
            data:
              title: "Bedroom Pre-Cool — Overcooling Fault"
              message: >
                A bedroom sensor reads {{ coldest_bedroom }}°C, below the 16°C
                child-safety floor. Check AC operation and sensor placement.
                If inside the deep-night check window the blueprint will
                correct upward.
              notification_id: "bedroom_precool_overcool_fault"
```

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.SafeLoader.add_multi_constructor('!', lambda l,s,n: None); yaml.safe_load(open('bedroom_precool.yaml'))" && echo VALID
```

Expected: `VALID`.

- [ ] **Step 3: Commit**

```bash
git add bedroom_precool.yaml
git commit -m "feat(bedroom-precool): add config validation, vacation override and sensor validation"
```

---

## Task 8: Action — 6-phase dispatch (DAY_OFF, PRECOOL, idempotent service calls)

**Executor:** Codex
**Rationale:** Mechanical YAML append of verbatim content plus a deterministic `python3` syntax check.

**Files:**
- Modify: `bedroom_precool.yaml`

Open STEP 6 — the phase dispatch — with the **first two** acting branches: `DAY_OFF` (ensure the AC is off, idempotently) and `PRECOOL` (closed-loop DRIVE / HOLD). The 6-branch dispatch `choose` is wrapped in an outer single-branch `choose` gated on `is_real_trigger`, so a manual "Run" (which has no `trigger.id`) computes everything and shows the debug dump but never actuates the AC. Task 9 appends the remaining four branches to the inner 6-branch `choose` and closes both.

The PRECOOL branch shows the LG service-call discipline in full:
- **Turn the unit on first** when it is off — `set_hvac_mode` fails with "command not supported in POWER OFF" on a powered-off LG unit.
- **Mode then temperature** as two separate, sequenced calls — the combined call was unreliable on LG ThinQ before HA 2025.7.
- Every call guarded by a current-vs-desired idempotency comparison — a stray call is a stray beep.
- The setpoint comparison treats an unknown (`null`) LG setpoint as "force a write" — `not current_setpoint_known` is in the OR.

- [ ] **Step 1: Append the opening of STEP 6 — the `is_real_trigger` wrapper and the DAY_OFF and PRECOOL branches**

After the STEP 5b `choose` block, append:

```yaml

  # =============================================
  # STEP 6: PHASE DISPATCH — exactly one phase acts.
  # Each acting branch resolves desired setpoint/mode/fan, then issues
  # only idempotent service calls (a stray call is a stray beep).
  # NIGHT_HOLD and DEEP_HOLD are deliberately EMPTY (zero service calls).
  #
  # The whole 6-branch dispatch is gated on is_real_trigger: a manual "Run"
  # has no trigger.id, so it computes everything and shows the STEP 8 debug
  # dump but NEVER actuates the AC nor double-applies the BEDTIME_LOCK
  # auto-learn write. STEP 1-5, 7 and 8 are unchanged on a manual Run.
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ is_real_trigger }}"
        sequence:
          - choose:
              # ---------- DAY_OFF: ensure the AC is off ----------
              - conditions:
                  - condition: template
                    value_template: "{{ phase == 'DAY_OFF' }}"
                sequence:
                  - choose:
                      - conditions:
                          - condition: template
                            value_template: "{{ ac_is_running }}"
                        sequence:
                          - service: climate.turn_off
                            target:
                              entity_id: "{{ ac_climate }}"

              # ---------- PRECOOL: closed-loop drive / hold ----------
              - conditions:
                  - condition: template
                    value_template: "{{ phase == 'PRECOOL' }}"
                sequence:
                  - variables:
                      precool_setpoint: >-
                        {% if precool_substate == 'DRIVE' %}
                          {{ effective_drive | float }}
                        {% else %}
                          {{ maintaining_setpoint | float }}
                        {% endif %}
                      precool_fan: >-
                        {% if precool_substate == 'DRIVE' %}
                          {{ fan_high }}
                        {% else %}
                          {{ fan_normal }}
                        {% endif %}
                  # 1. Ensure the unit is running and in the desired mode.
                  #    set_hvac_mode fails on a powered-off LG unit, so turn_on
                  #    first when off, then set the mode while it is running.
                  - choose:
                      - conditions:
                          - condition: template
                            value_template: "{{ not ac_is_running }}"
                        sequence:
                          - service: climate.turn_on
                            target:
                              entity_id: "{{ ac_climate }}"
                  # Mode guard intentionally omits the `ac_is_running` precondition:
                  # ac_is_running was captured in STEP 2 before this branch's
                  # climate.turn_on ran, so on a first-tick-from-off it is stale
                  # `false`. climate.turn_on always precedes this call when the unit
                  # was off, so the unit IS on by now; the stale current_hvac_mode
                  # ('off') still differs from desired_mode ('cool'), so the mode is
                  # set the same tick instead of waiting for the next minute.
                  - choose:
                      - conditions:
                          - condition: template
                            value_template: >-
                              {{ current_hvac_mode != desired_mode }}
                        sequence:
                          - service: climate.set_hvac_mode
                            target:
                              entity_id: "{{ ac_climate }}"
                            data:
                              hvac_mode: "{{ desired_mode }}"
                  # 2. Then set the temperature (separate, sequenced call).
                  - choose:
                      - conditions:
                          - condition: template
                            value_template: >-
                              {{ (not current_setpoint_known)
                                 or (current_setpoint | float - precool_setpoint | float)
                                    | abs > 0.1 }}
                        sequence:
                          - service: climate.set_temperature
                            target:
                              entity_id: "{{ ac_climate }}"
                            data:
                              temperature: "{{ precool_setpoint | float }}"
                  # 3. Fan, only if fan control is enabled and there is a delta.
                  - choose:
                      - conditions:
                          - condition: template
                            value_template: >-
                              {{ enable_fan_control
                                 and ac_fan_modes | length > 0
                                 and current_fan != precool_fan }}
                        sequence:
                          - service: climate.set_fan_mode
                            target:
                              entity_id: "{{ ac_climate }}"
                            data:
                              fan_mode: "{{ precool_fan }}"
```

**Note:** Both `choose` blocks are intentionally left **unclosed** — Task 9 appends the remaining four branches as further list items under the **inner** 6-branch `choose:` (the one nested inside the `is_real_trigger` wrapper).

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.SafeLoader.add_multi_constructor('!', lambda l,s,n: None); yaml.safe_load(open('bedroom_precool.yaml'))" && echo VALID
```

Expected: `VALID`. (A `choose` with two branches is valid YAML even though more branches follow.)

- [ ] **Step 3: Commit**

```bash
git add bedroom_precool.yaml
git commit -m "feat(bedroom-precool): add phase dispatch DAY_OFF and PRECOOL branches"
```

---

## Task 9: Action — BEDTIME_LOCK (+ auto-learn write), DEEP_NIGHT_CHECK, NIGHT_HOLD, DEEP_HOLD

**Executor:** Codex
**Rationale:** Mechanical YAML append of verbatim content plus a deterministic branch-count assertion.

**Files:**
- Modify: `bedroom_precool.yaml`

Append the remaining four branches to the STEP 6 `choose`, closing the 6-phase dispatch:
- **BEDTIME_LOCK** — only acts on an already-running AC (cool-day no-op otherwise). Locks the maintaining setpoint (mode then temperature) and, when auto-learn is on and the helper is configured, computes `bedtime_error` and writes the clamped `new_bias` to the `input_number` helper. The helper write is **beep-free** — it is an `input_number`, not the AC. The `BEDTIME_LOCK` window is `bedtime − 1 min → bedtime` (the `lock_tod` constant): exactly one periodic tick lands in it, which is what keeps the read-modify-write auto-learn write single-shot — a 2-minute window would land two ticks and double-apply the correction. A restart within that minute re-applies the write once but stays bounded by the `[−60, 120]` bias clamp.
- **DEEP_NIGHT_CHECK** — only acts on a running AC; nudges the setpoint by `correction_step` if drift exceeds `tolerance`. The corrective target is `maintaining_setpoint ∓ correction_step` (too warm → minus, overcooled → plus), both clamped to `ac_min_temp` / `ac_max_temp`; it is derived from the **stable `maintaining_setpoint`**, NOT the live `current_setpoint`. Because the periodic trigger runs this branch ~10 times across the 10-minute window, a target keyed off the moving `current_setpoint` would ratchet the setpoint by `correction_step` every minute. Keying it off the deterministic `maintaining_setpoint` makes the `abs(current_setpoint − deep_target_setpoint) > 0.1` idempotency guard genuinely cap the correction at exactly one `climate.set_temperature` call. The 10-minute window plus that guard hard-cap this at one beep.
- **NIGHT_HOLD** / **DEEP_HOLD** — `sequence: []`. Genuinely empty — zero service calls. This is what makes the quiet window silent.

- [ ] **Step 1: Append the four remaining branches under the inner STEP 6 `choose`**

After the PRECOOL branch's fan `choose` block (the last list item under the **inner** 6-branch `choose:`, the one nested inside the `is_real_trigger` wrapper), append at the same indentation as the existing DAY_OFF / PRECOOL branches:

```yaml

              # ---------- BEDTIME_LOCK: one locking command + auto-learn write ----------
              - conditions:
                  - condition: template
                    value_template: "{{ phase == 'BEDTIME_LOCK' }}"
                sequence:
                  # Only act on an already-running AC (cool-day no-op otherwise).
                  - choose:
                      - conditions:
                          - condition: template
                            value_template: "{{ ac_is_running }}"
                        sequence:
                          # Lock the maintaining setpoint (mode first, then temp).
                          - choose:
                              - conditions:
                                  - condition: template
                                    value_template: "{{ current_hvac_mode != desired_mode }}"
                                sequence:
                                  - service: climate.set_hvac_mode
                                    target:
                                      entity_id: "{{ ac_climate }}"
                                    data:
                                      hvac_mode: "{{ desired_mode }}"
                          - choose:
                              - conditions:
                                  - condition: template
                                    value_template: >-
                                      {{ (not current_setpoint_known)
                                         or (current_setpoint | float
                                             - maintaining_setpoint | float)
                                            | abs > 0.1 }}
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
                                      {{ enable_fan_control
                                         and ac_fan_modes | length > 0
                                         and current_fan != fan_normal }}
                                sequence:
                                  - service: climate.set_fan_mode
                                    target:
                                      entity_id: "{{ ac_climate }}"
                                    data:
                                      fan_mode: "{{ fan_normal }}"
                          # Auto-learn helper write — beep-free (an input_number,
                          # not the AC). Only on a cooling night (AC running).
                          - choose:
                              - conditions:
                                  - condition: template
                                    value_template: "{{ enable_auto_learn and lead_bias_configured }}"
                                sequence:
                                  - variables:
                                      bedtime_error: "{{ warmest_bedroom | float - ideal_temp | float }}"
                                      new_bias_raw: >-
                                        {{ (lead_bias | float)
                                           + (learn_gain | float)
                                             * (bedtime_error | float)
                                             * (k_indoor | float) }}
                                      # round(0) | int — the lead_bias_helper input_number
                                      # is created with step 1, so the written value must be
                                      # a whole number to match the helper's step.
                                      new_bias: "{{ [[new_bias_raw | float, -60] | max, 120] | min | round(0) | int }}"
                                  - service: input_number.set_value
                                    target:
                                      entity_id: "{{ lead_bias_entity }}"
                                    data:
                                      value: "{{ new_bias | float }}"

              # ---------- DEEP_NIGHT_CHECK: at most one corrective command ----------
              - conditions:
                  - condition: template
                    value_template: "{{ phase == 'DEEP_NIGHT_CHECK' }}"
                sequence:
                  - choose:
                      - conditions:
                          - condition: template
                            value_template: "{{ ac_is_running }}"
                        sequence:
                          - variables:
                              deep_drift: "{{ warmest_bedroom | float - ideal_temp | float }}"
                              # Target is derived from the STABLE maintaining_setpoint —
                              # NOT the moving current_setpoint. The periodic trigger runs
                              # this branch ~10 times across the 10-minute window;
                              # maintaining_setpoint is deterministic on every tick, so the
                              # abs(current_setpoint - deep_target_setpoint) > 0.1
                              # idempotency guard genuinely caps the correction at exactly
                              # one climate.set_temperature call. Single-lined to avoid a
                              # folded-scalar trailing-whitespace artifact.
                              deep_target_setpoint: "{% if deep_drift | float > tolerance | float %}{{ [[maintaining_setpoint | float - correction_step | float, ac_min_temp | float] | max, ac_max_temp | float] | min }}{% elif deep_drift | float < (0 - tolerance | float) %}{{ [[maintaining_setpoint | float + correction_step | float, ac_min_temp | float] | max, ac_max_temp | float] | min }}{% else %}{{ maintaining_setpoint | float }}{% endif %}"
                          - choose:
                              - conditions:
                                  - condition: template
                                    value_template: >-
                                      {{ current_setpoint_known
                                         and (deep_drift | float | abs) > (tolerance | float)
                                         and (current_setpoint | float
                                              - deep_target_setpoint | float)
                                             | abs > 0.1 }}
                                sequence:
                                  - service: climate.set_temperature
                                    target:
                                      entity_id: "{{ ac_climate }}"
                                    data:
                                      temperature: "{{ deep_target_setpoint | float }}"

              # ---------- NIGHT_HOLD: deliberately empty (zero service calls) ----------
              - conditions:
                  - condition: template
                    value_template: "{{ phase == 'NIGHT_HOLD' }}"
                sequence: []

              # ---------- DEEP_HOLD: deliberately empty (zero service calls) ----------
              - conditions:
                  - condition: template
                    value_template: "{{ phase == 'DEEP_HOLD' }}"
                sequence: []
```

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.SafeLoader.add_multi_constructor('!', lambda l,s,n: None); yaml.safe_load(open('bedroom_precool.yaml'))" && echo VALID
```

Expected: `VALID`.

- [ ] **Step 3: Confirm the phase dispatch has exactly 6 branches**

The 6-branch dispatch `choose` is nested one level inside the `is_real_trigger`
wrapper, so the finder walks the structure recursively rather than scanning
only top-level action items.

```bash
python3 -c "
import yaml
yaml.SafeLoader.add_multi_constructor('!', lambda l,s,n: None)
bp = yaml.safe_load(open('bedroom_precool.yaml'))

def find_six_branch(node):
    # Recursively search for a 'choose' with exactly 6 branches.
    if isinstance(node, dict):
        c = node.get('choose')
        if isinstance(c, list) and len(c) == 6:
            return True
        return any(find_six_branch(v) for v in node.values())
    if isinstance(node, list):
        return any(find_six_branch(v) for v in node)
    return False

assert find_six_branch(bp['action']), 'no 6-branch choose found'
print('phase dispatch branches OK: 6')
"
```

Expected: `phase dispatch branches OK: 6`.

- [ ] **Step 4: Commit**

```bash
git add bedroom_precool.yaml
git commit -m "feat(bedroom-precool): add BEDTIME_LOCK (auto-learn), DEEP_NIGHT_CHECK and hold branches"
```

---

## Task 10: Action — auxiliary notifications + manual-run debug dump

**Executor:** Codex
**Rationale:** Mechanical YAML append of verbatim content plus a deterministic `python3` syntax check.

**Files:**
- Modify: `bedroom_precool.yaml`

Append the final three action steps: STEP 7a (a one-time notice when auto-learn is on but no bias helper is configured), STEP 7b (a notice when both the forecast and the outdoor sensor are unavailable), and STEP 8 (the manual-run debug persistent notification — fires only when there is no `trigger.id`, i.e. a manual "Run"). The debug dump is the calibration tool: it surfaces every prediction variable so the user can tune coefficients and `hall_offset`.

- [ ] **Step 1: Append STEP 7a, STEP 7b and STEP 8**

After the closing of the STEP 6 `choose` (the `DEEP_HOLD` branch), append:

```yaml

  # =============================================
  # STEP 7a: LEAD-BIAS-HELPER NOT CONFIGURED — one-time notice
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: >-
              {{ enable_notifications and enable_auto_learn
                 and not lead_bias_configured }}
        sequence:
          - service: persistent_notification.create
            data:
              title: "Bedroom Pre-Cool — Auto-Learn Helper Missing"
              message: >
                Auto-Learn is enabled but no Lead-Time Bias Helper is
                configured. The blueprint still runs with a zero bias.
                Create an input_number helper and select it to enable
                self-learning.
              notification_id: "bedroom_precool_no_bias_helper"

  # =============================================
  # STEP 7b: FORECAST UNAVAILABLE — informational notice
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: >-
              {{ enable_notifications and phase == 'DAY_OFF'
                 and forecast_window_temps | length == 0
                 and not outdoor_now_ok }}
        sequence:
          - service: persistent_notification.create
            data:
              title: "Bedroom Pre-Cool — Forecast & Outdoor Unavailable"
              message: >
                Neither an hourly forecast nor the outdoor sensor is available.
                The prediction is leaning on the indoor gap and solar term only
                until one recovers.
              notification_id: "bedroom_precool_forecast_warning"

  # =============================================
  # STEP 8: DEBUG NOTIFICATION (manual run only)
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ trigger.id | default('manual') == 'manual' }}"
        sequence:
          - service: persistent_notification.create
            data:
              title: "Bedroom Pre-Cool Debug — {{ now().strftime('%H:%M:%S') }}"
              message: >
                **Phase:** {{ phase }}
                {% if phase == 'PRECOOL' %}({{ precool_substate }}){% endif %}

                **Warmest bedroom:** {{ warmest_bedroom }}°C
                | **Coldest:** {{ coldest_bedroom }}°C
                | **Ideal:** {{ ideal_temp }}°C

                **Humidity (max):** {{ room_humidity }}%
                | **Outdoor now:** {{ outdoor_now }}°C (ok={{ outdoor_now_ok }})

                **ΔT indoor:** {{ delta_in }}°C
                | **ΔT outdoor:** {{ delta_out }}°C
                | **forecast_max:** {{ forecast_max }}°C

                **Solar load:** {{ solar_load }}
                (elev {{ sun_elevation }}°, azim {{ sun_azimuth }}°)

                **lead_bias:** {{ lead_bias }} min
                (configured={{ lead_bias_configured }})

                **lead:** {{ lead }} min
                | **turn_on:** {{ turn_on_dt.strftime('%H:%M') }}
                | **bedtime:** {{ bedtime_dt.strftime('%H:%M') }}

                **cooling_needed:** {{ cooling_needed }}

                **AC:** mode={{ current_hvac_mode }},
                running={{ ac_is_running }},
                setpoint={{ current_setpoint }}°C (known={{ current_setpoint_known }}),
                fan={{ current_fan }}

                **AC limits:** min={{ ac_min_temp }}°C, max={{ ac_max_temp }}°C

                **maintaining_setpoint:** {{ maintaining_setpoint }}°C
                | **effective_drive:** {{ effective_drive }}°C

                **desired_mode:** {{ desired_mode }}
                | **vacation:** {{ vacation_active }}
              notification_id: "bedroom_precool_debug"
```

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.SafeLoader.add_multi_constructor('!', lambda l,s,n: None); yaml.safe_load(open('bedroom_precool.yaml'))" && echo VALID
```

Expected: `VALID`.

- [ ] **Step 3: Commit**

```bash
git add bedroom_precool.yaml
git commit -m "feat(bedroom-precool): add auxiliary notifications and manual-run debug dump"
```

---

## Task 11: Structural validation of the parsed blueprint

**Executor:** Codex
**Rationale:** Runs a deterministic `python3` assertion script and reports the result; no file edit unless an assertion fails.

**Files:**
- Verify: `bedroom_precool.yaml` (no modification unless an assertion fails)

Run a structural assertion pass on the fully parsed blueprint — input count, triggers, action-step count, mode flags, phase-dispatch branch count, and the presence of every key input. This catches a structurally wrong-but-syntactically-valid YAML before the work is handed to the user for HA import. The 6-branch phase dispatch is nested one level inside the `is_real_trigger` wrapper, so the script locates it with a recursive walk.

- [ ] **Step 1: Run the full structural assertion script**

```bash
python3 -c "
import yaml
yaml.SafeLoader.add_multi_constructor('!', lambda l,s,n: None)
with open('bedroom_precool.yaml') as f:
    bp = yaml.safe_load(f)

# --- metadata ---
assert 'blueprint' in bp, 'missing blueprint key'
for k in ('name', 'description', 'domain', 'input'):
    assert k in bp['blueprint'], f'missing blueprint.{k}'
assert bp['blueprint']['domain'] == 'automation', 'domain must be automation'
assert 'v1.0.0' in bp['blueprint']['name'], 'version missing from name'
assert '2025.7' in bp['blueprint']['description'], 'HA 2025.7 requirement missing from description'

# --- mode flags ---
assert bp['mode'] == 'restart', f\"mode must be restart, got {bp['mode']}\"
assert bp['max_exceeded'] == 'silent', 'max_exceeded must be silent'

# --- inputs: exactly 32 ---
inputs = bp['blueprint']['input']
assert len(inputs) == 32, f'expected 32 inputs, got {len(inputs)}'

# --- every key input present ---
expected_inputs = [
    'ac_climate', 'bedroom_temp_sensors', 'bedroom_humidity_sensors',
    'outdoor_temp_sensor', 'weather_entity', 'sun_entity', 'lead_bias_helper',
    'ac_sound_switch', 'ideal_temp', 'hall_offset', 'drive_setpoint',
    'tolerance', 'correction_step', 'skip_threshold', 'humidity_threshold',
    'bedtime', 'wake_time', 'deep_night_check', 'base_minutes', 'k_indoor',
    'k_outdoor', 'solar_max_minutes', 'safety_margin_minutes',
    'lead_cap_minutes', 'solar_afternoon_only', 'learn_gain',
    'sensor_strategy', 'enable_fan_control', 'enable_dry_mode',
    'enable_auto_learn', 'vacation_toggle', 'enable_notifications',
]
for key in expected_inputs:
    assert key in inputs, f'missing input: {key}'

# --- ideal_temp child-safety floor ---
assert inputs['ideal_temp']['selector']['number']['min'] == 16.0, 'ideal_temp min must be 16'

# --- top-level !input variables: one per input (32) ---
tlv = bp['variables']
assert len(tlv) == 32, f'expected 32 top-level variables, got {len(tlv)}'

# --- triggers: exactly 3 ---
trg = bp['trigger']
assert len(trg) == 3, f'expected 3 triggers, got {len(trg)}'
trg_ids = {t.get('id') for t in trg}
assert trg_ids == {'periodic', 'vacation_change', 'ha_start'}, f'trigger ids: {trg_ids}'

# --- action: 14 steps ---
act = bp['action']
assert len(act) == 14, f'expected 14 action steps, got {len(act)}'

# --- phase dispatch: a choose with exactly 6 branches ---
# The 6-branch dispatch is nested one level inside the is_real_trigger
# wrapper choose, so it is located with a recursive walk rather than a
# top-level scan of the action list.
def find_six_branch_chooses(node, acc):
    if isinstance(node, dict):
        c = node.get('choose')
        if isinstance(c, list) and len(c) == 6:
            acc.append(c)
        for v in node.values():
            find_six_branch_chooses(v, acc)
    elif isinstance(node, list):
        for v in node:
            find_six_branch_chooses(v, acc)
    return acc

phase_dispatch = find_six_branch_chooses(act, [])
assert len(phase_dispatch) == 1, 'expected exactly one 6-branch phase dispatch choose'

# --- the dispatch is gated on is_real_trigger (manual Run = inspect-only) ---
assert 'is_real_trigger' in yaml.dump(act), 'is_real_trigger gate missing from action'

# --- NIGHT_HOLD and DEEP_HOLD branches are empty sequences ---
empty = 0
for branch in phase_dispatch[0]:
    if branch.get('sequence') == []:
        empty += 1
assert empty == 2, f'expected 2 empty hold branches, got {empty}'

print('STRUCTURAL VALIDATION PASSED')
print(f'  inputs: {len(inputs)} | top-level vars: {len(tlv)} | triggers: {len(trg)}')
print(f'  action steps: {len(act)} | phase branches: 6 | empty hold branches: {empty}')
"
```

Expected:
```
STRUCTURAL VALIDATION PASSED
  inputs: 32 | top-level vars: 32 | triggers: 3
  action steps: 14 | phase branches: 6 | empty hold branches: 2
```

If any assertion fails, fix the source YAML, re-run the syntax check from Task 10 Step 2, then re-run this script. Commit the fix with `fix(bedroom-precool): ...` before continuing.

- [ ] **Step 2: No commit unless the YAML changed**

If Step 1 passed with no edits, there is nothing to commit for this task.

---

## Task 12: Update the README

**Executor:** Codex
**Rationale:** Inserts a verbatim markdown block at a precisely specified location — a mechanical edit.

**Files:**
- Modify: `README.md`

Add a "Bedroom Sleep Pre-Cool" section to the README, matching the format of the existing entries (Overview, Features with emoji bullets, Requirements, Installation with the My-HA import badge + raw URL).

- [ ] **Step 1: Read the current README structure**

```bash
grep -n "^## \|^### " README.md
```

Confirm the last blueprint section is "Bathroom Heating Rack Blueprint" and that the file ends with the `*Created by Martin Levie ...*` credit line.

- [ ] **Step 2: Insert the new section before the credit line**

Insert this block immediately **before** the final `---` + `*Created by Martin Levie (Gemini CLI Agent)*` line:

````markdown
## Bedroom Sleep Pre-Cool Blueprint

### Overview
Predictive pre-cooling of bedrooms via a single LG air conditioner in the upstairs hall. The blueprint brings the warmest bedroom to an ideal sleep temperature (default 19 °C) by a fixed bedtime, then holds the room quietly overnight while issuing the absolute minimum number of commands — because LG ACs beep on every command and the tone cannot be silenced in software. The AC cools the hall indirectly through open doors, so the turn-on time is *predicted* from the indoor gap, an hourly weather forecast, and solar gain, with a self-learning bias that auto-corrects from each night's result.

### Features
*   **🧊 6-Phase State Machine:** A stateless daily cycle — DAY-OFF, PRECOOL, BEDTIME-LOCK, NIGHT-HOLD, DEEP-NIGHT-CHECK, DEEP-HOLD — derived from the clock every minute, overnight-wrap-aware.
*   **🔮 Predictive Turn-On:** A transparent linear lead-time formula (indoor gap + forecast outdoor + solar load) recomputed each minute decides when to start cooling so the room hits target by bedtime.
*   **🧠 Self-Learning Bias:** One scalar — the lead-time bias — is persisted in an `input_number` helper and auto-corrected from each cooling night's outcome. Converges over ~3–6 nights.
*   **🔇 Strict Beep Budget:** Unlimited commands before bedtime; at most 0–2 after. NIGHT-HOLD and DEEP-HOLD issue zero commands; every climate call is idempotency-guarded.
*   **🌡️ Closed-Loop Pre-Cool:** DRIVE / HOLD sub-states cool the hall as hard as the AC allows until the warmest bedroom reaches ideal.
*   **💧 Opt-In Dry Mode:** Humidity-aware `dry` mode, default off — `cool` is the proven path; enable `dry` only after verifying it on the unit.
*   **🛡️ Child-Safe:** `ideal_temp` is bounded ≥ 16 °C; a sub-16 °C bedroom reading raises an overcooling fault. Every setpoint is clamped to the AC's discovered limits.
*   **🔍 Debug-Friendly:** Manual "Run" produces a persistent notification dumping every prediction variable for easy calibration.

### Requirements
*   **Home Assistant Core 2025.7+** (LG ThinQ `set_temperature` fix, PR #147008)
*   One LG air conditioner connected via the LG ThinQ integration (a `climate` entity)
*   Bedroom temperature sensors (e.g., Aqara) — the control target
*   An outdoor temperature sensor
*   A weather entity with an **hourly** forecast — Met.no or Open-Meteo (**not Buienradar** — it has no hourly forecast)
*   An `input_number` helper to persist the self-learned lead-time bias
*   Optional: an `input_boolean` for the vacation toggle; the AC's sound `switch`

See `requirements_bedroom_precool.md` for the detailed design.

### Installation
1. Click the button below to import this blueprint into your Home Assistant instance:

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fleviemartin%2FBlueprints_Home%2Fmain%2Fbedroom_precool.yaml)

2. Or manually copy this URL into the Blueprints configuration:
`https://raw.githubusercontent.com/leviemartin/Blueprints_Home/main/bedroom_precool.yaml`
````

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(bedroom-precool): add bedroom sleep pre-cool blueprint to README"
```

---

## Task 13: HA import and mental-simulation walkthrough

**Executor:** Claude
**Rationale:** Mental state-machine simulation is subjective verification, and Steps 1–4 are user-facing HA actions the Codex sandbox cannot perform.

**Files:**
- None modified (unless a defect is found — then fix `bedroom_precool.yaml`).

The build environment has no live Home Assistant, so behavioural testing is delegated to the user. Steps 1–4 are user-facing import steps; Steps 5–11 are the spec's mental-simulation checklist, each walked against the actual YAML to confirm the implementing branch exists and behaves.

- [ ] **Step 1: User imports the blueprint into HA**

Tell the user:

> "Import `bedroom_precool.yaml` — either copy it into `<ha_config>/blueprints/automation/custom/bedroom_precool.yaml`, or use **Settings → Automations & Scenes → Blueprints → Import Blueprint** with the raw GitHub URL. Then **restart Home Assistant** (HA caches blueprints). The 'Bedroom Sleep Pre-Cool v1.0.0' entry should appear with no error badge."

- [ ] **Step 2: User creates the prerequisite helper(s)**

Tell the user:

> "Create an `input_number` helper for the lead-time bias: **Settings → Devices & Services → Helpers → + → Number**, range −60 to 120, step 1, initial 0. Optionally create an `input_boolean` for the vacation toggle."

- [ ] **Step 3: User creates an automation from the blueprint**

Tell the user:

> "**Settings → Automations & Scenes → + Create Automation → Use Blueprint → Bedroom Sleep Pre-Cool.** Select the AC climate entity, the bedroom temperature sensors, the outdoor sensor, the weather entity (Met.no or Open-Meteo — **not Buienradar**), and the lead-time bias helper. Defaults cover the rest. Save."

- [ ] **Step 4: User confirms the debug notification**

A manual "Run" is **inspect-only**: it computes every variable and writes the
debug notification, but STEP 6's phase dispatch is gated on `is_real_trigger`,
so a manual Run never actuates the AC and never double-applies the BEDTIME_LOCK
auto-learn write. It is safe to Run at any time, including inside the lock minute.

Tell the user:

> "Open the automation, **⋮ → Run**, then check **Settings → Notifications** for the `bedroom_precool_debug` entry. Confirm `phase`, `warmest_bedroom`, `lead`, `turn_on`, `cooling_needed`, and the discovered AC `min`/`max` all look sensible. A manual Run only shows this debug dump — it does not send any command to the AC."

- [ ] **Step 5: Walk — cool day and warm day**

Against the YAML confirm:
- Cool day: with `warmest_bedroom <= ideal_temp` and `forecast_max <= skip_threshold`, `cooling_needed` is `false` → `precool_started` is `false` (AC off) → phase stays `DAY_OFF`; the `DAY_OFF` branch only calls `climate.turn_off` when `ac_is_running` → no command. The night phases all guard `ac_is_running` → fully no-op; auto-learn does not write (BEDTIME_LOCK's `ac_is_running` guard is false).
- Warm day: `cooling_needed` is `true`; `lead` is computed; at `now_tod >= turn_on_tod` the phase becomes `PRECOOL`; DRIVE drives `effective_drive`, HOLD holds `maintaining_setpoint`.

- [ ] **Step 6: Walk — hot-day miss and heatwave**

Confirm:
- PRECOOL unfinished at bedtime: at `BEDTIME_LOCK` (`ac_is_running` true) the blueprint locks `maintaining_setpoint` regardless of the current bedroom temperature — the room coasts down afterward, zero extra beeps.
- Heatwave: `lead` is `clamp(..., 0, lead_cap_minutes)` — it cannot exceed the cap; `effective_drive` and `maintaining_setpoint` are both clamped to `ac_min_temp` → the AC drives as cold as it can; the debug dump shows the gap.

- [ ] **Step 7: Walk — auto-learn loop**

Confirm in the `BEDTIME_LOCK` branch:
- `enable_auto_learn` on + `lead_bias_configured` → `bedtime_error = warmest_bedroom − ideal_temp`; `new_bias = clamp(lead_bias + learn_gain*bedtime_error*k_indoor, −60, 120)` written via `input_number.set_value`.
- Room warm at bedtime (`bedtime_error > 0`) → bias rises; overcooled (`< 0`) → bias falls; both clamped.
- `lead_bias_helper` unconfigured → `lead_bias_configured` false → `lead_bias` is 0, no write, STEP 7a fires the one-time notice; the blueprint still runs.
- Cool-day no-op → `ac_is_running` false at BEDTIME_LOCK → no auto-learn write.

Ask the user to set `bedtime` a few minutes ahead on a warm evening and confirm the helper value changes after the lock.

- [ ] **Step 8: Walk — restart in each phase**

Confirm: the phase is derived purely from `now` time-of-day plus `ac_is_running`; there is no persisted phase state. The `ha_start` trigger re-runs the pipeline. In `NIGHT_HOLD` / `DEEP_HOLD` the branch is `sequence: []` → a restart issues no command → no spurious beep.

- [ ] **Step 9: Walk — deep-night drift cases**

Confirm in the `DEEP_NIGHT_CHECK` branch (window `deep_tod → deep_end_tod`, 10 min):
- Warm drift (`> tolerance`) → setpoint −= `correction_step`. Overcooled (`< −tolerance`) → setpoint += `correction_step`. In-band → no command (idempotency guard).
- AC off → `ac_is_running` false → no command.
- After the window → phase is `DEEP_HOLD` → `sequence: []`, nothing regardless of drift.

- [ ] **Step 10: Walk — vacation and dry mode**

Confirm:
- Vacation toggled on at any phase → STEP 4 turns the AC off (if running) then `stop` — no phase logic runs. Toggled off → resumes next tick.
- `enable_dry_mode` off → `desired_mode` is always `cool`. On + humid + small gap (`warmest_bedroom <= ideal_temp + tolerance`, `room_humidity > humidity_threshold`) → `dry`.

- [ ] **Step 11: Walk — turn-on latch**

Confirm: once the AC is running, `precool_started` is `true` via the `or ac_is_running` term → `in_precool_window` stays true on the day side even if a recomputed `lead` pushes `turn_on_tod` later → the phase does not revert to `DAY_OFF` → the AC is not turned off mid-afternoon.

If any walkthrough step reveals a defect, fix `bedroom_precool.yaml`, re-run Task 10 Step 2 (syntax) and Task 11 Step 1 (structure), and commit with `fix(bedroom-precool): ...`. Otherwise there is nothing to commit for this task.

---

## Self-Review

### 1. Spec coverage

| Spec section | Implemented in |
|---|---|
| Blueprint metadata (name, description, domain, HA 2025.7 note) | Task 2 |
| Group 1 — Devices & Sensors (8 inputs) | Task 2 |
| Group 2 — Target Temperatures (7 inputs) | Task 2 |
| Group 3 — Schedule (3 inputs) | Task 3 |
| Group 4 — Prediction Tuning (8 inputs) | Task 3 |
| Group 5 — Behaviour (3 inputs) | Task 3 |
| Group 6 — Global Controls (2 inputs) | Task 3 |
| `mode: restart` / `max_exceeded: silent` | Task 4 |
| 3 triggers (periodic, vacation_change, ha_start) | Task 4 |
| Top-level `!input` pass-through variables | Task 4 |
| Action — mute sound pre-step | Task 5 |
| Computed variables — live state (`warmest_bedroom`, AC state, capability discovery) | Task 5 |
| `weather.get_forecasts` (plural) periodic fetch + `forecast_max` | Task 6 |
| Prediction — solar load, lead formula, `lead_bias` read, phase derivation | Task 6 |
| Runtime config validation | Task 7 |
| Vacation override (before sensor validation) | Task 7 |
| Sensor / AC-entity validation | Task 7 |
| Child-safety overcooling fault | Task 7 |
| 6-phase dispatch — DAY_OFF, PRECOOL | Task 8 |
| LG service-call discipline (turn_on-then-mode-then-temp, idempotency) | Task 8 |
| 6-phase dispatch — BEDTIME_LOCK + auto-learn write | Task 9 |
| 6-phase dispatch — DEEP_NIGHT_CHECK | Task 9 |
| 6-phase dispatch — empty NIGHT_HOLD / DEEP_HOLD | Task 9 |
| Forecast-unavailable / no-bias-helper notices | Task 10 |
| Manual-run debug notification | Task 10 |
| Structural validation | Task 11 |
| README entry | Task 12 |
| Testing — mental-simulation checklist (all 11 spec bullets) | Task 13 |
| Requirements doc | Task 1 |

Every spec section is covered. The spec's testing-checklist bullets map to Task 13 Steps 5–11.

### 2. Placeholder scan

No `TBD`, `TODO`, `FIXME`, `...`, "similar to Task N", or "same as above". Every task body shows the complete YAML for its section. The only intentional in-flight placeholders are `action: []` (Task 4, replaced in Task 5) and the deliberately-unclosed `choose:` at the end of Task 8 (extended in Task 9) — both are explicitly flagged in the task text and pass YAML validation as written.

### 3. Type consistency

- `!input` pass-through variable names in Task 4 exactly match the input keys from Tasks 2–3 (32 ↔ 32; verified by Task 3 Step 3 and Task 11).
- Runtime variable names are introduced once and referenced consistently: `warmest_bedroom`, `ac_is_running`, `current_setpoint_known`, `lead`, `phase`, `desired_mode`, `effective_drive`, `maintaining_setpoint`, `lead_bias_entity`, `lead_bias_configured` — defined in Tasks 5–6, consumed in Tasks 7–10.
- Phase string literals are consistent: `DAY_OFF`, `PRECOOL`, `BEDTIME_LOCK`, `DEEP_NIGHT_CHECK`, `NIGHT_HOLD`, `DEEP_HOLD` — the `phase` template emits exactly these and every dispatch branch matches one.
- All setpoint outputs are floats, clamped via `[[x, ac_min_temp]|max, ac_max_temp]|min`; `lead` is `int`; temperature comparisons use the `abs > 0.1` idempotency epsilon throughout.
- Fan modes are discovered from `ac_fan_modes` (never hard-coded); `current_fan` falls back to the string `'unknown'`, which can never equal a discovered mode, so the fan idempotency guard is safe when `fan_modes` is absent.

### 4. Pre-finalization validation performed

The full blueprint YAML was assembled, parsed with `pyyaml` (HA `!input` taught via `add_multi_constructor`), and structurally asserted before this plan was finalized: **32 inputs, 32 top-level variables, 3 triggers, 14 action steps, 6 phase-dispatch branches, 2 empty hold branches, `mode: restart`, `max_exceeded: silent`**. The overnight-wrap phase derivation was mentally simulated against 12 sample clock times (08:00 → 15:00 wrapping through midnight) plus the cool-day, warm-day, turn-on-latch, and mild→hot-flip cases — all produced the correct phase.

### 5. Deviation from the example plans (intentional)

The two example plans' YAML-validation command (`python3 -c "import yaml; yaml.safe_load(open('....yaml'))"`) **fails on `!input`** with stock `pyyaml` — verified against the committed `lg_ac_climate.yaml`. This plan's validation command adds `yaml.SafeLoader.add_multi_constructor('!', lambda l,s,n: None)` so the check actually passes. The heating-rack plan's `cd /Users/...` line is a hardcoded-macOS-path mistake and is deliberately **not** replicated — all commands here are cwd-relative from the repo root.

---

> **Truth Gate:** Codex's final step writes the completion sentinel as its last action — `printf '%s\\n' 'bedroom-precool' > /tmp/codex-done-bedroom-precool` — paired with codex-handoff's delete-first augment, so the file's existence on completion is positive proof the run reached the end of the plan rather than halting mid-task.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-22-bedroom-precool.md`. The blueprint work is on branch `feat/bedroom-precool`. Three execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batched with checkpoints.

**3. Codex Handoff** — hand the plan to Codex via the Stack A pipeline (`codex-handoff` → `/codex:rescue`); Tasks are mechanical Edit-and-validate, well suited to bundled routing. Tasks 13's user-facing import steps are reported back for the operator.

Which approach?
