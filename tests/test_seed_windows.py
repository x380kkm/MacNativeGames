"""games/totk/ios/tools/seed_windows.py on a synthetic seed (no game files): the seed's device form as build_ipa.py writes
it beside an IPA, its Metal libraries, what the runtime refuses, and the git tree hash that admits SPIRV-Cross's sources."""
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1]/'games/totk/ios/tools'
sys.path.insert(0, str(TOOLS))
import seed_windows  # noqa: E402
import shader_list  # noqa: E402  on sys.path through seed_windows

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


KEY_A, KEY_B, KEY_C = 'a' * 64, 'b' * 64, 'c' * 64
PLAIN = '{"attr":{},"fout":{"0":"float"},"img":{},"tex":{"8":"3d"}}'
DEPTH = '{"attr":{},"fout":{},"img":{},"tex":{"8":"2darray_depth"}}'
ADDED = 'extra lists: their rows added {} variants to the seed (a row a variant already serves adds none)'


class ExtraList(unittest.TestCase):
    """--extra-list: a device's own V rows in this seed only."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.shared = self.root/'shader_list.tsv'
        self.shared.write_text(f'# list\nV\t{KEY_C}\t{PLAIN}\nS\t{A}_b\t0\tt\n')
        self.list = patch.object(seed_windows, 'SHADER_LIST', self.shared); self.list.start()

    def tearDown(self):
        self.list.stop(); self.tmp.cleanup()

    def contribution(self, name, *rows):
        path = self.root/name
        path.write_text(''.join(line + '\n' for line in ('# Shaders this game met', *rows)))
        return path

    def seed(self, variants, skipped=()):
        """A seed folder: {key: [deps of each row of its .variants]}, the shaders the game has, the failed translations."""
        seed = self.root/'seed'; seed.mkdir()
        for key, rows in variants.items():
            (seed/f'{key}.variants').write_text(json.dumps([dict(variant=f'{key}-{i:012x}', deps=d) for i, d in enumerate(rows)]))
        (seed/'seed-manifest.json').write_text(json.dumps(dict(skipped=list(skipped))))
        (seed/'shader-keys.json').write_text(json.dumps(dict(keys=[KEY_A, KEY_B])))
        return seed

    def test_only_v_rows_are_taken_and_each_once(self):
        one = self.contribution('one', f'V\t{KEY_A}\t{PLAIN}', 'R\tabcd\tm', 'B\tabcd\t-\t-\tm')
        two = self.contribution('two', f'V\t{KEY_A}\t{PLAIN}', f'V\t{KEY_B}\t{DEPTH}')
        self.assertEqual(seed_windows.extra_rows([one, two]), {(KEY_A, PLAIN), (KEY_B, DEPTH)})

    def test_rows_come_back_in_the_lists_canonical_text(self):
        row = f'V\t{KEY_A}\t' + '{"tex": {"8": "3d"}, "img": {}, "fout": {"0": "float"}, "attr": {}}'
        self.assertEqual(seed_windows.extra_rows([self.contribution('one', row)]), {(KEY_A, PLAIN)})

    def test_a_row_shader_list_py_could_not_read_stops_it(self):
        for name, row in (('short key', f'V\tabc\t{PLAIN}'), ('not json', f'V\t{KEY_A}\t{{'), ('no deps', f'V\t{KEY_A}'),
                          ('other fields', f'V\t{KEY_A}\t{{"size":{{}}}}')):
            with self.subTest(name):
                path = self.contribution('bad', f'V\t{KEY_B}\t{PLAIN}', row)   # a good row before it does not excuse it
                with self.assertRaises(seed_windows.SeedError) as refused:
                    seed_windows.extra_rows([path])
                self.assertEqual(str(refused.exception), f'{path}:3: not a shader list V row')

    def test_a_file_without_v_rows_stops_it(self):
        with self.assertRaises(seed_windows.SeedError):
            seed_windows.extra_rows([self.contribution('none', 'R\tabcd\tm')])

    def test_the_list_is_the_shared_one_with_the_rows_after_it(self):
        path = seed_windows.list_with_rows({(KEY_B, DEPTH), (KEY_A, PLAIN), (KEY_C, PLAIN)}, self.root/'seed.list.tsv')
        merged = shader_list.ShaderList.load(path)
        self.assertEqual(merged.variants, {(KEY_A, PLAIN), (KEY_B, DEPTH), (KEY_C, PLAIN)})
        self.assertEqual(list(merged.warm), list(shader_list.ShaderList.load(self.shared).warm))
        self.assertTrue(path.read_bytes().startswith(self.shared.read_bytes()))
        # The same rows give the same file, so the seed is reused. A list in reverse order, since a set's order changes with
        # each process's string hashes and could come out sorted by chance.
        seed_windows.list_with_rows([(KEY_C, PLAIN), (KEY_B, DEPTH), (KEY_A, PLAIN)], path)
        appended = path.read_bytes()[len(self.shared.read_bytes()):]
        self.assertEqual(appended, f'V\t{KEY_A}\t{PLAIN}\nV\t{KEY_B}\t{DEPTH}\nV\t{KEY_C}\t{PLAIN}\n'.encode())

    def test_a_row_is_served_as_the_runtime_picks(self):
        seed = self.seed({KEY_A: [dict(tex={'8': '*'}), dict(tex={'8': '*_depth'})]})
        self.assertEqual(seed_windows.unserved(seed, {(KEY_A, PLAIN), (KEY_A, DEPTH)}), {})

    def test_a_depth_texture_is_not_served_by_a_colour_variant_and_the_reason_is_named(self):
        variant = f'{KEY_A}-{seed_windows.suffix(seed_windows.answers_for(json.loads(DEPTH)))}'
        seed = self.seed({KEY_A: [dict(tex={'8': '*'})]}, [dict(key=KEY_A, variant=variant, error='spirv-cross: no')])
        self.assertEqual(seed_windows.unserved(seed, {(KEY_A, PLAIN), (KEY_A, DEPTH)}), {variant: 'spirv-cross: no'})

    def test_a_shader_of_another_game_version_is_named(self):
        seed = self.seed({})
        answers = seed_windows.answers_for(json.loads(PLAIN))
        self.assertEqual(seed_windows.unserved(seed, {(KEY_C, PLAIN)}),
                         {f'{KEY_C}-{seed_windows.suffix(answers)}': 'this game version has no such shader'})

    def run_seed(self, *extra):
        work = self.root/'work'
        (work/'tools/bin').mkdir(parents=True, exist_ok=True)
        for name in ('totk_xlate.exe', 'spirv-cross.exe'):
            (work/'tools/bin'/name).write_bytes(b'')
        args = Namespace(work=work, romfs=self.root/'romfs', modules=None, version='v143', extra_list=list(extra))
        printed = io.StringIO()
        with patch.object(seed_windows.subprocess, 'run', return_value=Namespace(returncode=0)) as prepare, \
                contextlib.redirect_stdout(printed):
            seed_windows.cmd_seed(args)
        self.printed = printed.getvalue()
        return [str(part) for part in prepare.call_args.args[0]]

    def test_without_the_option_the_shared_list_is_used_as_it_is(self):
        self.assertNotIn('--shader-list', self.run_seed())
        self.assertFalse((self.root/'work/seed.list.tsv').exists())

    def test_with_the_option_the_preparation_gets_the_merged_list(self):
        (self.root/'work').mkdir()
        seed = self.seed({KEY_A: [dict(tex={'8': '*'})]})
        seed.rename(self.root/'work/seed')
        cmd = self.run_seed(self.contribution('one', f'V\t{KEY_A}\t{PLAIN}'))
        self.assertEqual(cmd[cmd.index('--shader-list') + 1], str((self.root/'work/seed.list.tsv').resolve()))
        self.assertIn(f'V\t{KEY_A}\t{PLAIN}\n', (self.root/'work/seed.list.tsv').read_text())
        self.assertIn('extra lists: the seed serves 1 of their 1 V rows\n', self.printed)
        self.assertNotIn('not served', self.printed)

    def test_the_run_says_how_many_rows_are_served_and_why_the_others_are_not(self):
        (self.root/'work').mkdir()
        answers = seed_windows.answers_for(json.loads(DEPTH))
        failed = f'{KEY_A}-{seed_windows.suffix(answers)}'
        missing = f'{KEY_C}-{seed_windows.suffix(seed_windows.answers_for(json.loads(PLAIN)))}'
        seed = self.seed({KEY_A: [dict(tex={'8': '*'})]}, [dict(key=KEY_A, variant=failed, error='spirv-cross: no')])
        seed.rename(self.root/'work/seed')
        self.run_seed(self.contribution('one', f'V\t{KEY_A}\t{PLAIN}', f'V\t{KEY_A}\t{DEPTH}', f'V\t{KEY_C}\t{PLAIN}'))
        lines = self.printed.splitlines()
        self.assertIn('extra lists: the seed serves 1 of their 3 V rows', lines)
        self.assertIn(f'  not served: {failed}: spirv-cross: no', lines)
        self.assertIn(f'  not served: {missing}: this game version has no such shader', lines)

    def own(self, key, deps):
        return f'{key}-{seed_windows.suffix(seed_windows.answers_for(json.loads(deps)))}'

    def seed_of_own_variants(self, key, *rows):
        """A seed whose variants of this shader carry the names the preparation gives these rows."""
        seed = self.seed({})
        (seed/f'{key}.variants').write_text(json.dumps([dict(variant=self.own(key, d), deps=json.loads(d)) for d in rows]))
        return seed

    def test_rows_other_variants_serve_add_no_variant(self):
        (self.root/'work').mkdir()
        seed = self.seed({KEY_A: [dict(tex={'8': '*'}), dict(tex={'8': '*_depth'})]})
        seed.rename(self.root/'work/seed')
        self.run_seed(self.contribution('one', f'V\t{KEY_A}\t{PLAIN}', f'V\t{KEY_A}\t{DEPTH}'))
        lines = self.printed.splitlines()
        self.assertIn('extra lists: the seed serves 2 of their 2 V rows', lines)
        self.assertIn(ADDED.format(0), lines)

    def test_a_variant_kept_for_a_row_is_counted(self):
        (self.root/'work').mkdir()
        seed = self.seed_of_own_variants(KEY_A, PLAIN)
        seed.rename(self.root/'work/seed')
        self.run_seed(self.contribution('one', f'V\t{KEY_A}\t{PLAIN}', f'V\t{KEY_A}\t{DEPTH}'))
        lines = self.printed.splitlines()
        self.assertIn('extra lists: the seed serves 1 of their 2 V rows', lines)
        self.assertIn(ADDED.format(1), lines)

    def test_two_rows_with_one_translation_added_one_variant(self):
        star, plain = '{"tex":{"8":"*"}}', '{"tex":{"8":"2d"}}'
        seed = self.seed_of_own_variants(KEY_A, star)
        self.assertEqual(seed_windows.added_variants(seed, {(KEY_A, star), (KEY_A, plain)}), {self.own(KEY_A, star)})

    def test_the_default_variant_is_not_added_by_a_row(self):
        row = '{"attr":{},"fout":{},"img":{},"tex":{}}'
        self.assertEqual(self.own(KEY_A, row), A)
        self.assertEqual(seed_windows.added_variants(self.seed_of_own_variants(KEY_A, row), {(KEY_A, row)}), set())

    def test_the_shadow_map_variant_is_not_added_by_a_row(self):
        default, depth = '{"attr":{},"fout":{},"img":{},"tex":{}}', '{"attr":{},"fout":{},"img":{},"tex":{"8":"*_depth"}}'
        seed = self.seed_of_own_variants(KEY_A, default, depth)
        (seed/f'{A}_b.json').write_text(json.dumps(dict(compare_slots=[8])))   # the translation that adds this job
        self.assertEqual(seed_windows.added_variants(seed, {(KEY_A, depth)}), set())

    def test_a_row_the_shared_list_has_too_added_nothing(self):
        seed = self.seed_of_own_variants(KEY_C, PLAIN)
        self.assertEqual(seed_windows.added_variants(seed, {(KEY_C, PLAIN)}), set())


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
