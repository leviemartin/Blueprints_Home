# Home Assistant Blueprints Collection

## Toddler Sleep Trainer & Nightlight Blueprint

### Overview
This Home Assistant blueprint is an expert-level automation designed to help toddlers sleep better. Based on sleep research, it manages light color and brightness to minimize sleep disruption while providing clear visual cues for when it is okay to wake up.

**Primary Device Support:** ThirdReality Smart Color Night Light (Type F).  
*Also compatible with any standard RGB Light and Motion Sensor in Home Assistant.*

### Features
*   **🔬 Research-Backed Colors:** Defaults to **Red/Amber** (warm hues) during the night to protect melatonin production and circadian rhythms.
*   **📅 Smart Scheduling:** Configurable "Wakeup Time" for **every day of the week** (Mon-Sun).
*   **🏃 Motion-Responsive:** 
    *   **Sleep Mode:** Ultra-low brightness (default 5%) to act as a gentle nightlight.
    *   **Boost Mode:** Smoothly increases brightness (default 20%) when the toddler moves/gets up, ensuring safety without startling them.
*   **⏰ Wakeup Indicator:** Automatically changes color (e.g., Green) and brightness at the scheduled time to signal "It's okay to get up".
*   **🔋 Power-Loss Safe:** Automatically restores the correct state (Night, Wakeup, or Off) after a power outage or Home Assistant restart.

### Installation
1. Click the button below to import this blueprint into your Home Assistant instance:

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fleviemartin%2FBlueprints_Home%2Fblob%2Fmain%2Fnightlight.yaml)

2. Or manually copy this URL into the Blueprints configuration:
`https://github.com/leviemartin/Blueprints_Home/blob/main/nightlight.yaml`

---

## Circadian Living Room Lights Blueprint

### Overview
A comprehensive lighting automation for the Living Room that adapts to human presence, circadian rhythms (Sun Elevation), and specific family routines. It utilizes the Aqara FP2 (or any lux+presence sensor) for high-precision control.

### Features
*   **☀️ Native Circadian Algorithm:** Automatically shifts Color Temperature (Kelvin) based on the Sun's elevation without external integrations.
*   **🍽️ Routine Overrides:** Dedicated time slots for **Dinner** (Bright/Neutral) and **Toddler Prep** (Warm Amber/Dim) to override the sun cycle.
*   **💡 Daylight Harvesting:**
    *   **Auto-ON:** Lights turn on if you enter and it's dark (<150 lux) OR if you are sitting and the sun sets.
    *   **Auto-OFF:** Lights turn off if the sun comes out (>400 lux) for 5 minutes.
*   **✨ Seamless Transitions:** Uses long transitions (30s) for color shifts and fast transitions (2s) for presence, ensuring a premium feel.

### Installation
1. Click the button below to import this blueprint into your Home Assistant instance:

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fleviemartin%2FBlueprints_Home%2Fblob%2Fmain%2Fcircadian_livingroom.yaml)

2. Or manually copy this URL into the Blueprints configuration:
`https://github.com/leviemartin/Blueprints_Home/blob/main/circadian_livingroom.yaml`

---

## LG AC Sleep & Movie Mode Blueprint

### Overview
Automates the Display (Light) and Sound (Beep) settings of LG Air Conditioners. Designed to ensure a dark room for sleeping and a distraction-free environment for movie watching.

### Features
*   **🌙 Auto-Sleep:** Automatically turns off AC display and sound at a set time each night.
*   **🎬 Movie Toggle:** Use a remote control (e.g., Philips Hue Dimmer) to toggle the AC into "Dark Mode" and back again with a single button press.
*   **🛠️ Hardware Flexibility:** Supports models with separate Display and Sound switch entities.

### Installation
1. Click the button below to import this blueprint into your Home Assistant instance:

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fleviemartin%2FBlueprints_Home%2Fblob%2Fmain%2Flg_sleep_movie.yaml)

2. Or manually copy this URL into the Blueprints configuration:
`https://github.com/leviemartin/Blueprints_Home/blob/main/lg_sleep_movie.yaml`

---
*Created by Martin Levie (Gemini CLI Agent)*
