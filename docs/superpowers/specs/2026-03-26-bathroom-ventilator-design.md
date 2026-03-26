# Bathroom Ventilator Automation — Design Spec

## Overview

A Home Assistant blueprint that intelligently controls a bathroom exhaust fan (via smart plug) to manage humidity, prevent mold, and maintain air quality — optimized for the humid Dutch climate (Laren, Netherlands).

The automation uses **dew point comparison** (indoor vs. outdoor) rather than raw relative humidity to make ventilation decisions. This produces fundamentally better results because dew point is an absolute measure of moisture content, independent of temperature.

## Hardware & Entities

| Device | Role | Blueprint Input |
|---|---|---|
| Smart plug (switch) | Controls ventilator on/off | `fan_switch` |
| Aqara humidity sensor | Indoor relative humidity | `humidity_sensor` |
| Aqara temperature sensor | Indoor temperature (for dew point calc) | `temperature_sensor` |
| Philips Hue motion sensor | Shower detection (sustained motion) | `motion_sensor` |
| OpenWeatherMap weather entity | Outdoor temp + humidity (for dew point calc) | `weather_entity` |

## Blueprint Inputs

### Device Inputs

| Input | Selector | Description |
|---|---|---|
| `fan_switch` | `entity` (domain: switch) | Smart plug controlling the ventilator |
| `humidity_sensor` | `entity` (domain: sensor, device_class: humidity) | Aqara bathroom humidity sensor |
| `temperature_sensor` | `entity` (domain: sensor, device_class: temperature) | Aqara bathroom temperature sensor |
| `motion_sensor` | `entity` (domain: binary_sensor, device_class: motion) | Philips Hue motion sensor |
| `weather_entity` | `entity` (domain: weather) | OpenWeatherMap entity for outdoor temp + humidity |

### Threshold Inputs

| Input | Default | Description |
|---|---|---|
| `target_humidity` | 60 | Below this RH%, fan stops (goal achieved) |
| `high_humidity` | 75 | Above this RH%, non-shower ventilation kicks in |
| `mold_humidity` | 85 | Above this RH% for 60 min, force fan regardless |
| `dew_point_delta_min` | 2.0 | Minimum indoor-outdoor dew point difference (°C) for ventilation to be effective |
| `shower_humidity_rise` | 10 | RH% increase within detection window that indicates a shower |
| `shower_motion_minutes` | 5 | Minimum motion duration (minutes) to qualify as shower activity |

### Timer Inputs

| Input | Default | Description |
|---|---|---|
| `post_shower_min_runtime` | 15 | Minimum fan run (minutes) after shower detection |
| `post_shower_max_runtime` | 45 | Hard maximum post-shower run (minutes) |
| `high_humidity_max_runtime` | 30 | Max run (minutes) for non-shower high humidity |
| `refresh_interval_hours` | 3 | Hours between air refresh cycles |
| `refresh_duration_minutes` | 10 | Duration (minutes) of each refresh cycle |
| `refresh_skip_below` | 55 | Skip refresh if humidity is already below this RH% |

### Schedule Inputs

| Input | Default | Description |
|---|---|---|
| `night_start` | "22:00:00" | Start of quiet hours |
| `night_end` | "05:30:00" | End of quiet hours |

### Toggle Inputs

| Input | Default | Description |
|---|---|---|
| `enable_refresh_cycles` | true | Toggle for air refresh cycles (disable once trickle vents installed) |

## Triggers

| # | Trigger ID | Type | Purpose |
|---|---|---|---|
| T1 | `humidity_change` | State change on `humidity_sensor` | Detect humidity rises/drops for shower detection and threshold monitoring |
| T2 | `motion_on` | State change on `motion_sensor` to `on` | Track motion start for shower detection |
| T3 | `motion_off` | State change on `motion_sensor` to `off` | Track motion end for shower detection |
| T4 | `periodic_eval` | Time pattern: every 5 minutes | Periodic evaluation for air refresh, mold safety, and re-evaluation of running fan |
| T5 | `ha_start` | Event: `homeassistant.start` | Restore correct state after HA restart |

The 5-minute time pattern (T4) is the backbone for refresh cycles, mold monitoring, and fan stop evaluation. Post-shower logic (Priority 3) uses internal `wait_for_trigger` + `delay` loops to enforce minimum run time.

## Computed Variables

All variables computed inside the `action:` block to ensure HA traces on failure.

### Sensor Readings

```yaml
indoor_temp: "{{ states(temperature_sensor) | float(20) }}"
indoor_rh: "{{ states(humidity_sensor) | float(50) }}"
outdoor_temp: "{{ state_attr(weather_entity, 'temperature') | float(15) }}"
outdoor_rh: "{{ state_attr(weather_entity, 'humidity') | float(50) }}"
```

### Dew Point Calculation (Magnus Formula)

```yaml
indoor_dp: >-
  {% set T = indoor_temp %}
  {% set RH = indoor_rh %}
  {% set a = 17.625 %}
  {% set b = 243.04 %}
  {% set alpha = (a * T) / (b + T) + log(RH / 100.0) %}
  {{ (b * alpha / (a - alpha)) | round(1) }}

outdoor_dp: >-
  {% set T = outdoor_temp %}
  {% set RH = outdoor_rh %}
  {% set a = 17.625 %}
  {% set b = 243.04 %}
  {% set alpha = (a * T) / (b + T) + log(RH / 100.0) %}
  {{ (b * alpha / (a - alpha)) | round(1) }}
```

### Decision Variables

```yaml
dp_delta: "{{ (indoor_dp - outdoor_dp) | round(1) }}"
ventilation_effective: "{{ dp_delta | float > dew_point_delta_min | float }}"
fan_is_on: "{{ is_state(fan_switch, 'on') }}"
is_night: >-
  {% set t = now().strftime('%H:%M') %}
  {{ t >= night_start[:5] or t < night_end[:5] }}
```

### Shower Detection

Shower is detected when humidity rises significantly while motion has been sustained. Since HA Jinja2 doesn't natively support querying historical sensor values, shower detection uses:

- **Humidity baseline:** captured when motion first activates (T2). The current humidity is compared against this baseline on subsequent triggers.
- **Sustained motion:** motion sensor has been `on` for at least `shower_motion_minutes`.

```yaml
motion_sustained: >-
  {{ is_state(motion_sensor, 'on') and
     (now() - states[motion_sensor].last_changed).total_seconds() > (shower_motion_minutes * 60) }}

shower_detected: >-
  {{ motion_sustained and
     (indoor_rh - humidity_baseline | float(indoor_rh)) > shower_humidity_rise }}
```

The `humidity_baseline` is tracked internally — set on motion start (T2), cleared on fan stop.

## Action Logic — Priority Choose Block

First match wins, evaluated on every trigger.

### Priority 1: Mold Safety Override

- **Condition:** `indoor_rh > mold_humidity` for 60+ minutes
- **Action:** Fan ON
- **Notes:** Ignores night mode, ignores dew point. Mold prevention trumps all. The 60-minute sustained check prevents false triggers from transient spikes.

### Priority 2: Target Achieved — Stop

- **Condition:** `fan_is_on` AND `indoor_rh < target_humidity`
- **Action:** Fan OFF
- **Notes:** Goal reached, stop regardless of what started the fan.

### Priority 3: Post-Shower Ventilation

- **Condition:** `shower_detected` (humidity spike + sustained motion)
- **Action:**
  1. Fan ON
  2. Wait `post_shower_min_runtime` (15 min) — guaranteed minimum
  3. Recheck loop every 5 min:
     - If `dp_delta < dew_point_delta_min` OR `indoor_rh < target_humidity` → Fan OFF, exit
  4. Hard stop at `post_shower_max_runtime` (45 min)
- **Notes:** Runs day AND night. Post-shower absolute humidity almost always exceeds outdoor humidity, even in humid Dutch conditions. Uses `wait_for_trigger` + `delay` internally to enforce minimum run.

### Priority 4: High Humidity (Non-Shower)

- **Condition:** `indoor_rh > high_humidity` AND `ventilation_effective` AND NOT `is_night`
- **Action:**
  1. Fan ON
  2. Re-evaluated every 5 min via T4 trigger
  3. Stop when `indoor_rh < target_humidity` OR `dp_delta < dew_point_delta_min` OR `high_humidity_max_runtime` reached
- **Notes:** Skipped at night. Skipped when outdoor air won't help (dew point check).

### Priority 5: Air Refresh Cycle

- **Condition:** `enable_refresh_cycles` AND NOT `is_night` AND `indoor_rh > refresh_skip_below` AND last refresh was > `refresh_interval_hours` ago
- **Action:** Fan ON for `refresh_duration_minutes` (10 min), then Fan OFF
- **Notes:** Skipped at night. Skipped if air is already dry. Toggleable for when trickle vents are installed.

### Priority 6: Default — Fan OFF

- **Condition:** `fan_is_on` AND none of the above conditions active
- **Action:** Fan OFF
- **Notes:** Catch-all to ensure fan doesn't stay on without reason.

### Hysteresis

5% RH buffer to prevent rapid on/off cycling. If the fan turned off because humidity dropped below `target_humidity` (60%), it won't re-trigger for non-shower high humidity until humidity rises above 65%. Post-shower and mold override bypass this hysteresis.

## State Restoration (HA Restart)

On `homeassistant.start` (T5):
- Re-evaluate all conditions from scratch
- If `indoor_rh > high_humidity` and `ventilation_effective` → resume fan
- If no conditions met → ensure fan is OFF
- No attempt to resume a "shower in progress" — the next humidity check catches it naturally

## Edge Cases

| Scenario | Handling |
|---|---|
| Sensor unavailable | All sensor reads have fallback defaults. Fan stays in current state — no action on bad data |
| Weather entity unavailable | Outdoor values fall back to conservative defaults (15°C, 50% RH). Neutral dew point won't block ventilation |
| Fan manually toggled | 5-min re-evaluation (T4) corrects state. Manual ON stays until next eval finds no reason. Manual OFF during shower — humidity check may re-enable |
| Shower at 05:15 (during night) | Night ends at 05:30, but shower detection (Priority 3) runs day AND night — fan activates correctly |
| Humid summer day, no shower | High humidity (Priority 4) checks dew point delta. If outdoor air equally humid, fan stays off — correct |
| Refresh cycle overlaps with shower | Shower (Priority 3) has higher priority. No conflict |
| Power outage on plug | Plug returns to default state (typically OFF). Next T4 evaluation corrects |

## Debug Support

On manual "Run" action, fire a `persistent_notification` showing:
- Indoor temp, RH, dew point
- Outdoor temp, RH, dew point
- Dew point delta and whether ventilation is effective
- Current detected mode (shower / high humidity / refresh / idle)
- Fan state
- Night mode status
- Time since last refresh cycle

## Key Design Decisions

1. **Dew point over relative humidity** for ventilation effectiveness — absolute moisture comparison handles the Dutch climate correctly across all seasons.
2. **Self-contained shower detection** (no helper entities required) — tracks humidity baseline internally using trigger IDs and fan state.
3. **Post-shower always ventilates** (minimum 15 min) — building science confirms post-shower absolute humidity nearly always exceeds outdoor, even in humid conditions.
4. **Configurable refresh cycles with toggle** — supports current needs (no trickle vents) and future state (trickle vents installed).
5. **Night mode is quiet by default** — only shower detection can activate the fan between 22:00 and 05:30.
6. **5-minute evaluation cycle** — balances responsiveness with simplicity. Consistent with other blueprints in this repository.
