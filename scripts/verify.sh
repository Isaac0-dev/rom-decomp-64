#!/bin/bash
# Take the input parameter as a path to a directory containing the mod files for an sm64coopdx mod.
# Then, run /run/media/isaacb/BAC01E20C01DE403/sm64coopdx/developer/mod_verifier/mod_verifier <input_path>

if [ -z "$1" ]; then
    echo "Usage: $0 <mod_directory_path>"
    exit 1
fi

MOD_PATH="$1"

if [ ! -d "$MOD_PATH" ]; then
    echo "Error: Directory not found: $MOD_PATH"
    exit 1
fi


# VERIFIER="/run/media/isaacb/BAC01E20C01DE403/sm64coopdx/developer/mod_verifier/mod_verifier"
VERIFIER="/run/media/isaacb/BAC01E20C01DE403/sm64coopdx/build/us_pc/sm64coopdx"

# if [ ! -x "$VERIFIER" ]; then
#     echo "Error: mod_verifier not found or not executable at $VERIFIER"
#     exit 1
# fi

echo "Verifying mod at: $MOD_PATH"
rm -r /home/isaacb/.local/share/sm64ex-coop/mods/012.sm64decade
mkdir /home/isaacb/.local/share/sm64ex-coop/mods/012.sm64decade
echo cp -r "$MOD_PATH"/* /home/isaacb/.local/share/sm64ex-coop/mods/012.sm64decade/
cp -r "$MOD_PATH"/* /home/isaacb/.local/share/sm64ex-coop/mods/012.sm64decade/
cd /run/media/isaacb/BAC01E20C01DE403/sm64coopdx/build/us_pc
./sm64coopdx
