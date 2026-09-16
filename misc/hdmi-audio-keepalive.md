# 锁屏/熄屏后 HDMI 无声（HDMI 音频保活）

> 适用环境：Ubuntu 24.04 / GNOME 46 / PipeWire 1.0.5 / 内核 6.8（uinput builtin）
> 解决日期：2026-09-16　涉及文件：`audio-keepalive.py`、`audio-keepalive.service`（本目录）

## 一、问题现象

- 锁屏/熄屏状态下用 musicbox、mpv、aiplayer 播放音乐，接 HDMI 的音响无声
- mpg123：从头到尾无声
- mpv：出几秒声，然后回到无声
- 切歌后几秒就没声

## 二、原理：为什么锁屏后 HDMI 就没声了

HDMI 音频不是一个独立声卡，它的存在由**显示链路**决定：

1. GPU 熄屏（DPMS Off）→ 显示管道关闭 → GPU 不再向 HDA codec 提供 ELD
2. codec 的 presence 变 0（`/proc/asound/card*/eld#*` 里 `monitor_present=0, eld_valid=0`）
3. 所有 HDMI 端口标记为不可用 → WirePlumber 把卡 profile 从 HDMI 切回 analog，**HDMI sink 被删除**
4. 播放中的流被迁移到 analog → 音响无声（播放器其实还在放）

而熄屏的触发者（读自 gsd-power 46 源码 `idle_configure()` / `handle_screensaver_active()`）：

- **锁屏（screensaver active）后，gsd-power 立即灭屏**，并挂一个**硬编码 30 秒**的
  "aggressive idle watch"：锁屏下任何活动后只要 30 秒无输入就再次灭屏
- 该路径**不读** `idle-delay`，写死常量 `SCREENSAVER_TIMEOUT_BLANK=30`
- D-Bus idle 抑制（`org.gnome.SessionManager.Inhibit`、Wayland idle-inhibit）只在
  **未锁屏**时有效（源码条件 `is_idle_inhibited && !screensaver_active`），锁屏后一律失效
- 结论：**只要会话锁着，任何客户端侧抑制都救不了；唯一杠杆是让 idle 监视器持续看到"输入活动"**

这就是为什么（mpv `--stop-screensaver`、`gnome-session-inhibit`、`idle-delay=0`）全部失败：
前者是 X11/合成器 API，后两者被上面两条源码逻辑直接绕过。

## 三、方案：audio-keepalive（内核输入层注入）

root 服务每 15 秒检测：PipeWire 里是否存在 **任何** `Stream/Output/Audio` 且状态 `running` 的流
（`pw-dump` 判定，播放器无关）。有 → 经内核 **uinput** 注入 ±1px 鼠标移动；没有 → 什么都不做。

### 行为矩阵（全部实测）

| 场景 | 行为 |
| --- | --- |
| 播放中（锁屏与否均可） | ~15 秒内自动点亮屏幕（`dpms: On`）→ ELD 有效 → HDMI sink 建立 → **持续有声** |
| 播放中 + 手动锁屏 | 锁屏界面常亮（`LockedHint=yes` + `dpms: On` 实测 50 秒不灭）→ 音乐不断 |
| 停止播放 | 注入停止 → ~30–45 秒照常熄屏（锁屏则 ~30 秒）→ 省电与安全恢复原样 |
| 暂停 | 流变 `idle`（corked）→ 同"停止"，~30–45 秒熄屏 |
| 暂停后恢复 | ~15–20 秒注入自动重新点亮屏幕 → HDMI 恢复 → 有声，**无需人工干预** |

### 设计要点

- **不依赖任何桌面 API**：注入走内核 uinput，换 KDE/XFCE/Windows 思路相同；
  检测走 PipeWire，任何 DE 下同样可用
- **播放器无关**：mpv（musicbox/aiplayer）、mpg123（libao→Pulse 兼容层）、ffplay、VLC、KODI、
  浏览器等一切 PipeWire/PulseAudio 客户端天然覆盖（实测 mpv 与 mpg123）
- **不播放时零干扰**：熄屏、自动锁、自动挂起等原有电源行为完全不变
- 已知边界：
  - 播放器显式绕过 PipeWire 直连 ALSA 硬件（如 `mpg123 -o alsa -d hw:1,3`）时检测不到；
    如需覆盖可再读 `/proc/asound/card*/pcm*/sub*/status`（内核级 PCM RUNNING 状态）
  - 暂停超过熄屏窗口后屏会灭，恢复播放后 ~20 秒自愈（如需暂停也保屏，
    把脚本里 `== 'running'` 改成 `in ('running', 'idle')`）

## 四、安装

本目录两个文件复制到系统位置（需要 sudo）：

```bash
sudo install -m 755 misc/audio-keepalive.py /usr/local/bin/audio-keepalive.py
sudo install -m 644 misc/audio-keepalive.service /etc/systemd/system/audio-keepalive.service
sudo systemctl daemon-reload
sudo systemctl enable --now audio-keepalive.service
```

注意：本服务以 root 运行，`/dev/uinput` 仅 root 可写，因此需要系统服务而非用户服务；
`service` 里的 `Environment=XDG_RUNTIME_DIR=/run/user/1001` 指向桌面会话用户的 uid，多用户机器按需修改。

## 五、验证清单

```bash
# 1) 服务活着、uinput 虚拟设备已创建
systemctl is-active audio-keepalive          # active
grep -H keepalive /sys/class/input/input*/name

# 2) mutter 是否接受了该设备（打开其 event 节点）
pid=$(pgrep -x gnome-shell); ls -la /proc/$pid/fd | grep event

# 3) 端到端：起播放 + 锁屏，等 50 秒（越过 30s 强制熄屏窗口）
musicbox play --id <id>
loginctl lock-session
sleep 50
cat /sys/class/drm/card0-HDMI-A-2/dpms        # 应为 On
grep -hE 'monitor_present|eld_valid' /proc/asound/card1/eld#2.3   # 应为 1/1
pactl list short sinks                        # 应出现 hdmi-surround 且 RUNNING
loginctl show-session 2 -p LockedHint         # yes（锁没破）

# 4) 反向：停止播放，~45 秒后应恢复熄屏
cat /sys/class/drm/card0-HDMI-A-2/dpms        # Off
```

## 六、踩坑记录（排错时按此对照）

1. **uinput 是内核 builtin**：本机 `modinfo uinput` 显示 `filename: (builtin)`，无需也不必
   `modprobe`/`modules-load.d`；若是模块型内核则需先加载。`/dev/uinput` 静态节点存在不代表能用。
2. **uinput 设备必须注册 `EV_KEY + BTN_LEFT/RIGHT/MIDDLE`**：只注册 REL 轴时，
   systemd `input_id` 不把它归类为鼠标（无 `ID_INPUT_MOUSE/POINTERS`），event 节点拿不到
   udev **seat 标签**，libinput 按 seat 标签过滤会直接无视 → mutter 根本不打开设备，
   注入完全无效（`gnome-shell` 的 fd 表里看不到该 event 节点可作判据）。
   只注册按键位、永不发送按键事件即可，无副作用。
3. **`uinput_user_dev` 必须写满 1116 字节**（name[80] + input_id 8 + ff_effects_max 4 + 4×64×4），
   内核按 `sizeof` 校验；事件写必须是**恰好一个** `struct input_event`（24 字节）每次 `write()`。
4. **mutter 验证注入是否生效**：`gdbus call --session --dest org.gnome.Mutter.IdleMonitor
   --object-path /org/gnome/Mutter/IdleMonitor/Core --method org.gnome.Mutter.IdleMonitor.GetIdletime`
   ——注入有效则 idletime 永远 < ~16 秒（服务轮询周期 15 秒）。
5. **`pkill -f mpg123` 会误杀自己**（-f 匹配完整命令行，自己的 shell 命令里也含该词），
   用 `pkill -x mpg123`。

## 七、与其它方案的对比

| 方案 | 结论 |
| --- | --- |
| `xset -d :0 -dpms` | 仅 X11 会话可用；Wayland 下 :0 是 Xwayland，无 DPMS 扩展，必然失败 |
| mpv `--force-window=yes --stop-screensaver` | 仅播放器自身有效；Wayland 用 zwp_idle_inhibit，**窗口被锁屏盖住即失效**，且 `--no-video`（musicbox 硬编码）直接禁用 |
| `gnome-session-inhibit` / D-Bus Inhibit | 锁屏后失效（同上源码条件），且依赖 GNOME |
| `idle-delay=0` | 无用：blank 路径不读 idle-delay；锁屏 30 秒照灭 |
| **audio-keepalive（本方案）** | 内核输入层，DE 无关、播放器无关、锁屏下依然有效 |
| 硬件 USB 鼠标抖动器 | 等效且真·零 OS 依赖，需额外硬件/USB 直通 |
