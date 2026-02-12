' Tayfa Launcher - Hidden Window Startup
' Запускает tayfa.bat без видимого окна терминала
' Для отладки запустите tayfa.bat напрямую

Set WshShell = CreateObject("WScript.Shell")

' Получаем путь к папке скрипта
ScriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)

' Переходим в папку скрипта
WshShell.CurrentDirectory = ScriptDir

' Запускаем tayfa.bat скрыто
' Параметры Run: команда, стиль окна (0 = скрыто), ждать завершения (False)
WshShell.Run "cmd /c """ & ScriptDir & "\tayfa.bat""", 0, False
