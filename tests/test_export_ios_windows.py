"""games/totk/ios/tools/export_ios_windows.py: runtime/game_patches_v143.c built for Windows exports a made-up work folder
the way the Mac's export-ios does; its device path accepts the export, starts sections from before the fade fix and the
render-resolution patch without them (and names them), and refuses a half-written fade fix; an export that lacks a patch
is refused. No game files: main is zeros with the original words game_patches_v143.c checks at its sites (an fdiv at the
aspect sites), subsdk0 and sdk are zeros. The export needs Windows with clang (Visual Studio's C++ Clang tools) and is
skipped elsewhere; the environment and the layout checks run everywhere."""
import hashlib
import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]/'games/totk/ios/tools'
sys.path.insert(0, str(TOOLS))
import export_ios_windows as export  # noqa: E402
import recover_modules  # noqa: E402

# A main laid out as 1.4.3's (the text's padding below a 4 KiB page end, a data page after the image), only shorter;
# subsdk0 and sdk as small as a layout allows.
LAYOUTS = {'main': dict(TEXT_END=0x2540400, RO_OFF=0x2541000, DATA_OFF=0x2544000, KEY_PAGE_OFF=0x2548000,
                        PATCH_OFF=0x254c000, FILE_SIZE=0x254f6b4),
           'subsdk0': dict(TEXT_END=0x3a00, RO_OFF=0x4000, DATA_OFF=0x8000, KEY_PAGE_OFF=0xc000, PATCH_OFF=0x10000,
                           FILE_SIZE=0x12345),
           'sdk': dict(TEXT_END=0x4000, RO_OFF=0x4000, DATA_OFF=0x8000, KEY_PAGE_OFF=0xc000, PATCH_OFF=0x10000,
                       FILE_SIZE=0x14000)}
LAYOUT = LAYOUTS['main']
STUB = (LAYOUT['TEXT_END'] + 15) & ~15
FDIV_S0 = 0x1e221820   # fdiv s0, s1, s2: an instruction aspect_site_ok accepts
FADE = {0x0a7ac4: 0x1e380008, 0x0a7ac8: 0x3942792a, 0x0a7acc: 0x0b080148, 0x0a7ad0: 0x39027928,
        0x95dd24: 0x1e380008, 0x95dd28: 0x0b080128, 0x6155e4: 0x1e38000a, 0x615660: 0x1e38000a}
RENDER_RES = {0x585e48: 0x1e220160, 0x585e50: 0xbd0cc660, 0x585e54: 0x1e220140, 0x585e60: 0xbd0cca60}
# game_patches_v143.c: each site with the original word it checks before writing.
SITES = {0x2db204: 0x6b08015f, 0x2db208: 0x1a89b10a, 0x2db22c: 0xb940468a, 0x2db360: 0x6b0801bf,     # fps60
         0x2db36c: 0x1a88c1ac, 0x2db340: 0xb9400288, 0x2db34c: 0x2a0a03f5,
         0x3e5658: 0x1e210808, 0x2daa54: 0xbd425260, 0x2daa58: 0x52a84e08, 0x2daa6c: 0x5e21d800,     # real-time frame step
         0x2daa70: 0x1e201820, 0x2daa74: 0x1e2c1001, 0x2daa78: 0x1e210800,
         0x246eac: 0x1e200940, 0x345904: 0x1e210801, 0x24944c: 0x94015e7d, 0x28bc98: 0x9400546a,     # cloth and hair clock
         0x562a64: 0xbd402920, 0x562a68: 0x52a85909, 0x562a6c: 0x1e270121,                         # slow-motion bounce
         **RENDER_RES, **FADE,
         0x628c74: FDIV_S0, 0xb43460: FDIV_S0, 0x1ff04f4: FDIV_S0, 0x253fbb0: FDIV_S0}                # aspect ratio
UNCHANGED = {0x562a68, 0x562a6c}   # the bounce patch checks these two words after its site and leaves them
FADE_VENEER = range(STUB + 928, STUB + 1008)
# The veneers behind the text: frame step 4 words, aspect 4 x 8, cloth 19, bounce 5, fade 20.
VENEERS = {STUB + 4 * i for i in range(4)} | {STUB + 48 + 4 * i for i in range(32)} | {STUB + 176 + 4 * i for i in range(19)} \
    | {STUB + 256 + 4 * i for i in range(5)} | set(FADE_VENEER[::4])


def words_changed(a, b):
    return {k for k in range(0, len(a), 4) if a[k:k + 4] != b[k:k + 4]}


def work_folder(root):
    """rewritten/v143 of the made-up modules, and an expected-v1.4.3.json pinning them; returns the images."""
    rewritten = root/'rewritten/v143'
    rewritten.mkdir(parents=True)
    images = {}
    for name, layout in LAYOUTS.items():
        image = bytearray(layout['FILE_SIZE'])
        for site, word in (SITES.items() if name == 'main' else ()):
            struct.pack_into('<I', image, site, word)
        images[name] = bytes(image)
        (rewritten/f'{name}.patched.bin').write_bytes(image)
        (rewritten/f'{name}.fixups.tsv').write_text(''.join(f'# {k}\t{v:#x}\n' for k, v in layout.items() if k != 'FILE_SIZE')
                                                    + '# KEY_PAGE_SIZE\t0x4000\n')
    pins = {f'{n}.patched.bin': hashlib.sha256(data).hexdigest() for n, data in images.items()}
    (root/'expected.json').write_text(json.dumps({'rewritten_sha256': pins}))
    return images


@unittest.skipUnless(os.name == 'nt', 'export_ios_windows.py is for Windows')
class ExportOnWindows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.clang = export.find_clang(None)
        except export.ExportError as e:
            raise unittest.SkipTest(str(e))
        cls.dir = tempfile.TemporaryDirectory()
        cls.root = Path(cls.dir.name)
        cls.hosts = export.build(cls.clang, cls.root, cls.root/'build.log')
        cls.images = work_folder(cls.root/'tree')
        cls.layouts = export.module_layouts(cls.root/'tree')
        cls.out = cls.root/'tree'/export.EXPORT_DIR
        with mock.patch.object(export, 'EXPECTED', cls.root/'tree/expected.json'):
            cls.counts, cls.sections = export.export(cls.hosts, cls.layouts, cls.out, cls.clang)
        cls.x0 = (cls.out/'main.x0.bin').read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def check(self, sections):
        return export.check(self.hosts['check'], sections, self.layouts, sections/'check-ios.log', 'check')

    def sections_with(self, name, x0):
        """A copy of the export with main.x0 replaced."""
        sections = self.root/name
        sections.mkdir(exist_ok=True)
        for part in ('x0', 'w', 'x1'):
            for module in LAYOUTS:
                data = x0 if (module, part) == ('main', 'x0') else (self.out/f'{module}.{part}.bin').read_bytes()
                (sections/f'{module}.{part}.bin').write_bytes(data)
        return sections

    def test_the_export_changes_the_sites_and_the_veneers_only(self):
        text = export.gen_embed.up(LAYOUT['TEXT_END'])
        self.assertEqual(len(self.x0), text)
        self.assertEqual(words_changed(self.images['main'][:text], self.x0), (set(SITES) - UNCHANGED) | VENEERS)
        for name, layout in LAYOUTS.items():
            image = self.images[name] + bytes(export.gen_embed.up(layout['FILE_SIZE']) - layout['FILE_SIZE'])
            text = export.gen_embed.up(layout['TEXT_END'])
            if name != 'main':
                self.assertEqual((self.out/f'{name}.x0.bin').read_bytes(), image[:text])
            self.assertEqual((self.out/f'{name}.w.bin').read_bytes(), image[text:layout['PATCH_OFF']])
            self.assertEqual((self.out/f'{name}.x1.bin').read_bytes(), image[layout['PATCH_OFF']:])
        self.assertEqual(self.counts, {'main': {'text': len((set(SITES) - UNCHANGED) | VENEERS), 'patch_area': 0},
                                       'subsdk0': {'text': 0, 'patch_area': 0}, 'sdk': {'text': 0, 'patch_area': 0}})

    def test_the_layout_and_the_record_name_the_sections(self):
        export.gen_embed.write_layout(self.out, self.root/'layout-of.json', export.NAMES)
        self.assertEqual((self.out/'layout.json').read_text(), (self.root/'layout-of.json').read_text())
        record = json.loads((self.out/'export-ios.json').read_text())
        self.assertEqual(record['sections'], self.sections)
        self.assertEqual(record['environment'], {'TOTK_RENDER_RES': '1280x720', 'TOTK_EXPORT_IOS': '<this folder>'})
        patches = export.PATCHES.read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(record['sources']['runtime/game_patches_v143.c'], hashlib.sha256(patches).hexdigest())

    def test_the_device_accepts_the_export_with_every_patch(self):
        self.assertEqual(self.check(self.out), [])
        self.assertIn("the device's checks of the embedded code passed", (self.out/'check-ios.log').read_text())

    def test_the_device_starts_sections_from_before_the_fade_fix_without_it_and_says_so(self):
        old = bytearray(self.x0)   # as 30a1b93 exported main: these sites original, the fade veneer padding
        for site, word in {**FADE, **RENDER_RES}.items():
            struct.pack_into('<I', old, site, word)
        old[FADE_VENEER.start:FADE_VENEER.stop] = bytes(len(FADE_VENEER))
        missing = self.check(self.sections_with('old', bytes(old)))
        self.assertEqual(len(missing), 2, missing)
        self.assertTrue(any('fade counters' in line for line in missing), missing)
        self.assertTrue(any('render resolution' in line for line in missing), missing)

    def test_the_device_refuses_a_half_written_fade_fix(self):
        half = bytearray(self.x0)   # the jumps without their veneer
        half[FADE_VENEER.start:FADE_VENEER.stop] = bytes(len(FADE_VENEER))
        with self.assertRaisesRegex(export.ExportError, 'embedded fade patch mismatch'):
            self.check(self.sections_with('half', bytes(half)))

    def test_an_export_without_a_patch_is_refused(self):
        with mock.patch.object(export, 'EXPECTED', self.root/'tree/expected.json'), \
                mock.patch.object(export, 'EXPORT_ENV', {**export.EXPORT_ENV, 'TOTK_FADE_FIX': '0'}):
            with self.assertRaisesRegex(export.ExportError, 'lacks patches.*fade counters'):
                export.export(self.hosts, self.layouts, self.root/'without-fade', self.clang)
        self.assertEqual(sorted(p.name for p in (self.root/'without-fade').iterdir()), ['check-ios.log', 'export-ios.log'])


class Inputs(unittest.TestCase):
    def test_no_totk_variable_of_the_shell_reaches_the_patches(self):
        with mock.patch.dict(os.environ, {'TOTK_FADE_FIX': '0', 'totk_render_res': '0'}):
            env = export.environment({'TOTK_RENDER_RES': '1280x720'})
        self.assertEqual({k for k in env if k.upper().startswith('TOTK_')}, {'TOTK_RENDER_RES'})

    def test_the_work_folder_gives_each_module_its_layout(self):
        with tempfile.TemporaryDirectory() as d:
            work_folder(Path(d))
            layouts = export.module_layouts(Path(d))
            self.assertEqual({n: layout for n, (_, layout) in layouts.items()}, LAYOUTS)
            (Path(d)/'rewritten/v143/sdk.fixups.tsv').write_text('# TEXT_END\t0x4000\n')
            with self.assertRaisesRegex(export.ExportError, 'needs TEXT_END'):
                export.module_layouts(Path(d))

    def test_the_runtime_layout_differs_from_the_30a1b93_app_in_main_x0_only(self):
        """ios/ci/embed-layout-v143.json pins an export of the same rewrites as the sections of the app 30a1b93 built:
        the same sizes and the same W and x1; main's text carries the patches added since."""
        pinned = {(m['name'], part): (m[part]['size'], m[part]['sha256'])
                  for m in json.loads(export.PINNED_LAYOUT.read_text())['modules'] for part in ('x0', 'w', 'x1')}
        old = recover_modules.APP_SECTIONS
        self.assertEqual(sorted(pinned), sorted(old))
        self.assertEqual({k: v[0] for k, v in pinned.items()}, {k: v[0] for k, v in old.items()})
        self.assertEqual({k for k in pinned if pinned[k] != old[k]}, {('main', 'x0')})


if __name__ == '__main__':
    unittest.main()
