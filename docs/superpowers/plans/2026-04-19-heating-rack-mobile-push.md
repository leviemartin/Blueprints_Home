# Heating Rack Blueprint — Mobile Push (v1.1.0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in mobile push notifications to the `bathroom_heating_rack.yaml` blueprint by introducing a `notify_targets` multi-select input and fanning it out to three action-site push events, shipping as v1.1.0.

**Architecture:** Pure YAML blueprint edits — one new input, one new variable, three inline `repeat.for_each` fan-out blocks placed adjacent to the existing `persistent_notification.create` steps in the action `choose` tree, plus a version-string bump. No new files, no Python, no tests-as-code. Validation is done with an `!input`-aware Python YAML safe loader; behavior is verified live in Home Assistant after reimport.

**Tech Stack:** Home Assistant Blueprints (YAML + Jinja2), HA Companion mobile app (`notify.mobile_app_*` services), `hass-cli` for live triggers, Python 3 with PyYAML for load validation.

**Spec reference:** `docs/superpowers/specs/2026-04-19-heating-rack-mobile-push.md` (commits `4c0293d` + `fadb57d` + `0ca5acd`).

---

## Files

- **Modify:** `bathroom_heating_rack.yaml` — add `notify_targets` input (~line 233), add `notify_targets` variable (~line 262), add fan-out to `climate_unavailable` branch (~line 491), add fan-out to `sensor_warning` branch (~line 507), add fan-out to `warmup_started` branch (~line 617), bump version string in `name:` (line 2) and `**Version:**` prefix in `description:` (line 4).
- **Modify:** `requirements_bathroom_heating_rack.md` — add a `## Mobile Push Notifications` section after the `## Testing & Debugging` section.
- **Modify:** `README.md` — add a `📱 Mobile Push` bullet to the Bathroom Heating Rack `### Features` list (around line 117–118).
- **Read-only reference:** `docs/superpowers/specs/2026-04-19-heating-rack-mobile-push.md`.

Note on line numbers: every anchor in this plan is given as an exact `old_string` for the Edit tool. Line numbers are v1.0.5 baseline and drift after each edit — rely on the string match, not the line numbers.

---

## Task 1: Baseline YAML validation

**Why:** Prove the `!input`-aware loader works on the untouched v1.0.5 file before we start editing. If this fails, the fault is in the loader and we fix it before touching the blueprint.

**Files:** None modified.

- [ ] **Step 1.1: Run the baseline validator**

From the repo root:

```bash
python3 -c "
import yaml
class L(yaml.SafeLoader): pass
def p(l,t,n):
    if isinstance(n,yaml.ScalarNode): return l.construct_scalar(n)
    if isinstance(n,yaml.SequenceNode): return l.construct_sequence(n)
    return l.construct_mapping(n)
L.add_multi_constructor('!',p); L.add_multi_constructor('tag:',p)
with open('bathroom_heating_rack.yaml') as f: yaml.load(f, Loader=L)
print('OK')"
```

Expected output: `OK`

If you see anything other than `OK`, stop and investigate. Do not proceed.

---

## Task 2: Add the `notify_targets` input

**Why:** Introduce the user-facing input the UI will render. Placed adjacent to `enable_notifications` so both notification-related inputs sit together.

**Files:** Modify `bathroom_heating_rack.yaml`.

- [ ] **Step 2.1: Add the new input**

Use Edit on `bathroom_heating_rack.yaml`:

- `old_string`:
```
    enable_notifications:
      name: Enable Persistent Notifications
      default: true
      selector: {boolean: {}}

mode: restart
```

- `new_string`:
```
    enable_notifications:
      name: Enable Persistent Notifications
      default: true
      selector: {boolean: {}}
    notify_targets:
      name: Mobile Push Targets
      description: >-
        List of notify services to push high-priority events to. Enter the
        full service name including the `notify.` prefix (e.g.,
        notify.mobile_app_martin). Leave empty to disable push. Events that
        push: climate unavailable, sensor warning, warmup started.
      default: []
      selector:
        text:
          multiple: true

mode: restart
```

- [ ] **Step 2.2: Validate YAML still loads**

```bash
python3 -c "
import yaml
class L(yaml.SafeLoader): pass
def p(l,t,n):
    if isinstance(n,yaml.ScalarNode): return l.construct_scalar(n)
    if isinstance(n,yaml.SequenceNode): return l.construct_sequence(n)
    return l.construct_mapping(n)
L.add_multi_constructor('!',p); L.add_multi_constructor('tag:',p)
with open('bathroom_heating_rack.yaml') as f: yaml.load(f, Loader=L)
print('OK')"
```

Expected output: `OK`

---

## Task 3: Add the `notify_targets` variable

**Why:** Surface the input into the action scope so `{{ notify_targets }}` resolves in the fan-out blocks below. Placed immediately below `enable_notifications` in the `variables:` section for grouping.

**Files:** Modify `bathroom_heating_rack.yaml`.

- [ ] **Step 3.1: Add the variable line**

Use Edit on `bathroom_heating_rack.yaml`:

- `old_string`:
```
  enable_predictive_motion: !input enable_predictive_motion
  enable_notifications: !input enable_notifications
```

- `new_string`:
```
  enable_predictive_motion: !input enable_predictive_motion
  enable_notifications: !input enable_notifications
  notify_targets: !input notify_targets
```

- [ ] **Step 3.2: Validate YAML still loads**

Same command as Step 2.2. Expect `OK`.

---

## Task 4: Add fan-out to `climate_unavailable` branch

**Why:** This is the hard-error branch. The push must fire before the `- stop:` step — if placed after, it is unreachable. See spec D4.

**Files:** Modify `bathroom_heating_rack.yaml`.

- [ ] **Step 4.1: Insert the fan-out between `persistent_notification.create` and `stop:`**

Use Edit on `bathroom_heating_rack.yaml`:

- `old_string`:
```
        sequence:
          - service: persistent_notification.create
            data:
              title: "Heating Rack — Climate Unavailable"
              message: >
                {{ entity_climate }} is {{ states(entity_climate) }}.
                Holding current state.
              notification_id: "heating_rack_climate_unavailable"
          - stop: "Climate entity unavailable"
```

- `new_string`:
```
        sequence:
          - service: persistent_notification.create
            data:
              title: "Heating Rack — Climate Unavailable"
              message: >
                {{ entity_climate }} is {{ states(entity_climate) }}.
                Holding current state.
              notification_id: "heating_rack_climate_unavailable"
          - repeat:
              for_each: "{{ notify_targets }}"
              sequence:
                - service: "{{ repeat.item }}"
                  data:
                    title: "Heating Rack — Climate Unavailable"
                    message: >-
                      {{ entity_climate }} is {{ states(entity_climate) }}.
                      Holding current state.
          - stop: "Climate entity unavailable"
```

- [ ] **Step 4.2: Validate YAML still loads**

Same command as Step 2.2. Expect `OK`.

---

## Task 5: Add fan-out to `sensor_warning` branch

**Why:** This branch has no `- stop:` — flow continues to STEP 3 afterwards. Fan-out placed immediately after the `persistent_notification.create` step.

**Files:** Modify `bathroom_heating_rack.yaml`.

- [ ] **Step 5.1: Insert the fan-out after `persistent_notification.create`**

Use Edit on `bathroom_heating_rack.yaml`:

- `old_string`:
```
        sequence:
          - service: persistent_notification.create
            data:
              title: "Heating Rack — Temperature Sensor Warning"
              message: >
                Both {{ sensor_bathroom_temp }} and
                {{ entity_climate }}.current_temperature are unavailable.
                Warmup formula is using 20°C as a fallback — ΔT-based
                lead time will be inaccurate until a sensor returns.
              notification_id: "heating_rack_sensor_warning"
```

- `new_string`:
```
        sequence:
          - service: persistent_notification.create
            data:
              title: "Heating Rack — Temperature Sensor Warning"
              message: >
                Both {{ sensor_bathroom_temp }} and
                {{ entity_climate }}.current_temperature are unavailable.
                Warmup formula is using 20°C as a fallback — ΔT-based
                lead time will be inaccurate until a sensor returns.
              notification_id: "heating_rack_sensor_warning"
          - repeat:
              for_each: "{{ notify_targets }}"
              sequence:
                - service: "{{ repeat.item }}"
                  data:
                    title: "Heating Rack — Temperature Sensor Warning"
                    message: >-
                      Both {{ sensor_bathroom_temp }} and
                      {{ entity_climate }}.current_temperature are
                      unavailable. Warmup using 20°C fallback — ETA
                      inaccurate until a sensor returns.
```

- [ ] **Step 5.2: Validate YAML still loads**

Same command as Step 2.2. Expect `OK`.

---

## Task 6: Add fan-out to `warmup_started` branch

**Why:** The push template references `{{ eta_min }}`, which is defined in the nested `- variables:` block immediately above the `persistent_notification.create`. Fan-out MUST stay below that variables block so `eta_min` is in scope.

**Files:** Modify `bathroom_heating_rack.yaml`.

- [ ] **Step 6.1: Insert the fan-out after `persistent_notification.create`**

Use Edit on `bathroom_heating_rack.yaml`:

- `old_string`:
```
          - service: persistent_notification.create
            data:
              title: "Heating Rack — Warmup Started"
              message: >
                Priority: {{ active_priority }}.
                Current {{ indoor_temp | round(1) }}°C → target
                {{ desired_setpoint }}°C. ETA ~{{ eta_min }} min.
              notification_id: "heating_rack_warmup_started"
```

- `new_string`:
```
          - service: persistent_notification.create
            data:
              title: "Heating Rack — Warmup Started"
              message: >
                Priority: {{ active_priority }}.
                Current {{ indoor_temp | round(1) }}°C → target
                {{ desired_setpoint }}°C. ETA ~{{ eta_min }} min.
              notification_id: "heating_rack_warmup_started"
          - repeat:
              for_each: "{{ notify_targets }}"
              sequence:
                - service: "{{ repeat.item }}"
                  data:
                    title: "Heating Rack — Warmup Started"
                    message: >-
                      {{ active_priority }}: {{ indoor_temp | round(1) }}°C
                      → {{ desired_setpoint }}°C. ETA ~{{ eta_min }} min.
```

- [ ] **Step 6.2: Validate YAML still loads**

Same command as Step 2.2. Expect `OK`.

---

## Task 7: Bump version strings

**Why:** User-visible version in the HA UI and changelog blurb in the description. Bump from `1.0.5` to `1.1.0`.

**Files:** Modify `bathroom_heating_rack.yaml`.

- [ ] **Step 7.1: Update the `name:` field**

Use Edit on `bathroom_heating_rack.yaml`:

- `old_string`:
```
  name: "Bathroom Heating Rack v1.0.5"
```

- `new_string`:
```
  name: "Bathroom Heating Rack v1.1.0"
```

- [ ] **Step 7.2: Update the `description:` version prefix**

Use Edit on `bathroom_heating_rack.yaml`:

- `old_string`:
```
    **Version: 1.0.5** — P6 idle and P2 fan-pause now drive setpoint to a configurable idle_setpoint (default 7°C) so the heater does not continue warming the room at the last active-routine setpoint (energy waste bug). v1.0.4 normalised 'unknown'→'heat_cool' to stop per-tick beeping. v1.0.3 stopped blocking on state='unknown'. v1.0.2 skipped set_preset_mode for integrations that reject 'none'. v1.0.1 fixed datetime arithmetic via as_datetime().
```

- `new_string`:
```
    **Version: 1.1.0** — Adds opt-in mobile push via the new `notify_targets` multi-select input. Push fires for three events: climate unavailable, sensor warning, and warmup started; the other two events (target reached, debug) stay persistent-notification-only. Empty `notify_targets` disables push entirely — existing deployments see no behavior change until the input is populated. v1.0.5 drove idle/pause setpoint to `idle_setpoint` (default 7°C) so the heater stops warming during idle. v1.0.4 normalised 'unknown'→'heat_cool' to stop per-tick beeping. v1.0.3 stopped blocking on state='unknown'. v1.0.2 skipped set_preset_mode for integrations that reject 'none'. v1.0.1 fixed datetime arithmetic via as_datetime().
```

- [ ] **Step 7.3: Validate YAML still loads**

Same command as Step 2.2. Expect `OK`.

---

## Task 8: Commit the blueprint YAML

**Why:** All blueprint edits are complete and the loader is happy. Capture them in one focused commit so `git revert` is a clean rollback if the live test later exposes a problem.

**Files:** Commit `bathroom_heating_rack.yaml`.

- [ ] **Step 8.1: Stage and commit**

```bash
git add bathroom_heating_rack.yaml && git commit -m "$(cat <<'EOF'
feat(heating-rack): add notify_targets input and push fan-out (v1.1.0)

Adds opt-in mobile push notifications via a new multi-select
`notify_targets` input. The blueprint fans out to every target in the
list for three events — climate_unavailable, sensor_warning, and
warmup_started — at the three existing persistent-notification sites.
target_reached and debug remain persistent-only.

Fan-out placement is load-bearing:
- climate_unavailable: between persistent_notification.create and the
  trailing `- stop:` so the push fires before the hard stop
- warmup_started: below the nested `- variables: eta_min:` block so the
  push template can reference eta_min

Default is empty list → zero behavior change for existing deployments
until the input is populated.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 8.2: Verify the commit landed**

```bash
git log --oneline -1
```

Expected: the commit you just made is at HEAD.

---

## Task 9: Document the feature in the requirements doc

**Why:** `requirements_bathroom_heating_rack.md` is the functional-requirements reference. Add a Mobile Push Notifications section so the feature is discoverable from the spec lineage.

**Files:** Modify `requirements_bathroom_heating_rack.md`.

- [ ] **Step 9.1: Add the Mobile Push Notifications section**

Use Edit on `requirements_bathroom_heating_rack.md`:

- `old_string`:
```
## Testing & Debugging
Manual "Run" in HA produces a persistent notification dumping all computed variables (indoor temp, ΔT, warmup_min, each slot's auto_start / effective_start / active flags, current priority winner, service-call decisions).
```

- `new_string`:
```
## Testing & Debugging
Manual "Run" in HA produces a persistent notification dumping all computed variables (indoor temp, ΔT, warmup_min, each slot's auto_start / effective_start / active flags, current priority winner, service-call decisions).

## Mobile Push Notifications (v1.1.0+)

In addition to the persistent notifications always shown inside Home Assistant, the blueprint can fan out a subset of events to any number of HA Companion `notify.mobile_app_*` services (or other `notify.*` services) via the `notify_targets` multi-select input.

**Input:** `notify_targets` — list of full notify service names (e.g. `notify.mobile_app_martin`). Default is empty (push disabled).

**Events that push** (when `notify_targets` is non-empty):
1. **Climate unavailable** — hard error, automation halts. Fires unconditionally.
2. **Temperature sensor warning** — both primary sensor and `climate.current_temperature` unavailable; warmup formula falls back to 20°C and lead time becomes inaccurate.
3. **Warmup started** — transition into an active routine (P3 boost / P4 evening / P5 morning). Gated by the existing `enable_notifications` input.

**Events that do NOT push** (stay persistent-notification-only):
- Target reached — fires on many consecutive minute ticks while within 0.5°C of setpoint; pushing would be spam.
- Debug (manual-run dump) — only fires on a manual `automation.trigger` call, when the user is already at the HA UI.

**Failure isolation:** if a single target in the list is mistyped or its device is logged out, that iteration errors in the automation trace but the remaining targets still receive the push and the automation does not halt.
```

- [ ] **Step 9.2: Commit the requirements update**

```bash
git add requirements_bathroom_heating_rack.md && git commit -m "$(cat <<'EOF'
docs(heating-rack): document mobile push in requirements

Adds a Mobile Push Notifications section describing the new
notify_targets input, which events push vs. stay persistent-only, and
the failure-isolation guarantee for bad targets.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Add a push bullet to the README

**Why:** The README's Bathroom Heating Rack `### Features` list is the user-facing advertisement. Add a one-line bullet so users browsing the repo see push notifications as a listed feature.

**Files:** Modify `README.md`.

- [ ] **Step 10.1: Insert a push bullet into the Features list**

Use Edit on `README.md`:

- `old_string`:
```
*   **🔍 Debug-Friendly:** Manual "Run" produces a persistent notification dumping all computed state (ΔT, warmup, each slot's auto_start / effective_start / active flags, winning priority).

### Requirements
```

- `new_string`:
```
*   **🔍 Debug-Friendly:** Manual "Run" produces a persistent notification dumping all computed state (ΔT, warmup, each slot's auto_start / effective_start / active flags, winning priority).
*   **📱 Mobile Push (v1.1.0+):** Opt-in push notifications via HA Companion (`notify.mobile_app_*`) for three high-signal events — climate unavailable, temperature-sensor warning, and warmup started. Multi-target fan-out; empty list disables push. Per-user opt-in via the `Mobile Push Targets` input; all five in-HA persistent notifications still fire.

### Requirements
```

- [ ] **Step 10.2: Commit the README update**

```bash
git add README.md && git commit -m "$(cat <<'EOF'
docs(heating-rack): note mobile push feature in README

Adds a one-line Features bullet advertising the v1.1.0 opt-in push
layer. In-repo README is the surface users browse first.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Push to GitHub

**Why:** The spec's goal is to ship v1.1.0 live on `main`. Users import from the raw GitHub URL, so nothing is "shipped" until it's pushed.

**Files:** None modified; git state only.

- [ ] **Step 11.1: Push the three new commits**

```bash
git push origin main
```

- [ ] **Step 11.2: Verify remote is up-to-date**

```bash
git log --oneline origin/main -5
```

Expected: the three new commits (`feat(heating-rack): add notify_targets...`, `docs(heating-rack): document mobile push...`, `docs(heating-rack): note mobile push feature...`) are at the top.

---

## Task 12: Reimport the blueprint in HA and restart Home Assistant

**Why:** HA caches blueprints aggressively; logic changes do not take effect until the YAML is reimported AND Home Assistant is restarted (project convention, see `CLAUDE.md`). The existing automation instance `automation.bathroom_heating_rack_v1_0_0` survives — it inherits the new `notify_targets` input at its default (empty list), so behavior is initially unchanged.

**Files:** None modified; Home Assistant UI action + service call.

- [ ] **Step 12.1: Reimport the blueprint**

In the HA UI: **Settings → Automations & Scenes → Blueprints → (⋮ menu on `Bathroom Heating Rack v1.0.5`) → Re-import blueprint**. Confirm the version label in the list updates to `v1.1.0`.

- [ ] **Step 12.2: Restart Home Assistant**

```bash
hass-cli service call homeassistant.restart
```

Then wait for HA to come back up (ping `hass-cli state get climate.heatingrack_bathroom` until it returns without a connection error).

- [ ] **Step 12.3: Confirm the automation survived**

```bash
hass-cli --output json state get automation.bathroom_heating_rack_v1_0_0 | python3 -c "import json,sys; s=json.load(sys.stdin)[0]; print(f\"state={s['state']}, last_triggered={s['attributes'].get('last_triggered')}\")"
```

Expected: `state=on` (the automation is enabled). `last_triggered` is informational.

---

## Task 13: Live test — default-empty sanity

**Why:** The new input defaults to empty. Verify zero-push + existing persistent behavior is unchanged before touching any inputs.

- [ ] **Step 13.1: Manually trigger the automation**

```bash
hass-cli service call automation.trigger --arguments entity_id=automation.bathroom_heating_rack_v1_0_0
```

- [ ] **Step 13.2: Verify the debug persistent_notification appeared**

```bash
python3 - <<'PY'
import websocket, json, os
t = os.environ['HASS_TOKEN']
ws = websocket.create_connection('ws://homeassistant.local:8123/api/websocket', timeout=10)
ws.recv(); ws.send(json.dumps({'type':'auth','access_token':t})); ws.recv()
ws.send(json.dumps({'id':1,'type':'persistent_notification/get'}))
for n in json.loads(ws.recv()).get('result',[]):
    if 'heating_rack_debug' in n.get('notification_id',''):
        print(f"[{n.get('notification_id')}] {n.get('title')}")
ws.close()
PY
```

Expected: one line showing the heating_rack_debug notification with the current timestamp. No phone push received on any device.

- [ ] **Step 13.3: Verify the trace has no error**

```bash
python3 - <<'PY'
import websocket, json, os
t = os.environ['HASS_TOKEN']
ws = websocket.create_connection('ws://homeassistant.local:8123/api/websocket', timeout=10)
ws.recv(); ws.send(json.dumps({'type':'auth','access_token':t})); ws.recv()
ws.send(json.dumps({'id':1,'type':'trace/list','domain':'automation','item_id':'1776551429917'}))
for tr in json.loads(ws.recv()).get('result',[])[-1:]:
    print(f"{tr.get('timestamp',{}).get('start','')} err={tr.get('error') or 'OK'}")
ws.close()
PY
```

Expected: the most recent trace timestamp is within the last minute, and `err=OK`.

---

## Task 14: Live test — single target, warmup push

**Why:** Real end-to-end verification that push reaches the user's phone via `notify.mobile_app_martin` on a real routine transition.

- [ ] **Step 14.1: Populate `notify_targets` in the HA UI**

In the HA UI: **Settings → Automations & Scenes → `Bathroom Heating Rack v1.1.0` automation → Edit**. In the `Mobile Push Targets` field, add `notify.mobile_app_martin` (as a single entry in the growable list). Save.

- [ ] **Step 14.2: Confirm `debug` still stays persistent-only with targets populated**

This is the D2-correctness check: spec contract says `debug` is persistent-notification-only, even when `notify_targets` is non-empty. A manual trigger is the only way to exercise the `debug` branch.

```bash
hass-cli service call automation.trigger --arguments entity_id=automation.bathroom_heating_rack_v1_0_0
```

Check your phone for the next 30 seconds.

Expected: **no push arrives**. Then verify the persistent debug notification did fire:

```bash
python3 - <<'PY'
import websocket, json, os
t = os.environ['HASS_TOKEN']
ws = websocket.create_connection('ws://homeassistant.local:8123/api/websocket', timeout=10)
ws.recv(); ws.send(json.dumps({'type':'auth','access_token':t})); ws.recv()
ws.send(json.dumps({'id':1,'type':'persistent_notification/get'}))
for n in json.loads(ws.recv()).get('result',[]):
    if 'heating_rack_debug' in n.get('notification_id',''):
        print(f"[{n.get('notification_id')}] {n.get('title')}")
ws.close()
PY
```

Expected: one line showing the heating_rack_debug notification with a very recent timestamp. If a push *did* arrive, the fan-out was misplaced under the debug branch — stop and investigate before proceeding.

- [ ] **Step 14.3: Force a warmup by setting Morning A time to ~2 minutes from now**

In the same automation edit view, set `morning_a_target_warm` time to `(current HH:MM + 2min)` and ensure today's weekday is in `morning_a_days`. Save. Note down the original values so you can restore them after the test.

- [ ] **Step 14.4: Wait 2–3 minutes, then check your phone**

Expected on the phone: one push notification titled `Heating Rack — Warmup Started` with a body like `P5_morning: 17.8°C → 23°C. ETA ~12 min.`

Expected in HA: a persistent_notification with the same title also appears.

- [ ] **Step 14.5: Check the trace confirms the repeat iterated once with no error**

```bash
python3 - <<'PY'
import websocket, json, os
t = os.environ['HASS_TOKEN']
ws = websocket.create_connection('ws://homeassistant.local:8123/api/websocket', timeout=10)
ws.recv(); ws.send(json.dumps({'type':'auth','access_token':t})); ws.recv()
ws.send(json.dumps({'id':1,'type':'trace/list','domain':'automation','item_id':'1776551429917'}))
for tr in json.loads(ws.recv()).get('result',[])[-3:]:
    print(f"{tr.get('timestamp',{}).get('start','')} err={tr.get('error') or 'OK'}")
ws.close()
PY
```

Expected: recent traces all show `err=OK`.

- [ ] **Step 14.6: Restore the original `morning_a_target_warm` and `morning_a_days` values**

In the HA UI, revert the two fields you changed in Step 14.2. Save.

---

## Task 15: Live test — two-target fan-out

**Why:** Verify the `repeat.for_each` loop delivers to every target, not just the first.

- [ ] **Step 15.1: Add a second target**

In the HA UI automation edit view, add `notify.mobile_app_pixel_9_pro_xl` to the `Mobile Push Targets` list (alongside `notify.mobile_app_martin`). Save.

- [ ] **Step 15.2: Force another warmup (same method as Step 14.3)**

Set `morning_a_target_warm` to ~2 min from now, ensure today is in `morning_a_days`, save.

- [ ] **Step 15.3: Verify both devices received the push**

Check both phones within 2–3 minutes of the configured time.

Expected: both devices show the `Heating Rack — Warmup Started` notification.

- [ ] **Step 15.4: Restore the `morning_a_target_warm` time**

Revert `morning_a_target_warm` to its original value.

---

## Task 16: Live test — failure isolation

**Why:** Spec claim: a single bad target does not suppress good targets or halt the automation. Must be verified live.

- [ ] **Step 16.1: Add a deliberately-bad target**

In the HA UI automation edit view, add `notify.mobile_app_does_not_exist` to `Mobile Push Targets` alongside the two good ones. Save.

- [ ] **Step 16.2: Force another warmup (same method)**

- [ ] **Step 16.3: Verify the two good devices still got the push**

Check both phones.

Expected: both good devices show the notification.

- [ ] **Step 16.4: Verify the trace shows an error for the bad target but the automation completed**

```bash
python3 - <<'PY'
import websocket, json, os
t = os.environ['HASS_TOKEN']
ws = websocket.create_connection('ws://homeassistant.local:8123/api/websocket', timeout=10)
ws.recv(); ws.send(json.dumps({'type':'auth','access_token':t})); ws.recv()
ws.send(json.dumps({'id':1,'type':'trace/list','domain':'automation','item_id':'1776551429917'}))
for tr in json.loads(ws.recv()).get('result',[])[-3:]:
    print(f"{tr.get('timestamp',{}).get('start','')} err={tr.get('error') or 'OK'}")
ws.close()
PY
```

Expected: the automation's top-level `err=OK` (the per-target error is logged inside the trace detail, not at the top level — HA does not surface inner-repeat errors as the automation's error). If you want to inspect the detail, the HA UI's automation trace inspector under the most recent run will show the failed service call inside the repeat branch.

- [ ] **Step 16.5: Remove the bad target**

In the HA UI, remove `notify.mobile_app_does_not_exist` from the list. Save.

---

## Task 17: Live test — sensor warning push

**Why:** Exercise the `sensor_warning` push path, which fires unconditionally (no `enable_notifications` gate) when both the primary temp sensor AND the climate.current_temperature are unavailable.

**Note:** This path is low-probability in normal operation. If reproducing it is hard (e.g., sensors are reliably up), skip this task and accept the unit-level verification from Task 1's YAML load.

- [ ] **Step 17.1: Point `bathroom_temp_sensor` at a non-existent entity**

In the HA UI automation edit view, change `bathroom_temp_sensor` to `sensor.nonexistent_test_sensor`. Save.

- [ ] **Step 17.2: Manually trigger the automation**

```bash
hass-cli service call automation.trigger --arguments entity_id=automation.bathroom_heating_rack_v1_0_0
```

- [ ] **Step 17.3: Verify the sensor_warning push arrived**

Check your phone.

Expected: a notification titled `Heating Rack — Temperature Sensor Warning`.

Note: this path only fires when BOTH the configured sensor AND `climate.current_temperature` are unavailable. `climate.heatingrack_bathroom.current_temperature` currently reports a real reading (`20.6°C` at session start), so the sensor_warning condition may not actually fire even with a bad primary sensor. If no push arrives, check the HA UI automation trace to confirm which branch ran.

- [ ] **Step 17.4: Restore `bathroom_temp_sensor`**

In the HA UI, revert `bathroom_temp_sensor` to `sensor.bathroom_temperature`. Save.

---

## Task 18: Live test — final state check

**Why:** After all inputs-fiddling tests, confirm the automation is back to its production configuration and the climate entity is in its expected idle state.

- [ ] **Step 18.1: Confirm the climate entity is idle**

```bash
hass-cli --output json state get climate.heatingrack_bathroom | python3 -c "import json,sys;d=json.load(sys.stdin)[0];print(f\"state={d['state']}, setpoint={d['attributes'].get('temperature')}, preset={d['attributes'].get('preset_mode')}, current_temp={d['attributes'].get('current_temperature')}\")"
```

Expected: `setpoint=7.0` (idle_setpoint), `preset=eco`, `state=unknown` (normal for Tuya), and the heater not actively heating (current_temp > setpoint).

- [ ] **Step 18.2: Confirm the automation has the expected targets and restored inputs**

In the HA UI automation edit view, verify:
- `notify_targets` contains the real production targets (leave whichever you want in production — recommended: just `notify.mobile_app_martin`).
- `morning_a_target_warm`, `morning_a_days`, and `bathroom_temp_sensor` match their pre-test values.

- [ ] **Step 18.3: Watch the next minute-tick trace to confirm zero errors**

```bash
python3 - <<'PY'
import websocket, json, os, time
t = os.environ['HASS_TOKEN']
ws = websocket.create_connection('ws://homeassistant.local:8123/api/websocket', timeout=10)
ws.recv(); ws.send(json.dumps({'type':'auth','access_token':t})); ws.recv()
ws.send(json.dumps({'id':1,'type':'trace/list','domain':'automation','item_id':'1776551429917'}))
for tr in json.loads(ws.recv()).get('result',[])[-3:]:
    print(f"{tr.get('timestamp',{}).get('start','')} err={tr.get('error') or 'OK'}")
ws.close()
PY
```

Expected: the three most-recent traces (each one-minute tick) all show `err=OK`.

---

## Task 19: Wrap

**Why:** Close the loop so the next session knows the feature is live and the Tuya beep-mute investigation is the next open work item.

- [ ] **Step 19.1: Append a session note**

Add a short section to `docs/superpowers/session-notes/2026-04-19-heating-rack-wrap.md` (or create a new `2026-04-19-v1.1.0-shipped.md` if preferred). One paragraph covering: v1.1.0 live, push verified on N devices, known-open item is Tuya beep-mute (LocalTuya investigation).

- [ ] **Step 19.2: Commit the note**

```bash
git add docs/superpowers/session-notes/ && git commit -m "$(cat <<'EOF'
docs(heating-rack): v1.1.0 shipped — push live, beep-mute next

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)" && git push origin main
```

---

## Rollback plan (if any live test fails)

No code rollback needed for runtime issues: clear `notify_targets` in the HA UI and push ceases immediately — the blueprint reverts to v1.0.5 behavior. If the blueprint YAML itself has a bug surfaced by live traces, `git revert <blueprint-commit>` then push, reimport, restart HA.

---

## Out of scope for v1.1.0 (do NOT implement)

- Actionable notification buttons (`[Cancel]`, `[Extend boost]`) — v1.2.0 candidate.
- Per-event target routing.
- Quiet-hours gating.
- User-customizable message templates.
- Tuya beep-mute (LocalTuya investigation) — separate workstream after this ships.
