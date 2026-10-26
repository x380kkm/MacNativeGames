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
    def __init__(self, *a):
        super().__init__(*a); self.uploads = []

    def upload(self, rel, *args, **kw):
        self.uploads.append(rel); super().upload(rel, *args, **kw)


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


if __name__ == '__main__':
    unittest.main()
