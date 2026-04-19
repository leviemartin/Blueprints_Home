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

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fleviemartin%2FBlueprints_Home%2Fmain%2Fnightlight.yaml)

2. Or manually copy this URL into the Blueprints configuration:
`https://raw.githubusercontent.com/leviemartin/Blueprints_Home/main/nightlight.yaml`

---

## Circadian Living Room Lights Blueprint

### Overview
A comprehensive lighting automation for the Living Room that adapts to human presence, circadian rhythms (Sun Elevation), and specific family routines. It utilizes the Aqara FP2 (or any lux+presence sensor) for high-precision control.

### Features
*   **☀️ Native Circadian Algorithm:** Automatically shifts Color Temperature (Kelvin) based on the Sun's elevation without external integrations.
*   **🛋️ Hue Infuse Support:** Optimized for Philips Hue Infuse ceiling lights, supporting independent control of main and backlight entities.
*   **✨ Native Hue Effects:** Supports triggering native effects like **Candlelight** and **Fireplace** during Evening and Night profiles.
*   **🍽️ Routine Overrides:** Dedicated time slots for **Dinner** (Bright/Neutral) and **Toddler Prep** (Warm Amber/Dim) to override the sun cycle.
*   **💡 Daylight Harvesting:**
    *   **Auto-ON:** Lights turn on if you enter and it's dark (<150 lux) OR if you are sitting and the sun sets.
    *   **Auto-OFF:** Lights turn off if the sun comes out (>400 lux) for 5 minutes.
*   **✨ Seamless Transitions:** Uses long transitions (30s) for color shifts and fast transitions (2s) for presence, ensuring a premium feel.

### Installation
1. Click the button below to import this blueprint into your Home Assistant instance:

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fleviemartin%2FBlueprints_Home%2Fmain%2Fcircadian_livingroom.yaml)

2. Or manually copy this URL into the Blueprints configuration:
`https://raw.githubusercontent.com/leviemartin/Blueprints_Home/main/circadian_livingroom.yaml`

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

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fleviemartin%2FBlueprints_Home%2Fmain%2Flg_sleep_movie.yaml)

2. Or manually copy this URL into the Blueprints configuration:
`https://raw.githubusercontent.com/leviemartin/Blueprints_Home/main/lg_sleep_movie.yaml`

---

## Bathroom Ventilator Blueprint

### Overview
An intelligent bathroom exhaust fan automation using dew point comparison for optimal humidity management. Designed for humid climates like the Netherlands, it makes ventilation decisions based on the actual moisture content of indoor vs. outdoor air — smarter than simple relative humidity thresholds.

### Features
*   **💧 Dew Point Intelligence:** Uses the Magnus formula to compare indoor vs. outdoor dew points, ensuring ventilation only runs when it will actually reduce humidity.
*   **🚿 Automatic Shower Detection:** Detects showers via sustained motion + humidity spike and ventilates for 15-45 minutes (configurable).
*   **🌙 Night Mode:** No fan activity between 22:00-05:30 (configurable) except for shower detection.
*   **🔄 Air Refresh Cycles:** Periodic 10-minute fan runs every 3 hours for air quality (toggleable, skipped at night or when humidity is already low).
*   **🛡️ Mold Safety Override:** Forces fan ON if humidity exceeds 85% for 60+ minutes, regardless of all other conditions.
*   **⚡ Energy Efficient:** Fan only runs when there's a reason — no wasteful continuous operation.

### Requirements
*   Smart plug (switch entity) controlling the exhaust fan
*   Indoor temperature + humidity sensor (e.g., Aqara)
*   Motion sensor (e.g., Philips Hue)
*   Weather entity with outdoor temp + humidity (e.g., OpenWeatherMap)

### Installation
1. Click the button below to import this blueprint into your Home Assistant instance:

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fleviemartin%2FBlueprints_Home%2Fmain%2Fbathroom_ventilator.yaml)

2. Or manually copy this URL into the Blueprints configuration:
`https://raw.githubusercontent.com/leviemartin/Blueprints_Home/main/bathroom_ventilator.yaml`

---

## Bathroom Heating Rack Blueprint

### Overview
Pre-heats a bathroom heating rack for scheduled routines (adult morning, kids bath) using a dynamic **ΔT-based warmup formula** that self-adjusts across seasons — no calendar boundaries needed. Predictive motion in the hall (morning) or on the stairs (evening) pulls the warmup start forward when someone is up early. Coordinates with the exhaust fan via `preset=eco` to avoid evicting freshly heated air during showers.

### Features
*   **🌡️ Dynamic Warmup:** Computes lead time from the current indoor-to-target temperature gap, so cold winter mornings get a longer pre-heat than warm summer mornings without any calendar configuration.
*   **📅 Dual-Slot Routines:** Primary + optional secondary slot per phase (e.g., Morning A = Mon–Fri 06:45, Morning B = Sat–Sun 08:30). Evening A for kids bath, Evening B for an optional adult evening.
*   **🏃 Predictive Motion Override:** Hall motion (morning) and stairs motion (evening) within a calculated lead window start the warmup immediately — useful when you're up before the scheduled time.
*   **⚡ Ad-hoc Boost Toggle:** Flip an `input_boolean` for an instant N-minute heat-up at a configurable boost temperature. Auto-expires cleanly.
*   **🌀 Ventilator Coordination:** Pauses active heating (via `preset=eco`) while the exhaust fan is running — no point heating air that's being evicted.
*   **🏖️ Vacation Mode:** Optional `input_boolean` cleanly disables the whole blueprint.
*   **🪶 Idempotent:** Evaluates every minute for precise timing, but only sends climate service calls on actual state transitions — ~4–10 service calls/day.
*   **🔍 Debug-Friendly:** Manual "Run" produces a persistent notification dumping all computed state (ΔT, warmup, each slot's auto_start / effective_start / active flags, winning priority).
*   **📱 Mobile Push (v1.1.0+):** Opt-in push notifications via HA Companion (`notify.mobile_app_*`) for three high-signal events — climate unavailable, temperature-sensor warning, and warmup started. Multi-target fan-out; empty list disables push. Per-user opt-in via the `Mobile Push Targets` input; all five in-HA persistent notifications still fire.

### Requirements
*   `climate` entity wrapping the heating rack (e.g., a `generic_thermostat` over a smart plug + bathroom temp sensor)
*   Bathroom temperature sensor (e.g., Aqara)
*   Hall + stairs motion sensors for predictive start (e.g., Philips Hue)
*   Ventilator switch entity (for coordination — matches bathroom_ventilator blueprint's light-domain convention)
*   Two `input_boolean` helpers: one for Ad-hoc Boost (required), one for Vacation (optional)

### Installation
1. Click the button below to import this blueprint into your Home Assistant instance:

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fleviemartin%2FBlueprints_Home%2Fmain%2Fbathroom_heating_rack.yaml)

2. Or manually copy this URL into the Blueprints configuration:
`https://raw.githubusercontent.com/leviemartin/Blueprints_Home/main/bathroom_heating_rack.yaml`

---
*Created by Martin Levie (Gemini CLI Agent)*
