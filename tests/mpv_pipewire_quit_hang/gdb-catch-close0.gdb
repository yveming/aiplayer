# Catch the first close() of fd 0 (stdin) in mpv and print the owning thread
# and a backtrace. This is the suspect call that frees fd 0 during failed VO
# probing, after which PipeWire's thread-loop epoll can be allocated as fd 0
# and later closed by the same path on a second loadfile.
#
# Usage:
#   gdb -q -batch -x gdb-catch-close0.gdb --args \
#       mpv --no-config --no-terminal --idle=yes --keep-open=yes <media>
#
# Tip: build/install mpv debug symbols for source-level frames.

set pagination off
set confirm off
set print thread-events off
set follow-fork-mode parent
set detach-on-fork on

# libc close(), first argument (rdi on x86-64) == 0
break close if $rdi == 0
commands
  silent
  printf "\n=== close(0) caught via close() ===\n"
  info threads
  printf "\n--- current thread backtrace ---\n"
  bt
  printf "=== end ===\n"
  kill
  quit
end

# Raw syscall fallback, in case close() is inlined or called as __close().
catch syscall close
condition $bpnum $rdi == 0
commands
  silent
  printf "\n=== close(0) caught via syscall ===\n"
  info threads
  printf "\n--- current thread backtrace ---\n"
  bt
  printf "=== end ===\n"
  kill
  quit
end

run
