"""
Cache storage implementations for the Audio Sample Organizer.
Handles saving and loading cache data from various storage backends.
"""

import json
import os
import pickle
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from .interfaces import ICacheStorage


class PickleStorage(ICacheStorage):
    """
    Store cache data in a pickle file.
    Fast and efficient but not human-readable.
    """
    
    def __init__(self, cache_file_path: str):
        """
        Initialize with the path to the cache file
        
        Args:
            cache_file_path: Path to the pickle file
        """
        self.cache_file = Path(cache_file_path)
        self.ensure_cache_dir()
    
    def ensure_cache_dir(self):
        """Ensure the cache directory exists"""
        cache_dir = self.cache_file.parent
        cache_dir.mkdir(parents=True, exist_ok=True)
    
    def load(self) -> Dict[str, Any]:
        """Load cache data from pickle file"""
        if not self.cache_file.exists():
            return {'metadata': {'version': 1}, 'entries': {}}
            
        try:
            with open(self.cache_file, 'rb') as f:
                data = pickle.load(f)
                
            # Validate data structure
            if not isinstance(data, dict) or 'entries' not in data:
                logging.warning(f"Invalid cache format in {self.cache_file}, starting fresh")
                return {'metadata': {'version': 1}, 'entries': {}}
                
            return data
            
        except (pickle.PickleError, EOFError, ImportError) as e:
            logging.warning(f"Error loading cache from {self.cache_file}: {e}")
            return {'metadata': {'version': 1}, 'entries': {}}
    
    def save(self, data: Dict[str, Any]) -> bool:
        """Save cache data to pickle file"""
        try:
            self.ensure_cache_dir()
            
            # Create a temporary file first
            temp_file = self.cache_file.with_suffix('.tmp')
            with open(temp_file, 'wb') as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
            
            # Replace the original file with the temporary file
            if os.name == 'nt' and self.cache_file.exists():  # Windows
                # On Windows, rename might fail if destination exists
                self.cache_file.unlink(missing_ok=True)
                
            temp_file.rename(self.cache_file)
            return True
            
        except (pickle.PickleError, OSError) as e:
            logging.error(f"Error saving cache to {self.cache_file}: {e}")
            return False
    
    def clear(self) -> bool:
        """Clear all cache data by removing the cache file"""
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
            return True
        except OSError as e:
            logging.error(f"Error clearing cache file {self.cache_file}: {e}")
            return False
    
    def get_size(self) -> int:
        """Get the current size of the cache file in bytes"""
        if not self.cache_file.exists():
            return 0
        return self.cache_file.stat().st_size


class JsonStorage(ICacheStorage):
    """
    Store cache data in a JSON file.
    Human-readable but slower and larger than pickle.
    """
    
    def __init__(self, cache_file_path: str):
        """
        Initialize with the path to the cache file
        
        Args:
            cache_file_path: Path to the JSON file
        """
        self.cache_file = Path(cache_file_path)
        self.ensure_cache_dir()
    
    def ensure_cache_dir(self):
        """Ensure the cache directory exists"""
        cache_dir = self.cache_file.parent
        cache_dir.mkdir(parents=True, exist_ok=True)
    
    def load(self) -> Dict[str, Any]:
        """Load cache data from JSON file"""
        if not self.cache_file.exists():
            return {'metadata': {'version': 1}, 'entries': {}}
            
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Validate data structure
            if not isinstance(data, dict) or 'entries' not in data:
                logging.warning(f"Invalid cache format in {self.cache_file}, starting fresh")
                return {'metadata': {'version': 1}, 'entries': {}}
                
            return data
            
        except json.JSONDecodeError as e:
            logging.warning(f"Error loading cache from {self.cache_file}: {e}")
            return {'metadata': {'version': 1}, 'entries': {}}
    
    def save(self, data: Dict[str, Any]) -> bool:
        """Save cache data to JSON file"""
        try:
            self.ensure_cache_dir()
            
            # Create a temporary file first
            temp_file = self.cache_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            # Replace the original file with the temporary file
            if os.name == 'nt' and self.cache_file.exists():  # Windows
                # On Windows, rename might fail if destination exists
                self.cache_file.unlink(missing_ok=True)
                
            temp_file.rename(self.cache_file)
            return True
            
        except (TypeError, OSError) as e:
            logging.error(f"Error saving cache to {self.cache_file}: {e}")
            return False
    
    def clear(self) -> bool:
        """Clear all cache data by removing the cache file"""
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
            return True
        except OSError as e:
            logging.error(f"Error clearing cache file {self.cache_file}: {e}")
            return False
    
    def get_size(self) -> int:
        """Get the current size of the cache file in bytes"""
        if not self.cache_file.exists():
            return 0
        return self.cache_file.stat().st_size


def create_storage(cache_file: str) -> ICacheStorage:
    """
    Factory function to create the appropriate storage backend
    based on the file extension
    
    Args:
        cache_file: Path to the cache file
    
    Returns:
        An instance of ICacheStorage
    """
    path = Path(cache_file)
    if path.suffix.lower() == '.json':
        return JsonStorage(cache_file)
    else:
        return PickleStorage(cache_file)