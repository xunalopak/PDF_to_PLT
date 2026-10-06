"""Package the Windows executable on the GitHub runner."""
import hashlib
import zipfile
from pathlib import Path

dist = Path('dist')
exe = dist / 'PDF_to_PLT.exe'
if not exe.is_file():
    raise SystemExit('Le binaire Windows doit avoir été compilé sur GitHub Actions.')
with zipfile.ZipFile(dist / 'PDF_to_PLT-windows-x64.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in (exe, Path('README.md'), Path('LICENSE')):
        archive.write(path, path.name)
checksums = ''.join(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n'
                    for path in (exe, dist / 'PDF_to_PLT-windows-x64.zip'))
(dist / 'SHA256SUMS.txt').write_text(checksums, encoding='ascii')
