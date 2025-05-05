@echo off
echo Building ResoniteSpotipy...

:: Create build directory if it doesn't exist
if not exist "build" mkdir build

:: Clean old distribution but preserve build cache for faster rebuilds
echo Cleaning previous distributions...
if exist "dist" rmdir /s /q dist
if exist "ResoniteSpotipy.zip" del ResoniteSpotipy.zip

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
    --exclude-module scipy ^
    --add-data "resonite_ui.py;." ^
    --add-data "spotify_color.py;." ^
    --add-data "APIClient.py;." ^
    ResoniteSpotipy.py

:: Check if build was successful
if not exist "dist\ResoniteSpotipy.exe" (
    echo Build failed! ResoniteSpotipy.exe not found.
    exit /b 1
)

:: Create the package
echo Creating package...
tar -a -c -f ResoniteSpotipy.zip -C dist ResoniteSpotipy.exe README.md LICENSE

echo Build completed successfully!
echo Package available at: ResoniteSpotipy.zip