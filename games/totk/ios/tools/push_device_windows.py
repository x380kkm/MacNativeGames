#!/usr/bin/env python3
"""Install the iPhone/iPad app and copy its game data to the device from Windows (also Linux and macOS) with
pymobiledevice3, as install_device.py does on a Mac with Xcode's devicectl. The device is connected by cable (on Windows
with iTunes or Apple Devices installed, for its usbmuxd) and unlocked; the app is signed already (package_ipa_windows.py).

  python push_device_windows.py deploy <name>.ipa --romfs <work>/totk/extracted/v143/romfs/romfs.bin --backup-to <dir>
         [--seed <name>-shader-seed] [--no-backup] [--mod <mod folder> [--version v143] [--slot strong]]
  python push_device_windows.py install <name>.ipa
  python push_device_windows.py romfs <romfs.bin> --bundle-id <id>        the 17 GB image into Documents/GameData
  python push_device_windows.py seed <name>-shader-seed --bundle-id <id>  the startup shaders into Documents/GameData
  python push_device_windows.py push-mod <mod folder> --bundle-id <id> [--version v143] [--slot strong]   a RomFS mod into Documents/mods
  python push_device_windows.py push-slots <folder> --bundle-id <id> [--version v143]   every slot folder make_gameplay_tuning.py --slots built
  python push_device_windows.py remove-mod --bundle-id <id> [--version v143] [--slot strong]
  python push_device_windows.py backup-save --to <dir> --bundle-id <id>   Documents/save, with account.uid
  python push_device_windows.py restore-save <backup folder> --bundle-id <id> [--safety-to <dir>] [--other-app]
  python push_device_windows.py status --bundle-id <id>
  python push_device_windows.py check                                    offline: pymobiledevice3 and the API used here
Every command but check also takes --udid <device> (required with more than one attached) and --simulate <folder>
(a local folder standing for the app's container, to rehearse a run without a device); --bundle-id defaults to the
IPA's for deploy and install.

deploy backs up the saves of an installed app first, installs over it (same bundle identifier and team: iOS keeps its
Documents, so the saves and the game data stay), copies the image given with --romfs when the device lacks it, and the
shaders beside the IPA (<name>-shader-seed, package_ipa_windows.py --seed) when their fingerprint is new. The saves are
Documents/save: account.uid (16 bytes, the local account) names the folder save/save/<hi><lo> that holds them
(runtime/account.c, fs_host.c); a backup (<dir>/<bundle id>-save-<time>/save with backup-manifest.json) keeps both, and
a restore first backs up what the device has (beside the backup, or into --safety-to). Close the game before a restore.

The files on the device follow ios/Sources/main.m and install_device.py: the image as romfs.bin.000, .001, ... of 1 GiB
(runtime/romfs.c: equal parts, the last one shorter), with romfs.sha256 saying "copying <sha256>" until every part is
there and the image's SHA-256 (index.json romfs_sha256) last; a copy that stopped goes on from the parts at their full
size. The shaders as one stream, <folder>.pack.000, ... (main.m seed_unpack, install_device.py write_pack), after
shader-seed.txt says "stale" and before it says "<folder>\\n<fingerprint>"; the app unpacks it on its next start. A
marker is written to a temporary name and renamed, so the app never reads half of one.

A player's RomFS mod (scripts/make_button_icons.py, make_mod_manifest.py) goes into Documents/mods/<version> (v143 for
1.4.3, runtime/game_version.h TOTK_GAME_DIR), which main.m hands to the runtime when it holds a manifest.tsv. push-mod
checks each line of the folder's manifest.tsv and each file it lists (size and SHA-256) as runtime/romfs.c does at start,
and copies only those files. The device's manifest.tsv goes first and comes back last, so the app never loads a mod
whose files are still being copied; until then manifest.tsv.copying holds the new manifest. A copy that stopped goes on
from the files at their full size; any other copy first empties the folder, so a file at its full size is one this
copy wrote. remove-mod removes the folder, manifest.tsv first. --slot names the folder Documents/mods/<version>-<slot>
instead, which main.m prefers when the Settings pane's mod slot row (TOTK_MOD_SLOT) names that slot. push-slots checks the
folders <version>-<slot> of every slot in MOD_SLOTS below the folder it is given, then copies them one after the other as
push-mod does, so running it again goes on where it stopped.

The device side is app_container.py (pymobiledevice3's house_arrest, AFC and installation_proxy). pymobiledevice3 (a pipx
or uv tool) has its own Python: the commands that reach the device start this script again in that interpreter
($TOTK_PMD3_PYTHON, or the one `uv tool dir` or pipx keeps it in)."""
import argparse, hashlib, json, re, subprocess, sys, tempfile, time, zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import app_container     # noqa: E402  the app's container: the device, or a folder standing for it
import install_device    # noqa: E402  write_pack and PART: the shader pack and the part size the app reads
from app_container import ipa_info   # noqa: E402

GAMEDATA = 'Documents/GameData'
SAVE = 'Documents/save'
MODS = 'Documents/mods'
MOD_VERSIONS = ('v0', 'v112', 'v121', 'v143', 'botw160', 'botw190')   # TOTK_GAME_DIR of each build (runtime/game_version.h)
MOD_VERSION = 'v143'   # the version package_ipa_windows.py packages
MOD_SLOTS = ('off', 'moderate', 'strong', 'max')   # the values of the Settings pane's TOTK_MOD_SLOT row (Root.plist)
COPYING = 'manifest.tsv.copying'   # the manifest of a mod copy that has not finished; the app reads manifest.tsv only
# A manifest line as runtime/romfs.c overlay_load reads it: path, size, SHA-256, the original's SHA-256 or "-" for an added file.
MANIFEST_LINE = re.compile(r'([^\t\n]{1,4095})\t(\d+)\t([0-9a-f]{64})\t([0-9a-f]{64}|-)(?![0-9a-f-])')
PART = install_device.PART


class PushError(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise PushError(message)


def bar(total, what):
    """A progress callback showing done/total on one line, at most twice a second, which it ends when all is done."""
    start, shown = time.time(), [0.0]
    def show(done):
        now = time.time()
        if done < total and now - shown[0] < 0.5:
            return
        shown[0] = now
        rate = done / max(now - start, 1e-3) / 2**20
        print(f'\r  {what}: {done / 2**20:.0f} of {total / 2**20:.0f} MiB, {rate:.0f} MiB/s ',
              end='\n' if done >= total else '', flush=True)
    return show


def push_romfs(box, image, log=print, progress=None):
    """The RomFS image into Documents/GameData in 1 GiB parts (install_device.py push_game_data). Returns what was done."""
    index = json.loads((image.parent/'index.json').read_text())
    sha, size = index['romfs_sha256'], image.stat().st_size
    require(size == index['romfs_size'], f'{image}: {size} bytes, its index.json says {index["romfs_size"]}')
    want = {f'romfs.bin.{i:03d}': min(PART, size - i * PART) for i in range((size + PART - 1) // PART)}
    box.makedirs(GAMEDATA)
    have = box.listdir(GAMEDATA) or {}
    marker = (box.read(f'{GAMEDATA}/romfs.sha256') or b'').decode(errors='replace').strip()
    complete = all(have.get(n, (None,))[0] == s for n, s in want.items())
    copying = f'copying {sha}'
    if 'romfs.bin' in have:   # romfs.c opens a whole image before any parts
        require(marker == sha and have['romfs.bin'][0] == size, 'Documents/GameData holds a romfs.bin of another image: '
                'remove it in the Files app (the runtime reads it before the parts), then run this again')
        log('game data: the device already has this image (one file)'); return 'present'
    if marker == sha and complete:
        log('game data: the device already has this image'); return 'present'
    stale = sorted(n for n in have if n.startswith('romfs.bin.') and n not in want)   # parts beyond this image's
    if complete and marker in ('', copying) and not stale:
        box.write(f'{GAMEDATA}/romfs.sha256', (sha + '\n').encode())
        log('game data: every part is on the device; only its marker was written again'); return 'marker'
    resume = marker == copying
    log(f'game data: copying {size / 2**30:.1f} GiB in {len(want)} parts (once; later installs keep it)'
        + (', going on from the parts already there' if resume else ''))
    if not resume:
        box.write(f'{GAMEDATA}/romfs.sha256', (copying + '\n').encode())   # until every part is there
    for name in stale:
        box.remove(f'{GAMEDATA}/{name}')
    for i, (name, n) in enumerate(want.items()):
        if resume and have.get(name, (None,))[0] == n:
            log(f'  part {i + 1}/{len(want)}: already there'); continue
        box.upload(f'{GAMEDATA}/{name}', image, i * PART, n, progress and progress(n, f'part {i + 1}/{len(want)}'))
    now = box.listdir(GAMEDATA) or {}
    short = [n for n, s in want.items() if now.get(n, (None,))[0] != s]
    require(not short, f'parts with the wrong size on the device after copying: {short}; run this again')
    box.write(f'{GAMEDATA}/romfs.sha256', (sha + '\n').encode())
    return 'copied'


def push_seed(box, seed, log=print, progress=None):
    """The device seed (package_ipa_windows.py --seed, build_ipa.py --image-outside) into Documents/GameData as one pack
    (install_device.py push_seed). Returns what was done."""
    fp = (seed/'fingerprint.txt').read_text().strip()
    require(len(fp) == 64, f'{seed}/fingerprint.txt is not a SHA-256')
    box.makedirs(GAMEDATA)
    lines = (box.read(f'{GAMEDATA}/shader-seed.txt') or b'').decode(errors='replace').split('\n')
    have = box.listdir(GAMEDATA) or {}
    if len(lines) >= 2 and lines[1].strip() == fp and (lines[0] in have or f'{lines[0]}.pack.000' in have):
        log('shaders: the device already has these'); return 'present'
    folder = f'shader-seed-{fp[:12]}-{int(time.time())}'
    names = sorted(p.name for p in seed.iterdir() if p.is_file())
    total = sum((seed/n).stat().st_size for n in names)
    log(f'shaders: copying {len(names)} files, {total / 2**30:.1f} GiB, as one pack (once per shader list)')
    box.write(f'{GAMEDATA}/shader-seed.txt', b'stale\n')   # until every part is there
    def push(part):
        box.upload(f'{GAMEDATA}/{part.name}', part, 0, None, progress and progress(part.stat().st_size, part.name))
        part.unlink()
    with tempfile.TemporaryDirectory(dir=seed.parent) as d:   # 1 GiB parts beside the seed, not on the system disk
        install_device.write_pack(seed, names, Path(d), folder, PART, push)
    box.write(f'{GAMEDATA}/shader-seed.txt', f'{folder}\n{fp}\n'.encode())
    return 'copied'


def remote_files(box, rel, prefix=''):
    """[(path below rel, size)] of every file under rel on the device, folders walked."""
    out = []
    for name, (size, folder) in sorted((box.listdir(rel) or {}).items()):
        if folder:
            out += remote_files(box, f'{rel}/{name}', f'{prefix}{name}/')
        else:
            out.append((prefix + name, size))
    return out


def remove_below(box, rel):
    """Every file and folder below rel on the device, each folder after what it held; rel itself stays."""
    for name, (_, folder) in sorted((box.listdir(rel) or {}).items()):
        if folder:
            remove_below(box, f'{rel}/{name}')
        box.remove(f'{rel}/{name}')


def romfs_path_ok(path):
    """runtime/romfs_path.h romfs_path_valid_relative: relative, parts between '/', none empty, '.' or '..', no '\\'."""
    return bool(path) and not path.startswith('/') and '\\' not in path and all(p not in ('', '.', '..') for p in path.split('/'))


def mod_files(folder):
    """The files a mod folder's manifest.tsv lists, [(RomFS path, size)], each checked as runtime/romfs.c checks it at
    start (a line it reads, a RomFS path, the file's size and SHA-256), and the manifest's bytes. The originals' SHA-256
    are checked against the device's RomFS by the game itself."""
    manifest = folder/'manifest.tsv'
    require(manifest.is_file(), f'{manifest} not found: make_button_icons.py or make_mod_manifest.py writes it')
    text = manifest.read_bytes()
    files = []
    for n, line in enumerate(text.decode('utf-8').split('\n'), 1):
        if not line or line.startswith('#'):   # romfs.c skips comment and empty lines
            continue
        m = MANIFEST_LINE.match(line)
        require(m, f'{manifest} line {n}: not a line runtime/romfs.c reads (path, size, SHA-256, original SHA-256), '
                'so the game would stop at start')
        path, size, sha = m.group(1), int(m.group(2)), m.group(3)
        require(romfs_path_ok(path), f'{manifest} line {n}: {path!r} is not a RomFS path')
        file = folder/path
        require(file.is_file() and file.stat().st_size == size, f'{file}: missing, or not the {size} bytes manifest.tsv says')
        with file.open('rb') as f:
            require(hashlib.file_digest(f, 'sha256').hexdigest() == sha, f'{file}: not the SHA-256 manifest.tsv says')
        files.append((path, size))
    require(files, f'{manifest} lists no file')
    paths = [p for p, _ in files]
    twice = next((p for p in paths if paths.count(p) > 1), None)
    require(twice is None, f'{manifest} lists {twice} twice, so the game would stop at start')
    return files, text


def mod_target(version, slot=None):
    """The folder below Documents/mods of a game version, or of one slot of it (ios/Sources/main.m)."""
    return f'{version}-{slot}' if slot else version


def push_mod(box, folder, target=MOD_VERSION, log=print, progress=None):
    """A mod folder's files (mod_files) into Documents/mods/<target>, manifest.tsv last. Returns what was done."""
    files, text = mod_files(folder)
    rel = f'{MODS}/{target}'
    box.makedirs(rel)
    have = dict(remote_files(box, rel))
    if box.read(f'{rel}/manifest.tsv') == text and all(have.get(p) == s for p, s in files):
        log(f'mod: the device already has this one in {rel}'); return 'present'
    resume = box.read(f'{rel}/{COPYING}') == text
    if 'manifest.tsv' in have:
        box.remove(f'{rel}/manifest.tsv')   # the app loads no mod from here until the copy is complete
    if not resume:   # an earlier mod's files go first: a file at its full size is then one this copy wrote
        remove_below(box, rel)
        require(box.listdir(rel) == {}, f'{rel} on the device could not be emptied; remove it in the Files app and run this again')
        box.write(f'{rel}/{COPYING}', text)
    total = sum(s for _, s in files)
    log(f'mod: copying {len(files)} files, {total / 2**20:.1f} MiB, into {rel}' + (', going on from the files already there' if resume else ''))
    show, done, shown = progress and progress(total, 'mod'), 0, [0]
    def report(n):   # one progress line over all files
        shown[0] = n; show(n)
    for path, size in files:
        if not (resume and have.get(path) == size):
            box.makedirs(f'{rel}/{path}'.rsplit('/', 1)[0])
            box.upload(f'{rel}/{path}', folder/path, 0, None, show and (lambda d, at=done: report(at + d)))
        done += size
    if show and shown[0] < total:   # the last files were there already: the line still ends
        show(total)
    now = dict(remote_files(box, rel))
    wrong = [p for p, s in files if now.get(p) != s]
    require(not wrong, f'files with the wrong size on the device after copying: {wrong[:5]}; run this again')
    box.write(f'{rel}/manifest.tsv', text)   # the next start loads the mod
    box.remove(f'{rel}/{COPYING}')
    return 'copied'


def push_slots(box, folder, version=MOD_VERSION, log=print, progress=None):
    """The folders <version>-<slot> below `folder` into Documents/mods, one slot after the other. Every folder is checked
    before the first one is copied. Returns slot -> what push_mod did."""
    mods = {slot: folder/mod_target(version, slot) for slot in MOD_SLOTS}
    missing = [mod.name for mod in mods.values() if not (mod/'manifest.tsv').is_file()]
    require(not missing, f'{folder} holds no {", ".join(missing)} with a manifest.tsv: give the folder that '
            'make_gameplay_tuning.py --slots wrote them into')
    for mod in mods.values():
        mod_files(mod)
    return {slot: push_mod(box, mod, mod_target(version, slot), log, progress) for slot, mod in mods.items()}


def remove_mod(box, target=MOD_VERSION, log=print):
    """Documents/mods/<target> off the device, manifest.tsv first. Returns what was done."""
    rel = f'{MODS}/{target}'
    have = box.listdir(rel)
    if have is None:
        log(f'mod: none on the device ({rel})'); return 'none'
    if 'manifest.tsv' in have:
        box.remove(f'{rel}/manifest.tsv')   # the app loads no mod from here even if the rest stops
    remove_below(box, rel); box.remove(rel)
    require(box.listdir(rel) is None, f'{rel} is still on the device; remove it in the Files app')
    log(f'mod: {rel} removed; the next start plays without it'); return 'removed'


def account_folder(uid):
    """save/save/<name> of an account.uid (16 bytes: lo, hi, little-endian; fs_host.c prints hi then lo)."""
    require(len(uid) == 16, f'account.uid is {len(uid)} bytes, not 16')
    lo, hi = int.from_bytes(uid[:8], 'little'), int.from_bytes(uid[8:], 'little')
    return f'{hi:016x}{lo:016x}'


def backup_save(box, root, log=print):
    """Documents/save of the device into root/<bundle id>-save-<time>/save with backup-manifest.json; returns the
    folder, None when the device has no saves."""
    files = remote_files(box, SAVE)
    if not files:
        log('saves: none on the device'); return None
    dest = Path(root)/f'{box.bundle_id}-save-{time.strftime("%Y%m%d-%H%M%S")}'
    while dest.exists():   # never into an earlier backup (a restore backs up beside the one it restores)
        dest = dest.with_name(dest.name + '-1')
    for rel, size in files:
        box.download(f'{SAVE}/{rel}', dest/'save'/rel)
        require((dest/'save'/rel).stat().st_size == size, f'{rel}: copied {(dest/"save"/rel).stat().st_size} of {size} bytes')
    uid = dest/'save/account.uid'
    require(uid.is_file(), f'the device has saves but no {SAVE}/account.uid: the backup in {dest} cannot be matched to them')
    account = account_folder(uid.read_bytes())
    manifest = dict(bundle_id=box.bundle_id, device=box.name, made=time.strftime('%Y-%m-%d %H:%M:%S'), account=account,
                    account_saves=sum(1 for rel, _ in files if rel.startswith(f'save/{account}/')),
                    files={rel: dict(size=size, sha256=hashlib.sha256((dest/'save'/rel).read_bytes()).hexdigest())
                           for rel, size in files})
    (dest/'backup-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    log(f'saves: {len(files)} files backed up to {dest} (account {account}, {manifest["account_saves"]} files in its folder)')
    return dest


def restore_save(box, backup, safety_root, other_app=False, log=print):
    """A backup_save folder into Documents/save, after backing up what the device has into safety_root. Files on the
    device the backup does not have stay."""
    manifest = json.loads((backup/'backup-manifest.json').read_text())
    for rel, f in manifest['files'].items():
        data = (backup/'save'/rel).read_bytes()
        require(len(data) == f['size'] and hashlib.sha256(data).hexdigest() == f['sha256'], f'{backup}/save/{rel}: changed since the backup')
    require(manifest['bundle_id'] == box.bundle_id or other_app,
            f'the backup is of {manifest["bundle_id"]}, not {box.bundle_id} (--other-app restores it anyway)')
    backup_save(box, safety_root, log)
    for rel in sorted(manifest['files']):
        parent = f'{SAVE}/{rel}'.rsplit('/', 1)[0]
        box.makedirs(parent); box.upload(f'{SAVE}/{rel}', backup/'save'/rel)
    now = dict(remote_files(box, SAVE))
    wrong = [rel for rel, f in manifest['files'].items() if now.get(rel) != f['size']]
    require(not wrong, f'files with the wrong size on the device after the restore: {wrong[:5]}')
    log(f'saves: {len(manifest["files"])} files restored (account {manifest["account"]})')


def status(box, log=print):
    app = box.installed()
    log(f'device: {box.name}')
    log(f'app {box.bundle_id}: ' + (f'{app.get("CFBundleShortVersionString")} ({app.get("CFBundleVersion")})' if app else 'not installed'))
    if not app:
        return
    have = box.listdir(GAMEDATA) or {}
    parts = sorted(n for n in have if n.startswith('romfs.bin'))
    marker = (box.read(f'{GAMEDATA}/romfs.sha256') or b'-').decode(errors='replace').strip()
    seed = (box.read(f'{GAMEDATA}/shader-seed.txt') or b'-').decode(errors='replace').strip().replace('\n', ' ')
    log(f'GameData: {len(parts)} image parts, {sum(have[n][0] for n in parts) / 2**30:.2f} GiB; romfs.sha256: {marker}')
    log(f'shader-seed.txt: {seed}')
    for name, (_, folder) in sorted((box.listdir(MODS) or {}).items()):
        if folder:
            lines = (box.read(f'{MODS}/{name}/manifest.tsv') or b'').decode(errors='replace').split('\n')
            listed = sum(1 for line in lines if line and not line.startswith('#'))
            log(f'mods/{name}: ' + (f'{listed} files in manifest.tsv' if listed else 'no manifest.tsv, so the app does not load it'))
    uid = box.read(f'{SAVE}/account.uid')
    log(f'saves: {len(remote_files(box, SAVE))} files' + (f', account {account_folder(uid)}' if uid else ', no account.uid'))


def deploy_app(box, a, ipa, info):
    """Back up the saves, install, then the image and the shaders the app does not carry, and --mod last."""
    require(a.mod or not a.slot, '--slot goes with --mod')
    if a.mod:
        mod_files(a.mod)   # a mod the game would refuse stops here, before the long steps
    if box.installed():
        if not a.no_backup:
            require(a.backup_to, 'the app is installed: give --backup-to <folder> for its saves (or --no-backup)')
            backup_save(box, a.backup_to)
    else:
        print('the app is not installed yet: no saves to back up', flush=True)
    print(f'installing {ipa.name} ({ipa.stat().st_size / 2**20:.0f} MiB): {info.get("CFBundleShortVersionString")} '
          f'({info.get("CFBundleVersion")})', flush=True)
    box.install(ipa, bar(ipa.stat().st_size, ipa.name))
    if a.romfs:
        push_romfs(box, a.romfs, progress=bar)
    elif not info['carries']['romfs']:
        marker = (box.read(f'{GAMEDATA}/romfs.sha256') or b'').decode(errors='replace').strip()
        print('game data: ' + ('the device has an image (romfs.sha256)' if len(marker) == 64 else
              'none on the device and none in the app: pass --romfs <romfs.bin>'), flush=True)
    seed = a.seed or ipa.with_name(ipa.stem + '-shader-seed')
    if not info['carries']['seed']:
        if (seed/'fingerprint.txt').is_file():
            push_seed(box, seed, progress=bar)
        else:
            print(f'shaders: no {seed.name} beside the IPA and none in the app (package_ipa_windows.py --seed)', flush=True)
    if a.mod:
        push_mod(box, a.mod, mod_target(a.version, a.slot), progress=bar)
    print('done. A first start after new shaders unpacks them on screen.', flush=True)


def arguments():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='command', required=True)
    def command(name, *args):
        c = sub.add_parser(name)
        for arg in args: c.add_argument(arg, type=Path)
        c.add_argument('--bundle-id', help='the app on the device (default: the IPA\'s, for deploy and install)')
        c.add_argument('--udid', help='the device (default: the one attached; with more than one the command stops and lists them)')
        c.add_argument('--simulate', type=Path, help='a local folder standing for the app\'s container')
        return c
    deploy = command('deploy', 'ipa')
    deploy.add_argument('--romfs', type=Path, help='romfs.bin (index.json beside it), for an app without it')
    deploy.add_argument('--seed', type=Path, help='the device seed (default: <ipa name>-shader-seed beside the IPA)')
    deploy.add_argument('--backup-to', type=Path, help='where the saves of the installed app are backed up first')
    deploy.add_argument('--no-backup', action='store_true', help='install without backing up the saves')
    def mod_version(c):
        c.add_argument('--version', choices=MOD_VERSIONS, default=MOD_VERSION,
                       help=f'the game version of the app, the folder below {MODS} (default: {MOD_VERSION})')
        return c
    def mod_folder(c):
        mod_version(c).add_argument('--slot', choices=MOD_SLOTS, help=f'the folder {MODS}/<version>-<slot> instead')
    deploy.add_argument('--mod', type=Path, help=f'a RomFS mod folder with its manifest.tsv, copied into {MODS}/<version> last')
    mod_folder(deploy)
    command('install', 'ipa')
    command('romfs', 'image')
    command('seed', 'folder')
    mod_folder(command('push-mod', 'folder'))
    mod_version(command('push-slots', 'folder'))
    mod_folder(command('remove-mod'))
    command('backup-save').add_argument('--to', type=Path, required=True)
    restore = command('restore-save', 'backup')
    restore.add_argument('--safety-to', type=Path, help='where the device\'s saves are backed up first (default: beside the backup)')
    restore.add_argument('--other-app', action='store_true', help='restore a backup of another bundle identifier')
    command('status')
    sub.add_parser('check')
    return p.parse_args()


def main():
    a = arguments()
    if a.command == 'check' or not getattr(a, 'simulate', None):
        try:
            import pymobiledevice3  # noqa: F401
        except ImportError:   # run again in pymobiledevice3's own interpreter
            sys.exit(subprocess.run([app_container.pmd3_python(), '-I', str(Path(__file__).resolve()), *sys.argv[1:]]).returncode)
    if a.command == 'check':
        print(app_container.check_api()); return
    ipa = getattr(a, 'ipa', None)
    info = ipa_info(ipa) if ipa else None
    bundle_id = a.bundle_id or (info and info['CFBundleIdentifier'])
    require(bundle_id, '--bundle-id is needed')
    if info:
        require(info['CFBundleIdentifier'] == bundle_id, f'{ipa.name} is {info["CFBundleIdentifier"]}, not {bundle_id}')
    box = app_container.LocalContainer(a.simulate, bundle_id) if a.simulate else app_container.DeviceContainer(bundle_id, a.udid)
    try:
        print(f'device: {box.name}; app {bundle_id}', flush=True)
        if a.command == 'deploy':
            deploy_app(box, a, ipa, info)
        elif a.command == 'install':
            box.install(ipa, bar(ipa.stat().st_size, ipa.name)); print('installed')
        elif a.command == 'romfs':
            push_romfs(box, a.image, progress=bar)
        elif a.command == 'seed':
            push_seed(box, a.folder, progress=bar)
        elif a.command == 'push-mod':
            push_mod(box, a.folder, mod_target(a.version, a.slot), progress=bar)
        elif a.command == 'push-slots':
            push_slots(box, a.folder, a.version, progress=bar)
        elif a.command == 'remove-mod':
            remove_mod(box, mod_target(a.version, a.slot))
        elif a.command == 'backup-save':
            backup_save(box, a.to)
        elif a.command == 'restore-save':
            print('close the game on the device first (swipe it away): it holds account.uid and writes the saves', flush=True)
            restore_save(box, a.backup, a.safety_to or a.backup.parent, a.other_app)
        else:
            status(box)
    finally:
        box.close()


if __name__ == '__main__':
    try:
        main()
    except (PushError, app_container.ContainerError, OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as e:
        print(f'\nERROR: {e}', file=sys.stderr); sys.exit(1)
