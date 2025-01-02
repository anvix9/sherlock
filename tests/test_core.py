# tests/test_core.py
from sherlock.core import hello

def test_hello():
    assert hello() == "Hello from Sherlock!"


