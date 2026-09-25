import argparse
import os
import sys
import atexit
import re
import zipfile
import bps

# Optional for downloading hacks
from urllib.parse import urljoin
from typing import Any as _Any, cast as _cast

try:
    import importlib

    requests_typed: _Any = importlib.import_module("requests")
except ImportError:
    requests_typed = _cast(_Any, None)

from utils import (
    CMD_BBH_pack,
    CMD_PTR_pack,
    debug_fail,
    debug_print,
    pack_to_bytes,
    get_vanilla_sm64_rom,
    set_log_level,
)

from context import ctx


def set_reached_end():
    ctx.reached_end = True


def INIT_LEVEL():
    return pack_to_bytes(CMD_BBH_pack(0x1B, 0x04, 0x0000))


def SLEEP(frames):
    return pack_to_bytes(CMD_BBH_pack(0x03, 0x04, frames))


def BLACKOUT(enabled):
    val = 0x0001 if enabled else 0x0000
    return pack_to_bytes(CMD_BBH_pack(0x34, 0x04, val))


def JUMP(addr):
    header = pack_to_bytes(CMD_BBH_pack(0x05, 0x08, 0x0000))
    address = pack_to_bytes(CMD_PTR_pack(addr))
    return header, address


STATUS_PREFIX = "STATUS|"
_status_enabled = False
args = None
_current_filename = None
last_output_dir = None

DOWNLOAD_FOLDER = "downloads"


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Extract ROM contents")
    p.add_argument(
        "--called-by-main",
        dest="called_by_main",
        action="store_true",
        help="Whether to return a status on exit or not.",
    )
    p.add_argument(
        "--status",
        dest="output_status",
        action="store_true",
        default=False,
        help="Emit machine-readable status lines for the GUI.",
    )
    p.add_argument(
        "--host",
        dest="host",
        choices=["bun", "node", "python", "auto"],
        default="auto",
        help="Emulation host to use (bun, node, or python).",
    )
    p.add_argument(
        "--aiff",
        dest="aiff_extraction",
        action="store_true",
        help="Whether to extract .aiff files of audio from the ROM.",
    )
    p.add_argument("-v", "--verbose", action="count", default=0, help="Increase output verbosity")
    p.add_argument(
        "filename",
        nargs="?",
        default="baserom.us.z64",
        help="ROM (.z64/.n64/.v64), BPS patch, ZIP, or romhacking.com URL",
    )
    return p.parse_args(argv)


def main(filename_override=None, output_status_override=None, called_by_main_override=None):
    from pipeline import ExtractionPipeline

    global _status_enabled, _current_filename, args, last_output_dir
    ctx.reached_end = False

    if args:
        set_log_level(args.verbose)

    filename = filename_override or (args.filename if args else "baserom.us.z64")

    resolved = resolve_rom_input(filename)
    if resolved is None:
        debug_fail(f"Failed to resolve ROM / patch input: '{filename}'")
        return 1
    filename = resolved

    called_by_main = (
        called_by_main_override
        if called_by_main_override is not None
        else (args.called_by_main if args else False)
    )
    status_flag = (
        output_status_override
        if output_status_override is not None
        else (args.output_status if args else False)
    )
    _status_enabled = bool(status_flag)
    _current_filename = filename

    # Initialize and run the Pipeline
    pipeline = ExtractionPipeline(
        rom_path=filename,
        output_status=_status_enabled,
        called_by_main=called_by_main,
        host=args.host if args else "auto",
        args=args,
    )

    exit_code = pipeline.run()
    last_output_dir = pipeline.output_dir

    """ vvvv code for development purposes vvvv """
    from n64_host import IS_BROWSER

    if not IS_BROWSER and sys.platform.startswith("linux"):
        executed_dir = os.getcwd()
        rom_name = os.path.basename(filename)
        git_tracking_dir = os.path.join(executed_dir, "git_tracking", rom_name)
        if os.path.exists(git_tracking_dir):
            sync_git_sh = os.path.join(executed_dir, "sync_git.sh")
            if os.path.exists(sync_git_sh):
                os.system(f'bash {sync_git_sh} "{rom_name}"')

        print("Copying to sm64ex-coop mods folder...")
        import shutil

        target_mods_path = os.path.expanduser("~/.local/share/sm64ex-coop/mods/012.sm64decade")
        source_path = pipeline.output_dir
        shutil.rmtree(target_mods_path, ignore_errors=True)
        shutil.copytree(source_path, target_mods_path)
    """ ^^^^ code for development purposes ^^^^ """

    # Success if the pipeline completes without exception
    ctx.reached_end = True

    if called_by_main:
        sys.exit(0 if exit_code == 100 else 1)

    return exit_code


def apply_bps_to_vanilla(patch_path, output_rom):
    """Apply a local BPS patch onto the vanilla SM64 US ROM.

    Reuses ``output_rom`` when it already matches the patch's target CRC32.
    """
    import binascii
    import utils as utils_mod

    try:
        with open(patch_path, "rb") as f:
            patcher = bps.BPSPatch(f.read())
    except Exception as e:
        debug_fail(f"Error: Invalid BPS patch '{patch_path}': {e}")
        return None

    if os.path.isfile(output_rom):
        try:
            with open(output_rom, "rb") as f:
                existing = f.read()
            existing_crc = binascii.crc32(existing) & 0xFFFFFFFF
            if existing_crc == patcher.target_checksum:
                print(f"Reusing existing patched ROM: {output_rom}")
                return output_rom
        except OSError:
            pass

    # get_vanilla_sm64_rom() caches the ROM bytes and sets
    # utils.vanilla_rom_path as a side effect; only the path is needed below.
    if get_vanilla_sm64_rom() is None:
        debug_fail("Error: Could not find a vanilla SM64 (US) base ROM for patching.")
        return None

    base_rom_path = utils_mod.vanilla_rom_path
    if not base_rom_path:
        debug_fail("Error: vanilla ROM path unknown after locating base ROM.")
        return None
    print(f"Patching {base_rom_path} with {patch_path} -> {output_rom}")
    try:
        bps.apply_patch(patch_path, base_rom_path, output_rom)
        print(f"Successfully patched ROM: {output_rom}")
        return output_rom
    except Exception as e:
        debug_fail(f"Error applying patch: {e}")
        return None


def _safe_extract_zip(zip_path, dest_dir):
    """Extract a zip with ZipSlip guard. Returns namelist, or None on failure."""
    try:
        os.makedirs(dest_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            names = zip_ref.namelist()
            base = os.path.realpath(dest_dir)
            for name in names:
                # Directory entries have no file content to guard.
                if name.endswith("/"):
                    continue
                target = os.path.realpath(os.path.join(base, name))
                if target != base and not target.startswith(base + os.sep):
                    debug_fail(f"Error: unsafe zip entry '{name}' in '{zip_path}'")
                    return None
                zip_ref.extract(name, dest_dir)
            return names
    except (zipfile.BadZipFile, OSError) as e:
        debug_fail(f"Error: could not extract zip '{zip_path}': {e}")
        return None


def _pick_zip_contents(dest_dir, names):
    """Pick (patch_path, rom_path) deterministically; first sorted hit wins."""
    bps_hits = sorted(n for n in names if n.lower().endswith(".bps") and not n.endswith("/"))
    rom_hits = sorted(
        n for n in names if n.lower().endswith((".z64", ".n64", ".v64")) and not n.endswith("/")
    )
    if len(bps_hits) > 1:
        debug_print(f"Zip has {len(bps_hits)} BPS files; using '{bps_hits[0]}'")
    if len(rom_hits) > 1:
        debug_print(f"Zip has {len(rom_hits)} ROMs; using '{rom_hits[0]}'")
    patch_path = os.path.join(dest_dir, bps_hits[0]) if bps_hits else None
    final_rom_path = os.path.join(dest_dir, rom_hits[0]) if rom_hits else None
    return patch_path, final_rom_path


def resolve_local_zip(zip_path):
    """Extract a local zip and return a ROM path, applying a BPS if needed."""
    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)

    dest_dir = os.path.join(DOWNLOAD_FOLDER, os.path.splitext(os.path.basename(zip_path))[0])

    debug_print(f"Extracting {zip_path}...")
    names = _safe_extract_zip(zip_path, dest_dir)
    if names is None:
        return None
    patch_path, final_rom_path = _pick_zip_contents(dest_dir, names)

    if patch_path and not final_rom_path:
        output_rom = os.path.splitext(patch_path)[0] + ".z64"
        return apply_bps_to_vanilla(patch_path, output_rom)

    if final_rom_path is None:
        debug_fail(f"Error: zip '{zip_path}' contains no ROM or BPS file.")
    return final_rom_path


def resolve_rom_input(filename):
    """Turn a URL, BPS, ZIP, or ROM path into a usable ROM file path."""
    if filename.startswith("http://") or filename.startswith("https://"):
        return download_and_patch(filename)

    if not os.path.isfile(filename):
        return filename

    lower = filename.lower()
    if lower.endswith(".zip"):
        return resolve_local_zip(filename)
    if lower.endswith(".bps"):
        output_rom = os.path.splitext(filename)[0] + ".z64"
        return apply_bps_to_vanilla(filename, output_rom)
    return filename


def download_and_patch(url):
    if requests_typed is None:
        debug_fail(
            "Error: 'requests' library is not installed. Run 'pip install requests' to use URL downloads."
        )
        return None

    m = re.search(r"romhacking\.com/hack/([^/]+)", url)
    if not m:
        debug_fail(f"Error: Invalid romhacking.com URL: {url}")
        return None

    slug = m.group(1)
    debug_print(f"Detected slug: {slug}")

    output_rom = f"{slug}.z64"
    if os.path.exists(output_rom):
        return output_rom

    search_queries = [slug, slug.replace("-", " ")]

    # Try to get the real title from the page to improve search accuracy
    try:
        page_response = requests_typed.get(url, timeout=10)
        if page_response.status_code == 200:
            title_match = re.search(
                r'<meta property="og:title" content="([^"]+)"', page_response.text
            )
            if title_match:
                real_title = title_match.group(1)
                debug_print(f"Extracted title from page: {real_title}")
                if real_title not in search_queries:
                    search_queries.insert(0, real_title)
    except Exception as e:
        debug_print(f"Warning: Could not fetch page to extract title: {e}")

    if "-" in slug:
        search_queries.extend(slug.split("-"))

    selected_hack = None
    seen_queries = set()
    for query in search_queries:
        if not query or query in seen_queries:
            continue
        seen_queries.add(query)

        debug_print(f"Searching for '{query}'...")
        params = {"search": query, "pageSize": "50"}

        try:
            response = requests_typed.get("https://api.romhacking.com/v4/hacks", params=params)
            response.raise_for_status()
            data = response.json()
            hacks = data if isinstance(data, list) else data.get("results", [])

            if not hacks:
                continue

            for h in hacks:
                url_title = h.get("urlTitle")
                if url_title and url_title.lower() == slug.lower():
                    selected_hack = h
                    break
            if selected_hack:
                break
        except Exception as e:
            debug_fail(f"Error during API search: {e}")
            return None

    if not selected_hack:
        debug_fail(
            f"Error: Could not find hack with slug or title related to '{slug}' on romhacking.com"
        )
        return None

    debug_print(
        f"Found hack: {selected_hack.get('title')} ({selected_hack.get('version', 'unknown')})"
    )

    download_url = None
    if "versions" in selected_hack and selected_hack["versions"]:
        latest_version = selected_hack["versions"][-1]
        if "download" in latest_version and "directHref" in latest_version["download"]:
            download_url = urljoin(
                "https://api.romhacking.com/", latest_version["download"]["directHref"]
            )

    if not download_url:
        debug_fail(f"Error: Could not find a direct download URL for hack '{slug}'")
        return None

    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)

    ext = ".bps"
    if ".zip" in download_url.lower():
        ext = ".zip"
    elif ".bps" in download_url.lower():
        ext = ".bps"

    dl_filename = f"{slug}{ext}"
    dl_path = os.path.join(DOWNLOAD_FOLDER, dl_filename)

    print(f"Downloading ROM from RHDC: {download_url}")
    with requests_typed.get(download_url, stream=True) as r:
        r.raise_for_status()
        with open(dl_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    final_rom_path = None
    patch_path = None

    if dl_path.endswith(".zip"):
        debug_print(f"Extracting {dl_path}...")
        names = _safe_extract_zip(dl_path, DOWNLOAD_FOLDER)
        if names is None:
            return None
        patch_path, final_rom_path = _pick_zip_contents(DOWNLOAD_FOLDER, names)
        if patch_path is None and final_rom_path is None:
            debug_fail(f"Error: zip '{dl_path}' contains no ROM or BPS file.")
            return None
    else:
        patch_path = dl_path

    if patch_path and not final_rom_path:
        final_rom_path = apply_bps_to_vanilla(patch_path, output_rom)

    return final_rom_path


def _cleanup_on_exit():
    if not ctx.reached_end:
        print(f"Failed to extract rom '{_current_filename or 'unknown'}'")


atexit.register(_cleanup_on_exit)

if __name__ == "__main__":
    args = parse_args()
    _status_enabled = bool(args.output_status)
    main()
