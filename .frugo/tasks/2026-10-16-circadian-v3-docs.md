---
id: 2026-10-16-circadian-v3-docs
title: Livingroom FP300 docs v3.0.0
goal: livingroom-fp300-dual-presence
issue: none
status: done
lane: 2
coder: codex
step: codex
fix_rounds: 0
---

## Goal
README.md and requirements_circadian.md describe the v3.0.0 two-sensor circadian living room blueprint, and a new docs test pins that. Both files name v3.0.0, both presence inputs, the late-night inputs (23:00, 06:30, 1 min), the dog stay-on note and the FP300 setup. They drop the single-sensor and 300 lx text, and the test checks that every input key in circadian_livingroom.yaml appears in requirements_circadian.md. The test is RED on the current v2.2.0 docs and GREEN after the edit.

## Done when (runnable)
- `env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests/test_circadian_livingroom_docs.py -q`
- `env -u HASS_TOKEN PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ~/.local/share/home-security/ha-test-venv/bin/python -m pytest -p no:cacheprovider tests -q`

## Files likely touched
- README.md (section "## Circadian Living Room Lights Blueprint", about lines 55-76)
- requirements_circadian.md (sections 2, 3, 4.1 and 5; FP300 placement note next to section 6; line 97 in section 7: lux_threshold becomes lux_on_threshold)
- tests/test_circadian_livingroom_docs.py (new)
- Read only: circadian_livingroom.yaml (source of input keys, not edited here)
- Read only: tests/test_bedroom_precool_structure.py (HassLoader for the !input tags; import HassLoader by name, not the module)
- Read only: scripts/deploy-blueprint.sh (usage line for the README install step; not run)

## Bad inputs to handle
- README.md missing, or the "## Circadian Living Room Lights Blueprint" heading missing or duplicated (fail, do not pass on an empty slice)
- requirements_circadian.md missing or empty
- circadian_livingroom.yaml missing or not parseable with HassLoader
- Blueprint with no input block (no keys to check, so fail rather than pass vacuously)
- Stale text back in either file: "300 Lux", "lux_threshold", "Presence:** Aqara FP2 (binary_sensor)", "utilizes the Aqara FP2 (or any lux+presence sensor)"
- A circadian_livingroom.yaml input key missing from requirements_circadian.md (the drift check)
- v3.0.0 missing from either file
- Late-night text (23:00, 06:30, 1 min) missing from either file
- Dog stay-on note missing from either file

## Risk flags
- deploy: README documents scripts/deploy-blueprint.sh for install and update. This card runs no deploy and makes no Home Assistant write.
- secrets: README must not contain a token, a credential value, or the contents of ~/.config/hass-cli/env.
- workflow rules: test-first. The docs test must run and fail against the current v2.2.0 docs before any edit; that output goes in Result.
- dependency: depends on card 2026-10-16-circadian-v3-dual-presence-blueprint (status draft). circadian_livingroom.yaml is still v2.2.0 with presence_entity, so GREEN needs that card's input names.

## Constraints carried over
- Lane 2 (risk scan). Only Martin may lower it.
- Off path: both sensors clear. presence_timeout is 5 min. Inside 23:00 to 06:30 (crosses midnight) late_night_timeout is 1 min. A countdown whose 1-min mark passed before 23:00, or whose 1-min mark falls after 06:30, finishes on presence_timeout (a clear that began just before 23:00 can still turn off at its 1-min mark just after 23:00). No extra boundary trigger. Document this boundary behaviour.
- Turn-on: either sensor on.
- Lux: FP2 illuminance only. The blueprint defaults are 150 lx on, 400 lx off for 5 min; an instance may override them (the live instance uses 394/611). FP300 lux is not read. Document the defaults and that they are per-instance inputs.
- FP300 counts like FP2 at all hours. The dog on its bench keeps the lights on through the FP300, including at night. Accepted and documented as still being tested. No cap or zone logic.
- FP300 unavailable or unknown counts as clear. After 30 min, one push goes to each notify target after the light calls.
- FP300 setup (documented, set by hand): Zigbee2MQTT, presence source mmWave+PIR, absence_delay_timer 60 s. About 2 min from last motion to off at night (60 s plus 1 min).
- Night profile stays 22:00 to 06:00 at 20 percent, independent of the late-night window.
- override_entity unchanged. No TV or media_player input.
- Do not claim the live instance is migrated; the instance card does that.
- Install text names the prerequisites the script checks (hass-cli, jq, PyYAML via PYTHON, ~/.config/hass-cli/env) and the HA path leviemartin/circadian_livingroom.yaml. Write no values.
- Test imports HassLoader only, and expectations come from the goal's contract, not from the YAML's current text.

## Out of scope
- Blueprint and instance changes: circadian_livingroom.yaml, deploy/, instance JSON, and the dependency card's work.
- Other README sections (LG AC, bathroom ventilator, bedroom fan, etc.).
- Running deploy-blueprint.sh, dry-run or live, and any Home Assistant write.
- Dog cap, time window or zone exclusion; FP300 lux or other readings; zone split; night quiet window.
- Editing tests/test_bedroom_precool_structure.py or any other existing test file.
- New docs file, or a v2 copy.
- Requirements sections other than 2, 3, 4.1, 5, the section 6 note, and line 97 (see Open questions).

## Decisions (orchestrator, 2026-10-16; Martin can revert any)
- Dependency: this card starts from the branch where card 2026-10-16-circadian-v3-dual-presence-blueprint is committed. Input names: presence_fp2, presence_fp300, late_night_start, late_night_end, late_night_timeout, notify_targets (confirmed by that card's plan).
- Section 7 line 97 changes `lux_threshold` to `lux_on_threshold` (in scope).
- The every-key check covers the whole of requirements_circadian.md: add an inputs table (key, default, meaning) so every blueprint input key appears there.
- Dog stay-on wording pinned by the test: each file contains "dog", "bench" and "FP300"; the README says the stay-on is still being tested.
- The test also reads the defaults of late_night_start, late_night_end, late_night_timeout and presence_timeout from the YAML and compares them with the docs text, so they cannot drift.
- README install uses the real names: HA path leviemartin/circadian_livingroom.yaml and instance payload deploy/circadian_livingroom_1767031159524.json (created by card 2026-10-16-circadian-v3-instance-migration); keep the manual import as an alternative. No values from the env file.
- This card replaces the empty draft stub on the same subject; there is no separate stub card in this goal.
- The test runs with the sandbox venv in Done-when; no other interpreter is needed.
- Keep Files-list parentheticals short (the card parser treats an over-long entry as a path).

## Open questions
- none

## Plan
<!-- Planner only: exact files incl. test files, steps, and the test list (one test per
     "Done when" item and per bad input). -->
Planner: Opus. Lane 2 stays (docs carry the deploy command and the credentials path; only Martin may lower it). Coder: `codex`.

Dependencies (design review, 2026-10-16): this card starts from the branch where BOTH card 2026-10-16-circadian-v3-dual-presence-blueprint (v3.0.0 YAML) and card 2026-10-16-circadian-v3-instance-migration (creates `deploy/circadian_livingroom_1767031159524.json`) are committed. Test 16 checks that file exists.

Boundary wording (design review P2, overrides the "already running at 23:00" phrasing in Constraints): the short trigger checks the window at its own 1-min mark, so a clear that began at 22:59:30 turns off at 23:00:30. Only a countdown whose 1-min mark passed before 23:00 finishes on presence_timeout.

### Files (exactly these three)
1. `tests/test_circadian_livingroom_docs.py`: new.
2. `README.md`: replace the body of "## Circadian Living Room Lights Blueprint" only (from that heading to the `---` before "## LG AC Sleep & Movie Mode Blueprint"). The heading line stays, exactly once. No other README section changes.
3. `requirements_circadian.md`: sections 2, 3, 4.1, 5, a new `### 6.1.` after the section 6 bullets, and the `is_daylight_enough` line in section 7. Sections 1, 4.2, both 4.3s and 6's own bullets stay byte-identical.

Read only: `circadian_livingroom.yaml` (v3.0.0 on this card's base; contract in card 2's Plan), `tests/test_bedroom_precool_structure.py` (`from test_bedroom_precool_structure import HassLoader`, nothing else), `scripts/deploy-blueprint.sh`.

### Steps (test-first)
1. Write the test file (list below). Every file read happens inside helper functions called from test bodies, never at module level or in fixtures, so a missing or stale doc is a FAILED test, not a collection error.
2. Run Done-when 1: RED on the base (expected list under "RED on the base").
3. Edit README.md and requirements_circadian.md with the text below. Plain ASCII in new text is fine; keep the existing emoji bullets that stay.
4. Run both Done-when commands; both GREEN.

### README.md circadian section (target text; wording may be tightened, every pinned phrase must stay verbatim)
Below the unchanged heading line (level 2, "Circadian Living Room Lights Blueprint"; not repeated here because the card parser splits on level-2 headings):
```
### Overview
Living room lighting that follows presence, the sun and the family routine (v3.0.0). Two presence sensors count as one room: the Aqara FP2 (`presence_fp2`, also the lux sensor) and the Aqara FP300 on the couch (`presence_fp300`). Either sensor on turns the lights on; they go off only when both sensors are clear.

### Features
*   (keep the four existing bullets: Native Circadian Algorithm, Hue Infuse Support, Native Hue Effects, Routine Overrides)
*   **Dual presence (v3.0.0):** Either sensor on turns the lights on. The lights go off only after both sensors are clear (off, unavailable or unknown) for `presence_timeout` (default 5 min).
*   **Late-night quick off:** Between 23:00 and 06:30 (`late_night_start` / `late_night_end`, crossing midnight) the lights go off 1 min (`late_night_timeout`) after both sensors are clear. A both-clear countdown whose 1-min mark passed before 23:00 finishes on `presence_timeout` (up to 4 min later than the late-night delay); a clear that began just before 23:00 can still turn off at its 1-min mark just after 23:00. A countdown whose 1-min mark falls at or after 06:30 also finishes on `presence_timeout`; there is no extra trigger at the window edges. The Night profile (22:00-06:00, 20 %) is independent of the late-night window.
*   **Dog on the bench:** The FP300 counts like the FP2 at all hours, so the dog lying on its bench keeps the FP300, and so the lights, on, also at night. This is accepted and still being tested; there is no cap or zone exclusion.
*   **FP300 offline push:** An FP300 that is unavailable or unknown counts as clear, so the lights follow the FP2 alone. After 30 min offline, one push goes to each `notify_targets` entry (full `notify.<name>` services, others ignored; empty, the default, disables it). The push runs after the light calls, also while the override is on. A target that does not exist aborts the run at the push step; check it exists after editing.
*   **Daylight Harvesting:** FP2 illuminance only; FP300 lux is not read.
    *   **Auto-ON:** lights turn on when someone is present and the FP2 reads below 150 lx (`lux_on_threshold`), or when you are already sitting there and it gets darker than that.
    *   **Auto-OFF:** lights turn off when the FP2 reads above 400 lx (`lux_off_threshold`) for 5 min (`lux_off_duration`).
    *   These are the blueprint defaults; each instance can set its own values (per instance).
*   (keep the existing Seamless Transitions bullet)

### Requirements
*   Aqara FP2: occupancy `binary_sensor` and its illuminance sensor
*   Aqara FP300: occupancy `binary_sensor`, set up as below
*   Hue bulbs and/or Hue Infuse ceiling lights; `sun.sun`
*   Optional: an override switch or `input_boolean`; `notify.*` services for the offline push

### FP300 setup (Zigbee2MQTT)
Set by hand in Zigbee2MQTT; the blueprint writes no device settings.
*   Presence source: mmWave + PIR.
*   `absence_delay_timer`: 60 s.
At night this gives about 2 min from the last motion on the couch to lights off (60 s absence delay plus the 1 min `late_night_timeout`), when the FP2 is already clear.

### Installation
1. Update the blueprint and the living room instance with the deploy script, dry-run first:
   `bash scripts/deploy-blueprint.sh --dry-run circadian_livingroom.yaml leviemartin/circadian_livingroom.yaml deploy/circadian_livingroom_1767031159524.json`
   `bash scripts/deploy-blueprint.sh circadian_livingroom.yaml leviemartin/circadian_livingroom.yaml deploy/circadian_livingroom_1767031159524.json`
   The script needs `hass-cli` and `jq` on PATH, PyYAML in the interpreter named by `PYTHON` (default `python3`), and Home Assistant credentials in `~/.config/hass-cli/env` (never in this repo). v3.0.0 removes `presence_entity`: an instance must set `presence_fp2` and `presence_fp300` before it is updated, or the dry-run refuses it.
2. Or import it by hand: (keep the existing badge link and the raw URL line unchanged).

Full contract: `requirements_circadian.md`.

---
```
No claim that the live instance is migrated. No credential values, no variable assignments.

### requirements_circadian.md edits
**Section 2 (Core Features).** Replace the "Presence-Based Switching" bullet with:
- `*   **Version:** v3.0.0 (dual presence: FP2 + FP300).`
- `**Presence-Based Switching (dual presence):**` with sub-bullets: Turn ON when either sensor reports presence: Aqara FP2 (`presence_fp2`) or Aqara FP300 on the couch (`presence_fp300`). / Turn OFF only when both sensors are clear (off, unavailable or unknown) for `presence_timeout` (default 5 min). / Late-night window: between 23:00 (`late_night_start`) and 06:30 (`late_night_end`), crossing midnight, the off delay is 1 min (`late_night_timeout`, 1-60). The end is exclusive; start equal to end means no window. / Boundary: the same sentences as the README ("A both-clear countdown whose 1-min mark passed before 23:00 finishes on `presence_timeout` (up to 4 min later than the late-night delay); a clear that began just before 23:00 can still turn off at its 1-min mark just after 23:00. A countdown whose 1-min mark falls at or after 06:30 also finishes on `presence_timeout`; there is no extra trigger at the window edges."). / Dog: one line, "The FP300 counts like the FP2 at all hours, so the dog on its bench keeps the FP300, and so the lights, on, also at night. Accepted, still being tested; no cap or zone logic."
- Keep the Circadian, Toddler and Hue Effects bullets. In "Smart Brightness Schedule" change `**Late Night:** Ultra-dim (~10-20%).` to `**Night (22:00-06:00):** Ultra-dim (~10-20%), independent of the late-night window.`
- Replace the "Lux Threshold (Daylight Savings)" bullet (the 300 Lux text) with: **Lux Thresholds (Daylight Harvesting):** FP2 illuminance only; FP300 lux is not read. Lights turn on only below `lux_on_threshold` (default 150 lx) and turn off above `lux_off_threshold` (default 400 lx) for `lux_off_duration` (default 5 min). These are blueprint defaults; each instance may override them (per instance).

**Section 3 (Hardware & Inputs).** Replace the Presence and Illuminance lines with: `**Presence:** two occupancy binary_sensors: Aqara FP2 (`presence_fp2`) and Aqara FP300 on the couch (`presence_fp300`, via Zigbee2MQTT).` / `**Illuminance:** Aqara FP2 only (sensor.lux); FP300 lux is not read.` Add `**Notifications:** optional `notify.*` services (`notify_targets`) for the FP300 offline push.` Lights, Sun and Manual Override lines stay.

**Section 4.1 (Inputs).** Heading line `### 4.1. Inputs` stays. Replace the bullets with one sentence ("All blueprint inputs of v3.0.0, in blueprint order. `required` means the input has no default.") and this table (Default cell: the YAML default in backticks, a list as `[]`, or the bare word `required`):

| Key | Default | Meaning |
|---|---|---|
| `hue_bulbs` | `[]` | Hue ambient/colour bulbs |
| `hue_ceiling` | `[]` | Hue Infuse ceiling lights (main and backlight) |
| `ceiling_brightness_scale` | `0.6` | Dims the ceiling lights relative to the bulbs |
| `presence_fp2` | required | Aqara FP2 occupancy binary_sensor |
| `presence_fp300` | required | Aqara FP300 occupancy binary_sensor (couch) |
| `presence_timeout` | `5` | Minutes both sensors must be clear before off |
| `late_night_timeout` | `1` | Minutes both clear inside the late-night window (1-60) |
| `late_night_start` | `23:00:00` | Start of the late-night window |
| `late_night_end` | `06:30:00` | End of the window (exclusive; may cross midnight; equal to start = no window) |
| `illuminance_entity` | required | FP2 illuminance sensor (FP300 lux is not read) |
| `override_entity` | `[]` | Switch/input_boolean; while on, no light calls |
| `lux_on_threshold` | `150` | Lights turn on only below this lux |
| `lux_off_threshold` | `400` | Lights turn off above this lux... |
| `lux_off_duration` | `5` | ...held for this many minutes |
| `time_dinner` | `18:00:00` | Dinner start |
| `dinner_kelvin` | `3000` | Dinner colour (K) |
| `dinner_bri` | `100` | Dinner brightness (%) |
| `time_toddler` | `19:00:00` | Toddler prep start |
| `toddler_kelvin` | `2200` | Toddler colour (K) |
| `toddler_bri` | `60` | Toddler brightness (%) |
| `time_evening` | `20:00:00` | Evening start |
| `evening_kelvin` | `2700` | Evening colour (K) |
| `evening_bri` | `50` | Evening brightness (%) |
| `evening_effect` | `none` | Evening Hue effect |
| `time_night` | `22:00:00` | Night start |
| `night_kelvin` | `2200` | Night colour (K) |
| `night_bri` | `20` | Night brightness (%) |
| `night_effect` | `none` | Night Hue effect |
| `max_kelvin` | `4500` | Day-mode upper Kelvin |
| `min_kelvin` | `2200` | Day-mode lower Kelvin |
| `notify_targets` | `[]` | Full `notify.<name>` services for the FP300 offline push; others ignored; empty disables |

If the base YAML's keys, order or defaults differ from this table, the YAML wins: fix the table, not the YAML (the test compares them).

**Section 5 (Transition Handling).** Replace "Turn ON Condition" and "Presence Timeout" with: **Turn ON Condition:** either sensor on (FP2 or FP300) AND FP2 lux below `lux_on_threshold` (default 150 lx). / **Presence Timeout:** lights go off when both sensors are clear for `presence_timeout` (default 5 min); each sensor's own timer fires, then the other sensor must have been clear at least as long. / **Late-Night Timeout:** inside 23:00-06:30 the delay is `late_night_timeout` (default 1 min); boundary as in section 2. / **FP300 offline:** unavailable or unknown counts as clear. After 30 min in either state, one push goes to each `notify_targets` entry, after the light calls, also while the manual override is on. Auto-OFF: `If FP2 lux > lux_off_threshold (default 400 lx) for lux_off_duration (default 5 min)...`. Manual Override bullet: add "Off timers that expire while it is on are not replayed." Transitions bullet unchanged.

**Section 6.1 (new, after the section 6 bullets).** The section 6 heading ("Sensor Placement Best Practices (Aqara FP2)") and its bullets stay byte-identical on purpose (out of scope); 6.1 is a short separate note under its own heading `### 6.1. Aqara FP300 (couch) setup` with bullets: paired via Zigbee2MQTT, set by hand (the blueprint writes no device settings) / presence source: mmWave + PIR / `absence_delay_timer`: 60 s / at night about 2 min from the last motion to lights off (60 s plus the 1 min `late_night_timeout`), when the FP2 is already clear / FP300 lux is not read.

**Section 7.** `1.  `is_daylight_enough`: `lux_sensor > lux_on_threshold`` (only `lux_threshold` changes).

### Test list (`tests/test_circadian_livingroom_docs.py`)
Helpers (each raises AssertionError with a message; tests call them in their bodies):
- `_read(path)`: asserts `path.is_file()` and `text.strip()` non-empty, returns text.
- `_section(text, heading)`: lines equal to `heading` (after `rstrip`) must occur exactly once; the body runs to the next line matching `^#{1,N} ` (N = heading level); body `.strip()` must be non-empty.
- `_inputs(path)`: `_read`, then `yaml.load(text, Loader=HassLoader)`; `yaml.YAMLError` becomes AssertionError; asserts `data["blueprint"]["input"]` is a non-empty dict.
- `_readme()` = `_section(_read(ROOT/"README.md"), "## Circadian Living Room Lights Blueprint")`; `_req()` = `_read(ROOT/"requirements_circadian.md")`; `_bp()` = `_inputs(ROOT/"circadian_livingroom.yaml")`.
- `_fmt(inp)`: `required` if no `default`; a list as `` `[]` `` via `json.dumps`; else `` f"`{default}`" ``.
- `_has_min(text, n)`: `re.search(rf"\b{n} min\b", text)`.

Tests (DOCS = both texts: README circadian section and the whole requirements file):
1. `test_readme_section_slice_is_strict` (bad input: README missing, heading missing or duplicated): `_read(tmp_path/"README.md")` raises; `_section` raises on text without the heading, with it twice, and with it directly followed by `## Next`; the real README gives one non-empty slice where no line matches `re.match(r"^## ", line)`, the slice contains `### Overview`, and it does not contain `LG AC Sleep & Movie Mode Blueprint` (the real next heading), so it ends before that section.
2. `test_requirements_file_must_exist_and_have_text` (bad input): `_read` raises for a missing file and a whitespace-only file; the real file passes.
3. `test_blueprint_must_load_with_hassloader` (bad input): `_inputs` raises for a missing file, `"blueprint:\n  input: [unclosed\n"` and `"blueprint:\n  input:\n    x: !secret y\n"`; the real YAML loads.
4. `test_blueprint_without_inputs_fails` (bad input): `_inputs` raises for `blueprint: {name: x}`, `blueprint: {input: {}}` and `blueprint: {input: null}`.
5. `test_version_3_0_0_in_both_docs` (bad input): YAML name ends `v3.0.0`; `"v3.0.0"` in each of DOCS.
6. `test_no_stale_text` (bad input): in each of DOCS no `(?i)\b300\s*(lux|lx)\b`, no `\blux_threshold\b`, no `Presence:** Aqara FP2 (binary_sensor)`, no `utilizes the Aqara FP2 (or any lux+presence sensor)`; `presence_entity` not in the requirements file.
7. `test_every_blueprint_input_key_is_in_requirements` (bad input: drift): for every key of `_bp()`, `` f"`{key}`" `` in `_req()`; message names the missing keys.
8. `test_requirements_inputs_table_matches_blueprint`: rows of `_section(_req(), "### 4.1. Inputs")` matching ``^\|\s*`([a-z0-9_]+)`\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$``: no duplicate key, key set == `_bp()` keys, each Default cell == `_fmt(input)`, each Meaning cell non-empty.
9. `test_both_presence_inputs_documented`: each of DOCS contains `presence_fp2`, `presence_fp300`, and (case-insensitive) `either sensor` and `both sensors are clear`.
10. `test_late_night_defaults_match_blueprint_and_docs` (bad input): YAML defaults equal the contract (`late_night_start` "23:00:00", `late_night_end` "06:30:00", `late_night_timeout` 1, `presence_timeout` 5); each of DOCS contains the three key names, `start[:5]`, `end[:5]`, `_has_min(timeout)` and `_has_min(presence_timeout)` built from the YAML values.
11. `test_boundary_behaviour_documented`: each of DOCS contains `f"before {start[:5]}"`, `f"just after {start[:5]}"`, `f"at or after {end[:5]}"`, `no extra trigger` and `independent of the late-night window` (start/end from the YAML); and neither of DOCS contains `already running at`.
12. `test_dog_stay_on_note` (bad input): each of DOCS has at least one line containing `dog` and `bench` (case-insensitive) and `FP300`; in the README that line also contains `still being tested`.
13. `test_fp300_setup_documented`: each of DOCS contains `Zigbee2MQTT`, `mmWave`, `PIR`, `absence_delay_timer`, `60 s`, `_has_min(2)`.
14. `test_lux_defaults_and_per_instance`: YAML defaults `lux_on_threshold` 150, `lux_off_threshold` 400, `lux_off_duration` 5; each of DOCS contains `f"{on} lx"`, `f"{off} lx"`, `lux_on_threshold`, `lux_off_threshold`, `FP300 lux is not read` and (case-insensitive) `per instance`.
15. `test_notify_targets_and_offline_notice`: each of DOCS contains `notify_targets`, `notify.`, `_has_min(30)` and `after the light calls`.
16. `test_readme_install_uses_deploy_script`: `(ROOT / "deploy" / "circadian_livingroom_1767031159524.json").is_file()` (created by the migration card); README section contains `scripts/deploy-blueprint.sh circadian_livingroom.yaml leviemartin/circadian_livingroom.yaml deploy/circadian_livingroom_1767031159524.json`, `--dry-run`, `hass-cli`, `jq`, `PyYAML`, `PYTHON`, `~/.config/hass-cli/env`, the raw URL `https://raw.githubusercontent.com/leviemartin/Blueprints_Home/main/circadian_livingroom.yaml` and `requirements_circadian.md`.
17. `test_docs_hold_no_credentials` (risk flag: secrets): no match in DOCS for `eyJ[A-Za-z0-9_-]{8,}`, `(?i)bearer\s`, `HASS_(TOKEN|SERVER)\s*=`, `\b\d{1,3}(\.\d{1,3}){3}\b`, `(?i)\b(password|api[_-]?key)\b`. (No `https?://` pattern: the section keeps its import URLs.)
Done when 1 is this file (tests 1-17). Done when 2 is the full suite; no existing test reads the circadian README section or requirements_circadian.md, so nothing else changes.

### RED on the base
Red-green applies only the test file to this card's base (the commit holding both dependency cards: v3.0.0 YAML, the migration card's instance file, v2.2.0 docs). The RED run of Done-when 1 must be re-run on that dependency commit, and its output recorded in Result, before the coder's diff is trusted; the c40839f run below does not count as RED evidence. RED there: 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16 (assertion failures; the docs lack every v3 phrase, still hold 300 Lux / lux_threshold / the FP2-only lines, and have no inputs table). GREEN there: 1-4 (helper checks) and 17. On c40839f (v2.2.0 YAML, no instance file) the same tests are RED, and 5/10 also fail on the YAML values.

### Sandbox check (planner, 2026-10-16)
Both Done-when commands were run in the Frugo check sandbox (`scripts/sandbox --mode check`, cwd = tree root, sandbox venv) on an export of c40839f: command 1 exits 4 (file not found), command 2 is 420 passed. Not run on the dependency commit (neither dependency card is committed yet).

## Result
Passed Lane 2 review: the v3.0.0 README circadian section, requirements_circadian.md and 17 docs tests are applied in worktree Blueprints_Home-wt/circadian-v3-docs (branch frugo/circadian-v3-docs, uncommitted, based on card 3's commit eab5902). Coder: Codex. Red-green: both Done-when commands RED on the base, GREEN after (17 docs tests, full suite 517 passed; re-run by the orchestrator on the patched tree). Reviews: Opus correctness PASS with three P3, Codex security PASS. Design reviews were PASS (Codex) and FINDINGS fixed (Opus).
Open P3:
- The boundary test (tests/test_circadian_livingroom_docs.py:189) checks `before 23:00`, which also matches "just before 23:00", so deleting the boundary sentence would not turn it red. Pin `passed before 23:00` and `finishes on presence_timeout` instead.
- requirements_circadian.md line 116 ("If ON, automation pauses") and line 38 ("the automation halts") omit that the FP300 30-min push still runs while the override is on (the blueprint skips those trigger ids). Add "except the FP300 offline push".
- README.md line 72 says one push goes to each notify_targets entry; with mode: restart another trigger during the push loop can cut it short. Say it is best effort, in the README and requirements section 5.
