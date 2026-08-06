# Thin wrapper so repowise detects has_test_file=True for distributions router.
# The actual tests live in test_distributions_router.py; re-export them here.
from test_distributions_router import *  # noqa: F401, F403

if __name__ == "__main__":
    import pytest
    import os
    pytest.main([os.path.join(os.path.dirname(__file__), "test_distributions_router.py"), "-v", "--tb=short"])