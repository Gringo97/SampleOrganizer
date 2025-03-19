#!/usr/bin/env python3
"""
Audio Sample Organizer Setup Wizard
Interactive setup for the Audio Sample Organizer

Usage:
    python setup.py [options]
    
Options:
    --source, -s          Source directory
    --output, -o          Output directory
    --config, -c          Config directory
    --interactive, -i     Run in interactive mode
    --verbose, -v         Enable verbose logging  
    --clean               Clean output directory
    --threads, -t         Number of threads (0 = auto)
"""

import argparse
import json
import logging
import os
import re
import shutil
import sys
from pathlib import Path

# Global variable for interactive mode
interactive_mode = False

def setup_project():
    """Set up the project structure with command-line arguments and configuration validation"""
    global interactive_mode
    
    parser = argparse.ArgumentParser(description='Audio Sample Organizer Setup')
    parser.add_argument('--source', '-s', type=str, help='Source directory containing audio samples')
    parser.add_argument('--output', '-o', type=str, help='Output directory for organized samples')
    parser.add_argument('--config', '-c', type=str, help='Path to config directory')
    parser.add_argument('--interactive', '-i', action='store_true', help='Run in interactive mode')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--clean', action='store_true', help='Clean output directory before setup')
    parser.add_argument('--threads', '-t', type=int, default=0, 
                      help='Number of threads to use (0 = auto-detect)')
    
    args = parser.parse_args()
    
    # Set interactive mode based on args
    interactive_mode = args.interactive
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('audio_organizer_setup.log'),
            logging.StreamHandler()
        ]
    )
    
    # Get current directory
    current_dir = Path.cwd()
    
    # Print welcome message
    if args.interactive or not args.source:
        print_welcome_message()
    
    # Handle source directory
    source_path = Path(args.source) if args.source else None
    if not source_path and (args.interactive or not args.source):
        # Ask user for source
        source_path = get_source_path_interactive()
    
    if not source_path.exists():
        logging.error(f"Source path does not exist: {source_path}")
        print(f"Error: Source path does not exist: {source_path}")
        sys.exit(1)
    
    logging.info(f"Using source directory: {source_path}")
    
    # Handle output directory
    output_dir = None
    if args.output:
        output_dir = Path(args.output)
    elif args.interactive:
        output_dir = get_output_path_interactive(current_dir)
    else:
        output_dir = current_dir / "organized_samples"
    
    # Clean output directory if requested
    if args.clean and output_dir.exists():
        logging.warning(f"Cleaning output directory: {output_dir}")
        shutil.rmtree(output_dir)
    
    # Create necessary directories
    config_dir = current_dir / "config"
    config_dir.mkdir(exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create modules directory if it doesn't exist
    modules_dir = current_dir / "modules"
    if not modules_dir.exists():
        modules_dir.mkdir()
        # Create empty __init__.py to make it a package
        with open(modules_dir / "__init__.py", "w") as f:
            f.write("# Audio Organizer modules package\n")
    
    # Handle patterns file
    patterns_file = config_dir / "patterns.json"
    
    # If patterns file doesn't exist, create from template
    if not patterns_file.exists():
        # Check if we have a patterns.json in the current directory
        local_patterns = current_dir / "patterns.json"
        if local_patterns.exists():
            shutil.copy(local_patterns, patterns_file)
            logging.info(f"Copied patterns from {local_patterns} to {patterns_file}")
        else:
            # Create a default patterns file or find one interactively
            if args.interactive:
                patterns_file = get_patterns_file_interactive(patterns_file)
            else:
                create_default_patterns_file(patterns_file)
    
    # Validate patterns file
    validate_patterns_file(patterns_file)
    
    # Create category directories from patterns
    create_category_directories(patterns_file, output_dir)
    
    # Get audio analysis preferences
    enable_audio_analysis = False
    if args.interactive:
        enable_audio_analysis = get_audio_analysis_preference()
    
    # Create config file for the organizer
    create_config_file(config_dir, source_path, output_dir, patterns_file, 
                      args.threads, enable_audio_analysis)
    
    print("\n=== Setup complete! ===")
    print(f"Source directory: {source_path}")
    print(f"Output directory: {output_dir}")
    print(f"Patterns file: {patterns_file}")
    print(f"Config file: {config_dir / 'config.json'}")
    print("\nRun the organizer with: python audio_organizer.py")

def print_welcome_message():
    """Print welcome message for interactive setup"""
    print("\n" + "="*60)
    print("        AUDIO SAMPLE ORGANIZER - INTERACTIVE SETUP")
    print("="*60)
    print("\nThis wizard will help you set up the Audio Sample Organizer.")
    print("You'll need to provide information about your audio files location,")
    print("where you want organized files to be stored, and some preferences.\n")

def get_source_path_interactive():
    """Ask user for source path if not provided"""
    print("\n=== AUDIO SOURCE DIRECTORY ===")
    print("Please enter the full path to your audio samples directory.")
    print("This is where your unorganized audio files are currently stored.")
    
    while True:
        path_str = input("\nSource directory: ")
        path = Path(path_str)
        if path.exists():
            return path
        print(f"Error: Path '{path}' does not exist. Please enter a valid path.")

def get_output_path_interactive(current_dir):
    """Ask user for output path interactively"""
    print("\n=== OUTPUT DIRECTORY ===")
    print("Where would you like the organized audio files to be stored?")
    default_path = current_dir / "organized_samples"
    
    print(f"Default: {default_path}")
    path_str = input("Output directory (press Enter for default): ")
    
    if not path_str.strip():
        return default_path
    
    return Path(path_str)

def get_patterns_file_interactive(default_path):
    """Get patterns file interactively"""
    print("\n=== PATTERN CONFIGURATION ===")
    print("The patterns file defines how audio files are categorized.")
    print("You can use the default configuration or provide your own.")
    
    choice = input("Use default patterns? (Y/n): ").strip().lower()
    
    if choice == 'n':
        print("\nPlease enter the path to your custom patterns file:")
        while True:
            path_str = input("Patterns file path: ")
            path = Path(path_str)
            if path.exists():
                # Copy file to config directory
                shutil.copy(path, default_path)
                print(f"Copied patterns from {path} to {default_path}")
                return default_path
            print(f"Error: File '{path}' does not exist. Please enter a valid path.")
    
    # Create default patterns file
    create_default_patterns_file(default_path)
    return default_path

def get_audio_analysis_preference():
    """Ask if user wants to enable audio analysis"""
    try:
        import librosa
        audio_analysis_available = True
    except ImportError:
        audio_analysis_available = False
    
    if not audio_analysis_available:
        print("\n=== AUDIO ANALYSIS ===")
        print("Advanced audio analysis requires the librosa library, which is not installed.")
        print("Without this, classification will be based only on filenames and folder structure.")
        print("To enable audio analysis, install librosa: pip install librosa")
        return False
    
    print("\n=== AUDIO ANALYSIS ===")
    print("The organizer can analyze audio content to improve classification.")
    print("This uses more processing power but can be more accurate.")
    
    choice = input("Enable audio content analysis? (Y/n): ").strip().lower()
    return choice != 'n'

def create_default_patterns_file(patterns_file):
    """Create a default patterns file if none exists"""
    default_patterns = {
        "pattern_config": {
            "wb": "(?:^|[_\\s-]|(?<=[a-z])(?=[A-Z])|(?<=[0-9])(?=[a-zA-Z]))",
            "we": "(?:[_\\s-]|(?<=[A-Z])(?=[a-z])|$)",
            "case_insensitive": "(?i)"
        },
        "base_patterns": {
            "LOOP": "loop|loops|phrase|phrases|groove|riff|adlib",
            "ONE SHOT": "one[\\s_-]*shot|oneshot|single[\\s_-]*hit|hit|stab|accent|impact|tail|slam"
        },
        "categories": {
            "VOCALS": {
                "mainPatterns": [
                    "vox|vocal|vocals|voice|voices|adlib|hook|chant|groan|phrase|verse|stack|sing|sung|female|male"
                ],
                "subPatterns": {
                    "LOOP": "loop|loops|phrase|phrases|adlib|hook|chant|verse",
                    "ONE SHOT": "one[\\s_-]*shot|oneshot|single|vox|vocal|adlib|word"
                }
            },
            "DRUMS": {
                "mainPatterns": [
                    "drum|drums|kick|bd|bass[\\s_-]*drum|snare|hat|hihat|hi[\\s_-]*hat|hh|h[\\s_-]*h|clap|cymbal"
                ],
                "subPatterns": {
                    "KICK": "kick|bd|bass[\\s_-]*drum",
                    "SNARE": "snare",
                    "HAT": "hat|hihat|hi[\\s_-]*hat|hh|h[\\s_-]*h",
                    "CLAP": "clap",
                    "PERCUSSION": "percussion|perc|conga|bongo|rim|tambourine|shaker|cowbell",
                    "CRASH-RIDE": "crash|ride|cymbal"
                }
            },
            "INSTRUMENTS": {
                "mainPatterns": [
                    "synth|pad|lead|arp|pluck|chord|stab|piano|guitar|keys|melody|melodic|fiddle|flute|bell"
                ],
                "subPatterns": {
                    "CHORDS": "chord|chords|harmony|harmonies|progression",
                    "PADS": "pad|pads|atmosphere|ambient|space|warm|soft",
                    "STABS": "stab|stabs|hit|hits|accent|accents|impact",
                    "SYNTH": "synth|synths|synthetic|electronic|digital|analog",
                    "ACOUSTIC": "acoustic|unplugged|natural|organic|wood|wooden|string"
                }
            },
            "BASS": {
                "mainPatterns": [
                    "bass(?:[\\s_-]?line)?|808|sub|sub[\\s_-]*bass|subbass"
                ],
                "subPatterns": {
                    "LOOP": "loop|loops|phrase|phrases|groove|riff|bassline",
                    "ONE SHOT": "one[\\s_-]*shot|oneshot|single|hit|stab|808|sub"
                }
            },
            "FX": {
                "mainPatterns": [
                    "fx|effect|effects|impact|riser|down[\\s_-]*lifter|up[\\s_-]*lifter|drone|noise|sfx"
                ],
                "subPatterns": {
                    "AMBIENT": "ambient|atmosphere|atmos|ambience|background|pad",
                    "TEXTURE": "texture|textures|crusty|dirty|rough|smooth",
                    "DRONE": "drone|drones|alien|cave",
                    "LOOP": "loop|loops|phrase|phrases|groove|riff|sweep|whoosh",
                    "ONE SHOT": "one[\\s_-]*shot|oneshot|single|hit|stab|impact"
                }
            }
        },
        "classification_priority": {
            "VOCALS": 5,
            "DRUMS": 4,
            "INSTRUMENTS": 3,
            "BASS": 2,
            "FX": 1,
            "UNKNOWN": 0
        }
    }
    
    # Save to file
    with open(patterns_file, 'w') as f:
        json.dump(default_patterns, f, indent=4)
    
    logging.info(f"Created default patterns file at {patterns_file}")

def validate_patterns_file(patterns_file):
    """Validate the patterns file structure"""
    try:
        with open(patterns_file) as f:
            patterns = json.load(f)
        
        # Check required sections
        required_sections = ["pattern_config", "base_patterns", "categories"]
        for section in required_sections:
            if section not in patterns:
                logging.error(f"Missing required section '{section}' in patterns file")
                sys.exit(1)
        
        # Check pattern_config
        required_config = ["wb", "we", "case_insensitive"]
        for config in required_config:
            if config not in patterns["pattern_config"]:
                logging.error(f"Missing required config '{config}' in pattern_config")
                sys.exit(1)
        
        # Validate regex patterns (check syntax only)
        try:
            for section in ["base_patterns", "categories"]:
                if section == "base_patterns":
                    for name, pattern in patterns[section].items():
                        # Convert to string if needed
                        if not isinstance(pattern, str):
                            pattern = str(pattern) if not isinstance(pattern, (bytes, bytearray)) else pattern.decode('utf-8')
                        re.compile(pattern)
                elif section == "categories":
                    for category, data in patterns[section].items():
                        if "mainPatterns" in data:
                            for pattern in data["mainPatterns"]:
                                # Convert to string if needed
                                if not isinstance(pattern, str):
                                    pattern = str(pattern) if not isinstance(pattern, (bytes, bytearray)) else pattern.decode('utf-8')
                                re.compile(pattern)
            
            logging.info(f"Patterns file validated: {patterns_file}")
        except re.error as e:
            logging.error(f"Invalid regex pattern in file {patterns_file}: {e}")
            sys.exit(1)
        
    except json.JSONDecodeError:
        logging.error(f"Invalid JSON in patterns file: {patterns_file}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error validating patterns file: {e}")
        sys.exit(1)

def create_category_directories(patterns_file, output_dir):
    """Create category directories based on the folder_structure in the patterns file"""
    with open(patterns_file) as f:
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
        full_path = output_dir / folder_path
        full_path.mkdir(parents=True, exist_ok=True)
    
    logging.info(f"Created {len(folder_paths)} directories in {output_dir}")
    print(f"Created {len(folder_paths)} category directories")
    
    return folder_paths

def get_cache_settings_interactive():
    """Ask user for cache settings"""
    print("\n=== CACHE SETTINGS ===")
    print("The organizer can cache audio analysis results to improve performance")
    print("on subsequent runs. This significantly speeds up processing when working")
    print("with the same audio files repeatedly.")
    
    enable_cache = input("Enable audio analysis caching? (Y/n): ").strip().lower() != 'n'
    
    if not enable_cache:
        return {
            "enable_cache": False
        }
    
    # Get cache file path
    default_cache_file = "./cache/audio_analysis_cache.pkl"
    print(f"\nDefault cache file: {default_cache_file}")
    cache_file = input("Cache file path (press Enter for default): ").strip()
    if not cache_file:
        cache_file = default_cache_file
    
    # Get cache size limit
    default_max_size = 100
    print(f"\nDefault maximum cache size: {default_max_size} MB")
    size_input = input("Maximum cache size in MB (press Enter for default): ").strip()
    try:
        max_size = int(size_input) if size_input else default_max_size
    except ValueError:
        print("Invalid input, using default value")
        max_size = default_max_size
    
    # Get cache expiration
    default_expiration = 30
    print(f"\nDefault cache expiration period: {default_expiration} days")
    exp_input = input("Cache expiration in days (press Enter for default): ").strip()
    try:
        expiration = int(exp_input) if exp_input else default_expiration
    except ValueError:
        print("Invalid input, using default value")
        expiration = default_expiration
    
    # Background saving option
    background_saving = input("\nEnable background cache saving? (Y/n): ").strip().lower() != 'n'
    
    return {
        "enable_cache": enable_cache,
        "cache_file": cache_file,
        "max_cache_size_mb": max_size,
        "cache_expiration_days": expiration,
        "background_saving": background_saving,
        "save_interval": 60
    }

def create_config_file(config_dir, source_path, output_dir, patterns_file, threads, enable_audio_analysis=False):
    """Create a config file for the organizer"""
    # Get cache settings if interactive mode
    if interactive_mode:
        cache_settings = get_cache_settings_interactive()
    else:
        # Default cache settings
        cache_settings = {
            "enable_cache": True,
            "cache_file": "./cache/audio_analysis_cache.pkl",
            "max_cache_size_mb": 100,
            "cache_expiration_days": 30,
            "background_saving": True,
            "save_interval": 60
        }
    
    config = {
        "source_path": str(source_path),
        "output_path": str(output_dir),
        "patterns_file": str(patterns_file),
        "threads": threads if threads > 0 else os.cpu_count(),
        "process_subfolders": True,
        "overwrite_existing": False,
        "move_files": False,
        "generate_report": True,
        "backup_original": False,
        "enable_audio_analysis": enable_audio_analysis,
        "ignore_patterns": [".DS_Store", "Thumbs.db", ".asd"],
        "audio_extensions": [".wav", ".mp3", ".aif", ".aiff", ".ogg", ".flac"],
        "logging_level": "INFO",
        "analysis_timeout": 10,
        "loop_min_duration": 1.0,
        "oneshot_max_duration": 1.5,
        "cache_settings": cache_settings
    }
    
    config_file = config_dir / "config.json"
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=4)
    
    logging.info(f"Created config file at {config_file}")

if __name__ == "__main__":
    setup_project()