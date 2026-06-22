' Install Instant Translator to Windows Startup.
' Run ONCE Ч creates a shortcut in the Startup folder.
' After reboot, translator starts automatically.

Dim shell, fso, startupPath, shortcutPath, scriptDir, pyw

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
startupPath = shell.SpecialFolders("Startup")
shortcutPath = startupPath & "\InstantTranslate.lnk"
pyw = "C:\Program Files\Python311\pythonw.exe"

' Delete old if exists
If fso.FileExists(shortcutPath) Then fso.DeleteFile(shortcutPath)

Dim shortcut
Set shortcut = shell.CreateShortcut(shortcutPath)
shortcut.TargetPath = pyw
shortcut.Arguments = """" & scriptDir & "\instant_translator.py"""
shortcut.WorkingDirectory = scriptDir
shortcut.WindowStyle = 7  ' minimized
shortcut.Description = "Instant Translator Ч Ctrl+C+C to translate"
shortcut.Save

If fso.FileExists(shortcutPath) Then
    MsgBox "√отово! ярлык создан в автозагрузке:" & vbCrLf & shortcutPath & vbCrLf & vbCrLf & _
           "ѕерезагрузи систему или запусти run_hidden.vbs вручную.", vbInformation, "Instant Translator"
Else
    MsgBox "ќшибка: не удалось создать €рлык в " & startupPath, vbExclamation, "Instant Translator"
End If
