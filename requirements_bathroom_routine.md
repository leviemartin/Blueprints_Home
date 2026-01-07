# Requirements: Bathroom Routine Blueprint

## Overview
A comprehensive lighting automation for a bathroom equipped with Philips Hue devices. The automation manages lighting based on motion, time of day (Circadian/Routine phases), and specific toddler sleep needs.

## Goals
1.  **Motion Activation:** Lights turn on when motion is detected and off after a configurable delay (default 5 min).
2.  **Circadian/Routine Rhythm:** Lighting adapts to 4 distinct phases: Morning, Day, Evening, Late Night.
3.  **Toddler Sleep Focus:** "Late Night" mode uses specific colors (Red) and low brightness to preserve melatonin. "Evening" mode forces warm light by 19:00 (or configured time) even in summer.
4.  **Override Control:** Support for a manual "Makeup Mode" (Bright Cool White) via an input boolean or remote.

## Hardware Scope
*   **Motion Sensor:** Philips Hue Motion Sensor.
*   **Main Lights:**
    *   Adore Bathroom Plafondlamp (White Ambiance)
    *   2x Adore Lighted Vanity Mirror (White Ambiance)
*   **Accent Light:**
    *   Philips Hue Go v2 (Color Ambiance) - Critical for "Red" night light.

## Time Blocks & Logic

### 1. Morning
*   **Trigger:** Start Time (Input, e.g., 07:00).
*   **Goal:** Wake up, energize.
*   **Light State:** High Brightness, Cool White (4000K-5000K).

### 2. Day
*   **Trigger:** Start Time (Input, e.g., 09:00).
*   **Goal:** Visibility, Neutral.
*   **Light State:** High/Medium Brightness, Neutral White (3000K-4000K).

### 3. Evening (Toddler Wind-Down)
*   **Trigger:** Start Time (Input, e.g., 18:30) OR Sunset (whichever is *earlier*, or just fixed time to ensure routine).
    *   *Strategy:* Use a fixed "Evening Start Time" input. In summer, sunset is late (22:00), but toddlers sleep at 19:00. A fixed time ensures the "Warm Light" trigger happens for the bedtime routine regardless of the sun.
*   **Goal:** Melatonin production, relax.
*   **Light State:**
    *   Color: Warm White (2200K - 2700K).
    *   Brightness: Dim (configurable).

### 4. Late Night (Sleep)
*   **Trigger:** Start Time (Input, e.g., 22:00 or "Bedtime").
*   **Goal:** Midnight bathroom trips without waking up fully.
*   **Light State:**
    *   **Hue Go:** Red (RGB 255,0,0) or Deep Amber.
    *   **Main Lights:** OFF (Configurable: "Allow Main Lights in Late Night" -> False by default).
    *   **Brightness:** Very Low (1-10%).

### 5. Override Mode (Makeup / Manual)
*   **Trigger:** Input Boolean (On).
*   **Goal:** Maximum visibility for grooming.
*   **Light State:** 100% Brightness, Cool White (4800K).
*   **Priority:** Highest. Overrides all other states/motion delays (lights stay on).

## Inputs (Blueprint)
*   **Devices:** Motion Sensor, Ceiling Light, Mirror Lights (Group?), Hue Go.
*   **Times:** Morning Start, Day Start, Evening Start, Late Night Start.
*   **Brightness/Color:** Per block (where applicable).
*   **Settings:** Motion Timeout (min), Transition Time.
*   **Helpers:** Override Entity (Input Boolean).

## Implementation Details
*   Use `choose` block in `action` to evaluate:
    1.  Override ON? -> Run Override Scene.
    2.  Motion OFF (for X min)? -> Turn Off.
    3.  Motion ON? -> Evaluate Time Block -> Apply Settings.
*   **Seamless Transitions:** Use `transition: 2` (or configurable) in light service calls.
