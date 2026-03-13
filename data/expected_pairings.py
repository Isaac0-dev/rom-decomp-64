"""
Expected pairings between vanilla SM64 behaviors and their typical models.

This is a many-to-many mapping used by the ObjectCorrelationPass to boost
or penalize confidence when cross-referencing ObjectRecord data.

Each entry maps a behavior name to the set of model names that vanilla SM64
uses with that behavior. A reverse index is auto-built at import time.
"""

from typing import Dict, FrozenSet, Set

# ---------------------------------------------------------------------------
# Behavior → valid model names  (canonical vanilla pairings)
# ---------------------------------------------------------------------------
# Source: sm64 decomp script.c files and level_commands.py OBJECT placements.

BEHAVIOR_TO_MODELS: Dict[str, FrozenSet[str]] = {
    # --- Coins ---
    "bhvYellowCoin": frozenset({"MODEL_YELLOW_COIN", "MODEL_YELLOW_COIN_NO_SHADOW"}),
    "bhvRedCoin": frozenset({"MODEL_RED_COIN", "MODEL_RED_COIN_NO_SHADOW"}),
    "bhvBlueCoinSwitch": frozenset({"MODEL_BLUE_COIN_SWITCH"}),
    "bhvBlueCoinJumping": frozenset({"MODEL_BLUE_COIN", "MODEL_BLUE_COIN_NO_SHADOW"}),
    "bhvBlueCoinSliding": frozenset({"MODEL_BLUE_COIN", "MODEL_BLUE_COIN_NO_SHADOW"}),
    "bhvHiddenBlueCoin": frozenset({"MODEL_BLUE_COIN", "MODEL_BLUE_COIN_NO_SHADOW"}),
    "bhvCoinFormation": frozenset({"MODEL_NONE", "MODEL_YELLOW_COIN"}),
    "bhvCoinInsideBoo": frozenset({"MODEL_BLUE_COIN", "MODEL_BLUE_COIN_NO_SHADOW"}),
    # --- Stars ---
    "bhvStar": frozenset({"MODEL_STAR", "MODEL_TRANSPARENT_STAR"}),
    "bhvHiddenStar": frozenset({"MODEL_STAR", "MODEL_TRANSPARENT_STAR"}),
    "bhvHiddenRedCoinStar": frozenset({"MODEL_STAR", "MODEL_TRANSPARENT_STAR"}),
    "bhvBowserCourseRedCoinStar": frozenset({"MODEL_STAR", "MODEL_TRANSPARENT_STAR"}),
    "bhvGrandStar": frozenset({"MODEL_STAR"}),
    "bhvCelebrationStar": frozenset({"MODEL_STAR"}),
    "bhvStarSpawnCoordinates": frozenset({"MODEL_STAR", "MODEL_TRANSPARENT_STAR"}),
    "bhvCCMTouchedStarSpawn": frozenset({"MODEL_STAR", "MODEL_TRANSPARENT_STAR"}),
    # --- Enemies: common ---
    "bhvGoomba": frozenset({"MODEL_GOOMBA"}),
    "bhvGoombaTripletSpawner": frozenset({"MODEL_GOOMBA"}),
    "bhvBobomb": frozenset({"MODEL_BLACK_BOBOMB"}),
    "bhvBobombBuddy": frozenset({"MODEL_BOBOMB_BUDDY"}),
    "bhvBobombBuddyOpensCannon": frozenset({"MODEL_BOBOMB_BUDDY"}),
    "bhvKoopa": frozenset({"MODEL_KOOPA_WITH_SHELL", "MODEL_KOOPA_WITHOUT_SHELL"}),
    "bhvKoopaShell": frozenset({"MODEL_KOOPA_SHELL"}),
    "bhvChainChomp": frozenset({"MODEL_CHAIN_CHOMP"}),
    "bhvChainChompGate": frozenset({"MODEL_BOB_CHAIN_CHOMP_GATE"}),
    "bhvBulletBill": frozenset({"MODEL_BULLET_BILL"}),
    "bhvBulletBillCannon": frozenset({"MODEL_NONE"}),
    "bhvSpindrift": frozenset({"MODEL_SPINDRIFT"}),
    "bhvAmp": frozenset({"MODEL_AMP"}),
    "bhvCirclingAmp": frozenset({"MODEL_AMP"}),
    "bhvHomingAmp": frozenset({"MODEL_AMP"}),
    "bhvFlyGuy": frozenset({"MODEL_FLYGUY"}),
    "bhvSnufit": frozenset({"MODEL_SNUFIT"}),
    "bhvScuttlebug": frozenset({"MODEL_SCUTTLEBUG"}),
    "bhvSwoop": frozenset({"MODEL_SWOOP"}),
    "bhvMrI": frozenset({"MODEL_MR_I"}),
    "bhvMoneybag": frozenset({"MODEL_MONEYBAG"}),
    "bhvSpiny": frozenset({"MODEL_SPINY", "MODEL_SPINY_BALL"}),
    "bhvEnemyLakitu": frozenset({"MODEL_ENEMY_LAKITU"}),
    "bhvPiranhaPlant": frozenset({"MODEL_PIRANHA_PLANT"}),
    "bhvFirePiranhaPlant": frozenset({"MODEL_PIRANHA_PLANT"}),
    # --- Enemies: bosses ---
    "bhvKingBobomb": frozenset({"MODEL_KING_BOBOMB"}),
    "bhvBigBully": frozenset({"MODEL_BULLY"}),
    "bhvBigBullyWithMinions": frozenset({"MODEL_BULLY_BOSS"}),
    "bhvBigChillBully": frozenset({"MODEL_BIG_CHILL_BULLY"}),
    "bhvBowser": frozenset({"MODEL_BOWSER"}),
    "bhvEyerokBoss": frozenset({"MODEL_NONE"}),
    "bhvEyerokHand": frozenset({"MODEL_EYEROK_LEFT_HAND", "MODEL_EYEROK_RIGHT_HAND"}),
    "bhvWiggler": frozenset({"MODEL_WIGGLER_HEAD", "MODEL_WIGGLER_BODY"}),
    "bhvChuckya": frozenset({"MODEL_CHUCKYA"}),
    "bhvHeaveHo": frozenset({"MODEL_HEAVE_HO"}),
    "bhvKlepto": frozenset({"MODEL_KLEPTO"}),
    # --- Enemies: water ---
    "bhvBub": frozenset({"MODEL_BUB"}),
    "bhvSushi": frozenset({"MODEL_SUSHI"}),
    "bhvUnagi": frozenset({"MODEL_UNAGI"}),
    "bhvBubba": frozenset({"MODEL_BUBBA"}),
    "bhvClamShell": frozenset({"MODEL_CLAM_SHELL"}),
    "bhvSkeeter": frozenset({"MODEL_SKEETER"}),
    # --- Enemies: BBH ---
    "bhvBoo": frozenset({"MODEL_BOO"}),
    "bhvBooInCastle": frozenset({"MODEL_BOO_CASTLE"}),
    "bhvGhostHuntBoo": frozenset({"MODEL_BOO"}),
    "bhvGhostHuntBigBoo": frozenset({"MODEL_BOO"}),
    "bhvBalconyBigBoo": frozenset({"MODEL_BOO"}),
    "bhvBooWithCage": frozenset({"MODEL_BOO"}),
    "bhvMadPiano": frozenset({"MODEL_MAD_PIANO"}),
    "bhvHauntedChair": frozenset({"MODEL_HAUNTED_CHAIR"}),
    "bhvFlyingBookend": frozenset({"MODEL_BOOKEND", "MODEL_BOOKEND_PART"}),
    "bhvBookendSpawn": frozenset({"MODEL_BOOKEND", "MODEL_BOOKEND_PART"}),
    # --- Enemies: desert ---
    "bhvPokey": frozenset({"MODEL_POKEY_HEAD", "MODEL_POKEY_BODY_PART"}),
    "bhvTweester": frozenset({"MODEL_TWEESTER"}),
    "bhvGrindel": frozenset({"MODEL_SSL_GRINDEL"}),
    "bhvSpindel": frozenset({"MODEL_SSL_SPINDEL"}),
    "bhvToxBox": frozenset({"MODEL_SSL_TOX_BOX"}),
    # --- Enemies: snow ---
    "bhvMrBlizzard": frozenset({"MODEL_MR_BLIZZARD"}),
    "bhvBigSnowmanWhole": frozenset({"MODEL_CCM_SNOWMAN_HEAD"}),
    "bhvPenguin": frozenset({"MODEL_PENGUIN"}),
    "bhvMontyMole": frozenset({"MODEL_MONTY_MOLE"}),
    "bhvFwoosh": frozenset({"MODEL_FWOOSH"}),
    # --- NPCs ---
    "bhvToad": frozenset({"MODEL_TOAD"}),
    "bhvMips": frozenset({"MODEL_MIPS"}),
    "bhvYoshi": frozenset({"MODEL_YOSHI"}),
    "bhvHoot": frozenset({"MODEL_HOOT"}),
    "bhvDorrie": frozenset({"MODEL_DORRIE"}),
    "bhvUkiki": frozenset({"MODEL_UKIKI"}),
    # --- Items / Collectibles ---
    "bhv1Up": frozenset({"MODEL_1UP"}),
    "bhv1UpWalking": frozenset({"MODEL_1UP"}),
    "bhv1UpRunningAway": frozenset({"MODEL_1UP"}),
    "bhv1UpJumpOnApproach": frozenset({"MODEL_1UP"}),
    "bhv1UpSliding": frozenset({"MODEL_1UP"}),
    "bhvHidden1Up": frozenset({"MODEL_1UP"}),
    "bhvBowserKey": frozenset({"MODEL_BOWSER_KEY", "MODEL_BOWSER_KEY_CUTSCENE"}),
    "bhvExclamationBox": frozenset({"MODEL_EXCLAMATION_BOX"}),
    "bhvBreakableBox": frozenset({"MODEL_BREAKABLE_BOX"}),
    "bhvBreakableBoxSmall": frozenset({"MODEL_BREAKABLE_BOX_SMALL"}),
    "bhvMetalBox": frozenset({"MODEL_METAL_BOX"}),
    "bhvHeart": frozenset({"MODEL_HEART"}),
    # --- Caps ---
    "bhvCapSwitch": frozenset({"MODEL_CAP_SWITCH"}),
    "bhvCapSwitchBase": frozenset({"MODEL_CAP_SWITCH_BASE"}),
    # --- Interactive objects ---
    "bhvCannon": frozenset({"MODEL_NONE"}),
    "bhvCannonClosed": frozenset({"MODEL_DL_CANNON_LID"}),
    "bhvPurpleSwitch": frozenset({"MODEL_PURPLE_SWITCH"}),
    "bhvFloorSwitch": frozenset({"MODEL_PURPLE_SWITCH"}),
    "bhvSignpost": frozenset({"MODEL_WOODEN_SIGNPOST"}),
    "bhvWoodenPost": frozenset({"MODEL_WOODEN_POST"}),
    "bhvCheckerboardPlatformSub": frozenset({"MODEL_CHECKERBOARD_PLATFORM"}),
    # --- Doors ---
    "bhvDoor": frozenset(
        {
            "MODEL_CASTLE_WOODEN_DOOR",
            "MODEL_CASTLE_CASTLE_DOOR",
            "MODEL_CASTLE_METAL_DOOR",
            "MODEL_BBH_HAUNTED_DOOR",
            "MODEL_HMC_WOODEN_DOOR",
            "MODEL_HMC_METAL_DOOR",
            "MODEL_HMC_HAZY_MAZE_DOOR",
            "MODEL_COURTYARD_WOODEN_DOOR",
            "MODEL_CCM_CABIN_DOOR",
        }
    ),
    "bhvDoorWarp": frozenset(
        {
            "MODEL_CASTLE_WOODEN_DOOR",
            "MODEL_CASTLE_CASTLE_DOOR",
            "MODEL_CASTLE_METAL_DOOR",
            "MODEL_CASTLE_GROUNDS_CASTLE_DOOR",
            "MODEL_CASTLE_GROUNDS_METAL_DOOR",
        }
    ),
    "bhvStarDoor": frozenset(
        {
            "MODEL_CASTLE_STAR_DOOR_30_STARS",
            "MODEL_CASTLE_STAR_DOOR_50_STARS",
            "MODEL_CASTLE_STAR_DOOR_8_STARS",
            "MODEL_CASTLE_STAR_DOOR_70_STARS",
            "MODEL_CASTLE_DOOR_0_STARS",
            "MODEL_CASTLE_DOOR_1_STAR",
            "MODEL_CASTLE_DOOR_3_STARS",
            "MODEL_CASTLE_KEY_DOOR",
        }
    ),
    # --- Trees (one behavior, many models) ---
    "bhvTree": frozenset(
        {
            "MODEL_BOB_BUBBLY_TREE",
            "MODEL_CCM_SNOW_TREE",
            "MODEL_SL_SNOW_TREE",
            "MODEL_SSL_PALM_TREE",
            "MODEL_COURTYARD_SPIKY_TREE",
            "MODEL_WDW_BUBBLY_TREE",
            "MODEL_CASTLE_GROUNDS_BUBBLY_TREE",
            "MODEL_WF_BUBBLY_TREE",
            "MODEL_THI_BUBBLY_TREE",
            "MODEL_UNKNOWN_TREE_1A",
        }
    ),
    # --- Misc ---
    "bhvBowlingBall": frozenset({"MODEL_BOWLING_BALL"}),
    "bhvFreeBowlingBall": frozenset({"MODEL_BOWLING_BALL"}),
    "bhvBoBBowlingBallSpawner": frozenset({"MODEL_NONE"}),
    "bhvBowserBomb": frozenset({"MODEL_BOWSER_BOMB"}),
    "bhvWaterMine": frozenset({"MODEL_WATER_MINE"}),
    "bhvKoopaFlag": frozenset({"MODEL_KOOPA_FLAG"}),
    "bhvCastleFlagWaving": frozenset({"MODEL_CASTLE_GROUNDS_FLAG"}),
    "bhvThwomp": frozenset({"MODEL_THWOMP"}),
    "bhvFallingBowserPlatform": frozenset(
        {
            "MODEL_BOWSER_3_FALLING_PLATFORM_1",
            "MODEL_BOWSER_3_FALLING_PLATFORM_2",
            "MODEL_BOWSER_3_FALLING_PLATFORM_3",
            "MODEL_BOWSER_3_FALLING_PLATFORM_4",
            "MODEL_BOWSER_3_FALLING_PLATFORM_5",
            "MODEL_BOWSER_3_FALLING_PLATFORM_6",
            "MODEL_BOWSER_3_FALLING_PLATFORM_7",
            "MODEL_BOWSER_3_FALLING_PLATFORM_8",
            "MODEL_BOWSER_3_FALLING_PLATFORM_9",
            "MODEL_BOWSER_3_FALLING_PLATFORM_10",
        }
    ),
    # --- Warps ---
    "bhvFadingWarp": frozenset({"MODEL_NONE"}),
    "bhvWarp": frozenset({"MODEL_NONE"}),
    "bhvDDDWarp": frozenset({"MODEL_NONE"}),
    "bhvDeathWarp": frozenset({"MODEL_NONE"}),
    "bhvFlyingWarp": frozenset({"MODEL_NONE"}),
    "bhvAirborneWarp": frozenset({"MODEL_NONE"}),
    "bhvAirborneDeathWarp": frozenset({"MODEL_NONE"}),
    "bhvAirborneStarCollectWarp": frozenset({"MODEL_NONE"}),
    "bhvExitPodiumWarp": frozenset({"MODEL_NONE"}),
}


# ---------------------------------------------------------------------------
# Reverse index: model name → set of valid behavior names
# ---------------------------------------------------------------------------

MODEL_TO_BEHAVIORS: Dict[str, Set[str]] = {}

for _beh_name, _model_set in BEHAVIOR_TO_MODELS.items():
    for _model_name in _model_set:
        MODEL_TO_BEHAVIORS.setdefault(_model_name, set()).add(_beh_name)
