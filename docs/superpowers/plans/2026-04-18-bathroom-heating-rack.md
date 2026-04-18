# Bathroom Heating Rack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Home Assistant blueprint (`bathroom_heating_rack.yaml`) that pre-heats `climate.heatingrack_bathroom` for scheduled routines (adult morning, kids bath) with dynamic ΔT-based warmup, predictive-motion early-start, ventilator coordination, and ad-hoc boost.

**Architecture:** Single-file HA blueprint, `mode: restart`. Action block follows a 5-step pipeline: compute variables → sensor validation → boost-expiry cleanup → priority choose (P1–P6) → debug notification. State machine is stateless per-tick; motion "pulls forward" an `auto_start` that is computed dynamically from the current indoor-to-target ΔT. Idempotent service calls to `climate.set_hvac_mode` / `set_preset_mode` / `set_temperature`.

**Tech Stack:** Home Assistant 2026.x blueprint YAML, Jinja2 templates, `hass-cli` for template validation + live service calls, `python -c "import yaml"` for local syntax validation.

**Reference spec:** `docs/superpowers/specs/2026-04-18-bathroom-heating-rack-design.md`

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `bathroom_heating_rack.yaml` | **Create** | The blueprint itself — metadata, inputs, triggers, action pipeline |
| `requirements_bathroom_heating_rack.md` | **Create** | User-facing requirements doc (mirrors `requirements_bathroom_ventilator.md` pattern) |
| `README.md` | **Modify** | Add a section for the new blueprint under the existing blueprint index |

**Environment prerequisites already in place:**
- `HASS_SERVER=http://homeassistant.local:8123`, `HASS_TOKEN=…` exported in `~/.zshrc`
- `hass-cli` (v1.0.0) installed via Homebrew
- HA MCP server registered in Claude Code at user scope
- `climate.heatingrack_bathroom` entity confirmed present with attributes `hvac_modes=["off","heat_cool"]`, `preset_modes=["eco"]`

---

## Task 1: Write the requirements doc

**Files:**
- Create: `requirements_bathroom_heating_rack.md`

- [ ] **Step 1: Create `requirements_bathroom_heating_rack.md`**

````markdown
# Requirements: Bathroom Heating Rack Blueprint

## Overview
Pre-heats the bathroom using the smart heating rack (`climate.heatingrack_bathroom`) so it is at comfort temperature in time for scheduled routines — adult morning and kids bath — while idling in eco the rest of the day.

## Goals
1. **Scheduled pre-heat** with dynamic warmup based on current indoor-to-target ΔT (self-adjusts across seasons without calendar boundaries).
2. **Dual slot per phase:** Morning A (primary, default Mon–Fri) + Morning B (optional, weekend). Evening A (kids bath) + Evening B (optional adult evening).
3. **Predictive motion override:** hall motion pulls morning auto-start forward; stairs motion does the same for evening.
4. **Ad-hoc boost:** user-flipped `input_boolean` gives N minutes at a configurable boost temperature, then auto-expires.
5. **Ventilator coordination:** pause active heating (via `preset=eco`) while the bathroom exhaust fan is running — avoids evicting freshly heated air.
6. **Idle eco:** when no routine is active, hold `preset=eco` so the thermostat stays on a frost-protect floor and resumes quickly.
7. **Vacation / full-off:** optional `input_boolean` cleanly disables the whole blueprint.
8. **Idempotent:** ~1440 ticks/day but only 4–10 service calls/day (only on transitions).

## Hardware
- `climate.heatingrack_bathroom` — generic_thermostat wrapping the heating rack's smart plug (`switch.heating_switch`) with `sensor.bathroom_temperature` as the temp source
- `sensor.bathroom_temperature` (Aqara) — indoor temp for ΔT calculation (primary)
- `binary_sensor.hall_motion` — morning predictive-motion trigger
- `binary_sensor.stairs_motion` — evening predictive-motion trigger
- `light.heater` — ventilator smart plug, observed for coordination

## Warmup Formula
```
ΔT            = max(0, target_temp - indoor_temp)
warmup_min    = clamp(
                  warmup_base + warmup_per_degree * ΔT,
                  warmup_min_minutes, warmup_max_minutes
                )
auto_start    = target_warm − warmup_min minutes
```

## Priority Order
1. Vacation / Off (highest)
2. Ventilator coordination (pause via eco)
3. Ad-hoc Boost
4. Evening Routine (A or B)
5. Morning Routine (A or B)
6. Idle (default — mode=heat_cool, preset=eco)

## Testing & Debugging
Manual "Run" in HA produces a persistent notification dumping all computed variables (indoor temp, ΔT, warmup_min, each slot's auto_start / effective_start / active flags, current priority winner, service-call decisions).
````

- [ ] **Step 2: Commit**

```bash
git add requirements_bathroom_heating_rack.md
git commit -m "docs(heating-rack): add requirements document"
```

---

## Task 2: Scaffold blueprint — metadata and inputs

**Files:**
- Create: `bathroom_heating_rack.yaml`

- [ ] **Step 1: Create file with metadata + all 31 inputs**

```yaml
blueprint:
  name: "Bathroom Heating Rack v1.0.0"
  description: >
    **Version: 1.0.0**

    Pre-heats the bathroom heating rack for adult morning and kids bath
    routines using dynamic ΔT-based warmup, predictive motion override,
    and ventilator coordination.

    **Features:**
    - Dual-slot routines per phase (e.g., weekday + weekend morning)
    - Dynamic warmup: self-adjusts across seasons via indoor ΔT
    - Predictive motion: hall → morning; stairs → evening
    - Ad-hoc boost toggle with auto-expiry
    - Ventilator coordination via eco preset (no heat eviction)
    - Vacation / full-off toggle

  domain: automation
  input:
    # ----- DEVICES -----
    heating_climate:
      name: Heating Rack Climate Entity
      description: The climate entity wrapping the heating rack smart plug.
      selector:
        entity:
          domain: climate
    bathroom_temp_sensor:
      name: Bathroom Temperature Sensor
      description: Indoor bathroom temperature sensor (for ΔT-based warmup).
      selector:
        entity:
          domain: sensor
          device_class: temperature
    hall_motion:
      name: Hall Motion Sensor (Morning Predictor)
      selector:
        entity:
          domain: binary_sensor
          device_class: motion
    stairs_motion:
      name: Stairs Motion Sensor (Evening Predictor)
      selector:
        entity:
          domain: binary_sensor
          device_class: motion
    fan_switch:
      name: Ventilator Switch
      description: "The exhaust fan entity (coordination target). Matches bathroom_ventilator blueprint's light-domain convention."
      selector:
        entity:
          domain: light

    # ----- GLOBAL CONTROLS -----
    vacation_off:
      name: Vacation / Full-Off Toggle (Optional)
      description: "Optional input_boolean. When ON, heating rack is forced off."
      default: []
      selector:
        entity:
          domain: input_boolean
          multiple: true
    boost_toggle:
      name: Ad-hoc Boost Toggle
      description: "Input boolean. When turned ON, heats to boost_target_temp for boost_runtime_min then auto-turns-off."
      selector:
        entity:
          domain: input_boolean

    # ----- BOOST SETTINGS -----
    boost_target_temp:
      name: Boost Target Temperature (°C)
      default: 23
      selector:
        number: {min: 18, max: 28, step: 0.5, unit_of_measurement: "°C"}
    boost_runtime_min:
      name: Boost Runtime (min)
      default: 30
      selector:
        number: {min: 10, max: 120, step: 5, unit_of_measurement: "min"}

    # ----- MORNING A (PRIMARY) -----
    morning_a_days:
      name: Morning A Days
      default: ["mon", "tue", "wed", "thu", "fri"]
      selector:
        select:
          multiple: true
          options:
            - {label: Monday, value: mon}
            - {label: Tuesday, value: tue}
            - {label: Wednesday, value: wed}
            - {label: Thursday, value: thu}
            - {label: Friday, value: fri}
            - {label: Saturday, value: sat}
            - {label: Sunday, value: sun}
    morning_a_target_warm:
      name: Morning A Target-Warm Time
      default: "06:45:00"
      selector: {time: {}}
    morning_a_hold_until:
      name: Morning A Hold-Until Time
      default: "08:00:00"
      selector: {time: {}}
    morning_a_target_temp:
      name: Morning A Target Temperature (°C)
      default: 23
      selector:
        number: {min: 18, max: 28, step: 0.5, unit_of_measurement: "°C"}

    # ----- MORNING B (OPTIONAL) -----
    morning_b_days:
      name: Morning B Days (leave empty to disable)
      default: []
      selector:
        select:
          multiple: true
          options:
            - {label: Monday, value: mon}
            - {label: Tuesday, value: tue}
            - {label: Wednesday, value: wed}
            - {label: Thursday, value: thu}
            - {label: Friday, value: fri}
            - {label: Saturday, value: sat}
            - {label: Sunday, value: sun}
    morning_b_target_warm:
      name: Morning B Target-Warm Time
      default: "08:30:00"
      selector: {time: {}}
    morning_b_hold_until:
      name: Morning B Hold-Until Time
      default: "10:00:00"
      selector: {time: {}}
    morning_b_target_temp:
      name: Morning B Target Temperature (°C)
      default: 23
      selector:
        number: {min: 18, max: 28, step: 0.5, unit_of_measurement: "°C"}

    # ----- EVENING A (KIDS BATH) -----
    evening_a_days:
      name: Evening A (Kids Bath) Days
      default: []
      selector:
        select:
          multiple: true
          options:
            - {label: Monday, value: mon}
            - {label: Tuesday, value: tue}
            - {label: Wednesday, value: wed}
            - {label: Thursday, value: thu}
            - {label: Friday, value: fri}
            - {label: Saturday, value: sat}
            - {label: Sunday, value: sun}
    evening_a_target_warm:
      name: Evening A Target-Warm Time
      default: "18:15:00"
      selector: {time: {}}
    evening_a_hold_until:
      name: Evening A Hold-Until Time
      default: "19:30:00"
      selector: {time: {}}
    evening_a_target_temp:
      name: Evening A Target Temperature (°C)
      default: 25
      selector:
        number: {min: 18, max: 28, step: 0.5, unit_of_measurement: "°C"}

    # ----- EVENING B (OPTIONAL ADULT EVENING) -----
    evening_b_days:
      name: Evening B Days (leave empty to disable)
      default: []
      selector:
        select:
          multiple: true
          options:
            - {label: Monday, value: mon}
            - {label: Tuesday, value: tue}
            - {label: Wednesday, value: wed}
            - {label: Thursday, value: thu}
            - {label: Friday, value: fri}
            - {label: Saturday, value: sat}
            - {label: Sunday, value: sun}
    evening_b_target_warm:
      name: Evening B Target-Warm Time
      default: "20:30:00"
      selector: {time: {}}
    evening_b_hold_until:
      name: Evening B Hold-Until Time
      default: "22:00:00"
      selector: {time: {}}
    evening_b_target_temp:
      name: Evening B Target Temperature (°C)
      default: 23
      selector:
        number: {min: 18, max: 28, step: 0.5, unit_of_measurement: "°C"}

    # ----- WARMUP FORMULA TUNING -----
    warmup_base_min:
      name: Warmup Base Minutes
      default: 10
      selector:
        number: {min: 5, max: 30, step: 1, unit_of_measurement: "min"}
    warmup_per_degree_min:
      name: Warmup Minutes per °C
      default: 5
      selector:
        number: {min: 1, max: 15, step: 1, unit_of_measurement: "min/°C"}
    warmup_min_minutes:
      name: Warmup Floor (min)
      default: 10
      selector:
        number: {min: 5, max: 30, step: 1, unit_of_measurement: "min"}
    warmup_max_minutes:
      name: Warmup Cap (min)
      default: 60
      selector:
        number: {min: 20, max: 120, step: 5, unit_of_measurement: "min"}

    # ----- BEHAVIOR TOGGLES -----
    enable_predictive_motion:
      name: Enable Predictive Motion Override
      default: true
      selector: {boolean: {}}
    enable_notifications:
      name: Enable Persistent Notifications
      default: true
      selector: {boolean: {}}

mode: restart
max_exceeded: silent

# Triggers, variables, and action will be added in later tasks.
trigger: []
action: []
```

- [ ] **Step 2: Validate YAML syntax**

```bash
cd /Users/martinlevie/Documents/GitHub/Blueprints_Home
python3 -c "import yaml; yaml.safe_load(open('bathroom_heating_rack.yaml'))"
```

Expected: no output (success). Any `yaml.YAMLError` fails the step.

- [ ] **Step 3: Commit**

```bash
git add bathroom_heating_rack.yaml
git commit -m "feat(heating-rack): scaffold blueprint metadata and inputs"
```

---

## Task 3: Add triggers

**Files:**
- Modify: `bathroom_heating_rack.yaml` (replace the `trigger: []` line)

- [ ] **Step 1: Replace `trigger: []` with full trigger list**

Replace the single line `trigger: []` with:

```yaml
trigger:
  # T1: Periodic 1-minute tick for dynamic auto_start + boost expiry
  - platform: time_pattern
    minutes: "/1"
    id: periodic

  # T2: Hall motion (morning predictive accelerator)
  - platform: state
    entity_id: !input hall_motion
    to: "on"
    id: hall_motion_on

  # T3: Stairs motion (evening predictive accelerator)
  - platform: state
    entity_id: !input stairs_motion
    to: "on"
    id: stairs_motion_on

  # T4: Boost toggle state change
  - platform: state
    entity_id: !input boost_toggle
    id: boost_change

  # T5: Vacation toggle state change
  - platform: state
    entity_id: !input vacation_off
    id: vacation_change

  # T6: Fan state change (ventilator coordination)
  - platform: state
    entity_id: !input fan_switch
    id: fan_change

  # T7: HA restart
  - platform: homeassistant
    event: start
    id: ha_start
```

- [ ] **Step 2: Validate YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('bathroom_heating_rack.yaml'))"
```

- [ ] **Step 3: Commit**

```bash
git add bathroom_heating_rack.yaml
git commit -m "feat(heating-rack): add 7 triggers (periodic, motions, toggles, fan, ha_start)"
```

---

## Task 4: Add live-state variables and vacation/boost state

**Files:**
- Modify: `bathroom_heating_rack.yaml` (replace `action: []` with first block)

- [ ] **Step 1: Replace `action: []` with the initial variables block**

Replace `action: []` with:

```yaml
action:
  # =============================================
  # STEP 1: COMPUTE VARIABLES
  # =============================================
  - variables:
      # --- Entity mappings (for readable templates below) ---
      entity_climate: !input heating_climate
      sensor_bathroom_temp: !input bathroom_temp_sensor
      sensor_hall_motion: !input hall_motion
      sensor_stairs_motion: !input stairs_motion
      entity_fan: !input fan_switch
      entity_vacation: !input vacation_off
      entity_boost: !input boost_toggle

      # --- Live sensor reads (with fallbacks) ---
      indoor_temp_primary: "{{ states(sensor_bathroom_temp) | float(-99) }}"
      indoor_temp_fallback: "{{ state_attr(entity_climate, 'current_temperature') | float(20) }}"
      indoor_temp: >-
        {% if indoor_temp_primary | float(-99) > -50 %}
          {{ indoor_temp_primary | float }}
        {% else %}
          {{ indoor_temp_fallback | float }}
        {% endif %}

      current_setpoint: "{{ state_attr(entity_climate, 'temperature') | float(7) }}"
      current_hvac_mode: "{{ states(entity_climate) }}"
      current_preset: "{{ state_attr(entity_climate, 'preset_mode') }}"
      fan_is_on: "{{ is_state(entity_fan, 'on') }}"

      # --- Time helpers ---
      today_dow: "{{ now().strftime('%a') | lower }}"
      now_dt: "{{ now() }}"

      # --- Vacation (safely handle empty list default) ---
      vacation_active: >-
        {% if entity_vacation is iterable and entity_vacation | length > 0 %}
          {{ expand(entity_vacation) | selectattr('state','eq','on') | list | length > 0 }}
        {% else %}
          false
        {% endif %}

      # --- Boost (stateless age-based expiry) ---
      boost_runtime_min_int: "{{ (boost_runtime_min | float) | int }}"
      boost_is_on: "{{ is_state(entity_boost, 'on') }}"
      boost_age_min: >-
        {{ ((now() - states[entity_boost].last_changed).total_seconds() / 60) | int }}
      boost_active: "{{ boost_is_on and boost_age_min < boost_runtime_min_int }}"
      boost_expired: "{{ boost_is_on and boost_age_min >= boost_runtime_min_int }}"
```

The `!input boost_runtime_min` is pulled via `!input` implicitly — references to `boost_runtime_min` inside Jinja come from a blueprint variable already named by `!input`. To make that explicit (and avoid `!input` scope confusion — see `bathroom_ventilator.yaml` for the pattern), we'll add `!input` pass-through variables in Task 5's preamble.

- [ ] **Step 2: Add `!input` pass-through variables at the TOP of the action block (before the other variable block)**

Prepend to the `action:` block, above the existing `- variables:` block:

```yaml
  # ----- !input pass-through (avoids Jinja2 !input scope issues) -----
  - variables:
      boost_runtime_min: !input boost_runtime_min
      boost_target_temp: !input boost_target_temp
      warmup_base_min: !input warmup_base_min
      warmup_per_degree_min: !input warmup_per_degree_min
      warmup_min_minutes: !input warmup_min_minutes
      warmup_max_minutes: !input warmup_max_minutes
      enable_predictive_motion: !input enable_predictive_motion
      enable_notifications: !input enable_notifications
      morning_a_days: !input morning_a_days
      morning_a_target_warm: !input morning_a_target_warm
      morning_a_hold_until: !input morning_a_hold_until
      morning_a_target_temp: !input morning_a_target_temp
      morning_b_days: !input morning_b_days
      morning_b_target_warm: !input morning_b_target_warm
      morning_b_hold_until: !input morning_b_hold_until
      morning_b_target_temp: !input morning_b_target_temp
      evening_a_days: !input evening_a_days
      evening_a_target_warm: !input evening_a_target_warm
      evening_a_hold_until: !input evening_a_hold_until
      evening_a_target_temp: !input evening_a_target_temp
      evening_b_days: !input evening_b_days
      evening_b_target_warm: !input evening_b_target_warm
      evening_b_hold_until: !input evening_b_hold_until
      evening_b_target_temp: !input evening_b_target_temp
```

- [ ] **Step 3: Validate YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('bathroom_heating_rack.yaml'))"
```

- [ ] **Step 4: Commit**

```bash
git add bathroom_heating_rack.yaml
git commit -m "feat(heating-rack): add live-state vars and vacation/boost state"
```

---

## Task 5: Add routine slot resolution variables (all 4 slots + aggregates)

**Files:**
- Modify: `bathroom_heating_rack.yaml` (append a third `- variables:` block inside `action:`)

- [ ] **Step 1: Append the slot-resolution block**

After the previous `- variables:` block (the one ending with `boost_expired:`), add **one new `- variables:` block** containing all 4 slot resolutions plus aggregates. Templates reference variables defined in earlier blocks:

```yaml
  # =============================================
  # STEP 1b: ROUTINE SLOT RESOLUTION
  # =============================================
  - variables:
      # ----- MORNING A -----
      ma_in_days: "{{ today_dow in morning_a_days }}"
      ma_target_warm_dt: "{{ today_at(morning_a_target_warm) }}"
      ma_hold_until_dt: "{{ today_at(morning_a_hold_until) }}"
      ma_delta_T: "{{ [0, morning_a_target_temp | float - indoor_temp | float] | max }}"
      ma_warmup_min: >-
        {{ [warmup_max_minutes | int,
            [warmup_min_minutes | int,
             (warmup_base_min | int) + (warmup_per_degree_min | int) * (ma_delta_T | float)] | max
           ] | min | int }}
      ma_auto_start_dt: >-
        {{ ma_target_warm_dt - timedelta(minutes=ma_warmup_min | int) }}
      ma_motion_lead_dt: >-
        {{ ma_target_warm_dt - timedelta(minutes=(warmup_max_minutes | int) + 30) }}
      ma_motion_last: "{{ states[sensor_hall_motion].last_changed }}"
      ma_motion_in_lead: >-
        {{ enable_predictive_motion and
           ma_motion_last > ma_motion_lead_dt and
           ma_motion_last < ma_target_warm_dt }}
      ma_effective_start: >-
        {% if ma_motion_in_lead %}
          {{ [ma_auto_start_dt, ma_motion_last] | min }}
        {% else %}
          {{ ma_auto_start_dt }}
        {% endif %}
      ma_active: >-
        {{ ma_in_days and
           ma_effective_start <= now_dt and
           now_dt < ma_hold_until_dt }}

      # ----- MORNING B -----
      mb_in_days: "{{ today_dow in morning_b_days }}"
      mb_target_warm_dt: "{{ today_at(morning_b_target_warm) }}"
      mb_hold_until_dt: "{{ today_at(morning_b_hold_until) }}"
      mb_delta_T: "{{ [0, morning_b_target_temp | float - indoor_temp | float] | max }}"
      mb_warmup_min: >-
        {{ [warmup_max_minutes | int,
            [warmup_min_minutes | int,
             (warmup_base_min | int) + (warmup_per_degree_min | int) * (mb_delta_T | float)] | max
           ] | min | int }}
      mb_auto_start_dt: "{{ mb_target_warm_dt - timedelta(minutes=mb_warmup_min | int) }}"
      mb_motion_lead_dt: "{{ mb_target_warm_dt - timedelta(minutes=(warmup_max_minutes | int) + 30) }}"
      mb_motion_last: "{{ states[sensor_hall_motion].last_changed }}"
      mb_motion_in_lead: >-
        {{ enable_predictive_motion and
           mb_motion_last > mb_motion_lead_dt and
           mb_motion_last < mb_target_warm_dt }}
      mb_effective_start: >-
        {% if mb_motion_in_lead %}{{ [mb_auto_start_dt, mb_motion_last] | min }}{% else %}{{ mb_auto_start_dt }}{% endif %}
      mb_active: >-
        {{ mb_in_days and mb_effective_start <= now_dt and now_dt < mb_hold_until_dt }}

      # ----- EVENING A -----
      ea_in_days: "{{ today_dow in evening_a_days }}"
      ea_target_warm_dt: "{{ today_at(evening_a_target_warm) }}"
      ea_hold_until_dt: "{{ today_at(evening_a_hold_until) }}"
      ea_delta_T: "{{ [0, evening_a_target_temp | float - indoor_temp | float] | max }}"
      ea_warmup_min: >-
        {{ [warmup_max_minutes | int,
            [warmup_min_minutes | int,
             (warmup_base_min | int) + (warmup_per_degree_min | int) * (ea_delta_T | float)] | max
           ] | min | int }}
      ea_auto_start_dt: "{{ ea_target_warm_dt - timedelta(minutes=ea_warmup_min | int) }}"
      ea_motion_lead_dt: "{{ ea_target_warm_dt - timedelta(minutes=(warmup_max_minutes | int) + 30) }}"
      ea_motion_last: "{{ states[sensor_stairs_motion].last_changed }}"
      ea_motion_in_lead: >-
        {{ enable_predictive_motion and
           ea_motion_last > ea_motion_lead_dt and
           ea_motion_last < ea_target_warm_dt }}
      ea_effective_start: >-
        {% if ea_motion_in_lead %}{{ [ea_auto_start_dt, ea_motion_last] | min }}{% else %}{{ ea_auto_start_dt }}{% endif %}
      ea_active: >-
        {{ ea_in_days and ea_effective_start <= now_dt and now_dt < ea_hold_until_dt }}

      # ----- EVENING B -----
      eb_in_days: "{{ today_dow in evening_b_days }}"
      eb_target_warm_dt: "{{ today_at(evening_b_target_warm) }}"
      eb_hold_until_dt: "{{ today_at(evening_b_hold_until) }}"
      eb_delta_T: "{{ [0, evening_b_target_temp | float - indoor_temp | float] | max }}"
      eb_warmup_min: >-
        {{ [warmup_max_minutes | int,
            [warmup_min_minutes | int,
             (warmup_base_min | int) + (warmup_per_degree_min | int) * (eb_delta_T | float)] | max
           ] | min | int }}
      eb_auto_start_dt: "{{ eb_target_warm_dt - timedelta(minutes=eb_warmup_min | int) }}"
      eb_motion_lead_dt: "{{ eb_target_warm_dt - timedelta(minutes=(warmup_max_minutes | int) + 30) }}"
      eb_motion_last: "{{ states[sensor_stairs_motion].last_changed }}"
      eb_motion_in_lead: >-
        {{ enable_predictive_motion and
           eb_motion_last > eb_motion_lead_dt and
           eb_motion_last < eb_target_warm_dt }}
      eb_effective_start: >-
        {% if eb_motion_in_lead %}{{ [eb_auto_start_dt, eb_motion_last] | min }}{% else %}{{ eb_auto_start_dt }}{% endif %}
      eb_active: >-
        {{ eb_in_days and eb_effective_start <= now_dt and now_dt < eb_hold_until_dt }}

      # ----- AGGREGATES -----
      morning_active: "{{ ma_active or mb_active }}"
      evening_active: "{{ ea_active or eb_active }}"
      morning_temp: >-
        {% if ma_active %}{{ morning_a_target_temp | float }}{% else %}{{ morning_b_target_temp | float }}{% endif %}
      evening_temp: >-
        {% if ea_active %}{{ evening_a_target_temp | float }}{% else %}{{ evening_b_target_temp | float }}{% endif %}
```

- [ ] **Step 2: Validate YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('bathroom_heating_rack.yaml'))"
```

- [ ] **Step 3: Template-render one slot via hass-cli as smoke test**

Create a throwaway template file (not tracked):

```bash
cat > /tmp/heating_warmup_check.j2 <<'EOF'
{% set indoor_temp = states('sensor.bathroom_temperature') | float(20) %}
{% set target_temp = 23 %}
{% set warmup_base_min = 10 %}
{% set warmup_per_degree_min = 5 %}
{% set warmup_min_minutes = 10 %}
{% set warmup_max_minutes = 60 %}
{% set delta_T = [0, target_temp - indoor_temp] | max %}
{% set warmup = [warmup_max_minutes, [warmup_min_minutes, warmup_base_min + warmup_per_degree_min * delta_T] | max] | min | int %}
Indoor: {{ indoor_temp }}°C, ΔT: {{ delta_T }}°C, Warmup: {{ warmup }} min
EOF
hass-cli template /tmp/heating_warmup_check.j2
```

Expected: line of the form `Indoor: 20.3°C, ΔT: 2.7°C, Warmup: 23 min`. Both values should be reasonable (0 ≤ ΔT ≤ 30, 10 ≤ warmup ≤ 60). Non-numeric output or errors fail the step.

Clean up after: `rm /tmp/heating_warmup_check.j2`

- [ ] **Step 4: Commit**

```bash
git add bathroom_heating_rack.yaml
git commit -m "feat(heating-rack): add routine slot resolution (MA/MB/EA/EB + aggregates)"
```

---

## Task 6: Add sensor validation + boost expiry cleanup

**Files:**
- Modify: `bathroom_heating_rack.yaml` (append two `choose` blocks after the variables)

- [ ] **Step 1: Append sensor validation + boost expiry blocks**

After the third `- variables:` block, add:

```yaml
  # =============================================
  # STEP 2: SENSOR VALIDATION
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: >-
              {{ states(entity_climate) in ['unavailable', 'unknown'] }}
        sequence:
          - service: persistent_notification.create
            data:
              title: "Heating Rack — Climate Unavailable"
              message: >
                climate.heatingrack_bathroom is {{ states(entity_climate) }}.
                Holding current state.
              notification_id: "heating_rack_climate_unavailable"
          - stop: "Climate entity unavailable"

  # =============================================
  # STEP 3: BOOST EXPIRY CLEANUP
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ boost_expired }}"
        sequence:
          - service: input_boolean.turn_off
            target:
              entity_id: "{{ entity_boost }}"
```

- [ ] **Step 2: Validate YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('bathroom_heating_rack.yaml'))"
```

- [ ] **Step 3: Commit**

```bash
git add bathroom_heating_rack.yaml
git commit -m "feat(heating-rack): add sensor validation and boost expiry cleanup"
```

---

## Task 7: Add priority waterfall (P1–P6) + idempotent service calls

**Files:**
- Modify: `bathroom_heating_rack.yaml`

- [ ] **Step 1: Append the main priority choose block**

After the boost-expiry cleanup block, append:

```yaml
  # =============================================
  # STEP 4: PRIORITY CHOOSE (P1–P6)
  # Each branch resolves desired_mode, desired_preset, desired_setpoint
  # via a nested variables block, then falls through to the idempotent
  # service-call block at the end.
  # =============================================
  - variables:
      desired_mode: >-
        {% if vacation_active %}off
        {% elif fan_is_on and (morning_active or evening_active or boost_active) %}heat_cool
        {% elif boost_active %}heat_cool
        {% elif evening_active %}heat_cool
        {% elif morning_active %}heat_cool
        {% else %}heat_cool
        {% endif %}
      desired_preset: >-
        {% if vacation_active %}none
        {% elif fan_is_on and (morning_active or evening_active or boost_active) %}eco
        {% elif boost_active %}none
        {% elif evening_active %}none
        {% elif morning_active %}none
        {% else %}eco
        {% endif %}
      desired_setpoint: >-
        {% if vacation_active %}none
        {% elif fan_is_on and (morning_active or evening_active or boost_active) %}none
        {% elif boost_active %}{{ boost_target_temp | float }}
        {% elif evening_active %}{{ evening_temp | float }}
        {% elif morning_active %}{{ morning_temp | float }}
        {% else %}none
        {% endif %}
      active_priority: >-
        {% if vacation_active %}P1_vacation
        {% elif fan_is_on and (morning_active or evening_active or boost_active) %}P2_fan_coord
        {% elif boost_active %}P3_boost
        {% elif evening_active %}P4_evening
        {% elif morning_active %}P5_morning
        {% else %}P6_idle
        {% endif %}

  # =============================================
  # STEP 4b: IDEMPOTENT SERVICE CALLS
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ current_hvac_mode != desired_mode }}"
        sequence:
          - service: climate.set_hvac_mode
            target:
              entity_id: "{{ entity_climate }}"
            data:
              hvac_mode: "{{ desired_mode }}"

  - choose:
      - conditions:
          - condition: template
            value_template: >-
              {{ (current_preset | default('none')) != desired_preset }}
        sequence:
          - service: climate.set_preset_mode
            target:
              entity_id: "{{ entity_climate }}"
            data:
              preset_mode: "{{ 'none' if desired_preset == 'none' else desired_preset }}"

  - choose:
      - conditions:
          - condition: template
            value_template: >-
              {{ desired_setpoint != 'none'
                 and (current_setpoint | float - desired_setpoint | float) | abs > 0.1 }}
        sequence:
          - service: climate.set_temperature
            target:
              entity_id: "{{ entity_climate }}"
            data:
              temperature: "{{ desired_setpoint | float }}"
```

Note on `preset_mode: 'none'` — HA `climate.set_preset_mode` expects a string preset name or the literal `"none"` to clear. Verified in HA docs.

- [ ] **Step 2: Validate YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('bathroom_heating_rack.yaml'))"
```

- [ ] **Step 3: Commit**

```bash
git add bathroom_heating_rack.yaml
git commit -m "feat(heating-rack): add priority waterfall and idempotent service calls"
```

---

## Task 8: Add notifications (warmup started, target reached, sensor warning)

**Files:**
- Modify: `bathroom_heating_rack.yaml`

- [ ] **Step 1: Append notification block after service calls**

```yaml
  # =============================================
  # STEP 5: NOTIFICATIONS
  # =============================================
  - choose:
      # Warmup started — transitioning to P3/P4/P5 from non-active
      - conditions:
          - condition: template
            value_template: >-
              {{ enable_notifications
                 and active_priority in ['P3_boost','P4_evening','P5_morning']
                 and (current_hvac_mode == 'off' or
                      (current_preset | default('none')) == 'eco') }}
        sequence:
          - variables:
              eta_delta: "{{ [0, desired_setpoint | float - indoor_temp | float] | max }}"
              eta_min: >-
                {{ [warmup_max_minutes | int,
                    [warmup_min_minutes | int,
                     (warmup_base_min | int) + (warmup_per_degree_min | int) * (eta_delta | float)] | max
                   ] | min | int }}
          - service: persistent_notification.create
            data:
              title: "Heating Rack — Warmup Started"
              message: >
                Priority: {{ active_priority }}.
                Current {{ indoor_temp | round(1) }}°C → target
                {{ desired_setpoint }}°C. ETA ~{{ eta_min }} min.
              notification_id: "heating_rack_warmup_started"

      # Target reached — within 0.5°C of desired while routine active
      - conditions:
          - condition: template
            value_template: >-
              {{ enable_notifications
                 and active_priority in ['P3_boost','P4_evening','P5_morning']
                 and desired_setpoint != 'none'
                 and (indoor_temp | float - desired_setpoint | float) | abs < 0.5 }}
        sequence:
          - service: persistent_notification.create
            data:
              title: "Heating Rack — At Target"
              message: >
                Bathroom at {{ indoor_temp | round(1) }}°C
                (target {{ desired_setpoint }}°C). {{ active_priority }}.
              notification_id: "heating_rack_target_reached"
```

- [ ] **Step 2: Validate YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('bathroom_heating_rack.yaml'))"
```

- [ ] **Step 3: Commit**

```bash
git add bathroom_heating_rack.yaml
git commit -m "feat(heating-rack): add warmup-started and target-reached notifications"
```

---

## Task 9: Add manual-run debug notification

**Files:**
- Modify: `bathroom_heating_rack.yaml`

- [ ] **Step 1: Append debug block at the end of action**

```yaml
  # =============================================
  # STEP 6: DEBUG NOTIFICATION (Manual Run Only)
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ trigger.id | default('manual') == 'manual' }}"
        sequence:
          - service: persistent_notification.create
            data:
              title: "Heating Rack Debug — {{ now().strftime('%H:%M:%S') }}"
              message: >
                **Indoor:** {{ indoor_temp | round(1) }}°C
                | **Setpoint:** {{ current_setpoint }}°C
                | **Mode:** {{ current_hvac_mode }}
                | **Preset:** {{ current_preset | default('none') }}

                **Fan:** {{ 'ON' if fan_is_on else 'OFF' }}
                | **Vacation:** {{ vacation_active }}
                | **Boost:** {{ 'ON' if boost_is_on else 'off' }} (age {{ boost_age_min }}m, expires {{ boost_runtime_min_int }}m)

                **Today:** {{ today_dow }}

                **Morning A:** days={{ ma_in_days }}, ΔT={{ ma_delta_T }}°C, warmup={{ ma_warmup_min }}m, auto_start={{ ma_auto_start_dt.strftime('%H:%M') }}, eff_start={{ ma_effective_start.strftime('%H:%M') }}, active={{ ma_active }}

                **Morning B:** days={{ mb_in_days }}, active={{ mb_active }}

                **Evening A:** days={{ ea_in_days }}, ΔT={{ ea_delta_T }}°C, warmup={{ ea_warmup_min }}m, auto_start={{ ea_auto_start_dt.strftime('%H:%M') }}, eff_start={{ ea_effective_start.strftime('%H:%M') }}, active={{ ea_active }}

                **Evening B:** days={{ eb_in_days }}, active={{ eb_active }}

                **→ Priority:** {{ active_priority }}
                | **→ Desired:** mode={{ desired_mode }}, preset={{ desired_preset }}, setpoint={{ desired_setpoint }}
              notification_id: "heating_rack_debug"
```

- [ ] **Step 2: Validate YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('bathroom_heating_rack.yaml'))"
```

- [ ] **Step 3: Commit**

```bash
git add bathroom_heating_rack.yaml
git commit -m "feat(heating-rack): add manual-run debug persistent notification"
```

---

## Task 10: Import blueprint into HA and run static validation

**Files:**
- None modified. Uses live HA instance.

- [ ] **Step 1: Copy blueprint into HA's blueprints/automation/custom/ directory**

User step (cannot automate — requires HA file access). Tell the user:

> "Copy `bathroom_heating_rack.yaml` into your HA config at `<ha_config>/blueprints/automation/custom/bathroom_heating_rack.yaml` (or import via the HA UI: **Settings → Automations & Scenes → Blueprints → Import Blueprint** using the raw GitHub URL or local file)."

- [ ] **Step 2: Restart Home Assistant**

Tell the user: "Restart HA (Settings → System → Restart) so the blueprint is re-parsed. HA caches blueprints aggressively."

- [ ] **Step 3: Confirm blueprint appears and parses**

```bash
hass-cli raw get /api/config/automation/config 2>&1 | head -3
```

Or, from HA UI: **Settings → Automations & Scenes → Blueprints** — the "Bathroom Heating Rack v1.0.0" entry should appear with no error badge.

If HA logs show a YAML or template error, capture the message, fix in the source file, and restart.

- [ ] **Step 4: Create an automation from the blueprint with default inputs**

Tell the user: "Go to **Settings → Automations & Scenes → + Create Automation → Use Blueprint → Bathroom Heating Rack**. Select your entities (defaults will mostly pre-select correctly), and create. You may also need an `input_boolean.heating_rack_boost` helper — create one via **Settings → Devices & Services → Helpers → + → Toggle**."

---

## Task 11: Mental-simulation walkthrough against the coverage checklist

**Files:**
- None modified. Validation only.

Walk the spec's testing checklist against the actual YAML, item by item. For each bullet, identify the exact template branch that implements it and run a template test via `hass-cli template` if reasonable.

- [ ] **Step 1: Cold morning — ΔT=8°C → auto_start = target − 50 min**

Sanity-render via `hass-cli template`:

```bash
cat > /tmp/check_cold.j2 <<'EOF'
{% set indoor = 14 %}{% set target = 22 %}
{% set dt = [0, target - indoor] | max %}
{% set w = [60, [10, 10 + 5 * dt] | max] | min | int %}
ΔT={{ dt }}, warmup={{ w }}min
EOF
hass-cli template /tmp/check_cold.j2 && rm /tmp/check_cold.j2
```

Expected: `ΔT=8, warmup=50min` (clamped correctly).

- [ ] **Step 2: Warm morning — ΔT=0.5°C → warmup clamped to floor (10 min)**

```bash
cat > /tmp/check_warm.j2 <<'EOF'
{% set indoor = 22.5 %}{% set target = 23 %}
{% set dt = [0, target - indoor] | max %}
{% set w = [60, [10, 10 + 5 * dt] | max] | min | int %}
warmup={{ w }}min
EOF
hass-cli template /tmp/check_warm.j2 && rm /tmp/check_warm.j2
```

Expected: `warmup=12min` (10 base + 2.5 per-degree → 12, above floor of 10).

- [ ] **Step 3: ΔT=12°C cold-snap → warmup clamped to cap (60 min)**

```bash
cat > /tmp/check_snap.j2 <<'EOF'
{% set indoor = 10 %}{% set target = 22 %}
{% set dt = [0, target - indoor] | max %}
{% set w = [60, [10, 10 + 5 * dt] | max] | min | int %}
warmup={{ w }}min
EOF
hass-cli template /tmp/check_snap.j2 && rm /tmp/check_snap.j2
```

Expected: `warmup=60min` (10 + 60 = 70 clamped to 60).

- [ ] **Step 4: Manually trigger automation and inspect debug notification**

Ask user: "Go to **Settings → Automations → [your instance] → ⋮ → Run Actions** (or click 'Run'). Then check **Settings → Notifications → Notification Center** for the `heating_rack_debug` entry."

Verify the debug notification shows sensible values for all slots.

- [ ] **Step 5: Toggle `boost_toggle` ON, re-run, verify P3**

Tell user: "Turn the boost helper ON via the Lovelace UI or `hass-cli service call input_boolean.turn_on --arguments entity_id=input_boolean.heating_rack_boost`. Re-run the automation. Debug notification should show **active_priority=P3_boost** and **desired_setpoint=23**."

- [ ] **Step 6: Turn fan ON while boost is active, verify P2 coord wins**

Tell user: "Turn on `light.heater` via the UI. Re-run the automation. Debug should show **active_priority=P2_fan_coord**, **desired_preset=eco**."

- [ ] **Step 7: Turn off fan and boost, verify return to P6 idle**

Tell user: "Turn both off. Re-run. Debug should show **active_priority=P6_idle**, **desired_preset=eco**, and no setpoint service call (idempotent skip)."

- [ ] **Step 8: Verify vacation override — enable, re-run, expect P1**

Tell user (only if they created a vacation helper): "Flip vacation ON. Re-run. Debug should show **P1_vacation**, **desired_mode=off**."

If any test fails, diagnose, fix the YAML, re-copy to HA, restart, retest. No commit for this task unless the YAML changes.

---

## Task 12: Update README with the new blueprint

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Read current README structure**

```bash
grep -n "^##\|^###" README.md | head -30
```

- [ ] **Step 2: Add a new blueprint section**

Locate the existing blueprints list (look for the "Bathroom Ventilator" section per `9deefab docs: add bathroom ventilator blueprint to README`). Add after it, matching its style:

````markdown
### 🔥 Bathroom Heating Rack (`bathroom_heating_rack.yaml`)

Pre-heats your bathroom heating rack for scheduled routines (adult morning, kids bath) using a **dynamic ΔT-based warmup formula** that self-adjusts across seasons — no calendar boundaries needed. Predictive motion in the hall (morning) or on the stairs (evening) pulls the warmup start forward when you're up early. Coordinates with the exhaust fan (via `preset=eco`) to avoid evicting freshly heated air during showers.

**Features:**
- Dual-slot routines per phase (e.g., weekday morning + weekend morning)
- Ad-hoc boost toggle with auto-expiry
- Vacation / full-off input_boolean
- Idempotent service calls (~10/day despite 1-min evaluation tick)
- Manual-run debug notification for one-click state inspection

**Requirements:**
- `climate` entity wrapping the heating rack (e.g., `generic_thermostat` over a smart plug + bathroom temp sensor)
- Hall + stairs motion sensors for predictive start
- Ventilator switch entity (for coordination)
- Two `input_boolean` helpers (boost + optional vacation)

See `requirements_bathroom_heating_rack.md` for detailed design.
````

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add bathroom heating rack blueprint to README"
```

---

## Task 13: Clean up orphan `script.heating_off`

**Files:**
- None in this repo. HA-side change.

- [ ] **Step 1: Confirm orphan status**

```bash
hass-cli raw get /api/config/script/config/heating_off 2>&1
```

Confirm sequence targets `switch.heating_bathroom_plug_on_off` (no longer exists).

- [ ] **Step 2: Delete via HA UI**

Tell user: "Go to **Settings → Automations & Scenes → Scripts → Bathroom_Heating_Off → ⋮ → Delete**. Confirm."

- [ ] **Step 3: Verify deletion**

```bash
hass-cli state list 2>&1 | grep "script.heating_off"
```

Expected: no output (entity gone).

---

## Self-Review

**1. Spec coverage:**

| Spec section | Implemented in |
|---|---|
| Hardware & entities | Task 2 (inputs) |
| 31 blueprint inputs | Task 2 (all inputs, full selectors + defaults) |
| 7 triggers | Task 3 |
| Live-state variables + vacation/boost | Task 4 |
| 4 routine slots + aggregates | Task 5 |
| Sensor validation + boost expiry cleanup | Task 6 |
| Priority waterfall (P1–P6) + idempotent service calls | Task 7 |
| Notifications (warmup started, target reached, sensor warning) | Tasks 6, 8 |
| Debug notification (manual run) | Task 9 |
| Testing (time-manipulation + mental simulation) | Tasks 10, 11 |
| README update | Task 12 |
| Orphan script cleanup | Task 13 |

All spec sections covered.

**2. Placeholder scan:** No TBD / TODO / "similar to" / placeholder language. Every step has exact paths, full YAML, or full commands.

**3. Type consistency:** Variable names used consistently across tasks. `entity_climate`, `boost_toggle`, `ma_active`, etc. are named in Task 4/5 and referenced by the same names in Tasks 7/9. Jinja `timedelta` and `today_at` are both valid HA template helpers.

**One known risk flagged in the plan:** HA `climate.set_preset_mode` may reject `"none"` as an explicit preset name depending on integration — some integrations require calling `set_preset_mode` with a specific preset (like `"eco"`) or omitting the call. Task 11 Step 7 validates this live. If it fails, the fix is to change the idempotent preset-clear branch to call `set_hvac_mode: heat_cool` without `set_preset_mode` when desired is `"none"`.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-18-bathroom-heating-rack.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
