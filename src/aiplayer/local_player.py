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

def _find_mpv():
    p = shutil.which("mpv")
    if p:
        return p
    raise FileNotFoundError(
        "mpv not found. Install mpv and set PATH, or pass mpv_path="
    )


def _cmd(ipc_path, command):
    """Send a JSON command to mpv IPC and return the response."""
    payload = json.dumps({"command": command}) + "\n"
    data = payload.encode("utf-8")
    is_win = sys.platform == "win32"
    try:
        if is_win:
            k32 = ctypes.windll.kernel32
            handle = k32.CreateFileW(
                ipc_path,
                0xC0000000,
                3,
                None,
                3,
                0,
                None,
            )
            if handle == -1:
                return {"error": f"Cannot open named pipe {ipc_path}"}
            written = ctypes.c_ulong(0)
            k32.WriteFile(handle, data, len(data), ctypes.byref(written), None)
            buf = ctypes.create_string_buffer(65536)
            read = ctypes.c_ulong(0)
            k32.ReadFile(handle, buf, 65536, ctypes.byref(read), None)
            k32.CloseHandle(handle)
            raw = buf.raw[:read.value]
            text = raw.decode("utf-8", errors="replace")
            return json.loads(text) if text.strip() else {}
        else:
            s = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
            s.settimeout(10)
            s.connect(ipc_path)
            s.sendall(data)
            resp = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                resp += chunk
                try:
                    result = json.loads(resp.decode())
                    break
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
            s.close()
            return result if resp else {}
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
        self._cleanup_stale_socket()
        r = _cmd(self.ipc_path, ["get_property", "idle"])
        if r.get("error") in (None, "success"):
            r2 = _cmd(self.ipc_path, ["get_property", "mpv-version"])
            if r2.get("error") in (None, "success"):
                self._running = True
                return True
            self._kill_previous()
        self._start()
        self._wait_for_server(timeout=5)
        self._running = True
        return True

    def _cleanup_stale_socket(self):
        if sys.platform != "win32" and os.path.exists(self.ipc_path):
            try:
                os.unlink(self.ipc_path)
            except OSError:
                pass

    def _kill_previous(self):
        if sys.platform == "win32":
            import subprocess
            r = subprocess.run(["taskkill", "/f", "/im", "mpv.exe"], capture_output=True, text=True)
            if r.returncode == 0:
                time.sleep(1)
        else:
            import subprocess
            r = subprocess.run(["pkill", "-9", "mpv"], capture_output=True, text=True)
            if r.returncode == 0:
                time.sleep(1)

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

        self._ensure_running()
        return self._cmd(["cycle", "pause"])

    def stop(self):

        self._ensure_running()
        return self._cmd(["stop"])

    def set_pause(self, paused=True):

        self._ensure_running()
        return self._cmd(["set_property", "pause", paused])

    def go_to(self, direction):

        self._ensure_running()
        if direction == "next":
            return self._cmd(["playlist-next"])
        elif direction == "previous":
            return self._cmd(["playlist-prev"])
        return {"error": "unknown direction"}

    def seek(self, position):

        self._ensure_running()
        if position == "beginning":
            return self._cmd(["seek", 0, "absolute-percent"])
        if isinstance(position, (int, float)):
            return self._cmd(["seek", position, "relative"])
        return self._cmd(["seek", position])

    def volume_up(self):

        self._ensure_running()
        r = self._cmd(["get_property", "volume"])
        v = (r.get("data") or 50) + 10
        return self._cmd(["set_property", "volume", min(100, v)])

    def volume_down(self):

        self._ensure_running()
        r = self._cmd(["get_property", "volume"])
        v = (r.get("data") or 50) - 10
        return self._cmd(["set_property", "volume", max(0, v)])

    def set_volume(self, vol):

        self._ensure_running()
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

    def quit(self):

        self._ensure_running()
        if self.process:
            self._cmd(["quit"])
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None




