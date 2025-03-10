"""
Utility functions for the Audio Sample Organizer
"""

import json
import logging
import os
import platform
import signal
import threading
from pathlib import Path
from typing import Dict, Any, Optional

class Timeout:
    """Context manager for timeout operations"""
    def __init__(self, seconds=1, error_message='Timeout'):
        self.seconds = seconds
        self.error_message = error_message
        
    def handle_timeout(self, signum, frame):
        raise TimeoutError(self.error_message)
        
    def __enter__(self):
        if platform.system() != 'Windows':  # signal.SIGALRM not available on Windows
            signal.signal(signal.SIGALRM, self.handle_timeout)
            signal.alarm(self.seconds)
        
    def __exit__(self, type, value, traceback):
        if platform.system() != 'Windows':
            signal.alarm(0)

def setup_logging(log_level: int = logging.INFO, log_file: str = 'audio_organizer.log'):
    """Setup logging configuration"""
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load configuration from file or create default"""
    default_config = {
        'source_path': '.',
        'output_path': './organized_samples',
        'patterns_file': './config/patterns.json',
        'threads': os.cpu_count(),
        'process_subfolders': True,
        'overwrite_existing': False,
        'move_files': False,
        'generate_report': True,
        'enable_audio_analysis': False,
        'logging_level': 'INFO'
    }
    
    # If config path provided, try to load it
    if config_path and config_path.exists():
        try:
            with open(config_path) as f:
                loaded_config = json.load(f)
                # Merge with defaults
                config = {**default_config, **loaded_config}
                return config
        except Exception as e:
            logging.error(f"Error loading config: {str(e)}")
            raise
    
    # Try to find config.json in config directory
    default_path = Path('./config/config.json')
    if default_path.exists():
        try:
            with open(default_path) as f:
                loaded_config = json.load(f)
                # Merge with defaults
                config = {**default_config, **loaded_config}
                return config
        except Exception as e:
            logging.error(f"Error loading config: {str(e)}")
            raise
    
    logging.warning("No config file found, using defaults")
    return default_config

def get_file_extension(file_path: Path) -> str:
    """Get file extension in lowercase without the dot"""
    return file_path.suffix.lower()[1:] if file_path.suffix else ""

def ensure_dir(directory: Path):
    """Ensure a directory exists, creating it if necessary"""
    directory.mkdir(parents=True, exist_ok=True)

class FileLock:
    """Simple lock for file operations"""
    def __init__(self):
        self.lock = threading.Lock()
        
    def acquire(self):
        return self.lock.acquire()
        
    def release(self):
        return self.lock.release()
        
    def __enter__(self):
        self.acquire()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

def sanitize_filename(filename: str) -> str:
    """Sanitize filename to be safe for all operating systems"""
    # Replace invalid characters with underscores
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Truncate filenames to a reasonable length
    if len(filename) > 255:
        base, ext = os.path.splitext(filename)
        filename = base[:255-len(ext)] + ext
        
    return filename

def check_audio_libraries():
    """Check if audio analysis libraries are available"""
    try:
        import librosa
        import numpy
        return True
    except ImportError:
        return False