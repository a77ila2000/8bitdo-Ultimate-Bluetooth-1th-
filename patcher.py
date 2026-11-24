"""Hash-pinned, offline-capable patch builder. No firmware writes in this program."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import struct
import sys
import urllib.request
import zipfile

from vendor import cryptdo8
import receiver_format
import patch_source

RESOURCES = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
HOME = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else RESOURCES
EXPECTED = {
    'controller-conservative': '78d7364aad506d5c7b33fa0db5712524bc8f1f0a49fe57f9a43e90b4a198b0b7',
    'controller-timing': '33b2b62d87cd65fb52caf1a1cc13190d8f3ad31a2ef70459c8a3d5307882c693',
    'controller-enhanced': 'dee297b7c1a5f0b0646f05fc16f792be94df1e52cc478338f1780612fd897767',
    'receiver-2ms': 'e47eb1b0eddcd817f03573671f58e98c452387ba67aff01e8852229d39c1ce95',
}
DLL_SHA = 'b38ffa61b12af29d41dc55212e5ba44e509130facf6e3c4db9a7141aa313f974'
UPDATER_SHA = '5880c67c092f6d6e658f5a3a10c87dd42a439d561de75384599befe7b905916c'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(name):
    return json.loads((RESOURCES / 'patches' / name).read_text(encoding='utf-8'))


def check_stock(data, kind):
    spec = load('stock.json')[kind]
    require(len(data) == spec['bytes'] and sha(data) == spec['sha256'],
            f'Wrong {kind} original; exact official version/hash required')


def apply_edits(original, edits, final_size):
    require(len(original) <= final_size <= len(original) + 512, 'Invalid image growth')
    image = bytearray(original) + bytes(final_size - len(original))
    end = 0
    for edit in edits:
        offset = int(edit['offset'], 0)
        before, after = bytes.fromhex(edit['before']), bytes.fromhex(edit['after'])
        require(len(before) == len(after) > 0 and end <= offset and offset + len(before) <= len(image),
                'Overlapping or out-of-range patch')
        require(image[offset:offset + len(before)] == before, f'Preimage mismatch at {offset:#x}')
        image[offset:offset + len(after)] = after
        end = offset + len(before)
    return bytes(image)


def controller_images(raw):
    check_stock(raw, 'controller')
    sections = cryptdo8.parse_image(raw)
    require(len(sections) == 1, 'Expected single controller section')
    section = sections[0]
    require((section['id'], section['addr'], section['pid'], section['payload_len']) ==
            (111, 0x01018000, 0x6007, 104960), 'Wrong controller header')
    cipher = cryptdo8.CIPHERS['yichip']
    plain = cryptdo8.decrypt_section(raw, section, cipher)
    recipe = load('controller.json')
    require(sha(plain) == recipe['stock_plain_sha256'], 'Plaintext original mismatch')
    require(cryptdo8.build_section(plain, cipher, 111, 0x01018000, len(plain), 0x6007) == raw,
            'Original encryption roundtrip failed')
    outputs = {'RESTORE-controller-v1.11.dat': raw}
    for name, variant in recipe['variants'].items():
        image = apply_edits(plain, variant['edits'], variant['plain_bytes'])
        require(sha(image) == variant['plain_sha256'], f'{name} plaintext mismatch')
        if name == 'controller-enhanced':
            patch_source.verify_payloads(image)
        encoded = cryptdo8.build_section(image, cipher, 111, 0x01018000, len(image), 0x6007)
        require(sha(encoded) == variant['dat_sha256'] == EXPECTED[name], f'{name} DAT mismatch')
        require(cryptdo8.decrypt_section(encoded, cryptdo8.parse_image(encoded)[0], cipher) == image,
                'Candidate decrypt roundtrip failed')
        outputs[name + '.dat'] = encoded
    return outputs


def receiver_images(raw):
    check_stock(raw, 'receiver')
    recipe = load('receiver.json')
    parsed = receiver_format.verify(raw)
    image = apply_edits(raw, recipe['edits'], len(raw))
    require(sha(image) == recipe['dat_sha256'] == EXPECTED['receiver-2ms'], 'Receiver DAT mismatch')
    after = receiver_format.verify(image)  # Validate nested JLFS file/area/header/boot CRCs.
    before_app, after_app = parsed['app'], after['app']
    p, n = before_app['position'], before_app['size']
    require(before_app['sha256'] == receiver_format.APP_SHA and after_app['position'] == p and after_app['size'] == n,
            'Unexpected receiver app')
    changes = [(i, a, b) for i, (a, b) in enumerate(zip(parsed['decoded'][p:p+n], after['decoded'][p:p+n])) if a != b]
    require(changes == [(0x10ee4, 4, 2)], 'Receiver app change extends beyond IN bInterval')
    for file in parsed['files']:
        if file['name'] != 'app.bin':
            match = next(f for f in after['files'] if (f['name'], f['area']) == (file['name'], file['area']))
            require(file['sha256'] == match['sha256'], 'Unrelated receiver file changed')
    return {'RESTORE-receiver-v1.04.dat': raw, 'receiver-2ms.dat': image}


def write_outputs(outputs, destination):
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        target = destination / name
        require(target.resolve().is_relative_to(destination.resolve()), 'Output path escapes destination')
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            require(target.read_bytes() == content, f'Existing file differs: {target.name}; use a fresh output folder')
        else:
            temporary = target.with_suffix(target.suffix + '.tmp')
            temporary.write_bytes(content)
            os.replace(temporary, target)
        print(f'{sha(content)}  {name}')
    (destination / 'SHA256SUMS.txt').write_text(''.join(f'{sha(data)}  {name}\n' for name, data in outputs.items()), encoding='ascii')


def acquire(kind, path, offline=False):
    spec = load('stock.json')[kind]
    if path.exists():
        content = path.read_bytes()
    else:
        require(not offline, f'Missing offline input: {path.name}')
        print('Downloading official ' + kind + ' ...', flush=True)
        request = urllib.request.Request(spec['url'], headers={'User-Agent': 'UltimateBT-Gen1-PatchBuilder/0.1'})
        with urllib.request.urlopen(request, timeout=60) as response:
            content = response.read(spec['bytes'] + 1)
        check_stock(content, kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    check_stock(content, kind)
    return content


def prepare_updater(archive_bytes, destination):
    # ZIP is hash pinned; additionally bound sizes and reject traversal/symlinks.
    import io
    check_stock(archive_bytes, 'updater')
    outputs = {}
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        require(sum(i.file_size for i in archive.infolist()) < 100_000_000, 'Updater archive too large')
        for item in archive.infolist():
            parts = Path(item.filename.replace('\\', '/')).parts
            require(not Path(item.filename).is_absolute() and '..' not in parts and
                    ((item.external_attr >> 16) & 0o170000) != 0o120000, 'Unsafe updater archive member')
            if item.is_dir():
                continue
            require(len(parts) >= 2 and parts[0] == '8BitDo_Firmware_Updater_Win', 'Unexpected updater archive root')
            name = '/'.join(parts[1:])
            require(name not in outputs, 'Duplicate updater member')
            # Manufacturer logs are mutable runtime state; seed them once.
            if name in ('data/debugLog.txt', 'data/updateLog.txt') and (destination / name).exists():
                continue
            outputs[name] = archive.read(item)
    require(sha(outputs.get('8BitDoFirmwareUpdaterTools.dll', b'')) == DLL_SHA and
            sha(outputs.get('8BitDo Firmware Updater.exe', b'')) == UPDATER_SHA, 'Updater executable/DLL identity changed')
    write_outputs(outputs, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command')
    for name in ('build', 'prepare'):
        p = subs.add_parser(name)
        p.add_argument('--stock-dir', type=Path, default=HOME / 'cache')
        p.add_argument('--out', type=Path, default=HOME / 'output')
        p.add_argument('--offline', action='store_true')
        p.add_argument('--skip-updater', action='store_true')
    p = subs.add_parser('identify', help='Read-only Windows boot identity; no flash/erase commands')
    p.add_argument('target', choices=('controller', 'receiver'))
    args = parser.parse_args(sys.argv[1:] or ['prepare'])
    if args.command == 'identify':
        from windows.boot_identity import identify
        print(json.dumps(identify(args.target)))
        return
    require(args.command in ('build', 'prepare'), 'Choose build or prepare')
    raw_c = acquire('controller', args.stock_dir / 'controller-v1.11.dat', args.offline or args.command == 'build')
    raw_r = acquire('receiver', args.stock_dir / 'receiver-v1.04.dat', args.offline or args.command == 'build')
    outputs = {**controller_images(raw_c), **receiver_images(raw_r)}
    write_outputs(outputs, args.out)
    if args.command == 'prepare' and not args.skip_updater:
        archive = acquire('updater', args.stock_dir / 'updater.zip', args.offline)
        prepare_updater(archive, HOME / 'vendor-runtime')
    print('Verified. No device firmware was written. Read docs/UPDATING.ko.md before flashing.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, AssertionError, zipfile.BadZipFile, StopIteration) as error:
        print('STOP: ' + str(error), file=sys.stderr)
        sys.exit(2)
