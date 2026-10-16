# Livingroom FP300 live audit

## Source

Read-only GET requests by the orchestrator on 2026-10-16. Nothing was written to Home Assistant, and no credential or address is recorded here.

## Instance

- id: `1767031159524`
- entity_id: `automation.circadian_living_room_lights_v1_0_4`
- alias: "Circadian Living Room Lights v2.1.1"
- state: on, mode: restart
- Only one circadian living-room instance exists.
- Snapshot (immutable, never deployed): `deploy/circadian_livingroom_1767031159524.live-v2.2.0.json`

## Blueprint path

HA blueprint path: `leviemartin/circadian_livingroom.yaml`. The copy in HA is v2.2.0 and has the same trigger, condition, action and variables as the repo file. Its input blocks differ only by HA normalisation (selector formatting, same defaults).

## Entities

| Role | entity_id | device_class / unit | present |
|---|---|---|---|
| FP2 presence | `binary_sensor.presence_sensor_fp2_e863_presence_sensor_1` | occupancy | yes |
| FP2 lux | `sensor.presence_sensor_fp2_e863_light_sensor_light_level` | illuminance, lx | yes |
| FP300 presence | `binary_sensor.living_room_main_fp300_couch_occupancy_sensor` | occupancy (same class as the FP2, so the existing binary_sensor/occupancy selector fits) | yes |
| FP300 battery | `sensor.living_room_main_fp300_couch_battery_sensor` | not recorded | yes |
| FP300 lux (not used) | `sensor.living_room_main_fp300_couch_light_sensor_light_level` | not recorded | yes |
| FP300 humidity (not used) | `sensor.living_room_main_fp300_couch_humidity_sensor` | not recorded | yes |
| FP300 temperature (not used) | `sensor.living_room_main_fp300_couch_temperature_sensor` | not recorded | yes |

## Notify target check

`notify.mobile_app_martin_fold` exists (1 of 8 live notify services).

## Live inputs and dry-run

Dry-run of the live instance against the repo blueprint (v2.2.0): INVALID. Unknown input keys: `govee_brightness_scale`, `govee_lights`, `hue_lights`, `light_entity`. They are leftovers from an older schema. HA ignores them and the automation still runs. This card records them and does not fix them; the migration card removes them.

Live lux thresholds are `lux_on_threshold` 394 and `lux_off_threshold` 611, not the blueprint defaults 150/400. The migration keeps 394/611 ("lux unchanged" means unchanged from today's behaviour, not from the code defaults). This is the orchestrator's decision and can be reverted.

Not set in the live instance, so blueprint defaults apply: `override_entity`, `presence_timeout`, `ceiling_brightness_scale`, `lux_off_duration`, `time_evening`, `evening_effect`, `night_effect`.

## Overlap matrix

Totals: 157 automations. 115 configs read via the config API, 42 YAML-defined (not readable via API, 404) and checked by YAML grep.

| Automation | id | state | shared entities |
|---|---|---|---|
| Circadian living room instance | `1767031159524` | on | itself (FP2 presence sensor 1, FP2 lux, 13 lights) |
| Dinner-table instance | `1767830683624` | off | none. Uses `binary_sensor.presence_sensor_fp2_e863_presence_sensor_2` (another zone of the same FP2) and `light.go_table_lamp_1/2` |
| Adjacent-room instance | `1773749905520` | on | none |
| lg_sleep_movie | no live instance | n/a | none |
| 42 YAML-defined automations (house alarm, door-status lights, 72h countdown, video health, nightlight Matthew) | not readable via API (checked by YAML grep) | n/a | none |

YAML grep method: read-only grep over `automations.yaml`, `scripts.yaml`, `scenes.yaml`, `configuration.yaml` and the 11 files in `packages/` (secrets files were not fetched) for the FP2 presence sensor 1, the FP2 lux sensor, the FP300 entities and all 13 light ids of the instance. No hit outside the circadian instance.

Checked against the v3.0.0 rules: either-on/both-clear, presence_timeout 5 min, and late_night_timeout 1 min between 23:00 and 06:30. No other automation uses these entities, so none of those rules can clash with another automation.

## GET failures

Only the 42 x 404 from the config API for the YAML-defined automations, covered by the YAML grep above.

Conclusion: no conflict found.
