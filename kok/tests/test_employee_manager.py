"""Тесты для employee_manager.py."""

import json
import sys
from pathlib import Path

import pytest

# Добавляем путь к модулю
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / ".tayfa" / "common"))

from employee_manager import (
    get_employees,
    get_employee,
    register_employee,
    remove_employee,
    set_employees_file,
    get_employees_file,
)


@pytest.fixture
def employees_file(tmp_path: Path) -> Path:
    """Создаёт временный employees.json и устанавливает его как текущий."""
    file_path = tmp_path / "employees.json"
    # Устанавливаем путь к файлу
    set_employees_file(file_path)
    yield file_path
    # Сброс после теста
    set_employees_file(None)


@pytest.fixture
def populated_employees_file(employees_file: Path) -> Path:
    """Создаёт employees.json с тестовыми данными."""
    data = {
        "employees": {
            "boss": {
                "role": "менеджер",
                "model": "opus",
                "created_at": "2024-01-01"
            },
            "hr": {
                "role": "HR-менеджер",
                "model": "sonnet",
                "created_at": "2024-01-01"
            },
            "developer": {
                "role": "разработчик",
                "model": "sonnet",
                "created_at": "2024-01-15"
            }
        }
    }
    employees_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return employees_file


# ============================================================
# Тесты get_employees
# ============================================================

class TestGetEmployees:
    """Тесты для get_employees()."""

    def test_get_employees_from_existing_file(self, populated_employees_file: Path):
        """Получение списка из существующего файла."""
        employees = get_employees()
        assert len(employees) == 3
        assert "boss" in employees
        assert "hr" in employees
        assert "developer" in employees
        assert employees["boss"]["role"] == "менеджер"

    def test_get_employees_empty_when_no_file(self, employees_file: Path):
        """Пустой список если файла нет."""
        # Файл не создан, должен вернуть пустой словарь
        employees = get_employees()
        assert employees == {}

    def test_get_employees_empty_when_corrupted_json(self, employees_file: Path):
        """Обработка битого JSON — возвращает пустой словарь."""
        employees_file.write_text("{ invalid json }")
        employees = get_employees()
        assert employees == {}

    def test_get_employees_returns_dict(self, populated_employees_file: Path):
        """Возвращает словарь, а не список."""
        employees = get_employees()
        assert isinstance(employees, dict)


# ============================================================
# Тесты get_employee
# ============================================================

class TestGetEmployee:
    """Тесты для get_employee()."""

    def test_get_existing_employee(self, populated_employees_file: Path):
        """Получение существующего сотрудника."""
        employee = get_employee("developer")
        assert employee is not None
        assert employee["role"] == "разработчик"
        assert employee["model"] == "sonnet"

    def test_get_nonexistent_employee_returns_none(self, populated_employees_file: Path):
        """None для несуществующего сотрудника."""
        employee = get_employee("unknown_person")
        assert employee is None

    def test_get_employee_case_sensitive(self, populated_employees_file: Path):
        """Case-sensitive поиск."""
        # boss существует, но Boss — нет
        assert get_employee("boss") is not None
        assert get_employee("Boss") is None
        assert get_employee("BOSS") is None

    def test_get_employee_from_empty_file(self, employees_file: Path):
        """Получение из пустого файла."""
        employee = get_employee("anyone")
        assert employee is None


# ============================================================
# Тесты register_employee
# ============================================================

class TestRegisterEmployee:
    """Тесты для register_employee()."""

    def test_register_new_employee(self, employees_file: Path):
        """Создание нового сотрудника."""
        result = register_employee("new_dev", "Python-разработчик", "sonnet")

        assert result["status"] == "created"
        assert result["name"] == "new_dev"
        assert result["role"] == "Python-разработчик"
        assert result["model"] == "sonnet"

        # Проверяем, что сотрудник сохранён
        employee = get_employee("new_dev")
        assert employee is not None
        assert employee["role"] == "Python-разработчик"

    def test_register_duplicate_returns_exists(self, populated_employees_file: Path):
        """Ошибка при дублировании имени."""
        result = register_employee("boss", "другая роль", "haiku")

        assert result["status"] == "exists"
        assert result["name"] == "boss"
        # Роль остаётся старой
        assert result["role"] == "менеджер"

    def test_register_with_default_model(self, employees_file: Path):
        """По умолчанию model = sonnet."""
        result = register_employee("tester", "тестировщик")

        assert result["model"] == "sonnet"
        employee = get_employee("tester")
        assert employee["model"] == "sonnet"

    def test_register_with_opus_model(self, employees_file: Path):
        """Регистрация с моделью opus."""
        result = register_employee("architect", "архитектор", "opus")

        assert result["model"] == "opus"
        employee = get_employee("architect")
        assert employee["model"] == "opus"

    def test_register_with_haiku_model(self, employees_file: Path):
        """Регистрация с моделью haiku."""
        result = register_employee("assistant", "помощник", "haiku")

        assert result["model"] == "haiku"
        employee = get_employee("assistant")
        assert employee["model"] == "haiku"

    def test_register_sets_created_at(self, employees_file: Path):
        """Автоматическое created_at."""
        from datetime import date

        register_employee("new_person", "роль")
        employee = get_employee("new_person")

        assert "created_at" in employee
        # Должна быть сегодняшняя дата
        assert employee["created_at"] == date.today().isoformat()

    def test_register_creates_file_if_not_exists(self, employees_file: Path):
        """Создаёт файл если его нет."""
        assert not employees_file.exists()

        register_employee("first_employee", "первый")

        assert employees_file.exists()
        data = json.loads(employees_file.read_text())
        assert "first_employee" in data["employees"]


# ============================================================
# Тесты remove_employee
# ============================================================

class TestRemoveEmployee:
    """Тесты для remove_employee()."""

    def test_remove_existing_employee(self, populated_employees_file: Path):
        """Удаление существующего сотрудника."""
        result = remove_employee("developer")

        assert result["status"] == "removed"
        assert result["name"] == "developer"

        # Проверяем, что удалён
        assert get_employee("developer") is None

    def test_remove_nonexistent_returns_not_found(self, populated_employees_file: Path):
        """Ошибка при удалении несуществующего."""
        result = remove_employee("unknown_person")

        assert result["status"] == "not_found"
        assert result["name"] == "unknown_person"

    def test_remove_boss_not_allowed(self, populated_employees_file: Path):
        """Boss удалить нельзя."""
        result = remove_employee("boss")

        assert result["status"] == "error"
        assert "boss" in result["message"].lower() or "hr" in result["message"].lower()

        # Boss всё ещё существует
        assert get_employee("boss") is not None

    def test_remove_hr_not_allowed(self, populated_employees_file: Path):
        """HR удалить нельзя."""
        result = remove_employee("hr")

        assert result["status"] == "error"

        # HR всё ещё существует
        assert get_employee("hr") is not None

    def test_remove_last_regular_employee(self, employees_file: Path):
        """Удаление последнего обычного сотрудника."""
        # Создаём только одного сотрудника
        register_employee("only_one", "единственный")

        result = remove_employee("only_one")

        assert result["status"] == "removed"
        assert get_employees() == {}


# ============================================================
# Тесты set_employees_file / get_employees_file
# ============================================================

class TestEmployeesFilePath:
    """Тесты для set_employees_file и get_employees_file."""

    def test_set_and_get_employees_file(self, tmp_path: Path):
        """Установка и получение пути к файлу."""
        custom_path = tmp_path / "custom" / "employees.json"

        set_employees_file(custom_path)
        assert get_employees_file() == custom_path

        # Сброс
        set_employees_file(None)

    def test_set_employees_file_accepts_string(self, tmp_path: Path):
        """Принимает строку как путь."""
        custom_path = str(tmp_path / "employees.json")

        set_employees_file(custom_path)
        assert get_employees_file() == Path(custom_path)

        # Сброс
        set_employees_file(None)

    def test_operations_use_custom_path(self, tmp_path: Path):
        """Операции используют установленный путь."""
        file1 = tmp_path / "file1.json"
        file2 = tmp_path / "file2.json"

        # Работаем с file1
        set_employees_file(file1)
        register_employee("emp1", "role1")

        # Переключаемся на file2
        set_employees_file(file2)
        register_employee("emp2", "role2")

        # Проверяем изоляцию
        set_employees_file(file1)
        assert get_employee("emp1") is not None
        assert get_employee("emp2") is None

        set_employees_file(file2)
        assert get_employee("emp1") is None
        assert get_employee("emp2") is not None

        # Сброс
        set_employees_file(None)
