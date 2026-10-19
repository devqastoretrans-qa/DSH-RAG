import os
import shutil
import sqlite3
from pathlib import Path

from src.qdrant_service import get_qdrant_service
from src.ingestion_tracker import get_ingestion_tracker
from src.semantic_cache import get_semantic_cache
from src.conversation_memory import get_conversation_memory

def wipe_all():
    print("=" * 60)
    print("PURGING ALL DATA: QDRANT VECTORS, DOCUMENTS & TRACKER")
    print("=" * 60)

    # 1. Purge Qdrant vectors
    qdrant = get_qdrant_service()
    col_name = qdrant.collection_name
    print(f"\n1. Clearing Qdrant collection '{col_name}'...")
    try:
        from qdrant_client.models import FilterSelector, Filter
        qdrant.client.delete(
            collection_name=col_name,
            points_selector=FilterSelector(filter=Filter())
        )
        print(" -> All vector points deleted.")
    except Exception as e:
        print(f" -> Notice during deletion: {e}")

    qdrant.ensure_collection(vector_size=384)
    info = qdrant.client.get_collection(col_name)
    print(f" -> Qdrant points count is now: {info.points_count}")

    # 2. Clear Ingestion Tracker Database
    tracker_db = Path("ingestion_tracker.db")
    if tracker_db.exists():
        print("\n2. Clearing Ingestion Tracker SQLite database...")
        conn = sqlite3.connect(str(tracker_db))
        conn.execute("DELETE FROM documents")
        conn.commit()
        conn.close()
        print(" -> Tracker records cleared.")

    # 3. Clear all files inside documents folder
    docs_dir = Path("documents")
    print(f"\n3. Cleaning files in '{docs_dir}'...")
    if docs_dir.exists():
        for item in docs_dir.iterdir():
            if item.is_file():
                try:
                    item.unlink()
                    print(f" -> Deleted file: {item.name}")
                except Exception as e:
                    print(f" -> Could not delete {item.name}: {e}")
            elif item.is_dir():
                # Inside subfolders: clinical_knowledge, sales_catalog, storage
                for sub_file in item.iterdir():
                    if sub_file.is_file():
                        try:
                            sub_file.unlink()
                            print(f" -> Deleted {item.name}/{sub_file.name}")
                        except Exception as e:
                            print(f" -> Could not delete {item.name}/{sub_file.name}: {e}")

    # Ensure empty subfolders exist
    (docs_dir / "clinical_knowledge").mkdir(parents=True, exist_ok=True)
    (docs_dir / "sales_catalog").mkdir(parents=True, exist_ok=True)
    (docs_dir / "storage").mkdir(parents=True, exist_ok=True)
    print(" -> Folders clinical_knowledge/, sales_catalog/, and storage/ are present and EMPTY.")

    # 4. Clear Caches & Memory
    print("\n4. Clearing Semantic Cache and Conversation Memory...")
    get_semantic_cache().clear()
    get_conversation_memory().clear()
    print(" -> Caches and memory cleared.")

    print("\n" + "=" * 60)
    print("COMPLETE: Knowledge base is 100% clean and ready for fresh Drive sync.")
    print("=" * 60)

if __name__ == "__main__":
    wipe_all()
