# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

# Only collect the 3 Qt modules actually used: QtCore, QtGui, QtWidgets
# This avoids bundling Qt3D, Charts, WebEngine, Multimedia, Bluetooth, QML, etc.
qt_used_modules = ['PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets']

hiddenimports = qt_used_modules + [
    # Qt platform plugin loader needs these at runtime
    'PySide6.QtOpenGL',
    # Third-party deps
    'aria2p', 'aria2p.client', 'aria2p.api', 'aria2p.downloads',
    'psutil', 'requests', 'requests.adapters', 'requests.auth',
    'websocket', 'websocket._core', 'filelock',
    'charset_normalizer', 'idna', 'urllib3',
]

# PySide6 Qt libs dir (platform plugin lives here)
import PySide6 as _pyside6_pkg
import pathlib
_pyside6_dir = pathlib.Path(_pyside6_pkg.__file__).parent
_qt_dir = _pyside6_dir / 'Qt'

# Include only the macOS platform plugin (essential for GUI to start)
binaries = [
    ('resources/aria2/mac/aria2c', 'resources/aria2/mac'),
]

# Add platform plugin
_platform_plugin = _qt_dir / 'plugins' / 'platforms' / 'libqcocoa.dylib'
if _platform_plugin.exists():
    binaries.append((str(_platform_plugin), 'PySide6/Qt/plugins/platforms'))

# Add styles plugin (needed for native look)
_styles_plugin = _qt_dir / 'plugins' / 'styles' / 'libqmacstyle.dylib'
if _styles_plugin.exists():
    binaries.append((str(_styles_plugin), 'PySide6/Qt/plugins/styles'))

# Add imageformats plugin (for QPixmap/icons)
_imgfmt_dir = _qt_dir / 'plugins' / 'imageformats'
if _imgfmt_dir.exists():
    for dylib in _imgfmt_dir.glob('*.dylib'):
        binaries.append((str(dylib), 'PySide6/Qt/plugins/imageformats'))

# Core Qt shared libraries needed by QtCore/Gui/Widgets
_qt_lib_dir = _qt_dir / 'lib'
_required_qt_libs = [
    'QtCore', 'QtGui', 'QtWidgets', 'QtOpenGL',
    'QtDBus', 'QtPrintSupport',  # pulled in transitively on macOS
]
if _qt_lib_dir.exists():
    for lib_name in _required_qt_libs:
        for fw in _qt_lib_dir.glob(f'{lib_name}.framework'):
            # framework bundle
            versions_dir = fw / 'Versions'
            if versions_dir.exists():
                for ver_dir in versions_dir.iterdir():
                    lib_file = ver_dir / lib_name
                    if lib_file.exists() and lib_file.is_file():
                        binaries.append((str(lib_file), f'PySide6/Qt/lib/{fw.name}/Versions/{ver_dir.name}'))

# PySide6 .so bindings for used modules
_so_modules = ['QtCore', 'QtGui', 'QtWidgets', 'QtOpenGL']
for mod in _so_modules:
    for so in _pyside6_dir.glob(f'{mod}.abi3.so'):
        binaries.append((str(so), 'PySide6'))

# qt.conf — needed so Qt finds plugins relative to the bundle
datas = [
    ('resources', 'resources'),
]

icon_path = None
for candidate in ('resources/icon.icns', 'resources/icon.png'):
    if os.path.exists(candidate):
        icon_path = candidate
        break

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Explicitly exclude unused heavy Qt modules
        'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DExtras',
        'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtGraphs',
        'PySide6.QtWebEngine', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
        'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
        'PySide6.QtBluetooth', 'PySide6.QtNfc', 'PySide6.QtLocation',
        'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets',
        'PySide6.QtRemoteObjects', 'PySide6.QtSensors', 'PySide6.QtSerialPort',
        'PySide6.QtSql', 'PySide6.QtSvg', 'PySide6.QtSvgWidgets',
        'PySide6.QtTest', 'PySide6.QtVirtualKeyboard',
        'PySide6.QtDesigner', 'PySide6.QtHelp',
        'PySide6.QtNetwork', 'PySide6.QtConcurrent',
        # Exclude tkinter and test frameworks
        'tkinter', '_tkinter', 'unittest', 'doctest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='红果短剧下载器',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=True,
    upx=True,
    upx_exclude=['*.dylib'],  # don't UPX dylibs - can break code signing
    name='红果短剧下载器',
)

app = BUNDLE(
    coll,
    name='红果短剧下载器.app',
    icon=icon_path,
    bundle_identifier='com.hongguo.downloader',
    info_plist={
        'CFBundleShortVersionString': '1.1.3',
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,  # support dark mode
    },
)
