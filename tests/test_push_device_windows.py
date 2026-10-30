"""games/totk/ios/tools/push_device_windows.py against a local folder standing for the app's container (app_container.py
LocalContainer, what --simulate uses): the RomFS image in parts with its marker last, a copy that stopped going on, the
shaders as one pack read back as ios/Sources/main.m seed_unpack reads it, and saves backed up and restored with their
account. No device and no game files."""
import hashlib
import json
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

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


def fake_usbmux(attached, names):
    """The two pymobiledevice3 modules DeviceContainer's constructor imports, the list of connections they were asked for
    as (serial, autopair) and the list of UDIDs whose connection was closed. attached: the UDIDs usbmuxd lists; names:
    udid -> name, a device without one does not answer when it is opened without pairing."""
    opened, closed = [], []

    async def list_devices():
        return [SimpleNamespace(serial=udid) for udid in attached]

    class Lockdown:
        def __init__(self, udid):
            self.udid = udid
            self.short_info = dict(DeviceName=names.get(udid), ProductVersion='27.0', UniqueDeviceID=udid)

        async def close(self):
            closed.append(self.udid)

    async def create_using_usbmux(serial=None, autopair=True):
        opened.append((serial, autopair))
        if serial is None and not attached:
            raise LookupError('no device connected')
        if not autopair and serial not in names:
            raise PermissionError('not paired')
        return Lockdown(serial or attached[0])

    package = ModuleType('pymobiledevice3'); package.__path__ = []
    lockdown, usbmux = ModuleType('pymobiledevice3.lockdown'), ModuleType('pymobiledevice3.usbmux')
    lockdown.create_using_usbmux, usbmux.list_devices = create_using_usbmux, list_devices
    return {'pymobiledevice3': package, 'pymobiledevice3.lockdown': lockdown, 'pymobiledevice3.usbmux': usbmux}, opened, closed


class OneDevice(unittest.TestCase):
    """DeviceContainer on a fake device list: it takes a device only when that device is the one meant."""
    IPAD, PHONE = '00008132-000A', '00008110-000B'
    NAMES = {IPAD: 'My iPad', PHONE: 'My iPhone'}

    def open(self, attached, udid=None, names=NAMES, first=False):
        modules, opened, self.closed = fake_usbmux(attached, names)
        with patch.dict(sys.modules, modules), patch.dict(os.environ, {'TOTK_PUSH_FIRST_DEVICE': '1' if first else '0'}):
            try:
                return app_container.DeviceContainer('a.b', udid), opened
            except app_container.ContainerError as e:
                return e, opened

    def test_the_one_device_attached_is_taken_by_its_udid(self):
        box, opened = self.open([self.IPAD])
        self.assertEqual(opened, [(self.IPAD, True)])
        self.assertEqual(box.name, f'My iPad (iOS 27.0, {self.IPAD})')   # what the commands print before they write

    def test_a_device_on_usb_and_wifi_is_one_device(self):
        _, opened = self.open([self.IPAD, self.IPAD])
        self.assertEqual(opened, [(self.IPAD, True)])

    def test_two_spellings_of_a_udid_are_one_device(self):
        # pymobiledevice3's MuxDevice.matches_udid compares UDIDs without hyphens
        plain = self.IPAD.replace('-', '')
        _, opened = self.open([plain, self.IPAD])
        self.assertEqual(opened, [(plain, True)])
        error, opened = self.open([self.IPAD, plain, self.PHONE])
        self.assertIsInstance(error, app_container.ContainerError)
        self.assertEqual(opened, [(self.IPAD, False), (self.PHONE, False)])

    def test_two_devices_are_refused_and_listed_before_any_is_opened_for_writing(self):
        error, opened = self.open([self.IPAD, self.PHONE])
        self.assertIsInstance(error, app_container.ContainerError)
        self.assertTrue(str(error).startswith('more than one device is attached'), str(error))
        self.assertIn('--udid', str(error))
        self.assertIn(f'{self.IPAD}  My iPad', str(error))
        self.assertIn(f'{self.PHONE}  My iPhone', str(error))
        self.assertEqual(opened, [(self.IPAD, False), (self.PHONE, False)])   # the names only, without pairing
        self.assertEqual(self.closed, [self.IPAD, self.PHONE])

    def test_a_device_that_does_not_answer_is_listed_by_its_udid(self):
        error, _ = self.open([self.IPAD, self.PHONE], names={self.IPAD: 'My iPad'})
        self.assertIn(f'{self.PHONE}  (name not available)', str(error))
        self.assertIn(f'{self.IPAD}  My iPad', str(error))
        self.assertEqual(self.closed, [self.IPAD])   # the other one was never opened

    def test_udid_names_the_device_among_several(self):
        box, opened = self.open([self.IPAD, self.PHONE], self.PHONE)
        self.assertEqual(opened, [(self.PHONE, True)])
        self.assertIn(self.PHONE, box.name)

    def test_no_device_says_so_as_before(self):
        error, _ = self.open([])
        self.assertIn('no device', str(error))

    def test_the_off_switch_leaves_the_pick_to_pymobiledevice3(self):
        _, opened = self.open([self.IPAD, self.PHONE], first=True)
        self.assertEqual(opened, [(None, True)])

    def test_the_commands_print_the_device_before_their_work(self):
        with tempfile.TemporaryDirectory() as d:
            mod = Path(d)/'mod'; mod.mkdir()
            (mod/'a.bin').write_bytes(b'x')
            (mod/'manifest.tsv').write_text(f'a.bin\t1\t{hashlib.sha256(b"x").hexdigest()}\t-\n')
            run = subprocess.run([sys.executable, str(TOOLS/'push_device_windows.py'), 'push-mod', str(mod), '--bundle-id', 'a.b',
                                  '--simulate', str(Path(d)/'device')], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        lines = run.stdout.splitlines()
        self.assertTrue(lines[0].startswith('device: folder '), lines)
        self.assertTrue(lines[1].startswith('mod: copying'), lines)


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

    def test_the_commands_with_simulate(self):
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


if __name__ == '__main__':
    unittest.main()
