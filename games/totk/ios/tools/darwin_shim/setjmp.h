/* The host's setjmp.h with Darwin's sigjmp_buf, which runtime/runtime.h names, for a C library without it
   (ios/tools/export_ios_windows.py). Nothing in the iOS export jumps. */
#pragma once
#include_next <setjmp.h>

typedef jmp_buf sigjmp_buf;
