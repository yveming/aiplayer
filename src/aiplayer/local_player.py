#!/usr/bin/env python3
"""
Local media player using mpv with JSON IPC.

Linux/macOS: Unix domain socket  (/tmp/mpv-socket)
Windows:      Named pipe          (\\\\.\\pipe\\mpv-pipe)
"""

import ctypes
import json
import os
import shutil
import socket as _socket
import subprocess
import sys
import time


MPV_IPC_PATH = "/tmp/mpv-socket" if sys.platform != "win32" else r"\\.\pipe\mpv-pipe"


_K32 = None


def _find_mpv():
    p = shutil.which("mpv")
    if p:
        return p
    raise FileNotFoundError(
        "mpv not found. Install mpv and set PATH, or pass mpv_path="
    )


def _extract_reply(resp):
    """Extract the command reply from buffered IPC output.

    Returns (reply, done): done=True once a complete non-event JSON line
    has been parsed. Incomplete trailing lines and mpv event lines are
    skipped so the caller can keep reading.
    """
    for line in resp.decode("utf-8", errors="replace").split("\n")[:-1]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(obj, dict) and "event" in obj:
            continue
        return obj, True
    return {}, False


def _win_kernel32():
    global _K32
    if _K32 is None:
        import ctypes.wintypes as wt
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.restype = wt.HANDLE
        k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD,
                                    wt.LPVOID, wt.DWORD, wt.DWORD, wt.HANDLE]
        k32.WriteFile.restype = wt.BOOL
        k32.WriteFile.argtypes = [wt.HANDLE, wt.LPCVOID, wt.DWORD,
                                  ctypes.POINTER(wt.DWORD), wt.LPVOID]
        k32.ReadFile.restype = wt.BOOL
        k32.ReadFile.argtypes = [wt.HANDLE, wt.LPVOID, wt.DWORD,
                                 ctypes.POINTER(wt.DWORD), wt.LPVOID]
        k32.CloseHandle.restype = wt.BOOL
        k32.CloseHandle.argtypes = [wt.HANDLE]
        _K32 = (k32, wt)
    return _K32


def _win_cmd(ipc_path, data, timeout=10):
    """Send one command over the mpv named pipe and read the reply."""
    k32, wt = _win_kernel32()
    invalid = ctypes.c_void_p(-1).value
    handle = k32.CreateFileW(ipc_path, 0xC0000000, 3, None, 3, 0, None)
    if handle is None or handle == invalid:
        return {"error": f"Cannot open named pipe {ipc_path}"}
    try:
        written = wt.DWORD(0)
        if not k32.WriteFile(handle, data, len(data), ctypes.byref(written), None):
            return {"error": f"WriteFile failed (winerror {ctypes.get_last_error()})"}
        if written.value != len(data):
            return {"error": f"WriteFile short write ({written.value}/{len(data)})"}
        buf = ctypes.create_string_buffer(65536)
        read = wt.DWORD(0)
        resp = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not k32.ReadFile(handle, buf, 65536, ctypes.byref(read), None):
                break
            if read.value == 0:
                time.sleep(0.05)
                continue
            resp += buf.raw[:read.value]
            reply, done = _extract_reply(resp)
            if done:
                return reply
        if not resp:
            return {"error": f"No response from mpv IPC at {ipc_path}"}
        reply, _ = _extract_reply(resp + b"\n")
        return reply
    finally:
        k32.CloseHandle(handle)


def _cmd(ipc_path, command):
    """Send a JSON command to mpv IPC and return the response."""
    payload = json.dumps({"command": command}) + "\n"
    data = payload.encode("utf-8")
    try:
        if sys.platform == "win32":
            return _win_cmd(ipc_path, data)
        s = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect(ipc_path)
        s.sendall(data)
        resp = b""
        reply, done = {}, False
        while not done:
            chunk = s.recv(4096)
            if not chunk:
                break
            resp += chunk
            reply, done = _extract_reply(resp)
        s.close()
        if not done and resp:
            reply, _ = _extract_reply(resp + b"\n")
        return reply
    except Exception as e:
        return {"error": str(e)}



class MpvPlayer:
    def __init__(self, mpv_path=None):
        self.mpv_path = mpv_path or _find_mpv()
        self.ipc_path = MPV_IPC_PATH
        self.process = None
        self._running = False

    def _ensure_running(self):
        if self._running:
            return True
        r = _cmd(self.ipc_path, ["get_property", "idle"])
        if r.get("error") in (None, "success"):
            self._running = True
            return True
        self._cleanup_stale_socket()
        self._start()
        self._wait_for_server(timeout=5)
        self._running = True
        return True

    def _probe(self):
        """Return True when an mpv IPC endpoint answers; refresh _running."""
        r = _cmd(self.ipc_path, ["get_property", "idle"])
        ok = r.get("error") in (None, "success")
        self._running = ok
        return ok

    def _cleanup_stale_socket(self):
        if sys.platform != "win32" and os.path.exists(self.ipc_path):
            try:
                os.unlink(self.ipc_path)
            except OSError:
                pass

    def _start(self):
        args = [self.mpv_path, "--idle=yes", "--keep-open=yes",
                f"--input-ipc-server={self.ipc_path}", "--no-terminal"]
        self.process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def _wait_for_server(self, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = _cmd(self.ipc_path, ["get_property", "idle"])
            if r.get("error") in (None, "success"):
                return True
            time.sleep(0.2)

        if self.process and self.process.poll() is not None:
            raise RuntimeError(
                f"mpv exited immediately (code {self.process.returncode}). "
                f"Check {self.mpv_path}."
            )
        raise TimeoutError(
            f"mpv IPC server not ready at {self.ipc_path} after {timeout}s"
        )

    def _cmd(self, command):
        return _cmd(self.ipc_path, command)

    def play(self, path):

        self._ensure_running()
        return self._cmd(["loadfile", path, "replace"])

    def play_pause(self):

        if not self._probe():
            return {"error": "not running"}
        return self._cmd(["cycle", "pause"])

    def stop(self):

        if not self._probe():
            return {"error": "not running"}
        r = self._cmd(["stop"])
        self._cmd(["quit"])
        self._running = False
        if self.process:
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
        return r

    def set_pause(self, paused=True):

        if not self._probe():
            return {"error": "not running"}
        return self._cmd(["set_property", "pause", paused])

    def go_to(self, direction):

        if not self._probe():
            return {"error": "not running"}
        if direction == "next":
            return self._cmd(["playlist-next"])
        elif direction == "previous":
            return self._cmd(["playlist-prev"])
        return {"error": "unknown direction"}

    def seek(self, position):

        if not self._probe():
            return {"error": "not running"}
        if position == "beginning":
            return self._cmd(["seek", 0, "absolute-percent"])
        if isinstance(position, (int, float)):
            return self._cmd(["seek", position, "relative"])
        return self._cmd(["seek", position])

    def volume_up(self):

        if not self._probe():
            return {"error": "not running"}
        r = self._cmd(["get_property", "volume"])
        v = (r.get("data") or 50) + 10
        return self._cmd(["set_property", "volume", min(100, v)])

    def volume_down(self):

        if not self._probe():
            return {"error": "not running"}
        r = self._cmd(["get_property", "volume"])
        v = (r.get("data") or 50) - 10
        return self._cmd(["set_property", "volume", max(0, v)])

    def set_volume(self, vol):

        if not self._probe():
            return {"error": "not running"}
        return self._cmd(["set_property", "volume", max(0, min(100, vol))])

    def get_properties(self, props):
        result = {}
        for p in props:
            r = self._cmd(["get_property", p])
            if r.get("error") in (None, "success"):
                result[p] = r.get("data")
        return result

    def playlist_append(self, path):

        self._ensure_running()
        return self._cmd(["loadfile", path, "append"])

    def play_next(self):

        self._ensure_running()
        return self._cmd(["playlist-next"])

    def playlist_clear(self):

        self._ensure_running()
        return self._cmd(["playlist-clear"])

    def playlist_play_index(self, index):

        self._ensure_running()
        return self._cmd(["set_property", "playlist-pos", index])

    def status(self):
        """Get current playback status."""
        r = self._cmd(["get_property", "path"])
        if r.get("error") not in (None, "success"):
            return {}
        info = {}
        for prop in ["path", "filename", "time-pos", "duration", "percent-pos", "metadata"]:
            r = self._cmd(["get_property", prop])
            if r.get("error") in (None, "success"):
                info[prop] = r.get("data")
        return info

