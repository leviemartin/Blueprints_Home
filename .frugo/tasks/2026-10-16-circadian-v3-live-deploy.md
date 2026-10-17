---
id: 2026-10-16-circadian-v3-live-deploy
title: Livingroom FP300 live deploy
goal: livingroom-fp300-dual-presence
issue: none
status: done
lane: 2
coder: codex
step: codex
fix_rounds: 0
---

## Goal
Deploy the v3.0.0 circadian living-room blueprint and its migrated instance to Home Assistant, after Martin's explicit deploy OK, so the FP300 counts as presence. Afterwards, one presence-on trace from the FP300 alone (couch, out of FP2 view) shows the turn-on branch.

## Done when (runnable)
`env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests -q`
`cd ~/AI/projects/Blueprints_Home && bash scripts/deploy-blueprint.sh --dry-run circadian_livingroom.yaml leviemartin/circadian_livingroom.yaml deploy/circadian_livingroom_1767031159524.json`
`cd ~/AI/projects/Blueprints_Home && bash scripts/deploy-blueprint.sh circadian_livingroom.yaml leviemartin/circadian_livingroom.yaml deploy/circadian_livingroom_1767031159524.json`

## Files likely touched
- circadian_livingroom.yaml (read only; the script pushes it to HA; it must be v3.0.0, and the repo copy still says v2.2.0 at line 2)
- deploy/circadian_livingroom_1767031159524.json (read only; the instance payload the script POSTs; not in the repo yet, created by the migration card)
- scripts/deploy-blueprint.sh (run only; not edited)
- deploy/1767031159524.prev.json (written by the script; gitignored, never committed; pinned as deploy/1767031159524.pre-v3.prev.json)

## Bad inputs to handle
- Instance file deploy/circadian_livingroom_1767031159524.json absent or empty
- Instance id missing, empty, or not matching ^[A-Za-z0-9_-]+$
- presence_entity still present in the instance file (must be removed, no alias)
- presence_fp2 or presence_fp300 missing or empty in the instance file
- Blueprint HA path not in the <owner>/<file>.yaml form
- Repo blueprint still at v2.2.0 when the dry-run runs (the dry-run must fail and the deploy must not start)
- Two or more circadian instances in the live states (target unclear; stop)
- Token or credential text found in the instance file or the repo (must not be committed or printed)
- blueprint/save succeeds but the instance POST fails (v3 blueprint is live with an unmigrated v2.2.0 instance; stop and report)
- Instance POST returns non-ok, or the state=on assertion fails (exit 1; restore from deploy/1767031159524.prev.json)
- Re-run after a partial deploy (the script overwrites deploy/1767031159524.prev.json, so the backup would then hold the v3 config; stop and check first)
- Deploy OK from Martin absent (stop before the third command)
- Trace shows no presence-on branch from the FP300 (report it; do not re-run the deploy)

## Risk flags
- deploy: live write to HA. It pushes the blueprint, POSTs the instance, and reloads the automation.
- data/migrations: breaking input rename. presence_entity is removed with no alias, so an unmigrated instance becomes unavailable.
- secrets: the script reads HASS_SERVER and HASS_TOKEN from ~/.config/hass-cli/env. The coder must not read that file or print a token.
- workflow rules: hard rule 1 applies. Martin's explicit deploy OK is required, and no standing OK applies. This card has no code patch, so rule 5 RED/GREEN does not hold on its own. The orchestrator decides whether it runs with no_runnable_checks or as the deploy step after the merge OK.

## Constraints carried over
- Lane 2 (risk scan). Only Martin may lower it.
- Runs only after every other card of goal livingroom-fp300-dual-presence is merged on main.
- Order: ask Martin for the deploy OK; run the suite and the dry-run; run the live deploy; read the newest automation trace; commit deploy/1767031159524.prev.json only after Martin's commit OK.
- The coder cannot reach HA. The live reads and the trace check are done by the orchestrator.
- Late-night inputs (late_night_start, late_night_end, late_night_timeout) are left unset, so the blueprint defaults apply.
- The notify target is notify.mobile_app_martin_fold, and it is checked live before the deploy.
- The trace must show the presence-on branch from the FP300 trigger. One check only; no multi-day observation.
- Rollback: POST deploy/1767031159524.prev.json back with the v2.2.0 blueprint. The script pushes whichever yaml it is given, so the v2.2.0 file must come from git history first.
- No edits to circadian_livingroom.yaml, README.md or requirements_circadian.md in this card.

## Out of scope
- FP300 device settings (absence_delay_timer, presence source). Martin sets them in Zigbee2MQTT per the README.
- Any dog-guard cap, time window or zone follow-up.
- Other automations and blueprints: adjacent_room_lights.yaml, dinner_table_lights.yaml, lg_sleep_movie.yaml.
- Tuning the late-night timeout or any other input.

## Live facts and decisions (orchestrator, 2026-10-16; Martin can revert any)
- Instance id `1767031159524`; HA blueprint path `leviemartin/circadian_livingroom.yaml` (confirmed live; the HA copy is v2.2.0). `notify.mobile_app_martin_fold` exists live. hass-cli (~/.local/bin) and jq (/usr/bin) are on PATH on the VPS. Only one circadian living-room instance exists live.
- Rollback source for the v2.2.0 blueprint: commit e093b63 (`git show e093b63:circadian_livingroom.yaml`), the main commit before this goal. The instance backup written by the script is `deploy/1767031159524.prev.json`.
- The script pushes the blueprint before the instance POST, so for a few seconds the v3 blueprint is live with the v2.2.0 instance (presence_entity unknown to v3). Accepted: the order is the script's, this card does not change it; if the POST fails the rollback above applies. A second run after a partial deploy is blocked until Martin has checked the backup.
- The trace check cannot be a shell command. The orchestrator reads the newest trace of automation.circadian_living_room_lights_v1_0_4 by hand (GET only) after Martin sits on the couch out of FP2 view, and records the result in Result. Martin does the physical step.
- Run mode: no code patch exists, so the planner decides how the card runs (`no_runnable_checks`, Lane 2 with 2 reviewers, or the deploy step after the merge OK). The run waits for every other card of this goal to be merged on main and for Martin's explicit deploy OK. Nothing here runs overnight.
- The dry-run and the suite use the sandbox venv from Done-when; the live script run uses system python3 with PyYAML via PYTHON as the script does. The planner confirms PyYAML is importable by the interpreter used.
- Keep Files-list parentheticals short (the card parser treats an over-long entry as a path).

## Open questions
- none

## Plan
<!-- Planner only: exact files incl. test files, steps, and the test list (one test per
     "Done when" item and per bad input). -->

Planner (Opus, Lane 2), 2026-10-16. Read: this card, scripts/deploy-blueprint.sh, tests/test_deploy_blueprint_script.py, .gitignore, the migration and blueprint cards, the audit snapshot at c40839f.

### Run mode (decided by planner; Martin can revert)
- **Deploy runbook, no patch.** Lane 2 stays. Coder: **none**. No coder brief, `codex-propose`, `apply-patch` or `red-green` runs for this card: there is no diff, and red-green cannot run without one. Front matter `coder: codex` / `step: codex` is left untouched (planner edits Plan only) and is never dispatched. Per hard rule 9 the orchestrator logs the reason: "deploy card, no patch; coder none".
- **Rule 5:** not applicable, because there is no patch. RED/GREEN for the v3.0.0 code is proven by the blueprint card and the migration card. Done-when 1 (suite) and 2 (dry-run) are pre-deploy gates. Done-when 3 is the live write itself, not a check. No automated check path ever runs Done-when 3, and only the orchestrator types it, by hand, after the deploy OK.
- **Reviews:** both Lane 2 design reviews run on this Plan (Opus for correctness, Codex for security; if Codex is at its weekly limit, a fresh Opus `high` session takes its place). Both must finish before Martin is asked for the deploy OK. There are no code reviews because there is no diff. The post-deploy evidence goes in `## Result
deployed v3.0.0 at 12:05 Amsterdam time on 2026-10-17, DEPLOY_SHA 20e5d436be0483fe75a978fe878b272b23b30736; trace PASS on a substituted couch test (Martin's choice), not the card's FP300-only turn-on check.
Deploy evidence: Martin's deploy OK given in session; suite 573 passed; dry-run 21 inputs; revalidation (HEAD, clean paths, ART_SHA, token scan, env-match, one instance, live v2.2.0, live config equal to the snapshot) passed; the single live run exited 0 with blueprint/save ok, instance written, deploy complete and the automation on, and no failure markers. The backup deploy/1767031159524.prev.json is pinned as deploy/1767031159524.pre-v3.prev.json (equal to the snapshot, gitignored, not committed). After the deploy: live config equals deploy/circadian_livingroom_1767031159524.json, live blueprint v3.0.0, automation on after 60 s, token scans clean.
Couch test (20:34-21:35 Amsterdam time): the card's FP300-only turn-on check could not run because Martin must cross FP2's view to reach the couch. Martin chose a substitute: sit on the couch, let FP2 clear, and confirm the lights stay on while only the FP300 sees him. Traces (UTC): 19:25:24 presence_on_fp300 took the SCENARIO 2 turn-on branch (FP2 had seen him first, so this does not prove FP300-alone turn-on); 19:26:37 presence_off_short_fp2 and 19:30:37 presence_off_long_fp2 (exactly 5 min after FP2 cleared at 19:25:37) both finished with no branch chosen, so no turn-off. All five lights stayed on through 21:34 Amsterdam time with the FP300 on. The both-clear turn-off was not re-tested here (Martin says he tested it earlier).
Not verified: the FP300-alone turn-on branch (older FP2 runs were beyond HA's 5-trace window); the 30-minute FP300 unavailable push; the late-night 1-minute timeout.
Open P3:
- FP300-alone turn-on is untested live. A test would need an approach path outside FP2's view, or FP2 disabled for a minute.
