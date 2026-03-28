# MOP behaviors 🧹

from dataclasses import dataclass
from typing import Dict


@dataclass
class MOPBehavior:
    name: str
    lua_code: str
    behavior_code: str
    model_folders: list[str] | None = None


MOP_BEHAVIORS: Dict[str, MOPBehavior] = {}


def register_mop_behavior(
    name: str, lua_code: str, behavior_code: str, model_folders: list[str] | None = None
):
    bhv = MOPBehavior(name, lua_code, behavior_code, model_folders or [])
    MOP_BEHAVIORS[name] = bhv
    return bhv


# --- Shared MOP Logic ---
# This code is included once in the generated Lua file if any MOP behaviors are used.
MOP_SHARED_LUA = """
---@diagnostic disable: param-type-mismatch, assign-type-mismatch

-----------------------------
-----Localized Functions-----
-----------------------------

-- Improves performance, which is needed since this is a lot of code to run
local play_sound = play_sound
local spawn_non_sync_object = spawn_non_sync_object
local obj_copy_pos_and_angle = obj_copy_pos_and_angle
local obj_set_model_extended = obj_set_model_extended
local network_init_object = network_init_object
local network_send_object = network_send_object
local obj_check_if_collided_with_object = obj_check_if_collided_with_object
local set_mario_action = set_mario_action
local cur_obj_was_attacked_or_ground_pounded = cur_obj_was_attacked_or_ground_pounded
local load_object_collision_model = load_object_collision_model
local cur_obj_is_mario_on_platform = cur_obj_is_mario_on_platform
local spawn_mist_particles = spawn_mist_particles
local cur_obj_play_sound_1 = cur_obj_play_sound_1
local cur_obj_hide = cur_obj_hide
local cur_obj_unhide = cur_obj_unhide
local coss = coss
local sins = sins
local obj_copy_pos = obj_copy_pos
local cur_obj_rotate_face_angle_using_vel = cur_obj_rotate_face_angle_using_vel
local cur_obj_move_using_vel = cur_obj_move_using_vel
local nearest_player_to_object = nearest_player_to_object
local spawn_red_coin_cutscene_star = spawn_red_coin_cutscene_star
local cur_obj_play_sound_2 = cur_obj_play_sound_2
local cur_obj_init_animation = cur_obj_init_animation
local obj_return_home_if_safe = obj_return_home_if_safe
local obj_turn_toward_object = obj_turn_toward_object
local is_point_within_radius_of_mario = is_point_within_radius_of_mario
local object_step = object_step
local obj_scale = obj_scale
local cur_obj_scale = cur_obj_scale
local cur_obj_update_floor_and_walls = cur_obj_update_floor_and_walls
local cur_obj_if_hit_wall_bounce_away = cur_obj_if_hit_wall_bounce_away
local cur_obj_move_standard = cur_obj_move_standard
local cur_obj_update_floor_height_and_get_floor = cur_obj_update_floor_height_and_get_floor
local count_objects_with_behavior = count_objects_with_behavior
local cur_obj_become_tangible = cur_obj_become_tangible
local obj_get_first_with_behavior_id = obj_get_first_with_behavior_id
local obj_get_next_with_same_behavior_id = obj_get_next_with_same_behavior_id
local cur_obj_scale_over_time = cur_obj_scale_over_time
local cur_obj_shake_screen = cur_obj_shake_screen
local lateral_dist_between_objects = lateral_dist_between_objects
local dist_between_objects = dist_between_objects
local obj_mark_for_deletion = obj_mark_for_deletion
local mario_stop_riding_object = mario_stop_riding_object
local obj_get_next_with_behavior_id = obj_get_next_with_behavior_id

-- Packing and unpacking like this allows for C-like type conversions
local string_pack = string.pack
local string_unpack = string.unpack
---@param value number
---@param pack_fmt string
---@param unpack_fmt string
local repack = function (value, pack_fmt, unpack_fmt)
    return string_unpack(unpack_fmt, string_pack(pack_fmt, value))
end

--------------------------
-----Helper Variables-----
--------------------------

local id_bhvFlipswap_Platform_Border_MOP = id_bhvUnused05A8
local id_bhvShrink_Platform_Border_MOP = id_bhvUnused05A8
local id_bhvGreen_Switchboard_Gears_MOP = id_bhvUnused05A8

local PURPLE_SWITCH_IDLE = 0
local PURPLE_SWITCH_PRESSED = 1
local PURPLE_SWITCH_TICKING = 2
local PURPLE_SWITCH_UNPRESSED = 3
local PURPLE_SWITCH_WAIT_FOR_MARIO_TO_GET_OFF = 4

local ANM_swim = 0
local ANM_attack = 1

local BLARGG_ACT_SWIM = 0
local BLARGG_ACT_CHASE = 1
local BLARGG_ACT_KNOCKBACK = 2
local BLARGG_ACT_BACKUP = 3

local FRIENDLY_BLARGG_ACT_IDLE = 0
local FRIENDLY_BLARGG_ACT_BEING_RIDDEN = 1

--------------------------
-----Helper Functions-----
--------------------------

-- ##### Switch statements are only faster when there's several different states
-- ##### This is because each lookup of the switch statement creates an entirely new function
-- ##### However the performance overhead isn't significant at all so use it whenever you feel like it
---@param param any
---@param case_table table<any, function>
---@return function?
local function switch(param, case_table)
    local case = case_table[param]
    if case then return case() end
    local def = case_table['default']
    return def and def() or nil
end

--- Moves Mario to the top of the object, then sets his Y speed and resets his fall.
---@param m MarioState
---@param obj Object
---@param new_velY integer
local function bounce_off_object(m, obj, new_velY)
    m.pos.y = obj.oPosY + obj.hitboxHeight
    m.vel.y = new_velY

    -- MARIO_UNKNOWN_8 is the flag that controls Mario's screaming when he falls from a high place
    -- This removes the flag so he can scream again
    m.flags = m.flags & ~MARIO_UNKNOWN_08

    play_sound(SOUND_ACTION_BOUNCE_OFF_OBJECT, m.marioObj.header.gfx.cameraToObject)
end

--- Gets closer to a goal value by the increment when ran
---@param goal integer
---@param src integer
---@param inc integer
local function approach_by_increment(goal, src, inc)
    local diff = goal - src
    if diff > inc then
        return src + inc
    elseif diff < -inc then
        return src - inc
    else
        return goal
    end
end

---@param m MarioState
---@return boolean
local function is_bubbled(m)
    return m.action == ACT_BUBBLED
end

---@param parent Object
---@param model ModelExtendedId
---@param behaviorId BehaviorId
local function spawn_object(parent, model, behaviorId)
    local obj = spawn_non_sync_object(behaviorId, model, 0, 0, 0, nil)
    if not obj then return nil end

    obj_copy_pos_and_angle(obj, parent)
    return obj
end

---@return boolean
local function is_current_area_sync_valid()
    local np = gNetworkPlayers
    for i = 1, MAX_PLAYERS - 1, 1 do
        if np[i] and np[i].connected and
        (not np[i].currLevelSyncValid or not np[i].currAreaSyncValid) and
        is_player_in_local_area(gMarioStates[i]) ~= 0 then
            return false
        end
    end
    return true
end

---@param start_point number
---@param end_point number
---@param time number
---@return number
local function lerp(start_point, end_point, time)
    return start_point * (1 - time) + end_point * time
end

--- @param obj Object
--- @param hitbox ObjectHitbox
local function obj_set_hitbox(obj, hitbox)
    if not obj or not hitbox then return end
    -- Sets other hitbox values once
    if (obj.oFlags & OBJ_FLAG_30) == 0 then
        obj.oFlags = obj.oFlags | OBJ_FLAG_30

        obj.oInteractType = hitbox.interactType
        obj.oDamageOrCoinValue = hitbox.damageOrCoinValue
        obj.oHealth = hitbox.health
        obj.oNumLootCoins = hitbox.numLootCoins

        cur_obj_become_tangible()
    end

    -- Set actual hitboxes
    obj.hitboxRadius = obj.header.gfx.scale.x * hitbox.radius
    obj.hitboxHeight = obj.header.gfx.scale.y * hitbox.height
    obj.hurtboxRadius = obj.header.gfx.scale.x * hitbox.hurtboxRadius
    obj.hurtboxHeight = obj.header.gfx.scale.y * hitbox.hurtboxHeight
    obj.hitboxDownOffset = obj.header.gfx.scale.y * hitbox.downOffset
end

-- --- Global Switch State (Shared) ---
local START_STATE = 1
local switch_block_state = START_STATE
local scalar_timer = 0
local StarSpawned = false

hook_event(HOOK_ON_PACKET_RECEIVE, function (datatable)
    if datatable.timer then scalar_timer = datatable.timer end
    if datatable.state then switch_block_state = datatable.state end
end)

hook_event(HOOK_ON_LEVEL_INIT, function ()
    switch_block_state = START_STATE
    StarSpawned = false
end)
"""

# --- Behaviors ---

register_mop_behavior(
    "bhvFlipBlock_MOP",
    """
local E_MODEL_FLIPBLOCK = smlua_model_util_get_id("FlipBlock_MOP")
local FLIP_BLOCK_ACT_UNINITIALIZED = 0
local FLIP_BLOCK_ACT_IDLE = 1
local FLIP_BLOCK_ACT_FLIPPING = 2
local FLIP_TIMER = 210

local sFlipBlockHitbox = {
    interactType = INTERACT_BREAKABLE,
    downOffset = 0,
    damageOrCoinValue = 0,
    health = 0,
    numLootCoins = 0,
    radius = 64,
    height = 64,
    hurtboxHeight = 0,
    hurtboxRadius = 0
}

function bhv_flip_block_init(obj)
    obj.oMoveAnglePitch = obj.oFaceAnglePitch
    obj_set_model_extended(obj, E_MODEL_FLIPBLOCK)
end

function bhv_flip_block_loop(obj)
    obj.oInteractStatus = 0
    if obj.oTimer == 0 and obj.oAction == FLIP_BLOCK_ACT_UNINITIALIZED then
        obj_set_hitbox(obj, sFlipBlockHitbox)
        obj.oAction = FLIP_BLOCK_ACT_IDLE
    end
    if obj.oAction == FLIP_BLOCK_ACT_FLIPPING then
        obj.header.gfx.scale.y = 0.1
        if obj.oTimer == FLIP_TIMER then
            obj.oAction = FLIP_BLOCK_ACT_IDLE
            obj.oSubAction = 0
            obj.header.gfx.scale.y = 1
        end
        obj.oFaceAnglePitch = obj.oFaceAnglePitch + (FLIP_TIMER - obj.oTimer) * 16
        if ((obj.oFaceAnglePitch / 0x8000) - obj.oSubAction) > 0 then
            cur_obj_play_sound_1(SOUND_GENERAL_SWISH_WATER)
            obj.oSubAction = obj.oSubAction + 1
        end
    else
        local m = gMarioStates[0]
        local next_position = m.pos.y + m.vel.y + 160
        if not is_bubbled(m) and cur_obj_was_attacked_or_ground_pounded() ~= 0
        or (mario_is_within_rectangle(obj.oPosX-100, obj.oPosX+100, obj.oPosZ-100, obj.oPosZ+100) ~= 0
            and m.vel.y > 0 and (m.ceil and m.ceil.object) and m.ceil.object == obj
            and (next_position > m.ceilHeight and next_position < obj.oPosY + 100)) then
            obj.oAction = FLIP_BLOCK_ACT_FLIPPING
            obj.oIntangibleTimer = FLIP_TIMER
            m.vel.y = (m.vel.y > 0) and 0 or m.vel.y
            cur_obj_play_sound_1(SOUND_GENERAL_SWISH_WATER)
        else
            obj.oFaceAnglePitch = obj.oMoveAnglePitch
            obj.header.gfx.scale.y = 1
            load_object_collision_model()
        end
    end
end
""",
    """
const BehaviorScript bhvFlipBlock_MOP[] = {
    BEGIN(OBJ_LIST_SURFACE),
    ID(id_bhvNewId),
    OR_INT(oFlags, OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE),
    SET_INT(oAction, 0),
    SET_FLOAT(oCollisionDistance, 500),
    LOAD_COLLISION_DATA(col_FlipBlock_MOP_0x7d1a98),
    CALL_NATIVE(bhv_flip_block_init),
    BEGIN_LOOP(),
    CALL_NATIVE(bhv_flip_block_loop),
    SET_INT(oInteractStatus, 0),
    END_LOOP(),
};
""",
    ["FlipBlock_MOP"],
)

register_mop_behavior(
    "bhvNoteblock_MOP",
    """
local E_MODEL_NOTEBLOCK = smlua_model_util_get_id("Noteblock_MOP")
local NOTEBLOCK_ACT_IDLE = 0
local NOTEBLOCK_ACT_BOUNCING = 1

function bhv_noteblock_init(obj)
    obj_set_model_extended(obj, E_MODEL_NOTEBLOCK)
end

function bhv_noteblock_loop(obj)
    local m = gMarioStates[0]
    local y_spd = 64

    if cur_obj_is_mario_on_platform() == 1 and not is_bubbled(m) then
        -- Jump. If A is pressed during the jump, increase y_spd.
        if m.controller.buttonPressed & A_BUTTON ~= 0 then
            y_spd = y_spd + 12
            spawn_mist_particles()
        end
        set_mario_action(m, ACT_DOUBLE_JUMP, 0)

        -- Calculates y speed
        local intermediate_y_spd = repack(y_spd, "f", "I")
		intermediate_y_spd = intermediate_y_spd + (obj.oBehParams2ndByte << 16)
		y_spd = repack(intermediate_y_spd, "I", "f")
		m.vel.y = y_spd

        obj.oAction = NOTEBLOCK_ACT_BOUNCING
    end

    if obj.oAction == NOTEBLOCK_ACT_BOUNCING then
        if obj.oTimer == 4 then
            obj.oAction = NOTEBLOCK_ACT_IDLE
            obj.oPosY = obj.oHomeY
        else
            -- Moves the noteblock slightly up and down, to give it a "bounce"
            if obj.oTimer > 2 then
                obj.oPosY = obj.oHomeY + (obj.oTimer % 3) * 6
            else
                obj.oPosY = obj.oHomeY - obj.oTimer * 6
            end
        end
    end
end
""",
    """
const BehaviorScript bhvNoteblock_MOP[] = {
    BEGIN(OBJ_LIST_SURFACE),
    ID(id_bhvNewId),
    OR_INT(oFlags, OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE),
    SET_HOME(),
    LOAD_COLLISION_DATA(col_Noteblock_MOP_0xaa6444),
    SCALE(0, 64),
    CALL_NATIVE(bhv_noteblock_init),
    BEGIN_LOOP(),
    CALL_NATIVE(bhv_noteblock_loop),
    CALL_NATIVE(load_object_collision_model),
    END_LOOP(),
};
""",
    ["Noteblock_MOP"],
)

register_mop_behavior(
    "bhvSandBlock_MOP",
    """
local E_MODEL_SANDBLOCK = smlua_model_util_get_id("SandBlock_MOP")
local SANDBLOCK_ACT_IDLE = 0
local SANDBLOCK_ACT_FADING = 1
local SANDBLOCK_ACT_DISAPPEARED = 2
local FADE_TIMER = 300

function bhv_sandblock_init(obj)
    obj_set_model_extended(obj, E_MODEL_SANDBLOCK)
end

function bhv_sandblock_loop(obj)
    -- Only activate collision if the sandblock has not disappeared
    if obj.oAction < SANDBLOCK_ACT_DISAPPEARED then
        load_object_collision_model()
    end
    -- Disappearing
    local action = obj.oAction
    if action == SANDBLOCK_ACT_FADING then
        if obj.oTimer == FADE_TIMER then
            obj.oAction = SANDBLOCK_ACT_DISAPPEARED
        end
        -- Causes the sandblock to become smaller and smaller on the y axis
        obj.header.gfx.scale.y = ((300 - obj.oTimer) / 300.0)
        -- Makes the sandblock not move the player vertically as it's breaking
        obj.oPosY = obj.oPosY + 1.025

        -- Spawn effects
        spawn_non_sync_object(id_bhvDirtParticleSpawner, E_MODEL_NONE, obj.oPosX, obj.oPosY, obj.oPosZ, nil)
        cur_obj_play_sound_1(SOUND_ENV_MOVINGSAND)
    elseif action == SANDBLOCK_ACT_DISAPPEARED then
        cur_obj_hide()
        if obj.oTimer == FADE_TIMER + 1 then
            obj.oPosY = obj.oHomeY
            obj.oAction = SANDBLOCK_ACT_IDLE
            obj.header.gfx.scale.y = 1.0
            cur_obj_unhide()
        end
    end

    if cur_obj_is_mario_on_platform() == 1 and obj.oAction == SANDBLOCK_ACT_IDLE and not is_bubbled(gMarioStates[0]) then
        obj.oAction = SANDBLOCK_ACT_FADING
    end
end
""",
    """
const BehaviorScript bhvSandBlock_MOP[] = {
    BEGIN(OBJ_LIST_SURFACE),
    ID(id_bhvNewId),
    OR_INT(oFlags, OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE),
    SET_HOME(),
    LOAD_COLLISION_DATA(col_Sandblock_MOP_0xaa6444),
    CALL_NATIVE(bhv_sandblock_init),
    BEGIN_LOOP(),
    CALL_NATIVE(bhv_sandblock_loop),
    END_LOOP(),
};
""",
    ["SandBlock_MOP"],
)

register_mop_behavior(
    "bhvSpring_MOP",
    """
local E_MODEL_SPRING = smlua_model_util_get_id("Spring_MOP")
local SPRING_ACT_READY = 0
local SPRING_ACT_USED = 1

function bhv_Spring_init(obj)
    obj_set_model_extended(obj, E_MODEL_SPRING)
end

function bhv_Spring_loop(obj)
    local m = gMarioStates[0]
    if is_bubbled(m) then return end

    -- Initial y speed
    local Yspd = 56.0
    local y_vel = nil
    local forward_vel = nil

    if obj.oAction == SPRING_ACT_READY then
        if obj_check_if_collided_with_object(obj, m.marioObj) ~= 0 then
            set_mario_action(m, ACT_DOUBLE_JUMP, 0)
            m.faceAngle.y = obj.oFaceAngleYaw

            y_vel = repack(Yspd, "f", "I")
            -- Calculates how fast Mario should go using oBehParams2ndByte
            forward_vel = repack(y_vel + (obj.oBehParams & 0x00FF0000), "I", "f")
            m.forwardVel = forward_vel

            -- Calculates how high Mario should go using the 1st byte
            y_vel = y_vel + (((obj.oBehParams >> 24) & 0xFF) << 16)
            bounce_off_object(m, obj, repack(y_vel, "I", "f"))

            -- Prevent interaction for some time
            obj.oAction = SPRING_ACT_USED
        end
    else
        if obj.oTimer == 15 then
            obj.oAction = SPRING_ACT_READY
        end
    end
end
""",
    """
const BehaviorScript bhvSpring_MOP[] = {
    BEGIN(OBJ_LIST_LEVEL),
    ID(id_bhvNewId),
    OR_INT(oFlags, OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE),
    SET_HITBOX(160, 160),
    SET_INTERACT_TYPE(INTERACT_COIN),
    SET_INT(oIntangibleTimer, 0),
    CALL_NATIVE(bhv_Spring_init),
    BEGIN_LOOP(),
    CALL_NATIVE(bhv_Spring_loop),
    END_LOOP(),
};
""",
    ["Spring_MOP"],
)

register_mop_behavior(
    "bhvShrink_Platform_MOP",
    """
local E_MODEL_SHRINK_PLATFORM = smlua_model_util_get_id("Shrink_Platform_MOP")
local E_MODEL_SHRINK_PLATFORM_BORDER = smlua_model_util_get_id("Shrink_Platform_Border_MOP")
local SHRINK_PLATFORM_ACT_IDLE = 0
local SHRINK_PLATFORM_ACT_SHRINKING = 1
local SHRINK_PLATFORM_ACT_DISAPPEARED = 2
local SHRINK_TIME = 150

function bhv_Shrink_Platform_init(obj)
    obj_set_model_extended(obj, E_MODEL_SHRINK_PLATFORM)
    spawn_object(obj, E_MODEL_SHRINK_PLATFORM_BORDER, id_bhvShrink_Platform_Border_MOP)
end

function bhv_Shrink_Platform_loop(obj)
    -- Only activate collision if the model is still visible
    if obj.oAction < SHRINK_PLATFORM_ACT_DISAPPEARED then
        load_object_collision_model()
    end

    local action = obj.oAction
    --disappearing
    if action == SHRINK_PLATFORM_ACT_SHRINKING then
        if obj.oTimer == SHRINK_TIME then
            obj.oAction = SHRINK_PLATFORM_ACT_DISAPPEARED
        end

        -- Slowly shrinks the size of the platform horizontally
        obj.header.gfx.scale.x = (SHRINK_TIME - obj.oTimer) / SHRINK_TIME
        obj.header.gfx.scale.z = (SHRINK_TIME - obj.oTimer) / SHRINK_TIME
    elseif action == SHRINK_PLATFORM_ACT_DISAPPEARED then
        -- Reset after the platform has fully disappeared
        cur_obj_hide()
        if obj.oTimer == SHRINK_TIME + 1 then
            obj.oAction = SHRINK_PLATFORM_ACT_IDLE
            obj.header.gfx.scale.x = 1.0
            obj.header.gfx.scale.z = 1.0
            cur_obj_unhide()
        end
    end

    -- Start disappearing once Mario gets on it
    if cur_obj_is_mario_on_platform() == 1 and obj.oAction == SHRINK_PLATFORM_ACT_IDLE and not is_bubbled(gMarioStates[0]) then
        obj.oAction = SHRINK_PLATFORM_ACT_SHRINKING
        cur_obj_play_sound_1(SOUND_OBJ_UNK23)
    end
end
""",
    """
const BehaviorScript bhvShrink_Platform_MOP[] = {
    BEGIN(OBJ_LIST_SURFACE),
    ID(id_bhvNewId),
    OR_INT(oFlags, OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE),
    LOAD_COLLISION_DATA(col_Shrink_Platform_MOP_0xad3720),
    SET_FLOAT(oCollisionDistance, 1024),
    CALL_NATIVE(bhv_Shrink_Platform_init),
    BEGIN_LOOP(),
    CALL_NATIVE(load_object_collision_model),
    END_LOOP(),
};
""",
    ["Shrink_Platform_MOP", "Shrink_Platform_Border_MOP"],
)

register_mop_behavior(
    "bhvSwitchblock_MOP",
    """
local E_MODEL_SWITCHBLOCK = smlua_model_util_get_id("Switchblock_MOP")
local SWITCHBLOCK_ACT_ACTIVE = 0
local SWITCHBLOCK_ACT_INACTIVE = 1

function bhv_Switchblock_init(obj)
    obj_set_model_extended(obj, E_MODEL_SWITCHBLOCK)
end

function bhv_Switchblock_loop(obj)
    -- Determines which block color this becomes
    obj.oAnimState = obj.oBehParams2ndByte + obj.oAction

    -- Only loads collision if the corresponding switch is pressed
    if switch_block_state == obj.oBehParams2ndByte >> 1 then
        load_object_collision_model()
        obj.oAction = SWITCHBLOCK_ACT_ACTIVE
    else
        obj.oAction = SWITCHBLOCK_ACT_INACTIVE
    end
end
""",
    """
const BehaviorScript bhvSwitchblock_MOP[] = {
    BEGIN(OBJ_LIST_SURFACE),
    ID(id_bhvNewId),
    OR_INT(oFlags, OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE),
    LOAD_COLLISION_DATA(col_Switchblock_MOP_0x7d3058),
    SET_FLOAT(oCollisionDistance, 512),
    CALL_NATIVE(bhv_Switchblock_init),
    BEGIN_LOOP(),
    CALL_NATIVE(bhv_Switchblock_loop),
    END_LOOP(),
};
""",
    ["Switchblock_MOP"],
)

register_mop_behavior(
    "bhvSwitchblock_Switch_MOP",
    """
local E_MODEL_SWITCHBLOCK_SWITCH = smlua_model_util_get_id("Switchblock_Switch_MOP")

function bhv_Switchblock_Switch_init(obj)
    obj_set_model_extended(obj, E_MODEL_SWITCHBLOCK_SWITCH)
end

function bhv_Switchblock_Switch_loop(obj)
    obj.oAnimState = obj.oBehParams2ndByte
    local old_state = switch_block_state
    if cur_obj_is_mario_on_platform() == 1 and not is_bubbled(gMarioStates[0]) then
        switch_block_state = obj.oBehParams2ndByte
    end

    local scalar = 0
    if switch_block_state ~= obj.oBehParams2ndByte then
        scalar = 1
    end

    -- Whenever the switch block state changes
    if old_state ~= switch_block_state then
        scalar_timer = 0
        local np = gNetworkPlayers
        for i = 1, MAX_PLAYERS - 1, 1 do
            if is_current_area_sync_valid() and np[0].currLevelNum == np[i].currLevelNum then
                network_send_to(i, true, { timer = 0, state = switch_block_state })
            end
        end
    end

    -- Slowly raise and lower the switch
    if scalar_timer < 100 then
        scalar_timer = scalar_timer + 1
    end

    local result = scalar * 0.9 + 0.1
    local current_scale = obj.header.gfx.scale.y

    -- Make smaller if the switch is pressed
    obj.header.gfx.scale.y = lerp(current_scale, result, scalar_timer * 0.01)
end
""",
    """
const BehaviorScript bhvSwitchblock_Switch_MOP[] = {
    BEGIN(OBJ_LIST_SURFACE),
    ID(id_bhvNewId),
    OR_INT(oFlags, OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE),
    LOAD_COLLISION_DATA(col_Switchblock_Switch_MOP_0x7d7348),
    SET_FLOAT(oCollisionDistance, 512),
    CALL_NATIVE(bhv_Switchblock_Switch_init),
    BEGIN_LOOP(),
    CALL_NATIVE(load_object_collision_model),
    CALL_NATIVE(bhv_Switchblock_Switch_loop),
    END_LOOP(),
};
""",
    ["Switchblock_Switch_MOP"],
)

register_mop_behavior(
    "bhvFlipswap_Platform_MOP",
    """
local E_MODEL_FLIPSWAP_PLATFORM = smlua_model_util_get_id("Flipswap_Platform_MOP")
local E_MODEL_FLIPSWAP_PLATFORM_BORDER = smlua_model_util_get_id("Flipswap_Platform_Border_MOP")
local FLIPSWAP_PLATFORM_ACT_IDLE = 0
local FLIPSWAP_PLATFORM_ACT_FLIPPING = 1
-- 1x is very fast, 0.5x is usually the norm
local FLIP_SPEED_MULTIPLIER = 0.5

function bhv_Flipswap_Platform_init(obj)
    obj_set_model_extended(obj, E_MODEL_FLIPSWAP_PLATFORM)
    -- Spawns the border
    local childObj = spawn_non_sync_object(id_bhvFlipswap_Platform_Border_MOP, E_MODEL_FLIPSWAP_PLATFORM_BORDER, obj.oPosX, obj.oPosY, obj.oPosZ,
    ---@param o Object
    function (o)
        -- Probably overdone but just to be safe
        obj_set_face_angle(o, obj.oFaceAnglePitch, obj.oFaceAngleYaw, obj.oFaceAngleRoll)
        obj_set_move_angle(o, obj.oMoveAnglePitch, obj.oMoveAngleYaw, obj.oMoveAngleRoll)
    end)
    childObj.parentObj = obj
end

function bhv_Flipswap_Platform_loop(obj)
    local m = gMarioStates[0]

    local action = obj.oAction
    if action == FLIPSWAP_PLATFORM_ACT_IDLE then
        -- If Mario enters an air action, start flipping
        if m.prevAction & ACT_GROUP_MASK ~= ACT_GROUP_AIRBORNE and m.action & ACT_GROUP_MASK == ACT_GROUP_AIRBORNE then
            --sloth brain it
            if obj.oFaceAngleRoll == 0 then
                obj.oMoveAngleRoll = -2048 * FLIP_SPEED_MULTIPLIER
            else
                obj.oMoveAngleRoll = 2048 * FLIP_SPEED_MULTIPLIER
            end
            obj.oAction = FLIPSWAP_PLATFORM_ACT_FLIPPING
        end
    elseif action == FLIPSWAP_PLATFORM_ACT_FLIPPING then
        -- Flip the platform
        if obj.oTimer < 16 * FLIP_SPEED_MULTIPLIER ^ -1 then
            obj.oFaceAngleRoll = obj.oFaceAngleRoll + obj.oMoveAngleRoll
        -- Disallow flipping again until Mario lands
        elseif m.action & ACT_GROUP_MASK ~= ACT_GROUP_AIRBORNE then
            obj.oAction = FLIPSWAP_PLATFORM_ACT_IDLE
        end
    end
end
""",
    """
const BehaviorScript bhvFlipswap_Platform_MOP[] = {
    BEGIN(OBJ_LIST_SURFACE),
    ID(id_bhvNewId),
    OR_INT(oFlags, OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE),
    SET_INT(oFaceAngleRoll, 0),
    LOAD_COLLISION_DATA(col_Flipswap_Platform_MOP_0x7d9d88),
    SET_FLOAT(oCollisionDistance, 1024),
    CALL_NATIVE(bhv_Flipswap_Platform_init),
    BEGIN_LOOP(),
    CALL_NATIVE(bhv_Flipswap_Platform_loop),
    CALL_NATIVE(load_object_collision_model),
    END_LOOP(),
};
""",
    ["Flipswap_Platform_MOP", "Flipswap_Platform_Border_MOP"],
)

register_mop_behavior(
    "bhvMoving_Grid_Platform_MOP",
    """
local E_MODEL_MOVING_GRID_PLATFORM = smlua_model_util_get_id("Moving_Grid_Platform_MOP")
local E_MODEL_MOVING_GRID_PLATFORM_GEARS = smlua_model_util_get_id("Moving_Grid_Platform_Gears_MOP")

function bhv_Moving_Grid_Platform_init(obj)
    obj_set_model_extended(obj, E_MODEL_MOVING_GRID_PLATFORM)
    -- Spawns the gears
    spawn_object(obj, E_MODEL_MOVING_GRID_PLATFORM_GEARS, id_bhvMoving_Grid_Platform_Gears_MOP)
end

function bhv_Moving_Grid_Platform_loop(obj)
    local m = gMarioStates[0]
    -- Only active if Mario is on the platform
    if cur_obj_is_mario_on_platform() == 1 and not is_bubbled(m) then
        -- Repacks the 2nd byte of the float into an integer
        local Bparam2 = repack(obj.oBehParams2ndByte, "I", "b")
        -- If it's 0 then it moves on the x axis, otherwise it moves on the z axis
        if Bparam2 == 0 then
            obj.oVelX = approach_by_increment(m.pos.x - m.prevPos.x, obj.oVelX, 4)
        else
            obj.oVelZ = approach_by_increment(m.pos.z - m.prevPos.z, obj.oVelZ, 4)
        end
    else
        obj.oVelX = approach_by_increment(0, obj.oVelX, 0.5)
        obj.oVelZ = approach_by_increment(0, obj.oVelZ, 0.5)
    end

    cur_obj_move_using_vel()
    load_object_collision_model()
end
""",
    """
const BehaviorScript bhvMoving_Grid_Platform_MOP[] = {
    BEGIN(OBJ_LIST_SURFACE),
    ID(id_bhvNewId),
    OR_INT(oFlags, OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE),
    LOAD_COLLISION_DATA(col_Moving_Grid_Platform_MOP_0x7db1e8),
    SET_FLOAT(oCollisionDistance, 1024),
    CALL_NATIVE(bhv_Moving_Grid_Platform_init),
    BEGIN_LOOP(),
    CALL_NATIVE(bhv_Moving_Grid_Platform_loop),
    END_LOOP(),
};
""",
    ["Moving_Grid_Platform_MOP", "Moving_Grid_Platform_Gears_MOP"],
)

register_mop_behavior(
    "bhvMoving_Grid_Platform_Gears_MOP",
    """
function bhv_Moving_Grid_Platform_Gears_loop(obj)
    local parent = obj.parentObj
    if not parent then return end

    -- Use the parent's velocity to determine how the gears should rotate
    local vel = parent.oVelX + parent.oVelZ
    obj.oFaceAnglePitch = obj.oFaceAnglePitch + vel * 64
    obj_copy_pos(obj, parent)
end
""",
    """
const BehaviorScript bhvMoving_Grid_Platform_Gears_MOP[] = {
    BEGIN(OBJ_LIST_DEFAULT),
    ID(id_bhvNewId),
    OR_INT(oFlags, OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE),
    BEGIN_LOOP(),
    CALL_NATIVE(bhv_Moving_Grid_Platform_Gears_loop),
    END_LOOP(),
};
""",
    ["Moving_Grid_Platform_Gears_MOP"],
)

register_mop_behavior(
    "bhvGreen_Switchboard_MOP",
    """
local E_MODEL_GREEN_SWITCHBOARD = smlua_model_util_get_id("Green_Switchboard_MOP")
local E_MODEL_GREEN_SWITCHBOARD_GEARS = smlua_model_util_get_id("Green_Switchboard_Gears_MOP")

function bhv_Green_Switchboard_init(obj)
    obj_set_model_extended(obj, E_MODEL_GREEN_SWITCHBOARD)
    -- Spawns the gears
    spawn_object(obj, E_MODEL_GREEN_SWITCHBOARD_GEARS, id_bhvGreen_Switchboard_Gears_MOP)
end

function bhv_Green_Switchboard_loop(obj)
    local m = gMarioStates[0]
    local move = 0

    if cur_obj_is_mario_on_platform() == 1 and not is_bubbled(m) then
        local dx = m.pos.x - obj.oPosX
        local dz = m.pos.z - obj.oPosZ

        -- Rotates the switchboard based on Mario's position
        local d_pos = dx * sins(obj.oMoveAngleYaw) + dz * coss(obj.oMoveAngleYaw)
        obj.oFaceAnglePitch = approach_by_increment(d_pos * -10, obj.oFaceAnglePitch, 128)

        -- Moves the switchboard based on its pitch
        move = obj.oFaceAnglePitch / -10
        if move > 10 then
            obj.oForwardVel = approach_by_increment(move, obj.oForwardVel, 2)
        elseif move < -10 then
            obj.oForwardVel = approach_by_increment(move, obj.oForwardVel, 2)
        end
    else
        obj.oForwardVel = approach_by_increment(0, obj.oForwardVel, 0.5)
        obj.oFaceAnglePitch = approach_by_increment(0, obj.oFaceAnglePitch, 128)
    end

    cur_obj_move_using_vel()
    load_object_collision_model()
end

function bhv_Green_Switchboard_Gears_loop(obj)
    local parent = obj.parentObj
    if not parent then return end

    -- Move with our parent and rotate using the parent's forward velocity
    obj_copy_pos(obj, parent)
    obj.oFaceAnglePitch = obj.oFaceAnglePitch + parent.oForwardVel * 64
end
""",
    """
const BehaviorScript bhvGreen_Switchboard_MOP[] = {
    BEGIN(OBJ_LIST_SURFACE),
    ID(id_bhvNewId),
    OR_INT(oFlags, OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE),
    LOAD_COLLISION_DATA(col_Green_Switchboard_MOP_0x7ddc38),
    SET_FLOAT(oCollisionDistance, 1024),
    CALL_NATIVE(bhv_Green_Switchboard_init),
    BEGIN_LOOP(),
    CALL_NATIVE(bhv_Green_Switchboard_loop),
    END_LOOP(),
};

const BehaviorScript bhvGreen_Switchboard_Gears_MOP[] = {
    BEGIN(OBJ_LIST_DEFAULT),
    ID(id_bhvNewId),
    OR_INT(oFlags, OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE),
    BEGIN_LOOP(),
    CALL_NATIVE(bhv_Green_Switchboard_Gears_loop),
    END_LOOP(),
};
""",
    ["Green_Switchboard_MOP", "Green_Switchboard_Gears_MOP"],
)

register_mop_behavior(
    "bhvMoving_Rotating_Block_MOP",
    """
local E_MODEL_MOVING_ROTATING_BLOCK = smlua_model_util_get_id("Moving_Rotating_Block_MOP")
local ZPLUS = 0 local ZMINUS = 1 local XPLUS = 2 local XMINUS = 3 local LOOP = 4
local Paths = {
    [ZPLUS] = {0, 0, 1}, [ZMINUS] = {0, 0, -1}, [XPLUS] = {1, 0, 0}, [XMINUS] = {-1, 0, 0}
}

function bhv_Moving_Rotating_Block_init(obj)
    obj_set_model_extended(obj, E_MODEL_MOVING_ROTATING_BLOCK)
end

function bhv_Moving_Rotating_Block_loop(obj)
    local p = Paths[obj.oBehParams2ndByte]
    if p then
        obj.oVelX = p[1] * 10
        obj.oVelY = p[2] * 10
        obj.oVelZ = p[3] * 10
    end
    cur_obj_rotate_face_angle_using_vel()
    cur_obj_move_using_vel()
end
""",
    """
const BehaviorScript bhvMoving_Rotating_Block_MOP[] = {
    BEGIN(OBJ_LIST_SURFACE),
    ID(id_bhvNewId),
    OR_INT(oFlags, OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE),
    LOAD_COLLISION_DATA(col_Moving_Rotating_Block_MOP_0x7d8a78),
    SET_FLOAT(oCollisionDistance, 1024),
    CALL_NATIVE(bhv_Moving_Rotating_Block_init),
    CALL_NATIVE(bhv_Moving_Rotating_Block_loop),
    CALL_NATIVE(load_object_collision_model),
    END_LOOP(),
};
""",
    ["Moving_Rotating_Block_MOP"],
)

register_mop_behavior(
    "bhvPSwitch_MOP",
    """
local E_MODEL_PURPLE_SWITCH = smlua_model_util_get_id("purple_switch_geo")

local function Swap_Coins_Box()
	local box_obj = obj_get_first_with_behavior_id(id_bhvBreakableBox)
	local coin_obj = obj_get_first_with_behavior_id(id_bhvYellowCoin)
	-- Turn all breakable boxes into yellow coins...
	while box_obj do
        box_obj.activeFlags = ACTIVE_FLAG_DEACTIVATED
        spawn_object(box_obj, E_MODEL_YELLOW_COIN, id_bhvYellowCoin)
        box_obj = obj_get_next_with_same_behavior_id(box_obj)
	end
    -- ...and all yellow coins into breakable boxes
	while coin_obj do
        coin_obj.activeFlags = ACTIVE_FLAG_DEACTIVATED
        coin_obj.oIntangibleTimer = -1
        spawn_object(coin_obj, E_MODEL_BREAKABLE_BOX, id_bhvBreakableBox)
        coin_obj = obj_get_next_with_same_behavior_id(coin_obj)
	end
end

function bhv_pswitch_init(obj)
    obj_set_model_extended(obj, E_MODEL_PURPLE_SWITCH)
end

function bhv_pswitch_loop(obj)
    local m = gMarioStates[0]
    local m_obj = m.marioObj
    local sound_source = { x = 0, y = 0, z = 0 }

    switch (obj.oAction, {
        [PURPLE_SWITCH_IDLE] = function ()
            cur_obj_scale(1.0)
            if m_obj.platform == obj and m.action & MARIO_UNKNOWN_13 == 0 then
                if lateral_dist_between_objects(obj, m_obj) < 127.5 then
                    obj.oAction = PURPLE_SWITCH_PRESSED
                end
            end
        end,
        [PURPLE_SWITCH_PRESSED] = function ()
            cur_obj_scale_over_time(2, 3, 1.0, 0.2)
            if obj.oTimer == 3 then
                cur_obj_play_sound_2(SOUND_GENERAL2_PURPLE_SWITCH)
                obj.oAction = PURPLE_SWITCH_TICKING
                cur_obj_shake_screen(SHAKE_POS_SMALL)
                Swap_Coins_Box()
            end
        end,
        [PURPLE_SWITCH_TICKING] = function ()
            if obj.oTimer < 360 then
                play_sound(SOUND_GENERAL2_SWITCH_TICK_FAST, sound_source)
            else
                play_sound(SOUND_GENERAL2_SWITCH_TICK_SLOW, sound_source)
            end
            if obj.oTimer > 400 then
                obj.oAction = PURPLE_SWITCH_WAIT_FOR_MARIO_TO_GET_OFF
                Swap_Coins_Box()
            end
        end,
        [PURPLE_SWITCH_UNPRESSED] = function ()
            cur_obj_scale_over_time(2, 3, 0.2, 1.0)
            if obj.oTimer == 3 then
                obj.oAction = PURPLE_SWITCH_IDLE
            end
        end,
        [PURPLE_SWITCH_WAIT_FOR_MARIO_TO_GET_OFF] = function ()
            if cur_obj_is_mario_on_platform() == 0 then
                obj.oAction = PURPLE_SWITCH_UNPRESSED
            end
        end
    })
end
""",
    """
const BehaviorScript bhvPSwitch_MOP[] = {
    BEGIN(OBJ_LIST_SURFACE),
    ID(id_bhvNewId),
    OR_INT(oFlags, OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE),
    LOAD_COLLISION_DATA(purple_switch_seg8_collision_0800C7A8),
    CALL_NATIVE(bhv_pswitch_init),
    BEGIN_LOOP(),
    CALL_NATIVE(bhv_pswitch_loop),
    CALL_NATIVE(load_object_collision_model),
    END_LOOP(),
};
""",
    [],
)

register_mop_behavior(
    "bhvCheckpoint_Flag_MOP",
    """
local E_MODEL_CHECKPOINT = smlua_model_util_get_id("Checkpoint_Flag_MOP")

function bhv_checkpoint_flag_init(obj)
    obj_set_model_extended(obj, E_MODEL_CHECKPOINT)
end

function bhv_checkpoint_flag_loop(obj)
    local m = gMarioStates[0]
    if obj.oAction == 0 then
        if obj_check_if_collided_with_object(obj, m.marioObj) ~= 0 then
            m.spawnInfo.startPos.x, m.spawnInfo.startPos.y, m.spawnInfo.startPos.z = obj.oPosX, obj.oPosY, obj.oPosZ
            m.spawnInfo.startAngle.y = obj.oFaceAngleYaw
            cur_obj_play_sound_1(SOUND_GENERAL_COLLECT_1UP)
            obj.oAction = 1
        end
    end
end
""",
    """
const BehaviorScript bhvCheckpoint_Flag_MOP[] = {
    BEGIN(OBJ_LIST_GENACTOR),
    ID(id_bhvNewId),
    OR_INT(oFlags, OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE | OBJ_FLAG_COMPUTE_DIST_TO_MARIO),
    SET_INT(oInteractType, INTERACT_POLE),
    SET_HITBOX(64, 650),
    SET_INT(oIntangibleTimer, -1),
    CALL_NATIVE(bhv_checkpoint_flag_init),
    BEGIN_LOOP(),
    CALL_NATIVE(bhv_checkpoint_flag_loop),
    END_LOOP(),
};
""",
    ["Checkpoint_Flag_MOP"],
)

register_mop_behavior(
    "bhvFlipswitch_Panel_MOP",
    """
local E_MODEL_FLIPSWITCH_PANEL = smlua_model_util_get_id("Flipswitch_Panel_MOP")

function bhv_flipswitch_panel_init(obj)
    obj_set_model_extended(obj, E_MODEL_FLIPSWITCH_PANEL)
    network_init_object(obj, false, { "oAction", "oAnimState" })
end

function bhv_flipswitch_panel_loop(obj)
    if StarSpawned then
        obj.oAnimState = 2
    else
        if obj.oAction == 0 then
            if cur_obj_is_mario_on_platform() == 1 and not is_bubbled(gMarioStates[0]) then
                obj.oAnimState = obj.oAnimState ~ 1
                cur_obj_play_sound_1(SOUND_GENERAL_BIG_CLOCK)
                obj.oAction = 1
                network_send_object(obj, true)
            end
        elseif obj.oAction == 1 then
            local cp = nearest_player_to_object(obj)
            if not cp or (cur_obj_is_mario_on_platform() == 0 and cp.platform ~= obj) then
                obj.oAction = 0
            end
        end
    end
end
""",
    """
const BehaviorScript bhvFlipswitch_Panel_MOP[] = {
    BEGIN(OBJ_LIST_SURFACE),
    ID(id_bhvNewId),
    OR_INT(oFlags, OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE),
    LOAD_COLLISION_DATA(col_Flipswitch_Panel_MOP_0x7daf78),
    SET_FLOAT(oCollisionDistance, 1024),
    CALL_NATIVE(bhv_flipswitch_panel_init),
    BEGIN_LOOP(),
    CALL_NATIVE(bhv_flipswitch_panel_loop),
    CALL_NATIVE(load_object_collision_model),
    END_LOOP(),
};
""",
    ["Flipswitch_Panel_MOP"],
)

register_mop_behavior(
    "bhvFlipswitch_Panel_StarSpawn_MOP",
    """
function bhv_flipswitch_panel_starspawn_loop(obj)
    if not StarSpawned then
        local flipswitches_count = count_objects_with_behavior(id_bhvFlipswitch_Panel_MOP)
        local flipswitches_active = 0

        local curr_obj = obj_get_first_with_behavior_id(id_bhvFlipswitch_Panel_MOP)
        while curr_obj do
            if curr_obj.oAnimState == 1 then
                flipswitches_active = flipswitches_active + 1
            end
            curr_obj = obj_get_next_with_behavior_id(curr_obj, id_bhvFlipswitch_Panel_MOP)
        end

        if flipswitches_active == flipswitches_count and flipswitches_count > 0 then
            spawn_red_coin_cutscene_star(obj.oPosX, obj.oPosY, obj.oPosZ)
            StarSpawned = true
        end
    end
end
""",
    """
const BehaviorScript bhvFlipswitch_Panel_StarSpawn_MOP[] = {
    BEGIN(OBJ_LIST_DEFAULT),
    ID(id_bhvNewId),
    OR_INT(oFlags, OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE),
    BEGIN_LOOP(),
    CALL_NATIVE(bhv_flipswitch_panel_starspawn_loop),
    END_LOOP(),
};
""",
    [],
)

register_mop_behavior(
    "bhvBlargg",
    """
local E_MODEL_BLARGG = smlua_model_util_get_id("blargg_geo")
local sBlarggHitbox = {
    interactType = INTERACT_MR_BLIZZARD,
    downOffset = 0,
    damageOrCoinValue = 1,
    health = 1,
    numLootCoins = 0,
    radius = 150,
    height = 250,
    hurtboxRadius = 150,
    hurtboxHeight = 250,
}

local function blargg_check_mario_collision(obj)
    if obj.oDistanceToMario < 300 and math.abs(obj.oPosY - gMarioStates[0].pos.y) < 300 then
        if (obj.oAction == BLARGG_ACT_CHASE or obj.oAction == BLARGG_ACT_SWIM) then
            if gMarioStates[0].action & ACT_FLAG_AIR == 0 then
                obj.oAction = BLARGG_ACT_KNOCKBACK
                cur_obj_init_animation(ANM_attack)
                cur_obj_play_sound_2(SOUND_OBJ2_PIRANHA_PLANT_BITE)
            end
        end
    end
end

local function blargg_act_swim(obj, m)
    obj.oForwardVel = 5.0
    if obj_return_home_if_safe(obj, obj.oHomeX, obj.oPosY, obj.oHomeZ, 800) == 1 and m.floor.type ~= SURFACE_DEFAULT then
        obj.oAction = BLARGG_ACT_CHASE
    end
end

local function blargg_act_chase_mario(obj, m)
    obj.oFlags = obj.oFlags | OBJ_FLAG_SET_FACE_YAW_TO_MOVE_YAW
    obj_turn_toward_object(obj, m.marioObj, 16, 4096)
    obj.oForwardVel = 10
    if is_point_within_radius_of_mario(obj.oHomeX, obj.oHomeY, obj.oHomeZ, 5000) == 0 or m.floor.type == SURFACE_DEFAULT then
        obj.oAction = BLARGG_ACT_SWIM
        cur_obj_init_animation(ANM_swim)
    end
end

local function blargg_act_knockback(obj, m)
    if obj.oBullyKBTimerAndMinionKOCounter == 18 then
        obj.oAction = BLARGG_ACT_CHASE
        obj.oBullyKBTimerAndMinionKOCounter = 0
        cur_obj_init_animation(ANM_attack)
        cur_obj_play_sound_2(SOUND_OBJ2_PIRANHA_PLANT_BITE)
    else
        obj.oBullyKBTimerAndMinionKOCounter = obj.oBullyKBTimerAndMinionKOCounter + 1
        obj_turn_toward_object(obj, m.marioObj, 16, 1280)
    end
end

local function blargg_act_back_up(obj)
    if obj.oTimer == 0 then
        obj.oFlags = obj.oFlags & ~OBJ_FLAG_SET_FACE_YAW_TO_MOVE_YAW
        obj.oMoveAngleYaw = obj.oMoveAngleYaw + 0x8000
    end
    obj.oForwardVel = 5.0
    if obj.oTimer == 15 then
        obj.oMoveAngleYaw = obj.oFaceAngleYaw
        obj.oFlags = obj.oFlags | OBJ_FLAG_SET_FACE_YAW_TO_MOVE_YAW
        obj.oAction = BLARGG_ACT_SWIM
    end
end

local function blargg_step(obj)
    local collisionFlags = object_step()
    if collisionFlags & (OBJ_FLAG_SET_FACE_YAW_TO_MOVE_YAW) == 0 and obj.oAction ~= BLARGG_ACT_KNOCKBACK then
        obj.oAction = BLARGG_ACT_BACKUP
    end
end

function bhv_blargg_init(obj)
    cur_obj_init_animation(ANM_swim)
    obj_set_model_extended(obj, E_MODEL_BLARGG)
    obj.oGravity = 4.0
    obj.oFriction = 0.91
    obj.oBuoyancy = 1.3
    obj_set_hitbox(obj, sBlarggHitbox)
    network_init_object(obj, true, nil)
end

function bhv_blargg_loop(obj)
    obj.oIntangibleTimer = 0
    blargg_check_mario_collision(obj)
    local m = gMarioStates[0]
    switch (obj.oAction, {
        [BLARGG_ACT_SWIM] = function () blargg_act_swim(obj, m) blargg_step(obj) end,
        [BLARGG_ACT_CHASE] = function () blargg_act_chase_mario(obj, m) blargg_step(obj) end,
        [BLARGG_ACT_KNOCKBACK] = function () blargg_act_knockback(obj, m) blargg_step(obj) end,
        [BLARGG_ACT_BACKUP] = function () blargg_act_back_up(obj) blargg_step(obj) end,
    })
end
""",
    """
const BehaviorScript bhvBlargg[] = {
    BEGIN(OBJ_LIST_GENACTOR),
    ID(id_bhvNewId),
    OR_INT(oFlags, (OBJ_FLAG_SET_FACE_YAW_TO_MOVE_YAW | OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE)),
    LOAD_ANIMATIONS(oAnimations, blargg_seg5_anims_0500616C),
    DROP_TO_FLOOR(),
    SET_HOME(),
    CALL_NATIVE(bhv_blargg_init),
    BEGIN_LOOP(),
        CALL_NATIVE(bhv_blargg_loop),
    END_LOOP(),
};
""",
    ["blargg"],
)

register_mop_behavior(
    "bhvFriendlyBlargg",
    """
local E_MODEL_FRIENDLY_BLARGG = smlua_model_util_get_id("friendly_blargg_geo")
local sBlarggFriendlyHitbox = {
    interactType = INTERACT_KOOPA_SHELL,
    downOffset = 0,
    damageOrCoinValue = 4,
    health = 1,
    numLootCoins = 1,
    radius = 50,
    height = 50,
    hurtboxRadius = 50,
    hurtboxHeight = 50,
}

local function blargg_friendly_explode(obj, m)
    set_mario_action(m, ACT_WALKING, 0)
    mario_stop_riding_object(m)
    spawn_object(obj, E_MODEL_EXPLOSION, id_bhvExplosion)
    obj_mark_for_deletion(obj)
end

function bhv_friendly_blargg_init(obj)
    cur_obj_init_animation(ANM_swim)
    obj_set_model_extended(obj, E_MODEL_FRIENDLY_BLARGG)
    obj_set_hitbox(obj, sBlarggFriendlyHitbox)
end

function bhv_blargg_friendly_loop(obj)
    if obj.oAction == FRIENDLY_BLARGG_ACT_IDLE then
        if obj.oInteractStatus & INT_STATUS_INTERACTED ~= 0 then
            obj.oAction = FRIENDLY_BLARGG_ACT_BEING_RIDDEN
        end
        cur_obj_move_standard(-20)
    elseif obj.oAction == FRIENDLY_BLARGG_ACT_BEING_RIDDEN then
        local m = gMarioStates[0]
        obj_copy_pos(obj, m.marioObj)
        local floor = cur_obj_update_floor_height_and_get_floor()
        if floor and floor.type ~= SURFACE_BURNING then
            blargg_friendly_explode(obj, m)
        end
        if obj.oInteractStatus & INT_STATUS_STOP_RIDING ~= 0 then
            obj.oAction = FRIENDLY_BLARGG_ACT_IDLE
        end
    end
    obj.oInteractStatus = 0
end
""",
    """
const BehaviorScript bhvFriendlyBlargg[] = {
    BEGIN(OBJ_LIST_LEVEL),
    ID(id_bhvNewId),
    OR_INT(oFlags, OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE),
    LOAD_ANIMATIONS(oAnimations, blargg_seg5_anims_0500616C),
    SET_OBJ_PHYSICS(30, -400, -50, 2000, 2000, 200, 0, 0),
    DROP_TO_FLOOR(),
    SET_HOME(),
    CALL_NATIVE(bhv_friendly_blargg_init),
    BEGIN_LOOP(),
        CALL_NATIVE(bhv_blargg_friendly_loop),
    END_LOOP(),
};
""",
    ["blargg_friendly"],
)

register_mop_behavior(
    "bhvEmitter_MOP",
    """
function bhv_emitter_loop(obj)
    spawn_object(obj, E_MODEL_NONE, id_bhvSparkleSpawn)
end
""",
    """
const BehaviorScript bhvEmitter_MOP[] = {
    BEGIN(OBJ_LIST_DEFAULT),
    ID(id_bhvNewId),
    OR_INT(oFlags, OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE),
    BEGIN_LOOP(),
        CALL_NATIVE(bhv_emitter_loop),
    END_LOOP(),
};
""",
    [],
)

register_mop_behavior(
    "bhvJukebox_MOP",
    """
function bhv_jukebox_loop(obj)
    obj_mark_for_deletion(obj)
end
""",
    """
const BehaviorScript bhvJukebox_MOP[] = {
    BEGIN(OBJ_LIST_DEFAULT),
    ID(id_bhvNewId),
    CALL_NATIVE(bhv_jukebox_loop),
    BREAK(),
};
""",
    [],
)

register_mop_behavior(
    "bhvShell_1_MOP",
    """
function bhv_shell_init(obj)
    obj_mark_for_deletion(obj)
end
""",
    """
const BehaviorScript bhvShell_1_MOP[] = {
    BEGIN(OBJ_LIST_DEFAULT),
    ID(id_bhvNewId),
    CALL_NATIVE(bhv_shell_init),
    BREAK(),
};
""",
    [],
)

register_mop_behavior(
    "bhvShell_2_MOP",
    """
function bhv_shell_init(obj)
    obj_mark_for_deletion(obj)
end
""",
    """
const BehaviorScript bhvShell_2_MOP[] = {
    BEGIN(OBJ_LIST_DEFAULT),
    ID(id_bhvNewId),
    CALL_NATIVE(bhv_shell_init),
    BREAK(),
};
""",
    [],
)
