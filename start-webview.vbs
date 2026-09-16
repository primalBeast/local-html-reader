' Start start-webview.cmd already minimized (no extra visible console).
' 7 = SW_SHOWMINNOACTIVE
Option Explicit
Dim fso, sh, dir, cmd, rc, splash
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir
splash = dir & "\lhr\assets\show-splash.ps1"
If fso.FileExists(splash) Then
  sh.Run "powershell.exe -STA -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & splash & """", 0, False
End If
cmd = "cmd.exe /c """ & dir & "\start-webview.cmd"""
rc = sh.Run(cmd, 7, True)
If rc <> 0 Then
  MsgBox "Local HTML Reader failed to start (code " & rc & ")." & vbCrLf & _
    "Double-click install.cmd, then try again.", 16, "Local HTML Reader"
End If
