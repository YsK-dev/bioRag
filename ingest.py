#!/usr/bin/env python3
"""
Wrapper script to satisfy the project deliverable requirement:
"2. ingest.py: The script that handles API calls to PubMed."

This forwards execution to the refactored code inside `src/`.
"""

import sys
import runpy

if __name__ == "__main__":
    runpy.run_module('src.ingest', run_name='__main__')
