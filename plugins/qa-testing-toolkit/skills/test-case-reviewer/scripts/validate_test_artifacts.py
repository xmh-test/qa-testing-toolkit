#!/usr/bin/env python3
"""Use the same contract as generation and Excel export."""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "test-case-generator" / "scripts"))
from test_case_contract import main

if __name__ == "__main__":
    raise SystemExit(main())
