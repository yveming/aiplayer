# Archived Diagnostics

One-off diagnostic scripts used during development to probe a real KODI
server (`192.168.100.11:9090`) and the user's IPTV backend
(`http://192.168.100.2:8000/iptv/`). Kept for archaeology only - they are
**not** run by `tests/run_all.py` and may reference outdated CLI flags
(`--m3u-url`, old script paths under `aiplayer/scripts/`).

If something breaks against real KODI/IPTV, prefer the current manual
checklist in `../REAL_KODI_TESTS.md` instead of these scripts.

## Known redundant pairs (iterations of the same probe)

| Superseded by            | Older variants                               |
|--------------------------|----------------------------------------------|
| `diag_pvr_files_probe2`  | `diag_pvr_files_probe`                       |
| `diag_pvr_clients_full`  | `diag_pvr_clients`                           |
| `diag_user_m3u_all`      | `diag_user_m3u_46ch`, `diag_user_m3u_survey` |
| `diag_catchup_11box_url` | `diag_catchup_http_dryrun` (dry-run)         |