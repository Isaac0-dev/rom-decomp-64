from .gbi1 import GBI1
from gbi_defines import G_DL_PUSH, G_GEOMETRYMODE_FLAGS_GBI2, get_named_flags
import vertices
import lights
from texture import set_tile_size
from utils import debug_print


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

        if dis:
            on_str = "G_ON" if on_val else "G_OFF"
            dis.set_cmd(
                "gsSPTexture",
                {"s": s, "t": t, "level": level, "tile": tile_val, "on": on_str},
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

    def execute_vertex(self, cmd0, cmd1, dis):
        count = self._SHIFTR(cmd0, 12, 8)
        v_end = (cmd0 & 0xFF) >> 1
        v0 = v_end - count
        address = cmd1

        if dis:
            vertices_name = vertices.parse_vertices(
                address, count, dis.sTxt, dis.context_prefix, self.parent_dl
            )
            if vertices_name is None:
                debug_print(f"Failed to parse vertices at address {address}")
                return
            dis.set_cmd(
                "gsSPVertex",
                {
                    "vtx_name": vertices_name,
                    "count": count,
                    "v0": v0,
                    "address": address,
                },
            )

    def execute_tri1(self, cmd0, cmd1, dis):
        v0 = self._SHIFTR(cmd0, 1, 7)
        v1 = self._SHIFTR(cmd0, 9, 7)
        v2 = self._SHIFTR(cmd0, 17, 7)

        if dis:
            dis.set_cmd("gsSP1Triangle", {"v0": v0, "v1": v1, "v2": v2, "flag": 0})

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

    def execute_matrix(self, cmd0, cmd1, dis):
        if dis:
            push = (cmd0 & 0x1) == 0
            replace = (cmd0 >> 1) & 0x1
            projection = (cmd0 >> 2) & 0x1
            t = []
            t.append("G_MTX_PROJECTION" if projection else "G_MTX_MODELVIEW")
            t.append("G_MTX_LOAD" if replace else "G_MTX_MUL")
            if push:
                t.append("G_MTX_PUSH")
            flags_str = " | ".join(t)
            dis.set_cmd("gsSPMatrix", {"flags": flags_str})

    def execute_dl(self, cmd0, cmd1, dis):
        # Same as GBI1 but different opcode
        param = self._SHIFTR(cmd0, 16, 8)
        address = cmd1

        if dis:
            dl_record = dis.parse_dl(address)
            if param == G_DL_PUSH:
                dis.set_cmd("gsSPDisplayList", {"dl": dl_record})
            else:
                dis.set_cmd("gsSPBranchList", {"dl": dl_record})
                dis.branch_taken = True

    def execute_end_dl(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsSPEndDisplayList", {"end": True})
            dis.end_dl = True

    def execute_move_mem(self, cmd0, cmd1, dis):
        type_val = cmd0 & 0xFE
        offset = self._SHIFTR(cmd0, 8, 8) << 3

        if dis:
            # GBI2 MoveMem types
            # G_GBI2_MV_VIEWPORT: 8
            # G_GBI2_MV_LIGHT:    10

            if type_val == 8:  # Viewport
                raise Exception("Viewports are unimplemented")
                # import rom_database as db

                # vp_name = db.resolve_symbol(cmd1, dis.context_prefix, "viewport")
                # dis.set_cmd("gsSPViewport", {"viewport": vp_name})
            if type_val == 10:  # Light
                length = self._SHIFTR(cmd0, 16, 8) << 1
                light_idx = (offset - 48) // 24
                if length == 40:
                    l1_record = lights.parse_light(cmd1, 24, dis.sTxt, dis.context_prefix)
                    l2_record = lights.parse_light(cmd1 + 24, 16, dis.sTxt, dis.context_prefix)
                    dis.set_cmd("gsSPSetLights1", {"light1": l1_record, "light2": l2_record})
                else:
                    light_record = lights.parse_light(cmd1, length, dis.sTxt, dis.context_prefix)
                    dis.set_cmd("gsSPLight", {"light": light_record, "idx": light_idx})
                return

            dis.set_cmd("gsSPMoveMem", {}, commented_out=True)

    def execute_move_word(self, cmd0, cmd1, dis):
        type_val = cmd0 & 0xFF
        offset = self._SHIFTR(cmd0, 8, 16)
        data = cmd1
        if dis:
            if type_val == 0x02:  # G_MW_NUMLIGHT
                num_lights = data // 24
                dis.set_cmd("gsSPNumLights", {"count": num_lights})
            elif type_val == 0x06:  # G_MW_SEGMENT
                segment = (offset >> 2) & 0xF
                dis.set_cmd("gsSPSegment", {"seg": segment, "addr": data}, commented_out=True)
            elif type_val == 0x08:  # G_MW_FOG
                multiplier = data >> 16
                fog_offset = data & 0xFFFF
                dis.set_cmd("gsSPFogPosition", {"mul": multiplier, "off": fog_offset})
            else:
                from gbi_defines import G_MOVEWORD_INDICES

                index_name = G_MOVEWORD_INDICES.get(type_val, f"0x{type_val:02X}")
                dis.set_cmd(
                    "gsSPMoveWord",
                    {"index": index_name, "offset": offset, "data": data},
                    commented_out=True,
                )

    def execute_modify_vtx(self, cmd0, cmd1, dis):
        vtx = self._SHIFTR(cmd0, 1, 15)
        offset = self._SHIFTR(cmd0, 16, 8)
        if dis:
            offset_name = {
                0x10: "G_MWO_POINT_RGBA",
                0x14: "G_MWO_POINT_ST",
                0x18: "G_MWO_POINT_XYSCREEN",
                0x1C: "G_MWO_POINT_ZSCREEN",
            }.get(offset, f"0x{offset:02X}")
            dis.set_cmd("gsSPModifyVertex", {"vtx": vtx, "offset": offset_name, "value": cmd1})

    def execute_cull_dl(self, cmd0, cmd1, dis):
        vstart = self._SHIFTR(cmd0, 1, 15)
        vend = self._SHIFTR(cmd1, 1, 15)

        if dis:
            dis.set_cmd("gsSPCullDisplayList", {"v0": vstart, "vn": vend})

    def execute_branch_z(self, cmd0, cmd1, dis):
        vtx = self._SHIFTR(cmd0, 12, 12)
        zval = cmd1
        if dis:
            dis.set_cmd("gsSPBranchLessZ", {"vtx": vtx, "zval": zval}, commented_out=True)

    def execute_quad(self, cmd0, cmd1, dis):
        v00 = self._SHIFTR(cmd1, 1, 7)
        v01 = self._SHIFTR(cmd1, 9, 7)
        v02 = self._SHIFTR(cmd1, 17, 7)
        v12 = self._SHIFTR(cmd0, 17, 7)

        if dis:
            dis.set_cmd(
                "gsSP1Quadrangle",
                {"v0": v00, "v1": v01, "v2": v02, "v3": v12, "flag": 0},
            )

    def execute_line_3d(self, cmd0, cmd1, dis):
        v0 = self._SHIFTR(cmd1, 1, 7)
        v1 = self._SHIFTR(cmd1, 9, 7)
        if dis:
            dis.set_cmd("gsSPLine3D", {"v0": v0, "v1": v1, "flag": 0}, commented_out=True)

    def execute_bg_rect_1cyc(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gSPBgRect1Cyc", {}, commented_out=True)

    def execute_bg_rect_copy(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gSPBgRectCopy", {}, commented_out=True)

    def execute_obj_render_mode(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gSPObjRenderMode", {}, commented_out=True)

    def execute_dma_io(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gSPDmaIo", {}, commented_out=True)

    def execute_pop_matrix(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsSPPopMatrix", {}, commented_out=True)

    def execute_set_geometry_mode(self, cmd0, cmd1, dis):
        import display_list

        clr = cmd0 & 0x00FFFFFF
        set_val = cmd1

        display_list.current_geometry_mode &= clr | 0xFF000000  # Keep upper byte
        display_list.current_geometry_mode |= set_val

        if dis:
            clr_flags = get_named_flags((~clr) & 0x00FFFFFF, G_GEOMETRYMODE_FLAGS_GBI2)
            set_flags = get_named_flags(set_val & 0x00FFFFFF, G_GEOMETRYMODE_FLAGS_GBI2)
            dis.set_cmd("gsSPGeometryMode", {"clr": clr_flags, "set": set_flags})

    def execute_rdp_half_1(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPHalf1", {})

    def execute_rdp_half_2(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsDPHalf2", {})

    def execute_load_ucode(self, cmd0, cmd1, dis):
        if dis:
            dis.set_cmd("gsSPLoadUcode", {}, commented_out=True)
