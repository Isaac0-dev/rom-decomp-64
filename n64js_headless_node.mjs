#!/usr/bin/env node

// This is a module to run n64js headless using Node.js.
// It patches parts of n64js that require a browser,
// and adds code to detect compression headers during PI DMA transfers.

import fs from 'fs/promises';
import path from 'path';
import readline from 'readline';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const scriptDir = __dirname;
const n64Root = path.join(scriptDir, 'n64js', 'src');

const moduleCache = new Map();

async function loadModule(relPath) {
    if (moduleCache.has(relPath)) {
        return moduleCache.get(relPath);
    }

    const absPath = path.join(n64Root, relPath);
    let code = await fs.readFile(absPath, 'utf8');

    if (relPath.includes('dbg_ui.js')) {
        code = `const DummyController = class {
  name() { return this; }
  min() { return this; }
  max() { return this; }
  step() { return this; }
  listen() { return this; }
  onChange() { return this; }
};

const GUIImpl = class {
  constructor() { this.visible = false; }
  title() { return this; }
  show() { this.visible = true; }
  hide() { this.visible = false; }
  add() { return new DummyController(); }
  addFolder() { return new GUIImpl(); }
};

export const dbgGUI = new GUIImpl();
export function show() {}
export function hide() {}
export function setVisible() {}`;
    } else if (relPath.includes('hle_graphics.js')) {
        code = code.replace(
            "export function initialiseRenderer",
            "export function __orig_initialiseRenderer"
        );

        code += `
export function initialiseRenderer($canvas) {
  if (globalThis.N64JS_HEADLESS) {
    globalThis.gl = { FRAMEBUFFER: 0, bindFramebuffer() {} };
    globalThis.renderer = {
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
}
export function resetRenderer() {}
export function presentBackBuffer() {}`;
    } else if (relPath.includes('microcodes.js')) {
        const hookSnippet = `logger.log(\`New RSP graphics ucode seen: \${version} = ucode \${ucode}\`);
  if (globalThis.__n64jsMicrocodeHook) {
    try {
      globalThis.__n64jsMicrocodeHook({ version, ucode });
    } catch (err) {
      console.warn('microcode hook failed', err);
    }
  }`;

        code = code.replace(
            "  logger.log(`New RSP graphics ucode seen: ${version} = ucode ${ucode}`);",
            hookSnippet
        );
    }

    // Rewrite relative imports to use Data URIs of their patched versions
    const importRegex = /\\bimport\s+(.+?)\s+from\s+['"](.+?)['"]/g;
    const matches = [...code.matchAll(importRegex)];
    
    for (const match of matches) {
        const fullMatch = match[0];
        const items = match[1];
        const dep = match[2];
        if (dep.startsWith('.')) {
            let depRelPath = path.join(path.dirname(relPath), dep);
            if (!depRelPath.endsWith('.js') && !depRelPath.endsWith('.mjs')) {
                depRelPath += '.js';
            }
            
            const depModule = await loadModule(depRelPath);
            code = code.replace(fullMatch, `import ${items} from '${depModule.dataUri}'`);
        } else if (dep === 'lil-gui') {
            code = code.replace(fullMatch, `// ${fullMatch}`);
        }
    }

    const encoded = Buffer.from(code).toString('base64');
    const dataUri = \`data:text/javascript;base64,\${encoded}\`;
    
    const moduleNamespace = await import(dataUri);
    const result = { ...moduleNamespace, dataUri };
    moduleCache.set(relPath, result);
    return result;
}

// Provide the globals expected by n64js modules.
globalThis.window = globalThis;
globalThis.N64JS_HEADLESS = true;
globalThis.performance = globalThis.performance || { now: () => Date.now() };
if (!globalThis.navigator) {
    Object.defineProperty(globalThis, 'navigator', {
        value: { userAgent: 'headless' },
        writable: true,
        configurable: true
    });
}

function makeGLStub() {
    const noop = () => { };
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
            if (prop in constants) return constants[prop];
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
    createElement: () => stubCanvas,
};
globalThis.alert = globalThis.alert || (() => { });
globalThis.localStorage = {
    getItem: () => null,
    setItem: () => {},
    removeItem: () => {},
};

globalThis.AudioContext = class {};
globalThis.AudioBuffer = class {};
globalThis.AudioBufferSourceNode = class {};

const jqueryStub = new Proxy(() => jqueryStub, {
    get: (target, prop) => {
        if (prop === 'ready') return (fn) => fn();
        return () => jqueryStub;
    }
});
globalThis.$ = globalThis.$ || jqueryStub;

const n64js = {};
globalThis.n64js = n64js;

let microcodeTaskDone = false;
let compressionTaskDone = false;
let detectedMicrocode = null;

const MICROCODE_MAP = {
    0: "F3D", 1: "F3DEX", 2: "F3DEX2", 3: "F3DEX", 4: "F3DEX2", 5: "F3D", 6: "F3D", 7: "F3DEX", 8: "F3D", 9: "F3D", 10: "F3DEX2", 11: "F3DEX",
};

globalThis.__n64jsMicrocodeHook = ({ version, ucode, hash }) => {
    const mapped = MICROCODE_MAP[ucode] || "unknown";
    console.log(\`[N64JS MICROCODE] ucode=\${ucode} mapped=\${mapped} version="\${version}"\`);
    microcodeTaskDone = true;
    maybeExit();
};

n64js.warn = (...args) => console.warn('[n64js]', ...args);
n64js.log = (...args) => console.log('[n64js]', ...args);
n64js.halt = (msg) => { throw new Error(\`n64js halt: \${msg}\`); };
n64js.ui = () => ({ displayWarning: () => {}, displayError: () => {} });
n64js.returnControlToSystem = () => { };
n64js.joybus = () => ({ dmaWrite(){}, dmaRead(){}, cpuRead(){}, cpuWrite(){} });

function maybeExit() {
    if (compressionTaskDone && microcodeTaskDone) {
        console.log('--- n64js completed tasks, exiting ---');
        process.exit(0);
    }
}

async function main() {
    const args = process.argv.slice(2);
    const romPath = path.resolve(args[0]);
    const compressionType = args.includes('--compression-type') ? args[args.indexOf('--compression-type') + 1] : 'MIO0';

    const { Hardware } = await loadModule('hardware.js');
    const { initCPU } = await loadModule('r4300.js');
    const { initRSP } = await loadModule('rsp.js');
    const { simulateBoot } = await loadModule('boot.js');
    const { fixRomByteOrder } = await loadModule('endian.js');
    const { generateCICType } = await loadModule('romdb.js');
    const { tvTypeFromCountry } = await loadModule('system_constants.js');
    const piModule = await loadModule('devices/pi.js');
    const { dumpMicrocodeFromN64State } = await import('./n64js_findmicrocode.mjs');

    const rominfo = { cic: '6101', save: 'Eeprom4k', tvType: 0 };
    const hardware = new Hardware(rominfo);
    globalThis.n64js.hardware = () => hardware;

    const originalCopyToRDRAM = piModule.PIRegDevice.prototype.copyToRDRAM;
    piModule.PIRegDevice.prototype.copyToRDRAM = function() {
        const cartAddr = this.mem.getU32(0x04) & 0xfffffffe;
        const rom = this.hardware.rom;
        if (rom) {
            const romOffset = cartAddr - 0x10000000;
            const slice = rom.u8.subarray(romOffset, romOffset + 4);
            const decoder = new TextDecoder();
            const header = decoder.decode(slice);
            if (header === compressionType) {
                console.log(\`[PI DMA] found \${compressionType} header at ROM 0x\${romOffset.toString(16)} cart=0x\${cartAddr.toString(16)}\`);
                compressionTaskDone = true;
                maybeExit();
            }
        }
        return originalCopyToRDRAM.apply(this, arguments);
    };

    const romBytes = await fs.readFile(romPath);
    const ab = romBytes.buffer.slice(romBytes.byteOffset, romBytes.byteOffset + romBytes.byteLength);
    fixRomByteOrder(ab);
    const rom = hardware.createROM(ab);
    rominfo.cic = generateCICType(rom.u8);
    rominfo.tvType = tvTypeFromCountry(rom.getU8(62));

    hardware.reset();
    initCPU(hardware);
    initRSP(hardware);
    hardware.loadROM();
    simulateBoot(globalThis.n64js.cpu0, hardware, rominfo);

    let totalCycles = 0;
    while (totalCycles < 100_000_000) {
        globalThis.n64js.cpu0.run(100_000);
        totalCycles += 100_000;
        if (totalCycles % 10_000_000 === 0) {
            dumpMicrocodeFromN64State({
                ram: hardware.ram.u8,
                readU32: (addr) => hardware.memMap.readMemoryInternal32(addr),
                readString: () => "",
                readMemBlock: () => new Uint8Array(0),
            });
        }
        maybeExit();
    }
}

main().catch(console.error);
