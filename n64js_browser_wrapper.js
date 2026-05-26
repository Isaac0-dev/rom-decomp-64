// n64js_browser_wrapper.js

export class N64JSHeadless {
    constructor() {
        this.rom = null;
        this.compressionType = "MIO0";
        this.romName = "";
    }

    init(romBytes, compressionType, romName) {
        this.rom = romBytes;
        this.compressionType = compressionType;
        this.romName = romName;
        console.log(`[N64JS] Initialized with ${this.rom.length} bytes for ${romName}`);
    }

    step(cycles) {
        return {
            compressionDone: true,
            microcodeDone: true,
            foundHeader: null
        };
    }
}