import os
import unittest
from fastapi.testclient import TestClient

from app import app
from src.sales_catalog import get_unowned_products, match_relevant_unowned_products, get_catalog_products

client = TestClient(app)

def test_sales_catalog_guardrails():
    print("\n--- 1. Testing Sales Catalog & Unowned Filtering Guardrail ---")
    
    # Simulate user who owns 'The Secure Relationship Bundle'
    profile_with_bundle = {
        "user_id": "1",
        "name": "Admin",
        "all_purchases": ["The Secure Relationship Bundle"],
        "courses_purchased": ["The Secure Relationship Bundle"],
        "books_purchased": []
    }
    
    unowned = get_unowned_products(profile_with_bundle)
    unowned_names = [p["name"] for p in unowned]
    print(f"Total catalog products: {len(get_catalog_products())}")
    print(f"Unowned products for Admin: {unowned_names}")
    
    assert "The Secure Relationship Bundle" not in unowned_names, "GUARDRAIL FAILED: Owned product was not filtered out!"
    print(">>> GUARDRAIL 1 VERIFIED: Already owned products are strictly excluded from recommendations! <<<")

    # Test relevance matching for anxious attachment query
    anxious_match = match_relevant_unowned_products("I feel so anxious when my partner does not text back", profile_with_bundle, limit=1)
    print(f"Matched product for anxious query: {anxious_match[0]['name']}")
    assert "Healing Anxious Attachment Masterclass" == anxious_match[0]["name"], "Expected Anxious Masterclass to match anxious query!"
    print(">>> GUARDRAIL 2 VERIFIED: Query relevance matching picks the exact matching course! <<<")


def test_sales_endpoint_live():
    print("\n--- 2. Testing Live /api/v1/sales/ask Endpoint ---")
    headers = {"Authorization": "Bearer dsh_rag_secret_key_2026", "X-API-Key": "dsh_rag_secret_key_2026"}
    
    # Clear cache first to ensure fresh PAB fetch
    client.post("/api/v1/cache/clear", headers=headers)

    payload = {
        "user_id": "admin",
        "question": "How do I communicate my needs without causing a fight with my avoidant partner?"
    }
    
    response = client.post("/api/v1/sales/ask", json=payload, headers=headers)
    print(f"Status Code: {response.status_code}")
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}"
    
    data = response.json()
    assert data["success"] is True
    assert data["mode"] == "sales"
    assert "answer" in data
    assert "recommended_products" in data
    
    print("\n--- Sales Bot Generated Response ---")
    print(data["answer"])
    print("\nRecommended Products in Metadata:")
    for rp in data.get("recommended_products", []):
        print(f"  * {rp['name']} - {rp['price']} ({rp['checkout_url']})")
        assert "The Secure Relationship Bundle" != rp["name"], "Owned product leaked into recommendations!"
        
    print("\n>>> SALES BOT ENDPOINT VERIFIED SUCCESSFULLY! <<<")


if __name__ == "__main__":
    test_sales_catalog_guardrails()
    test_sales_endpoint_live()
    print("\n>>> ALL SALES BOT TESTS PASSED! <<<")
