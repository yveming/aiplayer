# Root cause: `close(0)` from a failed DRM/EGL VO probe

## Summary

The hang is caused by `video/out/opengl/context_drm_egl.c` closing file
descriptor 0 (stdin). On a headless session the default `vo=gpu`/`gpu-next`
context probing tries the DRM/EGL context, fails late (`vo_drm_acquire_crtc()`
→ `Failed to set CRTC ...: Permission denied`), and then runs
`drm_egl_uninit()`. `p` comes from `talloc_zero()`, so
`p->drm_params.render_fd` is **0** until it is assigned near the end of
`drm_egl_init()`. An early `goto err` therefore reaches:

```c
if (p->drm_params.render_fd != -1)
    close(p->drm_params.render_fd);   /* render_fd == 0 -> close(0) */
```

This closes a descriptor mpv does not own.

## Why it hangs (two loadfiles required)

1. First `loadfile`: the failed `vo=gpu` DRM/EGL probe calls `close(0)`,
   closing stdin (`/dev/null`).
2. `ao=pipewire` then initialises and its `pw_thread_loop` calls
   `epoll_create1()`, which returns the lowest free fd: **0**.
3. Second `loadfile` (same audio format ⇒ AO reused, `init()` not re-entered):
   the same VO probe fails and `drm_egl_uninit()` calls `close(0)` again —
   this time closing the PipeWire thread-loop **epoll**.
4. The `mpv/ao/pipewire` thread's `epoll_wait(0)` now returns `EBADF` and
   busy-loops; `pw_thread_loop_stop()` can never join it, so `quit` hangs.

## Evidence

strace (`-f -tt -yy -e trace=close,...`) — thread `vo`:

```
close(11</dev/dri/card0>) = 0
close(9</dev/dri/card0>)  = 0
close(10</dev/dri/card0>) = 0
close(8</dev/dri/card0>)  = 0
close(0</dev/null<char 1:3>>) = 0      <-- close(0)
```

gdb breakpoint on `close` with `$rdi == 0` (script `gdb-catch-close0.gdb`):

```
Thread 14 "vo" hit Breakpoint 1.21, __GI___close (fd=0)
#0  __GI___close (fd=0) at .../close.c:26
#1  0x00005555556e98de in ?? ()
#2  0x0000555555675d1f in ?? ()
#3  0x0000555555675ec1 in ?? ()
#4  0x00005555556a82d0 in ?? ()
#5  0x0000555555696532 in ?? ()
#6  start_thread ()
```

The caller resolves to the DRM/EGL uninit tail call `jmp close@plt`
(linked address 0x18e344; frame #1 offset 0x1958de). That function calls
`eglMakeCurrent`, `eglDestroySurface`, `eglDestroyContext`,
`gbm_surface_destroy`, `eglTerminate`, `gbm_device_destroy`, then
`if (render_fd != -1) close(render_fd)`.

## Upstream fix

The real fix already exists on master but is **not** `1a78f9f`:

```
commit 7bf2d9cee615408efeac288f59deb525193dc137
Author: Kacper Michajłow
Date:   Mon Jul 6 11:14:32 2026

    vo/opengl/context_drm_egl: init fd to -1

    Instead of using zero initialized value. Otherwise an early init failure
    calls close(0), a descriptor we don't own, breaking whatever else happens
    to hold it.

--- a/video/out/opengl/context_drm_egl.c
+++ b/video/out/opengl/context_drm_egl.c
@@ -562,6 +562,8 @@ static bool drm_egl_init(struct ra_ctx *ctx)
     struct priv *p = ctx->priv = talloc_zero(ctx, struct priv);
+    p->drm_params.fd = -1;
+    p->drm_params.render_fd = -1;
```

`1a78f9f` ("avoid deadlock when starting thread loop") is unrelated; it only
changes when `pw_thread_loop_start()` runs in `pipewire_init_boilerplate()`,
which this repro never re-enters (the AO is reused).

## How to verify

- v0.41.0: one `loadfile` then `quit` → `close(0)` observed; two `loadfile`
  then `quit` → hang.
- Any build containing `7bf2d9cee`: the VO failure no longer touches fd 0.
