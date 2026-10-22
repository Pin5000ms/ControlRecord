using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

[assembly: AssemblyTitle("ControlRecord")]
[assembly: AssemblyDescription("Windows mouse recording and playback")]
[assembly: AssemblyVersion("0.1.0.0")]
[assembly: AssemblyFileVersion("0.1.0.0")]

internal static class Launcher
{
    // Quote arguments according to the Windows CommandLineToArgvW rules.
    private static string Quote(string value)
    {
        StringBuilder result = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in value)
        {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') { result.Append('\\', slashes * 2 + 1); result.Append(c); slashes = 0; continue; }
            result.Append('\\', slashes); slashes = 0; result.Append(c);
        }
        result.Append('\\', slashes * 2);
        result.Append('"');
        return result.ToString();
    }

    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            string root = AppDomain.CurrentDomain.BaseDirectory;
            string python = Path.Combine(root, "runtime", "pythonw.exe");
            string script = Path.Combine(root, "app", "main.py");
            if (!File.Exists(python) || !File.Exists(script))
                throw new FileNotFoundException("請先解壓縮完整的 ControlRecord 資料夾，再執行 EXE。");
            List<string> arguments = new List<string>();
            arguments.Add(Quote(script));
            foreach (string arg in args) arguments.Add(Quote(arg));
            ProcessStartInfo info = new ProcessStartInfo(python, String.Join(" ", arguments.ToArray()));
            info.WorkingDirectory = root;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.EnvironmentVariables["PYTHONUTF8"] = "1";
            using (Process child = Process.Start(info))
            {
                child.WaitForExit();
                if (child.ExitCode != 0)
                    MessageBox.Show("程式未正常結束，請查看 data\\application.log。", "ControlRecord", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return child.ExitCode;
            }
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message, "ControlRecord 無法啟動", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}

