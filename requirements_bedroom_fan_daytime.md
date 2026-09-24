# Bedroom Fan Daytime v1.0.0 — Requirements

Governing plan: `docs/superpowers/plans/2026-09-24-bedroom-fan-daytime-v1.0.0.md` (epic #39,
session #40). Blueprint: `bedroom_fan_daytime.yaml`. Tests:
`tests/test_bedroom_fan_daytime_structure.py`.

## Purpose

Ceiling fans upstairs are started by hand (dimmer holds, the dashboard), by the pre-cool
night write and by the seasonal-direction restart, and are then often left running in an
empty room all day. This blueprint switches a running fan **off** once the upstairs has
been vacant for `vacancy_minutes` inside the day window `[day_start, day_end)`.

It is **off-only**. Its only fan service is one `fan.turn_off` per run. It never switches
a fan on and never changes speed or direction. For the kids room it also owns the nap
toggle lifecycle, so a nap is never interrupted: while a nap is on, the room's fan is left
exactly as it is.

One instance per room: kids room (with the nap lifecycle) and master bedroom (without it).

## Actors and cooperation rules

| Actor | Role |
|---|---|
| **N**, this blueprint | Switches a running fan off after vacancy inside the day window. Owns the kids nap lifecycle (start, end, cap, forced end, stale reset, dashboard fallback). |
| **T**, nightlight v1.3.0 | Reads the nap toggle and paints the nap colour. It never touches a fan. |
| **C**, the safety cutoff | Authoritative and unchanged. Turns the kids fan off on height-gated motion and resumes it after 3 clear minutes. |
| **D**, the Hue dimmer v4.0 | Unchanged. Fan holds, scenes, the Off/+/− buttons. |
| **P**, pre-cool v1.2.1 | Unchanged. Night fan writes at 19:29 (settle until 20:14); fans are left alone at wake. |
| **S**, seasonal direction v1 | Unchanged. A season flip stops the fan, lets it coast, reverses it and restarts it. |

- **C–N** (kids fan, the fanprotection PIR): N issues `turn_off` only and never an on, so it
  cannot cancel the cutoff's pending resume. The off is **not** gated on the PIR. The PIR's
  clear and the resume's landed on both count as activity, so after any cutoff event the fan
  runs at least `vacancy_minutes` before N acts. N does not re-trigger C, because C fires
  only on PIR on-transitions.
- **D–N** (kids fan, buttons, gate): fan holds (long_press) are manual starts and stops, so a
  hand-started fan is off after the vacancy timeout unless a nap is on. Off short_release
  with the gate lit starts a nap. +/− short_release with the gate dark, or the gate turning
  on, ends it. initial_press and long_press never start or end a nap.
- **P–N** (both fans): P writes at 19:29 and at wake, both outside N's window. N writes
  nothing to a fan from 18:00 to 08:00. At 08:00, P's night fans are switched off after
  vacancy. Deploy invariant: P's fan windows lie outside `[day_start, day_end)`. With
  fan_assist on (not live), N may switch an assist fan off after vacancy. P does not
  rewrite a touched fan, so this cannot loop (documented v1 limitation).
- **S–N** (kids fan): a flip during the day restarts the fan with S's own on. That counts as
  activity, and the fan is switched off after vacancy. N never writes direction, and N's
  off never triggers S.
- **T–N** (nap toggle): N owns the lifecycle. T only reads the toggle and repaints on its
  transitions.

## Inputs

`fan` is required. Every other input has a default, so the deploy dry-run passes with
`fan` alone.

| Input | Selector | Default |
|---|---|---|
| `fan` | fan entity | required |
| `activity_sensors` | binary_sensor, multiple | `[]` (raises a configuration notice) |
| `day_start` | time | `08:00:00` |
| `day_end` | time | `18:00:00` |
| `day_end_margin_minutes` | number (min) | `5` |
| `vacancy_minutes` | number (min) | `20` |
| `nap_toggle` | input_boolean | `[]` |
| `nap_since_helper` | input_datetime | `[]` |
| `nap_start_button` | event | `[]` |
| `nap_end_buttons` | event, multiple | `[]` |
| `gate_entity` | light | `[]` |
| `nap_max_hours` | number (h) | `3` |
| `enable_notifications` | boolean | `true` |

Every input is passed through the top-level `variables:` as `<name>: !input <name>`.
Optional single-entity inputs use the gate idiom (`x if x is string and x | length > 0 else
none`). No `is_state`, `state_attr` or `states()` call ever receives a list.

**Triggers:** `tick` (time_pattern `/1`), `ha_start` (homeassistant start), `nap_toggle`
(state, no to/from), `nap_start` (state on the start button), `nap_end` (state on each end
button), `gate_on` (state on the gate, `to: on`). **Global condition** (restored-trigger
guard): `trigger.id is not defined or trigger.id in ['tick', 'ha_start'] or
(trigger.from_state is not none and not (trigger.from_state.attributes.restored |
default(false)))`. `mode: queued`, `max: 10`, `max_exceeded: silent`.

## Predicates (plan C2, verbatim)

- `is_real_trigger` (first, as defined under Triggers); `now_ts`; `day_start_ts = as_timestamp(today_at(day_start))`; `day_end_ts` likewise; `wrap_ts = day_end_ts - day_end_margin_minutes*60`; `in_day = day_start_ts <= now_ts < day_end_ts`.
- `fan_obj = states[fan]` (none when absent); `fan_avail = fan_obj is not none and fan_obj.state not in ['unavailable', 'unknown']`; `fan_on = fan_avail and fan_obj.state == 'on'`; `fan_touch_ts = as_timestamp(fan_obj.last_updated) if fan_obj is not none else 0` (R1-06: an absent fan never aborts the variables step) (a state or attribute change, a flap or any writer's landed command all count — a flap only delays an off).
- `occupied_now` = any configured sensor reads `on`. `sensor_ts` = the latest `last_changed` over the configured sensors (a sensor reading `off` contributes its last clear, Martin's rule; a sensor reading `unavailable`/`unknown` contributes the instant it dropped; a sensor absent from the state machine contributes 0).
- `has_nap` = `nap_toggle` and `nap_since_helper` both configured and both present in the state machine and not `unavailable`. `nap_on = has_nap and is_state(nap_toggle, 'on')`; `since_ts` = the since helper's timestamp (0 when unset); `toggle_ts` = the toggle's `last_changed` (0 without `has_nap`); `gate_on` = gate configured and `on`.
- `activity_ts = max(sensor_ts, fan_touch_ts, toggle_ts)`; `vacant = not occupied_now and now_ts - activity_ts >= vacancy_minutes*60`.

**Definition order is normative** (HA renders a `variables:` step top to bottom; each line uses only names defined above it — R1-01 delta):

- `trig_to = trigger.to_state if (trigger is defined and trigger.to_state is defined and trigger.to_state is not none) else none`; `gesture = trig_to.attributes.get('event_type', '') if trig_to is not none else ''` — no nested attribute access on a possibly undefined `trigger.to_state` (tick, ha_start and manual runs have none; HA's Undefined is not chainable, R1-02); every other use of `trigger.to_state`/`from_state` goes through the same guard. `since_fallback_due = is_real_trigger and has_nap and trigger.id == 'nap_toggle' and trig_to is not none and trig_to.state == 'on' and trigger.from_state is not none and trigger.from_state.state == 'off' and |since_ts - as_timestamp(trig_to.last_changed)| > 60` (a dashboard flip; N's own start wrote the since first, so no rewrite).
- `effective_since_ts` = `as_timestamp(trig_to.last_changed)` when `since_fallback_due`, else `since_ts` (the dashboard flip's own instant is the nap start for this run, R1-01/R2-01); `nap_stale = nap_on and now_ts >= day_start_ts and effective_since_ts < day_start_ts`; `nap_cap = nap_on and now_ts - effective_since_ts >= nap_max_hours*3600`; `nap_forced = nap_on and in_day and now_ts >= wrap_ts`.
- `nap_start_due = is_real_trigger and has_nap and not nap_on and trigger.id == 'nap_start' and gesture == 'short_release' and gate_on and day_start_ts <= now_ts < wrap_ts`. `nap_end_due = is_real_trigger and nap_on and ((trigger.id == 'nap_end' and gesture == 'short_release' and not gate_on) or trigger.id == 'gate_on' or nap_cap or nap_forced or nap_stale)`.
- `exempt = (nap_on and not nap_stale) or nap_start_due`. `off_due = is_real_trigger and in_day and fan_avail and fan_on and vacant and not exempt`.
- `config_error` = exactly one of `nap_toggle`/`nap_since_helper` configured, or a configured helper missing/`unavailable`, or `activity_sensors` empty, or a configured activity sensor absent from the state machine (R1-11), or the fan absent from the state machine (R1-06). A configuration error never suppresses an off and raises one notice. Only a nap-helper error (exactly one of the two configured, or a configured nap helper missing/`unavailable`) disables the nap lifecycle, through `has_nap`; a missing activity sensor or a missing fan leaves `has_nap`, the exemption and the cap/forced/stale housekeeping untouched (R2-04, R1-03 delta).

**Implementation notes, with the same names and meaning:**

- HA renders each `variables:` key on its own and passes the `literal_eval`'d result to the
  next key, so a State object cannot be stored in a variable. For that reason `fan_obj`
  holds a snapshot dict (`state`, `last_updated` as ISO text) and `trig_to` holds one too
  (`state`, `last_changed` as ISO text, `attributes.event_type`). The formulas above work
  on these dicts unchanged.
- `is_real_trigger` is `trigger is defined and trigger.id is defined and trigger.id !=
  'ha_start'`.
- Helper ids after the gate idiom are `nap_toggle_id`, `nap_since_id`, `gate_id` and
  `sensor_ids`. `config_problems` is the list behind `config_error`.

## Action order and allowed services

1. The variables step.
2. Nap start, gated on `nap_start_due`: `input_datetime.set_datetime` on the since helper
   with `timestamp: now_ts`, then `input_boolean.turn_on`.
3. Since fallback, gated on `since_fallback_due`: `set_datetime` with `timestamp:
   effective_since_ts`.
4. Nap end, gated on `nap_end_due`: `input_boolean.turn_off`.
5. Vacancy-off: one `choose` whose branch repeats the rule on live state (`off_due and
   is_state(fan, 'on')` and no activity sensor reads on). It issues exactly one
   `fan.turn_off` with `continue_on_error: true`.
6. Configuration notice.

There is no `wait_template`, `delay`, `wait_for_trigger` or `repeat`. Allowed services:
`fan.turn_off`, `input_boolean.turn_on`, `input_boolean.turn_off`,
`input_datetime.set_datetime`, `persistent_notification.create` and
`persistent_notification.dismiss`. Nothing else is allowed: no `homeassistant.*`,
`script.*`, `automation.*`, and no fan service other than turn_off. Every helper write
targets the `nap_toggle` or `nap_since_helper` input variable and never a literal entity.
The helper writes also carry `continue_on_error: true`, so a failing helper call cannot stop
the run before the fan step.

## Nap lifecycle

- **Start:** Off-button short_release while the gate is lit, inside `[day_start, wrap)`
  (08:00–17:55), with no nap on. The since helper is written first (= now), then the
  toggle. An Off tap during a nap does nothing (the since is unchanged), and so does an Off
  tap with the gate dark or an Off long_press.
- **End:** a +/− short_release with the gate dark, the gate turning on, the cap
  (`nap_max_hours` after the since), the forced end at `wrap` (17:55) inside the day, or the
  stale reset (at any real run at or after `day_start` when the since is older than today's
  `day_start`). An unset since (the helper was never written) counts as 0, so the nap ends
  at the next real tick.
- **Dashboard fallback:** when the toggle is switched from off to on by hand, N writes since =
  the transition instant, unless the helper already holds an instant within 60 s (N's own
  start wrote it first). In that same run the flip's instant is the nap start, so a stale
  since cannot end the nap straight away (R1-01).
- **Exemption:** while a nap is on and not stale, the fan is left exactly as it is: never
  started, never changed, never switched off. A nap start run is exempt too.
- **Activity:** a nap end (cap, forced or manual) is a toggle transition and therefore
  activity, so it grants one more vacancy period. The 08:00 stale reset does not exempt: the
  same run issues the nap end and the fan off (example 8, R1-03).
- **Night:** between 18:00 and 08:00 only the toggle and its since helper may change, as the
  toggle's own housekeeping (cap, a dashboard flip's since). No fan command is sent.
- **Restart and manual Run:** the `ha_start` run and a manual Run evaluate everything and
  write nothing. The first tick after boot continues a live nap. Replays of buttons, the
  toggle and the gate are stopped by the restored-trigger guard.

## Notices

There is one persistent notification per instance, with the fixed id
`bedroom_fan_daytime_config_{{ this.entity_id | replace('.', '_') }}`. It is created while
`config_error and enable_notifications` and dismissed otherwise. Both calls happen only on a
real trigger inside the day window, so a start, a manual Run and the night write nothing
(decided by the worker, recorded for the orchestrator). The message lists every problem. No
other notification exists in v1.

## Helpers and deploy order

Helpers are HA configuration. A blueprint never creates them:

- `input_boolean.kids_nap`, name **"Kids nap"** (icon `mdi:sleep`). Goes on a dashboard.
- `input_datetime.kids_nap_since`, name **"Kids nap since"**, has_date + has_time. Stays off
  dashboards.

Neither helper has an `initial` value, so both restore across restarts. Instants are read
as `state_attr(<input_datetime>, 'timestamp') | float(0)`.

Deploy order: **helpers → nightlight v1.3.0 → this blueprint → its two instances.**

1. Create both helpers. Read back `/api/states` and require exactly the two entity ids
   above. On any other id, stop: the instance JSONs pin these ids.
2. Deploy the nightlight and its instance.
3. `bash scripts/deploy-blueprint.sh bedroom_fan_daytime.yaml leviemartin/bedroom_fan_daytime.yaml`
   (blueprint/save only).
4. POST each instance once (`deploy/bedroom_fan_daytime_kids.json`,
   `deploy/bedroom_fan_daytime_master.json`) to `/api/config/automation/config/<id>`. Then
   run the script again with both instance files. Read the automation entity ids back from
   the alias slugs; never assume them.

Instances (`trace.stored_traces` 60):

- **kids** (`bedroom_fan_daytime_kids`, "Kids room — fan daytime v1.0.0"): fan
  `fan.ceiling_fan_light_v2`; activity sensors `binary_sensor.stairs_motion` and
  `binary_sensor.samuel_samuel_matthew_fanprotection`; nap toggle `input_boolean.kids_nap`;
  since helper `input_datetime.kids_nap_since`; start button `event.baby_room_button_4`; end
  buttons `event.baby_room_button_2` and `event.baby_room_button_3`; gate
  `light.kids_room_gate`.
- **master** (`bedroom_fan_daytime_master`, "Master bedroom — fan daytime v1.0.0"): fan
  `fan.ceiling_fan_light_v2_2`; activity sensor `binary_sensor.stairs_motion`; no nap
  inputs.

## Live steps (plan stage 8; each actuation authorized)

- **a)** With the gate dark, flip the toggle on. Expect the nap colour and since = the flip
  instant. Flip it off and the light goes off.
- **b)** With the gate lit, an Off tap turns the toggle on with since = now. A + tap with the
  gate dark turns it off. The kids fan is untouched throughout.
- **c)** Master vacancy-off: one `fan.turn_off` within 21 min plus lag, and no other call.
- **d)** Cutoff path: no N call during the hold, the resume is not cancelled, and the off
  comes 20 min after the later of the clear and the resume.
- **e)** First night: zero N fan calls from 18:00 to 08:00, and the 08:00 sweep.
- **f)** Optional restart during a nap: the toggle and since are unchanged, and `ha_start`
  issues nothing.

Rollback: disable or delete the two instances. The helpers may stay.

## Residuals (documented, not fixed in v1)

- R1-07: the 17:55 forced end is a toggle transition and therefore activity. A fan still
  running then is not switched off before 18:00 (20 min vacancy > 5 min margin). It runs
  until P's 19:29 write and the 08:00 sweep. This is not unsafe.
- The inherited 10–60 s cloud command lag. An off lands late, and a parent's start inside
  that lag is cancelled once (example 19).
- The hand-started master fan is seen only through its own state change, because only the
  stairs PIR sees the master room (example 3).
- A dead stairs PIR switches a running fan off while the room is occupied (example 15).
  This is the safe direction.
- A Tuya availability flap delays an off by one vacancy period (example 10).
- The same-second dashboard-flip race: the nap may end at once; flip it again (Decided 6).
- A possible `last_updated` churn from the cloud feed would keep a fan on. This is an
  observation criterion (Deferred 16).
- Seasonal v1's unverified stop and resume-cancel (R2-03) are unchanged.
- N's off of an assist fan when fan_assist is on. There is no loop (Deferred 10).

## Deferred to v2

See the governing plan's **Deferred** list
(`docs/superpowers/plans/2026-09-24-bedroom-fan-daytime-v1.0.0.md`, section "Deferred (for
the follow-up epic, filed at closing with Martin's go)"). None of its items is partly
implemented here.
