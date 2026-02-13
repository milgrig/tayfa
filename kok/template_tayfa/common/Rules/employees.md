# Список сотрудников

## Единый реестр

Источник правды — **`.tayfa/common/employees.json`**. Оркестратор показывает **только** зарегистрированных там.

- Новые сотрудники — **только** через `python .tayfa/hr/create_employee.py <имя>`.
- Просмотр: `python .tayfa/common/employee_manager.py list`
- Ручная регистрация: `python .tayfa/common/employee_manager.py register <имя> "<роль>"`
- Удаление: `python .tayfa/common/employee_manager.py remove <имя>` (boss и hr удалить нельзя).

---

## boss

**Роль**: Руководитель, координатор всех задач.

**Когда обращаться к boss**:
- Задача выполнена — нужна следующая задача или подтверждение.
- Серьёзные вопросы по задаче.
- Нужно создать нового сотрудника.

**Кто может обращаться**: любой сотрудник.

---

## hr

**Роль**: HR-менеджер, управление сотрудниками и агентами.

**Что умеет hr**:
- Создавать новых сотрудников (онбординг) через `.tayfa/hr/create_employee.py`.
- Менять системные промты сотрудников.

**Кто может обращаться**: только `boss`.

---

## Система задач

Каждая задача имеет **3 исполнителей**: постановщик, разработчик, тестировщик. Задачи создаёт boss через `.tayfa/common/task_manager.py`. Подробнее — `.tayfa/common/Rules/teamwork.md`.

```bash
python .tayfa/common/task_manager.py list              # все задачи
python .tayfa/common/task_manager.py get T001          # одна задача
python .tayfa/common/task_manager.py result T001 "..." # записать результат
python .tayfa/common/task_manager.py status T001 ...   # изменить статус
```

---

## Правила обращения

1. Не знаешь к кому — обращайся к `boss`.
2. К `hr` напрямую не обращайся (если ты не `boss`).
3. Для обращения — JSON в `request/`:

```json
{
  "name": "boss",
  "prompt": "Описание вопроса или результата"
}
```
