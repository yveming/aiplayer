#!/usr/bin/env python3
"""音频播放期间注入 1px 鼠标抖动，防止 GNOME 锁屏后 30s 强制熄屏切断 HDMI 音频。
由 systemd 系统服务以 root 运行；不播放时不注入，熄屏/自动锁行为保持原样。"""
import fcntl, json, os, struct, subprocess, time

UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_RELBIT, UI_DEV_CREATE = 0x40045564, 0x40045565, 0x40045566, 0x5501
EV_SYN, EV_KEY, EV_REL, REL_X = 0x00, 0x01, 0x02, 0x00

def make_device():
    fd = os.open('/dev/uinput', os.O_WRONLY)
    for ev in (EV_SYN, EV_KEY, EV_REL):
        fcntl.ioctl(fd, UI_SET_EVBIT, ev)
    for btn in (0x110, 0x111, 0x112):  # BTN_LEFT/RIGHT/MIDDLE，仅注册不发送
        fcntl.ioctl(fd, UI_SET_KEYBIT, btn)
    for code in (0x00, 0x01):  # REL_X, REL_Y
        fcntl.ioctl(fd, UI_SET_RELBIT, code)
    # struct uinput_user_dev: name[80] + input_id(HHHH) + ff_effects_max(I) + abs[64][4]i
    os.write(fd, struct.pack('=80sHHHHI', b'audio-keepalive', 0x06, 0x01, 0x01, 0x01, 0)
             + b'\x00' * 1024)
    fcntl.ioctl(fd, UI_DEV_CREATE)
    time.sleep(0.1)
    return fd

def move(fd, dx):
    os.write(fd, struct.pack('llHHi', 0, 0, EV_REL, REL_X, dx))
    os.write(fd, struct.pack('llHHi', 0, 0, EV_SYN, 0, 0))

def audio_playing():
    try:
        out = subprocess.run(['pw-dump'], capture_output=True, timeout=10).stdout
        objs = json.loads(out)
    except Exception:
        return False
    for o in objs:
        info = o.get('info') or {}
        props = info.get('props') or {}
        if props.get('media.class') == 'Stream/Output/Audio' and info.get('state') == 'running':
            return True
    return False

def main():
    fd = make_device()
    sign = 1
    while True:
        if audio_playing():
            try:
                move(fd, sign)
                sign = -sign
            except OSError:
                fd = make_device()
        time.sleep(15)

if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        with open('/tmp/audio-keepalive.err', 'a') as f:
            f.write(time.strftime('%F %T ') + traceback.format_exc() + '\n')
        raise
