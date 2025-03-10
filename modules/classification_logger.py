"""
Classification logger for the Audio Sample Organizer
Logs detailed classification results for easy analysis
"""

import json
import logging
import csv
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

class ClassificationLogger:
    """Logs detailed classification results to various formats"""
    
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.logs_dir = output_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Log files
        self.json_log = self.logs_dir / f"classification_log_{self.timestamp}.json"
        self.csv_log = self.logs_dir / f"classification_log_{self.timestamp}.csv"
        self.text_log = self.logs_dir / f"classification_log_{self.timestamp}.txt"
        
        # Initialize log files
        self._init_logs()
        
        # Batch data for efficiency
        self.batch_size = 100
        self.current_batch = []
        
        logging.info(f"Classification logger initialized. Logs will be saved to {self.logs_dir}")
    
    def _init_logs(self):
        """Initialize log files with headers"""
        # Initialize JSON log with an empty array
        with open(self.json_log, 'w') as f:
            json.dump([], f)
        
        # Initialize CSV log with headers
        with open(self.csv_log, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Filename", "Category", "Subcategory", "Confidence",
                "Is Loop", "Is One Shot", "Matched Patterns"
            ])
        
        # Initialize text log with header
        with open(self.text_log, 'w') as f:
            f.write("=== Audio Sample Classification Log ===\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    
    def log_result(self, result: Dict[str, Any]):
        """Log a single classification result"""
        self.current_batch.append(result)
        
        # Write batch if it reaches the threshold
        if len(self.current_batch) >= self.batch_size:
            self._write_batch()
    
    def _write_batch(self):
        """Write the current batch of results to log files"""
        if not self.current_batch:
            return
        
        # Append to JSON log
        try:
            with open(self.json_log, 'r+') as f:
                data = json.load(f)
                data.extend(self.current_batch)
                f.seek(0)
                json.dump(data, f, indent=2)
        except Exception as e:
            logging.error(f"Error writing to JSON log: {e}")
        
        # Append to CSV log
        try:
            with open(self.csv_log, 'a', newline='') as f:
                writer = csv.writer(f)
                for result in self.current_batch:
                    filename = Path(result["file"]).name
                    writer.writerow([
                        filename,
                        result["category"],
                        result["subcategory"],
                        result["confidence"],
                        "Yes" if result["type"] == "LOOP" else "No",
                        "Yes" if result["type"] == "ONE SHOT" else "No",
                        ", ".join(result["matched_patterns"])
                    ])
        except Exception as e:
            logging.error(f"Error writing to CSV log: {e}")
        
        # Append to text log
        try:
            with open(self.text_log, 'a') as f:
                for result in self.current_batch:
                    filename = Path(result["file"]).name
                    f.write(f"File: {filename}\n")
                    f.write(f"  Category: {result['category']}\n")
                    f.write(f"  Subcategory: {result['subcategory']}\n")
                    f.write(f"  Confidence: {result['confidence']}\n")
                    f.write(f"  Type: {result['type']}\n")
                    f.write(f"  Pattern Matches: {', '.join(result['matched_patterns'])}\n")
                    
                    # Add audio features if available
                    if "audio_features" in result:
                        f.write("  Audio Features:\n")
                        for key, value in result["audio_features"].items():
                            f.write(f"    {key}: {value}\n")
                    
                    f.write("\n")
        except Exception as e:
            logging.error(f"Error writing to text log: {e}")
        
        # Clear the batch
        self.current_batch = []
    
    def generate_summary(self, stats: Dict[str, Any]) -> str:
        """Generate a summary of classification results"""
        # Flush any remaining batch items
        self._write_batch()
        
        summary_path = self.logs_dir / f"classification_summary_{self.timestamp}.txt"
        try:
            with open(summary_path, 'w') as f:
                f.write("=== AUDIO SAMPLE CLASSIFICATION SUMMARY ===\n\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                f.write(f"Total files processed: {stats['processed_files']}\n")
                f.write(f"Failed files: {stats['failed_files']}\n")
                f.write(f"Processing time: {stats['processing_time']:.2f} seconds\n\n")
                
                # Category distribution
                f.write("Category Distribution:\n")
                for category, count in sorted(stats['category_counts'].items()):
                    percentage = (count / stats['processed_files']) * 100 if stats['processed_files'] > 0 else 0
                    f.write(f"  {category}: {count} files ({percentage:.1f}%)\n")
                
                # Confidence statistics
                if stats.get('confidence_scores'):
                    avg_confidence = sum(stats['confidence_scores']) / len(stats['confidence_scores'])
                    f.write(f"\nAverage confidence: {avg_confidence:.2f}\n")
                
                # Cache statistics if available
                if 'cache_stats' in stats:
                    f.write("\nCache Performance:\n")
                    for key, value in stats['cache_stats'].items():
                        f.write(f"  {key}: {value}\n")
                
                # Error summary
                if stats.get('error_logs'):
                    f.write("\nTop Errors:\n")
                    error_count = {}
                    for error in stats['error_logs']:
                        error_type = error.split(':', 1)[0] if ':' in error else error
                        error_count[error_type] = error_count.get(error_type, 0) + 1
                    
                    for error_type, count in sorted(error_count.items(), key=lambda x: x[1], reverse=True)[:10]:
                        f.write(f"  {error_type}: {count} occurrences\n")
            
            return str(summary_path)
        except Exception as e:
            logging.error(f"Error generating summary: {e}")
            return ""
    
    def finalize(self, stats: Dict[str, Any]):
        """Finalize logging and generate summary"""
        summary_path = self.generate_summary(stats)
        
        # Print paths of log files for easy access
        print("\n=== CLASSIFICATION LOGS ===")
        print(f"Text log: {self.text_log}")
        print(f"CSV log: {self.csv_log}")
        print(f"JSON log: {self.json_log}")
        if summary_path:
            print(f"Summary: {summary_path}")