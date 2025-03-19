"""
Interface definitions for the Audio Sample Organizer's cache system.
Defines the contracts for cache management components.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple


class ICacheKey(ABC):
    """Interface for cache key generation and validation"""
    
    @abstractmethod
    def generate(self, file_path: str) -> str:
        """Generate a cache key for a file path"""
        pass
    
    @abstractmethod
    def is_valid(self, key: str, file_path: str) -> bool:
        """Check if a cache key is still valid for a file path"""
        pass


class ICacheStorage(ABC):
    """Interface for cache storage backends"""
    
    @abstractmethod
    def load(self) -> Dict[str, Any]:
        """Load cache data from storage"""
        pass
    
    @abstractmethod
    def save(self, data: Dict[str, Any]) -> bool:
        """Save cache data to storage"""
        pass
    
    @abstractmethod
    def clear(self) -> bool:
        """Clear all cache data from storage"""
        pass
    
    @abstractmethod
    def get_size(self) -> int:
        """Get the current size of the cache in bytes"""
        pass


class ICacheManager(ABC):
    """Interface for cache management operations"""
    
    @abstractmethod
    def get(self, file_path: str) -> Optional[Any]:
        """Get a cached value for a file path"""
        pass
    
    @abstractmethod
    def put(self, file_path: str, value: Any) -> None:
        """Store a value in the cache for a file path"""
        pass
    
    @abstractmethod
    def invalidate(self, file_path: str) -> None:
        """Invalidate a cache entry for a file path"""
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """Clear the entire cache"""
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        pass
    
    @abstractmethod
    def shutdown(self) -> None:
        """Perform cleanup and ensure cache is saved"""
        pass