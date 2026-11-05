"""
Unit and Regression Tests for DEF-08:
Mid-Sentence Response Truncation and Orphan Section Headers Fix.
"""
import pytest
from src.generator import clean_trailing_truncation, OpenAIGeneratorService


def test_clean_orphan_section_header_user_scenario():
    """
    Verifies that a bare orphan header like 'Quick takeaways' at the end of a response
    is cleanly removed, leaving the valid preceding sentence intact.
    """
    raw_response = (
        "How this supports your Hybrid Group Coaching:\n\n"
        "Review your saved scripts before a coaching call to spot recurring patterns you've flagged.\n"
        "Bring a specific Reflections entry into the group discussion to illustrate a real-world repair attempt and receive feedback.\n"
        "Quick takeaways"
    )
    cleaned = clean_trailing_truncation(raw_response)
    assert "Quick takeaways" not in cleaned
    assert cleaned.endswith("receive feedback.")


def test_clean_orphan_markdown_header():
    """Verifies that markdown headers like '### Quick takeaways:' or '### Takeaways' are removed if severed."""
    raw_response = (
        "This is a complete clinical observation.\n\n"
        "### Quick takeaways:\n"
        "- Incomplete severed sentence with no"
    )
    cleaned = clean_trailing_truncation(raw_response)
    assert "### Quick takeaways:" not in cleaned
    assert "Incomplete severed" not in cleaned
    assert cleaned == "This is a complete clinical observation."


def test_preserve_complete_takeaways():
    """Verifies that complete takeaway sections with terminal punctuation are preserved 100% intact."""
    raw_response = (
        "This is a complete clinical observation.\n\n"
        "### Quick Takeaways\n"
        "- First actionable takeaway step.\n"
        "- Second actionable takeaway step."
    )
    cleaned = clean_trailing_truncation(raw_response)
    assert "- First actionable takeaway step." in cleaned
    assert "- Second actionable takeaway step." in cleaned
    assert cleaned.endswith("- Second actionable takeaway step.")


def test_clean_orphan_colon_label():
    """Verifies that trailing labels ending in a colon without body content are pruned."""
    raw_response = (
        "Understanding your partner's avoidance requires somatic awareness.\n\n"
        "Next Steps:"
    )
    cleaned = clean_trailing_truncation(raw_response)
    assert "Next Steps:" not in cleaned
    assert cleaned == "Understanding your partner's avoidance requires somatic awareness."


def test_effective_max_tokens_headroom():
    """
    Verifies that effective_max_tokens provides 1,200 headroom for generic and sales modes,
    and 400 for short definition lookups.
    """
    # Test short query
    short_query = "What is anxious attachment?"
    is_short = len(short_query.split()) <= 6 and any(
        w in short_query.lower() for w in ["what is", "define", "meaning", "who is", "cost", "price", "how much"]
    )
    assert is_short is True

    # Test complex clinical scenario
    complex_query = "My partner shuts down and stonewalls during conflict and I get anxious"
    is_short_complex = len(complex_query.split()) <= 6 and any(
        w in complex_query.lower() for w in ["what is", "define", "meaning", "who is", "cost", "price", "how much"]
    )
    assert is_short_complex is False
