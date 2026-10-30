/* The preset frame rate from the launch to the game's start, with production code in main.m's order. test_ios_settings.py
   inserts production phone_holds_30, runtime_phone_fps, runtime_phone_fps_set (hle_nvn.c), apply_frame_env and
   apply_preset_frame_rate (main.m) here. */
#include "settings_map.h"
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#undef TARGET_OS_IPHONE
#define TARGET_OS_IPHONE 1   /* phone_holds_30 reads the variable only there */
#ifdef _WIN32
/* The MSVC runtime has _putenv_s, which removes a variable given the empty value. */
static int setenv(const char *key, const char *value, int overwrite) { return !overwrite && getenv(key) ? 0 : _putenv_s(key, value); }
static int unsetenv(const char *key) { return _putenv_s(key, ""); }
#endif

/* PRODUCTION_CODE */

static int fails;
#define CHECK(c) do { if (!(c)) { printf("FAILED line %d: %s\n", __LINE__, #c); fails++; } } while (0)

/* apply_settings: `launch_value` from the launch environment, then the preset row handed over with overwrite 0. */
static void launch(const char *launch_value, const char *row) {
    atomic_store(&g_phone_hold30, -1); unsetenv("TOTK_PHONE_FPS"); unsetenv("DM_PRESENT_HZ");
    if (launch_value) setenv("TOTK_PHONE_FPS", launch_value, 1);
    setenv("TOTK_PHONE_FPS", row, 0);
}
/* The touch controls' first draw, which asks for the rate its button shows (touch_pad.m drawRect:). */
static void pad_draws(void) { (void)runtime_phone_fps(); }
static int held_30(void) { const char *e = getenv("TOTK_PHONE_FPS"); return e && !strcmp(e, "30"); }

int main(void) {
    /* the pad drew before the pick, either way round */
    launch(NULL, "60"); pad_draws(); apply_preset_frame_rate("30");
    CHECK(runtime_phone_fps() == 30 && held_30());
    launch(NULL, "30"); pad_draws(); apply_preset_frame_rate("60");
    CHECK(runtime_phone_fps() == 60 && !getenv("TOTK_PHONE_FPS"));
    /* no pick: the row stands */
    launch(NULL, "30"); pad_draws(); apply_preset_frame_rate("30");
    CHECK(runtime_phone_fps() == 30 && held_30());
    launch(NULL, "60"); pad_draws(); apply_preset_frame_rate("60");
    CHECK(runtime_phone_fps() == 60 && !getenv("TOTK_PHONE_FPS"));
    /* a controller hid the pad, so nothing read the variable before the pick */
    launch(NULL, "60"); apply_preset_frame_rate("30");
    CHECK(runtime_phone_fps() == 30 && held_30());
    launch(NULL, "30"); apply_preset_frame_rate("60");
    CHECK(runtime_phone_fps() == 60 && !getenv("TOTK_PHONE_FPS"));
    /* a launch value goes as well, whether the pad drew or not */
    launch("30", "60"); pad_draws(); apply_preset_frame_rate("60");
    CHECK(runtime_phone_fps() == 60 && !getenv("TOTK_PHONE_FPS"));
    launch("30", "60"); apply_preset_frame_rate("60");
    CHECK(runtime_phone_fps() == 60 && !getenv("TOTK_PHONE_FPS"));
    /* a value that is not the row's changes nothing */
    launch(NULL, "30"); pad_draws(); apply_preset_frame_rate("45");
    CHECK(runtime_phone_fps() == 30 && held_30());
    printf(fails ? "frame pick FAILED\n" : "frame pick ok\n");
    return fails != 0;
}
