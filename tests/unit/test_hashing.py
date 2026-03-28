"""Тесты для модуля хэширования."""

import hashlib
from pathlib import Path
import pytest
from src.core.hashing import (
    calculate_sha256,
    calculate_md5,
    calculate_both,
    sha256_to_hex,
    hex_to_sha256,
    sha256_to_subdir,
    verify_file_integrity,
)


@pytest.fixture
def test_file(tmp_path: Path) -> Path:
    """Создаёт тестовый файл с известным содержимым."""
    file_path = tmp_path / "test_file.bin"
    file_path.write_bytes(b"Hello, Open Storage!")
    return file_path


@pytest.fixture
def large_test_file(tmp_path: Path) -> Path:
    """Создаёт большой тестовый файл (10 MB)."""
    file_path = tmp_path / "large_file.bin"
    # Записываем 10 MB данных
    chunk = b"X" * (1024 * 1024)
    with open(file_path, 'wb') as f:
        for _ in range(10):
            f.write(chunk)
    return file_path


@pytest.mark.asyncio
async def test_calculate_sha256(test_file: Path):
    """Проверка расчёта SHA256."""
    sha256_bytes = await calculate_sha256(test_file)
    
    # Проверяем тип и размер
    assert isinstance(sha256_bytes, bytes)
    assert len(sha256_bytes) == 32
    
    # Проверяем корректность через hashlib
    expected = hashlib.sha256(b"Hello, Open Storage!").digest()
    assert sha256_bytes == expected


@pytest.mark.asyncio
async def test_calculate_md5(test_file: Path):
    """Проверка расчёта MD5."""
    md5_bytes = await calculate_md5(test_file)
    
    assert isinstance(md5_bytes, bytes)
    assert len(md5_bytes) == 16
    
    expected = hashlib.md5(b"Hello, Open Storage!").digest()
    assert md5_bytes == expected


@pytest.mark.asyncio
async def test_calculate_both(test_file: Path):
    """Проверка одновременного расчёта обоих хэшей."""
    sha256_bytes, md5_bytes = await calculate_both(test_file)
    
    assert len(sha256_bytes) == 32
    assert len(md5_bytes) == 16
    
    # Сверяем с отдельными вызовами
    sha256_single = await calculate_sha256(test_file)
    md5_single = await calculate_md5(test_file)
    
    assert sha256_bytes == sha256_single
    assert md5_bytes == md5_single


@pytest.mark.asyncio
async def test_large_file(large_test_file: Path):
    """Проверка работы с большими файлами (чанковое чтение)."""
    sha256_bytes = await calculate_sha256(large_test_file)
    assert len(sha256_bytes) == 32


@pytest.mark.asyncio
async def test_file_not_found():
    """Проверка обработки несуществующего файла."""
    with pytest.raises(FileNotFoundError):
        await calculate_sha256(Path("/nonexistent/file.bin"))


def test_sha256_to_hex():
    """Проверка конвертации bytes → hex."""
    test_bytes = b'\x00\x01\x02\x03' + b'\x00' * 28
    hex_str = sha256_to_hex(test_bytes)
    assert len(hex_str) == 64
    assert hex_str.startswith("00010203")


def test_hex_to_sha256():
    """Проверка конвертации hex → bytes."""
    hex_str = "00010203" + "00" * 28
    result_bytes = hex_to_sha256(hex_str)
    assert len(result_bytes) == 32
    assert result_bytes[0:4] == b'\x00\x01\x02\x03'


def test_hex_roundtrip():
    """Проверка круговой конвертации."""
    original = b'\xab\xcd\xef' + b'\x00' * 29
    hex_str = sha256_to_hex(original)
    restored = hex_to_sha256(hex_str)
    assert original == restored


def test_sha256_to_subdir():
    """Проверка генерации подкаталогов."""
    test_hash = bytes.fromhex("f00a1b2c3d4e5f6789abcdef0123456789abcdef0123456789abcdef01234567")
    
    assert sha256_to_subdir(test_hash, depth=1) == "f0"
    assert sha256_to_subdir(test_hash, depth=2) == "f0/0"


@pytest.mark.asyncio
async def test_verify_integrity(test_file: Path):
    """Проверка верификации файла."""
    expected = await calculate_sha256(test_file)
    assert await verify_file_integrity(test_file, expected) is True
    
    # Неправильный хэш
    wrong_hash = b'\x00' * 32
    assert await verify_file_integrity(test_file, wrong_hash) is False