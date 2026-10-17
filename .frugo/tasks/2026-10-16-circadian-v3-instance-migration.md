---
id: 2026-10-16-circadian-v3-instance-migration
title: Livingroom FP300 instance migration
goal: livingroom-fp300-dual-presence
issue: none
status: done
lane: 2
coder: codex
step: codex
fix_rounds: 0
---

## Goal
Migrate the live circadian living-room instance export to the v3.0.0 inputs: `presence_entity` becomes `presence_fp2`, `presence_fp300` is added, and `notify_targets` is set to `[notify.mobile_app_martin_fold]`. Every other input keeps its audited value. A test drives `scripts/deploy-blueprint.sh --dry-run` against the real blueprint, and the dry-run passes. No HA write happens in this card.

## Done when (runnable)
`env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests/test_circadian_livingroom_deploy.py -q`
`env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests -q`
`env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests/test_circadian_livingroom_deploy.py::test_migrated_instance_dry_run_passes -q`

## Files likely touched
- deploy/circadian_livingroom_1767031159524.json (new; the deployable v3.0.0 instance payload)
- tests/test_circadian_livingroom_deploy.py (edit: remove the xfailed v2.2.0 dry-run pin, add the v3.0.0 dry-run and migration tests)
- tests/test_circadian_livingroom_structure.py (edit: delete only card 2's test that pins the xfail marker on the removed v2.2.0 test)
- Read only: deploy/circadian_livingroom_1767031159524.live-v2.2.0.json (immutable snapshot, never edited), circadian_livingroom.yaml (v3.0.0), scripts/deploy-blueprint.sh, tests/test_deploy_blueprint_script.py

## Bad inputs to handle
- Export file deploy/circadian_livingroom_<id>.json absent or empty
- Instance id missing, empty, or not matching ^[A-Za-z0-9_-]+$
- presence_entity still present in the migrated instance (must be absent)
- presence_fp2 or presence_fp300 missing, empty, or not the entity ID recorded in the audit
- FP300 entity absent from live states (recorded as missing, not guessed)
- notify.mobile_app_martin_fold absent from live notify services (stop; do not add it)
- Instance input key outside the v3.0.0 schema, or a required input missing
- Live export containing token or credential text (must not be written into the JSON or the test)
- Non-presence input value differing from the audit literal
- use_blueprint.path not in the <owner>/<file>.yaml form
- Two or more circadian instances in the live export
- circadian_livingroom.yaml still at v2.2.0 when the dry-run runs (the dry-run must fail, not pass)

## Risk flags
- deploy: dry-run only. The instance file is the payload that the next card POSTs.
- data/migrations: breaking input rename. presence_entity is removed with no alias.
- secrets: the dry-run needs no HASS_TOKEN. The test must not read ~/.config/hass-cli/env, and no token may appear in the JSON or the test.
- workflow rules: test-first. The test must fail (RED) before the patch and pass (GREEN) after it.

## Constraints carried over
- Lane 2 (risk scan). Only Martin may lower it.
- RED before the patch: on the base tree the new tests fail because deploy/circadian_livingroom_1767031159524.json does not exist (about 20 failures); the v2.2.0 dry-run result is pinned by a test that passes on the base. GREEN after the patch.
- The test drives the real script and the real blueprint. It does not use a fake. It follows the `run` helper pattern in tests/test_deploy_blueprint_script.py and imports it as a sibling module (no tests/__init__.py).
- Non-presence input literals in the test are copied from the audit export, not from the migrated file.
- late_night_start, late_night_end and late_night_timeout are left unset, so the blueprint defaults apply.
- Only the instance JSON, the deploy test file and one deleted test in tests/test_circadian_livingroom_structure.py change (decided by orchestrator, Martin can revert: card 2's test 26 pins the xfail this card removes, so it goes with it). circadian_livingroom.yaml, README.md and requirements_circadian.md do not change.
- The remove step is the presence_entity key in the instance file. No file is deleted.

## Out of scope
- Any POST to HA, reload, service call, or live deploy (next card).
- Any change to circadian_livingroom.yaml, README.md or requirements_circadian.md.
- Creating deploy/<id>.prev.json (the deploy script's backup, next card).
- Setting late-night inputs to non-default values.
- The other blueprints and automations: adjacent_room_lights.yaml, dinner_table_lights.yaml, lg_sleep_movie.yaml.
- Writing FP300 device settings.
- Reading the HA credentials file or any token.

## Live facts and decisions (orchestrator, 2026-10-16)
- Baseline: card 2026-10-16-fp300-live-audit-export is committed (c40839f). It provides tests/test_circadian_livingroom_deploy.py (with `LIVE_INPUT`, the 23 audited live inputs, and `run`/`dry` helpers), deploy/circadian_livingroom_1767031159524.live-v2.2.0.json and docs/superpowers/research/2026-10-16-livingroom-fp300-live-audit.md. Card 2026-10-16-circadian-v3-dual-presence-blueprint (v3.0.0 blueprint) must be committed on the branch this card starts from; its xfail marker sits on `test_live_dry_run_pins_four_stale_keys`, which this card removes.
- Instance id `1767031159524`; HA blueprint path `leviemartin/circadian_livingroom.yaml` (pin as HA_PATH). FP2 presence `binary_sensor.presence_sensor_fp2_e863_presence_sensor_1` becomes `presence_fp2`; FP300 presence `binary_sensor.living_room_main_fp300_couch_occupancy_sensor` is `presence_fp300`; `notify.mobile_app_martin_fold` exists live.
- The migrated payload keeps id, description, use_blueprint.path and these inputs exactly as audited: illuminance_entity, min_kelvin, max_kelvin, time_dinner, time_toddler, time_night, dinner_bri, dinner_kelvin, toddler_bri, toddler_kelvin, evening_bri, evening_kelvin, night_bri, night_kelvin, lux_on_threshold 394, lux_off_threshold 611, hue_bulbs, hue_ceiling. It drops presence_entity (renamed to presence_fp2) and the four stale v2.1-era keys light_entity, hue_lights, govee_lights, govee_brightness_scale (unknown to the v3.0.0 schema; the dry-run would reject them). It adds presence_fp300 and notify_targets [notify.mobile_app_martin_fold]. Count: 23 live keys, minus 5 removed (presence_entity plus the four stale keys) leaves 18, plus presence_fp2, presence_fp300 and notify_targets gives 21. The planner pins the exact list.
- Decided by orchestrator, Martin can revert: the alias is updated to "Circadian Living Room Lights v3.0.0" (it still says v2.1.1; the entity_id stays automation.circadian_living_room_lights_v1_0_4 because HA derives it from the original name).
- Decided by orchestrator, Martin can revert: the late-night inputs stay unset (defaults 23:00, 06:30, 1 min); the test asserts they are absent.
- The test relies on the real script; PYTHON for PyYAML follows whatever the existing `run` helper in tests/test_deploy_blueprint_script.py does. It must not read ~/.config/hass-cli/env.
- Keep Files-list parentheticals short (the card parser treats an over-long entry as a path).

## Open questions
- none

## Plan
<!-- Planner only: exact files incl. test files, steps, and the test list (one test per
     "Done when" item and per bad input). -->
Planner: Opus, Lane 2 confirmed (payload for a live physical-world automation, breaking input rename, the next card POSTs it). Coder: `codex`.

### Orchestrator actions before coding (planner gaps, no decision reopened)
1. **Done-when 3 must be replaced.** As written it fails in the check sandbox twice over: `~/AI/projects/Blueprints_Home` is not visible there (HOME is a tmpfs; cwd is the check tree), and a bare script run prints no test count, so red-green returns `count-unknown` (exit 6). Replace it with:
   `env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests/test_circadian_livingroom_deploy.py::test_migrated_instance_dry_run_passes -q`
   It drives the same `bash scripts/deploy-blueprint.sh --dry-run circadian_livingroom.yaml leviemartin/circadian_livingroom.yaml deploy/circadian_livingroom_1767031159524.json` through `run`.
2. **Files list gained `tests/test_circadian_livingroom_structure.py`.** Card 2's plan test 26 (`test_deploy_dry_run_pin_is_xfailed_for_the_migration_card`) asserts by AST that the deploy test file holds exactly one xfail, on `test_live_dry_run_pins_four_stale_keys`. Removing that test (this card) turns test 26 red and breaks Done-when 2. Chosen route: this card deletes test 26 and pins the removal in its own file (test 18). This contradicts "Only the instance JSON and the new test file change"; the alternative is to amend card 2 so test 26 also accepts the test being absent, in which case drop the structure file from this card.

3. **Base commit (design review P2).** Card 2026-10-16-circadian-v3-dual-presence-blueprint is applied but uncommitted in `/home/martin/AI/projects/Blueprints_Home-wt/circadian-v3`. This card is coded only in a new worktree whose base is a commit holding that card (v3.0.0 blueprint: 31 inputs, required exactly illuminance_entity, presence_fp2, presence_fp300). It is never coded on c40839f or on an uncommitted tree.

### Sandbox facts (checked 2026-10-16 on an export of c40839f inside `scripts/sandbox --mode check`)
- `python3` resolves to `/usr/bin/python3` with system PyYAML 6.0.1, so `run` (no `PYTHON` set, inherits PATH `…/node/bin:/usr/bin:/bin`) works; no `PYTHON=` override is needed. The ha-test-venv python is visible read-only. Done-when 1 on the base: 15 passed.
- Done-when 1 and 2 run unchanged (cwd = tree root, `~` resolves to the visible venv).
- The migrated JSON below was dry-run in the sandbox against a v3.0.0 input-schema stand-in built from card 2's Plan (31 inputs; required exactly illuminance_entity, presence_fp2, presence_fp300): `ok (id 1767031159524, 21 inputs)`, rc 0. Against the v2.2.0 schema it fails with exactly the lines pinned in test 17; the unmigrated snapshot against v3 fails with exactly the lines pinned in test 8.

### Files (exactly these three)
1. `deploy/circadian_livingroom_1767031159524.json`: new, full content below.
2. `tests/test_circadian_livingroom_deploy.py`: edit (remove one test, add constants, two helpers, tests 1-18).
3. `tests/test_circadian_livingroom_structure.py`: delete one test function only (see gap 2).
Read only: the v2.2.0 snapshot (never edited), `circadian_livingroom.yaml` (v3.0.0), `scripts/deploy-blueprint.sh`, `tests/test_deploy_blueprint_script.py`, the audit note.

### The deployable payload (complete file; 2-space indent as `json.dumps(indent=2)`, ending `}\n`)
Top level 4 keys (id, alias, description, use_blueprint); use_blueprint 2 keys (path, input); input 21 keys = 23 live − 5 dropped (presence_entity, light_entity, hue_lights, govee_lights, govee_brightness_scale) + presence_fp2, presence_fp300, notify_targets. Order: live order, presence_entity replaced in place by presence_fp2 then presence_fp300, notify_targets last. No `trace` key, no late_night_* keys.
```json
{
  "id": "1767031159524",
  "alias": "Circadian Living Room Lights v3.0.0",
  "description": "",
  "use_blueprint": {
    "path": "leviemartin/circadian_livingroom.yaml",
    "input": {
      "presence_fp2": "binary_sensor.presence_sensor_fp2_e863_presence_sensor_1",
      "presence_fp300": "binary_sensor.living_room_main_fp300_couch_occupancy_sensor",
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
      "night_kelvin": 2000,
      "hue_bulbs": [
        "light.living_3",
        "light.living_4",
        "light.studio_3"
      ],
      "hue_ceiling": [
        "light.hue_infuse_ceiling_1",
        "light.hue_infuse_ceiling_2"
      ],
      "max_kelvin": 4000,
      "night_bri": 29,
      "notify_targets": [
        "notify.mobile_app_martin_fold"
      ]
    }
  }
}
```

### Steps (test-first)
0. RED baseline gate, before the coder's output is trusted: on the card-2 base commit, with only this card's two test-file edits applied, run Done-when 1 and confirm **18 passed, 20 failed**. The 18 passing tests are the 14 existing ones (the 15 base tests minus the removed pin) plus new tests 8, 9 (2 cases) and 18. The 20 failures are listed under "RED on the base". If the counts differ, the orchestrator re-derives the planner numbers before continuing. (The review note said "15 passed"; 15 is the count on the unedited base file, not after the test edit.)
1. `tests/test_circadian_livingroom_deploy.py`:
   - Delete `test_live_dry_run_pins_four_stale_keys` together with its `@pytest.mark.xfail(...)` decorator (card 2's edit). That is the "remove" step; no file is deleted. Keep `STALE_KEYS` (the audit-note test uses it), `import pytest`, `dry`, `snapshot_with` and every other existing test unchanged.
   - LIVE_INPUT, FP2_PRESENCE, FP300_PRESENCE, HA_PATH, INSTANCE_ID, NOTE, CREDENTIAL_PATTERNS are module constants of this same file: the new tests use them directly (no import). Audit literals always come from `LIVE_INPUT`, never from the migrated file. `run` stays imported as today: `from test_deploy_blueprint_script import run` (sibling module, no `tests/__init__.py`).
   - Add constants: `INSTANCE = ROOT / "deploy" / f"circadian_livingroom_{INSTANCE_ID}.json"`; `V3_ALIAS = "Circadian Living Room Lights v3.0.0"`; `NOTIFY_TARGET = "notify.mobile_app_martin_fold"`; `DROPPED_KEYS = ["presence_entity", *STALE_KEYS]`; `KEPT_KEYS` = the 18 names in live order (illuminance_entity, min_kelvin, time_dinner, time_toddler, time_night, dinner_bri, dinner_kelvin, toddler_bri, evening_kelvin, evening_bri, lux_off_threshold, lux_on_threshold, toddler_kelvin, night_kelvin, hue_bulbs, hue_ceiling, max_kelvin, night_bri); `MIGRATED_KEYS = ["presence_fp2", "presence_fp300", *KEPT_KEYS, "notify_targets"]`; `LATE_NIGHT_KEYS = ["late_night_start", "late_night_end", "late_night_timeout"]`; `V2_2_0_KEYS` = the 26 v2.2.0 inputs (hue_bulbs, hue_ceiling, ceiling_brightness_scale, presence_entity, presence_timeout, illuminance_entity, override_entity, lux_on_threshold, lux_off_threshold, lux_off_duration, time_dinner, dinner_kelvin, dinner_bri, time_toddler, toddler_kelvin, toddler_bri, time_evening, evening_kelvin, evening_bri, evening_effect, time_night, night_kelvin, night_bri, night_effect, max_kelvin, min_kelvin; copied from c40839f); `UNKNOWN = "  - unknown input keys (would make the instance unavailable): "`; `MISSING = "  - required inputs missing: "`; `ID_LINE = "  - instance id must match ^[A-Za-z0-9_-]+$ (it is used in URLs and backup paths)"`.
   - Add helpers: `problems(r)` = stdout lines starting with `"  - "`; `migrated_with(tmp_path, mutate)` = `snapshot_with` but loading `INSTANCE`.
   - Every script call goes through `dry(...)`, so `test_every_run_call_passes_dry_run` keeps holding; no new `run(` call, no `PYTHON` env, no read of any HA credential file.
2. `tests/test_circadian_livingroom_structure.py`: delete the one test function whose body names `test_live_dry_run_pins_four_stale_keys` (planned name `test_deploy_dry_run_pin_is_xfailed_for_the_migration_card`). In the same edit, remove `import ast` if the deleted test was its only user (design review P3a). Nothing else in that file changes.
3. Create the JSON exactly as above.
4. Run Done-when 1, 2 and the replacement 3.

### Test list (all in `tests/test_circadian_livingroom_deploy.py`)
1. `test_migrated_instance_dry_run_passes` (Done-when 1 and 3; the clean v3 dry-run): `r = dry(str(BP), HA_PATH, str(INSTANCE))`; `r.returncode == 0`; `r.stdout.splitlines() == ["blueprint: Circadian Living Room Lights v3.0.0", f"instance {INSTANCE}: ok (id {INSTANCE_ID}, 21 inputs)", "dry-run: validation passed, nothing deployed"]`; `r.stderr == ""`. Real script, real v3.0.0 blueprint, no fake.
2. `test_migrated_instance_shape` (bad input: path not owner/file): top-level keys == {id, alias, description, use_blueprint}; id == INSTANCE_ID; alias == V3_ALIAS; description == ""; `set(use_blueprint) == {"path", "input"}`; path == HA_PATH and `re.fullmatch(r"[^/]+/[^/]+\.yaml", path)`; `list(input) == MIGRATED_KEYS` (21).
3. `test_migration_drops_presence_entity_and_stale_keys` (bad input: presence_entity still present): no DROPPED_KEYS in input; `"presence_entity" not in INSTANCE.read_text()`; `[k for k in LIVE_INPUT if k not in DROPPED_KEYS] == KEPT_KEYS` (23 − 5 = 18, live order).
4. `test_presence_inputs_are_the_audited_entities` (bad inputs: fp2/fp300 missing, empty or not the audited id; FP300 absent from live states): presence_fp2 == FP2_PRESENCE == LIVE_INPUT["presence_entity"]; presence_fp300 == FP300_PRESENCE; for both, the audit note has a `|` table row containing the id and `yes` (an FP300 recorded missing makes this fail rather than letting a guessed id through).
5. `test_notify_targets_is_the_audited_fold_service` (bad input: Fold service absent): notify_targets == [NOTIFY_TARGET]; `re.fullmatch(r"notify[.][a-z0-9_]+", NOTIFY_TARGET)`; "`notify.mobile_app_martin_fold` exists" (with the backticks) is in the audit note.
6. `test_non_presence_inputs_keep_audit_literals` (bad input: value differs): for each k in KEPT_KEYS, `inp[k] == LIVE_INPUT[k]` and `type(inp[k]) is type(LIVE_INPUT[k])`; explicitly (inp["lux_on_threshold"], inp["lux_off_threshold"]) == (394, 611).
7. `test_late_night_inputs_left_unset`: no LATE_NIGHT_KEYS in input (blueprint defaults 23:00 / 06:30 / 1 min apply).
8. `test_unmigrated_snapshot_fails_v3_dry_run` (replaces the removed v2.2.0 pin; this is the card's "presence_entity unknown / presence inputs missing" outcome): `dry(str(BP), HA_PATH, str(SNAPSHOT))` rc 1, `"blueprint: Circadian Living Room Lights v3.0.0"` in stdout, `problems(r) == [UNKNOWN + "govee_brightness_scale, govee_lights, hue_lights, light_entity, presence_entity", MISSING + "presence_fp2, presence_fp300"]`.
9. `test_dry_run_rejects_absent_or_empty_export` (bad input), parametrized `absent`/`empty` on a tmp path: rc 1, `"validation passed"` and `"ok (id"` not in stdout; absent also has `"instance file not found"` in stderr.
10. `test_migrated_dry_run_rejects_bad_instance_id` (bad input), parametrized `[None, "", "../" + INSTANCE_ID, "1767 031159524"]` via `migrated_with` (None deletes `id`): rc 1, `problems(r) == [ID_LINE]`.
11. `test_migrated_dry_run_rejects_presence_entity` (bad input): add `presence_entity: FP2_PRESENCE` back: rc 1, `problems(r) == [UNKNOWN + "presence_entity"]`.
12. `test_migrated_dry_run_rejects_missing_required_input` (bad inputs: fp2/fp300 missing; required input missing), parametrized `presence_fp2`, `presence_fp300`, `illuminance_entity`: pop it: rc 1, `problems(r) == [MISSING + key]`.
13. `test_migrated_dry_run_rejects_key_outside_v3_schema` (bad input): add `govee_lights: LIVE_INPUT["govee_lights"]`: rc 1, `problems(r) == [UNKNOWN + "govee_lights"]`.
14. `test_migrated_dry_run_rejects_path_without_owner` (bad input): set use_blueprint.path to `"circadian_livingroom.yaml"`: rc 1, `problems(r) == ["  - use_blueprint.path 'circadian_livingroom.yaml' != 'leviemartin/circadian_livingroom.yaml'"]`.
15. `test_single_deployable_circadian_instance` (bad input: two or more instances): deploy `circadian_livingroom_*.json` files without `.live-v` in the name == [INSTANCE]; the parsed file is a dict (one instance, not a list). The existing `test_one_export_per_instance_id` stays and now also covers the new file.
16. `test_no_credentials_in_migrated_instance_or_this_test` (bad input: credential text; risk flag secrets): no CREDENTIAL_PATTERNS match in INSTANCE text; this file's source with the `CREDENTIAL_PATTERNS = [...]` statement cut out (`ast.get_source_segment`) matches none of them either; and the source contains none of `"hass" + "-cli"`, `"HASS" + "_TOKEN"`, `"." + "config/"` (split literals so the test does not match itself; verified on the base file).
17. `test_migrated_instance_fails_against_v2_2_0_blueprint` (bad input: blueprint still v2.2.0): write `tmp_path / "circadian_livingroom.yaml"` as `json.dumps({"blueprint": {"name": "Circadian Living Room Lights v2.2.0", "input": {k: {} if k in ("presence_entity", "illuminance_entity") else {"default": 0} for k in V2_2_0_KEYS}}})` (JSON is YAML; this is the old input schema, the only thing the script reads; the real v2.2.0 file is no longer in the tree); `dry(str(stub), HA_PATH, str(INSTANCE))`: rc 1, `"validation passed"` not in stdout, `problems(r) == [UNKNOWN + "notify_targets, presence_fp2, presence_fp300", MISSING + "presence_entity"]`. The test carries a comment: the stub is synthetic, and the real guard against a v2.2.0 blueprint in the tree is test 1's exact `blueprint: Circadian Living Room Lights v3.0.0` line. Once during coding (design review P3b), the orchestrator checks V2_2_0_KEYS and the two required keys against `git show c40839f:circadian_livingroom.yaml`, outside the patch. The planner already checked them on 2026-10-16.
18. `test_v2_2_0_pin_removed` (the remove step; replaces card 2's test 26): AST of this file has no function `test_live_dry_run_pins_four_stale_keys` and no `xfail` attribute anywhere.
Done-when 2: full suite, green only with step 2 applied.

### RED on the base (test files only applied to card 2's committed tree)
`INSTANCE` does not exist there, so tests 1-7, 10-17 fail by assertion or `FileNotFoundError` inside the test body (pytest `N failed`; test 1: script dies "instance file not found", rc 1). Tests 8, 9, 18 pass on the base. Done-when 1: 18 passed, 20 failed (parametrized cases counted; GREEN: 38 passed); replacement Done-when 3: `1 failed`; Done-when 2: the same failures. GREEN after the JSON is added. Precondition: card 2's v3.0.0 blueprint is committed on the base branch, otherwise test 8 and test 1 fail on the blueprint name.

## Result
Passed Lane 2 review: the v3.0.0 instance payload deploy/circadian_livingroom_1767031159524.json and 38 deploy tests are applied in worktree Blueprints_Home-wt/circadian-v3-migration (branch frugo/circadian-v3-migration, uncommitted, based on card 2's commit fe90797). The obsolete xfailed v2.2.0 pin and card 2's test 26 are removed. Coder: Codex. Red-green: all three Done-when commands RED on the base, GREEN after (38 deploy tests, full suite 500 passed with no xfail, 1 targeted test). Reviews: Opus correctness FINDINGS (one P3, resolved below) and Codex security PASS. Design reviews were PASS (Codex) and FINDINGS fixed (Opus).
Orchestrator check for the Opus P3: V2_2_0_KEYS in the deploy test equals the 26 input keys of `git show c40839f:circadian_livingroom.yaml`, and that blueprint's only inputs without a default are illuminance_entity and presence_entity, so the stub in test 17 matches the real v2.2.0 schema.
Open P3:
none
