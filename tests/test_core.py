# tests/test_core.py
import sys 
from pathlib import Path 

#sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ..src.sherlock.core  import hello

def test_hello():
    assert hello() == "Hello from Sherlock!"


