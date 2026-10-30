/* The iOS export of Tears of the Kingdom 1.4.3 (runtime/loader.c export-ios, which build_ipa.py runs on a Mac) for a
   host without the Mac loader. ios/tools/export_ios_windows.py builds this file twice with runtime/game_patches_v143.c as
   it is; darwin_shim stands in for the Darwin headers that file includes for its Mac diagnostics.

   TARGET_OS_IPHONE 0, the Mac's patch path, with TOTK_EXPORT_IOS=<dir> as for the loader:
     export_ios_host export {<name> <image> <file size> <TEXT_END> <RO_OFF> <DATA_OFF> <PATCH_OFF> <KEY_PAGE_OFF>}...
   loads each rewritten image as loader.c map_module does (zero-filled from a 16 KiB page, page_up(file size) bytes and
   main's data page after them), runs runtime_game_patches on main, and writes <dir>/<name>.x0.bin (the text,
   [0, page_up(TEXT_END))) and <dir>/<name>.x1.bin (the patch area, [PATCH_OFF, page_up(file size))) with the line of
   counts loader.c export_ios_text prints. The loader relocates before the patches; that writes [DATA_OFF, KEY_PAGE_OFF)
   only, which neither section holds and runtime_game_patches does not read, so it is left out here.

   TARGET_OS_IPHONE 1, the device's path:
     export_ios_host check {<name> <x0> <W> <x1> <file size> <TEXT_END> <RO_OFF> <DATA_OFF> <PATCH_OFF> <KEY_PAGE_OFF>}...
   puts each module's three sections back at their offsets as the iOS map_module does and runs runtime_game_patches on
   main: the device's checks of its embedded code, which stop with runtime_fail as on the device.

   Numbers are C literals (0x...). The base is aligned to Apple's page, so every ADRP word a patch makes is the one the
   Mac and the device make. */
#include "runtime.h"
#include "game_patches.h"
#include "world_survey.h"
#include <TargetConditionals.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PAGE 0x4000u   /* loader.c page_up */

_Noreturn void runtime_fail(const char *message) { fprintf(stderr, "[totk] FAIL: %s\n", message); exit(1); }
static void need(int ok, const char *message) { if (!ok) runtime_fail(message); }

/* What runtime_game_patches calls outside game_patches_v143.c, as scripts/v143_timing_fixture.c gives it. */
void *runtime_symbol(const char *name) { (void)name; return NULL; }   /* only Vert+ (TOTK_ASPECT_VERT=1) asks: tanf, atanf */
void runtime_survey_init(Module *m) {
    (void)m;
    const char *survey = getenv("TOTK_SURVEY");
    need(!survey || strcmp(survey, "1"), "the iOS export takes no survey session (TOTK_SURVEY=1)");
}
uint8_t *runtime_bench_cam;
void runtime_oe_push_message(uint32_t message) { (void)message; }
int mfxup_output_enabled(void) { return 0; }
void dm_gfx_set_flag(const char *name, int value) { (void)name; (void)value; }

static size_t page_up(size_t x) { return (x + PAGE - 1) & ~(size_t)(PAGE - 1); }

static uint64_t number(const char *s) {
    char *end; errno = 0;
    unsigned long long v = strtoull(s, &end, 0);
    need(*s && !*end && !errno, "an argument is not a number");
    return v;
}

/* The whole file, in memory from malloc; *size its length. */
static uint8_t *read_all(const char *path, size_t *size) {
    FILE *f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "[totk] %s: cannot open\n", path); runtime_fail("open module file"); }
    size_t cap = 1u << 20, n = 0; uint8_t *data = malloc(cap); need(data != NULL, "module file buffer");
    for (size_t got; (got = fread(data + n, 1, cap - n, f)) > 0;) {
        n += got;
        if (n == cap) { cap *= 2; data = realloc(data, cap); need(data != NULL, "module file buffer"); }
    }
    need(!ferror(f), "read module file"); fclose(f);
    *size = n; return data;
}

/* A module's range as the loader reserves it: zero-filled from an Apple page, page_up(file size) bytes and main's private
   data page after them (real-time frame step, aspect ratio and render size). The program ends after one run, so it is
   never freed. */
static void reserve(Module *m) {
    m->size = page_up(m->file_size) + (!strcmp(m->name, "main") ? PAGE : 0);
    uint8_t *raw = calloc(1, m->size + PAGE); need(raw != NULL, "map module");
    m->base = (uint8_t *)(((uintptr_t)raw + PAGE - 1) & ~(uintptr_t)(PAGE - 1));
    need(m->key_off % PAGE == 0 && m->key_off + PAGE <= m->patch_off && m->patch_off < m->size, "key and patch layout");
    need(page_up(m->text_end) <= (m->data_off & ~(uint64_t)(PAGE - 1)), "text/data overlap");
}

/* name, then the layout from the file size on (TEXT_END, RO_OFF, DATA_OFF, PATCH_OFF, KEY_PAGE_OFF). */
static Module layout(const char *name, char **at) {
    return (Module){.name = name, .file_size = number(at[0]), .text_end = number(at[1]), .ro_off = number(at[2]),
                    .data_off = number(at[3]), .patch_off = number(at[4]), .key_off = number(at[5])};
}

#if !TARGET_OS_IPHONE
static void write_file(const char *dir, const char *name, const char *part, const uint8_t *data, size_t n) {
    char path[4096];
    need(snprintf(path, sizeof path, "%s/%s.%s.bin", dir, name, part) < (int)sizeof path, "export path");
    FILE *f = fopen(path, "wb");
    need(f && fwrite(data, 1, n, f) == n && fclose(f) == 0, "write exported section");
}

/* loader.c export_ios_text for one module: orig is the rewritten image (page_up(file size) bytes, zero past its end). */
static void export_module(const Module *m, const uint8_t *orig, const char *out) {
    size_t n = page_up(m->text_end), p0 = m->patch_off, p1 = page_up(m->file_size);
    need(n <= p0 && p0 <= p1 && p1 <= m->size, "patch area layout");
    unsigned diff = 0, pdiff = 0;
    for (size_t k = 0; k < n; k += 4) if (memcmp(orig + k, m->base + k, 4)) diff++;
    for (size_t k = p0; k < p1; k += 4) if (memcmp(orig + k, m->base + k, 4)) pdiff++;
    write_file(out, m->name, "x0", m->base, n);
    write_file(out, m->name, "x1", m->base + p0, p1 - p0);
    printf("%s text_bytes=%zu patched_words=%u patch_area_bytes=%zu patched_words=%u\n", m->name, n, diff, p1 - p0, pdiff);
}

int main(int argc, char **argv) {
    enum { FIELDS = 8, MAX = 3 };
    need(argc > 2 && !strcmp(argv[1], "export") && (argc - 2) % FIELDS == 0 && (argc - 2) / FIELDS <= MAX,
         "usage: export_ios_host export {<name> <image> <file size> <TEXT_END> <RO_OFF> <DATA_OFF> <PATCH_OFF> <KEY_PAGE_OFF>}...");
    const char *out = getenv("TOTK_EXPORT_IOS");
    need(out != NULL, "export-ios needs TOTK_EXPORT_IOS=<dir>");
    unsigned count = (unsigned)(argc - 2) / FIELDS;
    Module modules[MAX]; uint8_t *orig[MAX];
    for (unsigned i = 0; i < count; i++) {
        char **a = argv + 2 + FIELDS * i;
        Module *m = &modules[i]; *m = layout(a[0], a + 2); reserve(m);
        size_t got; uint8_t *image = read_all(a[1], &got);
        need(got == m->file_size, "patched module size");
        memcpy(m->base, image, got); free(image);
        orig[i] = calloc(1, page_up(m->file_size)); need(orig[i] != NULL, "module copy");
        memcpy(orig[i], m->base, m->file_size);
        fprintf(stderr, "[totk] mapped %s size=%zu\n", m->name, m->size);
    }
    for (unsigned i = 0; i < count; i++) if (!strcmp(modules[i].name, "main")) runtime_game_patches(&modules[i]);
    for (unsigned i = 0; i < count; i++) export_module(&modules[i], orig[i], out);
    return 0;
}
#else
int main(int argc, char **argv) {
    enum { FIELDS = 10, MAX = 3 };
    need(argc > 2 && !strcmp(argv[1], "check") && (argc - 2) % FIELDS == 0 && (argc - 2) / FIELDS <= MAX,
         "usage: export_ios_host check {<name> <x0> <W> <x1> <file size> <TEXT_END> <RO_OFF> <DATA_OFF> <PATCH_OFF> <KEY_PAGE_OFF>}...");
    unsigned count = (unsigned)(argc - 2) / FIELDS;
    Module modules[MAX];
    for (unsigned i = 0; i < count; i++) {
        char **a = argv + 2 + FIELDS * i;
        Module *m = &modules[i]; *m = layout(a[0], a + 4);
        size_t z0, zw, z1; uint8_t *x0 = read_all(a[1], &z0), *w = read_all(a[2], &zw), *x1 = read_all(a[3], &z1);
        need(z0 == page_up(m->text_end) && z0 + zw == m->patch_off && m->patch_off + z1 == page_up(m->file_size), "embedded module layout");
        reserve(m);
        memcpy(m->base, x0, z0); memcpy(m->base + z0, w, zw); memcpy(m->base + m->patch_off, x1, z1);
        free(x0); free(w); free(x1);
        fprintf(stderr, "[totk] mapped embedded %s size=%zu\n", m->name, m->size);
    }
    unsigned checked = 0;
    for (unsigned i = 0; i < count; i++) if (!strcmp(modules[i].name, "main")) { runtime_game_patches(&modules[i]); checked++; }
    need(checked == 1, "check needs main");
    printf("main: the device's checks of the embedded code passed\n");
    return 0;
}
#endif
