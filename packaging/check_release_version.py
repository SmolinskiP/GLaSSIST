"""Check the application, installer and Flatpak release versions agree."""
import argparse
from pathlib import Path
import re
import runpy
import xml.etree.ElementTree as ET


def check_versions(root, expected=None):
    version = runpy.run_path(str(root / 'version.py'))['__version__']
    installer = re.search(r'#define MyAppVersion "([^"]+)"',
                          (root / 'setup.iss').read_text(encoding='utf-8')).group(1)
    metadata = ET.parse(root / 'packaging/flatpak/io.github.SmolinskiP.GLaSSIST.metainfo.xml')
    flatpak = metadata.find('./releases/release').get('version')
    manifest = (root / 'packaging/flatpak/flathub/io.github.SmolinskiP.GLaSSIST.yml').read_text(encoding='utf-8')
    flathub = re.findall(r'^\s+tag:\s*(\S+)', manifest, re.MULTILINE)[-1]
    versions = {'application': version, 'installer': installer,
                'Flatpak': flatpak, 'Flathub': flathub}
    if expected:
        versions['release tag'] = expected.removeprefix('v')
    if len(set(versions.values())) != 1:
        raise SystemExit(f'Release version mismatch: {versions}')
    print(f'Release versions verified: {version}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected', default='')
    args = parser.parse_args()
    check_versions(Path(__file__).resolve().parent.parent, args.expected)
