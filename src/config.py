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

def get_collection_config(key_or_name: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves collection configuration by key ('journals') or folder name ('Journals').
    """
    clean = key_or_name.strip().lower()
    if clean in CLINICAL_COLLECTIONS:
        return CLINICAL_COLLECTIONS[clean]
    if clean in FOLDER_NAME_TO_KEY:
        return CLINICAL_COLLECTIONS[FOLDER_NAME_TO_KEY[clean]]
    return None

def get_all_clinical_collection_names() -> list[str]:
    """Returns list of all 4 Qdrant collection names."""
    return [cfg["collection_name"] for cfg in CLINICAL_COLLECTIONS.values()]
