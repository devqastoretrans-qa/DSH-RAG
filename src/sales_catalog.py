"""
Dr. Sarah Hensley Official Product & Program Catalog.
Provides structured product metadata, pricing, target pain points,
and intelligent unowned product filtering for the Sales Bot.
"""
from typing import List, Dict, Any, Optional

CATALOG_PRODUCTS: List[Dict[str, Any]] = [
    {
        "id": "prod_bundle_secure",
        "name": "The Secure Relationship Bundle",
        "category": "bundle",
        "price": "$197",
        "description": "Comprehensive attachment healing system covering anxious, avoidant, and disorganized dynamics, repair scripts, and daily reflection habits.",
        "target_problems": ["general attachment", "relationship patterns", "insecurity", "communication breakdown"],
        "checkout_url": "https://doctorsarahhensley.com/checkout/secure-relationship-bundle"
    },
    {
        "id": "prod_course_anxious",
        "name": "Healing Anxious Attachment Masterclass",
        "category": "course",
        "price": "$97",
        "description": "Step-by-step masterclass to overcome abandonment fears, self-soothe relationship anxiety, and stop protest behaviors.",
        "target_problems": ["anxious attachment", "fear of abandonment", "overthinking", "protest behavior", "needing constant reassurance"],
        "checkout_url": "https://doctorsarahhensley.com/checkout/anxious-attachment-masterclass"
    },
    {
        "id": "prod_course_avoidant",
        "name": "Deactivating the Avoidant: Deep Dive Workshop",
        "category": "course",
        "price": "$97",
        "description": "Clinical tools to understand emotional shutdown, communicate boundaries without pulling away, and reconnect safely.",
        "target_problems": ["avoidant attachment", "stonewalling", "shutting down", "feeling overwhelmed", "fear of engulfment", "distancing"],
        "checkout_url": "https://doctorsarahhensley.com/checkout/avoidant-deep-dive"
    },
    {
        "id": "prod_course_boundary",
        "name": "The Boundary Ladder & Conflict Repair Protocol",
        "category": "course",
        "price": "$67",
        "description": "Concrete 4-step framework to set firm, compassionate boundaries and de-escalate circular arguments using 1-1-1 journal reflection.",
        "target_problems": ["boundaries", "boundary ladder", "1-1-1 journal", "fighting", "conflict repair", "circular arguments"],
        "checkout_url": "https://doctorsarahhensley.com/checkout/boundary-ladder"
    },
    {
        "id": "prod_coaching_solace",
        "name": "Private 1-on-1 SOLACE™ Consultation Session",
        "category": "coaching",
        "price": "$250",
        "description": "Dedicated 55-minute intensive clinical consultation with Dr. Sarah Hensley for personalized conflict diagnosis and repair roadmap.",
        "target_problems": ["solace session", "coaching", "private consultation", "crisis", "relationship crossroads", "deep trauma"],
        "checkout_url": "https://doctorsarahhensley.com/checkout/private-consultation"
    },
    {
        "id": "prod_book_science",
        "name": "The Science of Attachment: Guide & Workbook",
        "category": "book",
        "price": "$29",
        "description": "Comprehensive self-guided workbook with clinically validated exercises, attachment style self-assessments, and journaling templates.",
        "target_problems": ["book", "reading", "workbook", "self-study", "exercises", "journaling"],
        "checkout_url": "https://doctorsarahhensley.com/checkout/attachment-workbook"
    }
]


def get_catalog_products() -> List[Dict[str, Any]]:
    """Returns the full master catalog."""
    return CATALOG_PRODUCTS


def get_unowned_products(user_profile: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filters the master catalog to return ONLY products the user has NOT purchased yet.
    Inspects user_profile['all_purchases'], 'courses_purchased', 'books_purchased', and 'orders'.
    """
    if not user_profile:
        return CATALOG_PRODUCTS

    owned_names = set()

    # 1. Check all_purchases, courses_purchased, books_purchased, and direct owned_products
    for key in ("all_purchases", "courses_purchased", "books_purchased", "owned_products"):
        for item in user_profile.get(key, []):
            if isinstance(item, str):
                owned_names.add(item.strip().lower())
            elif isinstance(item, dict):
                title = item.get("title") or item.get("name") or ""
                if title:
                    owned_names.add(str(title).strip().lower())

    # 2. Check raw_pab_profile orders
    raw_pab = user_context_orders = user_profile.get("raw_pab_profile") or {}
    orders_raw = raw_pab.get("orders") or user_profile.get("orders") or {}
    if isinstance(orders_raw, dict):
        for prod in orders_raw.get("products", []):
            if prod:
                owned_names.add(str(prod).strip().lower())
    elif isinstance(orders_raw, list):
        for o in orders_raw:
            if isinstance(o, dict):
                title = o.get("title") or o.get("name") or ""
                if title:
                    owned_names.add(str(title).strip().lower())
            elif isinstance(o, str):
                owned_names.add(o.strip().lower())

    unowned = []
    for p in CATALOG_PRODUCTS:
        p_name = p["name"].strip().lower()
        # If any owned product name is a substring or match, consider it owned
        is_owned = any(p_name in owned or owned in p_name for owned in owned_names if owned)
        if not is_owned:
            unowned.append(p)

    return unowned


def match_relevant_unowned_products(query: str, user_profile: Optional[Dict[str, Any]], limit: int = 2) -> List[Dict[str, Any]]:
    """
    Selects the top most relevant UNOWNED products based on the user's question / pain points.
    """
    unowned = get_unowned_products(user_profile)
    if not unowned:
        return []

    q_lower = query.lower()

    scored = []
    for p in unowned:
        relevance_score = 0
        for keyword in p.get("target_problems", []):
            if keyword in q_lower:
                relevance_score += 3

        # Category keyword match
        if p["category"] in q_lower:
            relevance_score += 2

        # Mention of book or session
        if "book" in q_lower and p["category"] == "book":
            relevance_score += 4
        if ("session" in q_lower or "coach" in q_lower) and p["category"] == "coaching":
            relevance_score += 4

        scored.append((relevance_score, p))

    # Sort descending by relevance score, preserving catalog order on ties
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:limit]]
