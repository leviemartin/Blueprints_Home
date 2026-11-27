# RFC: Living room and adjacent-room lighting (daylight off, dog-safe nights, one rhythm)

26 November 2026 · Martin Levie. Decided in a grilling session and approved by Martin on 26 November 2026. Ledger: `docs/design/2026-11-26-living-room-lighting-jobs.json`.

The living room lights have been on almost nonstop since 22 November. The cause is a re-paired FP300 sensor and brightness thresholds the room never reaches. A dog on the couch also keeps them on at night. This RFC fixes both blueprints together, so the living room, kitchen, front hall, toilet and attic keep one rhythm. It is built outside Foreman by this Opus session, one job per branch, and every merge, push and HA deploy needs Martin's OK.

## 1. Goals and non-goals

| ID | Goal | Measured by | Baseline (16-26 Nov) |
| --- | --- | --- | --- |
| T1 | The living room lights switch off after the room is empty, every time | light and presence history | never since 22 Nov 00:47 |
| T2 | On bright days the living room lights are off for part of the morning, with at most 2 switches a day | light history and lux simulation | 0 min off |
| T3 | Between 01:00 and 06:00 the dog on the couch cannot keep the lights on | night history | the old FP300 fired 18 times and the lights switched about 12 times on 17 Nov |
| T4 | A missing or dead presence sensor never leaves the lights stuck on, and Martin is told | a structure test, plus a live check after deploy | lights stuck on, no alert |
| T5 | All five rooms use the same times, colours and brightness, enforced by a test | the drift test | 6 differences, and the attic runs on defaults |
| T6 | A manual change by hand survives the 5-minute update | a structure test, plus a live check | overwritten within 5 min |

**Non-goals:** no new helpers, no template sensors, and no Adaptive Lighting. Sensor placement and FP2 zone or sensitivity tuning are out of scope. So are the bedroom, bathroom and climate blueprints.

## 2. What the research found

Three read-only studies on 26 November. The full reports were kept outside the repo; this section summarises them.

- **No working way to turn the lights off.** The instance pointed at `binary_sensor.living_room_main_fp300_couch_occupancy_sensor`, which disappeared when the FP300 was re-paired. It is now `binary_sensor.aqara_presence_multisensor_fp300_occupancy`.
  - **Why the lights never switched off:** before an FP2-off can switch the lights off, `presence_off_ok` checks the FP300's `last_changed`. A missing entity has none, so the check is always false (`circadian_livingroom.yaml`, about L440-447).
  - **Why no alert came:** the FP300 off and offline triggers need state changes, and a deleted entity never produces any. The deploy dry-run checks input keys, not whether the entities exist.
  - **Covered by a test:** `tests/test_circadian_livingroom_structure.py:244` asserts this "missing sensor means occupied" rule.
- **Daylight off can't fire.** The rule needs more than 611 lx for 5 min, but the FP2 light sensor peaked at 187-399 lx over the 10 days.
  - **Daily shape:** above 150 lx from about 09:30, a 270-400 lx peak at 10:00-10:30 from a direct-sun patch, under 150 lx by about 11:45, 80-130 lx at midday, and under 50 lx from about 16:00.
  - **The lamps barely affect it:** they add about +25 lx in daytime (up to 45) and 0-8 lx at night.
  - **Readings are noisy:** the sensor reports on change, with a median gap of 44 s and steps of about 15 %. 60-70 % of crossings bounce back within 5 min.
  - **The FP300 light sensor is worse:** 929-1588 lx peaks from sun on the device, and reports up to 40 min apart.
  - **The trigger can't catch up:** it is edge-triggered `numeric_state`, so it never fires if lux is already above the threshold after a restart or reload.
- **The 250/175 setting holds up.** Simulated over 11 days, 250 lx held 10 min (off) and 175 lx held 5 min (on) gave 12 switches in total, at most 2 a day. The lights were off 41-74 min on bright days, for any lamp contribution from 20 to 45 lx. Gaps of 50 lx or less, or no wait on turn-on, gave 4-8 switches a day.
  - **Season caveat:** December and January rarely reach 250 lx. April to September exceed it 10-12 h a day. Flicker on cloudy summer days is untested, because the long-term statistics are only hourly.
- **Nights.** Between 01:00 and 06:00 the FP2 sees 6.1 events a night. 56 of 67 last under 60 s, which matches passing through; the 05:00 cluster is people getting up. The old FP300 held for minutes, 14 times with the FP2 clear, which matches the dog. Neither sensor can tell a pet from a person.
- **Front hall** (`sensor.frontdoor_hall_illuminance`, lamp `light.hue_aurelle_panel_1`): it peaks at 156-271 lx around 12:00-14:00, with readings of 100 lx or more from about 09:00 to 14:50. The lamp step is noisy, about +10 to +55 lx, mostly +25 to +40. The instance's 400 lx off threshold never fires.
- **Adjacent blueprint bugs.**
  - **2000 K skip:** the warning-colour guard (about L538-547) skips any lamp within 50 K of 2000 K. The kitchen, hall and toilet run at 2000 K from 20:00, so the 23:30 night dim never applies.
  - **Unused input:** `lux_off_duration` (about L333) does nothing.
  - **Same missing-sensor flaw:** a missing motion sensor counts as "not clear" (about L372-419).
- **Rhythm drift.**
  - **Times and brightness:** the living room uses dinner 17:45, toddler 18:45, toddler 85 % and night 29 %. The kitchen, hall and toilet use 18:00, 19:00, 80 % and 30 %.
  - **The attic runs entirely on defaults:** night at 22:00, 20 %, 2200 K, and min/max 2200/4500 K.
  - **Same in both blueprints:** the code formulas (day start 06:00, kelvin from sun elevation) are identical.
- **Best practice** (HA docs and community).
  - **Re-check on every trigger.** Recompute "lights should be on" on every relevant trigger, at start and reload, and on a periodic tick, instead of relying on crossings. This holds for the 2026 `illuminance.crossed_threshold` trigger too, which is still edge-only.
  - **Two thresholds plus a wait, with the off threshold above "on + lamp contribution".**

## 3. Already done: stopgap X0

At about 23:10 on 26 Nov, with Martin's OK, the living room instance was re-pointed to `binary_sensor.aqara_presence_multisensor_fp300_occupancy`.
- **How:** instance-only POST; the blueprint was not re-saved.
- **Backup:** `deploy/1767031159524.prev.json`.
- **Checked:** HA returned `ok`, the automation is `on`, and the live config shows the new entity.
- **Repo:** `deploy/circadian_livingroom_1767031159524.json` is updated but not committed.

Until J3 ships, the dog can hold the lights on at night again.

## 4. Decisions (grilling session, 26 Nov 2026)

| # | Decision |
| --- | --- |
| D1 | Repoint the FP300 now (done, X0). |
| D2 | **Missing or dead sensor.** A missing, unavailable or unknown presence or motion sensor counts as clear, and the other sensors decide. If every sensor is dead, the lights go off after the normal timeout. The living room pushes to its `notify_targets`, at most once an hour per sensor. The adjacent blueprint raises an HA persistent notification only, with a fixed `notification_id` per instance. The deploy script refuses a config whose entities don't exist. |
| D3 | **Re-check every time.** On every trigger, both blueprints recompute whether the lights should be on. The triggers are presence and motion changes, lux changes, `homeassistant: start`, `automation_reloaded`, the night-window edges and the 5-minute tick. The tick may switch lights off, never on. Everything stays inside the blueprint: no helpers. |
| D4 | **Living room brightness:** off when lux stays above 250 lx for 10 min, on when it stays below 175 lx for 5 min. Re-check against spring data in April 2027 (follow-up F1 in the ledger). |
| D4a | **27 Nov 2026, Martin: lowered to 70 / 125 lx** (same 5 / 10 min waits). Live on 27 Nov the room looked bright while the FP2 read only 65-80 lx of daylight at 13:30 (90-105 with the lamps on), so 175 kept the lights on. Simulated on 16-26 Nov: lights off 0.5-5.1 h a day between 09:00 and 17:00, usually 2 switches a day, some days 4-6. The 55 lx gap stays above the lamps' 25-45 lx. |
| D5 | **Adjacent rooms:** the same re-check logic and daylight off wherever an instance sets `illuminance_entity`. Today that is only the front hall (see D17). Kitchen and toilet are unchanged. |
| D6 | **Manual colour or brightness change:** updates to that light pause until the next profile boundary or until the room is empty. All five rooms. |
| D7 | **One rhythm:** settings stay in each instance, and a repo test fails when the shared rhythm inputs differ. The living room's values win: dinner 17:45 at 2300 K / 90 %, toddler 18:45 at 2100 K / 85 %, evening 20:00 at 2000 K / 70 %, night 23:30 at 2000 K / 29 %, min/max 2000/4000 K. Ceiling scale and effects stay living-room only. |
| D8 | The attic joins the shared rhythm, and the 2000 K skip gets fixed. |
| D9 | **Night window (01:00-06:00):** the FP300 is ignored completely. It can't turn the lights on or hold them on; the FP2 alone decides. A re-check at window start turns off lights that only the FP300 is holding. |
| D10 | **Dim warning in the window:** before turning off, the lights dim and stay dimmed for 1 min, and any FP2 presence restores them. |
| D11 | The window has its own two time inputs (defaults 01:00 and 06:00). The existing 23:00-06:30 short-timeout window is unchanged. |
| D12 | **Manual off:** the lights stay off until the room has been empty for the timeout. All five rooms (D13). |
| D13 | D6 and D12 apply to all five rooms. |
| D14 | The adjacent blueprint alerts through an HA persistent notification, not a phone push. |
| D15 | There is no cap on FP300-only presence outside the night window. |
| D16 | Delivery: this RFC plus a job ledger. Each job has its own branch, tests first, and a Codex review with P0 and P1 fixed. Every merge, push and HA deploy needs Martin's OK. |

**Decided by orchestrator** (Martin can revert any of these):
- **D17, front hall thresholds:** off above **220 lx held 10 min**, on below **150 lx** (unchanged), with 5 min added for the on side too. Reason: the lamp lifts a 150 lx reading to about 175-205 lx, which stays under 220, and middays reach 220 on 6 of 11 days.
- **D18, dim level:** the D10 dim goes to 30 % *of the current brightness*, at least 1 %. Night brightness is already 29 %, so a fixed "dim to 30 %" would not dim anything.
- **D19, how the dim works:** two stateless triggers instead of a delay. FP2 clear for `late_night_timeout` triggers the dim, and FP2 clear for `late_night_timeout` + 1 min triggers off. Under `mode: restart` the 5-minute tick would otherwise cancel a running delay and leave the lights dimmed.
- **D20, detecting manual changes (D6/D12) without a helper:**
  - **Manual colour or brightness:** if a lit light differs from the current profile target by more than a tolerance (about 150 K or 5 % brightness), it counts as manual and the tick skips it. A profile-boundary trigger re-applies the colour and brightness regardless.
  - **Manual off:** lights that are off, in an occupied room, and switched off after the room last became occupied count as manual. The lux and tick paths won't turn them back on; only a fresh empty-to-occupied change will.
  - **Fallback:** if J4 finds this unreliable, for example because Hue rounding or day-mode kelvin drift exceed the tolerance, it stops and asks Martin about adding an `input_boolean` per room.
- **D21, versions:** a minor bump per job instead of one big number. Living room v3.1.0, v3.2.0 and v3.3.0 for J2-J4; adjacent v2.1.0 for J5. Instance aliases are updated with each deploy.

## 5. Jobs

Each job runs on branch `lighting-2026-11/<id>`. Tests come first in `tests/` and run with `./blueprints-tests/bin/python -m pytest tests -q`. Each job also:
- updates `requirements_circadian.md` and the README section for the blueprint it touches;
- runs a dry run through `scripts/deploy-blueprint.sh --dry-run`;
- gets a Codex review, with P0 and P1 fixed;
- runs the full suite, then waits for Martin's OK before merging to local main, and again for the HA deploy.

After each deploy, a live check confirms the automation is `on`, and the relevant behaviour is watched in the history.

| Job | What | Depends on |
| --- | --- | --- |
| S0 | Add this RFC and the ledger to `docs/design/`, and commit the X0 deploy JSON and backup | — |
| J1 | **Drift test and deploy checks.** Add the D7 drift test over the active `deploy/*.json`. Align the kitchen, hall, toilet and attic instances to the living room values (D7/D8). Make `deploy-blueprint.sh` refuse instance entities that don't exist (D2). Deploy the instances only. | S0 |
| J2 | **Living room v3.1.0.** The re-check on every trigger (D3). Missing or dead sensors count as clear, with a de-duplicated push (D2), which reverses the test at `:244`. Lux 250/175 with 10/5 min waits (D4). Remove the `on + 300` guard. Lux decisions are skipped when there is no lux reading. | J1 |
| J3 | **Living room v3.2.0.** The night window inputs and FP300 ignore (D9/D11), and the dim then off using D18/D19. Re-check at the window edges. | J2 |
| J4 | **Living room v3.3.0.** Manual colour or brightness pause, and manual off respected (D6/D12/D20). | J2 |
| J5 | **Adjacent v2.1.0.** Mirror J2 and J4 (D3/D2/D13), with a persistent-notification alert (D14). Daylight off where lux is set, with the hall at D17. Fix the 2000 K skip (D8). Remove or wire `lux_off_duration`. Extend the drift test to check both blueprints share the same mode and kelvin formulas. | J2, J4 |

J3 and J4 both edit `circadian_livingroom.yaml`, so they run one after the other, not in parallel.

## 6. Risks

- **Re-checking on every lux report** means many short runs, with a median gap of 44 s. That is acceptable because no run contains a delay after D19. Check it in the automation traces after J2.
- **Detecting manual changes (D20)** is the least certain part, and the fallback is a helper.
- **Flicker on cloudy summer days** at 250/175 is unverified (follow-up F1).
- **The FP2 can still see the dog when she moves.** The night window removes the FP300's long holds, not the FP2's short events. A dog walking through still switches the lights on for about 1 min plus the dim.
