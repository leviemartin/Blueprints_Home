# Requirements: Bathroom Ventilator Blueprint (v2.0.0)

## Overview
Demand-controlled bathroom exhaust fan for the Dutch climate (Laren). An on/off fan on a smart plug is driven by indoor humidity, outdoor dew point, presence and a manual boost. The fan never runs on a timer schedule: trickle vents supply background air, the fan exhausts on demand (ASHRAE 62.2 §5 demand-controlled mode; Bbl art. 3.67 lid 6 is a capacity minimum, met by the TURBOE.125 at 230–345 m³/h).

## Goals
1. **Outdoor-conditioned targets:** the effective stop target is the higher of the configured target (60 % RH) and the indoor RH whose dew point equals outdoor dew point + margin (2 °C). The start threshold is the higher of the configured high-humidity start (75 %) and the effective stop target plus hysteresis (5 %). The fan stops where ventilation stops helping.
2. **Shower detection at any hour:** a humidity jump of ≥ 6 % between two consecutive sensor reports (the Aqara T1 reports instantly on that change) with bathroom motion within the last 15 min. Quiet hours (22:00–05:30) only block new non-shower starts.
3. **Bounded runs:** every run lasts at least 15 min and at most 45 min, except while a boost or the mold override is active (those outrank the cap: a boost runs its full runtime, the mold override runs until RH drops below 85 % or the outdoor air is no drier); a run continues while RH is above the effective stop target. A manual OFF on the plug is honoured for shower/high-humidity runs; mold override and degraded mode re-assert on the next evaluation.
4. **Mold safety:** RH ≥ 85 % with drier outdoor air forces the fan on at any hour, with one notification.
5. **Degraded mode:** humidity sensor unavailable ≥ 10 min → one push + persistent notification; the fan then runs 20 min after any motion until the sensor returns (second push on recovery).
6. **Boost:** an `input_boolean` toggle forces the fan on for 20 min, then clears itself.
7. **Stateless:** every trigger re-decides from live entity state; timing comes from `last_changed`; no delays, so boost and sensor loss interrupt instantly.

## Hardware (live 2026-09-07)
- `light.on_off_plug_1` — innr On/Off plug on the Hue bridge, feeds the TURBOE.125 tube fan (25–29 W, 29–34 dBA)
- `sensor.temp_sensor_bathroom` + `sensor.temp_sensor_bathroom_humidity_sensor` — Aqara T1 via Aqara Hub M2 (HomeKit); reports on ΔRH ≥ 6 % / ΔT ≥ 0.5 °C, else hourly
- `binary_sensor.bathroom_motion` — Hue motion sensor (bridge-controlled clear delay)
- `weather.home_sm` (Met.no, has `dew_point`) primary; `weather.openweathermap` fallback
- `input_boolean.bathroom_fan_boost` — dashboard boost toggle
- `notify.mobile_app_martin_fold` — push target

## Decision order (first match wins)
1. boost active → ON
2. sensors unavailable for ≥ 10 min → ON iff motion within the last 20 min (a shorter outage holds the fan as it is)
3. mold override (RH ≥ 85 %, indoor dew point above outdoor) → ON
4. fan on for < 15 min → stay ON
5. fan on for ≥ 45 min → OFF
6. shower signature → ON
7. fan on and RH > effective stop target → stay ON
8. fan off, RH > start threshold, not quiet hours → ON
9. otherwise → OFF

## Psychrometrics
Magnus: α = 17.625·T/(243.04+T) + ln(RH/100); Td = 243.04·α/(17.625−α).
Adaptive floor: RH_floor = 100·exp(17.625·Td'/(243.04+Td') − 17.625·T/(243.04+T)) with Td' = outdoor dew point + margin; 100 when Td' ≥ T.
Example: bathroom 22 °C, outdoor dew point 16 °C, margin 2 → floor 78.1 %; the fan stops at 78 % instead of running toward an unreachable 60 %.

## Testing & debugging
Manual "Run" writes a persistent notification with every computed variable (weather entity used, outdoor dew point, floor, stop/start targets, fan minutes, presence, flags, decision). `tests/test_bathroom_ventilator_structure.py` pins the schema, triggers, decision order and renders the psychrometric and decision rows.
