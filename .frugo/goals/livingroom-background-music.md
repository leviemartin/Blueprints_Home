---
goal: livingroom-background-music
title: Living room background music with kids remote
status: done
---

## Aim
Living-room Sonos plays background music while someone is in the room, stops for TV, an empty room or armed alarm; kids request songs and set volume from a Hue remote, loud needs parent approval

## Decisions
- Goal: Blueprints_Home, slug livingroom-background-music (Martin round 1). Users: the household; the kids use the Music Remote; Martin or Savannah approve loud.
- Build (round 2): one HA YAML package (automations, helpers, scripts), the first package in this repo; behaviour tests on the home-security HA harness (pytest-homeassistant-custom-component 0.13.372, merge_packages_config); deploy over Samba to /config/packages plus reload. Music: Sonos queue only, no Spotify, Spotcast or Music Assistant integration.
- Speakers (round 2): media_player.sonos (Living Room One) grouped with media_player.bedroom (Bedroom One). To confirm: Bedroom One area, and its Sonos-app alarm switch.sonos_alarm_1 (weekdays 08:25) plays outside HA.
- General music (round 3): Spotify-made Lazy Sunday, spotify:playlist:37i9dQZF1DWTc452KG008d, shuffled, all day, good variation of the same type; variety limited to its tracks at load time.
- Kids playlist (round 4): Pairilijst, spotify:playlist:4IzLPBPewQ4PCOF3qMYgDT (owner Martin); exactly this playlist, no other songs; shuffled and looping.
- Presence: FP2 zone 1 binary_sensor.presence_sensor_fp2_e863_presence_sensor_1 or FP300 binary_sensor.living_room_main_fp300_couch_occupancy_sensor (either-on, both-clear, as circadian instance 1767031159524). Dog ignored for now; review in the first 2 weeks (follow-up, not a gate).
- Empty room (round 5): 15 min empty then pause; resume the same track when presence returns. TV, Marantz and alarm stops pause and resume the same way (orchestrator reading, Martin can revert). TV: LG C9 media_player.lg_webos_tv_oled65c9pla on, any input, OR Marantz on any input counts as playing (read only; media_player.marantz_cinema_50). Alarm: Away and Night (arming, pending, triggered) on alarm_control_panel.house_alarm stop the music and block starts.
- Quiet hours (round 4): 22:00 to 07:30; presence does not start music; music playing stops at 22:00; before 22:00 it plays normally. Party: Hands-off toggle in the HA app, HA stops controlling the Sonos entirely, turns itself off at 06:00 next morning.
- Kids time (round 5-6): On starts 30 min of Pairilijst shuffled; HA snapshots the general music (track and position), plays Pairilijst, then restores the general music where it left off at the pre-kids volume. TV, Marantz, alarm, quiet hours, Hands-off or an empty room end kids time early: the time counts as used and the cooldown starts. Cooldown: 30 min after kids time ends (adult music); On is ignored during kids time and the cooldown. Off during kids time skips to another Pairilijst song. If the probe shows snapshot/restore fails, fallback is a fresh shuffled Lazy Sunday reload.
- Remote: brighten = volume up, dim = volume down (always, -0.05 per press, floor 0.05), Off = skip, On = kids time (when music is off, On starts general music then kids time, only if occupied, outside quiet hours, TV, Marantz and alarm allow); long press nothing.
- Volume (Martin, 2026-10-19, after listening live; supersedes start 0.15): start 0.07; free steps 0.10, 0.15 and 0.20 (the remote stops at 0.20 outside kids time); 0.25 and 0.30 only inside kids time after one approval (Approve unlocks 0.25, the next brighten gives 0.30); dim always works inside an approved kids time; approval lasts until kids time ends, then volume returns to its pre-kids level. Fixed volume_set on both Ones, ladder index in a helper, no read-modify-write on reported volume.
- Approval: actionable push to Martin (notify.mobile_app_martin_fold) and Savannah (notify.mobile_app_savannah_s25_ultra, confirm live) with Approve and Deny; first answer wins and clears the other; no answer in 2 min is Deny.
- Phone play: phone wins. Detection: Sonos source Spotify Connect and media_content_id x-sonos-vli: (June 2026 snapshot; probe confirms) plus an owner helper HA sets when it starts music. While active HA never starts, resumes or replaces music; empty room, TV, Marantz, alarm and quiet hours still pause it; remote volume works; On ignored. Ended when paused or stopped 10 min, or the Sonos leaves Spotify Connect; no resume of the phone session; the next normal start trigger loads Lazy Sunday fresh, shuffled, at 0.15.
- First card, read-and-revert live probe: play both playlist URIs on the group, read queue_size, media_playlist, shuffle, source, media_content_id; test sonos.snapshot/restore across a Pairilijst swap (does Lazy Sunday resume track and position); test pause/resume of the queue; read a phone Spotify Connect session; fallback for UPnP 800/714: play as My Sonos favorites (favorite_item_id FV:2/x).
- Martin round 5: 'adults get some music' was read as the cooldown being adult music time; confirm in the spec.
- Fact (remote): Hue RWL021 Music Remote, device dfad9901619a42507889cad7dfc9b8d9, event.kitchen_button_1..4, battery sensor.kitchen_battery_level; not the Living/Kitchen dimmer; confirm no Hue-app button assignments.
- Remove candidates (same remote): Sonos On Samuel 1701294514096 (plays missing media_player.living_room, likely failing), Sonos 20% Volume Samuel 1701295072034, Sonos 10% Volume Samuel 1701295128408, Sonos Off Samuel 1701294978959.
- Off limits: the AV chain (MXN10, Marantz, B&W, Tap Dial automations) and its LOCKED levels; never use the retired Pixel notify.
- Rules: simplest rule first; before spec approval a live REST inventory and interaction matrix over the shared entities plus outside controls (Sonos alarm, Hue-app routines, phone Spotify Connect). Times for Martin: Amsterdam.

- Martin round 7: Remove: export the four Samuel automations to deploy/*.retired.json, then delete them in the deploy card; the new map replaces all four buttons, so Off no longer stops the music (it skips); stopping is by empty room, the app or Hands-off.
- Martin round 7: Done when: harness tests for every rule (start; each pause and resume; quiet hours; Hands-off; kids time with snapshot, restore, cut-short and cooldown; volume ladder; approval first-answer-wins and 2 min Deny; phone session) plus the probe results recorded plus a short live check with Martin: walk in for music, TV on to pause and off to resume, On for Pairilijst, brighten to 0.30 for the push on both phones, then Approve.
- Martin round 7: Lane 2 for the whole goal (Opus plan, two design reviews, two code reviews); risk words alarm, deploy, production in ladder.yaml; only Martin lowers a lane. Budget: track only, default warn line 500,000 tokens per card (ladder.yaml measure mode).
- Visuals: no mock-up needed (no new UI beyond the Hands-off toggle and the approval push; orchestrator default, Martin can revert). Each approval push uses a unique action id so a stale push cannot approve later.
- Interview complete after 28 questions; next: goal sections, spec approval, cards.

## Done when
- Probe card: docs/superpowers/research/2026-10-18-livingroom-music-probe.md records, for the grouped Ones: Lazy Sunday and Pairilijst URI plays (queue_size, media_playlist, shuffle, source, media_content_id); whether sonos.snapshot and sonos.restore resume the Lazy Sunday track and position after a Pairilijst swap; whether pause and resume keep the queue; the attributes of a phone Spotify Connect session; the favorite fallback if a URI fails; the Sonos back in its prior state afterwards. The live overlap inventory and the interaction matrix are in the same file.
- env -u HASS_TOKEN ~/.local/share/home-security/ha-test-venv/bin/python -I -m pytest -q -p no:cacheprovider -c ha/tests/pytest-ha.ini ha/tests passes, covering: start (either sensor on starts Lazy Sunday shuffled at 0.15); pause and resume after 15 min both clear, LG on, Marantz on, or Away/Night (arming, pending, triggered) with resume where it left off; nothing starts during quiet hours 22:00 to 07:30 and music stops at 22:00; Hands-off blocks everything and resets at 06:00; kids time (snapshot, 30 min of Pairilijst, restore at the old volume, cut short by each stop rule, 30 min cooldown with On ignored, Off skips); volume ladder 0.05 to 0.25 and no 0.30 outside kids time or without approval; approval (first answer wins and clears the other push, Deny after 2 min, stale action id ignored); phone session (HA never replaces it, after 10 min paused or stopped the next start reloads fresh).
- The whole tests suite passes with the same interpreter.
- Live at deploy, with Martin: walk in and music starts; LG on pauses it and LG off resumes it; On starts Pairilijst; brighten to 0.30 sends the push to both phones and Approve gives 0.30.
- A final GET shows the four Samuel automations gone.

## Out of scope
- The AV chain (MXN10, Marantz Cinema 50, the B&W speakers, the Tap Dial automations) and its LOCKED levels: read only, never written.
- Spotify, Spotcast or Music Assistant integrations, the Spotify Web API, and Spotify radio or recommendations. Variety is limited to Lazy Sunday.
- Dog handling: reviewed in the first 2 weeks of use as a follow-up.
- Other Sonos (gym, Roam SL, bedroom use outside the group), the Bedroom One Sonos-app alarm, and Hue-app routines. If the overlap audit finds a conflict there, it goes to open questions, not into a fix.
- The circadian living-room lights, FP2 and FP300 settings, and the home-security package and alarm logic.
- Dashboard work beyond the Hands-off toggle helper; no mock-up.
- Loud or DND push delivery, and volume above 0.30.
- Multi-day observation as a gate.

## Remove
- Sonos On Samuel 1701294514096, Sonos 20% Volume Samuel 1701295072034, Sonos 10% Volume Samuel 1701295128408 and Sonos Off Samuel 1701294978959. All four use the Music Remote, which this package takes over. Each is exported to deploy/<id>.retired.json, then deleted in the deploy card, with a final GET showing it gone. Rollback is a re-POST of the export.
- The Off button no longer stops the music; it skips. Stopping is by empty room, the stop rules, quiet hours or Hands-off.
- The Sonos favorite FV:2/3 is kept. The play step that targeted the missing media_player.living_room goes away with its automation.
- Nothing else becomes obsolete: the circadian lights and the AV automations stay unchanged.

## Risks
- Lane 2 for the whole goal (Martin, round 7). The scan words alarm and deploy hit most cards, the approval push decides who may raise the volume, and the deploy writes live HA config and deletes automations.
- Unverified Sonos behaviour: editorial URIs (UPnP 800/714), snapshot and restore of a Spotify queue, the phone Spotify Connect attributes, and pause and resume. The probe card runs first; fallbacks are favorites and a fresh reload instead of restore.
- Loud volume: 0.30 is reachable only inside kids time with a live approval. The tests assert that no path sets more than 0.25 otherwise, and dim always works.
- Approval spoofing or stale pushes: a unique action id per request, accepted only within 2 min, first answer wins, the other push is cleared.
- HA restart during kids time or a pending approval: at start, kids time ends, the general music is restored or reloaded, and the approval is cleared. At-least-once, not exactly-once.
- A false phone-session detection could block HA music, and a missed one could replace a phone session. The probe sets the rule and the tests cover both cases.
- Overlap with the Bedroom One 08:25 Sonos alarm and Hue-app button routines: the live audit runs before spec approval.
- The dog keeps the music playing (accepted by Martin).
- Secrets: the HA token is read only by the orchestrator, never written to files or tests; tests run with env -u HASS_TOKEN.

## Budget
- Track only: ladder.yaml measure mode, warn line 500,000 tokens per card, fix budget 8,000,000 per card (Martin, round 7).
