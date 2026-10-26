#!/usr/bin/env python3
"""Package the iPhone/iPad app of Tears of the Kingdom 1.4.3 on a machine without Xcode (Windows; also Linux and macOS):
the runtime the ios-runtime workflow built, the game's code written into it, the game data of a work folder, then an IPA
signed with zsign. build_ipa.py and install_device.py do this on a Mac with Xcode.

  python package_ipa_windows.py <TOTK-runtime.zip | TOTK.app> --tree <work>/totk --out <dir>/<name>.ipa
         --p12 <certificate.p12> --p12-password-file <file> --profile <profile.mobileprovision> [--zsign <zsign.exe>]
         [--seed <seed folder> [--metallibs <folder>]] [--source-commit <commit>] [--game-data documents | app]
         [--unsigned-only]

The runtime: the ios-runtime workflow's artifact TOTK-runtime.zip, or the TOTK.app in it (build_ipa.py --runtime-only
--embed-layout ios/ci/embed-layout-v143.json). Its nine module sections (x0, W and x1 of main, subsdk0 and sdk, as
gen_embed.py names them) are zero-filled to the sizes of the layout, or already hold the modules. Each is filled from
the work folder's <tree>/build/from-ipa/embed/<module>.<part>.bin (recover_ipa.py) at its file offset; every section
file must match the layout's size and SHA-256, and so must the executable's own ios_embed table (loader.c checks the
sections against it at start).

The app: the runtime's own files and Info.plist (xcodegen made it from ios/project.yml), then the keys of the app the
device has (<old app>/Info.plist) that the runtime's lacks, Xcode's build keys (DT*, BuildMachineOSBuild) excepted, so
nothing a player's install relied on goes missing (the builder's TOTK* keys, of which TOTKSourceCommit and TOTKBuildDate
are set to this build's: --source-commit, the commit the workflow run built, as the artifact does not name it; this
checkout's HEAD by default, and today). The bundle identifier comes from the profile (or --bundle-id); the version and build number
stay those of the old app (1.4.3, 2610.22.1) unless given. The old app's icon (Assets.car, AppIcon*.png and its
CFBundleIcons keys) goes in when the runtime has none, its default.metallib when the runtime lacks one.

GameData (ios/Sources/main.m): game-data, romfs (runtime-index.bin, index.json, merge.log), romfs-patches,
romfs-patches-out and shared-fonts from the tree, each file checked against <tree>/recover-manifest.json when there is
one. --game-data documents (the default) leaves romfs.bin and the shader seed out: push_device_windows.py copies them
into the app's Documents/GameData once. --game-data app puts both into the app (a 17 GB IPA; large files are hard-linked
into the staging folder, not copied); zsign cannot sign an app holding the image (sign_ipa_windows.large_files), so with
it only <name>-unsigned.ipa is written (--unsigned-only), for a signing tool on a Mac.

--seed <folder>: the shader seed scripts/prepare_shader_seed.py made (seed_windows.py seed: <work>/seed, its
<folder>.aliases.tsv beside it). It must be of the runtime's translation chain (the rt-<chain> string in the
executable). Its device form (seed_windows.device_seed) goes beside the IPA as <name>-shader-seed (documents) or into
GameData/shader-seed (app); --metallibs adds Metal libraries compiled from this seed elsewhere, none otherwise.

Outputs beside --out: <name>.ipa (signed; verified by sign_ipa_windows.verify), <name>-unsigned.ipa (ad-hoc signed with
ios/Sources/TOTK.entitlements, like build_ipa.py's, for other signing tools; with the image in the app not signed at all),
<name>-shader-seed (with --seed, documents), <name>-package.json (inputs, outputs and their SHA-256). The staging folder
.<name>.staging beside them is removed unless --keep-staging."""
import argparse, datetime, hashlib, json, plistlib, re, shutil, subprocess, sys, zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
IOS = TOOLS.parent
GAME = IOS.parent
REPO = GAME.parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(REPO))
import build_app                    # noqa: E402  sha256 and say, as the Mac build prints them
import macho                        # noqa: E402  the executable's sections and ios_embed table
import seed_windows                 # noqa: E402  the seed's device form
import sign_ipa_windows as signing  # noqa: E402

VERSION = 'v143'
LAYOUT = IOS/f'ci/embed-layout-{VERSION}.json'
NAMES = ('main', 'subsdk0', 'sdk')
XCODE_BUILD_KEYS = {'BuildMachineOSBuild', 'DTCompiler', 'DTPlatformBuild', 'DTPlatformName', 'DTPlatformVersion',
                    'DTSDKBuild', 'DTSDKName', 'DTXcode', 'DTXcodeBuild'}   # what one Xcode build says about itself
ICON_KEYS = ('CFBundleIcons', 'CFBundleIcons~ipad')
ROMFS_IMAGE = re.compile(r'^romfs\.bin(\.\d{3})?$')
say = build_app.say


class PackageError(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise PackageError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def runtime_chain(exe):
    """The shader translation chain the runtime was built with: main.m names its cache folder "rt-" DMSH_CHAIN."""
    chains = {c for c in re.findall(rb'\0rt-([\x21-\x7e]{4,80})\0', exe) if b'\0' + c + b'\0' in exe}
    require(len(chains) == 1, f'cannot tell the runtime\'s shader chain (rt-<chain> strings: {sorted(chains)})')
    return chains.pop().decode()


def fill_sections(exe, sections_dir, layout):
    """Write the nine module sections into the executable (a bytearray) at their file offsets. Each section file must
    match the layout, and so must the executable's ios_embed table; a section that holds anything but zeros or its
    module already is an error. Returns what was done per section."""
    pins = {(m['name'], p): (m[p]['size'], m[p]['sha256']) for m in layout['modules'] for p in ('x0', 'w', 'x1')}
    require(sorted({n for n, _ in pins}) == sorted(NAMES), f'{LAYOUT.name} names {sorted({n for n, _ in pins})}')
    try:
        image = macho.MachO(bytes(exe))
        embed = macho.embed_hashes(image, NAMES)
    except macho.MachOError as e:
        raise PackageError(f'the runtime\'s ios_embed table cannot be read: {e}') from None
    done = []
    for (name, part), (size, sha) in pins.items():
        require(embed[name][part] == sha, f'{name} {part}: the runtime was built for {embed[name][part][:16]}..., '
                f'the layout pins {sha[:16]}... (another embed layout)')
        data = (sections_dir/f'{name}.{part}.bin').read_bytes()
        require(len(data) == size and digest(data) == sha,
                f'{sections_dir/f"{name}.{part}.bin"}: not the section the layout pins (run recover_ipa.py again)')
        seg, sect = macho.module_sections(name)[part]
        require((seg, sect) in image.sections, f'the runtime has no {seg},{sect} section')
        at, have = image.sections[(seg, sect)]
        require(at and have == size, f'{seg},{sect}: {have:#x} bytes at file offset {at:#x}, the layout needs {size:#x} in the file')
        current = exe[at:at + size]
        if current == data:
            done.append((name, part, 'already there'))
        else:
            require(current.count(0) == size, f'{seg},{sect} holds other bytes than zeros or this module')
            exe[at:at + size] = data
            done.append((name, part, 'written'))
        require(digest(exe[at:at + size]) == sha, f'{seg},{sect}: SHA-256 after writing')
    return done


def tree_manifest(tree):
    """{path: record} of <tree>/recover-manifest.json, {} for a tree without one (a Mac work folder)."""
    path = tree/'recover-manifest.json'
    return {f['path']: f for f in json.loads(path.read_text())['files']} if path.is_file() else {}


def checked(tree, manifest, rel, full_hash=True):
    """<tree>/rel after checking it against the manifest record (size, and SHA-256 or modification time)."""
    path = tree/rel
    require(path.is_file(), f'missing in the work folder: {path}')
    record = manifest.get(rel)
    if record:
        require(path.stat().st_size == record['size'], f'{path}: {path.stat().st_size} bytes, the manifest says {record["size"]}')
        if full_hash or 'mtime_ns' not in record:
            require(build_app.sha256(path) == record['sha256'], f'{path}: SHA-256 differs from recover-manifest.json')
        else:
            require(path.stat().st_mtime_ns == record['mtime_ns'], f'{path}: changed since recover_ipa.py checked it')
    return path


def game_data(tree, res, mode):
    """The tree's game data into the app's GameData folder res (build_ipa.py lines after 'res=dest/GameData')."""
    manifest = tree_manifest(tree)
    folders = [(f'build/game-data/{VERSION}', 'game-data'), (f'extracted/{VERSION}/romfs', 'romfs'),
               (f'extracted/{VERSION}/romfs-patches', 'romfs-patches'), (f'extracted/{VERSION}/romfs-patches-out', 'romfs-patches-out'),
               ('extracted/firmware/shared-fonts', 'shared-fonts')]
    count = 0
    for src, dst in folders:
        require((tree/src).is_dir(), f'missing in the work folder: {tree/src}')
        for path in sorted(p for p in (tree/src).rglob('*') if p.is_file()):
            rel = path.relative_to(tree).as_posix()
            if dst == 'romfs' and ROMFS_IMAGE.match(path.name):
                if mode != 'app' or path.name != 'romfs.bin':
                    continue
                seed_windows.link_or_copy(checked(tree, manifest, rel, full_hash=False), res/dst/path.name); count += 1; continue
            target = res/dst/path.relative_to(tree/src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(checked(tree, manifest, rel), target); count += 1
    require((res/'game-data/runtime-tables.bin').is_file(), f'missing game data: {tree}/build/game-data/{VERSION}/runtime-tables.bin')
    if mode == 'app':
        require((res/'romfs/romfs.bin').is_file(), f'--game-data app needs {tree}/extracted/{VERSION}/romfs/romfs.bin')
    return count


def unpack_runtime(runtime, app):
    """The runtime (TOTK-runtime.zip, or a TOTK.app folder) into the staging app folder; returns its Info.plist."""
    if runtime.is_dir():
        require((runtime/'Info.plist').is_file(), f'{runtime}: not an app folder (no Info.plist)')
        shutil.copytree(runtime, app)
    else:
        require(zipfile.is_zipfile(runtime), f'{runtime}: neither TOTK-runtime.zip nor a TOTK.app folder')
        with zipfile.ZipFile(runtime) as z:
            plists = [n for n in z.namelist() if re.fullmatch(r'(?:Payload/)?[^/]+\.app/Info\.plist', n)]
            require(len(plists) == 1, f'{runtime}: not one <name>.app in the archive')
            prefix = plists[0][:-len('Info.plist')]
            for n in z.namelist():
                rel = n[len(prefix):]
                if not n.startswith(prefix) or not rel or n.endswith('/'):
                    continue
                require('..' not in rel.split('/') and not rel.startswith('/'), f'{runtime}: unsafe path {n}')
                (app/rel).parent.mkdir(parents=True, exist_ok=True); (app/rel).write_bytes(z.read(n))
    shutil.rmtree(app/'_CodeSignature', ignore_errors=True)   # the runtime's ad-hoc signature no longer fits
    (app/'embedded.mobileprovision').unlink(missing_ok=True)
    return plistlib.loads((app/'Info.plist').read_bytes())


def app_info(runtime_info, old_info, identity, with_icons, build):
    """The app's Info.plist: identity > the runtime's own > the old app's keys (but Xcode's build keys and icons)."""
    info = dict(runtime_info)
    for key, value in old_info.items():
        if key not in info and key not in XCODE_BUILD_KEYS and key not in ICON_KEYS:
            info[key] = value
    if with_icons:
        info.update({k: old_info[k] for k in ICON_KEYS if k in old_info})
    info.update(identity)
    for key, value in (('TOTKSourceCommit', build['source_commit']), ('TOTKBuildDate', build['date'])):
        if key in info:
            info[key] = value
    return info


def write_ipa(root, out, executable):
    """Payload/ of root as an IPA without zsign, for an app holding a file zsign cannot seal: stored members (zip64 for the
    17 GB image) with the Unix modes of a Mac build."""
    out.unlink(missing_ok=True)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_STORED, allowZip64=True) as z:
        for path in sorted(p for p in (root/'Payload').rglob('*') if p.is_file()):
            info = zipfile.ZipInfo.from_file(path, path.relative_to(root).as_posix())
            info.create_system, info.external_attr = 3, (0o100755 if path == executable else 0o100644) << 16
            with open(path, 'rb') as src, z.open(info, 'w', force_zip64=info.file_size >= signing.ZSIGN_FILE_LIMIT) as dst:
                shutil.copyfileobj(src, dst, 8 << 20)


def git_commit():
    try:
        r = subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else 'unknown'
    except OSError:
        return 'unknown'


def arguments():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('runtime', type=Path, help='the ios-runtime workflow\'s TOTK-runtime.zip, or the TOTK.app folder in it')
    p.add_argument('--tree', type=Path, required=True, help='the work folder of the game (recover_ipa.py --out)')
    p.add_argument('--out', type=Path, required=True, help='the signed IPA to write (<name>.ipa)')
    p.add_argument('--game-data', choices=('documents', 'app'), default='documents',
                   help='documents (default): romfs.bin and the seed stay out of the app; app: both go into it')
    p.add_argument('--seed', type=Path, help='the shader seed folder (prepare_shader_seed.py --output, seed_windows.py seed)')
    p.add_argument('--metallibs', type=Path, help='with --seed: a folder of <variant>_b.metallib compiled from this seed '
                   '(compile_seed.py on a Mac); without it the device compiles every shader from its MSL')
    p.add_argument('--old-app', type=Path, help='the old app\'s files: Info.plist, Assets.car, AppIcon*.png, default.metallib '
                   '(default: <tree>/build/from-ipa/app)')
    p.add_argument('--bundle-id', help='default: the profile\'s application identifier')
    p.add_argument('--app-name', help='default: the old app\'s CFBundleDisplayName')
    p.add_argument('--short-version', help='CFBundleShortVersionString (default: the old app\'s)')
    p.add_argument('--bundle-version', help='CFBundleVersion (default: the old app\'s)')
    p.add_argument('--source-commit', help='the commit the runtime was built from (default: this checkout\'s HEAD)')
    p.add_argument('--layout', type=Path, default=LAYOUT, help=f'the section layout (default: ios/ci/{LAYOUT.name})')
    p.add_argument('--unsigned-only', action='store_true', help='write <name>-unsigned.ipa only')
    p.add_argument('--keep-staging', action='store_true', help='keep the staging folder (<dir>/.<name>.staging)')
    signing.add_identity_arguments(p)
    return p.parse_args()


def identity_of(a, old_info):
    """The app's identifier, name and versions, and the signing identity (None for --unsigned-only), all checked before
    the long steps."""
    bundle_id, ident = a.bundle_id, None
    if not a.unsigned_only:
        require(a.p12 and a.profile, 'give --p12 and --profile (or --unsigned-only)')
        granted = signing.read_profile(a.profile)[1].get('Entitlements', {}).get('application-identifier', '')
        bundle_id = bundle_id or (granted.split('.', 1)[1] if '.' in granted and not granted.endswith('*') else None)
    require(bundle_id, '--bundle-id is needed (the profile does not name one)')
    if not a.unsigned_only:
        ident = dict(zip(('openssl', 'der', 'password', 'profile_raw', 'profile', 'entitlements'), signing.identity(a, bundle_id)))
    short, build = a.short_version or old_info.get('CFBundleShortVersionString'), a.bundle_version or old_info.get('CFBundleVersion')
    require(short and build, 'no old app to keep the version from: give --short-version and --bundle-version')
    name = a.app_name or old_info.get('CFBundleDisplayName') or 'Tears of the Kingdom'
    return {'CFBundleIdentifier': bundle_id, 'CFBundleDisplayName': name, 'CFBundleName': name,
            'CFBundleShortVersionString': short, 'CFBundleVersion': build}, ident


def assemble(a, runtime, tree, app, old_app, old_info, identity):
    """The app folder from the runtime: sections written, its files, Info.plist. Returns what the report records."""
    runtime_info = unpack_runtime(runtime, app)
    exe_name = runtime_info['CFBundleExecutable']
    require(not (app/'GameData').exists(), f'{runtime} carries GameData already: give the runtime alone')
    exe = bytearray((app/exe_name).read_bytes())
    say('2/6 module sections into the executable')
    filled = fill_sections(exe, tree/'build/from-ipa/embed', json.loads(a.layout.read_text()))
    (app/exe_name).write_bytes(exe)
    for name, part, state in filled:
        print(f'  {name} {part}: {state}')
    say('3/6 app files')
    with_icons = not (app/'Assets.car').exists() and (old_app/'Assets.car').is_file()
    if with_icons:
        for icon in [old_app/'Assets.car', *sorted(old_app.glob('AppIcon*.png'))]:
            shutil.copyfile(icon, app/icon.name)
    if not (app/'default.metallib').exists() and (old_app/'default.metallib').is_file():
        shutil.copyfile(old_app/'default.metallib', app/'default.metallib')   # Xcode's library of the .metal sources
    build = {'source_commit': a.source_commit or git_commit(), 'date': datetime.date.today().isoformat()}
    info = app_info(runtime_info, old_info, identity, with_icons, build)
    (app/'Info.plist').write_bytes(plistlib.dumps(info, fmt=plistlib.FMT_BINARY))
    return dict(runtime=str(runtime), executable=exe_name, executable_sha256=digest(exe),
                sections={f'{n}.{p}': s for n, p, s in filled}, shader_chain=runtime_chain(exe), source_commit=build['source_commit'],
                info_from_old_app=sorted(k for k in info if k not in runtime_info and k not in identity),
                info={k: info.get(k) for k in ('CFBundleIdentifier', 'CFBundleShortVersionString', 'CFBundleVersion',
                                               'CFBundleDisplayName', 'MinimumOSVersion', 'DTSDKName')})


def main():
    a = arguments()
    tree, out, runtime = a.tree.resolve(), a.out.resolve(), a.runtime.resolve()
    require(out.suffix.lower() == '.ipa', '--out must end in .ipa')
    require(a.game_data == 'documents' or a.seed, '--game-data app needs --seed: the app has no shaders otherwise')
    require(a.seed or not a.metallibs, '--metallibs goes with --seed')
    old_app = (a.old_app or tree/'build/from-ipa/app').resolve()
    old_info = plistlib.loads((old_app/'Info.plist').read_bytes()) if (old_app/'Info.plist').is_file() else {}
    zsign = signing.tool('zsign', a.zsign, 'TOTK_ZSIGN')
    image = tree/f'extracted/{VERSION}/romfs/romfs.bin'
    if a.game_data == 'app' and not a.unsigned_only and image.is_file() and image.stat().st_size >= signing.ZSIGN_FILE_LIMIT:
        raise PackageError(f'--game-data app: zsign cannot sign the {image.stat().st_size / 2**30:.0f} GiB image '
                           '(sign_ipa_windows.large_files); use --game-data documents (the default), or --unsigned-only '
                           'for an IPA to sign on a Mac')
    identity, ident = identity_of(a, old_info)
    stem = out.stem; staging = out.parent/f'.{stem}.staging'
    shutil.rmtree(staging, ignore_errors=True)
    app = staging/'Payload/TOTK.app'
    say(f'1/6 runtime: {runtime}')
    report = dict(tool='games/totk/ios/tools/package_ipa_windows.py', made=datetime.datetime.now().isoformat(timespec='seconds'),
                  **assemble(a, runtime, tree, app, old_app, old_info, identity), tree=str(tree), game_data=a.game_data)
    say(f'4/6 game data ({a.game_data})')
    report['game_data_files'] = game_data(tree, app/'GameData', a.game_data)
    seed_out = None
    if a.seed:
        seed_out = app/'GameData/shader-seed' if a.game_data == 'app' else out.with_name(stem + '-shader-seed')
        report['seed_fingerprint'] = seed_windows.device_seed(a.seed.resolve(), seed_out, report['shader_chain'],
                                                              staging/'seed-lists', a.metallibs and a.metallibs.resolve())
        shutil.rmtree(staging/'seed-lists', ignore_errors=True)
        report['seed'] = str(seed_out)
        print(f'  shader seed: {seed_out} ({report["seed_fingerprint"][:12]})')
    level = 0 if a.game_data == 'app' else 1   # the 17 GB image is stored, not compressed
    unsigned = out.with_name(stem + '-unsigned.ipa')
    if signing.large_files(staging):   # the image in the app: written without zsign, and not signed
        say(f'5/6 {unsigned.name} (not signed: zsign cannot seal the image)')
        write_ipa(staging, unsigned, app/report['executable'])
        check = 'not signed; the executable keeps the signature it was linked with, which the written sections void'
    else:
        say(f'5/6 {unsigned.name} (ad-hoc signed with TOTK.entitlements)')
        signing.sign_adhoc(zsign, staging, unsigned, signing.APP_ENTITLEMENTS, level)
        check = signing.verify(unsigned)
    report['unsigned'] = dict(path=str(unsigned), sha256=build_app.sha256(unsigned), size=unsigned.stat().st_size, check=check)
    if ident:
        say(f'6/6 {out.name} (zsign)')
        signing.sign(zsign, ident['openssl'], staging, out, a.p12, ident['password'], a.profile, ident['entitlements'], level)
        report['signed'] = dict(path=str(out), sha256=build_app.sha256(out), size=out.stat().st_size,
                                check=signing.verify(out, ident['profile_raw'], ident['profile'], ident['der']))
    out.with_name(stem + '-package.json').write_text(json.dumps(report, indent=2, default=str) + '\n', encoding='utf-8', newline='\n')
    if not a.keep_staging:
        shutil.rmtree(staging, ignore_errors=True)
    say(f'ready: {out if ident else unsigned}' + (f'; shaders beside it: {seed_out}' if seed_out and a.game_data == 'documents' else ''))


if __name__ == '__main__':
    try:
        main()
    except (PackageError, signing.SignError, seed_windows.SeedError, OSError, KeyError, zipfile.BadZipFile,
            plistlib.InvalidFileException) as e:
        print(f'ERROR: {e}', file=sys.stderr); sys.exit(1)
