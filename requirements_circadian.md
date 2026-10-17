# Home Assistant Blueprint Requirement Document: Circadian LivingRoom Lights

## 1. Overview
**Name:** Circadian LivingRoom Lights  
**Description:** A comprehensive lighting automation for the Living Room that adapts to human presence, circadian rhythms (sun position), and specific family routines. Optimized for a Philips Hue ecosystem, including Hue Infuse ceiling lights and ambient bulbs.

## 2. Core Features
*   **Version:** v3.0.0 (dual presence: FP2 + FP300).
*   **Presence-Based Switching (dual presence):**
    *   Turn ON when either sensor reports presence: Aqara FP2 (`presence_fp2`) or Aqara FP300 on the couch (`presence_fp300`).
    *   Turn OFF only when both sensors are clear (off, unavailable or unknown) for `presence_timeout` (default 5 min).
    *   Late-night window: between 23:00 (`late_night_start`) and 06:30 (`late_night_end`), crossing midnight, the off delay is 1 min (`late_night_timeout`, 1-60). The end is exclusive; start equal to end means no window.
    *   A both-clear countdown whose 1-min mark passed before 23:00 finishes on `presence_timeout` (up to 4 min later than the late-night delay); a clear that began just before 23:00 can still turn off at its 1-min mark just after 23:00. A countdown whose 1-min mark falls at or after 06:30 also finishes on `presence_timeout`; there is no extra trigger at the window edges.
    *   The FP300 counts like the FP2 at all hours, so the dog on its bench keeps the FP300, and so the lights, on, also at night. Accepted, still being tested; no cap or zone logic.
*   **Native Circadian Algorithm:**
    *   Calculates Color Temperature (Kelvin) based on Sun Elevation (using `sun.sun`).
    *   **Daylight (Sun > 10°):** Cool White (~4500K-5500K) for energy/focus.
    *   **Sunset/Twilight:** Transitions to Warm White (~2700K).
*   **Toddler Summer Adjustment (The "Sunset Override"):**
    *   Even if the sun is still up (summer evenings), the lights must shift to "Sleep Prep" mode (Warm Amber, ~2200K) starting at **19:00** to support the toddler's 20:00 bedtime.
*   **Native Hue Effects:**
    *   Optional support for "Candlelight" or "Fireplace" effects on ceiling lights during Evening and Night profiles.
*   **Smart Brightness Schedule:**
    *   **Day:** Adaptive (or blocked by Lux threshold).
    *   **Dinner Mode (18:00-19:00):** Boost to high brightness (80-100%) for eating/tasks.
    *   **Evening/Relax:** Dim to ~40-50%.
    *   **Night (22:00-06:00):** Ultra-dim (~10-20%), independent of the late-night window.
*   **Lux Thresholds (Daylight Harvesting):** FP2 illuminance only; FP300 lux is not read. Lights turn on only below `lux_on_threshold` (default 150 lx) and turn off above `lux_off_threshold` (default 400 lx) for `lux_off_duration` (default 5 min). These are blueprint defaults; each instance may override them (per instance).

## 3. Hardware & Inputs
*   **Lights:** 
    *   **Philips Hue Bulbs:** Ambient/Color bulbs for general lighting.
    *   **Philips Hue Infuse:** Ceiling lights (Main and Backlight entities supported).
*   **Presence:** two occupancy binary_sensors: Aqara FP2 (`presence_fp2`) and Aqara FP300 on the couch (`presence_fp300`, via Zigbee2MQTT).
*   **Illuminance:** Aqara FP2 only (sensor.lux); FP300 lux is not read.
*   **Notifications:** optional `notify.*` services (`notify_targets`) for the FP300 offline push.
*   **Sun:** Home Assistant `sun.sun` entity.
*   **Manual Override:** An optional `input_boolean` or switch entity. If ON, the automation halts.

## 4. Detailed Logic & Settings

### 4.1. Inputs
All blueprint inputs of v3.0.0, in blueprint order. `required` means the input has no default.

| Key | Default | Meaning |
|---|---|---|
| `hue_bulbs` | `[]` | Hue ambient/colour bulbs |
| `hue_ceiling` | `[]` | Hue Infuse ceiling lights (main and backlight) |
| `ceiling_brightness_scale` | `0.6` | Dims the ceiling lights relative to the bulbs |
| `presence_fp2` | required | Aqara FP2 occupancy binary_sensor |
| `presence_fp300` | required | Aqara FP300 occupancy binary_sensor (couch) |
| `presence_timeout` | `5` | Minutes both sensors must be clear before off |
| `late_night_timeout` | `1` | Minutes both clear inside the late-night window (1-60) |
| `late_night_start` | `23:00:00` | Start of the late-night window |
| `late_night_end` | `06:30:00` | End of the window (exclusive; may cross midnight; equal to start = no window) |
| `illuminance_entity` | required | FP2 illuminance sensor (FP300 lux is not read) |
| `override_entity` | `[]` | Switch/input_boolean; while on, no light calls |
| `lux_on_threshold` | `150` | Lights turn on only below this lux |
| `lux_off_threshold` | `400` | Lights turn off above this lux... |
| `lux_off_duration` | `5` | ...held for this many minutes |
| `time_dinner` | `18:00:00` | Dinner start |
| `dinner_kelvin` | `3000` | Dinner colour (K) |
| `dinner_bri` | `100` | Dinner brightness (%) |
| `time_toddler` | `19:00:00` | Toddler prep start |
| `toddler_kelvin` | `2200` | Toddler colour (K) |
| `toddler_bri` | `60` | Toddler brightness (%) |
| `time_evening` | `20:00:00` | Evening start |
| `evening_kelvin` | `2700` | Evening colour (K) |
| `evening_bri` | `50` | Evening brightness (%) |
| `evening_effect` | `none` | Evening Hue effect |
| `time_night` | `22:00:00` | Night start |
| `night_kelvin` | `2200` | Night colour (K) |
| `night_bri` | `20` | Night brightness (%) |
| `night_effect` | `none` | Night Hue effect |
| `max_kelvin` | `4500` | Day-mode upper Kelvin |
| `min_kelvin` | `2200` | Day-mode lower Kelvin |
| `notify_targets` | `[]` | Full `notify.<name>` services for the FP300 offline push; others ignored; empty disables |

### 4.2. Per-Profile Effects
*   **Evening/Night:** Users can select native Hue effects (Candlelight, Fireplace) which are applied to the `hue_ceiling` entities automatically when the profile starts.

### 4.3. Time Slots (Brightness Profiles) - Fully Configurable
*   **Day Start:** 06:00 (Fixed). (Uses Max Kelvin input).
*   **Dinner:**
    *   Start Time (Default: 18:00)
    *   Kelvin (Default: 3000K)
    *   Brightness (Default: 100%)
*   **Toddler Prep:**
    *   Start Time (Default: 19:00)
    *   Kelvin (Default: 2200K)
    *   Brightness (Default: 60%)
*   **Evening:**
    *   Start Time (Default: 20:00)
    *   Kelvin (Default: 2700K)
    *   Brightness (Default: 50%)
    *   Effect (Optional: Candlelight/Fireplace)
*   **Night:**
    *   Start Time (Default: 22:00)
    *   Kelvin (Default: 2200K)
    *   Brightness (Default: 20%)
    *   Effect (Optional: Candlelight/Fireplace)

### 4.3. Circadian Math (Simplified)
*   **Day Mode:** Maps Sun Elevation to `min_kelvin` - `max_kelvin`.
*   **Override:** The specific time slots above take precedence over the sun calculation.

## 5. Transition Handling & Flicker Prevention
*   **Turn ON Condition:** either sensor on (FP2 or FP300) AND FP2 lux below `lux_on_threshold` (default 150 lx).
*   **Presence Timeout:** lights go off when both sensors are clear for `presence_timeout` (default 5 min); each sensor's own timer fires, then the other sensor must have been clear at least as long.
*   **Late-Night Timeout:** inside 23:00-06:30 the delay is `late_night_timeout` (default 1 min); boundary as in section 2.
*   **FP300 offline:** unavailable or unknown counts as clear. After 30 min in either state, one push goes to each `notify_targets` entry, after the light calls, also while the manual override is on. A target that does not exist aborts the run at the push step; check it exists after editing.
*   **Auto-OFF (Daylight Harvesting):**
    *   If FP2 lux > `lux_off_threshold` (default 400 lx) for `lux_off_duration` (default 5 min), turn OFF even if presence is detected.
*   **Manual Override:**
    *   Input: `override_entity` (Switch/Input Boolean).
    *   Behavior: If ON, automation pauses. Off timers that expire while it is on are not replayed.
    *   Resume: When turned OFF, automation resumes immediately.
*   **Seamless Transitions:**
    *   **Turn On/Off:** 2-5 seconds.
    *   **Circadian Updates:** 30 seconds.

## 6. Sensor Placement Best Practices (Aqara FP2)
*   **Mounting:** Wall-mounted at 1.4m - 1.8m high.
*   **Location:** Away from direct sunlight and reflective surfaces (mirrors/glass).
*   **Orientation:** Facing the center of the room, not directly at the window or the lights it controls.

### 6.1. Aqara FP300 (couch) setup
*   Paired via Zigbee2MQTT, set by hand (the blueprint writes no device settings).
*   Presence source: mmWave + PIR.
*   `absence_delay_timer`: 60 s.
*   At night about 2 min from the last motion to lights off (60 s plus the 1 min `late_night_timeout`), when the FP2 is already clear.
*   FP300 lux is not read.

## 7. Variables
1.  `is_daylight_enough`: `lux_sensor > lux_on_threshold`
2.  `sun_elevation`: `state_attr('sun.sun', 'elevation')`
3.  `todays_sunset`: `state_attr('sun.sun', 'next_setting')` (used for fallback logic if needed).
