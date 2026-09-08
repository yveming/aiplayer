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
        
        # Determine protocol
        if protocol == 'auto':
            # Local IPs use TCP, remote use HTTP
            if self._is_local_ip(host):
                self.protocol = 'tcp'
            else:
                self.protocol = 'http'
        else:
            self.protocol = protocol
        
        # Set port based on protocol
        if port is None:
            self.port = 9090 if self.protocol == 'tcp' else 8080
        else:
            self.port = port
        
        # Build connection URL/endpoint
        if self.protocol == 'http':
            self.base_url = f'http://{host}:{self.port}/jsonrpc'
        else:
            self.base_url = None  # TCP uses raw socket
        
        print(f"Connected to KODI (protocol: {self.protocol}, port: {self.port})")
    
    def _is_local_ip(self, host):
        """Check if host is local (same machine as this agent)"""
        local_ips = ['127.0.0.1', 'localhost', '::1']
        
        if host in local_ips:
            return True
        
        try:
            # Get all local IPs of this agent machine
            host_name = socket.gethostname()
            local_ip_list = socket.getaddrinfo(host_name, None)
            for ip_info in local_ip_list:
                if ip_info[4][0] == host:
                    return True
        except:
            pass
        
        return False
    
    def _request(self, method, params=None):
        """Send JSON-RPC request to KODI"""
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
                # Try to parse complete JSON
                try:
                    result = json.loads(response_data.decode('utf-8'))
                    break  # Valid JSON received
                except json.JSONDecodeError:
                    continue  # Incomplete JSON, keep reading
                except UnicodeDecodeError:
                    continue  # Incomplete UTF-8, keep reading
            
            sock.close()
            
            if not response_data:
                return None
            
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
            try:
                sock.close()
            except:
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
    
    def player_get_properties(self, player_id=0):
        """Get player properties"""
        return self._request('Player.GetProperties', {
            'playerid': player_id,
            'properties': ['time', 'totaltime', 'percentage', 'speed', 'volume']
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
    
    def playlist_play(self, playlist_id):
        """Play playlist"""
        return self._request('Playlist.Play', {'playlistid': playlist_id})
    
    def playlist_get_playlists(self):
        """Get available playlists"""
        return self._request('Playlist.GetPlaylists')
