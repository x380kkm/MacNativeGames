"""games/totk/ios/tools/seed_windows.py on a synthetic seed (no game files): the seed's device form as build_ipa.py writes
it beside an IPA, its Metal libraries, what the runtime refuses, and the git tree hash that admits SPIRV-Cross's sources."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1]/'games/totk/ios/tools'
sys.path.insert(0, str(TOOLS))
import seed_windows  # noqa: E402

CHAIN = 'totk-native-v8-unverified'
A, B = 'a' * 64 + '-b7530f698e76', 'b' * 64 + '-b7530f698e76'   # two variants: <shader key>-<bind state>


def make_seed(root, files=None, manifest_files=None, **manifest):
    """<root>/seed as prepare_shader_seed.py leaves it, its aliases beside it and a small shared list; returns the seed."""
    seed = root/'seed'; seed.mkdir(parents=True)
    files = files if files is not None else {
        f'{A}_b.metal': b'#include <metal_stdlib>\nvertex float4 main0() { return 0; }\n',
        f'{A}_b.json': '{"notes": ["贴"]}'.encode(), f'{"a" * 64}.variants': b'[]\n',
        f'{B}_b.metal': b'x' * 5000, f'{B}_b.json': b'{}', 'pso_manifest.tsv': b'# x\n', 'shader-keys.json': b'{}\n'}
    for n, data in files.items():
        (seed/n).write_bytes(data)
    names = manifest_files if manifest_files is not None else list(files)
    record = dict(schema=1, chain=CHAIN, version='v143', shaders=2, files={n: hashlib.sha256(files[n]).hexdigest() for n in names})
    (seed/'seed-manifest.json').write_text(json.dumps(record | manifest, indent=2) + '\n')
    (root/'seed.aliases.tsv').write_text(f'{"c" * 64}-b7530f698e76\t{A}\n')
    (root/'shader_list.tsv').write_text(f'# list\nS\t{A}_b\t0\tt\nS\t{"c" * 64}-b7530f698e76_b\t1\tt\nC\t{B}_b\tm\n')
    return seed


class DeviceSeed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.list = patch.object(seed_windows, 'SHADER_LIST', self.root/'shader_list.tsv'); self.list.start()

    def tearDown(self):
        self.list.stop(); self.tmp.cleanup()

    def device(self, seed, dest_name='TOTK-shader-seed', **kw):
        return seed_windows.device_seed(seed, self.root/dest_name, CHAIN, self.root/'lists', **kw)

    def test_the_folder_and_fingerprint_are_build_ipas(self):
        seed = make_seed(self.root, manifest_files=[f'{A}_b.metal'])   # the other hashes come from the files (build_ipa.py)
        fp = self.device(seed)
        dest = self.root/'TOTK-shader-seed'
        manifest = json.loads((dest/'seed-manifest.json').read_bytes())
        shaders = sorted(n.name for n in seed.iterdir() if n.name != 'seed-manifest.json')
        self.assertEqual(list(manifest['files']), shaders)
        self.assertEqual(manifest['files'][f'{B}_b.metal'], hashlib.sha256(b'x' * 5000).hexdigest())
        self.assertEqual(manifest['ios_source_manifest_sha256'], hashlib.sha256((seed/'seed-manifest.json').read_bytes()).hexdigest())
        self.assertEqual((manifest['ios_sdk'], manifest['ios_metallibs']), ('iphoneos', 0))
        parts = [(dest/n).read_bytes() for n in ('seed-manifest.json', 'shader_map.tsv', 'pso_list.tsv', 'pso_title.tsv')]
        self.assertEqual(fp, hashlib.sha256(b''.join(parts)).hexdigest())   # build_ipa.py's fingerprint
        self.assertEqual((dest/'fingerprint.txt').read_text().strip(), fp)
        self.assertEqual(parts[1], b'# TOTK control-code-sha256-v1\n')
        title = parts[3].decode()
        self.assertIn(f'S\t{A}_b\t0', title)   # the listed variant renamed to the one the seed carries (aliases)
        self.assertNotIn('c' * 64, title)
        self.assertIn(f'C\t{B}_b', parts[2].decode())
        for data in parts:
            self.assertNotIn(b'\r', data)   # the runtime splits these files at '\n' only
        self.assertEqual(sorted(p.name for p in dest.iterdir()), sorted(shaders + ['seed-manifest.json', 'shader_map.tsv',
                                                                                  'pso_list.tsv', 'pso_title.tsv', 'fingerprint.txt']))
        self.assertEqual((dest/f'{A}_b.json').read_bytes(), (seed/f'{A}_b.json').read_bytes())
        stamp = (dest/'fingerprint.txt').stat().st_mtime_ns
        self.assertEqual(self.device(seed), fp)
        self.assertEqual((dest/'fingerprint.txt').stat().st_mtime_ns, stamp)   # the same content is kept as it is

    def test_metal_libraries_of_the_seed_go_in(self):
        seed = make_seed(self.root)
        libs = self.root/'libs'; libs.mkdir()
        (libs/f'{A}_b.metallib').write_bytes(b'MTLB' + bytes(100))
        fp = self.device(seed, metallibs=libs)
        manifest = json.loads((self.root/'TOTK-shader-seed/seed-manifest.json').read_bytes())
        self.assertEqual(manifest['ios_metallibs'], 1)
        self.assertEqual(manifest['files'][f'{A}_b.metallib'], hashlib.sha256(b'MTLB' + bytes(100)).hexdigest())
        self.assertTrue(all(seed_windows.SEED_NAME.match(n) for n in manifest['files']))
        self.assertNotEqual(fp, self.device(seed, 'without'))

    def test_what_the_runtime_would_refuse_stops_it_and_leaves_the_folder(self):
        seed = make_seed(self.root)
        fp = self.device(seed)
        libs = self.root/'libs'; libs.mkdir()
        (libs/f'{"c" * 64}-b7530f698e76_b.metallib').write_bytes(b'MTLB')   # of a shader the seed does not carry
        with self.assertRaises(seed_windows.SeedError):
            self.device(seed, metallibs=libs)
        (libs/f'{"c" * 64}-b7530f698e76_b.metallib').unlink(); (libs/f'{A}_b.metallib').write_bytes(b'not metal')
        with self.assertRaises(seed_windows.SeedError):
            self.device(seed, metallibs=libs)
        self.assertEqual((self.root/'TOTK-shader-seed/fingerprint.txt').read_text().strip(), fp)
        with self.assertRaises(seed_windows.SeedError):
            seed_windows.device_seed(seed, self.root/'o', 'totk-native-v1', self.root/'lists')   # another chain
        with self.assertRaises(seed_windows.SeedError):   # the device form given as the seed
            seed_windows.device_seed(self.root/'TOTK-shader-seed', self.root/'o', CHAIN, self.root/'lists')

    def test_a_file_the_runtime_refuses_or_a_missing_one_stops_it(self):
        for case, kw in (('notes', dict(files={'notes.txt': b'x', f'{A}_b.metal': b'y'})),
                         ('missing', dict(files={f'{A}_b.metal': b'y'}, manifest_files=[])),
                         ('schema', dict(schema=2))):
            with self.subTest(case), tempfile.TemporaryDirectory() as d:
                seed = make_seed(Path(d), **kw)
                if case == 'missing':
                    record = json.loads((seed/'seed-manifest.json').read_text())
                    record['files'][f'{B}_b.metal'] = 'f' * 64
                    (seed/'seed-manifest.json').write_text(json.dumps(record))
                with self.assertRaises(seed_windows.SeedError):
                    seed_windows.device_seed(seed, Path(d)/'out', CHAIN, Path(d)/'lists')


class SpirvCrossSources(unittest.TestCase):
    def test_tree_hash_is_gits(self):
        # the ids git hash-object gives these objects (2026-10-26); 'a.b' sorts before the folder 'a' as git sorts trees
        entries = {'a.b': ('100644', b'x\n'), 'a/c': ('100755', b'#!/bin/sh\n'), 'z': ('120000', b'a.b')}
        self.assertEqual(seed_windows.tree_id(entries).hex(), '68dc3a9fbe195d0eee417eb5dbfbbf4e69db294b')
        self.assertEqual(seed_windows.tree_id(entries, 'a/').hex(), 'fee7c1f6724eb3d98f9e66c7582cbbe3a896c9ed')
        self.assertEqual(seed_windows.tree_id({}).hex(), '4b825dc642cb6eb9a060e54bf8d69288fbee4904')
        self.assertEqual(seed_windows.object_id(b'blob', b'hello\n').hex(), 'ce013625030ba8dba906f756967f9e9ca394464a')

    def test_flags_for_visual_studios_clang(self):
        self.assertEqual(seed_windows.windows_flags(['-O2', '-arch', 'arm64', '-std=c++11', '-DX']), ['-O2', '-std=c++14', '-DX'])

    def test_sources_keep_the_line_ends_git_stores(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d)/'a.cs', Path(d)/'out/a.cs'
            src.write_bytes(b'a\r\nb\r\n'); seed_windows.copy_as_stored(src, dst)
            self.assertEqual(dst.read_bytes(), b'a\nb\n')
            src.write_bytes(b'\0\r\n'); seed_windows.copy_as_stored(src, dst)
            self.assertEqual(dst.read_bytes(), b'\0\r\n')   # a binary file as it is


if __name__ == '__main__':
    unittest.main()
