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
*   **🌡️ Outdoor-Conditioned Targets (v2.0.0):** The stop target follows the outdoor dew point (Magnus, or the weather entity's native `dew_point`). On a muggy day the fan stops where ventilation stops helping instead of chasing an unreachable RH%.
*   **🚿 Shower Detection, Any Hour:** A humidity jump between two sensor reports plus recent motion — works with sensors that report on change (Aqara T1: 6 %). Quiet hours only block new non-shower starts.
*   **⏱️ Bounded, Stateless Runs:** Minimum 15 / maximum 45 min per shower or high-humidity run (boost, the mold override, degraded mode and the sensor-grace hold outrank these bounds), re-decided on every trigger from live state; boost and sensor loss interrupt instantly.
*   **🛟 Degraded Mode:** Humidity sensor offline → one push, then motion-timed runs until it returns.
*   **🔘 Boost Toggle + 📱 Push:** `input_boolean` boost with auto-expiry; mobile push for sensor offline/back and mold override.
*   **🦠 Mold Safety Override:** RH ≥ 85 % with drier outdoor air forces the fan on.

### Requirements
*   Fan entity (light, switch or fan) · indoor temperature + humidity sensor · motion sensor · weather entity (dew_point used when present) · optional fallback weather entity, boost input_boolean, notify targets

### Installation
1. Click the button below to import this blueprint into your Home Assistant instance:

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fleviemartin%2FBlueprints_Home%2Fmain%2Fbathroom_ventilator.yaml)

2. Or manually copy this URL into the Blueprints configuration:
`https://raw.githubusercontent.com/leviemartin/Blueprints_Home/main/bathroom_ventilator.yaml`

---

## Bathroom Heating Rack Blueprint

### Overview
Pre-heats a bathroom heating rack for scheduled routines (adult morning, kids bath) using a dynamic **ΔT-based warmup formula** that self-adjusts across seasons — no calendar boundaries needed. A **comfort floor** keeps the rack off while the room is already within `comfort_floor_delta` (default 1 °C) of the slot target, so a warm bathroom gets no pre-heat and no hold. Scheduled routines pause while the exhaust fan runs; a boost toggle gives an ad-hoc heat-up; a vacation toggle switches the rack off.

### Features
*   **🌡️ Dynamic Warmup:** Computes lead time from the current indoor-to-target temperature gap (`warmup_base + warmup_per_degree × ΔT`, clamped between a floor and a cap), so cold winter mornings get a longer pre-heat than warm summer mornings without any calendar configuration.
*   **🎯 Comfort Floor (v2.0.0):** A slot heats only while `indoor < target − comfort_floor_delta`. At or above that line the slot is satisfied — no pre-heat, no hold. While the device holds that slot's setpoint a 0.5 °C release deadband and a latched opening edge keep a noisy sensor from flipping the setpoint; without the room sensor the floor is suspended and a warning is raised.
*   **📅 Dual-Slot Routines:** Primary + optional secondary slot per phase (e.g., Morning A = Mon–Fri 06:45, Morning B = Sat–Sun 08:30). Evening A for kids bath, Evening B for an optional adult evening. A hold-until at or before target-warm is taken as the next day (the slot is evaluated per calendar day, so it still ends at midnight).
*   **⚡ Ad-hoc Boost Toggle:** Flip an `input_boolean` for an instant N-minute heat-up at a configurable boost temperature. Auto-expires cleanly; boost is explicit intent and is not paused by the fan.
*   **🌀 Ventilator Coordination:** Scheduled routines drop to `idle_setpoint` while the exhaust fan entity is on — no point heating air that's being evicted.
*   **🏖️ Vacation Mode:** Optional `input_boolean`(s) switch the rack off.
*   **🪶 Idempotent:** Evaluates every minute for precise timing, rounds the setpoint to the device `target_temp_step` and clamps it to the device range, and only sends climate service calls on actual transitions.
*   **🔍 Debug-Friendly:** Manual "Run" produces a persistent notification dumping all computed state (indoor temp, step, each slot's ΔT / warmup / auto_start / hold_until / in_window / active, winning priority, desired mode + setpoint).
*   **📱 Mobile Push:** Opt-in push via HA Companion (`notify.mobile_app_*`) for three high-signal events — climate unavailable (once, after 5 min), room sensor offline (once, after 10 min), and warmup started (once per transition, dismissed when the setpoint returns to idle). Targets are filtered to `notify.*` names, every push runs after the climate calls, and an empty list disables push. A target that does not exist aborts the run at the push step (HA does not suppress a missing action) — check it exists after editing.

### Requirements
*   `climate` entity for the heating rack (tested on a Tuya cloud thermostat element that reports `unknown` while on)
*   Bathroom temperature sensor (`device_class: temperature`); the climate entity's `current_temperature` is the fallback
*   Ventilator entity (or the group mirroring it) for coordination
*   Two `input_boolean` helpers: one for Ad-hoc Boost (required), one for Vacation (optional)
*   Optional: `notify.*` services for mobile push

### Installation
1. Click the button below to import this blueprint into your Home Assistant instance:

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fleviemartin%2FBlueprints_Home%2Fmain%2Fbathroom_heating_rack.yaml)

2. Or manually copy this URL into the Blueprints configuration:
`https://raw.githubusercontent.com/leviemartin/Blueprints_Home/main/bathroom_heating_rack.yaml`

## Bedroom Sleep Pre-Cool Blueprint

### Overview
Predictive pre-cooling of bedrooms via a single LG air conditioner in the upstairs hall. The blueprint brings the warmest bedroom to an ideal sleep temperature (default 19 °C) by a fixed bedtime, then holds the room quietly overnight while issuing the absolute minimum number of commands — because LG ACs beep on every command and the tone cannot be silenced in software. The AC cools the hall indirectly through open doors, so the turn-on time is *predicted* from the indoor gap, an hourly weather forecast, and solar gain, with a self-learning bias that auto-corrects from each night's result.

### Features
*   **🧊 6-Phase State Machine:** A stateless daily cycle — DAY-OFF, PRECOOL, BEDTIME-LOCK, NIGHT-HOLD, DEEP-NIGHT-CHECK, DEEP-HOLD — derived from the clock every minute, overnight-wrap-aware.
*   **🔮 Predictive Turn-On:** A transparent linear lead-time formula (indoor gap + forecast outdoor + solar load) recomputed each minute decides when to start cooling so the room hits target by bedtime.
*   **🧠 Self-Learning Bias:** One scalar — the lead-time bias — is persisted in an `input_number` helper and auto-corrected from each cooling night's outcome. Converges over ~3–6 nights.
*   **🔇 Strict Beep Budget:** Unlimited commands before bedtime; after bedtime the lock issues at most 3 (mode, setpoint, night fan — typically 1–2) and the deep-night check at most 1. NIGHT-HOLD and DEEP-HOLD issue zero commands; every climate call is idempotency-guarded.
*   **🌙 Night Fan (v1.0.3):** The fan mode locked in at bedtime is an input (default low), matched case-insensitively to the unit's modes, with a notice if the unit lacks it.
*   **✋ Manual Override (v1.1.0):** A setpoint changed on the unit during the pre-cool is left alone until the bedtime lock; a unit switched off inside the pre-cool window stays off for the night; one notice per override.
*   **📅 Daily Forecast Backstop (v1.1.0):** Between hourly fetches the prediction uses the day's forecast high; the auto-learn write is clamped to the helper's own range, with a notice while that range is narrower than −60…120.
*   **🌡️ Closed-Loop Pre-Cool:** DRIVE / HOLD sub-states cool the hall as hard as the AC allows until the warmest bedroom reaches ideal.
*   **💧 Opt-In Dry Mode:** Humidity-aware `dry` mode, default off — `cool` is the proven path; enable `dry` only after verifying it on the unit.
*   **🛡️ Child-Safe:** `ideal_temp` is bounded ≥ 16 °C; a sub-16 °C bedroom reading raises an overcooling fault. Every setpoint is clamped to the AC's discovered limits.
*   **🔍 Debug-Friendly:** Manual "Run" produces a persistent notification dumping every prediction variable for easy calibration.

### Requirements
*   **Home Assistant Core 2025.7+** (LG ThinQ `set_temperature` fix, PR #147008)
*   One LG air conditioner connected via the LG ThinQ integration (a `climate` entity)
*   Bedroom temperature sensors (e.g., Aqara) — the control target
*   An outdoor temperature sensor
*   A weather entity with an **hourly** forecast — Met.no or Open-Meteo (**not Buienradar** — it has no hourly forecast)
*   An `input_number` helper to persist the self-learned lead-time bias
*   Optional: an `input_boolean` for the vacation toggle; the AC's sound `switch`

See `requirements_bedroom_precool.md` for the detailed design.

### Installation
1. Click the button below to import this blueprint into your Home Assistant instance:

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fleviemartin%2FBlueprints_Home%2Fmain%2Fbedroom_precool.yaml)

2. Or manually copy this URL into the Blueprints configuration:
`https://raw.githubusercontent.com/leviemartin/Blueprints_Home/main/bedroom_precool.yaml`

---
*Created by Martin Levie (Gemini CLI Agent)*
