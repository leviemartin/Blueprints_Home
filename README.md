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
*   **🛏️ Nap toggle (v1.3.0):** the nightlight blueprint accepts an optional `nap_toggle` input_boolean; when set, nap-colour painting follows the toggle's state instead of the fixed nap window, repainting within seconds via two new state triggers (with a restored-trigger guard so a HA restart never replays a stale toggle state). Leave it empty for exact v1.2.0 behaviour.

### Installation
1. Click the button below to import this blueprint into your Home Assistant instance:

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fleviemartin%2FBlueprints_Home%2Fmain%2Fnightlight.yaml)

2. Or manually copy this URL into the Blueprints configuration:
`https://raw.githubusercontent.com/leviemartin/Blueprints_Home/main/nightlight.yaml`

---

## Bedroom Fan Daytime Blueprint

### Overview
Switches a running bedroom ceiling fan off once the upstairs has been empty for a while during the day, and manages the kids' nap toggle. It only ever switches a fan **off** — it never switches a fan on and never changes speed or direction, so it cannot fight the safety cutoff, the Hue dimmer, the pre-cool night write or the seasonal direction. One instance per room: kids (with the nap lifecycle) and master (without).

### Features
*   **Vacancy switch-off (08:00–18:00):** a running fan goes off 20 min after the last activity — any change of the configured motion sensors (a sensor reading on means occupied), of the fan itself, or of the nap toggle.
*   **One command, re-checked:** exactly one `fan.turn_off` per run on live state; nothing is sent to a fan between 18:00 and 08:00.
*   **Kids nap lifecycle:** a short press of the dimmer's Off button while the room lights are on (08:00–17:55) starts a nap; a short +/− press with the lights off, or the lights turning on, ends it; automatic ends at the 3-hour cap, at 17:55, and for a nap left over from before 08:00. While a nap is on the fan is left exactly as it is.
*   **Dashboard fallback:** switching "Kids nap" on by hand records the start time.
*   **Restart-safe:** a Home Assistant start and a manual Run write nothing; button, toggle and gate replays are ignored.
*   **Configuration notice:** one persistent notification per instance for configuration problems; it never blocks a switch-off.

### Requirements
*   The fan entity and at least one `binary_sensor` activity sensor.
*   For the nap lifecycle: an input_boolean **"Kids nap"** (`input_boolean.kids_nap`, on a dashboard), an input_datetime with date and time **"Kids nap since"** (`input_datetime.kids_nap_since`, off dashboards) — both without an initial value, so they survive restarts — plus the Hue dimmer's event entities and the room's gate light group.

### Installation
1. Create the helpers "Kids nap" (icon `mdi:sleep`) and "Kids nap since" (date + time) and check they received exactly the entity ids above.
2. Deploy the nightlight v1.3.0 and its instance: `bash scripts/deploy-blueprint.sh nightlight.yaml leviemartin/nightlight.yaml deploy/nightlight_1766142134972.json`.
3. Save this blueprint: `bash scripts/deploy-blueprint.sh bedroom_fan_daytime.yaml leviemartin/bedroom_fan_daytime.yaml`.
4. Create the two instances (POST `deploy/bedroom_fan_daytime_kids.json` and `deploy/bedroom_fan_daytime_master.json` to `/api/config/automation/config/<id>`), then run the script with both instance files and check both are `state=on`.

Or import via URL: `https://raw.githubusercontent.com/leviemartin/Blueprints_Home/main/bedroom_fan_daytime.yaml`. Full contract: `requirements_bedroom_fan_daytime.md`.

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
Heats a bathroom heating rack by the **room** temperature sensor — never the rack's own internal
sensor — for two daily windows (morning, evening) using a dynamic **ΔT-based warmup formula** that
self-adjusts across seasons — no calendar boundaries needed. A **restart deadband** keeps the rack off
once the room reaches its 22 °C target, and it restarts only if the room drops `restart_deadband`
below that line. The ventilator no longer pauses heating; a boost toggle gives a room-governed ad-hoc
heat-up; a vacation toggle switches the rack off.

### Features
*   **🌡️ Dynamic Warmup:** Computes lead time from the current room-to-target temperature gap (`warmup_base + warmup_per_degree × ΔT`, clamped between a floor and a cap), so cold winter mornings get a longer pre-heat than warm summer mornings without any calendar configuration.
*   **🎯 Room-Sensor Thermostat (v3.0.0):** The blueprint, not the rack, decides when the element runs. A window (or boost) heats only while the room sensor is below the room target; it stops at target and restarts only below `target − restart_deadband` (default 0.3 °C). The rack's own sensor is never read for this decision — `drive_setpoint` (24 °C) only caps the element inside the device. With no room sensor (primary and every backup non-numeric) the rack stays idle, the priority label reads `_blind`, and a warning is raised.
*   **📅 Dual-Slot Routines:** Primary + optional secondary slot per phase (Morning A = every day 06:45→07:45, Morning B optional; Evening A = every day 18:30→19:30, Evening B optional). Evening slots can skip the pre-heat lead entirely (`evening_preheat: false`, the default) and open exactly at their start time, or pre-heat like the morning (`evening_preheat: true`). A hold-until at or before target-warm is taken as the next day (the slot is evaluated per calendar day, so it still ends at midnight).
*   **⚡ Ad-hoc Boost Toggle:** Flip an `input_boolean` for an instant N-minute heat-up toward a room-governed boost target. Auto-expires cleanly; boost is explicit intent.
*   **🌀 No Fan Pause:** Scheduled windows keep heating through ventilator cycles — the exhaust fan no longer blocks heating.
*   **🏖️ Vacation Mode:** Optional `input_boolean`(s) switch the rack off.
*   **🪶 Idempotent:** Evaluates every minute for precise timing, rounds both the idle and drive setpoints to the device `target_temp_step` and clamps them to the device range, and only sends climate service calls on actual transitions.
*   **🔍 Debug-Friendly:** Manual "Run" produces a persistent notification dumping all computed state (room temp, primary/backup/known, setpoint step/range/idle/drive, mode, heating_now, each slot's ΔT / warmup / open / hold_until / in_window, the winning target source / target / line / call, winning priority, desired mode + setpoint).
*   **📱 Mobile Push:** Opt-in push via HA Companion (`notify.mobile_app_*`) for high-signal events — climate unavailable (once, after 5 min), room sensor offline (once, after 10 min, and again if the backup then also goes non-numeric for 10 min while the primary is still dead), and warmup started (once per transition, dismissed when the setpoint returns to idle). Targets are filtered to `notify.*` names, every push runs after the climate calls, and an empty list disables push. A target that does not exist aborts the run at the push step (HA does not suppress a missing action) — check it exists after editing.

### Requirements
*   `climate` entity for the heating rack (tested on a Tuya cloud thermostat element that reports `unknown` while on)
*   Primary room temperature sensor (`device_class: temperature`) — the bathroom humidity sensor's temperature entity, not the rack's own sensor
*   Optional backup room temperature sensor(s), used in order while the primary is non-numeric
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
*   **🔇 Strict Beep Budget:** Unlimited commands before bedtime; after bedtime `ac_hold` issues at most 3 (mode, setpoint, night fan — typically 1–2) and the deep-night check at most 1; `fan_only` issues at most 4 at the lock (typically 1), plus a guard trip on a night that drifts — a bare `turn_on` and an unconditional `set_hvac_mode` (2 beeps, so the unit always restarts in cooling mode, never whatever mode it last held) and up to two settle corrections (setpoint, fan) and one deep-night nudge (typically 2, worst case 5); a heat backstop (v1.2.0) unconditionally corrects the mode (`set_hvac_mode`, never `turn_off`) if the unit is ever found running in `heat` mode — ≤ 1 command per tick while a heat read persists, and nothing latches. NIGHT-HOLD and DEEP-HOLD issue zero commands (ac_hold; in fan-only mode the night guard may bring the unit back once, then re-checks it for 15 minutes); every climate call is idempotency-guarded. Known limitation: a person's off stamped inside the 180 s right after a lock that leaves the unit on (already over band) is treated as the blueprint's own off, and the guard may switch the unit back on at its next 5-minute tick (`turn_on` + cooling mode); an off stamped after that 180 s window is respected until wake — switch it off again after 19:33 to be safely past the window.
*   **🌙 Night Fan (v1.0.3):** The fan mode locked in at bedtime is an input (default low), matched case-insensitively to the unit's modes, with a notice if the unit lacks it.
*   **✋ Manual Override (v1.1.0):** A setpoint changed on the unit during the pre-cool is left alone until the bedtime lock; a unit switched off inside the pre-cool window stays off for the night; one notice per override.
*   **📅 Daily Forecast Backstop (v1.1.0):** Between hourly fetches the prediction uses the day's forecast high instead of the live outdoor reading alone.
*   **🎚️ Auto-Learn Helper Range (v1.1.0):** The auto-learn write is clamped to the whole numbers inside the helper's own range, skipped when that range does not overlap −60…120, with a notice while the range is narrower.
*   **🌀 Fan-Only Night Hold (v1.2.0):** `night_mode: fan_only` pre-chills the warmest bedroom below ideal, parks the AC at the lock and switches it off, then hands the night to the Bedroom Fans — a Night guard restores the parked state and cooling mode (with a 15-minute live-read settle check) only if a room drifts over ideal + tolerance; a heat backstop corrects the mode (never switches the unit off) if it is ever found running in heat mode.
*   **🛡️ Limits-aware setpoints (v1.2.1):** No pre-cool setpoint command is sent while the AC entity has not reported numeric min/max limits (they can be missing on the tick that turns the unit on); the next tick sends the clamped value, the manual-override detection is paused on such a tick, and a notice reports a unit that runs 5 minutes without limits. Fixes the rejected 16 °C drive setpoint (bug #30).
*   **🪭 Bedroom Fans (v1.2.0):** Ceiling fans written under one edge-triggered rule — configured, available, not already at target, interlock clear (including its clear hold), untouched since the reference — with a live re-check before every command, odd/even day-parity fan-assist / night-fan experiments, and no command ever sent to a fan the safety cutoff or a person just touched. An interlocked fan whose own on-transition lands inside this blueprint's active write window (fan-settle or fan-assist, armed only when the matching night-fan / fan-assist experiment is actually on for the night, plus a 120 s grace past each window's end) and within the last 120 s is switched off immediately if an interlock is active — this can only cancel a write this blueprint itself could have issued, so a deliberate start outside those windows, or an older one, is never touched (the safety cutoff's own manual-override contract stays authoritative). Fan writes and the skipped-fan notice run on every real tick — including while the AC entity is unavailable — and are skipped only during vacation.
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
