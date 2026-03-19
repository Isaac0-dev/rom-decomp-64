// Port of Project64 RSP microcode detector "DumpMicrocode.js" for running on top of n64js as a module.
// Original version by Davideesk found at https://hack64.net/Thread-Fast3D-Microcodes

/**
 * Options:
 *   ram           : Uint8Array snapshot of at least 4MB of RDRAM
 *   readU32(addr) : read 32-bit word from *current* emulated memory (virtual address)
 *   readString(addr, maxLen?) : read C-style string from emulated memory
 *   readMemBlock(addr, size)  : Uint8Array of `size` bytes from emulated memory (virtual addr)
 *   romName       : string (for logging)
 */
export function dumpMicrocodeFromN64State({
    ram,
    readU32,
    readString,
    readMemBlock,
    romName = 'UNKNOWN',
}) {
    if (!ram || ram.length < 4 * 1024 * 1024) {
        throw new Error('ram must be a Uint8Array of at least 4MB');
    }
    if (typeof readU32 !== 'function' ||
        typeof readString !== 'function' ||
        typeof readMemBlock !== 'function') {
        throw new Error('readU32, readString and readMemBlock must be provided');
    }

    // Local aliases to avoid threading everything everywhere.
    const RAM = ram;
    const RAM_SIZE = RAM.length;
    const ROM_NAME = String(romName ?? 'UNKNOWN');

    let nextMicrocodeStart = 0;

    const signatures = [
        [0x52, 0x53, 0x50, 0x20, 0x53, 0x57],           // "RSP SW"
        [0x52, 0x53, 0x50, 0x20, 0x47, 0x66, 0x78],     // "RSP Gfx"
    ];

    function ALIGN_8_BYTES(value) {
        return value & 0xFFFFFFF8;
    }

    function ALIGN_16_BYTES(value) {
        return value & 0xFFFFFFF0;
    }

    let current_indent = 0;
    function print(output) {
        if (current_indent <= 0) {
            console.log(output);
        } else {
            const indent = new Array(current_indent + 1).join(' ');
            console.log(indent + output);
        }
    }

    // These operate on the RAM snapshot (offsets 0 .. RAM_SIZE-1).
    function readIntFromRAM(offset) {
        return (
            (RAM[offset] << 24) |
            (RAM[offset + 1] << 16) |
            (RAM[offset + 2] << 8) |
            RAM[offset + 3]
        ) >>> 0;
    }

    function readShortFromRAM(offset) {
        return ((RAM[offset] << 8) | RAM[offset + 1]) >>> 0;
    }

    function readOverlayTableToGetSizeOfMicrocode(start_offset) {
        let address_offset = 0;
        let ucode_actual_size = 0;
        let end = false;
        while (!end) {
            const main_offset = readIntFromRAM(start_offset + address_offset);
            const size = readShortFromRAM(start_offset + address_offset + 4) + 1;
            const offset = readShortFromRAM(start_offset + address_offset + 6);

            if (offset > 0x0fff && offset < 0x2000 && size < 0x1000) {
                ucode_actual_size = Math.max(ucode_actual_size, main_offset + size);
            } else {
                end = true;
            }
            address_offset += 8;
        }
        return ucode_actual_size;
    }

    function intToByteArray(val) {
        return [
            (val >> 24) & 0xff,
            (val >> 16) & 0xff,
            (val >> 8) & 0xff,
            val & 0xff,
        ];
    }

    function DumpDataToNoFindFolder(loc, sig_name, actual_ucode_size) {
        print(`Recording microcode data at 0x${loc.toString(16)} for ${sig_name} (no OSTask found)`);

        // Fallback hash using the signature location.
        try {
            const codeBytes = readMemBlock(loc, actual_ucode_size);
            let hash = 0;
            for (const b of codeBytes) {
                hash = ((hash * 17) + b) >>> 0;
            }
            if (globalThis.__n64jsMicrocodeHook) {
                globalThis.__n64jsMicrocodeHook({ version: sig_name, hash, ucodeSize: actual_ucode_size });
            }
        } catch (err) {
            console.warn('Failed to compute microcode hash (fallback)', err);
        }

        if (nextMicrocodeStart !== 0) {
            print(
                `Using expected microcode start 0x${nextMicrocodeStart.toString(16)} to compute hash`
            );

            // Try to compute hash and surface via hook.
            try {
                const codeBytes = readMemBlock(nextMicrocodeStart, actual_ucode_size);
                let hash = 0;
                for (const b of codeBytes) {
                    hash = ((hash * 17) + b) >>> 0;
                }
                if (globalThis.__n64jsMicrocodeHook) {
                    globalThis.__n64jsMicrocodeHook({ version: sig_name, hash, ucodeSize: actual_ucode_size });
                }
            } catch (err) {
                console.warn('Failed to compute microcode hash (NoOSTask)', err);
            }
        }
    }

    function DumpOSTaskStructure(task_address, sig_name) {
        print(`Observed OSTask structure at 0x${task_address.toString(16)} for ${sig_name}`);
    }

    function DumpMicrocode(task_address, ucode_size, sig_name) {
        const ucode_address = task_address + 0x10;

        nextMicrocodeStart = (readU32(ucode_address) >>> 0) + ucode_size;
        if ((ucode_size & 0x8) !== 0) {
            nextMicrocodeStart += 8; // 16-byte alignment
        }

        print(`Captured microcode ${sig_name} (ucode size 0x${ucode_size.toString(16)})`);

        // Compute n64js-style microcode hash and surface it to the headless hook if present.
        try {
            const codeAddr = readU32(ucode_address) >>> 0;
            const codeBytes = readMemBlock(codeAddr, ucode_size);
            let hash = 0;
            for (const b of codeBytes) {
                hash = ((hash * 17) + b) >>> 0;
            }
            if (globalThis.__n64jsMicrocodeHook) {
                globalThis.__n64jsMicrocodeHook({ version: sig_name, hash, ucodeSize: ucode_size });
            }
        } catch (err) {
            console.warn('Failed to compute microcode hash', err);
        }
    }

    function FindOverlayTableEntriesInMemory(start, end) {
        const matches = [];

        let possibleFind = 0;
        let numEntries = 0;
        let startAddress = 0;
        let totalSize = 0;

        // Loop through memory 4 bytes at a time.
        for (let i = start; i < end; i += 4) {
            if (RAM[i] === 0 && RAM[i + 1] === 0) {
                const code_offset = (RAM[i + 2] << 8) | RAM[i + 3];
                const overlay_size = (RAM[i + 4] << 8) | RAM[i + 5];
                if (overlay_size <= 0x1000) {
                    const lastNibble = RAM[i + 5] & 0xf;
                    if (lastNibble === 0x07 || lastNibble === 0x0f) {
                        const firstNibble = (RAM[i + 6] >> 4) & 0xf;
                        if (firstNibble === 0x1) {
                            numEntries++;
                            totalSize = Math.max(
                                totalSize,
                                code_offset + (overlay_size + 1)
                            );
                            if (possibleFind === 0) {
                                possibleFind = i;
                            } else {
                                if (i - possibleFind === 8) {
                                    startAddress = 0x80000000 + possibleFind;
                                    possibleFind = 1;
                                }
                            }
                            i += 4;
                            continue;
                        }
                    }
                }
            }

            if (numEntries > 1 && startAddress !== 0) {
                print(
                    `Found ${numEntries} possible overlay entries at address: 0x${startAddress.toString(
                        16
                    )}`
                );
                print(`Microcode size = 0x${totalSize.toString(16)}`);
                matches.push([startAddress, totalSize]);
            }

            totalSize = 0;
            startAddress = 0;
            numEntries = 0;
            possibleFind = 0;
        }

        return matches;
    }

    // Basic pattern matcher over RAM snapshot
    function findMatches(pattern) {
        const target_length = pattern.length;
        const target_length_m1 = target_length - 1;
        const matches = [];
        let matching = 0;

        for (let i = 0; i < RAM_SIZE; i += 8) {
            for (let j = 0; j < 8; j++) {
                const idx = i + j;
                if (idx >= RAM_SIZE) break;
                if (RAM[idx] === pattern[matching]) matching++;
                else matching = 0;
                if (matching === target_length) {
                    matches.push(idx - target_length_m1);
                    matching = 0;
                }
            }
        }
        return matches;
    }

    // Faster variant assuming 4-byte alignment
    function findMatchesFaster(pattern) {
        const target_length = pattern.length;
        const target_length_m1 = target_length - 1;
        const matches = [];
        let matching = 0;

        for (let i = 0; i < RAM_SIZE; i += 8) {
            // unrolled as in original code
            if (RAM[i] === pattern[matching]) matching++;
            else matching = 0;
            if (matching === target_length) {
                matches.push(i - target_length_m1);
                matching = 0;
            }
            if (matching > 0) {
                if (RAM[i + 1] === pattern[matching]) matching++;
                else matching = 0;
                if (matching === target_length) {
                    matches.push(i + 1 - target_length_m1);
                    matching = 0;
                }
                if (matching > 1) {
                    if (RAM[i + 2] === pattern[matching]) matching++;
                    else matching = 0;
                    if (matching === target_length) {
                        matches.push(i + 2 - target_length_m1);
                        matching = 0;
                    }
                    if (matching > 2) {
                        if (RAM[i + 3] === pattern[matching]) matching++;
                        else matching = 0;
                        if (matching === target_length) {
                            matches.push(i + 3 - target_length_m1);
                            matching = 0;
                        }
                    }
                }
            }

            if (RAM[i + 4] === pattern[matching]) matching++;
            else matching = 0;
            if (matching === target_length) {
                matches.push(i + 4 - target_length_m1);
                matching = 0;
            }
            if (matching > 0) {
                if (RAM[i + 5] === pattern[matching]) matching++;
                else matching = 0;
                if (matching === target_length) {
                    matches.push(i + 5 - target_length_m1);
                    matching = 0;
                }
                if (matching > 1) {
                    if (RAM[i + 6] === pattern[matching]) matching++;
                    else matching = 0;
                    if (matching === target_length) {
                        matches.push(i + 6 - target_length_m1);
                        matching = 0;
                    }
                    if (matching > 2) {
                        if (RAM[i + 7] === pattern[matching]) matching++;
                        else matching = 0;
                        if (matching === target_length) {
                            matches.push(i + 7 - target_length_m1);
                            matching = 0;
                        }
                    }
                }
            }
        }

        return matches;
    }

    // Specialised dual-pattern matcher for "RSP SW" / "RSP Gfx"
    function findMatchesFor2PatternsFast(patterns) {
        const target_lengths = [patterns[0].length, patterns[1].length];
        const target_lengths_m1 = [
            target_lengths[0] - 1,
            target_lengths[1] - 1,
        ];
        const matches = [[], []];
        const matching = [0, 0];

        for (let i = 0; i < RAM_SIZE; i += 8) {
            // pattern 0
            if (RAM[i] === patterns[0][matching[0]]) matching[0]++;
            else matching[0] = 0;
            if (matching[0] === target_lengths[0]) {
                matches[0].push(i - target_lengths_m1[0]);
                matching[0] = 0;
            }
            if (matching[0] > 0) {
                if (RAM[i + 1] === patterns[0][matching[0]]) matching[0]++;
                else matching[0] = 0;
                if (matching[0] === target_lengths[0]) {
                    matches[0].push(i + 1 - target_lengths_m1[0]);
                    matching[0] = 0;
                }
                if (matching[0] > 1) {
                    if (RAM[i + 2] === patterns[0][matching[0]]) matching[0]++;
                    else matching[0] = 0;
                    if (matching[0] === target_lengths[0]) {
                        matches[0].push(i + 2 - target_lengths_m1[0]);
                        matching[0] = 0;
                    }
                    if (matching[0] > 2) {
                        if (RAM[i + 3] === patterns[0][matching[0]]) matching[0]++;
                        else matching[0] = 0;
                        if (matching[0] === target_lengths[0]) {
                            matches[0].push(i + 3 - target_lengths_m1[0]);
                            matching[0] = 0;
                        }
                        if (matching[0] > 3) {
                            if (RAM[i + 4] === patterns[0][matching[0]]) matching[0]++;
                            else matching[0] = 0;
                            if (matching[0] === target_lengths[0]) {
                                matches[0].push(i + 4 - target_lengths_m1[0]);
                                matching[0] = 0;
                            }
                            if (matching[0] > 4) {
                                if (RAM[i + 5] === patterns[0][matching[0]]) matching[0]++;
                                else matching[0] = 0;
                                if (matching[0] === target_lengths[0]) {
                                    matches[0].push(i + 5 - target_lengths_m1[0]);
                                    matching[0] = 0;
                                }
                                if (matching[0] > 5) {
                                    if (RAM[i + 6] === patterns[0][matching[0]]) matching[0]++;
                                    else matching[0] = 0;
                                    if (matching[0] === target_lengths[0]) {
                                        matches[0].push(i + 6 - target_lengths_m1[0]);
                                        matching[0] = 0;
                                    }
                                    if (matching[0] > 6) {
                                        if (RAM[i + 7] === patterns[0][matching[0]]) matching[0]++;
                                        else matching[0] = 0;
                                        if (matching[0] === target_lengths[0]) {
                                            matches[0].push(i + 7 - target_lengths_m1[0]);
                                            matching[0] = 0;
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // pattern 1
            if (RAM[i] === patterns[1][matching[1]]) matching[1]++;
            else matching[1] = 0;
            if (matching[1] === target_lengths[1]) {
                matches[1].push(i - target_lengths_m1[1]);
                matching[1] = 0;
            }
            if (matching[1] > 0) {
                if (RAM[i + 1] === patterns[1][matching[1]]) matching[1]++;
                else matching[1] = 0;
                if (matching[1] === target_lengths[1]) {
                    matches[1].push(i + 1 - target_lengths_m1[1]);
                    matching[1] = 0;
                }
                if (matching[1] > 1) {
                    if (RAM[i + 2] === patterns[1][matching[1]]) matching[1]++;
                    else matching[1] = 0;
                    if (matching[1] === target_lengths[1]) {
                        matches[1].push(i + 2 - target_lengths_m1[1]);
                        matching[1] = 0;
                    }
                    if (matching[1] > 2) {
                        if (RAM[i + 3] === patterns[1][matching[1]]) matching[1]++;
                        else matching[1] = 0;
                        if (matching[1] === target_lengths[1]) {
                            matches[1].push(i + 3 - target_lengths_m1[1]);
                            matching[1] = 0;
                        }
                        if (matching[1] > 3) {
                            if (RAM[i + 4] === patterns[1][matching[1]]) matching[1]++;
                            else matching[1] = 0;
                            if (matching[1] === target_lengths[1]) {
                                matches[1].push(i + 4 - target_lengths_m1[1]);
                                matching[1] = 0;
                            }
                            if (matching[1] > 4) {
                                if (RAM[i + 5] === patterns[1][matching[1]]) matching[1]++;
                                else matching[1] = 0;
                                if (matching[1] === target_lengths[1]) {
                                    matches[1].push(i + 5 - target_lengths_m1[1]);
                                    matching[1] = 0;
                                }
                                if (matching[1] > 5) {
                                    if (RAM[i + 6] === patterns[1][matching[1]]) matching[1]++;
                                    else matching[1] = 0;
                                    if (matching[1] === target_lengths[1]) {
                                        matches[1].push(i + 6 - target_lengths_m1[1]);
                                        matching[1] = 0;
                                    }
                                    if (matching[1] > 6) {
                                        if (RAM[i + 7] === patterns[1][matching[1]]) matching[1]++;
                                        else matching[1] = 0;
                                        if (matching[1] === target_lengths[1]) {
                                            matches[1].push(i + 7 - target_lengths_m1[1]);
                                            matching[1] = 0;
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        return matches;
    }

    function processF3DEX2(sig_offset, sig_name) {
        let actual_ucode_size = 0;
        const startOfDataCode = ALIGN_16_BYTES(sig_offset) - 0x130;

        const overlayEntries = FindOverlayTableEntriesInMemory(
            startOfDataCode,
            startOfDataCode + 0x800
        );

        if (!overlayEntries || overlayEntries.length === 0) {
            print('No overlay entries could be found for F3DEX2. :(');
            return false;
        }

        for (let i = 0; i < overlayEntries.length; i++) {
            actual_ucode_size = Math.max(actual_ucode_size, overlayEntries[i][1]);
        }

        const DataLocationMatches = findMatchesFaster(
            intToByteArray(0x80000000 + startOfDataCode)
        );

        print('Finding OSTask structures...');
        if (DataLocationMatches.length > 0) {
            let hasDumpedMicrocode = false;
            for (let i = 0; i < DataLocationMatches.length; i++) {
                const osTaskAddress = 0x80000000 + (DataLocationMatches[i] - 0x18);
                const aMatch = readU32(osTaskAddress);
                if (aMatch === 1) {
                    print(`Found OSTask structure at 0x${osTaskAddress.toString(16)}`);
                    current_indent += 2;

                    if (!hasDumpedMicrocode) {
                        DumpMicrocode(osTaskAddress, actual_ucode_size, sig_name);
                        hasDumpedMicrocode = true;
                    }

                    DumpOSTaskStructure(osTaskAddress, sig_name);

                    current_indent -= 2;
                    return true;
                }
            }
        } else {
            print('No OSTask structure was found for this signature.');
            current_indent += 2;
            DumpDataToNoFindFolder(
                0x80000000 + startOfDataCode,
                sig_name,
                actual_ucode_size
            );
            if (nextMicrocodeStart !== 0) {
                nextMicrocodeStart += actual_ucode_size;
            }
            current_indent -= 2;
            return true;
        }

        return false;
    }

    function findOSTaskStructureFromSignatureLocation(sig_offset, sig_name) {
        print('Finding overlays table...');

        let actual_ucode_size = 0;
        let overlays_table_location = 0;

        for (let i = 0; i < 0x100; i++) {
            const test_location = sig_offset - i * 8;
            const main_offset = readIntFromRAM(test_location);

            if (main_offset === 0) {
                const size = readShortFromRAM(test_location + 4) + 1;
                const offset = readShortFromRAM(test_location + 6);
                if (offset > 0x0fff && offset < 0x2000 && size < 0x1000) {
                    const second_main_offset = readIntFromRAM(test_location + 8);
                    const second_size = readShortFromRAM(test_location + 12);
                    const second_offset = readShortFromRAM(test_location + 14);
                    if (
                        second_offset > 0x0fff &&
                        second_offset < 0x2000 &&
                        second_size < 0x1000
                    ) {
                        overlays_table_location = test_location;
                        print(
                            `Found overlays table at 0x${(
                                0x80000000 + overlays_table_location
                            ).toString(16)}`
                        );
                        actual_ucode_size = readOverlayTableToGetSizeOfMicrocode(
                            overlays_table_location
                        );
                        break;
                    }
                }
            }
        }

        if (overlays_table_location === 0) {
            const isActuallyF3DEX2 = processF3DEX2(sig_offset, sig_name);
            if (!isActuallyF3DEX2) {
                print('Failed. :(');
            }
            return;
        }

        print(
            `Size of graphics microcode = 0x${actual_ucode_size.toString(16)}`
        );
        print('Finding OSTask structures...');

        const overlays_table_location_pattern = [
            0x80,
            (overlays_table_location >> 16) & 0xff,
            (overlays_table_location >> 8) & 0xff,
            overlays_table_location & 0xff,
        ];

        const DataLocationMatches = findMatchesFaster(
            overlays_table_location_pattern
        );
        let hasDumpedMicrocode = false;

        if (DataLocationMatches.length > 0) {
            for (let i = 0; i < DataLocationMatches.length; i++) {
                const osTaskAddress = 0x80000000 + (DataLocationMatches[i] - 0x18);
                const aMatch = readU32(osTaskAddress);
                if (aMatch === 1) {
                    print(`Found OSTask structure at ${osTaskAddress.toString(16)}`);
                    current_indent += 2;
                    if (!hasDumpedMicrocode) {
                        DumpMicrocode(osTaskAddress, actual_ucode_size, sig_name);
                        hasDumpedMicrocode = true;
                    }
                    DumpOSTaskStructure(osTaskAddress, sig_name);
                    current_indent -= 2;
                }
            }
        } else {
            print('No OSTask structure was found for this signature.');
            current_indent += 2;
            DumpDataToNoFindFolder(
                0x80000000 + overlays_table_location,
                sig_name,
                actual_ucode_size
            );
            if (nextMicrocodeStart !== 0) {
                nextMicrocodeStart += actual_ucode_size;
            }
            current_indent -= 2;
        }
    }

    function findAndDumpMicrocodesFromDataAddressAndMicrocodeSize(matches) {
        let OSTaskAddress = 0;
        let matchWithOSTask = -1;

        let breakThisEarly = false;

        print('Finding an OSTask structure...');
        current_indent += 2;

        for (let i = 0; i < matches.length; i++) {
            const startAddress = matches[i][0];

            const location_pattern = [
                0x80,
                (startAddress >> 16) & 0xff,
                (startAddress >> 8) & 0xff,
                startAddress & 0xff,
            ];

            const DataLocationMatches = findMatchesFaster(location_pattern);

            if (DataLocationMatches.length > 0) {
                for (let j = 0; j < DataLocationMatches.length; j++) {
                    const osTaskAddress = 0x80000000 + (DataLocationMatches[j] - 0x18);
                    const aMatch = readU32(osTaskAddress);
                    if (aMatch === 1) {
                        print(
                            `Found OSTask structure at 0x${osTaskAddress.toString(
                                16
                            )} for data 0x${startAddress.toString(16)}`
                        );
                        matchWithOSTask = i;
                        OSTaskAddress = osTaskAddress;
                        breakThisEarly = true;
                        break;
                    }
                }
            } else {
                print(
                    `No OSTask structure was found for data 0x${startAddress.toString(
                        16
                    )}`
                );
            }

            if (breakThisEarly) break;
        }

        if (OSTaskAddress === 0) {
            console.log('Could not find any OSTask structures for the microcode :(');
            current_indent -= 2;
            return;
        }
        current_indent -= 2;

        print('Processing Microcode from the OSTask structure...');
        current_indent += 2;
        DumpMicrocode(OSTaskAddress, matches[matchWithOSTask][1], 'NoSignature');
        DumpOSTaskStructure(OSTaskAddress, 'NoSignature');
        current_indent -= 2;

        print(
            'With the assumption that all microcodes are contiguous in memory,'
        );
        print(
            'now analyzing the other microcodes without any OSTask structures...'
        );
        current_indent += 2;

        if (matchWithOSTask === 0) {
            for (let i = 1; i < matches.length; i++) {
                if (nextMicrocodeStart !== 0) {
                    nextMicrocodeStart += matches[i][1];
                    if ((nextMicrocodeStart & 0x8) !== 0) nextMicrocodeStart += 8;
                    DumpDataToNoFindFolder(
                        matches[i][0],
                        'NoSignature',
                        matches[i][1]
                    );
                } else {
                    print('Error: nextMicrocodeStart is 0. (matchWithOSTask == 0)');
                    break;
                }
            }
        } else if (matchWithOSTask === matches.length - 1) {
            nextMicrocodeStart -= matches[matchWithOSTask][1];
            nextMicrocodeStart =
                0x80000000 + ALIGN_16_BYTES(nextMicrocodeStart & 0x7fffffff);
            for (let i = matches.length - 2; i >= 0; i--) {
                if (nextMicrocodeStart !== 0) {
                    nextMicrocodeStart -= matches[i][1];
                    nextMicrocodeStart =
                        0x80000000 + ALIGN_16_BYTES(nextMicrocodeStart & 0x7fffffff);
                    DumpDataToNoFindFolder(
                        matches[i][0],
                        'NoSignature',
                        matches[i][1]
                    );
                } else {
                    print(
                        'Error: nextMicrocodeStart is 0. (matchWithOSTask == matches.length - 1)'
                    );
                    break;
                }
            }
        } else {
            const savedNextMicrocodeStart = nextMicrocodeStart;

            nextMicrocodeStart -= matches[matchWithOSTask][1];
            nextMicrocodeStart =
                0x80000000 + ALIGN_16_BYTES(nextMicrocodeStart & 0x7fffffff);
            for (let i = matchWithOSTask - 1; i >= 0; i--) {
                if (nextMicrocodeStart !== 0) {
                    nextMicrocodeStart -= matches[i][1];
                    nextMicrocodeStart =
                        0x80000000 + ALIGN_16_BYTES(nextMicrocodeStart & 0x7fffffff);
                    DumpDataToNoFindFolder(
                        matches[i][0],
                        'NoSignature',
                        matches[i][1]
                    );
                } else {
                    print(
                        'Error: nextMicrocodeStart is 0. (matchWithOSTask == matches.length - 1)'
                    );
                    break;
                }
            }

            nextMicrocodeStart = savedNextMicrocodeStart;
            for (let i = matchWithOSTask + 1; i < matches.length; i++) {
                if (nextMicrocodeStart !== 0) {
                    nextMicrocodeStart += matches[i][1];
                    if ((nextMicrocodeStart & 0x8) !== 0) nextMicrocodeStart += 8;
                    DumpDataToNoFindFolder(
                        matches[i][0],
                        'NoSignature',
                        matches[i][1]
                    );
                } else {
                    print('Error: nextMicrocodeStart is 0. (matchWithOSTask == 0)');
                    break;
                }
            }
        }

        current_indent -= 2;
    }

    // === main() equivalent ===
    print(`Finding microcode signatures in "${ROM_NAME}"...`);

    let matches2 = findMatchesFor2PatternsFast(signatures);
    let foundNoMatches = true;

    for (let i = 0; i < signatures.length; i++) {
        for (let j = 0; j < matches2[i].length; j++) {
            if (matches2[i].length > 0) {
                const matched_offset = matches2[i][j]; // RAM offset
                const matched_addr = 0x80000000 + matched_offset;
                const signature_name = readString(matched_addr).replace(/\//g, ' ');
                print(
                    `Found signature "${signature_name}" at address 0x${matched_addr.toString(
                        16
                    )}`
                );
                foundNoMatches = false;
                current_indent += 2;
                findOSTaskStructureFromSignatureLocation(
                    matched_offset,
                    `${signature_name}(${matched_addr.toString(16)})`
                );
                current_indent -= 2;
            }
        }
    }

    if (foundNoMatches) {
        print(
            'Could not find any signatures. Trying a more precise (and slower) function...'
        );

        const f3dexMatches = findMatches(signatures[1]); // "RSP Gfx"
        if (f3dexMatches.length > 0) {
            for (let i = 0; i < f3dexMatches.length; i++) {
                const matched_offset = f3dexMatches[i];
                const matched_addr = 0x80000000 + matched_offset;
                const signature_name = readString(matched_addr).replace(/\//g, ' ');
                print(
                    `Found signature "${signature_name}" at address 0x${matched_addr.toString(
                        16
                    )}`
                );
                foundNoMatches = false;
                current_indent += 2;
                findOSTaskStructureFromSignatureLocation(
                    ALIGN_8_BYTES(matched_offset),
                    `${signature_name}(${matched_addr.toString(16)})`
                );
                current_indent -= 2;
            }
        }
    }

    if (foundNoMatches) {
        print('Could not find any signatures at all. :(');

        print('Looking for possible overlay table entries...');

        const entries = FindOverlayTableEntriesInMemory(0, 4 * 1024 * 1024);

        if (entries.length > 0) {
            print(`Found ${entries.length} possible overlay tables in RAM.`);
            findAndDumpMicrocodesFromDataAddressAndMicrocodeSize(entries);
        } else {
            print('No overlay table entries could be found. :(');
        }
    }

    print('Done.');
}
