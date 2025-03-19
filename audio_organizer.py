#!/usr/bin/env python3
"""
Audio Sample Organizer
A tool to organize audio samples based on patterns and audio content analysis.

Usage:
    python audio_organizer.py [options]
    
Options:
    --config, -c   Path to config file
    --setup        Run the setup wizard
    --help, -h     Show this help message
    --no-monitor   Disable progress monitor
"""

import argparse
import logging
import sys
import time
import subprocess
import os
from pathlib import Path

# Import modules
from modules.processor import AudioFileProcessor
from modules.utils import setup_logging, load_config

def launch_monitor(no_monitor=False):
    """Launch the monitor script in a separate window"""
    if no_monitor:
        return None
        
    monitor_path = Path("monitor.py")
    if not monitor_path.exists():
        print(f"Monitor script not found at {monitor_path}")
        print("Please create the monitor script first.")
        return None
    
    # Start monitor in a new process
    python_executable = sys.executable  # Get the current Python executable
    
    try:
        # Use different methods based on platform
        if os.name == 'nt':  # Windows
            # Start a detached process with a new console window
            monitor_process = subprocess.Popen(
                [python_executable, str(monitor_path)],
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            print(f"Started monitor in a new window (PID: {monitor_process.pid})")
            return monitor_process
        else:  # Linux/Mac
            # For Unix-like systems, try different terminal emulators
            terminals = [
                # GNOME Terminal
                ['gnome-terminal', '--', python_executable, str(monitor_path)],
                # KDE Konsole
                ['konsole', '-e', f'{python_executable} {monitor_path}'],
                # XFCE Terminal
                ['xfce4-terminal', '-e', f'{python_executable} {monitor_path}'],
                # MATE Terminal
                ['mate-terminal', '-e', f'{python_executable} {monitor_path}'],
                # LXDE Terminal
                ['lxterminal', '-e', f'{python_executable} {monitor_path}'],
                # Xterm (fallback)
                ['xterm', '-e', f'{python_executable} {monitor_path}']
            ]
            
            for terminal_cmd in terminals:
                try:
                    monitor_process = subprocess.Popen(terminal_cmd)
                    print(f"Started monitor in a new terminal window ({terminal_cmd[0]})")
                    return monitor_process
                except (subprocess.SubprocessError, FileNotFoundError):
                    continue
            
            # If all terminal attempts failed, inform the user
            print("Could not automatically launch the monitor in a terminal window.")
            print(f"Please open a new terminal and run: {python_executable} {monitor_path}")
            return None
            
    except Exception as e:
        print(f"Error starting monitor: {e}")
        print(f"You can manually run the monitor in a separate terminal: {python_executable} {monitor_path}")
        return None
def count_output_files(output_dir):
    """
    Count all files in the output directory structure recursively,
    excluding logs and reports directories
    """
    count = 0
    for root, dirs, files in os.walk(output_dir):
        # Skip the 'logs' and 'reports' directories which contain metadata
        if 'logs' in root.split(os.sep) or 'reports' in root.split(os.sep):
            continue
        count += len(files)
    return count

# Then in the main() function, add this code after processing is complete
# and before printing the summary:

    # Count actual files in output directory
    print("\nVerifying output files...")
    actual_file_count = count_output_files(processor.dest_path)
        
    # Print summary
    print(f"\n=== Organization Complete ===")
    print(f"Total files: {stats['total_files']}")
    print(f"Processed: {stats['processed_files']}")
    print(f"Failed: {stats['failed_files']}")
    print(f"Files in output directory: {actual_file_count}")
        
    # Check if counts match
    if actual_file_count != stats['processed_files']:
        print(f"WARNING: Count mismatch! Processed files ({stats['processed_files']}) ≠ Output files ({actual_file_count})")
        diff = stats['processed_files'] - actual_file_count
        if diff > 0:
            print(f"Missing {diff} files in output directory.")
        else:
            print(f"Output directory has {abs(diff)} more files than processed count.")
    else:
        print("✓ File counts match correctly!")
            
    print(f"Processing time: {total_time:.2f} seconds")    

def main():
    """Main entry point for the Audio Sample Organizer"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Audio Sample Organizer')
    parser.add_argument('--config', '-c', type=str, help='Path to config file')
    parser.add_argument('--setup', action='store_true', help='Run setup wizard')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--no-monitor', action='store_true', help='Disable progress monitor')
    
    # Add cache-related arguments
    parser.add_argument('--nocache', action='store_true', help='Disable audio analysis caching')
    parser.add_argument('--cleancache', action='store_true', help='Clear the audio analysis cache before processing')
    parser.add_argument('--cachefile', type=str, help='Path to the cache file (default: config setting or ./cache/audio_analysis_cache.pkl)')
    
    args = parser.parse_args()
    
    # Run setup wizard if requested
    if args.setup:
        # Import setup module only when needed
        print("Running setup wizard...")
        import setup
        setup.setup_project()
        return
    
    # Load configuration
    config_path = Path(args.config) if args.config else None
    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"Error loading configuration: {e}")
        print("Run with --setup to create a new configuration or specify a valid config file.")
        sys.exit(1)
    
    # Apply cache-related command-line arguments
    if 'cache_settings' not in config:
        config['cache_settings'] = {}
        
    if args.nocache:
        config['cache_settings']['enable_cache'] = False
        
    if args.cachefile:
        config['cache_settings']['cache_file'] = args.cachefile
        
    # Launch the monitor in background
    monitor_process = launch_monitor(args.no_monitor)
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(log_level, config.get('log_file', 'audio_organizer.log'))
    
    # Initialize the processor
    processor = None
    try:
        processor = AudioFileProcessor(config)
        
        # Handle cache clearing if requested
        if args.cleancache and hasattr(processor, 'cache_manager') and processor.cache_manager:
            print("Clearing audio analysis cache...")
            processor.cache_manager.clear()
            logging.info("Cache cleared before processing")
        
        # Print startup info
        logging.info(f"Audio Sample Organizer")
        logging.info(f"Source directory: {processor.source_path}")
        logging.info(f"Output directory: {processor.dest_path}")
        
        # Process files
        start_time = time.time()
        try:
            stats = processor.process_files()
        except Exception as processing_error:
            logging.critical(f"Critical error during file processing: {processing_error}", exc_info=True)
            # Attempt to save partial results or do cleanup
            if processor and hasattr(processor, 'cache_manager') and processor.cache_manager:
                try:
                    logging.info("Attempting to save cache before exiting due to error")
                    processor.cache_manager.shutdown()
                except Exception as shutdown_error:
                    logging.error(f"Error during emergency cache shutdown: {shutdown_error}")
            raise

        total_time = time.time() - start_time
        
        # Print summary
        print(f"\n=== Organization Complete ===")
        print(f"Total files: {stats['total_files']}")
        print(f"Processed: {stats['processed_files']}")
        print(f"Failed: {stats['failed_files']}")
        print(f"Processing time: {total_time:.2f} seconds")
        
        if stats['processed_files'] > 0:
            avg_time_per_file = total_time / stats['processed_files']
            print(f"Average time per file: {avg_time_per_file:.4f} seconds")
            print(f"Files per second: {stats['processed_files'] / total_time:.2f}")
        
        # Print cache statistics if available
        if 'cache_stats' in stats:
            cache_stats = stats['cache_stats']
            print("\nCache Statistics:")
            if 'hit_ratio' in cache_stats:
                print(f"Cache hit ratio: {cache_stats['hit_ratio']:.2f}%")
            if 'entry_count' in cache_stats:
                print(f"Cached entries: {cache_stats['entry_count']}")
        
        print(f"\nReport available in {processor.dest_path / 'reports'}")
        
    except KeyboardInterrupt:
        print("\nOrganization interrupted by user")
        logging.info("Organization interrupted by user")
        # Ensure cache is saved on interrupt
        if processor and hasattr(processor, 'cache_manager') and processor.cache_manager:
            logging.info("Saving cache after interrupt...")
            processor.cache_manager.shutdown()
        sys.exit(0)
    except Exception as e:
        print(f"Unhandled error: {e}")
        logging.critical(f"Unhandled error: {e}", exc_info=True)
        
        # Additional diagnostics
        import traceback
        try:
            with open('error_diagnostics.log', 'w') as f:
                f.write("Detailed Error Traceback:\n")
                traceback.print_exc(file=f)
        except Exception as log_error:
            logging.error(f"Could not write error diagnostics: {log_error}")
        
        # Ensure cache is saved on error
        if processor and hasattr(processor, 'cache_manager') and processor.cache_manager:
            try:
                logging.info("Attempting to save cache after unhandled error")
                processor.cache_manager.shutdown()
            except Exception as shutdown_error:
                logging.error(f"Error during cache shutdown: {shutdown_error}")
        
        sys.exit(1)
    """Main entry point for the Audio Sample Organizer"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Audio Sample Organizer')
    parser.add_argument('--config', '-c', type=str, help='Path to config file')
    parser.add_argument('--setup', action='store_true', help='Run setup wizard')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--no-monitor', action='store_true', help='Disable progress monitor')
    
    # Add cache-related arguments
    parser.add_argument('--nocache', action='store_true', help='Disable audio analysis caching')
    parser.add_argument('--cleancache', action='store_true', help='Clear the audio analysis cache before processing')
    parser.add_argument('--cachefile', type=str, help='Path to the cache file (default: config setting or ./cache/audio_analysis_cache.pkl)')
    
    args = parser.parse_args()
    
    # Run setup wizard if requested
    if args.setup:
        # Import setup module only when needed
        print("Running setup wizard...")
        import setup
        setup.setup_project()
        return
    
    # Load configuration
    config_path = Path(args.config) if args.config else None
    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"Error loading configuration: {e}")
        print("Run with --setup to create a new configuration or specify a valid config file.")
        sys.exit(1)
    
    # Apply cache-related command-line arguments
    if not 'cache_settings' in config:
        config['cache_settings'] = {}
        
    if args.nocache:
        config['cache_settings']['enable_cache'] = False
        
    if args.cachefile:
        config['cache_settings']['cache_file'] = args.cachefile
        
    # Launch the monitor in background
    monitor_process = launch_monitor(args.no_monitor)
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(log_level, config.get('log_file', 'audio_organizer.log'))
    
    # Initialize the processor
    try:
        processor = AudioFileProcessor(config)
        
        # Handle cache clearing if requested
        if args.cleancache and hasattr(processor, 'cache_manager') and processor.cache_manager:
            print("Clearing audio analysis cache...")
            processor.cache_manager.clear()
            logging.info("Cache cleared before processing")
        
        # Print startup info
        logging.info(f"Audio Sample Organizer")
        logging.info(f"Source directory: {processor.source_path}")
        logging.info(f"Output directory: {processor.dest_path}")
        
        # Process files
        start_time = time.time()
        try:
            stats = processor.process_files()
        except Exception as processing_error:
            logging.critical(f"Critical error during file processing: {processing_error}", exc_info=True)
            # Attempt to save partial results or do cleanup
            if 'processor' in locals():
                try:
                    partial_stats = getattr(processor, 'stats', {})
                    logging.info(f"Partial processing stats: {partial_stats}")
                except Exception:
                    pass
            raise

        total_time = time.time() - start_time

        # Count actual files in output directory
        print("\nVerifying output files...")
        actual_file_count = count_output_files(processor.dest_path)
        
        # Print summary
        print(f"\n=== Organization Complete ===")
        print(f"Total files: {stats['total_files']}")
        print(f"Processed: {stats['processed_files']}")
        print(f"Failed: {stats['failed_files']}")
        print(f"Files in output directory: {actual_file_count}")
        
        # Check if counts match
        if actual_file_count != stats['processed_files']:
            print(f"WARNING: Count mismatch! Processed files ({stats['processed_files']}) ≠ Output files ({actual_file_count})")
            diff = stats['processed_files'] - actual_file_count
            if diff > 0:
                print(f"Missing {diff} files in output directory.")
            else:
                print(f"Output directory has {abs(diff)} more files than processed count.")
        else:
            print("✓ File counts match correctly!")
            
        print(f"Processing time: {total_time:.2f} seconds")

        if stats['processed_files'] > 0:
            avg_time_per_file = total_time / stats['processed_files']
            print(f"Average time per file: {avg_time_per_file:.4f} seconds")
            print(f"Files per second: {stats['processed_files'] / total_time:.2f}")
        
        # Print cache statistics if available
        if 'cache_stats' in stats:
            cache_stats = stats['cache_stats']
            print("\nCache Statistics:")
            if 'hit_ratio' in cache_stats:
                print(f"Cache hit ratio: {cache_stats['hit_ratio']:.2f}%")
            if 'entry_count' in cache_stats:
                print(f"Cached entries: {cache_stats['entry_count']}")
        
        print(f"\nReport available in {processor.dest_path / 'reports'}")
        
    except KeyboardInterrupt:
        print("\nOrganization interrupted by user")
        logging.info("Organization interrupted by user")
        # Ensure cache is saved on interrupt
        if hasattr(processor, 'cache_manager') and processor.cache_manager:
            processor.cache_manager.shutdown()
        sys.exit(0)
    except Exception as e:
        print(f"Unhandled error: {e}")
        logging.critical(f"Unhandled error: {e}", exc_info=True)
        
        # Additional diagnostics
        import traceback
        try:
            with open('error_diagnostics.log', 'w') as f:
                f.write("Detailed Error Traceback:\n")
                traceback.print_exc(file=f)
        except Exception as log_error:
            logging.error(f"Could not write error diagnostics: {log_error}")
        
        # Ensure cache is saved on error
        if processor and hasattr(processor, 'cache_manager') and processor.cache_manager:
            try:
                processor.cache_manager.shutdown()
            except Exception as shutdown_error:
                logging.error(f"Error during cache shutdown: {shutdown_error}")
        
        sys.exit(1)
        
    """Main entry point for the Audio Sample Organizer"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Audio Sample Organizer')
    parser.add_argument('--config', '-c', type=str, help='Path to config file')
    parser.add_argument('--setup', action='store_true', help='Run setup wizard')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--no-monitor', action='store_true', help='Disable progress monitor')
    args = parser.parse_args()
    
    # Run setup wizard if requested
    if args.setup:
        # Import setup module only when needed
        print("Running setup wizard...")
        import setup
        setup.setup_project()
        return
    
    # Load configuration
    config_path = Path(args.config) if args.config else None
    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"Error loading configuration: {e}")
        print("Run with --setup to create a new configuration or specify a valid config file.")
        sys.exit(1)
    
    # Launch the monitor in background
    monitor_process = launch_monitor(args.no_monitor)
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(log_level, config.get('log_file', 'audio_organizer.log'))
    
    # Initialize the processor
    try:
        processor = AudioFileProcessor(config)
        
        # Print startup info
        logging.info(f"Audio Sample Organizer")
        logging.info(f"Source directory: {processor.source_path}")
        logging.info(f"Output directory: {processor.dest_path}")
        
        # Process files
        start_time = time.time()
        stats = processor.process_files()
        total_time = time.time() - start_time
        
        # Print summary
        print(f"\n=== Organization Complete ===")
        print(f"Total files: {stats['total_files']}")
        print(f"Processed: {stats['processed_files']}")
        print(f"Failed: {stats['failed_files']}")
        print(f"Processing time: {total_time:.2f} seconds")
        
        if stats['processed_files'] > 0:
            avg_time_per_file = total_time / stats['processed_files']
            print(f"Average time per file: {avg_time_per_file:.4f} seconds")
            print(f"Files per second: {stats['processed_files'] / total_time:.2f}")
        
        print(f"Report available in {processor.dest_path / 'reports'}")
        
    except KeyboardInterrupt:
        print("\nOrganization interrupted by user")
        logging.info("Organization interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        logging.error(f"Error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()