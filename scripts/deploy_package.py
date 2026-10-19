#!/usr/bin/env python3
"""Checked deployment of the livingroom package; never restart Home Assistant."""
import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "ha/packages"
DEPLOY_DIR = ROOT / "deploy"
SAMBA_ENV = Path.home() / ".config/hass-samba/env"
HA_ENV = Path.home() / ".config/hass-cli/env"
SAMUEL = ("1701294514096", "1701295072034", "1701295128408", "1701294978959")
LIVE = "packages/livingroom_music.yaml"
CHECK = "/api/config/core/check_config"
API = "/api/config/automation/config/"
MISSING = ("NT_STATUS_NO_SUCH_FILE", "NT_STATUS_OBJECT_NAME_NOT_FOUND")


class DeployError(Exception):
    def __init__(self, message, status=1):
        super().__init__(message)
        self.status = status


def stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _spawn(argv):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        raise DeployError("command unavailable or timed out") from None
    if result.returncode:
        output = result.stdout + result.stderr
        status = next((s for s in MISSING if s in output), 1)
        raise DeployError("command failed", status)
    return result.stdout


def env_file(path):
    try:
        values = {}
        for line in path.read_text().splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            words = shlex.split(line)
            if words and words[0] == "export":
                words = words[1:]
            if len(words) != 1 or "=" not in words[0]:
                raise ValueError
            key, value = words[0].split("=", 1)
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                raise ValueError
            if any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise ValueError
            values[key] = value
        return values
    except (OSError, ValueError, UnicodeError):
        raise DeployError("credential file missing, unreadable or malformed") from None


def require(values, keys):
    for key in keys:
        if not values.get(key):
            raise DeployError("missing " + key)


def ha_settings():
    values = env_file(HA_ENV)
    override = os.environ.get("HASS_SERVER")
    if override:
        values["HASS_SERVER"] = override
    require(values, ("HASS_SERVER", "HASS_TOKEN"))
    server = values["HASS_SERVER"].removesuffix("/")
    match = re.fullmatch(r"(https?)://([A-Za-z0-9_.-]+)(:[0-9]+)?", server)
    if not match or any(c.isspace() or ord(c) < 32 for c in server):
        raise DeployError("invalid HASS_SERVER")
    if match[1] == "http":
        try:
            allowed = ipaddress.ip_address(match[2]) in ipaddress.ip_network("100.64.0.0/10")
        except ValueError:
            allowed = False
        if not allowed:
            raise DeployError("invalid HASS_SERVER")
    return server, values["HASS_TOKEN"]


def private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def digest(data):
    return hashlib.sha256(data).digest()


def valid_check(ha):
    try:
        status, body = ha("POST", CHECK)
        result = json.loads(body)
        return status == 200 and isinstance(result, dict) and result.get("result") == "valid"
    except (DeployError, ValueError):
        return False


def preflight(ha):
    try:
        if ha("GET", "/api/")[0] == 200:
            return
    except DeployError:
        pass
    raise DeployError("HA API not reachable or token refused; nothing uploaded or deleted")


def deploy(ha, smb, tmp, data, backup):
    preflight(ha)
    if not valid_check(ha):
        raise DeployError("config already invalid; nothing uploaded")
    snapshot = tmp / "package.yaml"
    private(snapshot, data)
    config = tmp / "configuration.yaml"
    smb(f'get configuration.yaml "{config}"')
    # ponytail: guard the established include line; use a YAML parser if layouts expand.
    if not re.search(r"(?m)^[ \t]+packages:[ \t]*!include_dir_named[ \t]+packages[ \t]*$", config.read_text()):
        raise DeployError("Under homeassistant: add packages: !include_dir_named packages", 3)
    try:
        smb("ls " + LIVE)
        existing = True
    except DeployError as exc:
        if exc.status not in MISSING:
            raise
        existing = False
    old = tmp / "old.yaml"
    old_hash = None
    if existing:
        try:
            smb("mkdir backup-packages")
        except DeployError:
            pass
        try:
            smb("ls " + backup)
        except DeployError as exc:
            if exc.status not in MISSING:
                raise
        else:
            raise DeployError("backup path already exists; nothing uploaded")
        smb(f'get {LIVE} "{old}"')
        old_hash = digest(old.read_bytes())
        smb(f'put "{old}" {backup}')
        print("backup: " + backup)
    try:
        smb(f'put "{snapshot}" {LIVE}.new')
    except DeployError:
        raise DeployError("upload failed; live package unchanged") from None
    staged = tmp / "staged.yaml"
    new_hash = digest(data)
    try:
        smb(f'get {LIVE}.new "{staged}"')
        if digest(staged.read_bytes()) != new_hash:
            raise DeployError("staging mismatch")
    except (DeployError, OSError):
        raise DeployError("staged upload differs; live package unchanged") from None
    try:
        smb(f"rename {LIVE}.new {LIVE} -f")
    except DeployError:
        after_hash = None
        missing = False
        try:
            after = tmp / "after.yaml"
            smb(f'get {LIVE} "{after}"')
            after_hash = digest(after.read_bytes())
        except DeployError as exc:
            missing = exc.status in MISSING
        except OSError:
            pass
        if after_hash == new_hash:
            print("rename reply lost; new package installed")
        elif (existing and after_hash == old_hash) or (not existing and missing):
            raise DeployError("rename failed; live package unchanged; .new left in place") from None
        else:
            detail = "; backup: " + backup if existing else ""
            raise DeployError("rename result unresolved; check " + LIVE + " by hand" + detail, 5) from None
    if not valid_check(ha):
        try:
            if existing:
                smb(f'put "{old}" {LIVE}.new')
                smb(f'get {LIVE}.new "{staged}"')
                if digest(staged.read_bytes()) != old_hash:
                    raise DeployError("rollback staging mismatch")
                smb(f"rename {LIVE}.new {LIVE} -f")
                restored = tmp / "restored.yaml"
                smb(f'get {LIVE} "{restored}"')
                if digest(restored.read_bytes()) != old_hash:
                    raise DeployError("rollback mismatch")
            else:
                smb("del " + LIVE)
        except (DeployError, OSError):
            detail = "restore from " + backup if existing else "delete " + LIVE + " by hand"
            raise DeployError("rollback failed; " + detail, 5) from None
        raise DeployError("check_config failed; package rolled back", 4)
    print("check_config: valid")
    print("Martin: restart Home Assistant")
    return 0


def exports():
    result = {}
    for i in SAMUEL:
        try:
            obj = json.loads((DEPLOY_DIR / (i + ".retired.json")).read_text())
            if not isinstance(obj, dict) or obj.get("id") != i:
                raise ValueError
            result[i] = obj
        except (OSError, ValueError, UnicodeError):
            raise DeployError("missing or invalid export: deploy/" + i + ".retired.json") from None
    return result


def verify(ha):
    failed = False
    for i in SAMUEL:
        try:
            status, _ = ha("GET", API + i)
            if status == 404:
                print(i + " gone")
                continue
            print(i + " still present" if status == 200 else f"GET {i} failed (status {status})")
        except DeployError:
            print("GET " + i + " failed")
        failed = True
    return int(failed)


def retire(ha, saved):
    preflight(ha)
    pending = []
    for i in SAMUEL:
        try:
            status, body = ha("GET", API + i)
            if status == 404:
                print(i + " already removed")
                continue
            if status != 200:
                raise DeployError("GET failed")
            obj = json.loads(body)
        except (DeployError, ValueError):
            raise DeployError("GET " + i + " failed") from None
        if obj != saved[i]:
            raise DeployError(i + " differs from deploy/" + i + ".retired.json; nothing deleted")
        pending.append(i)
    for i in pending:
        try:
            status, _ = ha("DELETE", API + i)
        except DeployError:
            raise DeployError("DELETE " + i + " no reply; run --verify-retired") from None
        if status not in (200, 404):
            raise DeployError(f"DELETE {i} failed (status {status})")
        print("deleted " + i if status == 200 else i + " already removed")
    return verify(ha)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--package", choices=("livingroom_music",))
    modes.add_argument("--retire-automations", action="store_true")
    modes.add_argument("--verify-retired", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    if args.yes and not args.retire_automations:
        parser.error("--yes requires --retire-automations")
    if args.verify_retired and args.dry_run:
        parser.error("--verify-retired does not accept --dry-run")
    if args.retire_automations and not (args.yes or args.dry_run):
        parser.error("--retire-automations requires --yes")
    try:
        data = None
        saved = None
        backup = "backup-packages/livingroom_music.yaml.bak-" + stamp()
        if args.package:
            path = PACKAGE_DIR / "livingroom_music.yaml"
            if not path.is_file():
                raise DeployError("package file missing or not regular")
            with path.open("rb") as stream:
                data = stream.read(65537)
            if not 1 <= len(data) <= 65536:
                raise DeployError("package size must be 1..65536 bytes")
        if args.retire_automations:
            saved = exports()
        if args.dry_run:
            if args.package:
                print(f"backup: {backup}; upload {LIVE}.new; verify; rename to {LIVE}")
                print("check_config, then Martin restarts Home Assistant")
            else:
                for i in SAMUEL:
                    print("DELETE " + API + i)
            return 0
        samba = None
        if args.package:
            samba = env_file(SAMBA_ENV)
            require(samba, ("SMB_HOST", "SMB_SHARE", "SMB_USER", "SMB_PASS"))
            for key, pattern in (("SMB_HOST", r"[A-Za-z0-9_.-]+"), ("SMB_SHARE", r"[A-Za-z0-9_-]+")):
                if not re.fullmatch(pattern, samba[key]):
                    raise DeployError("invalid " + key)
        server, token = ha_settings()
        with tempfile.TemporaryDirectory(prefix="deploy-package-") as directory:
            tmp = Path(directory)
            header = tmp / "header"
            private(header, ("Authorization: Bearer " + token + "\n").encode())
            def ha(method, path):
                body = tmp / "body"
                try:
                    status = _spawn(["curl", "-q", "--noproxy", "*", "-sS", "--max-time", "60",
                                     "-o", str(body), "-w", "%{http_code}", "-H", "@" + str(header),
                                     "-H", "Content-Type: application/json", "-X", method, server + path]
                                    + (["--data", "{}"] if method == "POST" else []))
                    return int(status.strip()), body.read_text()
                except (OSError, ValueError, UnicodeError):
                    raise DeployError("HA response unreadable") from None
            if args.verify_retired:
                return verify(ha)
            if args.retire_automations:
                return retire(ha, saved)
            auth = tmp / "auth"
            private(auth, ("username = " + samba["SMB_USER"] + "\npassword = " + samba["SMB_PASS"] + "\n").encode())
            def smb(command):
                return _spawn(["smbclient", "//" + samba["SMB_HOST"] + "/" + samba["SMB_SHARE"],
                               "-A", str(auth), "-c", command])
            return deploy(ha, smb, tmp, data, backup)
    except DeployError as exc:
        print(str(exc))
        return exc.status if isinstance(exc.status, int) else 1
    except (OSError, UnicodeError):
        print("local file could not be read or written")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
