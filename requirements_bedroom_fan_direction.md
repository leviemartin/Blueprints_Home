# Bedroom Fan Direction v1.0.0 — Requirements

Governing plan: `docs/superpowers/plans/2026-09-25-bedroom-fan-direction-v1.0.0.md` (epic #44,
session #45), amended by A1 (advisory only) at
`/home/martin/AI/reviews/fan-direction-20260925/discovery-phases/amendment-a1-advisory-only.md`.
Blueprint: `bedroom_fan_direction.yaml`. Tests: `tests/test_bedroom_fan_direction_structure.py`
and the direction additions in `tests/test_bedroom_fans_deploy_consistency.py`.

## Purpose

**A1: advisory only.** This blueprint never sends a command of any kind to the fan — no
`set_direction`, `turn_on`, `turn_off`, `set_percentage` or `toggle`. Its only writes are the
season toggle (`input_boolean`) and notifications. Every evening it decides whether the season
is winter or summer from the forecast night low and writes that decision to the toggle; it then
checks whether the fan's *reported* direction matches what the toggle implies and, if not, tells
Martin so — by a persistent notification and a push. Martin changes the fan's direction himself,
in the Tuya app or with the remote, while the fan is off. Nothing in Home Assistant reverses the
fan.

A Home Assistant start and a manual Run evaluate everything and issue nothing (`is_tick` is
false, so nothing is due).

## Inputs

| Input | Selector | Default |
|---|---|---|
| `fan` | fan entity | required — read only, never commanded |
| `season_toggle` | input_boolean entity | required — off = summer, on = winter |
| `weather_entity` | weather entity, hourly forecast | required |
| `outdoor_sensor` | sensor entity, multiple | `[]` — first entry used, live backstop only |
| `notify_services` | text, multiple | `[]` |
| `fan_name` | text | `"the fan"` |
| `summer_direction` | select forward/reverse | `forward` |
| `winter_direction` | select forward/reverse | `reverse` |
| `outdoor_cold` | number, −10…20, step 0.5 °C | `8.0` |
| `outdoor_warm` | number, 0…30, step 0.5 °C (must exceed `outdoor_cold`) | `14.0` |
| `decide_time` | time | `18:00:00` |
| `night_start` | time | `19:30:00` |
| `night_end` | time | `07:15:00` |
| `write_toggle` | boolean | `true` — off evaluates and advises without ever writing the toggle |

Every input is passed through the top-level `variables:` as `<name>: !input <name>`.

**Triggers:** `tick` (`time_pattern`, minutes `/1`) and `ha_start` (`homeassistant` start,
evaluate only). No toggle trigger and no global condition. `mode: single`, `max_exceeded: silent`.

## Decision rule (season toggle)

**Stage A** is the four evaluation ticks starting at `decide_time`, then +15, +30 and +45 minutes
(`stage_a_ticks`). `decide_time` is valid only between 12:00 and 21:00 (`decide_ok`); outside that
range Stage A never runs and the `bedroom_fan_direction_forecast_<this.entity_id>` persistent
notice reports the misconfiguration ("Decide Time is outside 12:00–21:00...").

At each due Stage A tick, tonight's night low (between `night_start` and `night_end`, tomorrow
morning) is read with this precedence:

1. **Hourly forecast** — the minimum temperature over in-window rows, each row valid only when its
   timestamp parses and its temperature is finite and within −40…45 °C. The hourly low counts only
   when at least 10 distinct in-window timestamps remain, the earliest is within 90 minutes of
   `night_start` and the latest is within 90 minutes of `night_end`. Used only when the weather
   entity is usable: present, not `unavailable`/`unknown`, `temperature_unit` attribute `°C`, and
   `last_updated` within the last 3 hours.
2. **Daily forecast** (backstop) — fetched only when the hourly low failed and the weather entity
   supports `FORECAST_DAILY` (bit 1 of `supported_features`); the `templow` of the entry whose
   local date is tomorrow (never today's row), finite and within −40…45 °C.
3. **Live outdoor reading** — the first `outdoor_sensor` entry, finite, within −40…45 °C, unit
   `°C`, `last_updated` under 2 hours old.
4. **None** — no season decision is made that evening.

A hourly or daily low outside −40…45 °C, non-finite (NaN/inf), or not a number is dropped and
never counted.

**Season target:** winter when the night low is at or below `outdoor_cold` (default 8 °C); summer
when it is at or above `outdoor_warm` (default 14 °C); otherwise hold (cold is tested first, so a
misconfigured `outdoor_warm ≤ outdoor_cold` never yields both). No night low also means hold.

**One toggle change per evening (the latch):** the toggle is written only when Stage A is due,
`write_toggle` is on, the toggle's own state is known, the season target is not hold, the target
disagrees with the toggle's current state, *and* the toggle's `last_changed` is older than this
evening's `decide_start_ts`. A hand flip (or a Stage A write) at any point since `decide_time`
freezes the toggle for the rest of that evening — Stage A never overwrites a change made after its
own first tick, whether by Martin or by itself.

When the night low came from the live reading or is unknown (`forecast_degraded`), the forecast
notice is created (source-specific wording); otherwise it is dismissed. Both branches run at every
due Stage A tick.

## Advisory rule (direction notice)

Read after the toggle write, so it reflects the toggle's live state. `target_direction` is
`winter_direction` when the toggle now reads winter, `summer_direction` when it reads summer (both
default to `reverse`/`forward`), or empty when the toggle or the direction inputs are not in
`{forward, reverse}` — an empty target suppresses the advisory entirely.

`advice_reason` (checked in this order):

- `ok` — the fan reports a direction and it matches `target_direction`.
- `fan_unavailable` — the fan's state is `unavailable`, `unknown` or absent from the state
  machine.
- `direction_unknown` — the fan is present/available but reports no `direction` attribute in
  `{forward, reverse}`.
- `differs` — the fan is available, reports a direction, and it does not match.

Exact wordings (Step 8 of the YAML), all prefixed with `"Night low {{ night_low | round(1) }} °C"`
or `"Night low unknown"`:

- **differs**: `: set {{ fan_name_safe }} to {{ target_direction }} ({{ season }}) while it is
  off. It now reads {{ fan_direction_word }}.`
- **direction_unknown**: `: {{ fan_name_safe }} reports no direction (state
  {{ fan_state_word }}). Check it is set to {{ target_direction }} ({{ season }}) while it is
  off.`
- **fan_unavailable**: `: {{ fan_name_safe }} is {{ fan_state_word }}; its direction cannot be
  checked. It should be {{ target_direction }} ({{ season }}) tonight.`

**When it fires:** at the first Stage A tick of the evening, and again on a later Stage A tick
only if that tick changed the toggle. Because the toggle changes at most once per evening, this
caps the advisory at **two pushes per evening**. The persistent notice
(`bedroom_fan_direction_advice_<this.entity_id>`) is created first, then the same text is pushed
to every entry in `notify_services` that matches `^notify[.][a-z0-9_]+$` (`notify_list`), via a
`repeat: for_each` over that filtered list — so a malformed service name (other than the trailing-newline variant in Residuals) is dropped,
never sent; a
well-formed but unregistered one raises `ServiceNotFound` and aborts the remaining pushes. The persistent notice is created before the push loop specifically because
Home Assistant re-raises `ServiceNotFound` for a missing notify service despite
`continue_on_error: true`; ordering it first means the notice is never lost even if a later push
fails.

**Dismissal:** on any quarter-hour tick (`:00/:15/:30/:45`) where the direction now matches
(`direction_ok`), the advice notice is dismissed. It is not re-created between quarter-hours, so
it clears within 15 minutes of Martin fixing the direction.

## Notification ids

| Stem | Id | Fires on |
|---|---|---|
| forecast | `bedroom_fan_direction_forecast_<this.entity_id>` | every Stage A tick — created when the season was decided on the live reading or not decided at all; dismissed otherwise; created (misconfiguration text) when `decide_time` is out of range |
| advice | `bedroom_fan_direction_advice_<this.entity_id>` | created per the advisory rule above; dismissed on a quarter-hour tick that finds the direction matching |

## Actors and cooperation rules

| Actor | Role |
|---|---|
| **C**, the safety cutoff | Unchanged. Not commanded by this blueprint; no concurrency, since this blueprint sends no fan write. |
| **N**, daytime v1.1.0 | Unchanged (off-only, 08:00 switch-off and the daytime run limit). Not commanded by this blueprint. |
| **P**, pre-cool v1.2.1 | Unchanged. Its 19:29 night write and fan-assist writes are not commanded or contested by this blueprint. |
| **D**, the Hue dimmer v4.0 | Unchanged. Fan holds, scenes, the Off/+/− buttons. Not commanded by this blueprint. |
| **T**, nightlight v1.3.0 | Unchanged. Not commanded by this blueprint. |
| **S**, seasonal direction v1 | **Deleted** at deploy (T7). Its role — deciding the season and reversing the fan — is replaced by this blueprint's toggle decision plus an advisory notice; nothing in Home Assistant reverses the fan any more. |

Because this blueprint issues no fan service of any kind, it has no concurrency with any fan
writer; the only physical-safety-relevant act in this chain is deleting S (boundary B5) and its
disabled-on-load rollback.

## Boundaries

- **B5** (X–old seasonal S at deploy): both S and this blueprint react to the season toggle; S
  answers a toggle change with a fan write (stop/restart if the fan is on). This blueprint's Stage
  A toggle write must therefore never reach a live S — deploy order is the runbook's: step 0 read-only
  checks incl. the F1 drain check (stop on any deviation), 0b turn S off with `stop_actions: true`
  and confirm off / `current == 0` / `last_triggered` unchanged (stop on deviation), 1 delete S and
  confirm absent, then save the blueprint and create this blueprint's instance; rollback restores S only disabled-on-load
  and only on a separate go. This is the one physical-safety path left in the chain.
- **B6** (trust boundary): `weather_entity` (Met.no, internet) and `outdoor_sensor` (internet) are
  read as validated numbers only (finite, −40…45 °C, unit °C, fresh, enough distinct forecast
  timestamps); a bad forecast can at worst flip the toggle once per evening and produce a wrong
  advisory, never a fan command. Notice bodies are fixed wording with validated numbers and enum
  words only — never a raw forecast string.
- **B7** (authorization/deletion): every live write at deploy (turn off S with `stop_actions: true` (0b), delete S, blueprint save, instance
  create, forced-check config, real config, rollback) needs Martin's go; S is restored only with
  `initial_state: false` in the POSTed body and only on its own go.
- **B8** (toggle writer concurrency — Stage A vs Martin's hand flips): Stage A writes the toggle
  at most once per evening, only at its four ticks, only when the toggle's `last_changed` is older
  than today's `decide_time` (the latch). A hand flip after `decide_time` freezes Stage A for that
  evening; a hand flip before it may be overridden at `decide_time` when the night low is outside
  the band. Writes are idempotent. There is no toggle trigger, so a flip never re-enters this
  blueprint.
- **B9** (notify-service input): `notify_services` is Martin's config text; each entry is admitted
  only if it matches `^notify[.][a-z0-9_]+$`. The templated `service: "{{ repeat.item }}"` exists
  only inside the one `repeat` over that filtered list, `continue_on_error: true`, and the
  persistent notice is created before the push loop, so a missing service never loses the notice.

## Deploy runbook (T7)

From `/home/martin/AI/projects/Blueprints_Home` after merge, Martin's go before each numbered live
write, run between 12:00 and 16:00 so the forced check's `decide_time` falls inside the valid 12:00–21:00
range (**F10**) and completes before the real 18:00 evaluation.

0. Read-only preconditions: fan off, toggle off, `weather.home_sm` available; live
   `GET /api/config/automation/config/samuel_fan_seasonal_direction` byte-equal to
   `deploy/samuel_fan_seasonal_direction.retired.json` (else stop); `GET /api/services` lists
   `notify` → `mobile_app_martin_fold`; S's own attributes read `current == 0` and
   `last_triggered` null or older than the 2026-09-25 audit (**F1** — S drain check). Any failed
   precondition above (including S ran since the audit, or is running) → stop and report; do not
   delete S, do not create the new instance.
0b. GO: `automation.turn_off` S with `stop_actions: true`; confirm state `off`, `current == 0`,
   `last_triggered` unchanged. Any deviation → stop and report; do not delete S, do not create the
   new instance.
1. GO (only after 0b passed): `DELETE
   /api/config/automation/config/samuel_fan_seasonal_direction`; confirm
   `automation.samuel_fan_seasonal_direction` absent from `/api/states`. If S is still present
   after the DELETE → stop and report; do not create the new instance.
2. GO: `bash scripts/deploy-blueprint.sh bedroom_fan_direction.yaml
   leviemartin/bedroom_fan_direction.yaml` (blueprint save only, no instance argument).
3. GO: `POST /api/config/automation/config/bedroom_fan_direction_kids` with the real instance
   file; confirm `state=on` and `attributes.id`; after 2 minutes the tick traces show no service
   call other than `dismiss(advice)` at a :00/:15/:30/:45 tick (**F7**).
4. Forced check. **4a** (Martin, no go needed): flip the toggle ON by hand with the fan off
   reading forward; for 2 minutes the tick traces show no service call and no push arrives. **4b**
   GO (**F2** — explicit toggle-write suppression): build a scratch config from the real instance
   file with `jq '.use_blueprint.input += {"decide_time": "<next quarter-hour ≥ 5 min ahead, within 12:00–21:00>",
   "outdoor_cold": -10, "outdoor_warm": 30, "write_toggle": false}'` and POST it; at that tick the
   trace shows `[get_forecasts hourly, dismiss(forecast), create(advice),
   notify.mobile_app_martin_fold]` with `night_low_source` hourly, no `input_boolean` call (hold
   band and `write_toggle: false` both suppress it), no fan service; exactly one push reading "set
   kids fan to reverse (winter)". **4c** GO: POST the real instance file again; Martin flips the
   toggle back OFF by hand (before 18:00, so the latch allows the evening write); the next quarter
   tick shows only `dismiss(advice)` and the persistent notice is gone. Any deviation → stop; S
   stays deleted; rollback only on Martin's go.
5. Observe the 18:00 evaluation the same evening (first observation evening).

No live fan write anywhere in this runbook.

## Rollback (R, B5/R2-03)

Each step on Martin's go, stop on any failed prerequisite:

1. `automation.turn_off` this blueprint's instance with `stop_actions: true`; confirm `off` and no
   running trace.
2. `DELETE /api/config/automation/config/bedroom_fan_direction_kids`; confirm absent; dismiss the
   two persistent notice ids by hand.
3. Only if Martin separately asks for S back: `POST
   deploy/samuel_fan_seasonal_direction.restore-disabled.json` (carries `initial_state: false`),
   then confirm `automation.samuel_fan_seasonal_direction` reads `off` before any other step;
   re-enabling S's blind stop/restart needs its own explicit go.

The season toggle is untouched, and no fan command is sent in any rollback step.

## Residuals (documented, accepted)

- The 8/14 °C band (`outdoor_cold`/`outdoor_warm` defaults) is unvalidated on a local winter;
  re-check the first evening the night low reads below 8 °C.
- The master-bedroom instance is deferred; only the kids-room instance
  (`deploy/bedroom_fan_direction_kids.json`) is deployed.
- The `notify_services` filter regex (`^notify[.][a-z0-9_]+$`) accepts a value with a trailing
  newline — `$` matches just before a trailing `\n`, not only end-of-string. Whether the call then resolves
  to the name without the newline or raises (aborting the remaining pushes) depends on Home
  Assistant's template/service-name handling and is not verified; either way the persistent notice
  (created first) already exists. Only Martin's own config can supply it.
