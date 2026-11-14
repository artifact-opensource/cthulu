$ErrorActionPreference = 'Stop'

$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$exePath = Join-Path $projectRoot 'Cthulu HFT.exe'
$startupScript = Join-Path $projectRoot 'run_cthulu_hft_startup.ps1'
$rootForSource = $projectRoot.Replace('"', '""')

if (-not (Test-Path -LiteralPath $startupScript -PathType Leaf)) {
    throw "High-frequency startup script not found: $startupScript"
}
if (Test-Path -LiteralPath $exePath) {
    throw "Refusing to overwrite existing launcher: $exePath"
}

$source = @"
using System;
using System.Diagnostics;
using System.IO;

public static class CthuluHftLauncher
{
    [STAThread]
    public static void Main()
    {
        string root = @"$rootForSource";
        string startupScript = Path.Combine(root, "run_cthulu_hft_startup.ps1");
        if (!File.Exists(startupScript))
        {
            throw new FileNotFoundException("High-frequency startup script not found.", startupScript);
        }

        ProcessStartInfo start = new ProcessStartInfo();
        start.FileName = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.System),
            @"WindowsPowerShell\v1.0\powershell.exe");
        start.Arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"" +
            startupScript + "\"";
        start.WorkingDirectory = root;
        start.UseShellExecute = false;
        start.CreateNoWindow = true;
        Process.Start(start);
    }
}
"@

Add-Type -TypeDefinition $source `
    -OutputType WindowsApplication `
    -OutputAssembly $exePath `
    -ErrorAction Stop

if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
    throw "Failed to create the high-frequency launcher: $exePath"
}

Write-Output "Created root executable: $exePath"
