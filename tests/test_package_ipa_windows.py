"""games/totk/ios/tools/package_ipa_windows.py and macho.py on a synthetic runtime executable (no game files, no SDK):
the nine module sections written at their file offsets and checked against the layout and the executable's ios_embed
table, the Info.plist rules, the runtime archive and the commit it names, and the work folder's game data.

With TOTK_IOS_RUNTIME=<the ios-runtime workflow's TOTK-runtime.zip>, TOTK_RECOVERED=<recover_ipa.py --out folder, with
export_ios_windows.py's sections in build/export-ios> and zsign (--zsign's $TOTK_ZSIGN or PATH) the real runtime is
packaged (its nine sections written, ad-hoc signed) and the signature is checked, including that one changed byte of a
written section is found."""
import contextlib
import hashlib
import io
import json
import os
import plistlib
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]/'games/totk/ios/tools'
sys.path.insert(0, str(TOOLS))
import macho  # noqa: E402
import package_ipa_windows as package  # noqa: E402
import sign_ipa_windows as signing  # noqa: E402

CHAIN = 'totk-native-v8-unverified'
COMMIT = '89c0131b058d4b0d72e365eaca6ff40d7f6bc924'
BASE = 0x100000000
NAMES = ('main', 'subsdk0', 'sdk')
SECTIONS = {name: {'x0': ('__TOTKX', f'__{name}x0'), 'w': (f'__TOTK{name}W', '__img'), 'x1': ('__TOTKX', f'__{name}x1')}
            for name in NAMES}   # gen_embed.py section_names


def executable(sections, embed, strings=(), pointer_format=6, zero_fill=()):
    """A thin arm64 Mach-O laid out as far as the tools read the runtime: __TEXT with C strings, __DATA with the
    ios_embed table (rows of four string pointers, stored as chained fixups of pointer_format), a segment per group of
    module sections ({(segment, section): bytes}; the zero_fill ones without file bytes) and a symbol table naming
    _ios_embed. Returns the bytes and {(segment, section): file offset}."""
    cstrings = bytearray(b'\0')
    def cstr(s):
        cstrings.extend(s.encode() + b'\0'); return len(cstrings) - len(s) - 1
    rows = [[cstr(v) for v in row] for row in embed]
    for s in strings:
        cstr(s)
    groups = {}
    for (seg, sect), data in sections.items():
        groups.setdefault(seg, []).append((sect, data))
    segments = [('__TEXT', 0, 0x2000, [('__cstring', 0x1000, bytes(cstrings), 0)]),
                ('__DATA', 0x2000, 0x1000, [('__const', 0x2000, None, 0)])]
    at, offsets = 0x3000, {}
    for seg, sects in groups.items():
        start, placed = at, []
        for sect, data in sects:
            fill = (seg, sect) in zero_fill
            placed.append((sect, 0 if fill else at, data, 1 if fill else 0))
            offsets[(seg, sect)] = 0 if fill else at
            at += 0 if fill else len(data)
        at = (at + 0xfff) & ~0xfff
        segments.append((seg, start, at - start, placed))
    symoff, stroff, strtab = at, at + 16, b'\0_ios_embed\0'
    fixups = (stroff + len(strtab) + 7) & ~7
    starts = struct.pack('<I', len(segments)) + b''.join(struct.pack('<I', 4 + 4 * len(segments) if i == 1 else 0)
                                                          for i in range(len(segments)))
    starts += struct.pack('<IHHQIHH', 24, 0x4000, pointer_format, 0x2000, 0, 1, 0)
    blob = struct.pack('<7I', 0, 32, 0, 0, 0, 1, 0) + bytes(4) + starts
    commands = []
    for seg, fileoff, filesize, sects in segments:
        commands.append(struct.pack('<II16sQQQQiiII', 0x19, 72 + 80 * len(sects), seg.encode(), BASE + fileoff, filesize,
                                    fileoff, filesize, 7, 5, len(sects), 0))
        for sect, off, data, flags in sects:
            size = 32 * len(rows) if data is None else len(data)
            commands.append(struct.pack('<16s16sQQIIIIIIII', sect.encode(), seg.encode(), BASE + (off or fileoff), size, off,
                                        4, 0, 0, flags, 0, 0, 0))
    commands.append(struct.pack('<6I', 0x2, 24, symoff, 1, stroff, len(strtab)))
    commands.append(struct.pack('<4I', 0x80000034, 16, fixups, len(blob)))
    load = b''.join(commands)
    out = bytearray(fixups + len(blob))
    out[:32] = struct.pack('<IiiIIIII', 0xfeedfacf, 0x0100000c, 0, 2, len(segments) + 2, len(load), 0, 0)
    out[32:32 + len(load)] = load
    out[0x1000:0x1000 + len(cstrings)] = cstrings
    for i, row in enumerate(rows):
        for k, s in enumerate(row):
            target = BASE + 0x1000 + s
            struct.pack_into('<Q', out, 0x2000 + 32 * i + 8 * k, target - BASE if pointer_format == 6 else target)
    for seg, _, _, sects in segments[2:]:
        for sect, off, data, _ in sects:
            if off:
                out[off:off + len(data)] = data
    struct.pack_into('<IBBHQ', out, symoff, 1, 0x0f, 2, 0, BASE + 0x2000)
    out[stroff:stroff + len(strtab)] = strtab
    out[fixups:] = blob
    return bytes(out), offsets


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Runtime:
    """The nine sections of three synthetic modules, the layout pinning them, and a runtime built for that layout."""
    def __init__(self, root, pointer_format=6, embed_of=None):
        self.modules = {(n, p): bytes([i * 3 + j + 1]) * (0x40 * (j + 1)) for i, n in enumerate(NAMES) for j, p in enumerate(('x0', 'w', 'x1'))}
        self.dir = root/'embed'; self.dir.mkdir(parents=True, exist_ok=True)
        for (n, p), data in self.modules.items():
            (self.dir/f'{n}.{p}.bin').write_bytes(data)
        self.layout = {'modules': [{'name': n, **{p: {'size': len(self.modules[(n, p)]), 'sha256': digest(self.modules[(n, p)])}
                                                  for p in ('x0', 'w', 'x1')}} for n in NAMES]}
        embed = embed_of or {k: digest(v) for k, v in self.modules.items()}
        rows = [(n, embed[(n, 'x0')], embed[(n, 'w')], embed[(n, 'x1')]) for n in NAMES]
        zeros = {SECTIONS[n][p]: bytes(len(d)) for (n, p), d in self.modules.items()}
        self.exe, self.offsets = executable(zeros, rows, ['rt-' + CHAIN, CHAIN], pointer_format)


class Sections(unittest.TestCase):
    def test_the_modules_go_in_at_their_file_offsets(self):
        with tempfile.TemporaryDirectory() as d:
            rt = Runtime(Path(d))
            exe = bytearray(rt.exe)
            done = package.fill_sections(exe, rt.dir, rt.layout)
            self.assertEqual(sorted(done), sorted((n, p, 'written') for n, p in rt.modules))
            for (n, p), data in rt.modules.items():
                at = rt.offsets[SECTIONS[n][p]]
                self.assertEqual(bytes(exe[at:at + len(data)]), data)
            self.assertEqual(len(exe), len(rt.exe))
            self.assertEqual(package.runtime_chain(bytes(exe)), CHAIN)
            again = package.fill_sections(exe, rt.dir, rt.layout)
            self.assertEqual({state for _, _, state in again}, {'already there'})

    def test_other_bytes_another_layout_or_a_wrong_section_file_stop_it(self):
        with tempfile.TemporaryDirectory() as d:
            rt = Runtime(Path(d))
            exe = bytearray(rt.exe); exe[rt.offsets[SECTIONS['sdk']['w']]] = 0x55
            with self.assertRaises(package.PackageError):
                package.fill_sections(exe, rt.dir, rt.layout)
            other = Runtime(Path(d)/'other', embed_of={k: 'e' * 64 for k in rt.modules})
            with self.assertRaises(package.PackageError):
                package.fill_sections(bytearray(other.exe), rt.dir, rt.layout)
            (rt.dir/'main.x1.bin').write_bytes(b'\1' * 0xc0)
            with self.assertRaises(package.PackageError):
                package.fill_sections(bytearray(rt.exe), rt.dir, rt.layout)

    def test_the_check_only_run_reads_the_runtime_in_place_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            rt = Runtime(Path(d))
            layout = Path(d)/'layout.json'; layout.write_text(json.dumps(rt.layout))
            artifact = runtime_zip(Path(d)/'TOTK-runtime.zip', COMMIT + '\n', exe=rt.exe)
            before = sorted(p.relative_to(d).as_posix() for p in Path(d).rglob('*'))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                package.check_only(artifact, rt.dir, layout)
            self.assertEqual(out.getvalue().count('to be written'), 9)
            self.assertIn(COMMIT, out.getvalue())
            self.assertEqual(sorted(p.relative_to(d).as_posix() for p in Path(d).rglob('*')), before)
            other = Runtime(Path(d)/'other', embed_of={k: 'e' * 64 for k in rt.modules})   # built for another layout
            with self.assertRaisesRegex(package.PackageError, 'another embed layout'), contextlib.redirect_stdout(io.StringIO()):
                package.check_only(runtime_zip(Path(d)/'other.zip', exe=other.exe), rt.dir, layout)

    def test_the_chain_is_read_from_the_executable(self):
        exe = b'\0junk\0rt-' + CHAIN.encode() + b'\0more\0' + CHAIN.encode() + b'\0'
        self.assertEqual(package.runtime_chain(exe), CHAIN)
        with self.assertRaises(package.PackageError):
            package.runtime_chain(b'\0rt-x-v1\0')


class MachO(unittest.TestCase):
    def test_sections_symbols_and_both_pointer_formats(self):
        with tempfile.TemporaryDirectory() as d:
            for fmt in (2, 6):
                with self.subTest(pointer_format=fmt):
                    rt = Runtime(Path(d)/str(fmt), pointer_format=fmt)
                    exe = macho.MachO(rt.exe)
                    self.assertEqual(exe.pointer_format, fmt)
                    for (n, p), data in rt.modules.items():
                        self.assertEqual(exe.sections[SECTIONS[n][p]], (rt.offsets[SECTIONS[n][p]], len(data)))
                        self.assertEqual(macho.module_sections(n)[p], SECTIONS[n][p])
                    self.assertEqual(macho.embed_hashes(exe, NAMES)['subsdk0']['w'], digest(rt.modules[('subsdk0', 'w')]))
                    self.assertEqual(exe.symbol('_ios_embed'), BASE + 0x2000)

    def test_a_zero_fill_section_has_no_bytes_in_the_file(self):
        exe, _ = executable({('__TOTKX', '__mainx0'): bytes(64), ('__TOTKX', '__mainx1'): bytes(64)}, [],
                            zero_fill={('__TOTKX', '__mainx0')})
        image = macho.MachO(exe)
        self.assertEqual(image.sections[('__TOTKX', '__mainx0')], (0, 64))
        with self.assertRaises(macho.MachOError):
            image.section_bytes('__TOTKX', '__mainx0')
        self.assertEqual(image.section_bytes('__TOTKX', '__mainx1'), bytes(64))
        with self.assertRaises(macho.MachOError):
            image.symbol('_modules')

    def test_another_kind_of_file_is_refused(self):
        for data in (b'\x7fELF' + bytes(60), struct.pack('<Ii', 0xfeedfacf, 0x01000007) + bytes(24)):
            with self.subTest(data=data[:8]), self.assertRaises(macho.MachOError):
                macho.MachO(data)


class InfoPlist(unittest.TestCase):
    OLD = {'CFBundleIdentifier': 'old.id', 'CFBundleShortVersionString': '1.4.3', 'NSMotionUsageDescription': 'old text',
           'DTXcode': '2710', 'TOTKSourceCommit': 'old', 'TOTKBuildDate': '2026-10-22', 'TOTKBuildNumber': 1,
           'CFBundleIcons': {'x': 1}, 'Old': True}
    IDENTITY = {'CFBundleIdentifier': 'new.id', 'CFBundleShortVersionString': '1.4.3', 'CFBundleVersion': '2610.22.1'}
    BUILD = {'source_commit': 'abc', 'date': '2026-10-26'}

    def test_identity_over_the_runtime_over_the_old_app(self):
        runtime = {'DTXcode': '2660', 'NSMotionUsageDescription': 'new', 'CFBundleShortVersionString': '1.0', 'UIFileSharingEnabled': True}
        info = package.app_info(runtime, self.OLD, self.IDENTITY, False, self.BUILD)
        self.assertEqual(info['NSMotionUsageDescription'], 'new')
        self.assertEqual(info['DTXcode'], '2660')   # the runtime's own build keys, never the old app's
        self.assertTrue(info['Old'] and info['UIFileSharingEnabled'])
        self.assertEqual((info['CFBundleIdentifier'], info['CFBundleShortVersionString'], info['CFBundleVersion']),
                         ('new.id', '1.4.3', '2610.22.1'))
        self.assertEqual((info['TOTKSourceCommit'], info['TOTKBuildDate'], info['TOTKBuildNumber']), ('abc', '2026-10-26', 1))
        self.assertNotIn('CFBundleIcons', info)
        self.assertEqual(runtime['CFBundleShortVersionString'], '1.0')   # the runtime's record is left as it was

    def test_the_old_icons_come_with_the_old_icon_files(self):
        info = package.app_info({'DTXcode': '2660'}, self.OLD, self.IDENTITY, True, self.BUILD)
        self.assertEqual(info['CFBundleIcons'], {'x': 1})
        info = package.app_info({}, {k: v for k, v in self.OLD.items() if not k.startswith('TOTK')}, self.IDENTITY, False, self.BUILD)
        self.assertNotIn('TOTKSourceCommit', info)   # set to this build's only where the old app had them


def runtime_zip(path, commit=None, folder='', exe=b'exe'):
    """A TOTK-runtime.zip as ios-runtime.yml packs it: <folder>TOTK.app (the executable exe, the build's signature and a
    settings file) and, given commit, TOTK-runtime.commit beside it holding that text; an artifact from before the
    workflow wrote the file has none."""
    app = f'{folder}TOTK.app/'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr(app, b''); z.writestr(app + 'Info.plist', plistlib.dumps({'CFBundleExecutable': 'TOTK'}))
        z.writestr(app + 'TOTK', exe); z.writestr(app + '_CodeSignature/CodeResources', b'old')
        z.writestr(app + 'Settings.bundle/Root.plist', b'settings')
        if commit is not None:
            z.writestr(folder + package.RUNTIME_COMMIT, commit)
    return path


class Archive(unittest.TestCase):
    def test_the_runtime_archive_unpacks_without_its_signature(self):
        with tempfile.TemporaryDirectory() as d:
            artifact = runtime_zip(Path(d)/'TOTK-runtime.zip', COMMIT + '\n')
            app = Path(d)/'stage/Payload/TOTK.app'
            self.assertEqual(package.unpack_runtime(artifact, app), {'CFBundleExecutable': 'TOTK'})
            self.assertEqual(sorted(p.relative_to(app).as_posix() for p in app.rglob('*') if p.is_file()),
                             ['Info.plist', 'Settings.bundle/Root.plist', 'TOTK'])   # TOTK-runtime.commit stays out
            folder = Path(d)/'again/TOTK.app'
            package.unpack_runtime(app, folder)   # a TOTK.app folder too
            self.assertEqual((folder/'TOTK').read_bytes(), b'exe')
            (Path(d)/'TOTK').write_bytes(b'\xcf\xfa\xed\xfe')
            with self.assertRaises(package.PackageError):   # a bare executable is not a runtime any more
                package.unpack_runtime(Path(d)/'TOTK', Path(d)/'bare/TOTK.app')


class SourceCommit(unittest.TestCase):
    def test_the_runtime_names_its_commit_in_the_archive_or_beside_the_app_unpacked_from_it(self):
        with tempfile.TemporaryDirectory() as d:
            artifact = runtime_zip(Path(d)/'TOTK-runtime.zip', COMMIT + '\n')
            self.assertEqual(package.runtime_commit(artifact), COMMIT)
            self.assertEqual(package.runtime_commit(runtime_zip(Path(d)/'payload.zip', COMMIT + '\r\n', 'Payload/')), COMMIT)
            self.assertIsNone(package.runtime_commit(runtime_zip(Path(d)/'old.zip')))
            with zipfile.ZipFile(artifact) as z:
                z.extractall(Path(d)/'unpacked')
            self.assertEqual(package.runtime_commit(Path(d)/'unpacked/TOTK.app'), COMMIT)
            (Path(d)/'unpacked'/package.RUNTIME_COMMIT).unlink()
            self.assertIsNone(package.runtime_commit(Path(d)/'unpacked/TOTK.app'))

    def test_a_commit_file_that_names_no_commit_stops_it(self):
        with tempfile.TemporaryDirectory() as d:
            for text in ('', 'ios-windows-fixes\n', COMMIT[:12] + '\n', COMMIT + 'z\n'):
                with self.subTest(text=text), self.assertRaises(package.PackageError):
                    package.runtime_commit(runtime_zip(Path(d)/'bad.zip', text))

    def test_the_option_comes_first_then_the_runtime_then_the_checkout_with_a_warning(self):
        with tempfile.TemporaryDirectory() as d:
            named, old = runtime_zip(Path(d)/'named.zip', COMMIT + '\n'), runtime_zip(Path(d)/'old.zip')
            head, out = 'f' * 40, io.StringIO()
            with mock.patch.object(package, 'git_commit', return_value=head), contextlib.redirect_stdout(out):
                self.assertEqual(package.source_commit('abc', named), ('abc', '--source-commit'))
                self.assertEqual(package.source_commit('abc', old), ('abc', '--source-commit'))
                self.assertEqual(package.source_commit(None, named), (COMMIT, package.RUNTIME_COMMIT))
                self.assertEqual(out.getvalue(), '')
                self.assertEqual(package.source_commit(None, old), (head, 'checkout HEAD'))
            self.assertIn('warning', out.getvalue())
            self.assertIn(head, out.getvalue())


class GameData(unittest.TestCase):
    def tree(self, root):
        files = {'build/game-data/v143/runtime-tables.bin': b'tables', 'extracted/v143/romfs/romfs.bin': b'image',
                 'extracted/v143/romfs/index.json': b'{}', 'extracted/v143/romfs-patches/a/b.zs': b'patch',
                 'extracted/v143/romfs-patches-out/1920x1080/manifest.tsv': b'#', 'extracted/firmware/shared-fonts/0-standard.bfttf': b'font'}
        for rel, data in files.items():
            (root/rel).parent.mkdir(parents=True, exist_ok=True); (root/rel).write_bytes(data)
        records = [dict(path=rel, size=len(data), sha256=digest(data)) for rel, data in files.items()]
        (root/'recover-manifest.json').write_text(json.dumps(dict(files=records)))
        return files

    def test_the_files_go_where_main_m_reads_them_and_the_image_stays_out(self):
        with tempfile.TemporaryDirectory() as d:
            tree, res = Path(d)/'tree', Path(d)/'GameData'
            self.tree(tree)
            self.assertEqual(package.game_data(tree, res, 'documents'), 5)
            self.assertEqual(sorted(p.relative_to(res).as_posix() for p in res.rglob('*') if p.is_file()),
                             ['game-data/runtime-tables.bin', 'romfs-patches-out/1920x1080/manifest.tsv', 'romfs-patches/a/b.zs',
                              'romfs/index.json', 'shared-fonts/0-standard.bfttf'])

    def test_the_image_goes_into_the_app_in_parts_the_app_finds(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(package.push, 'PART', 2):
            tree, res = Path(d)/'tree', Path(d)/'GameData'
            self.tree(tree)
            self.assertEqual(package.game_data(tree, res, 'app'), 8)   # the 5 other files and 3 parts of 'image'
            parts = sorted(p.name for p in (res/'romfs').glob('romfs.bin*'))
            self.assertEqual(parts, ['romfs.bin.000', 'romfs.bin.001', 'romfs.bin.002'])
            self.assertEqual(b''.join((res/'romfs'/p).read_bytes() for p in parts), b'image')
        main = (package.IOS/'Sources/main.m').read_text(encoding='utf-8')
        self.assertIn('@"romfs/romfs.bin.000"', main)

    def slots(self, folder):
        for slot in package.push.MOD_SLOTS:
            data = f'{slot} font'.encode()
            mod = folder/f'v143-{slot}'
            (mod/'Font').mkdir(parents=True)
            (mod/'Font/a.bfotf').write_bytes(data)
            (mod/'.mod-original').mkdir()
            (mod/'.mod-original/a').write_bytes(b'kept on the PC')
            (mod/'.gameplay-tuning.json').write_text('{}')
            (mod/'manifest.tsv').write_text(f'# path\tsize\tsha256\toriginal_sha256\nFont/a.bfotf\t{len(data)}\t{digest(data)}\t{digest(b"")}\n', newline='\n')

    def test_the_slot_folders_go_into_the_app_as_the_device_would_get_them(self):
        with tempfile.TemporaryDirectory() as d:
            folder, mods = Path(d)/'mods', Path(d)/'GameData/mods'
            self.slots(folder)
            self.assertEqual(package.bundled_mods(folder, mods), 8)
            self.assertEqual(sorted(p.relative_to(mods).as_posix() for p in mods.rglob('*') if p.is_file()),
                             sorted(f'v143-{slot}/{name}' for slot in package.push.MOD_SLOTS for name in ('Font/a.bfotf', 'manifest.tsv')))
            self.assertEqual((mods/'v143-max/Font/a.bfotf').read_bytes(), b'max font')
            self.assertEqual((mods/'v143-max/manifest.tsv').read_bytes(), (folder/'v143-max/manifest.tsv').read_bytes())

    def test_a_slot_the_game_would_refuse_stops_it(self):
        with tempfile.TemporaryDirectory() as d:
            folder, mods = Path(d)/'mods', Path(d)/'GameData/mods'
            self.slots(folder)
            (folder/'v143-max/Font/a.bfotf').write_bytes(b'changed')
            with self.assertRaises(package.push.PushError):
                package.bundled_mods(folder, mods)
            shutil.rmtree(folder/'v143-max')
            with self.assertRaises(package.push.PushError):
                package.bundled_mods(folder, mods)

    def test_a_file_changed_since_recover_ipa_checked_it_stops_it(self):
        with tempfile.TemporaryDirectory() as d:
            tree = Path(d)/'tree'
            self.tree(tree)
            (tree/'extracted/v143/romfs-patches/a/b.zs').write_bytes(b'PATCH')
            with self.assertRaises(package.PackageError):
                package.game_data(tree, Path(d)/'GameData', 'documents')


def zsign_or_none():
    try:
        return signing.tool('zsign', None, 'TOTK_ZSIGN')
    except signing.SignError:
        return None


@unittest.skipUnless(os.environ.get('TOTK_IOS_RUNTIME') and os.environ.get('TOTK_RECOVERED') and zsign_or_none(),
                     'TOTK_IOS_RUNTIME and TOTK_RECOVERED name a runtime and a recovered work folder, and zsign is there')
class RealRuntime(unittest.TestCase):
    def test_the_runtime_gets_its_sections_and_a_sound_signature(self):
        tree = Path(os.environ['TOTK_RECOVERED'])
        with tempfile.TemporaryDirectory() as d:
            app = Path(d)/'stage/Payload/TOTK.app'
            info = package.unpack_runtime(Path(os.environ['TOTK_IOS_RUNTIME']), app)
            exe_name = info['CFBundleExecutable']
            exe = bytearray((app/exe_name).read_bytes())
            done = package.fill_sections(exe, tree/package.EXPORT_DIR, json.loads(package.LAYOUT.read_text()))
            self.assertEqual(len(done), 9)
            (app/exe_name).write_bytes(exe)
            ipa = Path(d)/'adhoc.ipa'
            signing.sign_adhoc(zsign_or_none(), Path(d)/'stage', ipa, signing.APP_ENTITLEMENTS)
            self.assertEqual(signing.verify(ipa)['entitlements'], {signing.MEMORY: True})
            with zipfile.ZipFile(ipa) as z:
                signed = bytearray(z.read(f'Payload/TOTK.app/{exe_name}'))
            at, size = macho.MachO(bytes(signed)).sections[('__TOTKX', '__mainx0')]
            signed[at + size // 2] ^= 1
            problems, _ = signing.check_executable(bytes(signed), b'', b'', info['CFBundleIdentifier'], None, None)
            self.assertTrue(any('code pages do not match' in p for p in problems), problems)


if __name__ == '__main__':
    unittest.main()
