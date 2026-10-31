"""The iPad Settings pane's mode -> environment mapping, without UIKit or a device."""
import plistlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLIST = ROOT / 'games/totk/ios/Settings.bundle/Root.plist'


class IOSSettings(unittest.TestCase):
    def _helper(self):
        compiler = shutil.which('cc')
        if not compiler:
            self.skipTest('A C compiler is required')
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory)
        executable = directory / 'ios-settings'
        build = subprocess.run(
            [compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
             '-I', str(ROOT / 'games/totk/ios/Sources'),
             str(ROOT / 'tests/test_ios_settings.c'),
             str(ROOT / 'games/totk/ios/Sources/settings_map.c'),
             '-o', str(executable)],
            capture_output=True, text=True)
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        return executable

    def _rows(self):
        with open(PLIST, 'rb') as file:
            root = plistlib.load(file)
        return {item['Key']: item for item in root['PreferenceSpecifiers'] if 'Key' in item}

    def test_picture_and_frame_modes(self):
        run = subprocess.run([str(self._helper())], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('ios settings ok', run.stdout)

    def test_the_frame_rate_reaches_the_runtime_on_the_launch_it_is_picked(self):
        """Production main.m and hle_nvn.c in main.m's order, in tests/ios_frame_pick_probe.c."""
        compiler = shutil.which('cc')
        if not compiler:
            self.skipTest('A C compiler is required')
        main = (ROOT / 'games/totk/ios/Sources/main.m').read_text(encoding='utf-8')
        hle = (ROOT / 'games/totk/third_party/d2r_gfx/gfx/nvn/hle_nvn.c').read_text(encoding='utf-8')
        code = '\n'.join((
            re.search(r'static _Atomic int g_phone_hold30 = -1;.*?\nvoid runtime_phone_fps_set\(int fps\) \{[^\n]*\n', hle, re.S).group(),
            re.search(r'static void apply_frame_env\(.*?\n}\n', main, re.S).group(),
            re.search(r'static void apply_preset_frame_rate\(.*?\n}\n', main, re.S).group()))
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory)
        source = directory / 'probe.c'
        fixture = (ROOT / 'tests/ios_frame_pick_probe.c').read_text(encoding='utf-8')
        source.write_text(fixture.replace('/* PRODUCTION_CODE */', code), encoding='utf-8')
        executable = directory / 'ios-frame-pick'
        build = subprocess.run(
            [compiler, '-std=gnu11', '-O1', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'games/totk/ios/Sources'),
             str(source), str(ROOT / 'games/totk/ios/Sources/settings_map.c'), '-o', str(executable)],
            capture_output=True, text=True)
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        run = subprocess.run([str(executable)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('frame pick ok', run.stdout)
        self.assertIn('apply_preset_frame_rate(fps.UTF8String);',
                      re.search(r'static void apply_display_settings\(void\) \{.*?\n}', main, re.S).group())

    def test_pane_values_are_accepted(self):
        executable = self._helper()
        rows = self._rows()
        for key, flag in (('TOTK_IOS_PICTURE_MODE', '--picture'), ('TOTK_FPS_CAP', '--frame-cap')):
            self.assertIn(key, rows)
            row = rows[key]
            self.assertIn('Values', row)
            self.assertIn('Titles', row)
            self.assertIn('DefaultValue', row)
            values = row['Values']
            self.assertTrue(values, key)
            self.assertEqual(len(values), len(row['Titles']), key)
            self.assertEqual(len(values), len(set(values)), key)
            for value in values:
                with self.subTest(key=key, value=value):
                    run = subprocess.run([str(executable), flag, value], capture_output=True, text=True)
                    self.assertEqual(run.returncode, 0, f'{key}={value}: {run.stdout}{run.stderr}')
        run = subprocess.run([str(executable), '--defaults'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        picture_default, frame_default = run.stdout.splitlines()
        self.assertEqual(picture_default, rows['TOTK_IOS_PICTURE_MODE']['DefaultValue'])
        self.assertEqual(frame_default, rows['TOTK_FPS_CAP']['DefaultValue'])

    def test_two_layers_are_one_choice(self):
        # One switch selects the layer (main.m's TOTK_CUSTOM_PICTURE): the presets (Full HD, frame rate) are handed over
        # when it is off, the custom picture and frame rows when it is on. Neither layer may write the other's keys, so
        # both rows sets must stay in the pane and the switch must default to the presets.
        rows = self._rows()
        self.assertIn('TOTK_CUSTOM_PICTURE', rows)
        self.assertEqual(rows['TOTK_CUSTOM_PICTURE']['Type'], 'PSToggleSwitchSpecifier')
        self.assertIs(rows['TOTK_CUSTOM_PICTURE']['DefaultValue'], False)
        self.assertIn('TOTK_DOCKED', rows)
        self.assertIn('TOTK_PHONE_FPS', rows)
        for key in ('TOTK_IOS_PICTURE_MODE', 'TOTK_RENDER_RES', 'TOTK_FPS_CAP'):
            self.assertIn(key, rows)
        executable = self._helper()
        for value in rows['TOTK_PHONE_FPS']['Values']:
            with self.subTest(key='TOTK_PHONE_FPS', value=value):
                run = subprocess.run([str(executable), '--preset-fps', value], capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, f'TOTK_PHONE_FPS={value}: {run.stdout}{run.stderr}')
        # The key -> layer table is the one main.m filters by; a row that moves layers without the table following it
        # would be handed over (or dropped) by the wrong layer.
        for key, layer in {'TOTK_DOCKED': 'preset', 'TOTK_NATIVE_PICTURE': 'preset', 'TOTK_PHONE_FPS': 'preset',
                           'TOTK_IOS_PICTURE_MODE': 'custom', 'TOTK_RENDER_RES': 'custom',
                           'TOTK_FPS_CAP': 'custom', 'TOTK_FPS_OVERLAY': 'always'}.items():
            with self.subTest(key=key, layer=layer):
                run = subprocess.run([str(executable), '--layer', key], capture_output=True, text=True)
                self.assertEqual(run.stdout.strip(), layer, key)

    def test_the_picture_stays_16_9_until_asked(self):
        # Filling an iPad's 4:3 narrows the camera and flattens the HUD, so it is a choice of its own, off by default, with a
        # key of its own: what an earlier build stored for TOTK_ASPECT is never read, main.m only walks the pane's rows.
        rows = self._rows()
        self.assertNotIn('TOTK_ASPECT', rows)
        self.assertIs(rows['TOTK_FILL_SCREEN']['DefaultValue'], False)
        self.assertIs(rows['TOTK_NATIVE_PICTURE']['DefaultValue'], False)
        main = (ROOT / 'games/totk/ios/Sources/main.m').read_text(encoding='utf-8')
        body = re.search(r'static void apply_display_settings\(void\) \{.*?\n}', main, re.S).group()
        self.assertIn('if (![d boolForKey:@"TOTK_FILL_SCREEN"]) setenv("TOTK_ASPECT","0",0);', body)
        self.assertLess(body.index('TOTK_FILL_SCREEN'), body.index('if (totk_custom_layer) return;'))   # both layers

    def test_scene_values_are_sizes(self):
        # build_ipa.py embeds one of these sizes in the exported patch, and main.m rejects a stored value the row does
        # not list; both parse <width>x<height>.
        row = self._rows()['TOTK_RENDER_RES']
        values = row['Values']
        self.assertIn(row['DefaultValue'], values)
        self.assertEqual(len(values), len(row['Titles']))
        for value in values:
            with self.subTest(value=value):
                width, height = (int(part) for part in value.lower().split('x'))
                self.assertGreaterEqual(width, 64)
                self.assertGreaterEqual(height, 64)

    def test_large_textures_row(self):
        # main.m hands the row over in both layers and turns it into TOTK_MIP_KEEP / TOTK_MIP_DROP through
        # settings_map.c; a pane value the table does not know would fall back to the default without the player
        # seeing why.
        row = self._rows()['TOTK_LARGE_TEXTURES']
        self.assertEqual(row['Type'], 'PSMultiValueSpecifier')
        self.assertEqual(len(row['Values']), len(row['Titles']))
        self.assertIn(row['DefaultValue'], row['Values'])
        self.assertEqual(row['DefaultValue'], 'auto')
        executable = self._helper()
        for value in row['Values']:
            with self.subTest(value=value):
                run = subprocess.run([str(executable), '--textures', value], capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, f'TOTK_LARGE_TEXTURES={value}: {run.stdout}{run.stderr}')
        run = subprocess.run([str(executable), '--textures-default'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(run.stdout.strip(), row['DefaultValue'])

    def test_mod_slot_row(self):
        # main.m takes the value as the last part of a folder name, Documents/mods/<version>-<value>, and only lower-case
        # letters; the row leaves the Breath of the Wild pane, which has no such folders. A string row is what reaches
        # the runtime: a slider or a switch would hand over "1" or "0".
        row = self._rows()['TOTK_MOD_SLOT']
        self.assertEqual(row['Type'], 'PSMultiValueSpecifier')
        self.assertEqual(row['TOTKApp'], 'totk')
        self.assertEqual(row['Values'], ['off', 'moderate', 'strong', 'max'])
        self.assertEqual(row['DefaultValue'], 'strong')
        self.assertEqual(len(row['Values']), len(row['Titles']))
        for value in row['Values']:
            self.assertRegex(value, r'^[a-z]{1,15}$')

    def test_no_interpolation_switch(self):
        # MetalFX interpolation costs more GPU than the frames it replaces on this device and a downscaled output is
        # not accepted by the interpolator, so the pane must not offer a switch that can only hurt.
        self.assertNotIn('TOTK_MFX_INTERP', self._rows())

    def test_overlays_are_separate_switches(self):
        # The runtime reads the two overlays independently; a single combined mode would be a third state the player
        # cannot see.
        rows = self._rows()
        self.assertNotIn('TOTK_HUD_MODE', rows)
        for key in ('TOTK_FPS_OVERLAY', 'TOTK_SHADER_OVERLAY'):
            self.assertIn(key, rows)
            self.assertEqual(rows[key]['Type'], 'PSToggleSwitchSpecifier')
            self.assertIs(rows[key]['DefaultValue'], False)   # nothing is drawn over the game unless the player asks


    def test_behaviours_the_code_turns_on_have_an_off_row(self):
        # The default is the code's (on for Tears of the Kingdom on iOS), so a row must not hand a value over until the
        # player chooses Off: main.m skips an empty string, while a switch would hand "1" over at every launch. The rows
        # leave the Breath of the Wild pane, whose build has these behaviours off.
        nvn = ROOT / 'games/totk/third_party/d2r_gfx/gfx/nvn'
        rows = self._rows()
        for key, reader in (('TOTK_OCCL_GUARD', 'nvn_mtl.m'), ('TOTK_RT_DUP', 'nvn_mtl.m'),
                            ('TOTK_VPOOL_UNALIGNED', 'totk_vpool.c')):
            with self.subTest(key=key):
                row = rows[key]
                self.assertEqual(row['Type'], 'PSMultiValueSpecifier')
                self.assertEqual(row['TOTKApp'], 'totk')
                self.assertEqual(row['DefaultValue'], '')
                self.assertEqual(row['Values'], ['', '0'])
                self.assertEqual(len(row['Titles']), 2)
                self.assertIn(f'getenv("{key}")', (nvn / reader).read_text(encoding='utf-8'))
        main = (ROOT / 'games/totk/ios/Sources/main.m').read_text(encoding='utf-8')
        self.assertIn('[value length] && [value length] < 64', main)

    def test_a_stored_scene_the_pane_dropped_goes_on_that_launch(self):
        """A source check, apply_settings being UIKit's: the loop hands the stored scene to the variable, so only what the
        variable held before the loop tells a launch value from it."""
        main = (ROOT / 'games/totk/ios/Sources/main.m').read_text(encoding='utf-8')
        body = re.search(r'static void apply_settings\(void\) \{.*?\n}\n', main, re.S).group()
        self.assertLess(body.index('BOOL scene_from_launch = getenv("TOTK_RENDER_RES") != NULL;'),
                        body.index('for (NSString *key in defaults)'))
        self.assertIn('if (!scene_from_launch) setenv("TOTK_RENDER_RES", fallback.UTF8String, 1);', body)

    def test_a_run_stays_on_the_layer_it_launched_with(self):
        """The Settings app can flip the switch while the app runs, and the pane promises that only a relaunch takes it. Read
        again at Play, a flip left neither layer's picture applied, or a 1080 drawable in handheld mode. A source check, the
        readers being UIKit's: apply_settings reads the switch once, and everything after asks what it decided."""
        sources = ROOT / 'games/totk/ios/Sources'
        texts = {file.name: file.read_text(encoding='utf-8') for file in sources.iterdir() if file.suffix in ('.m', '.c')}
        self.assertEqual([name for name, text in texts.items() for _ in re.finditer(r'ForKey:@"TOTK_CUSTOM_PICTURE"', text)],
                         ['main.m'])
        body = re.search(r'static void apply_settings\(void\) \{.*?\n}\n', texts['main.m'], re.S).group()
        self.assertIn('BOOL custom = [d boolForKey:@"TOTK_CUSTOM_PICTURE"];\n    totk_custom_layer = custom;', body)
        self.assertEqual(sum(len(re.findall(r'totk_custom_layer = ', text)) for text in texts.values()), 1)
        self.assertIn('if (totk_custom_layer) return;',
                      re.search(r'static void apply_display_settings\(void\) \{.*?\n}', texts['main.m'], re.S).group())
        self.assertIn('BOOL presets = !totk_custom_layer;', texts['start_screen.m'])

    def test_every_row_is_applied_at_launch(self):
        # main.m registers every TOTK_* row that has a DefaultValue and hands it to the runtime as an environment
        # variable; a row without one, or a key without the prefix, would show in Settings and change nothing.
        rows = self._rows()
        self.assertTrue(rows)
        for key, row in rows.items():
            with self.subTest(key=key):
                self.assertTrue(key.startswith('TOTK_'), key)
                self.assertIn('Type', row, key)
                self.assertIn('DefaultValue', row, key)


if __name__ == '__main__':
    unittest.main()
