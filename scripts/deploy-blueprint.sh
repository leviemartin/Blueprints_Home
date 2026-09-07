#!/usr/bin/env bash
# deploy-blueprint.sh — push a blueprint YAML to Home Assistant, migrate its automation
# instances, and assert every instance is still enabled afterwards.
#
#   scripts/deploy-blueprint.sh [--dry-run] <blueprint.yaml> <ha-blueprint-path> [instance.json ...]
#
#   <ha-blueprint-path>  the path HA knows the blueprint by, e.g. leviemartin/bathroom_ventilator.yaml
#   instance.json        full automation config (id, alias, use_blueprint{path,input}) to POST back
#                        to /api/config/automation/config/<id>; the endpoint reloads that automation.
#   --dry-run            validate only (YAML parses, every instance input key exists in the
#                        blueprint schema, every required input is present); no network.
#
# Credentials come from ~/.config/hass-cli/env (HASS_SERVER, HASS_TOKEN) and are never printed.
# Previous instance configs are saved to deploy/<id>.prev.json before they are overwritten.
set -euo pipefail

die() { printf 'deploy-blueprint: %s\n' "$*" >&2; exit 1; }

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then DRY_RUN=1; shift; fi
[ $# -ge 2 ] || die "usage: deploy-blueprint.sh [--dry-run] <blueprint.yaml> <ha-blueprint-path> [instance.json ...]"
BP_FILE=$1; BP_PATH=$2; shift 2
[ -f "$BP_FILE" ] || die "blueprint file not found: $BP_FILE"
case "$BP_PATH" in */*.yaml) ;; *) die "ha-blueprint-path must look like <owner>/<file>.yaml, got: $BP_PATH";; esac

PY=${PYTHON:-python3}
"$PY" -c 'import yaml' 2>/dev/null || die "$PY lacks PyYAML; set PYTHON=<interpreter with pyyaml>"

# --- 1. schema validation (offline) -------------------------------------------------------
SCHEMA_JSON=$("$PY" - "$BP_FILE" <<'EOF'
import json, sys, yaml
class L(yaml.SafeLoader): pass
L.add_constructor("!input", lambda l, n: {"__input__": l.construct_scalar(n)})
with open(sys.argv[1]) as fh:
    bp = yaml.load(fh, Loader=L)
inputs = bp["blueprint"]["input"]
print(json.dumps({"name": bp["blueprint"]["name"],
                  "keys": sorted(inputs),
                  "required": sorted(k for k, v in inputs.items() if "default" not in (v or {}))}))
EOF
) || die "blueprint YAML failed to parse"
printf 'blueprint: %s\n' "$(printf '%s' "$SCHEMA_JSON" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["name"])')"

validate_instance() {
  local f=$1
  [ -f "$f" ] || die "instance file not found: $f"
  "$PY" - "$f" "$BP_PATH" "$SCHEMA_JSON" <<'EOF' || exit 1
import json, sys
inst = json.load(open(sys.argv[1])); bp_path = sys.argv[2]; schema = json.loads(sys.argv[3])
problems = []
if inst.get("use_blueprint", {}).get("path") != bp_path:
    problems.append(f"use_blueprint.path {inst.get('use_blueprint', {}).get('path')!r} != {bp_path!r}")
given = set(inst.get("use_blueprint", {}).get("input", {}))
unknown = sorted(given - set(schema["keys"]))
missing = sorted(set(schema["required"]) - given)
if unknown: problems.append("unknown input keys (would make the instance unavailable): " + ", ".join(unknown))
if missing: problems.append("required inputs missing: " + ", ".join(missing))
import re
if not re.fullmatch(r"[A-Za-z0-9_-]+", str(inst.get("id", ""))):
    problems.append("instance id must match ^[A-Za-z0-9_-]+$ (it is used in URLs and backup paths)")
if problems:
    print(f"instance {sys.argv[1]}: INVALID\n  - " + "\n  - ".join(problems)); sys.exit(1)
print(f"instance {sys.argv[1]}: ok (id {inst['id']}, {len(given)} inputs)")
EOF
}

for f in "$@"; do validate_instance "$f"; done
if [ "$DRY_RUN" = 1 ]; then printf 'dry-run: validation passed, nothing deployed\n'; exit 0; fi

# --- 2. credentials ----------------------------------------------------------------------
[ -f "$HOME/.config/hass-cli/env" ] && . "$HOME/.config/hass-cli/env"
[ -n "${HASS_SERVER:-}" ] && [ -n "${HASS_TOKEN:-}" ] || die "HASS_SERVER / HASS_TOKEN not set"
command -v hass-cli >/dev/null || die "hass-cli not on PATH"
command -v jq >/dev/null || die "jq not on PATH"
# The token never appears in argv (process listings): curl reads the header from a 0600 temp file.
HDR=$(mktemp) || die "mktemp failed"
chmod 600 "$HDR"
printf 'Authorization: Bearer %s\n' "$HASS_TOKEN" > "$HDR"
trap 'rm -f "$HDR"' EXIT
api() { curl -sS --fail-with-body -H @"$HDR" -H 'Content-Type: application/json' "$@"; }

# --- 3. back up current instance configs -----------------------------------------------
mkdir -p deploy
for f in "$@"; do
  id=$(jq -r .id "$f")
  api "$HASS_SERVER/api/config/automation/config/$id" > "deploy/$id.prev.json" \
    || die "could not read current config of automation id $id"
  printf 'backup: deploy/%s.prev.json\n' "$id"
done

# --- 4. blueprint/save ---------------------------------------------------------------------
frame=$(jq -n --arg p "$BP_PATH" --rawfile y "$BP_FILE" '{domain:"automation", path:$p, yaml:$y, allow_override:true}')
resp=$(hass-cli -o json raw ws blueprint/save --json "$frame") || die "blueprint/save transport failure"
printf '%s' "$resp" | jq -e '.success == true' >/dev/null \
  || die "blueprint/save rejected: $(printf '%s' "$resp" | jq -c '.error // .')"
printf 'blueprint/save: ok (%s)\n' "$BP_PATH"

# --- 5. migrate instances --------------------------------------------------------------
for f in "$@"; do
  id=$(jq -r .id "$f")
  out=$(api -X POST "$HASS_SERVER/api/config/automation/config/$id" --data @"$f") \
    || die "POST instance $id failed: $out"
  printf '%s' "$out" | jq -e '.result == "ok"' >/dev/null || die "POST instance $id: unexpected response $out"
  printf 'instance %s: config written\n' "$id"
done

# --- 6. assert instances are enabled -----------------------------------------------------
sleep 3
fail=0
for f in "$@"; do
  id=$(jq -r .id "$f")
  line=$(api "$HASS_SERVER/api/states" | jq -r --arg id "$id" \
    '.[] | select(.entity_id|startswith("automation.")) | select(.attributes.id == $id) | "\(.entity_id) state=\(.state) last_triggered=\(.attributes.last_triggered)"')
  [ -n "$line" ] || { printf 'instance %s: NOT FOUND in states\n' "$id"; fail=1; continue; }
  printf '%s\n' "$line"
  case "$line" in *"state=on"*) ;; *) fail=1;; esac
done
[ "$fail" = 0 ] || die "at least one instance is not 'on' after deploy — inspect the entity, restore from deploy/<id>.prev.json if needed"
printf 'deploy complete\n'
