# Тесты для проекта Tayfa

## Структура

```
tests/
├── __init__.py              # Инициализация пакета тестов
├── conftest.py              # Общие fixtures для всех тестов
├── test_example.py          # Примеры тестов и проверка fixtures
├── test_settings_manager.py # Тесты для settings_manager.py
├── test_employee_manager.py # Тесты для employee_manager.py
└── test_backlog_manager.py  # Тесты для backlog_manager.py
```

## Запуск тестов

### Все тесты
```bash
pytest tests/
```

### Конкретный файл
```bash
pytest tests/test_settings_manager.py
```

### Конкретный тест
```bash
pytest tests/test_settings_manager.py::test_load_settings
```

### С подробным выводом
```bash
pytest tests/ -v
```

### С покрытием кода
```bash
pytest tests/ --cov=kok --cov-report=html
```

### Только async тесты
```bash
pytest tests/ -k async
```

### С маркерами
```bash
# Только unit тесты
pytest tests/ -m unit

# Только integration тесты
pytest tests/ -m integration

# Пропустить медленные тесты
pytest tests/ -m "not slow"
```

## Доступные fixtures

### tmp_tayfa_dir
Создаёт временную директорию .tayfa с базовой структурой:
```python
def test_example(tmp_tayfa_dir):
    assert tmp_tayfa_dir.exists()
    assert (tmp_tayfa_dir / "config.json").exists()
```

### mock_settings
Возвращает тестовые настройки:
```python
def test_example(mock_settings):
    assert mock_settings["theme"] == "dark"
    assert mock_settings["port"] == 8008
```

### mock_employees
Возвращает тестовый список сотрудников:
```python
def test_example(mock_employees):
    assert "boss" in mock_employees
    assert mock_employees["boss"]["role"] == "менеджер"
```

### mock_backlog_task
Возвращает тестовую задачу для бэклога:
```python
def test_example(mock_backlog_task):
    assert mock_backlog_task["id"] == "T001"
    assert mock_backlog_task["status"] == "новая"
```

### settings_files
Создаёт временные файлы settings.json и secret_settings.json:
```python
def test_example(settings_files):
    settings_path, secret_settings_path = settings_files
    assert settings_path.exists()
```

### mock_git_config
Возвращает тестовую конфигурацию Git:
```python
def test_example(mock_git_config):
    assert mock_git_config["defaultBranch"] == "main"
```

### clean_json_files
Автоматически очищает JSON файлы после теста:
```python
def test_example(clean_json_files, tmp_path):
    file = tmp_path / "test.json"
    file.write_text('{"key": "value"}')
    # После теста файл будет удалён
```

## Маркеры тестов

Доступные маркеры (определены в pytest.ini):

- `@pytest.mark.unit` - юнит-тесты
- `@pytest.mark.integration` - интеграционные тесты
- `@pytest.mark.slow` - медленные тесты
- `@pytest.mark.api` - тесты API endpoints
- `@pytest.mark.settings` - тесты настроек
- `@pytest.mark.backlog` - тесты работы с бэклогом
- `@pytest.mark.employees` - тесты работы с сотрудниками
- `@pytest.mark.git` - тесты Git интеграции

Пример использования:
```python
@pytest.mark.unit
def test_something():
    assert True

@pytest.mark.slow
@pytest.mark.integration
async def test_complex_scenario():
    # Сложный тест
    pass
```

## Async тесты

Для async тестов используйте декоратор `@pytest.mark.asyncio`:

```python
@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result == expected_value
```

## Конфигурация

Настройки pytest находятся в файле `pytest.ini`:

- `asyncio_mode = auto` - автоматический режим для async тестов
- `testpaths = tests` - путь к директории с тестами
- `python_files = test_*.py` - паттерн для файлов тестов

## Советы

1. **Изолируйте тесты**: Каждый тест должен быть независим от других
2. **Используйте fixtures**: Переиспользуйте общий setup код через fixtures
3. **Маркируйте тесты**: Используйте маркеры для категоризации
4. **Проверяйте покрытие**: Стремитесь к покрытию >80%
5. **Пишите понятные сообщения**: Используйте информативные assert сообщения

## Пример теста

```python
import pytest

@pytest.mark.unit
def test_example_function(tmp_tayfa_dir, mock_settings):
    """Пример хорошо написанного теста."""
    # Arrange (подготовка)
    config_path = tmp_tayfa_dir / "config.json"

    # Act (действие)
    result = some_function(config_path, mock_settings)

    # Assert (проверка)
    assert result is not None
    assert result["status"] == "success"
```
