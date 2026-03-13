import os
import sys
import re
from utils import level_name_to_int_lookup
from io import BytesIO
import threading


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for stream in self.streams:
            stream.write(data)

    def flush(self):
        for stream in self.streams:
            stream.flush()


AREA_REGEX = re.compile(r"area_(\d+)")


class OutputManager:
    def __init__(self, base_path, internal_name):
        self.base_path = base_path

        # Create a log file for the console output
        self.console_log_path = os.path.join(base_path, "console.log")
        self.console_log_file = open(self.console_log_path, "w", buffering=1)
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr

        # Redirect both stdout and stderr to both terminal and log file
        sys.stdout = Tee(self.original_stdout, self.console_log_file)
        sys.stderr = Tee(self.original_stderr, self.console_log_file)

        self.raw_log_path = os.path.join(base_path, "raw.log")
        self.raw_log_file = open(self.raw_log_path, "w")

        self.lua_file = open(os.path.join(base_path, "main.lua"), "w")
        self.lua_file.write(
            f"-- name: {internal_name}\n-- description: Extracted with rom-decomp-64.\n-- incompatible: romhack\n"
        )
        self.lua_file.close()

        self.current_file = None
        self.current_file_path = None
        self._file_cache = {}
        self.files = {}

        # Avoid truncating main.lua
        self.files[os.path.join(base_path, "main.lua")] = True

        self.lock = threading.Lock()
        self._futures = []

        self._created_dirs = set()

        # Make sure output directories exist
        self.levels_dir = os.path.join(base_path, "levels")
        self.misc_dir = os.path.join(base_path, "misc")
        self.textures_dir = os.path.join(base_path, "textures")
        self._ensure_dir(self.levels_dir)
        self._ensure_dir(self.misc_dir)
        self._ensure_dir(self.textures_dir)

    def register_future(self, future):
        # Track async tasks so close() can wait for completion.
        with self.lock:
            self._futures.append(future)

    def _ensure_dir(self, directory):
        if directory in self._created_dirs:
            return
        if not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        self._created_dirs.add(directory)

    def _get_file_handle(self, filepath):
        if filepath in self._file_cache:
            return self._file_cache[filepath]

        # Close the oldest opened file if the cache gets too large.
        if len(self._file_cache) >= 256:
            oldest_path = next(iter(self._file_cache))
            self._file_cache.pop(oldest_path).close()

        # Ensure directory exists
        self._ensure_dir(os.path.dirname(filepath))

        # If it's a new file (not in self.files), use 'wb' to truncate
        mode = "ab"
        if filepath not in self.files:
            mode = "wb"
            self.files[filepath] = True

        f = open(filepath, mode)
        self._file_cache[filepath] = f
        return f

    def write(self, ctx, type, context, content):
        with self.lock:
            if context is None:
                filename = "misc.c.txt"
                context = "misc.c.txt"
            elif "dl" in context or "vertex" in context or "light" in context:
                filename = "model.inc.c"
            elif "geo" in context:
                filename = "geo.inc.c"
            elif "trajectory" in context:
                filename = "trajectory.inc.c"
            elif "collision" in context:
                filename = "collision.inc.c"
            elif "macro" in context:
                filename = "macro.inc.c"
            elif "script" in context or ("level_" in context and "_entry" in context):
                filename = "script.c"
            elif "room" in context:
                filename = "room.inc.c"
            elif "texture" in context or "segment2" in context or "font_graphics" in context:
                filename = f"{context}.png"
            elif "tiles_c" in context:
                filename = "texture.inc.c"
            else:
                filename = "misc.c.txt"

            # Determine path based on level name
            target_dir = self.misc_dir
            found_level = False

            # Optimization: check current level from ctx first
            from utils import level_num_to_str

            if ctx.curr_level != -1:
                level = level_num_to_str.get(ctx.curr_level)
                if level and (
                    context.startswith(level + "_") or context == level or f"_{level}_" in context
                ):
                    level_dir = os.path.join(self.levels_dir, level)
                    area_index = ctx.curr_area
                    if area_index == -1:
                        # Fallback to regex if ctx doesn't have area yet
                        m = AREA_REGEX.search(context)
                        if m:
                            area_index = int(m.group(1))

                    if area_index != -1:
                        target_dir = os.path.join(level_dir, "areas", str(area_index))
                    else:
                        target_dir = level_dir
                    found_level = True

            if not found_level:
                for level in level_name_to_int_lookup:
                    if (
                        context.startswith(level + "_")
                        or context == level
                        or f"_{level}_" in context
                    ):
                        level_dir = os.path.join(self.levels_dir, level)
                        area_index = -1
                        m = AREA_REGEX.search(context)
                        if m:
                            area_index = int(m.group(1))

                        if area_index != -1:
                            target_dir = os.path.join(level_dir, "areas", str(area_index))
                        else:
                            target_dir = level_dir
                        break

            if "skybox" in context:
                target_dir = os.path.join(self.textures_dir, "skybox_tiles")
            elif (
                "segment2" in context
                or "font_graphics" in context
                or "texture_hud_char" in context
                or "texture_font_char" in context
                or "texture_transition" in context
                or "texture_waterbox" in context
            ):
                target_dir = os.path.join(self.textures_dir, "segment2")

            filepath = os.path.join(target_dir, filename)
            f = self._get_file_handle(filepath)

            if isinstance(content, BytesIO):
                f.write(content.getbuffer())
            elif isinstance(content, (bytes, bytearray, memoryview)):
                f.write(content)
            else:
                self.raw_log_file.write(f"// written to {filepath}\n" + content)
                f.write(content.encode("utf-8"))

    def write_lua(self, content: list[str], file: str):
        with self.lock:
            filepath = os.path.join(self.base_path, file)
            # Lua files are usually written once or appended rarely.
            # For simplicity, we can still use the cache but let's just write directly
            # to avoid mixing logic if they are intended to be completely overwritten.
            with open(filepath, "w") as lua_file:
                lua_file.writelines(content)

    def write_lua_append(self, content: list[str], file: str):
        with self.lock:
            filepath = os.path.join(self.base_path, file)
            f = self._get_file_handle(filepath)
            for line in content:
                f.write(line.encode("utf-8"))

    def create_file(self, rel_path, content=None, mode="w", binary=False):
        with self.lock:
            rel_path = rel_path.lstrip("/\\")
            target_path = os.path.join(self.base_path, rel_path)

            # Respect caller intent for append/write mode.
            file_mode = "ab"
            if "a" in mode:
                file_mode = "ab"
            elif "w" in mode:
                file_mode = "wb"

            self._ensure_dir(os.path.dirname(target_path))

            # Reuse cached handle only when it already matches append behavior.
            # For write/truncate, always reopen to honor truncation semantics.
            if target_path in self._file_cache and file_mode != "ab":
                self._file_cache[target_path].close()
                del self._file_cache[target_path]

            if target_path not in self._file_cache:
                if len(self._file_cache) >= 256:
                    oldest_path = next(iter(self._file_cache))
                    self._file_cache.pop(oldest_path).close()
                self._file_cache[target_path] = open(target_path, file_mode)

            f = self._file_cache[target_path]

            to_write = content
            if binary and isinstance(content, BytesIO):
                to_write = content.getbuffer()

            if to_write is not None:
                if isinstance(to_write, (bytes, bytearray, memoryview)):
                    f.write(to_write)
                else:
                    f.write(str(to_write).encode("utf-8"))

            return target_path

    def close(self):
        # Wait for any registered async tasks to finish before tearing down handles.
        futures = []
        with self.lock:
            futures = list(self._futures)
        for f in futures:
            try:
                f.result()
            except Exception:
                pass

        with self.lock:
            # Restore original stdout and stderr before closing
            if hasattr(self, "original_stdout"):
                sys.stdout = self.original_stdout
            if hasattr(self, "original_stderr"):
                sys.stderr = self.original_stderr

            if self.console_log_file:
                self.console_log_file.close()
            if self.raw_log_file:
                self.raw_log_file.close()
            if self.lua_file:
                self.lua_file.close()

            # Close all cached files
            for f in self._file_cache.values():
                f.close()
            self._file_cache.clear()
