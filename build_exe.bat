@echo off
setlocal
cd /d "%~dp0"

echo [1/4] Installing build dependencies...
python -m pip install -r requirements.txt || exit /b 1

echo [1.5/4] Closing previous EXE if it is running...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'TaskBarHeroAutoSynth.exe' -and $_.CommandLine -like '*\dist\TaskBarHeroAutoSynth.exe*' } | Select-Object -ExpandProperty ProcessId | ForEach-Object { Stop-Process -Id $_ -Force }" || exit /b 1

echo [2/4] Building TaskBarHeroAutoSynth.exe...
python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name TaskBarHeroAutoSynth ^
  --icon assets\app.ico ^
  --add-data "templates;templates" ^
  TaskBarHeroAutoSynth.pyw || exit /b 1

echo [3/4] Creating release zip...
if not exist release mkdir release
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$manual=(Get-ChildItem -LiteralPath . -Filter '*.txt' | Where-Object { $_.Name -ne 'requirements.txt' } | Select-Object -First 1).FullName; $ko=Join-Path 'release' ('TaskBarHeroAutoSynth_'+[char]0xACF5+[char]0xC720+[char]0xC6A9+'.zip'); $paths=@('dist\TaskBarHeroAutoSynth.exe',$manual); for($i=0;$i -lt 10;$i++){ try { Compress-Archive -Force -LiteralPath $paths -DestinationPath $ko -ErrorAction Stop; Copy-Item -Force $ko 'release\TaskBarHeroAutoSynth_share.zip'; exit 0 } catch { Start-Sleep -Milliseconds 700 } }; throw 'Release zip failed because files stayed locked.'" || exit /b 1

echo [4/4] Done.
echo EXE: %CD%\dist\TaskBarHeroAutoSynth.exe
echo ZIP: %CD%\release\TaskBarHeroAutoSynth_share.zip
endlocal
