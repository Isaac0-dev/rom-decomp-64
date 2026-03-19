import struct
import hashlib
from typing import Any, Dict, List, Optional
from segment import (
    get_segment,
    segment_from_addr,
    offset_from_segment_addr,
)
from utils import debug_print
from context import ctx

parsed_trajectories: Dict[str, str] = {}

# Standard vanilla trajectories and their SHA256 hashes of the raw binary data
# These hashes include the TRAJECTORY_END (-1) terminator.
VANILLA_TRAJECTORY_HASHES: Dict[str, str] = {
    "f09637cdc9db0ef0dcba179309a3b1962b5a0618abb76bf4e9a515c981026f8b": "bitfs_seg7_trajectory_070159AC",
    "13eee684e02ab98e95f5f27d34c87b2805e46310d014566b69123b256790fcba": "bitfs_seg7_trajectory_070159AC",
    "64265f47266631cd2894c75fc1b4b4fe3ff3bfbcbe5158900500b1372918a7ca": "bitfs_seg7_trajectory_070159AC",
    "567d0035c5c27199c9734ef331a7d4f4a3c216babcc9ea6d38cb19ce5a128a5d": "bob_seg7_metal_ball_path0",
    "480985db33afb63921c0e91cbf3bd5c6a583fda37e15283b7664d60e0b328de9": "bob_seg7_metal_ball_path1",
    "b13fb74989a8ee6d682e9551ee705bf249c91af759231f5ddeed3268bf8000c9": "bob_seg7_trajectory_koopa",
    "3d43f4fe4108c9e49f8691c17240d80ad15caedfd969ee7e07ed1ad822f3570c": "bob_seg7_trajectory_koopa",
    "101d2a51985854cdd953b26ed833fca2547eaa85306a3c5a5744503424c01f43": "bob_seg7_trajectory_koopa",
    "79aaaa599e8421c78d2b0d3ea476b34d74def8273bee23af8614a05f28f3f47d": "bob_seg7_trajectory_koopa",
    "f88087a06a2899d3aff9cf1eb43cb769e054f3c5bb8182259c0bbee2997bf2ba": "bob_seg7_trajectory_koopa",
    "840a0ee5412d471faf52c94356154a990a79e57b016ee3b6f11910ad2814790a": "bob_seg7_trajectory_koopa",
    "d6c6076814c40f5026c49114088fa22e293af4f8f3aee108baaac583101595ee": "ccm_seg7_trajectory_0701669C",
    "e5e8822a2d52e77dae259e47a5a52ac4da0eade9da489cbdfbfea2b1cab80572": "ccm_seg7_trajectory_0701669C",
    "f9dfe850e928a14f777ced6fb555134d54ef27d0461e1ad11b8e2a83ceb358d8": "ccm_seg7_trajectory_0701669C",
    "d4efd1a31e55a4b0145bfc0b4523c476e2e886f87780b0af5eb108cf66aa3b74": "ccm_seg7_trajectory_penguin_race",
    "1c777be9bc9acd2b52d5e5ce445a7109b6b195c81b781f18cad154d275225186": "ccm_seg7_trajectory_penguin_race",
    "fbc2d7bf9ec0117d7b50434b037d3395e04c0c8076f8ab2449a69d16acc47705": "ccm_seg7_trajectory_penguin_race",
    "4f1baad2b8f4090bd2f26c156cedf20e8cf0a2539f1443263d07b356e49c6869": "ccm_seg7_trajectory_penguin_race",
    "ce26e125cb70451b144bc6a4885a421d2e8e7e7101a6247dd6b189815a90812c": "ccm_seg7_trajectory_penguin_race",
    "8864bc0d144428ab2a19665d32c81629532dbe34328202e27159b3712f7d1d13": "ccm_seg7_trajectory_penguin_race",
    "e39cc65372fcb89a4d60b277b4239910c38ba3fe1f037ef62dcdc53cddcb0959": "ccm_seg7_trajectory_penguin_race",
    "ea17c8abaf39817d746dfbdf099bbb7f852700d929f63868038d401de7e9cd9b": "ccm_seg7_trajectory_snowman",
    "9a51b84b2898e4ada1324cc207b342ad954288dd03f28668f9764922c3019c9b": "ccm_seg7_trajectory_snowman",
    "f476560b44f764569de0880f6058cb249ea013db38177993c1be69b3ca73ffdd": "ccm_seg7_trajectory_snowman",
    "7748b24e02380d9d996606545374409a0a2ebc96e8c9219cdf8ea61f65da03c0": "hmc_seg7_trajectory_0702B86C",
    "2b07a46ab6f05ecc45fa2cb30b3e37c3dde51e065285795bff3906d1732ae9b6": "hmc_seg7_trajectory_0702B86C",
    "7878e9b2d3c9c2adae78d86c0bfc817d5a8deb08150e18d447702a70f780d36a": "inside_castle_seg7_trajectory_mips_0",
    "62ed526f5542068dadb260b6ef1a46b1d2505cf0da7a61cad9e2f3860d10babb": "inside_castle_seg7_trajectory_mips_1",
    "df85ca91e4c7dc2ccce4a1a2f947bceee6174e58ace7847b6b15ff0f1da0ea7c": "inside_castle_seg7_trajectory_mips_2",
    "fc0a9f58f3d885e5840dbe198d78d1474797f54200cb99ae3cb851639c872736": "inside_castle_seg7_trajectory_mips_3",
    "cbddb27a435304ad9ec58cad6a3a00cd520b995bc8efe23845d7c36a8d2d4785": "inside_castle_seg7_trajectory_mips_4",
    "8ad4e46e4c8b7b0b3f7071b93b2adeda9944a0ff5e4444936f1feb0c980dbfaa": "inside_castle_seg7_trajectory_mips_5",
    "6eed3f69a28f34bd1c346f31ef0dc74e66f9c8fcdcf6d4676a12ce2c6ca88666": "inside_castle_seg7_trajectory_mips_6",
    "54169af19b88a3242a4c9d18522b6ca801bc2f7a47433cbb15d3ae50a3750dea": "inside_castle_seg7_trajectory_mips_7",
    "93340276d3cce7c7ac994726ab0a2c22a3ca4297da3e0cab499083f280a0980c": "inside_castle_seg7_trajectory_mips_8",
    "5dda77a03a18cf1f738f3829ce1a5a7b638f10cc0ff59f333cca68ca77228b30": "inside_castle_seg7_trajectory_mips_9",
    "5c2d437cd8092dc681df8f7fb18da92e43d7ba31bc128f36f4b10c64cd984924": "jrb_seg7_trajectory_unagi_1",
    "e3e5b0809f2852fd048c9e0d48a44ed8b989fb521b795c583895e60512da0880": "jrb_seg7_trajectory_unagi_2",
    "ff49572e551e9779b16ea0b4947b5ef06f6d9b5ffb62bef51242cb77e1f07b45": "lll_seg7_trajectory_0702856C",
    "4155df56b5ecb0d82cf207624a3742ac2abaec8233f21c87a82a678251f55b73": "lll_seg7_trajectory_0702856C",
    "fd97e8393b5ea360a2465fd04400d325d611e8f816fe60e1fcbf94ab88d04609": "lll_seg7_trajectory_07028660",
    "2d3246102cadff377c984d5dbaa81f70dcdcfd675882c5f3845551f7dd91ec12": "lll_seg7_trajectory_07028660",
    "938c94a9d867b12b3d1f16144d41f294b9b8f54780ad37dba8ac51a1c84bf239": "rr_seg7_trajectory_0702EC3C",
    "12ef55f0d2cd0f7d0a0670e40c921c444701345c1e9f12a4113abfcc2772ed23": "rr_seg7_trajectory_0702ECC0",
    "39dbc6e6521a51c18db1abbb610306b45d3304c346a8e4a05603001945cd5f3f": "rr_seg7_trajectory_0702ED9C",
    "b8bd1bbef071280dcc16056faf02b73a79e1f7808c86c8e688dd8d8c3d52dbf2": "rr_seg7_trajectory_0702EEE0",
    "b468125c9c9df30f76990e1ee5a148a2e7e9df50afb5724c50ff6bb322cc6cad": "sTHIHugeMetalBallTraj",
    "1b2b324f97177aae17e9471100d23bef0e0e17b4dcc3250984a635c380e9d82b": "sTHITinyMetalBallTraj",
    "10eef090577830d1f91e802ef806af0915e601113e31736a6a2d5bba982ddc56": "sMantaRayTraj",
    "165a5eb27b0a864a903271c465d4f009a476c18fffd360d4e058155cb66158a4": "sCageUkikiPath",
    "41c5d95ad667d88d96605fed492d78fdbf052dce825a96c16760196a44a46aac": "thi_seg7_trajectory_koopa",
    "3464a165357db5a75ac060d88672d231e67b4bed3b3c989d672eb70a5655a308": "thi_seg7_trajectory_koopa",
    "f5424136be8e43b6cfe433b52e191b61edb2feb5f4b2778edcde0b4fbcc02704": "thi_seg7_trajectory_koopa",
    "e7eed8099587a8e9805c343bcc0944324a7b87aea7fe7e7aa69298a2db8fe8e7": "thi_seg7_trajectory_koopa",
    "291253c1b75621bfac6dd33b779ec0bf60253b8f94323cc204e676ac2607de6f": "thi_seg7_trajectory_koopa",
    "0ab7205af01edeea39817b5cf124f71bdb7bd4ed09c890e36716c7b9d261b95d": "thi_seg7_trajectory_koopa",
    "6f49e8284af20960625bd8b21782e81d79ab26db3000925ae64b4577d5dc94fd": "thi_seg7_trajectory_koopa",
    "88da239fd3b7500d303741620137940c50acf7913faae4b61731950aefd8a0a0": "ttm_seg7_trajectory_070170A0",
    "b5689e33a6c21131bd46a0825539ec862e8bfe42981f868eda64167f86e41d1d": "ttm_seg7_trajectory_070170A0",
    "0f10b4ca5db24a88c280aecea2d8d8f09cff609162879d358e4d56f1bf6c14ae": "ttm_seg7_trajectory_070170A0",
}

# Mapping of segmented addresses to names for vanilla compatibility (legacy fallback)
VANILLA_TRAJECTORY_NAMES: Dict[int, str] = {
    0x0702EC3C: "rr_seg7_trajectory_0702EC3C",
    0x0702ECC0: "rr_seg7_trajectory_0702ECC0",
    0x0702ED9C: "rr_seg7_trajectory_0702ED9C",
    0x0702EEE0: "rr_seg7_trajectory_0702EEE0",
    0x0701669C: "ccm_seg7_trajectory_0701669C",
    0x070159AC: "bitfs_seg7_trajectory_070159AC",
    0x0702B86C: "hmc_seg7_trajectory_0702B86C",
    0x0702856C: "lll_seg7_trajectory_0702856C",
    0x07028660: "lll_seg7_trajectory_07028660",
    0x070165A8: "ccm_seg7_trajectory_snowman",
    0x070116A0: "bob_seg7_trajectory_koopa",
    0x07011530: "bob_seg7_metal_ball_path0",
    0x070115C4: "bob_seg7_metal_ball_path1",
    0x0700E258: "thi_seg7_trajectory_koopa",
    0x07023604: "ccm_seg7_trajectory_penguin_race",
    0x0700D20C: "jrb_seg7_trajectory_unagi_1",
    0x0700D240: "jrb_seg7_trajectory_unagi_2",
    0x07078EF8: "inside_castle_seg7_trajectory_mips_0",
    0x07078F2C: "inside_castle_seg7_trajectory_mips_1",
    0x07078F68: "inside_castle_seg7_trajectory_mips_2",
    0x07078F7C: "inside_castle_seg7_trajectory_mips_3",
    0x07078FA8: "inside_castle_seg7_trajectory_mips_4",
    0x07078FD4: "inside_castle_seg7_trajectory_mips_5",
    0x07078FE8: "inside_castle_seg7_trajectory_mips_6",
    0x07079004: "inside_castle_seg7_trajectory_mips_7",
    0x07079020: "inside_castle_seg7_trajectory_mips_8",
    0x07079044: "inside_castle_seg7_trajectory_mips_9",
    0x070170A0: "ttm_seg7_trajectory_070170A0",
}


def parse_trajectory(segmented_addr: int, sTxt: Any, name: Optional[str] = None) -> Optional[str]:
    seg_num = segment_from_addr(segmented_addr)
    offset = offset_from_segment_addr(segmented_addr)

    segment_data = get_segment(seg_num)
    if segment_data is None:
        return f"0x{segmented_addr:08X}"

    pos = offset
    waypoint_count = 0
    MAX_WAYPOINTS = 2000

    raw_chunks = []
    points = []
    while pos + 2 <= len(segment_data) and waypoint_count < MAX_WAYPOINTS:
        traj_id = struct.unpack(">h", segment_data[pos : pos + 2])[0]
        if traj_id == -1:
            raw_chunks.append(b"\xff\xff")
            pos += 2
            break

        if pos + 8 > len(segment_data):
            break

        chunk = segment_data[pos : pos + 8]
        raw_chunks.append(chunk)
        tid, x, y, z = struct.unpack(">4h", chunk)
        points.append((tid, x, y, z))
        pos += 8
        waypoint_count += 1

    if waypoint_count == 0:
        return None

    # Hashing for identification and caching
    traj_hash = hashlib.sha256(b"".join(raw_chunks)).hexdigest()

    if traj_hash in parsed_trajectories:
        return parsed_trajectories[traj_hash]

    is_vanilla = traj_hash in VANILLA_TRAJECTORY_HASHES

    if is_vanilla:
        name = VANILLA_TRAJECTORY_HASHES[traj_hash]
    elif name is None:
        if segmented_addr in VANILLA_TRAJECTORY_NAMES:
            name = VANILLA_TRAJECTORY_NAMES[segmented_addr]
        else:
            name = f"trajectory_{segmented_addr:08X}"

    parsed_trajectories[traj_hash] = name

    # If it's vanilla, we've identified it.
    # The user requested to only output new trajectories.
    if is_vanilla:
        debug_print(f"Identified vanilla trajectory: {name}")
        return name

    # Heuristic: If all points are (0,0,0), it's probably padding
    is_all_zero = True
    for tid, x, y, z in points:
        if x != 0 or y != 0 or z != 0:
            is_all_zero = False
            break
    if is_all_zero:
        return None

    output_lines = [f"const Trajectory {name}[] = {{"]
    for tid, x, y, z in points:
        output_lines.append(f"    TRAJECTORY_POS({tid}, {x}, {y}, {z}),")

    output_lines.append("    TRAJECTORY_END(),")
    output_lines.append("};")

    final_output = "\n".join(output_lines) + "\n"
    sTxt.write(ctx, "trajectory", name, final_output)
    return name


def scan_for_trajectories(seg_num: int, sTxt: Any, prefix: Optional[str] = None) -> List[int]:
    data = get_segment(seg_num)
    if not data:
        return []

    found = []
    length = len(data)
    i = 0
    while i <= length - 8:
        i = data.find(b"\x00\x00", i)
        if i == -1 or i > length - 8:
            break

        # Ensure 2-byte alignment (shorts)
        if i % 2 != 0:
            i += 1
            continue

        # Check if it looks like a trajectory:
        # Sequential IDs or all-zeros, followed by a -1 after some points
        p = i
        count = 0
        is_valid = False
        is_sequential = True
        is_all_zeros = True

        while p + 8 <= length:
            try:
                # Use struct.unpack_from to avoid slicing overhead if data is large?
                # data[p:p+2] is small check.
                tid = struct.unpack(">h", data[p : p + 2])[0]
            except struct.error:
                break

            if tid == -1:
                if count >= 2:
                    is_valid = True
                break

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
                    next_tid = struct.unpack(">h", data[p : p + 2])[0]
                    if next_tid == -1:
                        if count >= 2:
                            is_valid = True
                        break
                except struct.error:
                    break

            if count > 1000:
                break

        if is_valid:
            addr = (seg_num << 24) | i
            if addr not in parsed_trajectories:
                name = None
                if prefix:
                    name = f"{prefix}_trajectory_{addr:08X}"

                res = parse_trajectory(addr, sTxt, name)
                if res:
                    found.append(addr)
        i += 2
    return found
