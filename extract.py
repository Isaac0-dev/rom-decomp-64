import argparse
import os
import sys
import atexit
import re
import zipfile
import bps

# Optional: requests for downloading hacks
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
    p.add_argument("-v", "--verbose", action="count", default=0, help="Increase output verbosity")
    p.add_argument("filename", nargs="?", default="baserom.us.z64")
    return p.parse_args(argv)


def main(filename_override=None, output_status_override=None, called_by_main_override=None):
    from pipeline import ExtractionPipeline

    global _status_enabled, _current_filename, args
    ctx.reached_end = False

    filename = filename_override or (args.filename if args else "baserom.us.z64")

    if filename.startswith("http://") or filename.startswith("https://"):
        patched_rom = download_and_patch(filename)
        assert patched_rom is not None, "Failed to download and patch ROM"
        filename = patched_rom

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
    )

    exit_code = pipeline.run()

    # Success if the pipeline completes without exception
    ctx.reached_end = True

    if called_by_main:
        sys.exit(0 if exit_code == 0 else 1)


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

    search_queries = [slug, slug.replace("-", " ")]
    if "-" in slug:
        search_queries.extend(slug.split("-"))

    selected_hack = None
    seen_queries = set()
    for query in search_queries:
        if not query or len(query) < 3 or query in seen_queries:
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
                if h.get("urlTitle") == slug:
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
            download_url = "https://api.romhacking.com/" + latest_version["download"]["directHref"]

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
        with zipfile.ZipFile(dl_path, "r") as zip_ref:
            zip_ref.extractall(DOWNLOAD_FOLDER)
            for name in zip_ref.namelist():
                if name.lower().endswith(".bps"):
                    patch_path = os.path.join(DOWNLOAD_FOLDER, name)
                elif name.lower().endswith((".z64", ".n64", ".v64")):
                    final_rom_path = os.path.join(DOWNLOAD_FOLDER, name)
    else:
        patch_path = dl_path

    if patch_path and not final_rom_path:
        vanilla_data = get_vanilla_sm64_rom()
        if vanilla_data is None:
            debug_fail("Error: Could not find a vanilla SM64 (US) base ROM for patching.")
            return None

        from utils import vanilla_rom_path as base_rom_path

        output_rom = f"{slug}.z64"
        debug_print(f"Patching {base_rom_path} with {patch_path} -> {output_rom}")

        try:
            assert base_rom_path is not None
            bps.apply_patch(patch_path, base_rom_path, output_rom)
            final_rom_path = output_rom
            debug_print(f"Successfully patched ROM: {output_rom}")
        except Exception as e:
            debug_fail(f"Error applying patch: {e}")
            return None

    return final_rom_path


def _cleanup_on_exit():
    if not ctx.reached_end:
        print(f"Failed to extract rom '{_current_filename or 'unknown'}'")


atexit.register(_cleanup_on_exit)

if __name__ == "__main__":
    args = parse_args()
    _status_enabled = bool(args.output_status)
    main()
