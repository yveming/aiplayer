#!/usr/bin/env python3
"""
Discover KODI instances via SSDP/UPNP/DLNA and Zeroconf/mDNS
"""

import socket
import threading
import time
import json
import sys
import requests
from xml.etree import ElementTree

try:
    from zeroconf import Zeroconf, ServiceBrowser, ServiceListener
    HAS_ZEROCONF = True
except ImportError:
    HAS_ZEROCONF = False

SSDP_MCAST_ADDR = '239.255.255.250'
SSDP_PORT = 1900
SSP_MX = 2
SSDP_ST = 'ssdp:all'

def discover_ssdp(timeout=5):
    """Discover UPnP/DLNA devices via SSDP"""
    responses = []
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('', 0))
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(timeout)
    
    message = f'M-SEARCH * HTTP/1.1\r\nHOST: {SSDP_MCAST_ADDR}:{SSDP_PORT}\r\nMAN: "ssdp:discover"\r\nMX: {SSP_MX}\r\nST: {SSDP_ST}\r\n\r\n'
    
    try:
        sock.sendto(message.encode(), (SSDP_MCAST_ADDR, SSDP_PORT))
    except Exception as e:
        print(f"SSDP discovery failed: {e}", file=sys.stderr)
        sock.close()
        return []
    
    while True:
        try:
            data, addr = sock.recvfrom(4096)
            response = data.decode('utf-8', errors='ignore')
            responses.append({
                'ip': addr[0],
                'response': response
            })
        except socket.timeout:
            break
    
    sock.close()
    return responses

def parse_location(response):
    """Extract location URL from SSDP response"""
    for line in response.split('\r\n'):
        if line.lower().startswith('location:'):
            return line.split(':', 1)[1].strip()
    return None

def get_device_info(location_url):
    """Get device info from UPnP description URL"""
    try:
        response = requests.get(location_url, timeout=3)
        root = ElementTree.fromstring(response.content)
        
        ns = {'upnp': 'urn:schemas-upnp-org:device-1-0'}
        friendly_name = root.find('.//upnp:friendlyName', ns)
        manufacturer = root.find('.//upnp:manufacturer', ns)
        
        return {
            'name': friendly_name.text if friendly_name is not None else 'Unknown',
            'manufacturer': manufacturer.text if manufacturer is not None else 'Unknown'
        }
    except:
        return {'name': 'Unknown', 'manufacturer': 'Unknown'}

def check_kodi_api_http(ip, port=8080, credentials=None):
    """Check if KODI HTTP JSON-RPC API is available.
    credentials: list of (username, password) tuples to try. None means no auth."""
    url = f'http://{ip}:{port}/jsonrpc'
    payload = {
        "jsonrpc": "2.0",
        "method": "JSONRPC.Version",
        "id": 1
    }
    
    auth_list = []
    if credentials:
        auth_list = credentials
    else:
        auth_list = [None]
    
    for auth in auth_list:
        try:
            response = requests.post(url, json=payload, timeout=3, auth=auth)
            if response.status_code == 200:
                data = response.json()
                if 'result' in data and 'version' in data['result']:
                    version = data['result']['version']
                    if isinstance(version, dict) and 'major' in version:
                        return True
            elif response.status_code == 401:
                pass
        except:
            pass
    
    return False

def check_kodi_api_tcp(ip, port=9090):
    """Check if KODI TCP WebSocket API is available"""
    try:
        import websocket
        ws = websocket.create_connection(
            f'ws://{ip}:{port}/jsonrpc',
            timeout=3,
            suppress_origin=True
        )
        ws.send('{"jsonrpc":"2.0","method":"JSONRPC.Version","id":1}')
        response = ws.recv()
        ws.close()
        
        import json
        data = json.loads(response)
        if 'result' in data and 'version' in data['result']:
            return True
    except:
        pass
    
    return False

def discover_mdns(timeout=5):
    """Discover devices via Zeroconf/mDNS"""
    results = []
    
    if not HAS_ZEROCONF:
        print("zeroconf not available, skipping mDNS discovery", file=sys.stderr)
        return results
    
    class KodiListener(ServiceListener):
        def add_service(self, zc, type_, name):
            info = zc.get_service_info(type_, name, timeout=2000)
            if info:
                for addr in info.addresses:
                    ip = socket.inet_ntoa(addr)
                    clean_name = name
                    for suffix in ['._http._tcp.local.', '._kodi._tcp.local.', '._xbmc._tcp.local.', '._airplay._tcp.local.', '._mediarenderer._tcp.local.', '._ssh._tcp.local.', '._workstation._tcp.local.', '._device-info._tcp.local.', '._smb._tcp.local.', '._nfs._tcp.local.', '.local.']:
                        clean_name = clean_name.replace(suffix, '')
                    results.append({
                        'ip': ip,
                        'port': info.port,
                        'name': clean_name
                    })

        def remove_service(self, zc, type_, name):
            pass

        def update_service(self, zc, type_, name):
            pass
    
    zeroconf = Zeroconf()
    listener = KodiListener()
    
    service_types = [
        "_http._tcp.local.",
        "_kodi._tcp.local.",
        "_xbmc._tcp.local.",
        "_airplay._tcp.local.",
        "_mediarenderer._tcp.local.",
        "_workstation._tcp.local.",
        "_device-info._tcp.local.",
        "_ssh._tcp.local.",
    ]
    
    browsers = []
    for st in service_types:
        try:
            browser = ServiceBrowser(zeroconf, st, listener)
            browsers.append(browser)
        except:
            pass
    
    time.sleep(timeout)
    
    for browser in browsers:
        browser.cancel()
    zeroconf.close()
    
    return results

def discover_kodi(credentials=None):
    """Main discovery function using SSDP, mDNS, and localhost probe.
    credentials: list of (username, password) tuples to try for HTTP auth."""
    print("Discovering KODI instances...")
    
    kodi_instances = []
    seen_ips = set()
    
    def probe_device(ip, device_name='Unknown'):
        """Probe 8080 and 9090 ports on a device"""
        if ip in seen_ips:
            return None
        
        actual_ip = ip
        if _is_local_ip(ip):
            actual_ip = '127.0.0.1'
        
        for port in [8080, 9090]:
            if port == 9090:
                if check_kodi_api_tcp(actual_ip, port):
                    seen_ips.add(ip)
                    return {
                        'ip': actual_ip,
                        'port': port,
                        'name': device_name,
                        'local': True,
                        'protocol': 'tcp'
                    }
            else:
                if check_kodi_api_http(actual_ip, port, credentials):
                    seen_ips.add(ip)
                    return {
                        'ip': actual_ip,
                        'port': port,
                        'name': device_name,
                        'local': _is_local_ip(ip),
                        'protocol': 'http'
                    }
        return None
    
    print("  Checking localhost...")
    instance = probe_device('127.0.0.1', 'Localhost')
    if instance:
        kodi_instances.append(instance)
    
    print("  mDNS discovery...")
    mdns_results = discover_mdns(timeout=3)
    print(f"  mDNS found {len(mdns_results)} device(s)")
    
    for result in mdns_results:
        ip = result['ip']
        instance = probe_device(ip, result['name'])
        if instance:
            kodi_instances.append(instance)
    
    print("  SSDP discovery...")
    ssdp_results = discover_ssdp(timeout=5)
    print(f"  SSDP found {len(ssdp_results)} response(s)")
    
    unique_ssdp_ips = set()
    for result in ssdp_results:
        ip = result['ip']
        if ip in seen_ips or ip in unique_ssdp_ips:
            continue
        unique_ssdp_ips.add(ip)
        
        location = parse_location(result['response'])
        device_name = 'Unknown'
        if location:
            info = get_device_info(location)
            device_name = info['name']
        
        instance = probe_device(ip, device_name)
        if instance:
            kodi_instances.append(instance)
    
    if not kodi_instances:
        print("No KODI instances found.")
        return []
    
    print(f"\nFound {len(kodi_instances)} KODI instance(s):")
    for i, instance in enumerate(kodi_instances, 1):
        local_str = "(local)" if instance['local'] else "(remote)"
        proto = instance.get('protocol', 'http')
        print(f"{i}. {instance['name']} - {instance['ip']}:{instance['port']} ({proto}) {local_str}")
    
    return kodi_instances

def _is_local_ip(ip):
    """Check if IP belongs to this machine"""
    local_ips = ['127.0.0.1', 'localhost', '::1']
    if ip in local_ips:
        return True
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            if info[4][0] == ip:
                return True
    except:
        pass
    return False

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Discover KODI instances')
    parser.add_argument('-c', '--credential', action='append', metavar='USER:PASS',
                        help='KODI credential (user:pass), can be specified multiple times')
    args = parser.parse_args()
    
    credentials = None
    if args.credential:
        credentials = []
        for c in args.credential:
            parts = c.split(':', 1)
            if len(parts) == 2:
                credentials.append((parts[0], parts[1]))
    
    instances = discover_kodi(credentials)
    if instances:
        print("\n" + json.dumps(instances, indent=2))
    else:
        print("\n[]")
