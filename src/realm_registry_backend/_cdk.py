"""CDK compatibility layer.

This module centralizes all imports from the Internet Computer CDK (currently Basilisk).
To switch CDKs, only this file needs to be modified.
"""

from basilisk import *  # noqa: F401, F403
from basilisk import ic  # noqa: F401 - explicit for IDE support

# In CPython template mode, Variant and Record are plain dict which doesn't
# accept keyword arguments (e.g. total=False) in __init_subclass__.
# Override with subclasses that accept arbitrary kwargs.
try:
    class _TestVariant(Variant, total=False):  # noqa: F405
        pass
except TypeError:
    class Variant(dict):
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__()

    class Record(dict):
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__()
