/* The host's signal.h with the fields of Darwin's arm64 ucontext_t that the Mac watchpoint handler of
   runtime/game_patches_v143.c reads (runtime_diag_watch_trap), for a C library without them
   (ios/tools/export_ios_windows.py). The iOS export takes no signal. */
#pragma once
#include_next <signal.h>
#include <stdint.h>

struct darwin_shim_mcontext {
    struct { uint64_t __far; uint32_t __esr, __exception; } __es;
    struct { uint64_t __x[29], __fp, __lr, __sp, __pc; uint32_t __cpsr, __pad; } __ss;
};
typedef struct { struct darwin_shim_mcontext *uc_mcontext; } ucontext_t;
