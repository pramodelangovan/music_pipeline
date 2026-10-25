@echo off
setlocal

set ROOT=%~dp0..
cd /d %ROOT%

python -m pip install --upgrade pip
python -m pip install -r requirements-desktop.txt

pyinstaller --clean --noconfirm apps\desktop\music_pipeline_desktop.spec

echo.
echo Build finished.
echo Output: dist\MusicPipelineDesktop\MusicPipelineDesktop.exe
