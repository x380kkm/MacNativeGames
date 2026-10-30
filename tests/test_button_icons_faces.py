"""make_button_icons.py --faces: which button each Switch face icon (A, B, X, Y) shows, without game data. A stand-in for
the game's text fonts records the letter each icon cuts out; PlayStation symbols are compared as outlines."""
import argparse
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'games/totk/scripts/make_button_icons.py'
sys.path.insert(0, str(ROOT/'games/totk/scripts'))
READY = all(importlib.util.find_spec(m) is not None for m in ('compression.zstd', 'fontTools'))
SLOTS = (0xE040, 0xE041, 0xE042, 0xE043)   # the Switch A, B, X and Y icons


class Letters:
    """Stands in for make_button_icons.Glyphs: hole() records the text instead of drawing it."""
    def __init__(self):
        self.cut = []

    def hole(self, pen, text, *args):
        self.cut.append(text)


@unittest.skipUnless(READY, 'needs Python 3.14 and fontTools')
class Faces(unittest.TestCase):
    def setUp(self):
        import make_button_icons
        from fontTools.pens.recordingPen import RecordingPen
        self.icons, self.pen = make_button_icons, RecordingPen

    def letters(self, style, faces=None):
        """The letter each Switch face icon of the style shows, in A, B, X, Y order."""
        out = []
        for cp in SLOTS:
            g = Letters()
            self.icons.style_icons(style, g, faces)[cp][1](self.pen())
            out.append(''.join(g.cut))
        return ''.join(out)

    def outline(self, style, faces, cp):
        pen = self.pen()
        self.icons.style_icons(style, Letters(), faces)[cp][1](pen)
        return pen.value

    def test_parsing(self):
        self.assertEqual(self.icons.parse_faces('BAXY'), 'BAXY')
        self.assertEqual(self.icons.parse_faces('baxy'), 'BAXY')
        for bad in ('', 'BAX', 'BAXYY', 'AABY', 'BAXZ', 'B A X Y'):
            with self.subTest(bad=bad), self.assertRaises(argparse.ArgumentTypeError):
                self.icons.parse_faces(bad)

    def test_xbox_default_is_by_position(self):
        # the default mapping plays each button where the Switch prompt shows it: the right button (Xbox B) for Switch A
        self.assertEqual(self.letters('xbox'), 'BAYX')
        self.assertEqual(self.icons.FACES['xbox'], 'BAYX')

    def test_xbox_faces_go_into_the_switch_slots_in_order(self):
        # a controller whose X and Y reach the game swapped: the button printed X plays Switch X
        self.assertEqual(self.letters('xbox', 'BAXY'), 'BAXY')
        self.assertEqual(self.letters('xbox', 'ABXY'), 'ABXY')
        g = Letters()
        hud = self.icons.style_icons('xbox', g, 'BAXY')
        for texture, letter in (('Nt_KeyTexA_00', 'B'), ('Nt_KeyTexB_00', 'A'), ('Nt_KeyTexX_00', 'X'), ('Nt_KeyTexY_00', 'Y')):
            g.cut.clear(); hud[self.icons.HUD_TEXTURES[texture]][1](self.pen())
            self.assertEqual(g.cut, [letter], texture)   # the button guide follows the same order

    def test_faces_change_only_the_face_icons(self):
        plain, swapped = self.icons.style_icons('xbox', Letters()), self.icons.style_icons('xbox', Letters(), 'BAXY')
        self.assertEqual(set(plain), set(swapped))
        for cp in set(plain) - set(SLOTS):
            self.assertEqual(self.outline('xbox', None, cp), self.outline('xbox', 'BAXY', cp), f'U+{cp:04X}')

    def test_playstation_defaults_stay(self):
        # by position Circle Cross Triangle Square, by label Cross Circle Square Triangle (as before --faces)
        self.assertEqual(self.icons.FACES['playstation'], 'BAYX')
        self.assertEqual(self.icons.FACES['playstation-label'], 'ABXY')
        for style, faces in self.icons.FACES.items():
            for cp in SLOTS:
                self.assertEqual(self.outline(style, None, cp), self.outline(style, faces, cp), (style, cp))
        symbols = [self.icons.PLAYSTATION_SYMBOLS[letter] for letter in self.icons.FACES['playstation']]
        self.assertEqual(symbols, ['circle', 'cross', 'triangle', 'square'])

    def test_playstation_faces_draw_the_symbol_of_the_named_button(self):
        # each slot shows the outline the default puts where that button's letter is
        default = self.icons.FACES['playstation']
        by_letter = {letter: self.outline('playstation', None, SLOTS[default.index(letter)]) for letter in default}
        for faces in ('BAXY', 'ABXY', 'YXBA'):
            for cp, letter in zip(SLOTS, faces):
                self.assertEqual(self.outline('playstation', faces, cp), by_letter[letter], (faces, letter))

    def test_the_command_line_checks_the_option(self):
        with tempfile.TemporaryDirectory() as d:
            def run(*args):
                return subprocess.run([sys.executable, str(SCRIPT), str(Path(d)/'mod'), '--romfs', d, *args],
                                      capture_output=True, text=True)
            keyboard = run('--style', 'keyboard', '--faces', 'BAXY')
            self.assertEqual(keyboard.returncode, 2)
            self.assertIn('--faces goes with --style xbox', keyboard.stderr)
            wrong = run('--style', 'xbox', '--faces', 'BAXZ')
            self.assertEqual(wrong.returncode, 2)
            self.assertIn('give each of A, B, X and Y once', wrong.stderr)
            self.assertFalse((Path(d)/'mod').exists())


if __name__ == '__main__':
    unittest.main()
