/* usleep, the one function of Darwin's unistd.h that the Mac diagnostics of runtime/game_patches_v143.c call, for a host
   without it (ios/tools/export_ios_windows.py). The iOS export never waits: it returns at once with an error. */
#pragma once

static inline int usleep(unsigned microseconds) { (void)microseconds; return -1; }
