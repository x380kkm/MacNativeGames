#!/usr/bin/env python3
"""The file formats of Tears of the Kingdom's RomFS, for the scripts that make mods from the player's own files
(make_button_icons.py, make_gameplay_tuning.py). It works on bytes in memory and writes no file. Python 3.14 (compression.zstd).

zstd: Pack/ZsDic.pack.zs is a zstd-compressed SARC of the game's dictionaries, and each frame header names the dictionary
its file was compressed with (id 1 zs.zsdic, id 3 pack.zsdic in 1.4.3). A replacement is compressed with the same
dictionary and declares its content size: the game's decompressor has no other way to learn it (docs/mods.md, "Three
packaging traps").

SARC: the member table (name -> byte range), and a repack that replaces one member and keeps the others byte-identical,
in their original order and alignment.

BYML v7, little-endian ("YB"): where a value sits. Hash (0xC1) and array (0xC0) nodes keep ints (0xD1) and floats (0xD2)
inline in a 4-byte field, so such a value changes in place and the document keeps its size. There is no BYML writer here:
adding a key or changing a node's shape is not covered.
"""
import struct
import sys
from collections import namedtuple

try:
    import compression.zstd as zstd
except ImportError:
    sys.exit('needs Python 3.14 (compression.zstd): run it with python3.14')

ZSDIC_PACK = 'Pack/ZsDic.pack.zs'
LEVEL = 19   # what make_romfs_patches.py and make_output_res_overlay.py compress their overlays with
ZSTD_MAGIC = b'\x28\xb5\x2f\xfd'
UNREADABLE = (AssertionError, IndexError, KeyError, ValueError, struct.error, zstd.ZstdError)   # what a damaged file raises here


def zstd_dictionaries(zsdic_pack):
    """Dictionary id -> zstd.ZstdDict of each dictionary in Pack/ZsDic.pack.zs, given that file's stored bytes. Raises
    ValueError when those bytes are not a zstd frame."""
    try:
        pack = zstd.decompress(zsdic_pack)
    except zstd.ZstdError as error:
        raise ValueError(f'not a readable zstd frame: {error}') from error
    dictionaries = {}
    for lo, hi in sarc_members(pack).values():
        dictionary = zstd.ZstdDict(pack[lo:hi])
        dictionaries[dictionary.dict_id] = dictionary
    return dictionaries


FrameHeader = namedtuple('FrameHeader', 'dictionary_id content_size checksum')
FrameHeader.__doc__ = """The header of a zstd frame: dictionary id (0: none), declared content size (None: not declared), and
    whether a checksum follows the data."""


def frame_header(raw):
    """The FrameHeader of the zstd frame at the start of `raw`."""
    if raw[:4] != ZSTD_MAGIC:
        raise ValueError('not a zstd frame')
    info = zstd.get_frame_info(raw)
    descriptor = raw[4]
    return FrameHeader(info.dictionary_id, info.decompressed_size, bool(descriptor & 0x04))


def decompress(raw, dictionaries):
    """The bytes of the zstd file `raw`, with the dictionary its frame names. A frame that does not declare its size is
    refused, since the game cannot load one."""
    try:
        header = frame_header(raw)
        if header.dictionary_id and header.dictionary_id not in dictionaries:
            raise ValueError(f'zstd dictionary {header.dictionary_id} is not in {ZSDIC_PACK}')
        data = zstd.decompress(raw, zstd_dict=dictionaries[header.dictionary_id] if header.dictionary_id else None)
    except zstd.ZstdError as error:
        raise ValueError(f'not a readable zstd frame: {error}') from error
    if header.content_size != len(data):
        raise ValueError(f'the zstd frame declares {header.content_size} bytes and holds {len(data)}')
    return data


def compress_like(data, original, dictionaries):
    """`data` as a zstd file made the way the zstd file `original` is: the same dictionary and checksum setting, with the
    content size declared. Raises ValueError when the result is not that, or does not decompress to `data`."""
    want = frame_header(original)
    options = {zstd.CompressionParameter.compression_level: LEVEL, zstd.CompressionParameter.checksum_flag: int(want.checksum)}
    raw = zstd.compress(data, options=options, zstd_dict=dictionaries[want.dictionary_id] if want.dictionary_id else None)
    got = frame_header(raw)
    if (got.dictionary_id, got.content_size, got.checksum) != (want.dictionary_id, len(data), want.checksum):
        raise ValueError(f'the zstd frame came out as {got}, not as {want} with {len(data)} bytes')
    if decompress(raw, dictionaries) != data:
        raise ValueError('the zstd frame does not decompress to its input')
    return raw


def sarc_members(data):
    """Name -> (absolute start, end) of every SARC member."""
    assert data[:4] == b'SARC' and data[6:8] == b'\xff\xfe'
    header, size, start = struct.unpack_from('<HxxII', data, 4)
    assert size == len(data) and data[header:header + 4] == b'SFAT'
    count = struct.unpack_from('<H', data, header + 6)[0]; names = header + 12 + count * 16
    assert data[names:names + 4] == b'SFNT'; names += 8
    out = {}
    for i in range(count):
        _, attribute, lo, hi = struct.unpack_from('<4I', data, header + 12 + i * 16)
        offset = names + (attribute & 0xffffff) * 4
        out[data[offset:data.index(0, offset, start)].decode()] = (start + lo, start + hi)
    return out


def repack(sarc, name, blob):
    """The SARC with member `name` replaced by `blob`, every other member byte-identical, in the original order and alignment."""
    start = struct.unpack_from('<I', sarc, 12)[0]
    fat = 0x14; count = struct.unpack_from('<H', sarc, fat + 6)[0]
    nodes = [list(struct.unpack_from('<4I', sarc, fat + 12 + i * 16)) for i in range(count)]
    members = sarc_members(sarc); by_range = {(lo, hi): k for k, (lo, hi) in members.items()}
    blobs = [blob if by_range[(start + n[2], start + n[3])] == name else sarc[start + n[2]:start + n[3]] for n in nodes]

    def alignment(offset):
        a = 1
        while offset % (a * 2) == 0 and a < 0x2000:
            a *= 2
        return a
    data, placed = bytearray(), {}
    for i in sorted(range(count), key=lambda i: nodes[i][2]):
        a = alignment(nodes[i][2]) if nodes[i][2] else 1
        while len(data) % a:
            data += b'\0'
        placed[i] = (len(data), len(data) + len(blobs[i])); data += blobs[i]
    head = bytearray(sarc[:start])
    for i in range(count):
        struct.pack_into('<II', head, fat + 12 + i * 16 + 8, *placed[i])
    out = bytearray(bytes(head) + bytes(data)); struct.pack_into('<I', out, 8, len(out)); out = bytes(out)
    check = sarc_members(out)
    for k, (lo, hi) in members.items():
        assert out[check[k][0]:check[k][1]] == (blob if k == name else sarc[lo:hi]), k
    return out


class Byml:
    """A BYML v7 little-endian document, read for where its values sit: nodes and 4-byte fields are offsets into `data`."""
    STRING, HASH, ARRAY, STRING_TABLE, INT, FLOAT = 0xa0, 0xc1, 0xc0, 0xc2, 0xd1, 0xd2

    def __init__(self, data):
        if data[:2] != b'YB' or struct.unpack_from('<H', data, 2)[0] != 7:
            raise ValueError('not a little-endian BYML v7 document')
        self.data = data
        keys, strings, self.root = struct.unpack_from('<III', data, 4)
        self.keys, self.strings = self._string_table(keys), self._string_table(strings)

    def _u32(self, at):
        return struct.unpack_from('<I', self.data, at)[0]

    def _count(self, node, kind):
        """The element count of the node at `node`, which must be of `kind`."""
        if self.data[node] != kind:
            raise ValueError(f'BYML node at {node:#x} is of kind {self.data[node]:#x}, not {kind:#x}')
        return self._u32(node) >> 8

    def _string_table(self, table):
        if not table:
            return []
        count = self._count(table, self.STRING_TABLE)
        offsets = struct.unpack_from(f'<{count}I', self.data, table + 4)
        return [self.data[table + o:self.data.index(0, table + o)].decode() for o in offsets]

    def entries(self, node):
        """Key -> (value kind, offset of its 4-byte field) of the hash node `node`."""
        out = {}
        for i in range(self._count(node, self.HASH)):
            entry = node + 4 + 8 * i
            out[self.keys[self._u32(entry) & 0xffffff]] = (self.data[entry + 3], entry + 4)
        return out

    def items(self, node):
        """(value kind, offset of its 4-byte field) of each element of the array node `node`."""
        count = self._count(node, self.ARRAY)
        fields = node + 4 + (count + 3 & ~3)   # the kinds, one byte each, padded to 4
        return [(self.data[node + 4 + i], fields + 4 * i) for i in range(count)]

    def field(self, node, key, kind):
        """The offset of the 4-byte field of `key` in the hash node `node`, which must hold a value of `kind`."""
        got, at = self.entries(node)[key]
        if got != kind:
            raise ValueError(f'BYML key {key} holds kind {got:#x}, not {kind:#x}')
        return at

    def child(self, node, key, kind=HASH):
        """The node that `key` of the hash node `node` refers to, which must be of `kind`."""
        return self._u32(self.field(node, key, kind))

    def string(self, field):
        """The string a field of kind STRING refers to."""
        return self.strings[self._u32(field)]
