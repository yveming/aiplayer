# Evidence index — mpv PipeWire quit hang

All files captured on the same machine/session (Ubuntu 24.04.5, mpv 0.41.0,
PipeWire 1.0.5). See `../issue.md` for the full write-up.

## Reproduce / primary evidence
- `../mpv_repro_pipewire_quit_hang.sh` — minimal reproduction script.
- `pipewire-hang-mpv.log` — `--log-file` output of a run that HUNG (default
  `vo=gpu` fails headless, `ao=pipewire`).
- `pipewire-hang-backtrace.txt` — gdb `thread apply all bt full` of the hung
  process (main thread in `pw_thread_loop_stop`, ao thread in
  `epoll_wait(epfd=0)` returning `EBADF`).
- `pipewire-hang-proc.txt` — `/proc/<pid>/task/*/{stat,wchan,syscall}` at hang.
- `pipewire-hang-fds.txt` — `/proc/<pid>/fd` at hang (note: no `fd/0`).

## Secondary: same trigger, other AO backend
- `pulse-hang-backtrace.txt` — gdb backtraces with `--ao=pulse` (libpulse
  self-deadlock in `pa_stream_cork`).

## Ruling out the client library
- `libpipewire-1.4.9-hang-proc.txt` — same v0.41.0 binary + libpipewire 1.4.9,
  still hangs.
- `libpipewire-1.4.9-hang-fds.txt` — fd list for the same run.

## Controls (no hang)
- `hang-video-default.log` — hang case: stream goes `streaming -> paused` and
  never returns to `streaming`.
- `control-video-vonull.log` — same files with `--vo=null`; stream resumes.
- `control-video-vox11.log` — same files with `--vo=x11`; stream resumes.
- `control-video-wayland-success.log` — default `vo=gpu-next` succeeds via a real
  Wayland compositor; stream resumes.
- `control-audio-forcewindow.log` — audio-only + `--force-window=yes` (forces the
  same failing vo); no hang.

## PipeWire graph state at hang
- `pw-cli-info.txt`, `pw-top.txt`, `sink-inputs.txt`, `sinks.txt`

---

## Suggested submission mapping

Paste into the issue form fields (`issue.md` sections), then attach:

| Issue form field | Attach these |
|---|---|
| `Log File` | `../mpv_repro_pipewire_quit_hang.sh`, `pipewire-hang-mpv.log`, `pipewire-hang-backtrace.txt` |
| `Actual Behavior` | optionally drag `pipewire-hang-proc.txt`, `pipewire-hang-fds.txt` here |
| rest (controls, pulse, libpipewire, pw graph) | GitHub Gist link, or `evidence.zip` |

If a Gist/zip is used, add one line to the issue:
`Full evidence (all logs/backtraces/controls): <link>`
