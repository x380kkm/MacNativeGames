#!/usr/bin/env python3
"""The iOS export of Tears of the Kingdom 1.4.3 on Windows: main's code with the game patches written in, as build_ipa.py
has the Mac loader's export-ios write it, made with runtime/game_patches_v143.c itself; standard library and clang only.

  python export_ios_windows.py --tree <work>/totk [--out <dir>] [--clang <clang.exe>]
  python export_ios_windows.py --tree <work>/totk --check <dir> [--clang <clang.exe>]

The iPhone / iPad cannot write code: an iOS build carries main's text with the game patches already in it, and the
runtime only checks their words at start (game_patches_v143.c, TARGET_OS_IPHONE). The sections of an app built at 30a1b93
(recover_ipa.py, build/from-ipa/embed) lack the patches added since, the fade-counter fix and the render-resolution patch:
on those sections the device's checks keep the game's own counters and scene size and log "not patched at build". This
tool makes the sections again from the pinned rewrites. It builds export_ios_host.c with game_patches_v143.c twice with clang,
darwin_shim standing in for the Darwin headers that file includes for its Mac diagnostics:
 - the export (without --check): checks <tree>/rewritten/v143/<module>.patched.bin against assets/expected-v1.4.3.json,
   runs the Mac patch path with build_ipa.py's environment (TOTK_EXPORT_IOS=<out>, TOTK_RENDER_RES=1280x720, no other
   TOTK_* variable) and writes the nine sections gen_embed.py embeds into <out> (default <tree>/build/export-ios, where
   package_ipa_windows.py takes them from): <module>.x0.bin and <module>.x1.bin as loader.c export_ios_text writes them,
   <module>.w.bin the image between them as gen_embed.py takes it. Then layout.json (gen_embed.py --layout-of; the
   runtime the ios-runtime workflow builds carries the hashes of ios/ci/embed-layout-v143.json, which must be this
   file), export-ios.json (the sources as committed, compiler, environment, inputs and outputs) and the check below,
   which must pass with every patch in the sections.
 - the check (--check <dir>, and after every export): the device's path on the sections in <dir> with no TOTK_* variable
   set. It stops where the device stops at start (runtime_fail) and names the patches the device would start without.
   Nothing is written into <dir>.
The tree's fixups.tsv give each module's layout and its image the file size, as for gen_embed.py. Logs: <out>/build.log,
export-ios.log and check-ios.log; --check prints its log. The sections are game code: never commit or upload them.

Windows only: darwin_shim fills in for the Microsoft C library (Visual Studio's C++ Clang tools: clang.exe from PATH,
--clang, or found with vswhere). On a Mac build_ipa.py runs the loader's own export-ios."""
import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
IOS = TOOLS.parent
GAME = IOS.parent
sys.path.insert(0, str(TOOLS))
import gen_embed   # noqa: E402  layout.json, as --layout-of writes it

VERSION = 'v143'
NAMES = ('main', 'subsdk0', 'sdk')   # runtime/loader.c module order
PAGE = gen_embed.PG
EXPORT_DIR = 'build/export-ios'   # under the work folder
RUNTIME = GAME/'runtime'
PATCHES = RUNTIME/'game_patches_v143.c'
HOST = TOOLS/'export_ios_host.c'
SHIM = TOOLS/'darwin_shim'
EXPECTED = GAME/'assets/expected-v1.4.3.json'
PINNED_LAYOUT = IOS/f'ci/embed-layout-{VERSION}.json'
# build_ipa.py: the scene-size patch is code the phone cannot write, so the export runs with one valid size (any size
# gives the same words; the device puts its own size on the data page).
EXPORT_ENV = {'TOTK_RENDER_RES': '1280x720'}
# The Makefile's flags for build/totk-native-v143 (NATIVE_OPT -O2); the iOS project (ios/project.yml) builds without -Werror.
CFLAGS = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Wno-deprecated-declarations', '-DTOTK_GAME_V143=1']
MAC_ONLY_CFLAGS = ['-Werror']
# Every file the two programs are built from (export-ios.json records their SHA-256).
SOURCES = [PATCHES, HOST] + [RUNTIME/h for h in ('game_patches.h', 'aspect_patch.h', 'aspect_math.h', 'game_version.h',
                                                'runtime.h', 'world_survey.h')] + sorted(SHIM.rglob('*.h'))
# Where a patch is missing from the sections, the device's path keeps the game's own code and logs one of these
# (game_patches_v143.c patch_fade_increment and patch_render_res, aspect_patch.h aspect_install).
NOT_EMBEDDED = ('(not patched at build)', "is not the export's stub branch")


class ExportError(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise ExportError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def source_digest(path):
    """A repository file's SHA-256 as committed: a Windows checkout with core.autocrlf has CR LF line ends instead."""
    return digest(path.read_bytes().replace(b'\r\n', b'\n'))


def find_clang(given):
    """--clang, else clang on PATH, else the newest Visual Studio's C++ Clang tools (vswhere)."""
    if given:
        require(Path(given).is_file() or shutil.which(given), f'{given}: no such compiler')
        return str(given)
    if shutil.which('clang'):
        return shutil.which('clang')
    vswhere = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'))/'Microsoft Visual Studio/Installer/vswhere.exe'
    if vswhere.is_file():
        found = subprocess.run([str(vswhere), '-latest', '-products', '*', '-find', r'VC\Tools\Llvm\x64\bin\clang.exe'],
                               capture_output=True, text=True).stdout.split('\n')
        found = [f.strip() for f in found if f.strip()]
        if found:
            return found[0]
    raise ExportError('clang not found: install Visual Studio\'s "C++ Clang tools for Windows" or give --clang')


def environment(extra):
    """This process's environment without any TOTK_* variable (each one changes what the patches do), plus extra."""
    return {k: v for k, v in os.environ.items() if not k.upper().startswith('TOTK_')} | extra


def run_logged(args, log, env, what):
    """Runs a program with its output in log; a failure names the runtime_fail line it stopped with."""
    with log.open('w', encoding='utf-8', newline='\n') as f:
        p = subprocess.run([str(a) for a in args], env=env, stdout=f, stderr=subprocess.STDOUT)
    if p.returncode:
        lines = log.read_text(encoding='utf-8', errors='replace').splitlines()
        stop = [line for line in lines if line.startswith('[totk] FAIL: ')]
        raise ExportError(f'{what} failed: ' + (stop[-1][len('[totk] FAIL: '):] if stop else f'exit {p.returncode}'))


def build(clang, into, log):
    """The two programs: the Mac's patch path (export) and the device's (check)."""
    hosts, failed = {}, None
    with log.open('w', encoding='utf-8', newline='\n') as f:
        for name, iphone in (('export', 0), ('check', 1)):
            exe = into/f'export_ios_{name}.exe'
            cmd = [clang, *CFLAGS, *(MAC_ONLY_CFLAGS if not iphone else []), f'-DTARGET_OS_IPHONE={iphone}',
                   '-isystem', SHIM, '-I', RUNTIME, HOST, PATCHES, '-o', exe]
            f.write(' '.join(str(c) for c in cmd) + '\n'); f.flush()
            if subprocess.run([str(c) for c in cmd], stdout=f, stderr=subprocess.STDOUT).returncode:
                failed = name
                break
            hosts[name] = exe
    if failed:
        raise ExportError(f'building the {failed} program failed; see {log}\n' + log.read_text(encoding='utf-8', errors='replace')[-3000:])
    return hosts


def module_layouts(tree):
    """{name: (image path, layout)} from <tree>/rewritten/v143: the fixups.tsv header, as gen_embed.py reads it, and the
    image's length as the file size."""
    rewritten = tree/'rewritten'/VERSION
    layouts = {}
    for name in NAMES:
        image, fixups = rewritten/f'{name}.patched.bin', rewritten/f'{name}.fixups.tsv'
        require(image.is_file() and fixups.is_file(), f'{rewritten}: {name}.patched.bin and {name}.fixups.tsv needed (recover_ipa.py)')
        hdr = dict(line[2:].split()[:2] for line in fixups.read_text().splitlines() if line.startswith('# ') and len(line.split()) >= 3)
        keys = ('TEXT_END', 'RO_OFF', 'DATA_OFF', 'PATCH_OFF', 'KEY_PAGE_OFF')
        require(all(k in hdr for k in keys), f'{fixups}: needs {", ".join(keys)}')
        layout = {k: int(hdr[k], 16) for k in keys}
        layout['FILE_SIZE'] = image.stat().st_size
        require(layout['PATCH_OFF'] % PAGE == 0 and gen_embed.up(layout['TEXT_END']) <= layout['KEY_PAGE_OFF']
                and layout['KEY_PAGE_OFF'] + PAGE <= layout['PATCH_OFF'] <= layout['FILE_SIZE'], f'{fixups}: not a 1.4.3 module layout')
        layouts[name] = (image, layout)
    return layouts


def layout_args(layout):
    return [hex(layout[k]) for k in ('FILE_SIZE', 'TEXT_END', 'RO_OFF', 'DATA_OFF', 'PATCH_OFF', 'KEY_PAGE_OFF')]


def check(host, sections, layouts, log, what):
    """The device's path on <sections>/<module>.<part>.bin for the modules of layouts (main among them), with no TOTK_*
    variable: runtime_fail stops it as on the device. Returns the log lines of the patches it starts without."""
    args = [host, 'check']
    for name, (_, layout) in layouts.items():
        parts = [sections/f'{name}.{part}.bin' for part in gen_embed.PARTS]
        require(all(p.is_file() for p in parts), f'{sections}: {name}.x0.bin, {name}.w.bin and {name}.x1.bin needed')
        args += [name, *parts, *layout_args(layout)]
    run_logged(args, log, environment({}), what)
    return [line for line in log.read_text(encoding='utf-8').splitlines() if any(n in line for n in NOT_EMBEDDED)]


def write_sections(host, layouts, images, out):
    """The Mac's patch path with build_ipa.py's environment: <out>/<module>.x0.bin and .x1.bin from the export program,
    <module>.w.bin from the image (gen_embed.py: from the end of the text's page to the patch area). Returns the patched
    word counts the program prints, {module: {'text': n, 'patch_area': n}}."""
    env = EXPORT_ENV | {'TOTK_EXPORT_IOS': str(out)}
    args = [host, 'export']
    for name, (image, layout) in layouts.items():
        args += [name, image, *layout_args(layout)]
    log = out/'export-ios.log'
    run_logged(args, log, environment(env), f'the export (see {log})')
    counts = {}
    for line in log.read_text(encoding='utf-8').splitlines():
        words = line.split()
        if len(words) == 5 and words[0] in layouts and words[1].startswith('text_bytes='):
            counts[words[0]] = {'text': int(words[2].split('=')[1]), 'patch_area': int(words[4].split('=')[1])}
    require(sorted(counts) == sorted(layouts), f'the export did not report every module; see {log}')
    for name, (_, layout) in layouts.items():
        (out/f'{name}.w.bin').write_bytes(images[name][gen_embed.up(layout['TEXT_END']):layout['PATCH_OFF']])
    return counts


def export(hosts, layouts, out, clang):
    """The nine sections of the pinned rewrites in out, their layout.json and export-ios.json, checked as on the device
    with every patch in them."""
    expected = json.loads(EXPECTED.read_text())['rewritten_sha256']
    images = {}
    for name, (image, _) in layouts.items():
        data = image.read_bytes()
        require(digest(data) == expected[f'{name}.patched.bin'], f'{image}: SHA-256 is not the pinned rewrite ({EXPECTED.name})')
        images[name] = data
    out.mkdir(parents=True, exist_ok=True)
    outputs = [out/f'{name}.{part}.bin' for name in NAMES for part in gen_embed.PARTS] + [out/'layout.json', out/'export-ios.json']
    for path in outputs:
        path.unlink(missing_ok=True)   # nothing of an earlier export stays beside this one
    try:
        counts = write_sections(hosts['export'], layouts, images, out)
        gen_embed.write_layout(out, out/'layout.json', NAMES)
        log = out/'check-ios.log'
        missing = check(hosts['check'], out, layouts, log, f'the device\'s checks of the export (see {log})')
        require(not missing, f'the export lacks patches the device checks for (see {log}): ' + '; '.join(missing))
    except ExportError:
        for path in outputs:
            path.unlink(missing_ok=True)   # a failed export leaves no sections to package
        raise
    sections = json.loads((out/'layout.json').read_text())['modules']
    version = subprocess.run([clang, '--version'], capture_output=True, text=True).stdout.splitlines()
    manifest = {'version': VERSION, 'tool': 'ios/tools/export_ios_windows.py',
                'sources': {p.relative_to(GAME).as_posix(): source_digest(p) for p in SOURCES},
                'clang': version[0] if version else '',
                'cflags': {'export': CFLAGS + MAC_ONLY_CFLAGS + ['-DTARGET_OS_IPHONE=0'], 'check': CFLAGS + ['-DTARGET_OS_IPHONE=1']},
                'environment': EXPORT_ENV | {'TOTK_EXPORT_IOS': '<this folder>'},
                'rewritten_sha256': {f'{n}.patched.bin': digest(images[n]) for n in NAMES},
                'patched_words': counts, 'sections': sections}
    (out/'export-ios.json').write_text(json.dumps(manifest, indent=2) + '\n', newline='\n')
    return counts, sections


def pinned_differences(sections):
    """The sections whose size or SHA-256 differ from ios/ci/embed-layout-v143.json, [] without that file."""
    try:
        pinned = {m['name']: m for m in json.loads(PINNED_LAYOUT.read_text())['modules']}
    except OSError:
        return []
    return [f'{m["name"]}.{part}' for m in sections for part in gen_embed.PARTS
            if m['name'] not in pinned or pinned[m['name']][part] != m[part]]


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('--tree', type=Path, required=True, help='the work folder (recover_ipa.py --out): rewritten/v143 with fixups.tsv')
    p.add_argument('--out', type=Path, help=f'where the sections go (default: <tree>/{EXPORT_DIR})')
    p.add_argument('--check', type=Path, metavar='DIR', help='only run the device\'s checks on the sections in DIR')
    p.add_argument('--clang', help='clang.exe (default: PATH, then Visual Studio\'s through vswhere)')
    a = p.parse_args()
    require(os.name == 'nt', 'export_ios_windows.py is for Windows; on a Mac build_ipa.py runs the loader\'s export-ios')
    tree = a.tree.resolve()
    layouts = module_layouts(tree)
    clang = find_clang(a.clang)
    with tempfile.TemporaryDirectory(prefix='export-ios-') as tmp:
        if a.check:
            sections = a.check.resolve()
            hosts = build(clang, Path(tmp), Path(tmp)/'build.log')
            log = Path(tmp)/'check-ios.log'
            try:
                missing = check(hosts['check'], sections, layouts, log, f'the device\'s checks of {sections}')
            finally:
                if log.is_file():
                    print(log.read_text(encoding='utf-8', errors='replace'), end='')
            print(f'{sections}: the device\'s checks of the embedded code passed')
            if missing:
                print(f'the device starts without {len(missing)} patch(es); an export (without --check) writes them in:')
                print('\n'.join(f'  {line}' for line in missing))
            return
        out = (a.out or tree/EXPORT_DIR).resolve()
        out.mkdir(parents=True, exist_ok=True)
        hosts = build(clang, Path(tmp), out/'build.log')
        counts, sections = export(hosts, layouts, out, clang)
    for name in NAMES:
        print(f'{name}: {counts[name]["text"]} text words and {counts[name]["patch_area"]} patch-area words patched')
    print(f'{out}: nine sections, layout.json, export-ios.json; the device\'s checks passed with every patch (check-ios.log)')
    differ = pinned_differences(sections)
    if differ:
        print(f'not the sections {PINNED_LAYOUT.relative_to(GAME).as_posix()} pins: {", ".join(differ)}; a runtime built from that '
              f'layout refuses them (build it from {out/"layout.json"})')


if __name__ == '__main__':
    try:
        main()
    except ExportError as e:
        sys.exit(f'export_ios_windows.py: {e}')
