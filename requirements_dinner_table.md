# Requirements: Dinner Table Lights

## Overview
A focused lighting automation for the dining table using Philips Hue Go (Portable) lights and an Aqara FP2 mmWave presence sensor.

## Goals
1.  **Presence-Based:** Lights turn on *only* when presence is detected in the specific dining zone.
2.  **Time-Window Restricted:** Automation only activates during specific configurable "Meal Windows" (Breakfast, Lunch, Dinner). Outside these times, presence is ignored (unless overridden).
3.  **Circadian "Warm" Offset:** Lighting should be warmer than standard expert recommendations to create a cozy atmosphere.
4.  **Battery Management:** Visual indicators for Low Battery (<5%) and Fully Charged (100% on power).

## Hardware Scope
*   **Lights:** Philips Hue Go v2 (Portable Table Lamp).
*   **Presence:** Aqara FP2 mmWave (Zone-based detection).
*   **Control:** Optional Remote/Helper for overrides.

## Logic Flow

### 1. Triggers
*   Presence Detected (Zone Occupied).
*   Presence Cleared (Zone Clear for X min).
*   Time Window Changes (Start/End of meals).
*   Battery Level/State Changes.
*   Override State Change.

### 2. Modes & Priority
The automation evaluates in this order:

1.  **Override Mode:** (Highest Priority)
    *   If ON: Force Lights ON (User defined color/brightness).
    *   Ignores presence and time windows.

2.  **Battery Critical:**
    *   Condition: Battery < 5% AND Discharging (Not Plugged In).
    *   Action: Pulse/Slow Breathe RED (Brightness 50%).

3.  **Battery Charged Notification:**
    *   Condition: Battery == 100% AND Plugged In (State = Charging/Full).
    *   Action: Solid GREEN (Brightness 50%).
    *   *Exit Condition:* When unplugged, revert to normal.

4.  **Normal Operation (Meal Windows):**
    *   **Condition:** Presence DETECTED **AND** Current Time is within a Meal Window.
    *   **Action:** Turn ON with specific settings (see below).

5.  **Off State:**
    *   **Condition:** Presence CLEARED (after delay) **OR** Current Time is OUTSIDE Meal Window (and presence triggers).
    *   **Action:** Turn OFF.

### 3. Circadian/Meal Settings (Warm Offset)

*   **Breakfast:**
    *   Time: Configurable (e.g., 07:00 - 10:00).
    *   Standard Rec: 4500K (Energizing).
    *   **Blueprint Target:** 3500K (Neutral Warm).
    *   Brightness: High.

*   **Lunch:**
    *   Time: Configurable (e.g., 12:00 - 14:00).
    *   Standard Rec: 5000K (Daylight).
    *   **Blueprint Target:** 4000K (Neutral).
    *   Brightness: Max.

*   **Dinner:**
    *   Time: Configurable (e.g., 17:30 - 20:00).
    *   Standard Rec: 2700K (Warm).
    *   **Blueprint Target:** 2200K (Candlelight/Golden).
    *   Brightness: Dim/Cozy.

### 4. Special Features
*   **Seamless Transitions:** All changes use `transition: 2` seconds (or configurable).
*   **Timeout:** Configurable presence timeout (default 5 mins).

## Inputs
*   **Entities:** Light(s), Presence Sensor, Battery Level Sensor (%), Battery State Sensor (optional).
*   **Times:** Start/End for Breakfast, Lunch, Dinner.
*   **Settings:** Brightness per block, Timeout duration.
*   **Helper:** Override Input Boolean.
