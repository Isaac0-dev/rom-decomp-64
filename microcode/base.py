from abc import ABC
from gbi_defines import (
    G_IM_FMT_MAP,
    G_IM_SIZ_MAP,
    G_SC_MAP,
    G_SETCOMBINE_ALPHA_COMBINERS,
    G_SETCOMBINE_COLOR_COMBINERS,
    G_SETCOMBINE_MODES,
    G_TX_CLAMP,
    G_TX_MAP,
    G_TX_MIRROR,
)
from utils import debug_print
from texture import (
    load_block,
    load_tile,
    load_tlut,
    set_texture_image,
    set_tile_format,
    set_tile_size,
)
from context import LevelAreaContext
from rom_database import CommandIR, RomDatabase


class Microcode(ABC):
    def __init__(self):
        self.commands = {}
        self.vertex_stride = 2  # Default for GBI1
        self.parent_dl = None

    def get_handler(self, command):
        opcode = (command >> 24) & 0xFF
        # debug_print(f"DEBUG: get_handler opcode=0x{opcode:02X} class={self.__class__.__name__} commands_keys={list(self.commands.keys())[:10]}...")
        if opcode not in self.commands:
            debug_print(f"DEBUG: Unknown opcode 0x{opcode:02X} for {self.__class__.__name__}")
        return self.commands.get(opcode, self.execute_unknown)

    def register_parent_dl(self, dl_span):
        self.parent_dl = dl_span

    def execute_unknown(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("UnknownGfx", {}, commented_out=True)
        return None

    def _SHIFTR(self, val, shift, size):
        return (val >> shift) & ((1 << size) - 1)

    def format_params(self, params):
        return ", ".join(map(str, params))

    def comment_out(self, text, condition=True):
        if not condition:
            return text
        if text.lstrip().startswith("//"):
            return text
        return f"// {text}"

    def serialize_command(self, cmd: CommandIR, db: RomDatabase, location: LevelAreaContext) -> str:
        """Serialize a CommandIR using microcode-specific logic."""
        # Follow the same pattern as execution: serialize_<name>
        if not cmd.name:
            return f"    // Unknown Gfx 0x{cmd.opcode:02X}"
        gfx_cmd = cmd.params[0]

        from rom_database import VertexRecord, TextureRecord, LightRecord, DisplayListRecord

        c = "// " if gfx_cmd.commented_out else ""

        if cmd.name == "gsSP4Triangles":
            # we need to convert this into 2 gsSP2Triangles commands
            # because gsSP4Triangles doesn't exist in coop
            tris = gfx_cmd.params.get("tris", [])
            cmd1 = tris[:-2]
            cmd2 = tris[2:]

            def i2p(indices):
                return ", ".join([str(i) for i in indices])[:-2]

            return f"    {c}gsSP2Triangles({i2p(cmd1)})\n    {c}gsSP2Triangles({i2p(cmd2)})"
        if cmd.name == "gsSPLight":
            from lights import vb_type_name_to_extension

            params = gfx_cmd.params
            light = params.get("light")
            idx = params.get("idx")
            ext = vb_type_name_to_extension(light.type_name, idx - 1)

            return f"    {c}gsSPLight(/* light */ &{light.name}{ext}, /* idx */ {idx})"
        else:
            params_str = ""
            for k, v in gfx_cmd.params.items():
                if (
                    isinstance(v, VertexRecord)
                    or isinstance(v, TextureRecord)
                    or isinstance(v, LightRecord)
                    or isinstance(v, DisplayListRecord)
                ):
                    params_str += f"/* {k} */ {v.name}, "
                elif isinstance(v, str):
                    params_str += f"/* {k} */ {v}, "
                elif isinstance(v, int):
                    params_str += f"/* {k} */ 0x{v:X}, "
                else:
                    raise Exception(
                        f"While looking at {cmd.name} found unknown parameter type {type(v)} for {k} ... {v}"
                    )

        params_str = params_str[:-2]

        return f"    {c}{cmd.name}({params_str})"

    # Common RDP Commands
    def execute_dp_set_texture_image(self, cmd0, cmd1, dis):
        fmt_val = self._SHIFTR(cmd0, 21, 3)
        siz_val = self._SHIFTR(cmd0, 19, 2)
        width = self._SHIFTR(cmd0, 0, 12) + 1
        texture_addr = cmd1

        fmt = G_IM_FMT_MAP.get(fmt_val, str(fmt_val))
        siz = G_IM_SIZ_MAP.get(siz_val, str(siz_val))

        if dis:
            texture_record = set_texture_image(
                texture_addr, fmt_val, siz_val, width, dis.context_prefix
            )
            dis.set_cmd(
                "gsDPSetTextureImage",
                {
                    "fmt": fmt,
                    "siz": siz,
                    "width": width,
                    "texture_record": texture_record,
                },
            )

    def execute_dp_set_tile(self, cmd0, cmd1, dis):
        fmt_val = self._SHIFTR(cmd0, 21, 3)
        siz_val = self._SHIFTR(cmd0, 19, 2)
        line = self._SHIFTR(cmd0, 9, 9)
        tmem = self._SHIFTR(cmd0, 0, 9)
        tile_val = self._SHIFTR(cmd1, 24, 3)
        palette = self._SHIFTR(cmd1, 20, 4)
        cmt_val = self._SHIFTR(cmd1, 18, 2)
        maskt = self._SHIFTR(cmd1, 14, 4)
        shiftt = self._SHIFTR(cmd1, 10, 4)
        cms_val = self._SHIFTR(cmd1, 8, 2)
        masks = self._SHIFTR(cmd1, 4, 4)
        shifts = self._SHIFTR(cmd1, 0, 4)

        fmt = G_IM_FMT_MAP.get(fmt_val, str(fmt_val))
        siz = G_IM_SIZ_MAP.get(siz_val, str(siz_val))
        tile = G_TX_MAP.get(tile_val, str(tile_val))

        def get_flags(val):
            flags = []
            if val & G_TX_MIRROR:
                flags.append("G_TX_MIRROR")
            if val & G_TX_CLAMP:
                flags.append("G_TX_CLAMP")
            if not flags:
                return "G_TX_WRAP"
            return " | ".join(flags)

        cmt = get_flags(cmt_val)
        cms = get_flags(cms_val)

        if dis:
            set_tile_format(tile_val, fmt_val, siz_val)
            dis.set_cmd(
                "gsDPSetTile",
                {
                    "fmt": fmt,
                    "siz": siz,
                    "line": line,
                    "tmem": tmem,
                    "tile": tile,
                    "palette": palette,
                    "cmt": cmt,
                    "maskt": maskt,
                    "shiftt": shiftt,
                    "cms": cms,
                    "masks": masks,
                    "shifts": shifts,
                },
            )

    def execute_dp_load_block(self, cmd0, cmd1, dis):
        uls = self._SHIFTR(cmd0, 12, 12)
        ult = self._SHIFTR(cmd0, 0, 12)
        tile_val = self._SHIFTR(cmd1, 24, 3)
        lrs = self._SHIFTR(cmd1, 12, 12)
        dxt = self._SHIFTR(cmd1, 0, 12)

        tile = G_TX_MAP.get(tile_val, str(tile_val))

        if dis:
            load_block(dis.sTxt, dis.current_pos, tile_val, uls, ult, lrs, dxt, None)
            dis.set_cmd(
                "gsDPLoadBlock",
                {
                    "tile": tile,
                    "uls": uls,
                    "ult": ult,
                    "lrs": lrs,
                    "dxt": dxt,
                },
            )

    def execute_dp_pipe_sync(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPPipeSync", {})

    def execute_dp_set_combine_mode(self, cmd0, cmd1, dis):
        # Cycle 0
        a0 = G_SETCOMBINE_COLOR_COMBINERS["a"].get(self._SHIFTR(cmd0, 20, 4), "0")
        b0 = G_SETCOMBINE_COLOR_COMBINERS["b"].get(self._SHIFTR(cmd1, 28, 4), "0")
        c0 = G_SETCOMBINE_COLOR_COMBINERS["c"].get(self._SHIFTR(cmd0, 15, 5), "0")
        d0 = G_SETCOMBINE_COLOR_COMBINERS["d"].get(self._SHIFTR(cmd1, 15, 3), "0")

        Aa0 = G_SETCOMBINE_ALPHA_COMBINERS["a"].get(self._SHIFTR(cmd0, 12, 3), "0")
        Ab0 = G_SETCOMBINE_ALPHA_COMBINERS["b"].get(self._SHIFTR(cmd1, 12, 3), "0")
        Ac0 = G_SETCOMBINE_ALPHA_COMBINERS["c"].get(self._SHIFTR(cmd0, 9, 3), "0")
        Ad0 = G_SETCOMBINE_ALPHA_COMBINERS["d"].get(self._SHIFTR(cmd1, 9, 3), "0")

        # Cycle 1
        a1 = G_SETCOMBINE_COLOR_COMBINERS["a"].get(self._SHIFTR(cmd0, 5, 4), "0")
        b1 = G_SETCOMBINE_COLOR_COMBINERS["b"].get(self._SHIFTR(cmd1, 24, 4), "0")
        c1 = G_SETCOMBINE_COLOR_COMBINERS["c"].get(self._SHIFTR(cmd0, 0, 5), "0")
        d1 = G_SETCOMBINE_COLOR_COMBINERS["d"].get(self._SHIFTR(cmd1, 6, 3), "0")

        Aa1 = G_SETCOMBINE_ALPHA_COMBINERS["a"].get(self._SHIFTR(cmd1, 21, 3), "0")
        Ab1 = G_SETCOMBINE_ALPHA_COMBINERS["b"].get(self._SHIFTR(cmd1, 3, 3), "0")
        Ac1 = G_SETCOMBINE_ALPHA_COMBINERS["c"].get(self._SHIFTR(cmd1, 18, 3), "0")
        Ad1 = G_SETCOMBINE_ALPHA_COMBINERS["d"].get(self._SHIFTR(cmd1, 0, 3), "0")

        cycle1 = f"{a0}, {b0}, {c0}, {d0}, {Aa0}, {Ab0}, {Ac0}, {Ad0}"
        cycle2 = f"{a1}, {b1}, {c1}, {d1}, {Aa1}, {Ab1}, {Ac1}, {Ad1}"

        cm1 = G_SETCOMBINE_MODES.get(cycle1)
        cm2 = G_SETCOMBINE_MODES.get(cycle2)

        if dis:
            if cm1 and cm2:
                dis.set_cmd(
                    "gsDPSetCombineMode",
                    {"cycle1": cm1, "cycle2": cm2},
                )
            else:
                dis.set_cmd(
                    "gsDPSetCombineLERP",
                    {"cycle1": cycle1, "cycle2": cycle2},
                )

    def execute_dp_fill_rectangle(self, cmd0, cmd1, dis):
        ulx = self._SHIFTR(cmd1, 14, 10)
        uly = self._SHIFTR(cmd1, 2, 10)
        lrx = self._SHIFTR(cmd0, 14, 10)
        lry = self._SHIFTR(cmd0, 2, 10)
        if dis:
            dis.set_cmd(
                "gsDPFillRectangle",
                {"ulx": ulx, "uly": uly, "lrx": lrx, "lry": lry},
                commented_out=True,
            )

    def execute_dp_set_fill_color(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPSetFillColor", {"d": cmd1}, commented_out=True)

    def execute_dp_set_scissor(self, cmd0, cmd1, dis):
        ulx = self._SHIFTR(cmd1, 12, 12)
        uly = self._SHIFTR(cmd1, 0, 12)
        lrx = self._SHIFTR(cmd0, 12, 12)
        lry = self._SHIFTR(cmd0, 0, 12)
        mode_val = self._SHIFTR(cmd0, 24, 2)

        mode = G_SC_MAP.get(mode_val, str(mode_val))

        if dis:
            dis.set_cmd(
                "gsDPSetScissor", {"mode": mode, "ulx": ulx, "uly": uly, "lrx": lrx, "lry": lry}
            )

    def execute_dp_set_fog_color(self, cmd0, cmd1, dis):
        r = self._SHIFTR(cmd1, 24, 8)
        g = self._SHIFTR(cmd1, 16, 8)
        b = self._SHIFTR(cmd1, 8, 8)
        a = self._SHIFTR(cmd1, 0, 8)
        if dis:
            dis.set_cmd("gsDPSetFogColor", {"r": r, "g": g, "b": b, "a": a})

    def execute_dp_set_tile_size(self, cmd0, cmd1, dis):
        uls = self._SHIFTR(cmd0, 12, 12)
        ult = self._SHIFTR(cmd0, 0, 12)
        tile = self._SHIFTR(cmd1, 24, 3)
        lrs = self._SHIFTR(cmd1, 12, 12)
        lrt = self._SHIFTR(cmd1, 0, 12)
        tile_name = G_TX_MAP.get(tile, str(tile))
        if dis:
            set_tile_size(tile, uls, ult, lrs, lrt)
            dis.set_cmd(
                "gsDPSetTileSize",
                {"tile": tile_name, "uls": uls, "ult": ult, "lrs": lrs, "lrt": lrt},
            )

    def execute_dp_load_tile(self, cmd0, cmd1, dis):
        uls = self._SHIFTR(cmd0, 12, 12)
        ult = self._SHIFTR(cmd0, 0, 12)
        tile_val = self._SHIFTR(cmd1, 24, 3)
        lrs = self._SHIFTR(cmd1, 12, 12)
        lrt = self._SHIFTR(cmd1, 0, 12)
        tile_name = G_TX_MAP.get(tile_val, str(tile_val))
        if dis:
            load_tile(dis.sTxt, dis.current_pos, tile_val, uls, ult, lrs, lrt)
            dis.set_cmd(
                "gsDPLoadTile",
                {"tile": tile_name, "uls": uls, "ult": ult, "lrs": lrs, "lrt": lrt},
            )

    def execute_dp_load_tlut(self, cmd0, cmd1, dis):
        tile_val = self._SHIFTR(cmd1, 24, 3)
        count = self._SHIFTR(cmd1, 14, 10)
        tile_name = G_TX_MAP.get(tile_val, str(tile_val))
        if dis:
            real_count = count + 1
            load_tlut(dis.sTxt, real_count, 0, None)
            dis.set_cmd("gsDPLoadTLUT", {"tile": tile_name, "count": count}, commented_out=True)

    def execute_dp_set_env_color(self, cmd0, cmd1, dis):
        r = self._SHIFTR(cmd1, 24, 8)
        g = self._SHIFTR(cmd1, 16, 8)
        b = self._SHIFTR(cmd1, 8, 8)
        a = self._SHIFTR(cmd1, 0, 8)
        if dis:
            dis.set_cmd("gsDPSetEnvColor", {"r": r, "g": g, "b": b, "a": a})

    def execute_dp_set_prim_color(self, cmd0, cmd1, dis):
        m = self._SHIFTR(cmd0, 8, 8)
        l_val = self._SHIFTR(cmd0, 0, 8)
        r = self._SHIFTR(cmd1, 24, 8)
        g = self._SHIFTR(cmd1, 16, 8)
        b = self._SHIFTR(cmd1, 8, 8)
        a = self._SHIFTR(cmd1, 0, 8)
        if dis:
            dis.set_cmd("gsDPSetPrimColor", {"m": m, "l": l_val, "r": r, "g": g, "b": b, "a": a})

    def execute_dp_set_blend_color(self, cmd0, cmd1, dis):
        r = self._SHIFTR(cmd1, 24, 8)
        g = self._SHIFTR(cmd1, 16, 8)
        b = self._SHIFTR(cmd1, 8, 8)
        a = self._SHIFTR(cmd1, 0, 8)
        if dis:
            dis.set_cmd("gsDPSetBlendColor", {"r": r, "g": g, "b": b, "a": a})

    def execute_dp_set_color_image(self, cmd0, cmd1, dis):
        fmt = self._SHIFTR(cmd0, 21, 3)
        siz = self._SHIFTR(cmd0, 19, 2)
        width = self._SHIFTR(cmd0, 0, 12) + 1
        img = cmd1
        if dis:
            dis.set_cmd("gsDPSetColorImage", {"fmt": fmt, "siz": siz, "width": width, "image": img})

    def execute_dp_set_depth_image(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPSetDepthImage", {}, commented_out=True)

    def execute_dp_load_sync(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPLoadSync", {})

    def execute_dp_tile_sync(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPTileSync", {})

    def execute_dp_full_sync(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPFullSync", {})

    def execute_dp_texture_rectangle(self, cmd0, cmd1, dis):
        self._execute_dp_tex_rect(cmd0, cmd1, dis, flip=False)

    def execute_dp_texture_rectangle_flip(self, cmd0, cmd1, dis):
        self._execute_dp_tex_rect(cmd0, cmd1, dis, flip=True)

    def _execute_dp_tex_rect(self, cmd0, cmd1, dis, flip=False):
        tile = self._SHIFTR(cmd0, 24, 3)
        uls = self._SHIFTR(cmd0, 12, 12)
        ult = self._SHIFTR(cmd0, 0, 12)
        lrs = self._SHIFTR(cmd1, 12, 12)
        lrt = self._SHIFTR(cmd1, 0, 12)
        fn = "gsDPTextureRectangleFlip" if flip else "gsDPTextureRectangle"
        if dis:
            dis.set_cmd(
                fn,
                {"uls": uls, "ult": ult, "lrs": lrs, "lrt": lrt, "tile": tile, "sft": 0, "tft": 0},
                commented_out=True,
            )

    def execute_dp_set_prim_depth(self, cmd0, cmd1, dis):
        z = self._SHIFTR(cmd0, 0, 16)
        dz = self._SHIFTR(cmd1, 0, 16)
        if dis:
            dis.set_cmd("gsDPSetPrimDepth", {"z": z, "dz": dz})

    def execute_dp_set_convert(self, cmd0, cmd1, dis):
        k0 = self._SHIFTR(cmd0, 13, 9)
        k1 = self._SHIFTR(cmd0, 4, 9)
        k2 = ((self._SHIFTR(cmd0, 0, 4)) << 5) | self._SHIFTR(cmd1, 27, 5)
        k3 = self._SHIFTR(cmd1, 18, 9)
        k4 = self._SHIFTR(cmd1, 9, 9)
        k5 = self._SHIFTR(cmd1, 0, 9)
        if dis:
            dis.set_cmd(
                "gsDPSetConvert", {"k0": k0, "k1": k1, "k2": k2, "k3": k3, "k4": k4, "k5": k5}
            )

    def execute_dp_set_key_gb(self, cmd0, cmd1, dis):
        cG = self._SHIFTR(cmd0, 8, 8)
        sG = self._SHIFTR(cmd0, 0, 8)
        wG = self._SHIFTR(cmd1, 24, 8)
        cB = self._SHIFTR(cmd1, 16, 8)
        sB = self._SHIFTR(cmd1, 8, 8)
        wB = self._SHIFTR(cmd1, 0, 8)
        if dis:
            dis.set_cmd(
                "gsDPSetKeyGB", {"cG": cG, "sG": sG, "wG": wG, "cB": cB, "sB": sB, "wB": wB}
            )

    def execute_dp_set_key_r(self, cmd0, cmd1, dis):
        cR = self._SHIFTR(cmd0, 8, 8)
        sR = self._SHIFTR(cmd0, 0, 8)
        wR = self._SHIFTR(cmd1, 8, 8)
        if dis:
            dis.set_cmd("gsDPSetKeyR", {"cR": cR, "sR": sR, "wR": wR})
