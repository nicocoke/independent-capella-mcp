"""Run the whole Python suite with network/process creation forbidden."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
# Import networking modules before replacing their socket primitive.
import ssl
import urllib.request
import subprocess

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
with patch("socket.socket", side_effect=AssertionError("Offline verification forbids sockets")), \
     patch("subprocess.Popen", side_effect=AssertionError("Offline verification forbids processes")), \
     patch("os.system", side_effect=AssertionError("Offline verification forbids shell execution")):
    suite = unittest.defaultTestLoader.discover(str(root / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
