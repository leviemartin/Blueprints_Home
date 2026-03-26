# Bathroom Ventilator Automation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Home Assistant blueprint that intelligently controls a bathroom exhaust fan using dew point comparison, shower detection, and scheduled air refresh cycles — optimized for the humid Dutch climate.

**Architecture:** Single blueprint YAML file following the project's established pattern: `!input` declarations, top-level `variables:` for entity mapping, `action:` block with computed variables and a priority-ordered `choose` block. Post-shower logic uses `repeat` with `until` for the minimum-run enforcement loop. `mode: single` to prevent overlapping runs.

**Tech Stack:** Home Assistant Blueprint YAML, Jinja2 templates, Magnus formula for dew point calculation.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `bathroom_ventilator.yaml` | Create | The complete blueprint |
| `requirements_bathroom_ventilator.md` | Create | Technical requirements document |
| `README.md` | Modify | Add entry for the new blueprint |

---

### Task 1: Create Requirements Document

**Files:**
- Create: `requirements_bathroom_ventilator.md`

- [ ] **Step 1: Write requirements document**

Create `requirements_bathroom_ventilator.md` with the following content:

```markdown
# Requirements: Bathroom Ventilator Blueprint

## Overview
An intelligent bathroom ventilator automation using dew point comparison for the Dutch climate (Laren, Netherlands). Controls an exhaust fan via a smart plug based on indoor/outdoor moisture conditions.

## Goals
1. **Humidity Management:** Keep bathroom humidity below 60% RH to prevent mold.
2. **Dew Point Intelligence:** Use indoor vs. outdoor dew point comparison (not raw RH%) to determine if ventilation is effective.
3. **Shower Detection:** Automatically detect showers via sustained motion + humidity spike, and ventilate for 15-45 min.
4. **Night Mode:** No fan activity between 22:00-05:30 except for shower detection.
5. **Air Refresh:** Periodic 10-min cycles every 3 hours (daytime only), toggleable for when trickle vents are installed.
6. **Mold Safety:** Force fan ON if humidity exceeds 85% for 60+ minutes, regardless of all other conditions.

## Hardware
- Smart plug (switch entity) controlling the ventilator
- Aqara temperature + humidity sensor (indoor)
- Philips Hue motion sensor
- OpenWeatherMap weather entity (outdoor temp + humidity)

## Key Thresholds (all configurable)
- Target humidity: 60% RH (fan stops below this)
- High humidity: 75% RH (non-shower ventilation trigger)
- Mold alarm: 85% RH sustained 60+ min
- Dew point delta minimum: 2.0°C (below this, ventilation is ineffective)
- Shower detection: 10% RH rise + 5 min sustained motion
- Hysteresis: 5% RH buffer to prevent cycling

## Dew Point Logic
Uses the Magnus formula to compute dew point from temperature and relative humidity:
- Td = (243.04 * alpha) / (17.625 - alpha)
- alpha = (17.625 * T) / (243.04 + T) + ln(RH / 100)

Ventilation is effective when indoor dew point exceeds outdoor dew point by > 2°C.

## Priority Order
1. Mold safety override (always)
2. Target achieved — stop fan
3. Post-shower ventilation (day + night)
4. High humidity, non-shower (day only, dew point gated)
5. Air refresh cycle (day only, humidity gated, toggleable)
6. Default — fan OFF
```

- [ ] **Step 2: Commit**

```bash
git add requirements_bathroom_ventilator.md
git commit -m "docs: add technical requirements for bathroom ventilator blueprint"
```

---

### Task 2: Blueprint Skeleton — Metadata, Inputs, Triggers, Variables

**Files:**
- Create: `bathroom_ventilator.yaml`

- [ ] **Step 1: Write the blueprint header and inputs**

Create `bathroom_ventilator.yaml` with the full `blueprint:` block including:

```yaml
blueprint:
  name: "Bathroom Ventilator v1.0.0"
  description: >
    **Version: 1.0.0**

    Intelligently controls a bathroom exhaust fan using dew point comparison
    for optimal humidity management in humid climates (e.g., Netherlands).

    **Features:**
    - Dew point-based ventilation decisions (smarter than RH% comparison)
    - Automatic shower detection (motion + humidity spike)
    - Night mode (22:00-05:30) — fan only runs after shower
    - Scheduled air refresh cycles (toggleable)
    - Mold safety override at 85% RH sustained

    **Requirements:**
    - Smart plug (switch) controlling the exhaust fan
    - Indoor temperature + humidity sensor (e.g., Aqara)
    - Motion sensor (e.g., Philips Hue)
    - Weather entity with outdoor temp + humidity (e.g., OpenWeatherMap)

  domain: automation
  input:
    # --- DEVICES ---
    fan_switch:
      name: Fan Switch
      description: Smart plug controlling the bathroom ventilator.
      selector:
        entity:
          domain: switch
    humidity_sensor:
      name: Humidity Sensor
      description: Indoor bathroom humidity sensor.
      selector:
        entity:
          domain: sensor
          device_class: humidity
    temperature_sensor:
      name: Temperature Sensor
      description: Indoor bathroom temperature sensor (for dew point calculation).
      selector:
        entity:
          domain: sensor
          device_class: temperature
    motion_sensor:
      name: Motion Sensor
      description: Bathroom motion sensor for shower detection.
      selector:
        entity:
          domain: binary_sensor
          device_class: motion
    weather_entity:
      name: Weather Entity
      description: "Weather entity for outdoor conditions (e.g., weather.openweathermap)."
      selector:
        entity:
          domain: weather

    # --- HUMIDITY THRESHOLDS ---
    target_humidity:
      name: Target Humidity (%)
      description: Fan stops when indoor humidity drops below this.
      default: 60
      selector:
        number:
          min: 40
          max: 80
          step: 5
          unit_of_measurement: "%"
    high_humidity:
      name: High Humidity Trigger (%)
      description: Non-shower ventilation activates above this.
      default: 75
      selector:
        number:
          min: 60
          max: 90
          step: 5
          unit_of_measurement: "%"
    mold_humidity:
      name: Mold Safety Threshold (%)
      description: Force fan ON if humidity exceeds this for 60+ minutes.
      default: 85
      selector:
        number:
          min: 75
          max: 95
          step: 5
          unit_of_measurement: "%"
    dew_point_delta_min:
      name: Minimum Dew Point Delta (°C)
      description: "Ventilation is only effective when indoor dew point exceeds outdoor by at least this much."
      default: 2.0
      selector:
        number:
          min: 0.5
          max: 5.0
          step: 0.5
          unit_of_measurement: "°C"

    # --- SHOWER DETECTION ---
    shower_humidity_rise:
      name: Shower Humidity Rise (%)
      description: "RH% increase (from motion start) that indicates a shower."
      default: 10
      selector:
        number:
          min: 5
          max: 25
          step: 1
          unit_of_measurement: "%"
    shower_motion_minutes:
      name: Shower Motion Duration (min)
      description: Minimum sustained motion to qualify as a shower.
      default: 5
      selector:
        number:
          min: 2
          max: 15
          step: 1
          unit_of_measurement: min

    # --- TIMER SETTINGS ---
    post_shower_min_runtime:
      name: Post-Shower Minimum Run (min)
      description: Minimum fan run time after shower detection.
      default: 15
      selector:
        number:
          min: 5
          max: 30
          step: 5
          unit_of_measurement: min
    post_shower_max_runtime:
      name: Post-Shower Maximum Run (min)
      description: Hard maximum fan run time after shower.
      default: 45
      selector:
        number:
          min: 15
          max: 90
          step: 5
          unit_of_measurement: min
    high_humidity_max_runtime:
      name: High Humidity Maximum Run (min)
      description: Maximum fan run for non-shower high humidity events.
      default: 30
      selector:
        number:
          min: 10
          max: 60
          step: 5
          unit_of_measurement: min

    # --- AIR REFRESH ---
    enable_refresh_cycles:
      name: Enable Air Refresh Cycles
      description: "Periodic fan runs for air quality. Disable once trickle vents are installed."
      default: true
      selector:
        boolean:
    refresh_interval_hours:
      name: Refresh Interval (hours)
      description: Hours between air refresh cycles.
      default: 3
      selector:
        number:
          min: 1
          max: 6
          step: 1
          unit_of_measurement: h
    refresh_duration_minutes:
      name: Refresh Duration (min)
      description: How long each refresh cycle runs.
      default: 10
      selector:
        number:
          min: 5
          max: 20
          step: 5
          unit_of_measurement: min
    refresh_skip_below:
      name: Refresh Skip Below (%)
      description: Skip refresh cycle if humidity is already below this.
      default: 55
      selector:
        number:
          min: 40
          max: 70
          step: 5
          unit_of_measurement: "%"

    # --- SCHEDULE ---
    night_start:
      name: Night Start (Quiet Hours)
      description: Fan will not run for non-shower events after this time.
      default: "22:00:00"
      selector:
        time:
    night_end:
      name: Night End (Quiet Hours)
      description: Normal fan operation resumes at this time.
      default: "05:30:00"
      selector:
        time:
```

- [ ] **Step 2: Add mode, triggers, and top-level variables**

Append below the `input:` block:

```yaml
mode: single
max_exceeded: silent

trigger:
  # T1: Humidity changes
  - platform: state
    entity_id: !input humidity_sensor
    id: "humidity_change"

  # T2: Motion starts
  - platform: state
    entity_id: !input motion_sensor
    to: "on"
    id: "motion_on"

  # T3: Motion stops
  - platform: state
    entity_id: !input motion_sensor
    to: "off"
    id: "motion_off"

  # T4: Periodic evaluation (every 5 min)
  - platform: time_pattern
    minutes: "/5"
    id: "periodic_eval"

  # T5: HA restart
  - platform: homeassistant
    event: start
    id: "ha_start"

variables:
  # --- Entity Mappings ---
  entity_fan: !input fan_switch
  sensor_humidity: !input humidity_sensor
  sensor_temperature: !input temperature_sensor
  sensor_motion: !input motion_sensor
  entity_weather: !input weather_entity

  # --- Thresholds ---
  thresh_target: !input target_humidity
  thresh_high: !input high_humidity
  thresh_mold: !input mold_humidity
  dp_delta_min: !input dew_point_delta_min
  shower_rh_rise: !input shower_humidity_rise
  shower_motion_min: !input shower_motion_minutes

  # --- Timers ---
  shower_min_run: !input post_shower_min_runtime
  shower_max_run: !input post_shower_max_runtime
  high_hum_max_run: !input high_humidity_max_runtime

  # --- Refresh ---
  refresh_enabled: !input enable_refresh_cycles
  refresh_interval: !input refresh_interval_hours
  refresh_duration: !input refresh_duration_minutes
  refresh_skip: !input refresh_skip_below

  # --- Schedule ---
  t_night_start: !input night_start
  t_night_end: !input night_end
```

- [ ] **Step 3: Commit**

```bash
git add bathroom_ventilator.yaml
git commit -m "feat(ventilator): add blueprint skeleton with inputs, triggers, and variables"
```

---

### Task 3: Action Block — Computed Variables and Validation

**Files:**
- Modify: `bathroom_ventilator.yaml` (append `action:` block)

- [ ] **Step 1: Add computed variables inside the action block**

Add the `action:` block starting with a `variables:` step. This computes all runtime values including dew points, decision flags, and shower detection.

```yaml
action:
  # =============================================
  # STEP 1: COMPUTE VARIABLES
  # =============================================
  - variables:
      # --- Sensor Readings ---
      indoor_temp: "{{ states(sensor_temperature) | float(20) }}"
      indoor_rh: "{{ states(sensor_humidity) | float(50) }}"
      outdoor_temp: "{{ state_attr(entity_weather, 'temperature') | float(15) }}"
      outdoor_rh: "{{ state_attr(entity_weather, 'humidity') | float(50) }}"

      # --- Dew Point (Magnus Formula) ---
      indoor_dp: >-
        {% set T = indoor_temp | float %}
        {% set RH = [indoor_rh | float, 1] | max %}
        {% set a = 17.625 %}
        {% set b = 243.04 %}
        {% set alpha = (a * T) / (b + T) + log(RH / 100.0) %}
        {{ (b * alpha / (a - alpha)) | round(1) }}
      outdoor_dp: >-
        {% set T = outdoor_temp | float %}
        {% set RH = [outdoor_rh | float, 1] | max %}
        {% set a = 17.625 %}
        {% set b = 243.04 %}
        {% set alpha = (a * T) / (b + T) + log(RH / 100.0) %}
        {{ (b * alpha / (a - alpha)) | round(1) }}

      # --- Decision Variables ---
      dp_delta: "{{ (indoor_dp | float - outdoor_dp | float) | round(1) }}"
      ventilation_effective: "{{ dp_delta | float > dp_delta_min | float }}"
      fan_is_on: "{{ is_state(entity_fan, 'on') }}"
      is_night: >-
        {% set t = now().strftime('%H:%M') %}
        {{ t >= t_night_start[:5] or t < t_night_end[:5] }}

      # --- Shower Detection ---
      # Shower detection uses a different approach than a persisted baseline.
      # Since blueprint variables don't persist across runs, we detect showers
      # by checking: (1) motion has been sustained for shower_motion_min, AND
      # (2) current humidity is significantly above the typical comfortable
      # range (thresh_high). This avoids the need for a persisted baseline.
      # The humidity_change trigger (T1) combined with motion_on (T2) timing
      # gives us the detection window.
      motion_is_on: "{{ is_state(sensor_motion, 'on') }}"
      motion_sustained: >-
        {{ is_state(sensor_motion, 'on') and
           (now() - states[sensor_motion].last_changed).total_seconds()
           > (shower_motion_min | int * 60) }}
      shower_detected: >-
        {{ motion_sustained and
           indoor_rh | float > (thresh_high | float - shower_rh_rise | float) }}

      # --- Hysteresis (5% buffer above target for P4 re-trigger) ---
      high_hum_trigger_point: >-
        {% if fan_is_on %}
          {{ thresh_target | float }}
        {% else %}
          {{ thresh_target | float + 5 }}
        {% endif %}

      # --- Mold Check (fan state proxy for duration) ---
      # If humidity > mold threshold and fan has been off for 60+ min,
      # this indicates sustained high humidity without ventilation
      mold_risk: >-
        {% set rh = indoor_rh | float %}
        {% set threshold = thresh_mold | float %}
        {% if rh < threshold %}
          false
        {% elif fan_is_on %}
          false
        {% else %}
          {% set fan_off_seconds = (now() - states[entity_fan].last_changed).total_seconds() %}
          {{ fan_off_seconds > 3600 }}
        {% endif %}

      # --- Fan Runtime Tracking ---
      fan_on_minutes: >-
        {% if not fan_is_on %}
          0
        {% else %}
          {{ ((now() - states[entity_fan].last_changed).total_seconds() / 60) | round(0) | int }}
        {% endif %}
      high_hum_max_exceeded: >-
        {{ fan_is_on and
           fan_on_minutes | int >= high_hum_max_run | int and
           not shower_detected }}

      # --- Refresh Timing ---
      # Check if enough time has passed since fan was last on
      minutes_since_fan_off: >-
        {% if fan_is_on %}
          0
        {% else %}
          {{ ((now() - states[entity_fan].last_changed).total_seconds() / 60) | round(0) | int }}
        {% endif %}
      refresh_due: >-
        {{ refresh_enabled and
           not is_night and
           indoor_rh | float > refresh_skip | float and
           minutes_since_fan_off | int >= (refresh_interval | int * 60) }}
```

- [ ] **Step 2: Add sensor validation step**

Add after the computed variables:

```yaml
  # =============================================
  # STEP 2: SENSOR VALIDATION
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: >-
              {{ states(sensor_humidity) in ['unavailable', 'unknown'] or
                 states(sensor_temperature) in ['unavailable', 'unknown'] }}
        sequence:
          - service: persistent_notification.create
            data:
              title: "Ventilator Blueprint — Sensor Warning"
              message: >
                Bathroom sensors unavailable. Fan holding current state.
                Humidity: {{ states(sensor_humidity) }},
                Temperature: {{ states(sensor_temperature) }}
              notification_id: "ventilator_sensor_warning"
          - stop: "Sensors unavailable"
```

- [ ] **Step 3: Commit**

```bash
git add bathroom_ventilator.yaml
git commit -m "feat(ventilator): add computed variables — dew point, shower detection, validation"
```

---

### Task 4: Main Priority Choose Block — Priorities 1-3

**Files:**
- Modify: `bathroom_ventilator.yaml` (append to action block)

- [ ] **Step 1: Add priorities 1-3 of the choose block**

Add the main choose block with mold safety, target achieved, and post-shower logic:

```yaml
  # =============================================
  # STEP 3: MAIN PRIORITY CHOOSE
  # =============================================
  - choose:
      # --- P1: MOLD SAFETY OVERRIDE ---
      - conditions:
          - condition: template
            value_template: "{{ mold_risk }}"
        sequence:
          - service: switch.turn_on
            target:
              entity_id: "{{ entity_fan }}"
          - service: persistent_notification.create
            data:
              title: "Ventilator — Mold Safety Override"
              message: >
                Fan forced ON: humidity {{ indoor_rh }}% has exceeded
                {{ thresh_mold }}% for 60+ minutes. Indoor DP: {{ indoor_dp }}°C,
                Outdoor DP: {{ outdoor_dp }}°C.
              notification_id: "ventilator_mold_warning"

      # --- P2: TARGET ACHIEVED — STOP ---
      - conditions:
          - condition: template
            value_template: "{{ fan_is_on and indoor_rh | float < thresh_target | float }}"
        sequence:
          - service: switch.turn_off
            target:
              entity_id: "{{ entity_fan }}"

      # --- P3: POST-SHOWER VENTILATION ---
      - conditions:
          - condition: template
            value_template: "{{ shower_detected }}"
        sequence:
          - service: switch.turn_on
            target:
              entity_id: "{{ entity_fan }}"
          # Minimum run: wait the guaranteed minimum time
          - delay:
              minutes: !input post_shower_min_runtime
          # Recheck loop: every 5 min, stop if conditions met or max reached
          - repeat:
              until:
                - condition: template
                  value_template: >-
                    {% set rh_now = states(sensor_humidity) | float(50) %}
                    {% set T_in = states(sensor_temperature) | float(20) %}
                    {% set RH_in = [rh_now, 1] | max %}
                    {% set a = 17.625 %}
                    {% set b = 243.04 %}
                    {% set alpha_in = (a * T_in) / (b + T_in) + log(RH_in / 100.0) %}
                    {% set dp_in = (b * alpha_in / (a - alpha_in)) | round(1) %}
                    {% set T_out = state_attr(entity_weather, 'temperature') | float(15) %}
                    {% set RH_out = [state_attr(entity_weather, 'humidity') | float(50), 1] | max %}
                    {% set alpha_out = (a * T_out) / (b + T_out) + log(RH_out / 100.0) %}
                    {% set dp_out = (b * alpha_out / (a - alpha_out)) | round(1) %}
                    {% set delta = dp_in - dp_out %}
                    {% set elapsed = (shower_min_run | int) + (repeat.index * 5) %}
                    {{ rh_now < thresh_target | float or
                       delta < dp_delta_min | float or
                       elapsed >= shower_max_run | int }}
              sequence:
                - delay:
                    minutes: 5
          - service: switch.turn_off
            target:
              entity_id: "{{ entity_fan }}"
```

- [ ] **Step 2: Commit**

```bash
git add bathroom_ventilator.yaml
git commit -m "feat(ventilator): add priorities 1-3 — mold safety, target stop, post-shower"
```

---

### Task 5: Main Priority Choose Block — Priorities 4-6

**Files:**
- Modify: `bathroom_ventilator.yaml` (append to choose block)

- [ ] **Step 1: Add priorities 4-6 to the choose block**

Add high humidity, air refresh, and default-off logic:

```yaml
      # --- P4: HIGH HUMIDITY (NON-SHOWER) ---
      - conditions:
          - condition: template
            value_template: >-
              {{ indoor_rh | float > high_hum_trigger_point | float and
                 ventilation_effective and
                 not is_night and
                 not high_hum_max_exceeded }}
        sequence:
          - service: switch.turn_on
            target:
              entity_id: "{{ entity_fan }}"
          # Fan stays on; T4 periodic trigger will re-evaluate.
          # P2 (target achieved) or P6 (default off) will stop it.

      # --- P5: AIR REFRESH CYCLE ---
      - conditions:
          - condition: template
            value_template: "{{ refresh_due }}"
        sequence:
          - service: switch.turn_on
            target:
              entity_id: "{{ entity_fan }}"
          - delay:
              minutes: !input refresh_duration_minutes
          - service: switch.turn_off
            target:
              entity_id: "{{ entity_fan }}"

      # --- P6: DEFAULT — FAN OFF ---
      # Catches: fan left on with no active reason, max runtime exceeded,
      # ventilation no longer effective, or any other unmatched state.
      - conditions:
          - condition: template
            value_template: "{{ fan_is_on }}"
        sequence:
          - service: switch.turn_off
            target:
              entity_id: "{{ entity_fan }}"
```

- [ ] **Step 3: Commit**

```bash
git add bathroom_ventilator.yaml
git commit -m "feat(ventilator): add priorities 4-6 — high humidity, refresh cycles, default-off"
```

---

### Task 6: Debug Notification (Manual Run Support)

**Files:**
- Modify: `bathroom_ventilator.yaml` (add debug notification at end of action block)

- [ ] **Step 1: Add debug persistent notification**

After the main `choose` block (at the end of the `action:` list), add a debug notification that fires on every run — useful for manual "Run" testing:

```yaml
  # =============================================
  # STEP 4: DEBUG NOTIFICATION (Manual Run)
  # =============================================
  - service: persistent_notification.create
    data:
      title: "Ventilator Debug — {{ now().strftime('%H:%M:%S') }}"
      message: >
        **Indoor:** {{ indoor_temp }}°C / {{ indoor_rh }}% RH / DP {{ indoor_dp }}°C

        **Outdoor:** {{ outdoor_temp }}°C / {{ outdoor_rh }}% RH / DP {{ outdoor_dp }}°C

        **DP Delta:** {{ dp_delta }}°C (effective: {{ ventilation_effective }})

        **Fan:** {{ 'ON' if fan_is_on else 'OFF' }} (on for {{ fan_on_minutes }}min)

        **Night:** {{ is_night }} | **Motion:** {{ motion_is_on }} (sustained: {{ motion_sustained }})

        **Shower:** {{ shower_detected }} | **Mold Risk:** {{ mold_risk }}

        **Refresh:** enabled={{ refresh_enabled }}, due={{ refresh_due }}, last off={{ minutes_since_fan_off }}min ago

        **Trigger:** {{ trigger.id | default('manual') }}
      notification_id: "ventilator_debug"
```

**Note:** This notification fires on every trigger including T4 (every 5 min). For production use, consider wrapping it in a condition that only fires on manual runs or adding a debug toggle input. For v1.0.0 this is acceptable — it overwrites itself each time (same `notification_id`) so only the latest state is visible.

- [ ] **Step 2: Commit**

```bash
git add bathroom_ventilator.yaml
git commit -m "feat(ventilator): add debug persistent notification for manual run testing"
```

---

### Task 7: Requirements Doc and README Update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Read current README.md**

Read `README.md` to understand the existing structure and add an entry for the new blueprint.

- [ ] **Step 2: Add bathroom ventilator entry to README**

Add a section for the bathroom ventilator blueprint following the same format as existing entries. Include:
- Blueprint name and version
- Brief description (dew point-based humidity management for Dutch climate)
- Import link (raw GitHub URL to `bathroom_ventilator.yaml`)
- List of required entities

- [ ] **Step 3: Commit**

```bash
git add README.md requirements_bathroom_ventilator.md
git commit -m "docs: add bathroom ventilator blueprint to README and requirements"
```

---

### Task 8: Final Review and Version Verification

**Files:**
- Review: `bathroom_ventilator.yaml` (full file read-through)

- [ ] **Step 1: Read the complete blueprint file**

Read `bathroom_ventilator.yaml` from top to bottom to verify:
- All inputs are referenced in `variables:` mapping
- All `!input` references in triggers are correct
- All computed variables in action block reference the correct variable names (not input names)
- Dew point formula is identical for indoor and outdoor
- Priority order matches spec (P1: mold, P2: target stop, P3: shower, P4: high humidity, P5: refresh, P6: default off)
- `mode: single` is set
- YAML indentation is correct throughout

- [ ] **Step 2: Cross-check against spec**

Compare the completed blueprint against `docs/superpowers/specs/2026-03-26-bathroom-ventilator-design.md`:
- All inputs from the spec are present
- All triggers from the spec are present
- All priority conditions match the spec
- Edge case handling (sensor unavailable, night shower, etc.) is covered

- [ ] **Step 3: Fix any issues found**

Address any discrepancies, typos, or missing elements.

- [ ] **Step 4: Final commit if changes were made**

```bash
git add bathroom_ventilator.yaml
git commit -m "fix(ventilator): address review findings before release"
```
