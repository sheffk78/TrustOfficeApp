"""
Tests for approval_handler.py — deterministic text-based approval.
Run: python3 backend/test_approval_handler.py
No MongoDB required for the regex layer; DB layer is exercised by the
integration path in the live app.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from approval_handler import is_approval_message, is_rejection_message

# --- Approval cases: must ALL match ---
APPROVALS = [
    "yes",
    "Yes",
    "YES!",
    "yes.",
    "yes please",
    "yep",
    "yeah",
    "yup",
    "y",
    "sure",
    "ok",
    "okay",
    "ok do it",
    "go",
    "go ahead",
    "do it",
    "Do it.",
    "approved",
    "I approve",
    "please do",
    "proceed",
    "confirm",
    "confirmed",
    "sounds good",
    "that works",
    "looks good",
    "looks good to me",
    "add it",
    "create it",
    "send it",
    "make it",
    "that's correct",
    "correct",
    "right",
    "affirmative",
]

# --- Rejection cases: must ALL be rejected-as-approval ---
REJECTIONS = [
    "no",
    "nope",
    "nah",
    "cancel",
    "stop",
    "wait",
    "don't",
    "do not",
    "reject",
    "dismiss",
    "not yet",
    "not now",
    "hold on",
]

# --- Ambiguous/other cases: must NOT match approval ---
OTHER = [
    "yes but use 50% instead",
    "yes, but change the name to Bob",
    "no I meant add a beneficiary",
    "what's my health score?",
    "add Jane as a beneficiary",
    "yes what is the EIN",
    "ok but hold on a second",
    "no wait, actually yes",
]

fails = []
for t in APPROVALS:
    if not is_approval_message(t):
        fails.append(f"APPROVAL not matched: {t!r}")
    if is_rejection_message(t):
        fails.append(f"APPROVAL misclassified as rejection: {t!r}")

for t in REJECTIONS:
    if not is_rejection_message(t):
        fails.append(f"REJECTION not matched: {t!r}")
    if is_approval_message(t):
        fails.append(f"REJECTION misclassified as approval: {t!r}")

for t in OTHER:
    if is_approval_message(t) or is_rejection_message(t):
        fails.append(f"OTHER misclassified: {t!r}")

if fails:
    print("FAILURES:")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)

print(f"PASS: {len(APPROVALS)} approvals, {len(REJECTIONS)} rejections, {len(OTHER)} ambiguous all handled correctly")