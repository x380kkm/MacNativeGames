"""One image at two colour slots (docs/how-it-works.md) with production code from nvn_mtl.m and nvn_obj.h: which slot is
stored and where clears go, in tests/rt_dup_probe.c, for each combination of platform, game and TOTK_RT_DUP. The store
itself is Objective-C, so a source check keeps both store paths asking the rule."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
NVN = ROOT / 'games/totk/third_party/d2r_gfx/gfx/nvn'


def production(pattern):
    return re.search(pattern, (NVN / 'nvn_mtl.m').read_text(encoding='utf-8'), re.S).group()


class OneImageAtTwoSlots(unittest.TestCase):
    def probe(self, *defines):
        compiler = shutil.which('cc')
        if not compiler:
            self.skipTest('A C compiler is required')
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory)
        code = '\n'.join(production(pattern) for pattern in (
            r'typedef struct \{ uint64_t ser, bytes; uint32_t lv, sl; int idx;.*?sd_att;',
            r'static sd_att g_sd\[9\]; static int g_nsd;',
            r'static int rt_dup_on\(void\) \{.*?static int rt_dup_unstored\(const sd_att \*t\) \{.*?\n}\n'))
        fixture = (ROOT / 'tests/rt_dup_probe.c').read_text(encoding='utf-8')
        source = directory / 'probe.c'
        source.write_text(fixture.replace('/* PRODUCTION_CODE */', code), encoding='utf-8')
        executable = directory / 'probe'
        build = subprocess.run(
            [compiler, '-std=gnu11', '-O1', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', *defines,
             '-I' + str(NVN), '-I' + str(NVN / 'include'), str(source), '-o', str(executable)],
            capture_output=True, text=True)
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        return executable

    def expect(self, executable, state, **variables):
        environment = {k: v for k, v in os.environ.items() if k != 'TOTK_RT_DUP'} | variables
        run = subprocess.run([str(executable), state], capture_output=True, text=True, env=environment)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('rt dup ok', run.stdout)

    def test_on_by_default_on_ios_and_off_with_its_switch(self):
        executable = self.probe('-DIOS_BUILD=1')
        self.expect(executable, 'on')
        self.expect(executable, 'off', TOTK_RT_DUP='0')

    def test_off_by_default_on_the_mac_and_on_with_its_switch(self):
        executable = self.probe('-DIOS_BUILD=0')
        self.expect(executable, 'off')
        self.expect(executable, 'on', TOTK_RT_DUP='1')

    def test_off_in_a_breath_of_the_wild_build(self):
        self.expect(self.probe('-DIOS_BUILD=1', '-DGAME_BOTW=1'), 'off')

    def test_both_store_paths_ask_the_rule(self):
        finish = production(r'static void sd_finish\(void\) \{.*?\n}\n')
        self.assertIn('enc_r_store(g_enc, t->depth, rt_dup_unstored(t) ? MTLStoreActionDontCare : MTLStoreActionStore, (NSUInteger)t->idx);', finish)
        self.assertIn('int dead = t->state == 2 || udc_dead || xvdead || rt_dup_unstored(t);', finish)


if __name__ == '__main__':
    unittest.main()
