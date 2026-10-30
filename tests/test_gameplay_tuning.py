"""games/totk/scripts/make_gameplay_tuning.py on a small fake RomFS made here (no game data): the fields it edits, what it
writes and refuses, values that never compound, the manifest, the four slot folders, and a damaged RomFS."""
import hashlib
import importlib.util
import json
import plistlib
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HAS_ZSTD = importlib.util.find_spec('compression.zstd') is not None   # Python 3.14
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'games/totk/scripts/make_gameplay_tuning.py'
sys.path.insert(0, str(ROOT/'games/totk/scripts'))
sys.path.insert(0, str(ROOT/'games/totk/ios/tools'))
sys.path.insert(0, str(ROOT/'tests'))

LIFE = 'Life/LifeParameters/Weapon_Sword_001.game__life__LifeParameters.bgyml'
SHIELD_LIFE = 'Life/LifeParameters/Weapon_Shield_001.game__life__LifeParameters.bgyml'
ENEMY_LIFE = 'Life/LifeParameters/Enemy_Bokoblin.game__life__LifeParameters.bgyml'
EQUIPMENT = 'Life/DamageParameters/EquipmentCommon.game__life__DamageParameters.bgyml'
SHIELD = 'Life/DamageParameters/ShieldCommon.game__life__DamageParameters.bgyml'
CONDITION = 'Component/ConditionParam/Player.game__component__ConditionParam.bgyml'
SWORD, EVENT_SWORD, TORCH = ('Pack/Actor/Weapon_Sword_001.pack.zs', 'Pack/Actor/Weapon_Sword_001_Event.pack.zs',
                             'Pack/Actor/Npc_Torch.pack.zs')
BUCKLER, ENEMY, PLAYER = 'Pack/Actor/Weapon_Shield_001.pack.zs', 'Pack/Actor/Enemy_Bokoblin.pack.zs', 'Pack/Actor/Player.pack.zs'
BOOTUP, TABLE = 'Pack/Bootup.Nin_NX_NVN.pack.zs', 'RSDB/GameActorInfo.Product.143.rstbl.byml.zs'
WEAPONS = (SWORD, EVENT_SWORD, TORCH, BUCKLER)


def f32(value):
    """`value` as the float32 the game reads."""
    return struct.unpack('<f', struct.pack('<f', value))[0]


@unittest.skipUnless(HAS_ZSTD, 'needs Python 3.14 (compression.zstd)')
class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import compression.zstd as zstd
        import romfs_formats
        from romfs_fixtures import byml, zstd_dictionary
        from test_mod_manifest import fake_romfs, sarc
        cls.formats, cls.sarc = romfs_formats, staticmethod(sarc)
        cls.top = tempfile.TemporaryDirectory()
        dictionaries = {1: zstd.ZstdDict(zstd_dictionary(1)), 3: zstd.ZstdDict(zstd_dictionary(3))}
        cls.dictionaries = dictionaries

        def life(value):
            return byml({'MaxLife': value, 'MaxLifeAlternateSettings': {}, 'UseBreakLife': False})
        damage = byml({'ExternalDamageParameters': {'DamageRates': {'Arrow': 1.0, 'Durability': 1.0, 'Water': 0.5}},
                       'InternalDamageParameters': {'Sum': 10}})
        condition = byml({'ChargeSpeedRate': [1.0, 2.0], 'ZonauEnergy_CostRate': [1.0, 0.8, 0.65, 0.5],
                          'ZonauEnergy_HealRate': [1.0, 1.5]})
        packs = {SWORD: {LIFE: life(20), EQUIPMENT: damage, 'Actor/Sword.bgyml': b'sword ' * 40},
                 EVENT_SWORD: {LIFE: life(20), EQUIPMENT: damage},
                 TORCH: {LIFE: life(20), EQUIPMENT: damage, 'Actor/Npc.bgyml': b'npc ' * 40},
                 BUCKLER: {SHIELD_LIFE: life(12), SHIELD: damage},
                 ENEMY: {ENEMY_LIFE: life(100)},
                 PLAYER: {CONDITION: condition, 'Actor/Player.bgyml': b'player ' * 40},
                 BOOTUP: {'Other/Thing.bgyml': byml({'MaxLife': 5})}}
        rows = [{'__RowId': 'Weapon_Sword_001', 'MaxLife': 20, 'Category': 'Sword'},
                {'__RowId': 'Weapon_Sword_001_Event', 'MaxLife': 20, 'Category': 'Sword'},
                {'__RowId': 'Npc_Torch', 'MaxLife': 20, 'Category': 'Npc'},
                {'__RowId': 'Weapon_Shield_001', 'MaxLife': 12, 'Category': 'Shield'},
                {'__RowId': 'Enemy_Bokoblin', 'MaxLife': 100, 'Category': 'Enemy'},
                {'__RowId': 'Weapon_Sword_002', 'Category': 'Sword'}]
        files = {path: zstd.compress(sarc(members), level=3, zstd_dict=dictionaries[3]) for path, members in packs.items()}
        files[TABLE] = zstd.compress(byml(rows), level=3, zstd_dict=dictionaries[1])
        files['Pack/ZsDic.pack.zs'] = zstd.compress(sarc({'zs.zsdic': zstd_dictionary(1), 'pack.zsdic': zstd_dictionary(3)}))
        files['Sound/Other.bwav'] = b'not a pack'
        cls.romfs = fake_romfs(Path(cls.top.name)/'romfs', files)
        cls.files = files

    @classmethod
    def tearDownClass(cls):
        cls.top.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.mod = self.root/'mod'

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), '--romfs', str(self.romfs), *map(str, args)],
                              capture_output=True, text=True)

    def tune(self, *args, mod=None):
        result = self.run_tool('--into', mod or self.mod, *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def unpacked(self, path, folder=None):
        raw = (folder or self.mod).joinpath(path).read_bytes() if folder is not False else self.files[path]
        return self.formats.decompress(raw, self.dictionaries)

    def member(self, path, name, folder=None):
        data = self.unpacked(path, folder)
        return data[slice(*self.formats.sarc_members(data)[name])]

    def life(self, path, name=LIFE, folder=None):
        doc = self.formats.Byml(self.member(path, name, folder))
        return struct.unpack_from('<i', doc.data, doc.field(doc.root, 'MaxLife', doc.INT))[0]

    def rates(self, key, folder=None):
        doc = self.formats.Byml(self.member(PLAYER, CONDITION, folder))
        return [struct.unpack_from('<f', doc.data, at)[0] for _, at in doc.items(doc.child(doc.root, key, doc.ARRAY))]

    def damage_rate(self, path, name, key, folder=None):
        doc = self.formats.Byml(self.member(path, name, folder))
        rates = doc.child(doc.child(doc.root, 'ExternalDamageParameters'), 'DamageRates')
        return struct.unpack_from('<f', doc.data, doc.field(rates, key, doc.FLOAT))[0]

    def rows(self, folder=None):
        doc = self.formats.Byml(self.unpacked(TABLE, folder))
        out = {}
        for _, field in doc.items(doc.root):
            row = doc.entries(struct.unpack_from('<I', doc.data, field)[0])
            life = struct.unpack_from('<i', doc.data, row['MaxLife'][1])[0] if 'MaxLife' in row else None
            out[doc.string(row['__RowId'][1])] = (life, doc.string(row['Category'][1]))
        return out

    def written(self, folder=None):
        folder = folder or self.mod
        return sorted(p.relative_to(folder).as_posix() for p in folder.rglob('*.zs'))

    def manifest(self, folder=None):
        lines = (folder or self.mod).joinpath('manifest.tsv').read_text(encoding='utf-8').splitlines()
        return {line.split('\t')[0]: line.split('\t') for line in lines if not line.startswith('#')}


class Edits(Fixture):
    def test_every_copy_of_a_member_changes_and_nothing_else(self):
        self.tune('--durability', 5, '--battery-drain', 4, '--battery-recharge', 3)
        self.assertEqual(self.written(), sorted([*WEAPONS, PLAYER, TABLE]))   # the enemy and Bootup packs are not edited
        for path in (SWORD, EVENT_SWORD, TORCH):
            self.assertEqual(self.life(path), 100)
        self.assertEqual(self.life(BUCKLER, SHIELD_LIFE), 60)
        self.assertEqual(self.rates('ZonauEnergy_CostRate'), [f32(v / 4) for v in (1.0, f32(0.8), f32(0.65), 0.5)])
        self.assertEqual(self.rates('ZonauEnergy_HealRate'), [3.0, 4.5])
        self.assertEqual(self.rates('ChargeSpeedRate'), [1.0, 2.0])
        self.assertEqual(self.rows(), {'Weapon_Sword_001': (100, 'Sword'), 'Weapon_Sword_001_Event': (100, 'Sword'),
                                       'Npc_Torch': (100, 'Npc'), 'Weapon_Shield_001': (60, 'Shield'),
                                       'Enemy_Bokoblin': (100, 'Enemy'), 'Weapon_Sword_002': (None, 'Sword')})

    def test_only_the_values_differ_from_the_original(self):
        self.tune('--durability', 5, '--battery-drain', 4, '--battery-recharge', 3)
        for path in (*WEAPONS, PLAYER, TABLE):
            before, after = self.unpacked(path, False), self.unpacked(path)
            self.assertEqual(len(before), len(after), path)
            changed = {i & ~3 for i in range(len(before)) if before[i] != after[i]}
            self.assertEqual(len(changed), {PLAYER: 6, TABLE: 4}.get(path, 1), path)   # fields of 4 bytes, each aligned to 4
            if path != TABLE:
                start = struct.unpack_from('<I', before, 12)[0]
                self.assertEqual(before[:start], after[:start], path)                      # the member table
                self.assertEqual(self.formats.sarc_members(before), self.formats.sarc_members(after))

    def test_frames_keep_the_dictionary_and_declare_the_size(self):
        self.tune('--durability', 2)
        for path, dictionary in ((SWORD, 3), (TABLE, 1)):
            header = self.formats.frame_header((self.mod/path).read_bytes())
            original = self.formats.frame_header(self.files[path])
            self.assertEqual(header.dictionary_id, dictionary)
            self.assertEqual(header.content_size, original.content_size)
            self.assertEqual(header.checksum, original.checksum)

    def test_only_files_that_differ_are_written(self):
        self.tune('--battery-recharge', 2)
        self.assertEqual(self.written(), [PLAYER])

    def test_the_limits_of_a_durability(self):
        import make_gameplay_tuning as tool
        self.assertEqual(tool.tuned('durability', 800, tool.Tuning(durability=100)), 80000)
        self.assertEqual(tool.tuned('durability', 1500, tool.Tuning(durability=100)), tool.MAX_DURABILITY)
        self.assertEqual(tool.tuned('durability', 4, tool.Tuning(durability=0.1)), 1)      # never 0: the item would break
        self.assertEqual(tool.tuned('durability', 25, tool.Tuning(durability=1.5)), 38)    # a whole number
        self.assertEqual(tool.tuned('durability', 0, tool.Tuning(durability=5)), 0)
        self.assertEqual(tool.tuned('durability', 0, tool.Tuning()), 0)

    def test_the_summary_says_what_changed(self):
        out = self.tune('--durability', 5, '--battery-drain', 4)
        self.assertIn('maximum durability x5: 8 of 8 values changed (packs: 4, table rows: 4), 12..20 -> 60..100', out)
        self.assertIn('battery drain /4: 4 of 4 values changed (packs: 1, table rows: 0)', out)
        self.assertIn('battery recharge x1: 0 of 2 values changed', out)
        self.assertIn('6 files written', out)

    def test_it_runs_with_python_dash_i(self):
        # -I leaves the script's own folder off the path, where its two modules are
        result = subprocess.run([sys.executable, '-I', str(SCRIPT), '--romfs', str(self.romfs), '--into', str(self.mod),
                                 '--durability', '2'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.life(SWORD), 40)

    def test_values_out_of_range_are_refused(self):
        for args in (('--durability', 0), ('--durability', 101), ('--battery-drain', 0), ('--battery-recharge', 'x'), ()):
            with self.subTest(args=args):
                result = self.run_tool('--into', self.mod, *args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(self.mod.exists())


class Manifest(Fixture):
    def test_the_whole_folder_is_listed(self):
        extra = self.mod/'Sound/Extra.bwav'; extra.parent.mkdir(parents=True); extra.write_bytes(b'another mod\'s file')
        self.tune('--durability', 5)
        manifest = self.manifest()
        self.assertEqual(sorted(manifest), sorted([*WEAPONS, TABLE, 'Sound/Extra.bwav']))
        for path in (*WEAPONS, TABLE):
            data = (self.mod/path).read_bytes()
            self.assertEqual(manifest[path][1:], [str(len(data)), hashlib.sha256(data).hexdigest(),
                                                  hashlib.sha256(self.files[path]).hexdigest()])
        self.assertEqual(manifest['Sound/Extra.bwav'][3], '-')
        self.assertTrue(extra.is_file())
        check = subprocess.run([sys.executable, str(ROOT/'games/totk/scripts/make_mod_manifest.py'), self.mod,
                                '--romfs', self.romfs, '--check'], capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn('the manifest would hold 6 files', check.stdout)

    def test_the_record_stays_out_of_the_manifest(self):
        self.tune('--durability', 5, '--battery-drain', 3)
        record = json.loads((self.mod/'.gameplay-tuning.json').read_text(encoding='utf-8'))
        self.assertEqual((record['durability'], record['battery_drain'], record['battery_recharge']), (5, 3, 1))
        self.assertNotIn('.gameplay-tuning.json', self.manifest())

    def test_the_manifest_ends_with_lf(self):
        self.tune('--durability', 2)
        self.assertNotIn(b'\r', (self.mod/'manifest.tsv').read_bytes())


class Runs(Fixture):
    """Each run starts from the RomFS, so a folder only ever holds one run's values."""
    def test_values_do_not_compound(self):
        self.tune('--durability', 5)
        first = (self.mod/SWORD).read_bytes()
        again = self.tune('--durability', 5)
        self.assertIn('0 files written', again)
        self.assertIn('5 already right', again)
        self.assertEqual((self.mod/SWORD).read_bytes(), first)
        self.tune('--durability', 2)
        self.assertEqual(self.life(SWORD), 40)
        self.assertEqual(self.rows()['Weapon_Sword_001'][0], 40)

    def test_a_value_back_at_the_original_removes_the_file(self):
        self.tune('--durability', 5, '--battery-drain', 3)
        out = self.tune('--durability', 1, '--battery-drain', 3)
        self.assertEqual(self.written(), [PLAYER])
        self.assertIn('5 removed', out)
        self.assertEqual(sorted(self.manifest()), [PLAYER])


class Refusals(Fixture):
    def changed_pack(self, member, blob):
        """The sword pack with `member` changed, compressed the way a mod would."""
        import compression.zstd as zstd
        data = self.unpacked(SWORD, False)
        members = {name: data[lo:hi] for name, (lo, hi) in self.formats.sarc_members(data).items()}
        return zstd.compress(self.sarc({**members, member: blob}), level=3, zstd_dict=self.dictionaries[3])

    def put(self, raw):
        (self.mod/SWORD).parent.mkdir(parents=True, exist_ok=True)
        (self.mod/SWORD).write_bytes(raw)

    def test_another_mods_file_stops_the_run_before_it_writes(self):
        cases = {'another member': self.changed_pack('Actor/Sword.bgyml', b'SWORD ' * 40),
                 'a longer file': self.changed_pack('Actor/Sword.bgyml', b'a longer sword ' * 40),
                 'not zstd': b'not a pack at all',
                 'unknown dictionary': self.compress_with_other_dictionary()}
        for name, raw in cases.items():
            with self.subTest(name):
                shutil.rmtree(self.mod, ignore_errors=True)
                self.put(raw)
                result = self.run_tool('--into', self.mod, '--durability', 5, '--battery-drain', 2)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('--replace', result.stderr)
                self.assertIn('Weapon_Sword_001.pack.zs', result.stderr)
                self.assertEqual((self.mod/SWORD).read_bytes(), raw)
                self.assertEqual(self.written(), [SWORD])
                self.assertFalse((self.mod/'manifest.tsv').exists())

    def compress_with_other_dictionary(self):
        import compression.zstd as zstd
        from romfs_fixtures import zstd_dictionary
        return zstd.compress(self.unpacked(SWORD, False), zstd_dict=zstd.ZstdDict(zstd_dictionary(9)))

    def test_replace_overwrites_it_from_the_original(self):
        self.put(self.changed_pack('Actor/Sword.bgyml', b'SWORD ' * 40))
        self.tune('--durability', 5, '--replace')
        self.assertEqual(self.life(SWORD), 100)
        self.assertEqual(self.member(SWORD, 'Actor/Sword.bgyml'), b'sword ' * 40)

    def test_a_tuning_that_needs_no_such_file_leaves_it(self):
        raw = self.changed_pack('Actor/Sword.bgyml', b'SWORD ' * 40)
        self.put(raw)
        self.tune('--battery-drain', 2)
        self.assertEqual((self.mod/SWORD).read_bytes(), raw)
        self.assertEqual(sorted(self.manifest()), sorted([SWORD, PLAYER]))

    def test_a_file_differing_in_its_values_only_counts_as_this_tools(self):
        data = bytearray(self.unpacked(SWORD, False))
        doc = self.formats.Byml(self.member(SWORD, LIFE, False))
        lo = self.formats.sarc_members(data)[LIFE][0]
        struct.pack_into('<i', data, lo + doc.field(doc.root, 'MaxLife', doc.INT), 777)
        self.put(self.formats.compress_like(bytes(data), self.files[SWORD], self.dictionaries))
        self.tune('--durability', 2)
        self.assertEqual(self.life(SWORD), 40)


class Slots(Fixture):
    def base(self):
        """A button icon mod: a replaced font, its merge's kept copy and a manifest."""
        base = self.root/'icons'
        (base/'Font').mkdir(parents=True)
        (base/'Font/Font.bfarc.zs').write_bytes(b'redrawn font')
        (base/'Font/Font.bfarc.zs.mod-original').write_bytes(b'kept copy')
        (base/'manifest.tsv').write_text('# path\tsize\tsha256\toriginal_sha256\n', encoding='utf-8', newline='\n')
        return base

    def build(self):
        result = self.run_tool('--slots', self.root/'mods', '--base', self.base() if not (self.root/'icons').exists() else self.root/'icons')
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.root/'mods'

    def test_the_four_folders(self):
        import make_gameplay_tuning as tool
        mods = self.build()
        self.assertEqual(sorted(p.name for p in mods.iterdir()), sorted(f'v143-{slot}' for slot in tool.SLOTS))
        for slot, tuning in tool.SLOTS.items():
            with self.subTest(slot):
                folder = mods/f'v143-{slot}'
                manifest = self.manifest(folder)
                self.assertEqual(manifest['Font/Font.bfarc.zs'][3], '-')
                self.assertEqual((folder/'Font/Font.bfarc.zs').read_bytes(), b'redrawn font')
                self.assertEqual(json.loads((folder/'.gameplay-tuning.json').read_text(encoding='utf-8'))['slot'], slot)
                if slot == 'off':
                    self.assertEqual(sorted(manifest), ['Font/Font.bfarc.zs'])
                    continue
                self.assertEqual(sorted(manifest), sorted(['Font/Font.bfarc.zs', *WEAPONS, PLAYER, TABLE]))
                self.assertEqual(self.life(SWORD, folder=folder), 20 * tuning.durability)
                self.assertEqual(self.rows(folder)['Weapon_Shield_001'][0], 12 * tuning.durability)
                self.assertEqual(self.rates('ZonauEnergy_CostRate', folder)[3], f32(0.5 / tuning.drain))
                self.assertEqual(self.rates('ZonauEnergy_HealRate', folder)[1], 1.5 * tuning.recharge)
                # Normal wear never reads this rate, so no slot edits it.
                self.assertEqual(self.damage_rate(SWORD, EQUIPMENT, 'Durability', folder), 1.0)
                self.assertEqual(self.damage_rate(BUCKLER, SHIELD, 'Durability', folder), 1.0)

    def test_the_base_folder_stays_as_it_was(self):
        self.build()
        self.assertEqual(sorted(p.relative_to(self.root/'icons').as_posix() for p in (self.root/'icons').rglob('*') if p.is_file()),
                         ['Font/Font.bfarc.zs', 'Font/Font.bfarc.zs.mod-original', 'manifest.tsv'])

    def test_a_second_run_takes_the_place_of_the_first(self):
        mods = self.build()
        (mods/'v143-strong/stale.bin').write_bytes(b'left from before')
        self.build()
        self.assertFalse((mods/'v143-strong/stale.bin').exists())
        self.assertEqual(sorted(p.name for p in mods.iterdir() if p.name.startswith('.')), [])

    def test_a_folder_this_tool_did_not_make_stops_the_run(self):
        mods = self.root/'mods'; (mods/'v143-strong').mkdir(parents=True)
        (mods/'v143-strong/mine.bin').write_bytes(b'the player\'s')
        result = self.run_tool('--slots', mods, '--base', self.base())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('v143-strong', result.stderr)
        self.assertEqual(sorted(p.name for p in mods.iterdir()), ['v143-strong'])
        self.assertEqual((mods/'v143-strong/mine.bin').read_bytes(), b'the player\'s')

    def test_a_base_holding_another_mods_pack_stops_the_run(self):
        base = self.base()
        (base/SWORD).parent.mkdir(parents=True); (base/SWORD).write_bytes(b'another mod\'s pack')
        result = self.run_tool('--slots', self.root/'mods', '--base', base)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Weapon_Sword_001.pack.zs', result.stderr)
        self.assertIn(f'take it out of {base}', result.stderr)
        self.assertNotIn('--replace', result.stderr)   # --slots refuses that option
        self.assertFalse((self.root/'mods').exists() and any((self.root/'mods').iterdir()))

    def test_the_options_of_the_two_modes_do_not_mix(self):
        base = self.base()
        for args in (('--slots', self.root/'mods'), ('--slots', self.root/'mods', '--base', base, '--durability', 5),
                     ('--slots', self.root/'mods', '--base', base, '--replace'), ('--into', self.mod, '--base', base, '--durability', 2)):
            with self.subTest(args=args):
                self.assertEqual(self.run_tool(*args).returncode, 2)

    def test_the_slots_are_the_panes_and_the_push_tools(self):
        import make_gameplay_tuning as tool
        import push_device_windows as push
        import settings_strings
        pane = plistlib.loads((ROOT/'games/totk/ios/Settings.bundle/Root.plist').read_bytes())
        row = next(item for item in pane['PreferenceSpecifiers'] if item.get('Key') == 'TOTK_MOD_SLOT')
        self.assertEqual(list(tool.SLOTS), row['Values'])
        self.assertEqual(tuple(tool.SLOTS), push.MOD_SLOTS)
        french = json.loads((ROOT/'games/totk/ios/tools/settings_fr.json').read_text(encoding='utf-8'))
        shown = settings_strings.tables(pane, french)
        for slot, title in zip(row['Values'], row['Titles']):
            durability, drain, recharge = tool.SLOTS[slot]
            if slot != 'off':   # the numbers the pane shows in each language are the table's
                self.assertIn(f'durability ×{durability}, drain ÷{drain}, recharge ×{recharge}', shown['en'][title])
                self.assertIn(f'耐久 ×{durability}，耗电 ÷{drain}，回充 ×{recharge}', shown['zh-Hans'][title])
                self.assertIn(f'durabilité ×{durability}, consommation ÷{drain}, recharge ×{recharge}', shown['fr'][title])


class DamagedRomfs(Fixture):
    """A damaged RomFS ends the run with one line that says what is wrong, and the mod folder is not made."""
    def assert_stops(self, romfs, *expected):
        result = subprocess.run([sys.executable, str(SCRIPT), '--romfs', str(romfs), '--into', str(self.mod), '--durability', '5'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)
        for text in expected:
            self.assertIn(text, result.stderr)
        self.assertFalse(self.mod.exists())

    def romfs_copy(self):
        copy = self.root/'romfs'
        shutil.copytree(self.romfs, copy)
        return copy

    def test_a_cut_image_says_which_file_and_how_many_bytes(self):
        romfs = self.romfs_copy()
        image = (romfs/'romfs.bin').read_bytes()
        (romfs/'romfs.bin').write_bytes(image[:len(image) // 2])
        self.assert_stops(romfs, 'romfs.bin', 'bytes at offset', 'damaged or incomplete')

    def test_an_index_too_short_to_hold_its_header(self):
        romfs = self.romfs_copy()
        (romfs/'runtime-index.bin').write_bytes(b'TOTKRFS1')
        self.assert_stops(romfs, 'runtime-index.bin', 'not a RomFS index')

    def test_an_image_of_zeros_stops_at_the_dictionary_pack(self):
        romfs = self.romfs_copy()
        (romfs/'romfs.bin').write_bytes(bytes((romfs/'romfs.bin').stat().st_size))
        self.assert_stops(romfs, 'Pack/ZsDic.pack.zs', 'not a readable zstd frame')

    def test_a_member_too_short_to_read_names_its_pack(self):
        import compression.zstd as zstd
        from test_mod_manifest import fake_romfs
        cut = zstd.compress(self.sarc({CONDITION: b'YB\x07\0'}), level=3, zstd_dict=self.dictionaries[3])
        self.assert_stops(fake_romfs(self.root/'romfs', {**self.files, PLAYER: cut}), PLAYER)


if __name__ == '__main__':
    unittest.main()
