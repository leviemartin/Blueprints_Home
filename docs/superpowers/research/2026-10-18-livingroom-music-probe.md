# Livingroom music live probe

## Source

Run by the orchestrator on 2026-10-18, about 21:30–21:45 Amsterdam time, through Home Assistant and the Sonos connector. Each live write had Martin's OK: snapshot of both Ones and Lazy Sunday play with replace and shuffle; second snapshot immediately after the read; Pairilijst play with replace and shuffle; restore; pause then play; final pause. Martin started Spotify from his phone for the phone-session step.
Martin approved the loss of the start queue.
Restoration re-applied the start-state readings as far as possible: group and volume 0.12 already matched, and both Ones were paused again. The original paused Spotify Connect session could not be replayed; the end state differed. Sonos keeps one snapshot per speaker: snapshot-2 replaced snapshot-1, so restoring that snapshot could only attempt the Lazy Sunday state, not the start state.

## Entities

| Role | entity_id | present |
|---|---|---|
| Living Room One | media_player.sonos | yes |
| Bedroom One | media_player.bedroom | yes |
| Music Remote button 1 | event.kitchen_button_1 | yes |
| Music Remote button 2 | event.kitchen_button_2 | yes |
| Music Remote button 3 | event.kitchen_button_3 | yes |
| Music Remote button 4 | event.kitchen_button_4 | yes |
| Presence FP2 zone 1 | binary_sensor.presence_sensor_fp2_e863_presence_sensor_1 | yes |
| Presence FP300 couch | binary_sensor.living_room_main_fp300_couch_occupancy_sensor | yes |
| LG TV | media_player.lg_webos_tv_oled65c9pla | yes |
| Marantz | media_player.marantz_cinema_50 | yes |
| MXN10 | media_player.mxn10 | yes |
| House alarm | alarm_control_panel.house_alarm | yes |
| Bedroom Sonos-app alarm | switch.sonos_alarm_1 | yes |
| Savannah push target | notify.mobile_app_savannah_s25_ultra | yes |

Read-only inventory at 17:20 Amsterdam: TV on with source HDMI 2, Marantz on, MXN10 off, house alarm disarmed, both presence sensors on. Savannah's notify target was present.

## Probe results

| # | step | result |
|---|---|---|
| 1 | start-state | ok: state paused, volume_level 0.12, source Spotify Connect, media_content_id x-sonos-vli:RINCON_...:2,spotify:..., group_members media_player.bedroom and media_player.sonos, queue_size 1, media_title You've Got a Friend in Me, media_artist Randy Newman, media_playlist none, favorites sonos FV:2/3 and Sonos play FV:2/2 (both Ones identical; no favorite for either playlist) |
| 2 | snapshot-1 | ok: sonos.snapshot on both Ones with_group true, no error |
| 3 | play-lazy-sunday | ok: play_media spotify:playlist:37i9dQZF1DWTc452KG008d with enqueue replace, then shuffle_set true, no error |
| 4 | read-lazy-sunday | ok: state playing, queue_size 80, media_playlist empty, shuffle true, source none (attribute absent), media_content_id x-sonos-spotify:spotify%3atrack%3a..., media_title Slow Hands, media_artist Niall Horan, media_position 88.3 (effective, after update_entity) |
| 5 | snapshot-2 | ok: sonos.snapshot on both Ones with_group true right after the read, no error |
| 6 | play-pairilijst | ok: play_media spotify:playlist:4IzLPBPewQ4PCOF3qMYgDT with enqueue replace, then shuffle_set true, no error |
| 7 | read-pairilijst | ok: state playing, queue_size 52, media_playlist empty, shuffle true, source none (attribute absent), media_content_id x-sonos-spotify:spotify%3atrack%3a..., media_title Come Alive, media_artist Hugh Jackman, media_position 8.3 (effective) |
| 8 | restore | ok: sonos.restore on both Ones with_group true, no error |
| 9 | restore-check | FAILED: the position came back but not the track or queue: media_title Come Alive (expected Slow Hands), media_position 97.4 (effective), queue_size 52 (expected 80), so Lazy Sunday did not resume |
| 10 | pause-play | ok: queue_size 52 before and after, media_playlist empty before and after, same track Come Alive, paused then playing again |
| 11 | favorite-fallback | not run: no UPnP 800 or 714 |
| 12 | phone-session | ok: Martin started Spotify on his phone; source Spotify Connect, media_content_id x-sonos-vli:RINCON_...:2,spotify:..., queue_size 1, media_playlist Liked Songs |
| 13 | restore-start-state | FAILED: re-applied start-state readings; end state differed: media_title, media_artist, media_playlist, media_content_id (the queue was replaced and the paused start session cannot be replayed; group_members, volume_level 0.12 and the paused state matched) |

Snapshot or restore failed: card 2026-10-18-livingroom-music-remote-kids uses the fresh-reload fallback.

Effective positions were compared: 88.3 s before snapshot-2 and 97.4 s after restore (9.1 s apart). The raw restored position was 89 s, applied to the Pairilijst queue. Snapshot did not preserve the Lazy Sunday queue. Pause/play did preserve the current queue.
Playlist plays returned an empty media_playlist and an x-sonos-spotify track id, so the playlist cannot be identified from those attributes; card 3 must keep its own owner helper.

## Phone session attributes

| attribute | value |
|---|---|
| source | Spotify Connect |
| media_content_id | x-sonos-vli:RINCON_...:2,spotify:... |
| queue_size | 1 |
| media_playlist | Liked Songs |
| state | playing |

Detection rule: confirmed.

The phone playlist name was available in media_playlist for this Connect session.

## Remote event types

| entity_id | event_types |
|---|---|
| event.kitchen_button_1 | initial_press, repeat, short_release, long_press, long_release |
| event.kitchen_button_2 | initial_press, repeat, short_release, long_press, long_release |
| event.kitchen_button_3 | initial_press, repeat, short_release, long_press, long_release |
| event.kitchen_button_4 | initial_press, repeat, short_release, long_press, long_release |

## Overlap matrix

| Automation | id | state | shared entities |
|---|---|---|---|
| Sonos On Samuel | 1701294514096 | on | Music Remote button 1 press; plays favorite FV:2/3 on media_player.living_room, which does not exist, so this button does nothing today (conflict, no change) |
| Sonos 20% Volume Samuel | 1701295072034 | on | Music Remote button 2 press; volume_set 0.25 on both Sonos devices |
| Sonos 10% Volume Samuel | 1701295128408 | on | Music Remote button 3 press; volume_set 0.15 on both Sonos devices |
| Sonos Off Samuel | 1701294978959 | on | Music Remote button 4 press; media_stop on both Sonos devices |

## Outside-HA controls

| control | finding |
|---|---|
| switch.sonos_alarm_1 | state off; Bedroom Weekdays alarm 08:25, duration 1 hour, volume 0.1, shuffle, weekdays only; currently disabled |
| Bedroom One area | media_player.bedroom is in area Bedroom; media_player.sonos is in area Living Room |
| Hue-app button assignments | not visible from HA; only the four Samuel automations and the event entities show; needs Martin to confirm there are none in the Hue app |
| Phone Spotify Connect | confirmed: source Spotify Connect and media_content_id starting x-sonos-vli: |

## Open questions

- Start queue lost (queue): the paused Spotify Connect session (You've Got a Friend in Me, 1 track) was replaced by the probe, with Martin's OK.
- Samuel On automation 1701294514096 targets media_player.living_room, which does not exist, so the remote On button does nothing today; no change here.
- Hue-app button assignments for the Music Remote cannot be read from HA; Martin to confirm there are none.
- The Music Remote battery sensor reads 15 percent.

Conclusion: direct playlist play and phone detection worked; snapshot restore lost the Lazy Sunday queue, requiring the fresh-reload fallback and an owner helper; the original paused session could not be restored.
