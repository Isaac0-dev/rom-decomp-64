console.log('[Worker] Worker script loaded!');

// Import Pyodide using dynamic import
const { loadPyodide } = await import("https://cdn.jsdelivr.net/pyodide/v0.26.0/full/pyodide.mjs");

let pyodide;
let romBuffer;
let emulator;

const pythonFiles = [
    'browser_bridge.py',
    'extract.py', 'pipeline.py', 'utils.py', 'context.py', 'rom_database.py', 
    'segment.py', 'texture.py', 'geo_layout.py', 'display_list.py', 
    'level_script.py', 'level_commands.py', 'collision.py', 'audio.py', 
    'disassemble_sound.py', 'aifc_decode.py', 'behavior.py', 
    'behavior_hashes.py', 'model_ids.py', 'mop.py', 'movtex.py', 
    'rooms.py', 'scroll_targets.py', 'trajectory.py', 'vertices.py', 
    'lights.py', 'constants.py', 'byteio.py', 'binary_to_png.py', 
    'gbi_defines.py', 'db_passes.py', 'deferred_output.py', 
    'optimization_passes.py', 'output_manager.py', 'serialization_helpers.py', 
    'vanilla_matcher.py', 'dynos_builtins.py', 'address_map.py', 
    'address_map_typed.py', 'script_definitions.py', 'n64_host.py', 'bps.py', 
    'base_processor.py', 'lua_modules.py', 'sm64.us.map', 'gen_anon_hashes.py', 
    'macro_objects.py', 'segment2_extractor.py', 'text_export.py',
    'microcode/base.py', 'microcode/gbi0.py', 'microcode/gbi1.py', 'microcode/gbi2.py', 'microcode/gbi0_dkr.py', 'microcode/__init__.py',
    'compression_util/__init__.py', 'compression_util/compression.py', 'compression_util/rnc.py',
    'function_matching/extractor.py', 'function_matching/generator.py', 'function_matching/matcher.py', 'function_matching/mips_utils.py',
    'data/expected_pairings.py', 'data/__init__.py',
    'tools/generate_behavior_hashes.py', 'tools/gen_traj_hashes.py', 'tools/gen_vanilla_database.py'
];

const dataFiles = [
    'data/vanilla_display_lists.json', 'data/vanilla_geos.json',
    'function_matching/vanilla_functions_db.json.gz'
];

// Define base URL dynamically to support local development and GitHub Pages
const pathParts = self.location.pathname.split('/');
const baseUrl = self.location.origin + (pathParts.length > 2 && pathParts[1] === 'rom-decomp-64' ? '/rom-decomp-64/' : '/');
console.log('[Worker] Base URL:', baseUrl);

async function init() {
    console.log('[Worker] Entering init()...');
    try {
        const module = await import(baseUrl + 'n64js_browser_wrapper.js');
        emulator = new module.N64JSHeadless();
        console.log('[Worker] Emulator module imported.');

    pyodide = await loadPyodide({
        // Prevent fatal error on exit(0)
        _pyodide_module: {
            noExitRuntime: true,
            onExit: () => console.log("Emulator exit handled.")
        }
    });
    console.log('[Worker] Pyodide loaded.');
        self.postMessage({ type: 'status', data: 'Loading packages...' });
        
        await pyodide.loadPackage('micropip');
        const micropip = pyodide.pyimport("micropip");
        await pyodide.loadPackage(['Pillow']);
        await micropip.install(['pypng']);
        
        self.postMessage({ type: 'status', data: 'Fetching source files...' });
        const cacheBuster = '?v=' + Date.now();
        for (const file of pythonFiles) {
            const dir = file.includes('/') ? file.substring(0, file.lastIndexOf('/')) : '';
            if (dir) pyodide.FS.mkdirTree('/' + dir);
            const resp = await fetch(baseUrl + file + cacheBuster);
            const text = await resp.text();
            pyodide.FS.writeFile('/' + file, text);
        }

        for (const file of dataFiles) {
            const dir = file.substring(0, file.lastIndexOf('/'));
            if (dir) pyodide.FS.mkdirTree('/' + dir);
            const resp = await fetch(baseUrl + file + cacheBuster);
            const buffer = await resp.arrayBuffer();
            pyodide.FS.writeFile('/' + file, new Uint8Array(buffer));
        }

        self.postMessage({ type: 'ready' });
        console.log('[Worker] Initialization complete.');
    } catch (err) {
        console.error('[Worker] Error during init:', err);
        self.postMessage({ type: 'error', data: err.message });
    }
}

self.onmessage = async (e) => {
    console.log('[Worker] Received message:', e.data);
    const { type, data } = e.data;
    
    if (type === 'init') {
        console.log('[Worker] Initializing...');
        await init();
    } else if (type === 'start') {
        romBuffer = data;
        await startExtraction();
    }
};

async function startExtraction() {
    self.postMessage({ type: 'log', data: 'Starting extraction in worker...' });

    pyodide.FS.writeFile('/input.z64', romBuffer);
    try { pyodide.FS.mkdir('/out'); } catch(e) {}

    // Setup bridge hooks
    self.initNativeEmulator = (romBytes, compressionType, romName) => {
        console.log('[N64JS] Initializing Native Headless Emulator...');
        emulator.init(romBytes.toJs(), compressionType, romName);
    };
    
    self.stepNativeEmulator = (cycles) => {
        return JSON.stringify(emulator.step(cycles));
    };

    pyodide.globals.set("js_log", (msg) => self.postMessage({ type: 'log', data: msg }));
    pyodide.globals.set("js_update_status", (component, state) => {
        self.postMessage({ type: 'status-update', component, state });
    });

    const pyCode = `
import sys
import io
import os
import zipfile
import asyncio

if '/' not in sys.path:
    sys.path.append('/')

os.chdir('/')

import browser_bridge
browser_bridge.patch_system()

import extract

class Logger:
    def write(self, data):
        if data.strip():
            if data.startswith("STATUS|"):
                parts = data.strip().split("|")
                if len(parts) >= 3:
                    js_update_status(parts[1], parts[2])
            js_log(data.strip())
    def flush(self): pass

sys.stdout = Logger()
sys.stderr = Logger()

async def run_extraction():
    try:
        js_log("Running main extraction pipeline...")
        extract.main(filename_override='/input.z64', output_status_override=True)
        js_log("Main extraction pipeline finished.")
        
        # Determine the actual output directory
        out_root = '/out'
        rom_dirs = [d for d in os.listdir(out_root) if os.path.isdir(os.path.join(out_root, d))]
        
        target_dir = os.path.join(out_root, rom_dirs[0]) if rom_dirs else out_root
        js_log(f"Zipping results from: {target_dir}")

        memory_zip = io.BytesIO()
        with zipfile.ZipFile(memory_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(target_dir):
                for file in files:
                    abs_path = os.path.join(root, file)
                    rel_path = os.path.relpath(abs_path, target_dir)
                    zf.write(abs_path, rel_path)
        
        memory_zip.seek(0)
        return memory_zip.getvalue()
    except Exception as e:
        import traceback
        js_log(traceback.format_exc())
        return None

# Execute
result = await run_extraction()
result
`;
    try {
        const result = await pyodide.runPythonAsync(pyCode);
        if (result) {
            const data = result.toJs();
            result.destroy();
            self.postMessage({ type: 'complete', data: data }, [data.buffer]);
        }
    } catch (err) {
        // Pyodide throws an 'Exit' error even on exit(0)
        if (err.toString().includes("Exit:")) {
            self.postMessage({ type: 'log', data: 'Extraction finished.' });
            // In case the zip was generated in the last run (pipeline might have returned it before exit)
            // But runPythonAsync will not return a value if the process exited.
            // We need the Python code to have finished its work.
        } else {
            self.postMessage({ type: 'log', data: 'Python Error: ' + err.message });
        }
    }
}
