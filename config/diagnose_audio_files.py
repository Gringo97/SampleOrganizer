import os
import logging
from pathlib import Path
import librosa
import soundfile as sf

def diagnose_audio_file(file_path):
    """Comprehensive audio file diagnosis"""
    try:
        # Basic file information
        print(f"\nDiagnosing file: {file_path}")
        print(f"File size: {os.path.getsize(file_path)} bytes")
        print(f"File extension: {file_path.suffix}")
        
        # Try different loading methods
        try:
            # Try librosa loading
            y, sr = librosa.load(file_path, sr=None, mono=True)
            print(f"Librosa: Duration = {librosa.get_duration(y=y, sr=sr):.2f} seconds")
            print(f"Sample rate: {sr} Hz")
            print(f"Channels: {1}")
        except Exception as librosa_error:
            print(f"Librosa loading failed: {librosa_error}")
        
        try:
            # Try soundfile for more detailed info
            with sf.SoundFile(file_path) as f:
                print(f"SoundFile: Frames = {len(f)}")
                print(f"SoundFile: Channels = {f.channels}")
                print(f"SoundFile: Sample rate = {f.samplerate}")
                print(f"SoundFile: Duration = {len(f)/f.samplerate:.2f} seconds")
        except Exception as sf_error:
            print(f"SoundFile loading failed: {sf_error}")
        
    except Exception as e:
        print(f"Unexpected error diagnosing {file_path}: {e}")

def main():
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    # Directory to diagnose
    source_dir = Path("D:/Oscar/Documents/SOUNDS/PRUEBAORGANIZAR")
    
    # Collect problematic files
    problematic_files = []
    
    # Iterate through files
    for file_path in source_dir.rglob('*'):
        if file_path.is_file():
            try:
                # Try to diagnose audio files
                diagnose_audio_file(file_path)
            except Exception as e:
                problematic_files.append((file_path, str(e)))
    
    # Report problematic files
    print("\n=== Problematic Files ===")
    for file, error in problematic_files:
        print(f"{file}: {error}")

if __name__ == "__main__":
    main()