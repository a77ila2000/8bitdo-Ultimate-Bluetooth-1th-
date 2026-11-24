"""Package tracked public sources and the two original executables only."""
from pathlib import Path
import hashlib
import subprocess
import zipfile

root = Path(__file__).resolve().parents[1]
files = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z']).decode().split('\0')
payload = {}
for name in filter(None, files):
    path = root / name
    if path.suffix.lower() in ('.dat', '.bin', '.dll', '.exe', '.log', '.zip'):
        raise ValueError('Unexpected tracked binary/private artifact: ' + name)
    payload[name] = path.read_bytes()
for name in ('PatchTool.exe', 'FlashTool.exe'):
    payload[name] = (root / 'dist' / name).read_bytes()
payload['SHA256SUMS.txt'] = ''.join(
    f'{hashlib.sha256(data).hexdigest()}  {name}\n'
    for name, data in sorted(payload.items())).encode('utf-8')
archive = root / 'dist/UltimateBT-Gen1-Experimental-Windows-x64.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as output:
    for name, data in sorted(payload.items()):
        output.writestr(name, data)
checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
(root / 'dist/SHA256SUMS.txt').write_text(checksum + '  ' + archive.name + '\n', encoding='ascii')
print(archive.name, archive.stat().st_size, checksum)
