# Project Context: Blueprints_Home

## Overview
This project serves as a repository for custom **Home Assistant Blueprints**. The primary focus is on expert-level, research-backed automations for smart home devices, specifically tailored for toddler sleep training and nightlight management.

The core blueprint, `nightlight.yaml`, is designed to work with the **ThirdReality Smart Color Night Light** (Type F) but is compatible with standard RGB lights and motion sensors.

## Architecture & Logic
The logic is contained entirely within the Home Assistant Blueprint YAML format, leveraging:
*   **Jinja2 Templating:** For dynamic time calculations and state management.
*   **State Machine Logic:** Distinct phases for "Night" (Sleep), "Motion Boost" (Safety), and "Wakeup" (Green light).
*   **User Inputs:** Configurable schedules, colors, and brightness levels exposed via the HA UI.

### Key Logic Flow (`nightlight.yaml`)
1.  **Triggers:**
    *   **Time:** 18:00 (Start Night Mode).
    *   **Motion:** `on` (Boost Brightness) / `off` (Return to Sleep Brightness).
    *   **Schedule:** Specific per-day wakeup times.
    *   **System:** `homeassistant.start` (State restoration).
2.  **Variables:** Inputs are mapped to variables (`bri_night`, `bri_boost`) to avoid Jinja2 scope issues. Time windows (`is_night_window`, `is_wakeup_window`) are calculated dynamically at runtime.
3.  **Actions:** A main `choose` block determines the correct light state based on the calculated time window and motion status.

## Key Files
*   **`nightlight.yaml`**: The main blueprint source code. This is the file users import into Home Assistant.
*   **`requirements.md`**: Detailed technical and research-based requirements used to design the automation logic.
*   **`README.md`**: User-facing documentation including installation instructions and configuration guides.
*   **`.github/workflows/`**: Standard Gemini automated workflows for issue triage and management.

## Development & Testing Conventions
*   **Versioning:** Semantic versioning is used in the blueprint name (e.g., `v1.1.2`) to help users track updates.
*   **Testing:**
    *   **Manual Run:** The "Run" action in Home Assistant is supported and includes a persistent notification for debugging.
    *   **Time Manipulation:** Testing involves temporarily changing the "Wakeup Time" input to the near future to verify transitions.
*   **Importing:** Home Assistant caches blueprints aggressively. **Always restart Home Assistant** after updating or re-importing a blueprint to ensure logic changes take effect.
*   **Error Handling:** Logic variables are computed inside the `action` block to ensure that if a template fails, a Trace is generated in Home Assistant for debugging.
