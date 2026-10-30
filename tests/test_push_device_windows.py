"""games/totk/ios/tools/push_device_windows.py against a local folder standing for the app's container (app_container.py
LocalContainer, what --simulate uses): the RomFS image in parts with its marker last, a copy that stopped going on, the
shaders as one pack read back as ios/Sources/main.m seed_unpack reads it, and saves backed up and restored with their
account. No device and no game files."""
import hashlib
import json
import plistlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]/'games/totk/ios/tools'
sys.path.insert(0, str(TOOLS))
import app_container  # noqa: E402
import push_device_windows as push  # noqa: E402


def read_pack(parts):
    """The entries of a shader pack as main.m seed_unpack reads them: "TOTKPACK1", then per file a u16 name length, the
    name, a u64 size and the bytes, a zero name length last. Returns ({name: bytes}, whether the stream ends there)."""
    data = b''.join(p.read_bytes() for p in parts)
    assert data[:9] == b'TOTKPACK1'
    at, out = 9, {}
    while True:
        nl = int.from_bytes(data[at:at + 2], 'little'); at += 2
        if not nl:
            return out, at == len(data)
        name = data[at:at + nl].decode(); at += nl
        assert nl < 256 and '/' not in name and name not in out
        size = int.from_bytes(data[at:at + 8], 'little'); at += 8
        out[name] = data[at:at + size]; at += size


class Counting(app_container.LocalContainer):
    """Records what it is asked to do (uploads, and every upload, write and remove in order in ops); with stop set, the
    upload after that many raises, as a cable pulled out would."""
    def __init__(self, *a):
        super().__init__(*a); self.uploads, self.ops, self.stop = [], [], None

    def upload(self, rel, *args, **kw):
        if self.stop is not None and len(self.uploads) >= self.stop:
            raise OSError('the cable came out')
        self.uploads.append(rel); self.ops.append(('upload', rel)); super().upload(rel, *args, **kw)

    def write(self, rel, data):
        self.ops.append(('write', rel)); super().write(rel, data)

    def remove(self, rel):
        self.ops.append(('remove', rel)); super().remove(rel)


def quiet(*_):
    pass


class Push(unittest.TestCase):
    def setUp(self):
        self.part, push.PART = push.PART, 1000
        self.dir = tempfile.TemporaryDirectory(); self.root = Path(self.dir.name)
        self.box = Counting(self.root/'device', 'a.b'); self.box.install(self.ipa())

    def tearDown(self):
        push.PART = self.part; self.dir.cleanup()

    def ipa(self, extra=()):
        ipa = self.root/'a.ipa'
        with zipfile.ZipFile(ipa, 'w') as z:
            z.writestr('Payload/A.app/Info.plist', plistlib.dumps({'CFBundleIdentifier': 'a.b', 'CFBundleShortVersionString': '1'}))
            for n in extra: z.writestr(f'Payload/A.app/{n}', b'x')
        return ipa

    def image(self, size=3500):
        romfs = self.root/'romfs'; romfs.mkdir(exist_ok=True)
        data = bytes(i % 251 for i in range(size)); (romfs/'romfs.bin').write_bytes(data)
        (romfs/'index.json').write_text(json.dumps({'romfs_sha256': hashlib.sha256(data).hexdigest(), 'romfs_size': size}))
        return romfs/'romfs.bin', data

    def device(self, name=''):
        return self.root/'device'/push.GAMEDATA/name

    def test_the_image_goes_in_parts_with_its_marker_last(self):
        image, data = self.image()
        self.assertEqual(push.push_romfs(self.box, image, log=quiet), 'copied')
        parts = sorted(self.device().glob('romfs.bin.*'))
        self.assertEqual([p.stat().st_size for p in parts], [1000, 1000, 1000, 500])   # romfs.c: equal parts, the last shorter
        self.assertEqual(b''.join(p.read_bytes() for p in parts), data)
        self.assertEqual(self.device('romfs.sha256').read_text(), hashlib.sha256(data).hexdigest() + '\n')
        self.assertEqual(push.push_romfs(self.box, image, log=quiet), 'present')

    def test_a_stopped_copy_goes_on_from_the_parts_already_there(self):
        image, data = self.image()
        push.push_romfs(self.box, image, log=quiet)
        sha = hashlib.sha256(data).hexdigest()
        self.device('romfs.sha256').write_text(f'copying {sha}\n')
        self.device('romfs.bin.002').write_bytes(b'cut')   # the cable came out during part 3
        self.device('romfs.bin.004').write_bytes(b'x' * 1000)   # a part beyond this image's
        self.box.uploads.clear()
        self.assertEqual(push.push_romfs(self.box, image, log=quiet), 'copied')
        self.assertEqual(self.box.uploads, [f'{push.GAMEDATA}/romfs.bin.002'])
        self.assertFalse(self.device('romfs.bin.004').exists())
        self.assertEqual(b''.join(p.read_bytes() for p in sorted(self.device().glob('romfs.bin.*'))), data)
        self.assertEqual(self.device('romfs.sha256').read_text().strip(), sha)

    def test_parts_all_there_get_their_marker_only(self):
        image, _ = self.image()
        push.push_romfs(self.box, image, log=quiet)
        self.device('romfs.sha256').unlink(); self.box.uploads.clear()
        self.assertEqual(push.push_romfs(self.box, image, log=quiet), 'marker')
        self.assertEqual(self.box.uploads, [])

    def test_a_whole_image_of_another_kind_is_not_covered_up(self):
        image, _ = self.image()
        self.device().mkdir(parents=True); self.device('romfs.bin').write_bytes(b'old')
        with self.assertRaises(push.PushError):
            push.push_romfs(self.box, image, log=quiet)

    def test_the_shaders_go_as_one_pack_the_app_unpacks(self):
        push.PART = 777   # parts that cut entries, names and sizes
        seed = self.root/'TOTK-shader-seed'; seed.mkdir()
        files = {f'{"a" * 64}-{i:012x}_b.metal': bytes([i]) * (300 * i) for i in range(1, 8)}
        files['fingerprint.txt'] = b'f' * 64 + b'\n'
        for n, b in files.items(): (seed/n).write_bytes(b)
        self.assertEqual(push.push_seed(self.box, seed, log=quiet), 'copied')
        folder, fp = self.device('shader-seed.txt').read_text().split('\n')[:2]
        self.assertEqual(fp, 'f' * 64)
        self.assertTrue(folder.startswith('shader-seed-' + 'f' * 12))
        parts = sorted(self.device().glob(folder + '.pack.*'))
        self.assertGreater(len(parts), 3)
        self.assertTrue(all(p.stat().st_size == 777 for p in parts[:-1]))
        self.assertEqual(read_pack(parts), (files, True))
        self.assertEqual(sorted(p.name for p in seed.parent.iterdir() if p.name.startswith('tmp')), [])   # parts beside the seed are gone
        self.assertEqual(push.push_seed(self.box, seed, log=quiet), 'present')

    def test_saves_come_back_with_their_account(self):
        save = self.root/'device'/push.SAVE
        uid = (1).to_bytes(8, 'little') + (2).to_bytes(8, 'little')
        account = push.account_folder(uid)
        self.assertEqual(account, '0000000000000002' + '0000000000000001')   # fs_host.c: hi, then lo
        (save/'save'/account).mkdir(parents=True); (save/'account.uid').write_bytes(uid)
        (save/'save'/account/'progress.sav').write_bytes(b'game 1')
        backup = push.backup_save(self.box, self.root/'backups', log=quiet)
        manifest = json.loads((backup/'backup-manifest.json').read_text())
        self.assertEqual((manifest['account'], manifest['account_saves']), (account, 1))
        (save/'save'/account/'progress.sav').write_bytes(b'game 2, later')
        push.restore_save(self.box, backup, self.root/'safety', log=quiet)
        self.assertEqual((save/'save'/account/'progress.sav').read_bytes(), b'game 1')
        safety = next((self.root/'safety').iterdir())
        self.assertEqual((safety/'save/save'/account/'progress.sav').read_bytes(), b'game 2, later')
        (backup/'save/account.uid').write_bytes(b'x' * 16)   # a backup changed since it was made is refused
        with self.assertRaises(push.PushError):
            push.restore_save(self.box, backup, self.root/'safety', log=quiet)

    def test_a_backup_of_another_app_needs_other_app(self):
        save = self.root/'device'/push.SAVE; save.mkdir(parents=True)
        (save/'account.uid').write_bytes(bytes(16))
        backup = push.backup_save(self.box, self.root/'backups', log=quiet)
        other = app_container.LocalContainer(self.root/'device', 'c.d')
        with self.assertRaises(push.PushError):
            push.restore_save(other, backup, self.root/'safety', log=quiet)
        push.restore_save(other, backup, self.root/'safety', other_app=True, log=quiet)

    def test_the_ipa_says_what_it_carries(self):
        info = app_container.ipa_info(self.ipa(['GameData/shader-seed/seed-manifest.json']))
        self.assertEqual(info['carries'], {'seed': True, 'romfs': False})
        self.assertEqual(self.box.installed()['CFBundleIdentifier'], 'a.b')


FONT, TABLE, LAYOUT = ('Font/Font.Nin_NX_NVN.bfarc.zs', 'System/Resource/ResourceSizeTable.Product.140.Nin_NX_NVN.rsizetable.zs',
                       'UI/LayoutArchive/Common.Product.140.Nin_NX_NVN.blarc.zs')


class Mods(unittest.TestCase):
    """push-mod and remove-mod: a RomFS mod in Documents/mods/<version>, which ios/Sources/main.m hands to the runtime
    when it holds a manifest.tsv; the manifest is written as make_mod_manifest.py writes it."""
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(); self.root = Path(self.dir.name)
        self.box = Counting(self.root/'device', 'a.b')
        self.on_device = self.root/'device'/push.MODS/'v143'

    def tearDown(self):
        self.dir.cleanup()

    def mod(self, files, name='mod', extra=''):
        folder = self.root/name
        lines = []
        for path, data in files.items():
            (folder/path).parent.mkdir(parents=True, exist_ok=True); (folder/path).write_bytes(data)
            lines.append(f'{path}\t{len(data)}\t{hashlib.sha256(data).hexdigest()}\t{"0" * 64}')
        (folder/'manifest.tsv').write_bytes(('# path\tsize\tsha256\toriginal_sha256\n' + '\n'.join(lines) + '\n' + extra).encode())
        (folder/(LAYOUT + '.mod-original')).parent.mkdir(parents=True, exist_ok=True)
        (folder/(LAYOUT + '.mod-original')).write_bytes(b'the mod\'s own archive, not listed')
        return folder

    def device_files(self):
        return {p.relative_to(self.on_device).as_posix(): p.read_bytes() for p in self.on_device.rglob('*') if p.is_file()}

    def test_the_listed_files_go_in_and_the_manifest_last(self):
        files = {FONT: b'font' * 300, TABLE: b'table', LAYOUT: b'layout' * 50}
        mod = self.mod(files)
        self.assertEqual(push.push_mod(self.box, mod, log=quiet), 'copied')
        self.assertEqual(self.device_files(), {**files, 'manifest.tsv': (mod/'manifest.tsv').read_bytes()})   # not .mod-original
        written = self.box.ops.index(('write', f'{push.MODS}/v143/manifest.tsv'))
        self.assertTrue(all(i < written for i, op in enumerate(self.box.ops) if op[0] == 'upload'))
        self.assertEqual(push.push_mod(self.box, mod, log=quiet), 'present')
        out = []
        self.box.install(self.ipa()); push.status(self.box, log=out.append)
        self.assertIn('mods/v143: 3 files in manifest.tsv', out)

    def ipa(self):
        ipa = self.root/'a.ipa'
        with zipfile.ZipFile(ipa, 'w') as z:
            z.writestr('Payload/A.app/Info.plist', plistlib.dumps({'CFBundleIdentifier': 'a.b'}))
        return ipa

    def test_a_stopped_copy_goes_on_without_the_manifest_in_place(self):
        old = self.mod({FONT: b'old font', LAYOUT: b'old layout'}, 'old')
        push.push_mod(self.box, old, log=quiet)
        new_files = {FONT: b'new font', LAYOUT: b'new layout', TABLE: b'table'}   # FONT and LAYOUT keep their sizes
        new = self.mod(new_files, 'new')
        self.box.stop = len(self.box.uploads) + 1   # the cable comes out after the first file
        with self.assertRaises(OSError):
            push.push_mod(self.box, new, log=quiet)
        self.assertFalse((self.on_device/'manifest.tsv').exists())   # the app loads no half-copied mod
        self.assertEqual((self.on_device/push.COPYING).read_bytes(), (new/'manifest.tsv').read_bytes())
        self.box.stop = None; self.box.uploads.clear()
        self.assertEqual(push.push_mod(self.box, new, log=quiet), 'copied')
        self.assertEqual(len(self.box.uploads), 2)   # the file copied before the stop is kept
        self.assertEqual(self.device_files(), {**new_files, 'manifest.tsv': (new/'manifest.tsv').read_bytes()})

    def test_another_mod_replaces_the_folder(self):
        push.push_mod(self.box, self.mod({FONT: b'a', 'Sound/Extra.bwav': b'extra'}, 'one'), log=quiet)
        two = self.mod({LAYOUT: b'b'}, 'two')
        push.push_mod(self.box, two, log=quiet)
        self.assertEqual(self.device_files(), {LAYOUT: b'b', 'manifest.tsv': (two/'manifest.tsv').read_bytes()})
        self.assertFalse((self.on_device/'Sound').exists())

    def test_a_mod_the_game_would_refuse_is_not_copied(self):
        files = {FONT: b'font'}
        cases = {
            'no manifest': lambda m: (m/'manifest.tsv').unlink(),
            'changed file': lambda m: (m/FONT).write_bytes(b'FONT'),
            'blank CR LF line': lambda m: (m/'manifest.tsv').write_bytes((m/'manifest.tsv').read_bytes() + b'\r\n'),
            'path out of the RomFS': lambda m: (m/'manifest.tsv').write_text(
                f'../{FONT}\t4\t{hashlib.sha256(b"font").hexdigest()}\t-\n'),
            'listed twice': lambda m: (m/'manifest.tsv').write_bytes((m/'manifest.tsv').read_bytes() * 2),
        }
        for name, spoil in cases.items():
            with self.subTest(name):
                mod = self.mod(files, name.replace(' ', '-')); spoil(mod)
                with self.assertRaises(push.PushError):
                    push.push_mod(self.box, mod, log=quiet)
                self.assertFalse(self.on_device.exists())

    def test_remove_mod_takes_the_folder_away(self):
        push.push_mod(self.box, self.mod({FONT: b'font', LAYOUT: b'layout'}), log=quiet)
        self.box.ops.clear()
        self.assertEqual(push.remove_mod(self.box, log=quiet), 'removed')
        self.assertEqual(self.box.ops[0], ('remove', f'{push.MODS}/v143/manifest.tsv'))
        self.assertFalse(self.on_device.exists())
        self.assertEqual(push.remove_mod(self.box, log=quiet), 'none')

    def test_a_slot_has_its_own_folder(self):
        plain = self.mod({FONT: b'plain'}, 'plain')
        strong = self.mod({FONT: b'strong font'}, 'strong')
        self.assertEqual(push.mod_target('v143'), 'v143')
        self.assertEqual(push.mod_target('v143', 'strong'), 'v143-strong')
        push.push_mod(self.box, plain, log=quiet)
        push.push_mod(self.box, strong, push.mod_target('v143', 'strong'), log=quiet)
        slot = self.on_device.with_name('v143-strong')
        self.assertEqual((slot/FONT).read_bytes(), b'strong font')
        self.assertEqual((self.on_device/FONT).read_bytes(), b'plain')
        self.assertEqual(push.remove_mod(self.box, push.mod_target('v143', 'strong'), log=quiet), 'removed')
        self.assertFalse(slot.exists())
        self.assertTrue((self.on_device/'manifest.tsv').is_file())

    def slots(self):
        """A folder holding the four slot folders, as make_gameplay_tuning.py --slots leaves them."""
        for slot in push.MOD_SLOTS:
            self.mod({FONT: f'{slot} font'.encode(), LAYOUT: f'{slot} layout'.encode()}, f'mods/v143-{slot}')
        return self.root/'mods'

    def test_push_slots_copies_every_slot(self):
        folder = self.slots()
        self.assertEqual(push.push_slots(self.box, folder, log=quiet), {slot: 'copied' for slot in push.MOD_SLOTS})
        for slot in push.MOD_SLOTS:
            on_device = self.on_device.with_name(f'v143-{slot}')
            self.assertEqual((on_device/FONT).read_bytes(), f'{slot} font'.encode())
            self.assertEqual((on_device/'manifest.tsv').read_bytes(), (folder/f'v143-{slot}/manifest.tsv').read_bytes())
        self.assertEqual(push.push_slots(self.box, folder, log=quiet), {slot: 'present' for slot in push.MOD_SLOTS})

    def test_push_slots_checks_every_folder_before_it_copies(self):
        folder = self.slots()
        (folder/'v143-max'/FONT).write_bytes(b'changed since the manifest')
        with self.assertRaises(push.PushError):
            push.push_slots(self.box, folder, log=quiet)
        self.assertEqual(self.box.uploads, [])
        (folder/'v143-max/manifest.tsv').unlink()
        with self.assertRaises(push.PushError):
            push.push_slots(self.box, folder, log=quiet)
        self.assertEqual(self.box.uploads, [])

    def test_push_slots_goes_on_where_it_stopped(self):
        folder = self.slots()
        self.box.stop = 3   # the two files of the first slot, then one of the second
        with self.assertRaises(OSError):
            push.push_slots(self.box, folder, log=quiet)
        second = self.on_device.with_name(f'v143-{push.MOD_SLOTS[1]}')
        self.assertFalse((second/'manifest.tsv').exists())   # the app loads no half-copied slot
        self.box.stop = None; self.box.uploads.clear()
        done = push.push_slots(self.box, folder, log=quiet)
        self.assertEqual(done, {push.MOD_SLOTS[0]: 'present', **{slot: 'copied' for slot in push.MOD_SLOTS[1:]}})
        self.assertEqual(len(self.box.uploads), 1 + 2 * 2)   # what the second slot still lacked, then the last two whole
        self.assertTrue((second/'manifest.tsv').is_file())

    def test_the_commands_with_simulate(self):
        import subprocess
        mod = self.mod({FONT: b'font'})
        script = TOOLS/'push_device_windows.py'
        def run(*args):
            return subprocess.run([sys.executable, str(script), *map(str, args), '--simulate', self.root/'device'],
                                  capture_output=True, text=True)
        deploy = run('deploy', self.ipa(), '--no-backup', '--mod', mod)
        self.assertEqual(deploy.returncode, 0, deploy.stderr)
        self.assertEqual((self.on_device/FONT).read_bytes(), b'font')
        removed = run('remove-mod', '--bundle-id', 'a.b')
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertFalse(self.on_device.exists())
        pushed = run('push-mod', mod, '--bundle-id', 'a.b', '--version', 'v121')
        self.assertEqual(pushed.returncode, 0, pushed.stderr)
        self.assertTrue((self.root/'device'/push.MODS/'v121/manifest.tsv').is_file())
        slot = run('push-mod', mod, '--bundle-id', 'a.b', '--slot', 'max')
        self.assertEqual(slot.returncode, 0, slot.stderr)
        self.assertTrue(self.on_device.with_name('v143-max').joinpath('manifest.tsv').is_file())
        removed = run('remove-mod', '--bundle-id', 'a.b', '--slot', 'max')
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertFalse(self.on_device.with_name('v143-max').exists())
        deployed = run('deploy', self.ipa(), '--no-backup', '--mod', mod, '--slot', 'off')
        self.assertEqual(deployed.returncode, 0, deployed.stderr)
        self.assertTrue(self.on_device.with_name('v143-off').joinpath('manifest.tsv').is_file())
        slots = run('push-slots', self.slots(), '--bundle-id', 'a.b')
        self.assertEqual(slots.returncode, 0, slots.stderr)
        self.assertEqual(self.on_device.with_name('v143-strong').joinpath(FONT).read_bytes(), b'strong font')
        self.assertNotEqual(run('deploy', self.ipa(), '--no-backup', '--slot', 'off').returncode, 0)   # no --mod to put there
        self.assertNotEqual(run('push-mod', mod, '--bundle-id', 'a.b', '--slot', 'other').returncode, 0)


if __name__ == '__main__':
    unittest.main()
