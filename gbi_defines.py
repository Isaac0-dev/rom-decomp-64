# GBI Constants and Maps
from typing import Any, Dict

# Image Formats
G_IM_FMT_RGBA = 0
G_IM_FMT_YUV = 1
G_IM_FMT_CI = 2
G_IM_FMT_IA = 3
G_IM_FMT_I = 4

G_IM_FMT_MAP = {
    G_IM_FMT_RGBA: "G_IM_FMT_RGBA",
    G_IM_FMT_YUV: "G_IM_FMT_YUV",
    G_IM_FMT_CI: "G_IM_FMT_CI",
    G_IM_FMT_IA: "G_IM_FMT_IA",
    G_IM_FMT_I: "G_IM_FMT_I",
}

# Image Sizes
G_IM_SIZ_4b = 0
G_IM_SIZ_8b = 1
G_IM_SIZ_16b = 2
G_IM_SIZ_32b = 3
G_IM_SIZ_DD = 5

G_IM_SIZ_MAP = {
    G_IM_SIZ_4b: "G_IM_SIZ_4b",
    G_IM_SIZ_8b: "G_IM_SIZ_8b",
    G_IM_SIZ_16b: "G_IM_SIZ_16b",
    G_IM_SIZ_32b: "G_IM_SIZ_32b",
    G_IM_SIZ_DD: "G_IM_SIZ_DD",
}

# Texture Tiles
G_TX_RENDERTILE = 0
G_TX_LOADTILE = 7

G_TX_MAP = {
    G_TX_RENDERTILE: "G_TX_RENDERTILE",
    G_TX_LOADTILE: "G_TX_LOADTILE",
}

# Texture On/Off
G_OFF = 0
G_ON = 1

G_ON_OFF_MAP = {
    G_OFF: "G_OFF",
    G_ON: "G_ON",
}

# Display List
G_DL_PUSH = 0x00
G_DL_NOPUSH = 0x01

# Matrix
G_MTX_MODELVIEW = 0x00
G_MTX_PROJECTION = 0x01
G_MTX_MUL = 0x00
G_MTX_LOAD = 0x02
G_MTX_NOPUSH = 0x00
G_MTX_PUSH = 0x04

# Texture Flags
G_TX_NOMIRROR = 0
G_TX_WRAP = 0
G_TX_MIRROR = 0x1
G_TX_CLAMP = 0x2
G_TX_NOMASK = 0
G_TX_NOLOD = 0

G_TX_FLAGS_MAP = {
    G_TX_MIRROR: "G_TX_MIRROR",
    G_TX_CLAMP: "G_TX_CLAMP",
}

# Scissor Modes
G_SC_NON_INTERLACE = 0
G_SC_ODD_INTERLACE = 3
G_SC_EVEN_INTERLACE = 2

G_SC_MAP = {
    G_SC_NON_INTERLACE: "G_SC_NON_INTERLACE",
    G_SC_ODD_INTERLACE: "G_SC_ODD_INTERLACE",
    G_SC_EVEN_INTERLACE: "G_SC_EVEN_INTERLACE",
}

# Color Combiner Mux
G_CCMUX_MAP = {
    0: "COMBINED",
    1: "TEXEL0",
    2: "TEXEL1",
    3: "PRIMITIVE",
    4: "SHADE",
    5: "ENVIRONMENT",
    6: "CENTER",
    7: "K4",
    8: "COMBINED_ALPHA",
    9: "TEXEL0_ALPHA",
    10: "TEXEL1_ALPHA",
    11: "PRIMITIVE_ALPHA",
    12: "SHADE_ALPHA",
    13: "ENV_ALPHA",
    14: "LOD_FRACTION",
    15: "PRIM_LOD_FRAC",
    31: "0",  # G_CCMUX_0 is 31
    30: "COMBINED",
    # Aliases
    # 6: 'SCALE' (Conflict with CENTER, usually context dependent, CENTER is safer default)
    # 7: 'NOISE' (Conflict with K4)
}

# Alpha Combiner Mux
G_ACMUX_MAP = {
    # Fix: Ensure 0 maps to COMBINED, not LOD_FRACTION, to avoid color slot pollution
    0: "COMBINED",
    1: "TEXEL0",
    2: "TEXEL1",
    3: "PRIMITIVE",
    4: "SHADE",
    5: "ENVIRONMENT",
    # Fix: G_ACMUX_1 is value 6. This fixes "Unknown gfx arg: G_ACMUX_6"
    6: "1",
    # Fix: G_ACMUX_0 is value 7.
    7: "0",
}

# Set Combine Modes (Pre-defined macros)
G_SETCOMBINE_MODES = {
    "0, 0, 0, PRIMITIVE, 0, 0, 0, PRIMITIVE": "G_CC_PRIMITIVE",
    "0, 0, 0, SHADE, 0, 0, 0, SHADE": "G_CC_SHADE",
    "TEXEL0, 0, SHADE, 0, 0, 0, 0, SHADE": "G_CC_MODULATEI",
    "TEXEL0, 0, SHADE, 0, 0, 0, 0, TEXEL0": "G_CC_MODULATEIDECALA",
    "TEXEL0, 0, SHADE, 0, 0, 0, 0, ENVIRONMENT": "G_CC_MODULATEIFADE",
    "G_CC_MODULATEI": "G_CC_MODULATERGB",
    "G_CC_MODULATEIDECALA": "G_CC_MODULATERGBDECALA",
    "G_CC_MODULATEIFADE": "G_CC_MODULATERGBFADE",
    "TEXEL0, 0, SHADE, 0, TEXEL0, 0, SHADE, 0": "G_CC_MODULATEIA",
    "TEXEL0, 0, SHADE, 0, TEXEL0, 0, ENVIRONMENT, 0": "G_CC_MODULATEIFADEA",
    "TEXEL0, 0, SHADE, 0, ENVIRONMENT, 0, TEXEL0, 0": "G_CC_MODULATEFADE",
    "G_CC_MODULATEIA": "G_CC_MODULATERGBA",
    "G_CC_MODULATEIFADEA": "G_CC_MODULATERGBFADEA",
    "TEXEL0, 0, PRIMITIVE, 0, 0, 0, 0, PRIMITIVE": "G_CC_MODULATEI_PRIM",
    "TEXEL0, 0, PRIMITIVE, 0, TEXEL0, 0, PRIMITIVE, 0": "G_CC_MODULATEIA_PRIM",
    "TEXEL0, 0, PRIMITIVE, 0, 0, 0, 0, TEXEL0": "G_CC_MODULATEIDECALA_PRIM",
    "G_CC_MODULATEI_PRIM": "G_CC_MODULATERGB_PRIM",
    "G_CC_MODULATEIA_PRIM": "G_CC_MODULATERGBA_PRIM",
    "G_CC_MODULATEIDECALA_PRIM": "G_CC_MODULATERGBDECALA_PRIM",
    "SHADE, 0, ENVIRONMENT, 0, SHADE, 0, ENVIRONMENT, 0": "G_CC_FADE",
    "TEXEL0, 0, ENVIRONMENT, 0, TEXEL0, 0, ENVIRONMENT, 0": "G_CC_FADEA",
    "0, 0, 0, TEXEL0, 0, 0, 0, SHADE": "G_CC_DECALRGB",
    "0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0": "G_CC_DECALRGBA",
    "0, 0, 0, TEXEL0, 0, 0, 0, ENVIRONMENT": "G_CC_DECALFADE",
    "0, 0, 0, TEXEL0, TEXEL0, 0, ENVIRONMENT, 0": "G_CC_DECALFADEA",
    "ENVIRONMENT, SHADE, TEXEL0, SHADE, 0, 0, 0, SHADE": "G_CC_BLENDI",
    "ENVIRONMENT, SHADE, TEXEL0, SHADE, TEXEL0, 0, SHADE, 0": "G_CC_BLENDIA",
    "ENVIRONMENT, SHADE, TEXEL0, SHADE, 0, 0, 0, TEXEL0": "G_CC_BLENDIDECALA",
    "TEXEL0, SHADE, TEXEL0_ALPHA, SHADE, 0, 0, 0, SHADE": "G_CC_BLENDRGBA",
    "TEXEL0, SHADE, TEXEL0_ALPHA, SHADE, 0, 0, 0, TEXEL0": "G_CC_BLENDRGBDECALA",
    "TEXEL0, SHADE, TEXEL0_ALPHA, SHADE, 0, 0, 0, ENVIRONMENT": "G_CC_BLENDRGBFADEA",
    "TEXEL0, 0, TEXEL0, SHADE, 0, 0, 0, SHADE": "G_CC_ADDRGB",
    "TEXEL0, 0, TEXEL0, SHADE, 0, 0, 0, TEXEL0": "G_CC_ADDRGBDECALA",
    "TEXEL0, 0, TEXEL0, SHADE, 0, 0, 0, ENVIRONMENT": "G_CC_ADDRGBFADE",
    "ENVIRONMENT, 0, TEXEL0, SHADE, 0, 0, 0, SHADE": "G_CC_REFLECTRGB",
    "ENVIRONMENT, 0, TEXEL0, SHADE, 0, 0, 0, TEXEL0": "G_CC_REFLECTRGBDECALA",
    "PRIMITIVE, SHADE, TEXEL0, SHADE, 0, 0, 0, SHADE": "G_CC_HILITERGB",
    "PRIMITIVE, SHADE, TEXEL0, SHADE, PRIMITIVE, SHADE, TEXEL0, SHADE": "G_CC_HILITERGBA",
    "PRIMITIVE, SHADE, TEXEL0, SHADE, 0, 0, 0, TEXEL0": "G_CC_HILITERGBDECALA",
    "0, 0, 0, SHADE, 0, 0, 0, TEXEL0": "G_CC_SHADEDECALA",
    "0, 0, 0, SHADE, 0, 0, 0, ENVIRONMENT": "G_CC_SHADEFADEA",
    "PRIMITIVE, ENVIRONMENT, TEXEL0, ENVIRONMENT, TEXEL0, 0, SHADE, 0": "G_CC_BLENDPE",
    "PRIMITIVE, ENVIRONMENT, TEXEL0, ENVIRONMENT, 0, 0, 0, TEXEL0": "G_CC_BLENDPEDECALA",
    "ENVIRONMENT, PRIMITIVE, TEXEL0, PRIMITIVE, TEXEL0, 0, SHADE, 0": "_G_CC_BLENDPE",
    "ENVIRONMENT, PRIMITIVE, TEXEL0, PRIMITIVE, 0, 0, 0, TEXEL0": "_G_CC_BLENDPEDECALA",
    "PRIMITIVE, TEXEL0, LOD_FRACTION, TEXEL0, PRIMITIVE, TEXEL0, LOD_FRACTION, TEXEL0": "_G_CC_SPARSEST",
    "TEXEL1, TEXEL0, PRIM_LOD_FRAC, TEXEL0, TEXEL1, TEXEL0, PRIM_LOD_FRAC, TEXEL0": "G_CC_TEMPLERP",
    "TEXEL1, TEXEL0, LOD_FRACTION, TEXEL0, TEXEL1, TEXEL0, LOD_FRACTION, TEXEL0": "G_CC_TRILERP",
    "TEXEL0, 0, TEXEL1, 0, TEXEL0, 0, TEXEL1, 0": "G_CC_INTERFERENCE",
    "TEXEL0, K4, K5, TEXEL0, 0, 0, 0, SHADE": "G_CC_1CYUV2RGB",
    "TEXEL1, K4, K5, TEXEL1, 0, 0, 0, 0": "G_CC_YUV2RGB",
    "0, 0, 0, COMBINED, 0, 0, 0, COMBINED": "G_CC_PASS2",
    "COMBINED, 0, SHADE, 0, 0, 0, 0, SHADE": "G_CC_MODULATEI2",
    "COMBINED, 0, SHADE, 0, COMBINED, 0, SHADE, 0": "G_CC_MODULATEIA2",
    "G_CC_MODULATEI2": "G_CC_MODULATERGB2",
    "G_CC_MODULATEIA2": "G_CC_MODULATERGBA2",
    "COMBINED, 0, PRIMITIVE, 0, 0, 0, 0, PRIMITIVE": "G_CC_MODULATEI_PRIM2",
    "COMBINED, 0, PRIMITIVE, 0, COMBINED, 0, PRIMITIVE, 0": "G_CC_MODULATEIA_PRIM2",
    "G_CC_MODULATEI_PRIM2": "G_CC_MODULATERGB_PRIM2",
    "G_CC_MODULATEIA_PRIM2": "G_CC_MODULATERGBA_PRIM2",
    "0, 0, 0, COMBINED, 0, 0, 0, SHADE": "G_CC_DECALRGB2",
    "COMBINED, SHADE, COMBINED_ALPHA, SHADE, 0, 0, 0, SHADE": "G_CC_DECALRGBA2",
    "ENVIRONMENT, SHADE, COMBINED, SHADE, 0, 0, 0, SHADE": "G_CC_BLENDI2",
    "ENVIRONMENT, SHADE, COMBINED, SHADE, COMBINED, 0, SHADE, 0": "G_CC_BLENDIA2",
    "TEXEL0, CENTER, SCALE, 0, 0, 0, 0, 0": "G_CC_CHROMA_KEY2",
    "ENVIRONMENT, COMBINED, TEXEL0, COMBINED, 0, 0, 0, SHADE": "G_CC_HILITERGB2",
    "ENVIRONMENT, COMBINED, TEXEL0, COMBINED, ENVIRONMENT, COMBINED, TEXEL0, COMBINED": "G_CC_HILITERGBA2",
    "ENVIRONMENT, COMBINED, TEXEL0, COMBINED, 0, 0, 0, TEXEL0": "G_CC_HILITERGBDECALA2",
    "ENVIRONMENT, COMBINED, TEXEL0, COMBINED, 0, 0, 0, COMBINED": "G_CC_HILITERGBPASSA2",
}

# G_SETOTHERMODE_H
G_MDSFT_ALPHADITHER = 4
G_MDSFT_RGBDITHER = 6
G_MDSFT_COMBKEY = 8
G_MDSFT_TEXTCONV = 9
G_MDSFT_TEXTFILT = 12
G_MDSFT_TEXTLUT = 14
G_MDSFT_TEXTLOD = 16
G_MDSFT_TEXTDETAIL = 17
G_MDSFT_TEXTPERSP = 19
G_MDSFT_CYCLETYPE = 20
G_MDSFT_PIPELINE = 23

G_SETOTHERMODE_H_SHIFTS = {
    G_MDSFT_ALPHADITHER: {
        "cmd": "gsDPSetAlphaDither",
        "consts": {
            (0 << G_MDSFT_ALPHADITHER): "G_AD_PATTERN",
            (1 << G_MDSFT_ALPHADITHER): "G_AD_NOTPATTERN",
            (2 << G_MDSFT_ALPHADITHER): "G_AD_NOISE",
            (3 << G_MDSFT_ALPHADITHER): "G_AD_DISABLE",
        },
    },
    G_MDSFT_RGBDITHER: {
        "cmd": "gsDPSetColorDither",
        "consts": {
            (0 << G_MDSFT_RGBDITHER): "G_CD_MAGICSQ",
            (1 << G_MDSFT_RGBDITHER): "G_CD_BAYER",
            (2 << G_MDSFT_RGBDITHER): "G_CD_NOISE",
            (3 << G_MDSFT_RGBDITHER): "G_CD_DISABLE",
        },
    },
    G_MDSFT_COMBKEY: {
        "cmd": "gsDPSetCombineKey",
        "consts": {
            (0 << G_MDSFT_COMBKEY): "G_CK_NONE",
            (1 << G_MDSFT_COMBKEY): "G_CK_KEY",
        },
    },
    G_MDSFT_TEXTCONV: {
        "cmd": "gsDPSetTextureConvert",
        "consts": {
            (0 << G_MDSFT_TEXTCONV): "G_TC_CONV",
            (5 << G_MDSFT_TEXTCONV): "G_TC_FILTCONV",
            (6 << G_MDSFT_TEXTCONV): "G_TC_FILT",
        },
    },
    G_MDSFT_TEXTFILT: {
        "cmd": "gsDPSetTextureFilter",
        "consts": {
            (0 << G_MDSFT_TEXTFILT): "G_TF_POINT",
            (3 << G_MDSFT_TEXTFILT): "G_TF_AVERAGE",
            (2 << G_MDSFT_TEXTFILT): "G_TF_BILERP",
        },
    },
    G_MDSFT_TEXTLUT: {
        "cmd": "gsDPSetTextureLUT",
        "consts": {
            (0 << G_MDSFT_TEXTLUT): "G_TT_NONE",
            (2 << G_MDSFT_TEXTLUT): "G_TT_RGBA16",
            (3 << G_MDSFT_TEXTLUT): "G_TT_IA16",
        },
    },
    G_MDSFT_TEXTLOD: {
        "cmd": "gsDPSetTextureLOD",
        "consts": {
            (0 << G_MDSFT_TEXTLOD): "G_TL_TILE",
            (1 << G_MDSFT_TEXTLOD): "G_TL_LOD",
        },
    },
    G_MDSFT_TEXTDETAIL: {
        "cmd": "gsDPSetTextureDetail",
        "consts": {
            (0 << G_MDSFT_TEXTDETAIL): "G_TD_CLAMP",
            (1 << G_MDSFT_TEXTDETAIL): "G_TD_SHARPEN",
            (2 << G_MDSFT_TEXTDETAIL): "G_TD_DETAIL",
        },
    },
    G_MDSFT_TEXTPERSP: {
        "cmd": "gsDPSetTexturePersp",
        "consts": {
            (0 << G_MDSFT_TEXTPERSP): "G_TP_NONE",
            (1 << G_MDSFT_TEXTPERSP): "G_TP_PERSP",
        },
    },
    G_MDSFT_CYCLETYPE: {
        "cmd": "gsDPSetCycleType",
        "consts": {
            (0 << G_MDSFT_CYCLETYPE): "G_CYC_1CYCLE",
            (1 << G_MDSFT_CYCLETYPE): "G_CYC_2CYCLE",
            (2 << G_MDSFT_CYCLETYPE): "G_CYC_COPY",
            (3 << G_MDSFT_CYCLETYPE): "G_CYC_FILL",
        },
    },
    G_MDSFT_PIPELINE: {
        "cmd": "gsDPPipelineMode",
        "consts": {
            (0 << G_MDSFT_PIPELINE): "G_PM_NPRIMITIVE",
            (1 << G_MDSFT_PIPELINE): "G_PM_1PRIMITIVE",
        },
    },
}

# G_SETCOMBINE
G_SETCOMBINE_COLOR_COMBINERS = {
    "a": {
        0x0: "COMBINED",
        0x1: "TEXEL0",
        0x2: "TEXEL1",
        0x3: "PRIMITIVE",
        0x4: "SHADE",
        0x5: "ENVIRONMENT",
        0x6: "1",
        0x7: "NOISE",
    },
    "b": {
        0x0: "COMBINED",
        0x1: "TEXEL0",
        0x2: "TEXEL1",
        0x3: "PRIMITIVE",
        0x4: "SHADE",
        0x5: "ENVIRONMENT",
        0x6: "CENTER",
        0x7: "K4",
    },
    "c": {
        0x0: "COMBINED",
        0x1: "TEXEL0",
        0x2: "TEXEL1",
        0x3: "PRIMITIVE",
        0x4: "SHADE",
        0x5: "ENVIRONMENT",
        0x6: "SCALE",
        0x7: "COMBINED_ALPHA",
        0x8: "TEXEL0_ALPHA",
        0x9: "TEXEL1_ALPHA",
        0xA: "PRIMITIVE_ALPHA",
        0xB: "SHADE_ALPHA",
        0xC: "ENV_ALPHA",
        0xD: "LOD_FRACTION",
        0xE: "PRIM_LOD_FRAC",
        0xF: "K5",
    },
    "d": {
        0x0: "COMBINED",
        0x1: "TEXEL0",
        0x2: "TEXEL1",
        0x3: "PRIMITIVE",
        0x4: "SHADE",
        0x5: "ENVIRONMENT",
        0x6: "1",
    },
}

G_SETCOMBINE_ALPHA_COMBINERS = {
    "a": {
        0x0: "COMBINED",
        0x1: "TEXEL0",
        0x2: "TEXEL1",
        0x3: "PRIMITIVE",
        0x4: "SHADE",
        0x5: "ENVIRONMENT",
        0x6: "1",
    },
    "b": {
        0x0: "COMBINED",
        0x1: "TEXEL0",
        0x2: "TEXEL1",
        0x3: "PRIMITIVE",
        0x4: "SHADE",
        0x5: "ENVIRONMENT",
        0x6: "1",
    },
    "c": {
        0x0: "LOD_FRACTION",
        0x1: "TEXEL0",
        0x2: "TEXEL1",
        0x3: "PRIMITIVE",
        0x4: "SHADE",
        0x5: "ENVIRONMENT",
        0x6: "PRIM_LOD_FRAC",
    },
    "d": {
        0x0: "COMBINED",
        0x1: "TEXEL0",
        0x2: "TEXEL1",
        0x3: "PRIMITIVE",
        0x4: "SHADE",
        0x5: "ENVIRONMENT",
        0x6: "1",
    },
}

# G_MOVEWORD
G_MOVEWORD_INDICES = {
    0x00: "G_MW_MATRIX",
    0x02: "G_MW_NUMLIGHT",
    0x04: "G_MW_CLIP",
    0x06: "G_MW_SEGMENT",
    0x08: "G_MW_FOG",
    0x0A: "G_MW_LIGHTCOL",
    0x0C: "G_MW_FORCEMTX",
    0x0E: "G_MW_PERSPNORM",
}

# G_GEOMETRYMODE
G_GEOMETRYMODE_FLAGS_GBI1 = {
    0x000001: "G_ZBUFFER",
    0x000002: "G_TEXTURE_ENABLE",
    0x000004: "G_SHADE",
    # 0x000008: "<unused>",
    # 0x000010: "<unused>",
    # 0x000020: "<unused>",
    0x000040: "G_FRESNEL_COLOR_EXT",
    0x000080: "G_PACKED_NORMALS_EXT",
    # 0x000100: "<unused>",
    0x000200: "G_SHADING_SMOOTH",
    # 0x000400: "<unused>",
    0x000800: "G_LIGHT_MAP_EXT",
    0x001000: "G_CULL_FRONT",
    0x002000: "G_CULL_BACK",
    0x003000: "G_CULL_BOTH",
    0x004000: "G_LIGHTING_ENGINE_EXT",
    # 0x008000: "<unused>",
    0x010000: "G_FOG",
    0x020000: "G_LIGHTING",
    0x040000: "G_TEXTURE_GEN",
    0x080000: "G_TEXTURE_GEN_LINEAR",
    0x100000: "G_LOD",
    # 0x200000: "<unused>",
    0x400000: "G_FRESNEL_ALPHA_EXT",
    0x800000: "G_CLIPPING",
}
G_GEOMETRYMODE_FLAGS_GBI2 = {
    0x000001: "G_ZBUFFER",
    # 0x000002: "<unused>",
    0x000004: "G_SHADE",
    # 0x000008: "<unused>",
    # 0x000010: "<unused>",
    # 0x000020: "<unused>",
    0x000040: "G_FRESNEL_COLOR_EXT",
    0x000080: "G_PACKED_NORMALS_EXT",
    # 0x000100: "<unused>",
    0x000200: "G_CULL_FRONT",
    0x000400: "G_CULL_BACK",
    0x000600: "G_CULL_BOTH",
    0x000800: "G_LIGHT_MAP_EXT",
    # 0x001000: "<unused>",
    # 0x002000: "<unused>",
    0x004000: "G_LIGHTING_ENGINE_EXT",
    # 0x008000: "<unused>",
    0x010000: "G_FOG",
    0x020000: "G_LIGHTING",
    0x040000: "G_TEXTURE_GEN",
    0x080000: "G_TEXTURE_GEN_LINEAR",
    0x100000: "G_LOD",
    0x200000: "G_SHADING_SMOOTH",
    0x400000: "G_FRESNEL_ALPHA_EXT",
    0x800000: "G_CLIPPING",
}

# G_SETOTHERMODE_L
G_MDSFT_ALPHACOMPARE = 0
G_MDSFT_ZSRCSEL = 2


G_SETOTHERMODE_L_SHIFTS: Dict[int, Dict[str, Any]] = {
    G_MDSFT_ALPHACOMPARE: {
        "cmd": "gsDPSetAlphaCompare",
        "consts": {
            (0 << G_MDSFT_ALPHACOMPARE): "G_AC_NONE",
            (1 << G_MDSFT_ALPHACOMPARE): "G_AC_THRESHOLD",
            (3 << G_MDSFT_ALPHACOMPARE): "G_AC_DITHER",
        },
    },
    G_MDSFT_ZSRCSEL: {
        "cmd": "gsDPSetDepthSource",
        "consts": {
            (0 << G_MDSFT_ZSRCSEL): "G_ZS_PIXEL",
            (1 << G_MDSFT_ZSRCSEL): "G_ZS_PRIM",
        },
    },
}

# Helpers


def C(w: int, pos: int, width: int) -> int:
    return (w >> pos) & ((1 << width) - 1)


def bnot(x: int, bits: int) -> int:
    mask = (1 << bits) - 1
    return mask - (x & mask)


def get_named_flags(flags: int, flagdict: dict[int, str]) -> str:
    params = []
    for flag, param in flagdict.items():
        if (flags & flag) == flag:
            params.append(param)
            flags &= bnot(flag, 32)
    if flags != 0:
        params.append(f"0x{flags:X}")
    return "|".join(params) if params else "0"
