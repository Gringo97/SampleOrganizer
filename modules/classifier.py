"""
Classification module for the Audio Sample Organizer
Handles pattern matching and category detection
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set, Any

# Import analyzer module
from .analyzer import AudioFeatures

@dataclass
class ClassificationResult:
    """Classification result including pattern predictions and audio features"""
    original_path: Path
    category: str
    subcategory: str
    confidence: float
    matched_patterns: List[str]
    is_loop: bool
    is_one_shot: bool
    audio_features: Optional[AudioFeatures] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for reporting"""
        result = {
            "file": str(self.original_path),
            "category": self.category,
            "subcategory": self.subcategory,
            "confidence": f"{self.confidence:.2f}",
            "matched_patterns": self.matched_patterns,
            "type": "LOOP" if self.is_loop else "ONE SHOT" if self.is_one_shot else "UNDEFINED"
        }
        
        # Add audio features if available
        if self.audio_features:
            result["audio_features"] = self.audio_features.to_dict()
            
        return result

class PatternMatcher:
    """Handles pattern matching and compilation with improved categorization"""
    def __init__(self, patterns_file: Path):
        self.patterns_file = patterns_file
        
        # Load patterns
        with open(patterns_file) as f:
            pattern_data = json.load(f)
            self.pattern_config = pattern_data["pattern_config"]
            self.base_patterns = pattern_data["base_patterns"]
            self.categories = pattern_data["categories"]
            self.folder_structure = pattern_data.get("folder_structure", {})
        
        # Get classification priority from pattern file
        self.category_priority = pattern_data.get("classification_priority", {})
        
        # Pre-compile all patterns for better performance
        self.compiled_patterns = self._precompile_patterns()
        
        # Store exact match keywords for common categories to improve detection
        self.exact_keywords = self._build_exact_keywords()
        
        logging.info(f"Loaded patterns from {patterns_file}")
        logging.info(f"Compiled patterns for {len(self.categories)} categories")
    
    def _build_exact_keywords(self) -> Dict[str, Set[str]]:
        """Build lists of exact match keywords for each category to improve detection"""
        exact_keywords = {}
        
        # Define strong keywords for each category that should take precedence
        exact_keywords["DRUMS"] = {
            'kick', 'snare', 'hat', 'hihat', 'tom', 'crash', 'ride', 'cymbal',
            'clap', 'percussion', 'drum', 'bongo', 'conga', 'rim', 'shaker',
            'tambourine', 'timbal', 'cowbell', 'perc', '808', '909', '707', '606'
        }
        
        exact_keywords["BASS"] = {
            'bass', 'sub', 'subbass', '808bass', 'bassline'
        }
        
        exact_keywords["VOCALS"] = {
            'vocal', 'vox', 'voice', 'acapella', 'verse', 'chorus', 'adlib', 'chant',
            'sing', 'rap', 'mc', 'lyric', 'word', 'speech', 'spoken', 'talk'
        }
        
        exact_keywords["FX"] = {
            'fx', 'effect', 'impact', 'riser', 'sweep', 'whoosh', 'transition',
            'buildup', 'sfx', 'foley', 'downlifter', 'uplifter'
        }
        
        return exact_keywords 

    
    def _precompile_patterns(self) -> Dict:
        """Pre-compile all regex patterns for better performance"""
        compiled = {
            'base': {},
            'categories': {},
            'subcategories': {}
        }
        
        wb = self.pattern_config["wb"]
        we = self.pattern_config["we"]
        ci = self.pattern_config["case_insensitive"]
        
        # Ensure configuration values are strings
        if not isinstance(wb, str):
            wb = str(wb) if not isinstance(wb, (bytes, bytearray)) else wb.decode('utf-8')
        if not isinstance(we, str):
            we = str(we) if not isinstance(we, (bytes, bytearray)) else we.decode('utf-8')
        if not isinstance(ci, str):
            ci = str(ci) if not isinstance(ci, (bytes, bytearray)) else ci.decode('utf-8')
        
        # Compile base patterns (LOOP and ONE SHOT)
        for key, pattern in self.base_patterns.items():
            # Ensure pattern is a string
            if not isinstance(pattern, str):
                pattern = str(pattern) if not isinstance(pattern, (bytes, bytearray)) else pattern.decode('utf-8')
            compiled['base'][key] = re.compile(f"{ci}{wb}(?:{pattern}){we}")
        
        # Compile category patterns
        for category, category_data in self.categories.items():
            compiled['categories'][category] = []
            
            # Main patterns
            if "mainPatterns" in category_data:
                for pattern_str in category_data["mainPatterns"]:
                    # Ensure pattern_str is a string
                    if not isinstance(pattern_str, str):
                        pattern_str = str(pattern_str) if not isinstance(pattern_str, (bytes, bytearray)) else pattern_str.decode('utf-8')
                    compiled['categories'][category].append(
                        re.compile(f"{ci}{wb}(?:{pattern_str}){we}")
                    )
            
            # Subcategory patterns
            if "subPatterns" in category_data:
                compiled['subcategories'][category] = {}
                for subcategory, pattern_str in category_data["subPatterns"].items():
                    # Ensure pattern_str is a string
                    if not isinstance(pattern_str, str):
                        pattern_str = str(pattern_str) if not isinstance(pattern_str, (bytes, bytearray)) else pattern_str.decode('utf-8')
                    compiled['subcategories'][category][subcategory] = re.compile(f"{ci}{wb}(?:{pattern_str}){we}")
        
        return compiled
        
    def check_loop_or_oneshot(self, base_name: str, folder_names: List[str]) -> Tuple[bool, bool]:
        """Determine if the sample is a loop or one-shot using pre-compiled patterns"""
        is_loop = False
        is_one_shot = False
        
        # Check for loop patterns using pre-compiled regex
        loop_pattern = self.compiled_patterns['base']["LOOP"]
        if loop_pattern.search(base_name) or any(loop_pattern.search(folder) for folder in folder_names if folder):
            is_loop = True
        
        # Check for one-shot patterns using pre-compiled regex
        one_shot_pattern = self.compiled_patterns['base']["ONE SHOT"]
        if one_shot_pattern.search(base_name) or any(one_shot_pattern.search(folder) for folder in folder_names if folder):
            is_one_shot = True
        
        # If both are detected, do more specific checking
        if is_loop and is_one_shot:
            # Look for stronger indicators
            loop_keywords = ['loop', 'phrase', 'groove', 'riff', 'beat', 'pattern']
            oneshot_keywords = ['one shot', 'oneshot', 'single hit', 'hit', 'stab', 'impact']
            
            # Count occurrences
            loop_count = sum(1 for kw in loop_keywords if kw in base_name.lower())
            oneshot_count = sum(1 for kw in oneshot_keywords if kw in base_name.lower())
            
            # Decide based on stronger evidence
            if loop_count > oneshot_count:
                is_one_shot = False
            else:
                is_loop = False
        
        # If none are detected, check folder names like "loops" or "one shots"
        if not is_loop and not is_one_shot:
            for folder in folder_names:
                if folder and ('loop' in folder.lower() or 'loops' in folder.lower()):
                    is_loop = True
                    break
                elif folder and ('one shot' in folder.lower() or 'oneshot' in folder.lower() or 'one-shot' in folder.lower()):
                    is_one_shot = True
                    break
        
        return is_loop, is_one_shot
    
    def _extract_keywords(self, text):
        """Extract keywords from text by splitting on non-alphanumeric chars"""
        if not text:
            return []
        
        # Convert to lowercase and split by non-alphanumeric chars
        words = re.split(r'[^a-zA-Z0-9]', text.lower())
        
        # Filter out empty strings and single characters
        return [word for word in words if len(word) > 1]
    
    def _match_keyword(self, folder_name, keyword):
        """Check if keyword matches folder name (case insensitive)"""
        if not keyword or not folder_name:
            return False
            
        folder_lower = folder_name.lower()
        keyword_lower = keyword.lower()
        
        return (
            keyword_lower == folder_lower or
            keyword_lower in folder_lower.split() or
            folder_lower in keyword_lower or
            keyword_lower in folder_lower
        )
    
    def check_pattern_match_strength(self, text: str, category: str) -> float:
        """Check the strength of pattern match for a specific category"""
        match_strength = 0.0
        
        # Check each pattern for this category
        for pattern in self.compiled_patterns['categories'][category]:
            matches = list(pattern.finditer(text))
            match_strength += len(matches) * 1.0
        
        return match_strength
    
    def check_exact_keyword_match(self, filename: str, folder_names: List[str]) -> Dict[str, float]:
        """Check for exact keyword matches in filename and folders"""
        scores = {}
        
        # Extract all words from filename
        filename_words = set([word.lower() for word in self._extract_keywords(filename)])
        
        # Extract all words from folder names
        folder_words = set()
        for folder in folder_names:
            folder_words.update([word.lower() for word in self._extract_keywords(folder)])
        
        # Check each category's keywords
        for category, keywords in self.exact_keywords.items():
            # Check filename keywords
            filename_matches = keywords.intersection(filename_words)
            if filename_matches:
                if category not in scores:
                    scores[category] = 0
                scores[category] += len(filename_matches) * 2.0  # Higher weight for filename matches
            
            # Check folder keywords
            folder_matches = keywords.intersection(folder_words)
            if folder_matches:
                if category not in scores:
                    scores[category] = 0
                scores[category] += len(folder_matches) * 1.5  # Medium weight for folder matches
        
        return scores

        
    def check_patterns(self, text: str, source_type: str) -> Dict[str, float]:
        """Check text against pre-compiled patterns and return scores for each category"""
        scores = {}
        
        # Check each category's patterns using pre-compiled regex
        for category, patterns in self.compiled_patterns['categories'].items():
            for pattern in patterns:
                matches = list(pattern.finditer(text))
                if matches:
                    if category not in scores:
                        scores[category] = 0
                    
                    # Base score depends on source type and number of matches
                    match_count = len(matches)
                    if source_type == "filename":
                        scores[category] += match_count * 1.0
                    elif source_type == "folder":
                        scores[category] += match_count * 1.5  # Higher weight for folder matches
        
        return scores
        
    def get_best_category(self, category_scores: Dict[str, float]) -> str:
        """Get the best category based on scores and priorities"""
        best_score = -1
        best_category = "UNKNOWN"
        
        for category, score in category_scores.items():
            priority = self.category_priority.get(category, 0)
            
            # Calculate combined score using both raw score and priority
            combined_score = score + (priority * 0.1)
            
            if combined_score > best_score:
                best_score = combined_score
                best_category = category
        
        return best_category
    
    def get_best_category(self, category_scores: Dict[str, float], filename: str, folder_names: List[str]) -> str:
        """Get the best category based on scores, priorities, and additional checks"""
        best_score = -1
        best_category = "UNKNOWN"
        
        # Get exact keyword matches (very strong signals)
        exact_keyword_scores = self.check_exact_keyword_match(filename, folder_names)
        
        # Add exact keyword scores with high weight
        for category, score in exact_keyword_scores.items():
            if category not in category_scores:
                category_scores[category] = 0
            category_scores[category] += score * 2  # Double the importance of exact keyword matches
        
        # Special handling for some categories
        if "kick" in filename.lower() or "bd" in filename.lower() or "bass drum" in filename.lower():
            if "DRUMS" not in category_scores:
                category_scores["DRUMS"] = 0
            category_scores["DRUMS"] += 5.0  # Strong boost for drum keywords
        
        if "vocal" in filename.lower() or "vox" in filename.lower() or "voice" in filename.lower():
            if "VOCALS" not in category_scores:
                category_scores["VOCALS"] = 0
            category_scores["VOCALS"] += 5.0  # Strong boost for vocal keywords
        
        # Evaluate each category with priority
        for category, score in category_scores.items():
            # Get priority from config (default to 0)
            priority = self.category_priority.get(category, 0)
            
            # Calculate combined score using both raw score and priority
            # Use priority as a multiplier for better differentiation
            combined_score = score * (1 + priority * 0.5)
            
            # Additional weight for specific categories to correct common misclassifications
            if category == "DRUMS" and any(kw in filename.lower() for kw in ['kick', 'snare', 'hat', 'clap', 'tom']):
                combined_score *= 1.5  # 50% boost for clear drum samples
                
            if category == "VOCALS" and any(kw in filename.lower() for kw in ['vocal', 'vox', 'voice']):
                combined_score *= 1.5  # 50% boost for clear vocal samples
                
            if category == "FX" and any(kw in filename.lower() for kw in ['fx', 'effect', 'riser', 'sweep']):
                combined_score *= 1.5  # 50% boost for clear fx samples
                
            if category == "BASS" and any(kw in filename.lower() for kw in ['bass', 'sub', '808']):
                combined_score *= 1.5  # 50% boost for clear bass samples
            
            # Prevent INSTRUMENTS from catching everything
            if category == "INSTRUMENTS":
                # If the file has strong indicators of another category, reduce INSTRUMENTS score
                if any(cat in category_scores for cat in ["DRUMS", "VOCALS", "FX", "BASS"]):
                    combined_score *= 0.7  # 30% reduction for INSTRUMENTS when other categories match
            
            if combined_score > best_score:
                best_score = combined_score
                best_category = category
        
        # If best score is too low, and no category detected but has audio, use audio features
        if best_score < 0.5 and best_category == "UNKNOWN":
            # Default to UNKNOWN/UNMATCHED_SAMPLES
            return "UNKNOWN"
        
        return best_category
        
     
    def determine_subcategory(self, category: str, base_name: str, folder_names: List[str], 
                           is_loop: bool, is_one_shot: bool) -> str:
        """Determine subcategory using the folder structure from patterns file"""
        # Get category data
        category_data = self.categories.get(category, {})
        
        # Get folder structure for this category from patterns file
        folder_structure = self.folder_structure.get(category, {})
        
        # Look for direct matches in subPatterns
        direct_matches = []
        if "subPatterns" in category_data and category in self.compiled_patterns['subcategories']:
            for subcat, pattern in self.compiled_patterns['subcategories'][category].items():
                if pattern.search(base_name) or any(pattern.search(folder) for folder in folder_names if folder):
                    direct_matches.append(subcat)
        
        # If we have direct matches, return the best one
        if direct_matches:
            # Prioritize the most specific patterns (those with more path segments)
            sorted_matches = sorted(direct_matches, key=lambda x: len(x.split('/')), reverse=True)
            return sorted_matches[0]
        
        # If no direct matches, determine the path using the folder structure
        if isinstance(folder_structure, list):
            # Simple list structure (like BASS or VOCALS)
            if "LOOP" in folder_structure and is_loop:
                return "LOOP"
            elif "ONE SHOT" in folder_structure and is_one_shot:
                return "ONE SHOT"
            elif folder_structure:
                return folder_structure[0]  # Return first option
        
        elif isinstance(folder_structure, dict):
            # Complex structure - determine best path based on content
            
            # First detect keywords in filename and folders
            keywords = set()
            for keyword in self._extract_keywords(base_name):
                keywords.add(keyword)
            for folder in folder_names:
                for keyword in self._extract_keywords(folder):
                    keywords.add(keyword)
                    
            # Check each first-level folder in structure
            for folder_name, subfolder in folder_structure.items():
                # Check if any keywords match this folder
                if any(self._match_keyword(folder_name, kw) for kw in keywords):
                    # Found matching folder
                    
                    # If it's a list (like ["LOOP", "ONE SHOT"])
                    if isinstance(subfolder, list):
                        if is_loop and "LOOP" in subfolder:
                            return f"{folder_name}/LOOP"
                        elif is_one_shot and "ONE SHOT" in subfolder:
                            return f"{folder_name}/ONE SHOT"
                        elif subfolder:
                            return f"{folder_name}/{subfolder[0]}"
                        else:
                            return folder_name
                            
                    # If it's a dict (deeper structure)
                    elif isinstance(subfolder, dict):
                        # For deeper structures, check keywords against subfolder names
                        for subfolder_name, subsubfolder in subfolder.items():
                            if any(self._match_keyword(subfolder_name, kw) for kw in keywords):
                                # Found matching subfolder
                                
                                # If it's a list (like ["LOOP", "ONE SHOT"])
                                if isinstance(subsubfolder, list):
                                    if is_loop and "LOOP" in subsubfolder:
                                        return f"{folder_name}/{subfolder_name}/LOOP"
                                    elif is_one_shot and "ONE SHOT" in subsubfolder:
                                        return f"{folder_name}/{subfolder_name}/ONE SHOT"
                                    elif subsubfolder:
                                        return f"{folder_name}/{subfolder_name}/{subsubfolder[0]}"
                                    else:
                                        return f"{folder_name}/{subfolder_name}"
                                else:
                                    return f"{folder_name}/{subfolder_name}"
                        
                        # If no subfolder matches, use the first subfolder
                        subfolder_names = list(subfolder.keys())
                        if subfolder_names:
                            first_subfolder = subfolder_names[0]
                            subsubfolder = subfolder[first_subfolder]
                            
                            if isinstance(subsubfolder, list):
                                if is_loop and "LOOP" in subsubfolder:
                                    return f"{folder_name}/{first_subfolder}/LOOP"
                                elif is_one_shot and "ONE SHOT" in subsubfolder:
                                    return f"{folder_name}/{first_subfolder}/ONE SHOT"
                                elif subsubfolder:
                                    return f"{folder_name}/{first_subfolder}/{subsubfolder[0]}"
                                else:
                                    return f"{folder_name}/{first_subfolder}"
                            else:
                                return f"{folder_name}/{first_subfolder}"
                    else:
                        return folder_name
            
            # Special cases based on category
            if category == "DRUMS":
                # Check for specific drum types in filename
                if "kick" in base_name.lower() or "bd" in base_name.lower() or "bass drum" in base_name.lower():
                    return "KICK/ONE SHOT" if is_one_shot else "KICK/LOOP"
                elif "snare" in base_name.lower():
                    return "SNARE/ONE SHOT" if is_one_shot else "SNARE/LOOP"
                elif "clap" in base_name.lower():
                    return "CLAP/ONE SHOT" if is_one_shot else "CLAP/LOOP"
                elif "hat" in base_name.lower() or "hh" in base_name.lower() or "h_h" in base_name.lower():
                    if "open" in base_name.lower():
                        return "OPEN HAT/ONE SHOT" if is_one_shot else "OPEN HAT/LOOP"
                    else:
                        return "CLOSED HAT/ONE SHOT" if is_one_shot else "CLOSED HAT/LOOP"
                elif "cymbal" in base_name.lower() or "crash" in base_name.lower() or "ride" in base_name.lower():
                    return "CRASH-RIDE/ONE SHOT" if is_one_shot else "CRASH-RIDE/LOOP"
                elif "tom" in base_name.lower():
                    return "PERCUSSION/TOM/ONE SHOT" if is_one_shot else "PERCUSSION/TOM/LOOP"
                
                # Check for LOOPS folder if it's a loop
                if "LOOPS" in folder_structure and is_loop:
                    return "LOOPS"
                # Default for drums
                return "KICK/ONE SHOT" if is_one_shot else "KICK/LOOP"
            
            elif category == "INSTRUMENTS":
                # Check for specific instrument types
                if "chord" in base_name.lower():
                    return "LOOP/CHORDS" if is_loop else "ONE SHOT/CHORDS"
                elif "pad" in base_name.lower():
                    return "LOOP/PADS" if is_loop else "ONE SHOT/SYNTH"
                elif "stab" in base_name.lower():
                    return "LOOP/STABS" if is_loop else "ONE SHOT/STABS"
                elif "piano" in base_name.lower() or "guitar" in base_name.lower() or "acoustic" in base_name.lower():
                    return "ONE SHOT/ACOUSTIC" if is_one_shot else "LOOP/SYNTH"
                
                # Default based on loop/one-shot
                if is_loop:
                    return "LOOP/SYNTH"
                elif is_one_shot:
                    return "ONE SHOT/SYNTH"
                else:
                    return "LOOP/SYNTH"  # Default fallback
            
            elif category == "FX":
                # Check for specific FX types
                if "ambient" in base_name.lower() or "atmos" in base_name.lower():
                    return "AMBIENT"
                elif "drone" in base_name.lower():
                    return "DRONE"
                elif "texture" in base_name.lower():
                    return "TEXTURE"
                
                # Default based on loop/one-shot
                if is_loop:
                    return "LOOP"
                else:
                    return "ONE SHOT"
            
            elif category == "BASS":
                return "LOOP" if is_loop else "ONE SHOT"
            
            elif category == "VOCALS":
                return "LOOP" if is_loop else "ONE SHOT"
        
        # Default for UNKNOWN
        if category == "UNKNOWN":
            return "UNMATCHED_SAMPLES"
            
        # Default empty subcategory for any other cases
        return ""

    def _extract_keywords(self, text):
        """Extract keywords from text by splitting on non-alphanumeric chars"""
        if not text:
            return []
        
        # Convert to lowercase and split by non-alphanumeric chars
        words = re.split(r'[^a-zA-Z0-9]', text.lower())
        
        # Filter out empty strings and single characters
        return [word for word in words if len(word) > 1]

    def _match_keyword(self, folder_name, keyword):
        """Check if keyword matches folder name (case insensitive)"""
        if not keyword or not folder_name:
            return False
            
        folder_lower = folder_name.lower()
        keyword_lower = keyword.lower()
        
        return (
            keyword_lower == folder_lower or
            keyword_lower in folder_lower.split() or
            folder_lower in keyword_lower or
            keyword_lower in folder_lower
        )