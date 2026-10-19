import sys
import json
from unittest.mock import MagicMock, patch
from src.user_db import UserDatabaseManager

def test_pab_formatting():
    sample_payload = {
        "cached": False,
        "profile": {
            "user_id": 1,
            "display_name": "test",
            "first_name": "Admin",
            "member_since": "2026-05-06 09:51:14",
            "locale": "en_US",
            "meta": {
                "first_name": "Admin",
                "last_name": "Tribepub"
            },
            "orders": [],
            "program": {
                "gamplify_attachmentos_points_log": [
                    {
                        "id": "49",
                        "action_key": "boundary_ladder",
                        "points": "1",
                        "daily_date": "2026-10-07",
                        "source_id": "6",
                        "note": "Boundary Ladder Entry",
                        "created_at": "2026-10-07 05:23:10"
                    },
                    {
                        "id": "42",
                        "action_key": "solace",
                        "points": "1",
                        "daily_date": "2026-10-07",
                        "source_id": "7",
                        "note": "SOLACE™ Session",
                        "created_at": "2026-10-07 03:23:15"
                    }
                ],
                "gamplify_attachmentos_user_streaks": [
                    {
                        "id": "7",
                        "streak_key": "boundary_ladder",
                        "current_streak": "2",
                        "longest_streak": "2",
                        "last_activity_date": "2026-10-07",
                        "last_period_key": "2026-41",
                        "updated_at": "2026-10-07 05:23:10"
                    },
                    {
                        "id": "1",
                        "streak_key": "solace",
                        "current_streak": "2",
                        "longest_streak": "2",
                        "last_activity_date": "2026-10-07",
                        "last_period_key": "2026-41",
                        "updated_at": "2026-10-07 03:23:15"
                    }
                ]
            },
            "generated_at": "2026-10-07T09:29:02+00:00"
        }
    }

    db_manager = UserDatabaseManager()
    
    # Mock requests.get to return sample payload
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = sample_payload

    with patch("requests.get", return_value=mock_resp):
        profile = db_manager._get_profile_from_pab_api("1")

    print("[TEST] Profile returned from PAB inspect API parser:")
    print(json.dumps(profile, indent=2))

    assert profile is not None, "Profile should not be None"
    assert profile["name"] == "Admin Tribepub", f"Expected name 'Admin Tribepub', got '{profile['name']}'"
    assert profile["backend"] == "PAB Profile API"
    assert len(profile["streaks"]) == 2, f"Expected 2 streaks, got {len(profile['streaks'])}"
    assert len(profile["recent_activities"]) == 2, f"Expected 2 recent activities, got {len(profile['recent_activities'])}"
    assert profile["has_history"] is True, "has_history should be True"

    print("\n[SUCCESS] PAB Inspect Profile API Parsing & Formatting Test Passed Successfully!")

if __name__ == "__main__":
    test_pab_formatting()
