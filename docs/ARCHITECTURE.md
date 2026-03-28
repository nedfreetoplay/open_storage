# 🗂️ План программы для хранения неизменяемых файлов (Hydrus-подобная архитектура)

> **Цель**: Система хранения файлов с идентификацией по хэшу (SHA256/MD5), системой тегов и клиент-серверной архитектурой на Python 3.14 + SQLite, с возможностью миграции на Rust.

---

## 🔧 Архитектурная схема

```
┌─────────────────┐     ┌─────────────────────┐     ┌─────────────────┐
│   GUI Client    │────▶│   Server Core       │────▶│   SQLite DB     │
│   (PyQt/PySide) │ IPC │   (FastAPI/Custom)  │     │   + File Store  │
└─────────────────┘     └─────────────────────┘     └─────────────────┘
         │                       │
         │    ┌──────────────────┘
         ▼    ▼
┌─────────────────┐
│ Remote Client   │
│ (HTTP API)      │
└─────────────────┘
```

### Режимы работы

| Режим | Описание | Транспорт |
|-------|----------|-----------|
| **Local** | Клиент запускает сервер как subprocess, общение через Unix socket / named pipe | IPC (ZeroMQ/asyncio streams) |
| **Remote** | Сервер запущен отдельно, клиенты подключаются по сети | HTTP/REST + WebSocket |

---

## 🗄️ Схема базы данных (SQLite)

### Основные таблицы

```sql
-- 1. Файлы: хранение хэшей и метаданных
CREATE TABLE files (
    hash_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256 BLOB NOT NULL UNIQUE,        -- 32 байта, плотное хранение
    md5 BLOB,                           -- опционально, 16 байт
    file_size INTEGER NOT NULL,
    mime_type TEXT,
    width INTEGER, height INTEGER,      -- для изображений/видео
    duration_ms INTEGER,                -- для медиа
    import_timestamp REAL NOT NULL,     -- UNIX timestamp
    file_path TEXT,                     -- относительный путь в хранилище
    status TEXT CHECK(status IN ('active', 'deleted', 'quarantined')) DEFAULT 'active'
);

-- 2. Теги: иерархическая система с неймспейсами (как в Hydrus)
CREATE TABLE namespaces (
    namespace_id INTEGER PRIMARY KEY AUTOINCREMENT,
    namespace TEXT UNIQUE NOT NULL      -- 'person', 'artist', 'copyright', ''
);

CREATE TABLE subtags (
    subtag_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subtag TEXT NOT NULL                -- 'andreas', 'pixiv', 'original'
);

CREATE TABLE tags (
    tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
    namespace_id INTEGER NOT NULL REFERENCES namespaces(namespace_id),
    subtag_id INTEGER NOT NULL REFERENCES subtags(subtag_id),
    UNIQUE(namespace_id, subtag_id)     -- один тег = одна пара
);

-- 3. Связь файлов и тегов (junction table)
CREATE TABLE file_tag_mappings (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash_id INTEGER NOT NULL REFERENCES files(hash_id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(tag_id) ON DELETE CASCADE,
    confidence REAL DEFAULT 1.0,        -- 0.0-1.0 для авто-тегов
    source TEXT,                        -- 'manual', 'downloader', 'ai'
    added_timestamp REAL NOT NULL,
    UNIQUE(hash_id, tag_id)             -- один тег на файл один раз
);

-- 4. Индексы для производительности поиска
CREATE INDEX idx_files_sha256 ON files(sha256);
CREATE INDEX idx_files_status ON files(status);
CREATE INDEX idx_mappings_hash ON file_tag_mappings(hash_id);
CREATE INDEX idx_mappings_tag ON file_tag_mappings(tag_id);
CREATE INDEX idx_tags_namespace ON tags(namespace_id);
CREATE INDEX idx_subtags_text ON subtags(subtag);
```

### Дополнительные таблицы (опционально, по мере развития)

```sql
-- Алиасы и синонимы тегов (для поиска)
CREATE TABLE tag_siblings (
    sibling_id INTEGER PRIMARY KEY,
    tag_id INTEGER NOT NULL REFERENCES tags(tag_id),
    master_tag_id INTEGER NOT NULL REFERENCES tags(tag_id),
    UNIQUE(tag_id)
);

-- Иерархия тегов (родитель-потомок)
CREATE TABLE tag_parents (
    parent_id INTEGER PRIMARY KEY,
    tag_id INTEGER NOT NULL REFERENCES tags(tag_id),
    parent_tag_id INTEGER NOT NULL REFERENCES tags(tag_id),
    UNIQUE(tag_id, parent_tag_id)
);

-- Кэш поисковых запросов
CREATE TABLE search_cache (
    cache_id INTEGER PRIMARY KEY,
    query_hash BLOB NOT NULL UNIQUE,    -- хэш параметров поиска
    result_hash_ids BLOB,               -- сжатый список hash_id
    created_at REAL NOT NULL,
    expires_at REAL
);
```

> 💡 **Важно**: Хэши хранятся как `BLOB` (32 байта для SHA256), а не как HEX-строки — это экономит 50% места и ускоряет сравнения [[11]].

---

## 📁 Структура проекта

```
hydrus_clone/
├── pyproject.toml              # Poetry/uv зависимости
├── src/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── hashing.py          # SHA256/MD5 calculators, async-friendly
│   │   ├── storage.py          # File I/O, hash-based subdirs (f00/fff)
│   │   └── config.py           # Settings management
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── schema.py           # DDL миграции, versioning
│   │   ├── models.py           # SQLAlchemy 2.0 models (для типизации)
│   │   ├── queries.py          # Prepared queries, search logic
│   │   └── connection.py       # Connection pool, WAL mode setup
│   │
│   ├── server/
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI app or custom async server
│   │   ├── ipc_handler.py      # Local IPC (Unix socket/pipe)
│   │   ├── http_api.py         # REST endpoints (/files, /tags, /search)
│   │   └── background.py       # Tasks: thumbnail gen, hash verification
│   │
│   ├── client/
│   │   ├── __init__.py
│   │   ├── main_window.py      # PyQt6/PySide6 GUI
│   │   ├── api_client.py       # Unified client: IPC or HTTP
│   │   ├── widgets/            # Tag editor, file grid, search bar
│   │   └── utils.py            # File dialogs, drag-drop handlers
│   │
│   └── shared/
│       ├── __init__.py
│       ├── schemas.py          # Pydantic models для API (вход/выход)
│       ├── protocols.py        # Abstract interfaces для будущей миграции на Rust
│       └── types.py            # Type aliases: HashID, TagID, FilePath
│
├── tests/
│   ├── unit/                   # Тесты функций
│   ├── integration/            # Тесты API + DB
│   └── conftest.py             # Fixtures: temp DB, test files
│
├── migrations/                 # Alembic или кастомные скрипты
│   └── versions/
│
└── docs/
    ├── ARCHITECTURE.md         # Этот план + детали
    └── RUST_MIGRATION.md       # План переноса модулей
```

---

## 🔌 Интерфейсы и протоколы

### 1. Unified API Client (абстракция транспорта)

```python
# shared/protocols.py
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional
from .types import HashID, TagID, FileMetadata, TagMapping

class StorageBackend(ABC):
    @abstractmethod
    async def add_file(self, file_path: Path, tags: list[str]) -> HashID: ...
    @abstractmethod
    async def get_file(self, hash_id: HashID) -> Optional[FileMetadata]: ...
    @abstractmethod
    async def search(self, tags: list[str], exclude: list[str] = None) -> list[HashID]: ...
    @abstractmethod
    async def add_tag(self, hash_id: HashID, tag: str) -> bool: ...
    @abstractmethod
    async def remove_tag(self, hash_id: HashID, tag: str) -> bool: ...
```

### 2. Реализации

| Транспорт | Класс | Особенности |
|-----------|-------|-------------|
| **Local IPC** | `IPCClient` | AsyncIO Unix socket / Windows named pipe, zero-copy для больших файлов |
| **HTTP** | `HTTPClient` | FastAPI + httpx, streaming для загрузки/скачивания, JWT auth |

### 3. Пример REST API (сервер)

```http
POST /api/v1/files          # Загрузка файла → {hash_id, sha256}
GET  /api/v1/files/{hash_id} # Метаданные файла
POST /api/v1/files/{hash_id}/tags  # Добавить теги: {"tags": ["person=anna", "art"]}
GET  /api/v1/search?tag=person:anna&tag=art  # Поиск по тегам
WS   /api/v1/events          # WebSocket: уведомления о новых файлах/тегах
```

> ✅ Все эндпоинты возвращают `application/json` с валидацией через Pydantic [[14]].

---

## 🗂️ Хранение файлов на диске

```
db/
├── client.master.db        # Основная метадата (таблицы выше)
├── client.mappings.db      # Опционально: выделенная БД для file_tag_mappings (масштабируемость)
└── client_files/           # Физические файлы
    ├── f00/                # Подкаталоги по первым 2 символам хэша
    │   ├── f00a1b2c3...    # Файл без расширения, имя = полный hex-хэш
    │   └── ...
    ├── f01/
    └── ...
    └── fff/
```

- Файлы переименовываются в `sha256_hex` при импорте (как в Hydrus) [[12]]
- Расширение не хранится в имени — определяется по `mime_type` в БД
- Поддерживается гранулярность: `f00/0/`, `f00/1/`, ... `f00/f/` для >100k файлов [[9]]

---

## 🔄 План миграции на Rust (постепенный)

### Этап 1: Абстракция границ (сейчас)

- Все бизнес-логика в `shared/` с чёткими интерфейсами
- Минимальное использование специфичных для Python фич в публичных API
- PyO3-ready структуры: `#[repr(C)]`, простые типы

### Этап 2: Выделение "горячих" модулей

```rust
// Пример: hashing.rs (Rust)
use sha2::{Sha256, Digest};
use std::path::Path;

pub fn calculate_sha256(path: &Path) -> Result<[u8; 32], IoError> {
    // ... оптимизированная реализация
}
```

```python
# Python wrapper через PyO3
from .rust_ext import calculate_sha256 as _rust_sha256
def calculate_sha256(path: Path) -> bytes:
    return _rust_sha256(str(path))
```

### Этап 3: Замена сервера

- Переписать `server/` на Rust + Actix-web/Axum
- Оставить Python-клиент, общающийся по тем же IPC/HTTP протоколам
- Постепенно переписать GUI на Tauri (Rust + WebView) или оставить PyQt

---

## 🚀 Roadmap разработки (поэтапно)

### Фаза 0: Подготовка (1-2 недели)

- [x] Настроить `pyproject.toml` с зависимостями: `aiofiles`, `aiosqlite`, `pydantic`, `fastapi`, `pyqt6`
- [x] Создать базовую структуру проекта
- [ ] Реализовать `hashing.py` с async-поддержкой

### Фаза 1: Ядро (2-3 недели)

- [ ] Реализовать `database/schema.py` и миграции
- [ ] Написать `storage.py`: импорт файла → хэш → сохранение в `client_files/`
- [ ] Протестировать: добавить файл → получить `hash_id` → проверить БД

### Фаза 2: Сервер (2 недели)

- [ ] Реализовать `server/main.py` с базовыми эндпоинтами
- [ ] Добавить IPC-транспорт (Unix socket)
- [ ] Протестировать: клиент → сервер → БД → ответ

### Фаза 3: Клиент (3-4 недели)

- [ ] Создать минимальный GUI: drag-drop, список файлов, добавление тегов
- [ ] Реализовать поиск по тегам с автодополнением
- [ ] Добавить отображение превью (генерация миниатюр на сервере)

### Фаза 4: Продвинутые функции (постоянно)

- [ ] Синонимы и иерархия тегов
- [ ] Пакетный импорт, дедупликация
- [ ] Экспорт/импорт тегов (Hydrus Tag Archive)
- [ ] Поддержка плагинов для парсинга метаданных

---

## ⚠️ Критические замечания и рекомендации

1. **SQLite WAL-режим обязателен** для конкурентного доступа:

   ```python
   # database/connection.py
   conn.execute("PRAGMA journal_mode=WAL")
   conn.execute("PRAGMA synchronous=NORMAL")  # баланс скорость/безопасность
   conn.execute("PRAGMA cache_size=-64000")   # 64MB кэш
   ```

2. **Транзакции для пакетных операций**: Добавление 100 тегов к файлу — одна транзакция, не 100.

3. **Асинхронность везде**: `aiosqlite`, `aiofiles`, `async def` в сервере — чтобы не блокировать при I/O.

4. **Валидация на границах**: Pydantic модели для всех входных/выходных данных — защита от некорректных запросов.

5. **Логирование и мониторинг**: `structlog` + метрики (количество файлов, время поиска) — для отладки и оптимизации.

6. **Тестирование**:
   - Юнит-тесты на хэширование и валидацию
   - Интеграционные: клиент → сервер → БД → проверка результата
   - Нагрузочные: 10k файлов, поиск по 5 тегам

---

## 📦 Зависимости (pyproject.toml фрагмент)

```toml
[project]
name = "hydrus-clone"
version = "0.1.0"
requires-python = ">=3.14"

dependencies = [
    "aiosqlite>=0.20.0",      # async SQLite
    "aiofiles>=23.0",         # async file I/O
    "pydantic>=2.0",          # data validation
    "fastapi>=0.110.0",       # HTTP API (опционально, можно кастомный сервер)
    "pyqt6>=6.6.0",           # GUI
    "pillow>=10.0.0",         # генерация превью
    "python-multipart",       # загрузка файлов в FastAPI
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio",
    "ruff",                   # линтер
    "mypy",                   # типизация
]
```

---

## 🎯 Следующие шаги для вас

1. **Создайте репозиторий** с указанной структурой
2. **Начните с `core/hashing.py`** — прототип асинхронного расчёта SHA256
3. **Реализуйте схему БД** в `database/schema.py` и протестируйте на временной БД
4. **Напишите простой CLI-клиент** для импорта файла → получения `hash_id`

> 💡 **Совет**: Не пытайтесь сделать всё сразу. Сначала рабочий прототип: «добавил файл → получил hash_id → нашёл по тегу». Затем постепенно добавляйте слои.

Если нужно — могу помочь с кодом для любого из модулей (хэширование, схема БД, IPC-транспорт). Укажите, с чего начнём? 🛠️
