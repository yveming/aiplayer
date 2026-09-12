# Real-KODI Test Commands

Manual test commands against the user's actual KODI servers. Run with the
installed tool (`aiplayer`, after `uv tool install .`) or `uv run aiplayer`
from the repo root.

| Box     | Address             | Protocol | Auth        | Catch-up                                          |
|---------|---------------------|----------|-------------|---------------------------------------------------|
| 11 box  | 192.168.100.11:9090 | TCP      | none        | NO via broadcastid (-32602) - use `--m3u <URL>`   |
| Sony TV | 192.168.100.43:8080 | HTTP     | kodi/hermes | YES (broadcastid)                                 |

TCP does **not** require `--username` / `--password`.
KODI under test: v21.3, JSON-RPC API 13.5.

Defaults (host/port/credentials) can be stored in
`~/.config/aiplayer/config.json` (`kodi` section) so the commands below
work without `--host`/`--port`.

## Connection check / auto-discovery

```
aiplayer --host 192.168.100.11 --port 9090 --protocol tcp tv
aiplayer --auto status          # SSDP/mDNS discovery, slow (~5s)
```

Expected: `Mode: KODI (192.168.100.11:9090)` + channel list.

## Movie Search

```
# Ordinal - Chinese / 第N部 / Arabic / none (all 3 Avatars)
aiplayer --host 192.168.100.11 --port 9090 movie "阿凡达三" --debug
aiplayer --host 192.168.100.11 --port 9090 movie "阿凡达第三部" --debug
aiplayer --host 192.168.100.11 --port 9090 movie "阿凡达 2" --debug
aiplayer --host 192.168.100.11 --port 9090 movie "阿凡达" --debug
```

Expected: KODI returns `result: "OK"` and the right Avatar file plays.

Multi-language: Chinese queries find English-named files and vice versa
via Douban alias expansion (needs network; silently skipped offline).

## Music Search (artist / album / song)

```
aiplayer --host 192.168.100.11 --port 9090 music --artist "赵传" --debug
aiplayer --host 192.168.100.11 --port 9090 music --artist "赵传" --album "我是一只小小鸟" --debug
```

The `--song` form matches files named with the song title. Track-numbered
files (`01.mp3`) have nothing to match - navigate by album instead.

## TV Episode Search

```
aiplayer --host 192.168.100.11 --port 9090 tv "黑暗物质第三季第四集" --debug
aiplayer --host 192.168.100.11 --port 9090 tv "黑暗物质 S03E04" --debug
aiplayer --host 192.168.100.11 --port 9090 tv "黑暗物质 3x04" --debug
```

Expected output (verified):

```
[debug] Searched 'video' (nfs://192.168.100.2/Public/video/): 1 candidate match(es)
Playing from video: Dark Matter / Season 3 / 黑暗物质.Dark.Matter.S03E04.720p...
{"id": 164, "jsonrpc": "2.0", "result": "OK"}
```

## PVR Live TV + Channels

```
aiplayer --host 192.168.100.11 --port 9090 tv
aiplayer --host 192.168.100.11 --port 9090 tv "湖南卫视"
```

Expected: prints `Found channel`, current program, and KODI tunes in.
Same works on the Sony box with `--protocol http --username kodi --password hermes`.

## PVR Catch-up

The user's IPTV m3u mixes two placeholder families channel-by-channel:
- Legacy strftime: `${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}`
- VLC shorthand: `{utc:YmdHMS}-{utcend:YmdHMS}`

`m3u_catchup.py` supports four families (KODI native seconds/strings,
iptvsimple strftime, VLC shorthand).

### Mode 1: broadcastid (Sony TV only)

```
aiplayer --host 192.168.100.43 --port 8080 --protocol http --username kodi --password hermes \
    catchup "湖南卫视" --date yesterday --time 18:30
```

Verified: KODI returns `result: "OK"`; PVR client builds the URL from the m3u.

### Mode 2: self-built URL (`--m3u`, works on both boxes)

Parse the m3u ourselves, substitute the channel's `catchup-source`
template, and `Player.Open({file: <url>})`. Bypasses the PVR client
entirely - required on the 11 box where `Player.Open({broadcastid})`
returns -32602.

`--m3u` accepts an http(s) URL **or** a local file path (default from
config `iptv.m3u`):

```
# URL
aiplayer --host 192.168.100.11 --port 9090 catchup "湖南卫视" \
    --date yesterday --time 18:30 \
    --m3u "http://192.168.100.2:8000/iptv/iptv-10.m3u"

# Local file (m3u must be readable from this machine)
aiplayer --host 192.168.100.11 --port 9090 catchup "湖南卫视" \
    --date yesterday --time 18:30 --m3u "G:\Public\iptv.m3u"
```

EPG XMLTV resolution order: `--epg` > config `iptv.epg` > m3u
`x-tvg-url`. Override with `--epg` when the m3u carries no `x-tvg-url`:

```
aiplayer --host 192.168.100.11 --port 9090 catchup "湖南卫视" \
    --date yesterday --time 18:30 \
    --m3u "http://192.168.100.2:8000/iptv/iptv-10.m3u" \
    --epg "http://192.168.100.2:8000/iptv/iptv-epg.xml.gz"
```

Verified on 11 box (2026-06-08): 湖南卫视 yesterday 18:30 → URL
`rtsp://118.123.55.74/.../...smil?playseek=20260607180000-20260607183000`
→ KODI `Player.Open` result "OK", `Player.GetItem` shows the same URL.

## Playback Control

```
aiplayer --host 192.168.100.11 --port 9090 pause
aiplayer --host 192.168.100.11 --port 9090 play
aiplayer --host 192.168.100.11 --port 9090 next
aiplayer --host 192.168.100.11 --port 9090 prev
aiplayer --host 192.168.100.11 --port 9090 stop
aiplayer --host 192.168.100.11 --port 9090 status
aiplayer --host 192.168.100.11 --port 9090 volume_up
aiplayer --host 192.168.100.11 --port 9090 volume_down
aiplayer --host 192.168.100.11 --port 9090 mute
```

Control commands act on whichever mode the *last play command* used -
pass the same `--host`/`--auto` flags (or none for default local mode).

## EPG Browsing

```
aiplayer --host 192.168.100.11 --port 9090 epg "湖南卫视" --date today
aiplayer epg "湖南卫视" --m3u "http://192.168.100.2:8000/iptv/iptv-10.m3u" --date yesterday
```

## When something breaks

The old `diag_*.py` probes were archived to `tests/archive/` (they use
outdated CLI flags). For raw responses, use the current CLI with
`--debug`, or write a quick probe against `KodiAPI` directly.