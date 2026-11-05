import os
import pytest
from unittest.mock import MagicMock, patch
from src.user_db import UserDatabaseManager
from src.sales_catalog import match_relevant_unowned_products, get_unowned_products


# =========================================================================
# 1. POSITIVE TEST CASES (Active Ownership)
# =========================================================================

def test_completed_order_active_ownership():
    """Verify orders with status 'completed' grant active ownership in memory and database."""
    udb = UserDatabaseManager()
    uid = "test_user_completed_pos"

    order_payload = {
        "id": 1001,
        "date_created": "2026-11-01T10:00:00",
        "status": "completed",
        "customer_id": uid,
        "billing": {"first_name": "Sarah", "last_name": "Connor", "email": "sarah_connor_test@example.com"},
        "line_items": [
            {"name": "Healing Anxious Attachment Masterclass"},
            {"name": "The Science of Attachment: Guide & Workbook"}
        ]
    }

    profile = udb.ingest_woocommerce_order_webhook(order_payload)

    # Verify collections
    assert "Healing Anxious Attachment Masterclass" in profile["courses_purchased"]
    assert "The Science of Attachment: Guide & Workbook" in profile["books_purchased"]
    assert len(profile["all_purchases"]) == 2

    # Verify underlying SQLite purchases table
    with udb._lock:
        with udb._get_sqlite_conn() as conn:
            rows = conn.execute("SELECT item_title FROM purchases WHERE user_id = ?", (uid,)).fetchall()
            db_titles = [r[0] for r in rows]
            assert "Healing Anxious Attachment Masterclass" in db_titles
            assert "The Science of Attachment: Guide & Workbook" in db_titles


def test_processing_order_active_ownership():
    """Verify orders with status 'processing' grant active ownership identically to completed orders."""
    udb = UserDatabaseManager()
    uid = "test_user_processing_pos"

    order_payload = {
        "id": 1002,
        "date_created": "2026-11-02T10:00:00",
        "status": "processing",
        "customer_id": uid,
        "billing": {"first_name": "Kyle", "last_name": "Reese", "email": "kyle@example.com"},
        "line_items": [
            {"name": "Deactivating the Avoidant: Deep Dive Workshop"}
        ]
    }

    profile = udb.ingest_woocommerce_order_webhook(order_payload)

    assert "Deactivating the Avoidant: Deep Dive Workshop" in profile["courses_purchased"]
    assert "Deactivating the Avoidant: Deep Dive Workshop" in profile["all_purchases"]

    with udb._lock:
        with udb._get_sqlite_conn() as conn:
            rows = conn.execute("SELECT item_title FROM purchases WHERE user_id = ?", (uid,)).fetchall()
            assert "Deactivating the Avoidant: Deep Dive Workshop" in [r[0] for r in rows]


@pytest.mark.parametrize("status_variant", ["COMPLETED", "Processing", "completed ", "  PROCESSING  "])
def test_status_case_insensitivity_and_whitespace(status_variant):
    """Verify status normalization handles uppercase, title case, and leading/trailing whitespace."""
    udb = UserDatabaseManager()
    uid = f"test_user_case_{hash(status_variant)}"

    order_payload = {
        "id": 1003,
        "date_created": "2026-11-03T10:00:00",
        "status": status_variant,
        "customer_id": uid,
        "billing": {"first_name": "John", "last_name": "Doe", "email": "case@example.com"},
        "line_items": [
            {"name": "The Boundary Ladder & Conflict Repair Protocol"}
        ]
    }

    profile = udb.ingest_woocommerce_order_webhook(order_payload)

    assert "The Boundary Ladder & Conflict Repair Protocol" in profile["courses_purchased"]
    assert "The Boundary Ladder & Conflict Repair Protocol" in profile["all_purchases"]


# =========================================================================
# 2. NEGATIVE TEST CASES (Inactive Orders & Audit Trail)
# =========================================================================

def test_refunded_order_rejected_from_active_ownership():
    """Verify orders with status 'refunded' are rejected from active ownership."""
    udb = UserDatabaseManager()
    uid = "test_user_refund_neg"

    order_payload = {
        "id": 2001,
        "date_created": "2026-11-01T10:00:00",
        "status": "refunded",
        "customer_id": uid,
        "billing": {"first_name": "Refunder", "last_name": "User", "email": "refunder@example.com"},
        "line_items": [
            {"name": "Healing Anxious Attachment Masterclass"}
        ]
    }

    profile = udb.ingest_woocommerce_order_webhook(order_payload)

    assert "Healing Anxious Attachment Masterclass" not in profile["courses_purchased"]
    assert "Healing Anxious Attachment Masterclass" not in profile["all_purchases"]

    # Verify not in DB purchases table
    with udb._lock:
        with udb._get_sqlite_conn() as conn:
            rows = conn.execute("SELECT item_title FROM purchases WHERE user_id = ?", (uid,)).fetchall()
            assert "Healing Anxious Attachment Masterclass" not in [r[0] for r in rows]


@pytest.mark.parametrize("inactive_status", ["cancelled", "failed", "CANCELLED", "Failed "])
def test_cancelled_and_failed_orders_blocked_from_ownership(inactive_status):
    """Verify cancelled and failed orders are blocked from granting active ownership."""
    udb = UserDatabaseManager()
    uid = f"test_user_inactive_{hash(inactive_status)}"

    order_payload = {
        "id": 2002,
        "date_created": "2026-11-02T10:00:00",
        "status": inactive_status,
        "customer_id": uid,
        "billing": {"first_name": "Inactive", "last_name": "User", "email": "inactive@example.com"},
        "line_items": [
            {"name": "Private 1-on-1 SOLACE Consultation Session"}
        ]
    }

    profile = udb.ingest_woocommerce_order_webhook(order_payload)

    assert "Private 1-on-1 SOLACE Consultation Session" not in profile["courses_purchased"]
    assert "Private 1-on-1 SOLACE Consultation Session" not in profile["all_purchases"]


def test_inactive_orders_recorded_in_past_records_audit_trail():
    """Verify all inactive orders (refunded, cancelled, failed) are fully recorded in past_records."""
    udb = UserDatabaseManager()
    uid = "test_user_audit_trail"

    for oid, status, item in [
        (3001, "refunded", "Course A"),
        (3002, "cancelled", "Course B"),
        (3003, "failed", "Course C")
    ]:
        udb.ingest_woocommerce_order_webhook({
            "id": oid,
            "date_created": "2026-11-04T10:00:00",
            "status": status,
            "customer_id": uid,
            "billing": {"first_name": "Audit", "last_name": "Tester", "email": "audit@example.com"},
            "line_items": [{"name": item}]
        })

    profile = udb.get_user_profile(uid)

    # Active purchases must remain empty
    assert len(profile["all_purchases"]) == 0

    # Historical audit trail must contain all 3 events
    record_text = " ".join(profile["past_records"])
    assert "Course A" in record_text
    assert "Course B" in record_text
    assert "Course C" in record_text
    assert "Refunded" in record_text or "refunded" in record_text.lower()
    assert "Cancelled" in record_text or "cancelled" in record_text.lower()


# =========================================================================
# 3. REAL-TIME REVOCATION (Webhook order.updated)
# =========================================================================

def test_active_to_refunded_transition_revokes_db_and_cache():
    """Simulate order.created (active) followed by order.updated (refunded) live lifecycle."""
    udb = UserDatabaseManager()
    uid = "test_user_active_to_refund"

    # Step 1: Active order completes
    order_create = {
        "id": 4001,
        "date_created": "2026-11-01T10:00:00",
        "status": "completed",
        "customer_id": uid,
        "billing": {"first_name": "Lifecycle", "last_name": "User", "email": "lifecycle@example.com"},
        "line_items": [
            {"name": "Healing Anxious Attachment Masterclass"},
            {"name": "The Secure Relationship Bundle"}
        ]
    }
    prof_created = udb.ingest_woocommerce_order_webhook(order_create)
    assert len(prof_created["all_purchases"]) == 2

    # Step 2: Refund arrives for Masterclass only
    order_refund = {
        "id": 4001,
        "date_created": "2026-11-01T10:00:00",
        "status": "refunded",
        "customer_id": uid,
        "billing": {"first_name": "Lifecycle", "last_name": "User", "email": "lifecycle@example.com"},
        "line_items": [
            {"name": "Healing Anxious Attachment Masterclass"}
        ]
    }
    prof_refunded = udb.ingest_woocommerce_order_webhook(order_refund)

    # Masterclass revoked, Secure Bundle remains active
    assert "Healing Anxious Attachment Masterclass" not in prof_refunded["courses_purchased"]
    assert "Healing Anxious Attachment Masterclass" not in prof_refunded["all_purchases"]
    assert "The Secure Relationship Bundle" in prof_refunded["all_purchases"]

    # Verify DB table state directly
    with udb._lock:
        with udb._get_sqlite_conn() as conn:
            rows = conn.execute("SELECT item_title FROM purchases WHERE user_id = ?", (uid,)).fetchall()
            db_titles = [r[0] for r in rows]
            assert "Healing Anxious Attachment Masterclass" not in db_titles
            assert "The Secure Relationship Bundle" in db_titles


def test_active_to_cancelled_transition_revokes_db_and_cache():
    """Simulate order.created followed by order.updated (cancelled)."""
    udb = UserDatabaseManager()
    uid = "test_user_active_to_cancelled"

    order_create = {
        "id": 4002,
        "date_created": "2026-11-01T10:00:00",
        "status": "processing",
        "customer_id": uid,
        "billing": {"first_name": "Cancel", "last_name": "User", "email": "cancel@example.com"},
        "line_items": [
            {"name": "Deactivating the Avoidant: Deep Dive Workshop"}
        ]
    }
    udb.ingest_woocommerce_order_webhook(order_create)

    # Cancellation arrives
    order_cancel = {
        "id": 4002,
        "date_created": "2026-11-01T10:00:00",
        "status": "cancelled",
        "customer_id": uid,
        "billing": {"first_name": "Cancel", "last_name": "User", "email": "cancel@example.com"},
        "line_items": [
            {"name": "Deactivating the Avoidant: Deep Dive Workshop"}
        ]
    }
    prof_cancelled = udb.ingest_woocommerce_order_webhook(order_cancel)

    assert "Deactivating the Avoidant: Deep Dive Workshop" not in prof_cancelled["courses_purchased"]
    assert "Deactivating the Avoidant: Deep Dive Workshop" not in prof_cancelled["all_purchases"]

    with udb._lock:
        with udb._get_sqlite_conn() as conn:
            rows = conn.execute("SELECT item_title FROM purchases WHERE user_id = ?", (uid,)).fetchall()
            assert "Deactivating the Avoidant: Deep Dive Workshop" not in [r[0] for r in rows]


# =========================================================================
# 4. SALES ADVISOR ANTI-COLLISION GUARDRAIL INTEGRATION
# =========================================================================

def test_refunded_course_is_unlocked_for_sales_recommendations():
    """Verify that a customer with a refunded course is eligible to be recommended that exact course."""
    udb = UserDatabaseManager()
    uid = "test_user_sales_unlocked"

    # Ingest refunded order for Healing Anxious Attachment Masterclass
    udb.ingest_woocommerce_order_webhook({
        "id": 5001,
        "date_created": "2026-11-01T10:00:00",
        "status": "refunded",
        "customer_id": uid,
        "billing": {"first_name": "Anxious", "last_name": "Student", "email": "anxious@example.com"},
        "line_items": [{"name": "Healing Anxious Attachment Masterclass"}]
    })

    profile = udb.get_user_profile(uid)

    # 1. Unowned product catalog must contain the refunded course
    unowned = get_unowned_products(profile)
    unowned_names = [p["name"] for p in unowned]
    assert "Healing Anxious Attachment Masterclass" in unowned_names

    # 2. Sales matching for relationship anxiety must recommend the masterclass
    recommendations = match_relevant_unowned_products(
        query="I struggle with severe relationship anxiety, abandonment fears, and protest behavior",
        user_profile=profile,
        limit=2
    )
    rec_names = [p["name"] for p in recommendations]
    assert "Healing Anxious Attachment Masterclass" in rec_names


def test_completed_course_remains_blocked_by_anti_collision_guardrail():
    """Verify that an actively completed course is blocked by the anti-collision guardrail."""
    udb = UserDatabaseManager()
    uid = "test_user_sales_blocked"

    # Ingest completed order for Healing Anxious Attachment Masterclass
    udb.ingest_woocommerce_order_webhook({
        "id": 5002,
        "date_created": "2026-11-01T10:00:00",
        "status": "completed",
        "customer_id": uid,
        "billing": {"first_name": "Active", "last_name": "Student", "email": "active@example.com"},
        "line_items": [{"name": "Healing Anxious Attachment Masterclass"}]
    })

    profile = udb.get_user_profile(uid)

    # 1. Unowned products must NOT contain the owned masterclass
    unowned = get_unowned_products(profile)
    unowned_names = [p["name"] for p in unowned]
    assert "Healing Anxious Attachment Masterclass" not in unowned_names

    # 2. Recommendations for anxiety should recommend alternative programs (e.g. Bundle), NOT the owned masterclass
    recommendations = match_relevant_unowned_products(
        query="I struggle with severe relationship anxiety and need guidance",
        user_profile=profile,
        limit=2
    )
    rec_names = [p["name"] for p in recommendations]
    assert "Healing Anxious Attachment Masterclass" not in rec_names


# =========================================================================
# 5. EDGE CASES & ERROR RESILIENCE
# =========================================================================

def test_missing_or_malformed_status_payload():
    """Verify system handles None, empty, missing, or weird status values gracefully without crashing."""
    udb = UserDatabaseManager()

    # Payload with status: None
    res1 = udb.ingest_woocommerce_order_webhook({
        "id": 6001,
        "status": None,
        "customer_id": "edge_user_1",
        "billing": {"email": "edge1@example.com"},
        "line_items": [{"name": "Course A"}]
    })
    # None status should not grant active ownership
    assert "Course A" not in res1["courses_purchased"]

    # Payload with empty string status: ""
    res2 = udb.ingest_woocommerce_order_webhook({
        "id": 6002,
        "status": "",
        "customer_id": "edge_user_2",
        "billing": {"email": "edge2@example.com"},
        "line_items": [{"name": "Course B"}]
    })
    assert "Course B" not in res2["courses_purchased"]

    # Payload missing status field entirely (defaults gracefully)
    res3 = udb.ingest_woocommerce_order_webhook({
        "id": 6003,
        "customer_id": "edge_user_3",
        "billing": {"email": "edge3@example.com"},
        "line_items": [{"name": "Course C"}]
    })
    assert "Course C" in res3["courses_purchased"]


def test_duplicate_order_sync_idempotency():
    """Verify duplicate webhook delivery does not create duplicate database rows."""
    udb = UserDatabaseManager()
    uid = "test_user_idempotent"

    payload = {
        "id": 7001,
        "date_created": "2026-11-01T10:00:00",
        "status": "completed",
        "customer_id": uid,
        "billing": {"email": "idemp@example.com"},
        "line_items": [{"name": "Healing Anxious Attachment Masterclass"}]
    }

    # Ingest 3 times in a row
    udb.ingest_woocommerce_order_webhook(payload)
    udb.ingest_woocommerce_order_webhook(payload)
    prof = udb.ingest_woocommerce_order_webhook(payload)

    assert len(prof["courses_purchased"]) == 1

    # Verify only 1 row exists in SQLite purchases table for this user
    with udb._lock:
        with udb._get_sqlite_conn() as conn:
            rows = conn.execute(
                "SELECT id FROM purchases WHERE user_id = ? AND item_title = ?",
                (uid, "Healing Anxious Attachment Masterclass")
            ).fetchall()
            assert len(rows) == 1
