import struct
import hashlib
from typing import Any, Dict, List, Optional, Set, Tuple
from segment import (
    get_segment,
    segment_from_addr,
    offset_from_segment_addr,
    sRom,
)
from utils import debug_print
from context import ctx

parsed_trajectories: Dict[str, str] = {}
_parsed_trajectory_addresses: Set[int] = set()

trajectory_string: str = ""

VANILLA_TRAJECTORIES: List[Tuple[int, str, str, int]] = [
    # 0: segmented address
    # 1: decomp name
    # 2: coop hardcoded field name
    # 3: editor index
    (0x0702EC3C, "rr_seg7_trajectory_0702EC3C", "PlatformRrTrajectory", 4),
    (0x0702ECC0, "rr_seg7_trajectory_0702ECC0", "PlatformRr2Trajectory", 5),
    (0x0702ED9C, "rr_seg7_trajectory_0702ED9C", "PlatformRr3Trajectory", 11),
    (0x0702EEE0, "rr_seg7_trajectory_0702EEE0", "PlatformRr4Trajectory", 12),
    (0x0701669C, "ccm_seg7_trajectory_0701669C", "PlatformCcmTrajectory", 6),
    (0x070159AC, "bitfs_seg7_trajectory_070159AC", "PlatformBitfsTrajectory", 7),
    (0x0702B86C, "hmc_seg7_trajectory_0702B86C", "PlatformHmcTrajectory", 8),
    (0x0702856C, "lll_seg7_trajectory_0702856C", "PlatformLllTrajectory", 9),
    (0x07028660, "lll_seg7_trajectory_07028660", "PlatformLll2Trajectory", 10),
    (0x070165A8, "ccm_seg7_trajectory_snowman", "SnowmanHeadTrajectory", 3),
    (0x070116A0, "bob_seg7_trajectory_koopa", "KoopaBobTrajectory", 0),
    (0x07011530, "bob_seg7_metal_ball_path0", "BowlingBallBobTrajectory", 13),
    (0x070115C4, "bob_seg7_metal_ball_path1", "BowlingBallBob2Trajectory", 15),
    (0x0700E258, "thi_seg7_trajectory_koopa", "KoopaThiTrajectory", 1),
    (0x07023604, "ccm_seg7_trajectory_penguin_race", "RacingPenguinTrajectory", 2),
    (0x0700D20C, "jrb_seg7_trajectory_unagi_1", "UnagiTrajectory", -1),
    (0x0700D240, "jrb_seg7_trajectory_unagi_2", "Unagi2Trajectory", -1),
    (0x07078EF8, "inside_castle_seg7_trajectory_mips_0", "MipsTrajectory", -1),
    (0x07078F2C, "inside_castle_seg7_trajectory_mips_1", "Mips2Trajectory", -1),
    (0x07078F68, "inside_castle_seg7_trajectory_mips_2", "Mips3Trajectory", -1),
    (0x07078F7C, "inside_castle_seg7_trajectory_mips_3", "Mips4Trajectory", -1),
    (0x07078FA8, "inside_castle_seg7_trajectory_mips_4", "Mips5Trajectory", -1),
    (0x07078FD4, "inside_castle_seg7_trajectory_mips_5", "Mips6Trajectory", -1),
    (0x07078FE8, "inside_castle_seg7_trajectory_mips_6", "Mips7Trajectory", -1),
    (0x07079004, "inside_castle_seg7_trajectory_mips_7", "Mips8Trajectory", -1),
    (0x07079020, "inside_castle_seg7_trajectory_mips_8", "Mips9Trajectory", -1),
    (0x07079044, "inside_castle_seg7_trajectory_mips_9", "Mips10Trajectory", -1),
    (0x070170A0, "ttm_seg7_trajectory_070170A0", "BowlingBallTtmTrajectory", 14),
]

VANILLA_TRAJECTORY_NAMES: Dict[int, str] = {entry[0]: entry[1] for entry in VANILLA_TRAJECTORIES}
VANILLA_TRAJECTORY_TO_COOP_NAME: Dict[str, str] = {
    entry[2]: entry[1] for entry in VANILLA_TRAJECTORIES
}
VANILLA_TRAJECTORY_FROM_EDITOR_IDX: Dict[int, Tuple[int, str, str, int]] = {
    entry[3]: entry for entry in VANILLA_TRAJECTORIES
}


def parse_trajectory(
    segmented_addr: int,
    sTxt: Any,
    name: Optional[str] = None,
    raw_data: Optional[bytes] = None,
    override_name: Optional[str] = None,
) -> Optional[str]:
    global trajectory_string
    if raw_data is not None:
        data = raw_data
        pos = 0
    else:
        seg_num = segment_from_addr(segmented_addr)
        offset = offset_from_segment_addr(segmented_addr)
        segment_data = get_segment(seg_num)
        if segment_data is None:
            return f"0x{segmented_addr:08X}"
        data = segment_data
        pos = offset

    waypoint_count = 0
    MAX_WAYPOINTS = 2000

    raw_chunks = []
    points = []
    while pos + 2 <= len(data) and waypoint_count < MAX_WAYPOINTS:
        traj_id = struct.unpack(">h", data[pos : pos + 2])[0]
        if traj_id == -1:
            raw_chunks.append(b"\xff\xff")
            pos += 2
            break

        if pos + 8 > len(data):
            break

        chunk = data[pos : pos + 8]
        raw_chunks.append(chunk)
        tid, x, y, z = struct.unpack(">4h", chunk)
        points.append((tid, x, y, z))
        pos += 8
        waypoint_count += 1

    if waypoint_count == 0:
        return None

    traj_hash = hashlib.sha256(b"".join(raw_chunks)).hexdigest()

    if traj_hash in parsed_trajectories:
        return parsed_trajectories[traj_hash]

    if name is None:
        if segmented_addr in VANILLA_TRAJECTORY_NAMES:
            name = VANILLA_TRAJECTORY_NAMES[segmented_addr]
        else:
            name = f"trajectory_{segmented_addr:08X}"

    parsed_trajectories[traj_hash] = name

    is_all_zero = True
    for tid, x, y, z in points:
        if x != 0 or y != 0 or z != 0:
            is_all_zero = False
            break
    if is_all_zero:
        return None

    if len(points) >= 3:
        xs = [p[1] for p in points]
        ys = [p[2] for p in points]
        zs = [p[3] for p in points]
        if max(xs) == min(xs) and max(ys) == min(ys) and max(zs) == min(zs):
            return None

    output_lines = [f"const Trajectory {name}[] = {{"]
    for tid, x, y, z in points:
        output_lines.append(f"    TRAJECTORY_POS({tid}, {x}, {y}, {z}),")

    output_lines.append("    TRAJECTORY_END(),")
    output_lines.append("};\n")

    final_output = "\n".join(output_lines)
    sTxt.write(ctx, "trajectory", name, final_output)

    if override_name is None:
        override_name = VANILLA_TRAJECTORY_TO_COOP_NAME.get(name)
    if override_name is None:
        override_name = "KoopaBobTrajectory"
    if override_name is not None:
        trajectory_string += (
            f'gBehaviorValues.trajectories.{override_name} = get_trajectory("{name}")\n'
        )
    return name


def _trajectory_at_offset(
    data: bytes,
    offset: int,
    length: int,
    require_sequential: bool = False,
    min_all_zero_count: int = 2,
) -> bool:
    p = offset
    count = 0
    is_sequential = True
    is_all_zeros = True

    while p + 8 <= length:
        try:
            tid = struct.unpack_from(">h", data, p)[0]
        except struct.error:
            break

        if tid == -1:
            return count >= 2

        if tid != count:
            is_sequential = False
        if tid != 0:
            is_all_zeros = False

        if not is_sequential and not is_all_zeros:
            break

        p += 8
        count += 1

        if p + 2 <= length:
            try:
                next_tid = struct.unpack_from(">h", data, p)[0]
                if next_tid == -1:
                    return count >= 2
            except struct.error:
                break

        if count > 1000:
            break

    if require_sequential:
        return is_sequential and count >= 2
    return (is_sequential and count >= 2) or (is_all_zeros and count >= min_all_zero_count)


def scan_for_trajectories(sTxt: Any) -> List[int]:
    found = []

    for addr in VANILLA_TRAJECTORY_NAMES:
        seg_num = segment_from_addr(addr)
        data = get_segment(seg_num)
        if not data:
            return []
        length = len(data)

        if addr in _parsed_trajectory_addresses:
            continue
        offset = offset_from_segment_addr(addr)
        if offset + 8 > length:
            continue
        _parsed_trajectory_addresses.add(addr)
        nm = VANILLA_TRAJECTORY_NAMES[addr]
        res = parse_trajectory(addr, sTxt, nm)
        if res:
            found.append(addr)
            debug_print(f"Found vanilla trajectory: {nm} at {addr:08X}")

    return found


def scan_sm64_editor_trajectories(sTxt: Any) -> List[int]:
    if sRom is None:
        debug_print("scan_sm64_editor_trajectories: sRom not loaded")
        return []

    pos = sRom.tell()
    sRom.seek(0)
    data = sRom.read()
    sRom.seek(pos)

    rom_len = len(data)
    editor_traj_base = 0x01205000
    slot_size = 0x500
    slot_count = 18

    found: List[int] = []
    for idx in range(slot_count):
        offset = editor_traj_base + slot_size * idx
        if offset + 8 > rom_len:
            break
        if offset in _parsed_trajectory_addresses:
            continue
        if _trajectory_at_offset(data, offset, rom_len, require_sequential=True):
            _parsed_trajectory_addresses.add(offset)
            nm = f"sm64_editor_trajectory_{idx:02d}"
            traj_info = VANILLA_TRAJECTORY_FROM_EDITOR_IDX.get(idx)
            assert traj_info is not None
            nm = traj_info[1]
            override_name = traj_info[2]
            res = parse_trajectory(0, sTxt, nm, raw_data=data[offset:], override_name=override_name)
            if res:
                found.append(offset)
                debug_print(f"SM64 Editor trajectory #{idx} at 0x{offset:06X} -> {res}")
    return found


def get_trajectory_string() -> str:
    global trajectory_string
    return trajectory_string
