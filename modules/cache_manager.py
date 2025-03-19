"""
Cache management system for the Audio Sample Organizer.
Handles caching of audio analysis results to improve performance.
"""

import logging
import threading
import time
import queue  # Add explicit import for queue module
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from queue import Queue
from typing import Any, Dict, List, Optional, Set, Tuple

from .interfaces import ICacheKey, ICacheManager, ICacheStorage
from .cache_key import FileMetadataKey
from .cache_storage import create_storage


class CacheEntry:
    """Represents a single cache entry with metadata"""
    
    def __init__(self, value: Any):
        self.value = value
        self.timestamp = datetime.now().timestamp()
        self.access_count = 1
        self.last_access = self.timestamp
    
    def access(self):
        """Update access statistics when entry is accessed"""
        self.access_count += 1
        self.last_access = datetime.now().timestamp()


class CacheManager(ICacheManager):
    """
    Manages audio analysis cache with options for background saving,
    size monitoring, and entry expiration.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the cache manager with configuration settings
        
        Args:
            config: Dictionary containing cache configuration
        """
        # Extract cache settings
        cache_config = config.get('cache_settings', {})
        self.enabled = cache_config.get('enable_cache', True)
        self.cache_file = cache_config.get('cache_file', './cache/audio_analysis_cache.pkl')
        self.max_size_mb = cache_config.get('max_cache_size_mb', 100)
        self.expiration_days = cache_config.get('cache_expiration_days', 30)
        self.background_saving = cache_config.get('background_saving', True)
        self.save_interval = cache_config.get('save_interval', 60)  # seconds
        
        # Initialize components
        self.key_generator = FileMetadataKey()  # Default key generator
        self.storage = create_storage(self.cache_file)
        
        # Initialize cache data
        self.cache_data = {'metadata': {'version': 1}, 'entries': {}}
        self.entry_objects = {}  # file_path -> CacheEntry
        self.path_to_key = {}    # file_path -> cache_key
        self.key_to_path = {}    # cache_key -> file_path
        
        # Statistics
        self.stats = {
            'hits': 0,
            'misses': 0,
            'invalidations': 0,
            'evictions': 0,
            'load_time': 0,
            'save_time': 0,
            'last_save': None,
            'entry_count': 0,
            'size_bytes': 0
        }
        
        # Thread synchronization
        self.lock = threading.RLock()
        self.save_queue = Queue()
        self.exit_flag = threading.Event()
        self.save_thread = None
        
        # Load cache on startup if enabled
        if self.enabled:
            self._load_cache()
            
            # Start background saving thread if enabled
            if self.background_saving:
                self._start_background_thread()
    
    def _load_cache(self):
        """Load cache data from storage"""
        if not self.enabled:
            return
            
        start_time = time.time()
        self.cache_data = self.storage.load()
        
        # Update statistics
        load_time = time.time() - start_time
        self.stats['load_time'] = load_time
        
        # Process cache entries
        now = datetime.now().timestamp()
        expiration_time = now - (self.expiration_days * 24 * 60 * 60)
        
        with self.lock:
            entries = self.cache_data.get('entries', {})
            valid_entries = {}
            
            for key, entry_data in entries.items():
                # Skip entries with missing or invalid timestamp
                if 'timestamp' not in entry_data:
                    continue
                    
                # Skip expired entries
                if entry_data['timestamp'] < expiration_time:
                    self.stats['evictions'] += 1
                    continue
                
                # Keep valid entries
                valid_entries[key] = entry_data
                
                # Create entry object
                if 'file_path' in entry_data and 'value' in entry_data:
                    file_path = entry_data['file_path']
                    entry = CacheEntry(entry_data['value'])
                    entry.timestamp = entry_data['timestamp']
                    entry.access_count = entry_data.get('access_count', 1)
                    entry.last_access = entry_data.get('last_access', entry.timestamp)
                    
                    self.entry_objects[file_path] = entry
                    self.path_to_key[file_path] = key
                    self.key_to_path[key] = file_path
            
            # Update cache data with valid entries only
            self.cache_data['entries'] = valid_entries
            self.stats['entry_count'] = len(valid_entries)
            self.stats['size_bytes'] = self.storage.get_size()
            
        logging.info(f"Loaded {self.stats['entry_count']} cache entries in {load_time:.2f}s")
    
    def _save_cache(self, force=False):
        """
        Save cache data to storage
        
        Args:
            force: If True, save regardless of whether there are pending changes
        """
        if not self.enabled:
            return
            
        # Skip saving if there are no entries and it's not a forced save
        if not force and len(self.entry_objects) == 0:
            return
            
        start_time = time.time()
        
        # Verify lock is a proper lock object before using it
        if not hasattr(self.lock, '__enter__') or not hasattr(self.lock, '__exit__'):
            logging.error(f"Lock is not a proper context manager, it's a {type(self.lock)}")
            # Create a new lock to avoid errors
            self.lock = threading.RLock()
        
        # Update entries in cache_data from entry_objects
        try:
            with self.lock:
                for file_path, entry in self.entry_objects.items():
                    key = self.path_to_key.get(file_path)
                    if not key:
                        continue
                        
                    self.cache_data['entries'][key] = {
                        'file_path': file_path,
                        'value': entry.value,
                        'timestamp': entry.timestamp,
                        'access_count': entry.access_count,
                        'last_access': entry.last_access
                    }
                
                # Update metadata
                self.cache_data['metadata']['last_saved'] = datetime.now().timestamp()
                self.cache_data['metadata']['entry_count'] = len(self.entry_objects)
                
                # Save to storage
                success = self.storage.save(self.cache_data)
                
            # Update statistics
            save_time = time.time() - start_time
            self.stats['save_time'] = save_time
            self.stats['last_save'] = datetime.now().timestamp()
            self.stats['size_bytes'] = self.storage.get_size()
            
            if success is False:
                logging.warning("Failed to save cache")
            else:
                logging.debug(f"Saved {len(self.entry_objects)} cache entries in {save_time:.2f}s")
                
        except Exception as e:
            logging.error(f"Error during cache save: {e}", exc_info=True)
    
    def _start_background_thread(self):
        """Start the background thread for cache saving"""
        if self.save_thread is not None and self.save_thread.is_alive():
            return  # Thread already running
            
        self.exit_flag.clear()
        self.save_thread = threading.Thread(target=self._background_save_worker)
        self.save_thread.daemon = True
        self.save_thread.start()
        logging.info("Started background cache saving thread")
    
    def _background_save_worker(self):
        """Worker function for background cache saving"""
        while not self.exit_flag.is_set():
            try:
                # Wait for save request or interval
                save_requested = False
                try:
                    self.save_queue.get(timeout=self.save_interval)
                    save_requested = True
                except queue.Empty:  # Explicitly catch Queue.Empty exception
                    # Timeout occurred, periodically save cache
                    pass
                except Exception as queue_error:
                    logging.error(f"Error getting from save queue: {queue_error}")
                    time.sleep(1)  # Prevent tight loop on error
                    continue
                    
                # Save cache
                try:
                    self._save_cache(force=save_requested)
                except Exception as save_error:
                    logging.error(f"Error in cache save operation: {save_error}")
                
                # Mark task as done if it was a requested save
                if save_requested:
                    try:
                        self.save_queue.task_done()
                    except Exception as task_error:
                        logging.error(f"Error marking task as done: {task_error}")
                    
            except Exception as e:
                logging.error(f"Error in cache save thread: {e}", exc_info=True)
                # Avoid tight loop if there's an error
                time.sleep(1)
    
    def _check_size_and_evict(self):
        """Check cache size and evict entries if necessary"""
        # Skip if max size is not set
        if self.max_size_mb <= 0:
            return
            
        # Calculate current size
        current_size_mb = self.stats['size_bytes'] / (1024 * 1024)
        
        # If we're under the limit, do nothing
        if current_size_mb <= self.max_size_mb:
            return
            
        with self.lock:
            # Calculate how many entries to remove (target ~20% reduction)
            target_reduction = 0.2
            target_size_mb = self.max_size_mb * 0.8
            
            # Sort entries by last access time (oldest first)
            sorted_entries = sorted(
                self.entry_objects.items(),
                key=lambda x: x[1].last_access
            )
            
            # Remove entries until we're under target size or run out of entries
            removed_count = 0
            for file_path, _ in sorted_entries:
                key = self.path_to_key.get(file_path)
                if not key:
                    continue
                    
                # Remove from all collections
                del self.entry_objects[file_path]
                del self.path_to_key[file_path]
                del self.key_to_path[key]
                if key in self.cache_data['entries']:
                    del self.cache_data['entries'][key]
                    
                removed_count += 1
                self.stats['evictions'] += 1
                
                # Check if we've removed enough
                if removed_count >= len(sorted_entries) // 3:  # Remove up to 1/3 of entries
                    break
            
            # Update entry count
            self.stats['entry_count'] = len(self.entry_objects)
            
            logging.info(f"Evicted {removed_count} cache entries due to size limit")
    
    def get(self, file_path: str) -> Optional[Any]:
        """
        Get a cached value for a file path
        
        Args:
            file_path: Path to the file
            
        Returns:
            The cached value or None if not found
        """
        if not self.enabled:
            self.stats['misses'] += 1
            return None
            
        with self.lock:
            # If we already have this path cached
            if file_path in self.entry_objects:
                key = self.path_to_key.get(file_path)
                
                # Verify the key is still valid
                if key and self.key_generator.is_valid(key, file_path):
                    # Update access stats
                    entry = self.entry_objects[file_path]
                    entry.access()
                    
                    self.stats['hits'] += 1
                    return entry.value
                else:
                    # Key is invalid (file changed), remove it
                    self._remove_entry(file_path)
            
            # Try to generate a key and check if it exists in cache
            try:
                new_key = self.key_generator.generate(file_path)
                
                # If this key exists, it's for a different file path (collision)
                if new_key in self.key_to_path:
                    existing_path = self.key_to_path[new_key]
                    if existing_path != file_path:
                        # This is a different file with the same key (unlikely but possible)
                        logging.debug(f"Cache key collision between {file_path} and {existing_path}")
                        self.stats['misses'] += 1
                        return None
                        
                    # This is the same file but path changed, update mappings
                    if existing_path in self.entry_objects:
                        entry = self.entry_objects[existing_path]
                        del self.entry_objects[existing_path]
                        self.entry_objects[file_path] = entry
                        self.path_to_key[file_path] = new_key
                        self.key_to_path[new_key] = file_path
                        
                        entry.access()
                        self.stats['hits'] += 1
                        return entry.value
                
                # Not found in cache
                self.stats['misses'] += 1
                return None
                
            except Exception as e:
                logging.warning(f"Error generating cache key for {file_path}: {e}")
                self.stats['misses'] += 1
                return None
    
    def put(self, file_path: str, value: Any) -> None:
        """Store a value in the cache for a file path"""
        if not self.enabled:
            return
            
        with self.lock:
            try:
                # Generate a new key
                key = self.key_generator.generate(file_path)
                
                # Convert NumPy objects to standard Python types
                import numpy as np
                def convert_numpy(obj):
                    if isinstance(obj, (np.float32, np.float64)):
                        return float(obj)
                    elif isinstance(obj, np.ndarray):
                        return obj.tolist()
                    elif isinstance(obj, dict):
                        return {k: convert_numpy(v) for k, v in obj.items()}
                    elif isinstance(obj, list):
                        return [convert_numpy(i) for i in obj]
                    return obj
                
                # Ensure no NumPy objects remain
                converted_value = convert_numpy(value)
                
                # Create a new entry
                entry = CacheEntry(converted_value)
                
                # Store mappings
                self.entry_objects[file_path] = entry
                self.path_to_key[file_path] = key
                self.key_to_path[key] = file_path
                
                # Update stats
                self.stats['entry_count'] = len(self.entry_objects)
                
                # Request a save if background saving is enabled
                if self.background_saving:
                    try:
                        self.save_queue.put_nowait(True)
                    except:
                        pass  # Queue full, will save on next interval
                else:
                    # Immediate save
                    self._save_cache()
                    
                # Check cache size and evict if necessary
                self._check_size_and_evict()
                
            except Exception as e:
                logging.warning(f"Error caching value for {file_path}: {e}")
    
    def _remove_entry(self, file_path: str) -> None:
        """
        Remove an entry from the cache
        
        Args:
            file_path: Path to the file
        """
        with self.lock:
            key = self.path_to_key.get(file_path)
            if not key:
                return
                
            # Remove from all collections
            if file_path in self.entry_objects:
                del self.entry_objects[file_path]
            
            if file_path in self.path_to_key:
                del self.path_to_key[file_path]
                
            if key in self.key_to_path:
                del self.key_to_path[key]
                
            if key in self.cache_data['entries']:
                del self.cache_data['entries'][key]
                
            # Update stats
            self.stats['invalidations'] += 1
            self.stats['entry_count'] = len(self.entry_objects)
    
    def invalidate(self, file_path: str) -> None:
        """
        Invalidate a cache entry for a file path
        
        Args:
            file_path: Path to the file
        """
        if not self.enabled:
            return
            
        self._remove_entry(file_path)
    
    def clear(self) -> None:
        """Clear the entire cache"""
        if not self.enabled:
            return
            
        with self.lock:
            # Clear all collections
            self.entry_objects.clear()
            self.path_to_key.clear()
            self.key_to_path.clear()
            self.cache_data['entries'] = {}
            
            # Clear storage
            self.storage.clear()
            
            # Update stats
            self.stats['entry_count'] = 0
            self.stats['size_bytes'] = 0
            self.stats['evictions'] += self.stats['entry_count']
            
            logging.info("Cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        stats = dict(self.stats)
        stats['enabled'] = self.enabled
        stats['background_saving'] = self.background_saving
        stats['cache_file'] = str(self.cache_file)
        stats['hit_ratio'] = (self.stats['hits'] / (self.stats['hits'] + self.stats['misses'])) * 100 if (self.stats['hits'] + self.stats['misses']) > 0 else 0
        stats['size_mb'] = self.stats['size_bytes'] / (1024 * 1024) if self.stats['size_bytes'] > 0 else 0
        stats['max_size_mb'] = self.max_size_mb
        
        return stats
    
    def shutdown(self) -> None:
        """Perform cleanup and ensure cache is saved"""
        if not self.enabled:
            return
            
        logging.info("Shutting down cache manager")
        
        # Stop background thread
        if self.background_saving and self.save_thread and self.save_thread.is_alive():
            # Set exit flag first to signal thread to stop
            self.exit_flag.set()
            
            # Try to join the thread with a timeout
            try:
                self.save_thread.join(timeout=5.0)
                # Check if thread is still alive after timeout
                if self.save_thread.is_alive():
                    logging.warning("Cache save thread did not terminate within timeout")
            except Exception as join_error:
                logging.error(f"Error joining cache thread: {join_error}")
        
        # Final save - even if the thread didn't terminate properly
        try:
            self._save_cache(force=True)
        except Exception as save_error:
            logging.error(f"Error during final cache save: {save_error}")
        
        logging.info(f"Cache shutdown complete. Entries: {self.stats['entry_count']}, " 
                    f"Hits: {self.stats['hits']}, Misses: {self.stats['misses']}")