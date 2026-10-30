#!/usr/bin/env python3
"""Make a RomFS mod that changes equipment durability and the Zonai battery, from the player's own RomFS.

What each option edits (Tears of the Kingdom 1.4.3; other versions are untested):
  --durability K        MaxLife times K in Life/LifeParameters/Weapon_{Sword,Lsword,Spear,Shield,Bow}_* of every pack that
                        carries such a member, and in the rows of RSDB/GameActorInfo named after those packs' actors. The
                        results are whole numbers from 1 to MAX_DURABILITY. A save keeps each item's durability, so only
                        items obtained after the mod is in get the new maximum.
  --battery-drain D     every entry of ZonauEnergy_CostRate divided by D, in Player's ConditionParam (index 0 is very likely
                        the rate without Zonaite armor, the others its levels). The game's code rounds a device's drain to
                        whole units per second; the slowest device found uses 15, so with the last entry at 0.5 a D above
                        15 could round its drain to nothing. The save's battery size stays as it is.
  --battery-recharge R  every entry of ZonauEnergy_HealRate times R, in the same member (index 1 is very likely the Zonaite
                        armor set bonus). The game's code does energy += MaxEnergy / 3000 * (rate * 150) * dt. The pause
                        before the battery recharges is a constant in that code, so it stays.

No option changes the wear per hit, so nothing here reaches items already owned. DamageRates.Durability in the
EquipmentCommon and ShieldCommon members looks like the place, but 1.4.3's code reads that rate only for an incoming attack
of the type Durability, and none was found. A melee hit costs a literal 1 (main+0x1cc4998) that no rate scales.

Rules: values change in place, so the unpacked sizes stay and the resource size table needs no change. Every pack under
Pack/ is read, and every copy of a member path gets the same edit. A run always starts from the original image, so
values never compound; a file already in the mod folder is never read for its values. Only files that differ from the
original are written. A file this tool wrote earlier and no longer needs is removed. A file in the mod folder that differs
from the original in anything but the values this tool edits is another mod's: the run stops before it writes anything,
unless --replace is given. Each frame keeps the original's zstd dictionary and declares its content size. The run ends
with make_mod_manifest.py's manifest over the whole folder, so the folder may hold other files (a button icon mod's).

--slots builds the four folders <version>-off, -moderate, -strong and -max that the Settings pane's mod slot row chooses
between (ios/Settings.bundle TOTK_MOD_SLOT, ios/Sources/main.m, values in SLOTS): each one is a copy of --base with that
slot's values, with its own manifest. A slot folder is built beside its old one and then takes its place; a folder of that
name this tool did not make stops the run.

.gameplay-tuning.json in the mod folder records the values; its leading dot keeps it out of the manifest and off the device.
The output holds files made from the game's own: keep it out of the repository.

Needs Python 3.14 (compression.zstd).
usage: make_gameplay_tuning.py --romfs <folder | romfs.bin> --into <mod folder> [--durability 5] [--battery-drain 3]
                               [--battery-recharge 3] [--replace]
       make_gameplay_tuning.py --romfs <folder | romfs.bin> --slots <folder> --base <mod folder> [--version v143]
"""
import argparse
from collections import namedtuple
import json
import math
from pathlib import Path
import re
import shutil
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))   # python -I leaves the script's own folder out
import make_mod_manifest   # noqa: E402
from make_mod_manifest import VERSIONS, read_index, romfs_folder, write_mod_manifest   # noqa: E402
from romfs_formats import ZSDIC_PACK, Byml, compress_like, decompress, sarc_members, zstd_dictionaries   # noqa: E402

WEAPON_LIFE = re.compile(r'Life/LifeParameters/Weapon_(Sword|Lsword|Spear|Shield|Bow)_[^/]+\.game__life__LifeParameters\.bgyml')
PLAYER_CONDITION = 'Component/ConditionParam/Player.game__component__ConditionParam.bgyml'
PACK = re.compile(r'Pack/.+\.pack\.zs')
ACTOR_INFO = re.compile(r'RSDB/GameActorInfo\.Product\.\d+\.rstbl\.byml\.zs')
MAX_DURABILITY = 100000
RECORD = '.gameplay-tuning.json'
UNREADABLE = (AssertionError, IndexError, KeyError, ValueError, struct.error)   # what the format code raises on a damaged file

Tuning = namedtuple('Tuning', 'durability drain recharge', defaults=(1, 1, 1))
Tuning.__doc__ = """The values of one mod: durability and recharge multiply, drain divides."""

# The Settings pane's slots, in its order.
SLOTS = {'off': Tuning(),
         'moderate': Tuning(durability=3, drain=2, recharge=2),
         'strong': Tuning(durability=5, drain=3, recharge=3),
         'max': Tuning(durability=10, drain=5, recharge=5)}

Value = namedtuple('Value', 'setting offset format')
Value.__doc__ = """One 4-byte field this tool edits: the Tuning field that sets it, its offset in the unpacked file and its
    struct format."""
Target = namedtuple('Target', 'path stored data values')
Target.__doc__ = """A RomFS file holding such fields: its path, its original stored and unpacked bytes, and its Values."""
Original = namedtuple('Original', 'romfs index dictionaries targets')
Original.__doc__ = """What a run takes from the RomFS: its folder, its index, the zstd dictionaries and the Targets."""


class TuningError(Exception):
    pass


def life_fields(doc):
    return [('durability', doc.field(doc.root, 'MaxLife', Byml.INT), '<i')]


def battery_fields(doc):
    out = []
    for key, setting in (('ZonauEnergy_CostRate', 'drain'), ('ZonauEnergy_HealRate', 'recharge')):
        for kind, field in doc.items(doc.child(doc.root, key, Byml.ARRAY)):
            if kind != Byml.FLOAT:
                raise ValueError(f'{key} holds kind {kind:#x}, not floats')
            out.append((setting, field, '<f'))
    return out


def member_fields(name):
    """The function that lists the fields this tool edits in the pack member `name`, or None for any other member."""
    if WEAPON_LIFE.fullmatch(name):
        return life_fields
    return battery_fields if name == PLAYER_CONDITION else None


def pack_values(data):
    """The Values of an unpacked pack."""
    values = []
    for name, (lo, hi) in sarc_members(data).items():
        fields = member_fields(name)
        if fields:
            values += [Value(setting, lo + at, form) for setting, at, form in fields(Byml(data[lo:hi]))]
    return values


def row_values(data, actors):
    """The MaxLife Values of the rows of an unpacked GameActorInfo table named after one of `actors`."""
    doc = Byml(data)
    values = []
    for _, field in doc.items(doc.root):
        row = doc.entries(struct.unpack_from('<I', data, field)[0])
        name = doc.string(row['__RowId'][1]) if '__RowId' in row else None
        if name in actors and 'MaxLife' in row:
            kind, at = row['MaxLife']
            if kind != Byml.INT:
                raise ValueError(f'row {name}: MaxLife holds kind {kind:#x}, not an int')
            values.append(Value('durability', at, '<i'))
    return values


def read_original(romfs):
    """The Original of the RomFS folder `romfs`: every pack is read, since any of them may carry a copy of a member."""
    index = read_index(romfs/'runtime-index.bin')
    with make_mod_manifest.image_file(romfs).open('rb') as image:
        def read(path):
            offset, size = index[path]; image.seek(offset); data = image.read(size)
            if len(data) != size:
                raise TuningError(f'{image.name}: {path} is {size} bytes at offset {offset}, and the image holds only '
                                  f'{len(data)} of them: the image is damaged or incomplete')
            return data
        if ZSDIC_PACK not in index:
            raise TuningError(f'{romfs} holds no {ZSDIC_PACK}: is this Tears of the Kingdom\'s RomFS?')
        try:
            dictionaries = zstd_dictionaries(read(ZSDIC_PACK))
        except UNREADABLE as error:
            raise TuningError(f'{ZSDIC_PACK}: {error!r}') from error
        packs = sorted(p for p in index if PACK.fullmatch(p) and p != ZSDIC_PACK)
        tables = sorted(p for p in index if ACTOR_INFO.fullmatch(p))
        targets, actors = [], set()
        for path in packs + tables:   # the packs first: the table's rows are their actors'
            stored = read(path)
            try:
                data = decompress(stored, dictionaries)
                values = row_values(data, actors) if ACTOR_INFO.fullmatch(path) else pack_values(data)
            except UNREADABLE as error:
                raise TuningError(f'{path}: {error!r}') from error
            if values:
                targets.append(Target(path, stored, data, values))
            if PACK.fullmatch(path) and any(v.setting == 'durability' for v in values):
                actors.add(path.rsplit('/', 1)[1].removesuffix('.pack.zs'))
    return Original(romfs, index, dictionaries, targets)


def tuned(setting, old, tuning):
    """The new value of a field of `setting` that holds `old`. Durability only scales what is above zero."""
    if setting == 'durability':
        factor = tuning.durability
        return old if factor == 1 or old <= 0 else min(MAX_DURABILITY, max(1, math.floor(old * factor + 0.5)))
    if setting == 'drain':
        return old / tuning.drain
    return old * tuning.recharge


def edited(target, tuning):
    """The target's unpacked bytes with `tuning` applied to the original values."""
    out = bytearray(target.data)
    for value in target.values:
        old = struct.unpack_from(value.format, target.data, value.offset)[0]
        struct.pack_into(value.format, out, value.offset, tuned(value.setting, old, tuning))
    return bytes(out)


def differs_only_in_values(stored, target, dictionaries):
    """Whether the zstd file `stored` holds the target's original bytes, its value fields aside."""
    try:
        data = decompress(stored, dictionaries)
    except ValueError:
        return False
    at = 0
    for offset in sorted(value.offset for value in target.values):
        if data[at:offset] != target.data[at:offset]:
            return False
        at = offset + 4
    return len(data) == len(target.data) and data[at:] == target.data[at:]


def plan(mod, original, tuning, replace):
    """[(target, its new unpacked bytes, the bytes of its file in the mod folder or None, whether this tool could have
    written that file)], and the files of other mods this tuning would have to overwrite."""
    changes, refused = [], []
    for target in original.targets:
        data = edited(target, tuning)
        file = mod/target.path
        stored = file.read_bytes() if file.is_file() else None
        ours = stored is not None and differs_only_in_values(stored, target, original.dictionaries)
        if stored is not None and not ours and data != target.data and not replace:
            refused.append(str(file))
        changes.append((target, data, stored, ours))
    return changes, refused


def refused_message(refused):
    """What stops a run that would overwrite the other mods' files `refused`."""
    return (f'{", ".join(refused[:5])}{" and others" if len(refused) > 5 else ""}: differ(s) from the original in more than '
            'the values this tool edits (another mod\'s file): nothing written')


def apply_tuning(mod, original, tuning, replace=False):
    """Bring the mod folder's tuned files in line with `tuning`. Returns (files written, bytes written, files already
    right, files removed)."""
    changes, refused = plan(mod, original, tuning, replace)
    if refused:
        raise TuningError(f'{refused_message(refused)}; pass --replace to overwrite')
    written, size, same, removed = 0, 0, 0, 0
    for target, data, stored, ours in changes:
        file = mod/target.path
        if data == target.data:
            if ours:
                file.unlink(); removed += 1
            continue
        packed = compress_like(data, target.stored, original.dictionaries)
        if packed == stored:
            same += 1
            continue
        file.parent.mkdir(parents=True, exist_ok=True); file.write_bytes(packed)
        written += 1; size += len(packed)
    return written, size, same, removed


def summary(original, tuning):
    """One line per setting: how many values, in how many packs and table rows, and the range before and after."""
    labels = {'durability': f'maximum durability x{tuning.durability:g}', 'drain': f'battery drain /{tuning.drain:g}',
              'recharge': f'battery recharge x{tuning.recharge:g}'}
    lines = []
    for setting, label in labels.items():
        found = [(t, v) for t in original.targets for v in t.values if v.setting == setting]
        if not found:
            lines.append(f'{label}: no such value in this RomFS')
            continue
        before = [struct.unpack_from(v.format, t.data, v.offset)[0] for t, v in found]
        after = [tuned(setting, old, tuning) for old in before]
        packs = {t.path for t, _ in found if PACK.fullmatch(t.path)}
        rows = sum(1 for t, _ in found if ACTOR_INFO.fullmatch(t.path))
        changed = sum(a != b for a, b in zip(after, before))
        lines.append(f'{label}: {changed} of {len(found)} values changed (packs: {len(packs)}, table rows: {rows}), '
                     f'{min(before):g}..{max(before):g} -> {min(after):g}..{max(after):g}')
    return lines


def check_found(original, tuning):
    """Stop when a setting that changes something found no value: this is not the RomFS the tool knows."""
    wanted = {'durability': tuning.durability != 1, 'drain': tuning.drain != 1, 'recharge': tuning.recharge != 1}
    found = {v.setting for t in original.targets for v in t.values}
    missing = [setting for setting, wants in wanted.items() if wants and setting not in found]
    if missing:
        raise TuningError(f'{original.romfs} holds no value for: {", ".join(missing)}: is this Tears of the Kingdom\'s RomFS?')


def make_mod(mod, original, tuning, replace=False, slot=None, base=None):
    """Write `tuning` into the mod folder, then its manifest and its record."""
    check_found(original, tuning)
    mod.mkdir(parents=True, exist_ok=True)
    written, size, same, removed = apply_tuning(mod, original, tuning, replace)
    for line in summary(original, tuning):
        print(line)
    print(f'{mod}: {written} files written ({size / 2**20:.1f} MiB), {same} already right, {removed} removed')
    try:
        _, found = write_mod_manifest(mod, original.romfs, original.index)
    except ValueError as error:
        raise TuningError(f'manifest not written: {error}') from error
    if found.misspelt:
        raise TuningError('manifest not written: ' + ', '.join(f'{a} (the RomFS has {b})' for a, b in found.misspelt))
    record = dict(tool='make_gameplay_tuning.py', slot=slot, durability=tuning.durability, battery_drain=tuning.drain,
                  battery_recharge=tuning.recharge, base=str(base) if base else None)
    (mod/RECORD).write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f'{mod/"manifest.tsv"}: {len(found.lines)} files ({len(found.lines) - len(found.added)} replaced, {len(found.added)} added)')


def build_slots(folder, base, version, original):
    """The folder <version>-<slot> below `folder` for every slot: a copy of the mod folder `base` with the slot's values."""
    slots = {slot: folder/f'{version}-{slot}' for slot in SLOTS}
    foreign = [str(path) for path in slots.values() if path.exists() and not (path/RECORD).is_file()]
    if foreign:
        raise TuningError(f'{", ".join(foreign)}: not made by this tool (no {RECORD}): move it away, nothing written')
    for tuning in SLOTS.values():
        refused = plan(base, original, tuning, False)[1]
        if refused:
            raise TuningError(f'{refused_message(refused)}; a slot cannot hold it, so take it out of {base}')
    for slot, tuning in SLOTS.items():
        target, staging, previous = slots[slot], folder/f'.{slots[slot].name}.new', folder/f'.{slots[slot].name}.old'
        print(f'--- slot {slot}')
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(base, staging)
        make_mod(staging, original, tuning, slot=slot, base=base)
        if target.exists():
            shutil.rmtree(previous, ignore_errors=True)
            target.rename(previous)
        staging.rename(target)
        shutil.rmtree(previous, ignore_errors=True)
        print(f'{target}: ready')


def multiplier(text):
    value = float(text)
    if not 0.1 <= value <= 100:
        raise argparse.ArgumentTypeError(f'{text}: give a number from 0.1 to 100')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--romfs', type=Path, required=True, help='a folder holding romfs.bin and runtime-index.bin, or that '
                        'romfs.bin (extracted/<version>/romfs; the build\'s overlay is the romfs-patches folder beside it)')
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument('--into', type=Path, metavar='FOLDER', help='the mod folder to write into (it is created when missing; '
                        'other files in it are kept and listed in the manifest)')
    output.add_argument('--slots', type=Path, metavar='FOLDER', help='build the folders <version>-<slot> of the four slots here')
    parser.add_argument('--base', type=Path, help='with --slots: the mod folder each slot starts from (the button icon mod)')
    parser.add_argument('--version', choices=VERSIONS, default='v143', help='with --slots: the first part of the folder names')
    parser.add_argument('--durability', type=multiplier, help='maximum durability of weapons, shields and bows times this')
    parser.add_argument('--battery-drain', type=multiplier, help='battery drain divided by this')
    parser.add_argument('--battery-recharge', type=multiplier, help='battery recharge times this')
    parser.add_argument('--replace', action='store_true', help='overwrite another mod\'s copy of a file this tool edits')
    args = parser.parse_args()
    values = (args.durability, args.battery_drain, args.battery_recharge)
    if args.slots and (any(v is not None for v in values) or args.replace):
        parser.error('--slots takes its values from the slots\' table; --durability, --battery-drain, --battery-recharge '
                     'and --replace go with --into')
    if args.slots and not (args.base and (args.base/'manifest.tsv').is_file()):
        parser.error('--slots needs --base, a mod folder with its manifest.tsv')
    if args.into and args.base:
        parser.error('--base goes with --slots')
    if args.into and all(v is None for v in values):
        parser.error('name at least one of --durability, --battery-drain and --battery-recharge')
    romfs = romfs_folder(args.romfs)
    for need in (make_mod_manifest.image_file(romfs), romfs/'runtime-index.bin'):
        if not need.is_file():
            parser.error(f'{need} not found')
    try:
        original = read_original(romfs)
        if args.slots:
            args.slots.mkdir(parents=True, exist_ok=True)
            build_slots(args.slots, args.base, args.version, original)
        else:
            make_mod(args.into, original, Tuning(*(1 if v is None else v for v in values)), args.replace)
    except (TuningError, ValueError, OSError) as error:
        sys.exit(str(error))


if __name__ == '__main__':
    main()
