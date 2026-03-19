# LG AC Climate Control Blueprint — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single Home Assistant blueprint YAML file (`lg_ac_climate.yaml`) that automates LG air conditioners per-floor with external temperature sensors, automatic heat/cool/off mode selection, outdoor-aware deadband, proportional fan control with escalation, per-day schedules, vacation mode, door sensor, and sound muting.

**Architecture:** Single monolithic blueprint following existing repository patterns. All logic in one YAML file using nested `choose` blocks, Jinja2 templates for computed variables, and a 10-minute `time_pattern` control loop. Sequential action steps: mute sound → compute variables → validate → main priority choose.

**Tech Stack:** Home Assistant Blueprint YAML, Jinja2 templating

**Spec:** `docs/superpowers/specs/2026-03-19-lg-ac-climate-control-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| **Create:** `lg_ac_climate.yaml` | The complete blueprint — inputs, triggers, variables, action logic |
| **Create:** `requirements_lg_ac_climate.md` | Technical requirements doc (follows existing pattern) |

---

### Task 1: Blueprint Skeleton — Metadata, Inputs (Devices & Comfort)

**Files:**
- Create: `lg_ac_climate.yaml`

Write the blueprint header (name, description, domain) and the first two input groups: Devices and Comfort Range.

- [ ] **Step 1: Create the blueprint file with metadata and device inputs**

```yaml
blueprint:
  name: "LG AC Climate Control v1.0.0"
  description: >
    **Version: 1.0.0**

    Automates LG air conditioners per-floor using external temperature sensors
    for reliable ambient readings.

    **Features:**
    - **Automatic Mode Selection:** Heats, cools, or turns off based on a
      configurable comfort range.
    - **Outdoor-Aware Deadband:** Disables deadband in extreme weather to
      prevent energy-wasting on/off cycling.
    - **Proportional Fan + Escalation:** Fan speed scales with distance from
      target, with time-based escalation if the target isn't reached.
    - **Per-Day Schedule:** Independent start/end times for each day of the week.
    - **Vacation Mode:** Toggle to force AC fully off.
    - **Door Sensor:** Auto-off when garden door is left open.
    - **Sound Mute:** Silences AC beep notifications.

    **Requirements:**
    - LG AC connected via SmartThinQ or LG ThinQ integration
    - External temperature sensor(s) (e.g., Aqara)
    - Outdoor temperature sensor
    - input_boolean helper for vacation mode

  domain: automation
  input:
    # --- DEVICES ---
    climate_entity:
      name: LG AC Climate Entity
      description: The climate entity for your LG air conditioner.
      selector:
        entity:
          domain: climate
    temperature_sensors:
      name: Temperature Sensors
      description: One or more Aqara (or other) temperature sensors for this floor.
      selector:
        entity:
          domain: sensor
          device_class: temperature
          multiple: true
    sensor_strategy:
      name: Sensor Aggregation Strategy
      description: "How to combine multiple sensor readings: average, min, or max."
      default: "average"
      selector:
        select:
          options:
            - label: "Average"
              value: "average"
            - label: "Minimum"
              value: "min"
            - label: "Maximum"
              value: "max"
    ac_sound_switch:
      name: AC Sound Switch (Optional)
      description: The switch entity for the AC beep sound. Leave empty if not available.
      default: []
      selector:
        entity:
          domain: switch
          multiple: true
    outdoor_temp_sensor:
      name: Outdoor Temperature Sensor
      description: An outdoor temperature sensor entity (not a weather entity).
      selector:
        entity:
          domain: sensor
          device_class: temperature
    door_sensor:
      name: Door Sensor (Optional)
      description: Garden/balcony door contact sensor(s). AC turns off when door is left open.
      default: []
      selector:
        entity:
          domain: binary_sensor
          multiple: true

    # --- COMFORT RANGE ---
    temp_range_low:
      name: Comfort Range — Low (°C)
      description: Lower bound of comfort range. AC heats if room drops below this.
      default: 20.0
      selector:
        number:
          min: 10.0
          max: 30.0
          step: 0.5
          unit_of_measurement: "°C"
    temp_range_high:
      name: Comfort Range — High (°C)
      description: Upper bound of comfort range. AC cools if room rises above this.
      default: 24.0
      selector:
        number:
          min: 10.0
          max: 30.0
          step: 0.5
          unit_of_measurement: "°C"
    deadband_outdoor_threshold:
      name: Deadband Outdoor Threshold (°C)
      description: "If outdoor temp is this far from the comfort range, deadband is disabled and AC holds in maintenance mode instead of cycling."
      default: 10.0
      selector:
        number:
          min: 0.0
          max: 25.0
          step: 0.5
          unit_of_measurement: "°C"
```

- [ ] **Step 2: Verify YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('lg_ac_climate.yaml'))" && echo "VALID"`
Expected: `VALID`

- [ ] **Step 3: Commit**

```bash
git add lg_ac_climate.yaml
git commit -m "feat(ac): add blueprint skeleton with metadata and device/comfort inputs"
```

---

### Task 2: Inputs — Schedule, Vacation, Fan, Door

**Files:**
- Modify: `lg_ac_climate.yaml`

Add the remaining input groups: per-day operating schedule (14 time inputs), vacation toggle, fan speed thresholds, escalation timeouts, and door delay.

- [ ] **Step 1: Add per-day schedule inputs**

Add under `input:` after the comfort range section:

```yaml
    # --- PER-DAY OPERATING SCHEDULE ---
    schedule_start_mon:
      name: "Monday — Start"
      default: "07:00:00"
      selector:
        time:
    schedule_end_mon:
      name: "Monday — End"
      default: "23:00:00"
      selector:
        time:
    schedule_start_tue:
      name: "Tuesday — Start"
      default: "07:00:00"
      selector:
        time:
    schedule_end_tue:
      name: "Tuesday — End"
      default: "23:00:00"
      selector:
        time:
    schedule_start_wed:
      name: "Wednesday — Start"
      default: "07:00:00"
      selector:
        time:
    schedule_end_wed:
      name: "Wednesday — End"
      default: "23:00:00"
      selector:
        time:
    schedule_start_thu:
      name: "Thursday — Start"
      default: "07:00:00"
      selector:
        time:
    schedule_end_thu:
      name: "Thursday — End"
      default: "23:00:00"
      selector:
        time:
    schedule_start_fri:
      name: "Friday — Start"
      default: "07:00:00"
      selector:
        time:
    schedule_end_fri:
      name: "Friday — End"
      default: "23:00:00"
      selector:
        time:
    schedule_start_sat:
      name: "Saturday — Start"
      default: "07:00:00"
      selector:
        time:
    schedule_end_sat:
      name: "Saturday — End"
      default: "23:00:00"
      selector:
        time:
    schedule_start_sun:
      name: "Sunday — Start"
      default: "07:00:00"
      selector:
        time:
    schedule_end_sun:
      name: "Sunday — End"
      default: "23:00:00"
      selector:
        time:
```

- [ ] **Step 2: Add vacation, fan, and door inputs**

```yaml
    # --- VACATION MODE ---
    vacation_toggle:
      name: Vacation Mode Toggle
      description: "An input_boolean helper. When ON, AC is forced fully off."
      selector:
        entity:
          domain: input_boolean

    # --- FAN SPEED & ESCALATION ---
    fan_speed_low_threshold:
      name: Fan Low Threshold (°C)
      description: "Distance from target below which fan = low."
      default: 1.0
      selector:
        number:
          min: 0.5
          max: 5.0
          step: 0.5
          unit_of_measurement: "°C"
    fan_speed_medium_threshold:
      name: Fan Medium Threshold (°C)
      description: "Distance from target for medium fan. Above this = high."
      default: 3.0
      selector:
        number:
          min: 1.0
          max: 10.0
          step: 0.5
          unit_of_measurement: "°C"
    escalation_stage_1_minutes:
      name: Escalation Stage 1 (min)
      description: "Minutes before first fan speed escalation."
      default: 20
      selector:
        number:
          min: 5
          max: 60
          unit_of_measurement: min
    escalation_stage_2_minutes:
      name: Escalation Stage 2 (min)
      description: "Minutes before second fan speed escalation (max speed)."
      default: 40
      selector:
        number:
          min: 10
          max: 120
          unit_of_measurement: min

    # --- DOOR ---
    door_off_delay:
      name: Door Open Delay (min)
      description: "Minutes to wait after door opens before shutting off AC."
      default: 5
      selector:
        number:
          min: 1
          max: 30
          unit_of_measurement: min
```

- [ ] **Step 3: Verify YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('lg_ac_climate.yaml'))" && echo "VALID"`
Expected: `VALID`

- [ ] **Step 4: Commit**

```bash
git add lg_ac_climate.yaml
git commit -m "feat(ac): add schedule, vacation, fan, and door inputs"
```

---

### Task 3: Triggers and Top-Level Variables

**Files:**
- Modify: `lg_ac_climate.yaml`

Add the `mode`, `max_exceeded`, triggers, and top-level variable mappings.

- [ ] **Step 1: Add mode, triggers, and variables**

Add after the closing of `input:`:

```yaml
mode: restart
max_exceeded: silent

trigger:
  # 1. Main Control Loop (every 10 minutes)
  - platform: time_pattern
    minutes: "/10"
    id: "update_loop"

  # 2. Vacation Mode ON
  - platform: state
    entity_id: !input vacation_toggle
    to: "on"
    id: "vacation_on"

  # 3. HA Restart
  - platform: homeassistant
    event: start
    id: "init"

variables:
  # --- Entity Mappings ---
  climate_ac: !input climate_entity
  sensors_temp: !input temperature_sensors
  strategy: !input sensor_strategy
  switch_sound: !input ac_sound_switch
  sensor_outdoor: !input outdoor_temp_sensor
  sensor_door: !input door_sensor
  entity_vacation: !input vacation_toggle

  # --- Comfort ---
  temp_low: !input temp_range_low
  temp_high: !input temp_range_high
  deadband_thresh: !input deadband_outdoor_threshold

  # --- Schedule (Start/End per day) ---
  t_start_mon: !input schedule_start_mon
  t_end_mon: !input schedule_end_mon
  t_start_tue: !input schedule_start_tue
  t_end_tue: !input schedule_end_tue
  t_start_wed: !input schedule_start_wed
  t_end_wed: !input schedule_end_wed
  t_start_thu: !input schedule_start_thu
  t_end_thu: !input schedule_end_thu
  t_start_fri: !input schedule_start_fri
  t_end_fri: !input schedule_end_fri
  t_start_sat: !input schedule_start_sat
  t_end_sat: !input schedule_end_sat
  t_start_sun: !input schedule_start_sun
  t_end_sun: !input schedule_end_sun

  # --- Fan ---
  fan_low_thresh: !input fan_speed_low_threshold
  fan_med_thresh: !input fan_speed_medium_threshold
  esc_stage_1: !input escalation_stage_1_minutes
  esc_stage_2: !input escalation_stage_2_minutes

  # --- Door ---
  door_delay: !input door_off_delay
```

- [ ] **Step 2: Verify YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('lg_ac_climate.yaml'))" && echo "VALID"`
Expected: `VALID`

- [ ] **Step 3: Commit**

```bash
git add lg_ac_climate.yaml
git commit -m "feat(ac): add triggers and top-level variable mappings"
```

---

### Task 4: Action Step 1 — Mute Sound (Standalone Pre-Step)

**Files:**
- Modify: `lg_ac_climate.yaml`

Add the action block starting with the standalone mute sound step. This runs BEFORE the main choose, following the pattern in `circadian_livingroom.yaml` and `adjacent_room_lights.yaml` where override checks are standalone choose blocks.

- [ ] **Step 1: Add the mute sound action**

Add after `variables:`:

```yaml
action:
  # =============================================
  # STEP 1: MUTE SOUND (standalone, always runs)
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: >
              {{ switch_sound not in [[], none, ''] and
                 expand(switch_sound) | selectattr('state', 'eq', 'on') | list | count > 0 }}
        sequence:
          - service: switch.turn_off
            target:
              entity_id: "{{ switch_sound }}"
```

**Pattern reference:** This mirrors `circadian_livingroom.yaml:330-335` and `adjacent_room_lights.yaml:353-358` where standalone `choose` blocks handle pre-checks before the main logic. The `lg_sleep_movie.yaml:71` uses the same `{{ target_sound != [] }}` pattern for optional sound switches.

- [ ] **Step 2: Verify YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('lg_ac_climate.yaml'))" && echo "VALID"`
Expected: `VALID`

- [ ] **Step 3: Commit**

```bash
git add lg_ac_climate.yaml
git commit -m "feat(ac): add mute sound pre-step action"
```

---

### Task 5: Action Step 2 — Computed Variables

**Files:**
- Modify: `lg_ac_climate.yaml`

Add the computed variables block inside the action. This is the core logic block that calculates all runtime state. Follows the pattern from `circadian_livingroom.yaml:338-378` and `adjacent_room_lights.yaml:361-394`.

- [ ] **Step 1: Add the computed variables action block**

Add after Step 1 (mute sound) in the action block:

```yaml
  # =============================================
  # STEP 2: COMPUTE VARIABLES
  # =============================================
  - variables:
      # --- Sensor Aggregation ---
      valid_temps: >
        {% set ns = namespace(vals=[]) %}
        {% for s in sensors_temp %}
          {% set v = states(s) %}
          {% if v not in ['unavailable', 'unknown', none] and v | float(none) is not none %}
            {% set ns.vals = ns.vals + [v | float] %}
          {% endif %}
        {% endfor %}
        {{ ns.vals }}
      sensors_available: "{{ valid_temps | length > 0 }}"
      current_temp: >
        {% if valid_temps | length == 0 %}
          {{ 0 }}
        {% elif strategy == 'min' %}
          {{ valid_temps | min }}
        {% elif strategy == 'max' %}
          {{ valid_temps | max }}
        {% else %}
          {{ ((valid_temps | sum) / (valid_temps | length)) | round(1) }}
        {% endif %}

      # --- Outdoor ---
      outdoor_temp: "{{ states(sensor_outdoor) | float(0) }}"

      # --- Vacation ---
      is_vacation: "{{ is_state(entity_vacation, 'on') }}"

      # --- Door ---
      door_is_open: >
        {% if sensor_door in [[], none, ''] %}
          false
        {% else %}
          {% set ns = namespace(open=false) %}
          {% for d in sensor_door %}
            {% if is_state(d, 'on') %}
              {% set opened_sec = as_timestamp(now()) - as_timestamp(states[d].last_changed) %}
              {% if opened_sec >= (door_delay | int * 60) %}
                {% set ns.open = true %}
              {% endif %}
            {% endif %}
          {% endfor %}
          {{ ns.open }}
        {% endif %}

      # --- Current AC State ---
      current_ac_mode: "{{ states(climate_ac) }}"

      # --- Per-Day Schedule ---
      schedule_start_today: >
        {{ [t_start_mon, t_start_tue, t_start_wed, t_start_thu, t_start_fri, t_start_sat, t_start_sun][now().weekday()] }}
      schedule_end_today: >
        {{ [t_end_mon, t_end_tue, t_end_wed, t_end_thu, t_end_fri, t_end_sat, t_end_sun][now().weekday()] }}
      in_operating_window: >
        {% set t_now = now().strftime('%H:%M:%S') %}
        {% set t_start = schedule_start_today %}
        {% set t_end = schedule_end_today %}
        {% if t_start <= t_end %}
          {{ t_start <= t_now < t_end }}
        {% else %}
          {{ t_now >= t_start or t_now < t_end }}
        {% endif %}

      # --- Target Mode & Distance ---
      target_mode: >
        {% if current_temp | float > temp_high | float %}
          cool
        {% elif current_temp | float < temp_low | float %}
          heat
        {% else %}
          off
        {% endif %}
      distance_from_target: >
        {% if current_temp | float > temp_high | float %}
          {{ (current_temp | float - temp_high | float) | round(1) }}
        {% elif current_temp | float < temp_low | float %}
          {{ (temp_low | float - current_temp | float) | round(1) }}
        {% else %}
          {{ 0 }}
        {% endif %}

      # --- Outdoor Distance & Deadband ---
      outdoor_distance: >
        {% set o = outdoor_temp | float %}
        {% set dist_low = (temp_low | float - o) | abs %}
        {% set dist_high = (o - temp_high | float) | abs %}
        {% if o < temp_low | float %}
          {{ dist_low | round(1) }}
        {% elif o > temp_high | float %}
          {{ dist_high | round(1) }}
        {% else %}
          {{ 0 }}
        {% endif %}
      deadband_active: "{{ outdoor_distance | float < deadband_thresh | float }}"

      # --- Fan Speed (Proportional) ---
      available_fan_modes: "{{ state_attr(climate_ac, 'fan_modes') | default(['low', 'mid', 'high'], true) }}"
      fan_mode_low: >
        {% set modes = available_fan_modes %}
        {% set ns = namespace(found='') %}
        {% for m in ['Low', 'low', '1'] if m in modes %}
          {% if ns.found == '' %}{% set ns.found = m %}{% endif %}
        {% endfor %}
        {{ ns.found if ns.found != '' else (modes[0] if modes | length > 0 else 'low') }}
      fan_mode_mid: >
        {% set modes = available_fan_modes %}
        {% set ns = namespace(found='') %}
        {% for m in ['Mid', 'Medium', 'mid', 'medium', '2'] if m in modes %}
          {% if ns.found == '' %}{% set ns.found = m %}{% endif %}
        {% endfor %}
        {{ ns.found if ns.found != '' else (modes[1] if modes | length > 1 else fan_mode_low) }}
      fan_mode_high: >
        {% set modes = available_fan_modes %}
        {% set ns = namespace(found='') %}
        {% for m in ['High', 'high', '3'] if m in modes %}
          {% if ns.found == '' %}{% set ns.found = m %}{% endif %}
        {% endfor %}
        {{ ns.found if ns.found != '' else (modes[2] if modes | length > 2 else fan_mode_mid) }}
      fan_mode_max: >
        {% set modes = available_fan_modes %}
        {% set ns = namespace(found='') %}
        {% for m in ['Power', 'Turbo', 'power', 'turbo', '4'] if m in modes %}
          {% if ns.found == '' %}{% set ns.found = m %}{% endif %}
        {% endfor %}
        {{ ns.found if ns.found != '' else fan_mode_high }}

      base_fan: >
        {% set dist = distance_from_target | float %}
        {% if dist < fan_low_thresh | float %}
          {{ fan_mode_low }}
        {% elif dist < fan_med_thresh | float %}
          {{ fan_mode_mid }}
        {% else %}
          {{ fan_mode_high }}
        {% endif %}

      # --- Escalation ---
      # NOTE: minutes_in_current_mode uses last_changed which resets on any
      # attribute update (including temperature reports). This means escalation
      # may not trigger as reliably as intended. A future v1.1 enhancement
      # could use an input_datetime helper to track mode-set time precisely.
      # The guard below ensures escalation resets to 0 when target_mode
      # differs from current mode (mode is changing or just changed).
      minutes_in_current_mode: >
        {% if target_mode != current_ac_mode %}
          0
        {% else %}
          {% set last = as_timestamp(states[climate_ac].last_changed) | default(as_timestamp(now())) %}
          {{ ((as_timestamp(now()) - last) / 60) | round(0) | int }}
        {% endif %}
      target_fan: >
        {% set mins = minutes_in_current_mode | int %}
        {% set fan_levels = [fan_mode_low, fan_mode_mid, fan_mode_high, fan_mode_max] %}
        {% set base_idx = fan_levels.index(base_fan) if base_fan in fan_levels else 0 %}
        {% if mins >= esc_stage_2 | int %}
          {{ fan_mode_max }}
        {% elif mins >= esc_stage_1 | int %}
          {{ fan_levels[[base_idx + 1, fan_levels | length - 1] | min] }}
        {% else %}
          {{ base_fan }}
        {% endif %}
```

**Key design decisions:**
- `valid_temps` uses a namespace loop to filter unavailable sensors (matches `expand()` + `selectattr()` pattern from `adjacent_room_lights.yaml:467-468`)
- Fan mode discovery reads `fan_modes` attribute and maps common LG ThinQ names (`Low`/`Mid`/`High`/`Power`) with fallbacks
- Schedule midnight-crossing handled with `if t_start <= t_end` check
- `minutes_in_current_mode` uses `last_changed` as baseline with a guard that resets to 0 when target_mode differs from current mode. Known limitation: `last_changed` also resets on attribute updates (temp reports), which may prevent escalation from triggering. Deferred to v1.1 for a more robust solution using `input_datetime` helper.
- Door logic handled entirely via computed variable `door_is_open` (no dedicated trigger) to avoid HA crash when door_sensor input is empty

- [ ] **Step 2: Verify YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('lg_ac_climate.yaml'))" && echo "VALID"`
Expected: `VALID`

- [ ] **Step 3: Commit**

```bash
git add lg_ac_climate.yaml
git commit -m "feat(ac): add computed variables block with sensor aggregation, schedule, fan logic"
```

---

### Task 6: Action Step 3 — Runtime Validation

**Files:**
- Modify: `lg_ac_climate.yaml`

Add the runtime validation step that guards against misconfigured comfort range.

- [ ] **Step 1: Add runtime validation**

Add after Step 2 (computed variables):

```yaml
  # =============================================
  # STEP 3: RUNTIME VALIDATION
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ temp_low | float >= temp_high | float }}"
        sequence:
          - service: persistent_notification.create
            data:
              title: "AC Climate Blueprint — Configuration Error"
              message: >
                Comfort range is misconfigured: Low ({{ temp_low }}°C) must be
                less than High ({{ temp_high }}°C). AC control is paused until
                this is corrected.
              notification_id: "ac_climate_config_error"
          - stop: "Comfort range misconfigured"
```

- [ ] **Step 2: Verify YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('lg_ac_climate.yaml'))" && echo "VALID"`
Expected: `VALID`

- [ ] **Step 3: Commit**

```bash
git add lg_ac_climate.yaml
git commit -m "feat(ac): add runtime validation for comfort range"
```

---

### Task 7: Action Step 4 — Main Priority Choose (Overrides: Sensors, Vacation, Window, Door)

**Files:**
- Modify: `lg_ac_climate.yaml`

Add the main `choose` block with the first four priority branches (4a-4d from spec): sensor check, vacation, operating window, door open.

- [ ] **Step 1: Add the main choose with override branches**

Add after Step 3 (validation):

```yaml
  # =============================================
  # STEP 4: MAIN PRIORITY CHOOSE
  # =============================================
  - choose:
      # --- 4a: SENSOR CHECK ---
      - conditions:
          - condition: template
            value_template: "{{ not sensors_available }}"
        sequence:
          - service: persistent_notification.create
            data:
              title: "AC Climate Blueprint — Sensor Warning"
              message: >
                All temperature sensors are unavailable. AC is holding current
                state until sensors recover. Sensors: {{ sensors_temp }}
              notification_id: "ac_climate_sensor_warning"
          - stop: "No sensors available"

      # --- 4a2: AC ENTITY UNAVAILABLE ---
      - conditions:
          - condition: template
            value_template: "{{ current_ac_mode in ['unavailable', 'unknown'] }}"
        sequence:
          - stop: "AC entity unavailable, retrying next loop"

      # --- 4b: VACATION MODE ---
      - conditions:
          - condition: template
            value_template: "{{ is_vacation }}"
        sequence:
          - condition: template
            value_template: "{{ current_ac_mode != 'off' }}"
          - service: climate.turn_off
            target:
              entity_id: "{{ climate_ac }}"

      # --- 4c: OUTSIDE OPERATING WINDOW ---
      - conditions:
          - condition: template
            value_template: "{{ not in_operating_window }}"
        sequence:
          - condition: template
            value_template: "{{ current_ac_mode != 'off' }}"
          - service: climate.turn_off
            target:
              entity_id: "{{ climate_ac }}"

      # --- 4d: DOOR OPEN ---
      # No dedicated trigger — door state is checked each loop cycle via
      # the door_is_open computed variable (includes duration check).
      # This avoids the HA crash when door_sensor is empty (optional input).
      - conditions:
          - condition: template
            value_template: "{{ door_is_open }}"
        sequence:
          - condition: template
            value_template: "{{ current_ac_mode != 'off' }}"
          - service: climate.turn_off
            target:
              entity_id: "{{ climate_ac }}"
```

**Pattern reference:** The `condition: template` guard before `climate.turn_off` prevents unnecessary service calls when the AC is already off — same pattern as `adjacent_room_lights.yaml` checking if lights are already on before updating.

- [ ] **Step 2: Verify YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('lg_ac_climate.yaml'))" && echo "VALID"`
Expected: `VALID`

- [ ] **Step 3: Commit**

```bash
git add lg_ac_climate.yaml
git commit -m "feat(ac): add override branches — sensor check, vacation, window, door"
```

---

### Task 8: Action Step 4 (continued) — Climate Control Branches (Deadband, Cool, Heat)

**Files:**
- Modify: `lg_ac_climate.yaml`

Add the remaining branches to the main `choose`: 4e (temp inside comfort range / deadband / maintenance), 4f (cool), 4g (heat).

- [ ] **Step 1: Add the climate control branches**

Add inside the main `choose` block (after branch 4d):

```yaml
      # --- 4e: TEMP INSIDE COMFORT RANGE ---
      - conditions:
          - condition: template
            value_template: "{{ target_mode == 'off' }}"
        sequence:
          - choose:
              # Deadband ACTIVE (mild outdoor) → turn off
              - conditions:
                  - condition: template
                    value_template: "{{ deadband_active }}"
                sequence:
                  - condition: template
                    value_template: "{{ current_ac_mode != 'off' }}"
                  - service: climate.turn_off
                    target:
                      entity_id: "{{ climate_ac }}"
              # Deadband DISABLED (extreme outdoor) → maintenance mode
              - conditions:
                  - condition: template
                    value_template: "{{ not deadband_active }}"
                sequence:
                  - service: climate.set_temperature
                    target:
                      entity_id: "{{ climate_ac }}"
                    data:
                      hvac_mode: >
                        {% if current_ac_mode in ['cool', 'heat'] %}
                          {{ current_ac_mode }}
                        {% elif current_temp | float >= ((temp_low | float + temp_high | float) / 2) %}
                          cool
                        {% else %}
                          heat
                        {% endif %}
                      temperature: >
                        {% if current_ac_mode == 'cool' %}
                          {{ temp_high }}
                        {% elif current_ac_mode == 'heat' %}
                          {{ temp_low }}
                        {% elif current_temp | float >= ((temp_low | float + temp_high | float) / 2) %}
                          {{ temp_high }}
                        {% else %}
                          {{ temp_low }}
                        {% endif %}
                  - service: climate.set_fan_mode
                    target:
                      entity_id: "{{ climate_ac }}"
                    data:
                      fan_mode: "{{ fan_mode_low }}"

      # --- 4f: COOL ---
      - conditions:
          - condition: template
            value_template: "{{ target_mode == 'cool' }}"
        sequence:
          - service: climate.set_temperature
            target:
              entity_id: "{{ climate_ac }}"
            data:
              hvac_mode: "cool"
              temperature: "{{ temp_high }}"
          - service: climate.set_fan_mode
            target:
              entity_id: "{{ climate_ac }}"
            data:
              fan_mode: "{{ target_fan }}"

      # --- 4g: HEAT ---
      - conditions:
          - condition: template
            value_template: "{{ target_mode == 'heat' }}"
        sequence:
          - service: climate.set_temperature
            target:
              entity_id: "{{ climate_ac }}"
            data:
              hvac_mode: "heat"
              temperature: "{{ temp_low }}"
          - service: climate.set_fan_mode
            target:
              entity_id: "{{ climate_ac }}"
            data:
              fan_mode: "{{ target_fan }}"
```

**Key design decisions:**
- Maintenance mode (4e, deadband disabled): when AC was already off and needs to pick a mode, it uses the midpoint of the comfort range to decide heat vs cool
- `climate.set_temperature` with `hvac_mode` in data payload combines mode+temp in one API call per spec
- `climate.set_fan_mode` is a separate call — this is necessary because HA's `climate.set_temperature` doesn't accept `fan_mode` in the data payload

- [ ] **Step 2: Verify YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('lg_ac_climate.yaml'))" && echo "VALID"`
Expected: `VALID`

- [ ] **Step 3: Commit**

```bash
git add lg_ac_climate.yaml
git commit -m "feat(ac): add climate control branches — deadband, cool, heat with fan control"
```

---

### Task 9: Requirements Documentation

**Files:**
- Create: `requirements_lg_ac_climate.md`

Write the technical requirements document following the existing pattern (see `requirements.md` for nightlight).

- [ ] **Step 1: Create the requirements doc**

```markdown
# LG AC Climate Control — Requirements

## Overview

Per-floor automated climate control for LG air conditioners using external
temperature sensors for reliable ambient readings. Optimizes for energy
efficiency through outdoor-aware deadband logic and proportional fan control.

## Hardware Requirements

- **AC Unit:** LG air conditioner connected via SmartThinQ or LG ThinQ
  integration (exposes a `climate` entity)
- **Temperature Sensors:** One or more per floor (e.g., Aqara WSDCGQ11LM)
- **Outdoor Sensor:** Any sensor entity with `device_class: temperature`
- **Door Sensor (Optional):** Binary sensor for garden/balcony door
- **Sound Switch (Optional):** The `switch` entity exposed by the LG
  integration for the AC's beep sound

## Home Assistant Requirements

- **input_boolean helper:** For vacation mode toggle
- **Integration:** SmartThinQ Sensors or LG ThinQ (cloud or local)

## Functional Requirements

### Climate Control
1. Automatic mode selection: heat if below range, cool if above, off if inside
2. Configurable comfort range with separate low/high bounds
3. Outdoor-aware deadband: when outdoor temp is extreme, AC holds in
   maintenance mode (low fan at boundary) instead of turning off
4. 10-minute polling loop for temperature checks

### Fan Control
1. Proportional fan speed based on distance from comfort boundary
2. Multi-stage time-based escalation when target isn't reached
3. Dynamic fan mode discovery from the climate entity's `fan_modes` attribute

### Scheduling
1. Per-day start/end operating times (7 pairs)
2. Overnight window support (e.g., 22:00 → 06:00)
3. AC turns off immediately when operating window ends

### Overrides
1. Vacation mode: forces AC fully off via input_boolean
2. Door sensor: AC turns off after configurable delay when door is left open
3. Sound mute: always keeps AC beep switch off

### Safety
1. Sensor failure: holds current AC state, fires persistent notification
2. Comfort range validation: blocks operation if low >= high
3. Graceful handling of AC entity unavailability
```

- [ ] **Step 2: Commit**

```bash
git add requirements_lg_ac_climate.md
git commit -m "docs(ac): add technical requirements for LG AC climate blueprint"
```

---

### Task 10: Final Validation & Integration Test

**Files:**
- Verify: `lg_ac_climate.yaml`

Final YAML validation and structural review.

- [ ] **Step 1: Full YAML validation**

Run: `python3 -c "import yaml; yaml.safe_load(open('lg_ac_climate.yaml'))" && echo "VALID"`
Expected: `VALID`

- [ ] **Step 2: Verify blueprint structure has all required sections**

Run: `python3 -c "
import yaml
with open('lg_ac_climate.yaml') as f:
    bp = yaml.safe_load(f)
assert 'blueprint' in bp, 'Missing blueprint key'
assert 'name' in bp['blueprint'], 'Missing name'
assert 'description' in bp['blueprint'], 'Missing description'
assert 'domain' in bp['blueprint'], 'Missing domain'
assert 'input' in bp['blueprint'], 'Missing input'
assert 'trigger' in bp, 'Missing trigger'
assert 'variables' in bp, 'Missing variables'
assert 'action' in bp, 'Missing action'
assert bp['mode'] == 'restart', 'Wrong mode'
inputs = bp['blueprint']['input']
# Verify key inputs exist
for key in ['climate_entity', 'temperature_sensors', 'sensor_strategy',
            'temp_range_low', 'temp_range_high', 'vacation_toggle',
            'outdoor_temp_sensor', 'schedule_start_mon', 'schedule_end_sun',
            'fan_speed_low_threshold', 'escalation_stage_1_minutes']:
    assert key in inputs, f'Missing input: {key}'
print(f'All checks passed. {len(inputs)} inputs, {len(bp[\"trigger\"])} triggers.')
"
`

Expected: `All checks passed. 28 inputs, 3 triggers.`

- [ ] **Step 3: Verify action structure**

Run: `python3 -c "
import yaml
with open('lg_ac_climate.yaml') as f:
    bp = yaml.safe_load(f)
actions = bp['action']
print(f'Action steps: {len(actions)}')
# Step 1: mute sound (choose)
assert 'choose' in actions[0], 'Step 1 should be choose (mute sound)'
# Step 2: computed variables
assert 'variables' in actions[1], 'Step 2 should be variables'
# Step 3: validation (choose)
assert 'choose' in actions[2], 'Step 3 should be choose (validation)'
# Step 4: main choose
assert 'choose' in actions[3], 'Step 4 should be choose (main logic)'
main_branches = actions[3]['choose']
print(f'Main choose branches: {len(main_branches)}')
print('Structure verified.')
"
`

Expected: `Action steps: 4` and `Main choose branches: 8` and `Structure verified.`

- [ ] **Step 4: Commit final state**

```bash
git add -A
git commit -m "feat(ac): LG AC Climate Control blueprint v1.0.0 complete"
```
