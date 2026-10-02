import sys

_target_deps = None

def pytest_collectstart(collector):
    global _target_deps
    m = sys.modules.get("dependencies")
    if m is not None and getattr(m, "__file__", None) is None and getattr(m, "__path__", None):
        # namespace package — record when it appears
        if _target_deps != "seen":
            _target_deps = "seen"
            print(f"\n>>> dependencies became NAMESPACE before: {collector}\n")
