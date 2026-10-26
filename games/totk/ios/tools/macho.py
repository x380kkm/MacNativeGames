#!/usr/bin/env python3
"""The parts of the app's executable (a thin 64-bit ARM Mach-O) the tools without Xcode read, with the standard library
only: its load commands, its sections with their file offsets and sizes, its defined symbols, pointers as chained fixups
store them (formats 2 and 6), and the ios_embed table gen_embed.py compiles into it, whose SHA-256 values
runtime/loader.c checks the nine module sections against.

recover_ipa.py reads an old app's tables and sections with it, package_ipa_windows.py the sections it writes the modules
into, sign_ipa_windows.py the code signature."""
import struct

import gen_embed   # the names of the module sections (section_names) and their order (PARTS)

LC_SEGMENT_64, LC_SYMTAB, LC_CODE_SIGNATURE, LC_DYLD_CHAINED_FIXUPS = 0x19, 0x2, 0x1d, 0x80000034
ZERO_FILL = {0x1, 0xc, 0x12}   # S_ZEROFILL, S_GB_ZEROFILL, S_THREAD_LOCAL_ZEROFILL: sections without bytes in the file


class MachOError(ValueError):
    pass


def u32(data, off):
    return struct.unpack_from('<I', data, off)[0]


def load_commands(data):
    """(command, offset, size) of each load command of a thin 64-bit Mach-O."""
    if len(data) < 32 or u32(data, 0) != 0xfeedfacf:
        raise MachOError('the executable is not a thin 64-bit Mach-O')
    off = 32
    for _ in range(u32(data, 16)):
        cmd, size = struct.unpack_from('<II', data, off)
        yield cmd, off, size
        off += size


class MachO:
    """A thin arm64 executable: segments [(name, vm address, file offset, file size)], sections {(segment, section):
    (file offset, size)} (offset 0 for a zero-fill section), defined symbols {name: address}."""
    def __init__(self, data):
        self.data = data
        if len(data) < 32 or struct.unpack_from('<Ii', data) != (0xfeedfacf, 0x0100000c):
            raise MachOError('the executable is not a thin 64-bit ARM Mach-O')
        self.segments, self.sections, self.symbols, symtab, fixups = [], {}, {}, None, None
        for cmd, off, _ in load_commands(data):
            if cmd == LC_SEGMENT_64:
                vm, _, fileoff, filesize, _, _, nsects, _ = struct.unpack_from('<QQQQiiII', data, off + 24)
                self.segments.append((bytes(data[off + 8:off + 24]).rstrip(b'\0').decode(), vm, fileoff, filesize))
                for s in range(off + 72, off + 72 + 80 * nsects, 80):
                    size, fo = struct.unpack_from('<QI', data, s + 40)
                    flags = u32(data, s + 64)
                    key = (bytes(data[s + 16:s + 32]).rstrip(b'\0').decode(), bytes(data[s:s + 16]).rstrip(b'\0').decode())
                    self.sections[key] = (0 if flags & 0xff in ZERO_FILL else fo, size)
            elif cmd == LC_SYMTAB:
                symtab = struct.unpack_from('<IIII', data, off + 8)
            elif cmd == LC_DYLD_CHAINED_FIXUPS:
                fixups = u32(data, off + 8)
        if symtab:
            symoff, nsyms, stroff, _ = symtab
            for i in range(nsyms):
                strx, ntype, _, _, value = struct.unpack_from('<IBBHQ', data, symoff + 16 * i)
                if ntype & 0xe0 == 0 and ntype & 0x0e == 0x0e:   # a defined symbol, not a debug entry
                    end = data.index(b'\0', stroff + strx)
                    self.symbols[bytes(data[stroff + strx:end]).decode(errors='replace')] = value
        self.base = next((vm for name, vm, _, _ in self.segments if name == '__TEXT'), 0)
        # dyld_chained_starts_in_segment.pointer_format: 2 DYLD_CHAINED_PTR_64 (target is an address), 6 _64_OFFSET
        # (target is an offset from the image base); both keep it in the low 36 bits and the top byte in bits 36..43.
        formats = set()
        if fixups is not None:
            starts = fixups + u32(data, fixups + 4)
            for i in range(u32(data, starts)):
                seg = u32(data, starts + 4 + 4 * i)
                if seg:
                    formats.add(struct.unpack_from('<H', data, starts + seg + 6)[0])
        if len(formats) > 1 or not formats <= {2, 6}:
            raise MachOError(f'the executable uses chained pointer formats {sorted(formats)}; this reads 2 and 6')
        self.pointer_format = formats.pop() if formats else None

    def at(self, vm, size):
        """The file offset of size bytes at a virtual address."""
        for _, start, fileoff, filesize in self.segments:
            if start <= vm and vm + size <= start + filesize:
                return fileoff + vm - start
        raise MachOError(f'{vm:#x}: not in the executable file')

    def read(self, vm, size):
        return bytes(self.data[self.at(vm, size):self.at(vm, size) + size]) if size else b''

    def u32(self, vm):
        return u32(self.read(vm, 4), 0)

    def u64(self, vm):
        return struct.unpack('<Q', self.read(vm, 8))[0]

    def pointer(self, vm):
        """The address a pointer at vm holds once dyld has rebased it."""
        raw = self.u64(vm)
        if self.pointer_format is None:
            return raw
        if raw >> 63:
            raise MachOError(f'{vm:#x}: a bound pointer (to another image) where the executable\'s own data is expected')
        target = (raw & 0xfffffffff) | ((raw >> 36) & 0xff) << 56
        return self.base + target if self.pointer_format == 6 else target

    def cstring(self, vm):
        off = self.at(vm, 1)
        return bytes(self.data[off:self.data.index(b'\0', off)]).decode()

    def symbol(self, name):
        if name not in self.symbols:
            raise MachOError(f'the executable has no symbol {name}' + ('' if self.symbols else ' (it has no symbol table: stripped)'))
        return self.symbols[name]

    def section_bytes(self, segment, section):
        """The bytes of a section the file holds."""
        offset, size = self.sections.get((segment, section), (None, 0))
        if not offset:
            raise MachOError(f'the executable has no {segment},{section} section'
                             + (' in the file (zero-fill)' if offset == 0 else ''))
        return bytes(self.data[offset:offset + size])


def module_sections(name):
    """{part: (segment, section)} of a module's three sections x0, w and x1, as gen_embed.py names them."""
    return {part: tuple(s.split(',')) for part, s in zip(gen_embed.PARTS, gen_embed.section_names(name))}


def embed_hashes(exe, names):
    """name -> {x0, w, x1} of a MachO: the ios_embed table of ios_embed.h (gen_embed.py), rows of four string pointers
    {name, x0, w, x1} holding the SHA-256 of each module section."""
    at = exe.symbol('_ios_embed')
    rows = [[exe.cstring(exe.pointer(at + 32 * i + 8 * k)) for k in range(4)] for i in range(len(names))]
    if sorted(r[0] for r in rows) != sorted(names):
        raise MachOError(f'_ios_embed names {[r[0] for r in rows]}, not {list(names)}')
    return {r[0]: dict(x0=r[1], w=r[2], x1=r[3]) for r in rows}
