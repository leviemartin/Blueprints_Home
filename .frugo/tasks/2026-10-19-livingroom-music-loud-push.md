---
id: 2026-10-19-livingroom-music-loud-push
title: "Loud heads-up approval push"
goal: livingroom-background-music
issue: "leviemartin/Blueprints_Home#56"
status: done
lane: 2
coder: codex
step: codex
fix_rounds: 0
---

## Goal
Martin (2026-10-19, live walk-through): the Approve/Deny push for the kids' louder-music request arrived on his Fold but silent. Make it an audible, heads-up, high-priority alert on both phones. This is a data-only change to the two push actions in `script.livingroom_music_approval_request` in `ha/packages/livingroom_music.yaml`, plus test updates. Tag, title, message and action ids stay the same, and the `clear_notification` calls stay the same.

## Done when (runnable)
`env -u HASS_TOKEN ~/.local/share/home-security/ha-test-venv/bin/python -I -m pytest -q -p no:cacheprovider -c ha/tests/pytest-ha.ini ha/tests`
`env -u HASS_TOKEN ~/.local/share/home-security/ha-test-venv/bin/python -I -m pytest -q -p no:cacheprovider -c ha/tests/pytest-ha.ini ha/tests/test_ha_livingroom_music_core.py ha/tests/test_ha_livingroom_music_remote_volume.py ha/tests/test_ha_livingroom_music_remote_kids.py`
`env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests -q`

## Files likely touched
- `ha/packages/livingroom_music.yaml` (10 added lines, Plan step 1)
- `ha/tests/test_ha_livingroom_music_remote_kids.py` (one assert replaced, one new test, Plan step 2)
- `ha/tests/conftest.py`, other test modules: read only, unchanged

## Bad inputs to handle
- A failed or missing push (either phone) still denies and clears, unchanged (`test_notify_failure`, all four cases, must pass unchanged).
- The push holds no secret, token, URL or entity state: the exact `data` dict is asserted, so any extra key fails the test.
- Action ids are unchanged: `LRM_APPROVE_<context.id>` and `LRM_DENY_<context.id>`, button titles Approve and Deny.
- `clear_notification` stays `{message: clear_notification, data: {tag: livingroom_music_approval}}` with no channel, on both phones.
- No decimal number is added to the package: `test_volume_text_rules` fails on any float above 0.30, and `ttl: 0` and `timeout: 120` are integers.

## Risk flags
- Approval push: this push decides who may raise the volume; only its delivery style changes.
- deploy: out of scope; the live package changes only after a separate deploy with Martin's OK.
- workflow rules: Lane 2 for the goal.

## Constraints carried over
- Lane 2 for the whole goal; only Martin lowers a lane.
- Base: main (657a6c4 or later). Branch `frugo/2026-10-19-livingroom-music-loud-push`, worktree `Blueprints_Home-wt/lm-push` (the orchestrator creates them).
- Pushes go only to notify.mobile_app_martin_fold and notify.mobile_app_savannah_s25_ultra (the retired Pixel stays forbidden by conftest).
- Tests run with env -u HASS_TOKEN; tests hold no token and no URL. Changed tests live under ha/tests/.
- Budget: track only, warn line 500,000 tokens per card.

## Out of scope
- Volume logic, timers, helpers, the approval lifecycle, `script.livingroom_music_clear_pushes`.
- `channel: alarm_stream`, bypassing Do Not Disturb, `alert_once`, `sticky`, `vibrationPattern`, `ledColor`.
- Deploying to HA, reloading, any live call; the goal file (the orchestrator updates it at bookkeeping).

## Open questions
none

## Decided by orchestrator
- Martin, 2026-10-19 (live): the approval push must sound; this overrides the goal's out-of-scope line "Loud or DND push delivery" for loudness only, not for Do Not Disturb.
- Planner: a new channel `kids_music_approval` with `importance: high`. Companion docs (notifications-basic, "Notification Channels"): sending to a new channel name creates it; the channel's options "will be ignored once they are set for a particular channel" and "only lowering of the `importance` will work". So the existing General channel cannot be raised; a new name is needed. Accepted importance values: `high`, `low`, `max`, `min`, `default`. Android's IMPORTANCE_HIGH makes a sound and shows as a heads-up notification.
- Planner: `priority: high` and `ttl: 0`. Companion docs (critical-notifications, Android): a default push may not ring "until screen is turned on" when the phone is stationary or the screen has been off for a while; to override this, "set `priority: high` and `ttl: 0`".
- Planner: `timeout: 120` (notifications-basic, "Notification Timeout": value in seconds). It matches the 2 min approval window and removes the push even when a `clear_notification` does not arrive (the docs note Android clears may need the app recently used).
- Planner: `clear_notification` needs only `message` and `data.tag` (notifications-basic, "Clearing"); no channel is added there.
- Planner: same keys on both phones (both Android). `alert_once` is not used: each new request should sound again.

## Plan
Planner: Opus, 2026-10-19, revision 1. Lane 2. Coder: `codex`. The planner ran the plan on a scratch copy of main (not the evidence; the code-phase checks are): with only the test edits, `test_approval_push` fails (RED) and the new clear test passes; with both edits all three Done-when commands pass.

### Coder scope
The coder implements the numbered changes (Steps 1 and 2) exactly as written. BLOCKED is only for a contradiction inside the plan that makes a numbered test or rule impossible to satisfy. A concern outside the numbered edits goes in a DONE_WITH_CONCERNS note, not into extra code.

### Step 1: package `ha/packages/livingroom_music.yaml`
1. In `script.livingroom_music_approval_request`, in both push actions (`notify.mobile_app_martin_fold` and `notify.mobile_app_savannah_s25_ultra`), directly after `tag: "livingroom_music_approval"` and before `actions:`, add at the same indent:
```yaml
                    channel: "kids_music_approval"
                    importance: "high"
                    priority: "high"
                    ttl: 0
                    timeout: 120
```
Nothing else changes; the two `clear_notification` blocks in `script.livingroom_music_clear_pushes` stay as they are. After the step, `channel: "kids_music_approval"` occurs exactly twice.

### Step 2: `ha/tests/test_ha_livingroom_music_remote_kids.py`
2. `test_approval_push`: the loop's `c.data["data"] == {"tag": ..., "actions": [...]}` assert becomes an exact assert on the whole call data:
`c.data == {"title": "Kids music volume", "message": "The kids ask for louder music. Approve or Deny within 2 minutes.", "data": {"tag": "livingroom_music_approval", "channel": "kids_music_approval", "importance": "high", "priority": "high", "ttl": 0, "timeout": 120, "actions": [{"action": "LRM_APPROVE_" + rid, "title": "Approve"}, {"action": "LRM_DENY_" + rid, "title": "Deny"}]}}`
This is the only test that pins the old data shape (checked: every other push test selects by `"actions" in c.data.get("data", {})`, `c.data["message"]` or `c.data["data"]["actions"]`, and the text rules in `test_package_text_rules` and `test_volume_text_rules` are unaffected).
3. New test directly after `test_approval_push`: `test_clear_push_data_unchanged`, parametrized `decision` in `["APPROVE", "DENY"]`: `music(kids=True, step=3, pending=True)`, read `rid`, clear records, `answer(hass, "LRM_" + decision + "_" + rid)`; assert `sorted(c.service for c in pushes(services)) == sorted([MARTIN, SAVANNAH])` and every push has `c.data == {"message": "clear_notification", "data": {"tag": "livingroom_music_approval"}}`. It passes on main and must keep passing.

### Live check (after a separate deploy, not part of the code)
Martin triggers a request (kids time, brighten at 0.20) and should hear the default notification sound and see a heads-up banner on both phones. The first push creates the channel "kids_music_approval" in the Home Assistant app with high importance, so no setting should be needed. If it is still silent: the phone is on silent or Do Not Disturb (this card does not bypass either), or Samsung One UI shows the channel muted; then Settings, Apps, Home Assistant, Notifications, "kids_music_approval": set it to Alert with sound. Because a channel's sound and importance are fixed after creation, a later change in this YAML would need another new channel name.

### Risks
- A failing test outside the edits listed here means a package edit went beyond Step 1.

## Result
<!-- First line: the result. Then "Open P3:" followed by "- " bullets for Martin, or "none". -->
The Approve/Deny push now asks for an audible, heads-up alert on both phones: a new Android channel `kids_music_approval` with `importance: high`, `priority: high`, `ttl: 0` and `timeout: 120` (matches the 2 min approval window), added after `tag` in the two push actions of script.livingroom_music_approval_request. Tag, title, message, action ids, the clear_notification calls and all volume logic are unchanged. Built and uncommitted on branch frugo/2026-10-19-livingroom-music-loud-push (worktree Blueprints_Home-wt/lm-push, based on main 657a6c4): 2 files (ha/packages/livingroom_music.yaml, ha/tests/test_ha_livingroom_music_remote_kids.py), 66 diff lines. Checks: the full ha/tests run (321 passed, includes all three modules named in the second Done-when command) and tests/ (780 passed); the HA commands are red on the clean base. Lane 2: one design round (both PASS), one code round (Opus PASS with one P3, Codex PASS).
Open P3:
- Live sound is unproven offline. After the deploy Martin should hear a sound on the next request. If it is still silent: the phone is on silent or Do Not Disturb (not bypassed), or Samsung created the new `kids_music_approval` channel muted; set it to Alert with sound under Settings, Apps, Home Assistant, Notifications. Later changes to the channel's sound or importance need another new channel name.
- `ttl: 0` means a phone that cannot be reached at once never gets the request (dropped, not queued); after 2 minutes the timer denies. Safe, but looks like "no push" again (design review P3).
- The goal's out-of-scope line "Loud or DND push delivery" is overridden by Martin's request for loudness only; the goal file keeps the old line until the bookkeeping commit.
- Opus correctness (code review P3): the recorded check for the second Done-when command ran one module; the full ha/tests run covers all three. Run it exactly as the card writes it next time.
- Process note: the guard treats any git command in a path containing "push" (this card's worktree and branch) as a git push; each such command needed a typed `frugo ok push:`. Avoid the word in future card ids.
