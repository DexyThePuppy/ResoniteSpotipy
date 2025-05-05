@echo off
echo Building ResoniteSpotipy...

:: Check if ResoniteSpotipy.exe is running
tasklist /FI "IMAGENAME eq ResoniteSpotipy.exe" 2>NUL | find /I /N "ResoniteSpotipy.exe" >NUL
if "%ERRORLEVEL%"=="0" (
    echo ResoniteSpotipy.exe is currently running. Closing it automatically...
    taskkill /F /IM ResoniteSpotipy.exe
    if errorlevel 1 (
        echo Failed to terminate the process. Please close it manually.
        pause
        goto :end
    )
    echo Successfully terminated the process.
    timeout /t 2 >NUL
)

:: Create build directory if it doesn't exist
if not exist "build" mkdir build

:: Clean old distribution but preserve build cache for faster rebuilds
echo Cleaning previous distributions...
if exist "dist\ResoniteSpotipy.exe" (
    del /F /Q "dist\ResoniteSpotipy.exe" 2>NUL
    if exist "dist\ResoniteSpotipy.exe" (
        echo WARNING: Could not delete the existing executable.
        echo It may be locked by another process.
        pause
        goto :end
    )
)
if exist "dist" rmdir /s /q dist
if exist "ResoniteSpotipy.zip" del /F /Q ResoniteSpotipy.zip

:: Build the executable with optimizations for speed
echo Building executable with PyInstaller...
python -m PyInstaller ^
    --clean ^
    -F ^
    --log-level WARN ^
    --noupx ^
    --exclude-module matplotlib ^
    --exclude-module notebook ^
    --exclude-module pandas ^
    --exclude-module PIL.ImageQt ^
    --exclude-module PyQt5 ^
    --exclude-module PyQt6 ^
    --exclude-module PySide2 ^
    --exclude-module PySide6 ^
    --exclude-module tkinter ^
    --hidden-import scipy ^
    --hidden-import sklearn ^
    --hidden-import scipy.special.cython_special ^
    --add-data "resonite_ui.py;." ^
    --add-data "spotify_color.py;." ^
    --add-data "APIClient.py;." ^
    ResoniteSpotipy.py

:: Check if build was successful
if not exist "dist\ResoniteSpotipy.exe" (
    echo Build failed! ResoniteSpotipy.exe not found.
    pause
    goto :end
)

:: Create the package
echo Creating package...
tar -a -c -f ResoniteSpotipy.zip -C dist ResoniteSpotipy.exe
if exist "README.md" tar -a -r -f ResoniteSpotipy.zip README.md
if exist "LICENSE" tar -a -r -f ResoniteSpotipy.zip LICENSE

if exist "ResoniteSpotipy.zip" (
    echo Build completed successfully!
    echo Package available at: ResoniteSpotipy.zip
) else (
    echo ERROR: Failed to create the package.
)

:end
exit /b