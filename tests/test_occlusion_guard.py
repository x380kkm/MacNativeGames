"""The occlusion report rules (docs/how-it-works.md, Occlusion queries) with production code from nvn_mtl.m: occl_guard_on
and occl_settle run in tests/occlusion_guard_probe.c, for each combination of platform, game and TOTK_OCCL_GUARD. The
completion handler around them is Objective-C, so source checks keep it feeding and writing what occl_settle settles."""
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


class OcclusionGuard(unittest.TestCase):
    def probe(self, *defines):
        compiler = shutil.which('cc')
        if not compiler:
            self.skipTest('A C compiler is required')
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory)
        code = '\n'.join(production(pattern) for pattern in (
            r'typedef struct \{ int kind; volatile uint32_t \*val;.*?post_op;',
            r'static _Atomic uint64_t g_occl_raised;', r'static _Atomic uint64_t g_occl_guarded;',
            r'#define OCCL_HOLD_FRAMES \d+',
            r'static int occl_guard_on\(void\) \{.*?\n}\n',
            r'typedef struct \{ int queries, zeros; \} occl_tally;',
            r'static occl_tally occl_settle\(.*?\n}\n'))
        fixture = (ROOT / 'tests/occlusion_guard_probe.c').read_text(encoding='utf-8')
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
        environment = {k: v for k, v in os.environ.items() if k != 'TOTK_OCCL_GUARD'} | variables
        run = subprocess.run([str(executable), state], capture_output=True, text=True, env=environment)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('occlusion guard ok', run.stdout)

    def test_on_by_default_on_ios_and_off_with_its_switch(self):
        executable = self.probe('-DIOS_BUILD=1')
        self.expect(executable, 'on')
        self.expect(executable, 'off', TOTK_OCCL_GUARD='0')

    def test_off_by_default_on_the_mac_and_on_with_its_switch(self):
        executable = self.probe('-DIOS_BUILD=0')
        self.expect(executable, 'off')
        self.expect(executable, 'on', TOTK_OCCL_GUARD='1')

    def test_off_in_a_breath_of_the_wild_build(self):
        self.expect(self.probe('-DIOS_BUILD=1', '-DGAME_BOTW=1'), 'off')

    def test_the_handler_hands_every_result_over_before_it_writes_a_report(self):
        handler = production(r'uint64_t mtl_sub_commit\(void\) \{.*?\n}\n')
        counted = handler.index('ops[i].sum = sum; ops[i].skipped = l->skipped; free(l);')
        settled = handler.index('occl_settle(ops, n, failed);')
        written = handler.index('uint64_t rec[2] = {ops[i].sum, gpu_ticks()};')
        self.assertLess(counted, settled)
        self.assertLess(settled, written)

    def test_a_failed_chunk_is_found_by_the_fence_of_its_submission(self):
        # g_last_commit_error does not say this: the next submission's start clears it, and it may be another
        # submission's failure.
        self.assertIn('atomic_store(&g_chunk_error_fence, fence_next);', production(r'static void mtl_sub_split\(void\) \{.*?\n}\n'))
        self.assertIn('int failed = cb.error != nil || atomic_load(&g_chunk_error_fence) == fence;',
                      production(r'uint64_t mtl_sub_commit\(void\) \{.*?\n}\n'))


if __name__ == '__main__':
    unittest.main()
