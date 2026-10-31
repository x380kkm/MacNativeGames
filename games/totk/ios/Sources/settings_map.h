#pragma once
#include <stdint.h>

/* The iPad Settings pane as the environment the runtime reads at launch. Kept free of UIKit so
   tests/test_ios_settings.py checks the tables on a Mac.
   Two layers, chosen by the pane's "Use custom settings" switch (TOTK_CUSTOM_PICTURE):
   - presets (off, the default): Full HD (TOTK_DOCKED) and the frame-rate row (TOTK_PHONE_FPS);
   - custom (on): the picture mode, the scene resolution and the frame-rate cap.
   A layer owns its keys completely, so the two never write the same environment variable. */
typedef struct {
    const char *drawable;        /* TOTK_IOS_DRAWABLE_H: rows, "0" = the panel's native pixels */
    const char *output_upscale;  /* TOTK_MFX_OUTPUT: MetalFX spatial scaling of the canvas into the drawable */
    const char *operation;       /* TOTK_OPERATION_MODE: "handheld" or "docked" (the 1080 mode uses the docked settings) */
    const char *scene_upscale;   /* TOTK_MFX_UPSCALE: "1" forces it on (the output upscale needs it); NULL keeps the pane's switch */
} totk_picture_env;

typedef struct {
    const char *present_hz;      /* DM_PRESENT_HZ, NULL: leave unset */
    const char *phone_fps;       /* TOTK_PHONE_FPS, NULL: leave unset */
} totk_frame_env;

/* The preset picture: 720p, Full HD (TOTK_DOCKED) or HD at the device's own pixels (TOTK_NATIVE_PICTURE, which wins): its
   own drawable, scene and output upscale; the operation mode follows. */
enum { TOTK_PICTURE_720, TOTK_PICTURE_1080, TOTK_PICTURE_SCREEN };
typedef struct {
    const char *operation;
    const char *drawable;        /* NULL: leave the runtime's handheld default; "0": the screen's own pixels */
    const char *scene;           /* TOTK_RENDER_RES, "0": the game's own size, NULL: leave the runtime's default */
    const char *output_upscale;
    const char *scene_upscale;   /* TOTK_MFX_UPSCALE: "1" forces it on (the output upscale needs it); NULL keeps the pane's switch */
} totk_preset_env;

/* mode is one of the pane's picture values; 0 when it is not (out is untouched). */
int totk_picture_env_build(const char *mode, totk_picture_env *out);
/* cap is "30" or "60". 0 when cap is not a pane value (out is untouched). The iOS display link is fixed at 60 Hz, so
   there is no higher entry: the uncapped path could never show more than 60 either. */
int totk_frame_env_build(const char *cap, totk_frame_env *out);
/* picture: TOTK_PICTURE_*. Always succeeds. */
int totk_preset_env_build(int picture, totk_preset_env *out);
/* fps is the pane's preset row, "60" (up to the display's rate) or "30" (held). 0 for anything else. */
int totk_preset_frame_env_build(const char *fps, totk_frame_env *out);

const char *totk_picture_mode_default(void);
const char *totk_frame_cap_default(void);

/* The Large textures row (TOTK_LARGE_TEXTURES, outside both layers): how the Metal copies of large mipmapped textures
   keep their levels (d2r_gfx nvn_mtl.m mip_drop_of, mip_keep_mode). NULL: leave the variable unset. */
typedef struct {
    const char *mip_keep;        /* TOTK_MIP_KEEP */
    const char *mip_drop;        /* TOTK_MIP_DROP */
} totk_texture_env;

/* mode is one of the row's values; 0 when it is not (out is untouched). */
int totk_texture_env_build(const char *mode, totk_texture_env *out);
const char *totk_large_textures_default(void);
/* What the row's "auto" means on this device: available_bytes is os_proc_available_memory() at launch, 0 when unknown. */
const char *totk_large_textures_auto(uint64_t available_bytes);

/* Which layer of the pane owns a key. ALWAYS: the pane's other rows (overlays, controllers, ...), handed over whatever
   the switch says. A key that moves to a layer must be listed here, so main.m's filter and the tests share one table. */
typedef enum { TOTK_KEY_ALWAYS, TOTK_KEY_PRESET, TOTK_KEY_CUSTOM } totk_key_layer;
totk_key_layer totk_key_layer_of(const char *key);
/* 1 when this run is on the custom layer. apply_settings reads the switch at launch and sets this once; everything after
   asks here, not the switch: the Settings app can flip it while the app runs, and the pane promises that only a relaunch
   takes it, so a run never mixes the layers. */
extern int totk_custom_layer;
