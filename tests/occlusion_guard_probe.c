/* The occlusion report rules on crafted submissions. test_occlusion_guard.py inserts production occl_guard_on,
   occl_settle and vis_count_lost here. argv[1]: "on" or "off", the guard state the switch and the build are expected to
   give. */
#ifdef _WIN32
#define _CRT_SECURE_NO_WARNINGS   /* this builds with -Werror, and the MSVC headers mark getenv deprecated */
#endif
#include "nvn_obj.h"
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>

#define MLOG(...) do { } while (0)
/* the platform the production code is built for: a Mac's own headers define this macro too */
#undef TARGET_OS_IPHONE
#define TARGET_OS_IPHONE IOS_BUILD
static int g_vis_counting;   /* nvn_mtl.m declares it among variables used nowhere here */

/* PRODUCTION_CODE */

#define MAX_OPS 8
static post_op ops[MAX_OPS];
static occl_tally tally;
static int fails;
#define CHECK(c) do { if (!(c)) { printf("FAILED line %d: %s\n", __LINE__, #c); fails++; } } while (0)
#define RAISED() ((int)atomic_load(&g_occl_raised))
#define GUARDED() ((int)atomic_load(&g_occl_guarded))

/* One submission of samples-passed queries: what each one counted, -1 for a query whose draw did not reach its counter. */
static void submit(int failed, int n, const long long *counted) {
    memset(ops, 0, sizeof ops);
    for (int i = 0; i < n; i++) { ops[i].kind = 3; ops[i].sum = counted[i] < 0 ? 0 : (uint64_t)counted[i]; ops[i].skipped = counted[i] < 0; }
    tally = occl_settle(ops, n, failed);
}
#define SUBMIT(failed, ...) submit(failed, (int)(sizeof((long long[]){__VA_ARGS__}) / sizeof(long long)), (long long[]){__VA_ARGS__})

/* A submission with a report of another counter and no samples-passed query. */
static void submit_without_queries(void) {
    memset(ops, 0, sizeof ops); ops[0].kind = 2;
    tally = occl_settle(ops, 1, 0);
    CHECK(tally.queries == 0 && tally.zeros == 0 && ops[0].sum == 0);
}

/* The frames of a hold: the zero is raised next to a real count, and it stays counted as measured. */
static void expect_hold(int frames) {
    for (int i = 0; i < frames; i++) {
        int guarded = GUARDED();
        SUBMIT(0, 5, 0);
        CHECK(ops[0].sum == 5 && ops[1].sum == 1); CHECK(GUARDED() == guarded + 1); CHECK(tally.queries == 2 && tally.zeros == 1);
    }
}
static void expect_trusted(void) {
    int guarded = GUARDED();
    SUBMIT(0, 5, 0);
    CHECK(ops[0].sum == 5 && ops[1].sum == 0); CHECK(GUARDED() == guarded);
}

static void guard_on(void) {
    /* before any frame of nothing but zeros, a zero next to a real count is trusted */
    expect_trusted(); CHECK(RAISED() == 0 && GUARDED() == 0);

    /* a frame of nothing but zeros reads visible, then the hold covers exactly OCCL_HOLD_FRAMES frames */
    SUBMIT(0, 0, 0, 0);
    CHECK(ops[0].sum == 1 && ops[1].sum == 1 && ops[2].sum == 1); CHECK(GUARDED() == 3 && RAISED() == 0); CHECK(tally.queries == 3 && tally.zeros == 3);
    expect_hold(OCCL_HOLD_FRAMES);
    expect_trusted();

    /* a submission without queries neither uses up the hold nor starts one */
    SUBMIT(0, 0);
    for (int i = 0; i < OCCL_HOLD_FRAMES + 5; i++) submit_without_queries();
    expect_hold(OCCL_HOLD_FRAMES);
    submit_without_queries();
    expect_trusted();

    /* another frame of nothing but zeros starts the hold again */
    SUBMIT(0, 0);
    expect_hold(OCCL_HOLD_FRAMES - 1);
    SUBMIT(0, 0);
    expect_hold(OCCL_HOLD_FRAMES);
    expect_trusted();

    /* a failed command buffer raises the zeros of its own submission and starts no hold */
    { int raised = RAISED(), guarded = GUARDED();
      SUBMIT(1, 5, 0);
      CHECK(ops[0].sum == 5 && ops[1].sum == 1); CHECK(RAISED() == raised + 1 && GUARDED() == guarded); CHECK(tally.zeros == 0); }
    expect_trusted();

    /* a report whose draw did not reach its counter reads 1 next to a real count, and starts no hold either */
    { int raised = RAISED();
      SUBMIT(0, -1, 5);
      CHECK(ops[0].sum == 1 && ops[1].sum == 5); CHECK(RAISED() == raised + 1); CHECK(tally.zeros == 0); }
    expect_trusted();

    /* a raised report is no counted sample: nothing was counted, so the frame rule still applies */
    { int raised = RAISED(), guarded = GUARDED();
      SUBMIT(0, -1, 0);
      CHECK(ops[0].sum == 1 && ops[1].sum == 1); CHECK(RAISED() == raised + 1 && GUARDED() == guarded + 1); CHECK(tally.zeros == 1); }
    expect_hold(OCCL_HOLD_FRAMES);
    expect_trusted();

    /* a command buffer that failed with nothing counted: every report comes from it, and the hold starts */
    { int raised = RAISED(), guarded = GUARDED();
      SUBMIT(1, 0, 0);
      CHECK(ops[0].sum == 1 && ops[1].sum == 1); CHECK(RAISED() == raised + 2 && GUARDED() == guarded); CHECK(tally.zeros == 0); }
    expect_hold(OCCL_HOLD_FRAMES);
    expect_trusted();

    /* an operation of another kind in a frame of nothing but zeros stays as it is */
    memset(ops, 0, sizeof ops);
    ops[0].kind = 3; ops[1].kind = 2; ops[2].kind = 3;
    tally = occl_settle(ops, 3, 0);
    CHECK(ops[0].sum == 1 && ops[1].sum == 0 && ops[2].sum == 1); CHECK(tally.queries == 2);
    expect_hold(OCCL_HOLD_FRAMES);
    expect_trusted();
}

static void guard_off(void) {
    /* nothing but zeros stays zeros, and there is no hold */
    SUBMIT(0, 0, 0, 0);
    CHECK(ops[0].sum == 0 && ops[1].sum == 0 && ops[2].sum == 0); CHECK(GUARDED() == 0 && RAISED() == 0); CHECK(tally.zeros == 3);
    expect_trusted();

    /* a failed command buffer changes nothing */
    SUBMIT(1, 5, 0);
    CHECK(ops[0].sum == 5 && ops[1].sum == 0); CHECK(RAISED() == 0);

    /* a draw held back while its shader is prepared raises its report on every platform */
    SUBMIT(0, -1);
    CHECK(ops[0].sum == 1); CHECK(RAISED() == 1 && GUARDED() == 0);
}

/* A draw that missed its counter marks the reports since the reset: with the guard, and while a query is counting. */
static void expect_count_lost(int marked) {
    g_vis_counting = 1; g_vis_skipped = 0; vis_count_lost();
    CHECK(g_vis_skipped == marked);
    g_vis_counting = 0; g_vis_skipped = 0; vis_count_lost();
    CHECK(!g_vis_skipped);
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    int expected_on = !strcmp(argv[1], "on");
    CHECK(occl_guard_on() == expected_on);
    if (expected_on) guard_on(); else guard_off();
    expect_count_lost(expected_on);
    printf(fails ? "occlusion guard FAILED\n" : "occlusion guard ok\n");
    return fails != 0;
}
