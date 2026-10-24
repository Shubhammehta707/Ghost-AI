"""
code/evaluation/main.py - Entry point for evaluation module.
"""

from pathlib import Path
import sys

# Ensure code/ directory is in python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation import main

if __name__ == "__main__":
    main()
