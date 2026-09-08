#!/usr/bin/env python3
"""Run all offline (no KODI required) test suites and print a summary.

Usage:
    python tests/run_all.py
    python tests/run_all.py --verbose    # show full output from each suite
"""
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

SUITES = [
    ('movie smoke',           'test_movie_smoke.py',         'movie 6 scenarios: flat, year dir, parens, etc.'),
    ('music 3-level',         'test_music_3level.py',        'music 4 + helpers 2: artist/album/song 3-level deep path'),
    ('movie ordinal unit',    'test_ordinal.py',             '14 ordinal + base cases (一/二/3/3部/2009/2001 etc.)'),
    ('movie ordinal e2e',     'test_ordinal_integration.py', '6 cases against 3-Avatar mock: 阿凡达三/一/2/3/第三部'),
    ('pvr unit',              'test_pvr_units.py',           'parse_time x10 + find_channel_by_name x5'),
    ('m3u catchup',           'test_m3u_catchup.py',         'm3u parse + URL builder covering strftime/VLC/seconds placeholders'),
]

# Real-KODI suite - skipped by default
E2E_SUITE = (
    'kodi e2e smoke',         'test_e2e_real_kodi.py',       'real KODI: version + GetSources + 46 channels + 68 broadcasts',
)


def run(suite_name, script, description, verbose):
    path = os.path.join(HERE, script)
    t0 = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, '-X', 'utf8', path],
            capture_output=True, text=True, encoding='utf-8',
            errors='replace',
            timeout=60,
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
        )
        dt = time.time() - t0
        out = proc.stdout or ''
        err = proc.stderr or ''
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        return dict(name=suite_name, script=script, desc=description,
                    passed='TIMEOUT', failed='TIMEOUT', dt=0, rc=-1)
    except Exception as e:
        return dict(name=suite_name, script=script, desc=description,
                    passed='ERROR', failed=str(e), dt=0, rc=-1)

    # Count PASS / OK / FAIL lines. The pvr_units suite prints
    # `parse_time(...) -> ...` lines instead of explicit PASS/FAIL,
    # so we also fall back to the process return code for those.
    p = sum(1 for ln in out.splitlines() if 'PASS' in ln and 'FAIL' not in ln) \
        + sum(1 for ln in out.splitlines() if '[OK' in ln)
    f = sum(1 for ln in out.splitlines() if 'FAIL' in ln)
    if p == 0 and f == 0:
        if rc == 0:
            p = 1  # bare-script-without-PASS-marker counts as one passing suite
        else:
            f = 1

    if verbose:
        print('=' * 70)
        print(f'  {suite_name}  ({script})')
        print(f'  {description}')
        print('=' * 70)
        print(out)
        if err:
            print('--- stderr ---')
            print(err)

    return dict(name=suite_name, script=script, desc=description,
                passed=p, failed=f, dt=dt, rc=rc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verbose', '-v', action='store_true',
                    help='Print full output of every suite')
    ap.add_argument('--e2e', action='store_true',
                    help='Also run the real-KODI E2E smoke test (requires KODI at 192.168.100.11:9090)')
    args = ap.parse_args()

    suites = list(SUITES)
    if args.e2e:
        suites.append(E2E_SUITE)

    print('KODI Control Skill - offline test suite'
          + (' (+e2e)' if args.e2e else ''))
    print('=' * 70)
    total_p = 0
    total_f = 0
    rows = []
    for name, script, desc in suites:
        r = run(name, script, desc, args.verbose)
        total_p += r['passed']
        total_f += r['failed']
        rows.append(r)

    if not args.verbose:
        print(f'{"suite":24}{"passed":>10}{"failed":>10}{"time":>10}  description')
        print('-' * 70)
        for r in rows:
            print(f'{r["name"]:24}{str(r["passed"]):>10}{str(r["failed"]):>10}'
                  f'{r["dt"]:>9.2f}s  {r["desc"]}')

    print('-' * 70)
    print(f'TOTAL: {total_p} passed, {total_f} failed')
    sys.exit(0 if total_f == 0 and total_p > 0 else 1)


if __name__ == '__main__':
    main()
