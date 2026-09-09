# Research validation — climate blueprints follow-up (bedroom_precool v1.1.0 + lg_ac_climate v1.3.0)

**Date:** 2026-09-09 · **Repo:** Blueprints_Home · **Entry:** Stack B C (epic #18, session #19) · **Mode:** Standard (3 Sonnet research agents, orchestrator verification of every verdict-bearing citation) · **HA:** Core 2026.9.0

## 1. Scope answers

Skipped (mid-flow invocation). Use case, constraints and locked decisions come from issue #19's kickoff and epic #18: (a) LG presence gating = setback, not off, configurable delta, resume on return, a new guest-mode toggle holds comfort; (b) replace the dead `forecast`-attribute fallback with a real `weather.get_forecasts type: daily` call; (c) manual-override handling during PRECOOL/NIGHT_HOLD is *designed here, not assumed*. Philosophy: stateless blueprints, beep budget, smallest correct diff (standard dial, PonyTail full).

## 2. Verdict: **proceed** (with noted uncertainty)

All three design questions are answered by primary sources plus two orchestrator-run live probes on this HA, and nothing contradicts the locked decisions. Three items stay open and are carried into the spec as explicit choices rather than consensus: the 2 °C default delta sits at the *ceiling* of the Dutch heat-pump guidance (not its middle); the 10-minute away debounce has one precedent, not three; and manual-override detection must use the blueprint's own known command values (design C) because HA `Context` inspection is provably blind for this automation — with a documented residual false-positive (a failed command at turn-on combined with an odd remembered setpoint).

## 3. Approach summary

`lg_ac_climate.yaml` v1.3.0 widens the comfort band by `away_setback_delta` while every presence entity has been away for `away_delay_minutes` and no "home indicator" (guest mode, EV car home, presence-unreliable guard) is on; on return the band snaps back on the next tick or the return trigger. `bedroom_precool.yaml` v1.1.0: (Task 0) clamps the auto-learn write to the helper's live min/max ∩ −60…120 with a state-driven notification when the helper is narrower; (R1-07) fetches a daily forecast on every day-side tick whose hourly window is empty and takes today's `temperature` (the day's high) as the fallback; (R1-04) tests call `scripts/deploy-blueprint.sh --dry-run`; (override) a live setpoint that is none of the values the blueprint itself could have commanded is treated as manual and respected until the next phase boundary; a unit switched off inside the pre-cool window (after `bedtime − lead_cap`) stays off.

## 4. Evidence by claim

| # | Claim (design-affecting) | Tier / sources | Quote (≤200 chars) | Independence | Status |
|---|---|---|---|---|---|
| C1 | Setback should be shallow for heat pumps; hydronic/floor systems → none, others 1–2 °C | T1 Milieu Centraal [A1]; T3 leissoF [A9b]; T3 ROBOT [A10] | "Niet lager als je vloerverwarming hebt, een bodemwarmtepomp hebt … 1 graad lager als je woning redelijke isolatie heeft … 2 graden lager als je woning matige isolatie heeft" [A1] | 3 orgs | **verified** (A1 fetched, wording confirmed) |
| C2 | Deep on/off cycling of ductless mini-splits costs efficiency (runs at max capacity) | T1 DOE BA-1407 [A2] | agent quote: house run on/off used 57 % more heating energy than simulated | single T1 | verified by agent; not re-fetched (informs, does not gate) |
| C3 | Manufacturer away modes leave the depth to the user (Daikin Home Leave = absolute setpoints 10–30/18–32 °C) | T1 Daikin manual [A3] | agent quote of the range table | single T1 | verified by agent (informs) |
| C4 | Presence blueprints debounce departures; the only concrete default found is 10 min, re-checked after the delay | T2 Better Thermostat [A6] | "Delay before Away (min) Wait this long after last person leaves 10 … After the delay expires, presence is re-checked before applying the Away preset." | single source | **unverified — single source** (does not gate; adopted as a local default) |
| C5 | `unknown`/`unavailable` handling for presence has no external norm; fail toward comfort is a local choice | T1 HA person docs [A5]; T1 templating docs [A11]; T3 community [A14] | person docs list only home/not_home/zone; "unknown … does not know its value right now" | 3 | verified (absence of a norm) |
| C6 | Immediate resume on return is the industry norm (no ramp) | T1 Nest [A15]; T1 ecobee [A16] | "switches back to its regular heating or cooling schedule when someone comes home"; "resumes the regular schedule" | 2 vendors | verified by agent |
| C7 | Daily forecast entry: `temperature` = day's HIGH, `templow` = LOW (Met.no derives max/min of the hourly readings); daily `datetime` = local noon in UTC | T1 pyMetno source [B9]; T1 HA dev docs [B2] | `None if daily_temperatures == [] else max(daily_temperatures)` / `min(daily_temperatures)`; `hour=12, minute=0, second=0, microsecond=0` | 2 | **verified** (raw source fetched; matches the live probe `2026-09-09T10:00:00+00:00`, 18.1/13.4) |
| C8 | Met.no core integration returns 6 daily and 48 hourly entries | T1 met/coordinator.py [B10]; T1 core PR #150486 [B12] | `get_forecast(time_zone, False, 0)`; `time_zone, True, range_stop=49`; PR merged 2025-09-12 | 2 | **verified** (source + `gh api` merged_at 2025-09-12T08:19:30Z; live probe counts 6/48) |
| C9 | The `forecast` state attribute was deprecated in 2023.9 and removed in 2024.4 → `state_attr(weather,'forecast')` is `None` | T1 HA 2024.4 release notes [B5]; T1 2023.9 notes [B4] | "The previously deprecated forecast attribute of weather entities, has now been removed. Use the weather.get_forecasts service" | 2 | **verified** (B5 fetched, wording confirmed) |
| C10 | `get_forecasts` with an unsupported `type` raises for the whole call (intended); features bits DAILY=1 HOURLY=2 TWICE_DAILY=4 | T3 core issue #104999 [B7]; T1 weather/const.py [B6] | issue closed `not_planned` 2023-12-04 | 2 | **verified** (`gh api` state_reason not_planned; live: `weather.openweathermap` returns nothing) |
| C11 | Met.no polls upstream every 55–65 min; `get_forecasts` serves cached coordinator data | T1 HA met docs [B8] | "weather data every 55 to 65 minutes. The polling interval is randomized to spread load across the Met.no" | single T1 | **verified** (fetched) |
| C12 | `response_variable` is script-run scoped and readable from a later `variables:` step; `continue_on_error` is a general per-action flag | T1 HA scripts docs [B13][B14] | "If a variable was not previously defined, it is assigned in the top-level (script run) scope" | 2 pages, one org | verified by agent; matches the shipped v1.0.3 pattern (works live) |
| C13 | A `time_pattern`-triggered automation's own service calls carry `parent_id=None, user_id=None` — the same shape as an integration push/poll write | T1 automation/__init__.py [C2]; T1 time_pattern.py [C1]; T1 core.py [C6]; T3 community context guide [C14]; **live probe** | `parent_id = None if context is None else context.id` / `trigger_context = Context(parent_id=parent_id)`; live: `climate.livingroom` last written by the LG automation at 09:10:03Z → `{"parent_id":null,"user_id":null}` | 3 files + forum + probe | **verified** (source fetched by the orchestrator; probe 2026-09-09 10:53Z) |
| C14 | `lg_thinq` never writes state inside the service call; state arrives via coordinator poll/MQTT push; `CoordinatorEntity.should_poll=False`; context window 5 s | T1 lg_thinq/entity.py [C7][C9]; climate.py [C8]; update_coordinator.py [C12]; entity.py [C5] | `CONTEXT_RECENT_TIME_SECONDS = 5`; `async_call_api` only awaits the API; `_handle_coordinator_update → async_write_ha_state()` | 4 files | **verified** (orchestrator fetched entity.py/climate.py/mqtt.py) |
| C15 | Setpoint-only changes bump `last_updated` but not `last_changed`; an OFF is a state-string change so `last_changed` moves | T1 core.py State/async_set [C17][C18] | `same_state = old_state.state == new_state … last_changed = old_state.last_changed if same_state else None` | single T1 (+ live: `climate.bedrooms` last_changed 05:15Z, last_updated 07:59Z after an attribute-only push) | **verified** (probe) |
| C16 | Adaptive Lighting detects manual control by remembering the contexts of its own calls (in-process cache) — unavailable to a stateless YAML blueprint | T2 adaptive-lighting README [C15] | "Treat turn-ons without a matching Home Assistant light.turn_on context as manual control" | single T2 | verified by agent (informs design B/C, not gating) |
| C17 | Expected-vs-actual comparison per cycle has precedent (Versatile Thermostat "Fix Incorrect State"), with the opposite polarity (re-assert) and a debounce | T2 versatile_thermostat docs [C16] | "detects these situations and automatically resends the command to synchronize the actual state with the desired state" | single T2 | verified by agent (informs) |
| C18 | LG target temperature reads `null` in some modes (eco preset confirmed; `off` observed live) | T1 core issue #146575 [C20]; live probe | live: `climate.bedrooms` off → `"temperature": null` | issue + probe | verified (already guarded by `current_setpoint_known`) |

## 5. Community consensus signals

- **Setback vs off for inverter air-to-air:** STRONG for "shallow setback, never off for short absences"; hydronic-specific "no setback" advice does not transfer to a fast air-to-air unit without auxiliary heat.
- **Default delta:** MIXED — 1–2 °C ceiling in NL guidance, manufacturers leave it to the user. 2.0 °C is defensible only as a configurable default; 1.5 °C would sit inside the guidance band.
- **Away debounce / unknown handling:** MIXED (no norm). 10 min (one precedent) and "unknown = home" (the house's own security resolver uses the same rule) are local choices.
- **Return behaviour:** STRONG — resume immediately, no ramp.
- **Forecast contract:** STRONG — daily high/low semantics, removal of the attribute, cached reads.
- **Manual-override detection in YAML:** STRONG that context inspection is blind for time-based triggers; MIXED between helper-based expected state (B) and known-value comparison (C) — no source does C verbatim, but its mechanism (compare live to commanded) has precedent.

## 6. Anti-patterns flagged

1. **Turning the heat pump off for short absences** (deep on/off cycling, DOE BA-1407) — the locked "setback, not off" decision already avoids it.
2. **Context-based manual detection on a `time_pattern` automation** — documented blind spot (community guide lists Time pattern: ❌ no parent_id) and confirmed by the live probe; design A is rejected.
3. **Reading `state_attr(weather,'forecast')`** — removed in 2024.4; dead code (R1-07).
4. **Calling `get_forecasts` for a type the entity lacks without `continue_on_error`** — raises and aborts the run (issue #104999); the daily call must be gated on `supported_features` bit 1 *and* carry `continue_on_error: true`.
5. **Re-asserting a setpoint every tick without an override path** — the v1.0.x PRECOOL loop overrides any user change within a minute (the reason for the override item).

## 7. Critique findings

- **What must be true for the design to be wrong?** (i) Martin's LG unit would have to behave like a hydronic system (slow response) for a 2 °C setback to cost more than it saves — it is an inverter split with no resistive backup, so the DOE aux-heat penalty does not apply. (ii) For design C: the unit would have to report setpoints that differ from what was commanded (grid rounding) — the live unit reports `target_temp_step 0.5` and every blueprint value is on the 0.5 grid. (iii) For the daily fallback: Met.no would have to drop today's entry before bedtime — the daily list starts at today's local-noon stamp regardless of the current hour (pyMetno builds days from the local date), and the design still falls back to `outdoor_now` if no entry matches today.
- **Over-weighted sources?** Milieu Centraal dominates the delta question; without it the two installer sources still cap at 1–2 °C, so the conclusion holds. The Better Thermostat 10-min value is a single source and is treated as such.
- **Incentives:** the two Dutch installer pages sell heat-pump/floor-heating services (an incentive to discourage setback); the manufacturer manual (Daikin) is neutral on depth. No vendor source supports the design's specific numbers.
- **Strongest contrarian position:** "Use design B (expected-state helper) — it detects *any* manual change including one to a known value, and the repo already has the pattern in lg_ac_climate.yaml." Answer: B needs a new helper plus a write on every commanding tick, shares C's false-positive class on dropped commands (LG spec residual risk 6, still gated there), and adds state to a deliberately stateless blueprint; C covers the requested case (a setpoint change) with zero helpers and no writes, and the one blind spot (a manual change *to* a blueprint value) simply yields the v1.0.x behaviour. B remains the documented fallback if C's residual bites in practice.

## 8. Contested claims

None material. Minor: setback depth (1 °C vs 2 °C) — installer sources lean 1 °C, the agency allows 2 °C for poorly insulated homes; resolved as a configurable default with the spec stating the trade-off (`proceed-with-noted-uncertainty`).

## 9. Unverified claims (not gating)

- `weather.get_forecast` (singular) removed in 2024.6 — agent-reported, no page opened; irrelevant to the design (the blueprint already uses the plural).
- Better Thermostat 10-minute departure delay — single source (verified on the page, but only one precedent).
- DOE "setback triggers resistive backup heat" — the primary energy.gov page 404'd; not applicable to this unit anyway.
- `lg_thinq` target temperature `null` specifically in `off` — confirmed live on this unit, not in a published issue.

## 10. Bibliography

**T1**
- [A1] https://www.milieucentraal.nl/energie-besparen/duurzaam-verwarmen-en-koelen/slim-verwarmen-met-een-warmtepomp/ — NL agency; graduated setback rule (fetched, wording confirmed)
- [A2] https://buildingscience.com/documents/bareports/ba-1407-long-term-monitoring-mini-splits-northeast/view — DOE Building America mini-split field study
- [A3] https://www.manualslib.com/manual/561570/Daikin-Ftxd50bvma.html?page=17 — Daikin Home Leave manual
- [A5] https://www.home-assistant.io/integrations/person/ — person states
- [A11] https://www.home-assistant.io/docs/templating/states/ — `unknown` definition
- [A15] https://support.google.com/googlehome/answer/9245535?hl=en — Nest Eco resumes schedule on return
- [A16] https://docs.sb.ecobee.com/reference/resumeschedule — ecobee resumeSchedule
- [B2] https://developers.home-assistant.io/docs/core/entity/weather/ — Forecast TypedDict
- [B4] https://www.home-assistant.io/blog/2023/09/06/release-20239/ — 2023.9 deprecation (history)
- [B5] https://www.home-assistant.io/blog/2024/04/03/release-20244/ — 2024.4 removal (fetched, wording confirmed)
- [B6] https://github.com/home-assistant/core/blob/dev/homeassistant/components/weather/const.py — feature bits
- [B8] https://www.home-assistant.io/integrations/met/ — 55–65 min polling (fetched)
- [B9] https://github.com/Danielhiversen/pyMetno/blob/master/metno/__init__.py — daily high/low derivation, local-noon stamp (raw fetched)
- [B10] https://github.com/home-assistant/core/blob/dev/homeassistant/components/met/coordinator.py — `range_stop=49` (raw fetched)
- [B12] https://github.com/home-assistant/core/pull/150486 — 48 h hourly, merged 2025-09-12 (gh api)
- [B13] https://www.home-assistant.io/docs/scripts/perform-actions/ — response_variable
- [B14] https://www.home-assistant.io/docs/scripts/ — variables scope, continue_on_error
- [B1] https://www.home-assistant.io/actions/weather.get_forecasts/ — action reference (fetched)
- [C1] https://github.com/home-assistant/core/blob/dev/homeassistant/components/homeassistant/triggers/time_pattern.py — no context passed
- [C2] https://github.com/home-assistant/core/blob/dev/homeassistant/components/automation/__init__.py — trigger_context (raw fetched: lines 697–698)
- [C5] https://github.com/home-assistant/core/blob/dev/homeassistant/helpers/entity.py — CONTEXT_RECENT_TIME_SECONDS = 5 (raw fetched)
- [C6][C17][C18] https://github.com/home-assistant/core/blob/dev/homeassistant/core.py — fresh Context(), last_changed/last_updated
- [C7][C9] https://github.com/home-assistant/core/blob/dev/homeassistant/components/lg_thinq/entity.py — async_call_api, coordinator write (raw fetched)
- [C8] https://github.com/home-assistant/core/blob/dev/homeassistant/components/lg_thinq/climate.py — async_set_temperature (raw fetched)
- [C12] https://github.com/home-assistant/core/blob/dev/homeassistant/helpers/update_coordinator.py — should_poll False
- [C13] https://github.com/home-assistant/core/pull/140427 — "several seconds or more" (unmerged PR)
- [C20] https://github.com/home-assistant/core/issues/146575 — target temperature null (eco)

**T2**
- [A6] https://better-thermostat.org/setup/automation-blueprints/ — 10-min departure delay (fetched, wording confirmed)
- [A7] https://github.com/jmcollin78/versatile_thermostat/blob/main/documentation/en/feature-presence.md — presence presets, no default
- [C15] https://github.com/basnijholt/adaptive-lighting — context-matching manual control
- [C16] https://github.com/jmcollin78/versatile_thermostat/blob/main/documentation/en/feature-advanced.md — Fix Incorrect State

**T3**
- [A8] https://github.com/CVKBaca/homeassistant-climate-controller — split-AC blueprint, away setpoints
- [A9] https://github.com/Reproduktor/ExtendedAwayStateBlueprintHassio — 24 h extended-away
- [A9b] https://leissof.nl/kenniscentrum/nachtverlaging-warmtepomp-niet-doen — installer, ≤1 °C
- [A10] https://www.robotclimate.com/kenniscentrum/post/warmtepompen-en-nachtverlaging/ — installer, 1–2 °C
- [A14] https://community.home-assistant.io/t/wth-is-there-not-a-fail-safe-mode-for-generic-thermostat/356954 — no unknown-state norm
- [B3] https://community.home-assistant.io/t/the-previously-deprecated-forecast-attribute-of-weather-entities-has-now-been-removed/713481
- [B7] https://github.com/home-assistant/core/issues/104999 — unsupported type raises, not planned (gh api)
- [B11] https://github.com/orgs/home-assistant/discussions/561 — stale 24 h claim (superseded)
- [B15] https://community.home-assistant.io/t/get-the-hourly-weather-forecast-in-an-automation-trigger/791367
- [C14] https://community.home-assistant.io/t/how-to-use-context/723136 — time_pattern has no parent_id

**T4**
- [A12] https://jgairco.nl/airco-aan-laten-of-uitzetten-verwarmen/ — single installer blog (few hours → 1–2 °C)

## 11. Methodology

Standard mode; 3 Sonnet `research` agents dispatched in parallel (setback consensus 44 tool uses; forecast contract 35; override detection 53), no timeouts. Cross-validation rule 1×T1 / 2×T2 / 3×T3 applied per claim; every verdict-bearing citation (C1, C7, C8, C9, C10, C11, C13, C14) was re-fetched by the orchestrator and the quoted text confirmed on the page or in the raw source; two live probes on this HA (state contexts of both climate entities vs their automations' runs; `get_forecasts` daily/hourly on `weather.home_sm` and `weather.openweathermap`). Total distinct sources: 42.
