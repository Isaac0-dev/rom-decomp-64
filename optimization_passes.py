from rom_database import RomDatabase, CommandIR
from typing import List


def eliminate_degenerate_triangles(commands: List[CommandIR]) -> List[CommandIR]:
    """Remove triangles where at least two indices are the same."""
    new_cmds = []
    for cmd in commands:
        if cmd.name == "gsSP1Triangle":
            params = cmd.params[0].params
            if "indices" in params:
                v0, v1, v2 = params["indices"]
            else:
                v0 = params.get("v0", 0)
                v1 = params.get("v1", 0)
                v2 = params.get("v2", 0)

            if v0 == v1 or v1 == v2 or v0 == v2:
                continue
        elif cmd.name == "gsSP2Triangles":
            params = cmd.params[0].params
            if "indices" in params:
                idx = params["indices"]
                v00, v01, v02, v10, v11, v12 = idx[0], idx[1], idx[2], idx[3], idx[4], idx[5]
            else:
                v00 = params.get("v00", 0)
                v01 = params.get("v01", 0)
                v02 = params.get("v02", 0)
                v10 = params.get("v10", 0)
                v11 = params.get("v11", 0)
                v12 = params.get("v12", 0)

            deg1 = v00 == v01 or v01 == v02 or v00 == v02
            deg2 = v10 == v11 or v11 == v12 or v10 == v12

            if deg1 and deg2:
                continue
            if deg1:
                # Convert to 1 triangle (the second one)
                if "indices" in params:
                    params["indices"] = [v10, v11, v12]
                else:
                    params["v0"] = v10
                    params["v1"] = v11
                    params["v2"] = v12
                    params.pop("v00", None)
                    params.pop("v01", None)
                    params.pop("v02", None)
                    params.pop("v10", None)
                    params.pop("v11", None)
                    params.pop("v12", None)
                    params["flag"] = params.get("flag1", 0)
                cmd.name = "gsSP1Triangle"
            elif deg2:
                # Convert to 1 triangle (the first one)
                if "indices" in params:
                    params["indices"] = [v00, v01, v02]
                else:
                    params["v0"] = v00
                    params["v1"] = v01
                    params["v2"] = v02
                    params.pop("v00", None)
                    params.pop("v01", None)
                    params.pop("v02", None)
                    params.pop("v10", None)
                    params.pop("v11", None)
                    params.pop("v12", None)
                    params["flag"] = params.get("flag0", 0)
                cmd.name = "gsSP1Triangle"
        new_cmds.append(cmd)
    return new_cmds


def batch_tri2(commands: List[CommandIR]) -> List[CommandIR]:
    """Convert pairs of consecutive gsSP1Triangle into gsSP2Triangles."""
    new_cmds = []
    i = 0
    while i < len(commands):
        cmd = commands[i]
        if cmd.name == "gsSP1Triangle" and i + 1 < len(commands):
            next_cmd = commands[i + 1]
            if next_cmd.name == "gsSP1Triangle":
                # Combine them
                p1 = cmd.params[0].params
                p2 = next_cmd.params[0].params

                if "indices" in p1:
                    v00, v01, v02 = p1["indices"]
                    flag0 = 0
                else:
                    v00 = p1.get("v0", 0)
                    v01 = p1.get("v1", 0)
                    v02 = p1.get("v2", 0)
                    flag0 = p1.get("flag", 0)

                if "indices" in p2:
                    v10, v11, v12 = p2["indices"]
                    flag1 = 0
                else:
                    v10 = p2.get("v0", 0)
                    v11 = p2.get("v1", 0)
                    v12 = p2.get("v2", 0)
                    flag1 = p2.get("flag", 0)

                from display_list import GfxCommand

                batch_gfx_cmd = GfxCommand(
                    w0=cmd.params[0].w0,
                    w1=next_cmd.params[0].w1,
                    params={
                        "v00": v00,
                        "v01": v01,
                        "v02": v02,
                        "flag0": flag0,
                        "v10": v10,
                        "v11": v11,
                        "v12": v12,
                        "flag1": flag1,
                    },
                )
                batch_ir = CommandIR(
                    opcode=0xB1,  # G_TRI2
                    params=[batch_gfx_cmd],
                    address=cmd.address,
                    name="gsSP2Triangles",
                )
                new_cmds.append(batch_ir)
                i += 2
                continue
        new_cmds.append(cmd)
        i += 1
    return new_cmds


def eliminate_redundant_rdp_state(commands: List[CommandIR]) -> List[CommandIR]:
    """Remove redundant gsDP state changes."""
    new_cmds = []
    last_combine_w0 = None
    last_combine_w1 = None
    last_env_color = None
    last_prim_color = None
    last_fog_color = None
    last_blend_color = None
    last_render_mode = None
    last_other_mode_l = None
    last_other_mode_h = None

    # We reset state tracking on jump/branch list or end dl to be safe
    reset_opcodes = {0x06, 0xB8}  # GS_DISPLAY_LIST, GS_END_DL

    for cmd in commands:
        if cmd.opcode in reset_opcodes:
            last_combine_w0 = None
            last_combine_w1 = None
            last_env_color = None
            last_prim_color = None
            last_fog_color = None
            last_blend_color = None
            last_render_mode = None
            last_other_mode_l = None
            last_other_mode_h = None
            new_cmds.append(cmd)
            continue

        w0 = cmd.params[0].w0
        w1 = cmd.params[0].w1

        if cmd.name == "gsDPSetCombineMode":
            if w0 == last_combine_w0 and w1 == last_combine_w1:
                continue
            last_combine_w0 = w0
            last_combine_w1 = w1

        elif cmd.name == "gsDPSetEnvColor":
            if w1 == last_env_color:
                continue
            last_env_color = w1

        elif cmd.name == "gsDPSetPrimColor":
            # Prim color also has w0 flags (m, l)
            w0 = w0 & 0xFFFF
            val = (w0, w1)
            if val == last_prim_color:
                continue
            last_prim_color = val

        elif cmd.name == "gsDPSetFogColor":
            if w1 == last_fog_color:
                continue
            last_fog_color = w1

        elif cmd.name == "gsDPSetBlendColor":
            if w1 == last_blend_color:
                continue
            last_blend_color = w1

        elif cmd.name == "gsDPSetRenderMode":
            if w1 == last_render_mode:
                continue
            last_render_mode = w1

        elif cmd.name == "gsDPSetOtherMode":
            # G_SETOTHERMODE_L (0xE2) or G_SETOTHERMODE_H (0xE3)
            if cmd.opcode == 0xE2:
                if w1 == last_other_mode_l:
                    continue
                last_other_mode_l = w1
            else:  # cmd.opcode == 0xE3
                if w1 == last_other_mode_h:
                    continue
                last_other_mode_h = w1

        new_cmds.append(cmd)
    return new_cmds


def insert_cull_dl(commands: List[CommandIR]) -> List[CommandIR]:
    """Insert gsSPCullDisplayList for the entire vertex range if a DL uses vertices."""
    # Simplified version: insert one cull at the start if we load vertices
    first_vtx = 999
    last_vtx = -1
    has_tris = False

    for cmd in commands:
        if cmd.name == "gsSP1Triangle":
            params = cmd.params[0].params
            if "indices" in params:
                idx = params["indices"]
            else:
                idx = [params.get("v0", 0), params.get("v1", 0), params.get("v2", 0)]
            first_vtx = min(first_vtx, *idx)
            last_vtx = max(last_vtx, *idx)
            has_tris = True
        elif cmd.name == "gsSP2Triangles":
            params = cmd.params[0].params
            if "indices" in params:
                idx = params["indices"]
            else:
                idx = [
                    params.get("v00", 0),
                    params.get("v01", 0),
                    params.get("v02", 0),
                    params.get("v10", 0),
                    params.get("v11", 0),
                    params.get("v12", 0),
                ]
            first_vtx = min(first_vtx, *idx)
            last_vtx = max(last_vtx, *idx)
            has_tris = True

    if has_tris and first_vtx <= last_vtx:
        from display_list import GfxCommand

        cull_gfx_cmd = GfxCommand(0xBE, 0, {"v0": first_vtx, "vn": last_vtx}, False)
        cull_ir = CommandIR(
            opcode=0xBE,  # G_CULLDL
            params=[cull_gfx_cmd],
            address=commands[0].address if commands else 0,
            name="gsSPCullDisplayList",
        )
        return [cull_ir] + commands

    return commands


def run_model_optimization_passes(db: RomDatabase):
    """Run all optimization passes on Display Lists in the database."""
    for dl_rec in db.display_lists.values():
        if not dl_rec.commands:
            continue

        # Order matters
        dl_rec.commands = eliminate_degenerate_triangles(dl_rec.commands)
        dl_rec.commands = eliminate_redundant_rdp_state(dl_rec.commands)
        dl_rec.commands = batch_tri2(dl_rec.commands)
        dl_rec.commands = insert_cull_dl(dl_rec.commands)
