import struct


class MipsInstruction:
    def __init__(self, raw_int):
        self.raw = raw_int
        self.opcode = (raw_int >> 26) & 0x3F
        self.rs = (raw_int >> 21) & 0x1F
        self.rt = (raw_int >> 16) & 0x1F
        self.rd = (raw_int >> 11) & 0x1F
        self.shamt = (raw_int >> 6) & 0x1F
        self.funct = raw_int & 0x3F
        self.immediate = raw_int & 0xFFFF
        self.target = raw_int & 0x03FFFFFF

    @property
    def is_jal(self):
        return self.opcode == 0x03

    @property
    def is_j(self):
        return self.opcode == 0x02

    @property
    def is_branch(self):
        # BEQ, BNE, BLEZ, BGTZ
        if self.opcode in [0x04, 0x05, 0x06, 0x07]:
            return True
        # REGIMM (BLTZ, BGEZ, etc.)
        if self.opcode == 0x01:
            # check rt for specific branch type if needed, but opcode 0x01 implies branch/trap
            return True
        # COP1 branches (BC1F, BC1T)
        if self.opcode == 0x11 and self.rs == 0x08:
            return True
        return False

    @property
    def is_jr(self):
        return self.opcode == 0x00 and self.funct == 0x08

    @property
    def is_jalr(self):
        return self.opcode == 0x00 and self.funct == 0x09

    def get_canonical_mask(self):
        """
        Returns the instruction word with position-dependent fields zeroed out.
        This creates a canonical form for matching across recompilations.

        Masked fields:
        - Jump targets (J, JAL): lower 26 bits
        - Branch immediates (BEQ, BNE, BLEZ, BGTZ, REGIMM): lower 16 bits
        - I-type immediates (ALU, Loads, Stores, LUI): lower 16 bits
        """
        masked = self.raw

        # 1. Jump targets (J=0x02, JAL=0x03): mask lower 26 bits
        if self.opcode in [0x02, 0x03]:
            return masked & 0xFC000000

        # 2. Branch immediates: mask lower 16 bits
        # BEQ=0x04, BNE=0x05, BLEZ=0x06, BGTZ=0x07, REGIMM=0x01
        branch_opcodes = [0x04, 0x05, 0x06, 0x07, 0x01]
        if self.opcode in branch_opcodes:
            return masked & 0xFFFF0000

        # 3. COP1 branches (BC1F, BC1T): mask lower 16 bits
        if self.opcode == 0x11 and self.rs == 0x08:
            return masked & 0xFFFF0000

        # 4. I-type immediates: mask lower 16 bits
        # ALU: ADDI, ADDIU, SLTI, SLTIU, ANDI, ORI, XORI, LUI
        # Loads: LB, LH, LWL, LW, LBU, LHU, LWR
        # Stores: SB, SH, SWL, SW, SWR
        # COP loads/stores: LWC1, LDC1, SWC1, SDC1
        i_type_opcodes = [
            0x08,
            0x09,
            0x0A,
            0x0B,
            0x0C,
            0x0D,
            0x0E,
            0x0F,  # ALU imm
            0x20,
            0x21,
            0x22,
            0x23,
            0x24,
            0x25,
            0x26,
            0x27,  # Loads
            0x28,
            0x29,
            0x2A,
            0x2B,
            0x2E,  # Stores
            0x30,
            0x31,
            0x35,
            0x38,
            0x39,
            0x3D,  # COP loads/stores
        ]
        if self.opcode in i_type_opcodes:
            return masked & 0xFFFF0000

        # R-type and others: return unchanged
        return masked

    def get_masked_bytes(self):
        """Returns the canonical masked instruction as bytes (big-endian)."""
        return struct.pack(">I", self.get_canonical_mask())


def extract_features(instructions):
    block_count = 1  # Starts with 1 block
    edge_count = 1  # Flow entry

    # Simple heuristic: meaningful instructions (non-NOP)
    inst_count = len([i for i in instructions if i.raw != 0])

    # CFG heuristics
    # Any branch or jump implies a block split/edge
    for i in instructions:
        if i.is_branch:
            block_count += 2  # Branch taken + Not taken (roughly)
            edge_count += 2
        elif i.is_j or i.is_jr:
            block_count += 1
            edge_count += 1
        elif i.is_jal or i.is_jalr:
            # Function call is not a block split in standard CFG usually,
            # but creates edges in call graph. We'll count it as a "feature".
            pass

    # Constants (LUI + ADDIU/OR pair detections is complex, let's just grab LUI immediates for now)
    constants = set()
    for idx, i in enumerate(instructions):
        if i.opcode == 0x0F:  # LUI
            constants.add(i.immediate << 16)
        # Check for simple large constants or float patterns?
        # Maybe just raw immediates that aren't obviously small offsets?

    # Opcode N-Grams (3-grams)
    opcodes = [i.opcode for i in instructions]
    ngrams = []
    if len(opcodes) >= 3:
        for i in range(len(opcodes) - 2):
            gram = f"{opcodes[i]:02X}{opcodes[i + 1]:02X}{opcodes[i + 2]:02X}"
            ngrams.append(gram)

    # Opcode Histogram (order-invariant, resilient to recompilation reordering)
    opcode_histogram: dict[int, int] = {}
    for i in instructions:
        op = i.opcode
        opcode_histogram[op] = opcode_histogram.get(op, 0) + 1

    return {
        "inst_count": inst_count,
        "block_count": block_count,
        "edge_count": edge_count,
        "constants": sorted(list(constants)),
        "opcode_ngrams": ngrams,
        "opcode_histogram": opcode_histogram,
    }
