import sys
import os

# Ensure project root is in Python path for module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Change working directory to project root so relative paths work
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dev.server_ui import app
