/* The Mach thread calls and types that the Mac watchpoint diagnostics of runtime/game_patches_v143.c use (frmwatch),
   for a host without them (ios/tools/export_ios_windows.py). The iOS export never sets a watchpoint: every call fails
   with KERN_FAILURE, which those diagnostics take as "no thread to watch". */
#pragma once
#include <stdint.h>

typedef int kern_return_t;
typedef unsigned natural_t;
typedef natural_t mach_port_t, mach_msg_type_number_t, thread_act_t, task_t;
typedef thread_act_t *thread_act_array_t;
typedef natural_t *thread_state_t;
typedef uintptr_t vm_address_t, vm_size_t;
typedef struct { uint64_t __bvr[16], __bcr[16], __wvr[16], __wcr[16], __mdscr_el1; } arm_debug_state64_t;

#define KERN_SUCCESS 0
#define KERN_FAILURE 5
#define ARM_DEBUG_STATE64 15
#define ARM_DEBUG_STATE64_COUNT ((mach_msg_type_number_t)(sizeof(arm_debug_state64_t) / sizeof(natural_t)))

static inline task_t mach_task_self(void) { return 0; }
static inline thread_act_t mach_thread_self(void) { return 0; }
static inline kern_return_t task_threads(task_t task, thread_act_array_t *list, mach_msg_type_number_t *count) {
    (void)task; *list = 0; *count = 0;
    return KERN_FAILURE;
}
static inline kern_return_t thread_get_state(thread_act_t thread, int flavor, thread_state_t state, mach_msg_type_number_t *count) {
    (void)thread; (void)flavor; (void)state; (void)count;
    return KERN_FAILURE;
}
static inline kern_return_t thread_set_state(thread_act_t thread, int flavor, thread_state_t state, mach_msg_type_number_t count) {
    (void)thread; (void)flavor; (void)state; (void)count;
    return KERN_FAILURE;
}
static inline kern_return_t thread_suspend(thread_act_t thread) { (void)thread; return KERN_FAILURE; }
static inline kern_return_t thread_resume(thread_act_t thread) { (void)thread; return KERN_FAILURE; }
static inline kern_return_t mach_port_deallocate(task_t task, mach_port_t name) { (void)task; (void)name; return KERN_FAILURE; }
static inline kern_return_t vm_deallocate(task_t task, vm_address_t address, vm_size_t size) {
    (void)task; (void)address; (void)size;
    return KERN_FAILURE;
}
