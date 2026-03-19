# LG AC Climate Control Blueprint — Design Spec

**Date:** 2026-03-19
**Version:** v1.0.0
**Blueprint file:** `lg_ac_climate.yaml`
**Approach:** Single monolithic blueprint (one instance per floor)

---

## Overview

A Home Assistant blueprint that automates LG air conditioners on a per-floor basis using external Aqara temperature sensors for reliable ambient readings. The blueprint automatically selects heating, cooling, or off mode based on a configurable comfort range, with outdoor-temperature-aware deadband logic for energy efficiency. Fan speed is proportionally controlled with multi-stage time-based escalation.

## Requirements Summary

- 2 floors, 1 LG AC per floor, multiple Aqara temp sensors per floor
- Automatic heat/cool/off mode selection
- Configurable comfort range (not a single set point)
- Outdoor-temperature-aware deadband: disables deadband in extreme weather to prevent cycling
- Per-day operating schedule (start/end per day of week)
- Vacation mode via `input_boolean` — forces AC fully off
- Configurable sensor aggregation strategy (average, min, max)
- Proportional fan speed based on distance from target
- Multi-stage time-based fan escalation with configurable timeouts
- Always mute AC sound switch (eliminate ping noise)
- Garden door sensor: turn off AC after configurable delay when door is open
- 10-minute check interval
- Immediate shutoff when operating window ends

---

## Inputs

### Devices

| Input | Selector | Description | Default |
|---|---|---|---|
| `climate_entity` | `entity` (domain: climate) | The LG AC climate entity | required |
| `temperature_sensors` | `entity` (domain: sensor, multiple) | Aqara temperature sensors for the floor | required |
| `sensor_strategy` | `select` (average / min / max) | How to aggregate multiple sensor readings | average |
| `ac_sound_switch` | `entity` (domain: switch, multiple, optional) | AC sound switch to mute. Empty = no sound control | `[]` |
| `outdoor_temp_sensor` | `entity` (domain: sensor) | Outdoor temperature sensor or HA weather entity | required |
| `door_sensor` | `entity` (domain: binary_sensor, multiple, optional) | Garden door contact sensor(s) | `[]` |

### Comfort Range

| Input | Selector | Description | Default |
|---|---|---|---|
| `temp_range_low` | `number` (°C, step 0.5, min 10, max 30) | Lower bound of comfort range | 20.0 |
| `temp_range_high` | `number` (°C, step 0.5, min 10, max 30) | Upper bound of comfort range | 24.0 |
| `deadband_outdoor_threshold` | `number` (°C, step 0.5, min 0, max 25) | Outdoor distance from comfort range beyond which deadband is disabled | 10.0 |

### Per-Day Operating Schedule

7 pairs of start/end times:

| Input | Selector | Description | Default |
|---|---|---|---|
| `schedule_start_mon` .. `schedule_start_sun` | `time` | Operating start time per day | 07:00:00 |
| `schedule_end_mon` .. `schedule_end_sun` | `time` | Operating end time per day | 23:00:00 |

Supports overnight windows (e.g., 22:00 → 06:00).

### Vacation Mode

| Input | Selector | Description | Default |
|---|---|---|---|
| `vacation_toggle` | `entity` (domain: input_boolean) | When on, AC is forced fully off | required |

### Fan Speed & Escalation

| Input | Selector | Description | Default |
|---|---|---|---|
| `fan_speed_low_threshold` | `number` (°C, step 0.5) | Distance from target below which fan = low | 1.0 |
| `fan_speed_medium_threshold` | `number` (°C, step 0.5) | Distance from target for medium fan | 3.0 |
| `escalation_stage_1_minutes` | `number` (min) | Time before first fan escalation | 20 |
| `escalation_stage_2_minutes` | `number` (min) | Time before second fan escalation | 40 |

### Door

| Input | Selector | Description | Default |
|---|---|---|---|
| `door_off_delay` | `number` (min) | Minutes to wait after door opens before shutting off AC | 5 |

---

## Triggers

| ID | Platform | Description |
|---|---|---|
| `update_loop` | `time_pattern` (every 10 min) | Main control loop |
| `vacation_on` | `state` (vacation toggle → on) | Immediately shut off AC |
| `vacation_off` | `state` (vacation toggle → off) | Resume on next loop cycle |
| `door_opened` | `state` (door sensor → on, for: `door_off_delay` minutes) | Turn off AC after door open delay |
| `ha_start` | `homeassistant` (event: start) | Re-evaluate after HA restart |

No per-day schedule triggers. The 10-minute loop checks the operating window each cycle.

---

## Variables

### Top-level (mapped from inputs)

```yaml
variables:
  climate_ac: !input climate_entity
  sensors_temp: !input temperature_sensors
  strategy: !input sensor_strategy
  switch_sound: !input ac_sound_switch
  sensor_outdoor: !input outdoor_temp_sensor
  sensor_door: !input door_sensor
  entity_vacation: !input vacation_toggle
  temp_low: !input temp_range_low
  temp_high: !input temp_range_high
  deadband_thresh: !input deadband_outdoor_threshold
  t_start_mon: !input schedule_start_mon
  t_end_mon: !input schedule_end_mon
  # ... through t_start_sun / t_end_sun
  fan_low_thresh: !input fan_speed_low_threshold
  fan_med_thresh: !input fan_speed_medium_threshold
  esc_stage_1: !input escalation_stage_1_minutes
  esc_stage_2: !input escalation_stage_2_minutes
  door_delay: !input door_off_delay
```

### Computed (inside action block)

| Variable | Logic |
|---|---|
| `current_temp` | Aggregate available sensor readings based on `strategy`. Skip unavailable/unknown sensors. |
| `sensors_available` | `true` if at least one sensor has a valid numeric reading |
| `outdoor_temp` | `states(sensor_outdoor) \| float` |
| `is_vacation` | `states(entity_vacation) == 'on'` |
| `door_is_open` | `true` if any door sensor is `on` (or empty list = false) |
| `schedule_start_today` | Pick today's start time via `now().weekday()` index |
| `schedule_end_today` | Pick today's end time via `now().weekday()` index |
| `in_operating_window` | `schedule_start_today <= now() < schedule_end_today` (with midnight-crossing support) |
| `target_mode` | `'cool'` if `current_temp > temp_high`, `'heat'` if `current_temp < temp_low`, `'off'` if inside range |
| `distance_from_target` | Distance from nearest comfort boundary (0 if inside range) |
| `outdoor_distance` | `abs(outdoor_temp - nearest_comfort_boundary)` |
| `deadband_active` | `outdoor_distance < deadband_thresh` |
| `ac_last_changed_minutes` | Minutes since `climate_ac` entity `last_changed` |
| `base_fan` | Proportional: `low` if distance < low_thresh, `medium` if < med_thresh, else `high` |
| `target_fan` | Escalated fan: bump up from base if `ac_last_changed_minutes` exceeds stage thresholds |

---

## Action Logic

Priority-based `choose` structure:

```
1. MUTE SOUND (always, first action)
   └─ If sound switch is not empty and is on → switch.turn_off

2. SENSOR CHECK
   └─ If sensors_available == false → hold current state, fire persistent_notification, stop

3. VACATION MODE (highest priority override)
   └─ If is_vacation → turn off AC, stop

4. OUTSIDE OPERATING WINDOW
   └─ If not in_operating_window → turn off AC, stop

5. DOOR OPEN
   └─ If triggered by door_opened → turn off AC, stop
   └─ If door_is_open (checked in loop) → keep AC off, stop

6. MAIN CLIMATE CONTROL (inside window, no overrides)

   6a. TEMP INSIDE COMFORT RANGE
       └─ If deadband_active (outdoor temp is mild):
           └─ Turn off AC, let room drift naturally
       └─ If NOT deadband_active (extreme outdoor temp):
           └─ MAINTENANCE MODE: keep AC on, low fan, hold at nearest boundary
               - If was cooling → hold at temp_range_high
               - If was heating → hold at temp_range_low

   6b. TARGET MODE = COOL (current_temp > temp_range_high)
       └─ climate.set_hvac_mode → cool
       └─ climate.set_temperature → temp_range_high
       └─ climate.set_fan_mode → target_fan (proportional + escalation)

   6c. TARGET MODE = HEAT (current_temp < temp_range_low)
       └─ climate.set_hvac_mode → heat
       └─ climate.set_temperature → temp_range_low
       └─ climate.set_fan_mode → target_fan (proportional + escalation)
```

### Fan Speed Logic

**Base (proportional):**
```
distance < fan_low_thresh   → "low"
distance < fan_med_thresh   → "medium"
distance >= fan_med_thresh  → "high"
```

**Escalation (override upward only):**
```
if ac_last_changed_minutes >= esc_stage_2  → max available speed
if ac_last_changed_minutes >= esc_stage_1  → bump up one level from base
otherwise                                  → use base fan speed
```

Fan escalation only bumps up, never down. If proportional already says "high", stage 1 doesn't lower it.

### Maintenance Mode (Deadband Disabled)

When outdoor temperature is extreme (outdoor_distance >= threshold), the AC stays on at low fan holding the comfort boundary instead of turning off. This prevents rapid on/off cycling that wastes energy in extreme weather.

---

## Edge Cases & Safety

| Scenario | Behavior |
|---|---|
| All sensors unavailable | Hold current AC state, fire persistent notification |
| Some sensors unavailable | Aggregate only available sensors |
| AC entity unavailable | Skip cycle, retry next loop |
| Overnight schedule (22:00 → 06:00) | Midnight-crossing check in `in_operating_window` |
| HA restart | `ha_start` trigger re-evaluates from scratch |
| Escalation timer reset | Resets when AC entity `last_changed` updates (mode change) |
| Door closes | AC resumes on next 10-minute loop cycle (not immediately) |
| Vacation toggled off | AC resumes on next loop cycle |

---

## Blueprint Metadata

```yaml
blueprint:
  name: "LG AC Climate Control v1.0.0"
  domain: automation
mode: restart
max_exceeded: silent
```

---

## Conventions

Following existing repository patterns:
- Variable prefixes: `sensor_*`, `entity_*`, `climate_*`, `switch_*`, `t_*`, `fan_*`
- Trigger IDs: kebab-case descriptive (`update_loop`, `vacation_on`, `door_opened`, `ha_start`)
- Nested `choose` blocks for priority logic
- Computed variables inside action block for HA trace debugging
- `color_temp_kelvin` convention (HA 2026.3 compatibility)
- Semantic versioning in blueprint name
