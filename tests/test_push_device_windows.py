"""games/totk/ios/tools/push_device_windows.py against a local folder standing for the app's container (app_container.py
LocalContainer, what --simulate uses): the RomFS image in parts with its marker last, a copy that stopped going on, the
shaders as one pack read back as ios/Sources/main.m seed_unpack reads it, and saves backed up and restored with their
account. No device and no game files."""
import contextlib
import hashlib
import itertools
import io
import json
import os
import plistlib
import shutil
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

    def seed(self, fingerprint):
        """A seed folder that makes a pack of several parts, each attempt at it named apart from the one before."""
        push.PART = 777
        seed = self.root/f'{fingerprint}-shader-seed'; seed.mkdir()
        (seed/'fingerprint.txt').write_text(fingerprint * 64 + '\n')
        for i in range(1, 8):
            (seed/f'{i}_b.metal').write_bytes(bytes([i]) * (300 * i))
        clock = itertools.count(1000)
        patcher = patch.object(push.time, 'time', lambda: next(clock))
        patcher.start(); self.addCleanup(patcher.stop)
        return seed

    def stop_copy(self, seed, after):
        self.box.stop = len(self.box.uploads) + after
        with self.assertRaises(OSError):
            push.push_seed(self.box, seed, log=quiet)
        self.box.stop = None

    def parts_of(self, fingerprint):
        return sorted(p.name for p in self.device().glob(f'shader-seed-{fingerprint * 12}-*.pack.*'))

    def test_a_stopped_seed_copy_leaves_the_seed_on_the_device_in_use(self):
        old, new = self.seed('a'), self.seed('b')
        push.push_seed(self.box, old, log=quiet)
        marker, kept = self.device('shader-seed.txt').read_bytes(), self.parts_of('a')
        self.stop_copy(new, 2)
        self.assertEqual(self.device('shader-seed.txt').read_bytes(), marker)   # main.m goes on reading the old seed
        self.assertEqual(self.parts_of('a'), kept)
        self.assertEqual(len(self.parts_of('b')), 2)

    def test_a_copy_after_a_stopped_one_starts_with_the_room_that_one_took(self):
        old, new = self.seed('a'), self.seed('b')
        push.push_seed(self.box, old, log=quiet)
        kept = self.parts_of('a')
        for _ in range(3):
            self.stop_copy(new, 2)
            self.assertEqual(len(self.parts_of('b')), 2)
            self.assertEqual(self.parts_of('a'), kept)
        self.box.ops.clear()
        self.assertEqual(push.push_seed(self.box, new, log=quiet), 'copied')
        kinds = [kind for kind, _ in self.box.ops]
        self.assertLess(kinds.index('remove'), kinds.index('upload'))
        self.assertEqual(self.box.ops[-1], ('write', f'{push.GAMEDATA}/shader-seed.txt'))
        self.assertEqual(kinds.count('write'), 1)   # the marker changes once, when every part is there
        folder = self.device('shader-seed.txt').read_text().split('\n')[0]
        self.assertTrue(all(n.startswith(folder + '.pack.') for n in self.parts_of('b')), self.parts_of('b'))
        self.assertEqual(read_pack(sorted(self.device().glob(folder + '.pack.*')))[1], True)
        self.assertEqual(self.parts_of('a'), kept)   # the app removes these at its next start

    def test_a_copy_clears_what_a_stale_marker_left_behind(self):
        new = self.seed('b')
        self.box.makedirs(push.GAMEDATA)
        self.box.write(f'{push.GAMEDATA}/shader-seed.txt', b'stale\n')   # an earlier copy, or install_device.py
        (self.device('shader-seed-cccccccccccc-1').mkdir())               # the seed that marker replaced, unpacked
        (self.device('shader-seed-cccccccccccc-1/seed-manifest.json')).write_text('{}')
        for name in ('shader-seed-dddddddddddd-2.pack.000', 'shader-seed-dddddddddddd-2.pack.001'):
            self.device(name).write_bytes(b'part')
        self.assertEqual(push.push_seed(self.box, new, log=quiet), 'copied')
        self.assertEqual(self.parts_of('d'), [])
        self.assertTrue(self.device('shader-seed-cccccccccccc-1/seed-manifest.json').is_file())   # the app's to remove
        self.assertNotIn('stale', self.device('shader-seed.txt').read_text())

    def test_a_part_gone_during_the_copy_keeps_the_marker(self):
        """The game started during the copy and removed what its marker does not name (main.m), so the pack is not whole."""
        old, new = self.seed('a'), self.seed('b')
        push.push_seed(self.box, old, log=quiet)
        marker = self.device('shader-seed.txt').read_bytes()
        upload = self.box.upload
        def app_starts(rel, *args, **kw):
            upload(rel, *args, **kw)
            if rel.endswith('.pack.001'):
                self.device(rel.rsplit('/', 1)[1].replace('.001', '.000')).unlink()
        self.box.upload = app_starts
        with self.assertRaisesRegex(push.PushError, r'\.pack\.000.*run this again'):
            push.push_seed(self.box, new, log=quiet)
        self.assertEqual(self.device('shader-seed.txt').read_bytes(), marker)

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
        parts = app_container.ipa_info(self.ipa(['GameData/romfs/romfs.bin.000']))
        self.assertEqual(parts['carries'], {'seed': False, 'romfs': True})
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

    def test_udid_on_the_command_line_reaches_the_container(self):
        modules = fake_usbmux([], {})[0]   # gets past main's import check, which would run it again in another interpreter
        command = ['push_device_windows.py', 'status', '--bundle-id', 'a.b', '--udid', self.PHONE]
        with patch.dict(sys.modules, modules), patch.object(sys, 'argv', command), \
                patch.object(app_container, 'DeviceContainer') as container, patch.object(push, 'status') as status, \
                contextlib.redirect_stdout(io.StringIO()):
            push.main()
        container.assert_called_once_with('a.b', self.PHONE)
        status.assert_called_once_with(container.return_value)

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


class NoContainerYet(app_container.LocalContainer):
    """Reads nothing before the app is installed, as DeviceContainer.documents raises then."""
    def read(self, rel):
        app_container.require(self.installed(), f'{self.bundle_id} is not installed on the device')
        return super().read(rel)

    def listdir(self, rel):
        app_container.require(self.installed(), f'{self.bundle_id} is not installed on the device')
        return super().listdir(rel)


class Deploy(unittest.TestCase):
    """deploy with --simulate: what stops it while the device is as it was, so it never ends with an app that cannot start."""
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(); self.addCleanup(self.dir.cleanup); self.root = Path(self.dir.name)
        self.container = self.root/'device'
        self.data = self.container/push.GAMEDATA
        self.ipa_file = self.ipa()

    def ipa(self, extra=()):
        ipa = self.root/'a.ipa'
        with zipfile.ZipFile(ipa, 'w') as z:
            z.writestr('Payload/A.app/Info.plist', plistlib.dumps({'CFBundleIdentifier': 'a.b', 'CFBundleVersion': 'new'}))
            for name in extra: z.writestr(f'Payload/A.app/{name}', b'x')
        return ipa

    def deploy(self, *args):
        return subprocess.run([sys.executable, str(TOOLS/'push_device_windows.py'), 'deploy', str(self.ipa_file), *map(str, args),
                               '--simulate', str(self.container)], capture_output=True, text=True)

    def on_device(self):
        return {p.relative_to(self.container).as_posix(): p.read_bytes() for p in self.container.rglob('*') if p.is_file()}

    def old_app(self):
        """An installed app, whose data a device shows; a run that installed over it would change this record."""
        self.data.mkdir(parents=True)
        (self.container/'.installed.json').write_text(json.dumps({'CFBundleIdentifier': 'a.b', 'CFBundleVersion': 'old'}))

    def image(self, size=10):
        """romfs.bin with its index.json, as --romfs takes them."""
        folder = self.root/'romfs'; folder.mkdir(exist_ok=True)
        (folder/'romfs.bin').write_bytes(bytes(size))
        (folder/'index.json').write_text(json.dumps({'romfs_sha256': hashlib.sha256(bytes(size)).hexdigest(), 'romfs_size': size}))
        return folder/'romfs.bin'

    def seed_folder(self, name='a-shader-seed'):
        """A device seed, by default where deploy looks for one: beside the IPA."""
        seed = self.root/name; seed.mkdir()
        (seed/'fingerprint.txt').write_text('f' * 64 + '\n')
        (seed/'a_b.metal').write_bytes(b'shader')
        return seed

    def image_on_device(self, marker='a' * 64):
        (self.data/'romfs.bin.000').write_bytes(b'part')
        if marker is not None:
            (self.data/'romfs.sha256').write_text(marker + '\n')

    def seed_on_device(self, marker=f'shader-seed-aaaaaaaaaaaa-1\n{"a" * 64}\n', kept='shader-seed-aaaaaaaaaaaa-1/seed-manifest.json'):
        """shader-seed.txt and a file of the seed it names: `kept`, in the unpacked folder or the pack the app has not unpacked."""
        (self.data/'shader-seed.txt').write_bytes(marker.encode())
        if kept:
            (self.data/kept).parent.mkdir(exist_ok=True)
            (self.data/kept).write_bytes(b'{}')

    def stops(self, *args, says):
        """The run ends with exit 1 and `says` in its error, and the device is as it was."""
        before = self.on_device()
        run = self.deploy(*args, '--no-backup')
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        for text in says:
            self.assertIn(text, run.stderr)
        self.assertNotIn('done.', run.stdout)
        self.assertEqual(self.on_device(), before, 'it changed the device first')

    def finishes(self, *args):
        """The run ends with exit 0 and the new app on the device. Returns what it printed."""
        run = self.deploy(*args, '--no-backup')
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('done.', run.stdout)
        self.assertEqual(json.loads((self.container/'.installed.json').read_text())['CFBundleVersion'], 'new')
        return run.stdout

    def test_the_folder_a_seed_is_made_from_is_not_a_device_seed(self):
        raw = self.root/'seed-f1d0077/seed'; raw.mkdir(parents=True)
        (raw/'seed-manifest.json').write_text('{}')
        self.stops('--romfs', self.image(), '--seed', raw, says=('fingerprint.txt not found', 'not the folder it is made from'))

    def test_a_seed_with_a_cut_fingerprint_stops_the_run(self):
        seed = self.seed_folder()
        (seed/'fingerprint.txt').write_text('short\n')
        self.stops('--romfs', self.image(), says=('is not a SHA-256',))              # the folder beside the IPA
        self.stops('--romfs', self.image(), '--seed', seed, says=('is not a SHA-256',))

    def test_a_bad_seed_stops_the_run_for_an_app_that_carries_its_shaders_too(self):
        self.ipa_file = self.ipa(['GameData/shader-seed/seed-manifest.json', 'GameData/romfs/romfs.bin'])
        self.stops('--seed', self.root/'none', says=('fingerprint.txt not found',))

    def test_a_romfs_that_is_not_there_stops_the_run(self):
        self.seed_folder()
        self.stops('--romfs', self.root/'none/romfs.bin', says=('index.json',))

    def test_a_romfs_of_another_size_stops_the_run(self):
        self.seed_folder()
        image = self.image()
        image.write_bytes(b'cut')
        self.stops('--romfs', image, says=('its index.json says 10',))

    def test_a_romfs_without_its_index_stops_the_run(self):
        self.seed_folder()
        image = self.image()
        (image.parent/'index.json').unlink()
        self.stops('--romfs', image, says=('index.json',))

    def test_a_whole_image_of_another_kind_on_the_device_stops_the_run(self):
        self.old_app(); self.seed_on_device()
        (self.data/'romfs.bin').write_bytes(b'another image')
        (self.data/'romfs.sha256').write_text('a' * 64 + '\n')
        self.stops('--romfs', self.image(), says=('holds a romfs.bin of another image',))

    def test_no_seed_anywhere_stops_the_run(self):
        self.stops('--romfs', self.image(), says=('a-shader-seed', 'none on the device', '--seed'))

    def test_no_image_anywhere_stops_the_run(self):
        self.seed_folder()
        self.stops(says=('no game data', 'none on the device', '--romfs'))

    def test_a_marker_that_names_no_seed_is_no_seed(self):
        folder = 'shader-seed-aaaaaaaaaaaa-1'
        self.old_app(); self.image_on_device()
        for marker, kept in (('stale\n', f'{folder}/seed-manifest.json'), (f'{folder}\n{"a" * 64}\n', None),
                             (f'{folder}\nshort\n', f'{folder}/seed-manifest.json')):
            with self.subTest(marker=marker, kept=kept):
                self.seed_on_device(marker, kept)
                self.stops(says=('none on the device',))
                shutil.rmtree(self.data/folder, ignore_errors=True)

    def test_an_image_still_being_copied_is_no_image(self):
        self.old_app(); self.seed_on_device(); self.image_on_device(f'copying {"a" * 64}')
        self.stops(says=('no game data',))

    def test_a_marker_without_the_image_is_no_image(self):
        self.old_app(); self.seed_on_device()
        (self.data/'romfs.sha256').write_text('a' * 64 + '\n')
        self.stops(says=('no game data',))

    def test_a_stopped_run_leaves_the_installed_app_and_makes_no_backup(self):
        self.old_app()
        (self.container/push.SAVE).mkdir(parents=True); (self.container/push.SAVE/'account.uid').write_bytes(bytes(16))
        before = self.on_device()
        run = self.deploy('--backup-to', self.root/'backups')
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertEqual(self.on_device(), before)
        self.assertFalse((self.root/'backups').exists())

    def test_what_the_device_has_is_enough(self):
        self.old_app(); self.image_on_device(); self.seed_on_device()
        output = self.finishes()
        self.assertIn('game data: the device has an image', output)
        self.assertIn('shaders: the device has a seed', output)

    def test_a_pack_the_app_has_not_unpacked_is_a_seed(self):
        self.old_app(); self.image_on_device(); self.seed_on_device(kept='shader-seed-aaaaaaaaaaaa-1.pack.000')
        self.finishes()

    def test_an_image_in_parts_without_a_marker_is_an_image(self):
        self.old_app(); self.image_on_device(None); self.seed_on_device()   # main.m reads it: only "copying ..." holds it back
        self.finishes()

    def test_a_whole_image_file_is_an_image(self):
        self.old_app(); self.seed_on_device()
        (self.data/'romfs.bin').write_bytes(b'whole')
        self.finishes()

    def test_a_whole_image_that_is_the_one_given_stays(self):
        image = self.image()
        self.old_app(); self.seed_on_device()
        (self.data/'romfs.bin').write_bytes(bytes(10))
        (self.data/'romfs.sha256').write_text(hashlib.sha256(bytes(10)).hexdigest() + '\n')
        self.assertIn('the device already has this image (one file)', self.finishes('--romfs', image))

    def test_what_the_app_carries_needs_nothing_else(self):
        self.ipa_file = self.ipa(['GameData/shader-seed/seed-manifest.json', 'GameData/romfs/romfs.bin'])
        self.finishes()
        self.assertEqual(sorted(self.data.glob('*')), [])

    def test_the_seed_beside_the_ipa_and_the_image_are_copied(self):
        self.seed_folder()
        self.finishes('--romfs', self.image())
        self.assertEqual((self.data/'romfs.sha256').read_text().strip(), hashlib.sha256(bytes(10)).hexdigest())
        self.assertEqual((self.data/'shader-seed.txt').read_text().split('\n')[1], 'f' * 64)

    def test_seed_names_a_device_seed_elsewhere(self):
        self.finishes('--romfs', self.image(), '--seed', self.seed_folder('elsewhere'))
        self.assertEqual((self.data/'shader-seed.txt').read_text().split('\n')[1], 'f' * 64)

    def test_a_new_seed_replaces_the_one_on_the_device(self):
        self.old_app(); self.image_on_device(); self.seed_on_device(); self.seed_folder()
        self.finishes()
        self.assertEqual((self.data/'shader-seed.txt').read_text().split('\n')[1], 'f' * 64)

    def test_a_first_install_asks_the_device_nothing_before_the_app_is_there(self):
        box = NoContainerYet(self.container, 'a.b')
        info = app_container.ipa_info(self.ipa_file)
        a = SimpleNamespace(mod=None, slot=None, romfs=None, seed=None, no_backup=True, backup_to=None, version=push.MOD_VERSION)
        with self.assertRaisesRegex(push.PushError, 'no game data'):
            push.deploy_app(box, a, self.ipa_file, info)
        a.romfs = self.image()
        with self.assertRaisesRegex(push.PushError, 'no shaders'):
            push.deploy_app(box, a, self.ipa_file, info)

    def test_the_seed_command_says_what_it_takes(self):
        self.old_app()
        (self.root/'raw').mkdir()
        run = subprocess.run([sys.executable, str(TOOLS/'push_device_windows.py'), 'seed', str(self.root/'raw'),
                              '--bundle-id', 'a.b', '--simulate', str(self.container)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertIn('fingerprint.txt not found', run.stderr)


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
        self.box.ops.clear()
        self.box.stop = len(self.box.uploads) + 1   # the cable comes out after the first file
        with self.assertRaises(OSError):
            push.push_mod(self.box, new, log=quiet)
        self.assertFalse((self.on_device/'manifest.tsv').exists())   # the app loads no half-copied mod
        self.assertEqual(next(op for op in self.box.ops if op[0] == 'remove'), ('remove', f'{push.MODS}/v143/manifest.tsv'))
        self.assertEqual((self.on_device/push.COPYING).read_bytes(), (new/'manifest.tsv').read_bytes())
        self.box.stop = None; self.box.uploads.clear()
        self.assertEqual(push.push_mod(self.box, new, log=quiet), 'copied')
        self.assertEqual(len(self.box.uploads), 2)   # the file copied before the stop is kept
        self.assertEqual(self.device_files(), {**new_files, 'manifest.tsv': (new/'manifest.tsv').read_bytes()})

    def test_a_stopped_copy_is_not_taken_up_by_another_mod(self):
        stopped = self.mod({FONT: b'old icons', LAYOUT: b'old layout'}, 'stopped')
        self.box.stop = len(self.box.uploads) + 1   # the cable comes out after the first file
        with self.assertRaises(OSError):
            push.push_mod(self.box, stopped, log=quiet)
        self.box.stop = None
        files = {FONT: b'new icons', LAYOUT: b'new layout'}   # the sizes of the stopped copy's files
        other = self.mod(files, 'other')
        self.assertEqual(push.push_mod(self.box, other, log=quiet), 'copied')
        self.assertEqual(self.device_files(), {**files, 'manifest.tsv': (other/'manifest.tsv').read_bytes()})

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

    def slots(self, version='v143'):
        """A folder holding the four slot folders, as make_gameplay_tuning.py --slots leaves them."""
        for slot in push.MOD_SLOTS:
            self.mod({FONT: f'{slot} font'.encode(), LAYOUT: f'{slot} layout'.encode()}, f'mods/{version}-{slot}')
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

    def test_push_slots_names_the_tool_that_makes_the_folders(self):
        folder = self.slots()
        (folder/'v143-max/manifest.tsv').unlink()
        with self.assertRaisesRegex(push.PushError, r'no v143-max with a manifest\.tsv.*make_gameplay_tuning\.py --slots'):
            push.push_slots(self.box, folder, log=quiet)
        for given in (self.root/'never built', folder/'v143-strong'):   # the second is a slot folder in place of their parent
            with self.assertRaisesRegex(push.PushError, r'no v143-off, .*make_gameplay_tuning\.py --slots'):
                push.push_slots(self.box, given, log=quiet)
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

    def test_push_slots_takes_its_version_from_the_command_line(self):
        import subprocess
        folder = self.slots('v121')
        pushed = subprocess.run([sys.executable, str(TOOLS/'push_device_windows.py'), 'push-slots', str(folder), '--version', 'v121',
                                 '--bundle-id', 'a.b', '--simulate', str(self.root/'device')], capture_output=True, text=True)
        self.assertEqual(pushed.returncode, 0, pushed.stderr)
        self.assertEqual(sorted(p.name for p in (self.root/'device'/push.MODS).iterdir()), sorted(f'v121-{slot}' for slot in push.MOD_SLOTS))

    def test_the_commands_with_simulate(self):
        mod = self.mod({FONT: b'font'})
        self.box.install(self.ipa())
        data = self.root/'device'/push.GAMEDATA/'shader-seed-aaaaaaaaaaaa-1'; data.mkdir(parents=True)   # deploy wants both
        (data.parent/'shader-seed.txt').write_bytes(f'{data.name}\n{"a" * 64}\n'.encode())
        (data.parent/'romfs.bin.000').write_bytes(b'part'); (data.parent/'romfs.sha256').write_text('a' * 64 + '\n')
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
        other_version = self.on_device.with_name('v121-max')
        versioned = run('push-mod', mod, '--bundle-id', 'a.b', '--version', 'v121', '--slot', 'max')
        self.assertEqual(versioned.returncode, 0, versioned.stderr)
        self.assertTrue((other_version/'manifest.tsv').is_file())
        removed = run('remove-mod', '--bundle-id', 'a.b', '--version', 'v121', '--slot', 'max')
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertFalse(other_version.exists())
        deployed = run('deploy', self.ipa(), '--no-backup', '--mod', mod, '--version', 'v121', '--slot', 'max')
        self.assertEqual(deployed.returncode, 0, deployed.stderr)
        self.assertTrue((other_version/'manifest.tsv').is_file())
        self.assertNotEqual(run('deploy', self.ipa(), '--no-backup', '--slot', 'off').returncode, 0)   # no --mod to put there
        self.assertNotEqual(run('push-mod', mod, '--bundle-id', 'a.b', '--slot', 'other').returncode, 0)


if __name__ == '__main__':
    unittest.main()
