# Tests

Offline test suite for aiplayer (KODI + local mpv unified player).

## Layout

| File                            | Type        | KODI? | What it covers                                              |
|---------------------------------|-------------|-------|-------------------------------------------------------------|
| `test_movie_smoke.py`           | offline     | no    | 6 movie search scenarios (flat file, year dir, parens...)   |
| `test_music_3level.py`          | offline     | no    | 4 music + 2 helper tests (artist / album / song deep path)  |
| `test_ordinal.py`               | offline     | no    | 14 `extract_movie_ordinal` + `strip_movie_ordinal` cases    |
| `test_ordinal_integration.py`   | offline     | no    | 6 cases against a 3-Avatar mock matching real media layout  |
| `test_pvr_units.py`             | offline     | no    | 10 `parse_time` + 5 `find_channel_by_name` cases            |
| `test_m3u_catchup.py`           | offline     | no    | m3u parse + catchup URL builder (4 placeholder families)    |
| `run_all.py`                    | runner      | no    | Run every offline suite + summarise                         |
| `REAL_KODI_TESTS.md`            | checklist   | YES   | Manual real-KODI test commands (movie / music / tv / pvr)   |
| `test_e2e_real_kodi.py`         | integration | YES   | Auto smoke-test against a real KODI box                     |
| `archive/`                      | archived    | YES   | 32 one-off `diag_*.py` probes (see `archive/README.md`)     |

Offline suites never hit the network: online metadata (Douban) only
activates on empty search results, which the mocks never produce, and
can be force-disabled with `"metadata": {"enabled": false}` in
`~/.config/aiplayer/config.json`.

## Running

```
# All offline suites (no KODI needed)
python tests/run_all.py

# Single suite
python tests/test_movie_smoke.py
python tests/test_ordinal_integration.py
python tests/test_pvr_units.py
```

The runner counts `PASS` and `[OK ...]` lines per suite, falling back to
return code for bare scripts (pvr_units). Any non-zero failure exits 1.

## Offline vs Real KODI

- **Offline** tests use `MockKodiAPI` to feed hard-coded trees. They
  cover the search/matching logic (ordinals, year extraction, fuzzy
  path matching, time-zone math) without needing a KODI instance.
- **Real KODI** tests in `REAL_KODI_TESTS.md` verify the same scenarios
  end-to-end on the user's actual KODI server (192.168.100.11:9090).
  These were the source of every bug fix in the changelog.

## When a test fails

1. If the offline test fails: bug is in the search/parsing logic -
   check `search_play.py` / `pvr_epg.py` first.
2. If a real KODI command from `REAL_KODI_TESTS.md` fails: either
   the KODI source layout changed, the JSON-RPC enum changed, or the
   user added new content. Re-run the matching `diag_*.py` to see
   the raw KODI response, then adjust the filter / parser.
