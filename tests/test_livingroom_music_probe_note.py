"""Pin the livingroom probe note without live access."""
import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NOTE = ROOT / "docs/superpowers/research/2026-10-18-livingroom-music-probe.md"
SECTIONS = [
    "Source", "Entities", "Probe results", "Phone session attributes",
    "Remote event types", "Overlap matrix", "Outside-HA controls", "Open questions",
]
ENTITY_IDS = [
    "media_player.sonos", "media_player.bedroom",
    *[f"event.kitchen_button_{n}" for n in range(1, 5)],
    "binary_sensor.presence_sensor_fp2_e863_presence_sensor_1",
    "binary_sensor.living_room_main_fp300_couch_occupancy_sensor",
    "media_player.lg_webos_tv_oled65c9pla", "media_player.marantz_cinema_50",
    "media_player.mxn10", "alarm_control_panel.house_alarm", "switch.sonos_alarm_1",
    "notify.mobile_app_savannah_s25_ultra",
]
PLAYLISTS = ["spotify:playlist:37i9dQZF1DWTc452KG008d", "spotify:playlist:4IzLPBPewQ4PCOF3qMYgDT"]
SAMUEL_IDS = ["1701294514096", "1701295072034", "1701295128408", "1701294978959"]
STEP_IDS = [
    "start-state", "snapshot-1", "play-lazy-sunday", "read-lazy-sunday",
    "snapshot-2", "play-pairilijst", "read-pairilijst", "restore",
    "restore-check", "pause-play", "favorite-fallback", "phone-session",
    "restore-start-state",
]
CONTROLS = ["switch.sonos_alarm_1", "Bedroom One area", "Hue-app button assignments"]
FALLBACK_LINE = (
    "Snapshot or restore failed: card 2026-10-18-livingroom-music-remote-kids "
    "uses the fresh-reload fallback."
)
RESULT_RE = re.compile(r"^(ok|FAILED|not run): \S")
CREDENTIAL_PATTERNS = [
    r"eyJ[A-Za-z0-9_-]{8,}", r"(?i)bearer\s", r"(?i)https?://", r"\b\d{1,3}(\.\d{1,3}){3}\b",
    r"HASS_(TOKEN|SERVER)\s*=", r"(?i)\b(password|api[_-]?key)\b",
]
GATE_SENTENCES = {
    "approved": "Martin approved the loss of the start queue.",
    "declined": "Martin did not approve the loss of the start queue.",
    "unknown": "The start queue state could not be read; the gated steps were not run.",
}
SKIP = {
    "declined": "not run: queue-loss not approved",
    "unknown": "not run: queue state unknown",
}
START = (
    "ok: state paused, volume_level 0.15, source Sonos, media_content_id none, "
    "queue_size 0, media_title none, media_artist none, media_playlist none"
)
RESTORE_FORMS = [
    "ok: re-applied start-state readings; end state matched start-state",
    "FAILED: re-applied start-state readings; end state differed: volume_level",
    "FAILED: unjoin; end state differed: group_members",
]


def section(text, heading):
    marker = "## " + heading
    assert text.splitlines().count(marker) == 1, heading
    body = text.splitlines()[text.splitlines().index(marker) + 1:]
    return body[:next((i for i, line in enumerate(body)
                       if line.startswith(("## ", "Conclusion:"))), len(body))]


def rows(lines):
    parsed = []
    for line in lines:
        if not line.startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r"[-: ]+", cell) for cell in cells):
            continue
        assert all(cells), line
        parsed.append(cells)
    assert parsed
    header, *data = parsed
    assert all(len(row) == len(header) for row in data)
    return header, data


def table(text, heading, header):
    actual, data = rows(section(text, heading))
    assert actual == header
    return data


def probes(text):
    data = table(text, "Probe results", ["#", "step", "result"])
    assert [row[1] for row in data] == STEP_IDS
    return {row[1]: row[2] for row in data}


def gate(text):
    p = probes(text)
    if not p["start-state"].startswith("ok:"):
        return "unknown"
    match = re.search(r"\bqueue_size (unknown|\d+)(?=,|;|$|\s)", p["start-state"])
    assert match, "start queue size missing"
    if match[1] == "unknown":
        return "unknown"
    if int(match[1]) == 0:
        return "empty"
    return "declined" if p["play-lazy-sunday"].startswith(SKIP["declined"]) else "approved"


def check_sections(text):
    assert text.splitlines() and text.splitlines()[0] == "# Livingroom music live probe"
    assert re.findall(r"^## (.+)$", text, re.M) == SECTIONS


def check_entities(text):
    data = table(text, "Entities", ["Role", "entity_id", "present"])
    assert sorted(row[1] for row in data) == sorted(ENTITY_IDS)
    assert all(row[2] in {"yes", "no"} for row in data)


def whole_id(entity):
    return r"(?<![\w.])" + re.escape(entity) + r"(?!\w)(?!\.\w)"


def check_absent_named(text):
    questions = "\n".join(section(text, "Open questions"))
    for _, entity, present in table(text, "Entities", ["Role", "entity_id", "present"]):
        if present == "no":
            assert re.search(whole_id(entity), questions), entity


def check_playlists(text):
    assert all(uri in text for uri in PLAYLISTS)


def check_steps(text):
    data = table(text, "Probe results", ["#", "step", "result"])
    assert [row[1] for row in data] == STEP_IDS
    assert [row[0] for row in data] == [str(n) for n in range(1, 14)]


def check_results(text):
    p = probes(text)
    assert all(RESULT_RE.match(result) for result in p.values())
    required = {
        "start-state": "queue_size media_title media_artist media_playlist media_content_id",
        "read-lazy-sunday": "queue_size media_playlist shuffle source media_content_id media_title media_position",
        "read-pairilijst": "queue_size media_playlist shuffle source media_content_id",
        "restore-check": "media_title media_position",
        "pause-play": "queue_size media_playlist",
    }
    for step, names in required.items():
        if p[step].startswith("ok:"):
            assert all(re.search(r"\b" + name + r" \S", p[step]) for name in names.split())
    mode = gate(text)
    questions = section(text, "Open questions")
    queue_question = any(line.startswith("- ") and "queue" in line.lower() for line in questions)
    end = p["restore-start-state"]
    if mode in SKIP:
        assert all(p[step].startswith(SKIP[mode]) for step in STEP_IDS[2:])
        assert queue_question
    else:
        assert (end.startswith(RESTORE_FORMS[0])
                or re.match(r"^FAILED: .+; end state differed: \S", end))
        replaced = any(p[step].startswith("ok:") or "played in place via FV:" in p[step]
                       for step in ("play-lazy-sunday", "play-pairilijst"))
        if mode == "approved" and replaced:
            assert end.startswith("FAILED:") and "queue" in end.lower()
            assert queue_question


def check_source(text):
    source = "\n".join(section(text, "Source"))
    assert "orchestrator" in source and "2026-10-18" in source
    assert "Martin's OK" in source
    assert "snapshot-2" in source and "snapshot-1" in source
    assert "start-state readings" in source
    mode = gate(text)
    for name, sentence in GATE_SENTENCES.items():
        assert source.count(sentence) == int(mode == name)
    end = probes(text)["restore-start-state"]
    assert source.count("end state matched start-state") == int(end.startswith("ok:"))
    assert source.count("end state differed") == int(end.startswith("FAILED:"))


def check_fallback(text):
    p = probes(text)
    needed = any(not p[step].startswith("ok:")
                 for step in ("snapshot-1", "snapshot-2", "restore", "restore-check"))
    assert text.count(FALLBACK_LINE) == int(needed)
    assert section(text, "Probe results").count(FALLBACK_LINE) == int(needed)


def check_favorite(text):
    p = probes(text)
    triggered = [(step, uri) for step, uri in zip(
        ("play-lazy-sunday", "play-pairilijst"), PLAYLISTS)
        if p[step].startswith("FAILED:") and re.search(r"\bUPnP (Error )?(800|714)\b", p[step])]
    fallback = p["favorite-fallback"]
    if not triggered:
        expected = SKIP.get(gate(text), "not run: no UPnP 800 or 714")
        assert fallback.startswith(expected)
    else:
        assert fallback.startswith(("ok:", "FAILED:"))
        questions = "\n".join(section(text, "Open questions"))
        for step, uri in triggered:
            match = re.search(r"; played in place via (FV:[\w/-]+)", p[step])
            if match:
                assert match[1] in fallback
            else:
                missing = "no favorite for " + uri
                assert "; " + missing in p[step] and missing in fallback
                assert any(line.startswith("- ") and uri in line for line in questions.splitlines())


def check_phone(text):
    data = table(text, "Phone session attributes", ["attribute", "value"])
    assert len({row[0] for row in data}) == len(data)
    attrs = dict(data)
    assert {"source", "media_content_id"} <= attrs.keys()
    confirmed = (probes(text)["phone-session"].startswith("ok:")
                 and attrs["source"] == "Spotify Connect"
                 and attrs["media_content_id"].startswith("x-sonos-vli:"))
    expected = "Detection rule: " + ("confirmed." if confirmed else "not confirmed.")
    lines = [line for line in text.splitlines() if line.startswith("Detection rule:")]
    assert lines == [expected]
    assert expected in section(text, "Phone session attributes")


def check_remote(text):
    data = table(text, "Remote event types", ["entity_id", "event_types"])
    assert sorted(row[0] for row in data) == [f"event.kitchen_button_{n}" for n in range(1, 5)]


def check_overlap(text):
    data = table(text, "Overlap matrix", ["Automation", "id", "state", "shared entities"])
    for ident in SAMUEL_IDS:
        assert [row[1] for row in data].count(ident) == 1


def check_controls(text):
    data = table(text, "Outside-HA controls", ["control", "finding"])
    for control in CONTROLS:
        assert [row[0] for row in data].count(control) == 1


def check_open_questions(text):
    lines = [line for line in section(text, "Open questions") if line.strip()]
    assert lines == ["none"] or (lines and all(line.startswith("- ") and line[2:].strip()
                                             for line in lines))


def check_conclusion(text):
    lines = re.findall(r"^Conclusion: .+$", text, re.M)
    assert len(lines) == 1
    assert lines[0] == text.rstrip("\n").splitlines()[-1]


def check_credentials(text):
    for pattern in CREDENTIAL_PATTERNS:
        assert not re.search(pattern, text), pattern


def test_note_exists_and_not_empty():
    assert NOTE.is_file()
    assert NOTE.read_text().strip()


def test_sections_in_order():
    check_sections(NOTE.read_text())


def test_entities_table():
    check_entities(NOTE.read_text())


def test_absent_entities_under_open_questions():
    check_absent_named(NOTE.read_text())


def test_playlist_uris_recorded():
    check_playlists(NOTE.read_text())


def test_probe_steps_once_in_order():
    check_steps(NOTE.read_text())


def test_every_probe_row_has_a_result():
    check_results(NOTE.read_text())


def test_source_agrees_with_restore_start_state():
    check_source(NOTE.read_text())


def test_fallback_line_matches_snapshot_restore_results():
    check_fallback(NOTE.read_text())


def test_favorite_fallback_after_upnp_error():
    check_favorite(NOTE.read_text())


def test_phone_session_attributes():
    check_phone(NOTE.read_text())


def test_remote_event_types():
    check_remote(NOTE.read_text())


def test_overlap_matrix_has_samuel_automations():
    check_overlap(NOTE.read_text())


def test_outside_ha_controls():
    check_controls(NOTE.read_text())


def test_open_questions_form():
    check_open_questions(NOTE.read_text())


def test_conclusion_single_and_last():
    check_conclusion(NOTE.read_text())


def test_no_credentials_in_note():
    check_credentials(NOTE.read_text())


def replace_section(text, heading, body):
    old = "\n".join(section(text, heading))
    return text.replace("## " + heading + "\n" + old,
                        "## " + heading + "\n" + body, 1)


def change_row(text, heading, column, key, mutate):
    lines = section(text, heading)
    found = 0
    for i, line in enumerate(lines):
        if line.startswith("|"):
            cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
            if cells[column] == key:
                lines[i] = mutate(cells)
                found += 1
    assert found == 1, (heading, key)
    return replace_section(text, heading, "\n".join(lines))


def set_result(text, step, result):
    return change_row(text, "Probe results", 1, step,
                      lambda cells: "| " + " | ".join([*cells[:2], result]) + " |")


def queue_fixture(text, mode):
    text = set_result(text, "start-state", START.replace("queue_size 0", "queue_size " + (
        "unknown" if mode == "unknown" else "40")))
    for step in STEP_IDS[2:]:
        text = set_result(text, step, SKIP[mode])
    source = "\n".join(section(text, "Source"))
    for sentence in GATE_SENTENCES.values():
        source = source.replace(sentence, "")
    for phrase in ("end state matched start-state", "end state differed"):
        source = source.replace(phrase, "")
    text = replace_section(text, "Source", source + "\n" + GATE_SENTENCES[mode] + "\n")
    text = text.replace(FALLBACK_LINE, "")
    text = replace_section(text, "Probe results",
                           "\n".join(section(text, "Probe results")) + "\n" + FALLBACK_LINE + "\n")
    return replace_section(text, "Open questions", "- Start queue: probe not run (queue).\n")


@pytest.mark.parametrize("form", RESTORE_FORMS)
def test_check_results_accepts_each_restore_start_state_form(form):
    text = set_result(NOTE.read_text(), "start-state", START)
    check_results(set_result(text, "restore-start-state", form))


@pytest.mark.parametrize("mode", ["declined", "unknown"])
def test_skipped_note_passes(mode):
    text = queue_fixture(NOTE.read_text(), mode)
    for check in (check_results, check_favorite, check_fallback, check_source, check_open_questions):
        check(text)


def absent_with_similar_id(text):
    text = change_row(text, "Entities", 1, "media_player.sonos",
                      lambda cells: "| " + " | ".join([*cells[:2], "no"]) + " |")
    questions = re.sub(whole_id("media_player.sonos"), "", "\n".join(section(text, "Open questions")))
    questions = "\n".join(line for line in questions.splitlines() if line.strip() != "none")
    return replace_section(text, "Open questions", questions + "\n- media_player.sonos_beam is missing\n")


def approved_but_restored(text):
    text = set_result(text, "start-state", START.replace("queue_size 0", "queue_size 40"))
    text = set_result(text, "play-lazy-sunday", "ok: played")
    text = set_result(text, "restore-start-state", RESTORE_FORMS[0])
    return replace_section(text, "Open questions", "- Start queue lost (queue).\n")


def missing_gate_sentence(text):
    text = set_result(text, "start-state", START.replace("queue_size 0", "queue_size 40"))
    text = set_result(text, "play-lazy-sunday", "ok: played")
    for sentence in GATE_SENTENCES.values():
        text = text.replace(sentence, "")
    return text


def upnp_without_favorite(text, code):
    text = set_result(text, "play-lazy-sunday", "FAILED: UPnP Error " + code + " received")
    return set_result(text, "favorite-fallback", "not run: no UPnP 800 or 714")


@pytest.mark.parametrize("check,mutate", [
    (check_sections, lambda t: ""),
    (check_sections, lambda t: t.replace("## Remote event types\n", "")),
    (check_sections, lambda t: t.replace("## Entities", "## TEMP").replace(
        "## Probe results", "## Entities").replace("## TEMP", "## Probe results")),
    (check_entities, lambda t: change_row(t, "Entities", 1, "media_player.bedroom", lambda c: "")),
    (check_entities, lambda t: change_row(t, "Entities", 1, "media_player.sonos",
                                        lambda c: "| " + " | ".join([*c[:2], "maybe"]) + " |")),
    (check_absent_named, absent_with_similar_id),
    (check_open_questions, lambda t: replace_section(t, "Open questions", "- A question.\nSee above.\n")),
    (check_playlists, lambda t: t.replace(PLAYLISTS[0], "spotify:playlist:x").replace(
        PLAYLISTS[1], "spotify:playlist:x")),
    (check_steps, lambda t: change_row(t, "Probe results", 1, "pause-play",
                                     lambda c: ("| " + " | ".join(c) + " |\n") * 2)),
    (check_steps, lambda t: change_row(t, "Probe results", 1, "pause-play", lambda c: "")),
    (check_results, lambda t: set_result(t, "restore-start-state", "TBD")),
    (check_results, lambda t: set_result(t, "pause-play", "")),
    (check_results, approved_but_restored),
    (check_results, lambda t: set_result(queue_fixture(t, "declined"), "pause-play",
                                       "ok: queue_size 40, media_playlist C")),
    (check_source, missing_gate_sentence),
    (check_fallback, lambda t: t.replace(FALLBACK_LINE, "") if FALLBACK_LINE in t else
     replace_section(t, "Probe results", "\n".join(section(t, "Probe results")) + "\n" + FALLBACK_LINE)),
    (check_favorite, lambda t: upnp_without_favorite(t, "800")),
    (check_favorite, lambda t: upnp_without_favorite(t, "714")),
    (check_phone, lambda t: t.replace("Detection rule: confirmed.", "Detection rule: not confirmed.")
     if "Detection rule: confirmed." in t else t.replace("Detection rule: not confirmed.", "Detection rule: confirmed.")),
    (check_phone, lambda t: re.sub(r"^Detection rule: .+\n", "", t, flags=re.M)),
    (check_phone, lambda t: t + "\nDetection rule: confirmed.\n"),
    (check_overlap, lambda t: change_row(t, "Overlap matrix", 1, "1701294978959", lambda c: "")),
    (check_remote, lambda t: change_row(t, "Remote event types", 0, "event.kitchen_button_4", lambda c: "")),
    (check_controls, lambda t: change_row(t, "Outside-HA controls", 0, "Bedroom One area", lambda c: "")),
    (check_conclusion, lambda t: t + "Conclusion: another conclusion.\n"),
    (check_conclusion, lambda t: re.sub(r"^Conclusion: .+\n", "", t, flags=re.M)),
    (check_conclusion, lambda t: t + "Trailing prose.\n"),
    *[(check_credentials, lambda t, sample=sample: t + "\n" + sample) for sample in [
        "https" + "://example.invalid", "http" + "://example.invalid", "192" + ".0.2.1",
        "Bear" + "er x", "ey" + "Jabcdefghijk", "HASS" + "_TOKEN=x",
        "pass" + "word", "api" + "_key",
    ]],
])
def test_check_rejects_mutated_note(check, mutate):
    text = NOTE.read_text()
    with pytest.raises(AssertionError):
        check(mutate(text))


def test_no_credentials_or_live_access_in_this_test():
    source = Path(__file__).read_text()
    tree = ast.parse(source)
    declaration = next(node for node in tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "CREDENTIAL_PATTERNS"
                               for t in node.targets))
    scrubbed = source.replace(ast.get_source_segment(source, declaration), "", 1)
    check_credentials(scrubbed)
    for forbidden in ("hass" + "-cli", "HASS" + "_TOKEN", "." + "config/", "." + "frugo"):
        assert forbidden not in source
    blocked = {"requests", "urllib", "http", "socket", "subprocess", "aiohttp"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] not in blocked for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in blocked
