"""Small stand-ins for the game's files, made from scratch for the mod script tests: BYML v7 documents and zstd
dictionaries with a chosen id. No game data."""
import struct

import compression.zstd as zstd


def byml(root):
    """A little-endian BYML v7 document holding `root`: dicts, lists, ints, floats, bools and strings, the layout
    games/totk/scripts/romfs_formats.py reads (keys and strings in sorted tables, hash entries in key order)."""
    keys, strings = set(), set()

    def collect(value):
        if isinstance(value, dict):
            keys.update(value)
        if isinstance(value, (dict, list)):
            for item in (value.values() if isinstance(value, dict) else value):
                collect(item)
        elif isinstance(value, str):
            strings.add(value)
    collect(root)
    keys, strings = sorted(keys), sorted(strings)

    def table(names):
        head = 4 + 4 * (len(names) + 1)
        offsets, blob = [], b''
        for name in names:
            offsets.append(head + len(blob)); blob += name.encode() + b'\0'
        offsets.append(head + len(blob))
        out = struct.pack('<I', 0xc2 | len(names) << 8) + struct.pack(f'<{len(offsets)}I', *offsets) + blob
        return out + b'\0' * (-len(out) % 4)

    key_table, string_table = table(keys), table(strings)
    out = bytearray(b'YB' + struct.pack('<HIII', 7, 16, 16 + len(key_table), 0) + key_table + string_table)

    def field(value):
        """(kind, 4-byte field) of a value; a dict or a list is written after everything before it."""
        if isinstance(value, dict):
            return 0xc1, node(value)
        if isinstance(value, list):
            return 0xc0, node(value)
        if isinstance(value, bool):
            return 0xd0, int(value)
        if isinstance(value, int):
            return 0xd1, value & 0xffffffff
        if isinstance(value, float):
            return 0xd2, struct.unpack('<I', struct.pack('<f', value))[0]
        return 0xa0, strings.index(value)

    def node(value):
        at = len(out)
        if isinstance(value, dict):
            items = sorted(value.items(), key=lambda item: keys.index(item[0]))
            out.extend(struct.pack('<I', 0xc1 | len(items) << 8) + bytes(8 * len(items)))
            for i, (key, item) in enumerate(items):
                kind, data = field(item)
                struct.pack_into('<II', out, at + 4 + 8 * i, keys.index(key) | kind << 24, data)
        else:
            types = (len(value) + 3) & ~3
            out.extend(struct.pack('<I', 0xc0 | len(value) << 8) + bytes(types + 4 * len(value)))
            for i, item in enumerate(value):
                kind, data = field(item)
                out[at + 4 + i] = kind
                struct.pack_into('<I', out, at + 4 + types + 4 * i, data)
        return at

    struct.pack_into('<I', out, 12, node(root))
    return bytes(out)


def zstd_dictionary(dictionary_id):
    """The bytes of a small trained zstd dictionary whose header carries `dictionary_id`."""
    samples = [f'sample {dictionary_id} {i} '.encode() * (i % 7 + 1) + bytes(range(i % 251)) for i in range(400)]
    content = bytearray(zstd.train_dict(samples, 4096).dict_content)
    struct.pack_into('<I', content, 4, dictionary_id)
    return bytes(content)
