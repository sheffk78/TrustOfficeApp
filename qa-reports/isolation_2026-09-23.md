============================= test session starts ==============================
platform darwin -- Python 3.9.6, pytest-8.4.2, pluggy-1.6.0
rootdir: /Users/socializerender/.openclaw/workspace/Kit/life/brands/TrustOffice/projects/TrustOfficeApp/backend
configfile: pytest.ini
plugins: anyio-4.12.1, asyncio-1.2.0, postmarker-1.0
asyncio: mode=strict, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 0 items / 1 error

==================================== ERRORS ====================================
________________ ERROR collecting tests/test_data_isolation.py _________________
backend/tests/test_data_isolation.py:67: in <module>
    raise RuntimeError(
E   RuntimeError: TRUSTOFFICE_QA_PASSWORD env var is required to run the isolation suite. The QA password is not stored in this repo.
=========================== short test summary info ============================
ERROR backend/tests/test_data_isolation.py - RuntimeError: TRUSTOFFICE_QA_PAS...
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.10s ===============================
