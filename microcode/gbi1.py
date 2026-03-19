from .base import Microcode
from gbi_defines import (
    G_DL_PUSH,
    G_GEOMETRYMODE_FLAGS,
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
import lights
from typing import Dict, cast
from texture import set_tile_size


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
            dis.set_cmd("gsSPReserved", {"w0": cmd0, "w1": cmd1})
            dis.text(f"// gsSPReserved(0x{cmd0:08X}, 0x{cmd1:08X})")

    def execute_clear_geometry_mode(self, cmd0, cmd1, dis):
        import display_list

        mask = cmd1
        display_list.current_geometry_mode &= ~mask
        if dis:
            dis.set_cmd("gsSPClearGeometryMode", {"w0": cmd0, "w1": cmd1})
            dis.text(f"gsSPClearGeometryMode(0x{mask:08X})")

    def execute_set_geometry_mode(self, cmd0, cmd1, dis):
        import display_list

        mask = cmd1
        display_list.current_geometry_mode |= mask
        if dis:
            # set_flags = cmd1 & 0xFFFFFF
            # set_params = get_named_flags(set_flags, G_GEOMETRYMODE_FLAGS)
            # clr_flags = bnot(C(cmd0, 0, 24), 24) & 0xFFFFFF
            # clr_params = get_named_flags(clr_flags, G_GEOMETRYMODE_FLAGS)
            # if clr_flags == 0xFFFFFF:
            #     dis.set_cmd("gsSPLoadGeometryMode", {"w0": cmd0, "w1": cmd1})
            #     dis.text(f"gsSPLoadGeometryMode({set_params})")
            #     return
            # if set_flags == 0:
            #     dis.set_cmd("gsSPClearGeometryMode", {"w0": cmd0, "w1": cmd1})
            #     dis.text(f"gsSPClearGeometryMode({clr_params})")
            #     return
            # if clr_flags == 0:
            #     dis.set_cmd("gsSPSetGeometryMode", {"w0": cmd0, "w1": cmd1})
            #     dis.text(f"gsSPSetGeometryMode({set_params})")
            #     return
            # dis.set_cmd("gsSPGeometryMode", {"w0": cmd0, "w1": cmd1})
            # dis.text(f"gsSPGeometryMode({clr_params}, {set_params})")

            dis.set_cmd("gsSPSetGeometryMode", {"w0": cmd0, "w1": cmd1})
            dis.text(
                f"gsSPSetGeometryMode({get_named_flags(mask & 0xFFFFFF, G_GEOMETRYMODE_FLAGS)})"
            )

    def execute_sp_noop(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsSPNoOp", {"w0": cmd0, "w1": cmd1})
            dis.text("gsSPNoOp()")

    def execute_noop(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPNoOp", {"w0": cmd0, "w1": cmd1})
            dis.text("gsDPNoOp()")

    def execute_sprite_2d_base(self, cmd0, cmd1, dis):
        # Sprite2DBase command (0x09) - used in F3DEX for 2D sprites
        if dis:
            dis.set_cmd("gsSPSprite2DBase", {"w0": cmd0, "w1": cmd1})
            dis.text("// gsSPSprite2DBase(/* TODO */)")

    def execute_sp_matrix(self, cmd0, cmd1, dis):
        flags = self._SHIFTR(cmd0, 16, 8)
        self._SHIFTR(cmd0, 0, 16)
        address = cmd1

        if dis:
            dis.set_cmd("gsSPMatrix", {"w0": cmd0, "w1": cmd1})

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
            else:
                t.append("G_MTX_NOPUSH")

            params = [f"0x{address:08X}", " | ".join(t)]
            dis.text(f"// gsSPMatrix({self.format_params(params)})")

    def execute_move_mem(self, cmd0, cmd1, dis):
        type_val = self._SHIFTR(cmd0, 16, 8)
        length = self._SHIFTR(cmd0, 0, 16)
        address = cmd1

        if dis:
            # Check for specific macro expansions like gsSPViewport
            if type_val == 0x80 and length == 16:  # G_MV_VIEWPORT
                dis.set_cmd("gsSPViewport", {"w0": cmd0, "w1": cmd1})
                dis.text(f"// gsSPViewport(0x{address:08X})")
                return

            if type_val == 0x82:  # G_MV_MATRIX
                # This is handled by gsSPMatrix, so this case should not be hit if the command is 0x01
                # But if it's a movemem, it's a different command.
                # For now, just log it as a generic movemem.
                pass

            if type_val == 0x84:  # G_MV_LOOKATX
                pass

            if type_val >= 0x86 and type_val <= 0x94:  # G_MV_LIGHT
                # Calculate light index (0 = Amb, 1 = Light1, 2 = Light2)
                # type_val starts at 0x86, increments by 2
                light_idx = (type_val - 0x86) // 2

                if length == 40:
                    # Split Lights2 into Lights1 and Light
                    l1_name, type_name = lights.parse_light(cmd1, 24, dis.sTxt, dis.context_prefix)
                    l2_name, type_name2 = lights.parse_light(
                        cmd1 + 24, 16, dis.sTxt, dis.context_prefix
                    )

                    dis.set_cmd(
                        "gsSPSetLights1", {"w0": cmd0, "w1": cmd1}
                    )  # Use SetLights1 as the primary command
                    dis.text(self.comment_out(f"gsSPSetLights1({l1_name})", l1_name == "NULL"))
                    dis.text(
                        self.comment_out(
                            f"gsSPLight(&{l2_name}, {light_idx + 2})", l2_name == "NULL"
                        )
                    )
                    dis.text(self.comment_out("gsSPNumLights(NUMLIGHTS_2)", l2_name == "NULL"))

                elif length == 24:
                    # Standard Lights1 (Ambient + Light)
                    light_name, type_name = lights.parse_light(
                        cmd1, length, dis.sTxt, dis.context_prefix
                    )
                    dis.set_cmd("gsSPSetLights1", {"w0": cmd0, "w1": cmd1})
                    dis.text(
                        self.comment_out(f"gsSPSetLights1({light_name})", light_name == "NULL")
                    )
                else:
                    # One light or ambient on it's own
                    light_name, type_name = lights.parse_light(
                        cmd1, length, dis.sTxt, dis.context_prefix
                    )
                    dis.set_cmd("gsSPLight", {"w0": cmd0, "w1": cmd1})
                    dis.text(
                        self.comment_out(
                            f"gsSPLight(&{light_name}{lights.vb_type_name_to_extension(type_name, light_idx)}, {light_idx + 1})",
                            light_name == "NULL",
                        )
                    )
                return

            # if type_val == 0x88: # G_MV_LIGHT
            #     light_name = lights.parse_light(cmd1, 40, dis.sTxt, dis.context_prefix)
            #     dis.set_cmd("gsSPSetLights2", {"w0": cmd0, "w1": cmd1})
            #     dis.text(f"// gsSPSetLights2({light_name})")
            #     return

            if type_val == 0x8A:  # G_MV_VIEWPORT
                # This is handled by gsSPViewport
                pass

            dis.text(f"// gsDma1p(G_MOVEMEM, 0x{address:08X}, {length}, {type_val})")

    def execute_vertex(self, cmd0, cmd1, dis):
        v0 = self._SHIFTR(cmd0, 16, 8) // self.vertex_stride
        n = self._SHIFTR(cmd0, 10, 6)
        address = cmd1

        if dis:
            vertices_name = vertices.parse_vertices(
                address, n, dis.sTxt, dis.context_prefix, self.parent_dl
            )
            dis.set_cmd(
                "gsSPVertex",
                {
                    "w0": cmd0,
                    "w1": cmd1,
                    "v0": v0,
                    "count": n,
                    "vtx_name": vertices_name,
                    "address": address,
                },
            )
            params = [
                f"/* vertices */ {vertices_name}",
                f"/* count */ {n}",
                f"/* v0 */ {v0}",
            ]
            dis.text(f"gsSPVertex({self.format_params(params)})")

    def execute_sp_display_list(self, cmd0, cmd1, dis):
        param = self._SHIFTR(cmd0, 16, 8)
        address = cmd1

        if dis:
            dl_name = dis.parse_dl(address)

            if param == G_DL_PUSH:
                dis.set_cmd("gsSPDisplayList", {"w0": cmd0, "w1": cmd1, "subdl": True})
                dis.text(f"gsSPDisplayList({dl_name})")
            else:
                dis.set_cmd("gsSPBranchList", {"w0": cmd0, "w1": cmd1})
                dis.text(f"gsSPBranchList({dl_name})")
                dis.branch_taken = True  # Signal that we branched

    def execute_load_ucode(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsSPLoadUcode", {"w0": cmd0, "w1": cmd1})
            dis.text(f"// gsSPLoadUcode(0x{cmd0:08X}, 0x{cmd1:08X})")

    def execute_branch_z(self, cmd0, cmd1, dis):
        vtx = self._SHIFTR(cmd0, 12, 12)
        zval = cmd1
        if dis:
            dis.set_cmd("gsSPBranchLessZ", {"w0": cmd0, "w1": cmd1})
            dis.text(f"gsSPBranchLessZ(/* vtx */ {vtx}, /* zval */ {zval}, ...)")

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
                {"w0": cmd0, "w1": cmd1, "indices": [v00, v01, v02, v10, v11, v12]},
            )
            params = [v00, v01, v02, 0, v10, v11, v12, 0]
            dis.text(f"gsSP2Triangles({self.format_params(params)})")

    def execute_modify_vertex(self, cmd0, cmd1, dis):
        vtx = self._SHIFTR(cmd0, 16, 16) // 2
        where = self._SHIFTR(cmd0, 0, 16)
        val = cmd1
        if dis:
            dis.set_cmd("gsSPModifyVertex", {"w0": cmd0, "w1": cmd1})
            dis.text(f"gsSPModifyVertex({vtx}, {where}, {val})")

    def execute_rdp_half_2(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPRdphalf2", {"w0": cmd0, "w1": cmd1})
            dis.text(f"gsDPRdphalf2(0x{cmd1:08X})")

    def execute_rdp_half_1(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPRdphalf1", {"w0": cmd0, "w1": cmd1})
            dis.text(f"gsDPRdphalf1(0x{cmd1:08X})")

    def execute_line_3d(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsSPLine3D", {"w0": cmd0, "w1": cmd1})
            v0 = self._SHIFTR(cmd0, 16, 8)
            wd = self._SHIFTR(cmd1, 24, 8)
            v0 = self._SHIFTR(cmd1, 16, 8)
            v1 = self._SHIFTR(cmd1, 8, 8)
            v2 = self._SHIFTR(cmd1, 0, 8)

            dis.text(self.comment_out(f"gsSPLine3D({v0}, {v1}, {v2}, {wd})"))

    def execute_end_dl(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsSPEndDisplayList", {"w0": cmd0, "w1": cmd1, "end": True})
            dis.text("gsSPEndDisplayList()")
            dis.end_dl = True  # Signal to stop parsing

    def execute_set_other_mode_l(self, cmd0, cmd1, dis):
        shift = self._SHIFTR(cmd0, 8, 8)
        length = self._SHIFTR(cmd0, 0, 8)
        data = cmd1

        if dis:
            # Provide a machine-readable record for the other-mode change
            dis.set_cmd("gsSPSetOtherMode", {"w0": cmd0, "w1": cmd1})
            cmd_info = G_SETOTHERMODE_L_SHIFTS.get(shift)
            if cmd_info:
                cmd_name = cmd_info["cmd"]
                const_val = cast(Dict[int, str], cmd_info["consts"]).get(data, f"0x{data:X}")
                dis.text(f"{cmd_name}({const_val})")
            else:
                dis.text(f"gsSPSetOtherMode(G_SETOTHERMODE_L, {shift}, {length}, 0x{data:08X})")

    def execute_set_other_mode_h(self, cmd0, cmd1, dis):
        shift = self._SHIFTR(cmd0, 8, 8)
        length = self._SHIFTR(cmd0, 0, 8)
        data = cmd1

        if dis:
            # Machine-readable record for other-mode high changes
            dis.set_cmd("gsSPSetOtherMode", {"w0": cmd0, "w1": cmd1})
            cmd_info = G_SETOTHERMODE_H_SHIFTS.get(shift)
            if cmd_info:
                cmd_name = cmd_info["cmd"]
                const_val = cast(Dict[int, str], cmd_info["consts"]).get(data, f"0x{data:X}")
                dis.text(f"{cmd_name}({const_val})")
            else:
                dis.text(f"gsSPSetOtherMode(G_SETOTHERMODE_H, {shift}, {length}, 0x{data:08X})")

    def execute_texture(self, cmd0, cmd1, dis):
        s = self._SHIFTR(cmd1, 16, 16)
        t = self._SHIFTR(cmd1, 0, 16)
        level = self._SHIFTR(cmd0, 11, 3)
        tile_val = self._SHIFTR(cmd0, 8, 3)
        on_val = self._SHIFTR(cmd0, 0, 8)

        tile = G_TX_MAP.get(tile_val, str(tile_val))
        on = G_ON_OFF_MAP.get(on_val, str(on_val))

        if dis:
            dis.set_cmd(
                "gsSPTexture",
                {"w0": cmd0, "w1": cmd1, "level": level, "tile": tile_val, "on": on_val},
            )
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

            params = [f"0x{s:04X}", f"0x{t:04X}", level, tile, on]
            dis.text(f"gsSPTexture({self.format_params(params)})")

    def execute_move_word(self, cmd0, cmd1, dis):
        index = self._SHIFTR(cmd0, 0, 8)
        offset = self._SHIFTR(cmd0, 8, 16)
        data = cmd1

        if dis:
            # Record move-word as a structured command; specific semantics are handled in branches
            dis.set_cmd("gsSPMoveWord", {"w0": cmd0, "w1": cmd1})
            index_name = G_MOVEWORD_INDICES.get(index)

            if index_name == "G_MW_NUMLIGHT":
                # Decode NUMLIGHTS packing
                if data >= 0x80000000 and offset == 0:
                    num_lights = ((data - 0x80000000) >> 5) - 1
                    dis.text(f"gsSPNumLights({num_lights})")
                    return
                elif data <= 8:
                    dis.text(f"gsSPNumLights({data})")
                    return
            elif index_name == "G_MW_CLIP":
                dis.text(self.comment_out(f"gsSPClipRatio({offset}, {data})"))
                return
            elif index_name == "G_MW_SEGMENT":
                dis.text(self.comment_out(f"gsSPSegment({offset >> 2}, 0x{data:08X})"))
                return
            elif index_name == "G_MW_FOG":
                fog_mul = (data >> 16) & 0xFFFF
                fog_off = data & 0xFFFF
                if fog_off & 0x8000:
                    fog_off -= 0x10000
                dis.text(f"gsSPFogFactor(0x{fog_mul:04X}, 0x{fog_off & 0xFFFF:04X})")
                return
            elif index_name == "G_MW_PERSPNORM":
                dis.text(self.comment_out(f"gSPPerspNormalize({data})"))
                return

            if index_name:
                dis.text(self.comment_out(f"gsSPMoveWord({index_name}, {offset}, {data})"))
            else:
                dis.text(self.comment_out(f"gsSPMoveWord({index}, {offset}, {data})"))

    def execute_pop_matrix(self, cmd0, cmd1, dis):
        self._SHIFTR(cmd1, 0, 8)
        flags = self._SHIFTR(cmd1, 0, 8)
        mode = "G_MTX_PROJECTION" if (flags & G_MTX_PROJECTION) else "G_MTX_MODELVIEW"

        if dis:
            dis.set_cmd("gsSPPopMatrix", {"w0": cmd0, "w1": cmd1})
            dis.text(self.comment_out(f"gsSPPopMatrix({mode})"))

    def execute_cull_dl(self, cmd0, cmd1, dis):
        vstart = self._SHIFTR(cmd0, 0, 16) // 40
        vend = cmd1 // 40
        if dis:
            params = [vstart, vend]
            dis.set_cmd("gsSPCullDisplayList", {"w0": cmd0, "w1": cmd1})
            dis.text(f"gsSPCullDisplayList({self.format_params(params)})")

    def execute_tri1(self, cmd0, cmd1, dis):
        v0 = self._SHIFTR(cmd1, 16, 8) // self.vertex_stride
        v1 = self._SHIFTR(cmd1, 8, 8) // self.vertex_stride
        v2 = self._SHIFTR(cmd1, 0, 8) // self.vertex_stride
        flag = self._SHIFTR(cmd1, 24, 8)

        if dis:
            params = [v0, v1, v2, flag]
            dis.set_cmd("gsSP1Triangle", {"w0": cmd0, "w1": cmd1, "indices": [v0, v1, v2]})
            dis.text(f"gsSP1Triangle({self.format_params(params)})")

    def execute_dp_set_other_mode(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd(
                "gsDPSetOtherMode",
                {
                    "w0": cmd0,
                    "w1": cmd1,
                },
            )
            dis.text(self.comment_out(f"gsDPSetOtherMode(0x{cmd0 & 0xFFFFFF:06X}, 0x{cmd1:08X})"))
