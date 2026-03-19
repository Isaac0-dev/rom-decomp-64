from .gbi1 import GBI1
import vertices


class GBI0(GBI1):
    def __init__(self):
        super().__init__()
        self.vertex_stride = 10
        # GBI0 overrides
        self.commands.update(
            {
                0x0F: self.execute_rdp_half_cont,
                0xB0: self.execute_unknown,  # Defined as executeBranchZ for GBI1
                0xB1: self.execute_tri4,  # Defined as executeTri2 for GBI1
                0xB2: self.execute_rdp_half_cont,  # Defined as executeModifyVertex for GBI1
                0x04: self.execute_vertex,  # Override vertex
                0xBE: self.execute_cull_dl,
            }
        )

    def execute_cull_dl(self, cmd0, cmd1, dis):
        # GBI0 uses 24 bits for start index
        vstart = (cmd0 & 0x00FFFFFF) // 40
        vend = cmd1 // 40

        if dis:
            params = [vstart, vend]
            dis.set_cmd("gsSPCullDisplayList", {"w0": cmd0, "w1": cmd1})
            dis.text(f"gsSPCullDisplayList({self.format_params(params)})")

    def execute_vertex(self, cmd0, cmd1, dis):
        n = self._SHIFTR(cmd0, 20, 4) + 1
        v0 = self._SHIFTR(cmd0, 16, 4)
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

    def execute_tri4(self, cmd0, cmd1, dis):
        idx09 = self._SHIFTR(cmd0, 12, 4)
        idx06 = self._SHIFTR(cmd0, 8, 4)
        idx03 = self._SHIFTR(cmd0, 4, 4)
        idx00 = self._SHIFTR(cmd0, 0, 4)

        idx11 = self._SHIFTR(cmd1, 28, 4)
        idx10 = self._SHIFTR(cmd1, 24, 4)
        idx08 = self._SHIFTR(cmd1, 20, 4)
        idx07 = self._SHIFTR(cmd1, 16, 4)
        idx05 = self._SHIFTR(cmd1, 12, 4)
        idx04 = self._SHIFTR(cmd1, 8, 4)
        idx02 = self._SHIFTR(cmd1, 4, 4)
        idx01 = self._SHIFTR(cmd1, 0, 4)

        if dis:
            tris = []
            indices_list = []

            if idx00 != idx01:
                tris.append(f"gsSP1Triangle({idx00}, {idx01}, {idx02}, 0)")
                indices_list.append([idx00, idx01, idx02])
            if idx03 != idx04:
                tris.append(f"gsSP1Triangle({idx03}, {idx04}, {idx05}, 0)")
                indices_list.append([idx03, idx04, idx05])
            if idx06 != idx07:
                tris.append(f"gsSP1Triangle({idx06}, {idx07}, {idx08}, 0)")
                indices_list.append([idx06, idx07, idx08])
            if idx09 != idx10:
                tris.append(f"gsSP1Triangle({idx09}, {idx10}, {idx11}, 0)")
                indices_list.append([idx09, idx10, idx11])

            dis.text("\n    ".join(tris))

            # Manually add commands for vanilla_matcher
            for indices in indices_list:
                dis.commands.append(
                    {"type": "gsSP1Triangle", "indices": indices, "w0": cmd0, "w1": cmd1}
                )

    def execute_rdp_half_cont(self, cmd0, cmd1, dis):
        # ModifyVertex
        # GBI0 ModifyVertex:
        # vtx = (cmd0 >>> 16) & 0xff;
        # where = (cmd0 >>> 12) & 0xf;
        # val = cmd1;
        vtx = self._SHIFTR(cmd0, 16, 8)
        where = self._SHIFTR(cmd0, 12, 4)
        val = cmd1

        if dis:
            dis.set_cmd("gsSPModifyVertex", {"w0": cmd0, "w1": cmd1})
            dis.text(f"gsSPModifyVertex({vtx}, {where}, {val})")


class F3DEX_GBI0(GBI1):
    def __init__(self):
        super().__init__()
        self.vertex_stride = 10
        # Override vertex with GBI0 style
        self.commands[0x04] = self.execute_vertex

    def execute_vertex(self, cmd0, cmd1, dis):
        # GBI0 style vertex
        n = self._SHIFTR(cmd0, 20, 4) + 1
        v0 = self._SHIFTR(cmd0, 16, 4)
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
