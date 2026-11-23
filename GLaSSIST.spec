# -*- mode: python ; coding: utf-8 -*-
# Used by build.bat, build_console.bat and the Windows GitHub Actions workflow.
# GLASSIST_CONSOLE=1 builds the console (debug) variant.
import os
import runpy

import onnxruntime
import openwakeword
from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)

app_version = runpy.run_path(os.path.join(SPECPATH, 'version.py'))['__version__']
version_tuple = tuple(int(part) for part in app_version.split('.')) + (0,) * (4 - len(app_version.split('.')))
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=version_tuple, prodvers=version_tuple),
    kids=[
        StringFileInfo([StringTable('040904B0', [
            StringStruct('CompanyName', 'Patryk Smoliński'),
            StringStruct('FileDescription', 'GLaSSIST'),
            StringStruct('FileVersion', app_version),
            StringStruct('InternalName', 'GLaSSIST'),
            StringStruct('LegalCopyright', 'MIT License'),
            StringStruct('OriginalFilename', 'GLaSSIST.exe'),
            StringStruct('ProductName', 'GLaSSIST'),
            StringStruct('ProductVersion', app_version),
        ])]),
        VarFileInfo([VarStruct('Translation', [0x0409, 1200])]),
    ],
)

datas = [
    ('frontend', 'frontend'), ('sound', 'sound'), ('img', 'img'), ('models', 'models'), ('locales', 'locales'),
    (os.path.dirname(openwakeword.__file__), 'openwakeword'),
    (os.path.join(os.path.dirname(onnxruntime.__file__), 'capi', '*'), 'onnxruntime/capi/'),
]
binaries = []
hiddenimports = ['openwakeword', 'openwakeword.model', 'openwakeword.utils', 'webrtcvad', 'pystray', 'PIL', 'numpy', 'scipy', 'onnxruntime', 'sounddevice', 'soundfile', 'miniaudio', 'webview', 'websockets', 'keyboard']
tmp_ret = collect_all('openwakeword')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('flet_desktop')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[os.path.join(SPECPATH, 'packaging', 'pyinstaller_hooks')],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GLaSSIST',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=os.environ.get('GLASSIST_CONSOLE') == '1',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['img\\icon.ico'],
    version=version_info,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='GLaSSIST',
)
