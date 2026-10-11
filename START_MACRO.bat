@echo off
setlocal

cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ^
  "$args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', '%~dp0cmd_remover.ps1'); Start-Process -FilePath 'powershell.exe' -ArgumentList $args -WorkingDirectory '%~dp0' -WindowStyle Hidden"

exit /b 0
