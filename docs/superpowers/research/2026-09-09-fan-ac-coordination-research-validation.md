# Bedroom ceiling-fan + AC coordination — research validation

Chain: Stack B Entry A, Blueprints_Home epic #25 / session #26 (2026-09-09). Validates the direction Martin chose in the brainstorm before the design spec is written. Companion files: `bedroom_precool.yaml` v1.0.3, `requirements_bedroom_precool.md`, kids-room fan blueprints in `~/projects/ceiling-fan-hue-blueprint/`.

## Scope answers

From the brainstorm (2026-09-09, seven decisions), not re-asked:
- **Use case.** Two upstairs bedrooms (master, kids) with open doors, cooled indirectly by the hall LG unit through `bedroom_precool.yaml`. Both rooms in scope, one shared target (ideal 23 °C); a third room joins later (door closed today) → fan LIST, not two entities. The VeSync Core300S purifier `fan.upstairs_rooms` is out of scope.
- **Constraints.** Kids fan `fan.ceiling_fan_light_v2` is shared with the dimmer (21 % / 1 % toggles), the safety cutoff (height-gated PIR, "manual override wins") and the seasonal flipper; night speed ceiling = very low (1 %) in both rooms; the LG beeps on every command; stateless blueprint, no new helpers unless unavoidable.
- **Tolerance.** Fan-only night hold: band ideal + 1.5 °C (24.5), AC fallback at ANY minute after bedtime, one trip per night; AC off at the bedtime lock after a small pre-chill. Energy goal: AC-off nights whenever the band allows. Season: mild nights from here on, so the design must be safe by construction and instrumented for next summer.
- **Philosophy.** Split success criteria: fan-assist during PRECOOL is judged on the measured sensor drop; the night hold is judged on comfort inside the band. Implementable in HA Jinja, stays inside the existing blueprint.

## Verdict

**proceed** — with the mechanism of the night hold reframed and the fan-assist demoted to an experiment.

1. **Fan-only night hold: proceed.** Our own 100-night history shows the rooms are FLAT with the AC off (−0.15 °C between 23:00 and 06:00 on pure no-AC nights) and REBOUND +0.3 … +1.4 °C toward the house-mass temperature after an evening AC run; with the pre-chill the warmest room ends 23.3–24.0 °C on September nights, inside the 24.5 band, and the continuous guard covers the nights after hot days when the band is breached within hours. The mechanism is "AC off + coast + guard", not the fans: the upstairs hall is WARMER than the bedrooms when the compressor is off, ENERGY STAR's "ceiling fans cool people, not rooms" is verified, and at 1 % the fans' air speed at bed height is unmeasured. The fans are a comfort/air-movement add-on, kept per-fan optional and measured by day parity.
2. **Fan-assist during PRECOOL: ship as an experiment input, off by default.** No source shows a receiving-room ceiling fan increasing open-doorway exchange; buoyancy already moves hall air through the open doors, and mixing can make a low sensor read flat or briefly higher. Our baselines (the hall reaches 21 °C in 15 minutes, the rooms take 2–3 hours) leave room for an effect, so the A/B by day parity decides. This week's forecast (highs 17–21 °C) gives no PRECOOL nights unless the skip threshold is overridden for the experiment.
3. **Energy: small.** On a mild night the LG's after-midnight hold cost 0.66 kWh (09-08); two AC-motor ceiling fans at their lowest step plausibly draw 0.5–1.1 kWh over the same hours. The saving is real only on warm nights (hold part 2–3 kWh) and is capped by the guard tripping on the hottest ones. The beep-free night, the end of the 21 °C hall draft and Martin's preference carry the feature; a one-off measurement of the fans' true draw belongs in the plan.

Two noted uncertainties that do not block: the fans' air speed and dB(A) at 1 % at the pillow (measure once), and the LG `turn_on` restore behaviour observed once on our unit (re-verified deliberately at deploy).

## Approach summary

Extend `bedroom_precool.yaml` (v1.1.0) with a `night_mode` select (`ac_hold` = today's behaviour, byte-for-byte; `fan_only` = new): during PRECOOL the target becomes `ideal − prechill_offset`; the BEDTIME_LOCK parks the LG on the maintaining setpoint and night fan, switches it OFF, and sets the listed bedroom fans to their night percentage; after bedtime a continuous guard turns the LG back on (one beep, restores the parked state) when the warmest room exceeds `ideal + tolerance`, and the running unit is the latch until wake. Fan writes are edge-triggered only (the AC-start tick, the lock tick, one deferred retry at the deep-night window), skip any fan whose interlock sensor is `on`, never touch direction, and never re-assert per tick. Fan-assist during PRECOOL is a separate input with day-parity A/B. No new helpers.

## Evidence by claim

**C1 — With the AC off the rooms do not cool overnight; they sit at the house-mass temperature and rebound toward it after an evening AC run.**
- Empirical (orchestrator-run, admissible): HA long-term statistics 2026-06-01 → 09-09, 100 nights, classified by LG daily energy. NOAC nights drift −0.15 ± 0.29 °C (23:00 → 06:00), outdoor min 9–13 °C; AMB nights (evening AC, off before midnight) +0.21 ± 0.75, with the September examples 08-20 +0.8, 08-21 +0.6, 08-29 +1.0, 08-31 +1.4, 09-02 +0.7, 09-05 +0.3. Full table in Lens 2 below.
- T1 [A1] EnergyPlus airflow-network reference — "Buoyancy flow only occurs when the air density in the upper zone is greater than the air density in the lower zone" (doorway exchange is ΔT-driven and continuous; fetched, verified).
- `support_status: verified` (own data + 1× T1).

**C2 — The upstairs hall is a warm reservoir when the compressor is off, so night-time doorway mixing cannot cool the rooms.**
- Empirical: LG intake 23.5–25.5 °C with the unit off (09-04 … 09-07) while the bedrooms read 23.0–24.1; intake 20–21.5 while cooling to setpoint 21 with the bedrooms 1.5–2.5 °C higher.
- `support_status: verified` (own data; the only upstairs-hall reading available).

**C3 — Ceiling fans do not lower measured room temperature; they cool occupants, and running them in an unoccupied room is waste.**
- T1 [A2] ENERGY STAR — "Ceiling fans cool people, not rooms." / "If the room is unoccupied, turn off the ceiling fan to save energy." (fetched by the agent AND re-verified by the orchestrator on the page).
- T1 [A3] CBE Berkeley fans guidebook — "a design speed of 0.5 m/s [100 fpm], equal to approximately 2 °C [4 °F] cooling effect" (re-verified on the page). Adult, awake occupants; no pediatric air-speed source exists.
- T1 [B1] Nationwide Children's (bunk-bed guidance) and the vendor direction pages [A5] agree fans act on the occupant. Cluster-independent (DOE, UC Berkeley, a children's hospital).
- `support_status: verified`.

**C4 — There is no evidence that a ceiling fan in the receiving room increases open-doorway exchange; mixing can make a low-mounted sensor read flat or briefly warmer.**
- Lens A found no T1–T3 source for the doorway-throughput claim after a targeted search; PNNL's jump-duct guidance [A4] ("A jump duct is a short piece of insulated flex duct … to provide a return air pathway between the two areas") exists because CLOSED doors block exchange — open doors already have the large-opening pathway of [A1].
- Destratification mechanism (warm ceiling air pulled down to the sensor): stated by Lens A from the general literature; the numeric gradient claim on the Airius vendor pages could not be confirmed → `unverified`.
- `support_status: verified as an absence` — no source supports the fan-assist premise; the A/B decides.

**C5 — `climate.turn_on` on the LG ThinQ integration is a single power-on call and the unit restores its last mode, setpoint and fan.**
- T1 [C1] HA core source `lg_thinq/climate.py` — `async_turn_on` is `await self.async_call_api(self.coordinator.api.async_turn_on(self.property_id))`, no mode/temperature/fan calls (fetched raw, verbatim).
- T1 [C2] HA core issue #131252 — "There is no specific PowerOn command. PowerOn requires to select a mode." (fetched).
- Empirical: recorder 2026-09-08 14:51:02Z — two seconds after the blueprint's `turn_on` the entity reported `cool / 21 / medium` (its last state); the `set_temperature 18` and `set_fan_mode high` rows followed at :08 and :10. Wake-off 09-09 05:15:07Z is a single `off` row.
- `support_status: verified` (2× T1 + own observation). Design consequence: park the unit before switching it off at the lock.

**C6 — Tuya cloud fans lag 10–60 s and can desync from remote/app control; same-tick read-back is unreliable; percentage steps are quantised.**
- T1 [D1] HA core issue #60034 "Tuya; delayed/missing state updates: Confirmed Tuya Cloud issue, awaiting upstream fix" (fetched).
- T3 [C3] community "Tuya devices have a 10 to 40 second delay" — "the delay is between 10 to 60 seconds when I actually time it"; T3 [C4] "State of Tuya ceiling fan is not changed in HA" — "if the light or fan is turned on or off with the remote the state doesn't change in HA" (both fetched); T3 [C5] percentage↔step thread (fetched). Three cluster-independent threads plus the T1 issue.
- `support_status: verified`. Design consequence: one command per transition, `percentage` always passed explicitly, no same-tick verification, guards on `unavailable`.

**C7 — Automation-scoped state and `for:` waits do not survive an HA restart; helpers do; `context.parent_id` is not usable for a `time_pattern` automation.**
- T1 [D2] HA trigger docs — "Use of the `for` option will not survive Home Assistant restart or the reload of automations." (re-verified on the page).
- T1 [D3] `input_boolean` docs — restores its prior state after a restart (fetched).
- T2 [D4] data.home-assistant.io context docs — "there is no native way to retrieve the original cause of a context in automations or templates"; T3 [D5] community context guide — Time Pattern triggers do NOT provide `parent_id`; T3 [D6] "context.parent_id not reliably set" thread (all fetched).
- `support_status: verified`. Design consequence: the latch stays the running AC (live state re-derived every tick, restart-safe by construction), no context-based ownership, no `for:`.

**C8 — The LG cloud integration can report `unavailable` transiently and can misreport state right after a restart.**
- T1 [D7] HA core issue #144277 (transient unavailable, integration reload fixes) and T1 [D8] issue #146575 (`eco` preset shows `off` after restart) — both fetched.
- `support_status: verified`. Design consequence: STEP 5 already stops the tick on `unavailable`; a stale `off` on a running unit costs at most one no-op `turn_on` beep; a 0.2 °C hysteresis on the guard limits flapping.

**C9 — Noise: the WHO bedroom guideline is 30 dB LAeq; a ceiling fan at its lowest step is probably below it, but AC-motor hum at 1 % is unmeasured.**
- T1 [B2] WHO Guidelines for Community Noise — "recommended guideline values inside bedrooms are 30 dB LAeq for steady-state continuous noise and for a noise event 45 dB LAmax" (re-verified on the page).
- T1 [B3] Hugh et al. 2014 (Pediatrics, via ENTtoday summary) — infant sound machines exceeded 50 dBA at 30 cm; 50 dBA is the nursery limit.
- T3 [B4] fan-industry blogs claim DC fans under 35 dB at low — single cluster, `unverified`.
- `support_status: verified for the thresholds, unverified for our fans` → one-off dB(A) reading at the pillow in the plan.

**C10 — Child sleep: pediatric guidance is 16–20 °C for INFANTS; the fan-and-SIDS finding is single-study and not an AAP recommendation; never aim a fan at a child; ceiling-fan clearance over a raised bed is a standing hazard independent of schedule.**
- T1 [B5] Coleman-Phox et al. 2008 (Kaiser summary) — "Fan use during sleep was associated with a 72% reduction in SIDS risk (AOR 0.28; 95% CI 0.10–0.77)"; T1 [B6] AAP 2022 — "insufficient evidence to recommend the use of a fan as a SIDS risk-reduction strategy" (quote via index, page 403); T2 [B7] Lullaby Trust 16–20 °C and "don't aim it directly towards the baby" (via index); T1 [B8] NCJ JGZ-richtlijn (fetched); T1 [B1] Nationwide Children's bunk-bed page — "Keep the top bunk away from ceiling fans" (fetched).
- `support_status: verified` for the constraints; the SIDS benefit is `unverified/contested` and the design does not rely on it. Martin's 23 °C ideal is his decision, above the infant guidance; the kids are past infancy.

**C11 — Energy: the LG's overnight hold is 0.6–1 kWh on mild nights and 2–3 kWh on warm ones; AC-motor ceiling fans draw tens of watts even on low; fan-staged setpoint relaxation saves ~21–36 % of compressor energy in field studies, but no study tests compressor-OFF nights with a rescue threshold.**
- Empirical: LG day counters — 0.66 kWh for 00:00–07:15 on 09-08 (mild), 3.29 kWh for the 09-07 evening (drive + hold), 6–11 kWh/day in the June/August heat; August total 91.5 kWh.
- T1 [C6] DOE/PNNL BASC — "draw 9 watts or less at medium speed as opposed to 30 to 40 watts for a standard ceiling fan motor"; "the thermostat can be raised as much as 4°F with no noticeable reduction in comfort if a ceiling fan … is present" (fetched).
- T1 [C7] CBE fans guidebook (Energy & Buildings 2021 mirror) — "36% of compressors energy savings when compared with air-conditioning only conditions" from 100 automated fans; fans "only 2% of the total compressors consumption" (fetched; the ScienceDirect abstract 403'd → the 21 % median is `unverified`).
- T1 [C8] LG DC12RH spec — rated input 933 W, fan motor output 30 W (fetched).
- `support_status: verified` for the numbers; the extrapolation to compressor-off nights is `unverified` and is exactly what Experiment 2 measures.

**C12 — Prior art: no HA blueprint coordinates a fan with a climate entity by phase; the community pattern is edge-triggered action plus a lock, and independent-threshold blueprints assume exclusive ownership.**
- T3 [D9] "Temperature Control Fan + Ceiling Fan Mode" blueprint thread (bypass-toggle bug); T3 [D10] "Advanced Ventilation/AC Management" blueprint (assumes exclusive ownership; case-mismatch on fan modes); T3 [D11] manual-override lock pattern thread; T2 [D12] Frenck on `mode: restart` — "restart mode checks conditions before it actually restarts" (all fetched). Three cluster-independent T3 + 1 T2.
- `support_status: verified at community tier`.

## Lens 2 — our own history (HA long-term statistics 2026-06-01 → 2026-09-09, 100 nights)

Source: `recorder/statistics_during_period` hourly means for `sensor.temperature_sensor_2` (master), `sensor.temperature_sensor_3` (kids), `sensor.openweathermap_temperature`; daily LG energy from `sensor.bedrooms_energy_yesterday` / `sensor.bedroom_bedrooms_energy_today` (Wh, LG ThinQ day counter, local midnight). `climate.bedrooms` intake temperature from the 10-day recorder. Fan state exists only in the 10-day recorder: the master fan (`fan.ceiling_fan_light_v2_2`) has been ON at 1 % for the entire window; the kids fan toggled at 1 % / 21 % by the dimmer and the safety cutoff. **So no night in the data set is a "fans off" night for the master room, and none is a controlled fan A/B** — the history answers the AC-off drift question, not the fan question. `sensor.hall_temperature` is a Hue motion sensor in the downstairs front-door hall (16–21 °C all summer) and is NOT the AC hall; the only upstairs-hall reading is the LG's own intake sensor.

**Night classes** (night = D 20:00 → D+1 06:00 local; "warmest" = max of the two rooms; energy(D) covers the evening pre-cool, energy(D+1) the after-midnight hold):

| class | rule | n | warmest 23:00 | warmest 06:00 | drift 23→06 (mean ± sd, range) | wake > 24.5 | outdoor min |
|---|---|---|---|---|---|---|---|
| NOAC | both days ≤ 500 Wh (LG idle ≈ 250–420 Wh/day) | 9 | 23.5 | 23.4 | −0.15 ± 0.29 (−0.6 … +0.5) | 1/9 (06-30, 25.4 after a 31 °C day) | 11.4 |
| AC night | energy(D+1) ≥ 600 and energy(D) ≥ 1500 | 56 | 24.0 | 23.8 | −0.22 ± 0.55 (−1.3 … +1.8) | 10/56 (heat waves, hall at 21 could not hold 23) | 16.6 |
| AMB | evening AC then off before midnight, or light use | 35 | 23.9 | 24.1 | +0.21 ± 0.75 (−2.3 … +1.5) | 14/35 | 15.4 |

**Finding L2-1 — with the AC off, the rooms are flat, not cooling.** On pure no-AC nights the warmest room moved −0.15 °C between 23:00 and 06:00 with outdoor minima of 9–13 °C. Closed windows: the 10 °C outdoor air never reaches the sensors. The rooms sit at the house-mass temperature (≈22–23 in June, ≈23.5–24.5 in late August).

**Finding L2-2 — after an evening AC run the rooms REBOUND upward to the mass temperature.** The AMB nights where the AC ran in the evening and was off before midnight are the closest analogue of the proposed fan-only hold: 08-20 23.6→24.4 (+0.8), 08-21 23.5→24.1 (+0.6), 08-29 23.5→24.5 (+1.0), 08-31 22.6→24.0 (+1.4), 09-02 23.8→24.4 (+0.7), 09-05 22.9→23.2 (+0.3, manual cool to 22 until 23:00, outdoor 11–13). Regression on the NOAC nights: drift(23→06) ≈ +1.54 − 0.072·T23, i.e. the overnight change is toward ≈21.4 °C only when the whole house is cool; in practice the room converges on the mass temperature within ~4–6 h. **Implication for the +1.5 band (24.5):** starting from a pre-chilled 22.5 the rooms end 23.3–24.0 in September conditions (inside the band); starting from 23.0 without pre-chill they end 23.5–24.5 (band edge). After a run of hot days (mass ≥ 24.5, e.g. 07-18…07-24, 06-28…07-03) the band is breached within 1–3 h and the guard trips — the fan-only night is not available on those nights whatever the fans do.

**Finding L2-3 — the upstairs hall is a WARM reservoir when the AC is off.** LG intake readings with the unit off: 23.5–25.5 °C on 09-04…09-07 while the bedrooms read 23.0–24.1 — the stairwell top is warmer than the bedrooms. With the unit cooling to setpoint 21 the intake reads 20–21.5 while the bedrooms sit 1.5–2.5 °C higher. So "pull cold hall air in with the fan" is only physically available while the AC runs; during a fan-only hold the open door is a slight heat source, and any doorway mixing the fans add works against the rooms. The night-hold fans therefore contribute skin-cooling and in-room mixing only — their expected effect on the sensor reading is ≈ 0 or slightly positive.

**Finding L2-4 — drive-rate baselines (what fan-assist must beat).** 09-07 (drive 18 °C / fan high from 16:51, outdoor 25.7→22.3): kids 25.4 (16:00) → 24.4 (18:00) → 23.5 (19:00) ≈ −0.9 °C/h; master 24.6 → 23.2. 09-08 (cool day, outdoor 17): kids 23.5 → 22.5 in 3 h ≈ −0.35 °C/h. 09-03 manual (setpoint 22, medium): kids 24.6 → 24.0 in 3 h ≈ −0.2 °C/h. The hall itself reaches 19.5–21 within the first hour; the bedrooms lag by 1.5–2.5 °C for the whole hold. That standing gap is the quantity a receiving-room fan could shrink; a doubling of the doorway exchange would show up as a visibly steeper first two hours of DRIVE, which the A/B protocol measures.

**Finding L2-5 — energy scale of the night hold.** 09-07/08 (pre-cool + full-night hold, outdoor 18→12): 3.29 kWh on 09-07 (16:51–24:00, mostly DRIVE) + 0.66 kWh on 09-08 (00:00–07:15 hold) ≈ 3.95 kWh ≈ €1.00. The after-midnight hold part on mild nights ≈ 0.6–1.0 kWh (€0.15–0.25); on heat-wave nights the unit ran 6–11 kWh/day. A fan-only night removes the hold part only; the DRIVE part stays (and grows by the pre-chill, ≈ 0.3–0.5 kWh). Order of magnitude for a season: ~40–60 cooling nights × 1–2 kWh ≈ 40–120 kWh ≈ €10–30. Modest; the beep-free night and the end of the 21 °C hall draft (Martin's "too cold" complaint) are the larger wins.

**Finding L2-6 — the season is over for measurement.** Forecast 09-09…09-14: highs 17–21 °C, lows 11–15 °C. With `skip_threshold` 21 the AC will not start on most of these evenings, so there is no PRECOOL to A/B this week and no warm night to stress the fan-only hold. Any measurement this year needs a deliberate experiment override (a lower skip threshold for the A/B nights) and the comfort-side validation will be trivially green in September.

## Lens 5 — control design inside the stateless pre-cool blueprint (orchestrator analysis of `bedroom_precool.yaml` v1.0.3)

**Constraints inherited from the blueprint:** stateless 1-minute `time_pattern` tick, `mode: restart`, phase derived from the clock, the running AC is the only persisted "PRECOOL started" bit, idempotent `climate` calls only (every call is a beep), one `input_number` helper. Constraints from the kids room: `fan.ceiling_fan_light_v2` is also written by the dimmer blueprint (hold = 21 % / 1 % toggles that read the live percentage), the safety cutoff (`binary_sensor.samuel_samuel_matthew_fanprotection` on → `fan.turn_off`, `wait_for_trigger` 3 min clear, ANY fan→on during the hold cancels the resume silently) and the seasonal direction flipper. Martin also turns the kids fan off by hand after bedtime (09-08 19:49). Verified live 2026-09-09: the cutoff fired several times a day in the last 10 days.

**Edge-triggered writes are the only safe pattern for the fans.** A level-triggered "ensure fan on" every minute would (i) cancel the safety cutoff's hold within 60 s of a cut — an adult standing under the fan gets the fan back on — and (ii) override Martin's manual off. The blueprint already has natural edges: (1) the PRECOOL tick that turns the AC on (`phase == PRECOOL and not ac_is_running`) is the only tick that starts the AC — fan-assist starts on that same tick and never again; (2) the BEDTIME_LOCK window is one tick (bedtime − 1 min); (3) the DEEP_NIGHT_CHECK window is 10 ticks but already carries an idempotency guard; (4) DAY_OFF's `ac_is_running` turn-off tick. No helper is needed for the fans: the fan commands ride the AC's own transitions.

**Interlock for the kids fan.** Before any fan command the blueprint checks a per-fan optional "interlock" binary_sensor list (the height-gated PIR); if any is `on` the fan is skipped this transition (notice, no retry loop). This makes the blueprint's fan-on impossible while an adult is under the fan. The BEDTIME_LOCK tick at 19:29 is exactly the bedtime routine, so the PIR will often be `on` → the kids fan is not set at the lock; the DEEP_NIGHT_CHECK window (01:00, room clear) is the single deferred retry: if the night mode wants very-low and the fan is off and the interlock is clear → one `fan.turn_on percentage: 1`. That is a second edge, not a loop. Martin's manual off after the lock is respected until 01:00 (documented; if he wants "off means off all night" the retry becomes an input).

**Night guard latch without a helper.** After bedtime the AC is off by design; the guard is `phase in (NIGHT_HOLD, DEEP_NIGHT_CHECK, DEEP_HOLD) and not ac_is_running and warmest_bedroom > ideal_temp + tolerance` → `climate.turn_on` (one beep; LG ThinQ restores the last mode/setpoint/fan — Lens C verifies). Once the unit runs, `ac_is_running` is true on every later tick, so the guard cannot fire twice, the existing DEEP_NIGHT_CHECK nudge applies as today, and DAY_OFF turns it off at wake. HA restart: the tick recomputes from live state — off + over band → fires (correct), on → holds (correct). ThinQ transient `unavailable`: STEP 5 already stops the tick, so a flapping cloud read cannot fire the guard. One failure mode to design out: the unit reports `off` for one tick while actually running (cloud lag) → the guard re-fires = a stray beep and possibly a mode reset; mitigation = the same `for`-style debounce the blueprint uses elsewhere (require two consecutive ticks over band, which the stateless loop cannot count) — the cheaper answer is a 0.2 °C hysteresis on the guard plus the fact that LG's `turn_on` on a running unit is a no-op beep at worst.

**Pre-chill.** `bedtime_target = ideal_temp − prechill_offset` (new input, default 0.5, only when night mode = fan-only). DRIVE/HOLD compare against `bedtime_target`; the auto-learn `bedtime_error` uses `bedtime_target` too, otherwise the bias converges on arriving at `ideal`, not below it. The guard keeps `ideal_temp + tolerance`. `maintaining_setpoint` is unchanged (it is what the guard's `turn_on` restores).

**Empirical check on our own unit (recorder, 2026-09-08 14:51Z):** the PRECOOL start tick issued `climate.turn_on`; two seconds later the entity reported `cool / setpoint 21 / fan medium` — the state it had when it was last switched off — and only then did the blueprint's `set_temperature 18` (14:51:08) and `set_fan_mode high` (14:51:10) land. So `turn_on` restores mode + setpoint + fan in ONE command (one beep). The wake-off on 09-09 05:15:07Z was likewise a single `off` row. Consequence for the fan-only lock: the unit must be PARKED on the maintaining setpoint and the night fan BEFORE it is switched off, otherwise a night-guard `turn_on` restores the DRIVE state (18 °C, fan high) at 02:00.

**Lock semantics change.** With night mode = fan-only the BEDTIME_LOCK first parks the unit (set_temperature maintaining / set_fan night_fan, each only if different — usually 0–1 calls because the pre-chill HOLD already sits there), then issues `climate.turn_off`, and sets the fans to very-low (1 %). Beep budget after bedtime: lock ≤ 3 (typically 1–2, same as v1.0.3) + guard ≤ 1 + deep-check ≤ 1 (only on guard nights). With night mode = AC (today's behaviour) nothing changes. A `night_mode` select (`ac_hold` | `fan_only`) keeps the v1.0.3 path intact and lets the A/B alternate by day parity (`fan_only_days: all | odd | even`).

**Fan list, not two entities.** Input `bedroom_fans` (multiple: true, domain fan) + `fan_interlocks` (multiple binary_sensor, optional) + `precool_fan_percentage` (default 21) + `night_fan_percentage` (default 1). A third fan later is a config edit. Direction is never touched (seasonal blueprint owns it). Every fan call is guarded on `states(fan) not in ['unavailable','unknown']` (Tuya cloud) and on the current percentage/state to keep calls idempotent inside a transition window.

**What the blueprint will NOT do:** no per-tick fan re-assertion, no fan-off at wake (Martin runs the master fan permanently; `fans_at_wake: leave | off` input, default leave), no direction changes, no fan speed above the PRECOOL percentage, no new helpers.

**Test surface:** the existing rendered phase-chain harness (`tests/`, `_render_chain`) extends naturally — new RED cases: guard fires exactly once across a night of ticks; lock issues exactly one climate call in fan-only mode; interlock `on` suppresses the fan call and the 01:00 retry issues at most one; pre-chill shifts DRIVE→HOLD and the learner's error; `night_mode: ac_hold` is byte-for-byte the v1.0.3 command sequence (regression pin).

## Community consensus signals

- **Fans lower the temperature a sensor reads — NEGATIVE.** DOE/ENERGY STAR, CBE and the vendor guidance all frame fans as occupant cooling; nobody claims a receiving-room ceiling fan pulls a conditioned hall into a bedroom.
- **Fans let you hold a warmer setpoint — STRONG** (adults, awake or asleep with air speed ≥ 0.3–0.5 m/s); **UNKNOWN at a 1 % AC-motor step** (air speed unmeasured).
- **Compressor-off nights at 15–20 °C outdoor with a rescue threshold — MIXED/none.** No study; our own history is the only evidence and it supports it in September.
- **Fan use for toddlers at night — STRONG on "fine if not aimed at the child", NEGATIVE on "it is a safety feature"** (AAP: insufficient evidence).
- **HA deconfliction — STRONG on edge-triggering + explicit ownership, NEGATIVE on `context` sniffing.**
- **Tuya cloud fans in automations — MIXED/NEGATIVE:** lag and desync are expected; local control is the community's fix (out of scope).

## Anti-patterns flagged

1. **Level-triggered "ensure fan on" every tick** — cancels the kids-room safety cutoff (its hold ends on any fan→on) and overrides manual control; the community's override-lock threads [D11] exist because of exactly this. Edge-trigger only.
2. **Switching the LG off from the DRIVE state** — a later `turn_on` restores 18 °C / fan high at 02:00 (C5). Park first.
3. **Reading fan state back in the same tick as the command** (C6) — Tuya cloud lag makes the idempotency guard lie; one command per transition, never a loop.
4. **Using `context.parent_id` to tell automation writes from manual ones** with a `time_pattern` trigger (C7) — not populated.
5. **Fan direction changes from the climate blueprint** — the seasonal flipper owns direction and stops/coasts the fan; a second writer would race it.
6. **`fan.turn_on` without `percentage`** — restore behaviour is undocumented in HA (Lens D checked the docs) and integration-specific; always pass the percentage.
7. **Leaning on the 2008 SIDS finding** to justify overnight fans — single study, not replicated to guideline strength (C10).

## Critique findings (Phase 4)

**What would have to be true for the verdict to be wrong?**
- For the night hold: that the rooms drift MORE with the fans on very-low than the 35 AMB nights suggest (e.g. the fans mix warm hall air in through the open doors, L2-3) — bounded by the continuous guard, so the failure mode is "more guard nights and a beep at 02:00", not an overheated child. Or that the LG does not restore its parked state on `turn_on` in some mode (we observed one restore; the deploy live-verify repeats it once deliberately).
- For fan-assist: that the doorway exchange is not the bottleneck at all (the hall cools in 15 min, the bedrooms take 2–3 h, L2-4). If the bottleneck is the rooms' own thermal mass, no fan changes the drive rate and the A/B reads null — which is why fan-assist ships as an experiment input, not a feature.
- For the guard band: that 24.5 °C with a toddler under a duvet is uncomfortable rather than merely warm. Pediatric guidance sits at 16–20 °C for infants (Lens B); Martin's chosen 23 °C ideal is already above it and the band tops at 24.5 — the design cannot close that gap, bedding does. Martin decided the band.

**Which sources are weighted too heavily?** The two CBE Berkeley pages (0.5 m/s ≈ 2 °C) are the whole quantitative basis for "fans make 24.5 feel like 22.5" and they describe adults awake; there is no pediatric air-speed comfort source. And the design does not actually lean on that number: at 1 % the air speed at bed height is unmeasured and probably far below 0.5 m/s, so the honest expected comfort effect of the night fans is small. The own-history findings (L2-1…L2-5) carry the verdict, and they are orchestrator-run empirical checks on the actual house, which outranks any external source for this decision.

**Incentive-aligned sources.** Hunter Fan (direction guidance), Airius (destratification vendor), fan-retail acoustics blogs, and the Big Ass Fans / CBE fan guidebook lineage (industry-funded research) all sell fans. None of their claims gate the verdict; ENERGY STAR / DOE's "cool people, not rooms" cuts against the vendors and is the one that shapes the design.

**Strongest contrarian position.** "Skip the fans entirely: the evidence says the night hold works because the AC is off and the house mass is ≈ 23.5 °C in September, not because of the fans; the fans add motor heat and a possible doorway short-circuit with a warmer hall, and DOE says fans in rooms with sleeping occupants who cannot feel a 1 % breeze are waste. Ship 'AC off at the lock + continuous guard + pre-chill' alone." This is a credible reading; the design answers it by making the fans a separate, measured, per-fan option (night percentage input, A/B by day parity) rather than the mechanism, and by keeping the master fan's permanent very-low (Martin's habit) untouched.

## A/B measurement protocol (proposed for the observe phase and next summer)

Instrumentation is free: HA already records the room sensors, the LG intake and energy, and the fans' state; the blueprint adds a per-tick debug line only on transitions (notification or `logbook` entry: phase, warmest, target, guard state, fan commands issued).

**Experiment 1 — fan-assist during PRECOOL (feature a).** Alternate by calendar-day parity (`fan_assist_days: all | odd | even | off`): odd days fans at `precool_fan_percentage` (21 %) from the AC-start tick, even days fans untouched. Metrics per night, from history: (i) minutes from AC start to warmest ≤ bedtime target; (ii) mean °C/h over the first 90 min of DRIVE normalised by (LG intake − warmest) gap; (iii) the auto-learn bias trajectory (a real effect shows as the bias falling on fan nights). Decision rule after ≥ 5 nights per arm with `cooling_needed` true: fan arm ≥ 20 % faster on (i) AND steeper on (ii) → keep on by default; otherwise leave the input off. This season: needs a deliberate `skip_threshold` override (18 °C) for the A/B nights because forecast highs are 17–21 °C; otherwise the experiment waits for the first warm spell of 2027.

**Experiment 2 — fan-only night hold (feature b).** Run `night_mode: fan_only` every night (the guard makes it safe); log per night: warmest at lock, at 01:00, at 06:00, guard trip time (if any), outdoor min, LG kWh. Compare against the 35 AMB rebound nights and the 09-07/08 AC-hold night. Success = warmest ≤ 24.5 at 06:00 on ≥ 80 % of nights whose previous-day max ≤ 26 °C, zero guard trips before 23:00, kWh(00:00–07:15) ≈ idle on non-trip nights. The fans' own contribution is tested by parity on the master room only (`night_fan_days: odd | even`), the kids fan stays on the fixed schedule Martin chose. With September's mild nights this experiment validates SAFETY and the guard mechanics now; the comfort/drift discrimination comes with warm nights.

**Stop rules.** Any night with a bedroom reading below 16 °C (existing overcooling fault) or a guard that fires more than once (latch broken) → `night_mode` back to `ac_hold` the next morning; the halt is a one-input change.

## Contested claims

- **Cooling-energy saving per degree of setpoint raise:** DOE/PNNL says 10–15 % per °F [C6]; county energy programmes cite ~3 % per °F [C9]. Minor: neither number gates the design (the design switches the compressor off rather than raising a setpoint). Noted so the plan does not quote a "%/°" figure.
- **SIDS risk reduction from fans:** 72 % in Coleman-Phox 2008 vs the AAP's "insufficient evidence" (2022). Minor for this design: the fans are not a safety feature and the kids are not infants.
- **Ceiling-fan low-speed draw:** DOE's 30–40 W (standard motor, medium) vs aggregator "3.6 W average at low" (T4) vs DC-motor 2–9 W. Material to the energy claim only → measured once via the house meter delta in the plan; the verdict already assumes the pessimistic number.

## Unverified claims (not gating)

- Numeric floor-to-ceiling stratification gradient in a bedroom (Airius vendor pages) — could not be confirmed.
- Air speed at bed height from a Tuya AC-motor fan at 1 % — no source; measure.
- °C/h post-AC drift from the literature — no sourced figure; our own data replaces it.
- A humidity cutoff on the ASHRAE 55 elevated-air-speed benefit — dropped.
- The Tuya product `9ecs16c53uqskxw6` wattage/specs — nothing found.
- The 21 % median compressor saving (ScienceDirect abstract 403) — only the 36 % figure on the CBE mirror is verified.
- LG beep mute — LG community thread DNS-failed; no ThinQ entity exposes a beep switch on this unit (the `ac_sound_switch` input remains optional).
- AAP 2022 and Lullaby Trust quotes — confirmed via search index only (pages 403).

## Bibliography

**T1 — primary / authoritative**
- [A1] https://bigladdersoftware.com/epx/docs/9-0/engineering-reference/airflownetwork-model.html — EnergyPlus airflow-network reference (fetched, verified)
- [A2] https://www.energystar.gov/products/ceiling_fans/installation-and-usage-tips — ENERGY STAR (fetched; re-verified by orchestrator)
- [A3] https://cbe-berkeley.gitbook.io/fans-guidebook/full-guidebook/elevated-air-speed-and-thermal-comfort — CBE Berkeley (fetched; re-verified by orchestrator)
- [A4] https://basc.pnnl.gov/resource-guides/jump-ducts — PNNL/DOE BASC (fetched)
- [B1] https://www.nationwidechildrens.org/research/areas-of-research/center-for-injury-research-and-policy/injury-topics/home-safety/bunk-bed-safety — Nationwide Children's (fetched)
- [B2] https://www.nonoise.org/library/whonoise/whonoise.htm — WHO Guidelines for Community Noise 1999 (fetched; re-verified by orchestrator)
- [B3] https://publications.aap.org/pediatrics/article/133/4/677/32749/Infant-Sleep-Machines-and-Hazardous-Sound-Pressure — Hugh et al. 2014 (403; corroborated via https://www.enttoday.org/article/sleep-machines-may-damage-infant-hearing/ fetched)
- [B5] https://divisionofresearch.kaiserpermanente.org/publications/use-of-a-fan-during-sleep-and-the-risk-of-sudden-infant-death-syndrome/ — Coleman-Phox 2008 summary (fetched)
- [B6] https://publications.aap.org/pediatrics/article/150/1/e2022057990/188304/Sleep-Related-Infant-Deaths-Updated-2022 — AAP 2022 (403; quote via index)
- [B8] https://www.jgzrichtlijnen.nl/richtlijn/jgz-richtlijn-preventie-wiegendood/3-preventie-van-wiegendood/ — NCJ JGZ-richtlijn (fetched)
- [B9] https://www.nationwidechildrens.org/family-resources-education/700childrens/2025/07/colorful-noise-and-sleep — white noise (fetched)
- [C1] https://raw.githubusercontent.com/home-assistant/core/dev/homeassistant/components/lg_thinq/climate.py — HA core lg_thinq climate (fetched)
- [C2] https://github.com/home-assistant/core/issues/131252 — LG PowerOn requires a mode (fetched)
- [C6] https://basc.pnnl.gov/resource-guides/ceiling-fans-energy-star — DOE/PNNL BASC ceiling fans (fetched)
- [C7] https://cbe-berkeley.gitbook.io/fans-guidebook/full-guidebook/conventional-hvac-vs.-ceiling-fans-integrated-hvac — CBE field study mirror (fetched); abstract https://www.sciencedirect.com/science/article/pii/S0378778821006034 (403)
- [C8] https://www.lg.com/uk/business/hvac/residential-solutions/residential-air-conditioner/wall-mounted/dc12rh/ — LG DC12RH spec (fetched)
- [D1] https://github.com/home-assistant/core/issues/60034 — Tuya delayed state updates (fetched)
- [D2] https://www.home-assistant.io/docs/automation/trigger/ — HA triggers (fetched; re-verified by orchestrator)
- [D3] https://www.home-assistant.io/integrations/input_boolean/ — restore on restart (fetched)
- [D7] https://github.com/home-assistant/core/issues/144277 — ThinQ transient unavailable (fetched)
- [D8] https://github.com/home-assistant/core/issues/146575 — ThinQ eco shows off after restart (fetched)
- https://www.home-assistant.io/integrations/lg_thinq/ · https://www.home-assistant.io/actions/fan.turn_on/ · https://www.home-assistant.io/integrations/fan/ · https://developers.home-assistant.io/docs/core/entity/fan/ — checked for restore/percentage_step text; absent (fetched)

**T2 — established expert / credible org**
- [A5] https://www.hunterfan.com/blogs/hunter-blog/ceiling-fan-direction-for-summer-and-winter — Hunter Fan direction guidance (fetched; vendor)
- [A6] https://www.simscale.com/blog/what-is-ashrae-55-thermal-comfort/ — ASHRAE 55 summary (fetched)
- [B7] https://www.lullabytrust.org.uk/baby-safety/safer-sleep-information/room-temperature/ — Lullaby Trust (403; via index)
- [B10] https://www.contemporarypediatrics.com/view/journal-club-using-fan-reduces-sids-risk — journal club on the 2008 study (403; via index)
- [B11] https://www.snopes.com/fact-check/fan-death/ — fan-death myth (via index)
- [D4] https://data.home-assistant.io/docs/context/ — HA context model (fetched)
- [D12] https://frenck.dev/automation-modes-in-home-assistant-why-the-default-isnt-your-friend/ — Frenck on automation modes (fetched)

**T3 — community**
- [C3] https://community.home-assistant.io/t/tuya-devices-have-a-10-to-40-second-delay/178320 (fetched)
- [C4] https://community.home-assistant.io/t/state-of-tuya-ceiling-fan-is-not-changed-in-ha/497015 (fetched)
- [C5] https://community.home-assistant.io/t/ceiling-fan-percentage-to-speed-number/671498 (fetched)
- [C9] https://www.fairfaxcounty.gov/environment-energy-coordination/news-and-events/take-two-degree-challenge-save-energy-and-money-season (via index)
- [C10] https://deepwiki.com/rospogrigio/localtuya/4.2-fan-entity — LocalTuya fan mapping (fetched)
- [C11] https://www.smarthomeexplorer.com/guides/dc-vs-ac-ceiling-fan-motors-guide (fetched; retail)
- [C12] https://community.home-assistant.io/t/tuya-lights-switches-delay-in-updating-states-is-it-only-me/357889 (via index)
- [D5] https://community.home-assistant.io/t/how-to-use-context/723136 (fetched)
- [D6] https://community.home-assistant.io/t/context-parent-id-not-reliably-set/664739 (fetched)
- [D9] https://community.home-assistant.io/t/temperature-control-fan-ceiling-fan-mode/515861 (fetched)
- [D10] https://community.home-assistant.io/t/advanced-ventilation-ac-management-blueprint/902962 (fetched)
- [D11] https://community.home-assistant.io/t/smart-auto-manual-override-strategy-for-automations-with-self-healing-timer/1011118 (fetched)
- [B12] https://www.healthline.com/health/sleeping-with-fan-on — dryness/dust (fetched)
- [A7] https://en.wikipedia.org/wiki/ASHRAE_55 (fetched; tertiary)
- [A8] https://forums.anandtech.com/threads/how-to-move-cold-air-to-a-hot-room.2440357/ — doorway box fans (via index)
- [A9] https://airiusfans.com/faq/ — destratification vendor (fetched; numeric claims not confirmed)

**T4 — unverified**
- https://ecocostsavings.com/ceiling-fan-power/ · https://robots.net/tech/how-much-energy-does-a-smart-plug-use/ · https://truetips.blog/ac-fan-mode-electricity-savings (inapplicable, central-air blower) · https://lgcommunity.us.com/discussion/13486/how-to-get-rid-off-the-on-off-beep-of-air-conditioners (DNS failed) · https://www.energystar.gov/productfinder/product/certified-ceiling-fans/details/2357729 (JS-rendered, via index)

## Methodology

Mode: **Standard-plus** — four Sonnet research agents dispatched in parallel (Lens A physics + contradicting evidence, Lens B child sleep/noise, Lens C energy + device behaviour, Lens D HA control-design prior art), each with the full brainstorm context and the T1–T4 tier instruction; ~4–8 minutes each, no timeouts. Lens 2 (own history) and Lens 5 (control design) were run by the orchestrator against HA long-term statistics, the 10-day recorder and the blueprint source. Cross-validation rule: 1× T1 or 2× T2 cluster-independent or 3× T3 cluster-independent; orchestrator-run empirical checks on the actual house outrank external sources. Verdict-carrying quotes (ENERGY STAR, CBE Berkeley, HA trigger docs, WHO) were re-fetched and confirmed on the page by the orchestrator. Firecrawl reported "Insufficient credits" for the whole session; agents fell back to WebFetch, and several primary pages (AAP, Lullaby Trust, ScienceDirect) returned 403 — those quotes are marked "via index" and none of them gates the verdict. 45 sources total (24 T1, 7 T2, 14 T3/T4).
