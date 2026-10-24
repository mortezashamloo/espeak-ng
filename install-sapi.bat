@echo off
setlocal EnableExtensions
title eSpeak NG SAPI5 - install

net session >nul 2>&1
if errorlevel 1 (
  echo Please close this window, right-click install-sapi.bat and choose "Run as administrator".
  pause
  exit /b 1
)

set "SRC=%~dp0"
set "DEST=%ProgramFiles%\eSpeak NG SAPI"
set "IS64="
if defined ProgramFiles(x86) set "IS64=1"
if defined ProgramW6432 set "DEST=%ProgramW6432%\eSpeak NG SAPI"
set "CLSID={61D23633-CE59-4101-8158-569FC6B51B49}"
set "R32="
if defined IS64 set "R32=/reg:32"

echo Close JAWS / NVDA / any program that is using eSpeak NG first, then press a key.
pause

echo Copying files to "%DEST%" ...
if exist "%DEST%" rd /s /q "%DEST%" >nul 2>&1
mkdir "%DEST%" >nul 2>&1
xcopy "%SRC%espeak-ng-data" "%DEST%\espeak-ng-data\" /E /I /Y /Q >nul
if errorlevel 1 goto :copyfail
if exist "%SRC%x86\libespeak-ng.dll" (
  mkdir "%DEST%\x86" >nul 2>&1
  copy /Y "%SRC%x86\libespeak-ng.dll" "%DEST%\x86\" >nul
  if errorlevel 1 goto :copyfail
)
if defined IS64 if exist "%SRC%x64\libespeak-ng.dll" (
  mkdir "%DEST%\x64" >nul 2>&1
  copy /Y "%SRC%x64\libespeak-ng.dll" "%DEST%\x64\" >nul
  if errorlevel 1 goto :copyfail
)

echo Registering the SAPI5 engine ...
call :clsid "%R32%" "%DEST%\x86\libespeak-ng.dll"
if defined IS64 call :clsid /reg:64 "%DEST%\x64\libespeak-ng.dll"

echo Registering voices ...
rem   :voice  <espeak voice name>  <Windows language id in hex>  <display name>
rem   To add a voice, copy one of the two lines below and change it.
call :voice fa 429 Persian
call :voice en-us 409 English-US

echo.
echo Done. In JAWS / NVDA / Windows choose the voice named "eSpeak NG Persian" or "eSpeak NG English-US".
pause
exit /b 0

:copyfail
echo Copying failed. Close every program that uses eSpeak NG (JAWS, NVDA) and run this file again.
pause
exit /b 1

:clsid
reg add "HKLM\SOFTWARE\Classes\CLSID\%CLSID%" /ve /d "eSpeakNG.TtsEngine" /f %~1 >nul
reg add "HKLM\SOFTWARE\Classes\CLSID\%CLSID%\InprocServer32" /ve /d "%~2" /f %~1 >nul
reg add "HKLM\SOFTWARE\Classes\CLSID\%CLSID%\InprocServer32" /v ThreadingModel /d Both /f %~1 >nul
exit /b 0

:voice
call :voicev "%R32%" %1 %2 %3
if defined IS64 call :voicev /reg:64 %1 %2 %3
exit /b 0

:voicev
set "K=HKLM\SOFTWARE\Microsoft\Speech\Voices\Tokens\eSpeakNG_%~2"
reg add "%K%" /ve /d "eSpeak NG %~4" /f %~1 >nul
reg add "%K%" /v CLSID /d "%CLSID%" /f %~1 >nul
reg add "%K%" /v Path /d "%DEST%" /f %~1 >nul
reg add "%K%" /v VoiceName /d "%~2" /f %~1 >nul
reg add "%K%\Attributes" /v Name /d "eSpeak NG %~4" /f %~1 >nul
reg add "%K%\Attributes" /v Language /d "%~3" /f %~1 >nul
reg add "%K%\Attributes" /v Gender /d Male /f %~1 >nul
reg add "%K%\Attributes" /v Age /d Adult /f %~1 >nul
reg add "%K%\Attributes" /v Vendor /d "eSpeak NG" /f %~1 >nul
exit /b 0
