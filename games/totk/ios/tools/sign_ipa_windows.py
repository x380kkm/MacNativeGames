#!/usr/bin/env python3
"""Sign the iPhone/iPad app with zsign on a machine without Xcode (Windows; also Linux and macOS), and check a signed IPA
without the device. install_device.py does the same with Xcode and codesign on a Mac.

  python sign_ipa_windows.py <folder holding Payload/TOTK.app | unsigned .ipa> --out <signed.ipa>
         --p12 <certificate.p12> --p12-password-file <file> --profile <profile.mobileprovision>
  python sign_ipa_windows.py --verify <signed.ipa> --profile <profile.mobileprovision> [--p12 ... --p12-password-file ...]
  python sign_ipa_windows.py --verify <name>-unsigned.ipa --adhoc

Before it signs, the profile must cover the app's bundle identifier, be valid for iOS and not expired, list the p12's
certificate in DeveloperCertificates, and grant get-task-allow and every entitlement of ios/Sources/TOTK.entitlements
(increased-memory-limit: the game's 3.2 GiB pool is above the default iOS limit). The app is signed with the four
entitlements install_device.py takes from the profile.

The p12 password is read from a file (or TOTK_P12_PASSWORD, or asked for) and handed to openssl through its environment,
never on a command line: openssl writes the private key re-encrypted with a one-time passphrase into a private temporary
folder, and only that passphrase goes to zsign (-p), whose command is shown with it masked. The folder is removed when
zsign is done. openssl: --openssl or $TOTK_OPENSSL, else the first of PATH's and Git for Windows' two that reads the p12
(OpenSSL 3 reads a p12 exported by Keychain Access, RC2-encrypted, only with its legacy provider, tried second; Git's
mingw64 openssl has that provider, its MSYS one not).

zsign writes no Unix modes into the IPA on Windows; set_unix_modes gives the entries those of a Mac build (0755 for the
executable and folders). zsign 1.1.2 on Windows seals a file of 4 GiB or more with the hash of its first size mod 4 GiB
bytes (large_files), so an app holding one is refused: the 17 GB RomFS image goes to the device's Documents instead
(push_device_windows.py).

--verify (and every signing run, on its output) reads the signed executable's code signature: the code directory's page
hashes over the whole file (so the game sections written in after the link are covered), its identifier and team, the
Info.plist and CodeResources hashes in its special slots, the entitlements blob, and the signer certificate in its CMS
signature; then every file against _CodeSignature/CodeResources, and embedded.mobileprovision against the profile."""
import argparse, base64, datetime, getpass, hashlib, os, plistlib, re, secrets, shutil, struct, subprocess, sys, tempfile, zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import macho   # noqa: E402  the executable's load commands

APP_ENTITLEMENTS = TOOLS.parent/'Sources/TOTK.entitlements'
MEMORY = 'com.apple.developer.kernel.increased-memory-limit'
SIGNED_KEYS = ('application-identifier', 'com.apple.developer.team-identifier', 'get-task-allow', MEMORY)
ZSIGN_FILE_LIMIT = 1 << 32
# Git for Windows' two: the mingw64 one carries the legacy provider a Keychain Access p12 (RC2) needs, the MSYS one not.
GIT_OPENSSL = (r'C:\Program Files\Git\mingw64\bin\openssl.exe', r'C:\Program Files\Git\usr\bin\openssl.exe')


class SignError(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise SignError(message)


def tools(name, given, env, fallbacks=()):
    """The paths a command-line tool may be at, in order: --<name> (or $env) alone when given, else PATH, then the usual
    install places."""
    chosen = given or os.environ.get(env)
    found = [chosen] if chosen else [shutil.which(name), *fallbacks]
    paths = list(dict.fromkeys(str(Path(c)) for c in found if c and Path(c).is_file()))
    require(paths, f'{name} not found: pass --{name} <path> or set {env}')
    return paths


def tool(name, given, env, fallbacks=()):
    return tools(name, given, env, fallbacks)[0]


def p12_openssl(given, p12, password):
    """(an openssl that reads the p12, the DER of its certificate): the first of the candidates that can."""
    error = None
    for openssl in tools('openssl', given, 'TOTK_OPENSSL', GIT_OPENSSL):
        try:
            return openssl, p12_certificate(openssl, p12, password)
        except SignError as e:
            error = e
    raise error


def read_profile(path):
    """(the file's bytes, its plist): a profile is CMS signed data whose content is the plist, stored as it is."""
    raw = Path(path).read_bytes()
    start, end = raw.find(b'<?xml'), raw.find(b'</plist>')
    require(start >= 0 and end > start, f'{path}: no property list in the profile')
    return raw, plistlib.loads(raw[start:end + len(b'</plist>')])


def app_identifier_matches(granted, team, bundle_id):
    return granted == f'{team}.{bundle_id}' or (granted.endswith('.*') and f'{team}.{bundle_id}'.startswith(granted[:-1]))


def signing_entitlements(profile, bundle_id, needed, now=None):
    """The entitlements the app is signed with, after checking the profile grants what the app needs."""
    now = now or datetime.datetime.now(datetime.UTC).replace(tzinfo=None)   # plistlib dates are naive UTC
    ents, team = profile.get('Entitlements', {}), (profile.get('TeamIdentifier') or ['?'])[0]
    require('iOS' in profile.get('Platform', []), f'the profile is for {profile.get("Platform")}, not iOS')
    require(profile['ExpirationDate'] > now, f'the profile expired on {profile["ExpirationDate"]:%Y-%m-%d} (UTC)')
    require(app_identifier_matches(ents.get('application-identifier', ''), team, bundle_id),
            f'the profile is for {ents.get("application-identifier")}, not {team}.{bundle_id}')
    for key, value in {**needed, 'get-task-allow': True, MEMORY: True}.items():
        require(ents.get(key) == value, f'the profile does not grant {key} = {value!r} (it has {ents.get(key)!r})')
    signed = {k: ents[k] for k in SIGNED_KEYS if k in ents}
    signed['application-identifier'] = f'{team}.{bundle_id}'   # concrete even under a wildcard profile
    return signed


def read_password(path):
    """The p12 password from a file (its line end is not part of it), TOTK_P12_PASSWORD, or the keyboard."""
    if path:
        return Path(path).read_text(encoding='utf-8').rstrip('\r\n')
    if os.environ.get('TOTK_P12_PASSWORD'):
        return os.environ['TOTK_P12_PASSWORD']
    return getpass.getpass('p12 password: ')


def openssl_pkcs12(openssl, p12, password, *args, passout=None):
    """openssl pkcs12 on the p12 with the password in the child's environment only; the legacy provider is tried when the
    p12 uses RC2 (Keychain Access exports). Returns stdout."""
    env = dict(os.environ, TOTK_P12_IN=password)
    if passout is not None:
        env['TOTK_KEY_OUT'] = passout; args = (*args, '-passout', 'env:TOTK_KEY_OUT')
    errors = []
    for legacy in ([], ['-legacy']):
        r = subprocess.run([openssl, 'pkcs12', *legacy, '-in', str(p12), '-passin', 'env:TOTK_P12_IN', *args],
                           env=env, capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout
        errors.append(r.stderr.strip().splitlines()[-1:] or ['?'])
        if 'unsupported' not in r.stderr and 'RC2' not in r.stderr:
            break
    raise SignError(f'openssl could not read {p12} (wrong password?): {errors[-1][0]}')


def pem_certificates(text):
    return [base64.b64decode(''.join(b.split())) for b in
            re.findall(r'-----BEGIN CERTIFICATE-----(.*?)-----END CERTIFICATE-----', text, re.S)]


def p12_certificate(openssl, p12, password):
    """The DER of the p12's own certificate (its key's, not the CA's)."""
    certs = pem_certificates(openssl_pkcs12(openssl, p12, password, '-nokeys', '-clcerts'))
    require(len(certs) == 1, f'{p12} holds {len(certs)} client certificates, not one')
    return certs[0]


def certificate_summary(openssl, der):
    """Subject and expiry of a certificate, as openssl prints them."""
    r = subprocess.run([openssl, 'x509', '-inform', 'DER', '-noout', '-subject', '-enddate'], input=der, capture_output=True)
    return ' '.join(r.stdout.decode(errors='replace').split()) if r.returncode == 0 else '?'


def large_files(root):
    """The files under root zsign cannot seal: zsign 1.1.2 on Windows hashes only the first size mod 4 GiB bytes of a larger
    file into CodeResources (romfs.bin, 17,052,625,232 bytes, got the SHA-256 of its first 4,167,723,344; 2026-10-26)."""
    return [p for p in Path(root).rglob('*') if p.is_file() and p.stat().st_size >= ZSIGN_FILE_LIMIT]


def run_zsign(zsign, args, out, root, secret=None):
    """zsign with args on the folder root (out is the IPA it writes); the command and its output are shown with secret
    masked. zsign keeps a .zsign_cache folder in its working folder, so it runs in a temporary one, removed after."""
    large = large_files(root)
    if large:
        raise SignError(f'zsign cannot sign a file of 4 GiB or more ({large[0]}): its seal would not match the file '
                        '(sign_ipa_windows.large_files)')
    paths = [str(Path(x).resolve()) if isinstance(x, Path) else str(x) for x in args]   # the working folder moves
    cmd = [str(zsign), '-f', *paths]   # -f: sign every file, never from zsign's cache of an earlier run
    shown = ['***' if c == secret else f'"{c}"' if ' ' in c else c for c in cmd]
    print('zsign: ' + ' '.join(shown), flush=True)
    with tempfile.TemporaryDirectory(prefix='totk-zsign-') as cwd:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, errors='replace')
    log = r.stdout + r.stderr
    if secret:
        log = log.replace(secret, '***')
    if r.returncode or not Path(out).is_file():
        raise SignError('zsign failed:\n' + '\n'.join(log.strip().splitlines()[-20:]))
    set_unix_modes(out)
    return log


def set_unix_modes(ipa):
    """Give the entries of an IPA Unix modes, as the zip of a Mac build has them: 0755 for folders and the app's
    executable, 0644 for the rest. zsign on Windows writes none (the files have no such modes there). Only the central
    directory changes, in place: no member is rewritten."""
    with zipfile.ZipFile(ipa) as z:
        plists = [n for n in z.namelist() if re.fullmatch(r'Payload/[^/]+\.app/Info\.plist', n)]
        require(len(plists) == 1, f'{ipa}: not one Payload/<name>.app')
        executable = plists[0][:-len('Info.plist')] + plistlib.loads(z.read(plists[0]))['CFBundleExecutable']
        count = len(z.infolist())
    with open(ipa, 'r+b') as f:
        size = f.seek(0, 2); f.seek(max(0, size - (1 << 16) - 22 - 76)); tail = f.read(); base = size - len(tail)
        at = tail.rfind(b'PK\x05\x06'); require(at >= 0, f'{ipa}: no end of central directory')
        cd_size, cd_off = struct.unpack_from('<II', tail, at + 12)
        if cd_off == 0xffffffff or cd_size == 0xffffffff:   # zip64: the locator just before points at the zip64 record
            loc = tail.rfind(b'PK\x06\x07', 0, at); require(loc >= 0, f'{ipa}: no zip64 locator')
            rec = struct.unpack_from('<Q', tail, loc + 8)[0] - base
            cd_size, cd_off = struct.unpack_from('<QQ', tail, rec + 40)
        f.seek(cd_off); cd = bytearray(f.read(cd_size)); pos = 0
        for _ in range(count):
            require(cd[pos:pos + 4] == b'PK\x01\x02', f'{ipa}: damaged central directory')
            made_by, flags = struct.unpack_from('<HxxH', cd, pos + 4)
            name_len, extra_len, comment_len = struct.unpack_from('<HHH', cd, pos + 28)
            name = bytes(cd[pos + 46:pos + 46 + name_len]).decode('utf-8' if flags & 0x800 else 'cp437')
            folder = name.endswith('/')
            mode = 0o40755 if folder else 0o100755 if name == executable else 0o100644
            struct.pack_into('<H', cd, pos + 4, (3 << 8) | (made_by & 0xff))   # made by: Unix
            struct.pack_into('<I', cd, pos + 38, (mode << 16) | (0x10 if folder else 0))
            pos += 46 + name_len + extra_len + comment_len
        f.seek(cd_off); f.write(cd)


def sign(zsign, openssl, root, out, p12, password, profile_path, entitlements, zip_level=1):
    """zsign root (a folder holding Payload/<name>.app, signed in place) into the IPA out, with the p12's key and
    certificate."""
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True); out.unlink(missing_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='totk-sign-'))   # mkdtemp: readable by this user only
    try:
        onetime = secrets.token_urlsafe(24)
        key = temp/'key.pem'
        openssl_pkcs12(openssl, p12, password, '-nocerts', '-out', str(key), passout=onetime)
        cert = temp/'cert.pem'
        der = p12_certificate(openssl, p12, password)
        cert.write_text('-----BEGIN CERTIFICATE-----\n' + base64.encodebytes(der).decode() + '-----END CERTIFICATE-----\n')
        ents = temp/'entitlements.plist'; ents.write_bytes(plistlib.dumps(entitlements))
        return run_zsign(zsign, ['-k', key, '-p', onetime, '-c', cert, '-m', profile_path, '-e', ents,
                                 '-z', zip_level, '-o', out, root], out, root, secret=onetime)
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def sign_adhoc(zsign, root, out, entitlements_file, zip_level=1):
    """An ad-hoc signature carrying the app's entitlements (as build_ipa.py's codesign --sign -), into the IPA out."""
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True); out.unlink(missing_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='totk-adhoc-'))
    try:
        ents = temp/'entitlements.plist'   # without the file's XML comments
        ents.write_bytes(plistlib.dumps(plistlib.loads(Path(entitlements_file).read_bytes())))
        return run_zsign(zsign, ['-a', '-e', ents, '-z', zip_level, '-o', out, root], out, root)
    finally:
        shutil.rmtree(temp, ignore_errors=True)


CS_SUPERBLOB, CS_DIRECTORY, CS_REQUIREMENTS = 0xfade0cc0, 0xfade0c02, 0xfade0c01
CS_ENTITLEMENTS, CS_DER_ENTITLEMENTS, CS_WRAPPER = 0xfade7171, 0xfade7172, 0xfade0b01
SLOT_INFO, SLOT_RESOURCES, SLOT_ENTITLEMENTS, SLOT_DER = 1, 3, 5, 7
HASHES = {1: hashlib.sha1, 2: hashlib.sha256}


def code_signature(exe):
    """The blobs of a thin 64-bit Mach-O's embedded signature, {magic: [blob bytes]}, and where it starts in the file."""
    try:
        where = [struct.unpack_from('<II', exe, off + 8) for cmd, off, _ in macho.load_commands(exe) if cmd == macho.LC_CODE_SIGNATURE]
    except macho.MachOError as e:
        raise SignError(str(e)) from None
    require(where, 'the executable has no code signature')
    start, _ = where[-1]
    sb_magic, _, count = struct.unpack_from('>III', exe, start)
    require(sb_magic == CS_SUPERBLOB, 'the code signature is not an embedded signature superblob')
    blobs = {}
    for i in range(count):
        _, at = struct.unpack_from('>II', exe, start + 12 + 8 * i)
        b_magic, b_len = struct.unpack_from('>II', exe, start + at)
        blobs.setdefault(b_magic, []).append(exe[start + at:start + at + b_len])
    return blobs, start


def code_directory(blob):
    """The fields of a code directory blob this checks; slot(i) is special slot -i for i > 0, code page -i otherwise."""
    fields = struct.unpack_from('>IIIIIIIBBBB', blob, 8)
    version, flags, hash_off, ident_off, n_special, n_code, limit, hash_size, hash_type, _, page = fields
    team, exec_flags = None, 0
    if version >= 0x20200 and struct.unpack_from('>I', blob, 48)[0]:
        team_off = struct.unpack_from('>I', blob, 48)[0]
        team = blob[team_off:blob.index(b'\0', team_off)].decode()
    if version >= 0x20300:
        limit = struct.unpack_from('>Q', blob, 56)[0] or limit
    if version >= 0x20400:
        exec_flags = struct.unpack_from('>Q', blob, 80)[0]
    def slot(i):
        at = hash_off - i * hash_size
        return blob[at:at + hash_size]
    return dict(version=version, flags=flags, identifier=blob[ident_off:blob.index(b'\0', ident_off)].decode(), team=team,
                n_special=n_special, n_code=n_code, limit=limit, hash_type=hash_type, page=1 << page, slot=slot,
                exec_flags=exec_flags)


def check_executable(exe, info_plist, code_resources, bundle_id, team, cert_der):
    """Problems with an executable's signature (empty when it is sound), and its entitlements. team None: an ad-hoc
    signature is expected (no team, no CMS signer)."""
    blobs, sig_start = code_signature(exe)
    problems = []
    directories = blobs.get(CS_DIRECTORY, [])
    require(directories, 'the code signature has no code directory')
    ent_blob = (blobs.get(CS_ENTITLEMENTS) or [b''])[0]
    entitlements = plistlib.loads(ent_blob[8:]) if ent_blob else {}
    der = (blobs.get(CS_DER_ENTITLEMENTS) or [b''])[0]
    for blob in directories:
        cd = code_directory(blob)
        h = HASHES.get(cd['hash_type'])
        if not h:
            problems.append(f'code directory hash type {cd["hash_type"]} unknown'); continue
        name = h().name
        if cd['identifier'] != bundle_id: problems.append(f'{name} code directory identifier {cd["identifier"]}')
        if cd['team'] != team: problems.append(f'{name} code directory team {cd["team"]}')
        if cd['limit'] != sig_start: problems.append(f'{name} code limit {cd["limit"]:#x}, signature at {sig_start:#x}')
        pages = (cd['limit'] + cd['page'] - 1) // cd['page']
        if cd['n_code'] != pages: problems.append(f'{name} code directory has {cd["n_code"]} pages, the file {pages}')
        bad = [i for i in range(min(pages, cd['n_code']))
               if h(exe[i * cd['page']:min((i + 1) * cd['page'], cd['limit'])]).digest() != cd['slot'](-i)]
        if bad: problems.append(f'{name}: {len(bad)} code pages do not match their hashes (first at {bad[0] * cd["page"]:#x})')
        for slot, data, what in ((SLOT_INFO, info_plist, 'Info.plist'), (SLOT_RESOURCES, code_resources, 'CodeResources'),
                                 (SLOT_ENTITLEMENTS, ent_blob, 'entitlements')):
            if cd['n_special'] >= slot and data and cd['slot'](slot) != h(data).digest():
                problems.append(f'{name}: the {what} hash differs')
            if cd['n_special'] < slot:
                problems.append(f'{name}: no {what} slot')
        if cd['version'] < 0x20400 or not cd['exec_flags'] & 1:   # CS_EXECSEG_MAIN_BINARY
            problems.append(f'{name} code directory version {cd["version"]:#x} without the main binary flag')
        if not der:
            problems.append('no DER entitlements (iOS 15 and later refuse an app without them)')
        elif cd['n_special'] < SLOT_DER or cd['slot'](SLOT_DER) != h(der).digest():
            problems.append(f'{name}: the DER entitlements hash differs')
    cms = (blobs.get(CS_WRAPPER) or [b''])[0]
    if team is None:
        if len(cms) > 8: problems.append('a CMS signature where an ad-hoc one was expected')
    elif len(cms) <= 8: problems.append('no CMS signature (ad-hoc signed)')
    elif cert_der and cert_der not in cms: problems.append('the CMS signature does not carry the signing certificate')
    return problems, entitlements


class IpaFiles:
    """The files of Payload/<name>.app in an IPA, by their path inside the app, read only when asked for (an app with
    its game data is 17 GB)."""
    def __init__(self, ipa):
        self.zip = zipfile.ZipFile(ipa)
        apps = {n.split('/')[1] for n in self.zip.namelist() if n.startswith('Payload/') and n.count('/') >= 2}
        require(len(apps) == 1 and next(iter(apps)).endswith('.app'), f'{ipa}: not one Payload/<name>.app')
        self.prefix = f'Payload/{next(iter(apps))}/'
        self.names = [n[len(self.prefix):] for n in self.zip.namelist() if n.startswith(self.prefix) and not n.endswith('/')]
        self.known = set(self.names)

    def __contains__(self, path):
        return path in self.known

    def __iter__(self):
        return iter(self.names)

    def __len__(self):
        return len(self.names)

    def read(self, path):
        return self.zip.read(self.prefix + path)

    def sha256(self, path):
        h = hashlib.sha256()
        with self.zip.open(self.prefix + path) as f:
            while chunk := f.read(8 << 20): h.update(chunk)
        return h.digest()


def check_resources(files, code_resources, executable):
    """Problems between the app's files (an IpaFiles) and its CodeResources files2 record."""
    record = plistlib.loads(code_resources).get('files2', {})
    problems = []
    for path, entry in record.items():
        want = entry.get('hash2') if isinstance(entry, dict) else None
        if path not in files:
            if not (isinstance(entry, dict) and entry.get('optional')): problems.append(f'{path}: listed, not in the app')
        elif want is not None and files.sha256(path) != want:
            problems.append(f'{path}: SHA-256 differs from CodeResources')
    skip = {'Info.plist', 'PkgInfo', executable}
    missing = [p for p in files if p not in record and p not in skip and not p.startswith('_CodeSignature/')]
    if missing: problems.append(f'{len(missing)} files not covered by CodeResources, e.g. {missing[0]}')
    return problems


def verify(ipa, profile_raw=None, profile=None, cert_der=None):
    """Check a signed IPA; returns a summary, raises SignError with every problem found. Without a profile the app must
    be ad-hoc signed with the entitlements of ios/Sources/TOTK.entitlements (sign_adhoc)."""
    files = IpaFiles(ipa)
    info_raw = files.read('Info.plist'); info = plistlib.loads(info_raw)
    executable, bundle_id = info.get('CFBundleExecutable', ''), info.get('CFBundleIdentifier', '')
    team = (profile.get('TeamIdentifier') or ['?'])[0] if profile else None
    problems = []
    for need in (executable, '_CodeSignature/CodeResources') + (('embedded.mobileprovision',) if profile else ()):
        if need not in files: problems.append(f'{need}: missing')
    if problems: raise SignError(f'{ipa}: ' + '; '.join(problems))
    if profile and files.read('embedded.mobileprovision') != profile_raw:
        problems.append('embedded.mobileprovision is not the given profile')
    resources = files.read('_CodeSignature/CodeResources')
    exe_problems, ents = check_executable(files.read(executable), info_raw, resources, bundle_id, team, cert_der)
    problems += exe_problems
    want = ({'application-identifier': f'{team}.{bundle_id}', 'com.apple.developer.team-identifier': team,
             'get-task-allow': True, MEMORY: True} if profile else plistlib.loads(APP_ENTITLEMENTS.read_bytes()))
    problems += [f'entitlement {k} = {ents.get(k)!r}, not {v!r}' for k, v in want.items() if ents.get(k) != v]
    problems += check_resources(files, resources, executable)
    if problems: raise SignError(f'{ipa}: ' + '; '.join(problems))
    summary = dict(bundle_id=bundle_id, version=info.get('CFBundleShortVersionString'), build=info.get('CFBundleVersion'),
                   team=team, entitlements=ents, files=len(files))
    if profile:
        summary.update(profile=profile.get('Name'), profile_uuid=profile.get('UUID'),
                       profile_expires=f'{profile["ExpirationDate"]:%Y-%m-%d}')
    return summary


def identity(a, bundle_id):
    """(openssl, certificate DER, password, profile bytes, profile, entitlements) after every check before signing."""
    profile_raw, profile = read_profile(a.profile)
    password = read_password(a.p12_password_file)
    openssl, der = p12_openssl(a.openssl, a.p12, password)
    require(der in profile.get('DeveloperCertificates', []),
            f'the certificate in {a.p12.name} ({certificate_summary(openssl, der)}) is not one of the profile\'s')
    needed = plistlib.loads(APP_ENTITLEMENTS.read_bytes())
    ents = signing_entitlements(profile, bundle_id, needed)
    print(f'signing identity: {certificate_summary(openssl, der)}; profile {profile.get("Name")} '
          f'({profile.get("UUID")}), until {profile["ExpirationDate"]:%Y-%m-%d}', flush=True)
    return openssl, der, password, profile_raw, profile, ents


def add_identity_arguments(p):
    p.add_argument('--p12', type=Path, default=os.environ.get('TOTK_IOS_P12'), help='certificate and key (default: $TOTK_IOS_P12)')
    p.add_argument('--p12-password-file', type=Path, default=os.environ.get('TOTK_IOS_P12_PASSWORD_FILE'),
                   help='a file holding the p12 password (default: $TOTK_IOS_P12_PASSWORD_FILE, $TOTK_P12_PASSWORD, or asked)')
    p.add_argument('--profile', type=Path, default=os.environ.get('TOTK_IOS_PROFILE'), help='the .mobileprovision (default: $TOTK_IOS_PROFILE)')
    p.add_argument('--zsign', help='zsign executable (default: $TOTK_ZSIGN or PATH)')
    p.add_argument('--openssl', help='openssl executable (default: $TOTK_OPENSSL, PATH, or Git for Windows\')')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('input', type=Path, nargs='?', help='a folder holding Payload/<name>.app, or an unsigned .ipa')
    p.add_argument('--out', type=Path, help='the signed IPA')
    p.add_argument('--verify', type=Path, help='check this signed IPA only')
    p.add_argument('--adhoc', action='store_true', help='with --verify: the IPA is ad-hoc signed (<name>-unsigned.ipa '
                   'of package_ipa_windows.py), no profile')
    add_identity_arguments(p)
    a = p.parse_args()
    if a.verify:
        require(a.adhoc or a.profile, '--verify needs --profile, or --adhoc')
        raw, profile = (None, None) if a.adhoc else read_profile(a.profile)
        der = None
        if a.p12 and profile:
            der = p12_openssl(a.openssl, a.p12, read_password(a.p12_password_file))[1]
        print(verify(a.verify, raw, profile, der)); return
    require(a.input and a.out and a.p12 and a.profile, 'give the app, --out, --p12 and --profile (or --verify <ipa>)')
    unpacked = Path(tempfile.mkdtemp(prefix='totk-unsigned-')) if a.input.suffix.lower() == '.ipa' else None
    try:
        root = unpacked or a.input
        if unpacked:
            with zipfile.ZipFile(a.input) as z: z.extractall(root)   # extractall drops absolute and .. parts
        apps = list((root/'Payload').glob('*.app'))
        require(len(apps) == 1, f'{root}: not one Payload/<name>.app')
        bundle_id = plistlib.loads((apps[0]/'Info.plist').read_bytes())['CFBundleIdentifier']
        openssl, der, password, raw, profile, ents = identity(a, bundle_id)
        sign(tool('zsign', a.zsign, 'TOTK_ZSIGN'), openssl, root, a.out, a.p12, password, a.profile, ents)
        print(verify(a.out, raw, profile, der))
    finally:
        if unpacked: shutil.rmtree(unpacked, ignore_errors=True)


if __name__ == '__main__':
    try: main()
    except (SignError, OSError, KeyError, zipfile.BadZipFile, plistlib.InvalidFileException) as e:
        print(f'ERROR: {e}', file=sys.stderr); sys.exit(1)
