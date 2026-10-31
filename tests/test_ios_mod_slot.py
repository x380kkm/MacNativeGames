"""The production choice of the player mod folder (ios/Sources/main.m apply_player_mods) on real folders: which folder the
runtime is handed, and the log line that says why. It uses Foundation, so it runs on macOS only."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'darwin', 'the choice uses macOS/iOS Foundation')
class IosModSlot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('clang')
        if not compiler:
            raise unittest.SkipTest('clang is required')
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        directory = Path(cls.temporary.name)
        source = (ROOT/'games/totk/ios/Sources/main.m').read_text(encoding='utf-8')
        start = source.index('static void apply_player_mods(')
        end = source.index('\n@interface TOTKApp', start)
        production = directory/'mod_slot.inc'
        production.write_text(source[start:end], encoding='utf-8')
        cls.executable = directory/'mod-slot'
        build = subprocess.run(
            [compiler, '-fobjc-arc', '-Wall', '-Wextra', '-Werror', '-framework', 'Foundation',
             '-DPRODUCTION_CHOICE="' + str(production) + '"',
             str(ROOT/'tests/ios_mod_slot_probe.m'), '-o', str(cls.executable)],
            capture_output=True, text=True, timeout=90)
        if build.returncode:
            raise AssertionError(build.stdout + build.stderr)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.mods = f'{self.directory.name}/mods/v143'
        self.app_mods = f'{self.directory.name}/TOTK.app/GameData/mods/v143'

    def folder(self, suffix='', name='manifest.tsv', root=None):
        """The folder Documents/mods/v143<suffix>, or root<suffix>, holding a file `name`; a manifest by default."""
        path = Path((root or self.mods) + suffix)
        path.mkdir(parents=True)
        (path/name).write_text('# path\tsize\tsha256\toriginal_sha256\n', encoding='utf-8')

    def choice(self, slot=None, launch=None):
        """(the value the runtime is handed, the log line) of a start with TOTK_MOD_SLOT `slot` and TOTK_ROMFS_MODS `launch`."""
        env = {k: v for k, v in os.environ.items() if k not in ('TOTK_MOD_SLOT', 'TOTK_ROMFS_MODS')}
        env.update({k: v for k, v in (('TOTK_MOD_SLOT', slot), ('TOTK_ROMFS_MODS', launch)) if v is not None})
        run = subprocess.run([str(self.executable), self.mods, self.app_mods], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        return run.stdout.strip(), run.stderr.strip()

    def loads(self, folder, why):
        return folder, f'[totk] player mods: {folder} ({why})'

    def loads_none(self, why):
        return '(not set)', f'[totk] player mods: none ({why})'

    def test_the_app_s_slot_is_used_when_the_device_has_no_mod(self):
        self.folder('-strong', root=self.app_mods)
        why = f"no {self.mods}-strong/manifest.tsv for mod slot strong, no {self.mods}/manifest.tsv, the app's mod slot strong"
        self.assertEqual(self.choice('strong'), self.loads(self.app_mods + '-strong', why))

    def test_a_folder_on_the_device_wins_over_the_app_s(self):
        self.folder('-strong', root=self.app_mods)
        self.folder('-strong')
        self.assertEqual(self.choice('strong'), self.loads(self.mods + '-strong', 'mod slot strong'))

    def test_the_plain_folder_on_the_device_wins_over_the_app_s(self):
        self.folder('-strong', root=self.app_mods)
        self.folder()
        self.assertEqual(self.choice('strong'), self.loads(self.mods, f'no {self.mods}-strong/manifest.tsv for mod slot strong'))

    def test_the_app_s_folder_of_another_slot_is_not_taken(self):
        self.folder('-max', root=self.app_mods)
        why = f'no {self.mods}-strong/manifest.tsv for mod slot strong, no {self.mods}/manifest.tsv'
        self.assertEqual(self.choice('strong'), self.loads_none(why))

    def test_without_a_slot_the_app_s_folders_stay_out(self):
        self.folder('-strong', root=self.app_mods)
        self.assertEqual(self.choice(), self.loads_none(f'no mod slot, no {self.mods}/manifest.tsv'))

    def test_the_chosen_slot_wins_over_the_plain_folder(self):
        self.folder(); self.folder('-strong')
        self.assertEqual(self.choice('strong'), self.loads(self.mods + '-strong', 'mod slot strong'))

    def test_a_half_copied_slot_is_passed_over(self):
        self.folder(); self.folder('-strong', 'manifest.tsv.copying')
        why = f'no {self.mods}-strong/manifest.tsv for mod slot strong'
        self.assertEqual(self.choice('strong'), self.loads(self.mods, why))

    def test_the_plain_folder_stands_in_for_a_missing_slot(self):
        self.folder(); self.folder('-max')
        why = f'no {self.mods}-strong/manifest.tsv for mod slot strong'
        self.assertEqual(self.choice('strong'), self.loads(self.mods, why))

    def test_no_slot_and_no_folder_loads_none(self):
        why = f'no {self.mods}-strong/manifest.tsv for mod slot strong, no {self.mods}/manifest.tsv'
        self.assertEqual(self.choice('strong'), self.loads_none(why))

    def test_without_a_slot_the_plain_folder_loads(self):
        self.folder()
        for slot in (None, ''):
            with self.subTest(slot=slot):
                self.assertEqual(self.choice(slot), self.loads(self.mods, 'no mod slot'))

    def test_without_a_slot_or_a_folder_none_loads(self):
        self.assertEqual(self.choice(), self.loads_none(f'no mod slot, no {self.mods}/manifest.tsv'))

    def test_a_launch_value_wins(self):
        self.folder(); self.folder('-strong')
        self.assertEqual(self.choice('strong', '/elsewhere'), self.loads('/elsewhere', 'TOTK_ROMFS_MODS from the launch'))

    def test_a_launch_value_can_load_none(self):
        self.folder(); self.folder('-strong')
        for launch in ('0', ''):
            with self.subTest(launch=launch):
                self.assertEqual(self.choice('strong', launch),
                                 (launch, '[totk] player mods: none (TOTK_ROMFS_MODS from the launch)'))

    def test_a_slot_is_lower_case_letters(self):
        self.folder()
        for slot in ('Strong', 'strong2', '../v143-strong', 'a/b'):
            with self.subTest(slot=slot):
                self.folder('-' + slot)
                self.assertEqual(self.choice(slot), self.loads(self.mods, 'no mod slot'))

    def test_a_slot_is_at_most_15_letters(self):
        self.folder(); self.folder('-' + 'a' * 15); self.folder('-' + 'a' * 16)
        self.assertEqual(self.choice('a' * 15), self.loads(f'{self.mods}-{"a" * 15}', f'mod slot {"a" * 15}'))
        self.assertEqual(self.choice('a' * 16), self.loads(self.mods, 'no mod slot'))


if __name__ == '__main__':
    unittest.main()
