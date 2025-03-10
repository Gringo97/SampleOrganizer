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
            
            # Show category breakdown
            if "category_counts" in status and status["category_counts"]:
                print("\nCategory breakdown:")
                for category, count in sorted(status["category_counts"].items(), 
                                             key=lambda x: x[1], reverse=True):
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