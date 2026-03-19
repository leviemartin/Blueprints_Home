# LG AC Climate Control — Requirements

## Overview

Per-floor automated climate control for LG air conditioners using external
temperature sensors for reliable ambient readings. Optimizes for energy
efficiency through outdoor-aware deadband logic and proportional fan control.

## Hardware Requirements

- **AC Unit:** LG air conditioner connected via SmartThinQ or LG ThinQ
  integration (exposes a `climate` entity)
- **Temperature Sensors:** One or more per floor (e.g., Aqara WSDCGQ11LM)
- **Outdoor Sensor:** Any sensor entity with `device_class: temperature`
- **Door Sensor (Optional):** Binary sensor for garden/balcony door
- **Sound Switch (Optional):** The `switch` entity exposed by the LG
  integration for the AC's beep sound

## Home Assistant Requirements

- **input_boolean helper:** For vacation mode toggle
- **Integration:** SmartThinQ Sensors or LG ThinQ (cloud or local)

## Functional Requirements

### Climate Control
1. Automatic mode selection: heat if below range, cool if above, off if inside
2. Configurable comfort range with separate low/high bounds
3. Outdoor-aware deadband: when outdoor temp is extreme, AC holds in
   maintenance mode (low fan at boundary) instead of turning off
4. 10-minute polling loop for temperature checks

### Fan Control
1. Proportional fan speed based on distance from comfort boundary
2. Multi-stage time-based escalation when target isn't reached
3. Dynamic fan mode discovery from the climate entity's `fan_modes` attribute

### Scheduling
1. Per-day start/end operating times (7 pairs)
2. Overnight window support (e.g., 22:00 → 06:00)
3. AC turns off immediately when operating window ends

### Overrides
1. Vacation mode: forces AC fully off via input_boolean
2. Door sensor: AC turns off after configurable delay when door is left open
3. Sound mute: always keeps AC beep switch off

### Safety
1. Sensor failure: holds current AC state, fires persistent notification
2. Comfort range validation: blocks operation if low >= high
3. Graceful handling of AC entity unavailability
