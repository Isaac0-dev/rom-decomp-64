from .base import Microcode
from gbi_defines import (
    G_DL_PUSH,
    G_GEOMETRYMODE_FLAGS_GBI1,
    G_MOVEWORD_INDICES,
    G_MTX_LOAD,
    G_MTX_PROJECTION,
    G_MTX_PUSH,
    G_ON_OFF_MAP,
    G_SETOTHERMODE_H_SHIFTS,
    G_SETOTHERMODE_L_SHIFTS,
    G_TX_MAP,
    get_named_flags,
)
import vertices
from typing import Dict, cast
from texture import set_tile_size
from utils import debug_print


class GBI1(Microcode):
    def __init__(self):
        super().__init__()
        self.vertex_stride = 2
        self.commands = {
            0x00: self.execute_sp_noop,
            0x01: self.execute_sp_matrix,
            0x02: self.execute_reserved,  # G_RESERVED0
            0x03: self.execute_move_mem,
            0x04: self.execute_vertex,
            0x05: self.execute_reserved,  # G_RESERVED1
            0x06: self.execute_sp_display_list,
            0x07: self.execute_reserved,  # G_RESERVED2
            0x08: self.execute_reserved,  # G_RESERVED3
            0x09: self.execute_sprite_2d_base,
            0xAF: self.execute_load_ucode,
            0xB0: self.execute_branch_z,
            0xB1: self.execute_tri2,
            0xB2: self.execute_modify_vertex,
            0xB3: self.execute_rdp_half_2,
            0xB4: self.execute_rdp_half_1,
            0xB5: self.execute_line_3d,
            0xB6: self.execute_clear_geometry_mode,
            0xB7: self.execute_set_geometry_mode,
            0xB8: self.execute_end_dl,
            0xB9: self.execute_set_other_mode_l,
            0xBA: self.execute_set_other_mode_h,
            0xBB: self.execute_texture,
            0xBC: self.execute_move_word,
            0xBD: self.execute_pop_matrix,
            0xBE: self.execute_cull_dl,
            0xBF: self.execute_tri1,
            0xC0: self.execute_noop,
            # RDP Commands
            0xE4: self.execute_dp_texture_rectangle,
            0xE5: self.execute_dp_texture_rectangle_flip,
            0xE6: self.execute_dp_load_sync,
            0xE7: self.execute_dp_pipe_sync,
            0xE8: self.execute_dp_tile_sync,
            0xE9: self.execute_dp_full_sync,
            0xEA: self.execute_dp_set_key_gb,
            0xEB: self.execute_dp_set_key_r,
            0xEC: self.execute_dp_set_convert,
            0xED: self.execute_dp_set_scissor,
            0xEE: self.execute_dp_set_prim_depth,
            0xEF: self.execute_dp_set_other_mode,
            0xF0: self.execute_dp_load_tlut,
            0xF2: self.execute_dp_set_tile_size,
            0xF3: self.execute_dp_load_block,
            0xF4: self.execute_dp_load_tile,
            0xF5: self.execute_dp_set_tile,
            0xF6: self.execute_dp_fill_rectangle,
            0xF7: self.execute_dp_set_fill_color,
            0xF8: self.execute_dp_set_fog_color,
            0xF9: self.execute_dp_set_blend_color,
            0xFA: self.execute_dp_set_prim_color,
            0xFB: self.execute_dp_set_env_color,
            0xFC: self.execute_dp_set_combine_mode,
            0xFD: self.execute_dp_set_texture_image,
            0xFE: self.execute_dp_set_depth_image,
            0xFF: self.execute_dp_set_color_image,
        }

    def execute_reserved(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsSPReserved", {"w0": cmd0, "w1": cmd1}, commented_out=True)

    def execute_clear_geometry_mode(self, cmd0, cmd1, dis):
        import display_list

        mask = cmd1
        display_list.current_geometry_mode &= ~mask
        if dis:
            flags = get_named_flags(mask & 0x00FFFFFF, G_GEOMETRYMODE_FLAGS_GBI1)
            dis.set_cmd("gsSPClearGeometryMode", {"flags": flags})

    def execute_set_geometry_mode(self, cmd0, cmd1, dis):
        import display_list

        mask = cmd1
        display_list.current_geometry_mode |= mask
        if dis:
            flags = get_named_flags(mask & 0x00FFFFFF, G_GEOMETRYMODE_FLAGS_GBI1)
            dis.set_cmd("gsSPSetGeometryMode", {"flags": flags})

    def execute_sp_noop(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsSPNoOp", {})

    def execute_noop(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPNoOp", {})

    def execute_sprite_2d_base(self, cmd0, cmd1, dis):
        # Sprite2DBase command (0x09) - used in F3DEX for 2D sprites
        if dis:
            vbase = cmd0 & 0x00FFFFFF
            dis.set_cmd("gsSPSprite2DBase", {"vbase": vbase}, commented_out=True)

    def execute_sp_matrix(self, cmd0, cmd1, dis):
        address = cmd1

        if dis:
            flags = self._SHIFTR(cmd0, 16, 8)
            t = []
            if flags & G_MTX_PROJECTION:
                t.append("G_MTX_PROJECTION")
            else:
                t.append("G_MTX_MODELVIEW")

            if flags & G_MTX_LOAD:
                t.append("G_MTX_LOAD")
            else:
                t.append("G_MTX_MUL")

            if flags & G_MTX_PUSH:
                t.append("G_MTX_PUSH")

            flags_str = " | ".join(t)
            dis.set_cmd("gsSPMatrix", {"address": address, "flags": flags_str}, commented_out=True)

    def execute_move_mem(self, cmd0, cmd1, dis):
        type_val = self._SHIFTR(cmd0, 16, 8)
        length = self._SHIFTR(cmd0, 0, 16)
        address = cmd1

        if dis:
            # Check for specific macro expansions like gsSPViewport
            if type_val == 0x80 and length == 16:  # G_MV_VIEWPORT
                dis.set_cmd("gsSPViewport", {"address": address})
                return

            if type_val == 0x82:  # G_MV_MATRIX
                pass

            if type_val == 0x84:  # G_MV_LOOKATX
                pass

            if type_val >= 0x86 and type_val <= 0x94:  # G_MV_LIGHT
                if length > 48:
                    debug_print(f"Invalid length for G_MV_LIGHT: {length}")
                    return

                # TODO: Figure this out
                import lights

                light_idx = (type_val - 0x86) // 2
                if length == 40:
                    # Split Lights2 into Lights1 and Light
                    l1_record = lights.parse_light(address, 24, dis.sTxt, dis.context_prefix)
                    l2_record = lights.parse_light(address + 24, 16, dis.sTxt, dis.context_prefix)
                    dis.set_cmd(
                        "gsSPSetLights1", {"light1": l1_record}, commented_out=l1_record is None
                    )
                    dis.set_cmd(
                        "gsSPLight",
                        {"light": l2_record, "idx": light_idx + 2},
                        commented_out=l2_record is None,
                    )
                    dis.set_cmd("gsSPNumLights", {"count": "NUMLIGHTS_2"}, commented_out=True)
                elif length == 24:
                    # Standard Lights1 (Ambient + Light)
                    light_record = lights.parse_light(address, length, dis.sTxt, dis.context_prefix)
                    dis.set_cmd(
                        "gsSPSetLights1",
                        {"light": light_record},
                        commented_out=light_record is None,
                    )
                else:
                    # One light or ambient on it's own
                    light_record = lights.parse_light(address, length, dis.sTxt, dis.context_prefix)
                    dis.set_cmd(
                        "gsSPLight",
                        {"light": light_record, "idx": light_idx + 1},
                        commented_out=light_record is None,
                    )
                return

            dis.set_cmd("gsSPMoveMem", {}, commented_out=True)

    def execute_vertex(self, cmd0, cmd1, dis):
        v0 = self._SHIFTR(cmd0, 16, 8) // self.vertex_stride
        n = self._SHIFTR(cmd0, 10, 6)
        address = cmd1

        if dis:
            vertices_record = vertices.parse_vertices(
                address, n, dis.sTxt, dis.context_prefix, self.parent_dl
            )
            if vertices_record is None:
                debug_print(f"Failed to parse vertices at address {address}")
                return
            dis.set_cmd(
                "gsSPVertex",
                {
                    "vtx_name": vertices_record,
                    "count": n,
                    "v0": v0,
                    "address": address,
                },
            )

    def execute_sp_display_list(self, cmd0, cmd1, dis):
        param = self._SHIFTR(cmd0, 16, 8)
        address = cmd1

        if dis:
            dl_record = dis.parse_dl(address)

            if param == G_DL_PUSH:
                dis.set_cmd("gsSPDisplayList", {"dl": dl_record})
            else:
                dis.set_cmd("gsSPBranchList", {"dl": dl_record})
                dis.branch_taken = True  # Signal that we branched

    def execute_load_ucode(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsSPLoadUcode", {}, commented_out=True)

    def execute_branch_z(self, cmd0, cmd1, dis):
        vtx = self._SHIFTR(cmd0, 12, 12)
        zval = cmd1
        if dis:
            dis.set_cmd("gsSPBranchLessZ", {"vtx": vtx, "zval": zval}, commented_out=True)

    def execute_tri2(self, cmd0, cmd1, dis):
        v00 = self._SHIFTR(cmd0, 16, 8) // self.vertex_stride
        v01 = self._SHIFTR(cmd0, 8, 8) // self.vertex_stride
        v02 = self._SHIFTR(cmd0, 0, 8) // self.vertex_stride
        v10 = self._SHIFTR(cmd1, 16, 8) // self.vertex_stride
        v11 = self._SHIFTR(cmd1, 8, 8) // self.vertex_stride
        v12 = self._SHIFTR(cmd1, 0, 8) // self.vertex_stride

        if dis:
            dis.set_cmd(
                "gsSP2Triangles",
                {
                    "v00": v00,
                    "v01": v01,
                    "v02": v02,
                    "flag0": 0,
                    "v10": v10,
                    "v11": v11,
                    "v12": v12,
                    "flag1": 0,
                },
            )

    def execute_modify_vertex(self, cmd0, cmd1, dis):
        vtx = self._SHIFTR(cmd0, 16, 16) // 2
        where = self._SHIFTR(cmd0, 0, 16)
        val = cmd1
        if dis:
            dis.set_cmd("gsSPModifyVertex", {"vtx": vtx, "where": where, "val": val})

    def execute_rdp_half_2(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPRdphalf2", {}, commented_out=True)

    def execute_rdp_half_1(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPRdphalf1", {}, commented_out=True)

    def execute_line_3d(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsSPLine3D", {"w0": cmd0, "w1": cmd1})
            v0 = self._SHIFTR(cmd0, 16, 8)
            wd = self._SHIFTR(cmd1, 24, 8)
            v0 = self._SHIFTR(cmd1, 16, 8)
            v1 = self._SHIFTR(cmd1, 8, 8)
            v2 = self._SHIFTR(cmd1, 0, 8)

            dis.set_cmd("gsSPLine3D", {"v0": v0, "v1": v1, "v2": v2, "wd": wd}, commented_out=True)

    def execute_end_dl(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsSPEndDisplayList", {})
            dis.end_dl = True  # Signal to stop parsing

    def execute_set_other_mode_l(self, cmd0, cmd1, dis):
        shift = self._SHIFTR(cmd0, 8, 8)
        length = self._SHIFTR(cmd0, 0, 8)
        data = cmd1

        if dis:
            cmd_info = G_SETOTHERMODE_L_SHIFTS.get(shift)
            if cmd_info:
                cmd_name = cmd_info["cmd"]
                const_val = cast(Dict[int, str], cmd_info["consts"]).get(data, f"0x{data:X}")
                dis.set_cmd(cmd_name, {"value": const_val})
            else:
                dis.set_cmd(
                    "gsSPSetOtherMode",
                    {"cmd": "G_SETOTHERMODE_L", "shift": shift, "len": length, "val": data},
                )

    def execute_set_other_mode_h(self, cmd0, cmd1, dis):
        shift = self._SHIFTR(cmd0, 8, 8)
        length = self._SHIFTR(cmd0, 0, 8)
        data = cmd1

        if dis:
            cmd_info = G_SETOTHERMODE_H_SHIFTS.get(shift)
            if cmd_info:
                cmd_name = cmd_info["cmd"]
                const_val = cast(Dict[int, str], cmd_info["consts"]).get(data, f"0x{data:X}")
                dis.set_cmd(cmd_name, {"value": const_val})
            else:
                dis.set_cmd(
                    "gsSPSetOtherMode",
                    {"cmd": "G_SETOTHERMODE_H", "shift": shift, "len": length, "val": data},
                )

    def execute_texture(self, cmd0, cmd1, dis):
        s = self._SHIFTR(cmd1, 16, 16)
        t = self._SHIFTR(cmd1, 0, 16)
        level = self._SHIFTR(cmd0, 11, 3)
        tile_val = self._SHIFTR(cmd0, 8, 3)
        on_val = self._SHIFTR(cmd0, 0, 8)

        tile = G_TX_MAP.get(tile_val, str(tile_val))
        on = G_ON_OFF_MAP.get(on_val, str(on_val))

        if dis:
            # When G_TEXTURE_GEN is set, texture dimensions come from scale values
            import display_list

            G_TEXTURE_GEN = 0x40000
            if (display_list.current_geometry_mode & G_TEXTURE_GEN) == G_TEXTURE_GEN:
                # Extract width/height from texture scale (shifted by 6)
                w = s >> 6
                h = t >> 6

                if w == 31:
                    w = 32
                elif w == 62:
                    w = 64
                if h == 31:
                    h = 32
                elif h == 62:
                    h = 64

                # Store dimensions for texture extraction
                set_tile_size(tile_val, 0, 0, (w - 1) << 2, (h - 1) << 2)

            dis.set_cmd(
                "gsSPTexture",
                {"s": s, "t": t, "level": level, "tile": tile, "on": on},
            )

    def execute_move_word(self, cmd0, cmd1, dis):
        index = self._SHIFTR(cmd0, 0, 8)
        offset = self._SHIFTR(cmd0, 8, 16)
        data = cmd1

        if dis:
            index_name = G_MOVEWORD_INDICES.get(index)

            if index_name == "G_MW_NUMLIGHT":
                # Decode NUMLIGHTS packing
                if data >= 0x80000000 and offset == 0:
                    num_lights = ((data - 0x80000000) >> 5) - 1
                    dis.set_cmd("gsSPNumLights", {"count": num_lights})
                    return
                elif data <= 8:
                    dis.set_cmd("gsSPNumLights", {"count": data})
                    return
            elif index_name == "G_MW_CLIP":
                dis.set_cmd("gsSPClipRatio", {"ratio": offset, "val": data}, commented_out=True)
                return
            elif index_name == "G_MW_SEGMENT":
                dis.set_cmd("gsSPSegment", {"seg": offset >> 2, "addr": data}, commented_out=True)
                return
            elif index_name == "G_MW_FOG":
                fog_mul = (data >> 16) & 0xFFFF
                fog_off = data & 0xFFFF
                if fog_off & 0x8000:
                    fog_off -= 0x10000
                dis.set_cmd("gsSPFogFactor", {"mul": fog_mul, "off": fog_off & 0xFFFF})
                return
            elif index_name == "G_MW_PERSPNORM":
                dis.set_cmd("gSPPerspNormalize", {"val": data}, commented_out=True)
                return

            dis.set_cmd(
                "gsSPMoveWord",
                {"index": index_name or index, "offset": offset, "data": data},
                commented_out=True,
            )

    def execute_pop_matrix(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsSPPopMatrix", {}, commented_out=True)

    def execute_cull_dl(self, cmd0, cmd1, dis):
        vstart = self._SHIFTR(cmd0, 0, 16) // 40
        vend = cmd1 // 40
        if dis:
            dis.set_cmd("gsSPCullDisplayList", {"v0": vstart, "vn": vend})

    def execute_tri1(self, cmd0, cmd1, dis):
        v0 = self._SHIFTR(cmd1, 16, 8) // self.vertex_stride
        v1 = self._SHIFTR(cmd1, 8, 8) // self.vertex_stride
        v2 = self._SHIFTR(cmd1, 0, 8) // self.vertex_stride
        flag = self._SHIFTR(cmd1, 24, 8)

        if dis:
            dis.set_cmd("gsSP1Triangle", {"v0": v0, "v1": v1, "v2": v2, "flag": flag})

    def execute_dp_set_other_mode(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPSetOtherMode", {})
