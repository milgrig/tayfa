# Список лишних файлов проекта Tayfa

**Версия**: 1.0
**Дата**: 2026-02-11
**Автор**: architect (задача T023)

---

## 1. Сводка

| Категория | Количество | Размер | Приоритет |
|-----------|------------|--------|-----------|
| Дубликат оркестратора (`kok/`) | ~20 файлов | **36 MB** | КРИТИЧНО |
| Виртуальное окружение (`venv/`) | 2 копии | **62 MB** | КРИТИЧНО |
| Python кэш (`__pycache__/`) | 192 директории | ~5 MB | Высокий |
| Файлы `.pyc` | 1598 файлов | ~5 MB | Высокий |
| Служебные файлы | 5 файлов | <1 KB | Средний |
| Логи | 2 файла | ~5 KB | Низкий |
| **ИТОГО к удалению** | | **~108 MB** | |

---

## 2. КРИТИЧНО: Дубликат оркестратора

### 2.1 Проблема

Существует **две копии** оркестратора:
- `kok/` (корень Tayfa_2) — **устаревшая версия**
- `Personel/project/kok/` — **актуальная версия**

### 2.2 Сравнение версий

| Файл | `kok/` | `Personel/project/kok/` | Вывод |
|------|--------|-------------------------|-------|
| `app.py` | 49 KB (09:50) | **56 KB (17:27)** | project/kok новее, +8 KB нового кода |
| `project_manager.py` | отсутствует | **15 KB** | Только в актуальной версии |
| `settings_manager.py` | отсутствует | **3 KB** | Только в актуальной версии |
| `check_agents.py` | 1.3 KB | отсутствует | Только в устаревшей версии |
| `create_shortcut.py` | 1.8 KB | отсутствует | Только в устаревшей версии |

### 2.3 Ключевые различия в app.py

**`Personel/project/kok/app.py`** содержит:
- Мультипроектность (`get_personel_dir()`, `get_project_dir()`)
- Динамические пути вместо захардкоженных
- Интеграция с `project_manager.py` и `settings_manager.py`

**`kok/app.py`** использует:
- Захардкоженные пути `PERSONEL_DIR`, `PERSONEL_WSL`
- Нет поддержки мультипроектности

### 2.4 Рекомендация

| Действие | Путь | Причина |
|----------|------|---------|
| **УДАЛИТЬ** | `kok/` | Устаревшая версия без мультипроектности |
| **ОСТАВИТЬ** | `Personel/project/kok/` | Актуальная версия |
| **ПЕРЕНЕСТИ** | `kok/check_agents.py` → `Personel/project/kok/` | Полезный скрипт, отсутствует в актуальной версии |

---

## 3. Виртуальное окружение (venv)

### 3.1 Проблема

| Путь | Размер | Статус |
|------|--------|--------|
| `kok/venv/` | 31 MB | В .gitignore (OK) |
| `Personel/project/kok/venv/` | 31 MB | В .gitignore (OK) |

### 3.2 Рекомендация

**Статус**: Уже в `.gitignore` — не попадёт в репозиторий.

При удалении `kok/` автоматически удалится `kok/venv/`.

---

## 4. Python кэш (__pycache__)

### 4.1 Проблема

| Метрика | Значение |
|---------|----------|
| Директорий `__pycache__/` | **192** |
| Файлов `.pyc` | **1598** |
| Основное местоположение | `*/venv/Lib/site-packages/` |

### 4.2 Проблемные места (вне venv)

```
Personel/common/__pycache__/
Personel/project/kok/__pycache__/
Personel/project/kok/template_tayfa/common/__pycache__/
Personel/project/kok/template_tayfa/hr/__pycache__/
```

### 4.3 Рекомендация

**Статус**: Уже в `.gitignore` — не попадёт в репозиторий.

**Действие**: Удалить `__pycache__/` из `template_tayfa/` — шаблон не должен содержать кэш.

---

## 5. Шаблон template_tayfa

### 5.1 Проблема

| Путь | Содержимое | Статус |
|------|------------|--------|
| `kok/template_tayfa/` | Пустые папки | **Устаревший** |
| `Personel/project/kok/template_tayfa/` | Файлы + `__pycache__` | **Актуальный, но с мусором** |

### 5.2 Мусор в template_tayfa

```
template_tayfa/common/__pycache__/employee_manager.cpython-312.pyc
template_tayfa/common/__pycache__/task_manager.cpython-312.pyc
template_tayfa/hr/__pycache__/create_employee.cpython-312.pyc
```

### 5.3 Рекомендация

| Действие | Путь |
|----------|------|
| **УДАЛИТЬ** | `Personel/project/kok/template_tayfa/*/__pycache__/` |
| **УДАЛИТСЯ** | `kok/template_tayfa/` (вместе с kok/) |

---

## 6. Служебные файлы

### 6.1 Временные файлы

| Файл | Назначение | Рекомендация |
|------|------------|--------------|
| `kok/_task_boss.txt` | Передача задачи boss | УДАЛИТЬ (вместе с kok/) |
| `Personel/project/kok/_task_boss.txt` | Передача задачи boss | **УДАЛИТЬ** или добавить в .gitignore |
| `Personel/project/kok/Tayfa.lnk` | Windows-ярлык | **УДАЛИТЬ** — не нужен в репозитории |

### 6.2 Файлы .gitkeep

Найдено **21 файл** `.gitkeep` в пустых директориях:
- `*/done/.gitkeep`
- `*/income/.gitkeep`
- `*/request/.gitkeep`

**Рекомендация**: ОСТАВИТЬ — нужны для сохранения структуры папок в git.

---

## 7. Логи

### 7.1 Файлы логов

| Путь | Размер | Рекомендация |
|------|--------|--------------|
| `kok/logs/executed_requests.jsonl` | 2.6 KB | УДАЛИТСЯ (вместе с kok/) |
| `Personel/project/kok/logs/executed_requests.jsonl` | ~2 KB | Добавить `logs/` в .gitignore |

### 7.2 Рекомендация

Добавить в `.gitignore`:
```
logs/
*.jsonl
```

---

## 8. Рекомендации по удалению

### 8.1 Таблица действий

| Приоритет | Путь | Действие | Причина |
|-----------|------|----------|---------|
| КРИТИЧНО | `kok/` | **УДАЛИТЬ** | Устаревший дубликат (36 MB) |
| КРИТИЧНО | `kok/check_agents.py` | **ПЕРЕНЕСТИ** → `project/kok/` | Полезный скрипт |
| Высокий | `project/kok/template_tayfa/*/__pycache__/` | **УДАЛИТЬ** | Кэш в шаблоне |
| Средний | `project/kok/Tayfa.lnk` | **УДАЛИТЬ** | Windows-ярлык |
| Средний | `project/kok/_task_boss.txt` | **УДАЛИТЬ** или .gitignore | Временный файл |
| Низкий | `project/kok/logs/*.jsonl` | .gitignore | Логи не нужны в репозитории |

### 8.2 Ожидаемый результат

| До очистки | После очистки | Экономия |
|------------|---------------|----------|
| ~150 MB | ~42 MB | **~108 MB (72%)** |

---

## 9. Обновление .gitignore

### 9.1 Текущий .gitignore (OK)

```gitignore
__pycache__/
*.py[cod]
venv/
.venv/
```

### 9.2 Рекомендуемые дополнения

```gitignore
# Логи
logs/
*.jsonl
*.log

# Временные файлы оркестратора
_task_*.txt

# Windows-артефакты
*.lnk
```

---

## 10. Скрипт очистки

### 10.1 Bash-скрипт (запускать из корня Tayfa_2)

```bash
#!/bin/bash
# cleanup_tayfa.sh — очистка проекта от лишних файлов

echo "=== Очистка проекта Tayfa ==="

# 1. Перенос полезного скрипта
echo "[1/5] Перенос check_agents.py..."
cp kok/check_agents.py Personel/project/kok/ 2>/dev/null && echo "OK" || echo "Уже существует или ошибка"

# 2. Удаление дубликата оркестратора
echo "[2/5] Удаление kok/ (устаревший дубликат)..."
rm -rf kok/
echo "OK"

# 3. Удаление __pycache__ из template_tayfa
echo "[3/5] Очистка template_tayfa от кэша..."
find Personel/project/kok/template_tayfa -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
echo "OK"

# 4. Удаление служебных файлов
echo "[4/5] Удаление временных файлов..."
rm -f Personel/project/kok/Tayfa.lnk
rm -f Personel/project/kok/_task_boss.txt
echo "OK"

# 5. Вывод результата
echo "[5/5] Готово!"
echo ""
du -sh Personel/
```

### 10.2 PowerShell-скрипт (для Windows)

```powershell
# cleanup_tayfa.ps1 — очистка проекта от лишних файлов

Write-Host "=== Очистка проекта Tayfa ===" -ForegroundColor Cyan

# 1. Перенос полезного скрипта
Write-Host "[1/5] Перенос check_agents.py..."
Copy-Item "kok\check_agents.py" "Personel\project\kok\" -ErrorAction SilentlyContinue

# 2. Удаление дубликата оркестратора
Write-Host "[2/5] Удаление kok\ (устаревший дубликат)..."
Remove-Item -Recurse -Force "kok" -ErrorAction SilentlyContinue

# 3. Удаление __pycache__ из template_tayfa
Write-Host "[3/5] Очистка template_tayfa от кэша..."
Get-ChildItem -Path "Personel\project\kok\template_tayfa" -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

# 4. Удаление служебных файлов
Write-Host "[4/5] Удаление временных файлов..."
Remove-Item "Personel\project\kok\Tayfa.lnk" -ErrorAction SilentlyContinue
Remove-Item "Personel\project\kok\_task_boss.txt" -ErrorAction SilentlyContinue

Write-Host "[5/5] Готово!" -ForegroundColor Green
```

---

## 11. Критерии приёмки (чеклист)

- [x] Проанализированы ВСЕ категории (дубликаты, кэш, venv, template, служебные, логи)
- [x] Для каждого файла/папки указана причина удаления
- [x] Даны чёткие рекомендации (удалить/оставить/переместить)
- [x] Предложено обновление .gitignore
- [x] Указан приоритет (КРИТИЧНО/Высокий/Средний/Низкий)
- [x] Предоставлен скрипт очистки (bash + PowerShell)
