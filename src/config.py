import os
from typing import Dict, Any, Optional
from qdrant_client.models import Distance

# Dimension of sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_VECTOR_SIZE = 384
EMBEDDING_DISTANCE = Distance.COSINE

# Clinical Subfolder to Qdrant Collection Mapping
CLINICAL_COLLECTIONS: Dict[str, Dict[str, Any]] = {
    "journals": {
        "folder_name": "Journals",
        "collection_name": "clinical_knowledge_journals",
        "display_name": "Clinical Knowledge > Journals",
        "folder_id": "1eyx5tahj1ovVbk_jammzN8dQWdw2Nd8H"
    },
    "other": {
        "folder_name": "Other",
        "collection_name": "clinical_knowledge_other",
        "display_name": "Clinical Knowledge > Other",
        "folder_id": "1kPCVDWwOpBpBJ7mNYBe0gl71ygVXvzfX"
    },
    "tools": {
        "folder_name": "Tools",
        "collection_name": "clinical_knowledge_tools",
        "display_name": "Clinical Knowledge > Tools",
        "folder_id": "1dlnfP12wFomlX0kYWgw_emaWwirj_96E"
    },
    "reflections": {
        "folder_name": "Reflections",
        "collection_name": "clinical_knowledge_reflections",
        "display_name": "Clinical Knowledge > Reflections",
        "folder_id": "1-IspRGOOdGCqfE55ltIFNkdnd3E5D9N6"
    }
}

# Reverse lookup by folder name (case-insensitive)
FOLDER_NAME_TO_KEY: Dict[str, str] = {
    cfg["folder_name"].lower(): key
    for key, cfg in CLINICAL_COLLECTIONS.items()
}

# Reverse lookup by folder ID
FOLDER_ID_TO_KEY: Dict[str, str] = {
    cfg["folder_id"]: key
    for key, cfg in CLINICAL_COLLECTIONS.items()
    if cfg.get("folder_id")
}

# Dedicated Platform & Website Navigation Collection Mapping
PLATFORM_COLLECTION: Dict[str, Any] = {
    "folder_name": "Platform Guide",
    "collection_name": os.getenv("QDRANT_PLATFORM_COLLECTION_NAME", "platform_guide").strip() or "platform_guide",
    "display_name": "Platform & Portal Guide",
    "folder_id": os.getenv("GOOGLE_DRIVE_PLATFORM_FOLDER_ID", "").strip(),
    "category": "platform"
}

PLATFORM_FOLDER_KEYWORDS = (
    "platform", "portal", "helpdesk", "navigation",
    "website_guide", "website guide", "membership_guide", "membership guide", "user_guide", "user guide"
)
PLATFORM_FILE_KEYWORDS = ("platform", "portal", "helpdesk", "navigation")

def get_collection_config(key_or_name: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves collection configuration by key ('journals'), folder name ('Journals'), or folder ID.
    """
    if not key_or_name:
        return None
    clean = str(key_or_name).strip().lower()
    if clean in CLINICAL_COLLECTIONS:
        return CLINICAL_COLLECTIONS[clean]
    if clean in FOLDER_NAME_TO_KEY:
        return CLINICAL_COLLECTIONS[FOLDER_NAME_TO_KEY[clean]]
    raw_str = str(key_or_name).strip()
    if raw_str in FOLDER_ID_TO_KEY:
        return CLINICAL_COLLECTIONS[FOLDER_ID_TO_KEY[raw_str]]
    return None

def resolve_target_collection(
    folder_name: Optional[str] = None,
    folder_id: Optional[str] = None,
    category: Optional[str] = None,
    filename: Optional[str] = None
) -> Dict[str, Any]:
    """
    Resolves the destination Qdrant collection, collection_key, folder_display, and category
    for an incoming document from Google Drive or manual upload.
    Ensures clinical documents never leak into the default sales 'documents' collection.
    """
    default_sales_col = os.getenv("QDRANT_COLLECTION_NAME", "documents").strip() or "documents"
    platform_col = get_platform_collection_name()
    platform_folder_id = os.getenv("GOOGLE_DRIVE_PLATFORM_FOLDER_ID", PLATFORM_COLLECTION.get("folder_id", "")).strip()

    # 1. Explicit Category Checks (Sales & Platform)
    cat_clean = (category or "").strip().lower()
    if cat_clean == "sales":
        return {
            "collection_name": default_sales_col,
            "collection_key": "sales",
            "folder_display": "Sales & Course Catalog",
            "category": "sales"
        }
    if cat_clean == "platform":
        return {
            "collection_name": platform_col,
            "collection_key": "platform",
            "folder_display": PLATFORM_COLLECTION["display_name"],
            "category": "platform"
        }

    # 2. Check Match by Folder ID
    if folder_id:
        clean_fid = folder_id.strip()
        if platform_folder_id and clean_fid == platform_folder_id:
            return {
                "collection_name": platform_col,
                "collection_key": "platform",
                "folder_display": PLATFORM_COLLECTION["display_name"],
                "category": "platform"
            }
        if clean_fid in FOLDER_ID_TO_KEY:
            k = FOLDER_ID_TO_KEY[clean_fid]
            cfg = CLINICAL_COLLECTIONS[k]
            return {
                "collection_name": cfg["collection_name"],
                "collection_key": k,
                "folder_display": cfg["display_name"],
                "category": "clinical"
            }

    # 3. Check Match by Folder Name
    if folder_name:
        f_low = folder_name.strip().lower()
        if f_low in ("platform", "platform guide", "portal") or any(w in f_low for w in PLATFORM_FOLDER_KEYWORDS):
            return {
                "collection_name": platform_col,
                "collection_key": "platform",
                "folder_display": PLATFORM_COLLECTION["display_name"],
                "category": "platform"
            }
        cfg = get_collection_config(folder_name)
        if cfg:
            key = FOLDER_NAME_TO_KEY.get(f_low, "other")
            return {
                "collection_name": cfg["collection_name"],
                "collection_key": key,
                "folder_display": cfg["display_name"],
                "category": "clinical"
            }
        if "journal" in f_low:
            c = CLINICAL_COLLECTIONS["journals"]
            return {"collection_name": c["collection_name"], "collection_key": "journals", "folder_display": c["display_name"], "category": "clinical"}
        if any(w in f_low for w in ("tool", "worksheet", "exercise", "handout")):
            c = CLINICAL_COLLECTIONS["tools"]
            return {"collection_name": c["collection_name"], "collection_key": "tools", "folder_display": c["display_name"], "category": "clinical"}
        if "reflection" in f_low:
            c = CLINICAL_COLLECTIONS["reflections"]
            return {"collection_name": c["collection_name"], "collection_key": "reflections", "folder_display": c["display_name"], "category": "clinical"}
        if any(w in f_low for w in ("sales", "pricing", "catalog", "checkout", "course", "masterclass")):
            return {
                "collection_name": default_sales_col,
                "collection_key": "sales",
                "folder_display": "Sales & Course Catalog",
                "category": "sales"
            }

    # 4. Check Match by Filename heuristics
    if filename:
        fn_low = filename.lower()
        if any(w in fn_low for w in PLATFORM_FILE_KEYWORDS):
            return {
                "collection_name": platform_col,
                "collection_key": "platform",
                "folder_display": PLATFORM_COLLECTION["display_name"],
                "category": "platform"
            }
        if any(w in fn_low for w in ("pricing", "sales", "catalog", "checkout", "masterclass")):
            return {
                "collection_name": default_sales_col,
                "collection_key": "sales",
                "folder_display": "Sales & Course Catalog",
                "category": "sales"
            }
        if "journal" in fn_low:
            c = CLINICAL_COLLECTIONS["journals"]
            return {"collection_name": c["collection_name"], "collection_key": "journals", "folder_display": c["display_name"], "category": "clinical"}
        if any(w in fn_low for w in ("tool", "worksheet", "exercise", "handout")):
            c = CLINICAL_COLLECTIONS["tools"]
            return {"collection_name": c["collection_name"], "collection_key": "tools", "folder_display": c["display_name"], "category": "clinical"}
        if "reflection" in fn_low:
            c = CLINICAL_COLLECTIONS["reflections"]
            return {"collection_name": c["collection_name"], "collection_key": "reflections", "folder_display": c["display_name"], "category": "clinical"}

    # 5. Default Clinical Fallback: Always route clinical docs to clinical_knowledge_other so they are searchable
    other_cfg = CLINICAL_COLLECTIONS["other"]
    return {
        "collection_name": other_cfg["collection_name"],
        "collection_key": "other",
        "folder_display": other_cfg["display_name"],
        "category": "clinical"
    }

def get_all_clinical_collection_names() -> list[str]:
    """Returns list of all 4 Qdrant collection names."""
    return [cfg["collection_name"] for cfg in CLINICAL_COLLECTIONS.values()]


def get_platform_collection_name() -> str:
    """Returns the dedicated Qdrant collection name for Platform & Portal docs."""
    return os.getenv("QDRANT_PLATFORM_COLLECTION_NAME", PLATFORM_COLLECTION["collection_name"]).strip() or "platform_guide"
