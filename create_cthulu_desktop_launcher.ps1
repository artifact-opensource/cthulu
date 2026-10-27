$ErrorActionPreference = 'Stop'

$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
$exePath = Join-Path $desktop 'Cthulu Launcher.exe'
$shortcutPath = Join-Path $desktop 'Cthulu Live.lnk'
$startupScript = Join-Path $projectRoot 'run_cthulu_startup.bat'
$rootForSource = $projectRoot.Replace('\', '\\').Replace('"', '\"')

if (-not (Test-Path -LiteralPath $startupScript)) {
    throw "Cthulu startup script not found: $startupScript"
}

$source = @"
using System;
using System.Diagnostics;
using System.IO;

public static class CthuluDesktopLauncher
{
    [STAThread]
    public static void Main()
    {
        string root = @"$rootForSource";
        string batch = Path.Combine(root, "run_cthulu_startup.bat");
        if (!File.Exists(batch))
        {
            throw new FileNotFoundException("Cthulu startup script not found.", batch);
        }

        ProcessStartInfo start = new ProcessStartInfo();
        start.FileName = Environment.GetEnvironmentVariable("ComSpec");
        start.Arguments = "/c \"\"" + batch + "\"\"";
        start.WorkingDirectory = root;
        start.UseShellExecute = false;
        start.CreateNoWindow = true;
        Process.Start(start);
    }
}
"@

if (Test-Path -LiteralPath $exePath) {
    Remove-Item -LiteralPath $exePath -Force
}
Add-Type -TypeDefinition $source `
    -OutputType WindowsApplication `
    -OutputAssembly $exePath `
    -ErrorAction Stop

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $exePath
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = 'Start or restart Cthulu using the project startup configuration.'
$shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,44"
$shortcut.Save()

if (-not (Test-Path -LiteralPath $exePath) -or
    -not (Test-Path -LiteralPath $shortcutPath)) {
    throw 'Failed to create the Cthulu desktop executable and shortcut.'
}

Write-Output "Created desktop executable: $exePath"
Write-Output "Created desktop shortcut: $shortcutPath"
