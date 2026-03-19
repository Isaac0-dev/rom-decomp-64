from .gbi1 import GBI1
from gbi_defines import G_DL_PUSH, G_GEOMETRYMODE_FLAGS, get_named_flags
import vertices
import lights
from texture import set_tile_size


class GBI2(GBI1):
    def __init__(self):
        super().__init__()
        self.vertex_stride = 2
        # GBI2 overrides
        self.commands.update(
            {
                0x00: self.execute_noop,
                0x01: self.execute_vertex,
                0x02: self.execute_modify_vtx,
                0x03: self.execute_cull_dl,
                0x04: self.execute_branch_z,
                0x05: self.execute_tri1,
                0x06: self.execute_tri2,
                0x07: self.execute_quad,
                0x08: self.execute_line_3d,
                0x09: self.execute_bg_rect_1cyc,
                0x0A: self.execute_bg_rect_copy,
                0x0B: self.execute_obj_render_mode,
                0x0C: self.execute_modify_vtx,
                0xD6: self.execute_dma_io,
                0xD7: self.execute_texture,  # GBI2 texture
                0xD8: self.execute_pop_matrix,
                0xD9: self.execute_set_geometry_mode,  # GBI2 geometry mode (different from GBI1 0xB7)
                0xDA: self.execute_matrix,
                0xDB: self.execute_move_word,
                0xDC: self.execute_move_mem,
                0xDD: self.execute_load_ucode,
                0xDE: self.execute_dl,  # GBI2 uses 0xDE for DL, GBI1 uses 0x06
                0xDF: self.execute_end_dl,  # GBI2 uses 0xDF, GBI1 uses 0xB8
                0xE0: self.execute_sp_noop,
                0xE1: self.execute_rdp_half_1,
                0xE2: self.execute_set_other_mode_l,  # GBI2 (different from GBI1 0xB9)
                0xE3: self.execute_set_other_mode_h,  # GBI2 (different from GBI1 0xBA)
                0xF1: self.execute_rdp_half_2,
            }
        )

    def execute_texture(self, cmd0, cmd1, dis):
        s = self._SHIFTR(cmd1, 16, 16)
        t = self._SHIFTR(cmd1, 0, 16)
        level = self._SHIFTR(cmd0, 11, 3)
        tile_val = self._SHIFTR(cmd0, 8, 3)
        on_val = self._SHIFTR(cmd0, 1, 1)  # GBI2 uses bit 1 for ON

        str(tile_val)

        if dis:
            dis.set_cmd(
                "gsSPTexture",
                {"w0": cmd0, "w1": cmd1, "level": level, "tile": tile_val, "on": on_val},
            )
            import display_list

            G_TEXTURE_GEN_GBI2 = 0x00040000
            if (display_list.current_geometry_mode & G_TEXTURE_GEN_GBI2) == G_TEXTURE_GEN_GBI2:
                # Extract width/height from texture scale
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

            on_str = "G_ON" if on_val else "G_OFF"
            params = [f"0x{s:04X}", f"0x{t:04X}", level, tile_val, on_str]
            dis.text(f"gsSPTexture({self.format_params(params)})")

    def execute_vertex(self, cmd0, cmd1, dis):
        count = self._SHIFTR(cmd0, 12, 8)
        v_end = (cmd0 & 0xFF) >> 1
        v0 = v_end - count
        address = cmd1

        if dis:
            vertices_name = vertices.parse_vertices(
                address, count, dis.sTxt, dis.context_prefix, self.parent_dl
            )
            dis.set_cmd(
                "gsSPVertex",
                {
                    "w0": cmd0,
                    "w1": cmd1,
                    "v0": v0,
                    "count": count,
                    "vtx_name": vertices_name,
                    "address": address,
                },
            )
            params = [
                f"/* vertices */ {vertices_name}",
                f"/* count */ {count}",
                f"/* v0 */ {v0}",
            ]
            dis.text(f"gsSPVertex({self.format_params(params)})")

    def execute_tri1(self, cmd0, cmd1, dis):
        v0 = self._SHIFTR(cmd0, 1, 7)
        v1 = self._SHIFTR(cmd0, 9, 7)
        v2 = self._SHIFTR(cmd0, 17, 7)
        flag = self._SHIFTR(cmd1, 24, 8)

        if dis:
            dis.set_cmd("gsSP1Triangle", {"w0": cmd0, "w1": cmd1, "indices": [v0, v1, v2]})
            params = [v0, v1, v2, flag]
            dis.text(f"gsSP1Triangle({self.format_params(params)})")

    def execute_tri2(self, cmd0, cmd1, dis):
        v00 = self._SHIFTR(cmd1, 1, 7)
        v01 = self._SHIFTR(cmd1, 9, 7)
        v02 = self._SHIFTR(cmd1, 17, 7)
        v10 = self._SHIFTR(cmd0, 1, 7)
        v11 = self._SHIFTR(cmd0, 9, 7)
        v12 = self._SHIFTR(cmd0, 17, 7)

        if dis:
            dis.set_cmd(
                "gsSP2Triangles",
                {"w0": cmd0, "w1": cmd1, "indices": [v00, v01, v02, v10, v11, v12]},
            )
            params = [v00, v01, v02, 0, v10, v11, v12, 0]
            dis.text(f"gsSP2Triangles({self.format_params(params)})")

    def execute_matrix(self, cmd0, cmd1, dis):
        push = (cmd0 & 0x1) == 0
        replace = (cmd0 >> 1) & 0x1
        projection = (cmd0 >> 2) & 0x1
        address = cmd1

        if dis:
            dis.set_cmd("gsSPMatrix", {"w0": cmd0, "w1": cmd1})
            t = []
            if projection:
                t.append("G_MTX_PROJECTION")
            else:
                t.append("G_MTX_MODELVIEW")

            if replace:
                t.append("G_MTX_LOAD")
            else:
                t.append("G_MTX_MUL")

            if push:
                t.append("G_MTX_PUSH")
            # else: t.append("G_MTX_NOPUSH")

            params = [f"0x{address:08X}", " | ".join(t)]
            dis.text(f"// gsSPMatrix({self.format_params(params)})")

    def execute_dl(self, cmd0, cmd1, dis):
        # Same as GBI1 but different opcode
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
                dis.branch_taken = True

    def execute_end_dl(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsSPEndDisplayList", {"w0": cmd0, "w1": cmd1, "end": True})
            dis.text("gsSPEndDisplayList()")
            dis.end_dl = True

    def execute_move_mem(self, cmd0, cmd1, dis):
        length = self._SHIFTR(cmd0, 16, 8) << 1
        offset = self._SHIFTR(cmd0, 8, 8) << 3
        type_val = cmd0 & 0xFE
        address = cmd1

        if dis:
            # GBI2 MoveMem types
            # G_GBI2_MV_VIEWPORT: 8
            # G_GBI2_MV_LIGHT:    10

            if type_val == 8:  # Viewport
                dis.set_cmd("gsSPViewport", {"w0": cmd0, "w1": cmd1})
                dis.text(self.comment_out(f"gsSPViewport(0x{address:08X})"))
            elif type_val == 10:  # Light
                # offset determines which light part
                # G_GBI2_MVO_L0: 2 * 24 = 48
                # stride is 24
                if offset >= 48:
                    light_idx = (offset - 48) // 24

                    if length == 40:
                        l1_name = lights.parse_light(cmd1, 24, dis.sTxt, dis.context_prefix)
                        l2_name = lights.parse_light(cmd1 + 24, 16, dis.sTxt, dis.context_prefix)

                        dis.set_cmd("gsSPSetLights1", {"w0": cmd0, "w1": cmd1})
                        dis.text(f"gsSPSetLights1({l1_name})")
                        dis.text(f"gsSPLight(&{l2_name}, {light_idx + 2})")
                        dis.text("gsSPNumLights(NUMLIGHTS_2)")
                    else:
                        light_name = lights.parse_light(cmd1, length, dis.sTxt, dis.context_prefix)
                        dis.set_cmd("gsSPLight", {"w0": cmd0, "w1": cmd1})
                        dis.text(f"gsSPLight(&{light_name}, {light_idx})")
                else:
                    dis.text(
                        f"// gsDma1p(G_MOVEMEM, 0x{address:08X}, {length}, {offset}, {type_val})"
                    )
            else:
                dis.text(f"// gsDma1p(G_MOVEMEM, 0x{address:08X}, {length}, {offset}, {type_val})")

    def execute_move_word(self, cmd0, cmd1, dis):
        type_val = self._SHIFTR(cmd0, 16, 8)
        offset = self._SHIFTR(cmd0, 0, 16)
        data = cmd1

        if dis:
            if type_val == 0x02:  # G_MW_NUMLIGHT
                num_lights = data // 24
                dis.set_cmd("gsSPNumLights", {"w0": cmd0, "w1": cmd1})
                dis.text(f"gsSPNumLights({num_lights})")
            elif type_val == 0x06:  # G_MW_SEGMENT
                segment = (offset >> 2) & 0xF
                dis.set_cmd("gsSPSegment", {"w0": cmd0, "w1": cmd1})
                dis.text(self.comment_out(f"gsSPSegment({segment}, 0x{data:08X})"))
            elif type_val == 0x08:  # G_MW_FOG
                multiplier = data >> 16
                fog_offset = data & 0xFFFF
                dis.set_cmd("gsSPFogPosition", {"w0": cmd0, "w1": cmd1})
                dis.text(f"gsSPFogPosition({multiplier}, {fog_offset})")
            else:
                dis.set_cmd("gsSPMoveWord", {"w0": cmd0, "w1": cmd1})
                dis.text(self.comment_out(f"gsSPMoveWord({type_val}, {offset}, {data})"))

    def execute_modify_vtx(self, cmd0, cmd1, dis):
        vtx = self._SHIFTR(cmd0, 1, 15)
        offset = self._SHIFTR(cmd0, 16, 8)
        value = cmd1

        if dis:
            offset_name = {
                0x10: "G_MWO_POINT_RGBA",
                0x14: "G_MWO_POINT_ST",
                0x18: "G_MWO_POINT_XYSCREEN",
                0x1C: "G_MWO_POINT_ZSCREEN",
            }.get(offset, f"0x{offset:02X}")
            dis.set_cmd("gsSPModifyVertex", {"w0": cmd0, "w1": cmd1})
            dis.text(f"gsSPModifyVertex({vtx}, {offset_name}, 0x{value:08X})")

    def execute_cull_dl(self, cmd0, cmd1, dis):
        vstart = self._SHIFTR(cmd0, 1, 15)
        vend = self._SHIFTR(cmd1, 1, 15)

        if dis:
            dis.set_cmd("gsSPCullDisplayList", {"w0": cmd0, "w1": cmd1})
            dis.text(f"gsSPCullDisplayList({vstart}, {vend})")

    def execute_branch_z(self, cmd0, cmd1, dis):
        vtx = self._SHIFTR(cmd0, 12, 12)
        zval = cmd1

        if dis:
            dis.set_cmd("gsSPBranchLessZ", {"w0": cmd0, "w1": cmd1})
            dis.text(f"// gsSPBranchLessZ({vtx}, 0x{zval:08X})")

    def execute_quad(self, cmd0, cmd1, dis):
        v00 = self._SHIFTR(cmd1, 1, 7)
        v01 = self._SHIFTR(cmd1, 9, 7)
        v02 = self._SHIFTR(cmd1, 17, 7)
        v10 = self._SHIFTR(cmd0, 1, 7)
        v11 = self._SHIFTR(cmd0, 9, 7)
        v12 = self._SHIFTR(cmd0, 17, 7)

        if dis:
            dis.set_cmd(
                "gsSP1Quadrangle",
                {"w0": cmd0, "w1": cmd1, "indices": [v00, v01, v02, v10, v11, v12]},
            )
            dis.text(f"gsSP1Quadrangle({v00}, {v01}, {v02}, {v12}, 0)")

    def execute_line_3d(self, cmd0, cmd1, dis):
        # Not implemented in many emulators
        v0 = self._SHIFTR(cmd1, 1, 7)
        v1 = self._SHIFTR(cmd1, 9, 7)

        if dis:
            dis.set_cmd("gsSPLine3D", {"w0": cmd0, "w1": cmd1})
            dis.text(f"// gsSPLine3D({v0}, {v1}, ...)")

    def execute_bg_rect_1cyc(self, cmd0, cmd1, dis):
        address = cmd1

        if dis:
            dis.set_cmd("gSPBgRect1Cyc", {"w0": cmd0, "w1": cmd1})
            dis.text(f"// gSPBgRect1Cyc(0x{address:08X})")

    def execute_bg_rect_copy(self, cmd0, cmd1, dis):
        address = cmd1

        if dis:
            dis.set_cmd("gSPBgRectCopy", {"w0": cmd0, "w1": cmd1})
            dis.text(f"// gSPBgRectCopy(0x{address:08X})")

    def execute_obj_render_mode(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gSPObjRenderMode", {"w0": cmd0, "w1": cmd1})
            dis.text(f"// gSPObjRenderMode(0x{cmd1:08X})")

    def execute_dma_io(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gSPDmaIo", {"w0": cmd0, "w1": cmd1})
            dis.text(f"// gSPDmaIo(0x{cmd0:08X}, 0x{cmd1:08X})")

    def execute_pop_matrix(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsSPPopMatrix", {"w0": cmd0, "w1": cmd1})
            dis.text("// gsSPPopMatrix(G_MTX_MODELVIEW)")

    def execute_set_geometry_mode(self, cmd0, cmd1, dis):
        import display_list

        clr = cmd0 & 0x00FFFFFF
        set_val = cmd1

        display_list.current_geometry_mode &= clr | 0xFF000000  # Keep upper byte
        display_list.current_geometry_mode |= set_val

        if dis:
            clr_flags = get_named_flags((~clr) & 0x00FFFFFF, G_GEOMETRYMODE_FLAGS)
            set_flags = get_named_flags(set_val & 0x00FFFFFF, G_GEOMETRYMODE_FLAGS)
            dis.set_cmd("gsSPGeometryMode", {"w0": cmd0, "w1": cmd1})
            dis.text(f"gsSPGeometryMode(~({clr_flags}), {set_flags})")

    def execute_rdp_half_1(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPHalf1", {"w0": cmd0, "w1": cmd1})
            dis.text(f"gsDPHalf1(0x{cmd1:08X})")

    def execute_rdp_half_2(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPHalf2", {"w0": cmd0, "w1": cmd1})
            dis.text(f"gsDPHalf2(0x{cmd1:08X})")

    def execute_load_ucode(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsSPLoadUcode", {"w0": cmd0, "w1": cmd1})
            dis.text(f"// gsSPLoadUcode(0x{cmd1:08X})")

    def execute_noop(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPNoOp", {"w0": cmd0, "w1": cmd1})
            dis.text("gsDPNoOp()")

    def execute_sp_noop(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsSPNoOp", {"w0": cmd0, "w1": cmd1})
            dis.text("gsSPNoOp()")
