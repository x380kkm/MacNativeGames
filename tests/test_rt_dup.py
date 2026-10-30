"""One image at two colour slots (docs/how-it-works.md) with production code from nvn_mtl.m and nvn_obj.h: which slot is
stored, what a draw marks and where clears go, in tests/rt_dup_probe.c, for each combination of platform, game and
TOTK_RT_DUP. The places that use these rules are Objective-C, so source checks keep the draw, both store paths, the
clears and the tile read asking them. On macOS tests/refl_colors_probe.m runs the reflection reader the draw's mark uses."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
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
        self.expect(self.probe('-DIOS_BUILD=0', '-DGAME_BOTW=1'), 'off')

    def test_both_store_paths_ask_the_rule(self):
        finish = production(r'static void sd_finish\(void\) \{.*?\n}\n')
        self.assertIn('enc_r_store(g_enc, t->depth, rt_dup_unstored(t) ? MTLStoreActionDontCare : MTLStoreActionStore, (NSUInteger)t->idx);', finish)
        self.assertIn('int dead = t->state == 2 || udc_dead || xvdead || rt_dup_unstored(t);', finish)

    def test_a_draw_marks_its_slots_only_when_its_primitives_are_encoded(self):
        """Each encode call of draw_inner sits under its own check for primitives, with the mark next to it, so a draw with
        no primitives and the exits between udc_note_draw and the encode calls mark nothing."""
        draw = production(r'static void draw_inner\(const p_draw \*dw, const p_draw_idx \*di\) \{.*?\n}\n')
        tail = draw[draw.index('udc_note_draw(pr);'):]
        strip = 'if (quads) rt_dup_note_encoded(pr);'
        self.assertIn(strip, tail)
        self.assertLess(tail.index('enc_r_draw_indexed(en, mp, (NSUInteger)n * 6'), tail.index(strip))
        marked = re.findall(r'if \([^{}]*\) \{ enc_r_draw\w*\(en, [^;]*\); rt_dup_note_encoded\(pr\); }', tail, re.S)
        self.assertEqual(len(marked), 6)
        self.assertEqual(len(re.findall(r'enc_r_draw\w*\(', tail)), len(marked) + 1, 'an encode call without its mark')
        self.assertEqual(tail.count('rt_dup_note_encoded(pr)'), len(marked) + 1, 'a mark without its encode call')
        self.assertLess(tail.index('enc_r_draw'), tail.index('rt_dup_note_encoded(pr)'))
        self.assertNotIn('rt_dup_note_draw', production(r'static void udc_note_draw\(NvProg \*pr\) \{.*?\n}\n'))

    def test_the_mark_uses_the_outputs_of_the_programs_fragment_stage(self):
        note = production(r'static void udc_note_draw\(NvProg \*pr\) \{.*?\n}\n')
        self.assertIn('uint8_t colors = 0, listed = 1;', note)   # no fragment stage: nothing listed, nothing written
        self.assertIn('if (st == 1) { cm = sh->rf.color_mask; colors = sh->rf.color_outputs; listed = sh->rf.colors_listed; }', note)
        self.assertIn('pr->udc_colors = colors; pr->udc_colors_listed = listed;', note)
        self.assertIn('rt_dup_note_draw(&g_sd[i], S.chmask.mask, pr->udc_colors, pr->udc_colors_listed);',
                      production(r'static void rt_dup_note_encoded\(__unsafe_unretained NvProg \*pr\) \{.*?\n}\n'))

    def test_the_outputs_come_from_what_the_translator_writes(self):
        """totk_xlate leaves raster empty, so color_mask is 0 for every shader; the list it does write is deps.fout, which the
        reflection has to read. That list is in the seeds already, so reading it needs no new seed."""
        service = (ROOT/'games/totk/tools/totk_xlate/Service.cs').read_text(encoding='utf-8')
        self.assertIn('["raster"] = new JsonObject()', service)
        self.assertIn('deps["fout"][k] = GetOr(fout, k, "float");', service)
        self.assertIn('deps[@"fout"]', (NVN/'nvn_refl.m').read_text(encoding='utf-8'))

    def test_every_kept_clear_goes_through_the_rule(self):
        """The op itself, and the two planning walks that take a clear ahead of its place."""
        self.assertIn('rt_dup_pend_clear(g->rt, c, g->clear_c, g->cc);', production(r'static void hoist_try\(void\) \{.*?\n}\n'))
        self.assertIn('rt_dup_pend_clear(r2, c, clr, cc);', production(r'static void fuse_try\(void\) \{.*?\n}\n'))
        self.assertIn('rt_dup_pend_clear(&R.rt, c, R.clear_c, R.cc);', production(r'case OP_CLEAR_COLOR: \{\n                const p_clear_color \*c = a;\n.*?break;\n            }\n'))
        self.assertEqual((NVN/'nvn_mtl.m').read_text(encoding='utf-8').count('MTLClearColorMake(c->rgba[0]'), 1, 'a clear kept past the rule')

    def test_a_mid_pass_clear_reaches_the_other_tile_copies(self):
        clear = production(r'static void clear_quad\(const p_clear_color \*c\) \{.*?\n}\n')
        self.assertIn('BOTW_RT_DUP_CLEAR_TO_FIRST(c)', clear)   # Breath of the Wild left the slot unattached: the first slot takes it
        self.assertIn('unsigned others = rt_dup_other_slots(&R.rt, c->index);\n'
                      '    for (int i = 0; i < 8; i++) if ((others >> i & 1) && g_pass.cfmt[i])\n'
                      '        clear_quad_core(en, g_pass.cfmt, g_pass.hd ? g_pass.dfmt : 0, g_pass.hs ? g_pass.sfmt : 0, '
                      'g_pass.samples, tw, th, i, c->mask, c->rgba, sc);', clear)

    def test_a_draw_does_not_read_one_of_two_tile_copies(self):
        self.assertIn('if (rt_dup_other_slots(&R.rt, j)) return nil;',
                      production(r'static id<MTLFunction> att_fb_take\(.*?\n}\n'))


@unittest.skipUnless(sys.platform == 'darwin', 'the reflection reader uses macOS/iOS Foundation and Metal')
class ColourOutputsOfAReflection(unittest.TestCase):
    """Production nvn_refl_from_json in tests/refl_colors_probe.m, on the reflections the runtime can meet."""
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('clang')
        if not compiler:
            raise unittest.SkipTest('clang is required')
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.executable = Path(cls.temporary.name)/'refl-colors'
        build = subprocess.run(
            [compiler, '-fobjc-arc', '-framework', 'Foundation', '-framework', 'Metal', '-I' + str(NVN),
             str(ROOT/'tests/refl_colors_probe.m'), str(NVN/'nvn_refl.m'), '-o', str(cls.executable)],
            capture_output=True, text=True, timeout=90)
        if build.returncode:
            raise AssertionError(build.stdout + build.stderr)

    def outputs(self, **reflection):
        """(colors_listed, color_outputs) of a reflection with these fields."""
        run = subprocess.run([str(self.executable), json.dumps({'route': 'B', 'bindings': [], **reflection})],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        listed, outputs = run.stdout.split()
        return int(listed), int(outputs)

    def test_the_translators_list(self):
        self.assertEqual(self.outputs(raster={}, deps={'fout': {'0': 'float', '2': 'uint'}}), (1, 0b101))

    def test_a_shader_with_no_colour_output_lists_none(self):
        self.assertEqual(self.outputs(raster={}, deps={'fout': {}}), (1, 0))

    def test_raster_colors_comes_first(self):
        self.assertEqual(self.outputs(raster={'colors': [1]}, deps={'fout': {'3': 'float'}}), (1, 0b10))

    def test_a_reflection_with_neither_list_says_so(self):
        self.assertEqual(self.outputs(raster={}), (0, 0))
        self.assertEqual(self.outputs(), (0, 0))


if __name__ == '__main__':
    unittest.main()
