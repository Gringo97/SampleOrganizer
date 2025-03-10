"""
Audio Sample Organizer - Modules Package

This package contains the core modules for the Audio Sample Organizer:
- analyzer: Audio content analysis
- classifier: Pattern matching and categorization
- processor: File processing and organization
- utils: Utility functions and helpers
"""

__version__ = '0.0.1'
__author__ = 'Oscar de la Fuente Ruiz 25/02/2025'

# Import key components for easier access
from .analyzer import AudioAnalyzer, AudioFeatures
from .classifier import PatternMatcher, ClassificationResult
from .processor import AudioFileProcessor
from .utils import setup_logging, load_config, check_audio_libraries

# Check for required libraries
audio_analysis_available = check_audio_libraries()