"""
Helper functions for the AI host system
"""

import logging
import os
import re

logger = logging.getLogger(__name__)

def is_same_player(username1: str, username2: str) -> bool:
    """Check if two usernames refer to the same player (with flexible matching)."""
    if not username1 or not username2:
        return False
        
    username1 = username1.lower()
    username2 = username2.lower()
    
    return (username1 == username2 or
            username1.startswith(username2) or
            username2.startswith(username1) or
            username1 in username2 or
            username2 in username1)

async def cleanup_audio_files(directory: str, max_files: int = 5):
    """
    Keep only the most recent audio files, deleting older ones.
    
    Args:
        directory: The directory containing audio files
        max_files: Maximum number of files to keep
    """
    try:
        # Get list of audio files in the directory
        audio_files = []
        for filename in os.listdir(directory):
            if filename.startswith("question_audio_") and filename.endswith(".wav"):
                file_path = os.path.join(directory, filename)
                audio_files.append((file_path, os.path.getmtime(file_path)))
        
        # Sort files by modification time (newest first)
        audio_files.sort(key=lambda x: x[1], reverse=True)
        
        # Delete older files beyond the max_files limit
        for file_path, _ in audio_files[max_files:]:
            try:
                os.remove(file_path)
                logger.info(f"Removed old audio file: {file_path}")
            except Exception as e:
                logger.error(f"Failed to remove audio file {file_path}: {e}")
        
    except Exception as e:
        logger.error(f"Error cleaning up audio files in {directory}: {e}") 