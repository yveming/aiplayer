#!/usr/bin/env python3
"""
KODI JSON-RPC API 2.0 Wrapper
Supports both HTTP (port 8080) and TCP (port 9090) connections.
- TCP: Used when KODI is on the same machine as the user
- HTTP: Used when KODI is on a different machine
"""

import requests
import json
import sys
import socket

def is_local_ip(host):
    """True when host is one of this machine's own addresses."""
    local_ips = ['127.0.0.1', 'localhost', '::1']
    if host in local_ips:
        return True
    try:
        host_name = socket.gethostname()
        for info in socket.getaddrinfo(host_name, None):
            if info[4][0] == host:
                return True
    except Exception:
        pass
    return False


class KodiAPI:
    def __init__(self, host, port=None, username='', password='', protocol='auto'):
        """
        Initialize KODI API connection.
        
        Args:
            host: KODI IP address or hostname
            port: Port number (auto-selects based on protocol if None)
            username: KODI username (optional)
            password: KODI password (optional)
            protocol: 'tcp', 'http', or 'auto' (auto-detects based on IP)
        """
        self.host = host
        self.username = username
        self.password = password
        self.auth = (username, password) if username and password else None
        self.id_counter = 1
        self._port_explicit = port is not None

        # protocol='auto': don't guess permanently. Keep an initial guess and
        # resolve on the first request by probing HTTP then TCP (local boxes
        # try TCP first) - remote KODI often runs TCP on 9090, which the old
        # "remote always HTTP" guess could never reach without --protocol tcp.
        self._auto = (protocol == 'auto')
        self._auto_resolved = not self._auto
        if self._auto:
            self.protocol = 'tcp' if is_local_ip(host) else 'http'
        else:
            self.protocol = protocol

        # Set port based on protocol
        if port is None:
            self.port = 9090 if self.protocol == 'tcp' else 8080
        else:
            self.port = port

        self._set_base_url()

        if self._auto:
            print(f"Connected to KODI (auto-detect: {host})")
        else:
            print(f"Connected to KODI (protocol: {self.protocol}, port: {self.port})")

    def _set_base_url(self):
        self.base_url = (f'http://{self.host}:{self.port}/jsonrpc'
                         if self.protocol == 'http' else None)

    def _protocol_port(self, proto):
        if self._port_explicit:
            return self.port
        return 9090 if proto == 'tcp' else 8080

    def _probe_version(self):
        """Best-effort JSONRPC.Version probe with no output (for auto-detect)."""
        payload = json.dumps({"jsonrpc": "2.0", "method": "JSONRPC.Version", "id": 0})
        data = None
        try:
            if self.protocol == 'http':
                r = requests.post(self.base_url, data=payload,
                                  auth=self.auth, timeout=3)
                if r.status_code != 200:
                    return False
                data = r.json()
            else:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                try:
                    sock.connect((self.host, self.port))
                    sock.sendall((payload + '\n').encode('utf-8'))
                    buf = b''
                    while True:
                        chunk = sock.recv(8192)
                        if not chunk:
                            break
                        buf += chunk
                        try:
                            data = json.loads(buf.decode('utf-8'))
                            break
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            continue
                finally:
                    sock.close()
        except (OSError, ValueError, requests.exceptions.RequestException):
            return False
        return isinstance(data, dict) and 'result' in data and 'version' in data['result']

    def _auto_candidates(self):
        """Protocols to try for 'auto'. A port pins the transport when it is
        one of the well-known ones (8080=http, 9090=tcp); other custom ports
        are tried with both."""
        if self._port_explicit:
            if self.port == 8080:
                return ['http']
            if self.port == 9090:
                return ['tcp']
        return ['tcp', 'http'] if is_local_ip(self.host) else ['http', 'tcp']

    def _resolve_auto(self):
        """Resolve protocol='auto' once, by probing the transports in order."""
        if not self._auto or self._auto_resolved:
            return
        self._auto_resolved = True
        for proto in self._auto_candidates():
            prev = (self.protocol, self.port, self.base_url)
            self.protocol = proto
            self.port = self._protocol_port(proto)
            self._set_base_url()
            if self._probe_version():
                return
            self.protocol, self.port, self.base_url = prev

    def _request(self, method, params=None):
        """Send JSON-RPC request to KODI"""
        self._resolve_auto()
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "id": self.id_counter,
        }
        if params:
            payload["params"] = params

        self.id_counter += 1
        payload_str = json.dumps(payload)

        if self.protocol == 'http':
            return self._request_http(payload_str)
        else:
            return self._request_tcp(payload_str)

    def jsonrpc(self, method, params=None):
        """Generic JSON-RPC call (alias for _request, public-friendly)."""
        return self._request(method, params)
    
    def _request_http(self, payload_str):
        """Send request via HTTP"""
        try:
            response = requests.post(
                self.base_url,
                data=payload_str,
                auth=self.auth,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"HTTP Error: {e}", file=sys.stderr)
            return None
        except json.JSONDecodeError as e:
            print(f"Invalid JSON response: {e}", file=sys.stderr)
            return None
    
    def _request_tcp(self, payload_str):
        """Send request via TCP socket (JSON-RPC over TCP, newline-delimited)"""
        sock = None
        result = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((self.host, self.port))

            # Send payload with newline delimiter
            sock.sendall((payload_str + '\n').encode('utf-8'))

            # Read response until we get a complete JSON
            response_data = b''
            while True:
                chunk = sock.recv(8192)
                if not chunk:
                    break
                response_data += chunk
                try:
                    result = json.loads(response_data.decode('utf-8'))
                    break  # Valid JSON received
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue  # Incomplete JSON/UTF-8, keep reading

            # A port can be open yet speak another protocol: no parseable JSON
            # means no usable reply - return None instead of crashing.
            return result
        except socket.timeout as e:
            print(f"TCP Socket Timeout: {e}", file=sys.stderr)
            return None
        except socket.error as e:
            print(f"TCP Socket Error: {e}", file=sys.stderr)
            return None
        except json.JSONDecodeError as e:
            print(f"Invalid JSON response: {e}", file=sys.stderr)
            return None
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
    
    def get_version(self):
        """Get KODI version"""
        return self._request('JSONRPC.Version')
    
    def player_get_active_players(self, type='all'):
        """Get active players"""
        return self._request('Player.GetActivePlayers')
    
    def player_play_pause(self, player_id=0):
        """Toggle play/pause"""
        return self._request('Player.PlayPause', {'playerid': player_id})
    
    def player_stop(self, player_id=0):
        """Stop playback"""
        return self._request('Player.Stop', {'playerid': player_id})
    
    def player_seek(self, player_id=0, position='beginning'):
        """Seek to position"""
        value = {'value': position}
        return self._request('Player.Seek', {'playerid': player_id, 'value': value})
    
    def player_go_to(self, player_id=0, to='next'):
        """Go to next/previous"""
        return self._request('Player.GoTo', {'playerid': player_id, 'to': to})
    
    def player_set_speed(self, player_id=0, speed=1):
        """Set playback speed"""
        return self._request('Player.SetSpeed', {'playerid': player_id, 'speed': speed})
    
    def player_get_item(self, player_id=0, properties=None):
        """Get the item currently loaded by a player.

        KODI returns only the requested fields. Some boxes reject most
        properties with -32602 (allowing only title/file/duration), so when an
        explicit property list fails we retry with the minimal set.
        """
        props = properties if properties is not None else ['title', 'file']
        result = self._request('Player.GetItem', {
            'playerid': player_id,
            'properties': props,
        })
        if result and 'error' in result and properties:
            minimal = [p for p in ('title', 'file', 'duration') if p in properties]
            if minimal and minimal != list(props):
                result = self._request('Player.GetItem', {
                    'playerid': player_id,
                    'properties': minimal,
                })
        return result

    def player_get_properties(self, player_id=0, properties=None):
        """Get player properties (time/totaltime/... by default)."""
        return self._request('Player.GetProperties', {
            'playerid': player_id,
            'properties': properties or ['time', 'totaltime', 'percentage', 'speed', 'volume'],
        })
    
    def application_set_volume(self, volume):
        """Set volume (0-100)"""
        volume = max(0, min(100, volume))
        return self._request('Application.SetVolume', {'volume': volume})
    
    def application_get_properties(self):
        """Get application properties"""
        return self._request('Application.GetProperties', {'properties': ['volume', 'muted']})
    
    def player_open_item(self, item):
        """Open item for playback"""
        return self._request('Player.Open', {'item': item})
    
    def video_library_get_movies(self, fields=None, limits=None):
        """Get movies from library"""
        params = {
            'properties': fields or ['title', 'year', 'file', 'playcount', 'lastplayed']
        }
        if limits:
            params['limits'] = limits
        return self._request('VideoLibrary.GetMovies', params)
    
    def video_library_get_episodes(self, fields=None, limits=None):
        """Get episodes from library"""
        params = {
            'properties': fields or ['title', 'showtitle', 'season', 'episode', 'file', 'playcount', 'lastplayed']
        }
        if limits:
            params['limits'] = limits
        return self._request('VideoLibrary.GetEpisodes', params)
    
    def video_library_get_tv_shows(self, fields=None, limits=None):
        """Get TV shows from library"""
        params = {
            'properties': fields or ['title', 'year', 'file', 'playcount', 'lastplayed']
        }
        if limits:
            params['limits'] = limits
        return self._request('VideoLibrary.GetTVShows', params)
    
    def audio_library_get_songs(self, fields=None, limits=None):
        """Get songs from library"""
        params = {
            'properties': fields or ['title', 'artist', 'album', 'file', 'playcount', 'lastplayed']
        }
        if limits:
            params['limits'] = limits
        return self._request('AudioLibrary.GetSongs', params)
    
    def audio_library_get_artists(self, fields=None, limits=None):
        """Get artists from library"""
        params = {
            'properties': fields or ['artist', 'album', 'file', 'playcount', 'lastplayed']
        }
        if limits:
            params['limits'] = limits
        return self._request('AudioLibrary.GetArtists', params)
    
    def audio_library_get_albums(self, fields=None, limits=None):
        """Get albums from library"""
        params = {
            'properties': fields or ['title', 'artist', 'album', 'file', 'playcount', 'lastplayed']
        }
        if limits:
            params['limits'] = limits
        return self._request('AudioLibrary.GetAlbums', params)
    
    def pvr_get_channels(self, channel_group_id=1, fields=None, limits=None):
        """Get PVR channels"""
        params = {
            'channelgroupid': channel_group_id
        }
        if fields:
            params['properties'] = fields
        if limits:
            params['limits'] = limits
        return self._request('PVR.GetChannels', params)
    
    def pvr_get_channel_groups(self, channeltype='tv'):
        """Get all PVR channel groups"""
        return self._request('PVR.GetChannelGroups', {'channeltype': channeltype})
    
    def pvr_get_broadcasts(self, channel_id, fields=None, limits=None):
        """Get EPG broadcasts for a channel"""
        params = {'channelid': channel_id}
        if fields:
            params['properties'] = fields
        if limits:
            params['limits'] = limits
        return self._request('PVR.GetBroadcasts', params)
    
    def pvr_get_channel_details(self, channel_id, properties=None):
        """Get PVR channel details. `properties` is a list of field names
        to include in the response (e.g. ['hascatchup', 'catchupid',
        'streamurl']). KODI returns only the fields you ask for, so
        catch-up callers must request the catch-up fields explicitly.
        """
        params = {'channelid': channel_id}
        if properties:
            params['properties'] = properties
        return self._request('PVR.GetChannelDetails', params)
    
    def files_get_directory(self, path, media='files', limit=None):
        """Get directory contents"""
        params = {
            'directory': path,
            'media': media
        }
        if limit:
            params['limits'] = limit
        return self._request('Files.GetDirectory', params)
    
    def files_get_sources(self, media='files'):
        """Get available sources"""
        return self._request('Files.GetSources', {'media': media})
    
    def files_prepare_play(self, path):
        """Prepare a path for playback"""
        return self._request('Files.PreparePlay', {'path': path})
    
    def playlist_add(self, playlist_id, item):
        """Add item to playlist"""
        return self._request('Playlist.Add', {
            'playlistid': playlist_id,
            'item': item
        })
    
    def playlist_clear(self, playlist_id):
        """Clear playlist"""
        return self._request('Playlist.Clear', {'playlistid': playlist_id})

    def playlist_remove(self, playlist_id, position):
        """Remove the item at `position` from a playlist"""
        return self._request('Playlist.Remove', {
            'playlistid': playlist_id,
            'position': position,
        })
    
    def playlist_play(self, playlist_id):
        """Play playlist"""
        return self._request('Playlist.Play', {'playlistid': playlist_id})
    
    def playlist_get_items(self, playlist_id=0, properties=None, limits=None):
        """Get items in a playlist (0=audio, 1=video, 2=picture)."""
        params = {
            'playlistid': playlist_id,
            'properties': properties or ['title', 'file', 'duration'],
        }
        if limits:
            params['limits'] = limits
        return self._request('Playlist.GetItems', params)

    def playlist_get_playlists(self):
        """Get available playlists"""
        return self._request('Playlist.GetPlaylists')
