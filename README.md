# aiplayer

统一媒体播放控制工具：同时支持 **KODI**（JSON-RPC）与**本地 mpv**，
支持本地媒体库搜索/播放、IPTV 直播/回看（m3u + XMLTV EPG）。

- **KODI 模式**：媒体库/目录搜索、播放控制、PVR 频道、EPG、回看
- **本地模式（默认）**：mpv 播放本地文件（CIFS/NFS 挂载目录）
- **IPTV**：HTTP m3u + XMLTV EPG 直播与回看（无需 KODI）
- **豆瓣元数据（可选）**：中↔英片名别名扩展、演员/导演作品兜底搜索，
  失效自动降级为纯本地搜索

## 环境要求

- Python >= 3.10，[uv](https://docs.astral.sh/uv/)
- 本地播放需要 [mpv](https://mpv.io/)（KODI 模式不需要）
- 可选：局域网内的 KODI 设备、IPTV m3u/EPG 地址

## 安装 mpv

**Debian / Ubuntu**：

```bash
sudo apt update && sudo apt install mpv
```

**Windows**（PowerShell）：

```powershell
winget install mpv-player.mpv-CI.MSVC
```

若 mpv 不在 PATH 中，请在配置文件里用 `mpv.path` 指定可执行文件完整路径
（见下文"配置"）。

## 安装 aiplayer

```bash
# 在项目目录内安装为全局 uv 工具（安装后任意位置可用 aiplayer 命令）
uv tool install .

# 代码更新后升级
uv tool install . --upgrade
```

也可以不安装、在项目目录内直接运行：

```bash
uv run aiplayer <参数>
```

首次运行任何命令时，会在 `~/.config/aiplayer/` 自动生成默认配置文件。

## AI Skill 安装

`skills/aiplayer/SKILL.md` 是给 AI 代理（opencode、Claude Code、Hermes Agent等）使用
的技能说明。

```bash
npx skills add ./skills/aiplayer
```

**注意**：技能文件是静态拷贝，更新本仓库后需重新安装才能同步。

## 使用方法

命令格式：

```
aiplayer [连接参数] <动作> [查询词] [动作参数]
```

**模式选择（三选一）**：

| 方式 | 说明 |
|---|---|
| 无参数（默认） | 本地 mpv 模式，搜索 config.json 中配置的媒体目录 |
| `--host <IP> [--port] [--protocol tcp\|http] [--username --password]` | 直连 KODI |
| `--auto` | SSDP/mDNS 自动发现 KODI（约 5 秒，慢，偶尔用一次） |

**动作**：必填。`movie` 电影 | `video` 剧集 | `music` 音乐 | `tv` 电视直播/频道 |
`epg` 节目单 | `catchup` 回看 | `playfile`/`playfiles`/`enqueue` 文件播放 |
其余为播放控制；`stop` 会停止播放并退出本地 mpv 进程（下次播放重新启动），
mpv 未运行时这些动作提示 Nothing playing。不做任何自动推断。

```bash
# 电影 / 剧集 / 音乐（本地模式）
aiplayer movie "肖申克的救赎"
aiplayer video "黑暗物质 S03E04"
aiplayer music --artist "赵传" --album "我是一只小小鸟"

# IPTV（--m3u 接受 http(s) URL 或本地文件路径，也可来自配置）
aiplayer tv "湖南卫视" --m3u "http://192.168.100.2:8000/iptv/iptv.m3u"
aiplayer tv --m3u "iptv.m3u"
aiplayer epg "湖南卫视" --m3u "http://..." --date yesterday
aiplayer epg --m3u "http://..."                      # 不接频道 = 所有频道当前节目
aiplayer catchup "湖南卫视" --m3u "http://..." --date yesterday --time 18:30

# KODI 模式
aiplayer --host 192.168.100.11 --port 9090 movie "阿凡达三"

# 按路径直接播放
aiplayer playfile "G:/music/歌.flac"
aiplayer playfiles "G:/music/a.flac" "G:/music/b.flac"

# 播放控制（作用于最近一次播放所在的模式）
aiplayer pause
aiplayer next
aiplayer volume_up
aiplayer status

# JSON 输出（面向 AI/脚本，无交互提示）
aiplayer movie "阿凡达" --json
```

完整动作/参数说明见 `skills/aiplayer/SKILL.md`。

## 配置

配置文件：`~/.config/aiplayer/config.json`，首次运行自动生成，可手工编辑。
优先级：**CLI 参数 > 配置文件 > 内置默认**；空值表示"未配置"，程序会给出
提示而不是瞎猜。文件损坏时警告并回退默认值。
实际生成的文件是标准 JSON（无注释），下面为便于说明加了注释：

```jsonc
{
  "kodi": {
    "host": "",            // KODI IP，配好后免传 --host
    "port": 0,             // 0 = 默认（TCP 9090 / HTTP 8080）
    "username": "",
    "password": "",
    "protocol": "auto"     // tcp / http / auto
  },
  "iptv": {
    "m3u": "",             // IPTV m3u：http(s):// URL 或本地文件路径
    "epg": ""              // XMLTV EPG：URL 或路径，m3u 无 x-tvg-url 时的兜底
  },
  "mpv": {
    "path": ""             // mpv 可执行文件路径；空 = 在 PATH 中找 mpv
  },
  "media": {
    "movie": [],           // 本地媒体根目录（无内置默认，必须自行配置）
    "video": [],
    "music": []
  },
  "metadata": {
    "enabled": true,       // 豆瓣元数据扩展开关；false = 完全离线
    "timeout": 5           // 单次请求超时（秒）
  }
}
```

### 支持多语言自动匹配，以及按演员、导演搜索

电影/剧集搜索**无结果时**自动触发（不增加正常路径延迟）：

1. **别名重试**：通过豆瓣把查询词扩展为中文/外文别名集，逐个重试现有匹配
2. **人物兜底**：查询词是演员/导演时（豆瓣名人联想命中），用其作品列表
   与本地媒体做模糊匹配

任何网络/接口异常都会静默降级为纯本地搜索。豆瓣为非官方接口，可能失效。

## 测试

```bash
# 全部离线测试（无需 KODI/网络）
python tests/run_all.py          # 或 uv run python tests/run_all.py

# 单个套件
python tests/test_movie_smoke.py

# 真机 KODI 手工检查清单
# 见 tests/REAL_KODI_TESTS.md
```

## 注意事项

1. **媒体目录必须配置**：`media.*` 没有内置默认路径，未配置时本地搜索会
   打印配置提示。
2. **mpv 找不到**：查找顺序为 `--mpv-path` > 配置 `mpv.path` > PATH 中的
   `mpv` > 报错。Windows 用 winget 安装后若提示找不到，把 mpv.exe 完整
   路径写进 `mpv.path`（或启动时传 `--mpv-path`）。
3. **mpv 实例复用**：本地播放通过 mpv JSON IPC 控制
   （Windows 命名管道 `\\.\pipe\mpv-pipe`，Linux `/tmp/mpv-socket`），
   新命令复用已运行的 mpv 实例；`stop` 后进程退出，下次播放重新启动。
4. **播放控制跟随模式**：pause/next/volume 等作用于"最近一次播放"的模式，
   需带与播放时相同的 `--host`/`--auto` 参数（默认本地模式则不带）。
5. **回看兼容性**：部分盒子 PVR broadcastid 回看返回 -32602（如 CoreELEC），
   请使用 `--m3u <URL>` 自建回看 URL。
6. **EPG 来源优先级**：`--epg` > 配置 `iptv.epg` > m3u 的 `x-tvg-url`；
   三者都没有时程序会提示配置。
7. **Windows 控制台乱码**：中文输出异常时先执行 `chcp 65001` 或设置
   `PYTHONIOENCODING=utf-8`。
8. **`--json` 模式**：搜索结果以 JSON 数组输出且无交互提示，供 AI/脚本
   消费；**永不直接播放**（单命中也返回单元素数组），用 `playfile`/`playfiles`/`enqueue` 二次播放。
9. **自动发现很慢**：`--auto` 触发 SSDP/mDNS（约 5 秒），日常请用配置或
    `--host` 直连。
10. **config m3u 作用域**：`iptv.m3u` 仅在本地模式自动生效；KODI 模式需显式 `--m3u`，
    否则 PVR 动作（tv/epg/catchup）不会被劫持。KODI 不回 EPG 时，`catchup`/`epg`
    会自动用 m3u/XMLTV（config 或 `--m3u`/`--epg`）打补丁。

11. **catchup 占位符时区**：`catchup-source` 模板占位符（含 `{utc:}` 命名）统一按本地时间填充，
    与 KODI iptvsimple 的实际行为一致（实测后端 playseek 按本地解释）。