"""
File Processing module for the Audio Sample Organizer
Handles file operations and organization
"""

import concurrent.futures
import json
import logging
import os
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Tuple

# Import required modules
from .analyzer import AudioAnalyzer, AudioFeatures
from .classifier import PatternMatcher, ClassificationResult
from .utils import ensure_dir, check_audio_libraries, sanitize_filename
# Add this import at the top of processor.py
from .classification_logger import ClassificationLogger



# Try to import visualization dependencies
try:
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    import matplotlib.pyplot as plt
    import seaborn as sns
    VISUALIZATION_AVAILABLE = True
except ImportError:
    VISUALIZATION_AVAILABLE = False
    logging.warning("matplotlib/seaborn not available - visualization disabled")

# Try importing audio processing library
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    logging.warning("pydub not available - basic audio validation will be used")

class AudioFileProcessor:
    """Handles audio file processing and organization"""
    def __init__(self, config: Dict):
        self.config = config
         # Extract paths from config
        self.source_path = Path(config.get('source_path', '.'))
        self.dest_path = Path(config.get('output_path', './organized_samples'))

        # Create destination directory
        ensure_dir(self.dest_path)
    
        self.patterns_file = Path(config.get('patterns_file', './config/patterns.json'))
    
        # Initialize pattern matcher
        self.pattern_matcher = PatternMatcher(self.patterns_file)

        # Create the folder structure
        self._create_initial_folder_structure()
    
        # Initialize classifier logger - Now moved after self.dest_path is defined
        self.logger = ClassificationLogger(self.dest_path)
    
        # Initialize audio analyzer if enabled
        self.audio_analyzer = None
        if config.get('enable_audio_analysis', False) and check_audio_libraries():
            self.audio_analyzer = AudioAnalyzer(config)
        
        # Initialize caches for file format detection
        self.audio_extensions = set(config.get('audio_extensions', 
                                   ['.wav', '.mp3', '.aif', '.aiff', '.ogg', '.flac']))
        self.non_audio_extensions = set(config.get('ignore_patterns', 
                                      ['.asd', '.ds_store', '.ini', '.txt', '.md']))
        
        # Thread safety
        self._stats_lock = threading.Lock()
        
        # Initialize statistics
        self.stats = {
            'total_files': 0,
            'processed_files': 0,
            'failed_files': 0,
            'category_counts': {},
            'confidence_scores': [],
            'error_logs': [],
            'match_details': [],
            'category_conflicts': [],
            'processing_time': 0.0,
            'start_time': time.time()
        }
        
        logging.info(f"Initialized AudioFileProcessor with source: {self.source_path}")
        logging.info(f"Output directory: {self.dest_path}")

    def _create_initial_folder_structure(self):
        """Create the initial folder structure from patterns file"""
        with open(self.patterns_file) as f:
            patterns = json.load(f)
    
        # Get folder structure from patterns file
        folder_structure = patterns.get("folder_structure", {})
    
        # Function to recursively build paths
        def build_paths(structure, current_path=""):
            paths = []
            if isinstance(structure, dict):
                for key, value in structure.items():
                    new_path = f"{current_path}/{key}" if current_path else key
                    if value:  # If it has children
                        paths.extend(build_paths(value, new_path))
                    else:
                        paths.append(new_path)
            elif isinstance(structure, list):
                if structure:  # If the list has items
                    for item in structure:
                        new_path = f"{current_path}/{item}" if current_path else item
                        paths.append(new_path)
                else:
                    # If the list is empty, just add the current path
                    paths.append(current_path)
            return paths
    
        # Build all paths
        folder_paths = build_paths(folder_structure)
    
        # Add reports directory
        folder_paths.append("reports")
    
        # Create all directories
        for folder_path in folder_paths:
            full_path = self.dest_path / folder_path
            full_path.mkdir(parents=True, exist_ok=True)
    
        logging.info(f"Created folder structure with {len(folder_paths)} directories")

    def process_files(self) -> Dict:
        """Process all audio files in the source directory"""
        start_time = time.time()
        
        try:
            # Get all files recursively
            all_files = list(self._get_files())
            valid_files = [f for f in all_files if self._is_valid_file(f)]
            
            self.stats['total_files'] = len(valid_files)
            logging.info(f"Found {self.stats['total_files']} files to process")
            
            # Process files in parallel if enabled
            max_workers = self.config.get('threads', os.cpu_count())
            
            if max_workers > 1 and self.stats['total_files'] > 10:
                logging.info(f"Using {max_workers} threads for parallel processing")
                self._process_files_parallel(valid_files, max_workers)
            else:
                logging.info("Using single-threaded processing")
                self._process_files_sequential(valid_files)
            
            # Generate report
            if self.config.get('generate_report', True):
                self._generate_report()
            
            # Update final processing time
            self.stats['processing_time'] = time.time() - start_time
            
            # Finalize logger and generate summary
            self.logger.finalize(self.stats)
            
            return self.stats
            
        except Exception as e:
            logging.error(f"Error during file processing: {str(e)}", exc_info=True)
            raise
    
    def _get_files(self) -> List[Path]:
        """Get all files from source directory, respecting config options"""
        if self.config.get('process_subfolders', True):
            return list(self.source_path.rglob('*'))
        else:
            return list(self.source_path.glob('*'))
    
    def _is_valid_file(self, file_path: Path) -> bool:
        """Check if a file should be processed"""
        # Skip directories
        if not file_path.is_file():
            return False
            
        # Skip hidden files
        if file_path.name.startswith('.'):
            return False
            
        # Skip files in ignore patterns
        if file_path.suffix.lower() in self.non_audio_extensions:
            return False
            
        # Check if it's a known audio extension
        if file_path.suffix.lower() in self.audio_extensions:
            return True
            
        # For unknown types, attempt more thorough check
        return self._is_valid_audio(file_path)
    
    def _is_valid_audio(self, file_path: Path) -> bool:
        """Check if file is a valid audio file"""
        # Skip .asd files and other non-audio files
        if file_path.suffix.lower() in self.non_audio_extensions:
            return False
            
        # For unknown formats, try pydub if available
        if PYDUB_AVAILABLE:
            try:
                # Just open the file to check if it's valid
                AudioSegment.from_file(str(file_path))
                # Cache this extension for future checks
                self.audio_extensions.add(file_path.suffix.lower())
                return True
            except Exception as e:
                # Only log warnings for extensions we haven't seen before
                if file_path.suffix.lower() not in self.non_audio_extensions:
                    logging.warning(f"Invalid audio file: {file_path}. Error: {str(e)}")
                    self.non_audio_extensions.add(file_path.suffix.lower())
                return False
        else:
            # Without pydub, just check common extensions
            return file_path.suffix.lower() in ['.wav', '.mp3', '.aif', '.aiff', '.ogg', '.flac']
    
    def _process_files_parallel(self, files: List[Path], max_workers: int):
        """Process files in parallel using ThreadPoolExecutor"""
        total_files = len(files)
        last_progress_time = time.time()
        progress_interval = 2  # Update progress every 2 seconds
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self._process_single_file, file_path): file_path for file_path in files}
            
            # Process completed futures
            processed_count = 0
            for future in concurrent.futures.as_completed(futures):
                file_path = futures[future]
                try:
                    result = future.result()
                    if result:
                        processed_count += 1
                        
                        # Show progress in real-time to the console
                        current_time = time.time()
                        if current_time - last_progress_time >= progress_interval or processed_count == total_files:
                            elapsed = current_time - self.stats['start_time']
                            files_per_second = processed_count / elapsed if elapsed > 0 else 0
                            percent_complete = (processed_count / total_files) * 100
                            
                            # Calculate estimated time remaining
                            if files_per_second > 0:
                                remaining_files = total_files - processed_count
                                eta_seconds = remaining_files / files_per_second
                                eta_str = self._format_time(eta_seconds)
                            else:
                                eta_str = "calculating..."
                            
                            # Create progress bar
                            bar_length = 30
                            filled_length = int(bar_length * processed_count // total_files)
                            bar = '█' * filled_length + '░' * (bar_length - filled_length)
                            
                            # Clear line and print progress
                            print(f"\rProgress: [{bar}] {processed_count}/{total_files} ({percent_complete:.1f}%) | "
                                  f"Speed: {files_per_second:.2f} files/sec | ETA: {eta_str}", end='', flush=True)
                            
                            last_progress_time = current_time
                            
                            # Also log to file but less frequently
                            if processed_count % 100 == 0 or processed_count == total_files:
                                logging.info(f"Processed {processed_count} of {total_files} files ({percent_complete:.1f}%)")
                            # Update progress status file
                            self._update_progress_status()
                        
                except Exception as e:
                    logging.error(f"Error processing {file_path}: {str(e)}")
                    with self._stats_lock:
                        self.stats['failed_files'] += 1
                        self.stats['error_logs'].append(str(e))
            
            # Final newline after progress bar
            print()
    
    def _process_files_sequential(self, files: List[Path]):
        """Process files sequentially"""
        total_files = len(files)
        for index, file_path in enumerate(files):
            try:
                self._process_single_file(file_path)
                
                # Log progress periodically
                if (index + 1) % 100 == 0 or (index + 1) == total_files:
                    elapsed = time.time() - self.stats['start_time']
                    files_per_second = (index + 1) / elapsed if elapsed > 0 else 0
                    logging.info(f"Processed {index + 1} of {total_files} files ({files_per_second:.2f} files/sec)")
            except Exception as e:
                logging.error(f"Error processing {file_path}: {str(e)}")
                self.stats['failed_files'] += 1
                self.stats['error_logs'].append(str(e))
    
    def _process_single_file(self, file_path: Path) -> bool:
        """Process a single file"""
        try:
            # Classify file
            result = self._classify_file(file_path)
            
            # Copy file to new location
            self._copy_file(file_path, result)
            
            # Update statistics in a thread-safe way
            with self._stats_lock:
                self.stats['processed_files'] += 1
                category_key = f"{result.category}/{result.subcategory}" if result.subcategory else result.category
                self.stats['category_counts'][category_key] = self.stats['category_counts'].get(category_key, 0) + 1
                self.stats['confidence_scores'].append(result.confidence)
                self.stats['match_details'].append(result.to_dict())
                # In the _process_single_file method, add this after updating statistics:
                # Log the classification result
                self.logger.log_result(result.to_dict())
            return True
            
        except Exception as e:
            logging.error(f"Error processing {file_path}: {str(e)}")
            with self._stats_lock:
                self.stats['failed_files'] += 1
                self.stats['error_logs'].append(f"{file_path}: {str(e)}")
            return False
    
    # Update the _classify_file method in AudioFileProcessor class
    def _classify_file(self, file_path: Path) -> ClassificationResult:
        """Classify file using improved pattern matching and audio analysis"""
        # Extract base name and folder paths for matching
        base_name = file_path.stem.lower()
        folder_path = str(file_path.relative_to(self.source_path).parent).lower()
        folder_names = [part.lower() for part in file_path.relative_to(self.source_path).parent.parts]
        
        # Analyze audio if analyzer is available
        audio_features = None
        if self.audio_analyzer:
            audio_features = self.audio_analyzer.analyze_file(file_path)
        
        # Determine if this is a loop or one-shot
        is_loop = False
        is_one_shot = False
        
        # First check using pattern matching
        pattern_loop, pattern_oneshot = self.pattern_matcher.check_loop_or_oneshot(base_name, folder_names)
        
        # Then check using audio analysis if available
        audio_loop, audio_oneshot = False, False
        if audio_features:
            audio_loop, audio_oneshot = self.audio_analyzer.detect_loop_oneshot(audio_features)
        
        # Combine results, prioritizing pattern matching for loop/oneshot detection
        # This change gives pattern matching higher priority than audio analysis
        if pattern_loop or pattern_oneshot:
            is_loop = pattern_loop
            is_one_shot = pattern_oneshot
        elif audio_features:
            is_loop = audio_loop
            is_one_shot = audio_oneshot
        
        # If both or neither are detected, use pattern matching as fallback
        if is_loop == is_one_shot:
            is_loop = pattern_loop
            is_one_shot = pattern_oneshot
        
        # Collect all potential category matches with scores
        category_scores = {}
        
        # 1. Check filename for category matches
        filename_matches = self.pattern_matcher.check_patterns(base_name, "filename")
        for category, score in filename_matches.items():
            if category not in category_scores:
                category_scores[category] = 0
            category_scores[category] += score
        
        # 2. Check folder names for category matches (higher weight)
        for folder in folder_names:
            folder_matches = self.pattern_matcher.check_patterns(folder, "folder")
            for category, score in folder_matches.items():
                if category not in category_scores:
                    category_scores[category] = 0
                category_scores[category] += score * 1.5  # Higher weight for folder matches
        
        # If no matches, default to UNKNOWN
        if not category_scores:
            return ClassificationResult(
                original_path=file_path,
                category="UNKNOWN",
                subcategory="UNMATCHED_SAMPLES",
                confidence=0.0,
                matched_patterns=[],
                is_loop=is_loop,
                is_one_shot=is_one_shot,
                audio_features=audio_features
            )
        
        # Determine best category based on scores, priorities, and additional checks
        best_category = self.pattern_matcher.get_best_category(category_scores, base_name, folder_names)
        
        # Calculate confidence score
        max_score = max(category_scores.values()) if category_scores else 0
        confidence = min(1.0, max_score / 5.0)  # Normalize confidence
        
        # Collect all pattern matches for debugging
        pattern_matches = []
        for category, score in category_scores.items():
            pattern_matches.append(f"{category}: {score:.2f}")
        
        # Determine subcategory
        subcategory = self.pattern_matcher.determine_subcategory(
            best_category, base_name, folder_names, is_loop, is_one_shot
        )
        
        return ClassificationResult(
            original_path=file_path,
            category=best_category,
            subcategory=subcategory,
            confidence=confidence,
            matched_patterns=pattern_matches,
            is_loop=is_loop,
            is_one_shot=is_one_shot,
            audio_features=audio_features
        )
    def _copy_file(self, source_path: Path, result: ClassificationResult):
        """Copy file to destination based on classification result"""
        # Determine destination path
        dest_dir = self._get_destination_directory(result.category, result.subcategory)
        
        # Create destination directory if it doesn't exist
        ensure_dir(dest_dir)
        
        # Destination file path
        dest_file = dest_dir / source_path.name
        
        # Handle filename conflicts
        if dest_file.exists() and not self.config.get('overwrite_existing', False):
            base = dest_file.stem
            suffix = dest_file.suffix
            counter = 1
            while dest_file.exists():
                dest_file = dest_dir / f"{base}_{counter}{suffix}"
                counter += 1
        
        # Copy or move the file
        if self.config.get('move_files', False):
            shutil.move(source_path, dest_file)
            logging.debug(f"Moved {source_path} to {dest_file}")
        else:
            shutil.copy2(source_path, dest_file)
            logging.debug(f"Copied {source_path} to {dest_file}")
    
    def _get_destination_directory(self, category: str, subcategory: str) -> Path:
        """Determine destination directory based on category and subcategory"""
        # Start with category directory
        dest_dir = self.dest_path / category
        
        # If no subcategory, that's the destination
        if not subcategory:
            return dest_dir
            
        # Handle subcategory with path components
        if '/' in subcategory:
            subcat_parts = subcategory.split('/')
            for part in subcat_parts:
                dest_dir = dest_dir / part
        else:
            dest_dir = dest_dir / subcategory
        
        return dest_dir
    
    def _generate_report(self):
        """Generate detailed report with visualizations"""
        try:
            # Create report directory
            report_dir = self.dest_path / "reports"
            ensure_dir(report_dir)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Generate text report
            self._generate_text_report(report_dir, timestamp)
            
            # Generate visualizations if available
            if VISUALIZATION_AVAILABLE:
                self._generate_visualizations(report_dir, timestamp)
            
            logging.info(f"Report generated at {report_dir}")
            
        except Exception as e:
            logging.error(f"Error generating report: {str(e)}")
    
    def _generate_text_report(self, report_dir: Path, timestamp: str):
        """Generate text report"""
        report_path = report_dir / f'organization_report_{timestamp}.txt'
        
        with open(report_path, 'w') as f:
            f.write("=== Audio Sample Organization Report ===\n\n")
            f.write(f"Total files processed: {self.stats['processed_files']}\n")
            f.write(f"Failed files: {self.stats['failed_files']}\n")
            f.write(f"Processing time: {self.stats['processing_time']:.2f} seconds\n\n")
            
            f.write("Category Distribution:\n")
            for category, count in sorted(self.stats['category_counts'].items()):
                f.write(f"{category}: {count} files\n")
                
            f.write("\nConfidence Statistics:\n")
            if self.stats['confidence_scores']:
                avg_confidence = sum(self.stats['confidence_scores']) / len(self.stats['confidence_scores'])
                f.write(f"Average pattern matching confidence: {avg_confidence:.2f}\n")
            
            # Add error logs section
            if self.stats['error_logs']:
                f.write("\nErrors encountered:\n")
                # Limit to 50 errors to avoid huge reports
                for error in self.stats['error_logs'][:50]:
                    f.write(f"- {error}\n")
                
                if len(self.stats['error_logs']) > 50:
                    f.write(f"... and {len(self.stats['error_logs']) - 50} more errors\n")
    
    def _generate_visualizations(self, report_dir: Path, timestamp: str):
        """Generate visualization charts"""
        if not self.stats['category_counts']:
            logging.warning("No data to generate visualizations")
            return
            
        try:
            # 1. Generate category distribution plot
            plt.figure(figsize=(15, 8))
            categories = list(self.stats['category_counts'].keys())
            counts = list(self.stats['category_counts'].values())
            
            # Sort by main category first, then by count
            sorted_data = sorted(zip(categories, counts), key=lambda x: (x[0].split('/')[0], -x[1]))
            categories, counts = zip(*sorted_data) if sorted_data else ([], [])
            
            plt.bar(range(len(categories)), counts)
            plt.xticks(range(len(categories)), categories, rotation=90, ha='right')
            plt.title('Audio Samples Distribution by Category')
            plt.xlabel('Category')
            plt.ylabel('Number of Files')
            plt.tight_layout()
            plt.savefig(report_dir / f'category_distribution_{timestamp}.png')
            plt.close()
            
            # 2. Generate confidence distribution plot
            if self.stats['confidence_scores']:
                plt.figure(figsize=(10, 6))
                sns.histplot(self.stats['confidence_scores'], bins=20)
                plt.title('Pattern Matching Confidence Distribution')
                plt.xlabel('Confidence Score')
                plt.ylabel('Count')
                plt.tight_layout()
                plt.savefig(report_dir / f'confidence_distribution_{timestamp}.png')
                plt.close()
            
            # 3. Generate category breakdown pie chart
            plt.figure(figsize=(12, 12))
            
            # Group by main category
            main_categories = {}
            for cat, count in self.stats['category_counts'].items():
                main_cat = cat.split('/')[0]
                main_categories[main_cat] = main_categories.get(main_cat, 0) + count
            
            labels = list(main_categories.keys())
            sizes = list(main_categories.values())
            
            # Use a colormap
            colors = plt.cm.tab10(range(len(labels)))
            
            plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=140, shadow=True)
            plt.axis('equal')
            plt.title('Distribution by Main Category')
            plt.savefig(report_dir / f'category_pie_chart_{timestamp}.png')
            plt.close()
            
        except Exception as e:
            logging.error(f"Error generating visualizations: {str(e)}")
    def _format_time(self, seconds):
        """Format seconds into a readable time string"""
        if seconds < 60:
            return f"{seconds:.1f} seconds"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f} minutes"
        else:
            hours = seconds / 3600
            return f"{hours:.1f} hours"
    
    def _process_files_sequential(self, files: List[Path]):
        """Process files sequentially with real-time progress display"""
        total_files = len(files)
        last_progress_time = time.time()
        progress_interval = 1  # Update progress every second
        
        for index, file_path in enumerate(files):
            try:
                self._process_single_file(file_path)
                
                # Show progress in real-time
                current_time = time.time()
                if current_time - last_progress_time >= progress_interval or (index + 1) == total_files:
                    elapsed = current_time - self.stats['start_time']
                    files_per_second = (index + 1) / elapsed if elapsed > 0 else 0
                    percent_complete = ((index + 1) / total_files) * 100
                    
                    # Calculate estimated time remaining
                    if files_per_second > 0:
                        remaining_files = total_files - (index + 1)
                        eta_seconds = remaining_files / files_per_second
                        eta_str = self._format_time(eta_seconds)
                    else:
                        eta_str = "calculating..."
                    
                    # Create progress bar
                    bar_length = 30
                    filled_length = int(bar_length * (index + 1) // total_files)
                    bar = '█' * filled_length + '░' * (bar_length - filled_length)
                    
                    # Clear line and print progress
                    print(f"\rProgress: [{bar}] {index + 1}/{total_files} ({percent_complete:.1f}%) | "
                          f"Speed: {files_per_second:.2f} files/sec | ETA: {eta_str}", end='', flush=True)
                    
                    last_progress_time = current_time
                    
                    # Also log to file but less frequently
                    if (index + 1) % 100 == 0 or (index + 1) == total_files:
                        logging.info(f"Processed {index + 1} of {total_files} files ({percent_complete:.1f}%)")
                    # Update progress status file
                    self._update_progress_status()
            
            except Exception as e:
                logging.error(f"Error processing {file_path}: {str(e)}")
                self.stats['failed_files'] += 1
                self.stats['error_logs'].append(str(e))
        
        # Final newline after progress bar
        print()

    def _update_progress_status(self):
        """Write current progress to a status file"""
        status_file = self.dest_path / "progress_status.json"

        # Calculate elapsed time and speed
        elapsed = time.time() - self.stats['start_time']
        files_per_second = self.stats['processed_files'] / elapsed if elapsed > 0 else 0

        # Calculate estimated time remaining
        if files_per_second > 0 and self.stats['processed_files'] < self.stats['total_files']:
            remaining_files = self.stats['total_files'] - self.stats['processed_files']
            eta_seconds = remaining_files / files_per_second
        else:
            eta_seconds = 0

        # Prepare status data
        status = {
            "timestamp": datetime.now().isoformat(),
            "total_files": self.stats['total_files'],
            "processed_files": self.stats['processed_files'],
            "failed_files": self.stats['failed_files'],
            "elapsed_seconds": elapsed,
            "files_per_second": files_per_second,
            "eta_seconds": eta_seconds,
            "category_counts": self.stats['category_counts'],
            "is_complete": self.stats['processed_files'] >= self.stats['total_files'],
            "recent_errors": self.stats['error_logs'][-5:] if self.stats['error_logs'] else []
        }

        # Write to file
        with open(status_file, 'w') as f:
            json.dump(status, f, indent=2)

