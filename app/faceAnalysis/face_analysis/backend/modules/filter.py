"""
Face Filter Module - Hybrid Implementation
Uses MediaPipe when available, falls back to OpenCV
"""

# Import the hybrid filter as the main filter
from .filter_hybrid import HybridFaceFilter as FaceFilter

# Export the class for backward compatibility
__all__ = ['FaceFilter']