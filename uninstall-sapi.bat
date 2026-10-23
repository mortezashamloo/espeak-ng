@echo off
setlocal EnableExtensions
title eSpeak NG SAPI5 - uninstall

net session >nul 2>&1
if errorlevel 1 (
  echo Please close this window, right-click uninstall-sapi.bat and choose "Run as administrator".
  pause
  exit /b 1
)

set "DEST=%ProgramFiles%\eSpeak NG SAPI"
if defined ProgramW6432 set "DEST=%ProgramW6432%\eSpeak NG SAPI"
set "CLSID={61D23633-CE59-4101-8158-569FC6B51B49}"
set "R32="
if defined ProgramFiles(x86) set "R32=/reg:32"

echo Close JAWS / NVDA first, then press a key.
pause

call :clean "%R32%"
if defined ProgramFiles(x86) call :clean /reg:64
rd /s /q "%DEST%" >nul 2>&1
echo Done.
pause
exit /b 0

:clean
reg delete "HKLM\SOFTWARE\Classes\CLSID\%CLSID%" /f %~1 >nul 2>&1
for /f "tokens=*" %%K in ('reg query "HKLM\SOFTWARE\Microsoft\Speech\Voices\Tokens" %~1 2^>nul ^| findstr /i "eSpeakNG_"') do reg delete "%%K" /f %~1 >nul 2>&1
exit /b 0
