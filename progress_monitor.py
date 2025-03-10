import os
from pathlib import Path
import time

def count_files(directory):
    """Count files in a directory and its subdirectories"""
    count = 0
    for root, dirs, files in os.walk(directory):
        count += len(files)
    return count

def main():
    """Monitor progress of audio file organization"""
    source_dir = "D:/Oscar/Documents/SOUNDS/SPLICEE"
    dest_dir = "organized_samples"
    
    # Initial count
    source_count = count_files(source_dir)
    print(f"Total source files: {source_count}")
    
    # Monitor loop
    while True:
        dest_count = count_files(dest_dir)
        if dest_count > 0:
            progress = (dest_count / source_count) * 100
            print(f"Progress: {dest_count} of {source_count} files processed ({progress:.1f}%)")
        else:
            print("Waiting for files to be processed...")
        
        # Check if complete
        if dest_count >= source_count:
            print("Process appears to be complete!")
            break
            
        time.sleep(5)  # Check every 5 seconds

if __name__ == "__main__":
    main()