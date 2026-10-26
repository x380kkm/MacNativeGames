"""games/totk/ios/tools/recover_ipa.py and recover_modules.py: the files they write read back as the build's own readers
read them, and the old app's export patches are undone. No game files.

With TOTK_RECOVERED=<the --out folder> the folder's files are also checked against its recover-manifest.json (romfs.bin
only with TOTK_RECOVERED_ROMFS=1: 17 GB to hash)."""
import hashlib
import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]/'games/totk/ios/tools'
sys.path.insert(0, str(TOOLS))
import recover_ipa  # noqa: E402
import recover_modules  # noqa: E402

LAYOUT = dict(name='main', patch_off=0x3af0000, key_off=0x3ae0000, text_end=0x2bb9c00, ro_off=0x2bba000, data_off=0x3569000)


def branch(pc, target):
    return 0x14000000 | (((target - pc) >> 2) & 0x3ffffff)


class LayoutFiles(unittest.TestCase):
    def test_fixups_read_back_as_gen_embed_and_prepare_runtime_read_them(self):
        text = ''.join(line + '\n' for line in recover_modules.fixups_lines(LAYOUT))
        header = dict(line[2:].split() for line in text.splitlines())   # gen_embed.py embed_modules
        self.assertEqual(int(header['TEXT_END'], 16), LAYOUT['text_end'])
        self.assertEqual(int(header['PATCH_OFF'], 16), LAYOUT['patch_off'])
        self.assertEqual(int(header['KEY_PAGE_OFF'], 16), LAYOUT['key_off'])
        layout = {}
        for line in text.splitlines():   # scripts/prepare_runtime.py
            _, key, value = line.split()
            layout[key] = int(value, 0)
        self.assertEqual(layout['DATA_OFF'], LAYOUT['data_off'])
        self.assertEqual(layout['KEY_PAGE_SIZE'], 0x4000)
        self.assertEqual([k for k in layout if k.startswith('KEY_K')][:2], ['KEY_K18_IDX', 'KEY_KTLS_IDX'])

    def test_text_files_end_lines_with_lf_on_every_system(self):
        with tempfile.TemporaryDirectory() as d:
            out = recover_ipa.Output(Path(d), {})
            out.text('build/game-data/v143/romfs-config.txt', ['ROMFS_IMAGE_SIZE 1', 'ROMFS_IMAGE_SHA256 ' + 'a' * 64], 'test')
            data = (Path(d)/'build/game-data/v143/romfs-config.txt').read_bytes()
            self.assertNotIn(b'\r', data)
            self.assertEqual(out.files['build/game-data/v143/romfs-config.txt']['sha256'], hashlib.sha256(data).hexdigest())

    def test_a_pinned_file_that_differs_is_not_written(self):
        with tempfile.TemporaryDirectory() as d:
            out = recover_ipa.Output(Path(d), {})
            with self.assertRaises(recover_modules.RecoverError):
                out.write('rewritten/v143/main.patched.bin', b'other', 'test', 'f' * 64)
            self.assertEqual(list(Path(d).rglob('*.bin')), [])

    def test_a_source_hash_is_the_committed_one_on_a_crlf_checkout(self):
        with tempfile.TemporaryDirectory() as d:
            lf, crlf = Path(d)/'lf.py', Path(d)/'crlf.py'
            lf.write_bytes(b'a = 1\nb = 2\n')
            crlf.write_bytes(b'a = 1\r\nb = 2\r\n')
            self.assertEqual(recover_ipa.source_sha256(crlf), hashlib.sha256(lf.read_bytes()).hexdigest())


class MainText(unittest.TestCase):
    """The export's patches are undone: listed sites from their originals, aspect sites from their stubs' first word, the
    veneers behind the text cleared, the read-only data after RO_OFF kept."""
    def test_patched_sites_and_veneers_are_put_back(self):
        layout = dict(text_end=0x1000, ro_off=0x1400)
        x0 = bytearray(0x4000)
        struct.pack_into('<I', x0, 0x100, 0x7100055f)              # a patched site
        struct.pack_into('<I', x0, 0x104, 0x22222222)              # a listed site left as it was
        stub = 0x1000 + recover_modules.ASPECT_STUBS
        struct.pack_into('<I', x0, stub, 0xbd414260)               # the aspect stub's copy of the site's instruction
        struct.pack_into('<I', x0, 0x200, branch(0x200, stub))
        x0[0x1010:0x1020] = b'\x55' * 16                           # another veneer
        x0[0x1400:0x1404] = b'RODA'
        text, restored = recover_modules.restore_main_text(bytes(x0), layout, {0x100: 0x6b08015f, 0x104: 0x22222222}, (0x200,))
        self.assertEqual(restored, [0x100, 0x200])
        self.assertEqual(struct.unpack_from('<I', text, 0x100)[0], 0x6b08015f)
        self.assertEqual(struct.unpack_from('<I', text, 0x200)[0], 0xbd414260)
        self.assertEqual(text[0x1000:0x1400], bytes(0x400))
        self.assertEqual(text[0x1400:0x1404], b'RODA')

    def test_branch_target(self):
        self.assertEqual(recover_modules.branch_target(branch(0x2000, 0x1000), 0x2000), 0x1000)
        self.assertEqual(recover_modules.branch_target(branch(0x1000, 0x5000), 0x1000), 0x5000)
        self.assertIsNone(recover_modules.branch_target(0xd63f03c0, 0x1000))


class Gates(unittest.TestCase):
    def module(self, image_size=0x30000):
        return dict(name='sdk', text_end=0x10000, patch_off=0x20000, file_size=image_size)

    def image(self, site, block):
        image = bytearray(0x30000)
        struct.pack_into('<I', image, site, branch(site, block))
        struct.pack_into('<I', image, block + 8, recover_modules.BLR_X30)
        return image

    def test_gates_of_the_image_are_kept_and_sorted(self):
        image = self.image(0x100, 0x20000)
        struct.pack_into('<I', image, 0x200, branch(0x200, 0x20020))
        struct.pack_into('<I', image, 0x20028, recover_modules.BLR_X30)
        m = self.module() | dict(gates=[(0x2002c, 0x200, 1, 3), (0x2000c, 0x100, 0, 0x85)])
        self.assertEqual(recover_modules.check_gates(bytes(image), m), [(0x2000c, 0x100, 0, 0x85), (0x2002c, 0x200, 1, 3)])

    def test_a_gate_whose_site_does_not_branch_there_stops(self):
        image = self.image(0x100, 0x20000)
        m = self.module() | dict(gates=[(0x2000c, 0x104, 0, 0x85)])
        with self.assertRaises(recover_modules.RecoverError):
            recover_modules.check_gates(bytes(image), m)


def adrp(pc, target, rd):
    imm = ((target & ~4095) - (pc & ~4095)) >> 12
    return 0x90000000 | ((imm & 3) << 29) | (((imm >> 2) & 0x7ffff) << 5) | rd


class Tables(unittest.TestCase):
    """runtime-tables.bin of recovered modules, written by scripts/prepare_runtime.py table_bytes in the layout
    runtime/loader.c load_tables reads."""
    def modules(self):
        out = []
        for name in recover_modules.NAMES:
            symbols = [('', 0, 0, 0, 0, 0), (f'{name}_sym', 0x10, 4, 1, 1, 2)]
            relocs = [(0x3000, 1027, 0, 0x10)]
            if name == 'main':
                symbols.append((recover_modules.GET_SYSTEM_TICK, 0, 0, 0, 1, 2)); relocs.append((0x3010, 1026, 2, 0))
            out.append(dict(name=name, digest='ab' * 32, file_size=0x50000, text_end=0x11000, ro_off=0x12000, data_off=0x3000,
                            patch_off=0x40000, key_off=0x30000, init=0x100, ctor_flag=0x3008, init_array=0, init_size=0,
                            symbols=symbols, relocs=relocs, gates=[(0x40010, 0x100, 0, 7)] if name == 'sdk' else []))
        return out

    def test_runtime_tables_have_the_layout_loader_c_reads(self):
        main_image = bytearray(0x12000)
        struct.pack_into('<IIII', main_image, 0x8000, adrp(0x8000, 0x3010, 16), 0xf9400211 | ((0x10 // 8) << 10), 0, 0xd61f0220)
        blob = recover_modules.runtime_tables(self.modules(), bytes(main_image))
        magic, version, nmodule, fmt, plt, slot, strings, strings_size, size = struct.unpack_from('<8s8sIIQQQQQ', blob)
        self.assertEqual((magic, version.rstrip(b'\0'), nmodule, fmt, size), (b'TOTKTAB1', b'v143', 3, 1, len(blob)))
        self.assertEqual((plt, slot), (0x8000, 0x3010))   # main's GetSystemTick slot and the PLT stub that loads it
        self.assertEqual(blob[strings + strings_size - 1], 0)
        for i, name in enumerate(recover_modules.NAMES):
            record = struct.unpack_from('<16s72s13Q4I', blob, 64 + 208 * i)
            self.assertEqual(record[0].rstrip(b'\0').decode(), name)
            self.assertEqual(record[2:12], (0x50000, 0x11000, 0x12000, 0x3000, 0x40000, 0x30000, 0x100, 0x3008, 0, 0))
            (symbols, relocs, gates), (nsym, nreloc, ngate) = record[12:15], record[15:18]
            self.assertTrue(symbols % 8 == 0 and relocs % 8 == 0 and gates % 8 == 0)
            self.assertEqual((nsym, nreloc, ngate), (3, 2, 0) if name == 'main' else (2, 1, 1 if name == 'sdk' else 0))
            value, _, name_at, defined, _, _ = struct.unpack_from('<QQIBBBx', blob, symbols + 24)
            self.assertEqual(blob[strings + name_at:blob.index(0, strings + name_at)].decode(), f'{name}_sym')
            self.assertEqual(struct.unpack_from('<QIIq', blob, relocs), (0x3000, 1027, 0, 0x10))
            if name == 'sdk':
                self.assertEqual(struct.unpack_from('<QQII', blob, gates), (0x40010, 0x100, 0, 7))

    def test_a_main_without_its_probe_stub_stops(self):
        with self.assertRaises(recover_modules.RecoverError):
            recover_modules.runtime_tables(self.modules(), bytes(0x12000))

    def test_runtime_index_is_prepare_romfs_backends(self):
        index = dict(files=[dict(path='A/b.txt', offset=512, size=3), dict(path='C', offset=1024, size=0)])
        blob = recover_ipa.runtime_index(index)
        magic, count, strings = struct.unpack_from('<8sQQ', blob)
        self.assertEqual((magic, count, strings), (b'TOTKRFS1', 2, 24 + 2 * 24))
        self.assertEqual(struct.unpack_from('<QQII', blob, 24 + 24), (1024, 0, 8, 2))
        self.assertEqual(blob[strings:], b'A/b.txt\0C\0')

    def test_embed_header_names_are_read_back(self):
        header = '{"main","%s","%s","%s"},\n' % ('1' * 64, '2' * 64, '3' * 64)
        self.assertEqual(recover_modules.embed_header_hashes(header), {'main': dict(x0='1' * 64, w='2' * 64, x1='3' * 64)})


@unittest.skipUnless(os.environ.get('TOTK_RECOVERED'), 'TOTK_RECOVERED=<folder recover_ipa.py wrote> checks that folder')
class RecoveredFolder(unittest.TestCase):
    def test_every_file_is_what_the_manifest_records(self):
        root = Path(os.environ['TOTK_RECOVERED'])
        manifest = json.loads((root/'recover-manifest.json').read_text())
        self.assertEqual(manifest['pending'], [])
        for entry in manifest['files']:
            path = root/entry['path']
            with self.subTest(entry['path']):
                self.assertEqual(path.stat().st_size, entry['size'])
                if entry['path'].endswith('romfs.bin') and os.environ.get('TOTK_RECOVERED_ROMFS') != '1':
                    continue
                h = hashlib.sha256()
                with open(path, 'rb') as f:
                    while chunk := f.read(8 << 20):
                        h.update(chunk)
                self.assertEqual(h.hexdigest(), entry['sha256'])


if __name__ == '__main__':
    unittest.main()
