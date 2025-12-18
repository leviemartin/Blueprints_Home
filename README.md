# Toddler Sleep Trainer & Nightlight Blueprint

## Overview
This Home Assistant blueprint is an expert-level automation designed to help toddlers sleep better. Based on sleep research, it manages light color and brightness to minimize sleep disruption while providing clear visual cues for when it is okay to wake up.

**Primary Device Support:** ThirdReality Smart Color Night Light (Type F).  
*Also compatible with any standard RGB Light and Motion Sensor in Home Assistant.*

## Features
*   **🔬 Research-Backed Colors:** Defaults to **Red/Amber** (warm hues) during the night to protect melatonin production and circadian rhythms.
*   **📅 Smart Scheduling:** Configurable "Wakeup Time" for **every day of the week** (Mon-Sun).
*   **🏃 Motion-Responsive:** 
    *   **Sleep Mode:** Ultra-low brightness (default 5%) to act as a gentle nightlight.
    *   **Boost Mode:** Smoothly increases brightness (default 20%) when the toddler moves/gets up, ensuring safety without startling them.
*   **⏰ Wakeup Indicator:** Automatically changes color (e.g., Green) and brightness at the scheduled time to signal "It's okay to get up".
*   **🔋 Power-Loss Safe:** Automatically restores the correct state (Night, Wakeup, or Off) after a power outage or Home Assistant restart.

## Installation
1.  Click the "Import Blueprint" button in Home Assistant or copy the URL of `nightlight.yaml` into your Blueprints configuration.
2.  Create a new automation using this blueprint.

## Configuration Options

### Devices
*   **Night Light:** Select your RGB light entity (e.g., `light.night_light`).
*   **Motion Sensor:** Select your motion sensor entity (e.g., `binary_sensor.night_light_motion`).

### Schedule (Wakeup Times)
Set the time you want the light to turn Green (Wakeup Mode) for each day:
*   **Monday - Friday:** Default 07:00
*   **Saturday - Sunday:** Default 07:30

### Colors & Brightness (Advanced)
*   **Night Color:** The color during sleep hours. *Recommendation: Red (255, 67, 0) or Amber.*
*   **Wakeup Color:** The color for the morning. *Default: Green (0, 255, 0).*
*   **Sleep Brightness:** Default 5%.
*   **Motion Boost Brightness:** Default 20%.
*   **Wakeup Brightness:** Default 50%.

### Timing
*   **Transition Time:** Time in seconds to fade between states (default 2s).
*   **Motion Clear Delay:** How long to stay in "Boost" mode after motion stops (default 30s).

## How it Works (Logic)
1.  **Start (18:00):** The automation activates "Night Mode" (Red, 5%).
2.  **Night Phase (18:00 -> Wakeup Time):** 
    *   If motion is detected, brightness boosts to 20%.
    *   When motion clears, it fades back to 5%.
3.  **Wakeup Phase (Wakeup Time -> +1 Hour):**
    *   The light turns Green (50%) to indicate morning.
4.  **End Phase (+1 Hour):**
    *   The light turns off automatically.

---
*Created by Martin Levie (Gemini CLI Agent)*
