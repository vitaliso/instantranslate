' Скрытый запуск Instant Translator (без консольного окна)
' Просто запусти этот файл — утилита будет работать в фоне.
' Выход: Ctrl+Shift+Q

CreateObject("WScript.Shell").Run "pythonw.exe """ & _
    CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & _
    "\instant_translator.py""", 0, False
