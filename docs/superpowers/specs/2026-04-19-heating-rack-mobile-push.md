# Heating Rack Blueprint — Mobile Push Notifications (v1.1.0)

Spec date: 2026-04-19
Target blueprint: `bathroom_heating_rack.yaml`
Version bump: v1.0.5 → v1.1.0 (minor — additive, opt-in, zero default-behavior change)

## Background

The v1.0.5 blueprint emits five `persistent_notification.create` events for heating-rack lifecycle events. Persistent notifications appear in the Home Assistant dashboard only — the user receives no signal away from the HA web UI. The HA Companion app is installed on four devices, with corresponding `notify.mobile_app_*` services already discovered (`notify.mobile_app_martin` primary). This spec adds an opt-in push layer for high-signal events while preserving all existing persistent-notification behavior.

## Goals

1. Deliver away-from-HA visibility for the three high-signal events: hard errors, sensor warnings, and warmup starts.
2. Preserve full backward compatibility — existing deployments see zero behavior change until they populate the new input.
3. Keep the feature portable across HA installations (no hardcoded device-specific service names in the blueprint).
4. Fail gracefully when a user enters a bad service name — one bad target must not suppress notifications to the others or halt the automation.

## Non-goals (v1.1.0)

- Actionable notification buttons (e.g., "Cancel routine," "Extend boost"). Reserved for a future version once push-only usage is observed.
- Per-event target routing (e.g., "warnings go to partner's phone too"). Not justified by current event count.
- Quiet-hours logic.
- User-customizable message templates.
- Integration with non-HA-native push backends (Discord, ntfy, etc.).

## Design decisions

### D1. Fan-out shape: multi-select input

A single blueprint input `notify_targets` accepts a list of notify service names. The blueprint fans out to all targets on each push event. Rationale: all four mobile devices are already configured via the HA Companion app, and the multi-select costs only one `repeat.for_each` block per event — strictly cheaper than two parallel blueprint instances. Default is empty list (opt-in).

### D2. Event routing: hard-coded split

The five events are statically classified into push and persistent-only channels. No user-facing per-event toggle — the split reflects a principled signal/noise judgment and can be revised in a future minor bump if usage data warrants.

| Event | Persistent | Push |
|---|---|---|
| `climate_unavailable` | ✅ always | ✅ |
| `sensor_warning` | ✅ always | ✅ |
| `warmup_started` | ✅ gated¹ | ✅ |
| `target_reached` | ✅ gated¹ | ❌ |
| `debug` (manual-run dump) | ✅ gated¹ | ❌ |

¹ Gated by the existing `enable_notifications` input; see D3. Hard errors (`climate_unavailable`, `sensor_warning`) bypass the gate in v1.0.5 and continue to do so in v1.1.0.

Rationale: push is reserved for events the user would want to see on a locked phone. `target_reached` fires predictably every morning and would be spam. `debug` only fires during manual runs when the user is already at the HA UI.

### D3. Gating relationship to `enable_notifications`

The existing `enable_notifications` input keeps its current semantics (gates persistent-notification creation for the three gated events: warmup_started, target_reached, debug). The new `notify_targets` input is the push gate — an empty list disables all push, a non-empty list enables push for the three push-classified events regardless of the `enable_notifications` state.

This separation allows decluttering the HA dashboard (set `enable_notifications=false`) while still receiving phone pushes, or vice versa. Crucially, hard errors (`climate_unavailable`, `sensor_warning`) currently fire a persistent_notification unconditionally — they will continue to do so, and they additionally push when `notify_targets` is non-empty.

### D4. Implementation pattern: inline parallel fan-out

Each of the three push events gets an inline `repeat.for_each` block placed immediately after its existing `persistent_notification.create` step, inside the same `sequence`. No shared helper sub-sequences; no event-bus indirection. The three sites are:

- `heating_rack_climate_unavailable` (around YAML line 485)
- `heating_rack_sensor_warning` (around YAML line 499)
- `heating_rack_warmup_started` (around YAML line 610)

Rationale: fan-out is 4 YAML lines per event × 3 events = ~12 added lines total. Keeping the push call co-located with the triggering branch is more auditable than indirection through `event.fire` → handler automation. Abstraction cost is not justified at this event count and single push backend.

### D5. No actionable buttons in v1.1.0

Push messages are plain title/message pairs with no `actions` key. Rationale: the most plausible actionable (`Cancel` on warmup_started) would require inventing a per-routine skip mechanism not present in the current input schema. Shipping push-only first lets the user observe which events they actually want to react to from the lock screen. Actionables can be added in v1.2.0 once that signal exists.

## Schema changes

### New input

```yaml
notify_targets:
  name: Mobile Push Targets
  description: >-
    List of notify services to push high-priority events to (e.g.,
    notify.mobile_app_martin). Leave empty to disable push. Events that
    push: climate unavailable, sensor warning, warmup started.
  default: []
  selector:
    text:
      multiple: true
```

Selector choice: `text` + `multiple: true`. The HA UI renders a growable list of text entries. Selecting `text` over `select` keeps the blueprint portable (no hardcoded device-specific service names in the blueprint YAML).

### New variable

One line in the `variables:` block, mirroring the existing `!input` mappings:

```yaml
notify_targets: !input notify_targets
```

### Fan-out block (repeated at three sites)

```yaml
- condition: template
  value_template: "{{ notify_targets | count > 0 }}"
- repeat:
    for_each: "{{ notify_targets }}"
    sequence:
      - service: "{{ repeat.item }}"
        data:
          title: "<event-specific>"
          message: "<event-specific>"
```

The `condition: template` short-circuits the empty-list case so `repeat.for_each` does not iterate over nothing — cheap guard that also keeps automation traces clean.

### Push payloads

| Site | Title | Message |
|---|---|---|
| `climate_unavailable` | `Heating Rack — Unavailable` | `Climate entity {{ heating_climate }} is unavailable. Holding current state.` |
| `sensor_warning` | `Heating Rack — Sensor Warning` | `Bathroom temp sensor stale/missing. Lead time will be inaccurate until a sensor returns.` |
| `warmup_started` | `Heating Rack — Warmup Started` | `{{ active_priority }}: heating to {{ desired_setpoint }}°C. ETA ~{{ eta_min }} min.` |

Messages mirror the persistent-notification text but are trimmed to <120 chars for mobile notification-shade legibility. No emojis per project convention.

### Version bump

The blueprint `name:` header string (and any `description:` line that includes a version) updates from `v1.0.5` to `v1.1.0`.

## Failure modes

- **Empty `notify_targets`:** `condition: template` evaluates false; the repeat block is skipped. Zero service calls, zero trace noise. Default behavior.
- **One bad service name** (e.g., `notify.mobile_app_typo`): that iteration of `repeat.for_each` logs an error in the automation trace. Subsequent iterations proceed normally. Other configured targets still receive the push. Automation does not halt.
- **All service names bad:** every iteration errors, persistent_notification still fires (fan-out is after, not before, the persistent step). Automation completes.
- **HA Companion app logged out on a target device:** same as bad service name — error is logged in the trace, automation continues. User observes no push on that device until re-login.
- **Extreme list length (>20 targets):** no practical concern; four devices is the current ceiling. `repeat.for_each` is synchronous but the service calls are fire-and-forget at the HA level.

## Testing plan

1. **YAML load** — run the `!input`-aware safe loader from the handoff cheatsheet. Must print `OK`.
2. **Reimport in HA** — the blueprint definition updates; the existing automation instance (`automation.bathroom_heating_rack_v1_0_0`) survives.
3. **Default-empty sanity** — manually trigger via `hass-cli`; verify persistent debug notification appears, no push sent, no error in trace.
4. **Single-target smoke** — populate `notify_targets=[notify.mobile_app_martin]`; manually trigger. Phone receives nothing (debug is persistent-only), persistent debug still appears.
5. **Real push: warmup_started** — set `morning_a_time` to `now + 2 min` with today's weekday in `morning_a_days`; wait. Phone receives `Heating Rack — Warmup Started` push AND persistent_notification fires. Restore inputs.
6. **Fan-out: two targets** — add `notify.mobile_app_pixel_9_pro_xl`; repeat step 5; both devices receive the push.
7. **Failure isolation** — add `notify.mobile_app_does_not_exist` alongside martin; trigger warmup. Martin still gets the push; trace shows one error for the bad target; automation completes.
8. **Sensor warning path** — temporarily point `bathroom_temp_sensor` at a non-existent entity; trigger. `sensor_warning` push arrives on all targets.

## Files to modify

1. `bathroom_heating_rack.yaml` — new input block, new variable line, three fan-out blocks in the action `choose`, version string bump.
2. `requirements_bathroom_heating_rack.md` — new functional-requirements section describing the push layer, the target input, the event split, and the gating relationship to `enable_notifications`.
3. `README.md` — user-facing note under the heating-rack section: new input, what it does, which events push.
4. `docs/superpowers/specs/2026-04-19-heating-rack-mobile-push.md` — this spec.

## Commit strategy

Four commits on `main`, in order:

1. `feat(heating-rack): add notify_targets input and push fan-out (v1.1.0)` — blueprint YAML only
2. `docs(heating-rack): document mobile push in requirements` — requirements.md
3. `docs(heating-rack): note push notifications in README` — README.md
4. `docs(heating-rack): add v1.1.0 mobile push design spec` — this file

## Rollback

No code rollback required. User clears the `notify_targets` input via the HA UI and push ceases immediately — the blueprint reverts to v1.0.5 behavior. If the blueprint YAML itself needs to be reverted, `git revert` of commit 1 suffices; commits 2–4 are doc-only and harmless to leave in place.

## Out of scope (future versions)

- Actionable notification buttons — candidate for v1.2.0 once the reactive events list stabilizes.
- Per-event target routing (severity-based fan-out) — revisit if the event surface grows beyond ~8 events.
- Quiet-hours gating — revisit if any push proves time-sensitive enough to annoy the user at night.
- Tuya beep-mute via LocalTuya — tracked as a separate investigation stream after v1.1.0 ships.
