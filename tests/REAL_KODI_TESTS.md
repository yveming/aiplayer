# Real-KODI Test Commands

Manual test commands for the user's actual KODI server at
`192.168.100.11:9090` (Sony TV, JSON-RPC over TCP, KODI v21.3,
JSON-RPC API 13.5). Run from the repo root or adjust paths.

TCP does **not** require `--username` / `--password`.

## Auto-discovery

```
# Quick: discover any KODI on the LAN
python aiplayer/scripts/discover_kodi.py
```

## Movie Search (Requirement #2)

```
# Ordinal - Chinese
python aiplayer/scripts/search_play.py --host 192.168.100.11 --port 9090 --protocol tcp --type movie --query "阿凡达三" --debug
# Ordinal - Chinese 第N部
python aiplayer/scripts/search_play.py --host 192.168.100.11 --port 9090 --protocol tcp --type movie --query "阿凡达第三部" --debug
# Ordinal - Arabic
python aiplayer/scripts/search_play.py --host 192.168.100.11 --port 9090 --protocol tcp --type movie --query "阿凡达 2" --debug
# No ordinal - all 3 Avatars
python aiplayer/scripts/search_play.py --host 192.168.100.11 --port 9090 --protocol tcp --type movie --query "阿凡达" --debug
```

Expected: KODI returns `result: "OK"` and the right Avatar file plays.

## Music Search (Requirement - artist / album / song)

```
python aiplayer/scripts/search_play.py --host 192.168.100.11 --port 9090 --protocol tcp --type music --artist "赵传" --debug
python aiplayer/scripts/search_play.py --host 192.168.100.11 --port 9090 --protocol tcp --type music --artist "赵传" --album "我是一只小小鸟" --debug
```

The `--song "我是一只小小鸟"` form is for files named with the song
title. If your music files are track-numbered (e.g. `01.mp3`), the
search has nothing to match and the user has to navigate by album.

## TV Episode Search (Requirement #3)

```
# Chinese 第N季第M集
python aiplayer/scripts/search_play.py --host 192.168.100.11 --port 9090 --protocol tcp --type tv --query "黑暗物质第三季第四集" --debug
# Standard S03E04
python aiplayer/scripts/search_play.py --host 192.168.100.11 --port 9090 --protocol tcp --type tv --query "黑暗物质 S03E04" --debug
# 3x04 alt format
python aiplayer/scripts/search_play.py --host 192.168.100.11 --port 9090 --protocol tcp --type tv --query "黑暗物质 3x04" --debug
```

Expected output (verified):
```
[debug] Searched 'video' (nfs://192.168.100.2/Public/video/): 1 candidate match(es)
Playing from video: Dark Matter / Season 3 / 黑暗物质.Dark.Matter.S03E04.720p.HDTV.x264.双语字幕精校版-深影字幕组
{"id": 164, "jsonrpc": "2.0", "result": "OK"}
```

## PVR Live TV (Requirement #4)

The 11 box is fine for live TV (no auth needed):

```
python aiplayer/scripts/pvr_epg.py --host 192.168.100.11 --port 9090 --protocol tcp --action play --channel "湖南卫视"
```

Expected: prints `Found channel`, current program, and KODI tunes in.

Sony TV (HTTP + auth) works the same way:

```
python aiplayer/scripts/pvr_epg.py --host 192.168.100.43 --port 8080 --protocol http --username kodi --password hermes --action play --channel "湖南卫视"
```

## PVR Catch-up (Requirement #5)

The user's IPTV setup uses **two** KODI boxes:

| Box           | Address                          | Protocol | Auth | Catch-up |
|---------------|----------------------------------|----------|------|----------|
| 11 box        | 192.168.100.11:9090              | TCP      | no   | NO (PVR client returns -32602 on broadcastid) |
| Sony TV       | 192.168.100.43:8080              | HTTP     | kodi/hermes | YES (PVR IPTV Simple Client builds URL from m3u) |

The user's m3u mixes two placeholder families channel-by-channel:
- Legacy strftime: `${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}`
- VLC shorthand: `{utc:YmdHMS}-{utcend:YmdHMS}`

### Mode 1: broadcastid (Sony TV only)

```
python aiplayer/scripts/pvr_epg.py --host 192.168.100.43 --port 8080 --protocol http --username kodi --password hermes --action catchup --channel "湖南卫视" --date "yesterday" --time "18:30"
```

Verified: KODI returns `result: "OK"`. PVR client parses the m3u
template and constructs the URL.

### Mode 2: self-built URL (both boxes, requires --m3u)

We parse the m3u file ourselves, find the channel's `catchup-source`
template, substitute placeholders with the broadcast's start/end
times, and call `Player.Open({file: <url>})`. This works on the
**11 box** because it bypasses the PVR client entirely.

```
# 1. Make the m3u reachable. Easiest: copy it to the NFS share
copy \\192.168.100.2\Public\iptv.m3u  G:\Public\iptv.m3u
#    (or wherever the NFS export lives - adjust path)

# 2. Run catchup with --m3u
python aiplayer/scripts/pvr_epg.py --host 192.168.100.11 --port 9090 --protocol tcp --action catchup --channel "湖南卫视" --date "yesterday" --time "18:30" --m3u "G:\Public\iptv.m3u"
```

`m3u_catchup.py` (new in v0.05) supports all four placeholder
families seen in real m3u files:
1. KODI native seconds: `{start}` `{end}` `{duration}` `{timestamp}` `{utc}`
2. KODI native strings: `{utctime}` `{utcstart}` `{utcend}` `{localtime}` ...
3. iptvsimple strftime: `${(b)yyyyMMddHHmmss}` `${(e)yyyy-MM-dd}` ...
4. VLC shorthand: `{utc:YmdHMS}` `{utcend:YmdHMS}` `{lutc:YmdHMS}` ...

## Self-Contained HTTP Catch-up (v0.05a, no --m3u file needed)

Same metadata, but the m3u and EPG are fetched directly from the
IPTV backend (m3u's `#EXTM3U` carries `x-tvg-url=".../iptv-epg.xml.gz"`).
Bypasses KODI PVR.GetChannels / PVR.GetBroadcasts entirely - useful on
boxes whose PVR client can't be reached over JSON-RPC (e.g. 11 box
where `Player.Open({broadcastid})` returns -32602).

```
# 11 box - HTTP m3u + EPG, no PVR calls
python aiplayer/scripts/pvr_epg.py --host 192.168.100.11 --port 9090 --protocol tcp \
    --action catchup --channel "湖南卫视" --date "yesterday" --time "18:30" \
    --m3u-url "http://192.168.100.2:8000/iptv/iptv-10.m3u" --use-http-epg

# Override the EPG URL (else read from x-tvg-url)
python aiplayer/scripts/pvr_epg.py --host 192.168.100.11 --port 9090 --protocol tcp \
    --action catchup --channel "湖南卫视" --date "yesterday" --time "18:30" \
    --m3u-url "http://192.168.100.2:8000/iptv/iptv-10.m3u" --use-http-epg \
    --epg-url "http://192.168.100.2:8000/iptv/iptv-epg.xml.gz"
```

Verified on 11 box (2026-06-08): 湖南卫视 yesterday 18:30 →
URL `rtsp://118.123.55.74/.../...smil?playseek=20260607180000-20260607183000`
→ KODI accepted (`Player.Open` result: "OK") and `Player.GetItem` shows
`file` = same URL → playing.

The m3u and EPG gz are fetched by `m3u_catchup._read_text` (HTTP) and
`m3u_catchup.parse_xmltv` (XMLTV, gunzip-aware). Channel id match uses
m3u's `tvg-id` against XMLTV's `channel id`.

## PVR Channel List

```
python aiplayer/scripts/pvr_epg.py --host 192.168.100.11 --port 9090 --protocol tcp --action channels
```

## Playback Control

```
python aiplayer/scripts/playback_control.py --host 192.168.100.11 --port 9090 --protocol tcp --action pause
python aiplayer/scripts/playback_control.py --host 192.168.100.11 --port 9090 --protocol tcp --action resume
python aiplayer/scripts/playback_control.py --host 192.168.100.11 --port 9090 --protocol tcp --action volume-up
python aiplayer/scripts/playback_control.py --host 192.168.100.11 --port 9090 --protocol tcp --action volume-down
```

## Diagnostics (when something breaks)

```
# Dump raw source paths
python tests/diag_kodi_sources.py

# Dump /Public/music/赵传/ tree
python tests/diag_music_tree.py

# Dump /Public/movie/ tree
python tests/diag_movie_tree.py

# Dump raw PVR.GetBroadcasts for 湖南卫视
python tests/diag_pvr_epg.py

# Scan all PVR channels for catch-up
python tests/diag_pvr_catchup_scan.py
```
