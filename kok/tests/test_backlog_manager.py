"""Тесты для backlog_manager.py."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Добавляем путь к модулю
sys.path.insert(0, str(Path(__file__).parent.parent.parent / ".tayfa" / "common"))

import backlog_manager


@pytest.fixture
def temp_backlog(tmp_path: Path, monkeypatch):
    """
    Фикстура для изолированного тестирования backlog_manager.
    Подменяет BACKLOG_FILE на временный файл.
    """
    backlog_file = tmp_path / "backlog.json"
    monkeypatch.setattr(backlog_manager, "BACKLOG_FILE", backlog_file)
    return backlog_file


@pytest.fixture
def populated_backlog(temp_backlog: Path):
    """
    Фикстура с предзаполненным бэклогом.
    """
    data = {
        "items": [
            {
                "id": "B001",
                "title": "Фича 1",
                "description": "Описание фичи 1",
                "priority": "high",
                "next_sprint": True,
                "created_by": "boss",
                "created_at": "2024-01-01T10:00:00",
                "updated_at": "2024-01-01T10:00:00"
            },
            {
                "id": "B002",
                "title": "Фича 2",
                "description": "Описание фичи 2",
                "priority": "medium",
                "next_sprint": False,
                "created_by": "boss",
                "created_at": "2024-01-02T10:00:00",
                "updated_at": "2024-01-02T10:00:00"
            },
            {
                "id": "B003",
                "title": "Фича 3",
                "description": "Описание фичи 3",
                "priority": "low",
                "next_sprint": True,
                "created_by": "analyst",
                "created_at": "2024-01-03T10:00:00",
                "updated_at": "2024-01-03T10:00:00"
            }
        ],
        "next_id": 4
    }
    temp_backlog.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return temp_backlog


# ============================================================================
# Тесты get_items()
# ============================================================================

class TestGetItems:
    """Тесты для функции get_items()."""

    def test_get_all_items(self, populated_backlog):
        """Получение всех записей."""
        items = backlog_manager.get_items()
        assert len(items) == 3
        assert items[0]["id"] == "B001"
        assert items[1]["id"] == "B002"
        assert items[2]["id"] == "B003"

    def test_get_items_empty_backlog(self, temp_backlog):
        """Пустой список если файла нет."""
        items = backlog_manager.get_items()
        assert items == []

    def test_filter_by_priority_high(self, populated_backlog):
        """Фильтрация по priority=high."""
        items = backlog_manager.get_items(priority="high")
        assert len(items) == 1
        assert items[0]["id"] == "B001"
        assert items[0]["priority"] == "high"

    def test_filter_by_priority_medium(self, populated_backlog):
        """Фильтрация по priority=medium."""
        items = backlog_manager.get_items(priority="medium")
        assert len(items) == 1
        assert items[0]["id"] == "B002"

    def test_filter_by_priority_low(self, populated_backlog):
        """Фильтрация по priority=low."""
        items = backlog_manager.get_items(priority="low")
        assert len(items) == 1
        assert items[0]["id"] == "B003"

    def test_filter_by_next_sprint_true(self, populated_backlog):
        """Фильтрация по next_sprint=True."""
        items = backlog_manager.get_items(next_sprint=True)
        assert len(items) == 2
        assert all(item["next_sprint"] is True for item in items)
        assert items[0]["id"] == "B001"
        assert items[1]["id"] == "B003"

    def test_filter_by_next_sprint_false(self, populated_backlog):
        """Фильтрация по next_sprint=False."""
        items = backlog_manager.get_items(next_sprint=False)
        assert len(items) == 1
        assert items[0]["id"] == "B002"
        assert items[0]["next_sprint"] is False

    def test_combined_filters(self, populated_backlog):
        """Комбинированная фильтрация по priority и next_sprint."""
        items = backlog_manager.get_items(priority="high", next_sprint=True)
        assert len(items) == 1
        assert items[0]["id"] == "B001"


# ============================================================================
# Тесты get_item()
# ============================================================================

class TestGetItem:
    """Тесты для функции get_item()."""

    def test_get_existing_item(self, populated_backlog):
        """Получение существующей записи."""
        item = backlog_manager.get_item("B001")
        assert item is not None
        assert item["id"] == "B001"
        assert item["title"] == "Фича 1"
        assert item["priority"] == "high"

    def test_get_nonexistent_item(self, populated_backlog):
        """Получение несуществующей записи."""
        item = backlog_manager.get_item("B999")
        assert item is None

    def test_get_item_empty_backlog(self, temp_backlog):
        """Получение записи из пустого бэклога."""
        item = backlog_manager.get_item("B001")
        assert item is None


# ============================================================================
# Тесты add_item()
# ============================================================================

class TestAddItem:
    """Тесты для функции add_item()."""

    def test_add_item_minimal_data(self, temp_backlog):
        """Создание с минимальными данными."""
        item = backlog_manager.add_item("Новая фича")

        assert "error" not in item
        assert item["id"] == "B001"
        assert item["title"] == "Новая фича"
        assert item["description"] == ""
        assert item["priority"] == "medium"  # default
        assert item["next_sprint"] is False  # default
        assert item["created_by"] == "boss"  # default

    def test_add_item_full_data(self, temp_backlog):
        """Создание с полными данными."""
        item = backlog_manager.add_item(
            title="Полная фича",
            description="Детальное описание",
            priority="high",
            next_sprint=True,
            created_by="analyst"
        )

        assert "error" not in item
        assert item["id"] == "B001"
        assert item["title"] == "Полная фича"
        assert item["description"] == "Детальное описание"
        assert item["priority"] == "high"
        assert item["next_sprint"] is True
        assert item["created_by"] == "analyst"
        assert "created_at" in item
        assert "updated_at" in item

    def test_add_item_auto_increment_id(self, temp_backlog):
        """Автогенерация ID (B001, B002...)."""
        item1 = backlog_manager.add_item("Фича 1")
        item2 = backlog_manager.add_item("Фича 2")
        item3 = backlog_manager.add_item("Фича 3")

        assert item1["id"] == "B001"
        assert item2["id"] == "B002"
        assert item3["id"] == "B003"

    def test_add_item_invalid_priority(self, temp_backlog):
        """Валидация priority — недопустимое значение."""
        result = backlog_manager.add_item("Фича", priority="invalid")

        assert "error" in result
        assert "invalid" in result["error"]
        assert "high, medium, low" in result["error"]

    def test_add_item_valid_priorities(self, temp_backlog):
        """Валидация priority — все допустимые значения."""
        for priority in ["high", "medium", "low"]:
            item = backlog_manager.add_item(f"Фича {priority}", priority=priority)
            assert "error" not in item
            assert item["priority"] == priority

    def test_add_item_default_priority_medium(self, temp_backlog):
        """Дефолтный priority = medium."""
        item = backlog_manager.add_item("Фича без приоритета")
        assert item["priority"] == "medium"

    def test_add_item_persisted(self, temp_backlog):
        """Запись сохраняется в файл."""
        backlog_manager.add_item("Персистентная фича")

        # Читаем напрямую из файла
        data = json.loads(temp_backlog.read_text())
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "Персистентная фича"
        assert data["next_id"] == 2


# ============================================================================
# Тесты edit_item()
# ============================================================================

class TestEditItem:
    """Тесты для функции edit_item()."""

    def test_edit_item_update_title(self, populated_backlog):
        """Обновление title."""
        result = backlog_manager.edit_item("B001", title="Новое название")

        assert "error" not in result
        assert result["title"] == "Новое название"
        assert result["description"] == "Описание фичи 1"  # не изменилось

    def test_edit_item_update_description(self, populated_backlog):
        """Обновление description."""
        result = backlog_manager.edit_item("B001", description="Новое описание")

        assert "error" not in result
        assert result["description"] == "Новое описание"
        assert result["title"] == "Фича 1"  # не изменилось

    def test_edit_item_update_priority(self, populated_backlog):
        """Обновление priority."""
        result = backlog_manager.edit_item("B001", priority="low")

        assert "error" not in result
        assert result["priority"] == "low"

    def test_edit_item_nonexistent(self, populated_backlog):
        """Ошибка для несуществующего ID."""
        result = backlog_manager.edit_item("B999", title="Новое")

        assert "error" in result
        assert "B999" in result["error"]
        assert "не найдена" in result["error"]

    def test_edit_item_partial_update(self, populated_backlog):
        """Частичное обновление (только title)."""
        original = backlog_manager.get_item("B001")
        result = backlog_manager.edit_item("B001", title="Только название")

        assert result["title"] == "Только название"
        assert result["description"] == original["description"]
        assert result["priority"] == original["priority"]

    def test_edit_item_invalid_priority(self, populated_backlog):
        """Ошибка при недопустимом priority."""
        result = backlog_manager.edit_item("B001", priority="invalid")

        assert "error" in result
        assert "invalid" in result["error"]

    def test_edit_item_updates_timestamp(self, populated_backlog):
        """updated_at обновляется при редактировании."""
        original = backlog_manager.get_item("B001")
        result = backlog_manager.edit_item("B001", title="Новое")

        assert result["updated_at"] != original["updated_at"]

    def test_edit_item_persisted(self, populated_backlog):
        """Изменения сохраняются в файл."""
        backlog_manager.edit_item("B001", title="Сохранённое")

        # Читаем напрямую из файла
        data = json.loads(populated_backlog.read_text())
        item = next(i for i in data["items"] if i["id"] == "B001")
        assert item["title"] == "Сохранённое"


# ============================================================================
# Тесты remove_item()
# ============================================================================

class TestRemoveItem:
    """Тесты для функции remove_item()."""

    def test_remove_existing_item(self, populated_backlog):
        """Удаление существующей записи."""
        result = backlog_manager.remove_item("B001")

        assert "error" not in result
        assert result["status"] == "removed"
        assert result["id"] == "B001"

        # Проверяем что запись удалена
        items = backlog_manager.get_items()
        assert len(items) == 2
        assert all(item["id"] != "B001" for item in items)

    def test_remove_nonexistent_item(self, populated_backlog):
        """Ошибка для несуществующего ID."""
        result = backlog_manager.remove_item("B999")

        assert "error" in result
        assert "B999" in result["error"]
        assert "не найдена" in result["error"]

    def test_remove_item_persisted(self, populated_backlog):
        """Удаление сохраняется в файл."""
        backlog_manager.remove_item("B002")

        # Читаем напрямую из файла
        data = json.loads(populated_backlog.read_text())
        assert len(data["items"]) == 2
        assert all(i["id"] != "B002" for i in data["items"])


# ============================================================================
# Тесты toggle_next_sprint()
# ============================================================================

class TestToggleNextSprint:
    """Тесты для функции toggle_next_sprint()."""

    def test_toggle_false_to_true(self, populated_backlog):
        """Переключение false → true."""
        # B002 имеет next_sprint=False
        result = backlog_manager.toggle_next_sprint("B002")

        assert "error" not in result
        assert result["next_sprint"] is True

    def test_toggle_true_to_false(self, populated_backlog):
        """Переключение true → false."""
        # B001 имеет next_sprint=True
        result = backlog_manager.toggle_next_sprint("B001")

        assert "error" not in result
        assert result["next_sprint"] is False

    def test_toggle_nonexistent_item(self, populated_backlog):
        """Ошибка для несуществующего ID."""
        result = backlog_manager.toggle_next_sprint("B999")

        assert "error" in result
        assert "B999" in result["error"]
        assert "не найдена" in result["error"]

    def test_toggle_updates_timestamp(self, populated_backlog):
        """updated_at обновляется при toggle."""
        original = backlog_manager.get_item("B001")
        result = backlog_manager.toggle_next_sprint("B001")

        assert result["updated_at"] != original["updated_at"]

    def test_toggle_persisted(self, populated_backlog):
        """Изменения сохраняются в файл."""
        backlog_manager.toggle_next_sprint("B002")

        # Читаем напрямую из файла
        data = json.loads(populated_backlog.read_text())
        item = next(i for i in data["items"] if i["id"] == "B002")
        assert item["next_sprint"] is True


# ============================================================================
# Тесты _load() и _save() (косвенно)
# ============================================================================

class TestLoadSave:
    """Тесты для вспомогательных функций _load() и _save()."""

    def test_load_creates_file_if_not_exists(self, temp_backlog):
        """_load() создаёт файл если не существует."""
        assert not temp_backlog.exists()

        items = backlog_manager.get_items()  # Вызывает _load()

        assert temp_backlog.exists()
        data = json.loads(temp_backlog.read_text())
        assert data == {"items": [], "next_id": 1}

    def test_load_handles_corrupted_json(self, temp_backlog):
        """_load() обрабатывает повреждённый JSON."""
        temp_backlog.write_text("{ invalid json }")

        items = backlog_manager.get_items()

        assert items == []
        # Файл должен быть пересоздан
        data = json.loads(temp_backlog.read_text())
        assert data == {"items": [], "next_id": 1}


# ============================================================================
# Тесты _format_list()
# ============================================================================

class TestFormatList:
    """Тесты для функции _format_list()."""

    def test_format_empty_list(self):
        """Форматирование пустого списка."""
        result = backlog_manager._format_list([])
        assert result == "Бэклог пуст."

    def test_format_list_with_items(self, populated_backlog):
        """Форматирование списка с записями."""
        items = backlog_manager.get_items()
        result = backlog_manager._format_list(items)

        assert "Бэклог (3):" in result
        assert "[B001]" in result
        assert "[B002]" in result
        assert "[B003]" in result
        assert "high" in result
        assert "medium" in result
        assert "low" in result
