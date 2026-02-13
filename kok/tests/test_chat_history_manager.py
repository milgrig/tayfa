"""Тесты для chat_history_manager.py."""

import json
import sys
from pathlib import Path

import pytest

# Добавляем путь к модулю
sys.path.insert(0, str(Path(__file__).parent.parent.parent / ".tayfa" / "common"))

from chat_history_manager import (
    set_tayfa_dir,
    get_tayfa_dir,
    save_message,
    get_history,
    clear_history,
    get_last_messages,
    search_history,
    _generate_message_id,
    _load_history,
    _save_history,
    MAX_HISTORY_SIZE,
)


@pytest.fixture
def chat_tayfa_dir(tmp_path: Path) -> Path:
    """Создаёт временную директорию .tayfa для тестов chat_history."""
    tayfa_dir = tmp_path / ".tayfa"
    tayfa_dir.mkdir()

    # Создаём папку агента
    agent_dir = tayfa_dir / "test_agent"
    agent_dir.mkdir()

    # Устанавливаем путь
    set_tayfa_dir(tayfa_dir)

    yield tayfa_dir

    # Cleanup
    set_tayfa_dir(None)


@pytest.fixture
def agent_with_history(chat_tayfa_dir: Path) -> str:
    """Создаёт агента с предзаполненной историей."""
    agent_name = "test_agent"

    # Создаём историю с 5 сообщениями
    messages = []
    for i in range(1, 6):
        messages.append({
            "id": f"msg_{i:03d}",
            "timestamp": f"2026-02-13T10:{i:02d}:00",
            "direction": "to_agent",
            "prompt": f"Вопрос {i}",
            "result": f"Ответ {i}",
            "runtime": "claude",
            "success": True,
        })

    history_file = chat_tayfa_dir / agent_name / "chat_history.json"
    history_file.write_text(json.dumps(messages, ensure_ascii=False, indent=2))

    return agent_name


class TestSetTayfaDir:
    """Тесты для set_tayfa_dir и get_tayfa_dir."""

    def test_set_and_get_tayfa_dir(self, tmp_path: Path):
        """Устанавливает и получает путь к .tayfa."""
        test_path = tmp_path / ".tayfa"
        test_path.mkdir()

        set_tayfa_dir(test_path)
        assert get_tayfa_dir() == test_path

        # Cleanup
        set_tayfa_dir(None)

    def test_set_tayfa_dir_none(self):
        """Устанавливает None."""
        set_tayfa_dir(None)
        assert get_tayfa_dir() is None


class TestSaveMessage:
    """Тесты для save_message."""

    def test_save_first_message_creates_file(self, chat_tayfa_dir: Path):
        """Сохранение первого сообщения создаёт файл."""
        agent_name = "new_agent"
        agent_dir = chat_tayfa_dir / agent_name
        agent_dir.mkdir()

        msg = save_message(
            agent_name=agent_name,
            prompt="Привет",
            result="Привет! Чем могу помочь?",
        )

        assert msg is not None
        assert msg["id"] == "msg_001"
        assert msg["prompt"] == "Привет"
        assert msg["result"] == "Привет! Чем могу помочь?"

        # Проверяем что файл создан
        history_file = chat_tayfa_dir / agent_name / "chat_history.json"
        assert history_file.exists()

    def test_save_message_appends_to_history(self, agent_with_history: str, chat_tayfa_dir: Path):
        """Добавление к существующей истории."""
        msg = save_message(
            agent_name=agent_with_history,
            prompt="Новый вопрос",
            result="Новый ответ",
        )

        assert msg is not None
        assert msg["id"] == "msg_006"  # После 5 существующих

        # Проверяем общее количество
        history = get_history(agent_with_history)
        assert history["total"] == 6

    def test_save_message_autogenerate_id_and_timestamp(self, chat_tayfa_dir: Path):
        """Автогенерация ID и timestamp."""
        agent_name = "test_agent"

        msg = save_message(
            agent_name=agent_name,
            prompt="Тест",
            result="Ответ",
        )

        assert msg is not None
        assert msg["id"].startswith("msg_")
        assert "timestamp" in msg
        assert "T" in msg["timestamp"]  # ISO формат

    def test_save_message_with_all_fields(self, chat_tayfa_dir: Path):
        """Сохранение всех полей (cost_usd, duration_sec, task_id)."""
        agent_name = "test_agent"

        msg = save_message(
            agent_name=agent_name,
            prompt="Выполни задачу",
            result="Готово",
            runtime="claude",
            cost_usd=0.05,
            duration_sec=12.567,
            task_id="T001",
            success=True,
            extra={"model": "opus"},
        )

        assert msg is not None
        assert msg["cost_usd"] == 0.05
        assert msg["duration_sec"] == 12.57  # Округлено до 2 знаков
        assert msg["task_id"] == "T001"
        assert msg["success"] is True
        assert msg["model"] == "opus"

    def test_save_message_without_tayfa_dir(self):
        """Возвращает None если tayfa_dir не установлен."""
        set_tayfa_dir(None)

        msg = save_message(
            agent_name="any_agent",
            prompt="Test",
            result="Test",
        )

        assert msg is None

    def test_save_message_fifo_limit(self, chat_tayfa_dir: Path):
        """FIFO: оставляет только MAX_HISTORY_SIZE сообщений."""
        agent_name = "test_agent"

        # Создаём историю с MAX_HISTORY_SIZE сообщений
        messages = []
        for i in range(1, MAX_HISTORY_SIZE + 1):
            messages.append({
                "id": f"msg_{i:03d}",
                "timestamp": f"2026-02-13T10:00:{i % 60:02d}",
                "direction": "to_agent",
                "prompt": f"Вопрос {i}",
                "result": f"Ответ {i}",
                "runtime": "claude",
                "success": True,
            })

        history_file = chat_tayfa_dir / agent_name / "chat_history.json"
        history_file.write_text(json.dumps(messages, ensure_ascii=False))

        # Добавляем ещё одно сообщение
        save_message(agent_name=agent_name, prompt="Новое", result="Новый ответ")

        # Проверяем что всего MAX_HISTORY_SIZE сообщений
        history = get_history(agent_name, limit=MAX_HISTORY_SIZE)
        assert history["total"] == MAX_HISTORY_SIZE

        # Первое сообщение удалено (FIFO), второе стало первым
        assert history["messages"][0]["prompt"] == "Вопрос 2"
        # Последнее — новое сообщение
        assert history["messages"][-1]["prompt"] == "Новое"


class TestGetHistory:
    """Тесты для get_history."""

    def test_get_all_history(self, agent_with_history: str):
        """Получение всей истории."""
        history = get_history(agent_with_history)

        assert history["total"] == 5
        assert len(history["messages"]) == 5
        assert history["limit"] == 50
        assert history["offset"] == 0

    def test_get_history_with_pagination(self, agent_with_history: str):
        """Пагинация (limit и offset)."""
        # Получаем 2 сообщения, пропуская 1 с конца
        history = get_history(agent_with_history, limit=2, offset=1)

        assert len(history["messages"]) == 2
        assert history["total"] == 5
        assert history["limit"] == 2
        assert history["offset"] == 1

    def test_get_history_empty(self, chat_tayfa_dir: Path):
        """Пустая история."""
        agent_name = "empty_agent"
        agent_dir = chat_tayfa_dir / agent_name
        agent_dir.mkdir()

        history = get_history(agent_name)

        assert history["total"] == 0
        assert history["messages"] == []

    def test_get_history_nonexistent_agent(self, chat_tayfa_dir: Path):
        """История несуществующего агента — пустой результат."""
        history = get_history("nonexistent_agent")

        assert history["total"] == 0
        assert history["messages"] == []

    def test_get_history_limit_500(self, chat_tayfa_dir: Path):
        """Лимит 500 сообщений."""
        agent_name = "test_agent"

        # Создаём 600 сообщений
        messages = []
        for i in range(1, 601):
            messages.append({
                "id": f"msg_{i:03d}",
                "timestamp": f"2026-02-13T10:00:00",
                "direction": "to_agent",
                "prompt": f"Q{i}",
                "result": f"A{i}",
                "runtime": "claude",
                "success": True,
            })

        history_file = chat_tayfa_dir / agent_name / "chat_history.json"
        history_file.write_text(json.dumps(messages, ensure_ascii=False))

        # Запрашиваем с большим лимитом
        history = get_history(agent_name, limit=1000)

        # Возвращает все 600 (лимит на файле, не на чтении)
        assert history["total"] == 600


class TestClearHistory:
    """Тесты для clear_history."""

    def test_clear_existing_history(self, agent_with_history: str, chat_tayfa_dir: Path):
        """Очистка существующей истории."""
        result = clear_history(agent_with_history)

        assert result["status"] == "cleared"
        assert result["deleted_count"] == 5

        # Проверяем что история пуста
        history = get_history(agent_with_history)
        assert history["total"] == 0

    def test_clear_empty_history(self, chat_tayfa_dir: Path):
        """Очистка пустой истории — без ошибки."""
        agent_name = "empty_agent"
        agent_dir = chat_tayfa_dir / agent_name
        agent_dir.mkdir()

        result = clear_history(agent_name)

        assert result["status"] == "cleared"
        assert result["deleted_count"] == 0

    def test_clear_returns_deleted_count(self, agent_with_history: str):
        """Возврат deleted_count."""
        result = clear_history(agent_with_history)

        assert "deleted_count" in result
        assert result["deleted_count"] == 5


class TestSearchHistory:
    """Тесты для search_history."""

    def test_search_in_prompt(self, agent_with_history: str):
        """Поиск по prompt."""
        results = search_history(agent_with_history, "Вопрос 3")

        assert len(results) == 1
        assert results[0]["prompt"] == "Вопрос 3"

    def test_search_in_result(self, agent_with_history: str):
        """Поиск по result."""
        results = search_history(agent_with_history, "Ответ 2")

        assert len(results) == 1
        assert results[0]["result"] == "Ответ 2"

    def test_search_empty_result(self, agent_with_history: str):
        """Пустой результат поиска."""
        results = search_history(agent_with_history, "несуществующий текст")

        assert len(results) == 0

    def test_search_case_insensitive(self, chat_tayfa_dir: Path):
        """Case-insensitive поиск."""
        agent_name = "test_agent"

        save_message(agent_name=agent_name, prompt="ПРИВЕТ", result="привет")
        save_message(agent_name=agent_name, prompt="Привет", result="ОТВЕТ")

        results = search_history(agent_name, "привет")

        assert len(results) == 2

    def test_search_with_limit(self, chat_tayfa_dir: Path):
        """Поиск с лимитом результатов."""
        agent_name = "test_agent"

        # Создаём 10 сообщений с одинаковым текстом
        for i in range(10):
            save_message(agent_name=agent_name, prompt=f"тест {i}", result="ответ")

        results = search_history(agent_name, "тест", limit=3)

        assert len(results) == 3

    def test_search_returns_newest_first(self, agent_with_history: str):
        """Поиск возвращает от новых к старым."""
        # Все сообщения содержат "Вопрос"
        results = search_history(agent_with_history, "Вопрос", limit=3)

        assert len(results) == 3
        # Первый результат — самый новый
        assert results[0]["prompt"] == "Вопрос 5"


class TestGetLastMessages:
    """Тесты для get_last_messages."""

    def test_get_last_5_messages(self, agent_with_history: str):
        """Получение последних 5 сообщений."""
        messages = get_last_messages(agent_with_history, count=5)

        assert len(messages) == 5
        assert messages[-1]["prompt"] == "Вопрос 5"  # Последний

    def test_get_last_messages_less_than_requested(self, agent_with_history: str):
        """Меньше сообщений чем запрошено."""
        messages = get_last_messages(agent_with_history, count=10)

        # Есть только 5 сообщений
        assert len(messages) == 5

    def test_get_last_messages_empty_history(self, chat_tayfa_dir: Path):
        """Пустая история."""
        agent_name = "empty_agent"
        agent_dir = chat_tayfa_dir / agent_name
        agent_dir.mkdir()

        messages = get_last_messages(agent_name, count=5)

        assert messages == []


class TestGenerateMessageId:
    """Тесты для _generate_message_id."""

    def test_first_message_id(self):
        """Первое сообщение получает ID msg_001."""
        msg_id = _generate_message_id([])
        assert msg_id == "msg_001"

    def test_increment_message_id(self):
        """Инкремент ID."""
        messages = [
            {"id": "msg_001"},
            {"id": "msg_002"},
            {"id": "msg_003"},
        ]

        msg_id = _generate_message_id(messages)
        assert msg_id == "msg_004"

    def test_handle_gaps_in_ids(self):
        """Обработка пропусков в ID."""
        messages = [
            {"id": "msg_001"},
            {"id": "msg_005"},  # Пропуск
            {"id": "msg_003"},
        ]

        msg_id = _generate_message_id(messages)
        assert msg_id == "msg_006"  # Берёт max + 1


class TestLoadAndSaveHistory:
    """Тесты для _load_history и _save_history."""

    def test_load_history_creates_empty_for_nonexistent(self, chat_tayfa_dir: Path):
        """Загрузка несуществующей истории возвращает пустой список."""
        messages = _load_history("nonexistent_agent")
        assert messages == []

    def test_load_history_handles_dict_format(self, chat_tayfa_dir: Path):
        """Обработка формата {"messages": [...]}."""
        agent_name = "test_agent"
        history_file = chat_tayfa_dir / agent_name / "chat_history.json"

        # Записываем в формате dict
        data = {"messages": [{"id": "msg_001", "prompt": "test"}]}
        history_file.write_text(json.dumps(data))

        messages = _load_history(agent_name)

        assert len(messages) == 1
        assert messages[0]["id"] == "msg_001"

    def test_save_history_atomic(self, chat_tayfa_dir: Path):
        """Атомарная запись (temp + rename)."""
        agent_name = "test_agent"

        messages = [{"id": "msg_001", "prompt": "test"}]
        result = _save_history(agent_name, messages)

        assert result is True

        # Проверяем что временных файлов не осталось
        temp_files = list((chat_tayfa_dir / agent_name).glob("chat_history_*.json"))
        assert len(temp_files) == 0
