# LG AC Climate Control — Requirements

## Overview

Per-floor automated climate control for LG air conditioners using external
temperature sensors for reliable ambient readings. Optimizes for energy
efficiency through outdoor-aware deadband logic and proportional fan control.
v1.1.0 additionally minimizes command traffic (every LG-accepted command
beeps — there is no API-level beep disable for LG split units) and respects
manual human input.

## Hardware Requirements

- **AC Unit:** LG air conditioner connected via SmartThinQ or LG ThinQ
  integration (exposes a `climate` entity)
- **Temperature Sensors:** One or more per floor (e.g., Aqara WSDCGQ11LM)
- **Weather Entity:** Any `weather` entity with a `temperature` attribute
  (e.g., Met.no) for outdoor readings
- **Door Sensor (Optional):** Binary sensor for garden/balcony door

## Home Assistant Requirements

- **input_boolean helper:** For vacation mode toggle
- **input_text helper (Optional, per floor):** Expected-state store for
  manual-override hold; feature is inert without it
- **Integration:** SmartThinQ Sensors or LG ThinQ (cloud or local)

## Functional Requirements

### Climate Control
1. Automatic mode selection: heat if below range, cool if above, off if inside
2. Configurable comfort range with separate low/high bounds
3. Deep hysteresis (v1.2.0): an actively heating/cooling AC continues until
   the room is a configurable margin (default 0.5 °C; the operator's
   living-room instance sets 1.0) inside the range, then turns OFF. While the
   deadband is active, the commanded setpoint aims `max(device step, 0.5 °C)`
   past that release point so the external room sensors — not the unit's
   internal one — decide when it is reached. If the device's setpoint grid or
   min/max limits leave no valid deep setpoint for a mode, that mode falls
   back to v1.1.0 boundary idling and a persistent notification is raised
4. Outdoor-aware deadband: when outdoor temp is extreme, AC holds in
   maintenance mode (low fan at boundary) instead of turning off
5. 10-minute polling loop for temperature checks
6. Idempotent command policy: a control tick sends a command only when it
   would change the AC's state — steady state is command-silent (and beep-free).
   v1.2.0 adds genuine off/on cycles, whose transitions beep by design — the
   operator's explicit silence-over-beeps trade

### Fan Control
1. Proportional fan speed based on distance from comfort boundary
2. Multi-stage time-based escalation when target isn't reached, applied only
   while the room is at least the low-fan threshold from target
3. Dynamic fan mode discovery from the climate entity's `fan_modes` attribute

### Scheduling
1. Per-day start/end operating times (7 pairs)
2. Overnight window support (e.g., 22:00 → 06:00); a window belongs to the
   day it starts and its tail past midnight is honored
3. AC turns off within one control tick (≤10 min) of the window ending

### Overrides
1. Vacation mode: forces AC fully off via input_boolean; control resumes
   immediately when toggled off
2. Door sensor: AC turns off at exactly the configured delay after the door
   opens (dedicated timed trigger), except across HA restarts — last_changed
   resets at boot, so shut-off resumes within door_off_delay of startup
3. Manual-override hold: a human change via remote/app (mode, setpoint beyond
   ±0.3 °C, or fan) is detected against the last automation-commanded state
   and honored for a configurable hold window (default 60 min). Vacation,
   schedule end, and door-open still force off during a hold. Requires a
   dedicated helper per instance.

### Safety & Degradation
1. Sensor failure: holds current AC state, fires persistent notification;
   sensors silently stale beyond a configurable window (default 90 min) are
   excluded from aggregation
2. Weather entity failure: deadband defaults to active (normal cycling),
   never maintenance-on-missing-data
3. Comfort range validation: blocks operation if low >= high or if twice the
   hysteresis margin exceeds the range (equality is legal since v1.2.0 — the
   release thresholds meet at the midpoint; the deep-pull feasibility gates
   keep the active targets strictly apart)
4. Graceful handling of AC entity unavailability
5. Warnings self-dismiss when their condition heals
6. HA restart never triggers a false manual-hold detection
7. Safety overrides (vacation/schedule/door) act even when all temperature
   sensors are stale or unavailable
8. A transient cloud command failure can produce one spurious manual-hold
   window (self-clears); floors sharing one LG account can fail correlated
   at the /10 boundary
