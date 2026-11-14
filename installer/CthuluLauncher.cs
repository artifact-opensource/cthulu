using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class CthuluLauncher
{
    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            string root = AppDomain.CurrentDomain.BaseDirectory;
            string action = args.Length == 0 ? "setup" : args[0].ToLowerInvariant();

            if (action == "setup")
            {
                string script = Path.Combine(root, "installer", "cthulu_first_run_setup.ps1");
                if (!File.Exists(script))
                {
                    throw new FileNotFoundException("The Cthulu first-run setup script is missing.", script);
                }

                string powershell = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.System),
                    @"WindowsPowerShell\v1.0\powershell.exe");
                var startInfo = new ProcessStartInfo
                {
                    FileName = powershell,
                    Arguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -STA -File \"" + script + "\"",
                    WorkingDirectory = root,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    WindowStyle = ProcessWindowStyle.Hidden
                };
                Process.Start(startInfo);
                return 0;
            }

            if (action == "launch")
            {
                string batch = Path.Combine(root, "Cthulu Launcher.bat");
                if (!File.Exists(batch))
                {
                    throw new FileNotFoundException("The Cthulu launcher batch file is missing.", batch);
                }

                string commandPrompt = Path.Combine(Environment.SystemDirectory, "cmd.exe");
                var startInfo = new ProcessStartInfo
                {
                    FileName = commandPrompt,
                    Arguments = "/d /c \"\"" + batch + "\"\"",
                    WorkingDirectory = root,
                    UseShellExecute = false,
                    CreateNoWindow = false,
                    WindowStyle = ProcessWindowStyle.Normal
                };
                Process.Start(startInfo);
                return 0;
            }

            throw new ArgumentException("Expected the 'setup' or 'launch' command.");
        }
        catch (Exception exception)
        {
            MessageBox.Show(
                "Cthulu could not start.\n\n" + exception.Message,
                "Cthulu",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return 1;
        }
    }
}
