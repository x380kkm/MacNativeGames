"""games/totk/scripts/romfs_formats.py: zstd with the game's dictionaries, SARC and in-place BYML fields, on bytes made here."""
import importlib.util
import struct
import sys
import unittest
from pathlib import Path

HAS_ZSTD = importlib.util.find_spec('compression.zstd') is not None   # Python 3.14
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'games/totk/scripts'))
sys.path.insert(0, str(ROOT/'tests'))


@unittest.skipUnless(HAS_ZSTD, 'needs Python 3.14 (compression.zstd)')
class Formats(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import compression.zstd as zstd
        import romfs_formats
        from romfs_fixtures import byml, zstd_dictionary
        from test_mod_manifest import sarc
        cls.zstd, cls.formats, cls.byml, cls.sarc = zstd, romfs_formats, staticmethod(byml), staticmethod(sarc)
        cls.pack = zstd.compress(sarc({'zs.zsdic': zstd_dictionary(1), 'pack.zsdic': zstd_dictionary(3)}))
        cls.dictionaries = romfs_formats.zstd_dictionaries(cls.pack)

    def test_the_dictionaries_come_by_their_id(self):
        self.assertEqual(sorted(self.dictionaries), [1, 3])

    def test_a_dictionary_pack_that_is_not_a_zstd_frame_is_refused(self):
        for raw in (bytes(64), self.pack[:20]):
            with self.subTest(raw=raw[:6]), self.assertRaises(ValueError):
                self.formats.zstd_dictionaries(raw)

    def test_a_replacement_keeps_the_dictionary_and_declares_its_size(self):
        data = b'stand-in pack ' * 200
        for dictionary_id in (1, 3):
            original = self.zstd.compress(data, level=3, zstd_dict=self.dictionaries[dictionary_id])
            raw = self.formats.compress_like(data[::-1], original, self.dictionaries)
            header = self.formats.frame_header(raw)
            self.assertEqual((header.dictionary_id, header.content_size, header.checksum), (dictionary_id, len(data), False))
            self.assertEqual(self.formats.decompress(raw, self.dictionaries), data[::-1])

    def test_a_file_without_a_dictionary_stays_without_one(self):
        original = self.zstd.compress(b'plain ' * 50, level=3)
        raw = self.formats.compress_like(b'other ' * 50, original, self.dictionaries)
        self.assertEqual(self.formats.frame_header(raw).dictionary_id, 0)
        self.assertEqual(self.formats.decompress(raw, {}), b'other ' * 50)

    def test_a_checksum_stays_when_the_original_has_one(self):
        checked = self.zstd.compress(b'plain ' * 50, options={self.zstd.CompressionParameter.checksum_flag: 1})
        self.assertTrue(self.formats.frame_header(checked).checksum)
        self.assertTrue(self.formats.frame_header(self.formats.compress_like(b'x' * 300, checked, {})).checksum)

    def test_what_the_game_cannot_load_is_refused(self):
        streamed = self.zstd.ZstdCompressor()
        no_size = streamed.compress(b'no declared size ' * 50) + streamed.flush()
        self.assertIsNone(self.formats.frame_header(no_size).content_size)
        other_dictionary = self.zstd.compress(b'x' * 300, zstd_dict=self.dictionaries[3])
        cut = self.zstd.compress(bytes(range(256)) * 20)[:40]
        for raw in (no_size, other_dictionary, b'not zstd', cut):
            with self.subTest(raw=raw[:6]), self.assertRaises(ValueError):
                self.formats.decompress(raw, {1: self.dictionaries[1]})

    def test_a_repack_replaces_one_member_and_keeps_the_others(self):
        members = {'a.bin': b'first' * 7, 'b.bin': b'second' * 9, 'c.bin': b'third'}
        original = self.sarc(members)
        out = self.formats.repack(original, 'b.bin', b'longer than before' * 11)
        ranges = self.formats.sarc_members(out)
        self.assertEqual(list(ranges), list(members))
        self.assertEqual(out[slice(*ranges['a.bin'])], members['a.bin'])
        self.assertEqual(out[slice(*ranges['c.bin'])], members['c.bin'])
        self.assertEqual(out[slice(*ranges['b.bin'])], b'longer than before' * 11)
        self.assertTrue(all(lo % 8 == 0 for lo, _ in ranges.values()))   # the original's alignment
        self.assertEqual(struct.unpack_from('<I', out, 8)[0], len(out))

    def test_a_value_changes_in_place(self):
        data = bytearray(self.byml({'MaxLife': 20, 'Name': 'sword', 'Rates': [1.0, 0.5], 'Inner': {'Rate': 2.5}, 'On': True}))
        doc = self.formats.Byml(bytes(data))
        self.assertEqual(struct.unpack_from('<i', data, doc.field(doc.root, 'MaxLife', doc.INT))[0], 20)
        self.assertEqual(doc.string(doc.field(doc.root, 'Name', doc.STRING)), 'sword')
        rates = doc.child(doc.root, 'Rates', doc.ARRAY)
        self.assertEqual([struct.unpack_from('<f', data, at)[0] for _, at in doc.items(rates)], [1.0, 0.5])
        self.assertEqual({kind for kind, _ in doc.items(rates)}, {doc.FLOAT})
        struct.pack_into('<f', data, doc.field(doc.child(doc.root, 'Inner'), 'Rate', doc.FLOAT), 7.5)
        again = self.formats.Byml(bytes(data))
        self.assertEqual(struct.unpack_from('<f', data, again.field(again.child(again.root, 'Inner'), 'Rate', again.FLOAT))[0], 7.5)

    def test_an_unexpected_shape_is_an_error(self):
        data = self.byml({'MaxLife': 20, 'Rates': [1.0]})
        doc = self.formats.Byml(data)
        with self.assertRaises(ValueError):
            doc.field(doc.root, 'MaxLife', doc.FLOAT)     # another kind of value: never written over
        with self.assertRaises(ValueError):
            doc.child(doc.root, 'Rates')                  # an array, not a hash
        with self.assertRaises(KeyError):
            doc.field(doc.root, 'Missing', doc.INT)
        for bad in (b'BY' + data[2:], data[:2] + struct.pack('<H', 6) + data[4:]):   # big-endian, another version
            with self.assertRaises(ValueError):
                self.formats.Byml(bad)


if __name__ == '__main__':
    unittest.main()
