"""Tests for the login-hint severity gate in error_alerting.

This file verifies that the special "account ready but no password set"
login hint is routed with severity "info", while ordinary login errors
still receive a non-info severity.
"""

import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_alert_login_hint")
os.environ.setdefault("JWT_SECRET", "test-secret-alert-hint")

import motor.motor_asyncio
import mongomock_motor

motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

import database

db = database.db


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    await db.error_logs.delete_many({})
    yield
    await db.error_logs.delete_many({})


@pytest.mark.asyncio
async def test_login_hint_routes_as_info(clean_db):
    import error_alerting

    result = await error_alerting.report_error(
        source="frontend",
        error_type="login",
        error_message="Your account is ready but no password is set yet. Use 'Forgot password' below to set one — the link is in your welcome email.",
    )

    doc = await db.error_logs.find_one({})
    assert doc is not None
    assert doc["metadata"]["severity"] == "info"
    assert result.get("severity") == "info"
    assert doc["resolved"] is False


@pytest.mark.asyncio
async def test_login_error_not_over_suppressed(clean_db):
    import error_alerting

    await error_alerting.report_error(
        source="frontend",
        error_type="login",
        error_message="Google OAuth consent failed",
    )

    doc = await db.error_logs.find_one({})
    assert doc is not None
    assert doc["metadata"]["severity"] != "info"
