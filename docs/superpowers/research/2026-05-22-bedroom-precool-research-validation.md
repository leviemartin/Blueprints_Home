# Bedroom Sleep Pre-Cool — Research Validation

**Date:** 2026-05-22
**Validates:** `docs/superpowers/specs/2026-05-22-bedroom-precool-design.md`
**Mode:** Deep (4 parallel agents + adversarial lens; firecrawl verification)

---

## 1. Scope answers

Refinement Q&A **skipped** — mid-flow Stack A invocation. Use case, constraints, tolerance,
and philosophy were taken directly from the approved design spec: a Home Assistant
blueprint that predictively pre-cools bedrooms via a single hall LG AC (indirect cooling
through open doors), reaches ~19 °C by ~19:30 bedtime, then holds quietly overnight within
a strict beep budget; transparent/tunable/debuggable logic, mainstream HA patterns.

## 2. Verdict

### PROCEED — with required adjustments

The core architecture is **validated**. A custom blueprint is genuinely the right vehicle:
no off-the-shelf HA integration does predictive pre-cool-to-a-deadline. The beep-budget
premise is real — no software path silences LG's per-command confirmation beep. The
linear lead-time formula + closed-loop precool structure is a mainstream HA community
pattern, and the design's safety margin + per-minute recompute neutralise its main
weakness. **No fatal flaw was found.**

But the research surfaced one serious physical risk — **indirect cooling through a doorway
is thermally weak, so `hall_offset` is likely under-spec** — and a set of required
parameter/scope adjustments (forecast source, dry-mode reliability, coefficient defaults,
a child-safety floor, LG service-call sequencing). Two of these warrant an **operator
decision** before the plan is written (see §2b). None forces a pivot or reframe — the
closed-loop design and the existing heatwave-degradation path already absorb the
indirect-cooling uncertainty.

### 2a. Required plan adjustments (no decision needed — absorb into writing-plans)

| # | Adjustment | Why |
|---|---|---|
| A | **Forecast source must be Met.no or Open-Meteo, not Buienradar.** Buienradar has no hourly forecast (T1-verified). Buienradar may still serve *current* outdoor temp + an Irradiance (W/m²) sensor. | §4 Claim 8 |
| B | **Revise coefficient defaults** — `k_outdoor` must be far smaller than `k_indoor` (outdoor is a secondary heat-leak correction, not a co-equal term). Lower `base`, lower `lead_cap`. Frame all coefficients as calibration inputs. | §4 Claim 1, 3 |
| C | **`drive_setpoint` → the AC's runtime `min_temp`**, not a fixed 16 °C; widen the `hall_offset` range (2 °C default is likely low — plausibly 3–6 °C). Document that on the hottest days indirect cooling may not reach 19 °C — graceful degradation already covers this. | §4 Claim 10 |
| D | **Child-safety floor** — clamp `ideal_temp ≥ 16 °C`; treat a sub-16 °C bedroom reading as a fault; README must warn against aiming airflow at a child's bed and note cool-mode dry-air. | §4 Claim 11 |
| E | **LG service-call discipline** — two sequenced calls (mode → temperature), set mode pre-bedtime while the unit is running, handle the "command not supported in POWER OFF" limitation, guard setpoint reads against `null`, require HA core ≥ 2025.7. | §4 Claim 6 |
| F | **Turn-on is a one-way latch** — never reuse `lead` to also turn the AC *off*; debounce sensor jitter. | §4 Claim 1 |

### 2b. Operator decisions (carried to writing-plans)

1. **`dry` mode** — research rates it unreliable for precise temperature targeting
   (model-dependent, fan locked Low, integration history of `null` setpoints in non-`cool`
   modes). The spec includes humidity/dry-mode in V1. Recommended: keep `dry` as an
   opt-in input, **default OFF**, with `cool` as the proven V1 path.
2. **Auto-learned correction** — the strongest adversarial finding: the canonical HA
   predictive-heating integration (`predheat`) was archived, and the maturing best
   practice self-corrects from observed error. The spec defers auto-learn to V2.
   Recommended: keep it V2, but make V1's calibration loop excellent (debug notification
   surfaces predicted-vs-actual) so manual tuning is easy.

These two are surfaced to the operator after this artifact; the plan absorbs the answers.

## 3. Approach summary

A single-instance HA blueprint controls one hall LG AC to pre-cool multiple bedrooms
(measured by in-room Aqara sensors) to ~19 °C by a fixed bedtime, then runs a beep-budgeted
overnight state machine: free adjustment before bedtime, a locked maintaining setpoint, at
most one corrective command ~01:00, AC off at wake. Turn-on time is predicted by a
transparent linear lead-time formula (indoor gap + forecast outdoor + solar), recomputed
each minute; pre-cool is closed-loop on the bedroom sensors.

## 4. Evidence by claim

**Claim 1 — A linear "lead = base + k·ΔT, fire when now ≥ deadline − lead" predictor is a
mainstream HA community pattern.** `support_status: verified` · SUPPORT.
- T1 — Versatile Thermostat (most-used HACS climate integration) docs:
  *"on_percent = coef_int * (target − current) + coef_ext * (target − outdoor) … default
  values for coef_int and coef_ext are 0.6 and 0.01"* — linear indoor+outdoor blend.
  Firecrawl-verified.
- T3 — HA Community forum thread on early-start heating: accepted answer uses
  `now() >= target − timedelta(hours=(target−current)/rate)`; OP: *"approaching this
  linearly is fine for me."*
- T3 — separate HA forum thread ("thermostat recovery mode"): independent implementation,
  `start = wakeup − 60·(target−current)/heating_rate`. Cluster-independent from the above.
- Meets the gate (1×T1 + 2 cluster-independent T3).

**Claim 2 — The maturing best practice is a self-calibrating RC-thermal model; the
canonical static predictor was abandoned.** `support_status: verified` · informs critique.
- T1 — `github.com/springfall2008/predheat`: *"This repository was archived by the owner
  on Oct 12, 2024. It is now read-only."* Firecrawl-verified.
- T2 — `github.com/ebozonne/SmartHRT` ("Smart Heating Recovery Time", actively maintained,
  last commit Dec 2025): commit history confirms an `RCth` thermal parameter, wind/forecast
  inputs, and *"self calibration auto-adjust values"*. Firecrawl-verified.

**Claim 3 — A linear cooling estimate is least accurate near the target (Newton's law of
cooling → exponential approach).** `support_status: verified` (standard physics).
- T1 — Newton's law of cooling: `T(t) = T∞ + (T0−T∞)·e^(−t/τ)`; approach asymptotes.
- Mitigation already in the design: a fixed safety margin, per-minute recompute, and an
  AC setpoint held *below* 19 °C keep the room on the steep (near-linear) part of the curve.

**Claim 4 — LG ACs beep on every command; no software mute exists.** `support_status:
verified` · SUPPORT (the beep-budget premise is justified).
- T3 ×3 cluster-independent — official LG ThinQ HA integration issue (*"the AC beeps and
  changes the value"*); r/homeassistant (*"it does and it's pretty annoying… haven't found
  a way to disable"*); LG-owners group (*"no mute function"*). Meets the gate.

**Claim 5 — `dry` HVAC mode honouring a target temperature is model-dependent.**
`support_status: contested` — see §8.

**Claim 6 — LG ThinQ climate-entity quirks: `null` setpoint in non-`cool` modes
(fixed PR #147008), combined mode+temp call historically buggy, mode change fails on a
powered-off unit.** `support_status: verified`.
- T1 — HA core PR #147008 "Fix Air Conditioner set temperature error in LG ThinQ".
- T3 — HA issues #141473 / #131252 (*"Command not supported in POWER OFF"*).

**Claim 7 — `weather.get_forecasts` (plural) is the current service; the `forecast`
entity attribute was removed in HA 2024.4.** `support_status: verified`.
- T1 — HA weather integration docs: `weather.get_forecasts`, `type: hourly`,
  `response_variable`.
- T1 — HA 2023.9 release notes deprecate the `forecast` attribute; removal landed 2024.4.

**Claim 8 — Buienradar provides only a daily forecast — no hourly.** `support_status:
verified` · CONTRADICT (changes the recommended forecast source).
- T1 — HA Buienradar integration docs (firecrawl-verified): forecast fields are
  *"Temperature n days ahead"*, *"Minimum temperature n days ahead"*, barometer and
  precipitation forecasts — all daily granularity; no hourly field.
- T3 — community "Definitive guide to Weather integrations" capability matrix: Buienradar
  hourly column blank; Met.no 24 h, Open-Meteo 168 h, OpenWeatherMap 24 h.

**Claim 9 — `sun.sun` exposes `elevation` and `azimuth`; azimuth-window solar modelling
is a mainstream HA pattern.** `support_status: verified`.
- T1 — HA Sun docs: *"Azimuth … clockwise from north"*, *"Elevation … angle between the
  sun and the horizon … negative values mean the sun is below the horizon."*
- T1/T3 — Adaptive Cover integration / sun-protection blueprints gate on an azimuth
  field-of-view window — the design's west-room approach is well-trodden.

**Claim 10 — Indirect cooling room-to-room through a doorway is thermally weak; the
`hall_offset` needed to land bedrooms at 19 °C is likely >2 °C.** `support_status:
unverified — single T2 cluster` · serious flagged concern, does not gate the verdict.
- T2 (single cluster — two experts, one thread) — GreenBuildingAdvisor: moving heat by
  air exchange needs `CFM = BTU/(1.08·ΔT)`; *"the smaller the temperature differential,
  the more air"*; a real attempt with two 150 CFM fans *"did almost nothing."*
- Underlying physics is sound regardless of source count; magnitude (≈3–6 °C offset) is an
  estimate to calibrate empirically. The closed-loop precool design adapts to whatever the
  true offset is; the residual risk is the AC's `min_temp` capping how cold the hall can go.

**Claim 11 — 19 °C is inside the safe nighttime range for a child's room; cooler is safer
for SIDS; airflow must not blow directly on a child.** `support_status: verified`.
- T1 — The Lullaby Trust (UK SIDS charity): safe range *"between 16–20 °C"*; *"babies are
  safer being cooler than being too hot."* Guidance: a fan is fine but *"don't aim it
  directly towards the baby."*

**Claim 12 — The ESPHome lg-controller (CN-REMO wired) is the mature silent alternative.**
`support_status: verified`.
- T2/T3 — `JanM321/esphome-lg-controller` (221★, active): explicit advantage *"No annoying
  sounds from the AC unit when changing settings through the controller"*; echoed
  independently in the HA Community thread.

## 5. Community consensus signals

| Topic | Signal | Summary |
|---|---|---|
| Predictive precool as a custom automation | **STRONG** | Community builds these; nothing off-the-shelf does precool-to-a-deadline. |
| Linear vs RC/self-calibrating formula | **MIXED** | Linear is common in DIY; RC + auto-correction is the maturing best practice. |
| LG beep / "minimize commands" | **STRONG** | The beep is real and not software-mutable; minimizing commands is justified. |
| `dry` mode for precise temperature targeting | **NEGATIVE** | Unreliable, model-dependent; fan locked Low; integration `null`-setpoint history. |
| Indirect room-to-room cooling via a doorway | **NEGATIVE** | HVAC community is skeptical without large forced airflow. |
| ESPHome wired controller | **STRONG** | Recommended silent, local path; mature project. |

## 6. Anti-patterns flagged

- **"Simplistic linear correlation without real physics, aimed at the setpoint itself"** —
  named by the SmartHRT author. The design avoids the worst of it via the safety margin
  and a sub-target AC setpoint; it must not *claim* last-degree accuracy.
- **Calling `weather.get_forecasts` every minute** — wasteful, risks provider rate limits;
  fetch every 15–30 min. (Already in the spec; reaffirmed.)
- **Hard-coding climate-entity assumptions** (HVAC modes, fan modes, a non-null setpoint) —
  discover from attributes; guard every read.
- **A static-coefficient predictor with no error feedback** — the exact class of project
  the HA community archived (`predheat`). V1 mitigates with manual calibration; auto-learn
  remains the highest-value V2 item.
- **Treating doorway room-to-room cooling as direct cooling** — the hall must run much
  colder than the target rooms.

## 7. Critique findings (adversarial pass)

- **What would have to be true for the design to be wrong?** (a) The AC's `min_temp` is too
  high to drive the hall cold enough for bedrooms to reach ~19 °C on a normal hot day — the
  core promise then fails (the heatwave-degradation path is the safety net, but it would
  fire too often). (b) Idempotency has any defect — a stale ThinQ attribute after a
  reconnect, a rounding mismatch — and the failure mode is a beep over a sleeping child,
  unusually unforgiving. (c) The operator never calibrates the coefficients/offset, so the
  prediction stays mediocre. The design depends on the debug notification making
  calibration genuinely easy.
- **Sources weighted too heavily.** The indirect-cooling magnitude rests on a single
  GreenBuildingAdvisor thread — directionally sound (it is thermodynamics) but the specific
  3–6 °C figure is one estimate; calibrate, don't hard-trust. The SmartHRT author's
  dismissal of linear models is somewhat self-promoting — keep the substance (RC +
  self-calibration is genuinely more rigorous), discount the rhetoric.
- **Incentive-aligned sources.** Versatile Thermostat docs promote their own algorithm;
  the SmartHRT author promotes their own model; LG marketing claims a remote "mute" button
  that does not survive API commands. All discounted accordingly; the structural facts they
  supply (coefficient form, beep reality) stand independently.
- **Steelmanned contrarian position.** *Ship the trivial version first. The LG AC's
  built-in sleep timer already ramps the overnight setpoint with zero beeps; pair it with a
  one-line "AC on at 17:00 if forecast peak > 22 °C" automation, observe for two weeks what
  hall setpoint actually lands the bedrooms at 19 °C, and only then decide whether a
  ~28-input predictive state machine earns its complexity. If it does, build the
  auto-learned offset/lead correction first — a predictor that cannot see its own error is
  the exact thing the community archived.* This is a legitimate position; it is not adopted
  because the operator has explicitly chosen to build the full blueprint, but its core
  insight — calibration and error-feedback are load-bearing — is folded into adjustments
  B, C and operator decision 2.

## 8. Contested claims

- **`dry` mode honours a target temperature.** One LG product manual (quoted in an HA
  issue) says the compressor stops *"once the set temperature is reached"* in dry mode;
  an r/hvacadvice thread reports *"temperature control does not work in … Dry modes"*; LG's
  own guidance frames dry mode as humidity-led *"at the same temperature."* Contradiction
  is **minor-material** — it does not break the design, but it makes the dry-mode *feature*
  unreliable. Resolution: de-risk via operator decision 1 (opt-in, default OFF).

## 9. Unverified claims (do NOT gate the verdict)

- **`hall_offset` ≈ 3–6 °C** — single T2 cluster; physics-sound, magnitude is an estimate.
  Carried forward as a calibration target and a triple-check on-unit-probe item.
- **"AC scheduling saves ≈ $0 vs a plain hold setpoint"** — single T3 blog; illustrative
  of the over-engineering risk, not gating.
- **Staged-automation restart fragility** — single T3 thread (2021, >12 months);
  illustrative; the design's stateless re-derivation is the correct mitigation.

## 10. Bibliography

**T1 — primary / authoritative**
- Versatile Thermostat algorithms — github.com/jmcollin78/versatile_thermostat/blob/main/documentation/en/algorithms.md
- predheat (archived) — github.com/springfall2008/predheat
- HA weather integration — home-assistant.io/integrations/weather/
- HA Buienradar integration — home-assistant.io/integrations/buienradar/
- HA Sun integration — home-assistant.io/integrations/sun/
- HA LG ThinQ integration — home-assistant.io/integrations/lg_thinq/
- HA core PR #147008 — github.com/home-assistant/core/pull/147008
- HA 2023.9 release notes — home-assistant.io/blog/2023/09/06/release-20239/
- The Lullaby Trust, hot-weather guidance — lullabytrust.org.uk/baby-safety/travel-and-weather/hot-weather/
- Newton's law of cooling — en.wikipedia.org/wiki/Newton%27s_law_of_cooling

**T2 — established expert**
- SmartHRT — github.com/ebozonne/SmartHRT
- ESPHome lg-controller — github.com/JanM321/esphome-lg-controller
- GreenBuildingAdvisor, moving conditioned air between rooms — greenbuildingadvisor.com/question/moving-conditioned-air-between-rooms-science-of-temperature-delta
- Koskila, HA 2024.4 weather changes — koskila.net/home-assistant-2024-4-changes-weather-forecasts-what-to-do/

**T3 — community signal**
- HA forum — early-start heating — community.home-assistant.io/t/automating-an-heaters-early-start-to-get-a-room-to-temperature-in-time/956504
- HA forum — thermostat recovery mode — community.home-assistant.io/t/thermostat-recovery-mode-or-when-to-start-heating-to-reach-the-set-point/508892
- HA forum — SmartHRT thread — community.home-assistant.io/t/smarthrt-smart-heating-recovery-time-cool-sleep-warm-wake-up/833025
- HA forum — Definitive guide to Weather integrations — community.home-assistant.io/t/definitive-guide-to-weather-integrations/736419
- HA forum — LG AC wired controller via ESPHome — community.home-assistant.io/t/lg-ac-wired-controller-integration-via-esphome-esp32/582954
- HA forum — Intelligent Preheating (physics-based) — community.home-assistant.io/t/intelligent-preheating-physics-based-pilot/962007
- HA core issue #146575 (LG beep) / #141473 / #131252 — github.com/home-assistant/core/issues
- r/homeassistant — LG AC beep — reddit.com/r/homeassistant/comments/ociwll/
- r/hvacadvice — temperature in Dry mode — reddit.com/r/hvacadvice/comments/xofijw/

**T4 — single / unverified (not gating)**
- Quora — disabling AC beep; LG marketing on remote "mute"; the-smart-home-hookup AC-scheduling blog.

## 11. Methodology

- **Mode:** Deep. 4 parallel general-purpose agents — (1) predictive climate-automation
  patterns + lead-time formula, (2) LG ThinQ climate entity / dry-mode / beep, (3)
  `weather.get_forecasts` + sun/solar, (4) adversarial — indirect cooling, anti-patterns,
  child safety.
- **Cross-validation rule applied:** 1×T1 OR 2×T2 OR 3×T3, cluster-independent.
- **Firecrawl verification:** 4 high-leverage claims spot-checked against primary sources
  (predheat archive status, SmartHRT model, Versatile Thermostat coefficients, Buienradar
  forecast granularity) — all confirmed; no fabricated citations found.
- **Timeouts / partial results:** none — all 4 agents returned full reports. Reddit pages
  were not directly scrapable; Reddit findings rest on search excerpts (flagged T3).
- **Quality bar:** Deep (15+ sources, 3+ per major claim) — met (~25 distinct sources).
