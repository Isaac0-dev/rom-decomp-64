from .gbi0 import GBI0


class GBI0DKR(GBI0):
    def __init__(self):
        super().__init__()
        self.vertex_stride = 10
        # DKR overrides
        self.commands.update(
            {
                0x05: self.execute_tri_dma,
                0x07: self.execute_display_list_len,
                0xBF: self.execute_set_addresses,
            }
        )

        self.billboard_mode = False
        self.matrix_index = 0
        self.matrix_address = 0
        self.vertex_address = 0
        self.vertex_offset = 0
        self.commands.update(
            {
                0x01: self.execute_matrix,
                0x04: self.execute_vertex,
                0xBB: self.execute_texture,  # Texture forced on
            }
        )

    def execute_vertex(self, cmd0, cmd1, dis):
        address = self.vertex_address + cmd1
        n = self._SHIFTR(cmd0, 19, 5) + 1
        flag = cmd0 & 0x00010000
        v0_base = self._SHIFTR(cmd0, 9, 5)

        if self.billboard_mode:
            self.vertex_offset = 1 if flag else 0
        elif not flag:
            self.vertex_offset = 0

        v0 = self.vertex_offset + v0_base

        if dis:
            # We cannot easily re-construct the parsing call since it depends on state (matrix index etc)
            dis.set_cmd(
                "gsSPVertex", {"w0": cmd0, "w1": cmd1, "v0": v0, "count": n, "address": address}
            )
            dis.text(f"gsSPVertex(0x{address:08X}, {v0}, {n})")

        self.vertex_offset += n

    def execute_display_list_len(self, cmd0, cmd1, dis):
        limit = self._SHIFTR(cmd0, 16, 8)
        address = cmd1
        if dis:
            dl_name = dis.parse_dl(address)
            dis.text(f"gsSPDisplayListLen({dl_name}, {limit})")

    def execute_matrix(self, cmd0, cmd1, dis):
        address = self.matrix_address + cmd1
        index = self._SHIFTR(cmd0, 22, 2)
        cmd0 & 0xFFFF

        if dis:
            dis.set_cmd("gsSPMatrix", {"w0": cmd0, "w1": cmd1})
            dis.text(f"gsSPMatrix(0x{address:08X}, {index})")

        # Update matrix index
        self.matrix_index = index

    def execute_texture(self, cmd0, cmd1, dis):
        s = self._SHIFTR(cmd1, 16, 16)
        t = self._SHIFTR(cmd1, 0, 16)
        level = self._SHIFTR(cmd0, 11, 3)
        tile_val = self._SHIFTR(cmd0, 8, 3)
        # on_val = self._SHIFTR(cmd0, 0, 8) # Ignored

        str(tile_val)  # Simple str for now

        if dis:
            dis.set_cmd(
                "gsSPTexture", {"w0": cmd0, "w1": cmd1, "level": level, "tile": tile_val, "on": 1}
            )

            # Use GBI1 style text but forced G_ON
            params = [f"0x{s:04X}", f"0x{t:04X}", level, tile_val, "G_ON"]
            dis.text(f"gsSPTexture({self.format_params(params)})")

    def execute_set_addresses(self, cmd0, cmd1, dis):
        # matrixAddress = cmd0; vertexAddress = cmd1;
        self.matrix_address = cmd0
        self.vertex_address = cmd1
        self.vertex_offset = 0
        if dis:
            dis.text(f"gsSPSetAddress(0x{cmd0:08X}, 0x{cmd1:08X})")

    def execute_move_word(self, cmd0, cmd1, dis):
        type_val = cmd0 & 0xFF

        if type_val == 0x02:
            self.billboard_mode = (cmd1 & 0x1) != 0
            if dis:
                dis.text(f"gSetBillboardMode({self.billboard_mode})")
        elif type_val == 0x0A:
            self.matrix_index = (cmd1 >> 6) & 0x3
            if dis:
                dis.text(f"gSetMatrixIndex({self.matrix_index})")
        else:
            super().execute_move_word(cmd0, cmd1, dis)

    def execute_tri_dma(self, cmd0, cmd1, dis):
        count = self._SHIFTR(cmd0, 4, 5)
        address = cmd1
        if dis:
            dis.text(f"gsSPTriDMA(0x{address:08X}, {count})")
