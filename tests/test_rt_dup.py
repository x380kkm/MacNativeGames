"""One image at two colour slots (docs/how-it-works.md) with production code from nvn_mtl.m and nvn_obj.h: which slot is
stored, what a draw marks and where clears go, in tests/rt_dup_probe.c, for each combination of platform, game and
TOTK_RT_DUP. The places that use these rules are Objective-C, so source checks keep the draw, both store paths, the
mid-pass clear and the tile read asking them."""
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

    def test_every_draw_marks_the_slots_it_wrote_through(self):
        note = production(r'static void udc_note_draw\(NvProg \*pr\) \{.*?\n}\n')
        self.assertIn('sd_att *t = &g_sd[i];\n        rt_dup_note_draw(t, S.chmask.mask, shader_color_mask);', note)
        self.assertIn('udc_note_draw(pr);', production(r'static void draw_inner\(const p_draw \*dw, const p_draw_idx \*di\) \{.*?\n}\n'))

    def test_a_mid_pass_clear_reaches_the_other_tile_copies(self):
        clear = production(r'static void clear_quad\(const p_clear_color \*c\) \{.*?\n}\n')
        self.assertIn('unsigned others = rt_dup_other_slots(&R.rt, c->index);\n'
                      '    for (int i = 0; i < 8; i++) if ((others >> i & 1) && g_pass.cfmt[i])\n'
                      '        clear_quad_core(en, g_pass.cfmt, g_pass.hd ? g_pass.dfmt : 0, g_pass.hs ? g_pass.sfmt : 0, '
                      'g_pass.samples, tw, th, i, c->mask, c->rgba, sc);', clear)

    def test_a_draw_does_not_read_one_of_two_tile_copies(self):
        self.assertIn('if (rt_dup_other_slots(&R.rt, j)) return nil;',
                      production(r'static id<MTLFunction> att_fb_take\(.*?\n}\n'))


if __name__ == '__main__':
    unittest.main()
