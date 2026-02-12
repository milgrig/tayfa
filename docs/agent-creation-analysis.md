# Анализ различий в создании агентов

## Найденная причина: типы в Pydantic модели

На разных компьютерах агенты работали по-разному: на одном была память (session_id сохранялся), на другом — нет.

**Причина найдена в файле `claude_api.py`:**

### Старая версия (БЕЗ памяти):
```python
class UnifiedRequest(BaseModel):
    name: str = ""
    prompt: str = ""
    system_prompt: str = ""
```

### Новая версия (С памятью):
```python
from typing import Optional

class UnifiedRequest(BaseModel):
    name: Optional[str] = ""
    prompt: Optional[str] = ""
    system_prompt: Optional[str] = ""
```

### Почему это критично

Оркестратор (`app.py`) отправляет JSON с `null` значениями:
```json
{"name": "boss", "prompt": null, "system_prompt": "...", "workdir": "/mnt/c/..."}
```

| Тип | Поведение при `null` |
|-----|---------------------|
| `str = ""` | Ошибка валидации или некорректная конвертация |
| `Optional[str] = ""` | Корректно принимает `null` как `None` |

**Результат в старой версии:**
1. Запросы частично падали или обрабатывались некорректно
2. `session_id` не сохранялся между вызовами
3. Каждый запрос создавал НОВУЮ сессию Claude CLI
4. Агент "забывал" контекст разговора

## Решение

1. Файл `claude_api.py` добавлен в репозиторий: `kok/claude_api.py`
2. `app.py` теперь запускает его из `kok/`, а не из `~/`

## Что нужно на новом компьютере

```bash
# 1. Создать venv
cd ~
python3 -m venv claude_venv
source claude_venv/bin/activate
pip install fastapi uvicorn httpx pydantic

# 2. Авторизовать Claude CLI
claude --dangerously-skip-permissions
```

---
*Спринт: S004, Задача: T018*
