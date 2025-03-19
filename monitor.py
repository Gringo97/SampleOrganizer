#!/usr/bin/env python3
"""
Real-time Progress Monitor for Audio Sample Organizer
Reads the progress_status.json file created by the processor
"""

import os
import json
import time
from datetime import datetime
from pathlib import Path
import re

def format_time(seconds):
    """Format seconds into a readable time string"""
    if seconds < 60:
        return f"{seconds:.1f} seconds"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f} minutes"
    else:
        hours = seconds / 3600
        return f"{hours:.1f} hours"

def load_folder_structure():
    """Load folder structure from patterns.json to organize output"""
    try:
        patterns_path = Path("config/patterns.json")
        if patterns_path.exists():
            with open(patterns_path, 'r') as f:
                patterns = json.load(f)
                return patterns.get("folder_structure", {})
        return {}
    except Exception as e:
        print(f"Error loading folder structure: {e}")
        return {}

def organize_categories(category_counts, folder_structure):
    """Organize category counts according to folder structure"""
    if not folder_structure:
        # Just return sorted by count if no structure is available
        return sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
    
    # Create a mapping of category paths to their counts
    organized = []
    
    # Function to recursively process the folder structure
    def process_structure(structure, current_path=""):
        items = []
        if isinstance(structure, dict):
            # Process each subcategory
            for key, value in structure.items():
                new_path = f"{current_path}/{key}" if current_path else key
                # Add items for this subcategory
                items.extend(process_structure(value, new_path))
        elif isinstance(structure, list):
            # Process leaf nodes
            for item in structure:
                new_path = f"{current_path}/{item}" if current_path else item
                # Check if this path or any subpath exists in category_counts
                for cat, count in category_counts.items():
                    if cat.startswith(new_path) or (new_path.startswith("UNKNOWN") and "UNKNOWN" in cat):
                        items.append((cat, count))
        
        # Check if the current path itself exists in category_counts
        for cat, count in category_counts.items():
            if cat == current_path or (not current_path and cat.split('/')[0] == current_path):
                items.append((cat, count))
        
        return items
    
    # Start with the root structure
    for category, struct in folder_structure.items():
        organized.extend(process_structure(struct, category))
    
    # Add any remaining categories that weren't in the structure
    for cat, count in category_counts.items():
        if not any(cat == existing[0] for existing in organized):
            organized.append((cat, count))
    
    # Ensure we didn't lose any categories
    if len(organized) < len(category_counts):
        # Add any missing categories
        for cat, count in category_counts.items():
            if not any(cat == existing[0] for existing in organized):
                organized.append((cat, count))
    
    # Sort within each main category by count
    result = []
    main_categories = {}
    
    for cat, count in organized:
        main_cat = cat.split('/')[0]
        if main_cat not in main_categories:
            main_categories[main_cat] = []
        main_categories[main_cat].append((cat, count))
    
    # Process categories in the order defined in the folder structure
    ordered_categories = list(folder_structure.keys())
    # Add any missing categories to the end
    for cat in main_categories.keys():
        if cat not in ordered_categories:
            ordered_categories.append(cat)
    
    for main_cat in ordered_categories:
        if main_cat in main_categories:
            # Sort subcategories by count
            sorted_subcats = sorted(main_categories[main_cat], key=lambda x: x[1], reverse=True)
            result.extend(sorted_subcats)
    
    return result

def main():
    """Monitor progress using the status file"""
    # Default output directory
    output_dir = "organized_samples"
    status_file = Path(output_dir) / "progress_status.json"
    
    # Try to load config for custom output path
    config_path = Path("config/config.json")
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                output_dir = config.get("output_path", output_dir)
                status_file = Path(output_dir) / "progress_status.json"
        except Exception as e:
            print(f"Error loading config: {e}")
    
    # Load folder structure from patterns.json
    folder_structure = load_folder_structure()
    
    print(f"Monitoring organization progress from: {status_file}")
    print("Waiting for process to start...")
    
    # Clear screen function
    clear = lambda: os.system('cls' if os.name=='nt' else 'clear')
    
    # Wait for status file to appear
    while not status_file.exists():
        time.sleep(1)
    
    try:
        while True:
            if not status_file.exists():
                print("Status file not found. Process may have ended.")
                break
            
            try:
                with open(status_file, 'r') as f:
                    status = json.load(f)
            except json.JSONDecodeError:
                # File might be in the middle of being written
                time.sleep(0.5)
                continue
            
            # Clear screen and display progress
            clear()
            timestamp = datetime.fromisoformat(status["timestamp"])
            
            print(f"=== AUDIO SAMPLE ORGANIZER - REAL-TIME PROGRESS ===")
            print(f"Status as of: {timestamp.strftime('%H:%M:%S')}")
            print(f"Output directory: {output_dir}")
            
            total = status["total_files"]
            processed = status["processed_files"]
            failed = status["failed_files"]
            progress = (processed / total) * 100 if total > 0 else 0
            
            # Display progress bar
            bar_length = 40
            filled_length = int(bar_length * processed // total) if total > 0 else 0
            bar = '█' * filled_length + '░' * (bar_length - filled_length)
            
            print(f"\nProgress: [{bar}] {processed:,}/{total:,} ({progress:.1f}%)")
            print(f"Failed files: {failed}")
            print(f"Processing speed: {status['files_per_second']:.2f} files/second")
            print(f"Elapsed time: {format_time(status['elapsed_seconds'])}")
            
            if status['eta_seconds'] > 0:
                print(f"Estimated time remaining: {format_time(status['eta_seconds'])}")
            
            # Show category breakdown with improved organization
            if "category_counts" in status and status["category_counts"]:
                print("\nCategory breakdown:")
                organized_categories = organize_categories(status["category_counts"], folder_structure)
                
                for category, count in organized_categories:
                    percent = (count / processed) * 100 if processed > 0 else 0
                    print(f"  {category}: {count:,} files ({percent:.1f}%)")
            
            # Show recent errors
            if "recent_errors" in status and status["recent_errors"]:
                print("\nRecent errors:")
                for error in status["recent_errors"]:
                    print(f"  {error}")
            
            # Check if process is complete
            if status.get("is_complete", False):
                print("\nProcess is complete!")
                break
            
            time.sleep(2)  # Update every 2 seconds
    
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")

if __name__ == "__main__":
    main()