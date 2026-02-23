# Home Assistant Blueprint Requirement Document: Circadian LivingRoom Lights

## 1. Overview
**Name:** Circadian LivingRoom Lights  
**Description:** A comprehensive lighting automation for the Living Room that adapts to human presence, circadian rhythms (sun position), and specific family routines. Optimized for a Philips Hue ecosystem, including Hue Infuse ceiling lights and ambient bulbs.

## 2. Core Features
*   **Presence-Based Switching:**
    *   Turn ON when presence is detected (Aqara FP2).
    *   Turn OFF when presence clears.
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
    *   **Late Night:** Ultra-dim (~10-20%).
*   **Lux Threshold (Daylight Savings):**
    *   Prevent lights from turning on if ambient light (Aqara FP2 Lux) is above a configurable threshold (e.g., 300 Lux).

## 3. Hardware & Inputs
*   **Lights:** 
    *   **Philips Hue Bulbs:** Ambient/Color bulbs for general lighting.
    *   **Philips Hue Infuse:** Ceiling lights (Main and Backlight entities supported).
*   **Presence:** Aqara FP2 (binary_sensor).
*   **Illuminance:** Aqara FP2 (sensor.lux).
*   **Sun:** Home Assistant `sun.sun` entity.
*   **Manual Override:** An optional `input_boolean` or switch entity. If ON, the automation halts.

## 4. Detailed Logic & Settings

### 4.1. Inputs
*   `hue_bulbs`: Target bulbs.
*   `hue_ceiling`: Target ceiling lights (Infuse).
*   `presence_entity`: Occupancy sensor.
*   `illuminance_entity`: Lux sensor.
*   `manual_override`: (Optional) Entity to block automation.
*   `lux_threshold`: Number (default 300). Above this, lights don't turn on.
*   `max_kelvin`: (Default 4500K).
*   `min_kelvin`: (Default 2200K - very warm).

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
*   **Turn ON Condition:** Presence detected AND Lux < 150 (Residential Standard).
*   **Presence Timeout (Feature):**
    *   Wait for a configurable duration (Default: 5 min) after presence clears before turning OFF.
*   **Auto-OFF (Daylight Harvesting):**
    *   If Lux > 400 (High Buffer) for **5 minutes**, turn OFF even if presence is detected.
*   **Manual Override:**
    *   Input: `override_entity` (Switch/Input Boolean).
    *   Behavior: If ON, automation pauses.
    *   Resume: When turned OFF, automation resumes immediately.
*   **Seamless Transitions:**
    *   **Turn On/Off:** 2-5 seconds.
    *   **Circadian Updates:** 30 seconds.

## 6. Sensor Placement Best Practices (Aqara FP2)
*   **Mounting:** Wall-mounted at 1.4m - 1.8m high.
*   **Location:** Away from direct sunlight and reflective surfaces (mirrors/glass).
*   **Orientation:** Facing the center of the room, not directly at the window or the lights it controls.

## 7. Variables
1.  `is_daylight_enough`: `lux_sensor > lux_threshold`
2.  `sun_elevation`: `state_attr('sun.sun', 'elevation')`
3.  `todays_sunset`: `state_attr('sun.sun', 'next_setting')` (used for fallback logic if needed).
