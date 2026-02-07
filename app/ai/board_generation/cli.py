"""
Command-line interface for generating Big Head boards.
"""

import os
import argparse
import asyncio
import logging
from datetime import datetime

from app.ai.board_generation.generator import BoardGenerator
from app.utils.logging_config import setup_logging

setup_logging()

async def main():
    """Run the board generation CLI."""
    parser = argparse.ArgumentParser(description='Generate Big Head game boards')
    parser.add_argument('--name', type=str, help='Name for the board file')
    parser.add_argument('--count', type=int, default=1, help='Number of boards to generate')
    parser.add_argument('--output-dir', type=str, default='app/game_data', help='Output directory')
    parser.add_argument('--model', type=str, default='gpt-4.1', help='LLM model to use')
    parser.add_argument('--no-double-big-heads', action='store_true', help='Disable double big heads')
    parser.add_argument('--user-input', type=str, default='', 
                      help='User preferences for the game (e.g., "nothing about science", "make it super easy")')
    
    args = parser.parse_args()
    
    generator = BoardGenerator(
        output_dir=args.output_dir,
        model=args.model,
        user_input=args.user_input
    )
    
    for i in range(args.count):
        if args.count > 1:
            if args.name:
                board_name = f"{args.name}_{i+1}"
            else:
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                board_name = f"generated_{timestamp}_{i+1}"
        else:
            board_name = args.name
        
        file_path = await generator.generate_and_save_board(
            board_name=board_name,
            add_double_big_heads=not args.no_double_big_heads
        )
        
        print(f"Generated board saved to: {file_path}")

if __name__ == "__main__":
    asyncio.run(main()) 