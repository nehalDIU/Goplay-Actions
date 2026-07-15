import hashlib
import os
from typing import Optional
from app.logger import logger

def calculate_sha256(content: str) -> str:
    """
    Computes the SHA256 hash of a string.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def get_last_hash(hash_file_path: str) -> Optional[str]:
    """
    Reads the last recorded hash from the file. Returns None if file does not exist.
    """
    if os.path.exists(hash_file_path):
        try:
            with open(hash_file_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            logger.warning(f"Could not read last hash file: {e}")
    return None

def save_last_hash(hash_file_path: str, new_hash: str) -> None:
    """
    Writes the new hash to the file. Creates parent directories if needed.
    """
    try:
        # Create directory if it doesn't exist
        directory = os.path.dirname(os.path.abspath(hash_file_path))
        if directory:
            os.makedirs(directory, exist_ok=True)
            
        with open(hash_file_path, "w", encoding="utf-8") as f:
            f.write(new_hash)
            
        logger.info(f"Saved new hash: [info]{new_hash[:8]}...[/info]")
    except Exception as e:
        logger.error(f"Failed to write hash to {hash_file_path}: {e}")
