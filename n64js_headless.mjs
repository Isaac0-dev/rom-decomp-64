#!/usr/bin/env bun

// This is a module to run n64js headless using Bun.
// It patches parts of n64js that require a browser,
// and adds code to detect compression headers during PI DMA transfers.

import fs from 'fs/promises';
import path from 'path';
import readline from 'readline';
import { plugin } from "bun";
import { dumpMicrocodeFromN64State } from './n64js_findmicrocode.mjs';

// Patch dbg_ui, hle_graphics, and inject a microcode hook
plugin({
    name: "override-dbgGUI",
    setup(build) {
        build.onLoad({ filter: /dbg_ui/ }, async (args) => {
            console.log("Patching:", args.path);
            const text = await Bun.file(args.path).text();
            const modified = text.replace(
                "export const dbgGUI = new GUI();",
                `const DummyController = class {
  name() { return this; }
  min() { return this; }
  max() { return this; }
  step() { return this; }
  listen() { return this; }
  onChange() { return this; }
};

const GUIImpl = (typeof GUI === 'function') ? GUI : class {
  constructor() { this.visible = false; }
  title() { return this; }
  show() { this.visible = true; }
  hide() { this.visible = false; }
  add() { return new DummyController(); }
  addFolder() { return new GUIImpl(); }
};

export const dbgGUI = new GUIImpl();`
            );
            return {
                contents: modified,
                loader: "js",
            };
        });

        build.onLoad({ filter: /hle_graphics/ }, async (args) => {
            console.log("Patching:", args.path);
            let code = await Bun.file(args.path).text();
            code = code.replace(
                "export function initialiseRenderer",
                "export function __orig_initialiseRenderer"
            );

            code += `
export function initialiseRenderer($canvas) {
  if (globalThis.N64JS_HEADLESS) {
    gl = { FRAMEBUFFER: 0, bindFramebuffer() {} };
    renderer = {
      nativeTransform: { initDimensions() {} },
      copyBackBufferToFrontBuffer() {},
      copyPixelsToFrontBuffer() {},
      newFrame() {},
      reset() {},
      debugClear() {},
    };
    return;
  }
  return __orig_initialiseRenderer($canvas);
}`;
            return {
                contents: code,
                loader: "js",
            };
        });

        build.onLoad({ filter: /microcodes\.js$/ }, async (args) => {
            console.log("Patching:", args.path);
            const text = await Bun.file(args.path).text();
            const hookSnippet = `logger.log(\`New RSP graphics ucode seen: \${version} = ucode \${ucode}\`);
  if (globalThis.__n64jsMicrocodeHook) {
    try {
      globalThis.__n64jsMicrocodeHook({ version, ucode });
    } catch (err) {
      console.warn('microcode hook failed', err);
    }
  }`;

            const modified = text.replace(
                "  logger.log(`New RSP graphics ucode seen: ${version} = ucode ${ucode}`);",
                hookSnippet
            );

            return {
                contents: modified,
                loader: "js",
            };
        });
    },
});

const scriptDir = import.meta.dir;
const projectRoot = scriptDir;
const n64Root = path.join(scriptDir, 'n64js', 'src');

async function loadModule(relPath) {
    return import(path.join(n64Root, relPath));
}

// Provide the globals expected by n64js modules.
globalThis.window = globalThis;
globalThis.N64JS_HEADLESS = true;
globalThis.performance = globalThis.performance || { now: () => Date.now() };
globalThis.navigator = globalThis.navigator || { userAgent: 'headless' };
function makeGLStub() {
    const noop = () => { };
    const generators = {
        createFramebuffer: () => ({}),
        createTexture: () => ({}),
        createRenderbuffer: () => ({}),
        createShader: () => ({}),
        createProgram: () => ({}),
        getUniformLocation: () => ({}),
        createVertexArray: () => ({}),
    };
    const constants = {
        FRAMEBUFFER: 0,
        COLOR_ATTACHMENT0: 0,
        DEPTH_ATTACHMENT: 0,
        TEXTURE_2D: 0,
        TEXTURE0: 0,
        RGBA: 0,
        UNSIGNED_BYTE: 0,
        UNSIGNED_SHORT_5_5_5_1: 0,
        NEAREST: 0,
        CLAMP_TO_EDGE: 0,
        TRIANGLES: 0,
        TRIANGLE_STRIP: 0,
        CULL_FACE: 0,
        BLEND: 0,
        DEPTH_TEST: 0,
        RENDERBUFFER: 0,
        DEPTH_COMPONENT16: 0,
        STATIC_DRAW: 0,
    };
    return new Proxy({}, {
        get(_, prop) {
            if (prop in constants) {
                return constants[prop];
            }
            if (prop in generators) {
                return generators[prop];
            }
            if (prop === 'canvas') {
                return stubCanvas;
            }
            return noop;
        },
    });
}

const stubCanvas = {
    width: 0,
    height: 0,
    style: {},
    requestFullscreen: () => Promise.resolve(),
    getContext: () => makeGLStub(),
};

globalThis.document = globalThis.document || {
    getElementById: () => stubCanvas,
};
globalThis.alert = globalThis.alert || (() => { });
function mapStorage() {
    const store = new Map();
    return {
        getItem: (key) => store.has(key) ? store.get(key) : null,
        setItem: (key, value) => store.set(key, value),
        removeItem: (key) => store.delete(key),
    };
}

globalThis.localStorage = mapStorage();

class DummyAudioContext {
    constructor() { }
    createBuffer() { return {}; }
    close() { }
}

globalThis.AudioContext = globalThis.AudioContext || DummyAudioContext;
globalThis.webkitAudioContext = globalThis.webkitAudioContext || DummyAudioContext;
globalThis.window.AudioContext = globalThis.window.AudioContext || DummyAudioContext;
class DummyAudioBuffer {
    copyToChannel() { }
    getChannelData() { return new Float32Array(0); }
}
globalThis.AudioBuffer = globalThis.AudioBuffer || DummyAudioBuffer;
class DummyAudioBufferSourceNode {
    constructor() {
        this.buffer = null;
        this.loop = false;
        this.loopStart = 0;
        this.loopEnd = 0;
    }
    connect() { return this; }
    disconnect() { return this; }
    start() { }
    stop() { }
}
globalThis.AudioBufferSourceNode = globalThis.AudioBufferSourceNode || DummyAudioBufferSourceNode;

function makeJQueryStub() {
    const base = {
        0: stubCanvas,
        length: 1,
        append() { return this; },
        appendTo() { return this; },
        html() { return this; },
        text() { return this; },
        attr() { return this; },
        css() { return this; },
        find() { return this; },
        on() { return this; },
        off() { return this; },
        show() { return this; },
        hide() { return this; },
        addClass() { return this; },
        removeClass() { return this; },
        remove() { return this; },
        scrollTop() { return this; },
        data() { return this; },
        val() { return this; },
        click() { return this; },
        bind() { return this; },
        unbind() { return this; },
        ready(fn) { if (typeof fn === 'function') { fn(); } return this; },
    };
    return new Proxy(base, {
        get(target, prop) {
            if (prop === Symbol.iterator) {
                return undefined;
            }
            if (prop in target) {
                return target[prop];
            }
            target[prop] = function () { return target; };
            return target[prop];
        },
    });
}

const jqueryStub = makeJQueryStub();
globalThis.$ = globalThis.$ || (() => jqueryStub);

const n64js = {};
globalThis.n64js = n64js;

// Capture microcode detection from n64js and translate it to a system we can interpret.
let detectedMicrocode = null;
const MICROCODE_MAP = {
    0: "F3D",      // kUCode_GBI0
    1: "F3DEX",    // kUCode_GBI1
    2: "F3DEX2",   // kUCode_GBI2
    3: "F3DEX",    // kUCode_GBI1_SDEX
    4: "F3DEX2",   // kUCode_GBI2_SDEX
    5: "F3D",      // kUCode_GBI0_WR
    6: "F3D",      // kUCode_GBI0_DKR
    7: "F3DEX",    // kUCode_GBI1_LL
    8: "F3D",      // kUCode_GBI0_SE
    9: "F3D",      // kUCode_GBI0_GE
    10: "F3DEX2",  // kUCode_GBI2_CONKER
    11: "F3DEX",   // kUCode_GBI0_PD
};

const MICROCODE_HASH_OVERRIDES = {
    0x60256efc: 10,
    0x6d8bec3e: 7,
    0x0c10181a: 6,
    0x713311dc: 6,
    0x23f92542: 9,
    0x169dcc9d: 6,
    0x26da8a4c: 7,
    0xcac47dc4: 11,
    0x6cbb521d: 8,
    0xdd560323: 7,
    0x64cc729d: 5,
    0xd73a12c4: 0,
    0x313f038b: 0,
};

function mapMicrocodeId(ucode) {
    return Object.prototype.hasOwnProperty.call(MICROCODE_MAP, ucode) ? MICROCODE_MAP[ucode] : null;
}

function inferUcodeFromString(version) {
    const prefixes = ["F3", "L3", "S2DEX"];
    let idx = -1;
    for (const prefix of prefixes) {
        idx = version.indexOf(prefix);
        if (idx >= 0) break;
    }
    if (idx >= 0) {
        if (version.indexOf("S2DEX", idx) >= 0) {
            return version.indexOf("fifo", idx) >= 0 || version.indexOf("xbux", idx) >= 0 ? 4 : 3;
        }
        return version.indexOf("fifo", idx) >= 0 || version.indexOf("xbux", idx) >= 0 ? 2 : 1;
    }
    return 0; // default GBI0
}

function detectUcode(version, hash) {
    if (hash !== undefined && hash !== null) {
        const override = MICROCODE_HASH_OVERRIDES[hash >>> 0];
        if (override !== undefined) {
            return override;
        }
    }
    return inferUcodeFromString(version);
}

globalThis.__n64jsMicrocodeHook = ({ version, ucode, hash }) => {
    const ucodeId = (ucode !== undefined && ucode !== null) ? ucode : detectUcode(version || "", hash);
    const mapped = mapMicrocodeId(ucodeId);
    detectedMicrocode = { version, ucode, mapped };
    microcodeTaskDone = true;
    maybeExit();
    const mappedText = mapped || "unknown";
    // Print straight to stdout so extract.py can consume it.
    console.log(`[N64JS MICROCODE] ucode=${ucodeId} mapped=${mappedText} version="${version}" hash=${hash !== undefined ? '0x' + (hash >>> 0).toString(16) : 'n/a'}`);
};

n64js.warn = (...args) => console.warn('[n64js]', ...args);
n64js.log = (...args) => console.log('[n64js]', ...args);
n64js.halt = (msg) => {
    throw new Error(`n64js halt: ${msg}`);
};
n64js.stopForBreakpoint = () => {
    throw new Error('Breakpoint hit');
};
n64js.check = (cond, msg) => {
    if (!cond) {
        console.warn('[n64js check failed]', msg);
    }
};
n64js.ui = () => ({
    displayWarning: (...args) => console.warn('[n64js warning]', ...args),
    displayError: (...args) => console.error('[n64js error]', ...args),
});
n64js.returnControlToSystem = () => { };
n64js.getLocalStorageItem = () => undefined;
n64js.setLocalStorageItem = () => { };
n64js.saveU8Array = () => { };
n64js.joybus = () => ({
    dmaWrite() { },
    dmaRead() { },
    cpuRead() { },
    cpuWrite() { },
});
n64js.onPresent = () => { };

function arrayBufferFromBuffer(buf) {
    const { buffer, byteOffset, byteLength } = buf;
    return buffer.slice(byteOffset, byteOffset + byteLength);
}

function parseArgs() {
    const [, , ...rest] = process.argv;
    if (rest.length === 0) {
        console.error('Usage: bun n64js_headless.mjs <rom.z64> [--breakpoint 0xADDR] [--max-steps N] [--compression-type TYPE]');
        process.exit(1);
    }
    const romPath = path.resolve(rest[0]);
    const opts = { romPath, breakpoints: [], maxSteps: -1, chunkCycles: 50_000, compressionType: 'MIO0', ipc: false };
    for (let i = 1; i < rest.length; ++i) {
        const arg = rest[i];
        if (arg === '--breakpoint' && i + 1 < rest.length) {
            const value = rest[++i];
            opts.breakpoints.push(parseInt(value, 16));
        } else if (arg === '--max-steps' && i + 1 < rest.length) {
            opts.maxSteps = parseInt(rest[++i], 10);
        } else if (arg === '--chunk-cycles' && i + 1 < rest.length) {
            opts.chunkCycles = parseInt(rest[++i], 10);
        } else if (arg === '--compression-type' && i + 1 < rest.length) {
            opts.compressionType = rest[++i];
        } else if (arg === '--ipc') {
            opts.ipc = true;
        }
    }
    return opts;
}

const {
    Hardware,
} = await loadModule('hardware.js');

let hardware;
let totalCycles = 0;
let lastMicrocodeProbeCycle = 0;
const MICROCODE_PROBE_INTERVAL = 5_000_000;
let compressionTaskDone = false;
let microcodeTaskDone = false;
let commandLoopActive = false;

function readU32(addr) {
    // Read 32-bit CPU-visible word from current emulated memory.
    const u32 = addr >>> 0;

    // Fast paths for the common regions we care about (cached/uncached RDRAM and SP DMEM/IMEM).
    const rdramOffset = (() => {
        if (u32 < hardware.ram.u8.length) {
            return u32;
        }
        if (u32 >= 0x80000000 && u32 < 0x80000000 + hardware.ram.u8.length) {
            return u32 - 0x80000000;
        }
        if (u32 >= 0xa0000000 && u32 < 0xa0000000 + hardware.ram.u8.length) {
            return u32 - 0xa0000000;
        }
        return -1;
    })();
    if (rdramOffset >= 0) {
        return hardware.ram.getU32(rdramOffset) >>> 0;
    }

    const spOffset = (() => {
        // RSP DMEM/IMEM aliases.
        if (u32 >= 0x04000000 && u32 < 0x04002000) {
            return (u32 - 0x04000000) % 0x2000;
        }
        if (u32 >= 0xa4000000 && u32 < 0xa4040000) {
            return (u32 - 0xa4000000) % 0x2000;
        }
        return -1;
    })();
    if (spOffset >= 0) {
        return hardware.sp_mem.getU32(spOffset) >>> 0;
    }

    // Fallback to the generic memory map, which knows about devices/IO.
    try {
        return hardware.memMap.readMemoryInternal32(u32) >>> 0;
    } catch (err) {
        console.warn(`readU32 failed at 0x${u32.toString(16)}:`, err);
        return 0;
    }
}

function readMemBlock(addr, size) {
    const u32 = addr >>> 0;

    const copyFromArray = (source, offset) => {
        const result = new Uint8Array(size);
        const available = Math.max(0, Math.min(size, source.length - offset));
        if (available > 0) {
            result.set(source.subarray(offset, offset + available));
        }
        return result;
    };

    // RDRAM aliases (physical, cached, uncached).
    const rdramOffset = (() => {
        if (u32 < hardware.ram.u8.length) {
            return u32;
        }
        if (u32 >= 0x80000000 && u32 < 0x80000000 + hardware.ram.u8.length) {
            return u32 - 0x80000000;
        }
        if (u32 >= 0xa0000000 && u32 < 0xa0000000 + hardware.ram.u8.length) {
            return u32 - 0xa0000000;
        }
        return -1;
    })();
    if (rdramOffset >= 0) {
        return copyFromArray(hardware.ram.u8, rdramOffset);
    }

    // RSP DMEM/IMEM aliases.
    const spOffset = (() => {
        if (u32 >= 0x04000000 && u32 < 0x04002000) {
            return (u32 - 0x04000000) % 0x2000;
        }
        if (u32 >= 0xa4000000 && u32 < 0xa4040000) {
            return (u32 - 0xa4000000) % 0x2000;
        }
        return -1;
    })();
    if (spOffset >= 0) {
        return copyFromArray(hardware.sp_mem.u8, spOffset);
    }

    // Generic fallback: walk through the memory map using device handlers.
    const result = new Uint8Array(size);
    for (let i = 0; i < size; i++) {
        const a = (u32 + i) >>> 0;
        try {
            const handler = hardware.memMap.getMemoryHandler(a);
            result[i] = handler.readU8(a) & 0xff;
        } catch (err) {
            console.warn(`readMemBlock: failed to read 0x${a.toString(16)}:`, err);
            result[i] = 0;
        }
    }
    return result;
}

function readString(addr, maxLen = 64) {
    // Read C-style string from emulated memory (ASCII).
    const bytes = readMemBlock(addr, maxLen);
    let s = '';
    for (let i = 0; i < bytes.length; i++) {
        if (bytes[i] === 0) break;
        s += String.fromCharCode(bytes[i]);
    }
    return s;
}

function runMicrocodeDetectionQuiet() {
    const origLog = console.log;
    const origWarn = console.warn;
    try {
        console.log = (...args) => {
            if (args.length && typeof args[0] === 'string' && args[0].startsWith('[N64JS MICROCODE]')) {
                return origLog(...args);
            }
        };
        console.warn = () => { };
        const ramSnapshot = hardware.ram.u8.slice(0, 4 * 1024 * 1024);
        dumpMicrocodeFromN64State({
            ram: ramSnapshot,
            readU32,
            readString,
            readMemBlock,
            romName: path.basename(opts.romPath),
        });
    } catch (err) {
        origWarn('microcode detection failed', err);
    } finally {
        console.log = origLog;
        console.warn = origWarn;
    }
}

function maybeExit() {
    if (commandLoopActive) {
        return;
    }
    if (compressionTaskDone && microcodeTaskDone) {
        console.log('--- n64js completed tasks, exiting ---');
        process.exit(0);
    }
}

async function commandLoop() {
    commandLoopActive = true;

    const rl = readline.createInterface({
        input: process.stdin,
        crlfDelay: Infinity,
    });

    for await (const line of rl) {
        if (!line.trim()) {
            continue;
        }

        let msg;
        try {
            msg = JSON.parse(line);
        } catch (err) {
            console.warn('Invalid IPC message on stdin:', err);
            continue;
        }

        let reply = null;

        if (msg.cmd === 'step') {
            n64js.cpu0.run(msg.cycles ?? 100000);
            reply = { pc: n64js.cpu0.pc >>> 0 };
        }

        if (msg.cmd === 'readU32') {
            reply = { value: readU32(msg.addr) };
        }

        console.log(JSON.stringify(reply));
    }
}

let opts;

async function main() {
    opts = parseArgs();

    const commandLoopRequested = opts.ipc || !process.stdin.isTTY;
    if (opts.maxSteps === null || Number.isNaN(opts.maxSteps)) {
        opts.maxSteps = commandLoopRequested ? 0 : -1;
    }
    if (commandLoopRequested) {
        commandLoopActive = true; // keep process alive until command loop ends
    }

    const encoder = new TextEncoder();
    const compressionBytes = encoder.encode(opts.compressionType);

    const {
        Hardware,
    } = await loadModule('hardware.js');
    const { initCPU } = await loadModule('r4300.js');
    const { initRSP } = await loadModule('rsp.js');
    const graphics = await loadModule('hle/hle_graphics.js');
    const { simulateBoot } = await loadModule('boot.js');
    const { fixRomByteOrder } = await loadModule('endian.js');
    const romdbModule = await loadModule('romdb.js');
    const {
        romdb,
        generateRomId,
        generateCICType,
        uint8ArrayReadString,
    } = romdbModule;
    const { tvTypeFromCountry } = await loadModule('system_constants.js');
    const piModule = await loadModule('devices/pi.js');
    const {
        PI_DRAM_ADDR_REG,
        PI_CART_ADDR_REG,
        PI_WR_LEN_REG,
        PI_STATUS_DMA_BUSY,
        PI_DOM1_ADDR1,
        PI_DOM1_ADDR2,
        PI_DOM1_ADDR3,
        isDom1Addr1,
        isDom1Addr2,
        isDom1Addr3,
    } = piModule;

    const rominfo = {
        id: '',
        name: '',
        cic: '6101',
        country: 0,
        tvType: 0,
        save: 'Eeprom4k',
    };

    hardware = new Hardware(rominfo);
    if (graphics.initialiseRenderer) {
        try {
            graphics.initialiseRenderer(globalThis.$('#display'));
        } catch (err) {
            console.warn('initialiseRenderer failed (headless stub)', err);
        }
    }
    n64js.hardware = () => hardware;

    const originalCopyToRDRAM = piModule.PIRegDevice.prototype.copyToRDRAM;
    piModule.PIRegDevice.prototype.copyToRDRAM = function instrumentedCopy() {
        const dramAddr = this.mem.getU32(PI_DRAM_ADDR_REG) & 0x00fffffe;
        const cartAddr = this.mem.getU32(PI_CART_ADDR_REG) & 0xfffffffe;
        const transferLen = (this.mem.getU32(PI_WR_LEN_REG) & 0x00ffffff) + 1;
        console.log(`[PI DMA] cart=0x${cartAddr.toString(16).padStart(8, '0')} dram=0x${dramAddr.toString(16).padStart(8, '0')} len=0x${transferLen.toString(16)}`);
        const rom = this.hardware.rom;
        if (rom && transferLen >= 4) {
            let romOffset = -1;
            if (isDom1Addr1(cartAddr)) {
                romOffset = cartAddr - PI_DOM1_ADDR1;
            } else if (isDom1Addr2(cartAddr)) {
                romOffset = cartAddr - PI_DOM1_ADDR2;
            } else if (isDom1Addr3(cartAddr)) {
                romOffset = cartAddr - PI_DOM1_ADDR3;
            }
            if (romOffset >= 0 && romOffset + 4 <= rom.u8.length) {
                const slice = rom.u8.subarray(romOffset, romOffset + 4);
                if (compressionBytes.length <= slice.length && compressionBytes.every((b, i) => slice[i] === b)) {
                    console.log(`[PI DMA] found ${opts.compressionType} header at ROM 0x${romOffset.toString(16)} cart=0x${cartAddr.toString(16)}`);

                    runMicrocodeDetectionQuiet();
                    compressionTaskDone = true;
                    maybeExit();
                }

                // Check for ALSeqFile header (sequence data)
                if (transferLen === 0x10 && romOffset + 0x10 <= rom.u8.length) {
                    const revision = (rom.u8[romOffset] << 8) | rom.u8[romOffset + 1];
                    const seqCount = (rom.u8[romOffset + 2] << 8) | rom.u8[romOffset + 3];

                    if (revision <= 5 && seqCount >= 10 && seqCount <= 100) {
                        console.log(`[PI DMA] Found potential ALSeqFile header at ROM 0x${romOffset.toString(16)}`);
                        console.log(`[PI DMA]   Revision: ${revision}, Sequence Count: ${seqCount}`);

                        // Make sure it looks valid
                        const firstOffset = (rom.u8[romOffset + 4] << 24) | (rom.u8[romOffset + 5] << 16) |
                            (rom.u8[romOffset + 6] << 8) | rom.u8[romOffset + 7];
                        const firstLen = (rom.u8[romOffset + 8] << 24) | (rom.u8[romOffset + 9] << 16) |
                            (rom.u8[romOffset + 10] << 8) | rom.u8[romOffset + 11];

                        // Bounds check them in case it's a random match
                        if (firstOffset > 0 && firstOffset < 0x100000 && firstLen > 0 && firstLen < 0x20000) {
                            console.log(`[PI DMA]   First entry: offset=0x${firstOffset.toString(16)}, len=0x${firstLen.toString(16)}`);
                            console.log(`[PI DMA] ALSeqFile at ROM 0x${romOffset.toString(16)}`);
                        }
                    }
                }
            }
        }
        return originalCopyToRDRAM.apply(this, arguments);
    };

    const romBytes = await fs.readFile(opts.romPath);
    let arrayBuffer = arrayBufferFromBuffer(romBytes);
    const maxCartSize = 64 * 1024 * 1024;
    if (arrayBuffer.byteLength < maxCartSize) {
        const padded = new ArrayBuffer(maxCartSize);
        new Uint8Array(padded).set(new Uint8Array(arrayBuffer));
        arrayBuffer = padded;
    }
    fixRomByteOrder(arrayBuffer);
    const rom = hardware.createROM(arrayBuffer);
    const hdr = {
        header: rom.getU32(0),
        clock: rom.getU32(4),
        bootAddress: rom.getU32(8),
        release: rom.getU32(12),
        crclo: rom.getU32(16),
        crchi: rom.getU32(20),
        name: uint8ArrayReadString(rom.u8, 32, 20),
        countryId: rom.getU8(62),
        romVersion: rom.getU8(63),
    };

    rominfo.cic = generateCICType(rom.u8);
    rominfo.id = generateRomId(hdr.crclo, hdr.crchi);
    rominfo.country = hdr.countryId;
    rominfo.tvType = tvTypeFromCountry(hdr.countryId);
    const info = romdb[rominfo.id];
    if (info) {
        rominfo.name = info.name;
        rominfo.save = info.save;
    } else {
        rominfo.name = hdr.name.trim();
    }

    console.log(`Loaded ROM ${rominfo.name} (id=${rominfo.id}, cic=${rominfo.cic})`);

    hardware.reset();
    initCPU(hardware);
    initRSP(hardware);
    hardware.loadROM();
    simulateBoot(n64js.cpu0, hardware, rominfo);

    const breakpoints = opts.breakpoints;
    const targetSet = new Set(breakpoints);
    const chunkCycles = opts.chunkCycles;
    totalCycles = 0;
    let hit = false;
    const shouldAutoStep = opts.maxSteps !== 0;

    if (shouldAutoStep) {
        while ((opts.maxSteps === -1 || totalCycles < opts.maxSteps) && !hit) {
            n64js.cpu0.run(chunkCycles);
            totalCycles += chunkCycles;
            const pc = n64js.cpu0.pc >>> 0;
            if (breakpoints.length === 0) {
                // console.log(`PC=0x${pc.toString(16).padStart(8, '0')}`);
            }
            if (targetSet.has(pc)) {
                console.log(`Hit breakpoint at PC=0x${pc.toString(16).padStart(8, '0')} after ${totalCycles} cycles`);
                hit = true;
            }
            const status = n64js.hardware().pi_reg.getU32(PI_WR_LEN_REG);
            if (status & PI_STATUS_DMA_BUSY) {
                // console.log('[PI] DMA busy');
            }

            // Periodically try an explicit microcode scan if nothing has been detected yet.
            if (!detectedMicrocode && (totalCycles - lastMicrocodeProbeCycle) >= MICROCODE_PROBE_INTERVAL) {
                runMicrocodeDetectionQuiet();
                lastMicrocodeProbeCycle = totalCycles;
            }

            maybeExit();
        }

        if (!hit && breakpoints.length) {
            console.warn(`Did not hit breakpoints ${breakpoints.map(pc => '0x' + pc.toString(16)).join(', ')} within ${opts.maxSteps} cycles`);
        }
    }

    if (commandLoopRequested) {
        await commandLoop();
        commandLoopActive = false;
        maybeExit();
    }
}

main().catch((err) => {
    console.error(err);
    process.exit(1);
});
