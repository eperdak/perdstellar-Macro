param(
    [switch]$Monitor,
    [string]$ReadyEventName,
    [string]$StopEventName
)

$ErrorActionPreference = 'Stop'

function New-LauncherEvent {
    param([string]$Name)

    $createdNew = $false
    return [System.Threading.EventWaitHandle]::new(
        $false,
        [System.Threading.EventResetMode]::ManualReset,
        $Name,
        [ref]$createdNew
    )
}

function Invoke-ConsoleMonitor {
    $readyHandle = $null
    $stopHandle = $null

    try {
        $readyHandle = [System.Threading.EventWaitHandle]::OpenExisting($ReadyEventName)
        $stopHandle = [System.Threading.EventWaitHandle]::OpenExisting($StopEventName)
        $handles = [System.Threading.WaitHandle[]]@($readyHandle, $stopHandle)
        $signal = [System.Threading.WaitHandle]::WaitAny($handles, 300000)

        if ($signal -ne 0) {
            return
        }

        if (-not ('Perdstellar.ConsoleApi' -as [type])) {
            Add-Type @'
using System;
using System.Runtime.InteropServices;

namespace Perdstellar {
    public static class ConsoleApi {
        [DllImport("kernel32.dll")]
        public static extern IntPtr GetConsoleWindow();

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    }
}
'@
        }

        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            $consoleHandle = [Perdstellar.ConsoleApi]::GetConsoleWindow()
            if ($consoleHandle -ne [IntPtr]::Zero) {
                [void][Perdstellar.ConsoleApi]::ShowWindow($consoleHandle, 0)
                return
            }

            Start-Sleep -Milliseconds 100
        }
    } catch {
        return
    } finally {
        if ($readyHandle) {
            $readyHandle.Dispose()
        }
        if ($stopHandle) {
            $stopHandle.Dispose()
        }
    }
}

if ($Monitor) {
    Invoke-ConsoleMonitor
    exit 0
}

$token = [Guid]::NewGuid().ToString('N')
$readyName = "Local\perdstellar_macro_ready_$token"
$stopName = "Local\perdstellar_macro_stop_$token"
$readyHandle = $null
$stopHandle = $null
$wrapperPath = Join-Path ([System.IO.Path]::GetTempPath()) "perdstellar_macro_$token.cmd"
$previousReadyEvent = $env:PERDSTALLAR_READY_EVENT

try {
    $readyHandle = New-LauncherEvent $readyName
    $stopHandle = New-LauncherEvent $stopName
    $env:PERDSTALLAR_READY_EVENT = $readyName

    $scriptPath = Join-Path $PSScriptRoot 'cmd_remover.ps1'
    $batchPath = Join-Path $PSScriptRoot 'debug.bat'
    $wrapperContent = @"
@echo off
start "" /b powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$scriptPath" -Monitor -ReadyEventName "$readyName" -StopEventName "$stopName"
call "$batchPath"
"@
    [System.IO.File]::WriteAllText($wrapperPath, $wrapperContent, [System.Text.Encoding]::ASCII)

    $child = Start-Process `
        -FilePath $env:ComSpec `
        -ArgumentList @('/d', '/c', ('"' + $wrapperPath + '"')) `
        -WorkingDirectory $PSScriptRoot `
        -WindowStyle Normal `
        -PassThru

    $child.WaitForExit()
} catch {
    return
} finally {
    if ($stopHandle) {
        try {
            [void]$stopHandle.Set()
        } catch {
        }
    }

    if ($readyHandle) {
        $readyHandle.Dispose()
    }
    if ($stopHandle) {
        $stopHandle.Dispose()
    }

    if ($null -eq $previousReadyEvent) {
        Remove-Item Env:PERDSTALLAR_READY_EVENT -ErrorAction SilentlyContinue
    } else {
        $env:PERDSTALLAR_READY_EVENT = $previousReadyEvent
    }

    Remove-Item $wrapperPath -Force -ErrorAction SilentlyContinue
}
