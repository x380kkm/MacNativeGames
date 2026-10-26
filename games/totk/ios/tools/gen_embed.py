#!/usr/bin/env python3
"""Emit the iOS executable sections for the already patched guest modules.

    gen_embed.py <rewritten> <embed.S> [--text-dir <export>] main subsdk0 sdk
    gen_embed.py --layout <layout.json> <embed.S>
    gen_embed.py --layout-of <sections> <layout.json> main subsdk0 sdk

The first form embeds the modules (.incbin) and prints the linker flags. The second emits zero-filled sections of the
sizes in a layout, with its hashes in ios_embed.h, and prints the same flags: a machine that never holds the game files
links the runtime this way, and the module bytes are written into those sections of the executable afterwards, at their
file offsets; the loader checks them against the hashes (loader.c). The third writes such a layout from section files
<name>.x0.bin, <name>.w.bin and <name>.x1.bin (the three sections of each module, as the executable holds them)."""
import hashlib, json, re, sys
from pathlib import Path

PG = 0x4000
PARTS = ('x0', 'w', 'x1')
def up(n): return (n + PG - 1) & ~(PG - 1)

def section_names(name):
    names = (f'__TOTKX,__{name}x0', f'__TOTK{name}W,__img', f'__TOTKX,__{name}x1')
    for sect in names:
        if any(len(s) > 16 for s in sect.split(',')): raise ValueError(f'{name}: Mach-O section name too long: {sect}')
    return names

def write_outputs(out, asm, entries):
    """embed.S, ios_embed.h beside it, and the linker flags on stdout."""
    out.write_text('\n'.join(asm)+'\n')
    header = ['/* Generated locally; hashes bind app contents to the verified rewrites. */',
              'typedef struct { const char *name, *x0, *w, *x1; } IosEmbed;', 'static const IosEmbed ios_embed[] = {']
    header += [f'{{"{e["name"]}","{e["x0"]}","{e["w"]}","{e["x1"]}"}},' for e in entries]
    header += ['};']
    (out.parent/'ios_embed.h').write_text('\n'.join(header)+'\n')
    flags = [f'-Wl,-segprot,__TOTK{e["name"]}W,rw,rw' for e in entries] + ['-Wl,-segprot,__TOTKX,r-x,r-x']
    print(' '.join(flags))

def embed_modules(root, out, names, text_dir):
    asm = ['// Generated from the locally verified game modules.']
    entries = []
    for name in names:
        image = root / f'{name}.patched.bin'
        hdr = dict(line[2:].split() for line in (root / f'{name}.fixups.tsv').read_text().splitlines())
        data = image.read_bytes(); text_end = int(hdr['TEXT_END'], 16); patch = int(hdr['PATCH_OFF'], 16)
        text_image = (text_dir / f'{name}.x0.bin') if text_dir else image
        text_data = text_image.read_bytes() if text_dir else data
        key = int(hdr['KEY_PAGE_OFF'], 16); size = int(hdr.get('FILE_IMAGE_LEN', f'{len(data):x}'), 16)
        x0, x1 = up(text_end), up(len(data))
        if len(text_data) != x0:
            raise ValueError(f'{name}: exported x0 must be exactly {x0:#x} bytes, got {len(text_data):#x}')
        sect_x0, sect_w, sect_x1 = section_names(name)
        if patch < 0:
            file_end = int(hdr['FILE_IMAGE_LEN'], 16)
            if file_end % PG or x0 > file_end or key % PG: raise ValueError(f'{name}: invalid far patch layout')
            parts = [(sect_x0, 0, x0), (sect_w, x0, file_end), (sect_x1, file_end, x1)]
        else:
            if patch % PG or x0 > key or key + PG > patch: raise ValueError(f'{name}: invalid patch layout')
            parts = [(sect_x0, 0, x0), (sect_w, x0, patch), (sect_x1, patch, x1)]
        hashes=[]
        for sect, lo, hi in parts:
            asm += [f'    .section {sect}', '    .p2align 14']
            section_image = text_image if sect == sect_x0 else image
            if sect == sect_x0: chunk_source = text_data
            else: chunk_source = data
            # The patch area as the export left it (loader.c export-ios: Breath of the Wild's exclusive-acquire patch changes it)
            x1_export = text_dir / f'{name}.x1.bin' if text_dir else None
            if sect == sect_x1 and x1_export and x1_export.is_file():
                x1_data = x1_export.read_bytes()
                if len(x1_data) != hi - lo: raise ValueError(f'{name}: exported x1 must be exactly {hi - lo:#x} bytes, got {len(x1_data):#x}')
                section_image, chunk_source, lo, hi = x1_export, x1_data, 0, hi - lo
            real = max(0, min(hi, len(chunk_source))-lo)
            if real: asm += [f'    .incbin "{section_image.resolve()}", {lo:#x}, {real:#x}']
            if hi-lo > real: asm += [f'    .space {hi-lo-real:#x}']
            asm += ['    .p2align 14']
            chunk=chunk_source[lo:min(hi,len(chunk_source))] if lo < len(chunk_source) else b''
            if len(chunk)<hi-lo: chunk += bytes(hi-lo-len(chunk))
            hashes.append(hashlib.sha256(chunk).hexdigest())
        entries.append({'name':name,'x0':hashes[0],'w':hashes[1],'x1':hashes[2]})
    write_outputs(out, asm, entries)

def embed_placeholders(layout, out):
    asm = ['// Generated from a section layout: zero-filled sections of the verified modules\' sizes.']
    entries = []
    for m in json.loads(layout.read_text())['modules']:
        name = m['name']
        for sect, part in zip(section_names(name), PARTS):
            size, digest = m[part]['size'], m[part]['sha256']
            if not isinstance(size, int) or size <= 0 or size % PG: raise ValueError(f'{name} {part}: size {size!r} is not a positive multiple of {PG:#x}')
            if not re.fullmatch(r'[0-9a-f]{64}', digest): raise ValueError(f'{name} {part}: not a SHA-256: {digest!r}')
            asm += [f'    .section {sect}', '    .p2align 14', f'    .space {size:#x}', '    .p2align 14']
        entries.append({'name': name, **{part: m[part]['sha256'] for part in PARTS}})
    write_outputs(out, asm, entries)

def write_layout(sections, out, names):
    modules = []
    for name in names:
        section_names(name)
        m = {'name': name}
        for part in PARTS:
            data = (sections / f'{name}.{part}.bin').read_bytes()
            if not data or len(data) % PG: raise ValueError(f'{name}.{part}.bin: {len(data):#x} bytes is not a positive multiple of {PG:#x}')
            m[part] = {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        modules.append(m)
    out.write_text(json.dumps({'modules': modules}, indent=2)+'\n')

args = sys.argv[1:]
if args and args[0] == '--layout':
    embed_placeholders(Path(args[1]), Path(args[2]))
elif args and args[0] == '--layout-of':
    write_layout(Path(args[1]), Path(args[2]), args[3:])
else:
    root, out = Path(args[0]), Path(args[1])
    args = args[2:]
    text_dir = None
    if '--text-dir' in args:
        i = args.index('--text-dir')
        text_dir = Path(args[i + 1])
        del args[i:i + 2]
    embed_modules(root, out, args, text_dir)
