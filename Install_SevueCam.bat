@echo off
title Install Sevue Virtual Camera

:: Auto-elevate to admin
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if "%errorlevel%" NEQ "0" (
    echo Requesting administrative privileges...
    goto UACPrompt
) else (
    goto gotAdmin
)

:UACPrompt
echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
echo UAC.ShellExecute "cmd.exe","/c %~s0", "", "runas", 1 >> "%temp%\getadmin.vbs"
"%temp%\getadmin.vbs"
del "%temp%\getadmin.vbs"
exit /b

:gotAdmin
pushd "%CD%"
cd /d "%~dp0"

echo Installing Sevue-VirtualCam...
regsvr32 /s "UnityCaptureFilter32.dll" "/i:UnityCaptureName=Sevue-VirtualCam"
regsvr32 /s "UnityCaptureFilter64.dll" "/i:UnityCaptureName=Sevue-VirtualCam"

echo Done.
echo Sevue-VirtualCam installed successfully.
pause
exit /b
