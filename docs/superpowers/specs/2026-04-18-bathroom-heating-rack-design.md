# Bathroom Heating Rack Automation — Design Spec

## Overview

A Home Assistant blueprint that pre-heats the bathroom using a smart heating rack so it is already at comfort temperature when the household needs it — the adult morning routine and the kids' evening bath routine — while aggressively minimising energy waste outside those windows.

The automation drives `climate.heatingrack_bathroom` (a `climate` entity wrapping the underlying `switch.heating_switch` smart plug) via **setpoint + preset control**, not raw on/off. A **dynamic warmup formula** computes how many minutes of lead time are needed based on the current indoor-to-target temperature gap, so the blueprint self-adjusts across seasons without calendar boundaries. **Predictive motion** (hallway in the morning, stairs in the evening) can pull the auto-start forward when someone is up early. **Ventilator coordination** pauses active heating when the bathroom exhaust fan runs during showers, because evicting freshly heated air is pure waste.

The design mirrors the conventions already established in `bathroom_routine.yaml`, `bathroom_ventilator.yaml`, and `nightlight.yaml`: priority-waterfall `choose` logic, variables computed inside `action:` for trace visibility, stateless re-evaluation on each tick, and idempotent service calls.

## Hardware & Entities

| Device | Role | Blueprint Input |
|---|---|---|
| Climate entity (generic_thermostat wrapper) | Setpoint/preset control of the heating rack | `heating_climate` |
| Aqara bathroom temperature sensor | Indoor temp for ΔT-based warmup calculation | `bathroom_temp_sensor` |
| Philips Hue hall motion sensor | Morning predictive-motion trigger | `hall_motion` |
| Philips Hue stairs motion sensor | Evening predictive-motion trigger | `stairs_motion` |
| Smart plug / light entity controlling exhaust fan | Source of truth for ventilator coordination | `fan_switch` |
| `input_boolean` (optional) | Vacation/full-off switch | `vacation_off` |
| `input_boolean` | Ad-hoc boost toggle | `boost_toggle` |

Observed device profile for `climate.heatingrack_bathroom`:

```
hvac_modes:        ["off", "heat_cool"]
min_temp:          7.0°C
max_temp:          30.0°C
target_temp_step:  1.0°C
preset_modes:      ["eco"]
supported_features: 401
```

Bonus signals available (not required by blueprint but useful for dashboards):
- `sensor.heating_switch_active_power` — live draw in W
- `sensor.heating_switch_total_energy_import` — cumulative kWh

## Blueprint Inputs

31 inputs total, grouped for HA UI legibility.

### Devices (5)

| Input | Selector | Default |
|---|---|---|
| `heating_climate` | `entity` domain `climate` | `climate.heatingrack_bathroom` |
| `bathroom_temp_sensor` | `entity` domain `sensor`, device_class `temperature` | `sensor.bathroom_temperature` |
| `hall_motion` | `entity` domain `binary_sensor`, device_class `motion` | `binary_sensor.hall_motion` |
| `stairs_motion` | `entity` domain `binary_sensor`, device_class `motion` | `binary_sensor.stairs_motion` |
| `fan_switch` | `entity` domain `light` (matches ventilator blueprint convention) | `light.heater` |

### Global Controls (2)

| Input | Selector | Notes |
|---|---|---|
| `vacation_off` | `entity` domain `input_boolean`, `multiple: true` | Multiple/optional so empty default `[]` is safe |
| `boost_toggle` | `entity` domain `input_boolean` | Required |

### Boost Settings (2)

| Input | Range | Default |
|---|---|---|
| `boost_target_temp` | 18–28°C, step 0.5 | 23 |
| `boost_runtime_min` | 10–120 min, step 5 | 30 |

### Morning A — primary morning (4)

| Input | Default |
|---|---|
| `morning_a_days` (multi-select Mon..Sun) | Mon–Fri |
| `morning_a_target_warm` (time) | 06:45 |
| `morning_a_hold_until` (time) | 08:00 |
| `morning_a_target_temp` (18–28°C) | 23 |

### Morning B — optional secondary (4)

| Input | Default |
|---|---|
| `morning_b_days` | `[]` (disabled) |
| `morning_b_target_warm` | 08:30 |
| `morning_b_hold_until` | 10:00 |
| `morning_b_target_temp` | 23 |

### Evening A — kids bath (4)

| Input | Default |
|---|---|
| `evening_a_days` | `[]` (user selects specific bath days) |
| `evening_a_target_warm` | 18:15 |
| `evening_a_hold_until` | 19:30 |
| `evening_a_target_temp` (18–28°C) | 25 |

### Evening B — optional adult evening (4)

| Input | Default |
|---|---|
| `evening_b_days` | `[]` (disabled) |
| `evening_b_target_warm` | 20:30 |
| `evening_b_hold_until` | 22:00 |
| `evening_b_target_temp` | 23 |

### Warmup Formula Tuning (4)

| Input | Range | Default |
|---|---|---|
| `warmup_base_min` | 5–30 min | 10 |
| `warmup_per_degree_min` | 1–15 min/°C | 5 |
| `warmup_min_minutes` | 5–30 min | 10 |
| `warmup_max_minutes` | 20–120 min | 60 |

### Behavior Toggles (2)

| Input | Default |
|---|---|
| `enable_predictive_motion` | true |
| `enable_notifications` | true |

## Triggers

```
mode: restart
max_exceeded: silent
```

| # | Trigger ID | Type | Purpose |
|---|---|---|---|
| T1 | `periodic` | `time_pattern` every 1 min | Re-evaluate state at auto_start precision; enforce boost expiry |
| T2 | `hall_motion_on` | State change on `hall_motion` → `on` | Predictive morning pre-heat accelerator |
| T3 | `stairs_motion_on` | State change on `stairs_motion` → `on` | Predictive evening pre-heat accelerator |
| T4 | `boost_change` | State change on `boost_toggle` | React to manual boost on/off |
| T5 | `vacation_change` | State change on `vacation_off` | Instant P1 handling |
| T6 | `fan_change` | State change on `fan_switch` | Instant ventilator coordination (P2) |
| T7 | `ha_start` | Event `homeassistant.start` | Reconcile state after restart |

**Design rationale:**
- **No explicit time triggers** for target_warm / hold_until. The 1-minute `periodic` tick catches window transitions within 60s — simpler than 16 extra time triggers (4 slots × 4 times).
- **1-minute tick** (vs. 5-min in ventilator blueprint) chosen because auto_start is dynamic and boost expiry needs minute precision. Logic is short; negligible load.
- **`mode: restart`** matches `bathroom_routine.yaml`: any fresh trigger cancels in-flight action and re-evaluates with current state. Idempotent service calls make this safe.

## Computed Variables

All variables computed inside the `action:` block (not top-level) so HA auto-generates traces on any template failure, matching `bathroom_ventilator.yaml` convention.

### Live state

```jinja
indoor_temp       = states(bathroom_temp_sensor) | float(20)     # fallback via climate.current_temperature on unavailability
current_setpoint  = state_attr(heating_climate, 'temperature') | float(7)
current_hvac_mode = states(heating_climate)
current_preset    = state_attr(heating_climate, 'preset_mode')
fan_is_on         = is_state(fan_switch, 'on')
today_dow         = now().strftime('%a') | lower   # "mon", "tue", ...
now_dt            = now()
```

### Vacation & boost

```jinja
vacation_active   = {% if vacation_off is iterable and vacation_off | length > 0 %}
                      expand(vacation_off) | selectattr('state','eq','on') | list | length > 0
                    {% else %} false {% endif %}

boost_is_on       = is_state(boost_toggle, 'on')
boost_age_min     = (now() - states[boost_toggle].last_changed).total_seconds() / 60
boost_active      = boost_is_on and boost_age_min < boost_runtime_min
boost_expired     = boost_is_on and boost_age_min >= boost_runtime_min
```

### Routine slot resolution (repeated identically for MA, MB, EA, EB)

For each slot X with inputs `<x>_days`, `<x>_target_warm`, `<x>_hold_until`, `<x>_target_temp` and associated motion sensor (`hall_motion` for MA/MB, `stairs_motion` for EA/EB):

```jinja
x_in_days           = today_dow in x_days
x_target_warm_dt    = today_at(x_target_warm)
x_hold_until_dt     = today_at(x_hold_until)
x_delta_T           = max(0, x_target_temp - indoor_temp)
x_warmup_min        = min(
                        warmup_max_minutes,
                        max(warmup_min_minutes, warmup_base_min + warmup_per_degree_min * x_delta_T)
                      )
x_auto_start_dt     = x_target_warm_dt − x_warmup_min minutes

# Motion "lead window" = earliest a motion event can pull forward auto_start
x_motion_lead_dt    = x_target_warm_dt − (warmup_max_minutes + 30) minutes

x_motion_last       = states[<slot's motion sensor>].last_changed
x_motion_in_lead    = enable_predictive_motion
                        and x_motion_last > x_motion_lead_dt
                        and x_motion_last < x_target_warm_dt

x_effective_start   = x_motion_in_lead
                        ? min(x_auto_start_dt, x_motion_last)
                        : x_auto_start_dt

x_active            = x_in_days
                        and x_effective_start <= now_dt
                        and now_dt < x_hold_until_dt
```

### Aggregate routine flags

```jinja
morning_active = ma_active or mb_active
evening_active = ea_active or eb_active

# A and B days are contractually non-overlapping (user-enforced: Mon–Fri vs Sat–Sun).
# Tie-break: A wins if both, but this should never occur.
morning_temp   = ma_active ? ma_target_temp : mb_target_temp
evening_temp   = ea_active ? ea_target_temp : eb_target_temp
```

## Action Logic — Priority Waterfall

The `action:` block is structured as four sequential steps so state cleanup does not compete with state-machine decisions:

```
Step 1: compute variables
Step 2: sensor validation (stop: on critical failure)
Step 3: boost expiry cleanup (standalone sequence, not inside the priority choose)
Step 4: priority choose (exactly one of P1–P6 wins)
Step 5: debug notification (manual run only)
```

### Step 3 — Boost expiry cleanup

```yaml
- choose:
    - conditions: "{{ boost_expired }}"
      sequence:
        - service: input_boolean.turn_off
          target: { entity_id: !input boost_toggle }
```

After clearing, the priority choose in Step 4 re-reads `boost_is_on` (now false) and flows to the correct priority without waiting for the next tick.

### Step 4 — Priority order (highest first)

| # | State | Condition | Resolution |
|---|---|---|---|
| **P1** | Vacation / Off | `vacation_active` | mode=`off`, preset=none |
| **P2** | Ventilator coordination | `fan_is_on and (morning_active or evening_active or boost_active)` | mode=`heat_cool`, preset=`eco` |
| **P3** | Ad-hoc Boost | `boost_active` | mode=`heat_cool`, preset=none, setpoint=`boost_target_temp` |
| **P4** | Evening Routine | `evening_active` | mode=`heat_cool`, preset=none, setpoint=`evening_temp` |
| **P5** | Morning Routine | `morning_active` | mode=`heat_cool`, preset=none, setpoint=`morning_temp` |
| **P6** | Idle (default) | _no match_ | mode=`heat_cool`, preset=`eco` |

### Idempotent service calls

Before any service call, compare current vs. desired. Only call services on a real delta:

```yaml
- choose:
    - conditions: "{{ current_hvac_mode != desired_mode }}"
      sequence:
        - service: climate.set_hvac_mode
          target: { entity_id: !input heating_climate }
          data: { hvac_mode: "{{ desired_mode }}" }

    - conditions: "{{ current_preset != desired_preset }}"
      sequence:
        - service: climate.set_preset_mode
          target: { entity_id: !input heating_climate }
          data: { preset_mode: "{{ desired_preset }}" }

    - conditions: >
        {{ desired_setpoint is not none
           and (current_setpoint | float - desired_setpoint | float) | abs > 0.1 }}
      sequence:
        - service: climate.set_temperature
          target: { entity_id: !input heating_climate }
          data: { temperature: "{{ desired_setpoint }}" }
```

Expected: ~1440 evaluation ticks/day → typically 4–10 actual service calls/day (only on transitions). Light on the thermostat, clean traces.

## Error Handling

| Failure | Response |
|---|---|
| `bathroom_temp_sensor` unavailable | Fall back to `state_attr(heating_climate, 'current_temperature')`. If that is also unavailable, `stop:` the tick, raise persistent notification with id `heating_rack_sensor_warning` (idempotent). |
| `heating_climate` unavailable | `stop:` the tick. Single persistent notification with id `heating_rack_climate_unavailable`; auto-cleared when entity returns. |
| `fan_switch` unavailable | Treat as `off` (fail-safe: never pause heating because fan state is unknown). |
| Motion sensor unavailable | Treat as "no motion ever" → fall back to pure time-based `auto_start`. |
| Template evaluation failure | HA generates automatic Trace (variables live in `action:`). `mode: restart` guarantees the next trigger re-evaluates with fresh state. |

A top-level **sensor-validation `choose`** runs before the priority tree (matches ventilator P0 pattern) and `stop:`s on critical failures with a clear message.

## Notifications

Gated by `enable_notifications`. All use `persistent_notification.create` with deterministic `notification_id`s so repeats overwrite rather than stack.

| Event | ID | Example message |
|---|---|---|
| Warmup started (idle → P3/P4/P5) | `heating_rack_warmup_started` | "Bathroom heating: started warmup. Current 18.5°C → target 23°C. ETA ~30 min." |
| Target reached | `heating_rack_target_reached` | "Bathroom at target (23.1°C). Kids bath ready." |
| Sensor warning | `heating_rack_sensor_warning` | "Bathroom temp sensor unavailable; using climate entity fallback." |
| Climate unavailable | `heating_rack_climate_unavailable` | "HeatingRack climate entity unavailable — holding state." |
| Debug (manual run only) | `heating_rack_debug` | Full variable dump (see Testing) |

No notifications for P6 idle, P2 pause, or routine end — avoids noise.

## Testing Approach

### Manual-run debug notification (matches `nightlight.yaml` / ventilator pattern)

Final `choose` branch detects manual trigger and dumps all computed variables:

```
Debug — 07:05:14
Indoor: 19.3°C | Target: 23°C | ΔT: 3.7°C
Day: mon | Fan: off | Vacation: false
Boost: off (age 0m) | expiry: 30m
Morning A: day_match=true, auto_start=06:30, motion_ago=14m,
           effective_start=06:30, active=true
Morning B: day_match=false, ...
Evening A: day_match=false, ...
Evening B: day_match=false, ...
Active routine: Morning A → setpoint 23°C, mode heat_cool, preset none
Decision: set_temperature(23)
```

One-click end-to-end visibility into the state machine.

### Time-manipulation testing

- Temporarily set `morning_a_target_warm` to `now() + 2 min` → observe auto_start reached within seconds on cold bathroom.
- Flip `boost_toggle` ON → observe P3 activation + auto-expiry at `boost_runtime_min`.
- Turn `fan_switch` ON while Morning A active → observe P2 supersedes P5.
- Turn `fan_switch` OFF → observe P5 re-takes with setpoint restored.

### Mental-simulation coverage checklist (to walk during implementation validation)

- [ ] Cold morning: ΔT=8°C → auto_start = target − 50 min
- [ ] Warm morning: ΔT=0.5°C → auto_start clamped to `warmup_min_minutes` before target
- [ ] Motion at 05:30, auto_start=05:55 → effective_start=05:30
- [ ] Motion at 03:00 (outside lead window) → ignored; auto_start=05:55
- [ ] Boost on at 10:00 (no routine) → P3, setpoint 23°C, auto-expires at 10:30
- [ ] Boost on during Morning A → P3 overrides P5
- [ ] Fan on during kids bath (P4 active) → P2 wins, preset=eco
- [ ] Fan off → P4 re-applies, preset=none, setpoint=25°C
- [ ] Vacation toggle on → P1 dominates all
- [ ] Sunday, Morning A = Mon–Fri, Morning B = Sat–Sun → Morning B wins
- [ ] HA restart mid-routine → re-evaluates and resumes correct state within 1 min
- [ ] Both A and B days configured non-overlapping (user guarantee) → no ambiguity

## Open Cleanup (post-validation)

- Delete the orphaned `script.heating_off` — references `switch.heating_bathroom_plug_on_off`, an entity that no longer exists. Last ran before `2026-04-11`.
- Consider deleting or repurposing `input_boolean.bathroomoverride` — used by `bathroom_routine.yaml` for makeup mode; unrelated to heating but worth auditing whether it is still wired.

## Design Principles Preserved From Existing Blueprints

- Waterfall `choose` with priorities (highest wins) — `bathroom_routine.yaml`
- Variables inside `action:` for trace visibility — `bathroom_ventilator.yaml`
- Stateless re-evaluation on every tick — `bathroom_ventilator.yaml`
- Idempotent service calls — new (natural for `climate` domain)
- Manual-run debug notification — `nightlight.yaml`, ventilator
- Deterministic notification IDs — ventilator
- `mode: restart` for responsiveness — `bathroom_routine.yaml`
- Sensor-unavailability fail-safes — ventilator
