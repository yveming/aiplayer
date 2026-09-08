#!/usr/bin/env python3
"""
Discover available players: KODI instances via SSDP/mDNS, or detect local mode.
"""

import sys
import os

from aiplayer.discover_kodi import discover_kodi as _discover_kodi, _is_local_ip
from aiplayer.local_search import find_local_media_roots


def detect_local_mode():
    """Check if local media directories exist (CIFS/NFS mounts)."""
    found = find_local_media_roots()
    total = sum(len(v) for v in found.values())
    if total > 0:
        return found
    return None


def discover_player(credentials=None, prefer_local=False):
    """Discover available player.

    Returns dict:
      - mode: 'kodi' or 'local'
      - instances: list of discovered instances (kodi) or None
      - media_roots: dict of media roots for local mode
      - message: human-readable description
    """
    # Try KODI first
    kodi_instances = _discover_kodi(credentials)

    if kodi_instances and not prefer_local:
        # For multiple instances, ask user
        if len(kodi_instances) > 1:
            print(f"\nMultiple KODI instances found ({len(kodi_instances)}). "
                  "Please specify which one to use.")
        else:
            inst = kodi_instances[0]
            print(f"\nUsing KODI: {inst['name']} ({inst['ip']}:{inst['port']})")

        return {
            'mode': 'kodi',
            'instances': kodi_instances,
            'media_roots': None,
            'message': f'Found {len(kodi_instances)} KODI instance(s)',
        }

    # No KODI - try local mode
    local_roots = detect_local_mode()
    if local_roots:
        total = sum(len(v) for v in local_roots.values())
        print(f"\nNo KODI found. Using local mode with {total} media director(y/ies).")
        return {
            'mode': 'local',
            'instances': None,
            'media_roots': local_roots,
            'message': f'Local mode with {total} media director(y/ies)',
        }

    return {
        'mode': None,
        'instances': None,
        'media_roots': None,
        'message': 'No KODI or local media found.',
    }


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Discover players')
    parser.add_argument('--prefer-local', action='store_true',
                        help='Prefer local mode even if KODI is available')
    args = parser.parse_args()

    result = discover_player(prefer_local=args.prefer_local)
    print(f"\nMode: {result['mode']}")
    print(f"Message: {result['message']}")
    if result.get('media_roots'):
        for media_type, dirs in result['media_roots'].items():
            print(f"  {media_type}: {[str(d) for d in dirs]}")
