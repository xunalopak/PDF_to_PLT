"""Create a synthetic vector PDF for tests, without any user artwork."""
import sys
import zlib
from pathlib import Path


def make_pdf(filename, content=None):
    if content is None:
        content = b'''q
0 0 36 36 re W n
0.1 0.1 0.1 RG
0.8 w 1 J 1 j
q 1 0 0 1 18 18 cm
14 0 m
14 7.732 7.732 14 0 14 c
-7.732 14 -14 7.732 -14 0 c
-14 -7.732 -7.732 -14 0 -14 c
7.732 -14 14 -7.732 14 0 c
h S Q
0 0 0 RG
1.2 w
12 8 m
9 12 12 18 23 25 c
S
0.1 0.1 0.1 rg
20 8 m 22 8 l 22 12 l 20 12 l h f
Q
'''
    compressed = zlib.compress(content)
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 36 36] /Resources << >> /Contents 4 0 R >>',
               f'<< /Length {len(compressed)} /Filter /FlateDecode >>\nstream\n'.encode('ascii')
               + compressed + b'\nendstream']
    data = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f'{i} 0 obj\n'.encode('ascii') + obj + b'\nendobj\n')
    xref = len(data)
    data.extend(b'xref\n0 5\n0000000000 65535 f \n')
    data.extend(''.join(f'{offset:010d} 00000 n \n' for offset in offsets[1:]).encode('ascii'))
    data.extend(f'trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode('ascii'))
    Path(filename).write_bytes(data)


if __name__ == '__main__':
    make_pdf(sys.argv[1])
