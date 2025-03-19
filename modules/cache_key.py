"""
Cache key generation for the Audio Sample Organizer.
Handles creating unique and reliable cache keys for audio files.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any

from .interfaces import ICacheKey


class FileMetadataKey(ICacheKey):
    """
    Cache key generator that uses file metadata (path, size, mtime).
    Fast and reliable for most use cases where file content hasn't changed.
    """
    
    def generate(self, file_path: str) -> str:
        """Generate a cache key based on file path, size and modification time"""
        # Normalize path to handle different separators and potential encoding issues
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
            
        # Get file stats
        stats = path.stat()
        
        # Create a metadata dictionary
        metadata = {
            'path': str(path.name),  # Just the filename, not the full path
            'size': stats.st_size,
            'mtime': stats.st_mtime,
            # Add normalized path hash for additional uniqueness
            'path_hash': hash(str(path))
        }
    
        # Convert to a string key
        key = json.dumps(metadata, sort_keys=True)
        return key
    
    def is_valid(self, key: str, file_path: str) -> bool:
        """
        Check if a cache key is still valid for a file path
        by comparing current metadata with the cached metadata
        """
        try:
            # Parse the key back to a metadata dict
            cached_metadata = json.loads(key)
            
            # Generate new metadata
            path = Path(file_path)
            if not path.exists():
                return False
                
            stats = path.stat()
            
            # Compare size and modification time
            return (cached_metadata['size'] == stats.st_size and
                    cached_metadata['mtime'] == stats.st_mtime)
        except (json.JSONDecodeError, KeyError, FileNotFoundError):
            return False


class ContentHashKey(ICacheKey):
    """
    Cache key generator that computes a partial hash of the file content.
    More accurate but slower than metadata-based keys.
    """
    
    def __init__(self, sample_size: int = 8192):
        """
        Initialize with the sample size to read from files
        
        Args:
            sample_size: Number of bytes to read from beginning of file
        """
        self.sample_size = sample_size
    
    def generate(self, file_path: str) -> str:
        """Generate a cache key based on a partial hash of file content"""
        import hashlib
        
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
            
        # Get file stats for additional security
        stats = path.stat()
        
        # Read first N bytes of the file
        with open(file_path, 'rb') as f:
            content_sample = f.read(self.sample_size)
        
        # Create a hash of the content sample
        content_hash = hashlib.md5(content_sample).hexdigest()
        
        # Create a metadata dictionary
        metadata = {
            'path': str(path.name),
            'size': stats.st_size,
            'hash': content_hash
        }
        
        # Convert to a string key
        key = json.dumps(metadata, sort_keys=True)
        return key
    
    def is_valid(self, key: str, file_path: str) -> bool:
        """
        Check if a cache key is still valid for a file path
        by comparing current content hash with the cached hash
        """
        import hashlib
        
        try:
            # Parse the key back to a metadata dict
            cached_metadata = json.loads(key)
            
            # Check if file exists and size matches
            path = Path(file_path)
            if not path.exists():
                return False
                
            stats = path.stat()
            if cached_metadata['size'] != stats.st_size:
                return False
                
            # Read and hash the same portion of the file
            with open(file_path, 'rb') as f:
                content_sample = f.read(self.sample_size)
            
            # Create a hash of the content sample
            content_hash = hashlib.md5(content_sample).hexdigest()
            
            # Compare hashes
            return cached_metadata['hash'] == content_hash
            
        except (json.JSONDecodeError, KeyError, FileNotFoundError):
            return False