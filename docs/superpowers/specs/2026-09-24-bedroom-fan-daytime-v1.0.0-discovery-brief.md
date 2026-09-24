# Discovery brief — d1-fans-occupancy-nap

Repo / Epic / Session / Phase: leviemartin/Blueprints_Home / Epic #39 / Session #40 / d1-fans-occupancy-nap
Rounds: 3 — ledger 58d32853 (r1), 5d32630f (r2), ce7ef232 (r3) — Driver: claude
Discovery worker self-reported model: Fable 5.1 (claude-fable-5-1), xhigh via stackb-discovery frontmatter (information only)
Compacted by the Opus orchestrator for the comment limit; fuller non-authoritative wording: ~/AI/reviews/bedroom-fans-20260924/discovery-r3-full-evidence.md (planner evidence only; this brief governs).

## 1. Outcome, scope, non-goals

Outcome. The kids fan (fan.ceiling_fan_light_v2) and master fan (fan.ceiling_fan_light_v2_2) stop running unattended by day: 08:00–18:00 a running fan is switched off once nobody has been upstairs for a vacancy timeout. During a parent-signalled nap the kids fan runs at the lowest step only when the temperature calls for it — cooling direction when warm, warming direction when cold, reversing mid-nap if the room crosses the band — and stops when the need clears or the nap ends. 18:00–08:00 the existing automations keep running (pre-cool 19:29 night fans, safety cutoff, dimmer). All seven actors (cutoff C, seasonal direction S, Hue dimmer D, pre-cool P, sleep trainer T, new daytime blueprint N, new manual detector M) cooperate under one rule: a fan a person genuinely changed after 18:00 is left alone by every automation writer until 08:00; an automation's own write, a cloud recovery or the cutoff's own off/resume is never mistaken for manual; fan and nightlight always agree on "napping".

Scope (full chain: tested blueprints, boards, deploy, observe):
- New bedroom_fan_daytime.yaml, one instance per room: kids (vacancy-off + nap + direction), master (vacancy-off only); baby room (sensor.temperature_sensor_4) later by configuration. Reads and stamps detector records.
- New fan_manual_watch.yaml (detector, §2a), one instance per fan (kids with cutoff/seasonal/interlock inputs; master plain).
- bedroom_precool.yaml v1.3.0: optional `fan_manual_records` (fan → {since, stamp} helpers) and `manual_window_start` (time). Configured: night-fan and fan-assist due rules use the detector record instead of raw last_updated, stamp before every command, treat another writer's newer stamp as ownership; unsafe-on cut keys on P's own stamp. Unconfigured: v1.2.1 byte-for-byte. Live instance redeployed with both fans' records and 18:00:00.
- nightlight.yaml v1.3.0: optional `nap_toggle`. Configured: nap cue follows the toggle (fixed window ignored), toggle state triggers repaint. Unconfigured: v1.2.0 fixed window. Live instance redeployed with input_boolean.kids_nap.
- Helpers (HA config, not blueprints): input_boolean.kids_nap; input_datetime.kids_fan_manual_since, input_datetime.master_fan_manual_since; input_text.kids_fan_expected, input_text.master_fan_expected (max 255).
- README, requirements_bedroom_fan_daytime.md, requirements_fan_manual_watch.md, updated pre-cool/nightlight requirements, deploy/ JSON for six instances, pytest structure + rendered-Jinja tests for all four YAMLs, deploy via scripts/deploy-blueprint.sh.

Non-goals: no change to the cutoff, seasonal or dimmer blueprints (ceiling-fan-hue-blueprint repo; M infers their writes), the AC, P's night speed, guard or fans_at_wake (stays `leave`); no camera/Frigate for the kids' bedroom; no new presence hardware; no humidity control. T's fixed 12:30–15:30 window becomes the fallback.

## 2. Constraints and decisions

- Nap signal (Q1): parent-signalled, no camera. Dimmer goodnight fade (Off short_release, gate group lit) inside 08:00–18:00 starts a nap; wake ramp (+/− short_release, gate dark) or gate group on ends it; dashboard toggle fallback; 3 h max.
- Manual window (Q2, supersedes intake): automations run at night; a genuine manual change 18:00–08:00 latches that fan until 08:00; P and N leave it alone; cutoff stays active regardless.
- Latch strictness (r3): real manual detector recording a per-fan "manual since" only for genuine user power/speed/direction changes; ignores unavailable→state recoveries, the cutoff's off/resume and our automations' writes. P and N honour it.
- Writers outside HA (r3): none — only HA, the physical remote, the wall switch. Any unstamped change that is not a recovery or trusted automation is a person's.
- Sleep trainer (r3): in scope; reads the nap toggle; fixed window only as fallback.
- Orchestrator musts (r3): (a) a nap-end off blocked by the cutoff hold is retried after the clear hold; (b) N never fights P's active phases (fan-assist, night settle).
- Seasonal attribution (decided): not manual — the toggle is a season preference and S restores the prior speed; counting it would make P skip the night fan whenever Martin flips the season, contradicting Q2. Dimmer fan holds stay manual.
- Daytime (Q3): nap-only in kids room; master never auto-started by day; any fan, incl. hand-started, off after the vacancy timeout.
- Direction (Q4): both directions with mid-nap reversal via state-verified stop-then-reverse.
- Intake: no hard-coded nap days/times; existing sensors only; minimal runtime. S26 (do not re-ask): night ceiling 1 %; cutoff authoritative; kids-fan writes edge-triggered only; fans not hard-coded.
- Cutoff contract (mode single): any fan.turn_on during the hold cancels the resume; fires only on a new PIR on-transition. Every writer refuses turn_on, turn_off and set_direction on the kids fan while binary_sensor.samuel_samuel_matthew_fanprotection is on/unavailable/unknown/absent or changed within the clear hold (5 min ≥ 3 + 2), and cuts its own write landing under a tripped PIR (120 s arm).
- Carried idioms: Tuya lag 10–60 s; one command per transition with percentage; continue_on_error; live re-check before each call; persistent notifications only.
- Attribution by stamp, not context (fact): Tuya cloud updates carry a fresh HA context, so user_id/parent_id cannot separate a remote press from an automation's confirmed write. Writers stamp expectations before commanding; M matches.
- Facts: winter_mode off = summer = forward (cooling), on = reverse. Fans supported_features 53; percentage kept while off. Live P: ideal 23, tolerance 1.5, fan_only, night fans all 1 % in 19:29–20:14 settle, interlock_clear 5, fan_assist off, fans_at_wake leave. Master fan ran 10 days straight; Tuya flaps 09-22 17:27→20:21, 09-24 08:21 and 15:26. Vacancy has one upstairs PIR, binary_sensor.stairs_motion (staircase_motion = same device); kids PIR adult-height only; samuel_nightlight_motion corroborating only.

### 2a. Manual detector (fan_manual_watch.yaml)

Per fan: `since` (input_datetime, written only by M) and `stamp` (input_text, written only by writers) formatted `writer|state|pct|dir|ts` (writer ∈ precool, daytime; `*` = not asserted; ts = unix s). Writer invariant: stamp first, command second; failed stamp aborts ("no stamp, no command"). M: one automation per fan, mode queued, state trigger on state and attributes, classifying in order with the event's own to_state.last_updated as now:
1. Replay (from_state none or restored) → ignore.
2. Recovery (from/to unavailable/unknown) → ignore.
3. No-op (state, pct, dir unchanged) → ignore.
4. Own write: stamp ts within lag_seconds (120) and new state matches (state; pct/dir when asserted) → ignore.
5. Cutoff (kids): on→off while the cutoff automation runs (`current` ≥ 1) and the sensor is on → cutoff; off→on within lag after the run ended (`current` 0, last_updated within lag) with the sensor clear ≥ hold − 15 s → resume. An on while the run is active = the cancel path = manual.
6. Seasonal (kids): any change within lag + coast (4 s) after S's last_triggered → ignore.
7. Otherwise → manual: since = event instant.
Consumer contract: manual-in-window = since ≥ window_start; "ours" = fan matches my latest stamp and since < stamp ts; "owned by another" = latest stamp is another writer's and newer than my reference; missing/unavailable helper → skip + one notice, never a write.
Residuals (all fail toward a skipped write, never unsafe): (i) an off-target Tuya intermediate publish inside lag reads manual and latches the fan for the night — live check (e); (ii) a person's change inside lag landing on the stamped value reads ours (no visible effect); (iii) a person's change within ~2 min after a season flip, or an off→on within 2 min after a cutoff resume, is attributed to that automation — P may set 1 % at 19:29 inside settle; (iv) renaming the cutoff/seasonal automation without updating M degrades their writes to manual; (v) writer crash between stamp and command leaves a stamp that expires after lag; (vi) dry-run must assert one watcher per fan and consistent helper mapping.

## 3. Interfaces

- Written: kids fan (turn_on+percentage, turn_off, set_direction); master fan (turn_off by N, turn_on by P); input_boolean.kids_nap (N only); *_manual_since (M only); *_expected (P and N only); light.samuel_nightlight (T, unchanged services); persistent_notification.
- Read: sensor.temperature_sensor_3 (kids, battery 26 %), _2 (master, unused in v1), _4 (baby, later); fanprotection interlock (M, N); binary_sensor.stairs_motion; event.baby_room_button_2/3/4; light.kids_room_gate (N, T); input_boolean.samuel_fan_winter_mode; automation.samuel_fan_safety_motion_cutoff and automation.samuel_fan_seasonal_direction `current`, `last_triggered`, last_updated (M); fan pct/dir; since/stamp helpers.
- Existing owners kept working: cutoff (unchanged, authoritative); seasonal (unchanged, attributed as automation); dimmer (unchanged; holds manual; Off/+/− events = nap signal); automation.toddler_sleep_trainer_nightlight_v1_1_0 (redeployed on v1.3.0 with nap_toggle); automation.bedroom_sleep_pre_cool_v1_0_0 (redeployed on v1.3.0; otherwise unchanged).
- Deploy: deploy-blueprint.sh dry-run validates instance keys; every new input has a default; six deploy JSONs; helpers before referencing instances (order §7).

## 4. Acceptance examples

Defaults: day 08:00–18:00, vacancy 20 min, nap_pct 1, ideal 23, tolerance 1.5, hysteresis 1.0, interlock_clear 5, reversal_dwell 30, nap_max 3 h, day_end_margin 5 min, lag 120 s, nap_end_retry 15 min. "Ours" = matches N's latest stamp, no manual since.
1. Morning sweep: both fans 1 % from P's stamped 19:29 write; last stairs motion 07:40 → at 08:00 each instance stamps + one turn_off (P's stamp older than day_start, no exemption).
2. Occupied morning: stairs 07:58 → nothing at 08:00; off 08:18 if quiet. Stairs/kids-PIR on-transition, since move or nap toggle on restarts that room's timer.
3. Hand-started master fan 14:00 unseen by sensors → manual 14:00 counts as activity → off 14:20; restart 14:21 → 14:41. Documented limitation.
4. Nap warm: Off tap (gate lit) 12:40 → toggle on; room 24.8 ≥ 24.5; fan off, no manual since nap start, interlock clear, forward → stamp `daytime|on|1|forward`, one turn_on 1 %; M sees a match → not manual. 23.4 ≤ 23.5 → stamp, turn_off. Wake ramp 14:30 → toggle off only.
5. Nap mild: 22.8 throughout → zero fan writes; nightlight nap colour.
6. Nap cold: 21.3 ≤ 21.5; fan off → stamp, set_direction reverse; after read-back (90 s timeout → abort, one notice) stamp, turn_on 1 %. Nap end → stamp, turn_off; after confirmed off, stamp, set_direction to the live season-toggle direction.
7. Mid-nap reversal: warming fan ours since 13:00; 13:45 room 24.6, dwell 45 ≥ 30, interlock clear, > 10 min before day_end → turn_off → wait off ≤ 90 s → set_direction → wait attribute ≤ 90 s → live interlock re-check → turn_on 1 %, each stamped.
8. Reversal aborted (PIR trip or timeout) → stop, fan off, one notice, no retry that nap.
9. Cutoff during nap fan: enter 13:10 → off; leave 13:12 → resume 1 % 13:15; M attributes both to C; N silent 13:10–13:17 (clear hold); resumed fan matches the stamp → still ours, band logic continues.
10. Nap start under interlock: PIR on → no write; clears 12:42 → write first tick after 12:47; still blocked 10 min after start → one notice, no more attempts.
11. Own write under lag: stamped turn_on 12:47:00, PIR trips 12:47:20, fan on 12:47:40 → stamp within 120 s + PIR on → stamp, turn_off (only protection; P's accepted residual).
12. Latch night: dimmer turns kids fan off 18:30 → manual ≥ 18:00 → P skips it at 19:29 and notes it; untouched master gets 1 %. 08:00 vacancy rule resumes both.
13. Latch boundary: dimmer hold 17:50 → manual < 18:00 → P sets 1 % at 19:29.
14. Latch expiry: master to 33 % by remote 21:00 → manual → 08:00 + vacancy → off.
15. Nap into day_end: toggle on 15:10, no end → forced end 17:55 (stamped off + direction restore before 18:00); no reversal starts after 17:45.
16. Nap cap: 12:30 untouched → forced off 15:30; ours fan off; direction restored.
17. Sensor failure: kids temperature unavailable/non-numeric → no nap start; ours fan running → off + one notice; < 16 °C → no fan, one notice.
18. Fan unavailable: no writes, one notice at nap start. Unavailable→on flap ignored by M; fan still matches stamp → ours.
19. Restart mid-nap: toggle/since/stamp persist; fan matching stamp → ours; restored-trigger guards block replays; next tick continues.
20. Season flip mid-nap: S reverses and restores 1 % (not manual, still ours); if the room still needs cooling the envelope (dwell 30 from S's write, stop-verified, interlock) reverses back once; nap end restores the toggle's current direction. At most one reversal per dwell.
21. Escape: disabling the kids N instance or clearing its toggle input stops nap writes, vacancy-off continues; disabling M → consumers skip + one notice; P without `fan_manual_records` and T without `nap_toggle` behave as v1.2.1/v1.2.0 (tests assert default paths).
22. Night silence: N issues no fan command 18:00–08:00 (trace audit); 17:55 wrap-up is last.
23. Flap not manual: kids fan unavailable 18:30→18:50 untouched → ignored → P sets 1 % at 19:29.
24. Cutoff at night: cut 18:40, resume 21 % 18:44 → both attributed to C → at 19:29 not at target, interlock clear since 18:46 → P stamps, sets 1 %.
25. Nap-end off during a hold (must a): wake ramp 14:30, cutoff holding since 14:29 → no write; resume 1 % 14:33; clear hold ends 14:35; next tick within nap_end_retry fan matches stamp → stamp, turn_off, direction restore. Zero calls 14:29–14:35.
26. Assist exemption (must b): fan_assist on, AC 16:10, P stamps both fans 21 % → N sees P stamps newer than day_start → vacancy-off skips them until next 08:00.
27. Nap vs assist: nap fan ours 1 % since 15:40; AC 16:10 → P sees N's stamp newer than AC start → skips kids fan (never 21 % on a napping child); master gets 21 %.
28. Nightlight follows toggle: Off tap 11:45 → toggle on; gate dark → nap colour (outside old window); nap end 13:10 → nightlight off within a minute; ramp's Jungle accent paints as before.
29. Nightlight fallback: no `nap_toggle` → fixed 12:30–15:30 as v1.2.0.
30. Stale toggle: toggle on 19:00 → no fan writes; night colour anyway; cap off 22:00; a toggle still on at 08:00 is switched off before vacancy logic.
31. Dimmer after a flip (residual iii): flip 20:00, hold 20:01 → attributed to S; same hold 20:05 → manual.
32. Record missing: input_text.kids_fan_expected deleted → P and N skip every command to that fan, one notice each; no unstamped command.
33. Daytime flap: unavailable 08:21→08:23 → no manual, timer untouched; vacancy-off 08:40 proceeds.
34. Person's on during a hold: cutoff holding since 13:10, parent holds "−" 13:12 → on during active run → manual (cancel); N hands off that nap; at night it latches.
35. Flip during a hold: fan off → S does set_direction only → resume proceeds; nothing manual.
36. Flip in settle: P stamped 1 % 19:29; flip 19:40 → off, reverse, on 1 % → at target, P writes nothing more; flip 19:28 on an off fan → set_direction only → 19:29 write proceeds.
37. Dimmer hold during nap: parent sets 21 % 13:00 → manual → parent's fan for that nap (no band writes, no nap-end off); vacancy-off 20 min after last upstairs activity.

### 4a. Interaction matrix

No shared entity (no rule needed): C–T, S–T, P–T (both use 18:00 by coincidence), T–M.

| Pair | Shared / window | Cooperation rule | Proof |
|---|---|---|---|
| C–S | kids fan, any | Unchanged; a flip during a hold finds the fan off → set_direction only, resume not cancelled. | 35 |
| C–D | kids fan, any | Dimmer hold during a hold = the cutoff's documented manual override; M records manual. | 34 |
| C–P | kids fan, settle/assist | P never writes under PIR on/unavailable/absent or within the 5-min clear hold; cuts only its own stamped write within 120 s; C off/resume not manual, so P applies 1 % after the hold if not at target. | 11, 24 |
| C–N | kids fan, PIR, day | N never turn_on/turn_off/set_direction while blocked; cuts own stamped write under a trip; aborts reversal on a trip; retries nap-end off after the clear hold. | 8–11, 25 |
| C–M | kids fan, any | M attributes C's off (run active, PIR on) and resume (run ended, clear ≥ hold); an on during the run is manual. | 9, 24, 34 |
| S–D | kids fan, any | Unchanged; a dimmer press within lag + coast after a flip is attributed to S (iii). | 31 |
| S–P | kids fan, settle | P never writes direction; a flip is not manual, so P still sets 1 % if not at target. | 36 |
| S–N | kids fan, toggle, day | Toggle = rest direction, restored at nap end from its live value; nap direction temperature-driven; mid-nap flip keeps the fan ours, at most one reversal per dwell; none after 17:45. | 20 |
| S–M | kids fan, any | S's writes within lag + coast of last_triggered = automation. | 36 |
| D–P | kids fan, night | Dimmer holds manual: after 18:00 latch until 08:00 (P skips); before 18:00 not. | 12, 13 |
| D–T | gate, nightlight | Unchanged: T pauses while gate lit, repaints at gate-off; with toggle the fade ends in nap colour, the ramp in the Jungle accent. | 28 |
| D–N | dimmer events, gate, kids fan, day | Off short_release (lit) starts nap; +/− short_release (dark) or gate on ends it; fan holds manual → N hands the nap to the parent; instant-off hold starts no nap. | 4, 6, 37 |
| D–M | kids fan, any | Dimmer writes unstamped → manual. | 12, 34 |
| P–N | both fans; day vs settle/assist | N commands only 08:00–17:55; N exempts fans whose latest stamp is P's and newer than day_start; P skips fans whose latest stamp is N's and newer than P's reference; P's night stamp is older than day_start at 08:00. | 1, 15, 22, 26, 27 |
| P–M | both fans, night | P stamps before every command; night write needs since < 18:00, assist needs since < AC start; own stamp = already written; unsafe-on cut keyed on own stamp; missing record → skip + notice. | 12, 14, 23, 24, 32 |
| T–N | nap toggle, day | Both read kids_nap; N owns its lifecycle (start, end, cap, 08:00 reset); T paints nap colour when on and gate dark; fixed window only without toggle. | 28–30 |
| N–M | both fans, day | N stamps every command incl. cuts and direction; vacancy activity uses since, not last_updated; ours = my stamp and since < stamp ts; manual during a nap hands the fan to the parent. | 3, 18, 19, 33, 37 |

## 5. Open choices, release and observation

Unresolved product choices: none.

Release (before deploy): pytest green for all four YAMLs — structure; inputs via top-level variables; instants as timestamps; rendered-Jinja tests for band/hysteresis, vacancy age, ownership and exemption predicates, interlock with clear hold, M's seven rules incl. cutoff off/resume/cancel and seasonal window, stamp parsing, P's record rule and v1.2.1 default path, T's toggle and fixed-window default paths. deploy-blueprint.sh --dry-run passes for six instances; every new input has a default; version tests updated (nightlight asserts v1.3); helpers exist and each fan maps to exactly one watcher.

Live verification (deploy day, kids room empty, Martin outside): a) set_direction on the off Tuya fan accepted, reads back in time, does not switch it on; b) one full reversal by hand from outside; c) cutoff path with a nap fan (enter → off; leave 3 min → resume; no re-assert; M records nothing manual); d) reversal enabled only after a–c pass, else cooling_only; e) attribution probe: stamped turn_on from off → no manual; one remote press → exactly one; HA restart or flap → none; a person's on during a hold → one; f) nightlight follows a toggle flip within a minute, gate dark.

Observation (≥ 3 weekdays and ≥ 3 nights, incl. one deliberate latch night with a remote change after 18:00 and, if possible, one flap or cutoff night): fans off within vacancy of the last upstairs activity each morning; ≥ 1 dimmer nap with fan on/off matching the band and nightlight matching the toggle; ≥ 1 mild nap with zero writes; P's 19:29 write lands on untouched, flapped or cutoff-resumed fans and skips only the hand-changed fan; since helpers move only on real presses (vs Martin's log); zero N fan calls 18:00–08:00; ≤ 1 notification per condition per day; no fight loops. Session closes only after deploy and observation.

## 6. Opportunities

Accepted: one instance per room; M as a reusable blueprint for any Tuya fan; nightlight keyed on the toggle; dashboard nap toggle; blocked-write, abort and missing-record notices; master vacancy-off; unsafe-on cut keyed on P's own stamp (removes the "cuts a person's on in settle" residual).
Deferred: native stamping in the cutoff and seasonal blueprints (removes residuals iii–iv); P fans_at_wake off at 07:15 under the detector rule; humidity-driven circulation; night circulation tuning; kids-room camera (privacy decision first; Camera-Hub-G5Pro-C1F4 unidentified); upstairs presence sensor (removes the hand-started limitation); fan power measurement.
Rejected: hard-coded nap windows; per-tick kids-fan re-assertion; PIR as child presence; streaming the kids' bedroom without explicit authorization; context-based attribution; reversal without a state-verified stop; modifying the safety cutoff in this chain.

## 7. Decided by orchestrator (proposed)

- N: mode restart, max_exceeded silent, 1-min time_pattern + state triggers (toggle, dimmer events, gate, stairs PIR, interlock), restored-trigger guard, ha_start re-evaluates only; one instance per room; nap state = input_boolean set by N, reference = its last_changed; thresholds as inputs (23 / 1.5 / 1.0, 16 °C floor); direction_mode cooling_only / both_at_start / both_with_reversal; rest direction from season toggle + summer/winter inputs; reversal envelope (dwell 30 from fan last_updated, 90 s waits, abort leaves off + one notice, not within 10 min of day_end, never while blocked, live re-check, 120 s cut); vacancy activity = sensor on-transitions, since moves, toggle on; blocked nap write retried 10 min then one notice; nap_end_retry 15 min; toggle on at day_start switched off first; day_end_margin 5.
- M: mode queued (max 10), lag 120 s, cutoff hold 3 min ± 15 s, seasonal window lag + coast; event timestamps, not now(); notification only for a missing helper.
- Records: helper names per §1; stamp `writer|state|pct|dir|ts`; P's `fan_manual_records` as an object selector fan → {since, stamp}; a configured fan without an entry falls back to v1.2.1 with one notice.
- P v1.3.0 limited to: reference instants of fans_due_night, fans_due_precool, fans_unset_night; stamp writes; own-stamp fans_unsafe_on; the notice; empty `manual_window_start` → lock_ts.
- T v1.3.0: `nap_toggle` default empty; two toggle state triggers with restored guard; is_nap_window = toggle when configured, else fixed window.
- Notifications: persistent_notification, fixed ids per condition, dismissed at the next boundary; no Telegram in v1.
- Deploy order: helpers → watchers → P → T → N. Files: README sections, requirements_bedroom_fan_daytime.md, requirements_fan_manual_watch.md, tests/test_bedroom_fan_daytime_structure.py, tests/test_fan_manual_watch_structure.py, deploy/bedroom_fan_daytime_{kids,master}_<id>.json, deploy/fan_manual_watch_{kids,master}_<id>.json, deploy/nightlight_1766142134972.json, updated deploy/bedroom_precool_1779553673971.json.

## 8. Stakes

- Physical safety: a second automatic starter and stop-reverse-restart on a head-height fan above a sleeping child, beside a cutoff whose resume any turn_on cancels. Cutoff stays authoritative; every command incl. set_direction gated on the interlock and clear hold; every abnormal path fails toward "fan off"; 10–60 s lag residual inherited. High-risk: design and code boards; reversal live test before enabling reversal.
- New shared trust point: since/stamp helpers feed two writers. A wrong "not manual" can only let P set 1 % at 19:29 inside settle over a person's change (iii, never past the interlock); a wrong "manual" only skips writes. The unsafe-on cut rewrite is safety-relevant — board must review; invariant "no stamp, no command".
- Config authority: redeploys two closed chains' live instances (P v1.3.0, T v1.3.0) plus four new automations and five helpers, all additive with behaviour-preserving defaults; T change touches the child's sleep cue.
- Deploy actuates real fans in children's rooms; live verification in an empty room.
- No new trust boundary, camera, secrets or destructive data.
