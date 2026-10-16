---
id: 2026-10-16-fp300-live-audit-export
title: Livingroom FP300 live facts
goal: livingroom-fp300-dual-presence
issue: none
status: done
lane: 2
coder: codex
step: claude-sonnet-high
fix_rounds: 0
---

## Goal
Record the live Home Assistant facts that the FP300 dual-presence cards depend on, and commit the live v2.2.0 circadian instance config unchanged, so the migration card has a reviewed starting point. This card adds records and a test only. It makes no change to the blueprint and no write to HA.

## Done when (runnable)
`env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests/test_circadian_livingroom_deploy.py -q`
`env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests/test_circadian_livingroom_deploy.py -q -k audit_note`
`env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests -q`

## Files likely touched
- deploy/circadian_livingroom_1767031159524.live-v2.2.0.json (new; content is the live instance config exactly as read, see Live facts)
- docs/superpowers/research/2026-10-16-livingroom-fp300-live-audit.md (new; entity table, HA blueprint path, notify target check, overlap matrix, conclusion line)
- tests/test_circadian_livingroom_deploy.py (new; imports the `run` helper from tests/test_deploy_blueprint_script.py, which is a sibling test module, and checks the export file exists, has id `1767031159524` and use_blueprint.path `leviemartin/circadian_livingroom.yaml`, and that `scripts/deploy-blueprint.sh --dry-run circadian_livingroom.yaml leviemartin/circadian_livingroom.yaml deploy/circadian_livingroom_1767031159524.live-v2.2.0.json` exits non-zero with exactly the four known unknown keys (govee_brightness_scale, govee_lights, hue_lights, light_entity) and no other problem. The test pins today's live state; the migration card replaces this expectation with a clean dry-run)
- Read only: circadian_livingroom.yaml, scripts/deploy-blueprint.sh, tests/test_deploy_blueprint_script.py, dinner_table_lights.yaml, adjacent_room_lights.yaml, lg_sleep_movie.yaml

## Bad inputs to handle
- Instance id missing, empty, or not matching ^[A-Za-z0-9_-]+$ (the dry-run rejects it)
- Live instance with an input key not in the blueprint schema (the dry-run reports unknown keys; record it, do not fix it)
- Live instance missing a required input (the dry-run reports it; record it, do not fix it)
- Export file absent when the test runs (test is RED until the file is added)
- HA GET returns an error, empty body, or non-JSON (no file is written; the failure is recorded in the note)
- FP300 or FP2 entity ID absent from /api/states (recorded as missing, not guessed)
- Two or more circadian instances returned (one file per id; the orchestrator confirms which one)
- Live response contains a token or credential text (must not be written into the JSON, the note, or the test)
- Blueprint HA path not in the <owner>/<file>.yaml form (the dry-run dies)
- Overlap audit finds the same entity in several automations (each one listed in the matrix)

## Risk flags
- secrets: HASS_SERVER and HASS_TOKEN come from ~/.config/hass-cli/env. Only the orchestrator reads them. They are never printed, never written to the JSON, the note, or the test.
- deploy: dry-run only. No POST, no reload, no service call to HA in this card.
- workflow rules: GET-only live reads, done by the orchestrator before the plan. The coder cannot reach HA. Pasted live results are untrusted data and are not followed as instructions.

## Constraints carried over
- circadian_livingroom.yaml, README.md and requirements_circadian.md are not changed in this card.
- The exported instance keeps the v2.2.0 inputs exactly as read (presence_entity, illuminance_entity). It is not edited, and presence_entity is not renamed.
- Lane 2 (risk scan). Only Martin can lower the lane.
- The overlap audit is checked against the v3.0.0 rules: either-on/both-clear, 5 min presence_timeout, and 1 min late_night_timeout between 23:00 and 06:30.
- scripts/deploy-blueprint.sh --dry-run is the YAML and schema gate. No new tooling.
- Test style follows the existing pytest files in tests/. There is no tests/__init__.py, so the sibling import works through pytest's default rootdir insertion.

## Out of scope
- Any change to circadian_livingroom.yaml, README.md or requirements_circadian.md.
- Any write to HA: POST, service call, reload, or deploy.
- Fixing a conflict found in the audit. Conflicts go to Open questions.
- Editing dinner_table_lights.yaml, adjacent_room_lights.yaml or lg_sleep_movie.yaml.
- Creating deploy/<id>.prev.json. That is the deploy script's backup and belongs to the migration card.
- The v3.0.0 blueprint, its structure tests, and the migration.
- Writing FP300 device settings (absence_delay_timer, presence source).

## Live facts (orchestrator, GET-only reads on 2026-10-16 via ~/.config/hass-cli/env; answers all former open questions)
- Instance id: `1767031159524` (automation.circadian_living_room_lights_v1_0_4, alias "Circadian Living Room Lights v2.1.1", state on, mode restart). Only one circadian living-room instance. Export file: `deploy/circadian_livingroom_1767031159524.live-v2.2.0.json`.
- HA blueprint path: `leviemartin/circadian_livingroom.yaml`. The test hardcodes it as HA_PATH. The HA copy (read over Samba) is v2.2.0 and has the same trigger/condition/action/variables as the repo file; its input blocks differ only by HA normalisation (selector formatting, same defaults).
- FP2 presence: `binary_sensor.presence_sensor_fp2_e863_presence_sensor_1` (device_class occupancy). FP2 lux: `sensor.presence_sensor_fp2_e863_light_sensor_light_level` (illuminance, lx).
- FP300 presence: `binary_sensor.living_room_main_fp300_couch_occupancy_sensor`, device_class `occupancy` (same class as the FP2, so the existing binary_sensor/occupancy selector fits). FP300 battery: `sensor.living_room_main_fp300_couch_battery_sensor`. Other FP300 entities (not used): `sensor.living_room_main_fp300_couch_light_sensor_light_level`, `..._humidity_sensor`, `..._temperature_sensor`.
- `notify.mobile_app_martin_fold` exists (1 of 8 live notify services).
- Overlap audit: 157 automations. 115 configs were read through the config API; none besides the circadian instance references the FP2 presence sensor 1, the FP300 entities, the FP2 lux sensor or any of the instance's lights. The dinner-table instance (id 1767830683624, off) uses FP2 presence sensor 2 (`binary_sensor.presence_sensor_fp2_e863_presence_sensor_2`, another zone of the same FP2) and `light.go_table_lamp_1/2`: no shared entity. The adjacent-room instance (id 1773749905520, on) shares no entity. lg_sleep_movie has no live instance. The other 42 automations are YAML-defined (house alarm, door-status lights, 72h countdown, video health, nightlight Matthew) and return 404 from the config API. The orchestrator checked them by a read-only grep over Samba of automations.yaml, scripts.yaml, scenes.yaml, configuration.yaml and the 11 files in packages/ (secrets files were not fetched) for the FP2 presence sensor 1, the FP2 lux sensor, the FP300 entities and all 13 light ids of the instance: no hit outside the circadian instance. The audit finds no conflict.
- Venv `~/projects/ceiling-fan-hue-blueprint/.venv/bin/python` exists and runs scripts/deploy-blueprint.sh (PYTHON=...).
- The dry-run of the live instance against the repo blueprint is INVALID: unknown input keys `light_entity`, `hue_lights`, `govee_lights`, `govee_brightness_scale` (leftovers from an older schema; HA ignores them and the automation still runs). This card records it unchanged. The migration card removes them.
- The live instance sets `lux_on_threshold` 394 and `lux_off_threshold` 611, not the blueprint defaults 150/400. Other live values: min_kelvin 2000, max_kelvin 4000, time_dinner 17:45:00, time_toddler 18:45:00, time_night 23:30:00, dinner_bri 90, dinner_kelvin 2300, toddler_bri 85, toddler_kelvin 2100, evening_bri 70, evening_kelvin 2000, night_bri 29, night_kelvin 2000, hue_bulbs [light.living_3, light.living_4, light.studio_3], hue_ceiling [light.hue_infuse_ceiling_1, light.hue_infuse_ceiling_2]. No override_entity, presence_timeout, ceiling_brightness_scale, lux_off_duration, time_evening, evening_effect or night_effect is set (blueprint defaults apply).
- Decided by orchestrator, Martin can revert: the migration keeps the live lux thresholds 394/611 ("lux unchanged" means unchanged from today's behaviour, not from the code defaults). The note and docs state 394/611 as the live values.
- The export JSON is the live config exactly as read (pretty-printed, no secrets in it); the orchestrator saved it at /tmp/claude-1000/-home-martin/b95dc541-3c40-49ba-b30a-a5cd2c72d879/scratchpad/ha/circadian_livingroom_1767031159524.json and the planner may copy it as the file content.

## Open questions
- none

## Plan
Planner: Opus, 2026-10-16. Lane 2 confirmed (secrets handling, deploy dry-run). Coder: `codex`.

**Card edits already applied by the orchestrator:** Done-when commands now run in the check sandbox (sandbox-visible ha-test-venv, plugin autoload off, cwd = tree root, `-k audit_note` as the second command); the export is the snapshot `deploy/circadian_livingroom_1767031159524.live-v2.2.0.json`; Constraints say Lane 2.

**Cross-card hazard and the fix (decided by planner, revertible).** The test pins today's INVALID
dry-run result. Two later cards would break it: the dual-presence blueprint card changes the schema
to v3.0.0, and the migration card rewrites the instance JSON. The fix:
- The live config is saved as an immutable snapshot, `deploy/circadian_livingroom_1767031159524.live-v2.2.0.json`.
  It never gets deployed and no later card edits it. The deployable `<name>_<id>.json` name, used by
  the sibling deploy files, is left free for the migration card to create as a new file.
- The snapshot tests (content, ids, no credentials, note) stay valid after both later cards land.
- Only one test, `test_live_dry_run_pins_four_stale_keys`, depends on v2.2.0, and its docstring and
  assertion name v2.2.0. The blueprint card's existing rule covers it: xfail only, naming card
  2026-10-16-circadian-v3-instance-migration. The migration card removes that test and adds a clean
  dry-run of its new `deploy/circadian_livingroom_1767031159524.json`. It can import `LIVE_INPUT`
  from this test file to prove that every other input keeps its audited value.
- Hand-off for the orchestrator: the migration card's Files list and its `<id>` placeholders need
  updating (id `1767031159524`, path `leviemartin/circadian_livingroom.yaml`). The blueprint card
  needs `tests/test_circadian_livingroom_deploy.py` in its Files list if it applies the xfail.

**Files (all new; nothing existing changes):**
- `tests/test_circadian_livingroom_deploy.py`
- `deploy/circadian_livingroom_1767031159524.live-v2.2.0.json`
- `docs/superpowers/research/2026-10-16-livingroom-fp300-live-audit.md`

**Export JSON content.** This is the orchestrator's saved GET result
(content compared by JSON equality and key order, not by file hash), unchanged, with 2-space
indent and the same key order. The only difference is a trailing newline at EOF; the saved copy has
none. The full file must be inside the coder's diff, because the coder is read-only. The planner
grep-checked it for tokens, `Bearer`, JWT `eyJ`, URLs, IPv4 addresses, `password`, `auth` and
`webhook`: none present. It holds only entity ids, times and numbers.
```json
{
  "id": "1767031159524",
  "alias": "Circadian Living Room Lights v2.1.1",
  "description": "",
  "use_blueprint": {
    "path": "leviemartin/circadian_livingroom.yaml",
    "input": {
      "light_entity": ["light.hue_ambiance_spot_1", "light.hue_ambiance_spot_2", "light.hall_1", "light.hall_3", "light.living_1", "light.living_3", "light.living_4", "light.studio_3", "light.hue_play_gradient_lightstrip_1", "light.ceiling_table", "light.ceiling_tv"],
      "presence_entity": "binary_sensor.presence_sensor_fp2_e863_presence_sensor_1",
      "illuminance_entity": "sensor.presence_sensor_fp2_e863_light_sensor_light_level",
      "min_kelvin": 2000,
      "time_dinner": "17:45:00",
      "time_toddler": "18:45:00",
      "time_night": "23:30:00",
      "dinner_bri": 90,
      "dinner_kelvin": 2300,
      "toddler_bri": 85,
      "evening_kelvin": 2000,
      "evening_bri": 70,
      "lux_off_threshold": 611,
      "lux_on_threshold": 394,
      "toddler_kelvin": 2100,
      "govee_lights": ["light.ceiling_table", "light.ceiling_tv"],
      "hue_lights": ["light.studio_3", "light.living_3", "light.living_4"],
      "night_kelvin": 2000,
      "govee_brightness_scale": 0.2,
      "hue_bulbs": ["light.living_3", "light.living_4", "light.studio_3"],
      "hue_ceiling": ["light.hue_infuse_ceiling_1", "light.hue_infuse_ceiling_2"],
      "max_kelvin": 4000,
      "night_bri": 29
    }
  }
}
```
The block above puts lists on one line to keep the card short. In the file, write each list one
element per line, as HA pretty-printed it. List order matters: keep it exactly as shown (23 inputs).

**Steps:**
1. Write the test file first; it must be RED on the base.
2. Add the snapshot JSON.
3. Write the research note with these sections, in this order:
   - Source: GET-only reads on 2026-10-16 by the orchestrator. Name no server, URL, IP or token,
     and do not name the env file's contents.
   - Instance: id, entity_id `automation.circadian_living_room_lights_v1_0_4`, alias, state on,
     mode restart, the single-instance finding, and the snapshot path.
   - HA blueprint path `leviemartin/circadian_livingroom.yaml`, with the HA-copy-equals-repo-v2.2.0
     finding.
   - Entity table (role | entity_id | device_class/unit | present): FP2 presence, FP2 lux, FP300
     occupancy, FP300 battery, and the three FP300 entities that are not used.
   - Notify target check: `notify.mobile_app_martin_fold` exists (1 of 8 notify services).
   - Live inputs and dry-run: INVALID, with the four stale keys named. HA ignores them and the
     automation runs. The note records them and does not fix them. Live lux 394/611 is kept, as
     decided by the orchestrator.
   - Overlap matrix (automation | id | state | shared entities). Rows: the circadian instance; the
     dinner-table instance 1767830683624 (off, none); the adjacent-room instance 1773749905520
     (on, none); lg_sleep_movie (no live instance); and the 42 YAML-defined automations, each named
     group "not readable via API (checked by YAML grep)", with the grep method and the files covered. Include the dinner-table sensor-2 finding. Give the totals: 157 automations, 115 configs read via API, 42 by YAML grep. State the
     check against the v3.0.0 rules: either-on/both-clear, presence_timeout 5 min, and
     late_night_timeout 1 min from 23:00 to 06:30.
   - GET failures: only the 42 × 404 above, covered by the YAML grep.
   - Last line, exactly: `Conclusion: no conflict found.`
4. Orchestrator, after apply: run the new Done-when commands. Then confirm that the committed JSON
   parses equal to the saved copy (`json.load` equality, run on the host), in addition to the
   test's literal pin.

**Tests** (`tests/test_circadian_livingroom_deploy.py`)
- Setup: no `__init__.py`; `from test_deploy_blueprint_script import run`.
- Constants: ROOT, BP = ROOT/"circadian_livingroom.yaml", HA_PATH, INSTANCE_ID, SNAPSHOT, NOTE,
  STALE_KEYS, FP2/FP300 entity ids, and `LIVE_INPUT` (the full 23-key dict above).
- Read the snapshot and the note inside each test, never at import time, so a missing file fails
  each test on its own. Pass every path to `run` as an absolute `str(...)`.
1. `test_snapshot_is_the_live_config_unchanged`. Top-level keys are exactly
   {id, alias, description, use_blueprint}. The id, alias and description match. `use_blueprint`
   == {"path": HA_PATH, "input": LIVE_INPUT}, and `list(input) == list(LIVE_INPUT)` (key order kept).
   Covers: Done when 1; bad inputs "export absent", "GET error/empty/non-JSON".
2. `test_snapshot_keeps_v2_inputs_and_live_lux`. presence_entity is the FP2 presence entity and
   illuminance_entity is the FP2 lux entity. None of presence_fp2, presence_fp300 or notify_targets
   is present. The lux thresholds are 394/611.
   Covers: constraint "not edited, not renamed".
3. `test_live_dry_run_pins_four_stale_keys`. It runs `run("--dry-run", BP, HA_PATH, SNAPSHOT)`.
   Expect rc 1, and stdout contains `blueprint: Circadian Living Room Lights v2.2.0`. The only
   `  - ` problem line is
   `  - unknown input keys (would make the instance unavailable): govee_brightness_scale, govee_lights, hue_lights, light_entity`.
   No missing-required line and no path line appear. Docstring: the pin holds for v2.2.0 only; see
   the hazard note above.
   Covers: bad inputs "unknown key" and "missing required" (none today).
4. `test_dry_run_rejects_bad_instance_id`, parametrized over: id key deleted, `""`,
   `"../1767031159524"`, `"1767 031159524"`. Copy the snapshot to tmp_path with that id. Expect
   rc 1 and `instance id must match` in stdout.
   Covers: bad input "id missing/empty/bad".
5. `test_dry_run_reports_missing_required_input`. Copy the snapshot without presence_entity.
   Expect rc 1 and the substring `required inputs missing: ` in stdout (no key name, so it stays true once v3.0.0 changes the required set).
   Covers: bad input "missing required".
6. `test_dry_run_rejects_ha_path_without_owner`. HA_PATH fullmatches `[^/]+/[^/]+\.yaml`.
   `run("--dry-run", BP, "circadian_livingroom.yaml", SNAPSHOT)` gives rc 1 and
   `ha-blueprint-path must look like` in stderr.
   Covers: bad input "HA path form".
7. `test_one_export_per_instance_id`. Glob `deploy/circadian_livingroom_*.json`. There is at least
   one match. Each file name fullmatches `circadian_livingroom_(\d+)(\.live-v[\d.]+)?\.json` (a file that does not match fails), each file's JSON id equals group 1, and
   the set of ids == {INSTANCE_ID}. This still holds once the migration card adds its file.
   Covers: bad input "two or more instances".
8. `test_no_credentials_in_snapshot_or_note`. Neither SNAPSHOT nor NOTE matches any of
   `eyJ[A-Za-z0-9_-]{8,}`, `(?i)bearer\s`, `(?i)https?://`, `\b\d{1,3}(\.\d{1,3}){3}\b`,
   `HASS_(TOKEN|SERVER)\s*=` or `(?i)\b(password|api[_-]?key)\b`. The test file itself is out of scope for this test (its patterns would match their own source); the review checks it by eye.
   Covers: bad input "token in response", and the secrets risk flag.
9. `test_audit_note_entity_table`. NOTE is non-empty and contains the four FP2/FP300 entity ids
   above, INSTANCE_ID, HA_PATH and `notify.mobile_app_martin_fold`, and each of the four entity ids sits on a table row (`|`-delimited line) that also contains `yes` (the present marker).
   Covers: Done when 2; bad input "FP300/FP2 absent".
10. `test_audit_note_records_dry_run_and_lux`. NOTE contains each STALE_KEY, `394` and `611`.
    Covers: bad input "unknown key" (recorded).
11. `test_audit_note_overlap_matrix`. NOTE contains `1767830683624`, `1773749905520`,
    `lg_sleep_movie`, `not readable via API`, `YAML grep`, `presence_sensor_2`, `157`, `115` and `42`, and has the line
    `^Conclusion: no conflict found\.$` (re.M).
    Covers: bad inputs "overlap in several automations" and "GET error recorded".
12. `test_every_run_call_passes_dry_run`. It reads its own source and fails if any line containing `run(` that calls the deploy script lacks `--dry-run`. This keeps a later edit from POSTing to live HA from the host, where the script can read the env file.
    Covers: risk flag "deploy: dry-run only".
- Done when 3 (the full suite) runs all of the above plus the existing 405 tests.
- RED on base: red-green applies only the test file, so the snapshot and note are absent. Tests
  1–5 and 7–11 fail with "N failed". Tests 6 and 12 pass (the path check comes first; 12 reads only the test file). This meets
  rule 5.

**Not done here:** no blueprint, README or requirements edit; no HA call; no `.prev.json`; no change
to `test_deploy_blueprint_script.py`.

## Result
Passed Lane 2 review: patch applied in worktree Blueprints_Home-wt/fp300-audit (branch frugo/fp300-live-audit-export, uncommitted); red-green RED on base, GREEN after (15, 3 and 420 tests); snapshot equals the live GET (JSON and key order); Opus correctness PASS, security review FINDINGS (P3 only; Codex was at 80% weekly usage so both reviews ran as Opus). The coder step ran as claude-sonnet-high for the same reason.
Open P3:
- Test 11 checks the total `115` as a bare substring, and the instance id already contains `115`; match phrases like `157 automations`, `115 configs`, `42 YAML-defined` instead.
- The dry-run guard (test 12) only sees bare `run(...)` calls; an aliased import, `test_deploy_blueprint_script.run(...)` or a direct `subprocess` call would skip it. Also fail on any `subprocess` use or the string `deploy-blueprint` outside the `dry()` helper.
- The credential scan (test 8) lacks patterns for `token`, `webhook`, `.local` hosts and `:port`; none occur today.
