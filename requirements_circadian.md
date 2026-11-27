# Home Assistant Blueprint Requirement Document: Circadian LivingRoom Lights

## 1. Overview
**Name:** Circadian LivingRoom Lights  
**Description:** A comprehensive lighting automation for the Living Room that adapts to human presence, circadian rhythms (sun position), and specific family routines. Optimized for a Philips Hue ecosystem, including Hue Infuse ceiling lights and ambient bulbs.

## 2. Core Features
*   **Version:** v3.3.0 (dual presence: FP2 + FP300; night window ignores the FP300; manual changes respected; re-check on every trigger, RFC `docs/design/2026-11-26-living-room-lighting.md`).
*   **Presence-Based Switching (dual presence):**
    *   Turn ON when either sensor reports presence: Aqara FP2 (`presence_fp2`) or Aqara FP300 on the couch (`presence_fp300`).
    *   Turn OFF only when both sensors are clear (off, unavailable or unknown) for `presence_timeout` (default 5 min). A sensor missing from Home Assistant (renamed or removed) counts as clear, so the other sensor decides alone.
    *   **Re-check:** every trigger recomputes one decision (off, on, update or nothing) from the current state. A 5-minute check, HA start and automation reload also re-check, so a missed timer or lux crossing is caught; the 5-minute check can turn lights off or refresh them, never turn them on. HA start and reload act on the current lux at once (HA drops the lux timers), so they can also turn lights on in an occupied dark room.
    *   Late-night window: between 23:00 (`late_night_start`) and 06:30 (`late_night_end`), crossing midnight, the off delay is 1 min (`late_night_timeout`, 1-60). The end is exclusive; start equal to end means no window.
    *   A both-clear countdown whose 1-min mark passed before 23:00 turns off at the next 5-minute check (23:00 itself is one); a clear that began just before 23:00 can still turn off at its 1-min mark just after 23:00. A countdown whose 1-min mark falls at or after 06:30 finishes on `presence_timeout`; there is no extra trigger at the window edges beyond the 5-minute check.
    *   **Night window (dog on the bench):** between 01:00 (`fp300_ignore_start`) and 06:00 (`fp300_ignore_end`) the FP300 is ignored: it cannot turn the lights on or keep them on, and the FP2 alone decides. Lights the FP300 was holding at 01:00 dim after `late_night_timeout` and go off a minute later. FP300 changes inside the window are ignored too. At the window end an FP300 that is still on does not turn the lights on (most likely the dog); a new FP300 or FP2 detection does. Outside the window the FP300 counts like the FP2 (no cap). Still being tested.
    *   **Dim warning:** inside the night window, the lights first dim to 30 % of the profile brightness (at least 1 %) when the FP2 has been clear for `late_night_timeout`, and go off one minute later; FP2 presence in that minute restores the profile. Inside the night window the timeout is always `late_night_timeout`.
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
*   **Lux Thresholds (Daylight Harvesting):** FP2 illuminance only; FP300 lux is not read. Lights turn on only below `lux_on_threshold` (default 150 lx) and turn off above `lux_off_threshold` (default 400 lx) for `lux_off_duration` (default 5 min). Lights that daylight turned off come back on once lux stays below `lux_on_threshold` for `lux_on_duration` (default 5 min) while someone is present. Between the two thresholds the lights keep their current state. No lux reading means no lux decision (presence alone turns the lights on). These are blueprint defaults; each instance may override them (per instance); the living room instance uses 45 / 90 lx and 5 / 10 min (lowered from 175 / 250 on 27 Nov 2026, RFC D4a/D4b).

## 3. Hardware & Inputs
*   **Lights:** 
    *   **Philips Hue Bulbs:** Ambient/Color bulbs for general lighting.
    *   **Philips Hue Infuse:** Ceiling lights (Main and Backlight entities supported).
*   **Presence:** two occupancy binary_sensors: Aqara FP2 (`presence_fp2`) and Aqara FP300 on the couch (`presence_fp300`, paired over Matter).
*   **Illuminance:** Aqara FP2 only (sensor.lux); FP300 lux is not read.
*   **Notifications:** optional `notify.*` services (`notify_targets`) for the presence-sensor offline push.
*   **Sun:** Home Assistant `sun.sun` entity.
*   **Manual Override:** An optional `input_boolean` or switch entity. If ON, the automation halts.

## 4. Detailed Logic & Settings

### 4.1. Inputs
All blueprint inputs of v3.3.0, in blueprint order. `required` means the input has no default.

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
| `fp300_ignore_start` | `01:00:00` | Start of the night window in which the FP300 is ignored |
| `fp300_ignore_end` | `06:00:00` | End of the night window (exclusive; may cross midnight; equal to start = no window) |
| `illuminance_entity` | required | FP2 illuminance sensor (FP300 lux is not read) |
| `override_entity` | `[]` | Switch/input_boolean; while on, no light calls |
| `override_timeout` | `30` | Minutes the room must be empty before a forgotten override switches itself off (0 = never) |
| `auto_off_helper` | `[]` | input_boolean the automation turns on when it switches the lights off; empty disables manual-off protection |
| `lux_on_threshold` | `150` | Lights turn on only below this lux |
| `lux_off_threshold` | `400` | Lights turn off above this lux... |
| `lux_off_duration` | `5` | ...held for this many minutes |
| `lux_on_duration` | `5` | Minutes lux must stay below `lux_on_threshold` before daylight-off lights come back on |
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
| `notify_targets` | `[]` | Full `notify.<name>` services for the presence-sensor offline push; others ignored; empty disables |

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
*   **Turn ON Condition:** lights off, either sensor on (FP2 or FP300) AND FP2 lux below `lux_on_threshold` (default 150 lx) or no lux reading, on a presence-on, lux-low or override-resume trigger.
*   **Presence Timeout:** lights go off when both sensors are clear for `presence_timeout` (default 5 min); any trigger checks that every sensor has been clear at least that long. A present sensor with no `last_changed` keeps the room occupied.
*   **Late-Night Timeout:** inside 23:00-06:30 the delay is `late_night_timeout` (default 1 min); boundary as in section 2.
*   **Sensor offline:** unavailable or unknown counts as clear. After 30 min in either state (FP2 or FP300), one push goes to each `notify_targets` entry, after the light calls, also while the manual override is on. A sensor missing from Home Assistant is pushed on the hourly 5-minute check (minute 0). A target that does not exist aborts the run at the push step; check it exists after editing.
*   **Auto-OFF (Daylight Harvesting):**
    *   If FP2 lux > `lux_off_threshold` (default 400 lx) for `lux_off_duration` (default 5 min), turn OFF even if presence is detected. The 5-minute check also turns off when the current reading is above the threshold and has not changed for `lux_off_duration`.
*   **Manual changes (no helper):**
    *   A lit light more than 5 % or 150 K away from the profile target (and not at the night dim level), or in a colour mode (xy, hs, rgb), counts as changed by hand. The 5-minute update and presence refreshes leave it alone until the next profile start (06:00 day, `time_dinner`, `time_toddler`, `time_evening`, `time_night`), which re-applies the profile to every lit light. Switching the lights off ends it too.
    *   Lights switched off by hand stay off (needs `auto_off_helper`): the automation turns the helper on whenever it switches the lights off itself and off whenever it turns them on or sees them on, so lights that are off while the helper is off, or that changed more than 30 s after the helper was set (a manual on and off since), were switched off by hand. A presence trigger then switches them on only when the room had been empty for the timeout before it (`presence_timeout`, or `late_night_timeout` in the late-night window, plus 1 min in the night window); lux-low, HA start and reload do not. Turning the override off does (by design: resume re-checks the room). Without the helper, presence switches lights on as in v3.2.0.
*   **Manual Override:**
    *   Input: `override_entity` (Switch/Input Boolean).
    *   Behavior: If ON, automation pauses. Off timers that expire while it is on are not replayed.
    *   Resume: When turned OFF, automation re-checks immediately: an empty room goes off, an occupied dark room comes on.
    *   Auto-resume: the 5-minute check switches a forgotten override off once both sensors have been clear for `override_timeout` (default 30 min; the FP300 is ignored in the night window, so the dog cannot keep it on). 0 disables it. Use it for a film or a dinner party: switch it on, and it ends by hand or when everyone has left.
*   **Seamless Transitions:**
    *   **Turn On/Off:** 2-5 seconds.
    *   **Circadian Updates:** 30 seconds.

## 6. Sensor Placement Best Practices (Aqara FP2)
*   **Mounting:** Wall-mounted at 1.4m - 1.8m high.
*   **Location:** Away from direct sunlight and reflective surfaces (mirrors/glass).
*   **Orientation:** Facing the center of the room, not directly at the window or the lights it controls.

### 6.1. Aqara FP300 (couch) setup
*   Paired over Matter since 22 Nov 2026 (the blueprint writes no device settings). Before that it came in through the Aqara hub via HomeKit (`binary_sensor.living_room_main_fp300_couch_occupancy_sensor`, now gone).
*   Matter exposes one occupancy setting: Hold time, currently 10 s. The mmWave/PIR detection mode is not exposed; the device default (mmWave + PIR) is used.
*   In the late-night window about 1 min 10 s from the last motion to lights off (10 s hold time plus the 1 min `late_night_timeout`), when the FP2 is already clear; inside the night window the FP300 is ignored.
*   FP300 lux is not read.

## 7. Variables
1.  `is_daylight_enough`: `lux_sensor > lux_on_threshold`
2.  `sun_elevation`: `state_attr('sun.sun', 'elevation')`
3.  `todays_sunset`: `state_attr('sun.sun', 'next_setting')` (used for fallback logic if needed).
