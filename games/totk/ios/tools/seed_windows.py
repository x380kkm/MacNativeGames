#!/usr/bin/env python3
"""Prepare the startup shader seed of an iPhone / iPad build on Windows, from game files prepared before
(ios/tools/recover_ipa.py, or a work folder of build_app.py), and make the seed's device form.

    python games/totk/ios/tools/seed_windows.py tools --work <dir> [--dotnet <dotnet>]
    python games/totk/ios/tools/seed_windows.py seed --work <dir> --romfs <tree>/extracted/v143/romfs --modules <tree>/rewritten/v143 --version v143 [--extra-list <file>]...

tools: what build_app.py and totk_xlate/publish_native.sh make on the Mac, with Visual Studio (its clang, the C++ tools and
  the linker NativeAOT uses) and the .NET 10 SDK. SPIRV-Cross at the commit build_app.py pins (SPIRV_CROSS), from GitHub's
  archive of that commit, used only when its files hash to the tree GitHub's API names for the commit. The spirv-cross
  program from build_app.py's SPIRV_CROSS_SOURCES and SPIRV_CROSS_FLAGS, with -std=c++14 instead of -std=c++11 (the MSVC
  library does not compile as C++11) and no -arch. The translator as publish_native.sh builds it: vendor/ryujinx with
  patches/*.patch, the service and SPIRV-Cross linked in (spirv_cross_inproc.cpp), NativeAOT for win-x64. Sources go in
  with the line ends git stores (a Windows clone checks them out with CRLF). Output: <work>/tools/bin (spirv-cross.exe,
  totk_xlate.exe, tools.json), the build logs in <work>/tools/logs.
seed: scripts/prepare_shader_seed.py with them, into <work>/seed, its caches beside it as on the Mac (seed.inventory,
  seed.translations, seed.aliases.tsv, seed.verified.json). --extra-list adds the V rows of a file a device wrote
  (shader-list-contribution.txt: the bind states it met that the shared list lacks) to this seed only: they join a copy
  of the shared list, <work>/seed.list.tsv, and the warm-up lists stay the shared list's. A row a variant made before
  already serves adds no variant (prepare_shader_seed.py plan). The run then prints how many rows the seed serves, with
  the rule the runtime picks a variant by (totk_shader_rt.m deps_match over <key>.variants), how many variants the rows
  added, and why the rows not served are not: a failed translation, or a shader this game version does not have. Without
  --extra-list the shared list is used as it is.

The device form (device_seed; package_ipa_windows.py --seed makes it beside the IPA with the runtime's translation chain,
push_device_windows.py copies it into the app's Documents/GameData) is what build_ipa.py puts beside an IPA built with
--image-outside: the seed's files, its manifest with every file's SHA-256 (build_ipa.py prepare_seed), shader_map.tsv,
the shared list's pso_list.tsv and pso_title.tsv renamed through <seed>.aliases.tsv, and fingerprint.txt, the SHA-256
of the manifest, shader_map.tsv, pso_list.tsv and pso_title.tsv as build_ipa.py computes it. Metal libraries come only
from a folder of <variant>_b.metallib compiled from this seed's MSL elsewhere (compile_seed.py on a Mac; package_ipa_windows.py
--metallibs): Windows has no
Metal compiler, and without them the device compiles each shader from its MSL when it first needs it (nvn_mtl.m
shader_load). The output holds game-derived data: keep <work> outside the repository."""
import argparse, ast, concurrent.futures, hashlib, json, os, re, shutil, subprocess, sys, tarfile, urllib.request
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
TOTK = TOOLS.parents[1]
REPO = TOTK.parents[1]
XLATE = TOTK / 'tools/totk_xlate'
sys.path.insert(0, str(TOTK/'scripts'))
from prepare_shader_seed import answers_for, builtin_variants, deps_match, suffix   # noqa: E402
from shader_list import KEY, ShaderList, canonical   # noqa: E402

# What the device imports (totk_shader_seed.h totk_seed_import_into): file names, schema 1, a shader count
SEED_NAME = re.compile(r'^(?:[0-9a-f]{64}\.variants|[0-9a-f]{64}-[0-9a-f]{12}_b\.(?:metal|json|metallib)|pso_manifest\.tsv|shader-keys\.json)$')
SHADER_MAP = b'# TOTK control-code-sha256-v1\n'   # build_ipa.py prepare_seed
SHADER_LIST = TOTK/'assets/shader_list.tsv'   # the shared list the warm-up lists come from (build_ipa.py)
VSWHERE = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'))/'Microsoft Visual Studio/Installer/vswhere.exe'


class SeedError(RuntimeError):
    pass


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def run(cmd, log, cwd=None, env=None):
    """Run cmd with its output in log; a failure raises with the log's last lines."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, 'w', encoding='utf-8', newline='\n') as f:
        r = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT)
    if r.returncode:
        tail = log.read_text(encoding='utf-8', errors='replace').splitlines()[-30:]
        raise SeedError(f'{Path(str(cmd[0])).name} failed ({r.returncode}); see {log}\n' + '\n'.join(tail))


def build_app_pins():
    """SPIRV_CROSS, SPIRV_CROSS_SOURCES and SPIRV_CROSS_FLAGS of build_app.py, read as publish_native.sh reads them."""
    names = {'SPIRV_CROSS', 'SPIRV_CROSS_SOURCES', 'SPIRV_CROSS_FLAGS'}
    found = {node.targets[0].id: ast.literal_eval(node.value) for node in ast.parse((REPO/'build_app.py').read_bytes()).body
             if isinstance(node, ast.Assign) and len(node.targets) == 1 and getattr(node.targets[0], 'id', None) in names}
    if set(found) != names:
        raise SeedError(f'build_app.py lacks {sorted(names - set(found))}')
    return found


def windows_flags(flags):
    """build_app.py's SPIRV-Cross flags for Visual Studio's clang (target x86_64-pc-windows-msvc): no -arch, and C++14
    instead of C++11, the oldest standard the MSVC library's headers compile with."""
    out, skip = [], False
    for flag in flags:
        if skip or flag == '-arch':
            skip = not skip
            continue
        out.append('-std=c++14' if flag == '-std=c++11' else flag)
    return out


def llvm_bin():
    """The LLVM tools of the newest Visual Studio with its clang component (vswhere)."""
    found = subprocess.run([str(VSWHERE), '-latest', '-products', '*', '-requires', 'Microsoft.VisualStudio.Component.VC.Llvm.Clang',
                            '-property', 'installationPath'], capture_output=True, text=True) if VSWHERE.is_file() else None
    path = found.stdout.strip().splitlines()[0] if found and found.returncode == 0 and found.stdout.strip() else ''
    bin_dir = Path(path)/'VC/Tools/Llvm/x64/bin'
    if not (bin_dir/'clang++.exe').is_file():
        raise SeedError('no Visual Studio with "C++ Clang tools for Windows" (and "Desktop development with C++") found')
    return bin_dir


def fetch(url, dest):
    with urllib.request.urlopen(url, timeout=120) as r, open(dest, 'wb') as f:
        shutil.copyfileobj(r, f)


def object_id(kind, data):
    return hashlib.sha1(kind + b' ' + str(len(data)).encode() + b'\0' + data).digest()


def tree_id(entries, prefix=''):
    """The hash of the tree object a commit with these files (relative path -> (mode, bytes)) records."""
    children = {}
    for rel, value in entries.items():
        if rel.startswith(prefix):
            head, sep, _ = rel[len(prefix):].partition('/')
            children.setdefault(head, None if sep else value)
    rows = []
    for name, value in children.items():
        if value is None:
            rows.append((name.encode()+b'/', b'40000 '+name.encode()+b'\0'+tree_id(entries, prefix+name+'/')))
        else:
            rows.append((name.encode(), value[0].encode()+b' '+name.encode()+b'\0'+object_id(b'blob', value[1])))
    return object_id(b'tree', b''.join(row for _, row in sorted(rows)))


def fetch_spirv_cross(url, commit, root):
    """<root>/src/SPIRV-Cross: the files of that commit, from GitHub's archive of it; accepted only when they hash to the
    tree GitHub's API names for the commit."""
    src, stamp = root/'src/SPIRV-Cross', root/'src/SPIRV-Cross.commit'
    if stamp.is_file() and stamp.read_text(encoding='utf-8').strip() == commit and src.is_dir():
        return src
    repo = re.fullmatch(r'https://github\.com/([^/]+/[^/]+?)(?:\.git)?', url)
    if not repo:
        raise SeedError(f'{url}: not a GitHub repository')
    dl = root/'dl'; dl.mkdir(parents=True, exist_ok=True)
    archive, info = dl/f'SPIRV-Cross-{commit}.tar.gz', dl/f'SPIRV-Cross-{commit}.json'
    fetch(f'https://api.github.com/repos/{repo.group(1)}/commits/{commit}', info)
    want = json.loads(info.read_text(encoding='utf-8'))['commit']['tree']['sha']
    fetch(f'https://github.com/{repo.group(1)}/archive/{commit}.tar.gz', archive)
    entries = {}
    with tarfile.open(archive) as t:
        for m in t.getmembers():
            rel = m.name.partition('/')[2]
            if not rel or m.isdir():
                continue
            if m.issym():
                entries[rel] = ('120000', m.linkname.encode())
            elif m.isfile():
                entries[rel] = ('100755' if m.mode & 0o111 else '100644', t.extractfile(m).read())
            else:
                raise SeedError(f'{archive}: unexpected member {m.name}')
    got = tree_id(entries).hex()
    if got != want:
        raise SeedError(f'{archive}: its files hash to tree {got}, commit {commit} has {want}')
    shutil.rmtree(src, ignore_errors=True)
    for rel, (mode, data) in entries.items():
        if mode != '120000':   # SPIRV-Cross's links are test references, not sources
            (src/rel).parent.mkdir(parents=True, exist_ok=True)
            (src/rel).write_bytes(data)
    stamp.write_text(commit+'\n', encoding='utf-8', newline='\n')
    print(f'SPIRV-Cross {commit}: {len(entries)} files, tree {want} checked')
    return src


def build_spirv_cross(src, pins, llvm, out, logs):
    """spirv-cross.exe (build_app.py build_spirv_cross) and totk_spirv_cross.lib (publish_native.sh: every source but
    main.cpp, and spirv_cross_inproc.cpp, which includes it)."""
    flags, objs = windows_flags(pins['SPIRV_CROSS_FLAGS']), out/'obj'
    objs.mkdir(parents=True, exist_ok=True)
    jobs = [(src/name, objs/(name+'.o'), []) for name in pins['SPIRV_CROSS_SOURCES']]
    jobs.append((XLATE/'spirv_cross_inproc.cpp', objs/'spirv_cross_inproc.o', ['-I', src]))
    def compile_one(job):
        source, obj, extra = job
        run([llvm/'clang++.exe', *flags, *extra, '-c', source, '-o', obj], logs/'spirv-cross'/(obj.stem+'.log'))
    with concurrent.futures.ThreadPoolExecutor(os.cpu_count() or 4) as pool:
        list(pool.map(compile_one, jobs))
    program = [objs/(name+'.o') for name in pins['SPIRV_CROSS_SOURCES']]
    run([llvm/'clang++.exe', *program, '-o', out/'spirv-cross.exe'], logs/'spirv-cross/link.log')
    lib = out/'totk_spirv_cross.lib'
    lib.unlink(missing_ok=True)
    run([llvm/'llvm-lib.exe', f'/out:{lib}', *[o for o in program if o.stem != 'main.cpp'], objs/'spirv_cross_inproc.o'],
        logs/'spirv-cross/lib.log')
    return out/'spirv-cross.exe', lib


def copy_as_stored(src, dst):
    """A file with the line ends git stores (LF): a Windows clone's checkout has CRLF (core.autocrlf), which neither the
    patches nor the Mac's build of the same sources have. A file with a NUL byte is copied as it is."""
    data = src.read_bytes()
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data if b'\0' in data else data.replace(b'\r\n', b'\n'))


def patch_program():
    """GNU patch, as publish_native.sh uses it: on PATH, or the one Git for Windows carries."""
    found = shutil.which('patch')
    vcs = shutil.which('git')
    candidates = [Path(found)] if found else []
    candidates += [Path(vcs).resolve().parents[1]/'usr/bin/patch.exe'] if vcs else []
    for p in candidates:
        if p.is_file():
            return p
    raise SeedError('no GNU patch: install Git for Windows, or put patch.exe on PATH')


def build_translator(lib, root, logs, dotnet):
    """publish_native.sh for win-x64: <root>/build/xlate/out/totk_xlate.exe."""
    stage = root/'build/xlate'
    shutil.rmtree(stage, ignore_errors=True)
    ryu = stage/'ryujinx-src'
    for p in sorted((REPO/'vendor/ryujinx').rglob('*')):
        rel = p.relative_to(REPO/'vendor/ryujinx')
        if p.is_file() and not ({'obj', 'bin'} & set(rel.parts[:-1])):
            copy_as_stored(p, ryu/rel)
    tool = patch_program()
    for p in sorted(XLATE.glob('patches/*.patch')):
        copy_as_stored(p, stage/'patches'/p.name)
        run([tool, '-s', '--binary', '-d', ryu, '-p1', '--forward', '-i', stage/'patches'/p.name], logs/f'patch-{p.stem}.log')
    for p in [*sorted(XLATE.glob('*.cs')), XLATE/'totk_xlate.csproj']:
        copy_as_stored(p, stage/'xlate'/p.name)
    # NativeAOT finds the linker through Visual Studio's vcvarsall.bat, which runs vswhere.exe from PATH
    env = dict(os.environ, PATH=os.environ.get('PATH', '') + os.pathsep + str(VSWHERE.parent))
    run([dotnet, 'publish', stage/'xlate/totk_xlate.csproj', '-c', 'Release', '-r', 'win-x64', '-p:PublishAot=true',
         '-p:InvariantGlobalization=true', f'-p:RyuSrc={ryu}', f'-p:TotkSpirvCrossLib={lib}', '-o', stage/'out'],
        logs/'dotnet-publish.log', env=env)
    return stage/'out/totk_xlate.exe'


def tool_version(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    return (r.stdout or r.stderr).strip().splitlines()[0] if r.returncode == 0 else None


def cmd_tools(a):
    root = a.work.resolve()/'tools'
    logs, bin_dir = root/'logs', root/'bin'
    pins, llvm = build_app_pins(), llvm_bin()
    url, commit = pins['SPIRV_CROSS']
    src = fetch_spirv_cross(url, commit, root)
    spirv_cross, lib = build_spirv_cross(src, pins, llvm, root/'build/spirv-cross', logs)
    translator = build_translator(lib, root, logs, a.dotnet)
    bin_dir.mkdir(parents=True, exist_ok=True)
    for p in (spirv_cross, translator):
        shutil.copyfile(p, bin_dir/p.name)
    record = dict(schema=1, spirv_cross=dict(url=url, commit=commit, flags=windows_flags(pins['SPIRV_CROSS_FLAGS']),
                                             clang=tool_version([llvm/'clang++.exe', '--version'])),
                  dotnet=tool_version([a.dotnet, '--version']), runtime='win-x64 NativeAOT, InvariantGlobalization',
                  files={p.name: sha256(bin_dir/p.name) for p in (spirv_cross, translator)})
    (bin_dir/'tools.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(f'tools ready in {bin_dir}: ' + ', '.join(f'{n} {d[:12]}' for n, d in record['files'].items()))


def extra_rows(paths):
    """The (shader key, deps) of the V rows of these files, deps in shader_list.py's canonical text. Comments and rows of
    other kinds (pipelines) are left out; a V row shader_list.py could not read stops it, since dropping it would leave
    that bind state out of the seed without a word. A file without V rows is the wrong file."""
    rows = set()
    for path in paths:
        found = 0
        for number, line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
            fields = line.split('\t')
            if fields[0] != 'V':
                continue
            try:
                deps = canonical(json.loads(fields[2])) if len(fields) == 3 and KEY.match(fields[1]) else None
            except ValueError:
                deps = None
            if deps is None:
                raise SeedError(f'{path}:{number}: not a shader list V row')
            rows.add((fields[1], deps)); found += 1
        if not found:
            raise SeedError(f'{path}: no V rows')
    return rows


def list_with_rows(rows, path):
    """path: the shared list with these V rows after its own, for prepare_shader_seed.py --shader-list; a row it has
    already counts once. Sorted, so the same rows give the same file and a seed made from it is reused."""
    path.write_bytes(SHADER_LIST.read_bytes() + ''.join(f'V\t{key}\t{deps}\n' for key, deps in sorted(rows)).encode())
    return path


def seed_variants(seed, key):
    """The rows of a shader's .variants, none when the seed has no variant of it."""
    index = seed/f'{key}.variants'
    return json.loads(index.read_bytes()) if index.is_file() else []


def unserved(seed, rows):
    """variant -> why, for the rows no variant of the seed serves. A row is served when a row of its shader's .variants
    matches its bind state, the test the runtime picks a variant with, so a served row is a draw the device does not skip."""
    failed = {row['variant']: row.get('error') for row in json.loads((seed/'seed-manifest.json').read_bytes()).get('skipped', [])}
    game = set(json.loads((seed/'shader-keys.json').read_bytes())['keys'])
    why = {}
    for key, deps in sorted(rows):
        answers = answers_for(json.loads(deps))
        if not any(deps_match(v.get('deps', {}), answers) for v in seed_variants(seed, key)):
            variant = f'{key}-{suffix(answers)}'
            why[variant] = 'this game version has no such shader' if key not in game else \
                failed.get(variant, 'seed-manifest.json records no failure for it')
    return why


def added_variants(seed, rows):
    """The variants of the seed only these rows asked for: a row's own translation, under the name prepare_shader_seed.py
    plan gives it, kept in its shader's .variants. A row a variant made before serves has none, since the preparation
    keeps no translation of it. A name the seed would hold without the rows is left out: a built-in variant's (the default
    bind state, the shadow maps' depth textures) or a shared-list row's, which a device's row can repeat."""
    def own(key, deps):
        return f'{key}-{suffix(answers_for(json.loads(deps)))}'
    shared = {own(key, deps) for key, deps in ShaderList.load(SHADER_LIST).variants}
    added = set()
    for key, deps in rows:
        variant = own(key, deps)
        kept = {v['variant'] for v in seed_variants(seed, key)} - {v['variant'] for v in builtin_variants(seed, key)}
        if variant in kept - shared:
            added.add(variant)
    return added


def cmd_seed(a):
    work, bin_dir = a.work.resolve(), a.work.resolve()/'tools/bin'
    for name in ('totk_xlate.exe', 'spirv-cross.exe'):
        if not (bin_dir/name).is_file():
            raise SeedError(f'{bin_dir/name} is missing: run "seed_windows.py tools --work {a.work}" first')
    extra = extra_rows(a.extra_list)
    cmd = [sys.executable, '-I', '-X', 'utf8', TOTK/'scripts/prepare_shader_seed.py', '--romfs', a.romfs.resolve(),
           '--output', work/'seed', '--translator', bin_dir/'totk_xlate.exe', '--spirv-cross', bin_dir/'spirv-cross.exe',
           '--version', a.version]
    if a.modules:
        cmd += ['--modules', a.modules.resolve()]
    if extra:
        cmd += ['--shader-list', list_with_rows(extra, work/'seed.list.tsv')]
    r = subprocess.run([str(c) for c in cmd])   # its progress goes to this console
    if r.returncode:
        raise SeedError(f'prepare_shader_seed.py failed ({r.returncode})')
    if extra:
        missing = unserved(work/'seed', extra)
        print(f'extra lists: the seed serves {len(extra) - len(missing)} of their {len(extra)} V rows')
        added = added_variants(work/'seed', extra)
        print(f'extra lists: their rows added {len(added)} variants to the seed (a row a variant already serves adds none)')
        for variant, why in missing.items():
            print(f'  not served: {variant}: {why}')
    print(f'seed ready in {work/"seed"}: package_ipa_windows.py --seed {work/"seed"} makes its device form')


def link_or_copy(src, dst):
    """A hard link where the file system allows one (the seed is ~90,000 files, 1.2 GB), a copy otherwise."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def metal_libraries(folder, manifest):
    """The <variant>_b.metallib files of folder, each of a shader the seed carries (<variant>_b.metal) and a Metal library
    (MTLB): the device loads one instead of compiling its MSL and does not check that it was made from it."""
    libs = sorted(Path(folder).glob('*_b.metallib'))
    for p in libs:
        with open(p, 'rb') as f:
            magic = f.read(4)
        if p.name.removesuffix('.metallib') + '.metal' not in manifest['files'] or magic != b'MTLB':
            raise SeedError(f'{p}: not a Metal library of a shader in this seed')
    return libs


def device_seed(seed, dest, chain, lists, metallibs=None):
    """dest: the seed's device form (the module docstring), with the Metal libraries of the folder metallibs, or none.
    The seed must be of the runtime's translation chain (chain) and hold only files the runtime imports; lists is a work
    folder for the exported shader lists. Its files are hard links where the file system allows. Returns the
    fingerprint; a dest of the same fingerprint is kept as it is."""
    if (seed/'fingerprint.txt').is_file():
        raise SeedError(f'{seed} is a device form already (fingerprint.txt): give the seed prepare_shader_seed.py made')
    raw = (seed/'seed-manifest.json').read_bytes()
    manifest = json.loads(raw)
    if manifest.get('chain') != chain:
        raise SeedError(f'{seed} is a seed of the translation chain {manifest.get("chain")}, the runtime translates with {chain}')
    shaders = manifest.get('shaders')
    if manifest.get('schema') != 1 or not isinstance(shaders, int) or shaders <= 0 or not manifest.get('files'):
        raise SeedError(f'{seed}: not a seed the runtime imports (schema 1, shaders, files)')
    names = sorted(n for n in os.listdir(seed) if n not in ('seed-manifest.json', 'shader_map.tsv') and (seed/n).is_file())
    refused = [n for n in names if not SEED_NAME.match(n)]
    if refused:
        raise SeedError(f'{seed}: files the runtime refuses in a seed (totk_shader_seed.h), e.g. {refused[:3]}')
    missing = sorted(set(manifest['files']) - set(names))
    if missing:
        raise SeedError(f'{seed}: {len(missing)} files its manifest names are not there, e.g. {missing[:3]}')
    libs = metal_libraries(metallibs, manifest) if metallibs else []
    known = manifest['files']   # the seed's own files keep the hashes checked when it was prepared (build_ipa.py)
    files = {n: known.get(n) or sha256(seed/n) for n in names} | {p.name: sha256(p) for p in libs}
    manifest.update(ios_metallibs=len(libs), ios_source_manifest_sha256=hashlib.sha256(raw).hexdigest(), ios_sdk='iphoneos')
    manifest['files'] = dict(sorted(files.items()))
    manifest_bytes = (json.dumps(manifest, indent=2) + '\n').encode()
    shutil.rmtree(lists, ignore_errors=True); lists.mkdir(parents=True)
    script = [sys.executable, '-I', '-X', 'utf8', TOTK/'scripts/shader_list.py']
    run([*script, 'export', SHADER_LIST, lists/'pso_list.tsv', lists/'pso_title.tsv'], lists/'export.log')
    aliases = seed.with_name(seed.name + '.aliases.tsv')   # listed variants the seed carries under another name
    if aliases.is_file():
        run([*script, 'rename', aliases, lists/'pso_title.tsv', lists/'pso_list.tsv'], lists/'rename.log')
    pso = {n: (lists/n).read_bytes() for n in ('pso_list.tsv', 'pso_title.tsv')}
    fingerprint = hashlib.sha256(manifest_bytes + SHADER_MAP + pso['pso_list.tsv'] + pso['pso_title.tsv']).hexdigest()
    stamp = dest/'fingerprint.txt'
    if stamp.is_file() and stamp.read_text(encoding='utf-8').strip() == fingerprint:
        return fingerprint
    partial = dest.with_name(dest.name + '.partial')
    shutil.rmtree(partial, ignore_errors=True); partial.mkdir(parents=True)
    for p in [*(seed/n for n in names), *libs]:
        link_or_copy(p, partial/p.name)
    (partial/'seed-manifest.json').write_bytes(manifest_bytes)
    (partial/'shader_map.tsv').write_bytes(SHADER_MAP)
    for n, data in pso.items():
        (partial/n).write_bytes(data)
    (partial/'fingerprint.txt').write_bytes((fingerprint + '\n').encode())   # last: names a complete folder
    shutil.rmtree(dest, ignore_errors=True); partial.rename(dest)
    return fingerprint


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='command', required=True)
    t = sub.add_parser('tools', help='build SPIRV-Cross and the translator into <work>/tools/bin')
    t.add_argument('--dotnet', default='dotnet', help='the .NET 10 SDK\'s dotnet (default: on PATH)')
    s = sub.add_parser('seed', help='prepare the seed into <work>/seed')
    s.add_argument('--romfs', type=Path, required=True, help='the folder with romfs.bin and index.json')
    s.add_argument('--modules', type=Path, help='rewritten/<version>: the game modules the shared list locates shaders in')
    s.add_argument('--version', required=True)
    s.add_argument('--extra-list', type=Path, action='append', default=[],
                   help='a device\'s shader-list-contribution.txt: its V rows join this seed; may be given again')
    for x in (t, s):
        x.add_argument('--work', type=Path, required=True, help='the folder that holds tools/ and seed/')
    a = p.parse_args()
    {'tools': cmd_tools, 'seed': cmd_seed}[a.command](a)


if __name__ == '__main__':
    try:
        main()
    except (SeedError, OSError, subprocess.CalledProcessError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)
