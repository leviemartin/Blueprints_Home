# Home Assistant Blueprint Requirement Document: NightLight

## 1. Overview
**Name:** NightLight  
**Description:** An advanced sleep-training and nightlight automation designed specifically for toddlers. It utilizes research-backed light hues to minimize sleep disruption while providing visual cues for "okay to wake" times. The automation manages light color, brightness, and motion-based interactions using the ThirdReality Smart Color Night Light.

## 2. Research & Safety Standards
*   **Sleep-Safe Color:** Research confirms that long-wavelength light (Red, Orange, Amber) has the least impact on melatonin production.
    *   **Requirement:** The "Night Mode" color must default to a Red hue (e.g., RGB: 255, 67, 0 or similar warm temperature).
    *   **Avoidance:** The automation should strictly avoid blue or cool-white light spectrums during the night phase.
*   **Brightness:**
    *   **Sleep Mode:** Must be dim (configurable, recommended 1-10%) to provide orientation without stimulating wakefulness.
    *   **Motion Mode:** Slightly brighter to ensure safety if the toddler gets up, but not bright enough to startle (configurable).

## 3. Hardware Compatibility
**Target Device:** ThirdReality Smart Color Night Light (Type F)
*   **Capabilities:** RGB Color control, Dimming, Integrated Motion Sensor.
*   **Integration:** The blueprint must accept a `light` entity and a `binary_sensor` (motion) entity. These are distinct entities provided by the ThirdReality device.

## 4. User Configuration (Inputs)
The blueprint must provide the following configurable inputs:

### 4.1. Devices
*   **Night Light Entity:** Selector for the light domain (Target: ThirdReality Light).
*   **Motion Sensor Entity:** Selector for the binary_sensor domain (Target: ThirdReality Motion Sensor).

### 4.2. Schedule (Wakeup Times)
*   **Wakeup Time (Mon-Fri):** Time selector (Default: 07:00).
*   **Wakeup Time (Sat-Sun):** Time selector (Default: 07:30).
    *   *Constraint:* Allow granular per-day configuration if possible, otherwise split Weekday/Weekend for simplicity as per standard HA blueprint limitations (or use 7 separate time inputs if "per day" is strictly required). *Recommendation: 7 separate inputs for maximum flexibility as requested.*

### 4.3. Colors & Brightness
*   **Night Color:** Color selector (Default: Red).
*   **Wakeup Color:** Color selector (Default: Green or Warm White).
*   **Night Brightness (Sleep):** Percentage slider (1-100%, Default: 5%).
*   **Night Brightness (Motion Boost):** Percentage slider (1-100%, Default: 20%).
*   **Wakeup Brightness:** Percentage slider (1-100%, Default: 50%).

### 4.4. Timing & Transitions
*   **Transition Time:** Number (seconds) for smooth fading between states (Default: 2s).
*   **Motion Timeout:** Number (seconds) to hold "Boost" brightness after motion clears before returning to "Sleep" brightness.

## 5. Functional Logic

### 5.1. Activation Window
*   **Start:** 18:00 (Fixed start time, or configurable optional input).
*   **End:** 1 hour *after* the scheduled Wakeup Time for the current day.
*   **Behavior:** Outside this window, the automation should ideally not interfere with the light (or ensure it is off).

### 5.2. State Machine

#### State A: Night Mode (18:00 -> Wakeup Time)
*   **Trigger:** Time becomes 18:00.
*   **Action:** Turn Light ON.
    *   Color: `Night Color`
    *   Brightness: `Night Brightness`
    *   Transition: `Transition Time`

#### State B: Motion Detected (During Night Mode)
*   **Trigger:** Motion Sensor changes to `on`.
*   **Condition:** Current time is between 18:00 and Wakeup Time.
*   **Action:**
    *   Increase Brightness to `Night Brightness (Motion Boost)`.
    *   Keep Color: `Night Color`.
    *   Transition: `Transition Time`.

#### State C: Motion Cleared (During Night Mode)
*   **Trigger:** Motion Sensor changes to `off` (for X seconds).
*   **Action:**
    *   Decrease Brightness to `Night Brightness`.
    *   Keep Color: `Night Color`.
    *   Transition: `Transition Time`.

#### State D: Wakeup Mode (Wakeup Time -> End Time)
*   **Trigger:** Time becomes `Wakeup Time` (dynamic based on day).
*   **Action:**
    *   Change Color to `Wakeup Color`.
    *   Change Brightness to `Wakeup Brightness`.
    *   Transition: `Transition Time`.

#### State E: End of Routine
*   **Trigger:** 1 hour after `Wakeup Time`.
*   **Action:** Turn Light OFF.

## 6. Edge Cases & Constraints
*   **Manual Override:** If the user manually changes the light color/brightness, the automation should ideally respect it until the next automation trigger (Motion or Time).
*   **Power Loss:** Ensure the light restores to the correct state (Night vs Wakeup) if power is cycled, based on the current time.
*   **Smooth Transitions:** All light changes must use the `transition` parameter to avoid jarring flashes.

## 7. Summary of Variables for Blueprint
1.  `light_entity`
2.  `motion_entity`
3.  `night_color` (Default: Red)
4.  `wakeup_color`
5.  `night_brightness`
6.  `boost_brightness`
7.  `wakeup_time_mon`
8.  `wakeup_time_tue`
9.  `wakeup_time_wed`
10. `wakeup_time_thu`
11. `wakeup_time_fri`
12. `wakeup_time_sat`
13. `wakeup_time_sun`
