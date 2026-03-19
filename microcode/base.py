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
        opcode = (cmd0 >> 24) & 0xFF
        if dis:
            dis.text(f"// Unknown command 0x{opcode:02X}: {cmd0:08X} {cmd1:08X}")
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

    # Common RDP Commands
    def execute_dp_set_texture_image(self, cmd0, cmd1, dis):
        fmt_val = self._SHIFTR(cmd0, 21, 3)
        siz_val = self._SHIFTR(cmd0, 19, 2)
        width = self._SHIFTR(cmd0, 0, 12) + 1
        texture_addr = cmd1

        fmt = G_IM_FMT_MAP.get(fmt_val, str(fmt_val))
        siz = G_IM_SIZ_MAP.get(siz_val, str(siz_val))

        if dis:
            texture_name = set_texture_image(
                texture_addr, fmt_val, siz_val, width, dis.context_prefix
            )
            dis.set_cmd(
                "gsDPSetTextureImage",
                {"fmt": fmt_val, "siz": siz_val, "width": width, "w0": cmd0, "w1": cmd1},
            )
            params = [
                f"/* fmt */ {fmt}",
                f"/* siz */ {siz}",
                f"/* width */ {width}",
                f"/* texture */ {texture_name}",
            ]
            dis.text(f"gsDPSetTextureImage({self.format_params(params)})")

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
                    "fmt": fmt_val,
                    "siz": siz_val,
                    "tile": tile_val,
                    "tmem": tmem,
                    "palette": palette,
                    "cmt": cmt_val,
                    "maskt": maskt,
                    "shiftt": shiftt,
                    "cms": cms_val,
                    "masks": masks,
                    "shifts": shifts,
                    "w0": cmd0,
                    "w1": cmd1,
                },
            )
            params = [fmt, siz, line, tmem, tile, palette, cmt, maskt, shiftt, cms, masks, shifts]
            dis.text(f"gsDPSetTile({self.format_params(params)})")

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
                    "tile": tile_val,
                    "uls": uls,
                    "ult": ult,
                    "lrs": lrs,
                    "dxt": dxt,
                    "w0": cmd0,
                    "w1": cmd1,
                },
            )
            params = [tile, uls, ult, lrs, dxt]
            dis.text(f"gsDPLoadBlock({self.format_params(params)})")

    def execute_dp_pipe_sync(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPPipeSync", {"w0": cmd0, "w1": cmd1})
            dis.text("gsDPPipeSync()")

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
            dis.set_cmd("gsDPSetCombineMode", {"modes": [cycle1, cycle2], "w0": cmd0, "w1": cmd1})

            if cm1 and cm2:
                dis.text(f"gsDPSetCombineMode({cm1}, {cm2})")
            else:
                dis.text(f"gsDPSetCombineLERP({cycle1}, {cycle2})")

    def execute_dp_fill_rectangle(self, cmd0, cmd1, dis):
        ulx = self._SHIFTR(cmd1, 14, 10)
        uly = self._SHIFTR(cmd1, 2, 10)
        lrx = self._SHIFTR(cmd0, 14, 10)
        lry = self._SHIFTR(cmd0, 2, 10)
        if dis:
            dis.set_cmd("gsDPFillRectangle", {"w0": cmd0, "w1": cmd1})
            params = [ulx, uly, lrx, lry]
            dis.text(self.comment_out(f"gsDPFillRectangle({self.format_params(params)})"))

    def execute_dp_set_fill_color(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPSetFillColor", {"w0": cmd0, "w1": cmd1})
            dis.text(f"// gsDPSetFillColor(0x{cmd1:08X})")

    def execute_dp_set_scissor(self, cmd0, cmd1, dis):
        ulx = self._SHIFTR(cmd1, 12, 12)
        uly = self._SHIFTR(cmd1, 0, 12)
        lrx = self._SHIFTR(cmd0, 12, 12)
        lry = self._SHIFTR(cmd0, 0, 12)
        mode_val = self._SHIFTR(cmd0, 24, 2)

        mode = G_SC_MAP.get(mode_val, str(mode_val))

        if dis:
            dis.set_cmd("gsDPSetScissor", {"w0": cmd0, "w1": cmd1})
            params = [mode, ulx, uly, lrx, lry]
            dis.text(f"gsDPSetScissor({self.format_params(params)})")

    def execute_dp_set_fog_color(self, cmd0, cmd1, dis):
        r = self._SHIFTR(cmd1, 24, 8)
        g = self._SHIFTR(cmd1, 16, 8)
        b = self._SHIFTR(cmd1, 8, 8)
        a = self._SHIFTR(cmd1, 0, 8)
        if dis:
            dis.set_cmd("gsDPSetFogColor", {"w0": cmd0, "w1": cmd1})
            params = [r, g, b, a]
            dis.text(f"gsDPSetFogColor({self.format_params(params)})")

    def execute_dp_set_tile_size(self, cmd0, cmd1, dis):
        uls = self._SHIFTR(cmd0, 12, 12)
        ult = self._SHIFTR(cmd0, 0, 12)
        tile = self._SHIFTR(cmd1, 24, 3)
        lrs = self._SHIFTR(cmd1, 12, 12)
        lrt = self._SHIFTR(cmd1, 0, 12)
        if dis:
            set_tile_size(tile, uls, ult, lrs, lrt)
            dis.set_cmd("gsDPSetTileSize", {"w0": cmd0, "w1": cmd1, "modes": [uls, ult, lrs, lrt]})
            params = [tile, uls, ult, lrs, lrt]
            dis.text(f"gsDPSetTileSize({self.format_params(params)})")

    def execute_dp_load_tile(self, cmd0, cmd1, dis):
        uls = self._SHIFTR(cmd0, 12, 12)
        ult = self._SHIFTR(cmd0, 0, 12)
        tile_val = self._SHIFTR(cmd1, 24, 3)
        lrs = self._SHIFTR(cmd1, 12, 12)
        lrt = self._SHIFTR(cmd1, 0, 12)
        tile = G_TX_MAP.get(tile_val, str(tile_val))
        if dis:
            load_tile(dis.sTxt, dis.current_pos, tile_val, uls, ult, lrs, lrt)
            dis.set_cmd("gsDPLoadTile", {"w0": cmd0, "w1": cmd1})
            params = [tile, uls, ult, lrs, lrt]
            dis.text(f"gsDPLoadTile({self.format_params(params)})")

    def execute_dp_load_tlut(self, cmd0, cmd1, dis):
        tile_val = self._SHIFTR(cmd1, 24, 3)
        count = self._SHIFTR(cmd1, 14, 10)
        tile = G_TX_MAP.get(tile_val, str(tile_val))
        if dis:
            real_count = count + 1
            load_tlut(dis.sTxt, real_count, 0, None)
            dis.set_cmd("gsDPLoadTLUT", {"w0": cmd0, "w1": cmd1})
            params = [tile, count]
            dis.text(f"// gsDPLoadTLUT_cmd({self.format_params(params)})")

    def execute_dp_set_env_color(self, cmd0, cmd1, dis):
        r = self._SHIFTR(cmd1, 24, 8)
        g = self._SHIFTR(cmd1, 16, 8)
        b = self._SHIFTR(cmd1, 8, 8)
        a = self._SHIFTR(cmd1, 0, 8)
        if dis:
            dis.set_cmd("gsDPSetEnvColor", {"w0": cmd0, "w1": cmd1})
            params = [r, g, b, a]
            dis.text(f"gsDPSetEnvColor({self.format_params(params)})")

    def execute_dp_set_prim_color(self, cmd0, cmd1, dis):
        m = self._SHIFTR(cmd0, 8, 8)
        l_val = self._SHIFTR(cmd0, 0, 8)
        r = self._SHIFTR(cmd1, 24, 8)
        g = self._SHIFTR(cmd1, 16, 8)
        b = self._SHIFTR(cmd1, 8, 8)
        a = self._SHIFTR(cmd1, 0, 8)
        if dis:
            dis.set_cmd("gsDPSetPrimColor", {"w0": cmd0, "w1": cmd1})
            params = [m, l_val, r, g, b, a]
            dis.text(f"gsDPSetPrimColor({self.format_params(params)})")

    def execute_dp_set_blend_color(self, cmd0, cmd1, dis):
        r = self._SHIFTR(cmd1, 24, 8)
        g = self._SHIFTR(cmd1, 16, 8)
        b = self._SHIFTR(cmd1, 8, 8)
        a = self._SHIFTR(cmd1, 0, 8)
        if dis:
            dis.set_cmd("gsDPSetBlendColor", {"w0": cmd0, "w1": cmd1})
            params = [r, g, b, a]
            dis.text(f"gsDPSetBlendColor({self.format_params(params)})")

    def execute_dp_set_color_image(self, cmd0, cmd1, dis):
        fmt = self._SHIFTR(cmd0, 21, 3)
        siz = self._SHIFTR(cmd0, 19, 2)
        width = self._SHIFTR(cmd0, 0, 12) + 1
        img = cmd1
        if dis:
            dis.set_cmd("gsDPSetColorImage", {"w0": cmd0, "w1": cmd1})
            params = [fmt, siz, width, f"0x{img:08X}"]
            dis.text(f"gsDPSetColorImage({self.format_params(params)})")

    def execute_dp_set_depth_image(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPSetDepthImage", {"w0": cmd0, "w1": cmd1})
            dis.text(f"// gsDPSetDepthImage(0x{cmd1:08X})")

    def execute_dp_load_sync(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPLoadSync", {"w0": cmd0, "w1": cmd1})
            dis.text("gsDPLoadSync()")

    def execute_dp_tile_sync(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPTileSync", {"w0": cmd0, "w1": cmd1})
            dis.text("gsDPTileSync()")

    def execute_dp_full_sync(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPFullSync", {"w0": cmd0, "w1": cmd1})
            dis.text("gsDPFullSync()")

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
            dis.set_cmd(fn, {"w0": cmd0, "w1": cmd1})
            params = [uls, ult, lrs, lrt, tile, 0, 0, 0, 0]
            dis.text(self.comment_out(f"{fn}({self.format_params(params)})"))

    def execute_dp_set_prim_depth(self, cmd0, cmd1, dis):
        z = self._SHIFTR(cmd0, 0, 16)
        dz = self._SHIFTR(cmd1, 0, 16)
        if dis:
            dis.set_cmd("gsDPSetPrimDepth", {"w0": cmd0, "w1": cmd1})
            dis.text(f"gsDPSetPrimDepth({z}, {dz})")

    def execute_dp_set_convert(self, cmd0, cmd1, dis):
        k0 = self._SHIFTR(cmd0, 13, 9)
        k1 = self._SHIFTR(cmd0, 4, 9)
        k2 = ((self._SHIFTR(cmd0, 0, 4)) << 5) | self._SHIFTR(cmd1, 27, 5)
        k3 = self._SHIFTR(cmd1, 18, 9)
        k4 = self._SHIFTR(cmd1, 9, 9)
        k5 = self._SHIFTR(cmd1, 0, 9)
        if dis:
            dis.set_cmd("gsDPSetConvert", {"w0": cmd0, "w1": cmd1})
            params = [k0, k1, k2, k3, k4, k5]
            dis.text(f"gsDPSetConvert({self.format_params(params)})")

    def execute_dp_set_key_gb(self, cmd0, cmd1, dis):
        cG = self._SHIFTR(cmd0, 8, 8)
        sG = self._SHIFTR(cmd0, 0, 8)
        wG = self._SHIFTR(cmd1, 24, 8)
        cB = self._SHIFTR(cmd1, 16, 8)
        sB = self._SHIFTR(cmd1, 8, 8)
        wB = self._SHIFTR(cmd1, 0, 8)
        if dis:
            dis.set_cmd("gsDPSetKeyGB", {"w0": cmd0, "w1": cmd1})
            params = [cG, sG, wG, cB, sB, wB]
            dis.text(f"gsDPSetKeyGB({self.format_params(params)})")

    def execute_dp_set_key_r(self, cmd0, cmd1, dis):
        cR = self._SHIFTR(cmd0, 8, 8)
        sR = self._SHIFTR(cmd0, 0, 8)
        wR = self._SHIFTR(cmd1, 8, 8)
        if dis:
            dis.set_cmd("gsDPSetKeyR", {"w0": cmd0, "w1": cmd1})
            params = [cR, sR, wR]
            dis.text(f"gsDPSetKeyR({self.format_params(params)})")
