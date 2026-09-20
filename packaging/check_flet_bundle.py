"""Fail Windows builds that would download the settings client at runtime."""
import argparse
from pathlib import Path


def check_bundle(directory):
    required = ('flet.exe', 'flutter_windows.dll', 'data/icudtl.dat',
                'data/flutter_assets/AssetManifest.bin')
    missing = [name for name in required if not (directory / name).is_file()]
    if missing:
        raise SystemExit(f'Incomplete Flet client in {directory}: {", ".join(missing)}')
    print(f'Bundled Flet client verified: {directory}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', nargs='?', type=Path)
    args = parser.parse_args()
    if args.directory is None:
        import flet.version
        import flet_desktop
        import flet_desktop.version
        if flet.version.version != flet_desktop.version.version:
            raise SystemExit('flet and flet-desktop versions must match; install requirements.txt')
        args.directory = Path(flet_desktop.__file__).parent / 'app' / 'flet'
    check_bundle(args.directory)
