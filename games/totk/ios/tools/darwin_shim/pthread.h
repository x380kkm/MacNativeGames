/* The part of Darwin's pthread.h that runtime/runtime.h and the Mac diagnostics of runtime/game_patches_v143.c name,
   for a host without it (ios/tools/export_ios_windows.py). The iOS export never starts a thread: these say so. */
#pragma once
#include <errno.h>
#include <stddef.h>

typedef unsigned long pthread_key_t;
typedef struct darwin_shim_thread *pthread_t;
typedef struct darwin_shim_thread_attr pthread_attr_t;

static inline int pthread_create(pthread_t *thread, const pthread_attr_t *attr, void *(*start)(void *), void *arg) {
    (void)attr; (void)start; (void)arg;
    *thread = NULL;
    return ENOSYS;
}
static inline int pthread_detach(pthread_t thread) { (void)thread; return ENOSYS; }
