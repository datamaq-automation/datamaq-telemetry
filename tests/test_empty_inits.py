"""tests/test_empty_inits.py."""

import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_all_inits_are_empty():
    non_empty = []
    for dirpath in [os.path.join(ROOT_DIR, "src"), os.path.join(ROOT_DIR, "tests")]:
        for root, _, files in os.walk(dirpath):
            if "__init__.py" in files:
                init_path = os.path.join(root, "__init__.py")
                if os.path.getsize(init_path) > 0:
                    non_empty.append(os.path.relpath(init_path, ROOT_DIR))

    assert not non_empty, f"Los siguientes __init__.py deben ser de 0 bytes: {non_empty}"
