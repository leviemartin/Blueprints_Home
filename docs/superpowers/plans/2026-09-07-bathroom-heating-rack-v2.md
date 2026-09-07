# Bathroom Heating Rack v2.0.0 — Implementation Plan (epic #10, session #13)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `bathroom_heating_rack.yaml` v2.0.0 — comfort floor (slot-keyed 0.5 °C deadband, latched opening edge, suspended without the room sensor), predictive motion removed, edge-triggered warmup and outage notifications, setpoint rounded to the device step and clamped to its range, filtered `notify.*` targets with every push after the climate calls, `to:` filters on the toggle/fan triggers, boost expiry as the last step, preset machinery removed, locale-safe weekday, next-day hold-until anchoring, Fold push target — with structure/render tests, the migrated + retuned instance config, docs, and a live deploy.

**Architecture:** One blueprint YAML. Top-level `variables:` pass every `!input` through; the action computes every fact in three `variables:` steps (live state → four routine slots → priority/desired setpoint), then runs short side-effect steps in this order: climate validation (hard stop on `unavailable`; in-HA warning state-driven, push once on the `climate_lost` trigger), two idempotent climate calls, the room-sensor warning (state-driven; push once on `temp_lost`), the warmup-started / dismissed notification edge, a manual-run debug dump, and boost expiry LAST (its `turn_off` restarts the run). Every push sits after the climate calls because HA does not suppress a missing action even with `continue_on_error`. No `delay`/`wait`/`repeat until`; the 1-minute tick plus `on`↔`off` and `for:`-guarded outage triggers re-decide everything from live facts. Deployment reuses `scripts/deploy-blueprint.sh` (pinned TCB file, not edited) with `deploy/bathroom_heating_rack_1776551429917.json`.

**Tech Stack:** Home Assistant 2026.9.0 blueprint YAML + Jinja2; pytest 9 + PyYAML 6 + Jinja2 3.1 structure/render tests (repo convention, see `tests/test_bathroom_ventilator_structure.py`); bash deploy script; hass-cli + curl against HA.

**Spec:** `docs/superpowers/specs/2026-09-07-bathroom-climate-v2-design.md` (§2 live device facts, §4 heating rack changes + §4.2 instance retune, §6 tests, §7 rollout). Design board 20260907-134749 approved the spec.
**Session issue:** leviemartin/Blueprints_Home #13 (Entry B; the issue body is the kickoff and carries `<!-- observe:open -->`).
**Branch:** `bathroom-heating-rack-v2` (off `main` `0b7d02f`) → PR → `main`. PR body carries `Session: #13` (deploying session — never `Closes`).

```
Stakes: standard
Trigger: default-up: automation logic change in bathroom_heating_rack.yaml + new tests/instance JSON/docs; no hard trigger matched (deploy script pinned via TCB_EXTRA, not edited; no file deleted; no dependency change)
Router: deterministic
Entry: B
tcb_manifest_sha: 94cccc64bc85efa5b38309bca448ff5dd1591f7c7598391ebd0a6e8a9b66caa7
tcb_baseline: /home/martin/AI/reviews/tcb-baseline-16ef53e7f973185a.txt
TCB_EXTRA: /home/martin/AI/projects/Blueprints_Home/scripts/deploy-blueprint.sh
declared_tcb_changes:
  (none — this plan edits no TCB file)
```

**Execution mode:** subagent-driven — T1, T2 and T3 to Sonnet subagents (well-specified: the test file, the YAML, the JSON and both docs are in this plan verbatim), T4 in the main loop (operator-visible live deploy). Boards at standard dial (R1 Opus + R2 Codex) at design-time (before T1) and code-time (after T3, before T4). `/effort xhigh` at both gates, `high` otherwise.

**Shell invariants (plan-wide):** tests run from the repo root via `PY=~/projects/ceiling-fan-hue-blueprint/.venv/bin/python; $PY -m pytest tests -q` (system python3 lacks pytest; venv verified 2026-09-07: Python 3.12.3, pyyaml 6.0.3, jinja2 3.1.6, pytest 9.1.0; baseline 133 green). Never pipe test output through `tail` when the exit code matters. Per-pillar commits, explicit paths, never `git add -A`. The deploy script is not edited by this plan (it keeps `set -euo pipefail` deliberately — a deploy must fail fast). HA access: `source ~/.config/hass-cli/env`; `hass-cli -o json raw ws …` output wraps in `.result`; timestamps in query strings end in `Z`.

## Global Constraints

Locked decisions (Martin, 2026-09-07 — the plan implements them as stated; they are not re-opened at the board):
- `comfort_floor_delta` input, default 1.0 °C (0–3, step 0.5): a slot is active only while `indoor_temp < slot_target − delta`; the warmup lead uses the same ΔT (`max(0, target − indoor)`). **Slot-keyed deadband + latched opening edge (triple-check P1 + board R1-01/R1-02, spec §4.1):** a slot is `<p>_heating` while the device setpoint equals that slot's rounded target (`<p>_target_dev`); while heating its floor is `target − delta + 0.5` and its opening edge is `target_warm − warmup_max_minutes` (`<p>_open_dt`) instead of the noise-sensitive ΔT `auto_start`. No new input. **Sensor loss (R1-06; R2-003 killed by the panel):** the floor requires the room sensor — while `indoor_temp_has_primary` is false the slot heats on schedule (`<p>_active = in_window and (not has_primary or indoor < floor)`), the lead uses the climate `current_temperature` (or 20 °C), and the room-sensor warning is raised.
- Predictive motion removed: inputs `hall_motion`, `stairs_motion`, `enable_predictive_motion`, their triggers and every `*_motion_*` variable; `effective_start` = `auto_start`.
- Warmup-started notification once per transition — condition `desired_setpoint > idle_setpoint_dev + 0.1 and current_setpoint ≤ idle_setpoint_dev + 0.1` (the tick that raises the setpoint; `current_setpoint` is read before the climate call; `idle_setpoint_dev` = the idle value as the device holds it, rounded + clamped — board R1-03/R2-006) — dismissed on the tick that lowers the setpoint back to idle. At-target notification removed. Outage pushes (climate unavailable, room sensor offline) fire once per outage on the `climate_lost` (5 min) / `temp_lost` (10 min) state triggers; the in-HA warnings follow the state (R2-004).
- `continue_on_error: true` on every `notify.*` call (and on every `persistent_notification.*` call, ventilator parity). It covers runtime errors from a reachable service only: a `notify.*` name that does not exist aborts the run at that step — verified live 2026-09-07 (throwaway script, `continue_on_error: true` on `notify.does_not_exist`: "Action … not found", next step never ran; board R1-04). Hence `notify_list` filters entries to `^notify[.][a-z0-9_]+$` (R1-05/R2-001, ventilator convention), every push runs after the climate calls, and Task 4 checks each target exists before deploying.
- `desired_setpoint` rounded half-up to `state_attr(climate, 'target_temp_step')` (0.5 when the attribute is missing or 0) with epsilon-nudged grid-count arithmetic, then clamped to `min_temp`/`max_temp` (defaults 7/30): `[max, [min, (((raw / step) + 0.501) | int) * step] | max] | min | round(2)` (memory: jinja grid quantization; board R2-006 — the `idle_setpoint` selector allows 5 °C below the device minimum and HA rejects an out-of-range value). Temperature selectors keep `step: 0.5`.
- `to: ["on", "off"]` on the boost, vacation and fan triggers.
- Boost `input_boolean.turn_off` is the LAST action step (after the notification edges and the debug dump): the restart it causes would abort anything after it (board R1-09).
- Preset machinery removed: no `desired_preset`, no `climate.set_preset_mode`; idle = `heat_cool` + `idle_setpoint`; `unknown` → `heat_cool` normalisation stays.
- Weekday: `['mon',…,'sun'][now().weekday()]`.
- `hold_until ≤ target_warm` → hold anchored to the next day (`today_at(hold) + 1 day`).
- Push target `notify.mobile_app_martin_fold` only (instance data).
- Instance retune (data): evening A Mon–Fri 19:15→20:30 @ 24 °C; evening B Sat–Sun 19:15→20:30 @ 23 °C (blueprint default temp); mornings unchanged (A = blueprint defaults Mon–Fri 06:45→08:00 @ 23; B = Sat–Sun 08:30→09:30 @ 23); `warmup_min_minutes` 10; `hall_motion`/`stairs_motion` keys dropped.
- Fan coordination stays on `light.heater`; audit items F1/F2 refuted — no change to the vacation/off path.

Engineering constraints:
- Blueprint inputs are removed → the stored instance MUST be migrated in the same deploy (spec §7); an unknown key or a missing required input makes the automation `unavailable`.
- Every boolean-valued variable is a `{{ … }}` expression, never bare `true`/`false` text (the v1 `vacation_active` else-branch rendered bare `false`, a truthy string; v2 uses `expand(entity_vacation) | selectattr('state','eq','on') | list | length > 0`).
- Every gate compare on grid-derived temperatures carries `round(2)` on both sides (`indoor_temp | float | round(2) < <p>_floor | float`, where `<p>_floor` is itself `round(2)`).
- No `delay`, `wait_*`, or `repeat until` in the action; timing comes from `now()`, `today_at()` and `states[x].last_changed`.
- `mode: restart`, `max_exceeded: silent` (unchanged).
- Version strings: blueprint name `Bathroom Heating Rack v2.0.0`, description starts with `**Version: 2.0.0**` and contains `comfort floor`.
- Every input has a `description` (pinned).

**Behaviour stated for the board (not a decision re-open):**
- *Comfort-floor boundary.* `sensor.bathroom_temperature` (Hue motion sensor) reports every ~5 min at 0.1 °C with ±0.3 °C swings between reports (live history 2026-09-07 13:14–13:39: 22.3 → 21.9 → 21.6 → 22.0 → 22.3 → 22.2), and today's room sits exactly at the morning floor line (22.0 against target 23 − 1.0). Without a deadband that sequence alone produces three idle→target rises in 25 minutes, each one a `climate.set_temperature` call plus a "Warmup started" push — the per-tick spam v2 exists to remove (research anti-pattern 6). The same noise moves the ΔT-derived `auto_start` by ±1.5 min across the 1-minute tick at the window's opening edge (board R1-01). Hence, while the device holds that slot's setpoint: a 0.5 °C release deadband on the floor and an opening edge latched at `target_warm − warmup_max_minutes`. At the deadband's upper edge a flip still costs one cloud call per report, but the element is off on both sides of it (the device's own sensor reads ~1.4 °C warmer, so with setpoint `target` it stops heating at room ≈ `target − 1.4`, below the floor line). Side effect of the latch: a setpoint left at a slot's target (HA down at hold-until) opens that slot up to `warmup_max_minutes` before target-warm on its next day — bounded by the cap.
- *Room sensor offline.* The floor cannot be evaluated on the climate entity's own sensor (reads ~1.4 °C warm — larger than the default delta, so every slot would read as satisfied; board R1-06), so slots heat on schedule as in v1, bounded by the device thermostat; the warning names the fallback. The opposite policy (inhibit heating when blind, R2-003) was killed by the skeptic panel: it is the fail-silent guard that cost the ventilator five weeks, and the both-sources-blind state is not reachable on this hardware while the climate entity is available.
- *HA restart during a boost* re-arms the boost window once (the helper's `last_changed` becomes the restart time; R2-002) — pre-existing, bounded by `boost_runtime_min`.
- *Outage pushes.* One per outage via `for:`-guarded state triggers (5 min climate, 10 min sensor); an outage already live at (re)load gets the in-HA warning (state-driven) but no push (no edge), as in the ventilator.
- *Midnight.* Slots are evaluated per calendar day. A window whose hold-until is at or before target-warm is anchored to the next day and therefore runs from `auto_start` until midnight; the after-midnight part is not honoured (documented in the input description and the requirements doc). Martin's four slots all end before midnight.
- *Warmup push per transition.* A fan pause inside a window lowers the setpoint (dismiss) and the resume raises it again (new push) — by definition of "once per transition" (spec §4.1). v1 pushed on every tick because the Tuya device always reports `preset_mode: eco` (3,336 logged `Service not found` errors since 09-04 = one per active-window minute).
- *Tuya latency.* If the cloud takes > 60 s to reflect a new setpoint, the next tick still sees `current_setpoint` at idle and repeats the call + notification once. Bounded, not observed today (setpoint attribute updates within seconds in the 09-07 history).

---

## Phase 0 — Pre-flight (Claude)

**Context budget:** ~20k tokens · 0 files edited · shell only · main loop.

- [x] Branch `bathroom-heating-rack-v2` created off `main` (`0b7d02f`) on 2026-09-07.
- [x] TCB baseline `/home/martin/AI/reviews/tcb-baseline-16ef53e7f973185a.txt` verified with `TCB_EXTRA` = deploy script: `verify` rc=0, aggregate `94cccc64…`, ABSENT lines 0.
- [x] HA 2026.9.0 reachable (`Europe/Amsterdam`); `notify.mobile_app_martin_fold` exists, `notify.mobile_app_martin` does not; `climate.heatingrack_bathroom` state `unknown`, `target_temp_step` 1.0, min 7, max 30, `preset_mode` eco, `temperature` 7.0; `light.heater`, `sensor.bathroom_temperature` (22.0), both helpers present.
- [x] Live instance config `1776551429917` read (alias "Bathroom Heating Rack v1.0.0", entity `automation.bathroom_heating_rack_v1_0_0`, `on`): keys `hall_motion: binary_sensor.hall_motion_2`, `stairs_motion: binary_sensor.staircase_motion`, `notify_targets: [notify.mobile_app_martin]`, `warmup_min_minutes: 28`, `evening_a_hold_until: 19:45:00`, `evening_b_target_warm: 18:30:00`, `evening_b_hold_until: 20:00:00`, `boost_target_temp: 26`, `boost_runtime_min: 55`, `morning_b_days: [sat, sun]`, `morning_b_hold_until: 09:30:00`, `evening_a_days: [mon…fri]`, `evening_b_days: [sat, sun]`, `vacation_off: [input_boolean.heating_rack_vacation]`, `boost_toggle: input_boolean.heating_rack_boost`.
- [x] Baseline suite green: `PASS=133 FAIL=0`.
- [x] Scratch run of the inline artifacts in a throwaway repo copy (lesson from session #11): rack file `PASS=116 FAIL=0` on the v2 YAML; RED against v1.1.1 `PASS=20 FAIL=96`; full suite `PASS=249 FAIL=0`; `scripts/deploy-blueprint.sh --dry-run` on the instance JSON passes (`18 inputs`); HA `validate_config` on the input-substituted v2 config: `triggers valid, actions valid`; live `/api/template` renders of the `notify_list` filter, the idle rounding (7.5 → 8.0) and the floor arithmetic match the harness (all re-run after the board fix wave).
- [x] Empirical check (board R1-04): a throwaway HA script with `continue_on_error: true` on `notify.does_not_exist_board_probe` stopped at that step (`script_execution: error`, "Action … not found", the next step never ran); script deleted afterwards.
- [x] Error baseline recorded: `system_log/list` shows 3,336 occurrences of "Bathroom Heating Rack v1.0.0: Choose at step 9: choice 1: Repeat at step 3: Error executing script. Service not found" (first 2026-09-04) — the v1 warmup notification fires every active-window minute and targets a non-existent service.
- [ ] At T4 time only: re-read the live instance config (the deploy script backs it up to `deploy/1776551429917.prev.json`, gitignored) and confirm `git rev-parse HEAD` = `origin/main`.

**Observation criteria ([8] applies — deploying session; issue #13 carries `<!-- observe:open -->`):**
1. `automation.bathroom_heating_rack_v1_0_0` (entity id unchanged; alias becomes v2.0.0) is `on` immediately after deploy and still `on` 24 h later.
2. A manual run's `heating_rack_debug` notification lists `step`, `Comfort floor`, and per slot `hold_until`, `in_window`, `active`, plus `setpoint=… (raw …)` — v2-only fields.
3. Next morning window (Mon–Fri target-warm 06:45 / Sat–Sun 08:30), decided by the trace at `auto_start` (`changed_variables`: `ma_active`/`mb_active`, `indoor_temp`, `<p>_floor`): **(a)** if `indoor_temp < floor` at `auto_start` → the setpoint rises to 23 at `auto_start` (never earlier than `target_warm − 60 min`) with exactly one "Heating Rack — Warmup Started" push per uninterrupted heating episode (a fan pause + resume inside the window is one more push, expected), no idle↔target flip while the room hovers at the line, and the setpoint returns to 7 at hold-until or once `indoor ≥ floor + 0.5`; **(b)** if `indoor_temp ≥ floor` at `auto_start` → `active=false`, `desired_setpoint=7.0`, no `climate.set_temperature` call and zero pushes for that window. Either branch passes; a push in branch (b), or more than one push per episode in branch (a), fails.
4. Evening window observed once with the same two branches: opening edge = 19:15 − lead (lead 10–60 min; no 90-min-early start), setpoint 24 on Mon–Fri / 23 on Sat–Sun in branch (a), back to 7 by 20:30.
5. Zero `Action … not found` / `Error executing script` lines for this automation in the HA log over 48 h; `heating_rack_warmup_started` created at most once per transition; no outage push unless the climate or the sensor was really away for the grace period.

---

## Task 1: Tests first (RED) + migrated instance JSON

**Model tier:** Sonnet
**Rationale:** Both files below are complete; the task is transcription plus running the suite RED against v1.1.1.
**Effort:** high (operator `/effort high` checkpoint).

**Context budget:** ~30k tokens · 2 files created · ~780 LOC · fits one Sonnet subagent window.

**Files:**
- Create: `tests/test_bathroom_heating_rack_structure.py`
- Create: `deploy/bathroom_heating_rack_1776551429917.json`
- Test: `tests/test_bathroom_heating_rack_structure.py`

**Interfaces:**
- Consumes: `bathroom_heating_rack.yaml` (v1.1.1 now, v2.0.0 after Task 2); `scripts/deploy-blueprint.sh --dry-run` (unchanged).
- Produces: the input key set `EXPECTED_INPUTS`, the trigger ids (`periodic, boost_change, vacation_change, fan_change, ha_start, climate_lost, temp_lost`), the action-step order and the variable names Task 2 must emit (in file order across the three `variables:` steps): `indoor_temp_primary, indoor_temp_fallback, indoor_temp_has_primary, indoor_temp_has_fallback, indoor_temp_both_unavailable, indoor_temp, current_setpoint, current_hvac_mode, current_hvac_mode_normalized, setpoint_step, setpoint_min, setpoint_max, idle_setpoint_dev, fan_is_on, notify_list, today_dow, now_dt, vacation_active, boost_runtime_min_int, boost_is_on, boost_age_min, boost_active, boost_expired` · per slot `<p>_in_days, <p>_target_warm_dt, <p>_hold_until_dt, <p>_target_dev, <p>_heating, <p>_delta_T, <p>_warmup_min, <p>_auto_start_dt, <p>_open_dt, <p>_in_window, <p>_floor, <p>_active` for `p ∈ {ma, mb, ea, eb}` · `morning_active, evening_active, morning_temp, evening_temp` · `desired_mode, desired_setpoint_raw, desired_setpoint, active_priority`. The instance JSON is the file Task 4 deploys.

- [ ] **Step 1: Write `tests/test_bathroom_heating_rack_structure.py` (verbatim)**

```python
"""Structural + rendered-logic pins for bathroom_heating_rack.yaml (Bathroom Heating Rack v2.0.0).

Run: cd ~/AI/projects/Blueprints_Home && \
     ~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q
"""
import ast
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment

ROOT = Path(__file__).resolve().parent.parent
BP_PATH = ROOT / "bathroom_heating_rack.yaml"
INSTANCE_PATH = ROOT / "deploy" / "bathroom_heating_rack_1776551429917.json"
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy-blueprint.sh"
HA_BP_PATH = "leviemartin/bathroom_heating_rack.yaml"


class _Input:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"!input {self.name}"

    def __eq__(self, other):
        return isinstance(other, _Input) and other.name == self.name


class HassLoader(yaml.SafeLoader):
    pass


HassLoader.add_constructor("!input", lambda loader, node: _Input(loader.construct_scalar(node)))


@pytest.fixture(scope="module")
def bp():
    with BP_PATH.open() as fh:
        return yaml.load(fh, Loader=HassLoader)


@pytest.fixture(scope="module")
def inputs(bp):
    return bp["blueprint"]["input"]


def norm(s):
    return " ".join(str(s).split())


def var_blocks(bp):
    """Every top-level `variables:` step of the action, in file order."""
    return [step["variables"] for step in bp["action"] if "variables" in step]


def get_var(bp, name):
    for block in var_blocks(bp):
        if name in block:
            return block[name]
    raise KeyError(name)


def step_kind(step):
    if "service" in step:
        return f"service:{step['service']}"
    for k in ("choose", "stop", "variables", "condition", "repeat"):
        if k in step:
            return k
    return "other"


def branch_cond(branch):
    return norm(branch["conditions"][0]["value_template"])


def walk(node):
    """Yield every dict inside a nested YAML structure."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)


def choose_steps(bp):
    return [s for s in bp["action"] if "choose" in s]


def service_of(seq):
    """The first `service:` name inside a sequence (searching nested dicts)."""
    for d in walk(seq):
        if "service" in d:
            return d["service"]
    return None


# ---------------------------------------------------------------- render harness
NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)   # a Tuesday


class _State:
    def __init__(self, state, minutes_ago=0.0, attrs=None):
        self.state = state
        self.minutes_ago = minutes_ago
        self.last_changed = NOW - timedelta(minutes=minutes_ago)
        self.attributes = attrs or {}


class _States:
    """HA `states`: callable -> state string; item access -> state object or None."""

    def __init__(self, table):
        self.table = table

    def __call__(self, eid):
        s = self.table.get(eid)
        return s.state if s else "unavailable"

    def __getitem__(self, eid):
        return self.table.get(eid)

    def rebase(self, when):
        """Make every `minutes_ago` relative to `when` (a test that moves `now` must not turn
        "boost 5 min ago" into "boost 7 h ago")."""
        for s in self.table.values():
            s.last_changed = when - timedelta(minutes=s.minutes_ago)
        return self


def parse(s):
    s = s.strip()
    try:
        return ast.literal_eval(s)
    except (ValueError, SyntaxError):
        return s


def as_datetime(v):
    return v if isinstance(v, datetime) else datetime.fromisoformat(str(v).strip())


def make_env(states, when):
    env = Environment()
    env.tests["match"] = lambda v, pattern: re.match(pattern, str(v)) is not None   # HA's `match` test

    def today_at(hhmmss):
        parts = [int(p) for p in str(hhmmss).split(":")] + [0, 0]
        return when.replace(hour=parts[0], minute=parts[1], second=parts[2], microsecond=0)

    def expand(ids):
        ids = [ids] if isinstance(ids, str) else list(ids)
        return [states[e] for e in ids if states[e]]

    env.globals.update(
        states=states,
        now=lambda: when,
        today_at=today_at,
        timedelta=timedelta,
        as_datetime=as_datetime,
        expand=expand,
        is_state=lambda eid, s: states(eid) == s,
        state_attr=lambda eid, a: (states[eid].attributes.get(a) if states[eid] else None),
    )
    return env


def render_vars(bp, ctx, states, upto, when=NOW):
    """Render every action-level `variables:` template in file order up to and including `upto`."""
    env = make_env(states.rebase(when), when)
    out = dict(ctx)
    for block in var_blocks(bp):
        for name, tpl in block.items():
            out[name] = parse(env.from_string(str(tpl)).render(**out))
            if name == upto:
                return out
    raise KeyError(upto)


def render_tpl(bp, tpl, states, when=NOW, **ctx):
    env = make_env(states.rebase(when), when)
    return parse(env.from_string(str(tpl)).render(**ctx))


WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"]


def base_ctx(**over):
    ctx = dict(
        entity_climate="climate.rack", sensor_bathroom_temp="sensor.t", entity_fan="light.fan",
        entity_vacation=["input_boolean.vac"], entity_boost="input_boolean.boost",
        boost_runtime_min=30, boost_target_temp=26, idle_setpoint=7, comfort_floor_delta=1.0,
        warmup_base_min=10, warmup_per_degree_min=5, warmup_min_minutes=10, warmup_max_minutes=60,
        enable_notifications=True, notify_targets=[],
        morning_a_days=WEEKDAYS, morning_a_target_warm="06:45:00", morning_a_hold_until="08:00:00",
        morning_a_target_temp=23,
        morning_b_days=[], morning_b_target_warm="08:30:00", morning_b_hold_until="10:00:00",
        morning_b_target_temp=23,
        evening_a_days=[], evening_a_target_warm="19:15:00", evening_a_hold_until="20:30:00",
        evening_a_target_temp=24,
        evening_b_days=[], evening_b_target_warm="20:30:00", evening_b_hold_until="22:00:00",
        evening_b_target_temp=23,
        trigger={"id": "periodic"},
    )
    ctx.update(over)
    return ctx


def world(**kw):
    table = {
        "sensor.t": _State("22.0"),
        "climate.rack": _State("unknown", attrs={"temperature": 7.0, "current_temperature": 23.4,
                                                 "target_temp_step": 1.0}),
        "light.fan": _State("off", minutes_ago=180),
        "input_boolean.vac": _State("off", minutes_ago=600),
        "input_boolean.boost": _State("off", minutes_ago=600),
    }
    table.update(kw)
    return _States(table)


def at(hhmm, day=NOW):
    hh, mm = map(int, hhmm.split(":"))
    return day.replace(hour=hh, minute=mm, second=0, microsecond=0)


def decide(bp, ctx, w, when=NOW):
    out = render_vars(bp, ctx, w, "active_priority", when)
    return out["active_priority"], out["desired_setpoint"]


# ---------------------------------------------------------------- structure pins

def test_version_bumped(bp):
    assert bp["blueprint"]["name"] == "Bathroom Heating Rack v2.0.0"
    assert bp["blueprint"]["description"].lstrip().startswith("**Version: 2.0.0**")
    assert "comfort floor" in bp["blueprint"]["description"]


EXPECTED_INPUTS = {
    "heating_climate", "bathroom_temp_sensor", "fan_switch", "vacation_off", "boost_toggle",
    "boost_target_temp", "boost_runtime_min", "idle_setpoint", "comfort_floor_delta",
    "morning_a_days", "morning_a_target_warm", "morning_a_hold_until", "morning_a_target_temp",
    "morning_b_days", "morning_b_target_warm", "morning_b_hold_until", "morning_b_target_temp",
    "evening_a_days", "evening_a_target_warm", "evening_a_hold_until", "evening_a_target_temp",
    "evening_b_days", "evening_b_target_warm", "evening_b_hold_until", "evening_b_target_temp",
    "warmup_base_min", "warmup_per_degree_min", "warmup_min_minutes", "warmup_max_minutes",
    "enable_notifications", "notify_targets",
}


def test_input_schema_exact_keys(inputs):
    assert set(inputs) == EXPECTED_INPUTS


def test_removed_inputs_absent(inputs):
    for k in ("hall_motion", "stairs_motion", "enable_predictive_motion"):
        assert k not in inputs


def test_selectors_and_defaults(inputs):
    cf = inputs["comfort_floor_delta"]
    assert cf["default"] == 1.0
    assert cf["selector"]["number"] == {"min": 0, "max": 3, "step": 0.5, "unit_of_measurement": "°C"}
    assert inputs["fan_switch"]["selector"]["entity"]["domain"] == "light"
    assert inputs["vacation_off"]["default"] == []
    assert inputs["vacation_off"]["selector"]["entity"] == {"domain": "input_boolean", "multiple": True}
    assert inputs["boost_toggle"]["selector"]["entity"]["domain"] == "input_boolean"
    assert "default" not in inputs["boost_toggle"]
    assert inputs["idle_setpoint"]["default"] == 7
    assert inputs["warmup_min_minutes"]["default"] == 10
    assert inputs["warmup_max_minutes"]["default"] == 60
    assert inputs["enable_notifications"]["default"] is True
    assert inputs["notify_targets"]["default"] == []
    assert inputs["notify_targets"]["selector"] == {"text": {"multiple": True}}
    for slot in ("morning_a", "morning_b", "evening_a", "evening_b"):
        assert inputs[f"{slot}_target_temp"]["selector"]["number"]["step"] == 0.5
        assert inputs[f"{slot}_target_warm"]["selector"] == {"time": {}}
        assert inputs[f"{slot}_hold_until"]["selector"] == {"time": {}}
    assert inputs["morning_a_days"]["default"] == WEEKDAYS
    assert inputs["evening_a_days"]["default"] == []


def test_every_input_has_a_description(inputs):
    missing = [k for k, v in inputs.items() if not str(v.get("description", "")).strip()]
    assert missing == []


def test_variable_mappings(bp):
    v = bp["variables"]
    assert v["entity_climate"] == _Input("heating_climate")
    assert v["sensor_bathroom_temp"] == _Input("bathroom_temp_sensor")
    assert v["entity_fan"] == _Input("fan_switch")
    assert v["entity_vacation"] == _Input("vacation_off")
    assert v["entity_boost"] == _Input("boost_toggle")
    assert v["comfort_floor_delta"] == _Input("comfort_floor_delta")
    assert v["notify_targets"] == _Input("notify_targets")
    for k in ("sensor_hall_motion", "sensor_stairs_motion", "enable_predictive_motion"):
        assert k not in v
    # every input except the entity roles is passed through under its own name
    passthrough = EXPECTED_INPUTS - {"heating_climate", "bathroom_temp_sensor", "fan_switch", "vacation_off", "boost_toggle"}
    for k in passthrough:
        assert v[k] == _Input(k), k


def test_mode_restart(bp):
    assert bp["mode"] == "restart"
    assert bp["max_exceeded"] == "silent"


def test_trigger_roster(bp):
    trig = {t["id"]: t for t in bp["trigger"]}
    assert list(trig) == ["periodic", "boost_change", "vacation_change", "fan_change", "ha_start", "climate_lost", "temp_lost"]
    assert trig["periodic"] == {"platform": "time_pattern", "minutes": "/1", "id": "periodic"}
    assert trig["boost_change"] == {"platform": "state", "entity_id": _Input("boost_toggle"), "to": ["on", "off"], "id": "boost_change"}
    assert trig["vacation_change"] == {"platform": "state", "entity_id": _Input("vacation_off"), "to": ["on", "off"], "id": "vacation_change"}
    assert trig["fan_change"] == {"platform": "state", "entity_id": _Input("fan_switch"), "to": ["on", "off"], "id": "fan_change"}
    assert trig["ha_start"] == {"platform": "homeassistant", "event": "start", "id": "ha_start"}
    assert trig["climate_lost"] == {"platform": "state", "entity_id": _Input("heating_climate"), "to": "unavailable",
                                    "for": {"minutes": 5}, "id": "climate_lost"}
    assert trig["temp_lost"] == {"platform": "state", "entity_id": _Input("bathroom_temp_sensor"), "to": ["unavailable", "unknown"],
                                 "for": {"minutes": 10}, "id": "temp_lost"}


def test_action_shape(bp):
    kinds = [step_kind(s) for s in bp["action"]]
    assert kinds == ["variables", "variables", "choose", "variables", "choose", "choose", "choose", "choose", "choose", "choose"]
    chooses = choose_steps(bp)
    # climate validation: unavailable → create + (push on the edge) + stop; available → dismiss
    unavailable, available = chooses[0]["choose"]
    assert branch_cond(unavailable) == "{{ states(entity_climate) == 'unavailable' }}"
    assert service_of(unavailable["sequence"]) == "persistent_notification.create"
    assert unavailable["sequence"][-1] == {"stop": "Climate entity unavailable"}
    assert branch_cond(available) == "{{ states(entity_climate) != 'unavailable' }}"
    assert available["sequence"] == [{"service": "persistent_notification.dismiss", "continue_on_error": True,
                                      "data": {"notification_id": "heating_rack_climate_unavailable"}}]
    assert service_of(chooses[1]["choose"][0]["sequence"]) == "climate.set_hvac_mode"
    assert service_of(chooses[2]["choose"][0]["sequence"]) == "climate.set_temperature"
    # room-sensor warning sits AFTER the climate calls
    lost, back = chooses[3]["choose"]
    assert branch_cond(lost) == "{{ not indoor_temp_has_primary }}"
    assert service_of(lost["sequence"]) == "persistent_notification.create"
    assert branch_cond(back) == "{{ indoor_temp_has_primary }}"
    assert back["sequence"] == [{"service": "persistent_notification.dismiss", "continue_on_error": True,
                                 "data": {"notification_id": "heating_rack_sensor_warning"}}]
    assert service_of(chooses[4]["choose"][0]["sequence"]) == "persistent_notification.create"
    assert service_of(chooses[4]["choose"][1]["sequence"]) == "persistent_notification.dismiss"
    assert service_of(chooses[5]["choose"][0]["sequence"]) == "persistent_notification.create"
    assert service_of(chooses[6]["choose"][0]["sequence"]) == "input_boolean.turn_off"
    for c in chooses:
        assert "default" not in c


def test_boost_expiry_is_the_last_step(bp):
    # the turn_off restarts the automation (mode: restart); anything after it would be aborted
    last = bp["action"][-1]
    assert branch_cond(last["choose"][0]) == "{{ boost_expired }}"
    assert service_of(last["choose"][0]["sequence"]) == "input_boolean.turn_off"
    kinds = [service_of(s["choose"][0]["sequence"]) if "choose" in s else None for s in bp["action"]]
    assert kinds.index("climate.set_temperature") < kinds.index("input_boolean.turn_off")


def test_outage_pushes_are_edge_gated(bp):
    chooses = choose_steps(bp)
    for idx, trigger_id in ((0, "climate_lost"), (3, "temp_lost")):
        seq = chooses[idx]["choose"][0]["sequence"]
        nested = [d for d in seq if "choose" in d]
        assert len(nested) == 1
        (branch,) = nested[0]["choose"]
        assert branch_cond(branch) == f"{{{{ trigger.id | default('') == '{trigger_id}' }}}}"
        assert any("repeat" in d for d in walk(branch["sequence"]))
        assert "default" not in nested[0]


def test_no_preset_machinery(bp):
    names = [n for b in var_blocks(bp) for n in b]
    assert not any("preset" in n for n in names)
    assert all(d.get("service") != "climate.set_preset_mode" for d in walk(bp["action"]))
    assert "preset" not in BP_PATH.read_text().split("action:", 1)[1]


def test_no_predictive_motion_remnants(bp):
    names = [n for b in var_blocks(bp) for n in b]
    assert not any("motion" in n for n in names)
    assert "motion" not in BP_PATH.read_text().split("domain: automation", 1)[1]


def test_weekday_locale_safe(bp):
    tpl = norm(get_var(bp, "today_dow"))
    assert tpl == "{{ ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'][now().weekday()] }}"
    assert "strftime('%a')" not in BP_PATH.read_text()


@pytest.mark.parametrize("slot,prefix", [("morning_a", "ma"), ("morning_b", "mb"), ("evening_a", "ea"), ("evening_b", "eb")])
def test_slot_templates(bp, slot, prefix):
    assert norm(get_var(bp, f"{prefix}_hold_until_dt")) == norm(
        f"{{% set w = today_at({slot}_target_warm) %}}{{% set h = today_at({slot}_hold_until) %}}"
        "{{ h + timedelta(days=1) if h <= w else h }}")
    assert norm(get_var(bp, f"{prefix}_target_dev")) == norm(
        f"{{{{ (((({slot}_target_temp | float) / (setpoint_step | float) + 0.501) | int) * (setpoint_step | float)) | round(2) }}}}")
    assert norm(get_var(bp, f"{prefix}_heating")) == norm(
        f"{{{{ (current_setpoint | float - {prefix}_target_dev | float) | abs < 0.1 }}}}")
    assert norm(get_var(bp, f"{prefix}_open_dt")) == norm(
        f"{{{{ as_datetime({prefix}_target_warm_dt) - timedelta(minutes=(warmup_max_minutes | int if {prefix}_heating else {prefix}_warmup_min | int)) }}}}")
    assert norm(get_var(bp, f"{prefix}_in_window")) == norm(
        f"{{{{ {prefix}_in_days and as_datetime({prefix}_open_dt) <= as_datetime(now_dt) "
        f"and as_datetime(now_dt) < as_datetime({prefix}_hold_until_dt) }}}}")
    assert norm(get_var(bp, f"{prefix}_floor")) == norm(
        f"{{{{ ({slot}_target_temp | float - comfort_floor_delta | float + (0.5 if {prefix}_heating else 0)) | round(2) }}}}")
    assert norm(get_var(bp, f"{prefix}_active")) == norm(
        f"{{{{ {prefix}_in_window and (not indoor_temp_has_primary or indoor_temp | float | round(2) < {prefix}_floor | float) }}}}")
    assert norm(get_var(bp, f"{prefix}_auto_start_dt")) == norm(
        f"{{{{ as_datetime({prefix}_target_warm_dt) - timedelta(minutes={prefix}_warmup_min | int) }}}}")


def test_setpoint_rounding_template(bp):
    assert norm(get_var(bp, "desired_setpoint")) == norm(
        "{% if desired_setpoint_raw == 'none' %}none{% else %}"
        "{{ [setpoint_max | float, [setpoint_min | float, ((((desired_setpoint_raw | float) / (setpoint_step | float) + 0.501) | int) * (setpoint_step | float))] | max] | min | round(2) }}{% endif %}")
    assert norm(get_var(bp, "idle_setpoint_dev")) == norm(
        "{{ [setpoint_max | float, [setpoint_min | float, ((((idle_setpoint | float) / (setpoint_step | float) + 0.501) | int) * (setpoint_step | float))] | max] | min | round(2) }}")
    assert norm(get_var(bp, "setpoint_min")) == "{{ state_attr(entity_climate, 'min_temp') | float(7) }}"
    assert norm(get_var(bp, "setpoint_max")) == "{{ state_attr(entity_climate, 'max_temp') | float(30) }}"
    assert norm(get_var(bp, "notify_list")) == "{{ notify_targets | select('match', '^notify[.][a-z0-9_]+$') | list }}"
    assert "floor_hysteresis" not in BP_PATH.read_text()
    assert norm(get_var(bp, "setpoint_step")) == norm(
        "{% set s = state_attr(entity_climate, 'target_temp_step') | float(0) %}{{ s if s > 0 else 0.5 }}")


def test_service_calls_idempotent(bp):
    chooses = choose_steps(bp)
    assert branch_cond(chooses[1]["choose"][0]) == "{{ current_hvac_mode_normalized != desired_mode }}"
    assert branch_cond(chooses[2]["choose"][0]) == norm(
        "{{ desired_setpoint != 'none' and (current_setpoint | float - desired_setpoint | float) | abs > 0.1 }}")
    call = chooses[2]["choose"][0]["sequence"][0]
    assert call["data"] == {"temperature": "{{ desired_setpoint | float }}"}
    assert call["target"] == {"entity_id": "{{ entity_climate }}"}


def test_notify_fanout_continue_on_error(bp):
    repeats = [d["repeat"] for d in walk(bp["action"]) if "repeat" in d]
    assert len(repeats) == 3
    assert "{{ notify_targets }}" not in BP_PATH.read_text().split("action:", 1)[1]
    for r in repeats:
        assert r["for_each"] == "{{ notify_list }}"
        (call,) = r["sequence"]
        assert call["service"] == "{{ repeat.item }}"
        assert call["continue_on_error"] is True
    for d in walk(bp["action"]):
        if str(d.get("service", "")).startswith("persistent_notification."):
            assert d.get("continue_on_error") is True, d["service"]


def test_warmup_notification_edge_shape(bp):
    branch_on, branch_off = choose_steps(bp)[4]["choose"]
    assert branch_cond(branch_on) == norm(
        "{{ enable_notifications and desired_setpoint != 'none' and desired_setpoint | float > idle_setpoint_dev | float + 0.1 "
        "and current_setpoint | float <= idle_setpoint_dev | float + 0.1 }}")
    ids = [d["notification_id"] for d in walk(branch_on["sequence"]) if "notification_id" in d]
    assert ids == ["heating_rack_warmup_started"]
    assert any("repeat" in d for d in walk(branch_on["sequence"]))
    assert branch_cond(branch_off) == norm(
        "{{ desired_setpoint != 'none' and desired_setpoint | float <= idle_setpoint_dev | float + 0.1 "
        "and current_setpoint | float > idle_setpoint_dev | float + 0.1 }}")
    assert branch_off["sequence"] == [{"service": "persistent_notification.dismiss", "continue_on_error": True,
                                       "data": {"notification_id": "heating_rack_warmup_started"}}]


def test_at_target_notification_removed(bp):
    text = BP_PATH.read_text()
    assert "heating_rack_target_reached" not in text
    assert "At Target" not in text


def test_debug_block_manual_only(bp):
    branch = choose_steps(bp)[5]["choose"][0]
    assert branch_cond(branch) == "{{ trigger.id | default('manual') == 'manual' }}"
    ids = [d["notification_id"] for d in walk(branch["sequence"]) if "notification_id" in d]
    assert ids == ["heating_rack_debug"]


def test_no_bare_boolean_text(bp):
    for block in var_blocks(bp):
        for name, tpl in block.items():
            s = norm(tpl)
            assert not re.search(r"%\}\s*(true|false)\s*\{%", s, re.I), name
            assert not re.search(r"%\}\s*(true|false)\s*$", s, re.I), name


def test_no_bare_condition_steps_anywhere(bp):
    for step in bp["action"]:
        assert step_kind(step) != "condition"


# ---------------------------------------------------------------- rendered logic

def test_today_dow_rows(bp):
    assert render_tpl(bp, get_var(bp, "today_dow"), world()) == "tue"
    assert render_tpl(bp, get_var(bp, "today_dow"), world(), when=NOW + timedelta(days=5)) == "sun"


@pytest.mark.parametrize("raw,step,expected", [
    (23.5, 1.0, 24.0), (23.5, 0.5, 23.5), (23.2, 1.0, 23.0), (22.5, 1.0, 23.0),
    (7.0, 1.0, 7.0), (7.0, 0.5, 7.0), (26.0, 1.0, 26.0),
    # non-dyadic rows (0.1 grid): raw/step is not binary-exact — the epsilon nudge must hold
    (22.3, 0.1, 22.3), (21.7, 0.1, 21.7), (22.35, 0.1, 22.4), (22.64, 0.1, 22.6), (22.65, 0.1, 22.7),
    (22.9, 0.1, 22.9), (22.4, 0.1, 22.4),
])
def test_setpoint_rounding_rows(bp, raw, step, expected):
    got = render_tpl(bp, get_var(bp, "desired_setpoint"), world(), desired_setpoint_raw=raw, setpoint_step=step,
                     setpoint_min=7.0, setpoint_max=30.0)
    assert got == pytest.approx(expected)


@pytest.mark.parametrize("raw,lo,hi,expected", [(5.0, 7.0, 30.0, 7.0), (31.0, 7.0, 30.0, 30.0), (26.0, 7.0, 25.0, 25.0), (24.0, 7.0, 30.0, 24.0)])
def test_setpoint_clamped_to_device_range(bp, raw, lo, hi, expected):
    got = render_tpl(bp, get_var(bp, "desired_setpoint"), world(), desired_setpoint_raw=raw, setpoint_step=1.0,
                     setpoint_min=lo, setpoint_max=hi)
    assert got == pytest.approx(expected)


@pytest.mark.parametrize("idle,step,attrs,expected", [
    (7, 1.0, {}, 7.0),
    (7.5, 1.0, {}, 8.0),          # off-grid idle is written as 8.0 — every idle comparison must use this value
    (7.5, 0.5, {}, 7.5),
    (5, 1.0, {}, 7.0),            # selector allows 5, device minimum is 7 → clamped
    (5, 1.0, {"min_temp": 5.0}, 5.0),
    (7, 1.0, {"min_temp": None}, 7.0),
])
def test_idle_setpoint_dev_rows(bp, idle, step, attrs, expected):
    a = {"temperature": 7.0, "current_temperature": 23.4, "target_temp_step": step, "min_temp": 7.0, "max_temp": 30.0}
    a.update(attrs)
    out = render_vars(bp, base_ctx(idle_setpoint=idle), world(**{"climate.rack": _State("unknown", attrs=a)}), "idle_setpoint_dev")
    assert out["idle_setpoint_dev"] == expected


def test_setpoint_range_defaults_when_attrs_missing(bp):
    out = render_vars(bp, base_ctx(), world(), "idle_setpoint_dev")
    assert (out["setpoint_min"], out["setpoint_max"], out["idle_setpoint_dev"]) == (7.0, 30.0, 7.0)


@pytest.mark.parametrize("targets,expected", [
    (["notify.mobile_app_martin_fold"], ["notify.mobile_app_martin_fold"]),
    (["notify.mobile_app_martin_fold", "mobile_app_x", "notify.Bad-Name", "script.foo", "notify.a b"], ["notify.mobile_app_martin_fold"]),
    ([], []),
])
def test_notify_list_filters_names(bp, targets, expected):
    assert render_vars(bp, base_ctx(notify_targets=targets), world(), "notify_list")["notify_list"] == expected


def _rack(setpoint, step=1.0, current=23.4):
    return {"climate.rack": _State("unknown", attrs={"temperature": setpoint, "current_temperature": current, "target_temp_step": step})}


@pytest.mark.parametrize("indoor,active", [
    (23.0, True),     # at the line but this slot is heating → deadband keeps it active
    (23.4, True),
    (23.5, False),    # line + 0.5 → released
    (22.9, True),
])
def test_comfort_floor_hysteresis_rows(bp, indoor, active):
    # the device holds this slot's setpoint (24) → the slot is heating: floor 23.5
    out = render_vars(bp, _evening_ctx(), world(**_rack(24.0), **{"sensor.t": _State(str(indoor))}), "ea_active", at("19:30"))
    assert (out["ea_target_dev"], out["ea_heating"], out["ea_floor"]) == (24.0, True, 23.5)
    assert out["ea_active"] is active
    # setpoint at idle: strict floor
    out = render_vars(bp, _evening_ctx(), world(**{"sensor.t": _State(str(indoor))}), "ea_active", at("19:30"))
    assert (out["ea_heating"], out["ea_floor"]) == (False, 23.0)
    assert out["ea_active"] is (indoor < 23.0)


def test_deadband_is_keyed_to_the_slot_not_any_raised_setpoint(bp):
    # boost (26) expiring inside the evening window at 23.3 °C must hand over to idle, not to P4_evening
    out = render_vars(bp, _evening_ctx(), world(**_rack(26.0), **{"sensor.t": _State("23.3")}), "active_priority", at("19:30"))
    assert (out["ea_heating"], out["ea_floor"], out["ea_active"]) == (False, 23.0, False)
    assert out["active_priority"] == "P6_idle"
    # a manual/other setpoint of 8.0 does not widen the floor either
    out = render_vars(bp, _evening_ctx(), world(**_rack(8.0), **{"sensor.t": _State("23.2")}), "ea_active", at("19:30"))
    assert (out["ea_heating"], out["ea_active"]) == (False, False)


def test_opening_edge_latches_while_heating(bp):
    # indoor 22.0 → ΔT 2 → lead 20 → auto_start 18:55. A warmer report (22.4 → lead 18 → 18:57) must not
    # close a window that is already heating; the latched edge is target_warm − warmup_max = 18:15.
    out = render_vars(bp, _evening_ctx(), world(**{"sensor.t": _State("22.4")}), "ea_active", at("18:56"))
    assert as_datetime(out["ea_auto_start_dt"]).strftime("%H:%M") == "18:57"
    assert (out["ea_heating"], out["ea_in_window"], out["ea_active"]) == (False, False, False)
    out = render_vars(bp, _evening_ctx(), world(**_rack(24.0), **{"sensor.t": _State("22.4")}), "ea_active", at("18:56"))
    assert as_datetime(out["ea_open_dt"]).strftime("%H:%M") == "18:15"
    assert (out["ea_heating"], out["ea_in_window"], out["ea_active"]) == (True, True, True)
    # but not before the latched edge, and never past hold_until
    out = render_vars(bp, _evening_ctx(), world(**_rack(24.0), **{"sensor.t": _State("22.4")}), "ea_active", at("18:10"))
    assert out["ea_in_window"] is False
    out = render_vars(bp, _evening_ctx(), world(**_rack(24.0), **{"sensor.t": _State("22.4")}), "ea_active", at("20:30"))
    assert out["ea_in_window"] is False


def test_floor_suspended_without_room_sensor(bp):
    # room sensor dead, rack's own sensor 23.4 (> floor 23.0): the slot still heats on schedule
    w = world(**{"sensor.t": _State("unavailable")})
    out = render_vars(bp, _evening_ctx(), w, "active_priority", at("19:30"))
    assert (out["indoor_temp_has_primary"], out["indoor_temp"]) == (False, 23.4)
    assert (out["ea_warmup_min"], out["ea_active"], out["active_priority"], out["desired_setpoint"]) == (13, True, "P4_evening", 24.0)
    # both sources gone: 20 °C lead, still on schedule
    w = world(**{"sensor.t": _State("unavailable"), "climate.rack": _State("unknown", attrs={"temperature": 7.0, "target_temp_step": 1.0})})
    out = render_vars(bp, _evening_ctx(), w, "active_priority", at("19:30"))
    assert (out["indoor_temp_both_unavailable"], out["indoor_temp"], out["ea_active"], out["active_priority"]) == (True, 20, True, "P4_evening")
    # with the sensor back at 23.4 the same slot is satisfied
    out = render_vars(bp, _evening_ctx(), world(**{"sensor.t": _State("23.4")}), "active_priority", at("19:30"))
    assert (out["ea_active"], out["active_priority"]) == (False, "P6_idle")


def test_comfort_floor_non_dyadic_rows(bp):
    # target 23.5, delta 0.5 → floor 23.0; indoor 22.9 from a "22.9" state string
    ctx = _evening_ctx(evening_a_target_temp=23.5, comfort_floor_delta=0.5)
    out = render_vars(bp, ctx, world(**{"sensor.t": _State("22.9")}), "ea_active", at("19:30"))
    assert (out["ea_floor"], out["ea_active"]) == (23.0, True)
    out = render_vars(bp, ctx, world(**{"sensor.t": _State("23.0")}), "ea_active", at("19:30"))
    assert out["ea_active"] is False


def test_setpoint_rounding_vacation_passthrough(bp):
    assert render_tpl(bp, get_var(bp, "desired_setpoint"), world(), desired_setpoint_raw="none", setpoint_step=1.0,
                      setpoint_min=7.0, setpoint_max=30.0) == "none"


@pytest.mark.parametrize("attr,expected", [(1.0, 1.0), (0.5, 0.5), (None, 0.5), (0, 0.5), ("1", 1.0)])
def test_setpoint_step_rows(bp, attr, expected):
    attrs = {"temperature": 7.0, "current_temperature": 23.4}
    if attr is not None:
        attrs["target_temp_step"] = attr
    w = world(**{"climate.rack": _State("unknown", attrs=attrs)})
    assert render_vars(bp, base_ctx(), w, "setpoint_step")["setpoint_step"] == expected


@pytest.mark.parametrize("indoor,floor,expected_min,expected_start", [
    (20.0, 10, 25, "06:20"),   # ΔT 3 → 10 + 5·3
    (22.5, 10, 12, "06:33"),   # ΔT 0.5 → 12.5 → int 12
    (22.5, 28, 28, "06:17"),   # floor wins (the old instance value)
    (10.0, 10, 60, "05:45"),   # cap 60
    (25.0, 10, 10, "06:35"),   # ΔT clamps at 0 → floor
])
def test_warmup_lead_rows(bp, indoor, floor, expected_min, expected_start):
    ctx = base_ctx(warmup_min_minutes=floor)
    out = render_vars(bp, ctx, world(**{"sensor.t": _State(str(indoor))}), "ma_auto_start_dt")
    assert out["ma_warmup_min"] == expected_min
    assert as_datetime(out["ma_auto_start_dt"]).strftime("%H:%M") == expected_start


def _evening_ctx(**over):
    return base_ctx(evening_a_days=["tue"], **over)


@pytest.mark.parametrize("indoor,delta,active,priority,setpoint", [
    (22.0, 1.0, True, "P4_evening", 24.0),
    (22.9, 1.0, True, "P4_evening", 24.0),
    (23.0, 1.0, False, "P6_idle", 7.0),     # at the floor line → satisfied
    (23.9, 0.0, True, "P4_evening", 24.0),  # delta 0: heat until target
    (24.0, 0.0, False, "P6_idle", 7.0),
    (21.0, 3.0, False, "P6_idle", 7.0),     # delta 3 → floor at 21
    (20.9, 3.0, True, "P4_evening", 24.0),
])
def test_comfort_floor_rows(bp, indoor, delta, active, priority, setpoint):
    ctx = _evening_ctx(comfort_floor_delta=delta)
    out = render_vars(bp, ctx, world(**{"sensor.t": _State(str(indoor))}), "active_priority", at("19:30"))
    assert out["ea_in_window"] is True
    assert out["ea_active"] is active
    assert (out["active_priority"], out["desired_setpoint"]) == (priority, setpoint)


@pytest.mark.parametrize("hhmm,in_window", [
    ("18:54", False), ("18:55", True), ("19:15", True), ("20:29", True), ("20:30", False), ("21:00", False),
])
def test_window_bounds_rows(bp, hhmm, in_window):
    # indoor 22 / target 24 → ΔT 2 → lead 20 min → auto_start 18:55
    out = render_vars(bp, _evening_ctx(), world(), "ea_active", at(hhmm))
    assert out["ea_warmup_min"] == 20
    assert as_datetime(out["ea_auto_start_dt"]).strftime("%H:%M") == "18:55"
    assert out["ea_in_window"] is in_window
    assert out["ea_active"] is in_window


def test_window_day_filter(bp):
    out = render_vars(bp, base_ctx(evening_a_days=["mon"]), world(), "ea_active", at("19:30"))
    assert out["ea_in_days"] is False
    assert out["ea_in_window"] is False


@pytest.mark.parametrize("warm,hold,hhmm,expected_hold_day,in_window", [
    ("06:45:00", "08:00:00", "07:00", 8, True),    # normal same-day window
    ("23:00:00", "01:00:00", "23:30", 9, True),    # hold before warm → next day; window runs to midnight
    ("23:00:00", "22:00:00", "23:30", 9, True),    # hold before warm → next day
    ("23:00:00", "23:00:00", "23:30", 9, True),    # hold == warm → next day
    ("23:00:00", "01:00:00", "22:30", 9, False),   # before auto_start (22:40 for ΔT 1)
])
def test_hold_until_anchor_rows(bp, warm, hold, hhmm, expected_hold_day, in_window):
    ctx = base_ctx(morning_a_days=["tue"], morning_a_target_warm=warm, morning_a_hold_until=hold)
    out = render_vars(bp, ctx, world(), "ma_active", at(hhmm))
    assert as_datetime(out["ma_hold_until_dt"]).day == expected_hold_day
    assert out["ma_in_window"] is in_window


def test_priority_vacation(bp):
    w = world(**{"input_boolean.vac": _State("on", minutes_ago=30)})
    out = render_vars(bp, _evening_ctx(), w, "active_priority", at("19:30"))
    assert out["vacation_active"] is True
    assert (out["desired_mode"], out["desired_setpoint"], out["active_priority"]) == ("off", "none", "P1_vacation")


def test_vacation_empty_list_is_false(bp):
    out = render_vars(bp, base_ctx(entity_vacation=[]), world(), "vacation_active")
    assert out["vacation_active"] is False


def test_priority_boost_and_expiry(bp):
    w = world(**{"input_boolean.boost": _State("on", minutes_ago=5)})
    assert decide(bp, base_ctx(), w) == ("P3_boost", 26.0)
    w = world(**{"input_boolean.boost": _State("on", minutes_ago=35)})
    out = render_vars(bp, base_ctx(), w, "active_priority")
    assert out["boost_expired"] is True
    assert out["active_priority"] == "P6_idle"


def test_boost_missing_entity_age_zero(bp):
    w = world()
    del w.table["input_boolean.boost"]
    out = render_vars(bp, base_ctx(), w, "boost_active")
    assert out["boost_age_min"] == 0
    assert out["boost_active"] is False


def test_priority_fan_coordination(bp):
    fan_on = {"light.fan": _State("on", minutes_ago=2)}
    assert decide(bp, _evening_ctx(), world(**fan_on), at("19:30")) == ("P2_fan_coord", 7.0)
    assert decide(bp, base_ctx(), world(**fan_on), at("12:00")) == ("P6_idle", 7.0)
    w = world(**fan_on, **{"input_boolean.boost": _State("on", minutes_ago=5)})
    assert decide(bp, _evening_ctx(), w, at("19:30")) == ("P3_boost", 26.0)


def test_evening_beats_morning(bp):
    ctx = base_ctx(morning_a_days=["tue"], morning_a_target_warm="19:00:00", morning_a_hold_until="21:00:00",
                   evening_a_days=["tue"])
    out = render_vars(bp, ctx, world(**{"sensor.t": _State("21.0")}), "active_priority", at("19:30"))
    assert out["morning_active"] is True and out["evening_active"] is True
    assert (out["active_priority"], out["desired_setpoint"]) == ("P4_evening", 24.0)


def test_morning_slot_setpoint_rounds_to_device_step(bp):
    ctx = base_ctx(morning_a_days=["tue"], morning_a_target_temp=23.5)
    assert decide(bp, ctx, world(), at("07:00")) == ("P5_morning", 24.0)
    w = world(**{"climate.rack": _State("unknown", attrs={"temperature": 7.0, "current_temperature": 23.4, "target_temp_step": 0.5})})
    assert decide(bp, ctx, w, at("07:00")) == ("P5_morning", 23.5)


def test_indoor_temp_fallback_rows(bp):
    out = render_vars(bp, base_ctx(), world(**{"sensor.t": _State("unavailable")}), "indoor_temp")
    assert (out["indoor_temp_has_primary"], out["indoor_temp"]) == (False, 23.4)
    w = world(**{"sensor.t": _State("unavailable"),
                 "climate.rack": _State("unknown", attrs={"temperature": 7.0, "target_temp_step": 1.0})})
    out = render_vars(bp, base_ctx(), w, "indoor_temp")
    assert (out["indoor_temp_both_unavailable"], out["indoor_temp"]) == (True, 20)


def test_hvac_mode_normalisation(bp):
    out = render_vars(bp, base_ctx(), world(), "current_hvac_mode_normalized")
    assert (out["current_hvac_mode"], out["current_hvac_mode_normalized"]) == ("unknown", "heat_cool")
    w = world(**{"climate.rack": _State("off", attrs={"temperature": 7.0, "target_temp_step": 1.0})})
    assert render_vars(bp, base_ctx(), w, "current_hvac_mode_normalized")["current_hvac_mode_normalized"] == "off"


@pytest.mark.parametrize("enabled,desired,current,expected", [
    (True, 24.0, 7.0, True),      # the tick that raises the setpoint
    (True, 24.0, 24.0, False),    # already raised
    (True, 24.0, 23.0, False),    # setpoint change between two active targets is not a warmup start
    (True, 7.0, 7.0, False),      # idle
    (True, "none", 7.0, False),   # vacation
    (False, 24.0, 7.0, False),    # notifications disabled
])
def test_warmup_notify_condition_rows(bp, enabled, desired, current, expected):
    tpl = choose_steps(bp)[4]["choose"][0]["conditions"][0]["value_template"]
    got = render_tpl(bp, tpl, world(), enable_notifications=enabled, desired_setpoint=desired,
                     current_setpoint=current, idle_setpoint_dev=7.0)
    assert got is expected


def test_warmup_edges_use_the_device_idle_value(bp):
    # idle 7.5 on a 1.0 step is written as 8.0: no phantom push at idle, and the dismiss can clear
    on = choose_steps(bp)[4]["choose"][0]["conditions"][0]["value_template"]
    off = choose_steps(bp)[4]["choose"][1]["conditions"][0]["value_template"]
    assert render_tpl(bp, on, world(), enable_notifications=True, desired_setpoint=8.0, current_setpoint=8.0, idle_setpoint_dev=8.0) is False
    assert render_tpl(bp, on, world(), enable_notifications=True, desired_setpoint=24.0, current_setpoint=8.0, idle_setpoint_dev=8.0) is True
    assert render_tpl(bp, off, world(), desired_setpoint=8.0, current_setpoint=24.0, idle_setpoint_dev=8.0) is True
    assert render_tpl(bp, off, world(), desired_setpoint=8.0, current_setpoint=8.0, idle_setpoint_dev=8.0) is False


@pytest.mark.parametrize("desired,current,expected", [
    (7.0, 24.0, True),      # the tick that lowers the setpoint
    (7.0, 7.0, False),      # already idle
    (24.0, 24.0, False),    # still active
    ("none", 24.0, False),  # vacation: hvac off, setpoint untouched
])
def test_warmup_dismiss_condition_rows(bp, desired, current, expected):
    tpl = choose_steps(bp)[4]["choose"][1]["conditions"][0]["value_template"]
    got = render_tpl(bp, tpl, world(), desired_setpoint=desired, current_setpoint=current, idle_setpoint_dev=7.0)
    assert got is expected


def test_warmup_eta_rows(bp):
    seq = choose_steps(bp)[4]["choose"][0]["sequence"]
    eta_vars = seq[0]["variables"]
    env = make_env(world(), NOW)
    ctx = dict(base_ctx(), desired_setpoint=24.0, indoor_temp=22.0)
    ctx["eta_delta"] = parse(env.from_string(str(eta_vars["eta_delta"])).render(**ctx))
    ctx["eta_min"] = parse(env.from_string(str(eta_vars["eta_min"])).render(**ctx))
    assert (ctx["eta_delta"], ctx["eta_min"]) == (2.0, 20)


# ---------------------------------------------------------------- instance + deploy dry-run

def test_instance_json_retune():
    inst = json.loads(INSTANCE_PATH.read_text())
    assert inst["id"] == "1776551429917"
    assert inst["alias"] == "Bathroom Heating Rack v2.0.0"
    assert inst["use_blueprint"]["path"] == HA_BP_PATH
    i = inst["use_blueprint"]["input"]
    assert i["heating_climate"] == "climate.heatingrack_bathroom"
    assert i["bathroom_temp_sensor"] == "sensor.bathroom_temperature"
    assert i["fan_switch"] == "light.heater"
    assert i["vacation_off"] == ["input_boolean.heating_rack_vacation"]
    assert i["boost_toggle"] == "input_boolean.heating_rack_boost"
    assert (i["boost_target_temp"], i["boost_runtime_min"]) == (26, 55)
    assert "morning_a_days" not in i and "morning_a_target_warm" not in i     # blueprint defaults: Mon–Fri 06:45→08:00 @ 23
    assert (i["morning_b_days"], i["morning_b_hold_until"]) == (["sat", "sun"], "09:30:00")
    assert (i["evening_a_days"], i["evening_a_target_warm"], i["evening_a_hold_until"], i["evening_a_target_temp"]) == (WEEKDAYS, "19:15:00", "20:30:00", 24)
    assert (i["evening_b_days"], i["evening_b_target_warm"], i["evening_b_hold_until"]) == (["sat", "sun"], "19:15:00", "20:30:00")
    assert "evening_b_target_temp" not in i                                     # blueprint default 23
    assert i["warmup_min_minutes"] == 10
    assert i["notify_targets"] == ["notify.mobile_app_martin_fold"]
    for k in ("hall_motion", "stairs_motion", "enable_predictive_motion"):
        assert k not in i
    assert set(i) <= EXPECTED_INPUTS


def test_instance_json_dry_run_validates():
    r = subprocess.run(["bash", str(DEPLOY_SCRIPT), "--dry-run", str(BP_PATH), HA_BP_PATH, str(INSTANCE_PATH)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ok (id 1776551429917" in r.stdout
    assert "dry-run: validation passed" in r.stdout
```

- [ ] **Step 2: Write `deploy/bathroom_heating_rack_1776551429917.json` (verbatim)**

```json
{
  "id": "1776551429917",
  "alias": "Bathroom Heating Rack v2.0.0",
  "description": "",
  "use_blueprint": {
    "path": "leviemartin/bathroom_heating_rack.yaml",
    "input": {
      "heating_climate": "climate.heatingrack_bathroom",
      "bathroom_temp_sensor": "sensor.bathroom_temperature",
      "fan_switch": "light.heater",
      "vacation_off": ["input_boolean.heating_rack_vacation"],
      "boost_toggle": "input_boolean.heating_rack_boost",
      "boost_target_temp": 26,
      "boost_runtime_min": 55,
      "morning_b_days": ["sat", "sun"],
      "morning_b_hold_until": "09:30:00",
      "evening_a_days": ["mon", "tue", "wed", "thu", "fri"],
      "evening_a_target_warm": "19:15:00",
      "evening_a_hold_until": "20:30:00",
      "evening_a_target_temp": 24,
      "evening_b_days": ["sat", "sun"],
      "evening_b_target_warm": "19:15:00",
      "evening_b_hold_until": "20:30:00",
      "warmup_min_minutes": 10,
      "notify_targets": ["notify.mobile_app_martin_fold"]
    }
  }
}
```

Morning A stays on the blueprint defaults (Mon–Fri 06:45→08:00 @ 23) exactly as the live v1 instance does; Morning B keeps its live overrides; Evening A/B carry the §4.2 retune; `evening_b_target_temp` is the blueprint default 23; the dropped keys are simply absent. `deploy/*.prev.json` is already gitignored.

- [ ] **Step 3: Run the new file RED against v1.1.1**

Run: `cd ~/AI/projects/Blueprints_Home && ~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests/test_bathroom_heating_rack_structure.py -q`
Expected: `96 failed, 20 passed` (the 20 are v1-neutral pins: mode, some selectors/defaults, the instance-JSON retune test, boost-age/hvac rows). The dry-run test fails on v1 with `required inputs missing: hall_motion, stairs_motion` — that is the RED signal for the migration.

- [ ] **Step 4: Confirm the rest of the suite is untouched**

Run: `~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q --deselect tests/test_bathroom_heating_rack_structure.py`
Expected: `133 passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_bathroom_heating_rack_structure.py deploy/bathroom_heating_rack_1776551429917.json
git commit -m "test(bathroom-heating-rack): v2.0.0 structure + render pins (RED on v1.1.1) and migrated instance JSON"
```

Step 6: Report `rack: PASS=20 FAIL=96` and `rest: PASS=133 FAIL=0`.

---

## Task 2: Blueprint v2.0.0 — `bathroom_heating_rack.yaml`

**Model tier:** Sonnet
**Rationale:** The YAML below is complete; the task is transcription, then driving Task 1 to green and fixing any pin mismatch by changing the YAML, never the pin's intent.
**Effort:** high.

**Context budget:** ~35k tokens · 1 file replaced · ~780 LOC · fits one Sonnet subagent window.

**Files:**
- Modify: `bathroom_heating_rack.yaml` (full replacement)
- Test: `tests/test_bathroom_heating_rack_structure.py`

**Interfaces:**
- Consumes: input keys, trigger ids, step order and variable names pinned in Task 1.
- Produces: blueprint path `leviemartin/bathroom_heating_rack.yaml` (unchanged in HA); the schema the instance JSON is validated against.

- [ ] **Step 1: Replace the file with this content (verbatim)**

```yaml
blueprint:
  name: "Bathroom Heating Rack v2.0.0"
  description: >
    **Version: 2.0.0** — comfort floor: a routine slot heats only while the room is below
    `target − comfort_floor_delta` (default 1 °C, with a 0.5 °C release deadband and a latched
    opening edge once that slot is heating), so a bathroom that is already warm gets no pre-heat
    and no hold; without the room sensor slots heat on schedule and a warning is raised; predictive motion (hall/stairs) is removed — a routine starts at the
    ΔT-computed auto_start; the warmup-started notification fires once per transition (the tick
    that raises the setpoint from idle) and is dismissed when the setpoint returns to idle; the
    at-target notification is gone; outage pushes fire once per outage (state triggers with a
    grace period) while the in-HA warnings follow the state; push targets are filtered to
    `notify.*` names and every push runs after the climate calls; the setpoint is rounded to the
    device `target_temp_step` and clamped to its min/max; boost/vacation/fan triggers fire on
    on↔off only; boost expiry is the last step; the preset (eco) machinery is removed — idle is
    `heat_cool` at `idle_setpoint`; the weekday lookup is locale-safe; a hold-until at or before
    target-warm anchors to the next day. History: v1.1.1 boost beats fan coordination ·
    v1.1.0 mobile push · v1.0.5 idle setpoint · v1.0.4 'unknown'→'heat_cool' · v1.0.1 datetime
    arithmetic.

    Pre-heats a bathroom heating rack for scheduled routines (adult morning, kids bath) using a
    ΔT-based warmup lead and a comfort floor, pauses while the exhaust fan runs, and offers a
    boost toggle and a vacation switch.

    **Features:**
    - Dual-slot routines per phase (e.g. weekday + weekend morning)
    - Dynamic warmup: lead time follows the indoor ΔT, clamped to a floor and a cap
    - Comfort floor: no heating while the room is already within `comfort_floor_delta` of target
      (0.5 °C release deadband + latched opening edge while that slot heats, so a noisy sensor
      cannot flip the setpoint); suspended, with a warning, while the room sensor is offline
    - Ad-hoc boost toggle with auto-expiry
    - Ventilator coordination: scheduled routines pause while the fan runs
    - Vacation / full-off toggle
    - Optional mobile push (climate unavailable, room sensor offline, warmup started — once per event)

  domain: automation
  input:
    # ----- DEVICES -----
    heating_climate:
      name: Heating Rack Climate Entity
      description: The climate entity of the heating rack (e.g. a Tuya cloud thermostat element).
      selector:
        entity:
          domain: climate
    bathroom_temp_sensor:
      name: Bathroom Temperature Sensor
      description: >-
        Indoor bathroom temperature sensor used for the ΔT warmup lead and the comfort floor.
        While it is unavailable the warmup lead falls back to the climate entity's
        current_temperature (or 20 °C), the comfort floor is suspended (slots heat on schedule)
        and a warning is raised after 10 minutes.
      selector:
        entity:
          domain: sensor
          device_class: temperature
    fan_switch:
      name: Ventilator Switch
      description: >-
        The exhaust fan entity (or the group mirroring it) whose ON state pauses scheduled
        routines. Use the same entity or group the ventilator blueprint switches.
      selector:
        entity:
          domain: light

    # ----- GLOBAL CONTROLS -----
    vacation_off:
      name: Vacation / Full-Off Toggle (Optional)
      description: "Optional input_boolean(s). When any is ON the heating rack is switched off."
      default: []
      selector:
        entity:
          domain: input_boolean
          multiple: true
    boost_toggle:
      name: Ad-hoc Boost Toggle
      description: "Input boolean. When turned ON, heats to boost_target_temp for boost_runtime_min then auto-turns-off."
      selector:
        entity:
          domain: input_boolean

    # ----- BOOST / IDLE / COMFORT -----
    boost_target_temp:
      name: Boost Target Temperature (°C)
      description: Setpoint applied while the boost toggle is active (rounded to the device step).
      default: 23
      selector:
        number: {min: 18, max: 28, step: 0.5, unit_of_measurement: "°C"}
    boost_runtime_min:
      name: Boost Runtime (min)
      description: The boost toggle is switched off this many minutes after it was turned on.
      default: 30
      selector:
        number: {min: 10, max: 120, step: 5, unit_of_measurement: "min"}
    idle_setpoint:
      name: Idle / Pause Setpoint (°C)
      description: >-
        Setpoint applied when no routine is active and while the fan pauses a routine. Rounded to
        the device step and clamped to its min/max before use (default 7 °C matches the device
        minimum).
      default: 7
      selector:
        number: {min: 5, max: 20, step: 0.5, unit_of_measurement: "°C"}
    comfort_floor_delta:
      name: Comfort Floor Delta (°C)
      description: >-
        A routine slot only heats while the room is below `target − delta`; at or above that line
        the slot is treated as satisfied (no pre-heat, no hold). While the device holds that slot's
        setpoint the slot stays active until the room is 0.5 °C above the line (release deadband
        against sensor noise) and its opening edge is latched at target-warm − warmup cap. 0 keeps
        only the deadband. The window is evaluated per calendar day: a slot whose hold-until is at
        or before its target-warm time runs until midnight.
      default: 1.0
      selector:
        number: {min: 0, max: 3, step: 0.5, unit_of_measurement: "°C"}

    # ----- MORNING A (PRIMARY) -----
    morning_a_days:
      name: Morning A Days
      description: Weekdays on which the Morning A slot applies.
      default: ["mon", "tue", "wed", "thu", "fri"]
      selector:
        select:
          multiple: true
          options:
            - {label: Monday, value: mon}
            - {label: Tuesday, value: tue}
            - {label: Wednesday, value: wed}
            - {label: Thursday, value: thu}
            - {label: Friday, value: fri}
            - {label: Saturday, value: sat}
            - {label: Sunday, value: sun}
    morning_a_target_warm:
      name: Morning A Target-Warm Time
      description: Time the bathroom should be warm; heating starts warmup_min minutes earlier.
      default: "06:45:00"
      selector: {time: {}}
    morning_a_hold_until:
      name: Morning A Hold-Until Time
      description: End of the slot. If at or before target-warm it is taken as the next day.
      default: "08:00:00"
      selector: {time: {}}
    morning_a_target_temp:
      name: Morning A Target Temperature (°C)
      description: Slot setpoint (rounded to the device step).
      default: 23
      selector:
        number: {min: 18, max: 28, step: 0.5, unit_of_measurement: "°C"}

    # ----- MORNING B (OPTIONAL) -----
    morning_b_days:
      name: Morning B Days (leave empty to disable)
      description: Weekdays on which the Morning B slot applies.
      default: []
      selector:
        select:
          multiple: true
          options:
            - {label: Monday, value: mon}
            - {label: Tuesday, value: tue}
            - {label: Wednesday, value: wed}
            - {label: Thursday, value: thu}
            - {label: Friday, value: fri}
            - {label: Saturday, value: sat}
            - {label: Sunday, value: sun}
    morning_b_target_warm:
      name: Morning B Target-Warm Time
      description: Time the bathroom should be warm; heating starts warmup_min minutes earlier.
      default: "08:30:00"
      selector: {time: {}}
    morning_b_hold_until:
      name: Morning B Hold-Until Time
      description: End of the slot. If at or before target-warm it is taken as the next day.
      default: "10:00:00"
      selector: {time: {}}
    morning_b_target_temp:
      name: Morning B Target Temperature (°C)
      description: Slot setpoint (rounded to the device step).
      default: 23
      selector:
        number: {min: 18, max: 28, step: 0.5, unit_of_measurement: "°C"}

    # ----- EVENING A (KIDS BATH) -----
    evening_a_days:
      name: Evening A (Kids Bath) Days
      description: Weekdays on which the Evening A slot applies.
      default: []
      selector:
        select:
          multiple: true
          options:
            - {label: Monday, value: mon}
            - {label: Tuesday, value: tue}
            - {label: Wednesday, value: wed}
            - {label: Thursday, value: thu}
            - {label: Friday, value: fri}
            - {label: Saturday, value: sat}
            - {label: Sunday, value: sun}
    evening_a_target_warm:
      name: Evening A Target-Warm Time
      description: Time the bathroom should be warm; heating starts warmup_min minutes earlier.
      default: "18:15:00"
      selector: {time: {}}
    evening_a_hold_until:
      name: Evening A Hold-Until Time
      description: End of the slot. If at or before target-warm it is taken as the next day.
      default: "19:30:00"
      selector: {time: {}}
    evening_a_target_temp:
      name: Evening A Target Temperature (°C)
      description: Slot setpoint (rounded to the device step).
      default: 25
      selector:
        number: {min: 18, max: 28, step: 0.5, unit_of_measurement: "°C"}

    # ----- EVENING B (OPTIONAL ADULT EVENING) -----
    evening_b_days:
      name: Evening B Days (leave empty to disable)
      description: Weekdays on which the Evening B slot applies.
      default: []
      selector:
        select:
          multiple: true
          options:
            - {label: Monday, value: mon}
            - {label: Tuesday, value: tue}
            - {label: Wednesday, value: wed}
            - {label: Thursday, value: thu}
            - {label: Friday, value: fri}
            - {label: Saturday, value: sat}
            - {label: Sunday, value: sun}
    evening_b_target_warm:
      name: Evening B Target-Warm Time
      description: Time the bathroom should be warm; heating starts warmup_min minutes earlier.
      default: "20:30:00"
      selector: {time: {}}
    evening_b_hold_until:
      name: Evening B Hold-Until Time
      description: End of the slot. If at or before target-warm it is taken as the next day.
      default: "22:00:00"
      selector: {time: {}}
    evening_b_target_temp:
      name: Evening B Target Temperature (°C)
      description: Slot setpoint (rounded to the device step).
      default: 23
      selector:
        number: {min: 18, max: 28, step: 0.5, unit_of_measurement: "°C"}

    # ----- WARMUP FORMULA TUNING -----
    warmup_base_min:
      name: Warmup Base Minutes
      description: Fixed part of the warmup lead (minutes).
      default: 10
      selector:
        number: {min: 5, max: 30, step: 1, unit_of_measurement: "min"}
    warmup_per_degree_min:
      name: Warmup Minutes per °C
      description: Added to the lead for every °C the room is below the slot target.
      default: 5
      selector:
        number: {min: 1, max: 15, step: 1, unit_of_measurement: "min/°C"}
    warmup_min_minutes:
      name: Warmup Floor (min)
      description: Shortest lead time regardless of ΔT.
      default: 10
      selector:
        number: {min: 5, max: 30, step: 1, unit_of_measurement: "min"}
    warmup_max_minutes:
      name: Warmup Cap (min)
      description: Longest lead time regardless of ΔT.
      default: 60
      selector:
        number: {min: 20, max: 120, step: 5, unit_of_measurement: "min"}

    # ----- NOTIFICATIONS -----
    enable_notifications:
      name: Enable Warmup-Started Notifications
      description: Persistent notification (and push) once per warmup transition.
      default: true
      selector: {boolean: {}}
    notify_targets:
      name: Mobile Push Targets
      description: >-
        List of notify services to push high-priority events to. Enter the full service name
        including the `notify.` prefix (e.g. notify.mobile_app_martin_fold); entries that do not
        look like `notify.<name>` are ignored. A target that does not exist aborts the run at the
        push step (HA does not suppress a missing action), so check it exists after editing. Leave
        empty to disable push. Events that push: climate unavailable (after 5 min), room sensor
        offline (after 10 min), warmup started.
      default: []
      selector:
        text:
          multiple: true

mode: restart
max_exceeded: silent

# =============================================
# TOP-LEVEL VARIABLES — !input pass-through
# =============================================
variables:
  entity_climate: !input heating_climate
  sensor_bathroom_temp: !input bathroom_temp_sensor
  entity_fan: !input fan_switch
  entity_vacation: !input vacation_off
  entity_boost: !input boost_toggle

  boost_runtime_min: !input boost_runtime_min
  boost_target_temp: !input boost_target_temp
  idle_setpoint: !input idle_setpoint
  comfort_floor_delta: !input comfort_floor_delta
  warmup_base_min: !input warmup_base_min
  warmup_per_degree_min: !input warmup_per_degree_min
  warmup_min_minutes: !input warmup_min_minutes
  warmup_max_minutes: !input warmup_max_minutes
  enable_notifications: !input enable_notifications
  notify_targets: !input notify_targets

  morning_a_days: !input morning_a_days
  morning_a_target_warm: !input morning_a_target_warm
  morning_a_hold_until: !input morning_a_hold_until
  morning_a_target_temp: !input morning_a_target_temp
  morning_b_days: !input morning_b_days
  morning_b_target_warm: !input morning_b_target_warm
  morning_b_hold_until: !input morning_b_hold_until
  morning_b_target_temp: !input morning_b_target_temp
  evening_a_days: !input evening_a_days
  evening_a_target_warm: !input evening_a_target_warm
  evening_a_hold_until: !input evening_a_hold_until
  evening_a_target_temp: !input evening_a_target_temp
  evening_b_days: !input evening_b_days
  evening_b_target_warm: !input evening_b_target_warm
  evening_b_hold_until: !input evening_b_hold_until
  evening_b_target_temp: !input evening_b_target_temp

trigger:
  # T1: 1-minute tick — auto_start, comfort floor, boost expiry
  - platform: time_pattern
    minutes: "/1"
    id: periodic

  # T2: boost toggle on/off (attribute-only updates ignored)
  - platform: state
    entity_id: !input boost_toggle
    to: ["on", "off"]
    id: boost_change

  # T3: vacation toggle on/off
  - platform: state
    entity_id: !input vacation_off
    to: ["on", "off"]
    id: vacation_change

  # T4: fan on/off (ventilator coordination; Hue group attribute updates ignored)
  - platform: state
    entity_id: !input fan_switch
    to: ["on", "off"]
    id: fan_change

  # T5: HA restart
  - platform: homeassistant
    event: start
    id: ha_start

  # T6: climate entity offline for 5 min (one push per outage; 'unknown' is the device's normal ON state)
  - platform: state
    entity_id: !input heating_climate
    to: unavailable
    for:
      minutes: 5
    id: climate_lost

  # T7: room temperature sensor non-numeric for 10 min (one push per outage)
  - platform: state
    entity_id: !input bathroom_temp_sensor
    to: [unavailable, unknown]
    for:
      minutes: 10
    id: temp_lost

action:
  # =============================================
  # STEP 1: LIVE STATE (inside action for trace visibility)
  # =============================================
  - variables:
      indoor_temp_primary: "{{ states(sensor_bathroom_temp) | float(-99) }}"
      indoor_temp_fallback: "{{ state_attr(entity_climate, 'current_temperature') | float(-99) }}"
      indoor_temp_has_primary: "{{ indoor_temp_primary | float(-99) > -50 }}"
      indoor_temp_has_fallback: "{{ indoor_temp_fallback | float(-99) > -50 }}"
      indoor_temp_both_unavailable: "{{ not indoor_temp_has_primary and not indoor_temp_has_fallback }}"
      indoor_temp: >-
        {% if indoor_temp_has_primary %}{{ indoor_temp_primary | float }}{% elif indoor_temp_has_fallback %}{{ indoor_temp_fallback | float }}{% else %}20{% endif %}

      current_setpoint: "{{ state_attr(entity_climate, 'temperature') | float(7) }}"
      current_hvac_mode: "{{ states(entity_climate) }}"
      # Tuya cloud climate entities report state 'unknown' while the switch DP is on and the
      # mode DP is eco (HA core tuya/climate.py hvac_mode) and 'off' when the switch is off.
      # 'unknown' is therefore the normal ON state: normalising it to 'heat_cool' keeps the
      # idempotent mode call from re-firing (and beeping) every tick.
      current_hvac_mode_normalized: "{{ 'heat_cool' if current_hvac_mode == 'unknown' else current_hvac_mode }}"
      # Device setpoint grid and range; defaults when the attributes are missing or zero.
      setpoint_step: >-
        {% set s = state_attr(entity_climate, 'target_temp_step') | float(0) %}{{ s if s > 0 else 0.5 }}
      setpoint_min: "{{ state_attr(entity_climate, 'min_temp') | float(7) }}"
      setpoint_max: "{{ state_attr(entity_climate, 'max_temp') | float(30) }}"
      # The idle value the device can actually hold: rounded half-up to the step (epsilon-nudged
      # grid count, round(2)) and clamped to the range. Every idle comparison uses this value.
      idle_setpoint_dev: "{{ [setpoint_max | float, [setpoint_min | float, ((((idle_setpoint | float) / (setpoint_step | float) + 0.501) | int) * (setpoint_step | float))] | max] | min | round(2) }}"
      fan_is_on: "{{ is_state(entity_fan, 'on') }}"
      # Push targets: only well-formed notify service names are dispatched (a typo would otherwise
      # be called as an arbitrary service). A well-formed name that does not exist still aborts the
      # run at the push step — HA does not suppress a missing action — so every push runs after
      # the climate calls and the deploy step checks each target exists.
      notify_list: "{{ notify_targets | select('match', '^notify[.][a-z0-9_]+$') | list }}"

      # Locale-safe weekday token (the %a abbreviation follows the system locale)
      today_dow: "{{ ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'][now().weekday()] }}"
      now_dt: "{{ now() }}"

      # Vacation: any listed toggle ON (an empty list renders False, never bare text)
      vacation_active: "{{ expand(entity_vacation) | selectattr('state', 'eq', 'on') | list | length > 0 }}"

      # Boost (stateless age-based expiry)
      boost_runtime_min_int: "{{ (boost_runtime_min | float) | int }}"
      boost_is_on: "{{ is_state(entity_boost, 'on') }}"
      boost_age_min: >-
        {% if states[entity_boost] %}{{ ((now() - states[entity_boost].last_changed).total_seconds() / 60) | int }}{% else %}0{% endif %}
      boost_active: "{{ boost_is_on and boost_age_min < boost_runtime_min_int }}"
      boost_expired: "{{ boost_is_on and boost_age_min >= boost_runtime_min_int }}"

  # =============================================
  # STEP 2: ROUTINE SLOT RESOLUTION
  # Per slot: in_days → target_warm/hold_until (hold anchored to the next day when it is at or
  # before target_warm) → heating? → ΔT → warmup lead → auto_start → open edge → in_window →
  # active (comfort floor with deadband, suspended without the room sensor).
  # =============================================
  - variables:
      # ----- MORNING A -----
      ma_in_days: "{{ today_dow in morning_a_days }}"
      ma_target_warm_dt: "{{ today_at(morning_a_target_warm) }}"
      ma_hold_until_dt: >-
        {% set w = today_at(morning_a_target_warm) %}{% set h = today_at(morning_a_hold_until) %}{{ h + timedelta(days=1) if h <= w else h }}
      # This slot's setpoint as the device holds it; while the device is at that value the slot is
      # the one heating: its floor gets the 0.5 °C release deadband and its opening edge is
      # latched at target_warm − warmup cap (the ΔT-derived auto_start moves with sensor noise).
      ma_target_dev: "{{ ((((morning_a_target_temp | float) / (setpoint_step | float) + 0.501) | int) * (setpoint_step | float)) | round(2) }}"
      ma_heating: "{{ (current_setpoint | float - ma_target_dev | float) | abs < 0.1 }}"
      ma_delta_T: "{{ [0, morning_a_target_temp | float - indoor_temp | float] | max }}"
      ma_warmup_min: >-
        {{ [warmup_max_minutes | int,
            [warmup_min_minutes | int,
             (warmup_base_min | int) + (warmup_per_degree_min | int) * (ma_delta_T | float)] | max
           ] | min | int }}
      ma_auto_start_dt: "{{ as_datetime(ma_target_warm_dt) - timedelta(minutes=ma_warmup_min | int) }}"
      ma_open_dt: "{{ as_datetime(ma_target_warm_dt) - timedelta(minutes=(warmup_max_minutes | int if ma_heating else ma_warmup_min | int)) }}"
      ma_in_window: >-
        {{ ma_in_days and as_datetime(ma_open_dt) <= as_datetime(now_dt) and as_datetime(now_dt) < as_datetime(ma_hold_until_dt) }}
      ma_floor: "{{ (morning_a_target_temp | float - comfort_floor_delta | float + (0.5 if ma_heating else 0)) | round(2) }}"
      # Without the room sensor the floor is suspended: the slot heats on schedule (v1 behaviour,
      # the device thermostat bounds the temperature) and the sensor warning below says so.
      ma_active: "{{ ma_in_window and (not indoor_temp_has_primary or indoor_temp | float | round(2) < ma_floor | float) }}"

      # ----- MORNING B -----
      mb_in_days: "{{ today_dow in morning_b_days }}"
      mb_target_warm_dt: "{{ today_at(morning_b_target_warm) }}"
      mb_hold_until_dt: >-
        {% set w = today_at(morning_b_target_warm) %}{% set h = today_at(morning_b_hold_until) %}{{ h + timedelta(days=1) if h <= w else h }}
      # This slot's setpoint as the device holds it; while the device is at that value the slot is
      # the one heating: its floor gets the 0.5 °C release deadband and its opening edge is
      # latched at target_warm − warmup cap (the ΔT-derived auto_start moves with sensor noise).
      mb_target_dev: "{{ ((((morning_b_target_temp | float) / (setpoint_step | float) + 0.501) | int) * (setpoint_step | float)) | round(2) }}"
      mb_heating: "{{ (current_setpoint | float - mb_target_dev | float) | abs < 0.1 }}"
      mb_delta_T: "{{ [0, morning_b_target_temp | float - indoor_temp | float] | max }}"
      mb_warmup_min: >-
        {{ [warmup_max_minutes | int,
            [warmup_min_minutes | int,
             (warmup_base_min | int) + (warmup_per_degree_min | int) * (mb_delta_T | float)] | max
           ] | min | int }}
      mb_auto_start_dt: "{{ as_datetime(mb_target_warm_dt) - timedelta(minutes=mb_warmup_min | int) }}"
      mb_open_dt: "{{ as_datetime(mb_target_warm_dt) - timedelta(minutes=(warmup_max_minutes | int if mb_heating else mb_warmup_min | int)) }}"
      mb_in_window: >-
        {{ mb_in_days and as_datetime(mb_open_dt) <= as_datetime(now_dt) and as_datetime(now_dt) < as_datetime(mb_hold_until_dt) }}
      mb_floor: "{{ (morning_b_target_temp | float - comfort_floor_delta | float + (0.5 if mb_heating else 0)) | round(2) }}"
      # Without the room sensor the floor is suspended: the slot heats on schedule (v1 behaviour,
      # the device thermostat bounds the temperature) and the sensor warning below says so.
      mb_active: "{{ mb_in_window and (not indoor_temp_has_primary or indoor_temp | float | round(2) < mb_floor | float) }}"

      # ----- EVENING A -----
      ea_in_days: "{{ today_dow in evening_a_days }}"
      ea_target_warm_dt: "{{ today_at(evening_a_target_warm) }}"
      ea_hold_until_dt: >-
        {% set w = today_at(evening_a_target_warm) %}{% set h = today_at(evening_a_hold_until) %}{{ h + timedelta(days=1) if h <= w else h }}
      # This slot's setpoint as the device holds it; while the device is at that value the slot is
      # the one heating: its floor gets the 0.5 °C release deadband and its opening edge is
      # latched at target_warm − warmup cap (the ΔT-derived auto_start moves with sensor noise).
      ea_target_dev: "{{ ((((evening_a_target_temp | float) / (setpoint_step | float) + 0.501) | int) * (setpoint_step | float)) | round(2) }}"
      ea_heating: "{{ (current_setpoint | float - ea_target_dev | float) | abs < 0.1 }}"
      ea_delta_T: "{{ [0, evening_a_target_temp | float - indoor_temp | float] | max }}"
      ea_warmup_min: >-
        {{ [warmup_max_minutes | int,
            [warmup_min_minutes | int,
             (warmup_base_min | int) + (warmup_per_degree_min | int) * (ea_delta_T | float)] | max
           ] | min | int }}
      ea_auto_start_dt: "{{ as_datetime(ea_target_warm_dt) - timedelta(minutes=ea_warmup_min | int) }}"
      ea_open_dt: "{{ as_datetime(ea_target_warm_dt) - timedelta(minutes=(warmup_max_minutes | int if ea_heating else ea_warmup_min | int)) }}"
      ea_in_window: >-
        {{ ea_in_days and as_datetime(ea_open_dt) <= as_datetime(now_dt) and as_datetime(now_dt) < as_datetime(ea_hold_until_dt) }}
      ea_floor: "{{ (evening_a_target_temp | float - comfort_floor_delta | float + (0.5 if ea_heating else 0)) | round(2) }}"
      # Without the room sensor the floor is suspended: the slot heats on schedule (v1 behaviour,
      # the device thermostat bounds the temperature) and the sensor warning below says so.
      ea_active: "{{ ea_in_window and (not indoor_temp_has_primary or indoor_temp | float | round(2) < ea_floor | float) }}"

      # ----- EVENING B -----
      eb_in_days: "{{ today_dow in evening_b_days }}"
      eb_target_warm_dt: "{{ today_at(evening_b_target_warm) }}"
      eb_hold_until_dt: >-
        {% set w = today_at(evening_b_target_warm) %}{% set h = today_at(evening_b_hold_until) %}{{ h + timedelta(days=1) if h <= w else h }}
      # This slot's setpoint as the device holds it; while the device is at that value the slot is
      # the one heating: its floor gets the 0.5 °C release deadband and its opening edge is
      # latched at target_warm − warmup cap (the ΔT-derived auto_start moves with sensor noise).
      eb_target_dev: "{{ ((((evening_b_target_temp | float) / (setpoint_step | float) + 0.501) | int) * (setpoint_step | float)) | round(2) }}"
      eb_heating: "{{ (current_setpoint | float - eb_target_dev | float) | abs < 0.1 }}"
      eb_delta_T: "{{ [0, evening_b_target_temp | float - indoor_temp | float] | max }}"
      eb_warmup_min: >-
        {{ [warmup_max_minutes | int,
            [warmup_min_minutes | int,
             (warmup_base_min | int) + (warmup_per_degree_min | int) * (eb_delta_T | float)] | max
           ] | min | int }}
      eb_auto_start_dt: "{{ as_datetime(eb_target_warm_dt) - timedelta(minutes=eb_warmup_min | int) }}"
      eb_open_dt: "{{ as_datetime(eb_target_warm_dt) - timedelta(minutes=(warmup_max_minutes | int if eb_heating else eb_warmup_min | int)) }}"
      eb_in_window: >-
        {{ eb_in_days and as_datetime(eb_open_dt) <= as_datetime(now_dt) and as_datetime(now_dt) < as_datetime(eb_hold_until_dt) }}
      eb_floor: "{{ (evening_b_target_temp | float - comfort_floor_delta | float + (0.5 if eb_heating else 0)) | round(2) }}"
      # Without the room sensor the floor is suspended: the slot heats on schedule (v1 behaviour,
      # the device thermostat bounds the temperature) and the sensor warning below says so.
      eb_active: "{{ eb_in_window and (not indoor_temp_has_primary or indoor_temp | float | round(2) < eb_floor | float) }}"

      # ----- AGGREGATES -----
      morning_active: "{{ ma_active or mb_active }}"
      evening_active: "{{ ea_active or eb_active }}"
      morning_temp: >-
        {% if ma_active %}{{ morning_a_target_temp | float }}{% else %}{{ morning_b_target_temp | float }}{% endif %}
      evening_temp: >-
        {% if ea_active %}{{ evening_a_target_temp | float }}{% else %}{{ evening_b_target_temp | float }}{% endif %}

  # =============================================
  # STEP 3: CLIMATE VALIDATION — 'unavailable' is a hard stop ('unknown' is the Tuya device's
  # normal ON state). The in-HA warning follows the state (created every tick of the outage,
  # idempotent by id; dismissed when the entity is back); the push fires once, on the
  # climate_lost trigger. Nothing below can run without the entity, so the push before `stop` is
  # safe here; every other push sits after the climate calls.
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ states(entity_climate) == 'unavailable' }}"
        sequence:
          - service: persistent_notification.create
            continue_on_error: true
            data:
              title: "Heating Rack — Climate Unavailable"
              message: >
                {{ entity_climate }} is {{ states(entity_climate) }}.
                Holding current state.
              notification_id: "heating_rack_climate_unavailable"
          - choose:
              - conditions:
                  - condition: template
                    value_template: "{{ trigger.id | default('') == 'climate_lost' }}"
                sequence:
                  - repeat:
                      for_each: "{{ notify_list }}"
                      sequence:
                        - service: "{{ repeat.item }}"
                          continue_on_error: true
                          data:
                            title: "Heating Rack — Climate Unavailable"
                            message: >-
                              {{ entity_climate }} has been unavailable for 5 min.
                              Holding current state.
          - stop: "Climate entity unavailable"
      - conditions:
          - condition: template
            value_template: "{{ states(entity_climate) != 'unavailable' }}"
        sequence:
          - service: persistent_notification.dismiss
            continue_on_error: true
            data:
              notification_id: "heating_rack_climate_unavailable"

  # =============================================
  # STEP 4: PRIORITY (first match wins)
  # P1 vacation > P3 boost > P2 fan pause (scheduled routines only) > P4 evening > P5 morning
  # > P6 idle. Labels are historical: the numeric suffix is not the evaluation order.
  # Every desired_* template is single-line so the rendered value carries no whitespace.
  # =============================================
  - variables:
      desired_mode: "{% if vacation_active %}off{% else %}heat_cool{% endif %}"
      desired_setpoint_raw: "{% if vacation_active %}none{% elif boost_active %}{{ boost_target_temp | float }}{% elif fan_is_on and (morning_active or evening_active) %}{{ idle_setpoint | float }}{% elif evening_active %}{{ evening_temp | float }}{% elif morning_active %}{{ morning_temp | float }}{% else %}{{ idle_setpoint | float }}{% endif %}"
      # Rounded half-up to the device step so the idempotency check below compares like with like,
      # then clamped to the device range (a value outside it is rejected by HA and would abort the
      # run). Grid-count arithmetic with an epsilon nudge (0.501) and round(2): raw/step is not
      # binary-exact for 0.1-grid values, so a bare +0.5 | int can land one step low.
      desired_setpoint: "{% if desired_setpoint_raw == 'none' %}none{% else %}{{ [setpoint_max | float, [setpoint_min | float, ((((desired_setpoint_raw | float) / (setpoint_step | float) + 0.501) | int) * (setpoint_step | float))] | max] | min | round(2) }}{% endif %}"
      active_priority: "{% if vacation_active %}P1_vacation{% elif boost_active %}P3_boost{% elif fan_is_on and (morning_active or evening_active) %}P2_fan_coord{% elif evening_active %}P4_evening{% elif morning_active %}P5_morning{% else %}P6_idle{% endif %}"

  # =============================================
  # STEP 5: IDEMPOTENT SERVICE CALLS
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ current_hvac_mode_normalized != desired_mode }}"
        sequence:
          - service: climate.set_hvac_mode
            target:
              entity_id: "{{ entity_climate }}"
            data:
              hvac_mode: "{{ desired_mode }}"

  - choose:
      - conditions:
          - condition: template
            value_template: >-
              {{ desired_setpoint != 'none'
                 and (current_setpoint | float - desired_setpoint | float) | abs > 0.1 }}
        sequence:
          - service: climate.set_temperature
            target:
              entity_id: "{{ entity_climate }}"
            data:
              temperature: "{{ desired_setpoint | float }}"

  # =============================================
  # STEP 6: ROOM SENSOR WARNING — state-driven in HA (created every tick while the room sensor is
  # non-numeric, dismissed when it is back); the push fires once, on the temp_lost trigger.
  # Sits after the climate calls so a push problem can never block a setpoint write.
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ not indoor_temp_has_primary }}"
        sequence:
          - service: persistent_notification.create
            continue_on_error: true
            data:
              title: "Heating Rack — Room Sensor Offline"
              message: >
                {{ sensor_bathroom_temp }} is non-numeric. Warmup lead uses
                {% if indoor_temp_has_fallback %}{{ entity_climate }}.current_temperature ({{ indoor_temp }}°C, the rack's own sensor, reads warm){% else %}a 20°C fallback{% endif %};
                the comfort floor is suspended, so routine slots heat on schedule until the sensor returns.
              notification_id: "heating_rack_sensor_warning"
          - choose:
              - conditions:
                  - condition: template
                    value_template: "{{ trigger.id | default('') == 'temp_lost' }}"
                sequence:
                  - repeat:
                      for_each: "{{ notify_list }}"
                      sequence:
                        - service: "{{ repeat.item }}"
                          continue_on_error: true
                          data:
                            title: "Heating Rack — Room Sensor Offline"
                            message: >-
                              {{ sensor_bathroom_temp }} non-numeric for 10 min.
                              Comfort floor suspended; slots heat on schedule until it returns.
      - conditions:
          - condition: template
            value_template: "{{ indoor_temp_has_primary }}"
        sequence:
          - service: persistent_notification.dismiss
            continue_on_error: true
            data:
              notification_id: "heating_rack_sensor_warning"

  # =============================================
  # STEP 7: WARMUP-STARTED NOTIFICATION — edge-triggered on the setpoint leaving idle
  # (current_setpoint was read before the set_temperature call above); dismissed on the tick
  # that returns the setpoint to idle. Compares against idle_setpoint_dev, the idle value the
  # device actually holds.
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: >-
              {{ enable_notifications
                 and desired_setpoint != 'none'
                 and desired_setpoint | float > idle_setpoint_dev | float + 0.1
                 and current_setpoint | float <= idle_setpoint_dev | float + 0.1 }}
        sequence:
          - variables:
              eta_delta: "{{ [0, desired_setpoint | float - indoor_temp | float] | max }}"
              eta_min: >-
                {{ [warmup_max_minutes | int,
                    [warmup_min_minutes | int,
                     (warmup_base_min | int) + (warmup_per_degree_min | int) * (eta_delta | float)] | max
                   ] | min | int }}
          - service: persistent_notification.create
            continue_on_error: true
            data:
              title: "Heating Rack — Warmup Started"
              message: >
                Priority: {{ active_priority }}.
                Current {{ indoor_temp | round(1) }}°C → target
                {{ desired_setpoint }}°C. ETA ~{{ eta_min }} min.
              notification_id: "heating_rack_warmup_started"
          - repeat:
              for_each: "{{ notify_list }}"
              sequence:
                - service: "{{ repeat.item }}"
                  continue_on_error: true
                  data:
                    title: "Heating Rack — Warmup Started"
                    message: >-
                      {{ active_priority }}: {{ indoor_temp | round(1) }}°C
                      → {{ desired_setpoint }}°C. ETA ~{{ eta_min }} min.

      - conditions:
          - condition: template
            value_template: >-
              {{ desired_setpoint != 'none'
                 and desired_setpoint | float <= idle_setpoint_dev | float + 0.1
                 and current_setpoint | float > idle_setpoint_dev | float + 0.1 }}
        sequence:
          - service: persistent_notification.dismiss
            continue_on_error: true
            data:
              notification_id: "heating_rack_warmup_started"

  # =============================================
  # STEP 8: DEBUG NOTIFICATION (manual run only)
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ trigger.id | default('manual') == 'manual' }}"
        sequence:
          - service: persistent_notification.create
            continue_on_error: true
            data:
              title: "Heating Rack Debug — {{ now().strftime('%H:%M:%S') }}"
              message: >
                **Indoor:** {{ indoor_temp | round(1) }}°C
                | **Setpoint:** {{ current_setpoint }}°C (step {{ setpoint_step }}, range {{ setpoint_min }}–{{ setpoint_max }}, idle {{ idle_setpoint_dev }})
                | **Mode:** {{ current_hvac_mode }}
                | **Push:** {{ notify_list }}

                **Fan:** {{ 'ON' if fan_is_on else 'OFF' }}
                | **Vacation:** {{ vacation_active }}
                | **Boost:** {{ 'ON' if boost_is_on else 'off' }} (age {{ boost_age_min }}m, expires {{ boost_runtime_min_int }}m)
                | **Comfort floor:** {{ comfort_floor_delta }}°C{{ '' if indoor_temp_has_primary else ' (SUSPENDED — room sensor offline)' }}

                **Today:** {{ today_dow }}

                **Morning A:** days={{ ma_in_days }}, ΔT={{ ma_delta_T }}°C, warmup={{ ma_warmup_min }}m, auto_start={{ as_datetime(ma_auto_start_dt).strftime('%H:%M') }}, open={{ as_datetime(ma_open_dt).strftime('%H:%M') }}, hold_until={{ as_datetime(ma_hold_until_dt).strftime('%a %H:%M') }}, heating={{ ma_heating }}, floor={{ ma_floor }}°C, in_window={{ ma_in_window }}, active={{ ma_active }}

                **Morning B:** days={{ mb_in_days }}, ΔT={{ mb_delta_T }}°C, warmup={{ mb_warmup_min }}m, auto_start={{ as_datetime(mb_auto_start_dt).strftime('%H:%M') }}, open={{ as_datetime(mb_open_dt).strftime('%H:%M') }}, hold_until={{ as_datetime(mb_hold_until_dt).strftime('%a %H:%M') }}, heating={{ mb_heating }}, floor={{ mb_floor }}°C, in_window={{ mb_in_window }}, active={{ mb_active }}

                **Evening A:** days={{ ea_in_days }}, ΔT={{ ea_delta_T }}°C, warmup={{ ea_warmup_min }}m, auto_start={{ as_datetime(ea_auto_start_dt).strftime('%H:%M') }}, open={{ as_datetime(ea_open_dt).strftime('%H:%M') }}, hold_until={{ as_datetime(ea_hold_until_dt).strftime('%a %H:%M') }}, heating={{ ea_heating }}, floor={{ ea_floor }}°C, in_window={{ ea_in_window }}, active={{ ea_active }}

                **Evening B:** days={{ eb_in_days }}, ΔT={{ eb_delta_T }}°C, warmup={{ eb_warmup_min }}m, auto_start={{ as_datetime(eb_auto_start_dt).strftime('%H:%M') }}, open={{ as_datetime(eb_open_dt).strftime('%H:%M') }}, hold_until={{ as_datetime(eb_hold_until_dt).strftime('%a %H:%M') }}, heating={{ eb_heating }}, floor={{ eb_floor }}°C, in_window={{ eb_in_window }}, active={{ eb_active }}

                **→ Priority:** {{ active_priority }}
                | **→ Desired:** mode={{ desired_mode }}, setpoint={{ desired_setpoint }} (raw {{ desired_setpoint_raw }})
              notification_id: "heating_rack_debug"

  # =============================================
  # STEP 9: BOOST EXPIRY — the LAST step: the turn_off restarts this automation (mode: restart,
  # boost_change), which would abort anything after it; by now the setpoint is lowered and the
  # warmup notification dismissed.
  # =============================================
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ boost_expired }}"
        sequence:
          - service: input_boolean.turn_off
            target:
              entity_id: "{{ entity_boost }}"
```

- [ ] **Step 2: Run the rack file to green**

Run: `~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests/test_bathroom_heating_rack_structure.py -q`
Expected: `116 passed`. If a pin fails, the YAML deviates from this plan — diff against Step 1, fix the YAML.

- [ ] **Step 3: Full suite**

Run: `~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q`
Expected: `249 passed`.

- [ ] **Step 4: Offline deploy validation**

Run: `scripts/deploy-blueprint.sh --dry-run bathroom_heating_rack.yaml leviemartin/bathroom_heating_rack.yaml deploy/bathroom_heating_rack_1776551429917.json`
Expected: `blueprint: Bathroom Heating Rack v2.0.0`, `instance …: ok (id 1776551429917, 18 inputs)`, `dry-run: validation passed, nothing deployed`.

- [ ] **Step 5: HA schema validation of the input-substituted config (read-only WS call)**

```bash
source ~/.config/hass-cli/env
~/projects/ceiling-fan-hue-blueprint/.venv/bin/python - <<'EOF' > /tmp/rack_substituted.json
import json, yaml
inst = json.load(open("deploy/bathroom_heating_rack_1776551429917.json"))["use_blueprint"]["input"]
class Inp:
    def __init__(self, n): self.n = n
class L(yaml.SafeLoader): pass
L.add_constructor("!input", lambda l, n: Inp(l.construct_scalar(n)))
bp = yaml.load(open("bathroom_heating_rack.yaml"), Loader=L)
defaults = {k: v["default"] for k, v in bp["blueprint"]["input"].items() if "default" in v}
def sub(x):
    if isinstance(x, Inp): return inst[x.n] if x.n in inst else defaults[x.n]
    if isinstance(x, dict): return {k: sub(v) for k, v in x.items()}
    if isinstance(x, list): return [sub(v) for v in x]
    return x
json.dump({"triggers": sub(bp["trigger"]), "actions": sub(bp["action"])}, open("/tmp/rack_substituted.json", "w"))
EOF
hass-cli -o json raw ws validate_config --json "$(cat /tmp/rack_substituted.json)" | jq -c '.result'
rm -f /tmp/rack_substituted.json
```
Expected: `{"triggers":{"valid":true,"error":null},"actions":{"valid":true,"error":null}}` (HA 2026.9 wants the plural keys; a `KeyError` from the substitution script means the JSON references an input the blueprint no longer has).

- [ ] **Step 6: Commit**

```bash
git add bathroom_heating_rack.yaml
git commit -m "feat(bathroom-heating-rack): v2.0.0 — comfort floor, predictive motion removed, edge-triggered warmup push, step rounding, to: filters, preset machinery removed"
```

Step 7: Report `rack: PASS=116 FAIL=0` and `suite: PASS=249 FAIL=0`.

---

## Task 3: Docs — requirements rewrite + README section

**Model tier:** Sonnet
**Rationale:** Both texts are fully specified below; the only judgment is replacing the right README block without touching its neighbours.
**Effort:** high.

**Context budget:** ~15k tokens · 2 files modified · ~100 LOC · fits one Sonnet subagent window.

**Files:**
- Modify: `requirements_bathroom_heating_rack.md` (full rewrite)
- Modify: `README.md` lines 101–131 (the "## Bathroom Heating Rack Blueprint" section, from its `## ` heading up to but excluding `## Bedroom Sleep Pre-Cool Blueprint`)

**Interfaces:**
- Consumes: the v2 input names and behaviour from Task 2.
- Produces: nothing downstream; documentation only.

- [ ] **Step 1: Rewrite `requirements_bathroom_heating_rack.md` (verbatim)**

````markdown
# Requirements: Bathroom Heating Rack Blueprint (v2.0.0)

## Overview
Pre-heats the bathroom with the heating rack (`climate.heatingrack_bathroom`) so it is warm in time for scheduled routines — adult morning and kids bath — and idles at a frost-protect setpoint the rest of the day. v2.0.0 adds a comfort floor (no heating when the room is already warm), removes predictive motion, and makes every notification edge-triggered.

## Goals
1. **Scheduled pre-heat** with a dynamic warmup lead based on the indoor-to-target ΔT (self-adjusts across seasons without calendar boundaries).
2. **Comfort floor:** a slot heats only while the room is below `target − comfort_floor_delta` (default 1 °C). A bathroom that is already warm gets no pre-heat and no hold. While the device holds that slot's setpoint the slot is "heating": it stays active until the room is 0.5 °C above the line (release deadband — the room sensor swings ±0.3 °C between reports) and its opening edge is latched at `target_warm − warmup_max` (the ΔT lead moves with sensor noise). Without the room sensor the floor is suspended: slots heat on schedule (v1 behaviour, the device thermostat bounds the temperature) and a warning is raised.
3. **Dual slot per phase:** Morning A (primary, default Mon–Fri) + Morning B (optional, weekend). Evening A (kids bath) + Evening B (optional adult evening).
4. **Ad-hoc boost:** user-flipped `input_boolean` gives N minutes at a configurable boost temperature, then auto-expires.
5. **Ventilator coordination:** scheduled routines pause (setpoint → `idle_setpoint`) while the bathroom exhaust fan is running — avoids evicting freshly heated air. Boost is explicit user intent and is not paused.
6. **Idle:** when no routine is active the thermostat holds `idle_setpoint` (default 7 °C, the device minimum) in `heat_cool`.
7. **Vacation / full-off:** optional `input_boolean` switches the rack off.
8. **Idempotent:** ~1440 ticks/day but only a handful of service calls/day (on transitions only). The setpoint is rounded to the device `target_temp_step` and clamped to its `min_temp`/`max_temp` so the comparison is exact and HA never rejects the value.

## Hardware (live 2026-09-07)
- `climate.heatingrack_bathroom` — Tuya cloud "ECOSO WIFI Element" (category wk). HA state is `unknown` while the switch is on and the mode is eco (the normal ON state — the blueprint treats it as `heat_cool`) and `off` when the switch is off. No `hvac_action`. `target_temp_step` 1.0, min 7, max 30. Its own sensor reads ~1.4 °C warmer than the room sensor and governs the element while a slot is active.
- `sensor.bathroom_temperature` — the Hue motion sensor's temperature (reports every ~5 min, 0.1 °C); primary input for ΔT and the comfort floor. Fallback: the climate entity's `current_temperature`.
- `light.heater` — Hue room group mirroring the exhaust-fan plug (`light.on_off_plug_1`, the ventilator blueprint's target); observed for coordination.
- `input_boolean.heating_rack_boost`, `input_boolean.heating_rack_vacation` — helpers.
- `notify.mobile_app_martin_fold` — the only push target.

## Warmup formula
```
ΔT            = max(0, target_temp − indoor_temp)
warmup_min    = clamp(warmup_base + warmup_per_degree × ΔT, warmup_min_minutes, warmup_max_minutes)
auto_start    = target_warm − warmup_min
in_window     = today in days AND auto_start ≤ now < hold_until
heating       = device setpoint == this slot's rounded target
open          = target_warm − (warmup_max_minutes if heating else warmup_min)
in_window     = today in days AND open ≤ now < hold_until
floor         = target_temp − comfort_floor_delta (+ 0.5 while heating)
active        = in_window AND (room sensor offline OR indoor_temp < floor)
```
`hold_until` at or before `target_warm` is taken as the next day; the slot is evaluated per calendar day, so such a window runs until midnight.

## Priority order (first match wins)
1. Vacation / Off — `hvac_mode: off`, setpoint untouched
2. Ad-hoc Boost — `boost_target_temp`
3. Ventilator coordination (scheduled routines only) — `idle_setpoint`
4. Evening routine (A or B) — slot target
5. Morning routine (A or B) — slot target
6. Idle — `idle_setpoint`

Labels in traces (`P1_vacation`, `P3_boost`, `P2_fan_coord`, `P4_evening`, `P5_morning`, `P6_idle`) are historical: the numeric suffix is not the evaluation order.

## Triggers
Every minute (`periodic`), boost/vacation/fan `on`↔`off` (attribute-only updates ignored), HA start, climate entity `unavailable` for 5 min (`climate_lost`), room sensor non-numeric for 10 min (`temp_lost`). `mode: restart`.

## Notifications
- **Climate unavailable** — in-HA warning follows the state (created while unavailable, dismissed when back); one push after 5 min (`climate_lost`); the run stops while the entity is unavailable.
- **Room sensor offline** — in-HA warning follows the state (created while `sensor.bathroom_temperature` is non-numeric, dismissed when back) and names the fallback in use (the rack's own sensor, or 20 °C); one push after 10 min (`temp_lost`). The comfort floor is suspended meanwhile; the run continues.
- **Warmup started** — once per transition, on the tick that raises the setpoint from idle (`enable_notifications` gates persistent + push); dismissed on the tick that returns the setpoint to idle. Idle is compared as the device holds it (rounded to the step, clamped to the range). A fan pause and resume inside a window is a new transition.
- **Debug** — manual run only: every computed variable (indoor temp, step/range/idle, push list, each slot's ΔT / warmup / auto_start / open / hold_until / heating / floor / in_window / active, the priority winner, desired mode and setpoint).

Push fan-out: `notify_targets` entries are filtered to well-formed `notify.<name>` service names before dispatch; each call carries `continue_on_error: true`, which covers runtime errors from a reachable service but **not** a missing action — HA aborts the run at a `notify.*` name that does not exist (verified live 2026-09-07 with a throwaway script). Every push therefore runs after the climate calls, and the deploy step checks that each target exists.

## Testing
`tests/test_bathroom_heating_rack_structure.py` pins the input schema, the trigger roster (`to:` filters, the two `for:` outage triggers), the action shape (pushes after the climate calls, edge-gated outage pushes, boost expiry last, no preset calls, no motion remnants), and renders the templates for weekday, setpoint rounding and clamping, the device idle value, the notify filter, warmup lead, comfort-floor gating with the slot-keyed deadband and latched opening edge, the suspended floor without the room sensor, window bounds, hold-until anchoring, priority rows and both notification edges; it also dry-runs the deploy script against the instance JSON.
````

- [ ] **Step 2: Replace the README section (verbatim; the section runs from `## Bathroom Heating Rack Blueprint` to the line before `## Bedroom Sleep Pre-Cool Blueprint`)**

````markdown
## Bathroom Heating Rack Blueprint

### Overview
Pre-heats a bathroom heating rack for scheduled routines (adult morning, kids bath) using a dynamic **ΔT-based warmup formula** that self-adjusts across seasons — no calendar boundaries needed. A **comfort floor** keeps the rack off while the room is already within `comfort_floor_delta` (default 1 °C) of the slot target, so a warm bathroom gets no pre-heat and no hold. Scheduled routines pause while the exhaust fan runs; a boost toggle gives an ad-hoc heat-up; a vacation toggle switches the rack off.

### Features
*   **🌡️ Dynamic Warmup:** Computes lead time from the current indoor-to-target temperature gap (`warmup_base + warmup_per_degree × ΔT`, clamped between a floor and a cap), so cold winter mornings get a longer pre-heat than warm summer mornings without any calendar configuration.
*   **🎯 Comfort Floor (v2.0.0):** A slot heats only while `indoor < target − comfort_floor_delta`. At or above that line the slot is satisfied — no pre-heat, no hold. While the device holds that slot's setpoint a 0.5 °C release deadband and a latched opening edge keep a noisy sensor from flipping the setpoint; without the room sensor the floor is suspended and a warning is raised.
*   **📅 Dual-Slot Routines:** Primary + optional secondary slot per phase (e.g., Morning A = Mon–Fri 06:45, Morning B = Sat–Sun 08:30). Evening A for kids bath, Evening B for an optional adult evening. A hold-until at or before target-warm is taken as the next day.
*   **⚡ Ad-hoc Boost Toggle:** Flip an `input_boolean` for an instant N-minute heat-up at a configurable boost temperature. Auto-expires cleanly; boost is explicit intent and is not paused by the fan.
*   **🌀 Ventilator Coordination:** Scheduled routines drop to `idle_setpoint` while the exhaust fan entity is on — no point heating air that's being evicted.
*   **🏖️ Vacation Mode:** Optional `input_boolean`(s) switch the rack off.
*   **🪶 Idempotent:** Evaluates every minute for precise timing, rounds the setpoint to the device `target_temp_step` and clamps it to the device range, and only sends climate service calls on actual transitions.
*   **🔍 Debug-Friendly:** Manual "Run" produces a persistent notification dumping all computed state (indoor temp, step, each slot's ΔT / warmup / auto_start / hold_until / in_window / active, winning priority, desired mode + setpoint).
*   **📱 Mobile Push:** Opt-in push via HA Companion (`notify.mobile_app_*`) for three high-signal events — climate unavailable (once, after 5 min), room sensor offline (once, after 10 min), and warmup started (once per transition, dismissed when the setpoint returns to idle). Targets are filtered to `notify.*` names, every push runs after the climate calls, and an empty list disables push. A target that does not exist aborts the run at the push step (HA does not suppress a missing action) — check it exists after editing.

### Requirements
*   `climate` entity for the heating rack (tested on a Tuya cloud thermostat element that reports `unknown` while on)
*   Bathroom temperature sensor (`device_class: temperature`); the climate entity's `current_temperature` is the fallback
*   Ventilator entity (or the group mirroring it) for coordination
*   Two `input_boolean` helpers: one for Ad-hoc Boost (required), one for Vacation (optional)
*   Optional: `notify.*` services for mobile push

### Installation
1. Click the button below to import this blueprint into your Home Assistant instance:

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fleviemartin%2FBlueprints_Home%2Fmain%2Fbathroom_heating_rack.yaml)

2. Or manually copy this URL into the Blueprints configuration:
`https://raw.githubusercontent.com/leviemartin/Blueprints_Home/main/bathroom_heating_rack.yaml`
````

- [ ] **Step 3: Check the README edit is scoped**

Run: `git diff --stat README.md && grep -c "^## " README.md`
Expected: only `README.md` changed, still 6 top-level `## ` sections (Nightlight, Circadian, LG AC, Ventilator, Heating Rack, Bedroom Pre-Cool); `grep -n -i "predictive motion override\|preset=eco\|generic_thermostat\|hall_motion\|stairs_motion" README.md requirements_bathroom_heating_rack.md` prints nothing.

- [ ] **Step 4: Suite still green**

Run: `~/projects/ceiling-fan-hue-blueprint/.venv/bin/python -m pytest tests -q`
Expected: `249 passed`.

- [ ] **Step 5: Commit**

```bash
git add requirements_bathroom_heating_rack.md README.md
git commit -m "docs(bathroom-heating-rack): requirements rewritten against spec §2/§4; README section for v2.0.0"
```

Step 6: Report `suite: PASS=249 FAIL=0`.

---

## Task 4: Deploy + live-verify (main loop, operator-visible)

**Model tier:** Fable (main loop)
**Rationale:** Live house state, irreversible-ish writes and judgment on trace evidence; not delegable.
**Effort:** high. **Preceded by:** code-time board PASS ([6]), `code-review-gate`, PR `Session: #13` merged ([7]) — deploy only from `main`.

**Context budget:** ~25k tokens · 0 files edited · shell + HA API · main loop.

**Files:** none edited. Uses `scripts/deploy-blueprint.sh` (pinned in the TCB roster; not modified by this plan) and `deploy/bathroom_heating_rack_1776551429917.json`.

- [ ] **Step 1: TCB verify + branch freshness** — `TCB_EXTRA=/home/martin/AI/projects/Blueprints_Home/scripts/deploy-blueprint.sh ~/.claude/skills/convene-board/scripts/tcb-manifest.sh verify /home/martin/AI/reviews/tcb-baseline-16ef53e7f973185a.txt` → rc 0 or HALT. Then `git fetch origin && git checkout main && [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ]`. If the harness classifier blocks the deploy command, render it through `op-templates.sh` (stack-b §4.6) and hand it to Martin — no workaround.
- [ ] **Step 2: Pre-deploy live read** — `GET /api/config/automation/config/1776551429917` (expect the v1 keys listed in Phase 0) and `GET /api/states/climate.heatingrack_bathroom` (note `temperature` and state); record both in the session log. **Notify-target existence (board R1-04):** every entry of `notify_targets` in the instance JSON must appear in `GET /api/services` under domain `notify` — `jq -r '.[] | select(.domain=="notify") | .services | keys[]'` must list `mobile_app_martin_fold`; a missing target HALTs the deploy (HA aborts the run at a missing action even with `continue_on_error`).
- [ ] **Step 3: Deploy** — `scripts/deploy-blueprint.sh bathroom_heating_rack.yaml leviemartin/bathroom_heating_rack.yaml deploy/bathroom_heating_rack_1776551429917.json` → expect `backup: deploy/1776551429917.prev.json`, `blueprint/save: ok`, `instance 1776551429917: config written`, `automation.bathroom_heating_rack_v1_0_0 state=on`, `deploy complete`. The backup is gitignored; never commit it.
- [ ] **Step 4: Read-path proof** — `POST /api/services/automation/trigger` with `{"entity_id":"automation.bathroom_heating_rack_v1_0_0"}`; read `persistent_notification/get` → `heating_rack_debug` must show `(step 1.0, range 7.0–30.0, idle 7.0)`, `Push: ['notify.mobile_app_martin_fold']`, `Comfort floor: 1.0°C`, and for all four slots `open=`, `hold_until=`, `heating=`, `floor=`, `in_window=`, `active=`, plus `setpoint=… (raw …)`. Then `trace/list` + `trace/get` for the automation: `changed_variables` contains `idle_setpoint_dev`, `notify_list`, `ea_open_dt`, `desired_setpoint_raw` (v2-only). Confirm the setpoint decision matches the clock: outside every window `active_priority=P6_idle`, `desired_setpoint=7.0`, no `climate.set_temperature` call in the trace; `heating_rack_sensor_warning` and `heating_rack_climate_unavailable` absent (both entities live).
- [ ] **Step 5: Log gate** — `system_log/list` filtered on `Heating Rack` / `heating_rack`: zero new entries after the deploy timestamp (the pre-deploy count is 3,336 — it must not grow).
- [ ] **Step 6: Record** — post the deploy evidence (entity state, debug dump excerpt, trace step, log gate) on session #13 via `github-sync` (`gh_scan_body` on the body file); the observation loop then runs against the Phase 0 criteria; `<!-- observe:open -->` stays until criteria 1–5 pass or Martin waives.

Step 7: Report `deploy: PASS=N FAIL=M` over the six steps above.

---

## Chain notes

- **[4] design-time board** runs on spec §4 + this plan before Task 1 (`triple-check` → `convene-board`, standard dial, R1 Opus + R2 Codex unpinned — record the model each leg reports, `/effort xhigh`).
- **[6] code-time board** runs on the branch diff after Task 3 (`review-shipped` → `convene-board`), then `code-review-gate`, PR with `Session: #13`, merge, Task 4, observation, `closing-session` (finish gated on [8]).
- Session #11 (ventilator) is still `in-review` with `observe:open` — untouched by this session.

---

## Execution record — SDD Tasks 1–3 + final whole-branch review (2026-09-07)

Tasks 1–3 shipped on `bathroom-heating-rack-v2` as verbatim transcriptions of the blocks above (Sonnet implementers, per-task Sonnet reviews, each byte-identical to the plan): T1 `e90f391` (RED 96/20 on v1.1.1), T2 `2f1ebd6` (116/116, suite 249, dry-run ok, HA `validate_config` valid), T3 `c66a342`. The Opus whole-branch review returned 0 Critical / 0 Important / 8 Minor; seven were fixed in one wave, `743254c`, and re-reviewed (all addressed, no new breakage). **After that commit the shipped files are authoritative over the inline blocks above**, which differ in exactly these points:
- `<p>_heating` gains `not boost_active and` (a boost equal to a slot target — the blueprint defaults are both 23 — must not latch that slot's deadband/opening edge).
- `<p>_target_dev` is clamped to `setpoint_min`/`setpoint_max` like `desired_setpoint` (a slot target above the device max would otherwise never latch).
- STEP 3 hard-stops on a MISSING climate entity too: `states[entity_climate] is none or states(entity_climate) == 'unavailable'` (HA reads `unknown` for a deleted/renamed entity, which the normaliser would have treated as ON; live-verified with `/api/template`); the available branch is the complement.
- `notify_list` carries the ventilator's scalar guard.
- Test harness: `states()` of a missing entity returns `'unknown'` (HA semantics); +7 tests (`test_climate_hard_stop_rows` ×4, `test_boost_does_not_alias_slot_heating`, `test_target_dev_clamped_to_device_range`, a scalar `notify_list` row) → rack **123**, suite **256** on this branch (origin/main gained 5 tests from the #15 hotfix meanwhile → expect **261** after the [7] merge).
- Requirements doc: the stale duplicate `in_window` line removed; `temp_lost` wording is "unavailable/unknown for 10 min".
Accepted-documented minor: a `/1` tick landing in the same sub-second as a `for:`-guarded outage trigger can cancel that outage run (`mode: restart`) and lose one push; self-healing on the next outage. Deferred cosmetic: the debug dump's `strftime('%a %H:%M')` day label.
