# Requirements: Bathroom Ventilator Blueprint

## Overview
An intelligent bathroom ventilator automation using dew point comparison for the Dutch climate (Laren, Netherlands). Controls an exhaust fan via a smart plug based on indoor/outdoor moisture conditions.

## Goals
1. **Humidity Management:** Keep bathroom humidity below 60% RH to prevent mold.
2. **Dew Point Intelligence:** Use indoor vs. outdoor dew point comparison (not raw RH%) to determine if ventilation is effective.
3. **Shower Detection:** Automatically detect showers via sustained motion + humidity spike, and ventilate for 15-45 min.
4. **Night Mode:** No fan activity between 22:00-05:30 except for shower detection.
5. **Air Refresh:** Periodic 10-min cycles every 3 hours (daytime only), toggleable for when trickle vents are installed.
6. **Mold Safety:** Force fan ON if humidity exceeds 85% for 60+ minutes, regardless of all other conditions.

## Hardware
- Smart plug (switch entity) controlling the ventilator
- Aqara temperature + humidity sensor (indoor)
- Philips Hue motion sensor
- OpenWeatherMap weather entity (outdoor temp + humidity)

## Key Thresholds (all configurable)
- Target humidity: 60% RH (fan stops below this)
- High humidity: 75% RH (non-shower ventilation trigger)
- Mold alarm: 85% RH sustained 60+ min
- Dew point delta minimum: 2.0°C (below this, ventilation is ineffective)
- Shower detection: 10% RH rise + 5 min sustained motion
- Hysteresis: 5% RH buffer to prevent cycling

## Dew Point Logic
Uses the Magnus formula to compute dew point from temperature and relative humidity:
- Td = (243.04 * alpha) / (17.625 - alpha)
- alpha = (17.625 * T) / (243.04 + T) + ln(RH / 100)

Ventilation is effective when indoor dew point exceeds outdoor dew point by > 2°C.

## Priority Order
1. Mold safety override (always)
2. Target achieved — stop fan
3. Post-shower ventilation (day + night)
4. High humidity, non-shower (day only, dew point gated)
5. Air refresh cycle (day only, humidity gated, toggleable)
6. Default — fan OFF
