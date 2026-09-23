' Start start-webview.cmd already minimized (no extra visible console).
' 7 = SW_SHOWMINNOACTIVE
Option Explicit
Dim fso, sh, dir, cmd, rc, splash, owner, already, age
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir
splash = dir & "\lhr\assets\splash.hta"
owner = sh.ExpandEnvironmentStrings("%TEMP%\lhr-splash.owner")
If fso.FileExists(splash) Then
  already = False
  If fso.FileExists(owner) Then
    age = DateDiff("s", fso.GetFile(owner).DateLastModified, Now)
    already = (age >= 0 And age < 30)
  End If
  If Not already Then
    fso.CreateTextFile(owner, True).Close
    sh.Run "mshta.exe """ & splash & """", 1, False
  End If
End If
cmd = "cmd.exe /c """ & dir & "\start-webview.cmd"""
rc = sh.Run(cmd, 7, True)
If rc <> 0 Then
  MsgBox "Local HTML Reader failed to start (code " & rc & ")." & vbCrLf & _
    "Double-click install.cmd, then try again.", 16, "Local HTML Reader"
End If
