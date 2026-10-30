#!/usr/bin/env python3
"""Recover what a Tears of the Kingdom 1.4.3 iPhone/iPad build takes from the player's game files out of an IPA that
build_ipa.py made earlier (with the RomFS inside, built at 30a1b93), for a player who still has that IPA but no longer the
card image, the update or the keys. Standard library only; runs on Windows and macOS.

    python3 games/totk/ios/tools/recover_ipa.py <TOTK.ipa> --out <work>/totk [--skip-romfs]

<work>/totk is the game folder of build_app.py's work folder. Each file goes where build_app.py puts it, so build_ipa.py
and scripts/prepare_shader_seed.py --modules use them as they are:
  rewritten/v143/<module>.patched.bin, <module>.fixups.tsv, build_src.sha256      (main, subsdk0, sdk)
  build/game-data/v143/runtime-tables.bin, rewriter.txt, romfs-config.txt, shared-fonts.txt
  extracted/v143/romfs/romfs.bin, index.json, runtime-index.bin, merge.log
  extracted/v143/romfs-patches/..., extracted/v143/romfs-patches-out/<size>/...
  extracted/firmware/shared-fonts/<n>-<name>.bfttf, manifest.json
  build/from-ipa/embed/<module>.x0.bin, .w.bin, .x1.bin, ios_embed.h, embed.S, layout.json      the app's nine embedded
      sections, with what gen_embed.py writes for them: the header and assembly that embed them (embed.S names this
      machine's paths; gen_embed.py <out>/rewritten/v143 <embed.S> --text-dir <out>/build/from-ipa/embed main subsdk0 sdk
      writes it again elsewhere), and their layout (--layout-of). main's text there lacks the game patches added since
      30a1b93, so the runtime takes other sections: export_ios_windows.py makes them from rewritten/v143 into
      build/export-ios, and package_ipa_windows.py writes those into it
  build/from-ipa/app/Assets.car, AppIcon*.png, default.metallib, Info.plist        the old app's own resources
  recover-manifest.json      every file with its size, SHA-256 and what it was checked against

Each file is checked before it is moved into its place, and the first failed check stops the run before
recover-manifest.json is written:
  - The three modules (recover_modules.py) against expected-v1.4.3.json rewritten_sha256. sdk and subsdk0 are the app's
    sections joined (x0 + W + x1, cut to the module's size). main's text also holds the game patches 30a1b93's export-ios
    applied: they are undone from the original instructions game_patches_v143.c checked, and the veneers behind the text
    are cleared. The result is accepted only as the pinned file, the one build_app.py makes from the card image.
  - runtime-tables.bin: the tables 30a1b93 compiled into the app (_modules, _symbol_N, _reloc_N, _gate_N), written by
    scripts/prepare_runtime.py table_bytes. Symbols, relocations, constructor flag, init tags and main's probe stub are
    made again from the pinned images as prepare_runtime.py makes them and must be the same. The gates are not in the
    image; each must have its site branch into the patch area and its return address follow a blr x30.
  - The nine sections against the app's own _ios_embed hashes and the sizes and SHA-256 of the sections of the app
    30a1b93 built (recover_modules.APP_SECTIONS); ios_embed.h and layout.json, written by gen_embed.py from the
    recovered modules and sections, must name the same.
  - romfs.bin, Deflate in the IPA (2 minutes on an SSD, 2026-10-26): streamed to disk while its SHA-256 is computed,
    against the pinned size and SHA-256, and moved into place only then. index.json
    against the same pin; runtime-index.bin made again from it (prepare_romfs_backend.py) must be byte for byte the app's.
  - The shared fonts as build_app.py accepts them: the pinned SHA-256, or a valid BFTTF bound by its own.
  - The RomFS overlays against their manifest.tsv (size and SHA-256 of each file) and, with romfs.bin there, each
    replaced file's original SHA-256 against the RomFS.
  - merge.log and the old app's resources by the CRC-32 of their IPA entries only (nothing pins them); for
    default.metallib the manifest says whether its Metal sources changed since the app's TOTKSourceCommit (git).
The game data text files are written as prepare_runtime.py, prepare_romfs_backend.py and prepare_shared_fonts.py write
them, with '\\n' line ends on every system. --skip-romfs does everything else (about 10 seconds); a later run extracts
romfs.bin, and reuses one the manifest records as checked (same size and modification time) instead of extracting it
again.

An app holds no ExeFS and none of the rewriter's other records (gates.tsv, sites.tsv, ...), so make game-data-v143 cannot
run prepare_runtime.py on this folder; build/AppIcon.icns and analysis/ are not recovered either, nor the app's shader
seed (another translation chain than this runtime's: scripts/prepare_shader_seed.py, or seed_windows.py on Windows, makes
a new one from this folder). Nothing recovered may be committed: --out is outside the repository, or the game folder
itself, whose .gitignore covers build/, extracted/ and rewritten/."""
import argparse, hashlib, json, plistlib, re, shutil, struct, subprocess, sys, time, zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
GAME = TOOLS.parents[1]
REPO = GAME.parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(REPO))
import build_app                 # noqa: E402  the pins and the shared-font acceptance of a build from the card image
import macho                     # noqa: E402
import recover_modules           # noqa: E402  the three code modules and the runtime tables
from recover_modules import APP_SECTIONS, NAMES, VERSION, RecoverError, digest, require   # noqa: E402

PINS = build_app.VERSIONS[VERSION]
OLD_APP_FILES = ('Assets.car', 'default.metallib', 'Info.plist')   # and every AppIcon*.png
METAL_SOURCES = (':(glob)games/totk/**/*.metal',)   # what Xcode compiles into default.metallib (ios/project.yml sources)
OVERLAY_SCRIPTS = ('games/totk/scripts/make_romfs_patches.py', 'games/totk/scripts/make_output_res_overlay.py')
say = build_app.say


def source_sha256(path):
    """A repository file's SHA-256 as committed (and as a Mac checkout has it): a Windows checkout with core.autocrlf
    turns its LF line ends into CR LF, which changes the hash that build_src.sha256 and the overlay records name."""
    return digest(path.read_bytes().replace(b'\r\n', b'\n'))


def git(*args):
    """A git command's output in this repository; None without git or without the history it needs."""
    try:
        p = subprocess.run(['git', '-C', str(REPO), *args], capture_output=True, text=True)
    except OSError:
        return None
    return p.stdout if p.returncode == 0 else None


def changed_since(commit, paths):
    """The files of paths that differ between commit and this checkout, None when git cannot tell."""
    out = git('diff', '--name-only', commit, '--', *paths) if commit else None
    return None if out is None else out.split()


class Output:
    """The output folder: each file is written next to its place, checked, then moved there, and recorded for
    recover-manifest.json."""
    def __init__(self, root, previous):
        self.root, self.previous, self.files, self.pending, self.notes = root, previous, {}, [], []

    def path(self, rel):
        return self.root / rel

    def record(self, rel, basis, pin=None, **extra):
        path = self.path(rel)
        sha = extra.pop('sha256', None) or build_app.sha256(path)
        require(not pin or sha == pin, f'{rel}: SHA-256 {sha[:16]}... is not the pinned {(pin or "")[:16]}...')
        self.files[rel] = dict(path=rel, size=path.stat().st_size, sha256=sha, basis=basis, pinned=bool(pin), **extra)

    def write(self, rel, data, basis, pin=None):
        require(not pin or digest(data) == pin, f'{rel}: SHA-256 {digest(data)[:16]}... is not the pinned {(pin or "")[:16]}...')
        path = self.path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + '.partial')
        partial.write_bytes(data)
        partial.replace(path)
        self.record(rel, basis, pin, sha256=digest(data))

    def text(self, rel, lines, basis):
        """A text file with '\\n' line ends on every system: the runtime's game data parser splits at '\\n' only."""
        self.write(rel, ''.join(line + '\n' for line in lines).encode(), basis)


class Ipa:
    """The files of Payload/<name>.app in the IPA, by their path inside the app."""
    def __init__(self, path):
        self.path = path
        try:
            self.zip = zipfile.ZipFile(path)
        except (OSError, zipfile.BadZipFile) as e:
            raise RecoverError(f'{path}: not a readable IPA ({e})') from None
        apps = sorted({n.rsplit('/', 1)[0] for n in self.zip.namelist() if re.fullmatch(r'Payload/[^/]+\.app/Info\.plist', n)})
        require(len(apps) == 1, f'{path}: {len(apps)} apps in Payload/')
        self.app = apps[0] + '/'
        self.info = plistlib.loads(self.read('Info.plist'))

    def has(self, rel):
        try:
            self.zip.getinfo(self.app + rel)
            return True
        except KeyError:
            return False

    def read(self, rel):
        try:
            return self.zip.read(self.app + rel)   # the CRC-32 of the entry is checked
        except KeyError:
            raise RecoverError(f'the app has no {rel}') from None
        except zipfile.BadZipFile as e:
            raise RecoverError(f'{rel}: damaged in the IPA ({e})') from None

    def names(self, folder):
        prefix = self.app + folder
        return sorted(n[len(self.app):] for n in self.zip.namelist() if n.startswith(prefix) and not n.endswith('/'))


def run_gen_embed(*args):
    p = subprocess.run([sys.executable, '-I', TOOLS / 'gen_embed.py', *args], capture_output=True, text=True)
    require(p.returncode == 0, f'gen_embed.py failed: {p.stderr.strip()[-500:]}')
    return p.stdout.strip()


def step_code(ipa, out):
    """The three modules, their layout files, the runtime tables and the nine embedded sections."""
    say('code: reading the app executable')
    exe = macho.MachO(ipa.read('TOTK' if ipa.has('TOTK') else ipa.info['CFBundleExecutable']))
    modules, embed = recover_modules.old_modules(exe), macho.embed_hashes(exe, NAMES)
    got = {m['name']: recover_modules.recover_module(exe, m, embed, PINS['rewritten_sha256'][f'{m["name"]}.patched.bin'])
           for m in modules}
    tables = recover_modules.runtime_tables(modules, got['main']['image'])
    rewritten, sections, data = f'rewritten/{VERSION}', 'build/from-ipa/embed', f'build/game-data/{VERSION}'
    for m in modules:
        name, r = m['name'], got[m['name']]
        how = ('x0 + W + x1, cut to the module size' if not r['restored'] else f'x0 with the original instruction put back '
               f'at {len(r["restored"])} sites of 30a1b93\'s export-ios patches and [TEXT_END, RO_OFF) cleared, + W + x1')
        out.write(f'{rewritten}/{name}.patched.bin', r['image'], f'the app\'s embedded sections ({how}); '
                  'expected-v1.4.3.json rewritten_sha256', PINS['rewritten_sha256'][f'{name}.patched.bin'])
        out.text(f'{rewritten}/{name}.fixups.tsv', recover_modules.fixups_lines(m), 'the app\'s _modules record, checked '
                 'against the section sizes (loader.c map_module) and the pinned image\'s relocations; key slots from '
                 'patch_nso.py KEY_INDEX')
        for part, blob in r['parts'].items():
            sect = ','.join(macho.module_sections(name)[part])
            out.write(f'{sections}/{name}.{part}.bin', blob, f'the app\'s section {sect}; SHA-256 as its _ios_embed and '
                      'recover_modules.APP_SECTIONS', APP_SECTIONS[(name, part)][1])
        if r['restored']:
            out.notes.append(f'{name}: original instruction put back at ' + ' '.join(f'{s:#x}' for s in r['restored']))
        if not r['found']['dt_hash']:
            out.notes.append(f'{name}: GNU hash only; its {m["nsym"]} symbols are the app\'s count, bounded by the data '
                             f'segment{" and followed by the name table" if r["found"]["dynstr_follows"] else ""}')
    out.write(f'{data}/runtime-tables.bin', tables, 'the app\'s compiled-in tables in loader.c load_tables layout; symbols, '
              'relocations, constructor flag, init tags and probe stub equal to what prepare_runtime.py makes of the pinned '
              'images; gates checked against them')
    rewriter = source_sha256(GAME / 'third_party/d2r/patch_nso.py')
    why = 'this repository\'s patch_nso.py, whose 1.4.3 output is the pinned rewrite (update_runtime.py check_rewriter)'
    out.text(f'{rewritten}/build_src.sha256', [f'{rewriter}  patch_nso.py'], why)
    out.text(f'{data}/rewriter.txt', [f'# SHA-256 of the patch_nso.py that rewrote rewritten/{VERSION}', f'REWRITER_SHA256 {rewriter}'], why)
    say('code: gen_embed.py on the recovered modules and the app\'s sections')
    flags = run_gen_embed(out.path(rewritten), out.path(f'{sections}/embed.S'), '--text-dir', out.path(sections), *NAMES)
    run_gen_embed('--layout-of', out.path(sections), out.path(f'{sections}/layout.json'), *NAMES)
    require(recover_modules.embed_header_hashes(out.path(f'{sections}/ios_embed.h').read_text()) == embed,
            'ios_embed.h from gen_embed.py names other hashes than the app\'s _ios_embed')
    require(recover_modules.layout_pins(json.loads(out.path(f'{sections}/layout.json').read_text())) == APP_SECTIONS,
            'layout.json from gen_embed.py --layout-of differs from recover_modules.APP_SECTIONS')
    out.record(f'{sections}/ios_embed.h', 'gen_embed.py; its nine hashes equal the app\'s _ios_embed')
    out.record(f'{sections}/embed.S', f'gen_embed.py (.incbin paths of this machine; linker flags {flags})')
    out.record(f'{sections}/layout.json', 'gen_embed.py --layout-of; equal to recover_modules.APP_SECTIONS')
    say(f'code: {", ".join(NAMES)} are the pinned rewrites; runtime tables {sum(len(m["relocs"]) for m in modules)} '
        f'relocations, {sum(len(m["gates"]) for m in modules)} gates')


def stage(out, rel):
    """A fresh folder beside out/rel; replace_folder moves it into place once it is checked."""
    tmp = out.path(rel + '.partial')
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    return tmp


def replace_folder(tmp, dst):
    if dst.exists():
        shutil.rmtree(dst)
    tmp.replace(dst)


def runtime_index(index):
    """runtime-index.bin from index.json, as prepare_romfs_backend.py makes it."""
    strings, rows = bytearray(), bytearray()
    for item in index['files']:
        name = item['path'].encode() + b'\0'
        rows.extend(struct.pack('<QQII', item['offset'], item['size'], len(strings), len(name)))
        strings.extend(name)
    return struct.pack('<8sQQ', b'TOTKRFS1', len(index['files']), 24 + len(rows)) + rows + strings


def step_data(ipa, out):
    """index.json, runtime-index.bin, merge.log, the shared fonts, the RomFS overlays and the game data text files."""
    romfs, data, pin = f'extracted/{VERSION}/romfs', f'build/game-data/{VERSION}', PINS['romfs']
    raw = ipa.read('GameData/romfs/index.json')
    index = json.loads(raw)
    require(index.get('status') == 'pass' and index.get('romfs_sha256') == pin['sha256'] and index.get('romfs_size') == pin['size'],
            'GameData/romfs/index.json is not the verified index of the pinned 1.4.3 RomFS')
    out.write(f'{romfs}/index.json', raw, 'status pass; its romfs_sha256 and romfs_size are the expected-v1.4.3.json romfs pin')
    blob = runtime_index(index)
    require(not ipa.has('GameData/romfs/runtime-index.bin') or ipa.read('GameData/romfs/runtime-index.bin') == blob,
            'the app\'s runtime-index.bin is not the one prepare_romfs_backend.py makes from its index.json')
    out.write(f'{romfs}/runtime-index.bin', blob, 'made from index.json as prepare_romfs_backend.py does; byte-equal to the app\'s')
    if ipa.has('GameData/romfs/merge.log'):
        out.write(f'{romfs}/merge.log', ipa.read('GameData/romfs/merge.log'), 'the extraction\'s log as the app carries it; no pin')
    out.text(f'{data}/romfs-config.txt', [f'ROMFS_IMAGE_SIZE {pin["size"]}', f'ROMFS_IMAGE_SHA256 {pin["sha256"]}',
             f'ROMFS_INDEX_SHA256 {digest(blob)}'], 'prepare_romfs_backend.py: the romfs pin and runtime-index.bin\'s SHA-256')
    step_fonts(ipa, out, data)
    for folder in ('romfs-patches', 'romfs-patches-out'):
        step_overlays(ipa, out, folder)


def step_fonts(ipa, out, data):
    """The shared fonts as a build accepts them (build_app.py validate_fonts), and shared-fonts.txt naming them."""
    fonts_rel = 'extracted/firmware/shared-fonts'
    tmp = stage(out, fonts_rel)
    for rel in ipa.names('GameData/shared-fonts/'):
        (tmp / rel.rsplit('/', 1)[1]).write_bytes(ipa.read(rel))
    try:
        build_app.validate_fonts(tmp)   # the fonts as a build accepts them, and manifest rows that match them
    except build_app.BuildError as e:
        raise RecoverError(f'shared fonts: {e}') from None
    replace_folder(tmp, out.path(fonts_rel))
    lines = []
    for f in json.loads((out.path(fonts_rel) / 'manifest.json').read_text())['fonts']:
        name, want = f"{f['type']}-{f['name']}.bfttf", PINS['shared_fonts_sha256'][f['name']]
        require(f['bfttf_bytes'] == f['font_bytes'] + 8 and ' ' not in name, f'shared font {name}: sizes')
        out.record(f'{fonts_rel}/{name}', 'expected-v1.4.3.json shared_fonts_sha256' if f['sha256'] == want else
                   'a valid BFTTF from another firmware version, bound by its own SHA-256 (build_app.py font_report)',
                   want if f['sha256'] == want else None)
        i = f['type']
        lines += [f'FONT{i}_FILE {name}', f'FONT{i}_FILE_BYTES {f["bfttf_bytes"]}', f'FONT{i}_FONT_BYTES {f["font_bytes"]}',
                  f'FONT{i}_SHA256 {f["sha256"]}']
    out.record(f'{fonts_rel}/manifest.json', 'the extraction\'s manifest; its rows match the files (build_app.py validate_fonts)')
    out.text(f'{data}/shared-fonts.txt', lines, 'prepare_shared_fonts.py: names, sizes and SHA-256 of the checked fonts')


def step_overlays(ipa, out, folder):
    """One RomFS overlay folder of the app (romfs-patches, romfs-patches-out), each file against its manifest.tsv."""
    rel = f'extracted/{VERSION}/{folder}'
    names = [n[len(f'GameData/{folder}/'):] for n in ipa.names(f'GameData/{folder}/')]
    if not names:
        return
    tmp = stage(out, rel)
    for n in names:
        (tmp / n).parent.mkdir(parents=True, exist_ok=True)
        (tmp / n).write_bytes(ipa.read(f'GameData/{folder}/{n}'))
    overlays = sorted({str(Path(n).parent).replace('\\', '/') for n in names if Path(n).name == 'manifest.tsv'})
    listed = {}
    for overlay in overlays:
        base = '' if overlay == '.' else overlay + '/'
        for line in (tmp / base / 'manifest.tsv').read_text().splitlines():
            if line and not line.startswith('#'):
                path, size, sha, original = line.split('\t')
                listed[base + path] = (int(size), sha, original)
    for n in names:
        if Path(n).name in ('manifest.tsv', 'overlay.json'):
            continue
        row = listed.get(n)
        require(row and (tmp / n).stat().st_size == row[0] and build_app.sha256(tmp / n) == row[1],
                f'{rel}/{n}: not the file its manifest.tsv lists')
    require(not set(listed) - set(names), f'{rel}: manifest.tsv lists files the app lacks: {sorted(set(listed) - set(names))[:3]}')
    replace_folder(tmp, out.path(rel))
    script = source_sha256(GAME / 'scripts/make_output_res_overlay.py')
    for n in names:
        record = out.path(f'{rel}/{n}')
        if Path(n).name == 'overlay.json':
            current = json.loads(record.read_text()).get('script_sha256') == script
            out.record(f'{rel}/{n}', 'the overlay\'s record' + ('' if current else '; made by another '
                       'make_output_res_overlay.py than this repository\'s (build_app.py makes it again on a Mac)'))
        elif Path(n).name == 'manifest.tsv':
            out.record(f'{rel}/{n}', 'the overlay\'s file list')
        else:
            out.record(f'{rel}/{n}', 'size and SHA-256 as its manifest.tsv; original_sha256 against the RomFS: pending',
                       original_sha256=listed[n][2], romfs_path=n.split('/', 1)[1] if folder == 'romfs-patches-out' else n)


def step_romfs(ipa, out, extract):
    """romfs.bin: streamed out of the IPA and checked against the pin, or the one a previous run checked."""
    rel, pin, member = f'extracted/{VERSION}/romfs/romfs.bin', PINS['romfs'], 'GameData/romfs/romfs.bin'
    path, before = out.path(rel), out.previous.get(rel)
    try:
        st = path.stat()
        if before and before.get('sha256') == pin['sha256'] and before.get('size') == st.st_size == pin['size'] \
                and before.get('mtime_ns') == st.st_mtime_ns:
            out.files[rel] = before
            say('data: romfs.bin is the one the last run checked')
            return True
    except OSError:
        pass
    if not extract:
        out.pending.append(rel)
        return False
    info = ipa.zip.getinfo(ipa.app + member)
    require(info.file_size == pin['size'], f'{member}: {info.file_size} bytes, the pinned 1.4.3 RomFS has {pin["size"]}')
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = path.stat().st_size if path.is_file() else 0   # replaced only once the new one is checked
    require(shutil.disk_usage(path.parent).free >= info.file_size + (1 << 30) - kept,
            f'{path.parent}: not enough free space for {info.file_size / 2**30:.1f} GiB')
    say(f'data: extracting romfs.bin ({info.file_size / 2**30:.1f} GiB, Deflate) and checking its SHA-256')
    partial, h, done, t0, beat = path.with_name(path.name + '.partial'), hashlib.sha256(), 0, time.time(), time.time()
    try:
        with ipa.zip.open(info) as src, open(partial, 'wb') as dst:
            while chunk := src.read(16 << 20):
                h.update(chunk)
                dst.write(chunk)
                done += len(chunk)
                if time.time() - beat >= 60:
                    beat = time.time()
                    say(f'   ... {done / 2**30:.1f} of {info.file_size / 2**30:.1f} GiB ({(beat - t0) / 60:.0f} min)')
    except zipfile.BadZipFile as e:
        partial.unlink(missing_ok=True)
        raise RecoverError(f'{member}: damaged in the IPA ({e})') from None
    if done != pin['size'] or h.hexdigest() != pin['sha256']:
        partial.unlink(missing_ok=True)
        raise RecoverError(f'romfs.bin: {done} bytes, SHA-256 {h.hexdigest()[:16]}...: not the pinned 1.4.3 RomFS')
    partial.replace(path)
    out.record(rel, f'streamed out of the IPA in {(time.time() - t0) / 60:.1f} min; expected-v1.4.3.json romfs size and '
               f'SHA-256', pin['sha256'], sha256=h.hexdigest(), mtime_ns=path.stat().st_mtime_ns)
    return True


def check_overlay_originals(out):
    """Each overlay file replaces a RomFS file whose SHA-256 its manifest names: read it from the checked romfs.bin."""
    romfs = out.path(f'extracted/{VERSION}/romfs')
    entries = {f['path']: f for f in json.loads((romfs / 'index.json').read_text())['files']}
    with open(romfs / 'romfs.bin', 'rb') as image:
        for rel, entry in out.files.items():
            if 'original_sha256' not in entry:
                continue
            item = entries.get(entry['romfs_path'])
            require(item, f'{rel}: replaces {entry["romfs_path"]}, which the RomFS does not hold')
            image.seek(item['offset'])
            require(digest(image.read(item['size'])) == entry['original_sha256'],
                    f'{rel}: made from another {entry["romfs_path"]} than this RomFS holds')
            entry['basis'] = entry['basis'].replace('pending', 'pass')


def step_app(ipa, out, commit):
    """The old app's own resources a new build can carry again."""
    rel = 'build/from-ipa/app'
    names = [n for n in OLD_APP_FILES if ipa.has(n)] + [n for n in ipa.names('AppIcon') if '/' not in n and n.endswith('.png')]
    for n in names:
        basis = 'the old app\'s file (CRC-32 of the IPA entry checked); no pin'
        if n == 'default.metallib':
            changed = changed_since(commit, METAL_SOURCES)
            flags = 'MTL_' in (TOOLS.parent / 'project.yml').read_text(encoding='utf-8')
            basis += ('; its sources (games/totk/**/*.metal) are ' +
                      ('unknown here (no git history)' if changed is None else
                       f'unchanged since {commit[:7]}' if not changed else f'changed since {commit[:7]}: {", ".join(changed)}')
                      + ('; ios/project.yml sets MTL_ build settings' if flags else '; ios/project.yml sets no MTL_ build settings'))
        if n.startswith('AppIcon') or n == 'Assets.car':
            basis += '; made from the game\'s own icon'
        out.write(f'{rel}/{n}', ipa.read(n), basis)


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('ipa', type=Path, help='the IPA build_ipa.py made (unsigned or signed), with GameData/romfs inside')
    p.add_argument('--out', type=Path, required=True, help='the game folder of the work folder (<work>/totk)')
    p.add_argument('--skip-romfs', action='store_true', help='everything except extracting romfs.bin (a later run does it)')
    a = p.parse_args()
    out_root, ipa_path = a.out.resolve(), a.ipa.resolve()
    require(out_root == GAME or not out_root.is_relative_to(REPO),
            f'{out_root} is inside the repository: game files must not land where git can commit them')
    ipa = Ipa(ipa_path)
    require(ipa.info.get('CFBundleShortVersionString') == PINS['display_version'],
            f'the app is version {ipa.info.get("CFBundleShortVersionString")}, this recovers {PINS["display_version"]}')
    manifest_path = out_root / 'recover-manifest.json'
    try:
        previous = {f['path']: f for f in json.loads(manifest_path.read_text())['files']}
    except (OSError, ValueError, KeyError, TypeError):
        previous = {}
    out = Output(out_root, previous)
    commit = ipa.info.get('TOTKSourceCommit')
    step_code(ipa, out)
    step_data(ipa, out)
    step_app(ipa, out, commit)
    if step_romfs(ipa, out, not a.skip_romfs):
        check_overlay_originals(out)
    else:
        out.pending.append('the RomFS overlays\' original_sha256 (needs romfs.bin)')
    changed = changed_since(commit, OVERLAY_SCRIPTS)
    out.notes.append('the overlay scripts (' + ', '.join(Path(s).name for s in OVERLAY_SCRIPTS) + ') are ' + (
        'unknown here (no git history)' if changed is None else f'unchanged since {commit[:7]}' if not changed else
        f'changed since {commit[:7]}: {", ".join(changed)}; a Mac build makes the overlays again'))
    if ipa.has('GameData/shader-seed/seed-manifest.json'):
        chain = json.loads(ipa.read('GameData/shader-seed/seed-manifest.json')).get('chain')
        out.notes.append(f'not recovered: the app\'s shader seed (chain {chain}); this runtime translates with '
                         + re.search(r'DMSH_CHAIN "([^"]+)"', (GAME / 'third_party/d2r_gfx/gfx/nvn/dmsh_chain.h').read_text()).group(1))
    st = ipa_path.stat()
    tool_files = [TOOLS / n for n in ('recover_ipa.py', 'recover_modules.py', 'macho.py', 'gen_embed.py')] + [GAME / 'scripts/prepare_runtime.py']
    manifest = dict(format=1, tool='games/totk/ios/tools/recover_ipa.py',
                    tool_sha256={f.relative_to(REPO).as_posix(): source_sha256(f) for f in tool_files},
                    repository_commit=(git('rev-parse', 'HEAD') or '').strip() or None, made=time.strftime('%Y-%m-%d %H:%M:%S'),
                    version=VERSION, source=dict(ipa=str(ipa_path), size=st.st_size, mtime_ns=st.st_mtime_ns, app=ipa.app,
                    bundle_id=ipa.info.get('CFBundleIdentifier'), short_version=ipa.info.get('CFBundleShortVersionString'),
                    bundle_version=ipa.info.get('CFBundleVersion'), source_commit=commit),
                    files=[out.files[k] for k in sorted(out.files)], pending=out.pending, notes=out.notes)
    partial = manifest_path.with_name(manifest_path.name + '.partial')
    partial.write_bytes((json.dumps(manifest, indent=2) + '\n').encode())
    partial.replace(manifest_path)
    say(f'{len(out.files)} files checked into {out_root}' + (f'; pending: {"; ".join(out.pending)}' if out.pending else ''))


if __name__ == '__main__':
    try:
        main()
    except (RecoverError, macho.MachOError, OSError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)
