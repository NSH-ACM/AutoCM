"""
Python wrapper for the AutoCM C++ physics engine.
Provides type hints and documentation for all C++ functions.
"""

try:
    import autocm_engine
except ImportError:
    raise ImportError("Could not import autocm_engine. Make sure it's built and in the Python path.")

# Re-export all C++ classes and functions
from autocm_engine import *
