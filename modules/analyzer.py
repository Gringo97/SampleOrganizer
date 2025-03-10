"""
Audio analysis module for the Audio Sample Organizer
Handles audio feature extraction and analysis
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple, Any

# Import utils
from .utils import Timeout

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
    def __init__(self, config: Dict):
        self.enabled = config.get('enable_audio_analysis', False) and LIBROSA_AVAILABLE
        self.in_memory_cache = {}  # In-memory cache for analysis results
        self.cache = {}  # Add this line to initialize the cache attribute
        self.analysis_timeout = config.get('analysis_timeout', 10)  # seconds
        self.cache_hits = 0
        self.cache_misses = 0
        
        # Analysis thresholds from config or defaults
        self.thresholds = {
            'loop_min_duration': config.get('loop_min_duration', 1.0),
            'oneshot_max_duration': config.get('oneshot_max_duration', 1.5),
            'percussive_threshold': config.get('percussive_threshold', 0.6),
            'harmonic_threshold': config.get('harmonic_threshold', 0.6),
            'high_energy_threshold': config.get('high_energy_threshold', 0.7),
        }
    
        if self.enabled:
            logging.info("Audio analysis enabled with librosa")
        else:
            logging.info("Audio analysis disabled")
    
    def analyze_file(self, file_path: Path) -> Optional[AudioFeatures]:
        """Analyze audio file and extract features"""
        if not self.enabled:
            return None
            
        # Check cache first
        cache_key = str(file_path)
        if cache_key in self.cache:
            return self.cache[cache_key]
            
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
                    
                    is_percussive = percussive_ratio > self.thresholds['percussive_threshold']
                    is_harmonic = harmonic_ratio > self.thresholds['harmonic_threshold']
                
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
                self.cache[cache_key] = features
                return features
                
        except TimeoutError:
            logging.warning(f"Analysis timeout for {file_path}")
            return None
        except Exception as e:
            logging.warning(f"Error analyzing audio file {file_path}: {str(e)}")
            return None
    
    def detect_loop_oneshot(self, features: AudioFeatures) -> Tuple[bool, bool]:
        """Detect if audio is likely a loop or one-shot based on its features"""
        is_loop = False
        is_one_shot = False
        
        if not features:
            return is_loop, is_one_shot
            
        # Check duration first
        if features.duration < self.thresholds['oneshot_max_duration']:
            is_one_shot = True
        elif features.duration > self.thresholds['loop_min_duration'] and features.tempo > 0:
            is_loop = True
            
        # Further refine based on audio characteristics
        if is_one_shot:
            # One-shots typically have a quick attack and decay
            if features.is_percussive and features.zero_crossing_rate > 0.1:
                is_one_shot = True
            # Low sustain for percussive one-shots
            elif features.duration < 0.5 and features.is_percussive:
                is_one_shot = True
        
        if is_loop:
            # Loops typically have consistent energy throughout
            if features.tempo > 60 and features.rms_energy > 0.05:
                is_loop = True
                
        # Edge cases - if both or neither are detected
        if is_loop and is_one_shot:
            # Prioritize based on features
            if features.duration > 2.0:
                is_one_shot = False
            else:
                is_loop = False
        
        return is_loop, is_one_shot