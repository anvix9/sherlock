# tests/test_core.py
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from sherlock.core import hello

def test_hello():
    assert hello() == "Hello from Sherlock!"


