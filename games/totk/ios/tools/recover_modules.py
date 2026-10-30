#!/usr/bin/env python3
"""The game's three code modules (main, subsdk0, sdk) out of the executable of an app build_ipa.py made at 30a1b93, for
recover_ipa.py; standard library only.

That app embeds each module as three sections (x0: the text as export-ios left it, W: the rest up to the patch area, x1:
the patch area; gen_embed.py), and 30a1b93 compiled the loader's tables into it (_modules, _symbol_N, _reloc_N, _gate_N,
the layouts of runtime/runtime.h). recover_module checks the sections as the app's loader checks them and against those
of the app 30a1b93 built (APP_SECTIONS), makes the rewritten image again (sdk and subsdk0: x0 + W + x1 cut to the module
size; main: its text with the game patches of 30a1b93's export-ios undone, EXPORT_SITES and ASPECT_SITES, and the
veneers behind the text cleared), and accepts it only as the pinned rewrite. The image's symbols, relocations, constructor flag and init tags,
made as scripts/prepare_runtime.py makes them, must be the app's; the gates, which the image does not hold, must each
have its site branch into the patch area and its return address follow a blr x30. runtime_tables writes them with
prepare_runtime.table_bytes."""
import hashlib, re, struct, sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
GAME = TOOLS.parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(GAME / 'scripts'))
sys.path.insert(0, str(GAME / 'third_party/d2r'))
import macho                     # noqa: E402
import prepare_runtime           # noqa: E402  runtime-tables.bin (table_bytes)
from relr import decode_relr     # noqa: E402

VERSION = 'v143'
NAMES = ('main', 'subsdk0', 'sdk')   # runtime/loader.c module order
PAGE = 0x4000
BLR_X30 = 0xd63f03c0
GET_SYSTEM_TICK = '_ZN2nn2os13GetSystemTickEv'
# What 30a1b93's export-ios wrote into main's text (runtime_game_patches, games/totk/runtime/game_patches_v143.c at
# 30a1b93): each site with the original instruction the patch checks before it writes. The patches off on iOS at 30a1b93
# (output, render and fixed resolution) are listed too, so an export made with them is undone as well.
EXPORT_SITES = {
    0x2db204: 0x6b08015f, 0x2db208: 0x1a89b10a, 0x2db22c: 0xb940468a, 0x2db360: 0x6b0801bf,     # fps60
    0x2db36c: 0x1a88c1ac, 0x2db340: 0xb9400288, 0x2db34c: 0x2a0a03f5,
    0x246eac: 0x1e200940, 0x345904: 0x1e210801, 0x24944c: 0x94015e7d, 0x28bc98: 0x9400546a,     # cloth and hair clock
    0x3e5658: 0x1e210808, 0x2daa54: 0xbd425260, 0x2daa58: 0x52a84e08, 0x2daa6c: 0x5e21d800,     # real-time frame step
    0x2daa70: 0x1e201820, 0x2daa74: 0x1e2c1001, 0x2daa78: 0x1e210800,
    0x562a64: 0xbd402920, 0x562a68: 0x52a85909, 0x562a6c: 0x1e270121,                         # slow-motion bounce
    0xbdb578: 0xd280f008, 0xbdb584: 0xf2c08708, 0x3dcb28: 0xd360fc64, 0x3dcb2c: 0xf9028663,     # output resolution
    0x3dcb30: 0xd001ac08,
    0x585e48: 0x1e220160, 0x585e50: 0xbd0cc660, 0x585e54: 0x1e220140, 0x585e60: 0xbd0cca60,     # render resolution
    0x5848a8: 0x2a1703e9,                                                                       # fixed resolution
}
# The aspect-ratio sites (aspect_install): site i branches to the stub at ((TEXT_END + 15) & ~15) + 48 + 32 * i, whose
# first word is the site's own instruction (aspect_math.h aspect_stub).
ASPECT_SITES = (0x628c74, 0xb43460, 0x1ff04f4, 0x253fbb0)
ASPECT_STUBS, ASPECT_STUB = 48, 32
# The nine sections of the app 30a1b93 built, (name, part) -> (size, SHA-256), as gen_embed.py --layout-of gives them.
# The runtime the ios-runtime workflow builds pins export_ios_windows.py's sections of the same rewrites instead
# (ios/ci/embed-layout-v143.json): the same sizes, W and x1, and main's text with the patches added since 30a1b93.
APP_SECTIONS = {
    ('main', 'x0'): (45858816, '01df600a0d1da3d56bafbd33cf26a843067e4e9c568d2655e5644d21652b228a'),
    ('main', 'w'): (15941632, '2c10022fd1d89785ec620f695ca4acd1d7d1feae20e9622b73ea521670100e5a'),
    ('main', 'x1'): (10502144, '9406ec53f3d778d426f7f198cda53eb37046994c2dcd12a674fa034bb9a142d2'),
    ('subsdk0', 'x0'): (3506176, '70f014733c7d72aefbf4ec8461948ef697ee174805420a1f35c60726d69b3b15'),
    ('subsdk0', 'w'): (3244032, '0abf7c6f9e4c883b24db896b3e7ade3d555a1e0e95f102501724051ee5932f6a'),
    ('subsdk0', 'x1'): (409600, '1f3d3b15b14e2eeb5eca16b0d18c3d5c1b6498b9fa3fb7d38573db99ef2d4fa7'),
    ('sdk', 'x0'): (6701056, '0b78c4a70546f5f4d800934439ac4fadd17bfc394301ff3945499d464e0501d9'),
    ('sdk', 'w'): (6275072, 'cdc7754ef82d594a6989c00b533766631017f2ef71f575ef4fd28986218f6769'),
    ('sdk', 'x1'): (1441792, '63c334048e97ff6cd0194af2c56638e08eaf70725bd1ed23731713f4ef9caa41'),
}


class RecoverError(Exception):
    pass


def require(ok, message):
    if not ok:
        raise RecoverError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def u32(data, off):
    return struct.unpack_from('<I', data, off)[0]


def page_up(n):
    return (n + PAGE - 1) & ~(PAGE - 1)


def branch_target(word, pc):
    """Where a B instruction at pc goes, None for any other instruction."""
    if word & 0xfc000000 != 0x14000000:
        return None
    imm = word & 0x3ffffff
    return pc + ((imm ^ 0x2000000) - 0x2000000) * 4


def layout_pins(layout):
    """(name, part) -> (size, SHA-256) of a layout gen_embed.py --layout-of wrote (its JSON, read)."""
    return {(m['name'], part): (m[part]['size'], m[part]['sha256']) for m in layout['modules'] for part in ('x0', 'w', 'x1')}


def old_modules(exe):
    """The tables 30a1b93's prepare_runtime.py compiled into the app (a macho.MachO): Module (192 bytes), Symbol (40),
    Reloc and Gate (24, the layouts of runtime/runtime.h)."""
    require('_modules' in exe.symbols, 'the app executable has no _modules: not an app built at 30a1b93 (its tables were '
            'compiled in)' + ('' if exe.symbols else '; it has no symbol table (stripped)'))
    modules = []
    for i, name in enumerate(NAMES):
        at = exe.symbol('_modules') + 192 * i
        q = [exe.u64(at + 8 * k) for k in range(13)]
        m = dict(name=exe.cstring(exe.pointer(at)), digest=exe.cstring(exe.pointer(at + 8)), file_size=q[2],
                 text_end=q[4], ro_off=q[5], data_off=q[6], patch_off=q[7], key_off=q[8], init=q[9], ctor_flag=q[10],
                 init_array=q[11], init_size=q[12], nsym=exe.u32(at + 112))
        require(m['name'] == name, f'_modules[{i}] is {m["name"]!r}, not {name}')
        symbols, nsym = exe.pointer(at + 104), m['nsym']
        m['symbols'] = [(exe.cstring(exe.pointer(symbols + 40 * k)),
                         *struct.unpack_from('<QQIII', exe.read(symbols + 40 * k + 8, 28))) for k in range(nsym)]
        m['relocs'] = list(struct.iter_unpack('<QIIq', exe.read(exe.pointer(at + 120), 24 * exe.u32(at + 128))))
        m['gates'] = list(struct.iter_unpack('<QQII', exe.read(exe.pointer(at + 136), 24 * exe.u32(at + 144))))
        modules.append(m)
    return modules


def restore_main_text(x0, layout, sites=EXPORT_SITES, aspect=ASPECT_SITES):
    """main's text as the rewriter left it: each patched site gets its original instruction back, and the veneers in
    [TEXT_END, RO_OFF) are cleared. Returns the text and the sites put back."""
    text, restored = bytearray(x0), []
    for site, original in sorted(sites.items()):
        require(site + 4 <= layout['text_end'], f'main+{site:#x} is outside the text')
        if u32(text, site) != original:
            struct.pack_into('<I', text, site, original)
            restored.append(site)
    stubs = ((layout['text_end'] + 15) & ~15) + ASPECT_STUBS
    for i, site in enumerate(aspect):
        stub = stubs + ASPECT_STUB * i
        if branch_target(u32(text, site), site) == stub:
            text[site:site + 4] = text[stub:stub + 4]
            restored.append(site)
    text[layout['text_end']:layout['ro_off']] = bytes(layout['ro_off'] - layout['text_end'])
    return bytes(text), sorted(restored)


def key_names():
    """The key page slots, in the order patch_nso.py numbers them (KEY_INDEX), for fixups.tsv."""
    source = (GAME / 'third_party/d2r/patch_nso.py').read_text(encoding='utf-8')
    found = re.search(r"^KEY_INDEX = \{k: i for i, k in enumerate\(\(([^)]*)\)\)\}", source, re.M)
    require(found, 'patch_nso.py no longer declares KEY_INDEX as this tool reads it')
    return re.findall(r"'(\w+)'", found.group(1))


def fixups_lines(m):
    """<module>.fixups.tsv as patch_nso.py writes it."""
    return [f'# PATCH_OFF\t{m["patch_off"]:#x}', f'# KEY_PAGE_OFF\t{m["key_off"]:#x}', '# KEY_PAGE_SIZE\t0x4000',
            f'# TEXT_END\t{m["text_end"]:#x}', f'# RO_OFF\t{m["ro_off"]:#x}', f'# DATA_OFF\t{m["data_off"]:#x}',
            *(f'# KEY_{k}_IDX\t{i}' for i, k in enumerate(key_names()))]


def check_layout(m, x0, w, x1):
    """The checks runtime/loader.c map_module makes on the sections, and the layout patch_nso.py gives the image."""
    require(len(x0) == page_up(m['text_end']) and len(x0) + len(w) == m['patch_off']
            and m['patch_off'] + len(x1) == page_up(m['file_size']), f'{m["name"]}: the embedded sections do not fit the module layout')
    require(m['text_end'] <= m['ro_off'] <= m['data_off'] <= m['key_off'] and m['key_off'] % PAGE == 0
            and m['patch_off'] % 0x10000 == 0 and m['key_off'] + PAGE <= m['patch_off'] < m['key_off'] + PAGE + 0x10000,
            f'{m["name"]}: TEXT_END/RO_OFF/DATA_OFF/KEY_PAGE_OFF/PATCH_OFF are not a rewriter layout')


def image_tables(image, m):
    """Symbols, relocations, constructor flag and init tags of a rewritten image, made as scripts/prepare_runtime.py makes
    them. A module with a GNU hash only gives no symbol count of its own: the old table's is used and bounded."""
    need = lambda ok, what: require(ok, f'{m["name"]}: {what}')
    mod0 = u32(image, 4)
    need(image[mod0:mod0 + 4] == b'MOD0', 'no MOD0 header')
    dyn, tags = mod0 + struct.unpack_from('<i', image, mod0 + 4)[0], {}
    for off in range(dyn, dyn + 4096 * 16, 16):
        tag, value = struct.unpack_from('<qQ', image, off)
        if tag == 0:
            break
        tags[tag] = value
    else:
        raise RecoverError(f'{m["name"]}: unterminated dynamic table')
    need(tags.get(11) == 24 and tags.get(9) == 24 and tags.get(20) == 7, 'unexpected dynamic entry sizes')
    nsym = u32(image, tags[4] + 4) if 4 in tags else m['nsym']
    need(0 < nsym * 24 <= m['data_off'] - tags[6], f'{nsym} symbols do not fit before the data segment')
    symbols = []
    for i in range(nsym):
        no, info, _, section, value, size = struct.unpack_from('<IBBHQQ', image, tags[6] + 24 * i)
        end = image.index(0, tags[5] + no, tags[5] + tags[10])
        symbols.append((image[tags[5] + no:end].decode(), value, size, int(bool(section)), info >> 4, info & 15))
    relocs = [(where, 1027, 0, addend) for where, addend in decode_relr(image, tags, m['data_off'], m['key_off'])]
    relocated = {r[0] for r in relocs}
    for address, size in [(tags[7], tags[8]), (tags[23], tags[2])]:
        need(size % 24 == 0, 'relocation table size')
        for off in range(address, address + size, 24):
            where, info, addend = struct.unpack_from('<QQq', image, off)
            kind, si = info & 0xffffffff, info >> 32
            need(kind in (257, 1025, 1026, 1027) and si < nsym and m['data_off'] <= where <= m['key_off'] - 8
                 and (kind != 1027 or 0 <= addend < m['key_off']) and where not in relocated, f'relocation at {where:#x}')
            relocated.add(where)
            relocs.append((where, kind, si, addend))
    a, w = u32(image, tags[12] + 16), u32(image, tags[12] + 20)   # 1.4.3's DT_INIT state load: x19, load at +20
    need(a & 0x9f00001f == 0x90000013 and w & 0xffc003ff == 0xb9400268, 'DT_INIT does not load its state flag as 1.4.3 does')
    imm = ((a >> 29) & 3) | (((a >> 5) & 0x7ffff) << 2)
    ctor_flag = ((tags[12] + 16) & ~4095) + (((imm ^ (1 << 20)) - (1 << 20)) << 12) + ((w >> 10) & 0xfff) * 4
    need(m['data_off'] <= ctor_flag < m['key_off'], 'constructor flag outside data')
    return dict(symbols=symbols, relocs=relocs, ctor_flag=ctor_flag, init=tags.get(12, 0), init_array=tags.get(25, 0),
                init_size=tags.get(27, 0), dt_hash=4 in tags, dynstr_follows=tags[5] == tags[6] + 24 * nsym)


def check_gates(image, m):
    """A gate block's return address follows its blr x30, and the original site branches into the patch area before it
    (patch_nso.py site_gate). Returns the gates sorted by return address, as runtime_dispatch searches them."""
    for ret, original, timer, _ in m['gates']:
        target = branch_target(u32(image, original), original) if original + 4 <= m['text_end'] else None
        require(timer in (0, 1) and target is not None and m['patch_off'] <= target < ret < m['file_size']
                and u32(image, ret - 4) == BLR_X30,
                f'{m["name"]}: gate {ret:#x} (site {original:#x}) is not a gate block of this image')
    gates = sorted(m['gates'])
    require(len({g[0] for g in gates}) == len(gates), f'{m["name"]}: two gates with one return address')
    return gates


def probe_stub(image, text_end, slot):
    """main's original PLT stub that loads the GetSystemTick slot (prepare_runtime.py)."""
    found = []
    for address in range(text_end - 0x10000, text_end - 12, 4):
        a, b, _, d = struct.unpack_from('<IIII', image, address)
        if a & 0x9f00001f != 0x90000010 or b & 0xffc003ff != 0xf9400211 or d != 0xd61f0220:
            continue
        imm = ((a >> 29) & 3) | (((a >> 5) & 0x7ffff) << 2)
        if (address & ~4095) + (((imm ^ (1 << 20)) - (1 << 20)) << 12) + ((b >> 10) & 0xfff) * 8 == slot:
            found.append(address)
    require(len(found) == 1, f'main: {len(found)} PLT stubs load the GetSystemTick slot')
    return found[0]


def recover_module(exe, m, embed, pin):
    """One module's three sections, checked against the app's ios_embed hashes (embed) and APP_SECTIONS, and the
    rewritten image made from them, which must be pin; the image's tables must be the app's. Returns the image, the
    sections, the sites put back and the image's own tables."""
    name = m['name']
    require(m['digest'] == pin, f'{name}: the app was built for the rewrite {m["digest"][:16]}..., this repository pins {pin[:16]}...')
    parts = {part: exe.section_bytes(*key) for part, key in macho.module_sections(name).items()}
    check_layout(m, parts['x0'], parts['w'], parts['x1'])
    for part, data in parts.items():
        require(digest(data) == embed[name][part], f'{name} {part}: the section is not what the app\'s _ios_embed names')
        require(APP_SECTIONS.get((name, part)) == (len(data), digest(data)),
                f'{name} {part}: the section is not the one the app 30a1b93 built has (APP_SECTIONS)')
    text, restored = restore_main_text(parts['x0'], m) if name == 'main' else (parts['x0'], [])
    image = (text + parts['w'] + parts['x1'])[:m['file_size']]
    require(digest(image) == pin, f'{name}: the module made from the app\'s sections ({len(restored)} patch sites put back) '
            f'is {digest(image)[:16]}..., not the pinned rewrite {pin[:16]}...: an app of another build')
    found = image_tables(image, m)
    for key in ('symbols', 'relocs', 'ctor_flag', 'init', 'init_array', 'init_size'):
        require(found[key] == m[key], f'{name}: the app\'s {key} differ from what prepare_runtime.py makes of the pinned image')
    m['gates'] = check_gates(image, m)
    return dict(image=image, parts=parts, restored=restored, found=found)


def table_module(m):
    """A module record of old_modules as prepare_runtime.table_bytes takes a module."""
    return dict(name=m['name'], sha256=m['digest'], size=m['file_size'], ctor_flag=m['ctor_flag'],
                layout=dict(TEXT_END=m['text_end'], RO_OFF=m['ro_off'], DATA_OFF=m['data_off'], PATCH_OFF=m['patch_off'],
                            KEY_PAGE_OFF=m['key_off']),
                tags={12: m['init'], 25: m['init_array'], 27: m['init_size']},
                symbols=[dict(name=n, value=v, size=s, defined=d, binding=b, type=t) for n, v, s, d, b, t in m['symbols']],
                relocs=[dict(where=w, kind=k, symbol=s, addend=a) for w, k, s, a in m['relocs']],
                gates=[dict(ret=r, original=o, timer=t, arg=a) for r, o, t, a in m['gates']])


def runtime_tables(modules, main_image):
    """runtime-tables.bin of the modules (prepare_runtime.table_bytes), with main's GetSystemTick slot and the original
    PLT stub that loads it (main_image: the rewritten main) found as prepare_runtime.py finds them."""
    main = modules[0]
    slot = next(r[0] for r in main['relocs'] if main['symbols'][r[2]][0] == GET_SYSTEM_TICK and r[1] == 1026)
    return prepare_runtime.table_bytes(VERSION, [table_module(m) for m in modules], probe_stub(main_image, main['text_end'], slot), slot)


def embed_header_hashes(text):
    """name -> {x0, w, x1} from an ios_embed.h that gen_embed.py wrote."""
    rows = re.findall(r'\{"(\w+)","([0-9a-f]{64})","([0-9a-f]{64})","([0-9a-f]{64})"\},', text)
    return {n: dict(x0=a, w=b, x1=c) for n, a, b, c in rows}
