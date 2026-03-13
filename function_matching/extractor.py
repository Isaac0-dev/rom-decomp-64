import struct
import hashlib

import importlib

try:
    _mod = importlib.import_module("function_matching.mips_utils")
except ImportError:
    _mod = importlib.import_module("mips_utils")
MipsInstruction = _mod.MipsInstruction


class ExtractedFunction:
    def __init__(self, start_offset, body_bytes, features, exact_hash, masked_signature, size):
        self.start_offset = start_offset
        self.body_bytes = body_bytes
        self.features = features
        self.exact_hash = exact_hash
        self.masked_signature = masked_signature
        self.size = size


class MipsFunctionExtractor:
    def __init__(self, rom_bytes, entry_point_offset, vram_start=0x80246000, rom_start=0x1000):
        self.rom = rom_bytes
        self.entry = entry_point_offset
        self.vram_start = vram_start
        self.rom_start = rom_start
        self.MAX_FUNC_SIZE = 0x4000  # 16KB

    def _vram_to_rom(self, vram):
        # TODO: Handle multiple segments if needed, for now assume main code
        if self.vram_start <= vram < self.vram_start + 0x2000000:  # 32MB range check
            return vram - self.vram_start + self.rom_start
        return None

    def _rom_to_vram(self, rom_offset):
        return self.vram_start + (rom_offset - self.rom_start)

    # Uses methods used in CFGs
    def extract(self):
        # Set of PC offsets (ROM offsets) that have been visited
        # Using instruction-level tracking prevents infinite loops and double-processing
        visited_instruction_addresses = set()

        # Worklist of block start offsets to explore
        worklist = [self.entry]

        # Set of all valid instruction offsets found (to construct the body)
        valid_instruction_offsets = set()

        # Tracking CFG
        edges = 0
        basic_blocks = 0
        constants = set()

        # Limits
        max_offset = self.entry + self.MAX_FUNC_SIZE
        MAX_INSTRUCTIONS = 4000  # ~16KB
        instructions_processed = 0

        while worklist:
            pc = worklist.pop(0)  # BFS/DFS
            basic_blocks += 1

            # Scan linear instructions in block
            curr_pc = pc
            while True:
                # Safety bounds
                if curr_pc < 0 or curr_pc + 4 > len(self.rom) or curr_pc >= max_offset:
                    break

                if instructions_processed >= MAX_INSTRUCTIONS:
                    return None

                # Instruction-level visited check prevents infinite loops
                if curr_pc in visited_instruction_addresses:
                    break

                visited_instruction_addresses.add(curr_pc)

                # Decode instruction
                inst_int = struct.unpack(">I", self.rom[curr_pc : curr_pc + 4])[0]
                inst = MipsInstruction(inst_int)

                valid_instruction_offsets.add(curr_pc)
                instructions_processed += 1

                if inst.opcode == 0x0F:  # LUI
                    constants.add(inst.immediate << 16)

                # Control flow
                if inst.is_branch:
                    edges += 2

                    # Destination address
                    imm16 = inst.immediate
                    if imm16 >= 0x8000:
                        imm16 -= 0x10000
                    offset = imm16 << 2
                    delay_slot_pc = curr_pc + 4
                    target_pc = delay_slot_pc + offset

                    # Delay slot is always executed
                    # Add delay slot to valid
                    if delay_slot_pc < len(self.rom) and delay_slot_pc < max_offset:
                        valid_instruction_offsets.add(delay_slot_pc)
                        instructions_processed += 1

                    # Add target to worklist if valid and not already visited
                    if target_pc not in visited_instruction_addresses:
                        if 0 <= target_pc < len(self.rom) and target_pc < max_offset:
                            worklist.append(target_pc)

                    # Fallthrough (Not Taken)
                    # Fallthrough is AFTER delay slot (curr + 8)
                    fallthrough_pc = curr_pc + 8
                    if fallthrough_pc not in visited_instruction_addresses:
                        if 0 <= fallthrough_pc < len(self.rom) and fallthrough_pc < max_offset:
                            worklist.append(fallthrough_pc)

                    # End of block
                    break

                elif inst.is_j:  # Unconditional jump
                    delay_slot_pc = curr_pc + 4
                    if delay_slot_pc < len(self.rom) and delay_slot_pc < max_offset:
                        valid_instruction_offsets.add(delay_slot_pc)
                        instructions_processed += 1

                    # Calculate destination
                    curr_vram = self._rom_to_vram(delay_slot_pc)
                    target_vram = (curr_vram & 0xF0000000) | (inst.target << 2)
                    target_rom = self._vram_to_rom(target_vram)

                    if target_rom is not None:
                        dist = abs(target_rom - self.entry)
                        if dist < self.MAX_FUNC_SIZE:
                            edges += 1
                            if target_rom not in visited_instruction_addresses:
                                worklist.append(target_rom)
                    break

                elif inst.is_jr:  # Jump register (return)
                    delay_slot_pc = curr_pc + 4
                    if delay_slot_pc < len(self.rom) and delay_slot_pc < max_offset:
                        if delay_slot_pc not in visited_instruction_addresses:
                            visited_instruction_addresses.add(delay_slot_pc)
                            valid_instruction_offsets.add(delay_slot_pc)
                            instructions_processed += 1
                    # JR $ra terminates this path - no fallthrough
                    break

                elif inst.is_jal or inst.is_jalr:
                    pass

                # Advance
                curr_pc += 4

        if not valid_instruction_offsets:
            return None

        # Reachability-Based Body Construction
        # Sort offsets to maintain programmatic order
        sorted_offsets = sorted(list(valid_instruction_offsets))

        # Determine logical size (extent)
        min_off = sorted_offsets[0]
        max_off = sorted_offsets[-1]
        extent_size = (max_off - min_off) + 4

        # Build contiguous body from reachable instructions matches ONLY
        body_parts = []
        for off in sorted_offsets:
            body_parts.append(self.rom[off : off + 4])
        body_bytes = b"".join(body_parts)

        # Calculate Features
        # Build opcode histogram
        opcode_histogram: dict[int, int] = {}
        for off in sorted_offsets:
            if off + 4 <= len(self.rom):
                val = struct.unpack(">I", self.rom[off : off + 4])[0]
                op = (val >> 26) & 0x3F
                opcode_histogram[op] = opcode_histogram.get(op, 0) + 1

        features = {
            "inst_count": len(sorted_offsets),
            "block_count": basic_blocks,
            "edge_count": edges,
            "constants": sorted(list(constants)),
            "opcode_ngrams": self._extract_ngrams(valid_instruction_offsets),
            "opcode_histogram": opcode_histogram,
        }

        # Calculate Hashes on the REACHABLE BODY
        exact_hash = hashlib.sha256(body_bytes).hexdigest()

        # Calculate Relocated Signature on the REACHABLE BODY
        masked_sig = self._generate_masked_signature(body_bytes)

        return ExtractedFunction(min_off, body_bytes, features, exact_hash, masked_sig, extent_size)

    def _extract_ngrams(self, instruction_offsets):
        sorted_offsets = sorted(list(instruction_offsets))
        if not sorted_offsets:
            return []

        opcodes = []
        for off in sorted_offsets:
            # Bounds check not strictly needed if valid_instruction_offsets were validated
            if off + 4 > len(self.rom):
                continue
            val = struct.unpack(">I", self.rom[off : off + 4])[0]
            opcodes.append((val >> 26) & 0x3F)

        ngrams = []
        if len(opcodes) >= 3:
            for i in range(len(opcodes) - 2):
                gram = f"{opcodes[i]:02X}{opcodes[i + 1]:02X}{opcodes[i + 2]:02X}"
                ngrams.append(gram)

        return ngrams

    # Normalised function signature with canonical register renaming and
    # pointer/offset related instructions masked out.
    def _generate_masked_signature(self, body_bytes):
        """
        Generate a canonical masked signature for recompilation-invariant matching.

        Key features:
        1. Uses centralized masking (get_canonical_mask) for immediates/targets
        2. Canonical register renaming: assigns sequential IDs to registers
           in order of first appearance, making signature independent of
           register allocation choices.
        3. Preserves $zero(0), $sp(29), $gp(28), $ra(31) indices for semantic correctness
        4. Masks immediate offsets even when using preserved registers like $gp
        5. Preserves funct and shamt fields for R-type instructions
        """
        masked_parts = []

        # Canonical register renaming map
        # Preserved registers keep their original indices
        PRESERVED_REGS = {0, 28, 29, 31}  # $zero, $gp, $sp, $ra
        register_map = {0: 0, 28: 28, 29: 29, 31: 31}
        next_id = 1  # Start assigning from 1 (0 is reserved for $zero)

        def get_canonical_reg(reg):
            """Get the canonical ID for a register, assigning new IDs as needed."""
            nonlocal next_id
            if reg in PRESERVED_REGS:
                return reg
            if reg not in register_map:
                register_map[reg] = next_id
                next_id += 1
            return register_map[reg]

        for i in range(0, len(body_bytes), 4):
            val = struct.unpack(">I", body_bytes[i : i + 4])[0]
            inst = MipsInstruction(val)

            # Step 1: Apply centralized masking for immediates/targets
            masked_val = inst.get_canonical_mask()

            # Step 2: Apply canonical register renaming
            opcode = inst.opcode

            # Extract register fields
            rs = inst.rs
            rt = inst.rt
            rd = inst.rd

            # Get canonical register IDs
            new_rs = get_canonical_reg(rs)
            new_rt = get_canonical_reg(rt)
            new_rd = get_canonical_reg(rd)

            # Rebuild instruction with renamed registers
            # Preserve: opcode (bits 31-26), funct (bits 5-0), shamt (bits 10-6)
            # For R-type: use mask 0xFC00003F to preserve opcode + funct
            # For I-type/J-type: registers are in rs/rt positions only

            if opcode == 0x00:  # R-type
                # Preserve opcode (6 bits) + funct (6 bits) + shamt (5 bits)
                # Layout: opcode(6) | rs(5) | rt(5) | rd(5) | shamt(5) | funct(6)
                shamt = inst.shamt
                funct = inst.funct
                masked_val = (
                    (opcode << 26)
                    | (new_rs << 21)
                    | (new_rt << 16)
                    | (new_rd << 11)
                    | (shamt << 6)
                    | funct
                )
            elif opcode in [0x02, 0x03]:  # J-type (J, JAL)
                # Only opcode matters, target already masked
                # JAL writes to $ra which is preserved
                masked_val = masked_val  # Already masked, no register fields to rename
            else:  # I-type
                # Layout: opcode(6) | rs(5) | rt(5) | immediate(16)
                # immediate is already masked by get_canonical_mask
                immediate_part = masked_val & 0xFFFF
                masked_val = (opcode << 26) | (new_rs << 21) | (new_rt << 16) | immediate_part

            masked_parts.append(struct.pack(">I", masked_val))

        return b"".join(masked_parts).hex()
