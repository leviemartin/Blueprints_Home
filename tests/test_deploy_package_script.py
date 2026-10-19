"""Offline deployment contract; all subprocesses are replaced by a remote model."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import stat
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIVE = "packages/livingroom_music.yaml"
BACKUP = "backup-packages/livingroom_music.yaml.bak-test"
CHECK = "/api/config/core/check_config"
API = "/api/config/automation/config/"
PINS = {
    "1701294514096": ("cc419360994a4f3090634f8947332c869e61f239173ff669019f30781ed7ded7", "Sonos On Samuel"),
    "1701294978959": ("dfcbbf36cb9cac091ab934dbebd1f6c967a66dae6e7ce4bd79fdad909f1aac4a", "Sonos Off Samuel"),
    "1701295072034": ("0f92757cfef9dfdb4f94bb0b82a616a82e2fc2338255ea6167a72279038874e0", "Sonos 20% Volume Samuel"),
    "1701295128408": ("6f9b378a57f5d8b329bb5887e4e7ee97354054c089cff376f023a35240ebbe97", "Sonos 10% Volume Samuel"),
}


@pytest.fixture(autouse=True)
def clear_server(monkeypatch):
    monkeypatch.delenv("HASS_SERVER", raising=False)


def load():
    spec = importlib.util.spec_from_file_location("deploy_package", ROOT / "scripts/deploy_package.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Remote:
    def __init__(self, m, monkeypatch, tmp_path):
        self.m = m
        self.remote = {"configuration.yaml": b"homeassistant:\n  packages: !include_dir_named packages\n", LIVE: b"old\n"}
        self.calls = []
        self.private = []
        self.events = []
        self.hook = lambda event: None
        self.checks = [(200, {"result": "valid"}), (200, {"result": "valid"})]
        self.exports = {i: {"id": i, "alias": "old"} for i in m.SAMUEL}
        self.automations = dict(self.exports)
        self.responses = {}
        self.values = {k: os.urandom(24).hex() for k in ("SMB_USER", "SMB_PASS", "HASS_TOKEN")}
        for key, value in {
            "PACKAGE_DIR": tmp_path / "packages", "DEPLOY_DIR": tmp_path / "deploy",
            "SAMBA_ENV": tmp_path / "samba-env", "HA_ENV": tmp_path / "ha-env",
        }.items():
            monkeypatch.setattr(m, key, value)
        m.PACKAGE_DIR.mkdir()
        m.DEPLOY_DIR.mkdir()
        self.package = m.PACKAGE_DIR / "livingroom_music.yaml"
        self.package.write_bytes(b"new\n")
        self.samba = {"SMB_HOST": "ha", "SMB_SHARE": "config",
                      "SMB_USER": self.values["SMB_USER"], "SMB_PASS": self.values["SMB_PASS"]}
        self.ha = {"HASS_SERVER": "https://ha.example:8123", "HASS_TOKEN": self.values["HASS_TOKEN"]}
        self.write_env()
        for i, obj in self.exports.items():
            (m.DEPLOY_DIR / (i + ".retired.json")).write_text(json.dumps(obj))
        monkeypatch.setattr(m, "stamp", lambda: "test")
        monkeypatch.setattr(m, "_spawn", self.spawn)

    def write_env(self):
        for path, values in ((self.m.SAMBA_ENV, self.samba), (self.m.HA_ENV, self.ha)):
            path.write_text("".join(f"export {k}={shlex.quote(v)}\n" for k, v in values.items()))

    def fail(self):
        raise self.m.DeployError("transport failed")

    def missing(self):
        raise self.m.DeployError("remote missing", "NT_STATUS_OBJECT_NAME_NOT_FOUND")

    def spawn(self, argv):
        self.calls.append(argv)
        if argv[0] == "smbclient":
            auth = Path(argv[argv.index("-A") + 1])
            self.private.append((auth, stat.S_IMODE(auth.stat().st_mode), auth.read_text()))
            words = shlex.split(argv[argv.index("-c") + 1])
            op, *args = words
            event = (op, args[-1] if op == "put" else args[0])
            self.events.append(event)
            self.hook(event)
            if op == "mkdir":
                return ""
            if op == "put":
                self.remote[args[1]] = Path(args[0]).read_bytes()
            elif op in ("get", "ls"):
                if args[0] not in self.remote:
                    self.missing()
                if op == "get":
                    Path(args[1]).write_bytes(self.remote[args[0]])
            elif op == "rename":
                assert args[2] == "-f"
                self.remote[args[1]] = self.remote.pop(args[0])
            elif op == "del":
                self.remote.pop(args[0])
            else:
                pytest.fail("unexpected Samba command")
            return ""
        assert argv[0] == "curl"
        assert argv[1:4] == ["-q", "--noproxy", "*"]
        header = Path(next(a[1:] for a in argv if a.startswith("@")))
        self.private.append((header, stat.S_IMODE(header.stat().st_mode), header.read_text()))
        method = argv[argv.index("-X") + 1]
        url = argv[argv.index("-X") + 2]
        path = urlsplit(url).path
        event = (method, path)
        self.events.append(event)
        self.hook(event)
        if event in self.responses:
            answer = self.responses[event]
        elif path == "/api/":
            answer = (200, {})
        elif path == CHECK:
            answer = self.checks.pop(0)
        elif path.startswith(API):
            i = path.removeprefix(API)
            assert i in self.m.SAMUEL
            if method == "DELETE":
                answer = (200 if i in self.automations else 404, {})
                self.automations.pop(i, None)
            else:
                answer = (200, self.automations[i]) if i in self.automations else (404, {})
        else:
            pytest.fail("unexpected HA path")
        if answer is None:
            self.fail()
        status, body = answer
        Path(argv[argv.index("-o") + 1]).write_text(json.dumps(body))
        return str(status)

    def deploy(self, *extra):
        return self.m.main(["--package", "livingroom_music", *extra])

    def retire(self, *extra):
        return self.m.main(["--retire-automations", "--yes", *extra])


def test_retired_exports_pinned():
    for i, (digest, alias) in PINS.items():
        data = (ROOT / "deploy" / (i + ".retired.json")).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest
        obj = json.loads(data)
        assert obj["id"] == i and obj["alias"] == alias
        assert set(obj) == {"action", "alias", "condition", "description", "id", "mode", "trigger"}
        assert all(t["device_id"] == "dfad9901619a42507889cad7dfc9b8d9" for t in obj["trigger"])


def test_deploy_existing_package_happy_path(monkeypatch, tmp_path, capsys):
    f = Remote(load(), monkeypatch, tmp_path)
    assert f.deploy() == 0
    assert f.remote[LIVE] == b"new\n" and f.remote[BACKUP] == b"old\n"
    assert f.events == [("GET", "/api/"), ("POST", CHECK), ("get", "configuration.yaml"),
                        ("ls", LIVE), ("mkdir", "backup-packages"), ("ls", BACKUP),
                        ("get", LIVE), ("put", BACKUP), ("put", LIVE + ".new"),
                        ("get", LIVE + ".new"), ("rename", LIVE + ".new"), ("POST", CHECK)]
    put = next(a for a in f.calls if a[0] == "smbclient" and 'package.yaml"' in a[-1])
    assert str(f.package) not in put[-1]
    assert capsys.readouterr().out.splitlines()[-1] == "Martin: restart Home Assistant"
    assert not any("/api/services" in str(a) or "DELETE" in a for a in f.calls)


def test_first_deploy_without_existing_package(monkeypatch, tmp_path):
    f = Remote(load(), monkeypatch, tmp_path)
    del f.remote[LIVE]
    assert f.deploy() == 0 and f.remote[LIVE] == b"new\n"
    assert not any("backup" in path for _, path in f.events)


@pytest.mark.parametrize("args", [
    ["--package", "security_core"], [], ["--package"], ["--package", ""],
    ["--package", "livingroom_music", "--bogus"], ["--retire-automations", "--yes", "1234"],
    ["--package", "livingroom_music", "--retire-automations"], ["--verify-retired", "--yes"],
    ["--verify-retired", "--dry-run"], ["--package", "livingroom_music", "--yes"],
    ["--retire-automations"],
])
def test_rejects_invalid_cli(monkeypatch, tmp_path, args):
    f = Remote(load(), monkeypatch, tmp_path)
    with pytest.raises(SystemExit) as exc:
        f.m.main(args)
    assert exc.value.code == 2 and not f.calls


@pytest.mark.parametrize("size", [None, 0, 65537])
def test_refuses_bad_package_file(monkeypatch, tmp_path, size):
    f = Remote(load(), monkeypatch, tmp_path)
    if size is None:
        f.package.unlink()
    else:
        f.package.write_bytes(b"x" * size)
    assert f.deploy() == 1 and not f.calls
    f.package.write_bytes(b"x" * 65536)
    assert f.deploy("--dry-run") == 0 and not f.calls


@pytest.mark.parametrize("existing", [True, False])
def test_check_config_invalid_rolls_back(monkeypatch, tmp_path, capsys, existing):
    f = Remote(load(), monkeypatch, tmp_path)
    if not existing:
        del f.remote[LIVE]
    f.checks[1] = (200, {"result": "invalid", "errors": "private-error-marker"})
    assert f.deploy() == 4
    assert f.remote.get(LIVE) == (b"old\n" if existing else None)
    out = capsys.readouterr().out
    assert "rolled back" in out and "restart" not in out and "private-error-marker" not in out


def test_leftover_new_file_is_overwritten(monkeypatch, tmp_path):
    f = Remote(load(), monkeypatch, tmp_path)
    f.remote[LIVE + ".new"] = b"stale"
    assert f.deploy() == 0 and f.remote[LIVE] == b"new\n"


def test_refuses_existing_backup_path(monkeypatch, tmp_path):
    f = Remote(load(), monkeypatch, tmp_path)
    f.remote[BACKUP] = b"keep"
    assert f.deploy() == 1 and f.remote[BACKUP] == b"keep"
    assert not any(op in ("put", "rename") for op, _ in f.events)


@pytest.mark.parametrize("bad", [
    "samba-absent", "samba-directory", "SMB_HOST", "SMB_SHARE", "SMB_USER", "SMB_PASS",
    "host-invalid", "share-invalid", "ha-absent", "HASS_SERVER", "HASS_TOKEN",
    "ftp", "lan", "http",
])
def test_refuses_bad_samba_or_ha_env(monkeypatch, tmp_path, capsys, bad):
    f = Remote(load(), monkeypatch, tmp_path)
    if bad in f.samba:
        del f.samba[bad]
    elif bad in f.ha:
        del f.ha[bad]
    elif bad == "host-invalid":
        f.samba["SMB_HOST"] = "a/b"
    elif bad == "share-invalid":
        f.samba["SMB_SHARE"] = "a b"
    elif bad in ("ftp", "lan", "http"):
        f.ha["HASS_SERVER"] = {"ftp": "ftp://x", "lan": "http://" + "192.168." + "1.5:8123",
                               "http": "http://ha.local:8123"}[bad]
    f.write_env()
    if bad in ("samba-absent", "samba-directory"):
        f.m.SAMBA_ENV.unlink()
        if bad == "samba-directory":
            f.m.SAMBA_ENV.mkdir()
    if bad == "ha-absent":
        f.m.HA_ENV.unlink()
    assert f.deploy() == 1 and not f.calls
    output = capsys.readouterr()
    assert all(v not in output.out + output.err for v in f.values.values())


def test_env_parse_export_quotes_and_ignores_process_env(monkeypatch, tmp_path):
    f = Remote(load(), monkeypatch, tmp_path)
    f.samba["SMB_PASS"] += "#" + os.urandom(8).hex()
    f.write_env()
    with f.m.SAMBA_ENV.open("a") as stream:
        stream.write("# comment\n\n")
    f.m.HA_ENV.write_text('HASS_SERVER=' + f.ha["HASS_SERVER"] + '\nHASS_TOKEN="' + f.ha["HASS_TOKEN"] + '"\n')
    for name in ("SMB_PASS", "HASS_TOKEN"):
        monkeypatch.setenv(name, os.urandom(24).hex())
    assert f.deploy() == 0
    contents = "".join(text for _, _, text in f.private)
    assert f.samba["SMB_PASS"] in contents and f.ha["HASS_TOKEN"] in contents
    assert os.environ["SMB_PASS"] not in contents and os.environ["HASS_TOKEN"] not in contents


@pytest.mark.parametrize("server", ["https://ha.example:8123", "http://" + "100." + "116.73.57:8123",
                                   "https://ha.example:8123/"])
def test_server_scheme_accepted(monkeypatch, tmp_path, server):
    f = Remote(load(), monkeypatch, tmp_path)
    f.ha["HASS_SERVER"] = server
    f.write_env()
    assert f.deploy() == 0
    urls = [a[a.index("-X") + 2] for a in f.calls if a[0] == "curl"]
    assert all(u.startswith(server.rstrip("/") + "/api/") and "//api" not in u for u in urls)


@pytest.mark.parametrize("failure", ["unauthorized", "transport", "baseline", "retire"])
def test_preflight_failure_uploads_nothing(monkeypatch, tmp_path, capsys, failure):
    f = Remote(load(), monkeypatch, tmp_path)
    if failure == "baseline":
        f.checks[0] = (200, {"result": "invalid"})
    else:
        f.responses[("GET", "/api/")] = None if failure == "transport" else (401, {})
    assert (f.retire() if failure == "retire" else f.deploy()) == 1
    assert not any(a[0] == "smbclient" for a in f.calls)
    assert not any(op == "DELETE" for op, _ in f.events)
    if failure == "retire":
        assert not any(op == "POST" for op, _ in f.events)
    if failure == "baseline":
        assert "config already invalid" in capsys.readouterr().out


@pytest.mark.parametrize("event", [("get", "configuration.yaml"), ("put", LIVE + ".new")])
def test_samba_failure_before_or_during_upload(monkeypatch, tmp_path, event):
    f = Remote(load(), monkeypatch, tmp_path)
    f.hook = lambda e: f.fail() if e == event else None
    assert f.deploy() == 1 and f.remote[LIVE] == b"old\n"
    assert not any(op == "rename" for op, _ in f.events)
    assert f.events.count(("POST", CHECK)) == 1


def test_staged_upload_corruption_no_rename(monkeypatch, tmp_path):
    f = Remote(load(), monkeypatch, tmp_path)
    def corrupt(e):
        if e == ("get", LIVE + ".new"):
            f.remote[LIVE + ".new"] = b"bad\n"
    f.hook = corrupt
    assert f.deploy() == 1 and f.remote[LIVE] == b"old\n"
    assert not any(op == "rename" for op, _ in f.events)


@pytest.mark.parametrize("mode", ["old", "absent", "committed", "unknown"])
def test_rename_error_reconciled(monkeypatch, tmp_path, capsys, mode):
    f = Remote(load(), monkeypatch, tmp_path)
    if mode == "absent":
        del f.remote[LIVE]
    def rename(e):
        if e == ("rename", LIVE + ".new"):
            if mode == "committed":
                f.remote[LIVE] = f.remote.pop(LIVE + ".new")
            elif mode == "unknown":
                f.remote[LIVE] = b"unknown"
            f.fail()
    f.hook = rename
    assert f.deploy() == {"old": 1, "absent": 1, "committed": 0, "unknown": 5}[mode]
    out = capsys.readouterr().out
    assert ("new package installed" if mode == "committed" else "unresolved" if mode == "unknown" else "unchanged") in out
    assert f.events.count(("POST", CHECK)) == (2 if mode == "committed" else 1)


@pytest.mark.parametrize("answer", [None, (502, {})])
def test_check_config_unreachable_or_timeout_rolls_back(monkeypatch, tmp_path, answer):
    f = Remote(load(), monkeypatch, tmp_path)
    f.checks[1] = answer
    assert f.deploy() == 4 and f.remote[LIVE] == b"old\n"


@pytest.mark.parametrize("existing", [True, False])
def test_rollback_failure(monkeypatch, tmp_path, capsys, existing):
    f = Remote(load(), monkeypatch, tmp_path)
    if not existing:
        del f.remote[LIVE]
    f.checks[1] = (200, {"result": "invalid"})
    def fail_rollback(e):
        if not f.checks and e[0] in ("rename", "del"):
            f.fail()
    f.hook = fail_rollback
    assert f.deploy() == 5
    out = capsys.readouterr().out
    assert ("rollback failed; restore from " + BACKUP if existing else "rollback failed; delete " + LIVE + " by hand") in out
    assert "restart" not in out


@pytest.mark.parametrize("retire", [False, True])
def test_dry_run_deploy_and_retire(monkeypatch, tmp_path, capsys, retire):
    f = Remote(load(), monkeypatch, tmp_path)
    f.m.HA_ENV.unlink()
    f.m.SAMBA_ENV.unlink()
    assert (f.m.main(["--retire-automations", "--dry-run"]) if retire else f.deploy("--dry-run")) == 0
    assert not f.calls
    out = capsys.readouterr().out
    assert all(API + i in out for i in f.m.SAMUEL) if retire else LIVE in out


def test_retire_deletes_exactly_four_then_verifies(monkeypatch, tmp_path):
    f = Remote(load(), monkeypatch, tmp_path)
    assert f.retire() == 0
    paths = [API + i for i in f.m.SAMUEL]
    assert f.events == [("GET", "/api/")] + [("GET", p) for p in paths] + [
        ("DELETE", p) for p in paths] + [("GET", p) for p in paths]


def test_retire_404_reported_already_removed(monkeypatch, tmp_path, capsys):
    f = Remote(load(), monkeypatch, tmp_path)
    i = f.m.SAMUEL[0]
    del f.automations[i]
    assert f.retire() == 0
    assert ("DELETE", API + i) not in f.events
    assert i + " already removed" in capsys.readouterr().out


@pytest.mark.parametrize("mode", ["drift", "status", "transport"])
def test_retire_refuses_drift_or_bad_status(monkeypatch, tmp_path, capsys, mode):
    f = Remote(load(), monkeypatch, tmp_path)
    i = f.m.SAMUEL[-1]
    f.responses[("GET", API + i)] = {
        "drift": (200, {}), "status": (500, {}), "transport": None}[mode]
    assert f.retire() == 1
    assert not any(op == "DELETE" for op, _ in f.events)
    expected = i + " differs from deploy/" + i + ".retired.json; nothing deleted" if mode == "drift" else "GET " + i + " failed"
    assert expected in capsys.readouterr().out.splitlines()


@pytest.mark.parametrize("mode", ["present", "transport"])
def test_retire_delete_or_final_get_fails(monkeypatch, tmp_path, capsys, mode):
    f = Remote(load(), monkeypatch, tmp_path)
    i = f.m.SAMUEL[1]
    if mode == "transport":
        f.responses[("DELETE", API + i)] = None
    else:
        f.responses[("GET", API + i)] = (200, f.exports[i])
    assert f.retire() == 1
    out = capsys.readouterr().out
    if mode == "transport":
        assert "DELETE " + i + " no reply; run --verify-retired" in out
        assert ("DELETE", API + f.m.SAMUEL[2]) not in f.events
    else:
        assert i + " still present" in out


@pytest.mark.parametrize("mode", ["absent", "empty", "wrong"])
def test_retire_refuses_missing_or_bad_export(monkeypatch, tmp_path, mode):
    f = Remote(load(), monkeypatch, tmp_path)
    path = f.m.DEPLOY_DIR / (f.m.SAMUEL[-1] + ".retired.json")
    if mode == "absent":
        path.unlink()
    else:
        path.write_text("" if mode == "empty" else '{"id": "different"}')
    assert f.retire() == 1 and not f.calls


@pytest.mark.parametrize("mode", ["gone", "present", "transport", "status"])
def test_verify_retired_is_read_only(monkeypatch, tmp_path, capsys, mode):
    f = Remote(load(), monkeypatch, tmp_path)
    f.automations.clear()
    if mode != "gone":
        f.responses[("GET", API + f.m.SAMUEL[0])] = {"transport": None, "present": (200, {}), "status": (500, {})}[mode]
    assert f.m.main(["--verify-retired"]) == (0 if mode == "gone" else 1)
    assert len(f.events) == 4 and all(op == "GET" for op, _ in f.events)
    i = f.m.SAMUEL[0]
    expected = {"gone": i + " gone", "present": i + " still present", "transport": "GET " + i + " failed", "status": "GET " + i + " failed (status 500)"}[mode]
    assert expected in capsys.readouterr().out.splitlines()


def test_credentials_never_in_argv_or_output(monkeypatch, tmp_path, capsys):
    f = Remote(load(), monkeypatch, tmp_path)
    assert f.deploy() == 0 and f.retire() == 0
    out = capsys.readouterr()
    for value in f.values.values():
        assert value not in str(f.calls) + out.out + out.err
    assert all("-A" in a and "-U" not in a for a in f.calls if a[0] == "smbclient")
    assert f.private and all(mode == 0o600 and not path.exists() for path, mode, _ in f.private)


@pytest.mark.parametrize("proxy", [False, True])
def test_curl_ignores_ambient_config(monkeypatch, tmp_path, proxy):
    f = Remote(load(), monkeypatch, tmp_path)
    if proxy:
        for key in ("http_proxy", "HTTPS_PROXY", "ALL_PROXY"):
            monkeypatch.setenv(key, "http://proxy.invalid")
    assert f.deploy() == 0
    assert all(a[1:4] == ["-q", "--noproxy", "*"] for a in f.calls if a[0] == "curl")


@pytest.mark.parametrize("config", [b"homeassistant: {}", b"homeassistant: {}\n\npackages: !include_dir_named packages\n"])
def test_packages_not_enabled_stops(monkeypatch, tmp_path, config):
    f = Remote(load(), monkeypatch, tmp_path)
    f.remote["configuration.yaml"] = config
    assert f.deploy() == 3 and not any(op == "put" for op, _ in f.events)


@pytest.mark.parametrize("valid", [True, False])
def test_hass_server_env_override(monkeypatch, tmp_path, valid):
    f = Remote(load(), monkeypatch, tmp_path)
    server = "http://" + "100." + "116.73.57:8123" if valid else "http://ha.local:8123"
    monkeypatch.setenv("HASS_SERVER", server)
    assert f.deploy() == (0 if valid else 1)
    if valid:
        assert all(a[a.index("-X") + 2].startswith(server + "/") for a in f.calls if a[0] == "curl")
    else:
        assert not f.calls


def test_process_hass_token_ignored(monkeypatch, tmp_path, capsys):
    f = Remote(load(), monkeypatch, tmp_path)
    del f.ha["HASS_TOKEN"]
    f.write_env()
    value = os.urandom(24).hex()
    monkeypatch.setenv("HASS_TOKEN", value)
    assert f.deploy() == 1 and not f.calls
    out = capsys.readouterr()
    assert value not in out.out + out.err
    assert all(value.encode() not in p.read_bytes() for p in tmp_path.rglob("*") if p.is_file())


def test_source_change_after_validation_not_uploaded(monkeypatch, tmp_path):
    f = Remote(load(), monkeypatch, tmp_path)
    f.hook = lambda e: f.package.write_bytes(b"alt\n") if e == ("GET", "/api/") else None
    assert f.deploy() == 0 and f.remote[LIVE] == b"new\n"


def test_rollback_staging_corruption(monkeypatch, tmp_path, capsys):
    f = Remote(load(), monkeypatch, tmp_path)
    f.checks[1] = (200, {"result": "invalid"})
    def corrupt(e):
        if not f.checks and e == ("get", LIVE + ".new"):
            f.remote[LIVE + ".new"] = b"bad\n"
    f.hook = corrupt
    assert f.deploy() == 5
    assert f.events.count(("rename", LIVE + ".new")) == 1
    out = capsys.readouterr().out
    assert "rollback failed; restore from " + BACKUP in out and "rolled back" not in out and "restart" not in out


def test_env_unquoted_password_preserves_hash(monkeypatch, tmp_path):
    f = Remote(load(), monkeypatch, tmp_path)
    password = os.urandom(24).hex() + "#" + os.urandom(24).hex()
    f.m.SAMBA_ENV.write_text(
        "".join(f"{k}={shlex.quote(v)}\n"
                for k, v in f.samba.items() if k != "SMB_PASS") + "SMB_PASS=" + password + "\n")
    assert f.deploy() == 0
    auth = [text for path, _, text in f.private if path.name == "auth"]
    assert auth and all("password = " + password in text.splitlines() for text in auth)


@pytest.mark.parametrize("server", [
    "https://ha.example#fragment", "https://ha.example?query",
    "https://user@ha.example", "https://ha.example/path",
    "https://ha.example//", "https://ha.example/#fragment",
])
def test_server_rejects_non_authority_urls(monkeypatch, tmp_path, server):
    f = Remote(load(), monkeypatch, tmp_path)
    f.ha["HASS_SERVER"] = server
    f.write_env()
    assert f.deploy() == 1 and not f.calls
