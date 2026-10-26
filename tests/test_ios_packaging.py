"""games/totk/ios/tools/build_ipa.py: what an iOS build leaves out of the way and copies (2026-10-23)."""
import sys
import tempfile
import time
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]/'games/totk/ios/tools'
sys.path.insert(0, str(TOOLS))
import build_ipa  # noqa: E402
import install_device  # noqa: E402


class Discard(unittest.TestCase):
    def test_a_folder_is_moved_aside_at_once_and_deleted_later(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); old = root/'TOTK.app'
            (old/'GameData/shader-seed').mkdir(parents=True)
            for i in range(50):
                (old/f'GameData/shader-seed/{i}.metallib').write_bytes(b'x')
            build_ipa.discard(old)
            self.assertFalse(old.exists())   # the path is free for the new build right away
            for _ in range(100):
                if not any(root.iterdir()):
                    break
                time.sleep(0.05)
            self.assertEqual(list(root.iterdir()), [])   # and the moved folder is gone once the background delete ran

    def test_a_missing_path_is_fine(self):
        with tempfile.TemporaryDirectory() as d:
            build_ipa.discard(Path(d)/'none')


class SeedBeside(unittest.TestCase):
    """--ios-game-data documents leaves the startup shaders beside the output; the README installs the .ipa, and the
    seed was pushed only for an .app folder, so the game said 'No shaders' after a successful install."""
    def layout(self, root, output):
        (root/'Tears of the Kingdom-shader-seed').mkdir()
        (root/'Tears of the Kingdom-shader-seed/fingerprint.txt').write_text('f' * 64)
        app = root/'signed/Payload/TOTK.app'; (app/'GameData').mkdir(parents=True)
        return root/output, app

    def test_an_ipa_gets_its_seed(self):
        with tempfile.TemporaryDirectory() as d:
            ipa, app = self.layout(Path(d), 'Tears of the Kingdom.ipa'); ipa.write_bytes(b'PK')
            self.assertEqual(install_device.seed_beside(ipa, app), Path(d)/'Tears of the Kingdom-shader-seed')

    def test_an_app_folder_gets_its_seed(self):
        with tempfile.TemporaryDirectory() as d:
            out, app = self.layout(Path(d), 'Tears of the Kingdom.app'); out.mkdir()
            self.assertEqual(install_device.seed_beside(out, out), Path(d)/'Tears of the Kingdom-shader-seed')

    def test_an_app_that_carries_its_seed_gets_none(self):
        with tempfile.TemporaryDirectory() as d:
            ipa, app = self.layout(Path(d), 'Tears of the Kingdom.ipa'); (app/'GameData/shader-seed').mkdir()
            self.assertIsNone(install_device.seed_beside(ipa, app))


def read_pack(parts):
    """ios/Sources/main.m seed_unpack, in Python: the files of a pack stream cut into parts."""
    data = b''.join(p.read_bytes() for p in parts); assert data[:9] == b'TOTKPACK1'; at, out = 9, {}
    while True:
        nl = int.from_bytes(data[at:at + 2], 'little'); at += 2
        if not nl: return out, at == len(data)
        name = data[at:at + nl].decode(); at += nl
        size = int.from_bytes(data[at:at + 8], 'little'); at += 8
        out[name] = data[at:at + size]; at += size


class ShaderPack(unittest.TestCase):
    def test_files_come_back_whole_across_part_boundaries(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); seed = root/'seed'; seed.mkdir(); parts = []
            files = {'a.metal': b'x' * 1000, 'b.json': b'{}', 'empty.variants': b'', 'c.metallib': bytes(range(256)) * 3}
            for n, b in files.items():
                (seed/n).write_bytes(b)
            install_device.write_pack(seed, sorted(files), root, 'shader-seed-x', 97, parts.append)
            self.assertGreater(len(parts), 10)   # cut in the middle of names, sizes and contents
            self.assertTrue(all(p.stat().st_size <= 97 for p in parts))
            got, exact = read_pack(parts)
            self.assertEqual(got, files)
            self.assertTrue(exact)   # nothing after the end mark



class FullHD(unittest.TestCase):
    """Settings › Full HD (docked): off by default, Tears of the Kingdom only, with the 1600x900 scene (1.4.3 renders
    960x540 on the phone otherwise), and no switch in Breath of the Wild's Settings pane (build_ipa.py)."""
    def test_switch_off_by_default_and_docked_at_1600x900(self):
        import plistlib, re
        ios = TOOLS.parent
        specs = plistlib.loads((ios/'Settings.bundle/Root.plist').read_bytes())['PreferenceSpecifiers']
        switch = [s for s in specs if s.get('Key') == 'TOTK_DOCKED']
        self.assertEqual(len(switch), 1)
        self.assertIs(switch[0]['DefaultValue'], False)
        main = (ios/'Sources/main.m').read_text()
        branch = re.search(r'#ifndef GAME_BOTW\n(.*?)#endif', main[main.index('TOTK_DOCKED') - 200:], re.S)
        self.assertTrue(branch and 'TOTK_DOCKED' in branch.group(1))
        for line in ('"TOTK_OPERATION_MODE","docked"', '"TOTK_IOS_DRAWABLE_H","1080"', '"TOTK_RENDER_RES","1600x900"'):
            self.assertIn(line, branch.group(1))
        build = (TOOLS/'build_ipa.py').read_text()
        self.assertIn("s.get('Key')=='TOTK_DOCKED'", build)
        self.assertIn("'      - path: Gen/Settings.bundle'", build)


class MotionSettings(unittest.TestCase):
    """Settings › Motion (Sources/motion_input.m): the keys, values and defaults of the 1.4.3 iPad build of 2026-10-22, so
    a player's choices keep their meaning. The code reads the same keys, accepts the same words, falls back to and
    registers the same defaults, and Breath of the Wild's pane, which loses the Full HD group (build_ipa.py), keeps the
    motion group. Other groups may come and go: nothing here counts them or depends on where they are."""
    def test_pane_and_code_agree_and_botw_keeps_the_group(self):
        import plistlib, re
        ios = TOOLS.parent
        specs = plistlib.loads((ios/'Settings.bundle/Root.plist').read_bytes())['PreferenceSpecifiers']
        def one(key):
            found = [s for s in specs if s.get('Key') == key]
            self.assertEqual(len(found), 1, key)
            return found[0]
        source, invert = one('TOTK_MOTION_SOURCE'), one('TOTK_DEVICE_GYRO_INVERT_PITCH')
        self.assertEqual(source['Type'], 'PSMultiValueSpecifier')
        self.assertEqual(source['Values'], ['auto', 'controller', 'device', 'off'])
        self.assertEqual(len(source['Titles']), len(source['Values']))
        self.assertEqual(source['DefaultValue'], 'auto')
        self.assertEqual(invert['Type'], 'PSToggleSwitchSpecifier')
        self.assertIs(invert['DefaultValue'], True)

        code = (ios/'Sources/motion_input.m').read_text(encoding='utf-8')
        names = dict(re.findall(r'\b(k\w+Key) = @"(\w+)"', code))
        self.assertEqual(names, {'kSourceKey': 'TOTK_MOTION_SOURCE', 'kInvertKey': 'TOTK_DEVICE_GYRO_INVERT_PITCH'})
        self.assertIn('stringForKey:kSourceKey', code)
        self.assertIn('boolForKey:kInvertKey', code)
        accepted = re.search(r'@\[([^\]]*)\] containsObject:mode\] \? mode : @"(\w+)"', code)
        self.assertTrue(accepted)
        self.assertEqual(re.findall(r'@"(\w+)"', accepted.group(1)), source['Values'])
        self.assertEqual(accepted.group(2), source['DefaultValue'])   # anything else counts as the default
        registered = re.search(r'registerDefaults:@\{([^}]*)\}\]', code)
        self.assertTrue(registered)
        defaults = {names[key]: word if flag == '' else flag == 'YES'
                    for key, word, flag in re.findall(r'(k\w+Key): @(?:"(\w*)"|(YES|NO))', registered.group(1))}
        self.assertEqual(defaults, {'TOTK_MOTION_SOURCE': source['DefaultValue'],
                                    'TOTK_DEVICE_GYRO_INVERT_PITCH': invert['DefaultValue']})

        # Breath of the Wild: build_ipa.py takes out the Full HD switch and the group in front of it.
        self.assertIn('del specs[at-1:at+1]', (TOOLS/'build_ipa.py').read_text(encoding='utf-8'))
        botw = list(specs)
        at = next(i for i, s in enumerate(botw) if s.get('Key') == 'TOTK_DOCKED')
        del botw[at - 1:at + 1]
        keys = [s.get('Key') for s in botw]
        self.assertNotIn('TOTK_DOCKED', keys)
        first, last = keys.index('TOTK_MOTION_SOURCE'), keys.index('TOTK_DEVICE_GYRO_INVERT_PITCH')
        self.assertEqual(botw[first - 1]['Type'], 'PSGroupSpecifier')   # the motion group's heading is still there
        self.assertLess(first, last)
        self.assertFalse([s for s in botw[first:last] if s['Type'] == 'PSGroupSpecifier'])   # both rows in that group


if __name__ == '__main__':
    unittest.main()
