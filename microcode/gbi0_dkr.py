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
            dis.set_cmd("gsSPVertex", {"address": address, "v0": v0, "count": n})

        self.vertex_offset += n

    def execute_display_list_len(self, cmd0, cmd1, dis):
        limit = self._SHIFTR(cmd0, 16, 8)
        address = cmd1
        if dis:
            dl_record = dis.parse_dl(address)
            dis.set_cmd("gsSPDisplayListLen", {"dl": dl_record, "limit": limit})

    def execute_matrix(self, cmd0, cmd1, dis):
        address = self.matrix_address + cmd1
        index = self._SHIFTR(cmd0, 22, 2)
        cmd0 & 0xFFFF

        if dis:
            dis.set_cmd("gsSPMatrix", {"address": address, "index": index})

        # Update matrix index
        self.matrix_index = index

    def execute_texture(self, cmd0, cmd1, dis):
        s = self._SHIFTR(cmd1, 16, 16)
        t = self._SHIFTR(cmd1, 0, 16)
        level = self._SHIFTR(cmd0, 11, 3)
        tile_val = self._SHIFTR(cmd0, 8, 3)
        # on_val = self._SHIFTR(cmd0, 0, 8) # Ignored

        if dis:
            dis.set_cmd(
                "gsSPTexture", {"s": s, "t": t, "level": level, "tile": tile_val, "on": "G_ON"}
            )

    def execute_set_addresses(self, cmd0, cmd1, dis):
        # matrixAddress = cmd0; vertexAddress = cmd1;
        self.matrix_address = cmd0
        self.vertex_address = cmd1
        self.vertex_offset = 0
        if dis:
            dis.set_cmd("gsSPSetAddress", {})

    def execute_move_word(self, cmd0, cmd1, dis):
        type_val = cmd0 & 0xFF

        if type_val == 0x02:
            self.billboard_mode = (cmd1 & 0x1) != 0
            if dis:
                pass
        elif type_val == 0x0A:
            self.matrix_index = (cmd1 >> 6) & 0x3
            if dis:
                pass
        else:
            super().execute_move_word(cmd0, cmd1, dis)

    def execute_tri_dma(self, cmd0, cmd1, dis):
        count = self._SHIFTR(cmd0, 4, 5)
        address = cmd1
        if dis:
            dis.set_cmd("gsSPTriDMA", {"count": count, "address": address})
