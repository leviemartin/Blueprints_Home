# Climate blueprints follow-up — Bedroom Sleep Pre-Cool v1.1.0 + LG AC Climate Control v1.3.0 — Implementation Plan (epic #18, session #19)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every code artifact below is a **verbatim unified diff** that was scratch-built, run RED against the shipped files and GREEN on the result, validated by HA `validate_config`, and re-applied onto a clean checkout to the pinned sha256 — a task is done only when its file hashes match.

**Goal:** Ship `bedroom_precool.yaml` v1.1.0 (auto-learn write clamped to the helper's live range + state-driven notice; real daily-forecast backstop replacing the dead `forecast` attribute read; manual setpoint / manual off respected until the next phase boundary) and `lg_ac_climate.yaml` v1.3.0 (presence setback: widened comfort band while everyone is away, guest-mode / EV / flap-guard hold comfort, immediate resume), with tests, both migrated instance configs, docs, and a live deploy of both instances.

**Architecture:** Two stateless blueprints, each edited by anchored hunks. Pre-cool: STEP 2b gains a daily `weather.get_forecasts` call on day-side ticks whose hourly window is empty; STEP 2c gains the helper-range variables, the known-setpoint set and the manual-off instant compare; the PRECOOL branch is wrapped in one override gate; the lock clamps and conditionally skips the learn write; STEP 7d/7e are state-driven notices. LG: four optional inputs + two return triggers; the comfort inputs become `temp_low_cfg`/`temp_high_cfg` and STEP 1 defines the effective `temp_low`/`temp_high` before the first consumer, so every downstream template is byte-identical. Deployment reuses `scripts/deploy-blueprint.sh` (pinned TCB file, not edited) with `deploy/bedroom_precool_1779553673971.json` and `deploy/lg_ac_climate_1775578219942.json`.

**Tech Stack:** Home Assistant 2026.9.0 blueprint YAML + Jinja2; pytest 9 + PyYAML 6 + Jinja2 3.1 structure/render harness (`tests/test_bedroom_precool_structure.py`, `tests/test_lg_ac_climate_structure.py`, `tests/test_deploy_blueprint_script.py`'s `run` harness); bash deploy script; hass-cli + curl against HA.

**Spec:** `docs/superpowers/specs/2026-09-09-climate-followup-v1.1.0-design.md` (§2 live facts, §3 pre-cool, §4 LG, §5 tests, §6 rollout). Research: `docs/superpowers/research/2026-09-09-climate-followup-research-validation.md` (verdict proceed).
**Session issue:** leviemartin/Blueprints_Home #19 (Entry C; the issue body is the kickoff and carries `<!-- observe:open -->`; epic #18 stays open until #24 closes).
**Branch:** `climate-followup-v1.1.0` (off `main` `5c5a08b` = `origin/main` at chain start) → PR → `main`. PR body carries `Session: #19` (deploying session — never `Closes`). Merge `origin/main` into the branch before opening the PR (a concurrent session may move it).

```
Stakes: standard
Trigger: default-up: automation logic changes in bedroom_precool.yaml + lg_ac_climate.yaml, tests, instance JSON, docs; no hard trigger matched (deploy script pinned via TCB_EXTRA and not edited; no file deleted; no dependency change)
Router: deterministic
Entry: C
tcb_manifest_sha: 94cccc64bc85efa5b38309bca448ff5dd1591f7c7598391ebd0a6e8a9b66caa7
tcb_baseline: /home/martin/AI/reviews/tcb-baseline-16ef53e7f973185a.txt
TCB_EXTRA: /home/martin/AI/projects/Blueprints_Home/scripts/deploy-blueprint.sh
declared_tcb_changes:                      # verbatim = /home/martin/AI/reviews/declared-tcb-16ef53e7f973185a.txt
  effe49ce87beb46086fc2973efe2c145d2a48b447c62dfbd38beb51e0c571436  /home/martin/.claude/settings.json
```

**Declared TCB drift (pre-existing, not made by this chain):** `~/.claude/settings.json` changed at 2026-09-09 07:50:56Z, one minute after a `/compact` in another Claude session (transcript 0bea7ab4, no tool call edited the file) — the baseline `16ef…` (2026-09-07) still carried the old sha `e12b55db…`. Non-permission content vs the July backup differs only in harness-managed keys (`autoCompactEnabled`, `remoteControlAtStartup`, `model` alias, plugin toggles); hooks are the three `notify.sh` hooks CLAUDE.md documents; `permissions.allow` has 536 entries, none new since July. Two other chains today baselined over the same sha (`1db44b50…` 08:01Z, `3b82a91a…` 10:38Z). This chain declares the drift at its exact sha instead of recomputing the baseline (`verify` with the declared file → rc 0; any further change to settings.json fails closed again). Operator veto point: the design board / Martin.

**Execution mode:** subagent-driven — T1–T4 to Sonnet subagents (mechanical: extract the fenced diff from THIS plan file, `git apply`, verify the pinned sha256, run the named checks, commit); T5 in the main loop (operator-visible live deploy). Boards at standard dial (R1 Opus + R2 Codex, Codex unpinned = account default model, recorded per leg) at design-time (before T1) and code-time (after T4, before T5). `/effort xhigh` at both gates, `high` otherwise.

**Shell invariants (plan-wide):** run from the repo root `/home/martin/AI/projects/Blueprints_Home` on branch `climate-followup-v1.1.0`; tests via `PY=~/projects/ceiling-fan-hue-blueprint/.venv/bin/python; $PY -m pytest tests -q` (system python3 lacks pytest; venv: Python 3.12.3, pyyaml 6, jinja2 3.1, pytest 9; baseline **282 green** on `5c5a08b`). Never pipe test output through `tail` when the exit code matters. Per-pillar commits, explicit paths, never `git add -A`. The deploy script is not edited. HA access: `source ~/.config/hass-cli/env`; `hass-cli -o json raw ws …` output wraps in `.result`; timestamps in query strings end in `Z`; helpers via WS (`input_boolean/create`), not REST. Patch extraction: each artifact sits in a 4-backtick ````diff fence immediately after an HTML marker `<!-- patch:<path> -->`; the snippet in each task pulls it out by marker — never retype a diff.

## Global Constraints

Locked decisions (issue #19, 2026-09-09 — implemented as stated; not re-opened at the board):
- Task 0 exactly as written on #19: clamp `new_bias` to the helper's live min/max ∩ −60…120 (`state_attr(lead_bias_entity,'min') | float(-60)` / `'max' | float(120)`); a state-driven persistent notification while the helper range is narrower, no push; render rows incl. min 60 / max 240 → 60 + notification; the deploy task pre-checks the live helper range; the requirements doc states the range; inside v1.1.0, no separate version.
- R1-07: the dead `state_attr(weather,'forecast')` fallback becomes a real `weather.get_forecasts type: daily` call (hourly cadence unchanged at /15; the daily call backs every day-side tick whose hourly window is empty). R1-04: the instance tests call the deploy `--dry-run` on the committed instance JSON; only the genuinely new assertions stay in Python.
- Manual override (designed in research-validate, design C): a running unit whose setpoint is none of the four values the blueprint can command is manual → PRECOOL issues nothing until the bedtime lock, which proceeds as usual (and skips that night's learn write); an `off` transition stamped inside `[bedtime − lead_cap, lock)` that is neither the HA-start/reload re-creation nor the vacation turn-off is a manual off → the unit stays off for the night. NIGHT_HOLD is untouched; DEEP_NIGHT_CHECK keeps its correction (literal "next phase boundary"). One state-driven persistent notification per override; no mobile push (the blueprint has none).
- LG v1.3.0: away = setback (configurable delta, default 2.0 °C), not off; return = resume immediately; a NEW `input_boolean.climate_guest_mode` holds comfort; presence = `person.martin_levie` + `person.savannah_levie`; `input_boolean.security_ev_car_home` and `input_boolean.security_presence_unreliable` are home indicators; **`input_boolean.security_auto_away` is the alarm's auto-arm feature toggle (off since 2026-08-15), not an away state, and is NOT wired** (spec §2 — flagged to Martin). `unknown`/`unavailable` = home. No comfort-band default change (`temp_range_low` 20.0 / `temp_range_high` 24.0 stay; the instance keeps 21 / 23.5).
- Sessions #15, #22, #24 (in-review, observation open) and #26 (queued research on epic #25) are not touched.

Engineering constraints:
- Every new input is additive with a default (a removed/renamed input makes the stored instance `unavailable`); the LG top-level rename `temp_low`→`temp_low_cfg` is internal (inputs keep their names).
- Every boolean-valued variable is a `{{ … }}` expression, never bare `true`/`false` text; values that feed `==`/`!=`/service data are single-lined; no datetime crosses a `variables:` boundary (instants as timestamps; `earliest_turn_on_ts`, `ac_off_since_ts`, `automation_up_since_ts`, `vacation_changed_ts` are floats).
- `weather.get_forecasts` calls carry `continue_on_error: true` and the daily one is gated on `supported_features` bit 1 (an unsupported type raises for the whole call).
- Declaration order inside a `variables:` block is load-bearing (HA renders top to bottom): pinned by tests.
- `mode: restart`, `max_exceeded: silent` unchanged; `homeassistant.min_version` unchanged.
- Version strings: `Bedroom Sleep Pre-Cool v1.1.0` / `**Version: 1.1.0**`; `LG AC Climate Control v1.3.0` / `**Version: 1.3.0**`; instance aliases follow.
- Instance configs gain `trace: {stored_traces: 30 | 20}` (HA keeps 5 by default — ~5 minutes of a 1-minute automation — too few to read the [8] evidence).

**Behaviour stated for the board (not a decision re-open):**
- *Setback depth.* Dutch heat-pump guidance caps setback at 1–2 °C (Milieu Centraal: none for floor heating, 1 °C reasonable insulation, 2 °C poor insulation); the inverter air-to-air unit has no resistive backup, so the DOE aux-heat penalty does not apply. 2.0 °C is the locked default and per-instance tunable (0–5).
- *Away debounce.* 10 min re-checked every tick (`last_changed`-based, stateless; the Better Thermostat blueprint precedent). Return is immediate via the two new triggers. An HA restart re-arms the setback 10 min after boot.
- *Leaving while heating.* A unit heating at 21.5 °C (release 22) finds itself inside 19–25.5 → `target_mode` off → one `climate.turn_off`; it re-heats only below 19.0. This is the setback, not "off": the unit runs whenever the room leaves the widened band.
- *Override residuals.* A manual change to one of the blueprint's own four values is re-asserted within a minute (v1.0.x behaviour). A setpoint command that fails on the turn-on tick can leave the unit at a remembered unknown value that reads as manual for the night (notification shown; self-heals next day). A reload of the instance (config edit) resets `this.last_changed` and, if the old setpoint is not in the new set, reads as manual until the lock.
- *Daily high in the evening.* `temperature` is the day's HIGH; after the afternoon peak the backstop overstates the remaining heat → an earlier start (the asymmetric-cost rule accepts early).
- *`get_forecasts` cadence.* Both calls read HA's cached coordinator data (Met.no polls upstream every 55–65 min); a daily call on 14 of 15 day-side ticks costs no upstream traffic.

---

## Phase 0 — Pre-flight (Claude, main loop) — DONE 2026-09-09

**Context budget:** ~25k tokens · 0 repo files edited · shell only.

- [x] Branch `climate-followup-v1.1.0` created off `main` (`5c5a08b` = `origin/main`) in the main checkout (no worktree; #15/#22/#24 branches are merged).
- [x] TCB: `verify` against `/home/martin/AI/reviews/tcb-baseline-16ef53e7f973185a.txt` with `TCB_EXTRA` = the deploy script → rc 2 on ONE undeclared drift (`~/.claude/settings.json`, evidence in the header); declared at its sha in `/home/martin/AI/reviews/declared-tcb-16ef53e7f973185a.txt` → `verify BASELINE declared` rc 0; ABSENT lines 0; deploy script present in the baseline (path-column match).
- [x] HA 2026.9.0 reachable (`Europe/Amsterdam`). Live facts (spec §2): `input_number.autolearner` min −60 / max 240 / step 1 / state 62; `climate.bedrooms` + `climate.livingroom` min 18 / max 30 / step 0.5, fan modes auto/low/medium/high, `temperature: null` while off; `weather.home_sm` = Met.no, `supported_features` 3, daily 6 entries (`temperature` = high, `templow` = low, `datetime` local-noon-as-UTC), hourly 48; `weather.openweathermap` no forecast; persons `person.martin_levie` / `person.savannah_levie`; `input_boolean.security_ev_car_home` on, `security_presence_unreliable` off, `security_auto_away` off (= the alarm's auto-arm toggle); `input_boolean.climate_guest_mode` ABSENT (created in T5); automation entities `automation.bedroom_sleep_pre_cool_v1_0_0` / `automation.lg_ac_climate_control_v1_0_0` both `on`.
- [x] Empirical probes: both climate states last written by their automations' time-pattern runs carry `context.parent_id null, user_id null` (context inspection rejected); `climate.bedrooms` last_changed 05:15Z / last_updated 07:59Z (attribute-only pushes do not move `last_changed`); HA stores 5 traces per automation.
- [x] Baseline suite green: `282 passed` on `5c5a08b`.
- [x] Scratch run of the inline artifacts in a throwaway repo copy: full suite **311 passed**; RED against the shipped files **32 failed / 66 passed** in the two changed test files (every new test red); `scripts/deploy-blueprint.sh --dry-run` green for both instances (`9 inputs` / `31 inputs`); HA `validate_config` on both input-substituted configs: `{"triggers":{"valid":true},"actions":{"valid":true}}`; live `/api/template` renders match the harness for `bitwise_and`, `as_local` date match, `states[entity]` item access (none when missing), `state_attr('', …)` → default, `expand(...)` last_changed max, the list literal, the string-form guard, the persons loop and the indicator `selectattr`; all nine diffs re-applied with `git apply` onto a clean checkout reproduce the pinned sha256s.
- [ ] At T5 time only: confirm `git rev-parse HEAD` = `origin/main`, re-read both live instance configs (the deploy script backs them up to `deploy/<id>.prev.json`, gitignored), re-check the helper range live.

**Observation criteria ([8] applies — deploying session; issue #19 carries `<!-- observe:open -->`):**
1. `automation.bedroom_sleep_pre_cool_v1_0_0` and `automation.lg_ac_climate_control_v1_0_0` (entity ids unchanged; aliases v1.1.0 / v1.3.0) are `on` immediately after deploy and still `on` 24 h later.
2. The first bedtime lock after deploy (19:29 CEST) writes the bias: `input_number.autolearner` `last_changed` at 19:29 local with a whole-number value inside −60…120, **no** `Invalid value for input_number.autolearner` log line, and no `bedroom_precool_bias_helper_range` notification (range −60…240 covers −60…120).
3. A day-side tick with `forecast_fetch_due: False` traces `finished` with `forecast_daily_high` = today's high (a number), `forecast_daily_ok: True`, `forecast_max ≥ outdoor_now`; a `/15` tick shows the hourly path.
4. LG: with the instance temporarily at `away_delay_minutes: 0`, both persons injected `not_home`, the EV latch and guest mode off → the triggered run's `changed_variables` show `away_active: True`, `temp_low: 19.0`, `temp_high: 25.5`; with `input_boolean.climate_guest_mode` on → `away_active: False`, `temp_low: 21.0`, `temp_high: 23.5`; states restored and the 10-min delay redeployed afterwards.
5. Zero `Error executing script` / `Invalid value` / `does not support` log lines for either automation over 24 h; `bedroom_precool_manual_override` appears only if a setpoint is changed by hand during PRECOOL (optional exercise: change the setpoint by remote at ~18:30, confirm no re-assert for the following minutes + the notice; the 19:29 lock re-applies 21 °C and dismisses it).

---

## Task 1: Tests first (RED) + migrated instance configs

**Model tier:** Sonnet
**Rationale:** Mechanical: extract four diffs from this plan, `git apply`, verify hashes, run the suite RED, commit.
**Effort:** high (operator `/effort high` checkpoint).

**Context budget:** ~25k tokens · 4 files modified · shell only.

**Files:**
- Modify: `tests/test_bedroom_precool_structure.py` (v1.0.3 pins → v1.1.0; R1-04 dry-run tests; harness stubs; 21 new tests)
- Modify: `tests/test_lg_ac_climate_structure.py` (v1.2.0 pins → v1.3.0; trigger roster; 10 new tests incl. the LG instance dry-run moved here from the pre-cool file)
- Modify: `deploy/bedroom_precool_1779553673971.json` (alias v1.1.0, `trace.stored_traces` 30)
- Modify: `deploy/lg_ac_climate_1775578219942.json` (alias v1.3.0, presence inputs, `trace.stored_traces` 20)

**Interfaces:**
- Consumes: `bedroom_precool.yaml` v1.0.3 / `lg_ac_climate.yaml` v1.2.0 (RED now, GREEN after T2/T3); `tests/test_deploy_blueprint_script.py::run` (unchanged).
- Produces: the variable names T2/T3 must emit — pre-cool STEP 2b `weather_daily_supported, forecast_daily_due, forecast_daily_list, forecast_daily_high, forecast_daily_ok` (and `forecast_max` rewritten); STEP 2c `bias_helper_min, bias_helper_max, bias_floor, bias_ceiling, bias_helper_range_ok, earliest_turn_on_ts, automation_up_since_ts, ac_off_since_ts, vacation_changed_ts, manual_off, known_setpoints, setpoint_is_known, manual_setpoint`; notification ids `bedroom_precool_bias_helper_range`, `bedroom_precool_manual_override`; LG top-level `temp_low_cfg, temp_high_cfg, presence_entities, home_indicators, away_delta, away_delay`, STEP 1 `presence_enabled, away_delay_sec, persons_all_away, home_indicator_on, away_active, temp_low, temp_high`, trigger ids `presence_return, indicator_on`. The two JSON files are what T5 deploys.

- [ ] **Step 1: Extract and apply the four diffs**

```bash
cd /home/martin/AI/projects/Blueprints_Home && git status --short   # expect only the untracked .stack-b marker + plan/spec/research docs
python3 - <<'EOF'
import re, pathlib
plan = pathlib.Path("docs/superpowers/plans/2026-09-09-climate-followup-v1.1.0.md").read_text()
for path in ["tests/test_bedroom_precool_structure.py", "tests/test_lg_ac_climate_structure.py",
             "deploy/bedroom_precool_1779553673971.json", "deploy/lg_ac_climate_1775578219942.json"]:
    m = re.search(r"<!-- patch:%s -->\n````diff\n(.*?)\n````\n" % re.escape(path), plan, re.S)
    assert m, path
    out = pathlib.Path("/tmp/claude-1000/-home-martin/plan-patches"); out.mkdir(parents=True, exist_ok=True)
    (out / (path.replace("/", "__") + ".patch")).write_text(m.group(1) + "\n")
    print("extracted", path)
EOF
for p in /tmp/claude-1000/-home-martin/plan-patches/tests__test_bedroom_precool_structure.py.patch \
         /tmp/claude-1000/-home-martin/plan-patches/tests__test_lg_ac_climate_structure.py.patch \
         /tmp/claude-1000/-home-martin/plan-patches/deploy__bedroom_precool_1779553673971.json.patch \
         /tmp/claude-1000/-home-martin/plan-patches/deploy__lg_ac_climate_1775578219942.json.patch; do
  git apply --check "$p" && git apply "$p" && echo "applied $p"
done
```

- [ ] **Step 2: Verify the pinned hashes**

```bash
sha256sum tests/test_bedroom_precool_structure.py tests/test_lg_ac_climate_structure.py deploy/bedroom_precool_1779553673971.json deploy/lg_ac_climate_1775578219942.json
```
Expected (exact):
```
c9672742b2a756c2dc468e236edb25a8101055073c083350536f3547f7925bd1  tests/test_bedroom_precool_structure.py
52c9b2fa43ae33e43bfac79a59ebad5482acfc3ab4de59e9d607f57b0e650156  tests/test_lg_ac_climate_structure.py
16441db6049bb0d53d62d756eb6fd0febc0d95afe54c7b02fe4aaa9708ee7641  deploy/bedroom_precool_1779553673971.json
7b7fa2d5bd13c781bb446fa0ce8d4e9e216b33b733c06ca896d82e8d0b982aaf  deploy/lg_ac_climate_1775578219942.json
```
A mismatch means the diff did not apply cleanly (stale base) — stop and report; never hand-edit toward the hash.

- [ ] **Step 3: Run the two changed test files — expect RED**

Run: `PY=~/projects/ceiling-fan-hue-blueprint/.venv/bin/python; $PY -m pytest tests/test_bedroom_precool_structure.py tests/test_lg_ac_climate_structure.py -q`
Expected: `32 failed, 66 passed` — the failing set is exactly: pre-cool `test_version_bumped, test_precool_instance_values, test_rendered_new_bias_is_clamped_to_the_helpers_live_range, test_bias_range_variables_are_defined_after_lead_bias_and_before_the_lock, test_bias_helper_range_notice_is_state_driven, test_auto_learn_write_is_clamped_and_skipped_on_an_override_night, test_dead_forecast_attribute_read_is_gone, test_rendered_weather_daily_supported_reads_feature_bit_1, test_rendered_forecast_daily_high_picks_todays_entry_by_local_date, test_rendered_forecast_max_prefers_hourly_then_daily_then_outdoor, test_rendered_forecast_daily_due_only_when_the_hourly_window_is_empty_on_the_day_side, test_daily_forecast_call_is_gated_and_error_tolerant, test_forecast_variables_are_defined_in_dependency_order, test_forecast_unavailable_notice_also_requires_the_daily_backstop_to_be_absent, test_rendered_manual_setpoint_is_any_value_the_blueprint_could_not_have_commanded, test_rendered_setpoint_is_known_treats_a_non_list_as_known, test_rendered_manual_off_only_for_an_off_transition_inside_the_adoption_window, test_rendered_manual_off_survives_a_missing_climate_state, test_precool_commands_are_gated_on_the_override_flags_and_the_boundaries_are_not, test_manual_override_notice_is_state_driven_and_phase_gated, test_override_variables_are_defined_in_dependency_order` (21) and LG `test_version_bumped, test_trigger_roster, test_presence_inputs_are_additive_with_defaults, test_presence_variable_mappings_and_cfg_rename, test_presence_triggers, test_presence_variables_precede_every_band_consumer, test_rendered_persons_all_away_requires_everyone_away_for_the_delay, test_rendered_home_indicator_on, test_rendered_away_active_and_effective_band, test_description_documents_presence_setback, test_lg_instance_passes_the_deploy_dry_run_and_wires_presence` (11). The instance dry-run tests fail here only because the blueprints do not yet declare the new inputs / versions.

- [ ] **Step 4: Commit (tests + instance pillar)**

```bash
git add tests/test_bedroom_precool_structure.py tests/test_lg_ac_climate_structure.py deploy/bedroom_precool_1779553673971.json deploy/lg_ac_climate_1775578219942.json
git commit -m "test(climate): v1.1.0 pre-cool + v1.3.0 LG pins (RED) — helper-range clamp, daily backstop, manual override, presence setback; instances migrated (aliases, presence inputs, stored_traces)"
```

Step 5: Report `RED: 32 failed / 66 passed` and the four hash lines.

### Artifacts for Task 1

<!-- patch:tests/test_bedroom_precool_structure.py -->
````diff
diff --git a/tests/test_bedroom_precool_structure.py b/tests/test_bedroom_precool_structure.py
index 252976b..13e93ad 100644
--- a/tests/test_bedroom_precool_structure.py
+++ b/tests/test_bedroom_precool_structure.py
@@ -1,4 +1,4 @@
-"""Structural pins for bedroom_precool.yaml (Bedroom Sleep Pre-Cool v1.0.3) and its
+"""Structural pins for bedroom_precool.yaml (Bedroom Sleep Pre-Cool v1.1.0) and its
 deployed instance configs.
 
 Run: cd ~/AI/projects/Blueprints_Home && \
@@ -72,37 +72,34 @@ def test_instants_are_carried_as_timestamps_not_datetimes(text):
 
 
 def test_version_bumped(bp):
-    assert bp["blueprint"]["name"].endswith("v1.0.3")
-    assert "**Version: 1.0.3**" in bp["blueprint"]["description"]
+    assert bp["blueprint"]["name"].endswith("v1.1.0")
+    assert "**Version: 1.1.0**" in bp["blueprint"]["description"]
 
 
-# --- deployed instance configs ---------------------------------------------------------
+# --- deployed instance config (board 20260907-163522 R1-04: the deploy dry-run owns the
+# schema checks — unknown keys, required inputs, use_blueprint.path, instance-id rule) ---
 
-def test_precool_instance_keys_exist_and_weather_supports_hourly_forecasts():
-    inst = json.loads(PRECOOL_INSTANCE.read_text())
-    inputs = _inputs(BP_PATH)
-    assert inst["use_blueprint"]["path"] == "leviemartin/bedroom_precool.yaml"
-    unknown = set(inst["use_blueprint"]["input"]) - set(inputs)
-    assert not unknown, f"instance keys absent from blueprint schema: {unknown}"
-    # weather.openweathermap reports supported_features None in this HA (no forecast
-    # service); weather.home_sm (Met.no) supports hourly forecasts (features 3).
-    assert inst["use_blueprint"]["input"]["weather_entity"] == "weather.home_sm"
-    assert inst["alias"].endswith("v1.0.3")
+from test_deploy_blueprint_script import run as deploy_run
+
+HA_PATH = "leviemartin/bedroom_precool.yaml"
 
 
-def test_lg_ac_instance_escalation_stages_are_ordered_and_in_range():
-    inst = json.loads(LG_INSTANCE.read_text())
-    inputs = _inputs(LG_PATH)
-    i = inst["use_blueprint"]["input"]
-    unknown = set(i) - set(inputs)
-    assert not unknown, f"instance keys absent from blueprint schema: {unknown}"
-    s1, s2 = i["escalation_stage_1_minutes"], i["escalation_stage_2_minutes"]
-    # target_fan tests stage 2 before stage 1 (elif chain): s2 <= s1 makes the mid
-    # stage unreachable and sends the fan to max after s2 minutes.
-    assert s1 < s2, f"stage 1 ({s1}) must fire before stage 2 ({s2})"
-    for key, val in (("escalation_stage_1_minutes", s1), ("escalation_stage_2_minutes", s2)):
-        sel = inputs[key]["selector"]["number"]
-        assert sel["min"] <= val <= sel["max"], f"{key}={val} outside selector range"
+def test_precool_instance_passes_the_deploy_dry_run():
+    r = deploy_run("--dry-run", str(BP_PATH), HA_PATH, str(PRECOOL_INSTANCE))
+    assert r.returncode == 0, r.stdout + r.stderr
+    assert "dry-run: validation passed" in r.stdout
+    assert "ok (id 1779553673971" in r.stdout
+
+
+def test_precool_instance_values():
+    inst = json.loads(PRECOOL_INSTANCE.read_text())
+    # weather.openweathermap supports no forecast type (a get_forecasts call raises);
+    # weather.home_sm (Met.no) supports daily + hourly (supported_features 3).
+    assert inst["use_blueprint"]["input"]["weather_entity"] == "weather.home_sm"
+    assert inst["alias"].endswith("v1.1.0")
+    # HA keeps 5 traces by default — ~5 minutes of a 1-minute automation, too few to read
+    # the bedtime-lock evidence after the fact ([8] observation)
+    assert inst["trace"]["stored_traces"] >= 30
 
 
 # --- rendered behaviour (board 20260907-163522 R1-01: realized outputs, not name pins) ---
@@ -132,9 +129,24 @@ def _reparse(rendered):
         return rendered
 
 
+_MISSING = object()
+
+
+def _ha_float(v, d=_MISSING):
+    """HA's `float` filter: the default (which may be none) on anything unparsable."""
+    try:
+        return float(v)
+    except (TypeError, ValueError):
+        if d is _MISSING:
+            raise
+        return d
+
+
 def _env(now):
     env = Environment()
-    env.filters["float"] = lambda v, d=0.0: float(v) if str(v).strip() not in ("", "None") else d
+    env.filters["float"] = _ha_float
+    env.filters["as_local"] = lambda d: d.astimezone(TZ)
+    env.filters["bitwise_and"] = lambda a, b: int(a) & int(b)
     env.filters["timestamp_custom"] = (
         lambda ts, fmt="%Y-%m-%d %H:%M:%S", local=True: datetime.fromtimestamp(float(ts), tz=TZ).strftime(fmt)
     )
@@ -384,3 +396,324 @@ def test_night_fan_unsupported_notice_is_gated_on_fan_control_and_resolution(bp)
 def test_precool_instance_sets_night_fan_low():
     inst = json.loads(PRECOOL_INSTANCE.read_text())
     assert inst["use_blueprint"]["input"]["night_fan"] == "low"
+
+
+# --- v1.1.0 (issue #19; spec docs/superpowers/specs/2026-09-09-climate-followup-v1.1.0-design.md) ---
+
+class _St:
+    """A minimal HA State: `.state` + `.last_changed`."""
+
+    def __init__(self, state, last_changed):
+        self.state, self.last_changed = state, last_changed
+
+
+class _States(dict):
+    """`states[entity]` -> State or None (HA semantics); `states(entity)` -> state string."""
+
+    def __getitem__(self, key):
+        return self.get(key)
+
+    def __call__(self, key):
+        st = self.get(key)
+        return st.state if st is not None else "unknown"
+
+
+def _var_template_deep(bp, name):
+    """Template of a `variables:` key anywhere in the action tree (branch-level too)."""
+    def walk(node):
+        if isinstance(node, dict):
+            v = node.get("variables")
+            if isinstance(v, dict) and name in v:
+                return v[name]
+            for val in node.values():
+                r = walk(val)
+                if r is not None:
+                    return r
+        elif isinstance(node, list):
+            for item in node:
+                r = walk(item)
+                if r is not None:
+                    return r
+        return None
+    t = walk(bp.get("action") or bp.get("actions"))
+    if t is None:
+        raise KeyError(name)
+    return t
+
+
+def _notices(bp, notification_id):
+    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
+    return [(c, s) for c, s in steps
+            if (s.get("data") or {}).get("notification_id") == notification_id]
+
+
+# ---- Task 0: the auto-learn write is clamped to the helper's live range --------------
+
+BIAS_CHAIN = ["bias_helper_min", "bias_helper_max", "bias_floor", "bias_ceiling", "bias_helper_range_ok"]
+
+
+def _bias_chain(bp, helper_min, helper_max, raw):
+    now = datetime(2026, 9, 9, 19, 29, tzinfo=TZ)
+    attrs = {"min": helper_min, "max": helper_max}
+    ctx = dict(lead_bias_entity="input_number.autolearner", state_attr=lambda e, a: attrs.get(a))
+    ctx = _render_chain(bp, BIAS_CHAIN, now, ctx)
+    ctx["new_bias_raw"] = raw
+    ctx["new_bias"] = _reparse(_env(now).from_string(_var_template_deep(bp, "new_bias")).render(**ctx).strip())
+    return ctx
+
+
+def test_rendered_new_bias_is_clamped_to_the_helpers_live_range(bp):
+    # 2026-09-08 17:29Z: a helper created with min 60 rejected 58.0 and aborted the lock run
+    ctx = _bias_chain(bp, 60.0, 240.0, 58.0)
+    assert (ctx["bias_floor"], ctx["bias_ceiling"]) == (60.0, 120.0)
+    assert ctx["new_bias"] == 60 and ctx["bias_helper_range_ok"] is False
+    ctx = _bias_chain(bp, -60.0, 240.0, 58.0)
+    assert ctx["new_bias"] == 58 and ctx["bias_helper_range_ok"] is True
+    assert _bias_chain(bp, -60.0, 240.0, -80.0)["new_bias"] == -60
+    assert _bias_chain(bp, -60.0, 240.0, 130.0)["new_bias"] == 120
+    # attributes missing (helper unavailable / unconfigured '') -> the blueprint's own bounds
+    ctx = _bias_chain(bp, None, None, 130.0)
+    assert (ctx["bias_floor"], ctx["bias_ceiling"], ctx["new_bias"]) == (-60.0, 120.0, 120)
+    assert ctx["bias_helper_range_ok"] is True
+    assert _bias_chain(bp, None, None, -80.0)["new_bias"] == -60
+
+
+def test_bias_range_variables_are_defined_after_lead_bias_and_before_the_lock(text):
+    assert (_def_index(text, "lead_bias") < _def_index(text, "bias_helper_min")
+            < _def_index(text, "bias_helper_max") < _def_index(text, "bias_floor")
+            < _def_index(text, "bias_ceiling") < _def_index(text, "bias_helper_range_ok")
+            < text.index("new_bias:"))
+
+
+def test_bias_helper_range_notice_is_state_driven(bp):
+    n = _notices(bp, "bedroom_precool_bias_helper_range")
+    kinds = sorted((s.get("service") or s.get("action")) for _, s in n)
+    assert kinds == ["persistent_notification.create", "persistent_notification.dismiss"]
+    create_conds = next(c for c, s in n if s["service"].endswith("create"))
+    assert any("not bias_helper_range_ok" in t and "lead_bias_configured" in t
+               and "enable_notifications" in t and "enable_auto_learn" in t for t in create_conds)
+    assert all(s.get("continue_on_error") is True for _, s in n)
+
+
+def test_auto_learn_write_is_clamped_and_skipped_on_an_override_night(bp):
+    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
+    writes = [(c, s) for c, s in steps if (s.get("service") or s.get("action")) == "input_number.set_value"]
+    assert len(writes) == 1
+    conds, step = writes[0]
+    assert any("phase == 'BEDTIME_LOCK'" in t for t in conds)
+    assert any("ac_is_running" in t for t in conds)
+    assert any("enable_auto_learn" in t and "lead_bias_configured" in t and "not manual_setpoint" in t for t in conds)
+    assert step["data"]["value"] == "{{ new_bias | float }}"
+    nb = _var_template_deep(bp, "new_bias")
+    assert "bias_floor" in nb and "bias_ceiling" in nb and "-60" not in nb and "120" not in nb
+
+
+# ---- R1-07: a real daily forecast backs the non-fetch ticks --------------------------
+
+def test_dead_forecast_attribute_read_is_gone(text):
+    assert "state_attr(weather_entity, 'forecast')" not in text
+    assert "forecast_daily_fallback" not in text
+
+
+def test_rendered_weather_daily_supported_reads_feature_bit_1(bp):
+    now = datetime(2026, 9, 9, 12, 0, tzinfo=TZ)
+    r = lambda feat: _reparse(_render(bp, "weather_daily_supported", now,
+                                      weather_entity="weather.x", state_attr=lambda e, a: feat))
+    assert r(3) is True and r(1) is True and r(5) is True
+    assert r(2) is False and r(4) is False and r(0) is False and r(None) is False
+
+
+def test_rendered_forecast_daily_high_picks_todays_entry_by_local_date(bp):
+    now = datetime(2026, 9, 9, 14, 40, tzinfo=TZ)
+    lst = [
+        {"datetime": "2026-09-08T10:00:00+00:00", "temperature": 30.0, "templow": 20.0},  # stale first entry
+        {"datetime": "2026-09-09T10:00:00+00:00", "temperature": 18.1, "templow": 13.4},  # today (live probe shape)
+        {"datetime": "2026-09-10T10:00:00+00:00", "temperature": 18.6, "templow": 10.9},
+    ]
+    assert _reparse(_render(bp, "forecast_daily_high", now, forecast_daily_list=lst)) == 18.1
+    # no entry for today -> the first usable entry; nothing usable -> None
+    assert _reparse(_render(bp, "forecast_daily_high", now, forecast_daily_list=lst[2:])) == 18.6
+    assert _reparse(_render(bp, "forecast_daily_high", now, forecast_daily_list=[])) is None
+    assert _reparse(_render(bp, "forecast_daily_high", now,
+                            forecast_daily_list=[{"datetime": "2026-09-09T10:00:00+00:00"}])) is None
+    # local-date match: 23:30 local on the 9th is 21:30Z, still the 9th's entry
+    late = datetime(2026, 9, 9, 23, 30, tzinfo=TZ)
+    assert _reparse(_render(bp, "forecast_daily_high", late, forecast_daily_list=lst)) == 18.1
+
+
+def _forecast_max_chain(bp, now, hourly, daily_high, outdoor_now):
+    ctx = dict(forecast_window_temps=hourly, forecast_daily_high=daily_high, outdoor_now=outdoor_now)
+    return _render_chain(bp, ["forecast_daily_ok", "forecast_max"], now, ctx)
+
+
+def test_rendered_forecast_max_prefers_hourly_then_daily_then_outdoor(bp):
+    now = datetime(2026, 9, 9, 14, 40, tzinfo=TZ)
+    assert _forecast_max_chain(bp, now, [24.0, 22.5], 26.0, 22.0)["forecast_max"] == 24.0
+    ctx = _forecast_max_chain(bp, now, [], 24.0, 22.0)
+    assert ctx["forecast_daily_ok"] is True and ctx["forecast_max"] == 24.0
+    assert _forecast_max_chain(bp, now, [], 18.1, 22.0)["forecast_max"] == 22.0   # never below the live reading
+    ctx = _forecast_max_chain(bp, now, [], None, 22.0)
+    assert ctx["forecast_daily_ok"] is False and ctx["forecast_max"] == 22.0
+    # the boundary may hand the daily value over as a string
+    assert _forecast_max_chain(bp, now, [], "24.0", 22.0)["forecast_max"] == 24.0
+
+
+def test_rendered_forecast_daily_due_only_when_the_hourly_window_is_empty_on_the_day_side(bp):
+    r = lambda hh, mm, window, supported: _reparse(_render(
+        bp, "forecast_daily_due", datetime(2026, 9, 9, hh, mm, tzinfo=TZ),
+        forecast_window_temps=window, weather_daily_supported=supported,
+        wake_time="07:15:00", bedtime="19:30:00"))
+    assert r(14, 40, [], True) is True
+    assert r(14, 40, [24.0], True) is False      # the hourly window carries the prediction
+    assert r(14, 40, [], False) is False         # entity without FORECAST_DAILY: never call
+    assert r(20, 0, [], True) is False           # after bedtime: unused
+    assert r(7, 0, [], True) is False            # before wake: unused
+
+
+def test_daily_forecast_call_is_gated_and_error_tolerant(bp):
+    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
+    calls = {s["data"]["type"]: (c, s) for c, s in steps
+             if (s.get("service") or s.get("action")) == "weather.get_forecasts"}
+    assert set(calls) == {"hourly", "daily"}
+    for t, (c, s) in calls.items():
+        assert s["continue_on_error"] is True, t
+        assert s["response_variable"] == f"{t}_forecast_resp", t
+    assert any("forecast_daily_due" in t for t in calls["daily"][0])
+    assert any("forecast_fetch_due" in t for t in calls["hourly"][0])
+
+
+def test_forecast_variables_are_defined_in_dependency_order(text):
+    assert (_def_index(text, "forecast_window_temps") < _def_index(text, "forecast_daily_due")
+            < _def_index(text, "forecast_daily_list") < _def_index(text, "forecast_daily_high")
+            < _def_index(text, "forecast_daily_ok") < _def_index(text, "forecast_max"))
+    assert _def_index(text, "weather_daily_supported") < _def_index(text, "forecast_daily_due")
+
+
+def test_forecast_unavailable_notice_also_requires_the_daily_backstop_to_be_absent(bp):
+    n = _notices(bp, "bedroom_precool_forecast_warning")
+    assert len(n) == 1
+    assert any("not forecast_daily_ok" in t and "not outdoor_now_ok" in t for t in n[0][0])
+
+
+# ---- Manual override (research design C — known-value set; spec §3.2) --------------
+
+OVERRIDE_CHAIN = ["known_setpoints", "setpoint_is_known", "manual_setpoint"]
+
+
+def _override(bp, current_setpoint, running=True, known=True, **over):
+    now = datetime(2026, 9, 9, 17, 0, tzinfo=TZ)
+    ctx = dict(effective_drive=18.0, maintaining_setpoint=21.0, correction_step=1.5,
+               ac_min_temp=18.0, ac_max_temp=30.0, current_setpoint=current_setpoint,
+               current_setpoint_known=known, ac_is_running=running)
+    ctx.update(over)
+    return _render_chain(bp, OVERRIDE_CHAIN, now, ctx)
+
+
+def test_rendered_manual_setpoint_is_any_value_the_blueprint_could_not_have_commanded(bp):
+    # live instance: ideal 23, hall offset 2, drive 16 -> clamped 18, step 1.5
+    assert _override(bp, 18.0)["known_setpoints"] == [18.0, 21.0, 19.5, 22.5]
+    for v in (18.0, 21.0, 19.5, 22.5, 21.05, 17.95):
+        assert _override(bp, v)["manual_setpoint"] is False, v
+    for v in (24.0, 20.0, 23.0, 18.5, 30.0):
+        assert _override(bp, v)["manual_setpoint"] is True, v
+    assert _override(bp, 24.0, running=False)["manual_setpoint"] is False      # off: nothing to respect
+    assert _override(bp, 24.0, known=False)["manual_setpoint"] is False        # LG null setpoint
+    # deep-night values clamp to the device range like the commands themselves
+    assert _override(bp, 18.0, ac_max_temp=22.0)["known_setpoints"] == [18.0, 21.0, 19.5, 22.0]
+
+
+def test_rendered_setpoint_is_known_treats_a_non_list_as_known(bp):
+    now = datetime(2026, 9, 9, 17, 0, tzinfo=TZ)
+    r = lambda ks: _reparse(_render(bp, "setpoint_is_known", now, known_setpoints=ks, current_setpoint=24.0))
+    assert r("[18.0, 21.0]") is True     # a string-form list must not iterate characters
+    assert r("") is True
+    assert r([18.0, 21.0]) is False
+
+
+MANUAL_OFF_CHAIN = ["earliest_turn_on_ts", "automation_up_since_ts", "ac_off_since_ts",
+                    "vacation_changed_ts", "manual_off"]
+
+
+def _manual_off(bp, ac_state, ac_last_changed, automation_last_changed=None, vacation=(), unavailable=False):
+    now = datetime(2026, 9, 9, 17, 0, tzinfo=TZ)
+    vac = [_St("off", t) for t in vacation]
+    ctx = dict(bedtime="19:30:00", lead_cap_minutes=240, ac_climate="climate.bedrooms",
+               vacation_toggle=["input_boolean.vac"] if vacation else [],
+               ac_is_running=ac_state not in ("off", "unavailable", "unknown"),
+               ac_unavailable=unavailable,
+               states=_States({"climate.bedrooms": _St(ac_state, ac_last_changed)}),
+               this=_St("on", automation_last_changed or datetime(2026, 9, 9, 6, 0, tzinfo=TZ)),
+               expand=lambda ids: vac)
+    return _render_chain(bp, MANUAL_OFF_CHAIN, now, ctx)
+
+
+def test_rendered_manual_off_only_for_an_off_transition_inside_the_adoption_window(bp):
+    t = lambda h, m: datetime(2026, 9, 9, h, m, tzinfo=TZ)
+    ctx = _manual_off(bp, "off", t(16, 30))
+    assert ctx["earliest_turn_on_ts"] == t(15, 30).timestamp()
+    assert ctx["manual_off"] is True                                            # switched off inside 15:30-19:29
+    assert _manual_off(bp, "off", t(7, 15))["manual_off"] is False              # the wake turn-off
+    assert _manual_off(bp, "off", t(15, 29))["manual_off"] is False             # DAY_OFF ended a manual daytime start
+    assert _manual_off(bp, "off", t(15, 30))["manual_off"] is True              # window edge is inclusive
+    assert _manual_off(bp, "cool", t(16, 30))["manual_off"] is False            # running
+    assert _manual_off(bp, "unavailable", t(16, 30), unavailable=True)["manual_off"] is False
+    # HA start / automation reload re-creates the state with a fresh last_changed
+    assert _manual_off(bp, "off", t(16, 30), automation_last_changed=t(16, 29))["manual_off"] is False
+    assert _manual_off(bp, "off", t(16, 30), automation_last_changed=t(16, 28))["manual_off"] is True
+    # the vacation branch's turn_off is not a manual off
+    assert _manual_off(bp, "off", t(16, 30), vacation=[t(16, 30)])["manual_off"] is False
+    assert _manual_off(bp, "off", t(16, 30), vacation=[t(15, 0)])["manual_off"] is True
+
+
+def test_rendered_manual_off_survives_a_missing_climate_state(bp):
+    now = datetime(2026, 9, 9, 17, 0, tzinfo=TZ)
+    ctx = dict(bedtime="19:30:00", lead_cap_minutes=240, ac_climate="climate.gone", vacation_toggle=[],
+               ac_is_running=False, ac_unavailable=True, states=_States({}),
+               this=_St("on", datetime(2026, 9, 9, 6, 0, tzinfo=TZ)), expand=lambda ids: [])
+    ctx = _render_chain(bp, MANUAL_OFF_CHAIN, now, ctx)
+    assert ctx["ac_off_since_ts"] == 0 and ctx["manual_off"] is False
+
+
+def _climate_calls_in_phase(bp, phase):
+    steps = _service_steps(bp.get("action") or bp.get("actions"), [])
+    return [(c, s) for c, s in steps
+            if (s.get("service") or s.get("action") or "").startswith("climate.")
+            and any(f"phase == '{phase}'" in t for t in c)]
+
+
+def test_precool_commands_are_gated_on_the_override_flags_and_the_boundaries_are_not(bp):
+    precool = _climate_calls_in_phase(bp, "PRECOOL")
+    assert sorted(s["service"] for _, s in precool) == \
+        ["climate.set_fan_mode", "climate.set_hvac_mode", "climate.set_temperature", "climate.turn_on"]
+    for c, s in precool:
+        assert any("not manual_setpoint and not manual_off" in t for t in c), s["service"]
+    # the bedtime lock is the phase boundary that ends the override: its commands are ungated
+    lock = _climate_calls_in_phase(bp, "BEDTIME_LOCK")
+    assert sorted(s["service"] for _, s in lock) == \
+        ["climate.set_fan_mode", "climate.set_hvac_mode", "climate.set_temperature"]
+    assert not any("manual" in t for c, _ in lock for t in c)
+    # the deep-night check keeps its correction (literal "next phase boundary" reading, spec §3.2)
+    deep = _climate_calls_in_phase(bp, "DEEP_NIGHT_CHECK")
+    assert [s["service"] for _, s in deep] == ["climate.set_temperature"]
+    assert not any("manual" in t for c, _ in deep for t in c)
+
+
+def test_manual_override_notice_is_state_driven_and_phase_gated(bp):
+    n = _notices(bp, "bedroom_precool_manual_override")
+    kinds = sorted((s.get("service") or s.get("action")) for _, s in n)
+    assert kinds == ["persistent_notification.create", "persistent_notification.dismiss"]
+    create_conds = next(c for c, s in n if s["service"].endswith("create"))
+    assert any("manual_setpoint or manual_off" in t and "NIGHT_HOLD" in t and "PRECOOL" in t
+               and "enable_notifications" in t for t in create_conds)
+    assert all(s.get("continue_on_error") is True for _, s in n)
+
+
+def test_override_variables_are_defined_in_dependency_order(text):
+    assert (_def_index(text, "maintaining_setpoint") < _def_index(text, "known_setpoints")
+            < _def_index(text, "setpoint_is_known") < _def_index(text, "manual_setpoint"))
+    assert (_def_index(text, "earliest_turn_on_tod") < _def_index(text, "earliest_turn_on_ts")
+            < _def_index(text, "automation_up_since_ts") < _def_index(text, "ac_off_since_ts")
+            < _def_index(text, "vacation_changed_ts") < _def_index(text, "manual_off"))
+    # both flags are computed in STEP 2c, before the STEP 6 dispatch that reads them
+    assert _def_index(text, "manual_setpoint") < text.index("# STEP 3: RUNTIME (CONFIG) VALIDATION")
+    assert _def_index(text, "manual_off") < text.index("# STEP 3: RUNTIME (CONFIG) VALIDATION")
````

<!-- patch:tests/test_lg_ac_climate_structure.py -->
````diff
diff --git a/tests/test_lg_ac_climate_structure.py b/tests/test_lg_ac_climate_structure.py
index 184b524..6ca64cc 100644
--- a/tests/test_lg_ac_climate_structure.py
+++ b/tests/test_lg_ac_climate_structure.py
@@ -1,16 +1,21 @@
-"""Structural + logic pins for lg_ac_climate.yaml (LG AC Climate Control v1.2.0).
+"""Structural + logic pins for lg_ac_climate.yaml (LG AC Climate Control v1.3.0).
 
 Run: cd ~/AI/projects/Blueprints_Home && \
      ~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q
 """
-from datetime import datetime
+import ast
+import json
+from datetime import datetime, timedelta
 from pathlib import Path
 
 import pytest
 import yaml
 from jinja2 import Environment
 
-BP_PATH = Path(__file__).resolve().parent.parent / "lg_ac_climate.yaml"
+ROOT = Path(__file__).resolve().parent.parent
+BP_PATH = ROOT / "lg_ac_climate.yaml"
+LG_INSTANCE = ROOT / "deploy" / "lg_ac_climate_1775578219942.json"
+HA_PATH = "leviemartin/lg_ac_climate.yaml"
 
 
 class _Input:
@@ -104,8 +109,8 @@ def test_fan_discovery_untouched(bp):
 # ---- v1.1.0 additions ----
 
 def test_version_bumped(bp):
-    assert bp["blueprint"]["name"] == "LG AC Climate Control v1.2.0"
-    assert "**Version: 1.2.0**" in bp["blueprint"]["description"]
+    assert bp["blueprint"]["name"] == "LG AC Climate Control v1.3.0"
+    assert "**Version: 1.3.0**" in bp["blueprint"]["description"]
 
 
 def test_new_input_schemas(inputs):
@@ -220,7 +225,8 @@ def test_window_formula_owns_overnight_tail(bp):
 def test_trigger_roster(bp):
     trigs = bp["trigger"]
     ids = [t.get("id") for t in trigs]
-    assert ids == ["update_loop", "vacation_on", "init", "door_open", "vacation_off", "init"]
+    assert ids == ["update_loop", "vacation_on", "init", "door_open", "vacation_off", "init",
+                   "presence_return", "indicator_on"]
     reload_t = trigs[5]
     # reloads don't fire homeassistant:start (board R2-2); same id → same seed semantics.
     # If the event name were ever wrong, the trigger is inert — safe either way.
@@ -775,3 +781,177 @@ def test_rendered_manual_detected(bp):
     ]
     for ctx, want in cases:
         assert render_var(bp, "manual_detected", ctx) == want, ctx
+
+
+# ---- v1.3.0: presence setback (issue #19; spec docs/superpowers/specs/2026-09-09-climate-followup-v1.1.0-design.md) ----
+
+def _reparse(rendered):
+    """What HA does to a rendered variables value before the next step sees it."""
+    try:
+        return ast.literal_eval(rendered)
+    except (ValueError, SyntaxError):
+        return rendered
+
+
+class _St:
+    def __init__(self, state, last_changed):
+        self.state, self.last_changed = state, last_changed
+
+
+class _States(dict):
+    """`states[entity]` -> State or None (HA semantics)."""
+
+    def __getitem__(self, key):
+        return self.get(key)
+
+
+def test_presence_inputs_are_additive_with_defaults(inputs):
+    pe = inputs["presence_entities"]
+    assert pe["default"] == []
+    assert pe["selector"]["entity"]["multiple"] is True
+    assert pe["selector"]["entity"]["domain"] == ["person", "device_tracker"]
+    hi = inputs["home_indicators"]
+    assert hi["default"] == []
+    assert hi["selector"]["entity"]["multiple"] is True
+    assert hi["selector"]["entity"]["domain"] == ["input_boolean", "binary_sensor"]
+    d = inputs["away_setback_delta"]
+    assert d["default"] == 2.0
+    n = d["selector"]["number"]
+    assert (n["min"], n["max"], n["step"]) == (0.0, 5.0, 0.5)
+    dl = inputs["away_delay_minutes"]
+    assert dl["default"] == 10
+    n = dl["selector"]["number"]
+    assert (n["min"], n["max"], n["step"]) == (0, 120, 5)
+    # comfort-band defaults untouched (operator decision 2026-09-07)
+    assert (inputs["temp_range_low"]["default"], inputs["temp_range_high"]["default"]) == (20.0, 24.0)
+
+
+def test_presence_variable_mappings_and_cfg_rename(bp):
+    v = bp["variables"]
+    assert v["temp_low_cfg"] == _Input("temp_range_low")
+    assert v["temp_high_cfg"] == _Input("temp_range_high")
+    assert "temp_low" not in v and "temp_high" not in v      # the effective band lives in STEP 1
+    assert v["presence_entities"] == _Input("presence_entities")
+    assert v["home_indicators"] == _Input("home_indicators")
+    assert v["away_delta"] == _Input("away_setback_delta")
+    assert v["away_delay"] == _Input("away_delay_minutes")
+
+
+def test_presence_triggers(bp):
+    trigs = bp["trigger"]
+    ret = trigs[6]
+    assert (ret["platform"], ret["to"], ret["id"]) == ("state", "home", "presence_return")
+    assert ret["entity_id"] == _Input("presence_entities")
+    ind = trigs[7]
+    assert (ind["platform"], ind["to"], ind["id"]) == ("state", "on", "indicator_on")
+    assert ind["entity_id"] == _Input("home_indicators")
+
+
+def test_presence_variables_precede_every_band_consumer(bp):
+    keys = list(bp["action"][0]["variables"].keys())
+    i = {k: keys.index(k) for k in
+         ("current_temp", "presence_enabled", "away_delay_sec", "persons_all_away", "home_indicator_on",
+          "away_active", "temp_low", "temp_high", "outdoor_temp_raw", "setpoint_cool_q",
+          "setpoint_heat_q", "target_mode", "outdoor_distance", "cool_deep_ok")}
+    assert (i["current_temp"] < i["presence_enabled"] < i["away_delay_sec"] < i["persons_all_away"]
+            < i["home_indicator_on"] < i["away_active"] < i["temp_low"] < i["temp_high"]
+            < i["outdoor_temp_raw"])
+    for consumer in ("setpoint_cool_q", "setpoint_heat_q", "target_mode", "outdoor_distance", "cool_deep_ok"):
+        assert i["temp_high"] < i[consumer], consumer
+
+
+PRESENCE_CHAIN = ["presence_enabled", "away_delay_sec", "persons_all_away", "home_indicator_on",
+                  "away_active", "temp_low", "temp_high"]
+
+
+def _away(bp, persons, delay=10, indicators=(), delta=2.0, enabled=True, entities=None, tl=21.0, th=23.5):
+    """persons: [(state, minutes_since_last_change)]; indicators: states of the home indicators."""
+    now = datetime(2026, 9, 9, 17, 0)
+    ids = [f"person.p{i}" for i in range(len(persons))]
+    st = _States({pid: _St(state, now - timedelta(minutes=mins)) for pid, (state, mins) in zip(ids, persons)})
+    ctx = dict(presence_entities=(ids if enabled else []) if entities is None else entities,
+               home_indicators=[f"input_boolean.i{i}" for i in range(len(indicators))],
+               expand=lambda _ids: [_St(x, now) for x in indicators],
+               away_delay=delay, away_delta=delta, temp_low_cfg=tl, temp_high_cfg=th, states=st)
+    for name in PRESENCE_CHAIN:
+        ctx[name] = _reparse(render_var(bp, name, ctx, now=now))
+    return ctx
+
+
+def test_rendered_persons_all_away_requires_everyone_away_for_the_delay(bp):
+    assert _away(bp, [("not_home", 15), ("not_home", 30)])["persons_all_away"] is True
+    assert _away(bp, [("work", 15), ("not_home", 30)])["persons_all_away"] is True     # a named zone is away
+    assert _away(bp, [("home", 15), ("not_home", 30)])["persons_all_away"] is False
+    assert _away(bp, [("unknown", 15), ("not_home", 30)])["persons_all_away"] is False  # unknown fails toward home
+    assert _away(bp, [("unavailable", 15), ("not_home", 30)])["persons_all_away"] is False
+    assert _away(bp, [("not_home", 3), ("not_home", 30)])["persons_all_away"] is False  # 3 min < 10 min delay
+    assert _away(bp, [("not_home", 10), ("not_home", 30)])["persons_all_away"] is True  # edge inclusive
+    assert _away(bp, [("not_home", 0), ("not_home", 0)], delay=0)["persons_all_away"] is True
+    ctx = _away(bp, [("not_home", 15)], enabled=False)
+    assert ctx["presence_enabled"] is False and ctx["persons_all_away"] is False
+    # a string-form list on the far side of the boundary must not enable the feature
+    ctx = _away(bp, [("not_home", 15)], entities="['person.p0']")
+    assert ctx["presence_enabled"] is False and ctx["persons_all_away"] is False
+    # an entity that does not exist fails toward home
+    assert _away(bp, [("not_home", 15)], entities=["person.p0", "person.gone"])["persons_all_away"] is False
+
+
+def test_rendered_home_indicator_on(bp):
+    assert _away(bp, [("not_home", 15)], indicators=("off", "on"))["home_indicator_on"] is True
+    assert _away(bp, [("not_home", 15)], indicators=("off", "off"))["home_indicator_on"] is False
+    assert _away(bp, [("not_home", 15)], indicators=())["home_indicator_on"] is False
+
+
+def test_rendered_away_active_and_effective_band(bp):
+    # live instance: band 21-23.5, delta 2 -> 19-25.5 while away
+    ctx = _away(bp, [("not_home", 15), ("not_home", 30)], indicators=("off", "off", "off"))
+    assert ctx["away_active"] is True and (ctx["temp_low"], ctx["temp_high"]) == (19.0, 25.5)
+    ctx = _away(bp, [("not_home", 15), ("not_home", 30)], indicators=("on", "off", "off"))  # guest mode
+    assert ctx["away_active"] is False and (ctx["temp_low"], ctx["temp_high"]) == (21.0, 23.5)
+    ctx = _away(bp, [("home", 15), ("not_home", 30)])
+    assert ctx["away_active"] is False and (ctx["temp_low"], ctx["temp_high"]) == (21.0, 23.5)
+    ctx = _away(bp, [("not_home", 15), ("not_home", 30)], delta=0)
+    assert ctx["away_active"] is False and (ctx["temp_low"], ctx["temp_high"]) == (21.0, 23.5)
+    ctx = _away(bp, [("not_home", 15)], enabled=False)
+    assert ctx["away_active"] is False and (ctx["temp_low"], ctx["temp_high"]) == (21.0, 23.5)
+
+
+def test_rendered_target_mode_turns_off_inside_the_widened_band(bp):
+    # heating at 21.5 with band 21-23.5 (margin 1, release 22) keeps heating; once away the band
+    # is 19-25.5 (release 20) and the same room reads in-range -> off; re-heat only below 19
+    ctx = dict(margin=1.0, current_ac_mode="heat", current_temp=21.5)
+    assert render_var(bp, "target_mode", {**ctx, "temp_low": 21.0, "temp_high": 23.5}) == "heat"
+    assert render_var(bp, "target_mode", {**ctx, "temp_low": 19.0, "temp_high": 25.5}) == "off"
+    assert render_var(bp, "target_mode", {**ctx, "current_temp": 18.8, "current_ac_mode": "off",
+                                          "temp_low": 19.0, "temp_high": 25.5}) == "heat"
+
+
+def test_description_documents_presence_setback(bp):
+    d = bp["blueprint"]["description"]
+    assert "Presence Setback" in d and "never off" in d
+
+
+def test_lg_instance_passes_the_deploy_dry_run_and_wires_presence():
+    from test_deploy_blueprint_script import run as deploy_run
+    r = deploy_run("--dry-run", str(BP_PATH), HA_PATH, str(LG_INSTANCE))
+    assert r.returncode == 0, r.stdout + r.stderr
+    assert "dry-run: validation passed" in r.stdout
+    inst = json.loads(LG_INSTANCE.read_text())
+    i = inst["use_blueprint"]["input"]
+    assert inst["alias"].endswith("v1.3.0")
+    assert i["presence_entities"] == ["person.martin_levie", "person.savannah_levie"]
+    assert i["home_indicators"] == ["input_boolean.climate_guest_mode",
+                                    "input_boolean.security_ev_car_home",
+                                    "input_boolean.security_presence_unreliable"]
+    assert i["away_setback_delta"] == 2 and i["away_delay_minutes"] == 10
+    # security_auto_away is the alarm's auto-arm feature toggle, not an away state (spec §2)
+    assert "security_auto_away" not in json.dumps(inst)
+    assert (i["temp_range_low"], i["temp_range_high"]) == (21, 23.5)   # no comfort-band change
+    assert inst["trace"]["stored_traces"] >= 20
+    # target_fan tests stage 2 before stage 1 (elif chain): s2 <= s1 makes the mid stage unreachable
+    s1, s2 = i["escalation_stage_1_minutes"], i["escalation_stage_2_minutes"]
+    assert s1 < s2
+    inputs = yaml.load(BP_PATH.read_text(), Loader=HassLoader)["blueprint"]["input"]
+    for key, val in (("escalation_stage_1_minutes", s1), ("escalation_stage_2_minutes", s2)):
+        sel = inputs[key]["selector"]["number"]
+        assert sel["min"] <= val <= sel["max"], key
````

<!-- patch:deploy/bedroom_precool_1779553673971.json -->
````diff
diff --git a/deploy/bedroom_precool_1779553673971.json b/deploy/bedroom_precool_1779553673971.json
index 72e5127..d954f7c 100644
--- a/deploy/bedroom_precool_1779553673971.json
+++ b/deploy/bedroom_precool_1779553673971.json
@@ -1,6 +1,6 @@
 {
   "id": "1779553673971",
-  "alias": "Bedroom Sleep Pre-Cool v1.0.3",
+  "alias": "Bedroom Sleep Pre-Cool v1.1.0",
   "description": "",
   "use_blueprint": {
     "path": "leviemartin/bedroom_precool.yaml",
@@ -20,5 +20,8 @@
         "input_number.autolearner"
       ]
     }
+  },
+  "trace": {
+    "stored_traces": 30
   }
 }
````

<!-- patch:deploy/lg_ac_climate_1775578219942.json -->
````diff
diff --git a/deploy/lg_ac_climate_1775578219942.json b/deploy/lg_ac_climate_1775578219942.json
index 8713f40..da51d60 100644
--- a/deploy/lg_ac_climate_1775578219942.json
+++ b/deploy/lg_ac_climate_1775578219942.json
@@ -1,6 +1,6 @@
 {
   "id": "1775578219942",
-  "alias": "LG AC Climate Control v1.2.0",
+  "alias": "LG AC Climate Control v1.3.0",
   "description": "",
   "use_blueprint": {
     "path": "leviemartin/lg_ac_climate.yaml",
@@ -35,7 +35,21 @@
       "escalation_stage_1_minutes": 20,
       "weather_entity": "weather.openweathermap",
       "fan_speed_medium_threshold": 2,
-      "comfort_margin": 1
+      "comfort_margin": 1,
+      "presence_entities": [
+        "person.martin_levie",
+        "person.savannah_levie"
+      ],
+      "home_indicators": [
+        "input_boolean.climate_guest_mode",
+        "input_boolean.security_ev_car_home",
+        "input_boolean.security_presence_unreliable"
+      ],
+      "away_setback_delta": 2,
+      "away_delay_minutes": 10
     }
+  },
+  "trace": {
+    "stored_traces": 20
   }
 }
````

---

## Task 2: Blueprint `bedroom_precool.yaml` v1.1.0

**Model tier:** Sonnet
**Rationale:** Mechanical apply + hash + suite + dry-run + HA validate_config; the logic was scratch-verified.
**Effort:** high.

**Context budget:** ~30k tokens · 1 file modified (+371/−? lines) · shell only.

**Files:**
- Modify: `bedroom_precool.yaml` (header, STEP 2b, STEP 2c, STEP 6 PRECOOL/BEDTIME_LOCK, STEP 7b/7d/7e, STEP 8)
- Test: `tests/test_bedroom_precool_structure.py` (from T1)

**Interfaces:**
- Consumes: the T1 test names/variables; `deploy/bedroom_precool_1779553673971.json`.
- Produces: `bedroom_precool.yaml` v1.1.0 with every variable listed under T1 "Produces" (pre-cool half), the wrapped PRECOOL branch (`{{ not manual_setpoint and not manual_off }}`), the learn-write gate `{{ enable_auto_learn and lead_bias_configured and not manual_setpoint }}`, `new_bias` clamped to `bias_floor`/`bias_ceiling`, notices 7d/7e.

- [ ] **Step 1: Extract and apply the diff**

```bash
cd /home/martin/AI/projects/Blueprints_Home
python3 - <<'EOF'
import re, pathlib
plan = pathlib.Path("docs/superpowers/plans/2026-09-09-climate-followup-v1.1.0.md").read_text()
path = "bedroom_precool.yaml"
m = re.search(r"<!-- patch:%s -->\n````diff\n(.*?)\n````\n" % re.escape(path), plan, re.S); assert m
out = pathlib.Path("/tmp/claude-1000/-home-martin/plan-patches"); out.mkdir(parents=True, exist_ok=True)
(out / "bedroom_precool.yaml.patch").write_text(m.group(1) + "\n"); print("extracted")
EOF
git apply --check /tmp/claude-1000/-home-martin/plan-patches/bedroom_precool.yaml.patch && git apply /tmp/claude-1000/-home-martin/plan-patches/bedroom_precool.yaml.patch
sha256sum bedroom_precool.yaml
```
Expected: `f191557e1aa71e94567b890a13e9f57a4c15154d448c8c5e5d7b470c529aed0c  bedroom_precool.yaml`

- [ ] **Step 2: Pre-cool tests GREEN**

Run: `PY=~/projects/ceiling-fan-hue-blueprint/.venv/bin/python; $PY -m pytest tests/test_bedroom_precool_structure.py -q`
Expected: `41 passed` (every pre-cool pin: the 21 new ones plus the unchanged phase/boundary tests; the LG file is still RED until Task 3).

- [ ] **Step 3: Offline deploy validation**

Run: `PYTHON=~/projects/ceiling-fan-hue-blueprint/.venv/bin/python scripts/deploy-blueprint.sh --dry-run bedroom_precool.yaml leviemartin/bedroom_precool.yaml deploy/bedroom_precool_1779553673971.json`
Expected: `blueprint: Bedroom Sleep Pre-Cool v1.1.0`, `instance deploy/bedroom_precool_1779553673971.json: ok (id 1779553673971, 9 inputs)`, `dry-run: validation passed, nothing deployed`.

- [ ] **Step 4: HA schema validation of the input-substituted config (read-only WS call)**

```bash
source ~/.config/hass-cli/env
~/projects/ceiling-fan-hue-blueprint/.venv/bin/python - bedroom_precool.yaml deploy/bedroom_precool_1779553673971.json > /tmp/claude-1000/-home-martin/precool_substituted.json <<'EOF'
import json, sys, yaml
bp_file, inst_file = sys.argv[1], sys.argv[2]
inst = json.load(open(inst_file))["use_blueprint"]["input"]
class Inp:
    def __init__(self, n): self.n = n
class L(yaml.SafeLoader): pass
L.add_constructor("!input", lambda l, n: Inp(l.construct_scalar(n)))
bp = yaml.load(open(bp_file), Loader=L)
defaults = {k: v["default"] for k, v in bp["blueprint"]["input"].items() if "default" in v}
def sub(x):
    if isinstance(x, Inp): return inst[x.n] if x.n in inst else defaults[x.n]
    if isinstance(x, dict): return {k: sub(v) for k, v in x.items()}
    if isinstance(x, list): return [sub(v) for v in x]
    return x
json.dump({"triggers": sub(bp["trigger"]), "actions": sub(bp["action"])}, sys.stdout)
EOF
hass-cli -o json raw ws validate_config --json "$(cat /tmp/claude-1000/-home-martin/precool_substituted.json)" | jq -c '.result'
rm -f /tmp/claude-1000/-home-martin/precool_substituted.json
```
Expected: `{"triggers":{"valid":true,"error":null},"actions":{"valid":true,"error":null}}`

- [ ] **Step 5: Commit (code pillar)**

```bash
git add bedroom_precool.yaml
git commit -m "feat(bedroom-precool): v1.1.0 — auto-learn clamped to the helper's range (+notice), daily forecast backstop, manual setpoint/off respected until the next phase boundary"
```

Step 6: Report `precool: 50 passed`, the hash line, the dry-run line, the validate_config line.

### Artifact for Task 2

<!-- patch:bedroom_precool.yaml -->
````diff
diff --git a/bedroom_precool.yaml b/bedroom_precool.yaml
index aa508ce..99d6e10 100644
--- a/bedroom_precool.yaml
+++ b/bedroom_precool.yaml
@@ -1,12 +1,15 @@
 blueprint:
-  name: "Bedroom Sleep Pre-Cool v1.0.3"
+  name: "Bedroom Sleep Pre-Cool v1.1.0"
   description: >
-    **Version: 1.0.3** — `night_fan` input (default low): the fan mode locked
-    in at bedtime, matched case-insensitively against the unit's modes, with a
-    notice when the unit lacks it. History: v1.0.2 wake-time turn-off works
-    again (running-unit latch bounded to bedtime − lead cap; a manual daytime
-    turn-on ends within a minute) · v1.0.1 instants carried as timestamps
-    across the variables boundary · v1.0.0 initial.
+    **Version: 1.1.0** — manual override: a setpoint changed on the unit during
+    the pre-cool is respected until the bedtime lock, and a unit switched off
+    inside the pre-cool window stays off; a real daily forecast backs the
+    prediction between hourly fetches; the auto-learn write is clamped to the
+    helper's own range, with a notice while that range is narrower than
+    −60…120. History: v1.0.3 `night_fan` input (default low) · v1.0.2
+    wake-time turn-off works again (running-unit latch bounded to bedtime −
+    lead cap) · v1.0.1 instants carried as timestamps across the variables
+    boundary · v1.0.0 initial.
 
     Predictive pre-cooling of bedrooms via a single hall LG air conditioner.
     Reaches an ideal sleep temperature by a fixed bedtime, then holds the room
@@ -36,6 +39,11 @@ blueprint:
     - Night fan input (default low): the fan mode locked in at bedtime, matched
       by exact name (case-insensitive) to the unit's modes, with a notice if the
       unit lacks it
+    - Manual override (v1.1.0): a setpoint changed on the unit during the
+      pre-cool is left alone until the bedtime lock; a unit switched off inside
+      the pre-cool window stays off for the night; one notice per override
+    - Daily forecast backstop (v1.1.0): between hourly fetches the prediction
+      uses the day's forecast high, not the live outdoor reading alone
     - Opt-in humidity-aware dry mode (default off — cool is the proven path)
     - Idempotent service calls — a stray command is a stray beep
     - Vacation toggle, manual-run debug notification
@@ -48,6 +56,8 @@ blueprint:
     - A weather entity that provides an HOURLY forecast — Met.no or Open-Meteo
       (Buienradar has no hourly forecast and will not work)
     - An input_number helper to persist the self-learned lead-time bias
+      (min −60 or lower, max 120 or higher, step 1 — the write is clamped to
+      the helper's range and a notice is raised while it is narrower)
 
   domain: automation
   input:
@@ -110,8 +120,10 @@ blueprint:
       description: >
         An input_number helper the blueprint uses to persist its self-learned
         lead-time correction (minutes) across restarts. Create one via
-        Settings -> Devices & Services -> Helpers -> Number, range roughly
-        -60 to 120, step 1. Required when Enable Auto-Learn is on.
+        Settings -> Devices & Services -> Helpers -> Number with min -60 (or
+        lower), max 120 (or higher), step 1. The blueprint clamps its write
+        to the helper's range and warns while the range is narrower.
+        Required when Enable Auto-Learn is on.
       default: []
       selector:
         entity:
@@ -581,28 +593,36 @@ action:
         {% endif %}
 
   # =============================================
-  # STEP 2b: FORECAST FETCH (periodic, ~every 15 min during DAY-OFF)
+  # STEP 2b: FORECAST FETCH
   # weather.get_forecasts is the PLURAL current action — the singular
-  # weather.get_forecast was deprecated. Fetched into a response
-  # variable, then forecast_max is templated from it.
+  # weather.get_forecast was deprecated. Both calls read HA's cached forecast
+  # (Met.no refreshes upstream every 55-65 min), so they are cheap. The HOURLY
+  # window (now -> bedtime) is fetched near a 15-minute boundary; a DAILY
+  # forecast backs every other day-side tick, and any tick whose hourly
+  # window comes back empty. Fetched into response variables, then
+  # forecast_max is templated from them.
   # =============================================
   - variables:
       # Fetch only near a 15-minute boundary (minute mod 15 == 0) AND only
       # during the daytime wake -> bedtime window — the forecast result is
       # consumed by DAY_OFF alone, so fetching it overnight is pure waste.
-      # Between fetches the live outdoor sensor carries the prediction.
       forecast_fetch_due: >-
         {{ (now().minute | int) % 15 == 0
            and now().strftime('%H:%M:%S') >= wake_time
            and now().strftime('%H:%M:%S') < bedtime }}
+      # FORECAST_DAILY is bit 1 of the weather entity's supported_features
+      # (FORECAST_HOURLY = 2, FORECAST_TWICE_DAILY = 4). get_forecasts RAISES
+      # for a type the entity lacks, so the daily call is gated on the bit.
+      weather_daily_supported: >-
+        {{ (state_attr(weather_entity, 'supported_features') | int(0)) | bitwise_and(1) > 0 }}
   - choose:
       - conditions:
           - condition: template
             value_template: "{{ forecast_fetch_due }}"
         sequence:
           # continue_on_error: a weather-entity failure must not abort the
-          # whole action run — the forecast_daily_fallback -> outdoor_now
-          # chain below handles a missing/empty response.
+          # whole action run — the daily backstop -> outdoor_now chain below
+          # handles a missing/empty response.
           - service: weather.get_forecasts
             continue_on_error: true
             target:
@@ -643,18 +663,62 @@ action:
           {% endif %}
         {% endfor %}
         {{ ns.vals }}
-      forecast_daily_fallback: >-
-        {% set d = state_attr(weather_entity, 'forecast') %}
-        {% if d is iterable and d is not string and d | length > 0 %}
-          {{ d[0].temperature | float(outdoor_now | float) }}
-        {% else %}
-          {{ outdoor_now | float }}
-        {% endif %}
+      # The daily backstop is due on every day-side tick whose hourly window
+      # is empty: the 14 of 15 ticks without a fetch, and a fetch tick whose
+      # window has no entry left before bedtime.
+      forecast_daily_due: >-
+        {{ forecast_window_temps | length == 0
+           and weather_daily_supported
+           and now().strftime('%H:%M:%S') >= wake_time
+           and now().strftime('%H:%M:%S') < bedtime }}
+  - choose:
+      - conditions:
+          - condition: template
+            value_template: "{{ forecast_daily_due }}"
+        sequence:
+          - service: weather.get_forecasts
+            continue_on_error: true
+            target:
+              entity_id: "{{ weather_entity }}"
+            data:
+              type: daily
+            response_variable: daily_forecast_resp
+  - variables:
+      forecast_daily_list: >-
+        {{ daily_forecast_resp[weather_entity].forecast
+           if daily_forecast_resp is defined
+              and daily_forecast_resp is mapping
+              and weather_entity in daily_forecast_resp
+              and daily_forecast_resp[weather_entity].forecast is defined
+           else [] }}
+      # A daily entry's `temperature` is the day's HIGH (Met.no: the max of
+      # that day's hourly readings; `templow` is the low) stamped at local
+      # noon. Take today's entry by LOCAL date, else the first entry, else
+      # none (the `None` literal re-parses to none on the far side).
+      forecast_daily_high: >-
+        {% set ns = namespace(today=none, first=none) %}
+        {% for f in forecast_daily_list %}
+          {% set ts = f.datetime | default(none) %}
+          {% set tp = f.temperature | default(none) %}
+          {% if ts is not none and tp is not none %}
+            {% if ns.first is none %}{% set ns.first = tp | float %}{% endif %}
+            {% set fdt = as_datetime(ts) %}
+            {% if fdt is not none and ns.today is none and (fdt | as_local).date() == now().date() %}
+              {% set ns.today = tp | float %}
+            {% endif %}
+          {% endif %}
+        {% endfor %}
+        {{ ns.today if ns.today is not none else ns.first }}
+      forecast_daily_ok: "{{ forecast_daily_high is not none and forecast_daily_high | float(none) is not none }}"
+      # Precedence: hourly window max -> the day's forecast high (never below
+      # the live outdoor reading) -> the live outdoor reading alone.
       forecast_max: >-
         {% if forecast_window_temps | length > 0 %}
           {{ forecast_window_temps | max }}
+        {% elif forecast_daily_ok %}
+          {{ [forecast_daily_high | float, outdoor_now | float] | max }}
         {% else %}
-          {{ [forecast_daily_fallback | float, outdoor_now | float] | max }}
+          {{ outdoor_now | float }}
         {% endif %}
 
   # =============================================
@@ -697,6 +761,15 @@ action:
         {% else %}
           0
         {% endif %}
+      # The helper's own range, intersected with the blueprint's -60..120
+      # clamp (v1.1.0): a helper created narrower — the live one had min 60
+      # until 2026-09-09 — rejected the write and aborted the lock run.
+      # state_attr of an unconfigured ('') helper is none -> the defaults.
+      bias_helper_min: "{{ state_attr(lead_bias_entity, 'min') | float(-60) }}"
+      bias_helper_max: "{{ state_attr(lead_bias_entity, 'max') | float(120) }}"
+      bias_floor: "{{ [bias_helper_min | float, -60] | max }}"
+      bias_ceiling: "{{ [bias_helper_max | float, 120] | min }}"
+      bias_helper_range_ok: "{{ bias_helper_min | float <= -60 and bias_helper_max | float >= 120 }}"
       # --- Lead-time formula (transparent linear blend), then clamp ---
       lead_raw: >-
         {{ (base_minutes | float)
@@ -745,6 +818,33 @@ action:
       # ABOVE wake_time and slip past a string compare.
       earliest_turn_on_tod: >-
         {{ (today_at(bedtime) - timedelta(minutes=lead_cap_minutes | int)).strftime('%H:%M:%S') }}
+      earliest_turn_on_ts: "{{ as_timestamp(today_at(bedtime) - timedelta(minutes=lead_cap_minutes | int)) }}"
+      # --- Manual OFF inside the adoption window (v1.1.0) ---
+      # The blueprint never switches the unit off between earliest_turn_on and
+      # the lock (DAY_OFF cannot see a running unit there; only the vacation
+      # branch can), so an `off` transition stamped inside that window came
+      # from a person (remote, app, the unit's own timer). It is respected:
+      # PRECOOL does not restart the unit and the night is a cool-day no-op.
+      # Guards: the state re-created at HA start / automation reload carries
+      # a fresh last_changed (this.last_changed moves at the same moment), and
+      # the vacation branch's turn_off is recognised by the toggle's own
+      # last_changed. Instants are compared as timestamps in one template.
+      automation_up_since_ts: "{{ as_timestamp(this.last_changed) | float(0) if this is defined else 0 }}"
+      ac_off_since_ts: "{{ as_timestamp(states[ac_climate].last_changed) | float(0) if states[ac_climate] is not none else 0 }}"
+      vacation_changed_ts: >-
+        {% set ns = namespace(ts=0) %}
+        {% if vacation_toggle is iterable and vacation_toggle is not string %}
+          {% for v in expand(vacation_toggle) %}
+            {% set t = as_timestamp(v.last_changed) | float(0) %}
+            {% if t > ns.ts %}{% set ns.ts = t %}{% endif %}
+          {% endfor %}
+        {% endif %}
+        {{ ns.ts }}
+      manual_off: >-
+        {{ (not ac_is_running) and (not ac_unavailable)
+           and ac_off_since_ts | float >= earliest_turn_on_ts | float
+           and ac_off_since_ts | float > automation_up_since_ts | float + 60
+           and vacation_changed_ts | float < ac_off_since_ts | float - 5 }}
       # --- Phase derivation (all time-of-day string comparisons) ---
       # The "day side" of the schedule runs wake -> bedtime_lock.
       on_day_side: "{{ wake_tod <= now_tod and now_tod < lock_tod }}"
@@ -774,6 +874,20 @@ action:
       maintaining_setpoint: >-
         {{ [[ideal_temp | float - hall_offset | float, ac_min_temp | float] | max,
             ac_max_temp | float] | min }}
+      # --- Manual SETPOINT override (v1.1.0) ---
+      # The blueprint can only ever have commanded four setpoints: drive,
+      # maintaining, and the two deep-night corrections. A running unit whose
+      # setpoint is none of them was set by a person; PRECOOL then leaves the
+      # unit alone until the bedtime lock (the next phase boundary) and the
+      # lock skips that night's auto-learn write. HA state contexts cannot
+      # tell this automation's writes from the remote's (both carry no
+      # parent/user on a time-pattern run — verified live 2026-09-09), so the
+      # comparison is against values, not authorship. Single-lined: the list
+      # crosses the variables boundary and is re-parsed as a list; a value
+      # that arrives in any other shape counts as known (v1.0.x behaviour).
+      known_setpoints: "{{ [effective_drive | float, maintaining_setpoint | float, [[maintaining_setpoint | float - correction_step | float, ac_min_temp | float] | max, ac_max_temp | float] | min, [[maintaining_setpoint | float + correction_step | float, ac_min_temp | float] | max, ac_max_temp | float] | min] }}"
+      setpoint_is_known: "{% set ns = namespace(ok=false) %}{% if known_setpoints is string or known_setpoints is not iterable %}{% set ns.ok = true %}{% else %}{% for k in known_setpoints %}{% if (current_setpoint | float - k | float) | abs <= 0.1 %}{% set ns.ok = true %}{% endif %}{% endfor %}{% endif %}{{ ns.ok }}"
+      manual_setpoint: "{{ ac_is_running and current_setpoint_known and not setpoint_is_known }}"
       # --- Cool vs dry mode (only chosen while beeps are free) ---
       # Single-lined: this value feeds == comparisons and hvac_mode:; a
       # folded scalar would leave trailing whitespace on the rendered token.
@@ -971,63 +1085,71 @@ action:
                         {% else %}
                           {{ fan_normal }}
                         {% endif %}
-                  # 1. Ensure the unit is running and in the desired mode.
-                  #    set_hvac_mode fails on a powered-off LG unit, so turn_on
-                  #    first when off, then set the mode while it is running.
-                  - choose:
-                      - conditions:
-                          - condition: template
-                            value_template: "{{ not ac_is_running }}"
-                        sequence:
-                          - service: climate.turn_on
-                            target:
-                              entity_id: "{{ ac_climate }}"
-                  # Mode guard intentionally omits the `ac_is_running` precondition:
-                  # ac_is_running was captured in STEP 2 before this branch's
-                  # climate.turn_on ran, so on a first-tick-from-off it is stale
-                  # `false`. climate.turn_on always precedes this call when the unit
-                  # was off, so the unit IS on by now; the stale current_hvac_mode
-                  # ('off') still differs from desired_mode ('cool'), so the mode is
-                  # set the same tick instead of waiting for the next minute.
+                  # v1.1.0: a person's setpoint, or a manual off inside the
+                  # window, wins until the bedtime lock — no command at all
+                  # while either flag is set (STEP 7e says so).
                   - choose:
                       - conditions:
                           - condition: template
-                            value_template: >-
-                              {{ current_hvac_mode != desired_mode }}
+                            value_template: "{{ not manual_setpoint and not manual_off }}"
                         sequence:
-                          - service: climate.set_hvac_mode
-                            target:
-                              entity_id: "{{ ac_climate }}"
-                            data:
-                              hvac_mode: "{{ desired_mode }}"
-                  # 2. Then set the temperature (separate, sequenced call).
-                  - choose:
-                      - conditions:
-                          - condition: template
-                            value_template: >-
-                              {{ (not current_setpoint_known)
-                                 or (current_setpoint | float - precool_setpoint | float)
-                                    | abs > 0.1 }}
-                        sequence:
-                          - service: climate.set_temperature
-                            target:
-                              entity_id: "{{ ac_climate }}"
-                            data:
-                              temperature: "{{ precool_setpoint | float }}"
-                  # 3. Fan, only if fan control is enabled and there is a delta.
-                  - choose:
-                      - conditions:
-                          - condition: template
-                            value_template: >-
-                              {{ enable_fan_control
-                                 and ac_fan_modes | length > 0
-                                 and current_fan != precool_fan }}
-                        sequence:
-                          - service: climate.set_fan_mode
-                            target:
-                              entity_id: "{{ ac_climate }}"
-                            data:
-                              fan_mode: "{{ precool_fan }}"
+                            # 1. Ensure the unit is running and in the desired mode.
+                            #    set_hvac_mode fails on a powered-off LG unit, so turn_on
+                            #    first when off, then set the mode while it is running.
+                            - choose:
+                                - conditions:
+                                    - condition: template
+                                      value_template: "{{ not ac_is_running }}"
+                                  sequence:
+                                    - service: climate.turn_on
+                                      target:
+                                        entity_id: "{{ ac_climate }}"
+                            # Mode guard intentionally omits the `ac_is_running` precondition:
+                            # ac_is_running was captured in STEP 2 before this branch's
+                            # climate.turn_on ran, so on a first-tick-from-off it is stale
+                            # `false`. climate.turn_on always precedes this call when the unit
+                            # was off, so the unit IS on by now; the stale current_hvac_mode
+                            # ('off') still differs from desired_mode ('cool'), so the mode is
+                            # set the same tick instead of waiting for the next minute.
+                            - choose:
+                                - conditions:
+                                    - condition: template
+                                      value_template: >-
+                                        {{ current_hvac_mode != desired_mode }}
+                                  sequence:
+                                    - service: climate.set_hvac_mode
+                                      target:
+                                        entity_id: "{{ ac_climate }}"
+                                      data:
+                                        hvac_mode: "{{ desired_mode }}"
+                            # 2. Then set the temperature (separate, sequenced call).
+                            - choose:
+                                - conditions:
+                                    - condition: template
+                                      value_template: >-
+                                        {{ (not current_setpoint_known)
+                                           or (current_setpoint | float - precool_setpoint | float)
+                                              | abs > 0.1 }}
+                                  sequence:
+                                    - service: climate.set_temperature
+                                      target:
+                                        entity_id: "{{ ac_climate }}"
+                                      data:
+                                        temperature: "{{ precool_setpoint | float }}"
+                            # 3. Fan, only if fan control is enabled and there is a delta.
+                            - choose:
+                                - conditions:
+                                    - condition: template
+                                      value_template: >-
+                                        {{ enable_fan_control
+                                           and ac_fan_modes | length > 0
+                                           and current_fan != precool_fan }}
+                                  sequence:
+                                    - service: climate.set_fan_mode
+                                      target:
+                                        entity_id: "{{ ac_climate }}"
+                                      data:
+                                        fan_mode: "{{ precool_fan }}"
 
               # ---------- BEDTIME_LOCK: one locking command + auto-learn write ----------
               - conditions:
@@ -1079,11 +1201,13 @@ action:
                                     data:
                                       fan_mode: "{{ night_fan_mode }}"
                           # Auto-learn helper write — beep-free (an input_number,
-                          # not the AC). Only on a cooling night (AC running).
+                          # not the AC). Only on a cooling night (AC running) and
+                          # never while a manual setpoint is active at the lock:
+                          # that night's outcome does not reflect the predictor.
                           - choose:
                               - conditions:
                                   - condition: template
-                                    value_template: "{{ enable_auto_learn and lead_bias_configured }}"
+                                    value_template: "{{ enable_auto_learn and lead_bias_configured and not manual_setpoint }}"
                                 sequence:
                                   - variables:
                                       bedtime_error: "{{ warmest_bedroom | float - ideal_temp | float }}"
@@ -1092,10 +1216,11 @@ action:
                                            + (learn_gain | float)
                                              * (bedtime_error | float)
                                              * (k_indoor | float) }}
-                                      # round(0) | int — the lead_bias_helper input_number
-                                      # is created with step 1, so the written value must be
-                                      # a whole number to match the helper's step.
-                                      new_bias: "{{ [[new_bias_raw | float, -60] | max, 120] | min | round(0) | int }}"
+                                      # Clamped to the helper's live range intersected with
+                                      # -60..120 (bias_floor/bias_ceiling) so the write can
+                                      # never be rejected; round(0) | int — the helper is
+                                      # created with step 1, so the value must be whole.
+                                      new_bias: "{{ [[new_bias_raw | float, bias_floor | float] | max, bias_ceiling | float] | min | round(0) | int }}"
                                   - service: input_number.set_value
                                     target:
                                       entity_id: "{{ lead_bias_entity }}"
@@ -1180,13 +1305,15 @@ action:
             value_template: >-
               {{ enable_notifications and phase == 'DAY_OFF'
                  and forecast_window_temps | length == 0
+                 and not forecast_daily_ok
                  and not outdoor_now_ok }}
         sequence:
           - service: persistent_notification.create
             data:
               title: "Bedroom Pre-Cool — Forecast & Outdoor Unavailable"
               message: >
-                Neither an hourly forecast nor the outdoor sensor is available.
+                Neither an hourly nor a daily forecast nor the outdoor sensor
+                is available.
                 The prediction is leaning on the indoor gap and solar term only
                 until one recovers.
               notification_id: "bedroom_precool_forecast_warning"
@@ -1211,6 +1338,78 @@ action:
                 The bedtime lock uses {{ fan_normal }} instead.
               notification_id: "bedroom_precool_night_fan_unsupported"
 
+  # =============================================
+  # STEP 7d: AUTO-LEARN HELPER RANGE — state-driven notice (v1.1.0)
+  # Created while the helper's range does not cover -60..120 (the write is
+  # clamped to the helper's range meanwhile), dismissed once it does.
+  # =============================================
+  - choose:
+      - conditions:
+          - condition: template
+            value_template: >-
+              {{ enable_notifications and enable_auto_learn
+                 and lead_bias_configured and not bias_helper_range_ok }}
+        sequence:
+          - service: persistent_notification.create
+            data:
+              title: "Bedroom Pre-Cool — Auto-Learn Helper Range Too Narrow"
+              message: >
+                {{ lead_bias_entity }} allows {{ bias_helper_min }} to
+                {{ bias_helper_max }}, but the lead-time bias needs -60 to 120.
+                Until the helper is widened the learned bias is clamped to
+                {{ bias_floor }}…{{ bias_ceiling }} (a bias floored at
+                {{ bias_floor }} min starts the pre-cool that much early every
+                night). Edit the helper's min/max under Settings -> Devices &
+                Services -> Helpers.
+              notification_id: "bedroom_precool_bias_helper_range"
+            continue_on_error: true
+    default:
+      - service: persistent_notification.dismiss
+        data:
+          notification_id: "bedroom_precool_bias_helper_range"
+        continue_on_error: true
+
+  # =============================================
+  # STEP 7e: MANUAL OVERRIDE — state-driven notice (v1.1.0)
+  # One notice per override episode: created while a manual setpoint or a
+  # manual off is being respected, dismissed at the next phase boundary.
+  # =============================================
+  - choose:
+      - conditions:
+          - condition: template
+            value_template: >-
+              {{ enable_notifications
+                 and phase in ['PRECOOL', 'BEDTIME_LOCK', 'NIGHT_HOLD']
+                 and (manual_setpoint or manual_off) }}
+        sequence:
+          - service: persistent_notification.create
+            data:
+              title: "Bedroom Pre-Cool — Manual Override"
+              message: >
+                {% if manual_off %}
+                {{ ac_climate }} was switched off inside the pre-cool window;
+                the blueprint leaves it off tonight (no bedtime lock, no
+                deep-night check). Switch it on by hand to resume the pre-cool.
+                {% elif phase == 'NIGHT_HOLD' %}
+                {{ ac_climate }} holds a setpoint of {{ current_setpoint }}°C
+                that the blueprint did not set. It is respected until the
+                deep-night check at {{ deep_tod }}, which may correct drift.
+                {% else %}
+                {{ ac_climate }} holds a setpoint of {{ current_setpoint }}°C
+                that the blueprint did not set (its own values are
+                {{ known_setpoints }}). It is respected until the bedtime lock
+                at {{ lock_tod }}, which re-applies {{ maintaining_setpoint }}°C;
+                tonight's auto-learn update is skipped while the override is
+                active at the lock.
+                {% endif %}
+              notification_id: "bedroom_precool_manual_override"
+            continue_on_error: true
+    default:
+      - service: persistent_notification.dismiss
+        data:
+          notification_id: "bedroom_precool_manual_override"
+        continue_on_error: true
+
   # =============================================
   # STEP 8: DEBUG NOTIFICATION (manual run only)
   # =============================================
@@ -1236,12 +1435,15 @@ action:
                 **ΔT indoor:** {{ delta_in }}°C
                 | **ΔT outdoor:** {{ delta_out }}°C
                 | **forecast_max:** {{ forecast_max }}°C
+                | **daily high:** {{ forecast_daily_high }}°C (ok={{ forecast_daily_ok }})
 
                 **Solar load:** {{ solar_load }}
                 (elev {{ sun_elevation }}°, azim {{ sun_azimuth }}°)
 
                 **lead_bias:** {{ lead_bias }} min
                 (configured={{ lead_bias_configured }})
+                | **helper range:** {{ bias_helper_min }}…{{ bias_helper_max }}
+                (ok={{ bias_helper_range_ok }})
 
                 **lead:** {{ lead }} min
                 | **turn_on:** {{ turn_on_ts | float | timestamp_custom('%H:%M') }}
@@ -1257,6 +1459,9 @@ action:
 
                 **AC limits:** min={{ ac_min_temp }}°C, max={{ ac_max_temp }}°C
 
+                **manual:** setpoint={{ manual_setpoint }}
+                (known {{ known_setpoints }}), off={{ manual_off }}
+
                 **maintaining_setpoint:** {{ maintaining_setpoint }}°C
                 | **effective_drive:** {{ effective_drive }}°C
 
````

---

## Task 3: Blueprint `lg_ac_climate.yaml` v1.3.0

**Model tier:** Sonnet
**Rationale:** Mechanical apply + hash + full suite + dry-run + HA validate_config.
**Effort:** high.

**Context budget:** ~25k tokens · 1 file modified (+118 lines) · shell only.

**Files:**
- Modify: `lg_ac_climate.yaml` (header, inputs group, triggers 7–8, top-level variables, STEP 1 presence block)
- Test: `tests/test_lg_ac_climate_structure.py` (from T1)

**Interfaces:**
- Consumes: the T1 LG test names; `deploy/lg_ac_climate_1775578219942.json`.
- Produces: `lg_ac_climate.yaml` v1.3.0 — inputs `presence_entities, home_indicators, away_setback_delta, away_delay_minutes`; triggers `presence_return`, `indicator_on`; top-level `temp_low_cfg`/`temp_high_cfg` + four presence variables; STEP 1 `presence_enabled … temp_high` before `outdoor_temp_raw`.

- [ ] **Step 1: Extract and apply the diff**

```bash
cd /home/martin/AI/projects/Blueprints_Home
python3 - <<'EOF'
import re, pathlib
plan = pathlib.Path("docs/superpowers/plans/2026-09-09-climate-followup-v1.1.0.md").read_text()
path = "lg_ac_climate.yaml"
m = re.search(r"<!-- patch:%s -->\n````diff\n(.*?)\n````\n" % re.escape(path), plan, re.S); assert m
out = pathlib.Path("/tmp/claude-1000/-home-martin/plan-patches"); out.mkdir(parents=True, exist_ok=True)
(out / "lg_ac_climate.yaml.patch").write_text(m.group(1) + "\n"); print("extracted")
EOF
git apply --check /tmp/claude-1000/-home-martin/plan-patches/lg_ac_climate.yaml.patch && git apply /tmp/claude-1000/-home-martin/plan-patches/lg_ac_climate.yaml.patch
sha256sum lg_ac_climate.yaml
```
Expected: `269faa50c05f69e33c4c99d9fc30c12782afe85eafecc5eaad694fd90ed8c442  lg_ac_climate.yaml`

- [ ] **Step 2: Full suite GREEN**

Run: `PY=~/projects/ceiling-fan-hue-blueprint/.venv/bin/python; $PY -m pytest tests -q`
Expected: `311 passed` (282 baseline − 2 hand-rolled instance tests removed + 31 new).

- [ ] **Step 3: Offline deploy validation**

Run: `PYTHON=~/projects/ceiling-fan-hue-blueprint/.venv/bin/python scripts/deploy-blueprint.sh --dry-run lg_ac_climate.yaml leviemartin/lg_ac_climate.yaml deploy/lg_ac_climate_1775578219942.json`
Expected: `blueprint: LG AC Climate Control v1.3.0`, `instance deploy/lg_ac_climate_1775578219942.json: ok (id 1775578219942, 31 inputs)`, `dry-run: validation passed, nothing deployed`.

- [ ] **Step 4: HA schema validation (same substitution script as Task 2 Step 4 with `lg_ac_climate.yaml deploy/lg_ac_climate_1775578219942.json`, output file `/tmp/claude-1000/-home-martin/lg_substituted.json`)**

Expected: `{"triggers":{"valid":true,"error":null},"actions":{"valid":true,"error":null}}`

- [ ] **Step 5: Commit (code pillar)**

```bash
git add lg_ac_climate.yaml
git commit -m "feat(lg-ac-climate): v1.3.0 — presence setback (widened band while everyone is away; guest-mode/EV/flap-guard hold comfort; immediate resume)"
```

Step 6: Report `suite: 311 passed`, the hash line, the dry-run line, the validate_config line.

### Artifact for Task 3

<!-- patch:lg_ac_climate.yaml -->
````diff
diff --git a/lg_ac_climate.yaml b/lg_ac_climate.yaml
index 8156cf1..2633662 100644
--- a/lg_ac_climate.yaml
+++ b/lg_ac_climate.yaml
@@ -1,7 +1,7 @@
 blueprint:
-  name: "LG AC Climate Control v1.2.0"
+  name: "LG AC Climate Control v1.3.0"
   description: >
-    **Version: 1.2.0**
+    **Version: 1.3.0**
 
     Automates LG air conditioners per-floor using external temperature sensors
     for reliable ambient readings.
@@ -26,6 +26,12 @@ blueprint:
       stays command-free. If the device's setpoint grid or limits leave no
       valid deep setpoint, that mode falls back to v1.1.0 boundary idling
       and a persistent notification is raised.
+    - **Presence Setback (v1.3.0):** While every listed person / tracker has
+      been away for a configurable delay and no home indicator (guest-mode
+      toggle, EV-at-home latch, presence-unreliable guard) is on, the comfort
+      band widens by a configurable delta — a setback, never off. Someone
+      arriving, or an indicator turning on, restores the band at once.
+      Unknown/unavailable presence counts as home.
     - **Manual-Override Hold:** Optional input_text helper detects remote/app
       changes and pauses comfort control for a configurable window (vacation,
       schedule end, and door-open still force off). Reloading any automation
@@ -39,6 +45,8 @@ blueprint:
     - Weather entity for outdoor temperature (e.g., Met.no)
     - input_boolean helper for vacation mode
     - input_text helper (optional) for manual-override hold
+    - person / device_tracker entities and input_boolean helpers (optional)
+      for the presence setback
 
   domain: automation
   homeassistant:
@@ -291,6 +299,48 @@ blueprint:
           step: 5
           unit_of_measurement: min
 
+    # --- PRESENCE SETBACK (v1.3.0, optional) ---
+    presence_entities:
+      name: Presence Entities (Optional)
+      description: "person or device_tracker entities. The setback applies only while EVERY one of them has been away (any state except home/unknown/unavailable) for the Away Delay. Leave empty to disable presence gating."
+      default: []
+      selector:
+        entity:
+          domain:
+            - person
+            - device_tracker
+          multiple: true
+    home_indicators:
+      name: Home Indicators (Optional)
+      description: "input_boolean / binary_sensor entities that hold comfort while ON regardless of the trackers — e.g. a guest-mode toggle, an EV-at-home latch, a presence-unreliable guard."
+      default: []
+      selector:
+        entity:
+          domain:
+            - input_boolean
+            - binary_sensor
+          multiple: true
+    away_setback_delta:
+      name: Away Setback (°C)
+      description: "How far the comfort band widens on each side while everyone is away: heat only below Low − delta, cool only above High + delta. 0 disables the setback. Guidance for heat pumps is 1–2 °C; deeper is allowed for poorly insulated homes."
+      default: 2.0
+      selector:
+        number:
+          min: 0.0
+          max: 5.0
+          step: 0.5
+          unit_of_measurement: "°C"
+    away_delay_minutes:
+      name: Away Delay (min)
+      description: "Every presence entity must have been away at least this long before the setback applies (short absences such as walking the dog do not count). Return is immediate."
+      default: 10
+      selector:
+        number:
+          min: 0
+          max: 120
+          step: 5
+          unit_of_measurement: min
+
 mode: restart
 max_exceeded: silent
 
@@ -330,6 +380,19 @@ trigger:
     event_type: automation_reloaded
     id: "init"
 
+  # 7. Someone arrives — restore the comfort band at once (v1.3.0).
+  #    An empty entity list is a valid, inert state trigger (door_sensor precedent).
+  - platform: state
+    entity_id: !input presence_entities
+    to: "home"
+    id: "presence_return"
+
+  # 8. A home indicator switches on (guest mode, EV arrives, flap guard) (v1.3.0)
+  - platform: state
+    entity_id: !input home_indicators
+    to: "on"
+    id: "indicator_on"
+
 variables:
   # --- Entity Mappings ---
   climate_ac: !input climate_entity
@@ -340,8 +403,10 @@ variables:
   entity_vacation: !input vacation_toggle
 
   # --- Comfort ---
-  temp_low: !input temp_range_low
-  temp_high: !input temp_range_high
+  # The configured band. The EFFECTIVE temp_low / temp_high are defined in
+  # STEP 1 (widened while away) so every downstream consumer stays unchanged.
+  temp_low_cfg: !input temp_range_low
+  temp_high_cfg: !input temp_range_high
   deadband_thresh: !input deadband_outdoor_threshold
 
   # --- Schedule (Start/End per day) ---
@@ -375,6 +440,12 @@ variables:
   hold_helper: !input manual_hold_helper
   hold_minutes: !input manual_hold_minutes
 
+  # --- Presence setback (v1.3.0) ---
+  presence_entities: !input presence_entities
+  home_indicators: !input home_indicators
+  away_delta: !input away_setback_delta
+  away_delay: !input away_delay_minutes
+
 action:
   # =============================================
   # STEP 1: COMPUTE VARIABLES
@@ -405,6 +476,45 @@ action:
           {{ ((valid_temps | sum) / (valid_temps | length)) | round(1) }}
         {% endif %}
 
+      # --- Presence setback (v1.3.0) — declared BEFORE the first consumer of
+      # temp_low / temp_high (outdoor_distance, the quantised setpoints, the
+      # gates, target_mode); HA renders this block top to bottom. ---
+      presence_enabled: >-
+        {{ presence_entities is iterable and presence_entities is not string
+           and presence_entities | length > 0 }}
+      away_delay_sec: "{{ away_delay | int(0) * 60 }}"
+      # Every listed entity must be away — any state except home / unknown /
+      # unavailable (a named zone counts as away; unknown fails toward home,
+      # the house's security-resolver rule) — and must have been in that
+      # state for at least the away delay (last_changed moves only on a real
+      # state change, never on a GPS attribute update). Return is immediate.
+      persons_all_away: >-
+        {% if not presence_enabled %}
+          {{ false }}
+        {% else %}
+          {% set ns = namespace(ok=true) %}
+          {% for p in presence_entities %}
+            {% set st = states[p] %}
+            {% if st is none or st.state in ['home', 'unknown', 'unavailable']
+                  or (as_timestamp(now()) - as_timestamp(st.last_changed)) < away_delay_sec | float %}
+              {% set ns.ok = false %}
+            {% endif %}
+          {% endfor %}
+          {{ ns.ok }}
+        {% endif %}
+      home_indicator_on: >-
+        {{ home_indicators is iterable and home_indicators is not string
+           and home_indicators | length > 0
+           and expand(home_indicators) | selectattr('state', 'eq', 'on') | list | count > 0 }}
+      away_active: >-
+        {{ presence_enabled and persons_all_away and not home_indicator_on
+           and away_delta | float(0) > 0 }}
+      # The effective band: widened by the delta while away. A unit that was
+      # heating inside the widened band turns OFF on the next tick (one beep)
+      # and re-heats only below the setback floor; cooling mirrors it.
+      temp_low: "{{ (temp_low_cfg | float) - (away_delta | float if away_active else 0) }}"
+      temp_high: "{{ (temp_high_cfg | float) + (away_delta | float if away_active else 0) }}"
+
       # --- Outdoor (from weather entity) ---
       outdoor_temp_raw: "{{ state_attr(entity_weather, 'temperature') }}"
       weather_ok: "{{ outdoor_temp_raw is not none and outdoor_temp_raw | float(none) is not none }}"
````

---

## Task 4: Docs — requirements + README

**Model tier:** Sonnet
**Rationale:** Three doc diffs (≈160 lines); mechanical apply + hash; docs pillar — untested by design.
**Effort:** high.

**Context budget:** ~15k tokens · 3 files modified · shell only.

**Files:**
- Modify: `requirements_bedroom_precool.md` (helper range; PRECOOL row; Manual Override section; prediction fallback order; auto-learn clamp; Safety-3)
- Modify: `requirements_lg_ac_climate.md` (presence entities; Climate-7; Overrides-4; Safety-9)
- Modify: `README.md` (two pre-cool feature bullets; the README has no LG AC Climate Control section — none is added)

- [ ] **Step 1: Extract and apply the three diffs**

```bash
cd /home/martin/AI/projects/Blueprints_Home
python3 - <<'EOF'
import re, pathlib
plan = pathlib.Path("docs/superpowers/plans/2026-09-09-climate-followup-v1.1.0.md").read_text()
out = pathlib.Path("/tmp/claude-1000/-home-martin/plan-patches"); out.mkdir(parents=True, exist_ok=True)
for path in ["requirements_bedroom_precool.md", "requirements_lg_ac_climate.md", "README.md"]:
    m = re.search(r"<!-- patch:%s -->\n````diff\n(.*?)\n````\n" % re.escape(path), plan, re.S); assert m, path
    (out / (path + ".patch")).write_text(m.group(1) + "\n"); print("extracted", path)
EOF
for p in requirements_bedroom_precool.md requirements_lg_ac_climate.md README.md; do
  git apply --check "/tmp/claude-1000/-home-martin/plan-patches/$p.patch" && git apply "/tmp/claude-1000/-home-martin/plan-patches/$p.patch" && echo "applied $p"
done
sha256sum requirements_bedroom_precool.md requirements_lg_ac_climate.md README.md
```
Expected:
```
c02f0a4cc75d5f93db58c88472cef1617e0ba69bd2ea481326d56e245ac342d8  requirements_bedroom_precool.md
52c3b9ecb13dc879b1c5b5a2b9c8d05dc336bb2057d616b8f226af3c878c2b42  requirements_lg_ac_climate.md
bb6d7dcce1d3c5baf90b413dc5553c130771ce4fa10c84e4c2db9628c08f4b3c  README.md
```

- [ ] **Step 2: Suite still green** — Run: `PY=~/projects/ceiling-fan-hue-blueprint/.venv/bin/python; $PY -m pytest tests -q` → `311 passed`.

- [ ] **Step 3: Commit (docs pillar)**

```bash
git add requirements_bedroom_precool.md requirements_lg_ac_climate.md README.md
git commit -m "docs(climate): pre-cool v1.1.0 (helper range, daily backstop, manual override) + LG v1.3.0 presence setback requirements; README bullets"
```

Step 4: Report the three hash lines and `311 passed`.

### Artifacts for Task 4

<!-- patch:requirements_bedroom_precool.md -->
````diff
diff --git a/requirements_bedroom_precool.md b/requirements_bedroom_precool.md
index 65bb5f7..7c30c7c 100644
--- a/requirements_bedroom_precool.md
+++ b/requirements_bedroom_precool.md
@@ -40,7 +40,11 @@ observed outcome.
   `set_temperature` fix (PR #147008).
 - **input_number helper:** Persists the self-learned lead-time bias across
   restarts. Create one via Settings -> Devices & Services -> Helpers ->
-  Number (range roughly -60 to 120, step 1).
+  Number with **min −60 (or lower), max 120 (or higher), step 1**. The
+  blueprint clamps its write to the helper's live range intersected with
+  −60…120 and raises a persistent notification while the helper is narrower
+  (v1.1.0 — a helper created with min 60 used to reject the write and abort
+  the lock run).
 - **input_boolean helper (optional):** For the vacation toggle.
 
 ## Daily State Machine
@@ -51,7 +55,7 @@ acts. Phase boundaries span midnight (bedtime -> wake is an overnight window).
 | Phase | Window | AC behaviour | Beeps |
 |---|---|---|---|
 | DAY-OFF | wake -> min(turn_on, bedtime − lead_cap) | Ensure AC off — any running unit is switched off on the next tick; recompute turn-on each tick | 1 at wake (+1 per manual daytime turn-on) |
-| PRECOOL | turn_on -> bedtime − 1 min | Cooling; closed-loop DRIVE / HOLD | many (allowed) |
+| PRECOOL | turn_on -> bedtime − 1 min | Cooling; closed-loop DRIVE / HOLD; stands down while a manual setpoint or a manual off is active (v1.1.0) | many (allowed) |
 | BEDTIME-LOCK | bedtime − 1 min -> bedtime | Lock mode, maintaining setpoint and the night fan (`night_fan`, default low) + auto-learn write | ≤ 3 (typically 1–2) |
 | NIGHT-HOLD | bedtime -> deep-night check | Holds; blueprint issues nothing | 0 |
 | DEEP-NIGHT-CHECK | deep-night check -> +10 min | At most one corrective command | 0 or 1 |
@@ -64,17 +68,47 @@ onward; earlier on the day side (from wake) a running unit is a leftover
 night hold and DAY-OFF turns it off. Consequence: a unit switched on by hand
 between wake and `bedtime − lead_cap_minutes` is switched off again within a
 minute (one beep) — to use it manually during the day, disable the
-automation (manual-override handling is a v1.1.0 item). Configuration
+automation. Configuration
 validation rejects a lead cap whose earliest turn-on is at or before wake
 time, comparing instants so a cap that wraps past midnight is caught too.
 Cool-day nights (the AC was never started) are fully no-op.
 
+## Manual Override (v1.1.0)
+
+A person's change on the unit during the pre-cool is respected until the next
+phase boundary:
+
+- **Manual setpoint.** The blueprint can only ever have commanded four
+  setpoints (drive, maintaining, and the two deep-night corrections). A
+  running unit whose setpoint is none of them (±0.1 °C) was set by a person:
+  PRECOOL issues no command at all (mode, setpoint, fan) until the bedtime
+  lock, which re-applies the maintaining setpoint and the night fan as usual;
+  that night's auto-learn update is skipped when the override is still active
+  at the lock. A manual setpoint during NIGHT-HOLD is untouched until the
+  deep-night check, which keeps its correction rule.
+- **Manual off.** The blueprint never switches the unit off between
+  `bedtime − lead_cap_minutes` and the lock (only the vacation branch can), so
+  an `off` transition stamped inside that window came from a person: the unit
+  stays off for the night (no lock, no deep-night check). The state re-created
+  at an HA start / automation reload and the vacation turn-off are recognised
+  and not treated as manual.
+- One persistent notification per override episode, dismissed at the boundary.
+- HA state contexts cannot distinguish this automation's own writes from the
+  remote's (both carry no parent/user on a time-pattern run), so detection is
+  by value, not authorship. Known limits: a manual change *to* one of the
+  blueprint's own values is re-asserted within a minute; a setpoint command
+  that fails on the turn-on tick can leave the unit at a remembered value that
+  reads as manual for that night (the notification shows it).
+
 ## Prediction Model
 
 ```
 warmest_bedroom = aggregate(bedroom sensors, strategy)        # default: max
 delta_in        = max(0, warmest_bedroom − ideal_temp)
-forecast_max    = max forecast temp over [now -> bedtime]     # fallback: outdoor sensor
+forecast_max    = max hourly forecast temp over [now -> bedtime]
+                  # hourly fetched every 15 min; other ticks use the day's
+                  # forecast high (never below the live outdoor reading);
+                  # without either: the live outdoor sensor
 delta_out       = max(0, max(forecast_max, outdoor_now) − ideal_temp)
 solar_load      = 0..1 from sun elevation + azimuth
 lead_bias       = self-learned correction (minutes)
@@ -102,7 +136,8 @@ The blueprint self-learns one scalar — the lead-time bias — persisted in an
 ```
 # at BEDTIME-LOCK, only if the AC was running this night:
 bedtime_error = warmest_bedroom − ideal_temp
-new_bias      = clamp(lead_bias + learn_gain * bedtime_error * k_indoor, -60, 120)
+new_bias      = clamp(lead_bias + learn_gain * bedtime_error * k_indoor,
+                      max(helper.min, -60), min(helper.max, 120))
 ```
 
 Room too warm at bedtime -> bias rises (start earlier tomorrow); overcooled ->
@@ -140,8 +175,10 @@ the bias and subsequent nights wash the outlier out.
 ### Safety
 1. Bedroom sensor failure: holds state, fires a persistent notification.
 2. AC entity unavailable: skips the tick, retries next minute.
-3. Forecast unavailable: falls back to the daily forecast, then to the live
-   outdoor sensor.
+3. Forecast: the hourly window (fetched every 15 minutes) feeds the
+   prediction; every other daytime tick uses the day's forecast high
+   (`weather.get_forecasts type: daily`, gated on the entity's
+   FORECAST_DAILY feature); without either, the live outdoor sensor.
 4. `ideal_temp` is bounded >= 16 °C (child-safety floor); a bedroom reading
    below 16 °C raises an overcooling-fault notification.
 5. Every setpoint clamped to the AC's discovered `min_temp` / `max_temp`.
````

<!-- patch:requirements_lg_ac_climate.md -->
````diff
diff --git a/requirements_lg_ac_climate.md b/requirements_lg_ac_climate.md
index d160d96..d492066 100644
--- a/requirements_lg_ac_climate.md
+++ b/requirements_lg_ac_climate.md
@@ -23,6 +23,9 @@ manual human input.
 - **input_boolean helper:** For vacation mode toggle
 - **input_text helper (Optional, per floor):** Expected-state store for
   manual-override hold; feature is inert without it
+- **Presence entities (Optional):** `person` / `device_tracker` entities plus
+  `input_boolean` / `binary_sensor` "home indicators" (guest-mode toggle,
+  EV-at-home latch, presence-unreliable guard) for the presence setback
 - **Integration:** SmartThinQ Sensors or LG ThinQ (cloud or local)
 
 ## Functional Requirements
@@ -46,6 +49,15 @@ manual human input.
    v1.2.0 adds genuine off/on cycles, whose transitions beep by design — the
    operator's explicit silence-over-beeps trade
 
+7. Presence setback (v1.3.0): while every presence entity has been away
+   (any state except home/unknown/unavailable) for the away delay (default
+   10 min) and no home indicator is on, the comfort band widens by the away
+   setback delta (default 2 °C) on both sides — a setback, never off: a unit
+   heating inside the widened band turns off and re-heats only below
+   `low − delta`, cooling mirrors it. Someone arriving or an indicator
+   switching on restores the band immediately (dedicated triggers). Vacation,
+   the schedule window and the door pierce still outrank presence
+
 ### Fan Control
 1. Proportional fan speed based on distance from comfort boundary
 2. Multi-stage time-based escalation when target isn't reached, applied only
@@ -64,6 +76,11 @@ manual human input.
 2. Door sensor: AC turns off at exactly the configured delay after the door
    opens (dedicated timed trigger), except across HA restarts — last_changed
    resets at boot, so shut-off resumes within door_off_delay of startup
+4. Presence gating: the guest-mode toggle (`input_boolean.climate_guest_mode`
+   on the living-room instance) holds comfort while guests are in the house;
+   the security system's EV-at-home latch and presence-unreliable guard do the
+   same. `input_boolean.security_auto_away` is the alarm's auto-arm feature
+   toggle, not an away state, and is deliberately not a presence input
 3. Manual-override hold: a human change via remote/app (mode, setpoint beyond
    ±0.3 °C, or fan) is detected against the last automation-commanded state
    and honored for a configurable hold window (default 60 min). Vacation,
@@ -88,3 +105,6 @@ manual human input.
 8. A transient cloud command failure can produce one spurious manual-hold
    window (self-clears); floors sharing one LG account can fail correlated
    at the /10 boundary
+9. Presence: `unknown` / `unavailable` counts as home (fail toward comfort,
+   the security resolver's rule); an HA restart resets every `last_changed`,
+   so the setback re-arms one away delay after boot
````

<!-- patch:README.md -->
````diff
diff --git a/README.md b/README.md
index 02710af..fd6c298 100644
--- a/README.md
+++ b/README.md
@@ -140,6 +140,8 @@ Predictive pre-cooling of bedrooms via a single LG air conditioner in the upstai
 *   **🧠 Self-Learning Bias:** One scalar — the lead-time bias — is persisted in an `input_number` helper and auto-corrected from each cooling night's outcome. Converges over ~3–6 nights.
 *   **🔇 Strict Beep Budget:** Unlimited commands before bedtime; after bedtime the lock issues at most 3 (mode, setpoint, night fan — typically 1–2) and the deep-night check at most 1. NIGHT-HOLD and DEEP-HOLD issue zero commands; every climate call is idempotency-guarded.
 *   **🌙 Night Fan (v1.0.3):** The fan mode locked in at bedtime is an input (default low), matched case-insensitively to the unit's modes, with a notice if the unit lacks it.
+*   **✋ Manual Override (v1.1.0):** A setpoint changed on the unit during the pre-cool is left alone until the bedtime lock; a unit switched off inside the pre-cool window stays off for the night; one notice per override.
+*   **📅 Daily Forecast Backstop (v1.1.0):** Between hourly fetches the prediction uses the day's forecast high; the auto-learn write is clamped to the helper's own range, with a notice while that range is narrower than −60…120.
 *   **🌡️ Closed-Loop Pre-Cool:** DRIVE / HOLD sub-states cool the hall as hard as the AC allows until the warmest bedroom reaches ideal.
 *   **💧 Opt-In Dry Mode:** Humidity-aware `dry` mode, default off — `cool` is the proven path; enable `dry` only after verifying it on the unit.
 *   **🛡️ Child-Safe:** `ideal_temp` is bounded ≥ 16 °C; a sub-16 °C bedroom reading raises an overcooling fault. Every setpoint is clamped to the AC's discovered limits.
````

---

## Task 5: Deploy + live-verify (main loop, operator-visible) — after the code-time board, the PR (`Session: #19`) and the merge

**Model tier:** Fable (main loop). **Effort:** xhigh at the gate, high otherwise.

**Context budget:** ~30k tokens · 0 repo files edited (the deploy script writes gitignored `deploy/<id>.prev.json`).

- [ ] **Step 1: Pre-checks**

```bash
cd /home/martin/AI/projects/Blueprints_Home && git fetch origin && git rev-parse HEAD origin/main   # must be equal (merged)
source ~/.config/hass-cli/env
hass-cli -o json state get input_number.autolearner | jq -e '(.[0] // .) | .attributes | (.min <= -60 and .max >= 120 and .step == 1)' && echo "helper range OK" || { echo "HELPER RANGE TOO NARROW — widen it before deploying"; exit 1; }
hass-cli -o json state get input_boolean.climate_guest_mode 2>/dev/null | jq -r '(.[0] // .) | .entity_id' || true
```
If `input_boolean.climate_guest_mode` is absent, create it (WS, not REST) and re-read:
```bash
hass-cli -o json raw ws input_boolean/create --json '{"name":"climate_guest_mode","icon":"mdi:account-group"}' | jq -c '.result | {id, name}'
sleep 2; hass-cli -o json state get input_boolean.climate_guest_mode | jq -c '(.[0] // .) | {entity_id, state}'
```
Expected: `{"entity_id":"input_boolean.climate_guest_mode","state":"off"}`. If the entity id differs (device-derived-id lesson), rename it via `config/entity_registry/update` (`new_entity_id`) before deploying — the instance JSON names this exact id.
Both dry-runs green (Task 2/3 Step 3 commands).

- [ ] **Step 2: Deploy both blueprints**

```bash
scripts/deploy-blueprint.sh bedroom_precool.yaml leviemartin/bedroom_precool.yaml deploy/bedroom_precool_1779553673971.json
scripts/deploy-blueprint.sh lg_ac_climate.yaml leviemartin/lg_ac_climate.yaml deploy/lg_ac_climate_1775578219942.json
```
Expected per run: `backup: deploy/<id>.prev.json`, `blueprint/save: ok`, `instance <id>: config written`, `automation.… state=on …`, `deploy complete`. Rollback = `POST /api/config/automation/config/<id>` with `deploy/<id>.prev.json` + re-save the previous YAML from `git show main~1:<file>`.

- [ ] **Step 3: Pre-cool read-path proof** — trigger a manual Run (`hass-cli service call automation.trigger --arguments entity_id=automation.bedroom_sleep_pre_cool_v1_0_0,skip_condition=true`), read `persistent_notification` `bedroom_precool_debug`: it lists `daily high`, `helper range … (ok=True)`, `manual: setpoint=False …, off=False`. Then read the next tick's trace (`hass-cli -o json raw ws trace/list --json '{"domain":"automation","item_id":"1779553673971"}'` → newest run_id → `trace/get`), confirm `script_execution: finished` and, on a non-`/15` day-side tick, `forecast_daily_high` numeric + `forecast_daily_ok: True` in `changed_variables`; confirm no `bedroom_precool_bias_helper_range` notification exists.

- [ ] **Step 4: LG away/hold proof (criterion 4)** — deploy a temporary variant with `away_delay_minutes: 0` (a copy of the instance JSON with that one value, via the deploy script), inject `person.martin_levie` and `person.savannah_levie` = `not_home` (`POST /api/states/<id>` with the current attributes), turn `input_boolean.security_ev_car_home` off (`input_boolean.turn_off`; guest and `security_presence_unreliable` are off), trigger the automation (`automation.trigger`, `skip_condition=true`), read the newest trace: `away_active: True`, `temp_low: 19.0`, `temp_high: 25.5`. Turn `input_boolean.climate_guest_mode` on, trigger again: `away_active: False`, `temp_low: 21.0`, `temp_high: 23.5`. Restore: guest off, EV latch on, re-inject both persons `home` (their trackers overwrite on the next report anyway), redeploy the committed instance JSON (`away_delay_minutes: 10`), confirm `on`. Note on #19 that the simulation touched the persons (4 flips, below the security flap guard's 6/h) and the EV latch.

- [ ] **Step 5: Evidence on #19** — post the deploy output lines, the debug-dump fields, the trace excerpts and the criteria table (criteria 1–5 pending → PASS as observed) via `gh issue comment 19 -R leviemartin/Blueprints_Home --body-file …` (secret-scanned). Keep `<!-- observe:open -->` until criteria 1–5 pass (or Martin waives), then `observe:closed` → `gh_finish_session` in [9]; epic #18 stays open until #24 closes.

## Chain notes

- Design-time board: `triple-check` → `convene-board` on spec + this plan (standard: R1 Opus, R2 Codex unpinned — record the model per leg; call budget 24). Findings actioned in-session (P0/P1 never deferred).
- Code-time board after T4: `review-shipped` → `convene-board` (CYCLE=1) on the branch diff; `code-review-gate`; merge `origin/main` into the branch; PR `Session: #19`; merge; T5; closing-session.
- Operator questions carried to the report (no decisions taken silently): (1) `security_auto_away` not wired (toggle, not state); (2) the deep-night check keeps its correction on a NIGHT_HOLD manual value (literal boundary reading) — one-line gate if Martin prefers otherwise; (3) "one push max" read as one persistent notification per override; (4) the pre-existing `~/.claude/settings.json` drift declared rather than re-baselined.
