// Which sampled textures of a translated shader need every level of their texture (TOTK #337).
// On iPhone and iPad the Metal copy of a large mipmapped CPU-pool texture leaves out its top level (nvn_mtl.m
// mip_drop_of). A copy one level smaller is drawn correctly when the GPU picks the level from the screen footprint, as
// fragment shaders sampling with an implicit level do. It is wrong when the shader names texels or levels itself:
// texelFetch (MSL read), textureGather (gather, spvGatherConstOffsets), textureSize and textureQueryLevels (get_width,
// get_height, get_depth, get_num_mip_levels), and sampling at an explicit level (mode NVN_LEVEL_EXACT_LEVELS). The
// copy then answers with the game's level 1 at level 0, half the size, so a lookup by texel position reads other data.
// Plain C, so tests can run it on the MSL of a shader seed without Metal.
#pragma once
#include <stddef.h>
#include <string.h>

enum { NVN_LEVEL_EXACT_OFF = 0, NVN_LEVEL_EXACT_TEXELS = 1, NVN_LEVEL_EXACT_LEVELS = 2 };

/* The ')' that closes the call whose '(' is at open; NULL when the source ends first. */
static inline const char *nvn_msl_call_end(const char *open) {
    int depth = 0;
    for (const char *c = open; *c; c++) {
        if (*c == '(') depth++;
        else if (*c == ')' && --depth == 0) return c;
    }
    return NULL;
}

/* 1 when the MSL accesses the argument-buffer texture `name` (spirv-cross writes spvDescriptorSet0.<name>) by texel
   position, gathers it or asks for its size or level count; with mode NVN_LEVEL_EXACT_LEVELS also when it samples it
   at an explicit level. A name too long for the pattern buffer counts as such an access (the texture keeps its levels). */
static inline int nvn_msl_level_exact(const char *src, const char *name, int mode) {
    static const char *const texel_calls[] = {"read(", "gather(", "get_width(", "get_height(", "get_depth(", "get_num_mip_levels("};
    static const char gather_helper[] = "spvGatherConstOffsets(";   // textureGatherOffsets: spirv-cross passes the texture to this helper
    if (!src || !name || !*name || mode <= NVN_LEVEL_EXACT_OFF) return 0;
    char pat[128];
    size_t head = sizeof "spvDescriptorSet0." - 1, nl = strlen(name), hl = sizeof gather_helper - 1;
    if (head + nl >= sizeof pat) return 1;
    memcpy(pat, "spvDescriptorSet0.", head); memcpy(pat + head, name, nl + 1);
    size_t pl = head + nl;
    for (const char *p = strstr(src, pat); p; p = strstr(p + pl, pat)) {
        const char *q = p + pl;
        if (*q == ',') {   // passed as an argument: only the gather helper takes a texture this way
            if ((size_t)(p - src) >= hl && !strncmp(p - hl, gather_helper, hl)) return 1;
            continue;
        }
        if (*q == ')') q++;   // spvDepthCast(spvDescriptorSet0.<name>).<member>(...)
        if (*q != '.') continue;   // another member whose name starts with this one (<name>Smplr)
        q++;
        for (size_t i = 0; i < sizeof texel_calls / sizeof *texel_calls; i++)
            if (!strncmp(q, texel_calls[i], strlen(texel_calls[i]))) return 1;
        if (mode >= NVN_LEVEL_EXACT_LEVELS && !strncmp(q, "sample", 6)) {   // sample( and sample_compare(
            const char *open = strchr(q, '('), *end = open ? nvn_msl_call_end(open) : NULL;
            if (end) for (const char *c = open; c < end; c++) if (!strncmp(c, "level(", 6)) return 1;
        }
    }
    return 0;
}
