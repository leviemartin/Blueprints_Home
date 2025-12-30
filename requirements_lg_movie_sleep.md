# Home Assistant Blueprint Requirement Document: LG Sleep & Movie

## 1. Overview
**Name:** LG Sleep & Movie  
**Description:** An automation that manages the Light (Display) and Sound (Beep) settings of an LG Air Conditioner based on "Sleep" schedules and a manual "Movie" mode triggered by a remote control.

## 2. Goals
*   **Sleep Mode (Time-Based):** Automatically turn OFF the AC display light and sound during specified sleep hours to ensure a dark and quiet environment.
*   **Movie Mode (Event-Based):** Allow a remote control (Philips Hue) to toggle the AC display/sound OFF for movie watching and ON again afterwards (restoring state).

## 3. Hardware & Entities
*   **LG Air Conditioner:**
    *   **Display Light Entity:** A `switch` entity controlling the AC display (e.g., `switch.living_room_ac_display`).
    *   **Sound/Beep Entity:** A `switch` entity controlling the AC beep (e.g., `switch.living_room_ac_beep`). *Note: Optional, as not all models support this.*
*   **Remote Control:**
    *   **Device:** Philips Hue Dimmer Switch (or similar).
    *   **Trigger:** A specific button press (e.g., "On" button hold, or dedicated scene button).

## 4. Configuration Inputs
The blueprint must expose the following:

### 4.1. Devices
*   `ac_display_switch`: Target switch for the AC display.
*   `ac_sound_switch`: Target switch for the AC sound (Optional).
*   `remote_trigger`: A Device Trigger selector to capture the specific button press from the Hue remote.

### 4.2. Sleep Schedule
*   `sleep_start_time`: Time to automatically turn OFF lights/sound (Default: 22:00).
*   `sleep_end_time`: Time to allow lights/sound again (Default: 07:00). *Note: The automation primarily acts at the START of sleep. The end time might be used to reset, or just strictly defines the window.*

### 4.3. Movie Mode Behavior
*   **Trigger:** The remote button press acts as a **Toggle**.
*   **Action:**
    *   **If Switches are currently ON:** Turn them OFF (Start Movie/Quiet Mode).
    *   **If Switches are currently OFF:** Turn them ON (End Movie/Restore).

## 5. Logic Flow

### 5.1. Sleep Trigger (Time)
*   **Trigger:** Time reaches `sleep_start_time`.
*   **Action:**
    *   Turn OFF `ac_display_switch`.
    *   Turn OFF `ac_sound_switch`.

### 5.2. Movie Trigger (Remote)
*   **Trigger:** Remote button pressed.
*   **Condition:** None (Always allow toggle).
*   **Action:**
    *   Check state of `ac_display_switch`.
    *   **If ON:** Turn OFF both Display and Sound.
    *   **If OFF:** Turn ON both Display and Sound.

## 6. Variables
*   `is_display_on`: `is_state(ac_display_switch, 'on')`
