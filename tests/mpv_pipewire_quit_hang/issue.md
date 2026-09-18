# mpv issue draft

**Suggested title:** `ao_pipewire: mpv hangs on quit after a second "loadfile replace" when the video output fails to initialize (ao thread spins in epoll_wait on a closed fd)`

> Paste the sections below into the mpv issue form, then attach the files
> listed at the bottom of this document ("Files to attach").

---

### mpv Information

```
mpv v0.41.0 Copyright © 2000-2025 mpv/MPlayer/mplayer2 projects
libplacebo version: v6.338.2
FFmpeg version: 6.1.1-3ubuntu5
FFmpeg library versions:
   libavcodec      60.31.102
   libavdevice     60.3.100
   libavfilter     9.12.100
   libavformat     60.16.100
   libavutil       58.29.100
   libswresample   4.12.100
   libswscale       7.5.100
```

### Other Information

```
- Linux version: Ubuntu 24.04.5 LTS (Noble), kernel 6.8.0-139-generic #139-Ubuntu SMP PREEMPT_DYNAMIC
- Source of mpv: PPA ppa:ubuntuhandbook1/mpv, package mpv 0.41.0-0ubuntu5~ubuntu2404
- PipeWire: pipewire 1.0.5, libpipewire-0.3-0t64 1.0.5-1ubuntu3.3 (32/64-bit)
- Session: SSH only. XDG_SESSION_TYPE=tty, no DISPLAY / WAYLAND_DISPLAY.
  The local seat0 session owns DRM master, so the default vo=gpu cannot initialize:
      [vo/gpu/drm] Failed to acquire DRM master: Permission denied
      [vo/gpu] Failed initializing any suitable GPU context!
      [cplayer] Video: no video
- Reproduces with --no-config, so user config/scripts are not involved.
```

### Reproduction Steps

Any two **video** files (with an audio track) work; I tested two 1080p MKVs.
Audio-only files do *not* reproduce (see the condition table below).

1. Run from a session where the default video output cannot be initialized
   (here: SSH without a display / DRM master; `mpv` ends up with `Video: no video`).
2. Use the attached script `mpv_repro_pipewire_quit_hang.sh`:

   ```sh
   ./mpv_repro_pipewire_quit_hang.sh <media1> <media2>
   ```

   It starts mpv with
   `--idle=yes --keep-open=yes --no-config --no-terminal --input-ipc-server=... --log-file=...`
   and then sends, over IPC:

   ```
   loadfile <media1> replace     # wait 2 s
   loadfile <media2> replace     # wait 2 s
   quit
   ```

3. `quit` replies `success`, but the mpv process never exits.

Reproduction rate on this machine: 5/5 runs of the script, 7/8 runs of a
parameterized loop (random 0.2–2 s delays between commands). It is a race.

### Expected Behavior

`quit` should terminate the mpv process.

### Actual Behavior

The IPC `quit` command returns `success` and mpv logs a normal shutdown up to
the end of the player core teardown, but the process stays alive:

- `mpv/ao/pipewire` is the only thread in state `R` (spinning);
- the main thread is blocked in `pw_thread_loop_stop()` → `pthread_join`;
- `SIGTERM` still terminates the process.

`/proc/<pid>/task/*/stat` at hang time:

```
mpv                    state=S wchan=futex_wait_queue
log                    state=S wchan=futex_wait_queue
worker                 state=S wchan=futex_wait_queue
mpv/ao/pipewire        state=R wchan=0
module-rt              state=S wchan=ep_poll
pw-data-loop           state=S wchan=ep_poll
```

gdb backtrace of the hung process:

```
Thread 1 (Thread ... "mpv"):
#0  __futex_abstimed_wait_common64 (...)
#2  __GI___futex_abstimed_wait_cancelable64 (...)
#3  __pthread_clockjoin_ex (...) at ./nptl/pthread_join_common.c:102
#4  pw_thread_loop_stop () from /lib/x86_64-linux-gnu/libpipewire-0.3.so.0
#5  ... (mpv, no symbols) ...
#6  ... (mpv, no symbols) ...
#9  main ()

Thread 36 (Thread ... "mpv/ao/pipewire"):
#0  epoll_wait (epfd=0, events=..., maxevents=32, timeout=-1) at epoll_wait.c:30
        sc_ret = -9            # -EBADF
#1  ... libspa-support.so
#2  ... libspa-support.so
#3  ... libpipewire-0.3.so.0
#4  start_thread ...
```

At hang time fd 0 is **closed** in the process (it was `/dev/null` at start), so
the PipeWire thread loop keeps calling `epoll_wait()` on an invalid fd, gets
`EBADF`, and busy-loops; `pw_thread_loop_stop()` can therefore never join it.
(`/proc/<pid>/fd` list attached; there is no `fd/0` entry.)

### Log File

Attached (`--log-file` output of a run that hung). The log ends mid-teardown,
after the player core is gone and while the audio output is being destroyed:

```
[cplayer] finished playback, success (reason 3)
[cplayer] Running hook: ytdl_hook/on_after_end_file
[cplayer] Exiting... (Quit)
...
[osc] Destroying client handle...
```

### Sample Files

Cannot share the original files, but any video file works. Tested with:

```
Casino.Royale...DTS-HD.x264-Grym.mkv : hevc 1920x800 10-bit, dts 48000 Hz 5.1
No.Time.To.Die...DDP5.1...mkv        : h264 1920x800,        eac3 48000 Hz 5.1
```

### Additional analysis / conditions

Bisecting (8 runs per condition unless noted; same machine/session):

| condition                                                        | hangs |
|------------------------------------------------------------------|-------|
| two MKVs, default (`vo=gpu` fails headless, `ao=pipewire`)       | 7/8 |
| two MKVs, `--vo=null`                                            | 0/8 |
| two MKVs, `--vo=x11` (fails fast)                                | 0/8 |
| two MKVs, `--vo=wlshm` / `--vo=dmabuf-wayland` (no compositor; fails) | 0/8 |
| two MKVs, `--gpu-context=wayland` (no compositor; fails)         | 0/8 |
| two MKVs, **real Wayland compositor** (`WAYLAND_DISPLAY` set; vo succeeds) | 0/4 |
| two MKVs, `--no-video`                                           | 0/8 |
| two MKVs, `--ao=null`                                            | 0/6 |
| two MKVs, `--ao=pulse`                                           | 5/8 |
| only one `loadfile replace`, then quit                           | 0/6 |
| `stop` immediately before each `loadfile`                        | 4/6 |
| audio-only (48 kHz stereo + 44.1 kHz stereo)                     | 0/8 |
| audio-only, same format (same file twice)                        | 0/8 |
| audio-only + `--force-window=yes` (forces the same failing vo)   | 0/8 |
| audio-only, same format + `--force-window=yes`                   | 0/8 |
| audio-only + heavy CPU load (both cores busy)                    | 0/6 |
| audio-only + `--force-window=yes` + heavy CPU load               | 0/6 |

Observations:

- A **second** `loadfile replace` is required (a single load never hangs).
- It is **not** simply "a failed video output": audio-only with
  `--force-window=yes` also runs the same failing `vo=gpu` path (and even with
  heavy CPU load), yet never hangs. A real **video track** in the container is
  required.
- It is **not** simply "any failed video output": `--vo=x11`, `--vo=wlshm`,
  `--vo=dmabuf-wayland` and `--gpu-context=wayland` all fail here and deselect
  the video track, yet do not hang. The (default, slow, multi-context)
  `vo=gpu`/`gpu-next` probing path is what makes the difference. Conversely,
  when the video output actually **succeeds** — either `--vo=null` or a real
  Wayland compositor (`WAYLAND_DISPLAY` set, `vo=gpu-next` registers
  `wl_compositor` and allocates GPU memory) — the audio stream resumes
  (`paused -> streaming`) and there is no hang.
  (Note: `--vo=wayland` is not a valid VO name in this build; the Wayland VOs
  are `wlshm` and `dmabuf-wayland`, plus `gpu`/`gpu-next` with a Wayland
  context.)
- A closer look at the hang shows the reused AO stream is left **paused and
  never resumed**. On the second `loadfile replace` (same audio format, so the
  AO is reused), the log goes:

  ```
  [ao/pipewire] Stream state changed: old_state=streaming state=paused   # on replace
  [mkv] deselect track 0
  [cplayer] Video: no video
  [cplayer] Starting playback...
  [cplayer] playback restart complete @ 0.000000, audio=playing, video=eof
  # ...but no "paused -> streaming" state change follows, unlike the non-hanging cases
  ```

  With `--vo=null`, `--vo=x11`, `--no-video` or audio-only, the same sequence
  *does* show `old_state=paused state=streaming` right after playback restart,
  and quitting then works. So in the hanging case `ao_pipewire` never leaves the
  paused state before teardown, and `uninit()` → `pw_thread_loop_stop()` then
  joins a thread stuck in `epoll_wait()` on an invalid fd.

- `--ao=null` avoids it, but `--ao=pulse` **also hangs** (5/8), with a different
  stack (libpulse self-deadlock):
  main thread in `pa_stream_cork()` → `pa_mainloop_wakeup()` → blocked `write()`
  to the wakeup pipe, while the `threaded-ml` thread is blocked in
  `pa_mainloop_poll()` on the mutex held by the main thread.
  This suggests the mpv-side trigger is in the AO teardown/reload path and the
  PipeWire-specific stack is one manifestation of it.

### Additional testing

- Reproduces with `--no-config`.
- The `mpv/ao/pipewire` thread spinning is visible in a live process
  (`state=R`) and in gdb (`epoll_wait(epfd=0, ..., -1)` returning `EBADF`).

- **The client library was ruled out.** I ran the *same* v0.41.0 binary against
  a newer **libpipewire 1.4.9** client (Debian `libpipewire-0.3-0t64` +
  matching `libspa-0.2-modules` + `libpipewire-0.3-modules`, selected via
  `LD_LIBRARY_PATH` / `SPA_PLUGIN_DIR` / `PIPEWIRE_MODULE_DIR`, still talking to
  the same PipeWire 1.0.5 daemon). It still hangs **7/8**, with the identical
  state (`mpv/ao/pipewire` running, fd 0 closed). So this is not fixed by a
  newer libpipewire.

- I tested a recent git build, `mpv v0.41.0-1049-g0b7ed670f` (built
  2026-09-17). That build is compiled **without** the PipeWire AO (it only
  provides `pulse` and `alsa`), so the exact PipeWire stack could not be
  re-tested on master. Under the same headless + failed-`vo` conditions, its
  `--ao=pulse` did **not** hang in 8/8 runs, whereas v0.41.0 with `--ao=pulse`
  hangs 5/8. (Caveat: that build bundles newer ffmpeg/libplacebo/libpulse, so
  this is suggestive rather than conclusive.)

### Root-cause hypothesis (ao_pipewire.c)

Observed behaviour:

- The second `loadfile replace` has the same audio format as the first, so the
  AO is **reused** — `ao_pipewire`'s `init()` is *not* called again.
- On replace the stream goes `streaming -> paused`; after
  `playback restart complete ... audio=playing` it never returns to
  `streaming` (no `paused -> streaming` event), unlike every non-hanging case.
- On `quit`, `uninit()` calls `pw_thread_loop_stop()`; the AO thread is stuck
  in `epoll_wait()` on a closed fd (fd 0) and never exits, so the join blocks
  forever.

So the failure is in the **AO reuse / pause-resume / teardown** path of
`ao_pipewire`, not necessarily in `init()`. The `--ao=pulse` variant deadlocks
inside libpulse during the same `loadfile replace` + `quit` sequence, which is
consistent with the trigger being in mpv's AO teardown/reload sequencing rather
than in one specific backend.

For completeness, v0.41.0's `init()` does contain a separate, related defect:
`wait_for_init_done()` only waits 50 ms, and on timeout `p->init_state` stays
`INIT_STATE_NONE` while `init()` still returns success:

```c
/* v0.41.0 */
if (p->init_state == INIT_STATE_ERROR)
    goto error;
return 0;   /* returns success even with a half-initialized stream */
```

master changes this to:

```c
/* master, commit e5486b96d7 */
if (p->init_state != INIT_STATE_SUCCESS)
    goto error;
```

That defect does not appear to be what triggers *this* repro (the AO is reused,
so `init()` is not re-entered), but it is in the same area and may be related
to other manifestations. `1a78f9fa8e` additionally avoids a deadlock when
starting the thread loop; neither commit is in v0.41.0.

### Request

Could you check whether this still reproduces on current master with a build
that has the PipeWire AO enabled (`-Dpipewire=enabled`)? If master no longer
hangs, this can be closed as fixed there; otherwise the backtraces and state
above should point at the AO teardown/reload path.

### I carefully read all instructions and confirm the following

- [x] I tested and confirmed that the issue exists with the latest release version or newer.
- [x] I provided all required information including system and mpv version.
- [x] I produced the log file with the exact same set of files, parameters, and conditions used in "Reproduction Steps", with the addition of `--log-file=output.txt`.
- [x] I produced the log file while the behaviors described in "Actual Behavior" were actively observed.
- [x] I attached the full, untruncated log file.
- [x] I attached the backtrace in the case of a crash.

---

## Files to attach (from this machine)

- `~/mpv_pipewire_quit_hang/mpv_repro_pipewire_quit_hang.sh`
- `~/mpv_pipewire_quit_hang/evidence/pipewire-hang-mpv.log`  (log file, hung run)
- `~/mpv_pipewire_quit_hang/evidence/pipewire-hang-backtrace.txt` (gdb, `thread apply all bt full`)
- `~/mpv_pipewire_quit_hang/evidence/pipewire-hang-proc.txt`
- `~/mpv_pipewire_quit_hang/evidence/pipewire-hang-fds.txt`
- `~/mpv_pipewire_quit_hang/evidence/pulse-hang-backtrace.txt` (secondary, `--ao=pulse`)
- `~/mpv_pipewire_quit_hang/evidence/libpipewire-1.4.9-hang-proc.txt` (libpipewire ruled out)
- `~/mpv_pipewire_quit_hang/evidence/libpipewire-1.4.9-hang-fds.txt`
- `~/mpv_pipewire_quit_hang/evidence/hang-video-default.log` (hang; stream never resumes)
- `~/mpv_pipewire_quit_hang/evidence/control-audio-forcewindow.log` (no hang; control)
- `~/mpv_pipewire_quit_hang/evidence/control-video-vonull.log` (no hang; control)
- `~/mpv_pipewire_quit_hang/evidence/control-video-vox11.log` (no hang; control)
- `~/mpv_pipewire_quit_hang/evidence/control-video-wayland-success.log` (no hang; vo succeeds via real compositor)
- `~/mpv_pipewire_quit_hang/evidence/{pw-cli-info,pw-top,sink-inputs,sinks}.txt`
