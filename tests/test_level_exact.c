// CPU-only regression of nvn_msl_level_exact: which texture accesses in spirv-cross MSL name texels or levels, so the
// texture keeps every level of its Metal copy (nvn_mtl.m mip_drop_of). The snippets are written by hand in the shape
// spirv-cross emits; no translated game shader is used.
#include "../games/totk/third_party/d2r_gfx/gfx/nvn/nvn_level_exact.h"
#include <assert.h>
#include <stdio.h>

static const char *src =
    "struct spvDescriptorSetBuffer0 { texture2d<float> fp_t_tcb_8 [[id(0)]]; sampler fp_t_tcb_8Smplr [[id(1)]];\n"
    "    texture2d<float> fp_t_tcb_80 [[id(2)]]; texture2d<float> fp_t_tcb_A [[id(3)]]; texture2d<float> fp_t_tcb_C [[id(4)]];\n"
    "    texture2d<float> fp_t_tcb_E [[id(5)]]; depth2d<float> fp_t_tcb_10 [[id(6)]]; texture2d<float> fp_t_tcb_12 [[id(7)]];\n"
    "    texture2d<float> fp_t_tcb_14 [[id(8)]]; texture2d<float> fp_t_tcb_16 [[id(9)]]; depth2d<float> fp_t_tcb_18 [[id(10)]]; };\n"
    "fragment main0_out main0(constant spvDescriptorSetBuffer0& spvDescriptorSet0 [[buffer(0)]]) {\n"
    "    float4 _1 = spvDescriptorSet0.fp_t_tcb_8.sample(spvDescriptorSet0.fp_t_tcb_8Smplr, float2(0.5));\n"
    "    float4 _2 = spvDescriptorSet0.fp_t_tcb_80.read(uint2(int2(3, 4)), 0);\n"
    "    float4 _3 = spvDescriptorSet0.fp_t_tcb_A.sample(spvDescriptorSet0.fp_t_tcb_ASmplr, float2(0.5), level(0.0));\n"
    "    int _4 = int2(spvDescriptorSet0.fp_t_tcb_C.get_width(), spvDescriptorSet0.fp_t_tcb_C.get_height()).x;\n"
    "    float4 _5 = spvGatherConstOffsets(spvDescriptorSet0.fp_t_tcb_E, spvDescriptorSet0.fp_t_tcb_ESmplr, _9, component::x);\n"
    "    float _6 = spvDepthCast(spvDescriptorSet0.fp_t_tcb_10).sample_compare(spvDescriptorSet0.fp_t_tcb_10Smplr, float2(0.5), 0.5, level(0.0));\n"
    "    float _7 = spvDescriptorSet0.fp_t_tcb_12.sample(spvDescriptorSet0.fp_t_tcb_12Smplr, float2(0.5)).x + float(level(1));\n"
    "    float2 _8; _8.x = spvDescriptorSet0.fp_t_tcb_14.calculate_clamped_lod(spvDescriptorSet0.fp_t_tcb_14Smplr, float2(_55, _57));\n"
    "    _8.y = spvDescriptorSet0.fp_t_tcb_16.calculate_unclamped_lod(spvDescriptorSet0.fp_t_tcb_16Smplr, float2(_55, _57));\n"
    "    float _10 = spvDepthCast(spvDescriptorSet0.fp_t_tcb_18).calculate_clamped_lod(spvDescriptorSet0.fp_t_tcb_18Smplr, float2(0.5));\n"
    "}\n";

int main(void) {
    // A sampled texture with an implicit level is never named; a member whose name starts with it (fp_t_tcb_80) is another texture.
    assert(!nvn_msl_level_exact(src, "fp_t_tcb_8", NVN_LEVEL_EXACT_TEXELS));
    assert(!nvn_msl_level_exact(src, "fp_t_tcb_8", NVN_LEVEL_EXACT_LEVELS));
    assert(nvn_msl_level_exact(src, "fp_t_tcb_80", NVN_LEVEL_EXACT_TEXELS));   // texelFetch
    // Sampling at an explicit level counts only with mode 2.
    assert(!nvn_msl_level_exact(src, "fp_t_tcb_A", NVN_LEVEL_EXACT_TEXELS));
    assert(nvn_msl_level_exact(src, "fp_t_tcb_A", NVN_LEVEL_EXACT_LEVELS));
    assert(nvn_msl_level_exact(src, "fp_t_tcb_C", NVN_LEVEL_EXACT_TEXELS));    // textureSize
    assert(nvn_msl_level_exact(src, "fp_t_tcb_E", NVN_LEVEL_EXACT_TEXELS));    // textureGatherOffsets through the helper
    assert(!nvn_msl_level_exact(src, "fp_t_tcb_10", NVN_LEVEL_EXACT_TEXELS));  // depth compare through spvDepthCast
    assert(nvn_msl_level_exact(src, "fp_t_tcb_10", NVN_LEVEL_EXACT_LEVELS));
    // A level( after the sample call's closing parenthesis belongs to another expression.
    assert(!nvn_msl_level_exact(src, "fp_t_tcb_12", NVN_LEVEL_EXACT_LEVELS));
    // textureQueryLod (both halves, also through spvDepthCast) counts only with mode 2.
    assert(!nvn_msl_level_exact(src, "fp_t_tcb_14", NVN_LEVEL_EXACT_TEXELS));
    assert(nvn_msl_level_exact(src, "fp_t_tcb_14", NVN_LEVEL_EXACT_LEVELS));
    assert(!nvn_msl_level_exact(src, "fp_t_tcb_16", NVN_LEVEL_EXACT_TEXELS));
    assert(nvn_msl_level_exact(src, "fp_t_tcb_16", NVN_LEVEL_EXACT_LEVELS));
    assert(!nvn_msl_level_exact(src, "fp_t_tcb_18", NVN_LEVEL_EXACT_TEXELS));
    assert(nvn_msl_level_exact(src, "fp_t_tcb_18", NVN_LEVEL_EXACT_LEVELS));
    // Off, no source, no name, an unknown name.
    assert(!nvn_msl_level_exact(src, "fp_t_tcb_80", NVN_LEVEL_EXACT_OFF));
    assert(!nvn_msl_level_exact(src, "fp_t_tcb_14", NVN_LEVEL_EXACT_OFF));
    assert(!nvn_msl_level_exact(NULL, "fp_t_tcb_80", NVN_LEVEL_EXACT_TEXELS));
    assert(!nvn_msl_level_exact(src, "", NVN_LEVEL_EXACT_TEXELS));
    assert(!nvn_msl_level_exact(src, "fp_t_tcb_99", NVN_LEVEL_EXACT_LEVELS));
    // A name too long for the pattern buffer keeps the texture's levels.
    char longname[200]; for (unsigned i = 0; i < sizeof longname - 1; i++) longname[i] = 'x'; longname[sizeof longname - 1] = 0;
    assert(nvn_msl_level_exact(src, longname, NVN_LEVEL_EXACT_TEXELS));
    printf("PASS: texel reads, gathers, size queries, explicit levels and LOD queries found; implicit sampling and prefixes left alone\n");
    return 0;
}
