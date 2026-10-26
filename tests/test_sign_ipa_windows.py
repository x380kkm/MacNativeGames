"""games/totk/ios/tools/sign_ipa_windows.py without a certificate or zsign: what a profile must grant, the entitlements
the app is signed with, the Unix modes of the IPA's entries, and the files zsign cannot seal."""
import datetime
import plistlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1]/'games/totk/ios/tools'
sys.path.insert(0, str(TOOLS))
import sign_ipa_windows as signing  # noqa: E402


def profile(**changes):
    p = {'Platform': ['iOS'], 'TeamIdentifier': ['TEAM123456'], 'ExpirationDate': datetime.datetime(2099, 1, 1),
         'Entitlements': {'application-identifier': 'TEAM123456.a.b', 'com.apple.developer.team-identifier': 'TEAM123456',
                          'get-task-allow': True, signing.MEMORY: True, 'keychain-access-groups': ['TEAM123456.*']}}
    for k, v in changes.items():
        if k in p: p[k] = v
        else: p['Entitlements'][k.replace('_', '-')] = v
    return p


class Entitlements(unittest.TestCase):
    NEEDED = {signing.MEMORY: True}

    def test_the_app_is_signed_with_the_four_entitlements(self):
        ents = signing.signing_entitlements(profile(), 'a.b', self.NEEDED)
        self.assertEqual(ents, {'application-identifier': 'TEAM123456.a.b', 'com.apple.developer.team-identifier': 'TEAM123456',
                                'get-task-allow': True, signing.MEMORY: True})
        wildcard = profile(); wildcard['Entitlements']['application-identifier'] = 'TEAM123456.*'
        self.assertEqual(signing.signing_entitlements(wildcard, 'a.b', self.NEEDED)['application-identifier'], 'TEAM123456.a.b')

    def test_a_profile_that_cannot_sign_the_app_stops_it(self):
        bad = [profile(get_task_allow=False), profile(Platform=['xrOS']), profile(ExpirationDate=datetime.datetime(2000, 1, 1))]
        no_memory = profile(); del no_memory['Entitlements'][signing.MEMORY]
        other = profile(); other['Entitlements']['application-identifier'] = 'TEAM123456.c.d'
        for p in bad + [no_memory, other]:
            with self.subTest(p=p), self.assertRaises(signing.SignError):
                signing.signing_entitlements(p, 'a.b', self.NEEDED)

    def test_the_profile_plist_is_found_in_its_signed_data(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'x.mobileprovision'
            path.write_bytes(b'\x30\x82junk' + plistlib.dumps({'Name': 'n'}) + b'\xa0\x82tail')
            self.assertEqual(signing.read_profile(path)[1], {'Name': 'n'})

    def test_the_password_file_has_no_line_end(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'p').write_bytes(b'secret \r\n')
            self.assertEqual(signing.read_password(Path(d)/'p'), 'secret ')


class Archive(unittest.TestCase):
    def test_entries_get_unix_modes_in_place(self):
        for count in (3, 70000):   # 70,000 entries: the zip64 end records
            with self.subTest(count=count), tempfile.TemporaryDirectory() as d:
                ipa = Path(d)/'a.ipa'
                with zipfile.ZipFile(ipa, 'w') as z:
                    z.writestr('Payload/', b''); z.writestr('Payload/A.app/Info.plist', plistlib.dumps({'CFBundleExecutable': 'A'}))
                    z.writestr('Payload/A.app/A', b'\xcf\xfa\xed\xfe')
                    for i in range(count): z.writestr(f'Payload/A.app/r/{i}', b'x')
                before = ipa.stat().st_size
                signing.set_unix_modes(ipa)
                with zipfile.ZipFile(ipa) as z:
                    modes = {i.filename: i.external_attr >> 16 for i in z.infolist()}
                    self.assertEqual(z.testzip(), None)
                self.assertEqual(modes['Payload/'], 0o40755)
                self.assertEqual(modes['Payload/A.app/A'], 0o100755)
                self.assertEqual(modes['Payload/A.app/r/0'], 0o100644)
                self.assertEqual(ipa.stat().st_size, before)

    def test_zsign_is_not_run_on_a_file_it_cannot_seal(self):
        """zsign 1.1.2 on Windows seals a file of 4 GiB or more with the hash of its first size mod 4 GiB bytes."""
        with tempfile.TemporaryDirectory() as d, patch.object(signing, 'ZSIGN_FILE_LIMIT', 10):
            app = Path(d)/'stage/Payload/A.app'; app.mkdir(parents=True); (app/'image').write_bytes(b'x' * 10)
            self.assertEqual(signing.large_files(Path(d)/'stage'), [app/'image'])
            with self.assertRaises(signing.SignError):
                signing.run_zsign(Path(d)/'zsign that must not run', [], Path(d)/'out.ipa', Path(d)/'stage')

    def test_an_executable_without_a_signature_is_reported(self):
        header = (0xfeedfacf).to_bytes(4, 'little') + bytes(12) + (0).to_bytes(4, 'little') + bytes(12)
        with self.assertRaises(signing.SignError):
            signing.code_signature(header)
        with self.assertRaises(signing.SignError):
            signing.code_signature(b'\x7fELF' + bytes(28))


if __name__ == '__main__':
    unittest.main()
