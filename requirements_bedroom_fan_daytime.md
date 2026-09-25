# Bedroom Fan Daytime v1.1.0 — Requirements

Governing plan: `docs/superpowers/plans/2026-09-25-bedroom-fan-daytime-v1.1.0.md` (epic #39,
session #42). Blueprint: `bedroom_fan_daytime.yaml`. Tests:
`tests/test_bedroom_fan_daytime_structure.py` and
`tests/test_bedroom_fans_deploy_consistency.py`.

v1.1.0 replaces v1.0.0 (session #40; vacancy switch-off and kids nap lifecycle). The nap
toggle lifecycle, dimmer gestures, gate, vacancy/activity sensors and the configuration
notice are removed. Rollback: redeploy v1.0.0 from commit `14ae934`.

## Purpose

Upstairs ceiling fans are started by hand (dimmer holds, the dashboard), by the pre-cool
night write and by the seasonal-direction restart, and are then often left running all day.
This blueprint limits daytime running:

1. At `day_start` (08:00) any fan still running from the night is switched off.
2. Between `day_start` and `day_end` (08:00–18:00) a fan that is switched on, by anyone or
   anything, runs for `max_run_minutes` (120) and is then switched off.
3. From `day_end` to `day_start` (18:00–08:00) nothing is switched off. Pre-cool and manual
   control work as before, and a fan started at 17:00 keeps running past 18:00.

It is **off-only**. Its only service is one `fan.turn_off`. It never switches a fan on and
never changes speed or direction. One instance per room: kids room and master bedroom.

## Actors and cooperation rules

| Actor | Role |
|---|---|
| **N**, this blueprint | Switches a running fan off at 08:00 and after the maximum run inside the day window. |
| **C**, the safety cutoff | Authoritative and unchanged. Turns the kids fan off on height-gated motion and resumes it after 3 clear minutes. |
| **D**, the Hue dimmer v4.0 | Unchanged. Fan holds, scenes, the Off/+/− buttons. |
| **P**, pre-cool v1.2.1 | Unchanged. Night fan writes at 19:29; fans are left alone at wake. |
| **S**, seasonal direction v1 | **Deleted.** Direction advisory is now `bedroom_fan_direction` v1.0.0, which sends no fan command; nothing in Home Assistant reverses the fan. |
| **T**, nightlight v1.3.0 | Unchanged blueprint. Its instance no longer sets `nap_toggle`, so it paints the fixed 12:30–15:30 nap window (the v1.2.0 behaviour). |

The only concurrency is N's `fan.turn_off` against the other writers. An off can never cancel
the cutoff's pending resume, and N never triggers C (C fires on PIR on-transitions) or S. P's
19:29 write lies outside N's window; at 08:00 P's night fans are switched off.

## Inputs

| Input | Selector | Default |
|---|---|---|
| `fan` | fan entity | required |
| `day_start` | time | `08:00:00` |
| `day_end` | time | `18:00:00` (exclusive; must be later than `day_start`) |
| `max_run_minutes` | number, 15–600 min | `120` |

Every input is passed through the top-level `variables:` as `<name>: !input <name>`.

**Triggers:** `tick` (time_pattern, minutes `/1`) and `ha_start` (homeassistant start). There
are no state triggers and no global condition. `mode: queued`, `max: 10`,
`max_exceeded: silent`.

## Predicates

One action-level `variables:` step, defined in this order. HA renders each key separately
and hands the next key the `literal_eval`'d result, so only strings, booleans and unix
timestamps are stored, never a State object.

- `is_real_trigger = trigger is defined and trigger.id is defined and trigger.id == 'tick'`.
  An `ha_start` run and a manual Run evaluate everything and issue nothing.
- `now_ts = as_timestamp(now())`; `day_start_ts = as_timestamp(today_at(day_start))`;
  `day_end_ts = as_timestamp(today_at(day_end))`; `in_day = day_start_ts <= now_ts < day_end_ts`.
- `fan_state` = the fan's state string, or `'absent'` when the fan is not in the state
  machine; `fan_on = fan_state == 'on'`.
- `on_since_ts` = `as_timestamp(states[fan].last_changed)` when the fan is present, else 0.
  While the fan reads on, `last_changed` is the instant it went on. A speed or direction
  change is an attribute update and does not move it.
- `from_night = on_since_ts < day_start_ts` (running since before today's `day_start`).
- `run_expired = now_ts - on_since_ts >= max_run_minutes * 60`.
- `off_due = is_real_trigger and in_day and fan_on and (from_night or run_expired)`.

## Action

One `choose` with one option and no default. Its condition re-checks live state:
`off_due and is_state(fan, 'on') and day_start_ts <= as_timestamp(now()) < day_end_ts`. Its
sequence is exactly one `fan.turn_off` (target `{{ fan }}`, `continue_on_error: true`).

Nothing else: no other service of any kind, no notifications, no helpers, and no
`wait_template`, `delay`, `wait_for_trigger` or `repeat`.

## Acceptance examples (pinned by the tests)

1. A night fan (on since 19:29 yesterday) is switched off at the 08:00 tick; at 07:59 nothing.
2. A fan switched on at 07:50 is still from the night and is switched off at 08:00.
3. A fan switched on at 10:00 is not switched off at 11:59 and is switched off at 12:00.
4. A fan switched on at 16:30: no off at 17:59, and nothing from 18:00 on; it runs into the
   evening and is a night fan at the next 08:00.
5. A fan on at 17:00 whose speed changes at 17:30 keeps `on_since` 17:00; nothing before 18:00.
6. Cutoff during a run: on 10:00, cutoff off 11:00, resume 11:03 → `on_since` 11:03 → off at
   13:03.
7. Tuya flap: unavailable 10:30, on again 10:32 → `on_since` 10:32 → off at 12:32.
8. A fan that is off, unavailable, unknown or absent: no command and no error.
9. `ha_start` and a manual Run: no service call even when the other conditions hold.
10. Live re-check: the snapshot says due but the fan reads off meanwhile, or the live clock
    has crossed 18:00 → no command.
11. The master and kids instances are independent.
12. The nightlight instance has no `nap_toggle` and paints the fixed window (the nightlight's
    own tests cover the empty-input path).

## Instances and deploy

Instances (`trace.stored_traces` 60, inputs = `fan` only, defaults for the rest):

- **kids**: `deploy/bedroom_fan_daytime_kids.json`, id `bedroom_fan_daytime_kids`,
  "Kids room — fan daytime v1.1.0", fan `fan.ceiling_fan_light_v2`.
- **master**: `deploy/bedroom_fan_daytime_master.json`, id `bedroom_fan_daytime_master`,
  "Master bedroom — fan daytime v1.1.0", fan `fan.ceiling_fan_light_v2_2`.

The instance ids are unchanged, so the live automations are migrated in place. Their entity
ids stay `automation.kids_room_fan_daytime_v1_0_0` and
`automation.master_bedroom_fan_daytime_v1_0_0`, because an alias change does not rename them.

Deploy: `bash scripts/deploy-blueprint.sh bedroom_fan_daytime.yaml
leviemartin/bedroom_fan_daytime.yaml deploy/bedroom_fan_daytime_kids.json
deploy/bedroom_fan_daytime_master.json`, then the nightlight instance
(`deploy/nightlight_1766142134972.json`, without `nap_toggle`). Only after that, when no
instance references them any more, delete the helpers `input_boolean.kids_nap` and
`input_datetime.kids_nap_since`.

## Residuals (documented, accepted)

- A cutoff resume or a Tuya availability flap is an off/on cycle and restarts the run, so the
  fan runs up to `max_run_minutes` after the resume (examples 6 and 7). This fails toward a
  longer run and is never an on.
- A fan switched on late in the afternoon runs into the evening: nothing is switched off from
  18:00 to 08:00, and the fan is a night fan at the next `day_start` (example 4).
- The inherited 10–60 s cloud command lag: an off may land up to a minute late. A tick that
  finds the fan still on sends the off again, which is harmless.
- A Home Assistant restart may reset the fan's `last_changed` to the start instant. The run
  is then counted from the restart, which fails toward a longer run. A night fan still
  goes off at 08:00 when the restart happened before `day_start`.
