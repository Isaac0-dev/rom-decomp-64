from rom_database import RomDatabase, CommandIR
from typing import List, Dict, Any, Optional

def eliminate_degenerate_triangles(commands: List[CommandIR]) -> List[CommandIR]:
    """Remove triangles where at least two indices are the same."""
    new_cmds = []
    for cmd in commands:
        if cmd.name == "gsSP1Triangle":
            params = cmd.params[0]
            indices = params.get("indices", [0, 0, 0])
            if indices[0] == indices[1] or indices[1] == indices[2] or indices[0] == indices[2]:
                continue
        elif cmd.name == "gsSP2Triangles":
            params = cmd.params[0]
            indices = params.get("indices", [0, 0, 0, 0, 0, 0])
            deg1 = indices[0] == indices[1] or indices[1] == indices[2] or indices[0] == indices[2]
            deg2 = indices[3] == indices[4] or indices[4] == indices[5] or indices[3] == indices[5]
            if deg1 and deg2:
                continue
            if deg1:
                # Convert to 1 triangle (the second one)
                params["indices"] = indices[3:6]
                cmd.name = "gsSP1Triangle"
            elif deg2:
                # Convert to 1 triangle (the first one)
                params["indices"] = indices[0:3]
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
            next_cmd = commands[i+1]
            if next_cmd.name == "gsSP1Triangle":
                # Combine them
                indices1 = cmd.params[0].get("indices", [0, 0, 0])
                indices2 = next_cmd.params[0].get("indices", [0, 0, 0])
                batch_ir = CommandIR(
                    opcode=0xB1, # G_TRI2
                    params=[{
                        "indices": indices1 + indices2,
                        "w0": cmd.params[0].get("w0", 0), # Not perfect but G_TRI2 uses both
                        "w1": next_cmd.params[0].get("w1", 0)
                    }],
                    address=cmd.address,
                    name="gsSP2Triangles"
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
    reset_opcodes = {0x06, 0xB8} # GS_DISPLAY_LIST, GS_END_DL

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

        if cmd.name == "gsDPSetCombineMode":
            w0 = cmd.params[0].get("w0")
            w1 = cmd.params[0].get("w1")
            if w0 == last_combine_w0 and w1 == last_combine_w1:
                continue
            last_combine_w0 = w0
            last_combine_w1 = w1

        elif cmd.name == "gsDPSetEnvColor":
            val = cmd.params[0].get("w1")
            if val == last_env_color:
                continue
            last_env_color = val

        elif cmd.name == "gsDPSetPrimColor":
            # Prim color also has w0 flags (m, l)
            w0 = cmd.params[0].get("w0") & 0xFFFF
            w1 = cmd.params[0].get("w1")
            val = (w0, w1)
            if val == last_prim_color:
                continue
            last_prim_color = val

        elif cmd.name == "gsDPSetFogColor":
            val = cmd.params[0].get("w1")
            if val == last_fog_color:
                continue
            last_fog_color = val

        elif cmd.name == "gsDPSetBlendColor":
            val = cmd.params[0].get("w1")
            if val == last_blend_color:
                continue
            last_blend_color = val

        elif cmd.name == "gsDPSetRenderMode":
            w1 = cmd.params[0].get("w1")
            if w1 == last_render_mode:
                continue
            last_render_mode = w1

        elif cmd.name == "gsDPSetOtherMode":
            mode = cmd.params[0].get("mode") # Usually a bitmask
            w1 = cmd.params[0].get("w1")
            # G_SETOTHERMODE_L (0xE2) or G_SETOTHERMODE_H (0xE3)
            if cmd.opcode == 0xE2:
                if w1 == last_other_mode_l: continue
                last_other_mode_l = w1
            else: # cmd.opcode == 0xE3
                if w1 == last_other_mode_h: continue
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
            idx = cmd.params[0].get("indices", [0, 0, 0])
            first_vtx = min(first_vtx, *idx)
            last_vtx = max(last_vtx, *idx)
            has_tris = True
        elif cmd.name == "gsSP2Triangles":
            idx = cmd.params[0].get("indices", [0, 0, 0, 0, 0, 0])
            first_vtx = min(first_vtx, *idx)
            last_vtx = max(last_vtx, *idx)
            has_tris = True

    if has_tris and first_vtx <= last_vtx:
        cull_ir = CommandIR(
            opcode=0xBE, # G_CULLDL
            params=[{"v0": first_vtx, "vn": last_vtx}],
            address=commands[0].address if commands else 0,
            name="gsSPCullDisplayList"
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
