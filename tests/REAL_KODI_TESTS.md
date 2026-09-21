# Real-KODI Test Commands

Manual test commands against real KODI servers. Run with the installed tool
(`aiplayer`, after `uv tool install .`) or `uv run aiplayer` from the repo root.

Two example boxes are used below (replace hosts/credentials with your own):

| Box   | Address              | Protocol | Auth         | Catch-up                                        |
|-------|----------------------|----------|--------------|-------------------------------------------------|
| Box A | kodi-tcp.local:9090  | TCP      | none         | PVR broadcastid rejected (-32602) -> **auto m3u fallback** (see below) |
| Box B | <KODI_IP>:8080       | HTTP     | kodi/<pass>  | YES (broadcastid)                               |

Box A gets its IP from DHCP, so use an mDNS name (`kodi-tcp.local`) instead of
the IP; Box B has no mDNS name, so use its IP (`<KODI_IP>`, or give it a DHCP
reservation).

TCP does **not** require `--username` / `--password`.
KODI under test: v21.3, JSON-RPC API 13.5.

Defaults (host/port/credentials) can be stored in
`~/.config/aiplayer/config.json` (`kodi` section) so the commands below
work without `--host`/`--port`.

## Connection check / auto-discovery

```
aiplayer --host kodi-tcp.local --port 9090 --protocol tcp tv
aiplayer search                 # discovery only: list discoverable instances
aiplayer search --json          # same, JSON array (exit 0 if any found, else 1)
aiplayer --auto status          # SSDP/mDNS discovery, slow (~5s), then status
```

Expected: `Mode: KODI (kodi-tcp.local:9090)` + channel list. `search` only
lists instances and does not connect.

Note: boxes that do not advertise SSDP/mDNS (e.g. some Android TV boxes) will
not appear; use `kodi.host`/`--host` for those.

## Movie Search

```
# Ordinal - Chinese / 第N部 / Arabic / none (all 3 Avatars)
aiplayer --host kodi-tcp.local --port 9090 movie "阿凡达三" --debug
aiplayer --host kodi-tcp.local --port 9090 movie "阿凡达第三部" --debug
aiplayer --host kodi-tcp.local --port 9090 movie "阿凡达 2" --debug
aiplayer --host kodi-tcp.local --port 9090 movie "阿凡达" --debug
```

Expected: KODI returns `result: "OK"` and the right Avatar file plays.

Multi-language: Chinese queries find English-named files and vice versa
via Douban alias expansion (needs network; silently skipped offline).

## Music Search (artist / album / song)

```
aiplayer --host kodi-tcp.local --port 9090 music --artist "赵传" --debug
aiplayer --host kodi-tcp.local --port 9090 music --artist "赵传" --album "我是一只小小鸟" --debug
```

The `--song` form matches files named with the song title. Track-numbered
files (`01.mp3`) have nothing to match - navigate by album instead.

## TV Episode Search

```
aiplayer --host kodi-tcp.local --port 9090 tv "黑暗物质第三季第四集" --debug
aiplayer --host kodi-tcp.local --port 9090 tv "黑暗物质 S03E04" --debug
aiplayer --host kodi-tcp.local --port 9090 tv "黑暗物质 3x04" --debug
```

Expected output (verified):

```
[debug] Searched 'video' (nfs://server/Public/video/): 1 candidate match(es)
Playing from video: Dark Matter / Season 3 / 黑暗物质.Dark.Matter.S03E04.720p...
{"id": 164, "jsonrpc": "2.0", "result": "OK"}
```

## PVR Live TV + Channels

```
aiplayer --host kodi-tcp.local --port 9090 tv
aiplayer --host kodi-tcp.local --port 9090 tv "湖南卫视"
```

Expected: prints `Found channel`, current program, and KODI tunes in.
Same works on Box B with `--protocol http --username kodi --password <pass>`.

## PVR Catch-up

The user's IPTV m3u mixes two placeholder families channel-by-channel:
- Legacy strftime: `${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}`
- VLC shorthand: `{utc:YmdHMS}-{utcend:YmdHMS}`

`m3u_catchup.py` supports four families (KODI native seconds/strings,
iptvsimple strftime, VLC shorthand).

### Mode 1: broadcastid (Box B only)

```
aiplayer --host <KODI_IP> --port 8080 --protocol http --username kodi --password <pass> \
    catchup "湖南卫视" --date yesterday --time 18:30
```

Verified: KODI returns `result: "OK"`; PVR client builds the URL from the m3u.

### Mode 1b: automatic fallback (Box A)

On Box A, `Player.Open({broadcastid})` returns -32602. Without `--m3u`,
`catchup` now detects that and automatically rebuilds the URL from the
configured `iptv.m3u` + XMLTV (config `iptv.epg` or the m3u `x-tvg-url`):

```
aiplayer --host kodi-tcp.local --port 9090 catchup "CCTV-1综合" --date yesterday --time 21:00
# -> PVR catch-up via broadcastid failed: {'code': -32602, ...}
# -> falling back to m3u/XMLTV catch-up patch...
# -> Catchup URL: ...
```

If no m3u is configured it fails loudly (no more silent success). This is
covered offline by `tests/test_tv_patch.py` (broadcastid-rejected mock).
Note: the fallback needs an EPG source; `iptv.m3u`'s `x-tvg-url` or
`iptv.epg`/`--epg` must resolve.

### Mode 2: self-built URL (`--m3u`, works on both boxes)

Parse the m3u ourselves, substitute the channel's `catchup-source`
template, and `Player.Open({file: <url>})`. Bypasses the PVR client
entirely. Still useful to force a specific m3u, or when XMLTV comes from a
source other than the configured one.

`--m3u` accepts an http(s) URL **or** a local file path (default from
config `iptv.m3u`):

```
# URL
aiplayer --host kodi-tcp.local --port 9090 catchup "湖南卫视" \
    --date yesterday --time 18:30 \
    --m3u "http://iptv.example/iptv/iptv-10.m3u"

# Local file (m3u must be readable from this machine)
aiplayer --host kodi-tcp.local --port 9090 catchup "湖南卫视" \
    --date yesterday --time 18:30 --m3u "G:\Public\iptv.m3u"
```

EPG XMLTV resolution order: `--epg` > config `iptv.epg` > m3u
`x-tvg-url`. Override with `--epg` when the m3u carries no `x-tvg-url`:

```
aiplayer --host kodi-tcp.local --port 9090 catchup "湖南卫视" \
    --date yesterday --time 18:30 \
    --m3u "http://iptv.example/iptv/iptv-10.m3u" \
    --epg "http://iptv.example/iptv/iptv-epg.xml.gz"
```

Verified on Box A (2026-06-08): 湖南卫视 yesterday 18:30 → URL
`rtsp://<STREAM_IP>/.../...smil?playseek=20260607180000-20260607183000`
→ KODI `Player.Open` result "OK", `Player.GetItem` shows the same URL.

## Queue / files

```
aiplayer --host kodi-tcp.local --port 9090 playfile  "<url-or-path>"
aiplayer --host kodi-tcp.local --port 9090 playfiles "<url1>" "<url2>"   # replace queue
aiplayer --host kodi-tcp.local --port 9090 append    "<url-or-path>"     # add one
aiplayer --host kodi-tcp.local --port 9090 list                          # numbered queue
aiplayer --host kodi-tcp.local --port 9090 remove    "<url-or-path>"     # drop one by path
```

`list` prints `▶` on the playing entry. `remove` matches the full path first,
then falls back to basename/title (since `list` only shows basenames). Works
on local mpv too (no `--host`).

## Discovery

`search` discovers KODI over SSDP/mDNS and lists instances (probing both
HTTP (8080) and TCP (9090, raw JSON-RPC)) without connecting:

```
aiplayer search
aiplayer search --json
```

`--auto` with an action discovers first, then runs the action (falls back
to local mpv when nothing is found). `--local`/`--auto`/`--host` are
mutually exclusive - combining them is a command-line error (exit 2). With
several discovered instances, `--auto` picks the one matching the
**configured** `kodi.host` (or fails listing the choices); `--host` connects
to a specific box directly without discovering:

```
aiplayer --auto status
aiplayer --host kodi-tcp.local status
```

## Automated checks

Read-only smoke (no playback): `python tests/test_e2e_real_kodi.py --box tcp`
(or `--box http`). Playback checks for tv/catchup/queue:
`python tests/real_playback_check.py --box tcp` (also `--box http` /
`--box local`) - this one tunes and mutates the queue, so run it deliberately.

## Playback Control

```
aiplayer --host kodi-tcp.local --port 9090 pause
aiplayer --host kodi-tcp.local --port 9090 play
aiplayer --host kodi-tcp.local --port 9090 next
aiplayer --host kodi-tcp.local --port 9090 prev
aiplayer --host kodi-tcp.local --port 9090 stop
aiplayer --host kodi-tcp.local --port 9090 status
aiplayer --host kodi-tcp.local --port 9090 volume_up
aiplayer --host kodi-tcp.local --port 9090 volume_down
aiplayer --host kodi-tcp.local --port 9090 mute
```

Control commands act on whichever mode the *last play command* used -
pass the same `--host`/`--auto` flags (or none for default local mode).

## EPG Browsing

```
aiplayer --host kodi-tcp.local --port 9090 epg "湖南卫视" --date today
aiplayer epg "湖南卫视" --m3u "http://iptv.example/iptv/iptv-10.m3u" --date yesterday
```

## When something breaks

The old `diag_*.py` probes were archived to `tests/archive/` (they use
outdated CLI flags). For raw responses, use the current CLI with
`--debug`, or write a quick probe against `KodiAPI` directly.