import quickjs
import os
import re
import sys
import json
import time
from typing import Dict, Tuple, List


class N64JSHost:
    _transpile_cache: Dict[str, Tuple[str, List[str]]] = {}

    def __init__(self, n64js_root):
        self.root = os.path.abspath(n64js_root)
        self.ctx = quickjs.Context()
        self.modules = {}
        self.found_headers = []
        self.detected_microcode = None
        self.total_cycles = 0
        self.last_microcode_probe_cycle = 0
        self.microcode_probe_interval = 10_000_000
        self.compression_type = "MIO0"
        self.compression_done = False
        self.microcode_done = False
        self._setup_environment()

    def _setup_environment(self):
        self.ctx.add_callable("console_log", self._python_console_log)
        self.ctx.add_callable("header_found", self._header_found)
        self.ctx.add_callable("microcode_found", self._microcode_found)
        self.ctx.add_callable("alseq_found", self._alseq_found)
        # Use Latin-1 for faster binary transfer than Base64
        self.ctx.add_callable(
            "__get_bytes_raw", lambda b: b.decode("latin-1") if isinstance(b, bytes) else b
        )

        self.ctx.eval("""
        var global = globalThis; var window = globalThis; var self = globalThis;
        globalThis.console = {
            log: function() { console_log(Array.prototype.slice.call(arguments).join(' ')); },
            warn: function() { console_log('WARN: ' + Array.prototype.slice.call(arguments).join(' ')); },
            error: function() { console_log('ERROR: ' + Array.prototype.slice.call(arguments).join(' ')); }
        };

        globalThis.atob = (s) => {
            const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
            let str = String(s).replace(/=+$/, '');
            let output = '';
            for (let bc = 0, bs, buffer, idx = 0; buffer = str.charAt(idx++); ~buffer && (bs = bc % 4 ? bs * 64 + buffer : buffer, bc++ % 4) ? output += String.fromCharCode(255 & bs >> (-2 * bc & 6)) : 0) {
                buffer = chars.indexOf(buffer);
            }
            return output;
        };

        globalThis.N64JS_HEADLESS = true;
        globalThis.performance = { now: function() { return Date.now(); } };
        globalThis.navigator = { userAgent: 'headless' };
        globalThis.TextEncoder = class { encode(s) { return new Uint8Array(Array.from(s).map(c => c.charCodeAt(0))); } };

        const stub = new Proxy(function() { return stub; }, { get: (t, p) => p === Symbol.toPrimitive ? (h) => (h === 'number' ? 0 : "") : stub });
        globalThis.$ = stub; globalThis.jQuery = stub; globalThis.AudioContext = stub; globalThis.AudioBuffer = stub;
        globalThis.AudioBufferSourceNode = stub;
        globalThis.document = { getElementById: () => ({ getContext: () => ({ createFramebuffer:()=>({}), bindFramebuffer:()=>{}, createTexture:()=>({}), createRenderbuffer:()=>({}), createShader:()=>({}), createProgram:()=>({}), getUniformLocation:()=>({}), createVertexArray:()=>({}), canvas:{width:640,height:480}, clearColor:()=>{}, clear:()=>{}, viewport:()=>{}, useProgram:()=>{} }), width:640, height:480, style:{} }), createElement: () => ({ getContext: () => ({}) }) };

        var registry = new Map();
        globalThis.__require = (path) => {
            let p = path;
            if(p.substring(0,2)==='./') p=p.substring(2);
            if(p.endsWith('.mjs')) p=p.substring(0,p.length-4)+'.js';
            if(p==='fs/promises') return {readFile:async()=>""};
            if(registry.has(p)) return registry.get(p);
            if(!p.endsWith('.js') && registry.has(p+'.js')) return registry.get(p+'.js');
            const base = p.split('/').pop();
            if(registry.has(base)) return registry.get(base);
            throw new Error("Module not found: " + path);
        };
        globalThis.__registerModule = (path, exports) => { registry.set(path, exports); };

        globalThis.n64js = {
            log: m => console.log(m),
            warn: m => console.log('WARN: ' + m),
            error: m => console.log('ERROR: ' + m),
            halt: m => {
                const s = (new Error()).stack;
                console.log("HALT: " + m + (s ? "\\nStack: " + s : ""));
                throw new Error(m);
            },
            ui: () => ({ displayWarning: m=>console.log('WARN: ' + m), displayError: m=>console.log('ERROR: ' + m), addFolder: ()=>stub, add: ()=>stub }),
            joybus: () => ({ dmaWrite(){}, dmaRead(){}, cpuRead(){}, cpuWrite(){} }),
            onPresent: () => {},
            check: (cond, msg) => { if(!cond) globalThis.n64js.halt(msg); },
            returnControlToSystem: () => {},
            breakEmulationForDisplayListDebug: () => {},
            getLocalStorageItem: () => undefined,
            setLocalStorageItem: () => {}
        };

        globalThis.__n64jsMicrocodeHook = (info) => {
            microcode_found(JSON.stringify(info));
        };
        """)

    def _python_console_log(self, msg):
        try:
            if msg.startswith("[N64JS MICROCODE]") or msg.startswith("[PI DMA]"):
                print(msg, flush=True)
            elif "HALT" in msg or "ERROR" in msg or "Exception" in msg or "WARN" in msg:
                print(f"[JS] {msg}", flush=True)
        except Exception:
            pass

    def _header_found(self, rom_offset, cart_addr):
        self.found_headers.append((rom_offset, cart_addr))
        print(
            f"[PI DMA] found {self.compression_type} header at ROM 0x{rom_offset:08X} cart=0x{cart_addr:08X}",
            flush=True,
        )
        self.compression_done = True
        self._check_exit()

    def _microcode_found(self, info_json):
        info = json.loads(info_json)
        self.detected_microcode = info
        v = info.get("version", "unknown")
        mapped = "F3DEX2"
        if "2.0D" in v:
            mapped = "F3DEX"
        elif "F3DEX " in v:
            mapped = "F3DEX"
        elif "F3D" in v:
            mapped = "F3D"
        print(f'[N64JS MICROCODE] ucode=0 mapped={mapped} version="{v}"', flush=True)
        self.microcode_done = True
        self._check_exit()

    def _check_exit(self):
        if self.compression_done and self.microcode_done:
            print("--- n64js completed tasks, exiting ---", flush=True)
            time.sleep(0.05)
            os._exit(0)

    def _alseq_found(self, rom_offset, rev, sc):
        print(f"[PI DMA] ALSeqFile at ROM 0x{rom_offset:08X}", flush=True)

    def load_module(self, rel_path, is_entry=False):
        rel_path = rel_path.replace("\\", "/").replace("//", "/")
        if rel_path.startswith("./"):
            rel_path = rel_path[2:]

        reg_path = rel_path
        if reg_path.endswith(".mjs"):
            reg_path = reg_path[:-4] + ".js"
        if reg_path in self.modules:
            return

        cache_key = rel_path
        if cache_key in self._transpile_cache:
            wrapper, keys_to_reg = self._transpile_cache[cache_key]
            self.ctx.eval(wrapper)
            for k in keys_to_reg:
                self.modules[k] = True
            return

        abs_path = None
        test_roots = [
            self.root,
            os.path.dirname(self.root),
            os.path.dirname(os.path.dirname(self.root)),
        ]
        for root in test_roots:
            p = os.path.join(root, rel_path)
            if os.path.exists(p) and not os.path.isdir(p):
                abs_path = p
                break
            if os.path.exists(p + ".js"):
                abs_path = p + ".js"
                reg_path = rel_path + ".js"
                break
            if os.path.exists(p + ".mjs"):
                abs_path = p + ".mjs"
                reg_path = rel_path + ".mjs"
                break

        if not abs_path:
            raise FileNotFoundError(f"Module file not found: {rel_path}")

        with open(abs_path, "r", encoding="utf-8") as f:
            code = f.read()

        # Strip underscores from numeric literals
        code = re.sub(r"(\b0x[0-9a-fA-F]+)_([0-9a-fA-F]+\b)", r"\1\2", code)
        code = re.sub(r"(\b\d+)_(\d+\b)", r"\1\2", code)

        # Patch for BigInt | Number compatibility in QuickJS
        if "r4300.js" in rel_path:
            code = code.replace("this.pc | 0", "Number(this.pc) | 0")
            code = code.replace("signedPC = this.pc | 0", "signedPC = Number(this.pc) | 0")
            code = code.replace("=== 0", "== 0")
            code = code.replace("let fragment = lookupFragment(this.pc);", "let fragment = null;")

        if "memaccess.js" in rel_path:
            code = code.replace(
                "const phys = (sAddr + 0x80000000) | 0",
                "const phys = (Number(sAddr) + 0x80000000) | 0",
            )

        if "hle_graphics.js" in rel_path:
            code = "export var gl={FRAMEBUFFER:0,bindFramebuffer(){}}; export var renderer={nativeTransform:{initDimensions(){}},copyBackBufferToFrontBuffer(){},copyPixelsToFrontBuffer(){},newFrame(){},reset(){},debugClear(){}}; export function initialiseRenderer($canvas){}; export function resetRenderer(){}; export function presentBackBuffer(){}; export function hleGraphics(){};"
        elif "dbg_ui.js" in rel_path:
            code = "export const dbgGUI = n64js.ui().addFolder(); export function show(){}; export function hide(){}; export function setVisible(){};"
        elif "hardware.js" in rel_path:
            code = code.replace(
                "arrayBuffer = arrayBuffer.transfer(minLength);",
                "{ const newBuffer = new ArrayBuffer(minLength); new Uint8Array(newBuffer).set(new Uint8Array(arrayBuffer)); arrayBuffer = newBuffer; }",
            )
        elif "devices/" in rel_path:
            code = re.sub(r"throw\s+['\"]Read is out of range['\"];?", "return 0;", code)
            code = re.sub(r"throw\s+['\"]Write is out of range['\"];?", "return;", code)
            if "dps.js" in rel_path:
                code = re.sub(r"throw\s+['\"]DPS writes are unhandled['\"];?", "return;", code)
                code = re.sub(r"throw\s+['\"]DPS reads are unhandled['\"];?", "return 0;", code)
            if "sp.js" in rel_path:
                code = code.replace(
                    "throw 'Read is out of range in ' + this.name + ' (ea=' + toString32(ea) + ')';",
                    "return 0;",
                )
                code = code.replace("throw 'Read is out of range';", "return 0;")

        if "microcodes.js" in rel_path:
            hook = """logger.log(`New RSP graphics ucode seen: ${version} = ucode ${ucode}`); if(globalThis.__n64jsMicrocodeHook){ try{globalThis.__n64jsMicrocodeHook({version,ucode});}catch(err){console.warn('microcode hook failed',err);}}"""
            code = code.replace(
                "logger.log(`New RSP graphics ucode seen: ${version} = ucode ${ucode}`);", hook
            )

        if "n64js_findmicrocode.mjs" in rel_path:
            code = code.replace(
                "globalThis.__n64jsMicrocodeHook({ version: sig_name, hash, ucodeSize: ucode_size });",
                "const _info = { version: sig_name, hash, ucodeSize: ucode_size }; if(globalThis.__n64js_detected_microcodes) globalThis.__n64js_detected_microcodes.push(_info); if(globalThis.__n64jsMicrocodeHook) globalThis.__n64jsMicrocodeHook(_info);",
            )
            code = code.replace(
                "export function dumpMicrocodeFromN64State",
                "function dumpMicrocodeFromN64State_Impl",
            )
            code += "\nexport function dumpMicrocodeFromN64State(opts) { globalThis.__n64js_detected_microcodes = []; dumpMicrocodeFromN64State_Impl(opts); return globalThis.__n64js_detected_microcodes; }\n"

        def replace_dep(match):
            target, dep = match.group(1).strip(), match.group(2)
            dep_rel = (
                os.path.normpath(os.path.join(os.path.dirname(rel_path), dep))
                .replace("\\", "/")
                .replace("//", "/")
            )
            if dep_rel.startswith("./"):
                dep_rel = dep_rel[2:]
            self.load_module(dep_rel)
            k = dep_rel
            if k.endswith(".mjs"):
                k = k[:-4] + ".js"

            if target == "{ rsp }" or target == "{rsp}":
                return f"const _rsp_mod = __require('{k}'); const rsp = new Proxy({{}}, {{ get: (t,p) => {{ const r = _rsp_mod.rsp; if(!r) return undefined; const v = r[p]; return typeof v === 'function' ? v.bind(r) : v; }} }});"
            if target.startswith("{") and target.endswith("}"):
                return f'const {target} = __require("{k}")'
            elif "*" in target:
                m = re.search(r"as\s+([a-zA-Z0-9_]+)", target)
                n = m.group(1) if m else "unknown"
                return f'const {n} = __require("{k}")'
            else:
                return f'const {target} = __require("{k}").default'

        code = re.sub(r'\bimport\s+(.+?)\s+from\s+[\'"](.+?)[\'"]', replace_dep, code)
        export_names = []

        def handle_export_basic(m):
            export_names.append(m.group(2))
            return f"{m.group(1)} {m.group(2)}"

        code = re.sub(
            r"\bexport\s+(class|function|var|const|let)\s+([a-zA-Z0-9_]+)",
            handle_export_basic,
            code,
        )

        def handle_export_braces(m):
            for n in m.group(1).split(","):
                export_names.append(n.strip().split(" as ").pop())
            return f"/* export {{ {m.group(1)} }} */"

        code = re.sub(
            r"\bexport\s+{(.+?)}",
            handle_export_braces,
            code,
        )

        export_binds = ""
        unique_exports = list(set(export_names))
        for name in unique_exports:
            export_binds += f"Object.defineProperty(__exports, '{name}', {{ get: () => {name}, enumerable: true, configurable: true }});\n"

        keys = [reg_path]
        if is_entry:
            keys.append(os.path.basename(reg_path))
        reg_calls = "".join(
            [f'globalThis.__registerModule("{k}", __exports);\n' for k in set(keys)]
        )

        wrapper = f"(function(){{ var __exports = {{}}; {code} {export_binds} {reg_calls} }})();"
        try:
            self.ctx.eval(wrapper)
            keys_to_reg = list(set(keys))
            for k in keys_to_reg:
                self.modules[k] = True
            N64JSHost._transpile_cache[cache_key] = (wrapper, keys_to_reg)
        except Exception as e:
            raise Exception(f"Failed to execute module {rel_path}: {e}")

    def init_emulator(self, rom_bytes, compression_type, rom_name="HEADLESS"):
        self.compression_type = compression_type
        print(f"[N64Host] Initializing emulator with {len(rom_bytes)} bytes...", flush=True)
        self.ctx.add_callable(
            "__get_rom_chunk_raw", lambda o, s: rom_bytes[o : o + s].decode("latin-1")
        )

        js_load = """
            (function() {
                const len = __ROM_LEN__;
                const ab = new ArrayBuffer(len);
                const u8 = new Uint8Array(ab);
                const CHUNK = 1024 * 1024;
                for(let i=0; i < len; i += CHUNK) {
                   const s = Math.min(CHUNK, len - i);
                   const raw = __get_rom_chunk_raw(i, s);
                   for(let j=0; j < s; j++) {
                       u8[i+j] = raw.charCodeAt(j);
                   }
                }
                globalThis.__romU8 = u8;
            })();
        """.replace("__ROM_LEN__", str(len(rom_bytes)))
        self.ctx.eval(js_load)

        core = [
            "emulated_exception.js",
            "hardware.js",
            "r4300.js",
            "rsp.js",
            "boot.js",
            "endian.js",
            "romdb.js",
            "system_constants.js",
            "devices/pi.js",
            "devices/vi.js",
            "devices/mi.js",
            "devices/si.js",
            "devices/ai.js",
            "devices/ri.js",
            "devices/sp.js",
            "devices/dpc.js",
            "devices/dps.js",
            "devices/ram.js",
            "devices/pif.js",
            "devices/rom.js",
            "n64js_findmicrocode.mjs",
            "base64.js",
            "cpu0reg.js",
        ]

        for mod in core:
            self.load_module(mod, is_entry=True)

        self.ctx.eval(
            """
            try {
                (function() {
                    const regs = __require("cpu0reg.js");
                    globalThis.__REGS = regs;
                    const hardwareMod = __require("hardware.js");
                    hardwareMod.Hardware.prototype.checkSIStatusConsistent = function() {};

                    const piModule = __require("devices/pi.js");
                    const compForward = new TextEncoder().encode("__COMP_TYPE__");
                    const compBackward = new Uint8Array(compForward).reverse();
                    const realOrigDMA = piModule.PIRegDevice.prototype.copyToRDRAM;

                    piModule.PIRegDevice.prototype.copyToRDRAM = function() {
                        const cart = this.mem.getU32(0x04) & 0xfffffffe;
                        const len = (this.mem.getU32(0x0c) & 0x00ffffff) + 1;
                        const rom = this.hardware.rom;
                        if (rom && len >= 4) {
                            let o = -1;
                            if (cart >= 0x10000000 && cart < 0x10000000 + rom.u8.length) o = cart - 0x10000000;
                            if (o >= 0 && o + 4 <= rom.u8.length) {
                                const sl = rom.u8.subarray(o, o + 4);
                                if (compForward.every((b, i) => sl[i] === b) || compBackward.every((b, i) => sl[i] === b)) {
                                    console.log("[PI DMA] Match found at 0x" + o.toString(16));
                                    header_found(o, cart);
                                    globalThis.runMicrocodeDetectionQuiet();
                                }
                                if (len === 0x10) {
                                    const rv = (rom.u8[o]<<8)|rom.u8[o+1];
                                    const sc = (rom.u8[o+2]<<8)|rom.u8[o+3];
                                    if (rv <= 5 && sc >= 10 && sc <= 100) { alseq_found(o, rv, sc); }
                                }
                            }
                        }
                        return realOrigDMA.apply(this, arguments);
                    };

                    const bootMod = __require("boot.js");
                    const r4300Mod = __require("r4300.js");
                    const rspMod = __require("rsp.js");
                    const endianMod = __require("endian.js");
                    const romdbMod = __require("romdb.js");
                    const sysConstMod = __require("system_constants.js");
                    const findMcMod = __require("n64js_findmicrocode.mjs");
                    const graphicsOptionsMod = __require("hle/graphics_options.js");
                    graphicsOptionsMod.graphicsOptions.emulationMode = 'LLE';

                    const ab = globalThis.__romU8.buffer;
                    endianMod.fixRomByteOrder(ab);
                    const rominfo = {
                        cic: romdbMod.generateCICType(globalThis.__romU8),
                        save: 'Eeprom4k',
                        tvType: sysConstMod.tvTypeFromCountry(globalThis.__romU8[0x3E])
                    };

                    const hardware = new hardwareMod.Hardware(rominfo);
                    if (hardware.sp_reg.u8.length === 0x20) {
                        const memRegionMod = __require("memory_region.js");
                        const new_sp_reg = new memRegionMod.MemoryRegion(new ArrayBuffer(0x34));
                        new_sp_reg.u8.set(hardware.sp_reg.u8);
                        hardware.sp_reg = new_sp_reg;
                        hardware.spRegDevice.mem = new_sp_reg;
                        hardware.spRegDevice.u8 = new_sp_reg.u8;
                    }
                    globalThis.__hardware = hardware;
                    n64js.hardware = () => hardware;

                    globalThis.runMicrocodeDetectionQuiet = function() {
                        try {
                            const RAM = hardware.ram.u8;
                            const r32 = (a) => {
                                const u = a >>> 0;
                                if (u < RAM.length) return hardware.ram.getU32(u) >>> 0;
                                if (u >= 0x80000000 && u < 0x80000000 + RAM.length) return hardware.ram.getU32(u - 0x80000000) >>> 0;
                                return 0;
                            };
                            const rMB = (a, s) => {
                                const u = a >>> 0;
                                let o = -1;
                                if (u < RAM.length) o = u;
                                else if (u >= 0x80000000 && u < 0x80000000 + RAM.length) o = u - 0x80000000;
                                if (o >= 0) return RAM.subarray(o, o + s);
                                return new Uint8Array(s);
                            };
                            const rS = (a, m = 64) => {
                                const b = rMB(a, m);
                                let s = '';
                                for(let i=0;i<b.length;i++){ if(b[i]===0) break; s+=String.fromCharCode(b[i]); }
                                return s;
                            };
                            const found = findMcMod.dumpMicrocodeFromN64State({ ram: RAM, readU32: r32, readString: rS, readMemBlock: rMB, romName: '__ROM_NAME__' });
                            if (found && found.length > 0) {
                                globalThis.__n64jsMicrocodeHook(found[0]);
                            }
                        } catch (err) {}
                    };

                    globalThis.__stepEmulator = function(cycles) {
                        hardware.cpu0.run(cycles);
                    };

                    hardware.reset();
                    r4300Mod.initCPU(hardware);
                    rspMod.initRSP(hardware);
                    hardware.createROM(ab);
                    hardware.loadROM();
                    bootMod.simulateBoot(hardware.cpu0, hardware, rominfo);
                })();
            } catch(e) {}
        """.replace("__COMP_TYPE__", self.compression_type).replace("__ROM_NAME__", rom_name)
        )
        print("Emulator initialized and ready.", flush=True)

    def step(self, cycles=1000000):
        try:
            self.total_cycles += cycles
            self.ctx.eval(f"globalThis.__stepEmulator({cycles});")
            if (
                not self.microcode_done
                and (self.total_cycles - self.last_microcode_probe_cycle)
                >= self.microcode_probe_interval
            ):
                self.ctx.eval("globalThis.runMicrocodeDetectionQuiet();")
                self.last_microcode_probe_cycle = self.total_cycles
        except Exception as e:
            print(f"Step Error: {e}")
            raise
        return self.found_headers


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python n64_host.py <rom.z64> [--compression-type TYPE]")
        sys.exit(1)

    rom_path = sys.argv[1]
    comp_type = "MIO0"
    if "--compression-type" in sys.argv:
        comp_type = sys.argv[sys.argv.index("--compression-type") + 1]

    script_dir = os.path.dirname(os.path.abspath(__file__))
    n64_src = os.path.join(script_dir, "n64js", "src")
    if not os.path.exists(n64_src):
        n64_src = os.path.join(os.getcwd(), "py", "n64js", "src")

    host = N64JSHost(n64_src)
    if os.path.exists(rom_path):
        with open(rom_path, "rb") as f:
            rom_data = f.read()
        host.init_emulator(rom_data, comp_type, os.path.basename(rom_path))
        print("Stepping...", flush=True)
        start = time.time()
        while time.time() - start < 115:
            host.step(5000000)
    else:
        print(f"ROM not found: {rom_path}")
