---
id: 2026-10-18-livingroom-music-deploy
title: Livingroom music deploy and live check
goal: livingroom-background-music
issue: "leviemartin/Blueprints_Home#53"
status: done
lane: 2
coder: codex
step: codex
fix_rounds: 4
---

## Goal
Deploy the livingroom_music package to Home Assistant over Samba with a checked upload and rollback, retire the four Samuel Music Remote automations (their GET exports are kept, and a final GET shows them gone), and run the live check with Martin. When this is done, the package runs on HA, the four Samuel automations are gone, and each live step has passed under Martin's own OK.

## Done when (runnable)
`env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests -q`
`env -u HASS_TOKEN ~/.local/share/home-security/ha-test-venv/bin/python -I -m pytest -q -p no:cacheprovider -c ha/tests/pytest-ha.ini ha/tests`

## Files likely touched
- scripts/deploy_package.py (new; sits beside scripts/deploy-blueprint.sh)
- tests/test_deploy_package_script.py (new; offline, _spawn mocked, zero network; modelled on tests/test_deploy_blueprint_script.py)
- deploy/1701294514096.retired.json (new; the orchestrator's GET export, copied byte for byte by the coder from .frugo/inputs/exports/, not produced by the script)
- deploy/1701295072034.retired.json (new; same)
- deploy/1701295128408.retired.json (new; same)
- deploy/1701294978959.retired.json (new; same)
- ha/packages/livingroom_music.yaml (read only; the script uploads it; created by the core card, does not exist yet)

## Bad inputs to handle
- --package value other than livingroom_music: refused, nothing uploaded
- --package missing or empty: refused
- ha/packages/livingroom_music.yaml missing or empty: refused before any upload
- Package file over 64 KiB (65,536 bytes): refused before upload
- Package YAML invalid: check_config fails, backup is restored, exit non-zero
- Leftover .new file from an earlier run: overwritten by the upload (it is this script's own artifact)
- Backup path already exists for this run: refused, nothing overwritten
- ~/.config/hass-samba/env missing, unreadable or missing a variable: fails before upload, no credential printed
- Samba unreachable or upload fails midway: no rename, live package unchanged
- Rename fails or times out after upload: the live file is read back and reported as unchanged (.new left in place, exit 1), new installed (continues to check_config) or unresolved (exit 5)
- check_config unreachable or times out: treated as a failed check, backup restored
- Rollback itself fails: exit non-zero, backup path printed, no restart message
- --dry-run: no upload, no rename, no DELETE; prints the plan and exits 0
- Unknown or extra argument: refused
- DELETE on an automation id already gone (404): reported as already removed, not an error
- DELETE returns OK but GET still lists the id: live step fails
- Export file for an id missing or empty before DELETE: no DELETE sent
- Automation id not one of the four Samuel ids: refused
- Approve answer after 2 min or from a stale push during the live check: Deny applies, live check records it
- Live check started before Martin has restarted HA: live check does not start

## Risk flags
- secrets: Samba credentials in ~/.config/hass-samba/env (read, never printed); HA token via HASS_TOKEN (never in argv, files or tests)
- auth: HA GET and DELETE calls need the token
- deploy: uploads to /config/packages over Samba, runs check_config, asks Martin to restart HA
- file deletion: DELETE /api/config/automation/config/<id> removes four live HA automations (not files); the four exports are the rollback by re-POST
- trust boundary: the approval push is answered from Martin's and Savannah's phones and is tested live
- physical safety: the live check brightens to 0.30, which is loud
- workflow rules: Lane 2; each live step needs its own OK from Martin; notify.mobile_app_pixel_9_pro_xl is never called

## Constraints carried over
- Lane 2 for the whole goal; only Martin lowers a lane.
- Starts only after 2026-10-18-livingroom-music-remote-kids is done.
- Each live step has its own OK from Martin: run the deploy; Martin restarts HA; DELETE the four automations; live check.
- Script allows only --package livingroom_music, rolls back on a failed check_config, and ends with "Martin: restart Home Assistant". It never restarts HA itself.
- The four exports deploy/<id>.retired.json are GET exports and stay unchanged. Rollback for an automation is a re-POST of its export.
- Only these four automations are deleted: Sonos On Samuel 1701294514096, Sonos 20% Volume Samuel 1701295072034, Sonos 10% Volume Samuel 1701295128408, Sonos Off Samuel 1701294978959.
- Off as stop is removed (Off skips). The Sonos favorite FV:2/3 stays.
- Samba credentials and the HA token are never printed, written to files or put in argv. Tests run with env -u HASS_TOKEN and zero network.
- Read only, never a service call: media_player.marantz_cinema_50, media_player.mxn10, media_player.lg_webos_tv_oled65c9pla, alarm_control_panel.house_alarm.
- Budget: track only, warn line 500,000 tokens per card.

## Out of scope
- Package logic changes. A fix found live needs a new round.
- The dog review.
- Any automation other than the four Samuel ones, and the AV chain, circadian lights, FP2/FP300 settings and home-security package.
- Changing or rewriting the four exports.
- Restarting HA from the script.
- The FV:2/3 favorite.
- Spotify, Spotcast or Music Assistant integration.
- Loud or DND push, and volume above 0.30.

## Open questions
none

## Decided by orchestrator
Decided overnight 2026-10-18 while Martin sleeps (he is back at 7:00 Amsterdam); Martin can revert any of these.
- Dependencies: the deploy script and its offline tests do not depend on the card 3 package content, so the script work proceeds on a branch based on the core card's commit (ha/packages/livingroom_music.yaml and ha/tests exist there). Card 3 is parked on an arbiter decision; the LIVE steps (upload, HA restart, DELETE, live check) cannot start until card 3 is done and Martin gives each OK. This card is the filled stub of the same id (one card file).
- Samba target, credentials and write path: the existing memory notes reference_ha_config_samba_write_path.md (creds in ~/.config/hass-samba/env, Tailscale excluded by default) and the model scripts scripts/deploy-blueprint.sh and ~/AI/projects/home-security/scripts/ (read only); the planner reads them and follows their conventions. Target directory /config/packages as in the goal; HA must have packages enabled in configuration.yaml (the live deploy step checks this read-only; if not enabled it is a stop, not an edit).
- check_config: the same HA endpoint and token handling as scripts/deploy-blueprint.sh (token via a 0600 header file, never argv).
- Backup: a timestamped copy kept outside packages/ in a sibling directory named by the planner; an existing backup path for this run is refused.
- Leftover .new file: overwritten (it is this script's own artifact); an existing backup file is refused.
- Size limit for the package file: 64 KiB.
- Model script ~/AI/projects/home-security/scripts/deploy_video.py: read only for conventions; no need to paste it.
- Retired exports: the orchestrator exports the four automations by GET (read only) on 2026-10-18 and places them as deploy/<id>.retired.json in the worktree before the coder runs; the coder does not write them.
- DELETE and the final GET: script subcommands of scripts/deploy_package.py (--retire-automations with an explicit --yes, and --verify-retired read only), tested offline; each live run needs its own OK from Martin.
- The live walk-through is a checklist in the card's Result, run with Martin; it has no runnable command.
- Test home is ha/tests/ (core card).
- After design round 1 (planner's concern): HASS_SERVER may be overridden from the process environment (server URL only, still under the https / Tailscale-http rule); HASS_TOKEN always comes from ~/.config/hass-cli/env, never from the process environment.

## Plan
Planner (Opus, Lane 2 confirmed: deploy, live config write, automation deletion, credentials). Coder: codex. Rev 4, 2026-10-18 (design rounds 1-3 and the arbiter FIX applied).

Planner card fix: the four `test -s deploy/<id>.retired.json` lines were removed from Done when. They ran no test, and red-green needs a test count for every Done-when command (otherwise count-unknown, exit 6). The four exports are now pinned byte for byte by test 1 in the first Done-when command. The Bad inputs on the size limit and the leftover .new now state the orchestrator's decisions (64 KiB, overwrite).

### Files
- scripts/deploy_package.py (new, Python 3 stdlib only, executable, `#!/usr/bin/env python3`)
- tests/test_deploy_package_script.py (new; pytest; offline; loads the script with importlib inside each test and monkeypatches `_spawn`, `SAMBA_ENV`, `HA_ENV`, `PACKAGE_DIR`, `DEPLOY_DIR`, `stamp`; zero network; never reads `.frugo/` or the real `~/.config` files)
- deploy/1701294514096.retired.json, deploy/1701295072034.retired.json, deploy/1701295128408.retired.json, deploy/1701294978959.retired.json (new; byte-for-byte copies of `.frugo/inputs/exports/<id>.retired.json`; note the inputs have NO trailing newline, so each diff hunk ends with `\ No newline at end of file`)
- Nothing else. ha/packages/livingroom_music.yaml is read only.

### Conventions (from the models)
- `_spawn`, `DeployError(message, status)`, the 0600 Samba auth file (`smbclient //HOST/SHARE -A <file>`, never `-U`) and the upload-`.new`-then-`rename -f` pattern follow ~/AI/projects/home-security/scripts/deploy_video.py (`deploy_ha`, `main`). `_spawn` keeps only the statuses NT_STATUS_NO_SUCH_FILE and NT_STATUS_OBJECT_NAME_NOT_FOUND and never returns or prints command output on failure; drop the ssh/Synology special case; `timeout=120`.
- HA calls follow scripts/deploy-blueprint.sh: the token is written only into a 0600 temp header file (`Authorization: Bearer ...`) and passed as `curl -H @<file>`. The deploy-blueprint.sh model has no check_config call; the endpoint is `POST /api/config/core/check_config` as in deploy_video.py.
- Env files (one parser for both, as deploy_video.py `main`): lines that are blank or whose first non-blank character is `#` are skipped; every other line goes through `shlex.split(line)` (no `comments=True`, so `SMB_PASS=ab#cd` stays `ab#cd`, as bash reads it), a leading `export` word is dropped, and the rest must be one `KEY=VALUE` word (shlex removes matching quotes). Values come from the file only; the process environment is ignored (so an exported HASS_TOKEN in the shell is never used), with one exception: a non-empty HASS_SERVER in the process environment overrides the file's HASS_SERVER (the server URL only; it is still checked by the HASS_SERVER rule below, and the file's HASS_SERVER is then not required). `SAMBA_ENV = ~/.config/hass-samba/env` needs SMB_HOST (`[A-Za-z0-9_.-]+`), SMB_SHARE (`[A-Za-z0-9_-]+`), SMB_USER, SMB_PASS. `HA_ENV = ~/.config/hass-cli/env` needs HASS_TOKEN (always from the file) and HASS_SERVER (unless overridden). Error messages may name a variable, never a value.
- HASS_SERVER (security P1): after `rstrip("/")`, it must pass `re.fullmatch(r"(https?)://([^/:]+)(:\d+)?", server)`; requests use `server + path`. `https` is allowed for any host. Plain `http` is allowed only when the host is an IPv4 address inside 100.64.0.0/10 (`ipaddress.ip_address(host) in ipaddress.ip_network("100.64.0.0/10")`): that is the Tailscale route, and WireGuard encrypts the hop (memory reference_ha_direct_tailscale_route). Any other http host, or anything else, is refused before any `_spawn`.
- Private files: the auth file and the header file are created inside one `tempfile.TemporaryDirectory()` with `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)` wrapped in `os.fdopen(fd, "w")`.
- One HA helper: `ha(method, path)` runs `_spawn(["curl", "-q", "--noproxy", "*", "-sS", "--max-time", "60", "-o", <tmp body file>, "-w", "%{http_code}", "-H", "@" + <hdr file>, "-H", "Content-Type: application/json", "-X", method, server + path] + (["--data", "{}"] if method == "POST" else []))` and returns `(int(status), body_text)`. `-q` must be the first argument (security P2: no ~/.curlrc, so no ambient trace or verbose setting), followed by `--noproxy` `*` (arbiter FIX: no http_proxy/https_proxy/ALL_PROXY can route the token outside the Tailscale hop; argv only, the env passed to curl is not edited). No `--fail`, so 404 is a status, not an exception; a transport error or timeout raises DeployError. Bodies are never printed.
- Exit codes: 0 ok; 1 refused or failed with the live package unchanged (or a retire step refused or failed); 2 usage error (argparse); 3 packages not enabled in configuration.yaml (stop, no edit); 4 check_config failed and the rollback succeeded; 5 unresolved: the rollback failed, or after a rename error the live file is neither the old nor the new package.

### CLI (exactly three modes, argparse, mutually exclusive, one required)
- `--package livingroom_music [--dry-run]` (choices=("livingroom_music",); `--package` without a value, `--package ""` or another name is a usage error).
- `--retire-automations --yes [--dry-run]` (`--yes` is required unless `--dry-run`; missing it is `parser.error`, exit 2).
- `--verify-retired` (read only).
- There is no id argument: the ids are the constant `SAMUEL = ("1701294514096", "1701295072034", "1701295128408", "1701294978959")`, so a fifth id cannot be given (an extra positional is a usage error). `--yes` or `--dry-run` with `--verify-retired`, and `--yes` with `--package`, are usage errors (simple: reject, no extra meaning).

### Steps (deploy mode)
1. Local checks, before any `_spawn`: `PACKAGE_DIR / "livingroom_music.yaml"` exists, is a regular file, size 1..65,536 bytes. Else print the reason, exit 1. No local YAML parse (check_config is the YAML gate). The file is read once; these validated bytes and their sha256 (`NEW`) are the only package content used afterwards (security P2).
2. `--dry-run`: print the plan (the remote paths of steps 6-9 and "check_config, then Martin restarts Home Assistant"), exit 0. No env file read, no `_spawn`.
3. Read `SAMBA_ENV` and `HA_ENV` (missing file, a directory or other OSError, a bad line, a missing or invalid variable, or a refused HASS_SERVER: exit 1 before any `_spawn`). Create the auth and header files (Conventions).
4. Preflight: `ha("GET", "/api/")` must return 200; a DeployError or any other status is exit 1 with nothing sent over Samba ("HA API not reachable or token refused; nothing uploaded"). Then a baseline `ha("POST", "/api/config/core/check_config")` must be valid (same rule as step 10); otherwise exit 1, "config already invalid; nothing uploaded". Write the validated bytes to a private snapshot `<tmp>/package.yaml` (0600, same os.open rule as the auth file).
5. `get configuration.yaml "<tmp>/configuration.yaml"`; it must match `(?m)^\s+packages:\s*!include_dir_named\s+packages\s*$`, else print "Under homeassistant: add packages: !include_dir_named packages" and exit 3 (no upload). A regex, not a YAML load: home-security packages already live there, this only guards a rare corner.
6. `ls packages/livingroom_music.yaml`: success means `existing`; a not-found status means first deploy; any other failure is exit 1.
7. If `existing`: `BACKUP = "backup-packages/livingroom_music.yaml.bak-" + stamp()` (UTC `%Y%m%dT%H%M%SZ`, same directory as home-security's backups); `mkdir backup-packages` (failure ignored); `ls BACKUP` succeeding means refuse, exit 1, nothing uploaded; not-found continues; `get packages/livingroom_music.yaml "<tmp>/old.yaml"` (keep its sha256, `OLD`); `put "<tmp>/old.yaml" BACKUP`; print `backup: BACKUP`. A failure of that `get` or `put` (or an `ls BACKUP` failure other than not-found): exit 1, no `.new` put, live package unchanged.
8. `put "<tmp>/package.yaml" packages/livingroom_music.yaml.new` (the snapshot, never the repo path; overwrites a leftover `.new`; HA's include_dir_named ignores `*.yaml.new`). Failure: exit 1, no rename, "upload failed; live package unchanged". Then verify the staging copy: `get packages/livingroom_music.yaml.new "<tmp>/staged.yaml"`; its sha256 must equal `NEW`, else (or if the get fails) exit 1, no rename, "staged upload differs; live package unchanged". This replaces the rev 2 `ls` size check.
9. `rename packages/livingroom_music.yaml.new packages/livingroom_music.yaml -f`. On a DeployError (failure or timeout; the server may have done the rename and lost the reply) reconcile once (security P1): `get packages/livingroom_music.yaml "<tmp>/after.yaml"`.
   - its sha256 equals `NEW`: print "rename reply lost; new package installed" and continue with step 10;
   - it equals `OLD` (existing), or the get is not-found (first deploy): print "rename failed; live package unchanged; .new left in place", exit 1;
   - anything else (other bytes, or the get fails another way): print "rename result unresolved; check packages/livingroom_music.yaml by hand" (plus `backup: BACKUP` when existing), exit 5.
10. `ha("POST", "/api/config/core/check_config")`: valid only if status 200 and the JSON body has `result == "valid"`. A DeployError, another status, bad JSON or another result is a failed check.
11. Failed check: automatic rollback, covered by Martin's OK for this deploy run (security P1, see Live steps). `existing`: `put "<tmp>/old.yaml" packages/livingroom_music.yaml.new`; `get` the staged `.new` back and require sha256 `OLD` (else exit 5, no rename); the same rename; then `get packages/livingroom_music.yaml` and require sha256 `OLD` (else exit 5); first deploy: `del packages/livingroom_music.yaml`. Rollback ok: print "check_config failed; package rolled back", exit 4. Any rollback step fails: print "rollback failed; restore from BACKUP" (first deploy: "delete packages/livingroom_music.yaml by hand"), exit 5. No reconcile inside the rollback (rare corner; exit 5 already means "check by hand"). Neither prints the restart line.
12. Valid: print "check_config: valid" and, as the last line, `Martin: restart Home Assistant`, exit 0. The script never calls `/api/services/...` and never restarts or reloads HA.

### Steps (retire and verify modes)
1. Retire, before any `_spawn`: for each id in SAMUEL, `DEPLOY_DIR / f"{id}.retired.json"` exists, is non-empty, parses as JSON and its `id` equals the filename id; any failure: exit 1, no HA call.
2. Retire `--dry-run`: print the four `DELETE /api/config/automation/config/<id>` lines, exit 0, no env read, no `_spawn`.
3. Retire: read `HA_ENV` (deploy step 3, header file only). Preflight = `ha("GET", "/api/")` must be 200 only (no check_config, no snapshot); otherwise exit 1, nothing deleted.
4. Retire drift check (correctness P2), for all four ids before any DELETE: `ha("GET", f"/api/config/automation/config/{id}")`. 404: print "<id> already removed" and skip it. 200: the parsed body must equal the parsed export, else print "<id> differs from deploy/<id>.retired.json; nothing deleted" and exit 1. Any other status, bad JSON, or a DeployError (no reply or timeout; print "GET <id> failed"): exit 1, nothing deleted.
5. For each id that was 200, in order: `ha("DELETE", ...)`: 200 prints "deleted <id>"; 404 prints "<id> already removed"; anything else prints "DELETE <id> failed (status N)" and exits 1 without sending the rest; a DeployError prints "DELETE <id> no reply; run --verify-retired" and exits 1 without sending the rest. Then run verify.
6. Verify (also the whole of `--verify-retired`): `ha("GET", ...)` for each id: 404 prints "<id> gone"; 200 prints "<id> still present"; other prints "GET <id> failed (status N)"; a DeployError prints "GET <id> failed". Exit 0 only if all four are 404, else 1. Verify sends only GETs (no preflight needed).

### Test list (tests/test_deploy_package_script.py)
Loading: a plain helper `load()` (not a fixture) imports scripts/deploy_package.py with importlib, and every test calls it in its own body, so before the patch every test fails with FileNotFoundError/ImportError as a failed test (correctness P2). The fake is a small remote-state model: a dict of remote paths to bytes. smbclient commands are matched by the `-c` prefix (`get` writes the remote bytes to the quoted local path, or raises not-found; `ls` succeeds and lists name and size, or raises not-found; `mkdir`, `put`, `rename -f` (moves the bytes), `del`). Failure injection per command (raise DeployError, or for "lost reply" do the rename and then raise). curl calls are matched by `-X` and URL path (the fake writes the configured body to the `-o` path and returns the status). Every argv is recorded, plus the mode of the `-A` and `-H @` files at call time. Fake credentials come from `os.urandom(...).hex()` (as the home-security tests do). Test sources hold no literal IPv4 address: build them by concatenation, e.g. `"100." + "116.73.57"`. An autouse fixture runs `monkeypatch.delenv("HASS_SERVER", raising=False)` for every test (correctness P2: the shell running the tests may export it); only test 32 sets it. Each test fails before the patch and passes after.
1. `test_retired_exports_pinned` (replaces the former `test -s` lines): for each id, sha256 of `deploy/<id>.retired.json` equals 1701294514096 cc419360994a4f3090634f8947332c869e61f239173ff669019f30781ed7ded7, 1701294978959 dfcbbf36cb9cac091ab934dbebd1f6c967a66dae6e7ce4bd79fdad909f1aac4a, 1701295072034 0f92757cfef9dfdb4f94bb0b82a616a82e2fc2338255ea6167a72279038874e0, 1701295128408 6f9b378a57f5d8b329bb5887e4e7ee97354054c089cff376f023a35240ebbe97 (hashes of the orchestrator's exports, taken by the planner); and readable pins: JSON `id` equals the filename id; alias equals `Sonos On Samuel`, `Sonos Off Samuel`, `Sonos 20% Volume Samuel`, `Sonos 10% Volume Samuel` respectively; keys are exactly {action, alias, condition, description, id, mode, trigger}; every trigger has device_id dfad9901619a42507889cad7dfc9b8d9. This test does not call `load()`; it fails before the patch because the files are absent.
2. `test_deploy_existing_package_happy_path`: call order is GET /api/, POST check_config (baseline), get configuration.yaml, ls package, mkdir, ls BACKUP, get package, put BACKUP, put `.new` (from the snapshot path), get `.new`, rename `-f`, POST check_config; exit 0; the remote live file equals the local package bytes and BACKUP equals the old bytes; last stdout line is `Martin: restart Home Assistant`; no curl URL contains `/api/services` and no DELETE.
3. `test_first_deploy_without_existing_package`: no remote file; no backup commands; baseline check, put, get `.new`, rename, check valid; exit 0.
4. `test_rejects_other_package`: `--package security_core` exits 2, zero `_spawn`.
5. `test_rejects_missing_or_empty_package` (3 cases: `[]`, `["--package"]`, `["--package", ""]`): exit 2, zero `_spawn`.
6. `test_refuses_missing_or_empty_package_file` (2: absent, 0 bytes): exit 1, zero `_spawn`.
7. `test_refuses_oversize_package_file`: 65,537 bytes exits 1 with zero `_spawn`; 65,536 bytes with `--dry-run` exits 0.
8. `test_check_config_invalid_rolls_back` (2: existing, first deploy): body `{"result": "invalid", "errors": "<marker>"}`; existing: the live file is back to the old bytes; first: the live file is gone; exit 4; stdout has "rolled back", not the marker and not "restart".
9. `test_leftover_new_file_is_overwritten`: the remote starts with a stale `.new`; after the run the live file equals the local package bytes; no refusal; exit 0.
10. `test_refuses_existing_backup_path`: the remote already has BACKUP; exit 1; no `put`, no `rename`.
11. `test_refuses_bad_samba_or_ha_env` (14: Samba env absent; Samba env path is a directory; each of SMB_HOST, SMB_SHARE, SMB_USER, SMB_PASS missing; SMB_HOST `a/b`; SMB_SHARE `a b`; HA env absent; HASS_SERVER missing; HASS_TOKEN missing; HASS_SERVER `ftp://x`; HASS_SERVER `"http://" + "192.168." + "1.5:8123"`; HASS_SERVER `http://ha.local:8123`): exit 1, zero `_spawn`; stdout and stderr contain none of the fake values.
12. `test_env_parse_export_quotes_and_ignores_process_env`: env files with `export SMB_PASS='...'` and `HASS_TOKEN="..."` lines, a `# comment` line, and an SMB_PASS value containing `#` in the middle (kept whole); the process environment holds a different HASS_TOKEN and SMB_PASS; the header and auth files hold the file values, not the environment ones; exit 0.
13. `test_server_scheme_accepted` (3: `https://ha.example:8123`, `"http://" + "100." + "116.73.57:8123"`, `https://ha.example:8123/`): the deploy runs, every curl URL starts with that server without its trailing `/`, and no URL contains `//api`; exit 0.
14. `test_preflight_failure_uploads_nothing` (4: GET /api/ returns 401, curl raises DeployError, the baseline check_config returns invalid with stdout "config already invalid"; and a `--retire-automations --yes` run whose GET /api/ returns 401): exit 1; zero smbclient calls; the retire case sends zero DELETE and no POST. The fake's check_config answers are a per-test sequence (baseline first), so tests 8, 17 and 18 return valid for the baseline and their configured answer for the second call.
15. `test_samba_failure_before_or_during_upload` (2: the get of configuration.yaml fails, the `.new` put fails): exit 1; no rename, no check_config; the live file is unchanged.
16. `test_staged_upload_corruption_no_rename`: the fake stores a `.new` of the same size with one byte changed; exit 1; no rename; live file unchanged.
17. `test_rename_error_reconciled` (4): (a) existing, rename fails and the live file is still old: exit 1, "unchanged", no check_config; (b) first deploy, rename fails, no live file: exit 1, "unchanged"; (c) commit then lost reply (the fake renames, then raises): "new installed", check_config runs, exit 0 with the restart line; (d) the live file afterwards matches neither: exit 5, "unresolved", no check_config.
18. `test_check_config_unreachable_or_timeout_rolls_back` (2: curl raises DeployError, status 502): rollback runs, exit 4.
19. `test_rollback_failure` (2: existing with the rollback rename failing, stdout contains BACKUP; first deploy with the `del` failing, stdout says "delete packages/livingroom_music.yaml by hand"): exit 5; no "restart".
20. `test_dry_run_deploy_and_retire` (2: `--package livingroom_music --dry-run`, `--retire-automations --dry-run`): exit 0, zero `_spawn`; output names `packages/livingroom_music.yaml`, or the four DELETE ids.
21. `test_rejects_unknown_or_extra_argument` (6: `--package livingroom_music --bogus`, `--retire-automations --yes 1234`, `--package livingroom_music --retire-automations`, `--verify-retired --yes`, `--verify-retired --dry-run`, `--package livingroom_music --yes`): exit 2, zero `_spawn`. The `1234` case is the bad input "id not one of the four" (no id argument exists).
22. `test_retire_requires_yes`: `--retire-automations` alone exits 2, zero `_spawn`.
23. `test_retire_deletes_exactly_four_then_verifies`: pre-GET returns each export's JSON, DELETE 200, final GET 404; DELETE URLs are exactly the four SAMUEL paths in order, each after all four pre-GETs; no POST; exit 0.
24. `test_retire_404_reported_already_removed`: the pre-GET returns 404 for one id; stdout has "<id> already removed"; no DELETE for that id; the other three are deleted; exit 0.
25. `test_retire_refuses_drift_or_bad_status` (3: one pre-GET body differs from its export in one field; one pre-GET returns 500; one pre-GET raises DeployError, stdout "GET <id> failed"): exit 1; zero DELETE.
26. `test_retire_delete_or_final_get_fails` (2: DELETE 200 for all and final GET 200 for one id, stdout "<id> still present"; the second DELETE raises DeployError, stdout "DELETE <id> no reply; run --verify-retired" and no third or fourth DELETE): exit 1.
27. `test_retire_refuses_missing_or_bad_export` (3, on a tmp DEPLOY_DIR: one file absent, one empty, one with a mismatched id): exit 1, zero `_spawn`.
28. `test_verify_retired_is_read_only` (2: all 404 exits 0 and one 200 exits 1; one GET raises DeployError, stdout "GET <id> failed", exit 1): only GET calls.
29. `test_credentials_never_in_argv_or_output`: over a happy deploy and a retire run, no recorded argv element contains the fake SMB_USER, SMB_PASS or HASS_TOKEN; smbclient always has `-A` and never `-U`; the `-A` and `-H @` files had mode 0600 at call time and are gone afterwards; stdout and stderr contain none of the fake values.
30. `test_curl_ignores_ambient_config` (2: no proxy variables; `http_proxy`, `HTTPS_PROXY` and `ALL_PROXY` set in the process environment via monkeypatch): in every recorded curl argv, `argv[1] == "-q"` and `argv[2:4] == ["--noproxy", "*"]`.
31. `test_packages_not_enabled_stops`: configuration.yaml without the packages line; exit 3; no `put`.
32. `test_hass_server_env_override` (2): the HA env file has `https://ha.example:8123`; (a) process HASS_SERVER `"http://" + "100." + "116.73.57:8123"`: every curl URL starts with the override, exit 0; (b) process HASS_SERVER `http://ha.local:8123`: refused, exit 1, zero `_spawn`.
33. `test_process_hass_token_ignored`: the HA env file has HASS_SERVER but no HASS_TOKEN, and the process environment has HASS_TOKEN: exit 1, zero `_spawn`, the process token appears in no file, argv or output.
34. `test_source_change_after_validation_not_uploaded`: the fake changes the local package file (same size, other bytes) on its first call (GET /api/); the run exits 0 and the remote live file equals the originally validated bytes, not the changed file.
35. `test_rollback_staging_corruption`: existing package, the second check_config is invalid, and the fake corrupts the rollback `.new` (same size, one byte changed); exit 5; no rollback rename; stdout contains BACKUP; no "rolled back" and no "restart".

Collected test count: 77 test ids (35 functions; the parametrized ones as listed). RED applies only this test file: all 77 fail (76 on the missing script, test 1 on the missing exports). GREEN: all 77 pass.
Not offline-testable, covered by the live walk-through (the package behaviour itself is tested in ha/tests by the core and remote-kids cards): "Approve after 2 min or stale push" and "live check before the restart". Rare corners left without a test (design round 2 P3s): an env file with mode 000 (the directory case covers OSError), a reconcile inside the rollback, an `ls` of the package failing with a status other than not-found (step 6), a failing `get` of the old package or `put` of BACKUP (step 7, exit 1 stated above), and a failing `get` of the staged `.new` (step 8).
Done-when: command 1 runs the whole tests/ suite including the 77 new test ids; command 2 runs the core card's ha/tests unchanged (at least one test, green before and after).

### Live steps that need Martin's own OK (orchestrator, after card 3 is shipped and this card is merged as Martin approves)
1. OK 1: the deploy run `--package livingroom_music`. This OK explicitly includes the script's automatic rollback of this same package if check_config fails (restore the backup, or delete a first-deploy file). The approval request must say so.
2. Martin restarts Home Assistant himself.
3. OK 2: `--retire-automations --yes` (drift check, four DELETEs, then the GET check).
4. OK 3: the live check with Martin present.
Any other write (a re-POST of an export, a manual Samba restore or delete of the package) is a further separate OK.

### Live walk-through checklist (orchestrator with Martin; results with Amsterdam times go into Result)
- [ ] Pre (read only, correctness P1): card 3 (2026-10-18-livingroom-music-remote-kids) is shipped, and this branch contains it: git merge-base --is-ancestor <card 3 head commit> HEAD passes. The sha256 of ha/packages/livingroom_music.yaml on this branch equals the one on main and is written into Result before OK 1. Both Done-when commands are green on this branch. GET each Samuel id and compare it as parsed JSON with deploy/<id>.retired.json (drift: stop). The Samba add-on is reachable from the VPS. If any of this fails: no deploy, and no retire.
- [ ] OK 1, deploy (rollback included, see above): output redirected to a scratchpad file and secret-scanned, only a scanned tail shown. Expect exit 0 and the last line `Martin: restart Home Assistant`. Exit 3: stop and tell Martin (no configuration.yaml edit). Exit 1 or 4: stop and report. Exit 5: stop, name the backup path, and say the live file needs a check by hand.
- [ ] Martin restarts HA and says so. The live check does not start before he does.
- [ ] Read only after restart: input_boolean.livingroom_music_hands_off exists and the package automations (ids livingroom_music_*) are listed with state on. Missing: stop (the package did not load), no retire and no live check.
- [ ] OK 2, retire: never before the pre-check, OK 1 and the read-only check above have passed; run right after them (the Samuel automations share the Music Remote buttons and would fight the volume ladder); output redirected and scanned; expect four "deleted" or "already removed" lines and four "gone"; then `--verify-retired` (read only) shows all four gone. This is the goal's final GET.
- [ ] OK 3, live check, Martin at the speaker (0.30 is loud): walk in, Lazy Sunday starts at 0.15; LG TV on pauses it, LG off resumes the same track; On starts Pairilijst; brighten to 0.25, then once more: the approval push reaches Martin's Fold and Savannah's S25 and the volume stays at 0.25; Approve gives 0.30 and the other phone's push clears. A late (after 2 min) or stale Approve: Deny applies and is recorded. Then dim back down. notify.mobile_app_pixel_9_pro_xl is never used; nothing on the read-only AV and alarm entities is called.
- [ ] A failure in the live check: Martin turns Hands-off on in the HA app (no write by the orchestrator); a package fix is a new round; restoring the old remote is a re-POST of the four exports, each under its own OK.

## Result
Deploy script and offline tests are built and uncommitted on branch frugo/2026-10-18-livingroom-music-deploy (worktree Blueprints_Home-wt/lm-deploy, based on the core card commit 2bd5012): scripts/deploy_package.py (checked Samba upload with rollback; --retire-automations --yes; --verify-retired), tests/test_deploy_package_script.py (87 offline cases) and the four deploy/<id>.retired.json GET exports (byte-identical to the 2026-10-18 live GET, pinned by sha256). Both Done-when commands pass (whole tests suite 722; HA tests 104), red on the clean base. Lane 2: three design rounds, one design arbiter FIX, one code fix round; Opus correctness P3 only, Codex security PASS. NO live step has run: no upload, no HA restart, no DELETE, no live check (each needs Martin's own OK, in this order: deploy run incl. its automatic rollback; Martin restarts HA; retire the four automations right after the restart; live check with Martin). Pre-check before OK 1: card 3 shipped, this branch contains it, sha256 of ha/packages/livingroom_music.yaml recorded here. Card 3 is parked on an arbiter decision, so the live steps cannot start yet.
Open P3:
- Opus: every HA call writes to the same curl body file and it is not deleted between calls; an empty reply body could read the previous body (HA always sends JSON, so unlikely). Fix: unlink before each spawn.
- The live-only bad inputs (Approve after 2 min or from a stale push gives Deny; no live check before the restart) are covered only by the walk-through checklist in the plan; not counted as covered until the live steps are recorded here with Amsterdam times.
- Live order: retire the four Samuel automations right after the restart and before the live check; they share the remote buttons with the new package.
- .frugo/inputs/ (untracked) stays out of the commit and is deleted after the card closes.

Live record (2026-10-19, Amsterdam times; Martin present at the speaker for the walk-through):
- Shipped to main: scripts/deploy_package.py and the four deploy/<id>.retired.json at cfd4c14 (rebased on 916bc50). Pre-check passed: the branch contained card 3b, package sha256 18d67c07...9f50e matched main, both Done-when commands green (780 tests, 303 HA), the four Samuel exports identical to the live GET, Samba host reachable.
- 14:50 deploy run, exit 0, check_config valid, package sha256 18d67c07...9f50e; Martin restarted HA. Read-only check: 10 package automations on, helpers and scripts loaded.
- 14:54 retire run: four automations deleted (1701294514096, 1701295072034, 1701295128408, 1701294978959) and `--verify-retired` showed all four gone. The first attempt used the shell's HASS_SERVER (the Nabu Casa URL), failed on TLS before changing anything, and was re-run over the Tailscale route (HASS_SERVER=http://100.116.73.57:8123).
- 16:57 and 18:04: two further deploy runs (start volume 0.07 with sha256 e82c88d3...5ed8; audible push with sha256 774d5f9a...), each exit 0, check_config valid, followed by an HA restart by Martin and a read-only load check.
- Live walk-through, passed: Lazy Sunday started by itself at the new start level; LG TV on paused the music and TV off resumed the same track; On started Pairilijst (kids time on, 30 min); brighten reached 0.20 and the next brighten opened the Approve/Deny push (2 min timer); Approve gave 0.25, one more brighten gave 0.30; five dims went back down to 0.07 (17:14 to 17:16). After the loud-push deploy the push arrived with sound and as a heads-up on Martin's Fold (about 18:15).
- Not exercised live (covered only by the offline tests): a late (after 2 min) or stale Approve; confirmation that Savannah's S25 push cleared after Martin approved; the late-night quiet-hours stop.
- Changes made on the way, each shipped as its own card on main: start volume 0.07 and approval above 0.20 (657a6c4, issue #55), audible high-priority push (23ddc87, issue #56).
