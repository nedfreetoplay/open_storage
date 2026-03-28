"""
Асинхронные функции для расчёта хэшей файлов (SHA256/MD5).

Оптимизировано для больших файлов через чанковое чтение.
Возвращает хэши как bytes (BLOB), а не hex-строки.
"""

import hashlib
from pathlib import Path
from typing import Optional

import aiofiles
from aiofiles.threadpool.binary import AsyncBufferedReader


# Константы
SHA256_CHUNK_SIZE = 1024 * 1024  # 1 MB chunks для баланса I/O и памяти
MD5_CHUNK_SIZE = 1024 * 1024


async def calculate_sha256(file_path: Path, chunk_size: int = SHA256_CHUNK_SIZE) -> bytes:
    """
    Асинхронно вычисляет SHA256 хэш файла.
    
    Args:
        file_path: Путь к файлу
        chunk_size: Размер чанка для чтения (по умолчанию 1 MB)
    
    Returns:
        bytes: 32-байтовый SHA256 хэш (BLOB формат)
    
    Raises:
        FileNotFoundError: Если файл не существует
        IOError: Если ошибка чтения файла
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    if not file_path.is_file():
        raise IOError(f"Not a file: {file_path}")
    
    sha256_hash = hashlib.sha256()
    
    async with aiofiles.open(file_path, mode='rb') as f:
        stream: AsyncBufferedReader = f
        while True:
            chunk = await stream.read(chunk_size)
            if not chunk:
                break
            sha256_hash.update(chunk)
    
    return sha256_hash.digest()  # Возвращаем bytes, а не hex!


async def calculate_md5(file_path: Path, chunk_size: int = MD5_CHUNK_SIZE) -> bytes:
    """
    Асинхронно вычисляет MD5 хэш файла (опционально).
    
    Args:
        file_path: Путь к файлу
        chunk_size: Размер чанка для чтения
    
    Returns:
        bytes: 16-байтовый MD5 хэш (BLOB формат)
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    md5_hash = hashlib.md5()
    
    async with aiofiles.open(file_path, mode='rb') as f:
        stream: AsyncBufferedReader = f
        while True:
            chunk = await stream.read(chunk_size)
            if not chunk:
                break
            md5_hash.update(chunk)
    
    return md5_hash.digest()


async def calculate_both(file_path: Path) -> tuple[bytes, bytes]:
    """
    Вычисляет оба хэша за один проход по файлу (эффективнее для I/O).
    
    Returns:
        tuple[bytes, bytes]: (sha256_hash, md5_hash)
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    sha256_hash = hashlib.sha256()
    md5_hash = hashlib.md5()
    
    # Используем больший чанк для оптимизации
    chunk_size = max(SHA256_CHUNK_SIZE, MD5_CHUNK_SIZE)
    
    async with aiofiles.open(file_path, mode='rb') as f:
        stream: AsyncBufferedReader = f
        while True:
            chunk = await stream.read(chunk_size)
            if not chunk:
                break
            sha256_hash.update(chunk)
            md5_hash.update(chunk)
    
    return sha256_hash.digest(), md5_hash.digest()


# Утилиты для конвертации (для отображения и логов)

def sha256_to_hex(sha256_bytes: bytes) -> str:
    """Конвертирует SHA256 bytes в hex-строку для отображения."""
    return sha256_bytes.hex()


def hex_to_sha256(hex_string: str) -> bytes:
    """Конвертирует hex-строку обратно в bytes (для импорта/экспорта)."""
    return bytes.fromhex(hex_string)


def sha256_to_subdir(sha256_bytes: bytes, depth: int = 1) -> str:
    """
    Генерирует путь подкаталога для хранения файла по хэшу.
    
    Пример: sha256 = b'\\xf0\\x0a\\x1b...' → 'f0' (depth=1) или 'f0/0' (depth=2)
    
    Args:
        sha256_bytes: SHA256 хэш в bytes
        depth: Глубина вложенности (1 = 256 папок, 2 = 4096 папок)
    
    Returns:
        str: Путь подкаталога, например 'f0' или 'f0/0'
    """
    hex_hash = sha256_bytes.hex()
    
    if depth == 1:
        return hex_hash[:2]
    elif depth == 2:
        return f"{hex_hash[:2]}/{hex_hash[2:3]}"
    else:
        # Для очень больших коллекций
        parts = [hex_hash[i:i+1] for i in range(0, depth * 2, 2)]
        return '/'.join(parts)


async def verify_file_integrity(file_path: Path, expected_sha256: bytes) -> bool:
    """
    Проверяет целостность файла путём сравнения хэшей.
    
    Args:
        file_path: Путь к файлу для проверки
        expected_sha256: Ожидаемый SHA256 хэш (bytes)
    
    Returns:
        bool: True если хэши совпадают
    """
    try:
        actual_sha256 = await calculate_sha256(file_path)
        return actual_sha256 == expected_sha256
    except (FileNotFoundError, IOError):
        return False