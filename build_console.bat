@echo off
echo ========================================
echo      GLaSSIST Ultimate Build Script
echo ========================================
echo.

:: Check if virtual environment is activated
if not defined VIRTUAL_ENV (
    echo ERROR: Virtual environment not activated!
    echo Please run: venv\Scripts\activate
    pause
    exit /b 1
)

:: Step 1: Clean up old builds
echo [1/5] Cleaning up old builds...
if exist "dist" (
    echo   Removing dist folder...
    rmdir /s /q "dist"
)
if exist "build" (
    echo   Removing build folder...
    rmdir /s /q "build"
)
if exist "inno\GLaSSIST-Debug.exe" (
    echo   Removing old installer...
    del /q "inno\GLaSSIST-Debug.exe"
)
if exist "*.spec" (
    echo   Removing old spec files...
    del /q "*.spec"
)
echo   Cleanup complete!
echo.

:: Step 2: Build with PyInstaller
echo [2/5] Building application with PyInstaller...
echo   This may take several minutes...
pyinstaller --name "GLaSSIST" ^
    --icon "img/icon.ico" ^
    --add-data "frontend;frontend" ^
    --add-data "sound;sound" ^
    --add-data "img;img" ^
    --add-data "models;models" ^
    --add-data "venv/Lib/site-packages/openwakeword;openwakeword" ^
    --add-data "venv/Lib/site-packages/onnxruntime/capi/*;onnxruntime/capi/" ^
    --hidden-import "openwakeword" ^
    --hidden-import "openwakeword.model" ^
    --hidden-import "openwakeword.utils" ^
    --hidden-import "webrtcvad" ^
    --hidden-import "pystray" ^
    --hidden-import "PIL" ^
    --hidden-import "numpy" ^
    --hidden-import "scipy" ^
    --hidden-import "onnxruntime" ^
    --hidden-import "sounddevice" ^
    --hidden-import "soundfile" ^
    --hidden-import "webview" ^
    --hidden-import "websockets" ^
    --hidden-import "keyboard" ^
    --collect-all "openwakeword" ^
    --noconfirm ^
    main.py

if %ERRORLEVEL% neq 0 (
    echo   PyInstaller build failed!
    pause
    exit /b 1
)
echo   PyInstaller build complete!
echo.

:: Step 3: Fix MSVCP140.dll issue
echo [3/5] Fixing Visual C++ Runtime...
if exist "C:\Windows\System32\MSVCP140.dll" (
    copy "C:\Windows\System32\MSVCP140.dll" "dist\GLaSSIST\_internal\" > nul
    echo   MSVCP140.dll copied successfully!
) else (
    echo   Warning: MSVCP140.dll not found in System32
    echo   You may need to install Visual C++ Redistributable
)
echo.

:: Step 4: Test the build
echo [4/5] Testing the build...
if exist "dist\GLaSSIST\GLaSSIST.exe" (
    echo   GLaSSIST.exe created successfully!
    echo   Size: 
    for %%I in ("dist\GLaSSIST\GLaSSIST.exe") do echo     %%~zI bytes
) else (
    echo   GLaSSIST.exe not found!
    pause
    exit /b 1
)
echo.

:: Step 5: Build installer with Inno Setup
echo [5/5] Building installer with Inno Setup...
set INNO_PATH="C:\Program Files (x86)\Inno Setup 6\Compil32.exe"
if not exist %INNO_PATH% (
    echo   Inno Setup not found at %INNO_PATH%
    echo   Please install Inno Setup 6 or update the path
    echo   Skipping installer build...
    goto :skip_installer
)

if not exist "setup_debug.iss" (
    echo   installer.iss not found!
    echo   Please create the Inno Setup script first
    goto :skip_installer
)

echo   Building installer...
%INNO_PATH% /cc "setup_debug.iss"
if %ERRORLEVEL% neq 0 (
    echo   Installer build failed!
    pause
    exit /b 1
)

if exist "inno\GLaSSIST-Debug.exe" (
    echo   Installer created successfully!
    echo   Location: inno\GLaSSIST-Setup.exe
    echo   Size: 
    for %%I in ("inno\GLaSSIST-Debug.exe") do echo     %%~zI bytes
) else (
    echo   Installer not found!
)

:skip_installer
echo.
echo ========================================
echo            BUILD COMPLETE!
echo ========================================
echo.
echo Files created:
echo   dist\GLaSSIST\GLaSSIST.exe - Standalone application
if exist "inno\GLaSSIST-Debug.exe" (
    echo   inno\GLaSSIST-Debug.exe - Windows installer
)
echo.
echo Ready for distribution!
echo.
pause