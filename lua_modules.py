from typing import Set
from context import ctx, LevelAreaContext
from utils import level_num_to_const_name

_2d_areas: Set[LevelAreaContext] = set()


def register_2d_area(
    level_area: LevelAreaContext,
    min_x: int,
    max_x: int,
    min_y: int,
    max_y: int,
    min_z: int,
    max_z: int,
    is_z_axis: bool,
):
    _2d_areas.add(
        (
            level_area.curr_level,
            level_area.curr_area,
            min_x,
            max_x,
            min_y,
            max_y,
            min_z,
            max_z,
            is_z_axis,
        )
    )


def apply_lua_modules():
    content = []
    applied_any_module = False

    if len(_2d_areas) > 0:
        applied_any_module = True
        content.append("local sLevelInformation = {\n")
        for level, area, min_x, max_x, min_y, max_y, min_z, max_z, is_z_axis in _2d_areas:
            level_const = level_num_to_const_name.get(level, "LEVEL_NONE")
            content.append(
                f"    [{level_const}] = " + "{ { "
                f"{level_const}, "
                f"{area}, "
                f"{min_x}, {max_x}, "
                f"{min_y}, {max_y}, "
                f"{min_z}, {max_z}" + " }, "
                f"{'true' if is_z_axis else 'false'}, 0 "
                "},\n"
            )
        content.append("}\n\n")
        content.append("-- Disable OMM camera for 2D areas\n")
        content.append("if OmmApi then\n")
        content.append(
            f'    OmmApi.omm_register_game("{ctx.db.meta.internal_name}", function () return true end, function ()\n'
        )
        content.append(
            """        OmmApi.omm_register_game_data(-1, 2, LEVEL_PSS, true, false, 0, 250, nil)
        for _, levelData in pairs(sLevelInformation) do
            OmmApi.omm_register_camera_no_collision_box(table.unpack(levelData[1]))
        end
"""
        )
        content.append("    end)\n")
        content.append("end\n")

        content.append("""
-- Keep player on 2D axis
hook_event(HOOK_MARIO_UPDATE, function (m)
    if m.playerIndex ~= 0 then return end
    local np = gNetworkPlayers[m.playerIndex]
    local levelData = sLevelInformation[np.currLevelNum]
    if levelData and levelData[1][2] == np.currAreaIndex then
        if levelData[1] then
            m.pos.z = levelData[2]
        else
            m.pos.x = levelData[2]
        end
    end
end)
""")

    if applied_any_module:
        ctx.txt.write_lua(content, "lua_modules.lua")
