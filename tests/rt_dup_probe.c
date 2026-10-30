/* One image at two colour slots on crafted passes. test_rt_dup.py inserts production rt_dup_on, rt_dup_share_clears,
   rt_dup_other_slots, rt_dup_note_draw and rt_dup_unstored here; rt_dup_of comes from nvn_obj.h. argv[1]: "on" or "off",
   the state the switch and the build are expected to give. */
#include "nvn_obj.h"
#include <stdio.h>
#include <stdlib.h>

#define MLOG(...) do { } while (0)
/* the platform the production code is built for: a Mac's own headers define this macro too */
#undef TARGET_OS_IPHONE
#define TARGET_OS_IPHONE IOS_BUILD
#ifndef GAME_BOTW   /* the build rt_dup_share_clears is compiled in */
typedef struct { double red, green, blue, alpha; } MTLClearColor;
static struct { p_set_rt rt; uint8_t clear_c[8]; MTLClearColor cc[8]; } R;   /* the fields of nvn_mtl.m's replay state used here */
#endif

/* PRODUCTION_CODE */

static int fails;
#define CHECK(c) do { if (!(c)) { printf("FAILED line %d: %s\n", __LINE__, #c); fails++; } } while (0)

static void attach(int slot, uint64_t serial, uint32_t level, uint32_t layer, int drawn) {
    sd_att a = {0}; a.ser = serial; a.lv = level; a.sl = layer; a.idx = slot; a.drawn = (uint8_t)drawn;
    g_sd[g_nsd++] = a;
}
static int unstored(int i) { return rt_dup_unstored(&g_sd[i]); }
#define CHANNELS(slot) (0xfu << (4 * (slot)))   /* every channel of a slot in a channel mask */

static int noted(int slot, uint32_t channel_mask, uint32_t shader_color_mask) {
    sd_att a = {0}; a.idx = slot;
    rt_dup_note_draw(&a, channel_mask, shader_color_mask);
    return a.drawn;
}

/* What a draw leaves on a slot. This bookkeeping runs with the rule on and off. */
static void draw_notes(void) {
    CHECK(noted(2, CHANNELS(2), 1u << 2));
    /* one channel is enough, and the last slot is a slot */
    CHECK(noted(2, 1u << 8, 1u << 2));
    CHECK(noted(7, CHANNELS(7), 1u << 7));
    /* the slot's channels are masked off, or the shader does not output to it */
    CHECK(!noted(2, ~CHANNELS(2), 1u << 2));
    CHECK(!noted(2, CHANNELS(2), 1u << 1));
    /* a shader without reflection: the channel mask decides */
    CHECK(noted(2, CHANNELS(2), 0));
    CHECK(!noted(2, ~CHANNELS(2), 0));
    /* the depth and stencil planes are not colour slots */
    { sd_att a = {0}; a.idx = -1; a.depth = 1; rt_dup_note_draw(&a, ~0u, 0); CHECK(!a.drawn); }
    { sd_att a = {0}; a.idx = 0; a.depth = 2; rt_dup_note_draw(&a, ~0u, 0); CHECK(!a.drawn); }
    /* a later draw with the slot masked off does not take the mark back */
    { sd_att a = {0}; a.idx = 1; rt_dup_note_draw(&a, CHANNELS(1), 0); rt_dup_note_draw(&a, 0, 0); CHECK(a.drawn); }
}

static void stores_on(void) {
    /* no shared image */
    g_nsd = 0; attach(0, 1, 0, 0, 1); attach(1, 2, 0, 0, 1); attach(2, 3, 0, 0, 1);
    CHECK(!unstored(0) && !unstored(1) && !unstored(2));
    /* drawn through the first: the second is not stored */
    g_nsd = 0; attach(0, 1, 0, 0, 1); attach(1, 2, 0, 0, 0); attach(2, 1, 0, 0, 0);
    CHECK(!unstored(0) && !unstored(1) && unstored(2));
    /* drawn through the second only: that one is stored */
    g_nsd = 0; attach(0, 1, 0, 0, 0); attach(1, 2, 0, 0, 0); attach(2, 1, 0, 0, 1);
    CHECK(unstored(0) && !unstored(1) && !unstored(2));
    /* drawn through both, or through neither: the first, and one store is enough */
    g_nsd = 0; attach(0, 1, 0, 0, 1); attach(2, 1, 0, 0, 1);
    CHECK(!unstored(0) && unstored(1));
    g_nsd = 0; attach(0, 1, 0, 0, 0); attach(2, 1, 0, 0, 0);
    CHECK(!unstored(0) && unstored(1));
    /* three slots: one store */
    g_nsd = 0; attach(0, 1, 0, 0, 0); attach(1, 1, 0, 0, 0); attach(2, 1, 0, 0, 1);
    CHECK(unstored(0) && unstored(1) && !unstored(2));
    /* another level or layer is another image */
    g_nsd = 0; attach(0, 1, 0, 0, 0); attach(2, 1, 1, 0, 0); attach(3, 1, 0, 1, 0);
    CHECK(!unstored(0) && !unstored(1) && !unstored(2));
    /* the depth plane of a texture is not a colour slot, wherever it stands in the list */
    g_nsd = 0; attach(0, 1, 0, 0, 0); attach(-1, 1, 0, 0, 0); g_sd[1].depth = 1;
    CHECK(!unstored(0) && !unstored(1));
    g_nsd = 0; attach(-1, 1, 0, 0, 0); g_sd[0].depth = 1; attach(0, 1, 0, 0, 0);
    CHECK(!unstored(0) && !unstored(1));
    /* the mark a draw leaves decides: a draw through the second slot alone stores that one */
    g_nsd = 0; attach(0, 1, 0, 0, 0); attach(2, 1, 0, 0, 0);
    for (int i = 0; i < g_nsd; i++) rt_dup_note_draw(&g_sd[i], CHANNELS(2), 0);
    CHECK(unstored(0) && !unstored(1));
}

static void stores_off(void) {
    g_nsd = 0; attach(0, 1, 0, 0, 1); attach(2, 1, 0, 0, 0);
    CHECK(!unstored(0) && !unstored(1));
}

#ifndef GAME_BOTW
static tex_t tx[2];
static void pass(int n) { memset(&R, 0, sizeof R); R.rt.n = n; for (int i = 0; i < n; i++) R.rt.color[i] = &tx[i == 1]; }   /* slot 1 holds another image */

/* BOTW_RT_DUP_CLEARS() is the call site in nvn_mtl.m. */
static void clears_on(void) {
    /* a clear of the second slot reaches the first, and the other way round */
    pass(3); R.clear_c[2] = 1; R.cc[2].red = 0.5; BOTW_RT_DUP_CLEARS()
    CHECK(R.clear_c[0] && !R.clear_c[1] && R.clear_c[2] && R.cc[0].red == 0.5);
    pass(3); R.clear_c[0] = 1; R.cc[0].red = 0.25; BOTW_RT_DUP_CLEARS()
    CHECK(R.clear_c[0] && !R.clear_c[1] && R.clear_c[2] && R.cc[2].red == 0.25);
    /* three slots, the clear on the last */
    pass(4); R.clear_c[3] = 1; R.cc[3].red = 0.75; BOTW_RT_DUP_CLEARS()
    CHECK(R.clear_c[0] && R.clear_c[2] && R.clear_c[3] && R.cc[0].red == 0.75 && R.cc[2].red == 0.75);
    /* no clear stays no clear */
    pass(3); BOTW_RT_DUP_CLEARS()
    CHECK(!R.clear_c[0] && !R.clear_c[1] && !R.clear_c[2]);
    /* the same texture at another level is another image, at the same level it is the same */
    pass(2); R.rt.color[1] = &tx[0]; R.rt.has_cview[1] = 1; R.rt.cview[1].set_levels = 1; R.rt.cview[1].base_level = 1;
    CHECK(rt_dup_of(&R.rt, 1) == -1);
    CHECK(rt_dup_other_slots(&R.rt, 0) == 0 && rt_dup_other_slots(&R.rt, 1) == 0);
    R.rt.cview[1].base_level = 0;
    CHECK(rt_dup_of(&R.rt, 1) == 0);
    CHECK(rt_dup_other_slots(&R.rt, 0) == 1u << 1 && rt_dup_other_slots(&R.rt, 1) == 1u << 0);
}

/* The other copies of an image, asked from each of its slots: what a mid-pass clear reaches and a tile read refuses. */
static void other_slots_on(void) {
    pass(4);
    CHECK(rt_dup_other_slots(&R.rt, 0) == (1u << 2 | 1u << 3));
    CHECK(rt_dup_other_slots(&R.rt, 2) == (1u << 0 | 1u << 3));
    CHECK(rt_dup_other_slots(&R.rt, 3) == (1u << 0 | 1u << 2));
    /* slot 1 holds another image */
    CHECK(rt_dup_other_slots(&R.rt, 1) == 0);
    /* a slot past the end of the pass is not a slot of the pass */
    pass(3); R.rt.color[3] = &tx[0];
    CHECK(rt_dup_other_slots(&R.rt, 0) == 1u << 2);
    /* an empty slot holds no image */
    pass(3); R.rt.color[2] = NULL;
    CHECK(rt_dup_other_slots(&R.rt, 0) == 0 && rt_dup_other_slots(&R.rt, 2) == 0);
}

static void clears_off(void) {
    pass(3); R.clear_c[2] = 1; BOTW_RT_DUP_CLEARS()
    CHECK(!R.clear_c[0] && R.clear_c[2]);
    CHECK(rt_dup_other_slots(&R.rt, 0) == 0 && rt_dup_other_slots(&R.rt, 2) == 0);
}
#endif

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    int expected_on = !strcmp(argv[1], "on");
    CHECK(rt_dup_on() == expected_on);
    draw_notes();
    if (expected_on) stores_on(); else stores_off();
#ifndef GAME_BOTW
    tx[0].serial = 10; tx[1].serial = 11;
    if (expected_on) { clears_on(); other_slots_on(); } else clears_off();
#endif
    printf(fails ? "rt dup FAILED\n" : "rt dup ok\n");
    return fails != 0;
}
