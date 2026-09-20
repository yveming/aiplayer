# Reply for mpv issue #18498

> Paste the block below into the issue (comment from `@yveming`).

---

**TL;DR:** the `close(0)` is `drm_egl_uninit()` in
`video/out/opengl/context_drm_egl.c`; it is fixed by
`7bf2d9cee615408efeac288f59deb525193dc137` ("init fd to -1"), which is already
on master. `1a78f9fa8e` is unrelated.

You're right about the `close(0)`. I reproduced it under strace and caught the
exact call with gdb. It is in the DRM/EGL GPU context, not in `ao_pipewire`:

`video/out/opengl/context_drm_egl.c`, `drm_egl_init()` does
`p = ctx->priv = talloc_zero(ctx, struct priv)`, so
`p->drm_params.render_fd` is 0 until it is assigned near the very end of the
function (line ~621). On this headless box the probe fails earlier, at
`vo_drm_acquire_crtc()` (`Failed to set CRTC for connector 90: Permission
denied`), which jumps to

```c
err:
    drm_egl_uninit(ctx);
```

and `drm_egl_uninit()` does

```c
if (p->drm_params.render_fd != -1)
    close(p->drm_params.render_fd);   /* render_fd == 0 -> close(0) */
```

closing stdin.

strace of a single loadfile (fd-decorated) — thread `vo`:

```
close(11</dev/dri/card0>) = 0
close(9</dev/dri/card0>)  = 0
close(10</dev/dri/card0>) = 0
close(8</dev/dri/card0>)  = 0
close(0</dev/null<char 1:3>>) = 0
```

gdb, breakpoint on `close` with `$rdi == 0`:

```
Thread 14 "vo" hit Breakpoint, __GI___close (fd=0)
#0  __GI___close (fd=0)
#1  0x00005555556e98de in ?? ()   # tail jmp close@plt in drm_egl_uninit
#2  0x0000555555675d1f in ?? ()
...
```

This also explains the whole matrix: the first `loadfile` frees fd 0, then
`ao_pipewire`'s `pw_thread_loop` `epoll_create1()` takes the lowest free fd =
0, and the second `loadfile`'s failing VO probe closes fd 0 again — this time
the PipeWire epoll — so the AO thread spins in `epoll_wait(0)`/`EBADF` and
`pw_thread_loop_stop()` never joins. `--vo=null` / a working VO never runs
`drm_egl_uninit()`, hence no hang.

Note the actual fix is not `1a78f9fa8e` but:

```
7bf2d9cee615408efeac288f59deb525193dc137
vo/opengl/context_drm_egl: init fd to -1
```

which adds `p->drm_params.render_fd = -1;` (and `fd = -1`) right after the
`talloc_zero()`, and is already on master. That's why master would no longer
reproduce this. My earlier build (`v0.41.0-1049-g0b7ed670f`) had this fix but
was compiled without the PipeWire AO, so I couldn't confirm the full hang
there; the close(0) itself is gone either way.

So I think this can be closed as fixed by `7bf2d9cee` rather than `1a78f9f`.

Reproduction details, the strace/gdb output and the gdb script are attached
(`close0-evidence.zip`).

---
