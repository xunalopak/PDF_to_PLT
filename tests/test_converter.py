import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from app import convert_pdf
from pdf_to_lasertrace import cubic, intervals, read_logo_pdf, stroke_outline, visible_intervals
from fixture_pdf import make_pdf


def decode_plt(filename):
    paths = []
    for command in Path(filename).read_text().replace('\n', '').split(';'):
        if command.startswith('PU') and command[2:]:
            paths.append([tuple(float(n) / 40 for n in command[2:].split(','))])
        elif command.startswith('PD'):
            numbers = [float(n) / 40 for n in command[2:].split(',')]
            if len(numbers) % 2 or not paths:
                raise AssertionError('Tracé HPGL incohérent')
            paths[-1].extend(zip(numbers[::2], numbers[1::2]))
        elif command not in ('IN', 'PA', 'SP1', 'PU', 'SP0', ''):
            raise AssertionError(f'Commande inattendue : {command}')
    return paths


class ConversionTests(unittest.TestCase):
    def test_round_caps_have_the_expected_area(self):
        path = stroke_outline([(1, 1), (3, 1)], .4, True, .0002)[0]
        area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(path, path[1:]))) / 2
        self.assertAlmostEqual(area, 2 * .4 + math.pi * .2 ** 2, delta=.0003)
        self.assertAlmostEqual(min(p[0] for p in path), .8, delta=.0003)
        self.assertAlmostEqual(max(p[0] for p in path), 3.2, delta=.0003)

    def test_fill_preserves_holes_and_white_masks(self):
        outer = [(0, 0), (4, 0), (4, 4), (0, 4), (0, 0)]
        inner = [(1, 1), (3, 1), (3, 3), (1, 3), (1, 1)]
        self.assertEqual(intervals([outer, inner], 2), [(0, 1), (3, 4)])
        self.assertEqual(visible_intervals([([outer], (0, 0, 0)), ([inner], (1, 1, 1))], 2),
                         [(0, 1), (3, 4)])

    def test_cubic_does_not_discard_collinear_reversals(self):
        self.assertEqual(cubic([(0, 0), (1, 0), (2, 0), (3, 0)], .0002), [(3, 0)])
        path = [(0, 0)] + cubic([(0, 0), (4, 0), (-4, 0), (0, 0)], .0002)
        self.assertGreater(max(p[0] for p in path), 1)
        self.assertLess(min(p[0] for p in path), -1)

    def test_end_to_end_conversion_scale_and_no_laser_bridges(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'Dessin été.pdf'
            output = Path(directory) / 'conversion'
            make_pdf(source)
            original = source.read_bytes()
            files, size = convert_pdf(source, output)
            self.assertEqual(len(files), 6)
            self.assertEqual(source.read_bytes(), original)
            self.assertAlmostEqual(size[0], 12.7)
            contours = decode_plt(output / 'Dessin été_lasertrace_contours.plt')
            self.assertEqual(len(contours), 4)
            self.assertTrue(all(p[0] == p[-1] for p in contours))
            width = max(p[0] for path in contours for p in path) - min(p[0] for path in contours for p in path)
            self.assertAlmostEqual(width, 10.16, delta=.001)
            regions, _ = read_logo_pdf(source)
            strokes = decode_plt(output / 'Dessin été_lasertrace_rempli.plt')[len(contours):]
            self.assertGreater(len(strokes), 100)
            for path in strokes:
                self.assertEqual(len(path), 2)
                self.assertEqual(path[0][1], path[1][1])
                left, right = sorted(p[0] for p in path)
                spans = visible_intervals(regions, path[0][1])
                self.assertTrue(any(abs(left - a) < .00001 and abs(right - b) < .00001 for a, b in spans))

    def test_existing_files_are_preserved_without_explicit_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'test.pdf'
            output = Path(directory) / 'output'
            make_pdf(source)
            files, _ = convert_pdf(source, output)
            snapshots = {p.name: p.read_bytes() for p in files}
            with self.assertRaises(FileExistsError):
                convert_pdf(source, output, spacing=.04)
            self.assertEqual(snapshots, {p.name: p.read_bytes() for p in files})
            convert_pdf(source, output, spacing=.04, overwrite=True)
            self.assertNotEqual(snapshots['test_lasertrace_rempli.plt'],
                                (output / 'test_lasertrace_rempli.plt').read_bytes())

    def test_unsupported_pdf_leaves_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'unsupported.pdf'
            output = Path(directory) / 'output'
            make_pdf(source, b'0 0 0 rg 1 2 m /Font1 12 Tf')
            with self.assertRaisesRegex(ValueError, 'Opérateur PDF'):
                convert_pdf(source, output)
            self.assertFalse(output.exists())
            source.write_bytes(b'not a pdf')
            with self.assertRaises(ValueError):
                convert_pdf(source, output)
            self.assertFalse(output.exists())

    def test_invalid_spacing_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'test.pdf'
            make_pdf(source)
            for step in (0, -.01, .0001, float('nan'), float('inf')):
                with self.subTest(step=step), self.assertRaises(ValueError):
                    convert_pdf(source, Path(directory) / 'output', step)

    def test_command_line_entrypoint(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'test.pdf'
            output = Path(directory) / 'output'
            make_pdf(source)
            result = subprocess.run([sys.executable, 'app.py', '--convert', str(source),
                                     '--output-dir', str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output / 'test_lasertrace_rempli.plt').exists())
            failed = subprocess.run([sys.executable, 'app.py', '--convert', str(source),
                                     '--output-dir', str(output)], capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)


if __name__ == '__main__':
    unittest.main()
