"""
ViaFence plugin for KiCad 9.0
"""

import os
import sys

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from .via_fence import ViaFencePlugin

# Create plugin instance
plugin = ViaFencePlugin()
plugin.register()