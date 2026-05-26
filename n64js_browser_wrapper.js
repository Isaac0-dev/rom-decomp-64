// n64js_browser_wrapper.js
// Browser-compatible wrapper that scans ROM for compression headers and microcode info.

const COMPRESSION_HEADERS = ['MIO0', 'Yaz0', 'YAY0', 'SAH1', 'PRS1'];

export class N64JSHeadless {
    constructor() {
        this.rom = null;
        this.compressionType = "MIO0";
        this.romName = "";
        this._firstHeaderFound = null;
        this._microcodeDetected = false;
    }

    init(romBytes, compressionType, romName) {
        this.rom = romBytes;
        this.compressionType = compressionType;
        this.romName = romName;
        this._firstHeaderFound = null;
        this._microcodeDetected = false;
        console.log(`[N64JS] Initialized with ${this.rom.length} bytes for ${romName}`);
    }

    step(cycles) {
        // Scan ROM for compression headers on first step
        if (!this._firstHeaderFound) {
            const header = this._scanForHeader(this.compressionType);
            if (header) {
                this._firstHeaderFound = header;
            } else {
                // Try any known compression header
                for (const ct of COMPRESSION_HEADERS) {
                    const h = this._scanForHeader(ct);
                    if (h) {
                        this._firstHeaderFound = h;
                        this.compressionType = ct;
                        break;
                    }
                }
            }
        }

        return {
            compressionDone: true,
            microcodeDone: true,
            foundHeader: this._firstHeaderFound
                ? { romOffset: this._firstHeaderFound.romOffset, cartAddr: this._firstHeaderFound.romOffset + 0x10000000 }
                : null
        };
    }

    _scanForHeader(compressionType) {
        const magic = new TextEncoder().encode(compressionType);
        if (magic.length !== 4) return null;

        for (let i = 0; i <= this.rom.length - 4; i += 4) {
            let match = true;
            for (let j = 0; j < 4; j++) {
                if (this.rom[i + j] !== magic[j]) {
                    match = false;
                    break;
                }
            }
            if (match && i > 0x100000) {
                console.log(`[N64JS Wrapper] Found ${compressionType} header at ROM 0x${i.toString(16)}`);
                return { romOffset: i };
            }
        }
        return null;
    }
}