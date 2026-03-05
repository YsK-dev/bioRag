#!/usr/bin/env python3
"""
Wrapper script to satisfy the project deliverable requirement:
"1. main.py: The entry point to run the query engine."

This forwards execution to the refactored code inside `src/`.
"""

import sys
from src.main import main

if __name__ == "__main__":
    sys.exit(main())
