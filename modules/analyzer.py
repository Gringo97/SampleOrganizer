"""
Audio analysis module for the Audio Sample Organizer
Handles audio feature extraction and analysis with caching support
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple, Any

# Import utils
from .utils import Timeout
from .interfaces import ICacheManager

# Try to import librosa
try:
    import librosa
    import numpy as np
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    logging.warning("librosa not available - audio analysis disabled")

@dataclass
class AudioFeatures:
    """Features extracted from audio analysis"""
    duration: float
    tempo: float
    is_percussive: bool
    is_harmonic: bool
    spectral_centroid: float
    spectral_bandwidth: float
    rms_energy: float
    zero_crossing_rate: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert features to dictionary for reporting"""
        return {
            "duration": f"{self.duration:.2f}s",
            "tempo": f"{self.tempo:.1f} BPM" if self.tempo > 0 else "N/A",
            "type": "Percussive" if self.is_percussive else "Harmonic" if self.is_harmonic else "Mixed",
            "spectral_centroid": f"{self.spectral_centroid:.1f} Hz",
            "energy": f"{self.rms_energy:.4f}",
            "zero_crossing_rate": f"{self.zero_crossing_rate:.4f}"
        }

class AudioAnalyzer:
    """Handles audio feature extraction and analysis with caching"""
    def __init__(self, config: Dict, cache_manager: Optional[ICacheManager] = None):
        """
        Initialize the audio analyzer
        
        Args:
            config: Configuration dictionary
            cache_manager: Optional cache manager for persistent caching
        """
        self.config = config
        self.enabled = config.get('enable_audio_analysis', False) and LIBROSA_AVAILABLE
        self.in_memory_cache = {}  # Fallback in-memory cache when no cache manager is available
        self.analysis_timeout = config.get('analysis_timeout', 10)  # seconds
        
        # Use the provided cache manager if available
        self.cache_manager = cache_manager
        self.using_persistent_cache = cache_manager is not None
        
        # Statistics
        self.cache_hits = 0
        self.cache_misses = 0
        
        # Load duration thresholds from patterns file
        self.patterns_file = config.get('patterns_file')
        self.category_thresholds = {}
        self.default_thresholds = {
            'loop_min_duration': config.get('loop_min_duration', 1.0),
            'oneshot_max_duration': config.get('oneshot_max_duration', 1.5),
            'percussive_threshold': config.get('percussive_threshold', 0.6),
            'harmonic_threshold': config.get('harmonic_threshold', 0.6),
            'high_energy_threshold': config.get('high_energy_threshold', 0.7),
        }
        
        self._load_duration_thresholds()
        
        if self.enabled:
            cache_type = "persistent" if self.using_persistent_cache else "in-memory"
            logging.info(f"Audio analysis enabled with librosa using {cache_type} caching")
        else:
            logging.info("Audio analysis disabled")
    
    def _load_duration_thresholds(self):
        """Load duration thresholds from patterns file"""
        if not self.patterns_file:
            logging.warning("No patterns file specified, using default thresholds")
            return
            
        try:
            with open(self.patterns_file) as f:
                patterns_data = json.load(f)
                
            # Check if duration thresholds are defined
            if 'duration_thresholds' in patterns_data:
                # Load global defaults
                if 'global' in patterns_data['duration_thresholds']:
                    global_thresholds = patterns_data['duration_thresholds']['global']
                    self.default_thresholds['loop_min_duration'] = global_thresholds.get(
                        'loop_min_duration', self.default_thresholds['loop_min_duration'])
                    self.default_thresholds['oneshot_max_duration'] = global_thresholds.get(
                        'oneshot_max_duration', self.default_thresholds['oneshot_max_duration'])
                
                # Load category-specific thresholds
                for category, thresholds in patterns_data['duration_thresholds'].items():
                    if category != 'global':
                        self.category_thresholds[category] = thresholds
                
                logging.info(f"Loaded duration thresholds from {self.patterns_file}")
        except Exception as e:
            logging.warning(f"Error loading duration thresholds: {e}")
    
    def analyze_file(self, file_path: Path) -> Optional[AudioFeatures]:
        """
        Analyze audio file and extract features with caching
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            AudioFeatures object or None if analysis failed
        """
        if not self.enabled:
            return None
        
        # Convert Path to string for cache keys
        file_path_str = str(file_path)

        # Validate file exists and is readable
        try:
            if not file_path.exists():
                logging.warning(f"File not found: {file_path}")
                return None
            
            # Check file size using config values
            file_size = file_path.stat().st_size
            min_size = self.config.get('min_file_size_bytes', 5120)  # Default 5 KB
            max_size = self.config.get('max_file_size_bytes', 52428800)  # Default 50 MB
            
            if file_size < min_size:
                logging.debug(f"Skipping very small file: {file_path}")
                return None
            
            if file_size > max_size:
                logging.debug(f"Skipping very large file: {file_path}")
                return None
        
        except Exception as e:
            logging.warning(f"Error checking file {file_path}: {e}")
            return None    
            
        # Try persistent cache first if available
        if self.using_persistent_cache:
            cached_features = self.cache_manager.get(file_path_str)
            if cached_features is not None:
                self.cache_hits += 1
                return cached_features
                
        # Fallback to in-memory cache if needed
        elif file_path_str in self.in_memory_cache:
            self.cache_hits += 1
            return self.in_memory_cache[file_path_str]
        
        # Cache miss, perform analysis
        self.cache_misses += 1
        
        try:
            # Use a timeout to prevent hanging on corrupt files
            with Timeout(seconds=self.analysis_timeout):
                # Load audio file
                y, sr = librosa.load(file_path, sr=None, mono=True, duration=30)
                
                # Basic features
                duration = librosa.get_duration(y=y, sr=sr)
                
                # Tempo estimation
                tempo = 0.0
                try:
                    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
                    tempo = librosa.beat.tempo(onset_envelope=onset_env, sr=sr)[0]
                except Exception as e:
                    # Tempo estimation can fail on non-rhythmic sounds
                    logging.debug(f"Tempo estimation failed for {file_path}: {e}")
                    tempo = 0.0
                
                # Harmonic/percussive separation
                y_harmonic, y_percussive = librosa.effects.hpss(y)
                harmonic_energy = np.mean(y_harmonic**2)
                percussive_energy = np.mean(y_percussive**2)
                total_energy = harmonic_energy + percussive_energy
                
                is_percussive = False
                is_harmonic = False
                
                if total_energy > 0:
                    percussive_ratio = percussive_energy / total_energy
                    harmonic_ratio = harmonic_energy / total_energy
                    
                    is_percussive = percussive_ratio > self.default_thresholds['percussive_threshold']
                    is_harmonic = harmonic_ratio > self.default_thresholds['harmonic_threshold']
                
                # Spectral features
                spectral_centroid = np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)[0])
                spectral_bandwidth = np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr)[0])
                
                # Energy
                rms_energy = np.mean(librosa.feature.rms(y=y)[0])
                
                # Other features
                zero_crossing_rate = np.mean(librosa.feature.zero_crossing_rate(y=y)[0])
                
                # Create features object
                features = AudioFeatures(
                    duration=duration,
                    tempo=tempo,
                    is_percussive=is_percussive,
                    is_harmonic=is_harmonic,
                    spectral_centroid=spectral_centroid,
                    spectral_bandwidth=spectral_bandwidth,
                    rms_energy=rms_energy,
                    zero_crossing_rate=zero_crossing_rate
                )
                
                # Cache the result
                if self.using_persistent_cache:
                    self.cache_manager.put(file_path_str, features)
                else:
                    self.in_memory_cache[file_path_str] = features
                    
                return features
                
        except TimeoutError:
            logging.warning(f"Analysis timeout for {file_path}")
            return None
        except Exception as e:
            logging.warning(f"Error analyzing audio file {file_path}: {str(e)}")
            return None
    
    def get_duration_thresholds(self, category: str, subcategory: str = None) -> Tuple[float, float]:
        """Get duration thresholds specific to a category and subcategory"""
        # Default thresholds
        loop_min = self.default_thresholds['loop_min_duration']
        oneshot_max = self.default_thresholds['oneshot_max_duration']
        
        # If no category, return defaults
        if not category or category not in self.category_thresholds:
            return loop_min, oneshot_max
        
        # Get category thresholds
        cat_thresholds = self.category_thresholds[category]
        
        # Update with category level thresholds if available
        if 'loop_min_duration' in cat_thresholds:
            loop_min = cat_thresholds['loop_min_duration']
        if 'oneshot_max_duration' in cat_thresholds:
            oneshot_max = cat_thresholds['oneshot_max_duration']
        
        # If subcategory is specified, check for more specific thresholds
        if subcategory:
            # Extract subcategory key (first part before slash if it's a path)
            subcategory_key = subcategory.split('/')[0] if '/' in subcategory else subcategory
            
            # Check if this subcategory has specific thresholds
            if subcategory_key in cat_thresholds:
                subcat_thresholds = cat_thresholds[subcategory_key]
                
                # Update with subcategory thresholds if available
                if 'loop_min_duration' in subcat_thresholds:
                    loop_min = subcat_thresholds['loop_min_duration']
                if 'oneshot_max_duration' in subcat_thresholds:
                    oneshot_max = subcat_thresholds['oneshot_max_duration']
        
        return loop_min, oneshot_max
        
    def detect_loop_oneshot(self, features: AudioFeatures, 
                           category: str = None, subcategory: str = None) -> Tuple[bool, bool]:
        """Detect if audio is likely a loop or one-shot based on its features and category"""
        is_loop = False
        is_one_shot = False
        
        if not features:
            return is_loop, is_one_shot
            
        # Get category-specific thresholds
        loop_min_duration, oneshot_max_duration = self.get_duration_thresholds(category, subcategory)
        
        # Log detailed thresholds for debugging
        if category:
            logging.debug(f"Using thresholds for {category}/{subcategory if subcategory else ''}: " +
                         f"loop_min={loop_min_duration}, oneshot_max={oneshot_max_duration}")
            
        # Check duration first
        if features.duration <= oneshot_max_duration:
            is_one_shot = True
        elif features.duration >= loop_min_duration and features.tempo > 0:
            is_loop = True
            
        # Further refine based on audio characteristics
        if is_one_shot:
            # One-shots typically have a quick attack and decay
            if features.is_percussive and features.zero_crossing_rate > 0.1:
                is_one_shot = True
            # Low sustain for percussive one-shots
            elif features.duration < 0.5 and features.is_percussive:
                is_one_shot = True
                
            # Category-specific characteristics
            if category == "DRUMS":
                # Drums one-shots are almost always percussive
                if features.is_percussive:
                    is_one_shot = True
            elif category == "FX":
                # FX shots can be longer and still be one-shots
                if features.duration <= oneshot_max_duration * 1.2:  # Give a bit more leeway
                    is_one_shot = True
        
        if is_loop:
            # Loops typically have consistent energy throughout
            if features.tempo > 60 and features.rms_energy > 0.05:
                is_loop = True
                
            # Category-specific characteristics
            if category == "DRUMS":
                # Drum loops should have a clear tempo and be fairly long
                if features.tempo > 80 and features.duration >= loop_min_duration:
                    is_loop = True
            elif category == "VOCALS":
                # Vocal loops might have variable tempo but still be loops
                if features.duration >= loop_min_duration:
                    is_loop = True
                
        # Edge cases - if both or neither are detected
        if is_loop and is_one_shot:
            # Prioritize based on features
            if features.duration > loop_min_duration * 1.5:
                is_one_shot = False
            elif features.duration < oneshot_max_duration * 0.8:
                is_loop = False
            else:
                # Use percussive vs harmonic features as a tiebreaker
                if features.is_percussive and category in ["DRUMS", "FX"]:
                    is_one_shot = features.duration < oneshot_max_duration
                    is_loop = not is_one_shot
                elif features.is_harmonic and category in ["INSTRUMENTS", "VOCALS", "BASS"]:
                    is_loop = features.duration > loop_min_duration
                    is_one_shot = not is_loop
        
        return is_loop, is_one_shot
        
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self.cache_hits + self.cache_misses
        hit_ratio = (self.cache_hits / total * 100) if total > 0 else 0
        
        stats = {
            'hits': self.cache_hits,
            'misses': self.cache_misses,
            'total': total,
            'hit_ratio': hit_ratio,
            'using_persistent_cache': self.using_persistent_cache
        }
        
        # Add persistent cache stats if available
        if self.using_persistent_cache:
            persistent_stats = self.cache_manager.get_stats()
            stats['persistent_cache'] = persistent_stats
            
        return stats