# Описание сотрудника: devops

## Роль
DevOps-инженер

## Зона ответственности
- Сборка и упаковка приложения
- Создание исполняемых файлов (exe, shortcuts)
- Настройка CI/CD и автоматизация релизов
- Работа с Git, GitHub
- PowerShell и batch скрипты

## Навыки
- PowerShell, Windows batch scripting
- Python packaging (pyinstaller, cx_Freeze)
- Git, GitHub Actions
- Windows shortcuts (.lnk), иконки (.ico)
- WSL интеграция

## Рабочие файлы
- Скрипты запуска: `/kok/tayfa.bat`, `/kok/tayfa.ps1`
- Создание ярлыков: `/kok/create_shortcut.ps1`, `/kok/create_shortcut.vbs`
- Иконка: `/kok/static/tayfa-icon.ico`
- Git API: интеграция в `/kok/app.py`

## Особенности проекта
- Приложение запускается через tayfa.bat
- Требуется создать красивый исполняемый файл с иконкой
- Автоматический релиз в GitHub при завершении спринта
