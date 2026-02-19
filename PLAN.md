# Plan: Graceful Timeout Recovery для агентов

## Проблема
При таймауте (`subprocess.TimeoutExpired`) в `_run_claude()`:
- Процесс убивается, partial output теряется
- `session_id` не возвращается → нельзя продолжить сессию
- Вся работа агента пропадает
- В retry-логике `app.py` агент заново получает ту же задачу без контекста

## Решение: Popen + polling + resume

Вместо `subprocess.run()` (блокирующий, убивает при таймауте) →
`subprocess.Popen()` + периодический polling, при таймауте:
1. Захватить partial stdout (если есть)
2. **Не убивать процесс сразу** — дать `proc.communicate(timeout=30)` для graceful завершения
3. Вернуть partial result + session_id + флаг `"timeout": true`
4. В retry-логике `app.py` — использовать session_id для `--resume` с follow-up промптом

---

## Шаг 1: `kok/claude_api.py` — заменить `subprocess.run` на `Popen` в `_run_claude()`

**Файл:** `kok/claude_api.py`, строки 333-365

**Было:**
```python
proc = subprocess.run(
    cmd_parts, input=prompt, text=True, capture_output=True,
    timeout=timeout, cwd=workdir or None, encoding="utf-8", shell=False,
)
...
except subprocess.TimeoutExpired:
    return {"code": -1, "result": "", "error": "timeout", "session_id": ""}
```

**Станет:**
```python
proc = subprocess.Popen(
    cmd_parts,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    encoding="utf-8",
    cwd=workdir or None,
)
try:
    stdout, stderr = proc.communicate(input=prompt, timeout=timeout)
except subprocess.TimeoutExpired:
    # Попытка получить partial output
    partial_stdout = ""
    partial_stderr = ""
    try:
        # Даём 30 секунд на graceful завершение
        stdout, stderr = proc.communicate(timeout=30)
        partial_stdout = stdout or ""
        partial_stderr = stderr or ""
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            stdout, stderr = proc.communicate(timeout=5)
            partial_stdout = stdout or ""
            partial_stderr = stderr or ""
        except Exception:
            pass

    # Попытка извлечь session_id из partial output (JSON)
    session_id = ""
    if partial_stdout:
        try:
            data = json.loads(partial_stdout)
            session_id = data.get("session_id", "")
            partial_stdout = data.get("result", partial_stdout)
        except json.JSONDecodeError:
            pass  # partial_stdout остаётся как есть (raw text)

    logger.warning(
        f"_run_claude: TIMEOUT after {timeout}s, "
        f"partial_stdout_len={len(partial_stdout)}, session_id={session_id[:8] if session_id else 'none'}"
    )

    return {
        "code": -1,
        "result": partial_stdout,
        "error": "timeout",
        "session_id": session_id,
        "is_timeout": True,
    }
```

**Суть:** при таймауте Claude CLI мог уже записать файлы, сделать часть работы. Даже если stdout пуст — `session_id` даёт возможность продолжить через `--resume`.

---

## Шаг 2: `kok/claude_api.py` — сохранять session при таймауте

**Файл:** `kok/claude_api.py`, строки 605-625 (в endpoint `/run`)

Сейчас session сохраняется только при `new_sid` (успех). Нужно также сохранять при таймауте:

```python
# После вызова _run_claude:
new_sid = result.get("session_id")
if new_sid:
    _save_session(req.name, new_sid, project_path, model=run_model)

# НОВОЕ: при таймауте тоже вернуть session_id, не очищая сессию
if result.get("is_timeout"):
    return result  # Пусть caller решает, retry или нет
```

---

## Шаг 3: `kok/app.py` — умный retry при таймауте с resume-промптом

**Файл:** `kok/app.py`, строки 2526-2625 (retry loop в `api_trigger_task`)

Сейчас при retry агент получает тот же самый промпт заново. Это плохо — он начинает с нуля.

**Новая логика для таймаутов:**

```python
# В блоке except для Claude API:
except Exception as exc:
    last_error = exc
    error_type = _classify_error(exc)

    # НОВОЕ: Для таймаутов — используем resume-промпт
    if error_type == "timeout" and attempt < _MAX_RETRY_ATTEMPTS:
        # Промпт-пинг: проверить статус и продолжить
        timeout_resume_prompt = (
            "Ты получил таймаут на предыдущем запросе. "
            "Если ты работал над задачей и сделал часть работы — "
            "кратко опиши что уже сделано и продолжи работу. "
            "Если ты завис или занимался не тем — начни задачу заново. "
            "Оригинальная задача: " + full_prompt[:500]
        )
        # Retry с resume-промптом (session сохранена, --resume сработает)
        await asyncio.sleep(_RETRY_DELAY_SEC)
        continue  # следующий attempt использует session_id автоматически
```

Но тут важный нюанс: **промпт для retry нужно заменить**. В текущей архитектуре `full_prompt` — фиксированный. Нужно добавить переменную `retry_prompt`:

```python
retry_prompt = None  # None = использовать оригинальный full_prompt

for attempt in range(1, _MAX_RETRY_ATTEMPTS + 1):
    current_prompt = retry_prompt or full_prompt
    retry_prompt = None  # сбросить для следующей итерации

    # ... вызов API с current_prompt ...

    except Exception as exc:
        if error_type == "timeout" and attempt < _MAX_RETRY_ATTEMPTS:
            retry_prompt = (
                "Ты получил таймаут на предыдущей попытке. "
                "Если работал правильно — продолжи с того места. "
                "Если застрял — начни заново.\n\n"
                f"Оригинальная задача:\n{full_prompt[:1000]}"
            )
```

---

## Шаг 4: `kok/app.py` — передавать `is_timeout` и partial result из claude_api

**Файл:** `kok/app.py`, строка 670-671

Сейчас `httpx.ReadTimeout` → сразу 504. Но `claude_api.py` уже обрабатывает таймаут внутри и возвращает JSON с `is_timeout`. Проблема в том, что `httpx` сам таймаутит HTTP-соединение.

**Решение:** Увеличить HTTP-таймаут `call_claude_api` чуть больше чем agent_timeout, чтобы `claude_api.py` успел вернуть свой graceful-ответ:

```python
# В app.py, вызов call_claude_api:
timeout=get_agent_timeout() + 60  # +60s запас для graceful shutdown в claude_api
```

Это гарантирует, что `claude_api.py` **всегда** успеет вернуть ответ (даже при таймауте внутри subprocess), а `app.py` получит `is_timeout` + `session_id`.

---

## Шаг 5: Обработка ответа с `is_timeout` в trigger

**Файл:** `kok/app.py`, в блоке Claude API (строки 2561-2596)

После получения `api_result`:
```python
api_result = await call_claude_api(...)

# НОВОЕ: Проверить, был ли таймаут
if api_result.get("is_timeout"):
    partial = api_result.get("result", "")
    logger.warning(
        f"[Trigger] {task_id}: agent {agent_name} timed out, "
        f"partial_len={len(partial)}, has_session={bool(api_result.get('session_id'))}"
    )
    # Не считаем это успехом — пусть retry-логика продолжит
    raise HTTPException(status_code=504, detail=f"Agent timeout (partial work saved): {partial[:200]}")
```

---

## Итого: что изменится

| Файл | Что меняется |
|------|-------------|
| `kok/claude_api.py` | `subprocess.run` → `Popen` + graceful timeout с partial output и session_id |
| `kok/claude_api.py` | `/run` endpoint: сохранять session при таймауте |
| `kok/app.py` | HTTP-таймаут = agent_timeout + 60s (запас) |
| `kok/app.py` | Retry loop: при таймауте использовать resume-промпт вместо повторного оригинального |
| `kok/app.py` | Обработка `is_timeout` в trigger response |

## Что НЕ меняется
- Config (`agent_timeout_seconds`) — без изменений
- Session management — используем существующую систему per-model sessions
- Error classification — `"timeout"` уже retryable
- Failure logging — продолжает работать как есть
