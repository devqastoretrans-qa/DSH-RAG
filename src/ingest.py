import os
import sys
import io
import re
import gc
import uuid
import argparse
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from src.config import CLINICAL_COLLECTIONS, get_collection_config, EMBEDDING_VECTOR_SIZE
from src.qdrant_service import get_qdrant_service
from src.embeddings import get_embedding_service
from src.document_loader import extract_document_content
from src.chunker import chunk_text, clean_document_title

load_dotenv()


def get_drive_client():
    """Initializes and returns Google Drive API client using existing service account."""
    sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json").strip()
    if not os.path.isabs(sa_path):
        sa_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), sa_path)
    
    if not os.path.exists(sa_path):
        raise FileNotFoundError(f"Service account file not found at: {sa_path}")

    creds = service_account.Credentials.from_service_account_file(
        sa_path,
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=creds)


def clean_pdf_text(text: str) -> str:
    """
    Cleans raw page text:
    - Removes isolated page numbers (e.g. 'Page 1 of 2', '1 / 3', standalone numbers)
    - Fixes hyphenated line-breaks (e.g. 'dysregu-\nlation' -> 'dysregulation')
    - Collapses excessive spaces and empty lines
    """
    if not text:
        return ""

    # Fix hyphenation across line breaks
    text = re.sub(r'(\b\w+)-\n(\w+\b)', r'\1\2', text)

    # Remove standalone page numbers or headers
    text = re.sub(r'(?i)\bpage\s+\d+(\s+of\s+\d+)?\b', '', text)
    text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)

    # Normalize whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def list_drive_pdfs_recursive(service, folder_id: str, top_folder_key: str) -> List[Dict[str, Any]]:
    """
    Recursively discovers all PDFs inside folder_id.
    Nested subfolder files map to top_folder_key.
    """
    results = []
    query = f"'{folder_id}' in parents and trashed = false"
    items = service.files().list(
        q=query,
        fields="files(id, name, mimeType, size, modifiedTime, md5Checksum, webViewLink)",
        pageSize=100
    ).execute().get("files", [])

    for item in items:
        mime = item.get("mimeType", "")
        if mime == "application/vnd.google-apps.folder":
            # Recurse into nested folder
            results.extend(list_drive_pdfs_recursive(service, item["id"], top_folder_key))
        elif mime == "application/pdf" or item.get("name", "").lower().endswith(".pdf"):
            item["top_folder_key"] = top_folder_key
            results.append(item)
    return results


def get_stored_files_in_collection(qdrant, collection_name: str) -> Dict[str, Dict[str, Any]]:
    """
    Retrieves a dictionary of all currently indexed files in a Qdrant collection:
    {drive_file_id: {"md5Checksum": ..., "modified_time": ..., "point_count": ...}}
    """
    stored = {}
    qdrant.ensure_collection(vector_size=EMBEDDING_VECTOR_SIZE, collection_name=collection_name)
    
    offset = None
    while True:
        try:
            scroll_res = qdrant.client.scroll(
                collection_name=collection_name,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False
            )
            points, next_offset = scroll_res
            for p in points:
                fid = p.payload.get("drive_file_id")
                if fid:
                    if fid not in stored:
                        stored[fid] = {
                            "file_name": p.payload.get("file_name", ""),
                            "md5Checksum": p.payload.get("md5Checksum") or p.payload.get("md5_checksum", ""),
                            "modified_time": p.payload.get("modified_time", ""),
                            "point_count": 0
                        }
                    stored[fid]["point_count"] += 1
            if not next_offset:
                break
            offset = next_offset
        except Exception:
            break

    return stored


def download_drive_file_bytes(service, file_id: str) -> bytes:
    """Streams file content into memory buffer."""
    req = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buf.seek(0)
    data = buf.read()
    buf.close()
    return data


def ingest_single_pdf(
    service,
    file_info: Dict[str, Any],
    collection_cfg: Dict[str, Any],
    qdrant,
    embedder,
    chunk_size: int = 150,
    chunk_overlap: int = 25
) -> int:
    """
    Downloads, extracts, chunks, embeds and upserts a single PDF into its target collection.
    Memory footprint is kept strictly minimal.
    """
    file_id = file_info["id"]
    file_name = file_info["name"]
    collection_name = collection_cfg["collection_name"]
    folder_display = collection_cfg["display_name"]
    col_key = collection_cfg.get("key", "")
    modified_time = file_info.get("modifiedTime", "")
    md5_checksum = file_info.get("md5Checksum", "")
    drive_url = file_info.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"

    print(f"  -> Ingesting '{file_name}' (ID: {file_id}, size: {file_info.get('size')} B)...")

    # 1. Download
    pdf_bytes = download_drive_file_bytes(service, file_id)

    # 2. Extract text page by page
    pages = extract_document_content(pdf_bytes, filename=file_name)
    del pdf_bytes
    gc.collect()

    if not pages:
        print(f"     [WARNING] No extractable text found in '{file_name}' (needs OCR or empty). Skipping.")
        return 0

    # 3. Clean text and chunk per page to respect page boundaries
    clean_title = clean_document_title(file_name)
    all_chunks = []
    global_chunk_idx = 0

    for page_dict in pages:
        p_num = page_dict.get("page_number", 1)
        raw_text = page_dict.get("text", "")
        cleaned_text = clean_pdf_text(raw_text)
        if not cleaned_text:
            continue

        page_chunks = chunk_text(cleaned_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        for c_idx, c_text in enumerate(page_chunks):
            # Deterministic UUID5 point ID from drive_file_id + global_chunk_idx
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{file_id}_{global_chunk_idx}"))
            
            payload = {
                "collection_key": col_key,
                "folder_display": folder_display,
                "file_name": file_name,
                "filename": file_name,
                "document_name": clean_title,
                "drive_file_id": file_id,
                "drive_url": drive_url,
                "page_number": p_num,
                "page": p_num,
                "chunk_index": global_chunk_idx,
                "text": c_text,
                "raw_text": c_text,
                "modified_time": modified_time,
                "md5Checksum": md5_checksum,
                "md5_checksum": md5_checksum,
                "category": "clinical",
                "status": "READY"
            }
            all_chunks.append((point_id, c_text, payload))
            global_chunk_idx += 1

    if not all_chunks:
        print(f"     [WARNING] Zero chunks produced for '{file_name}'.")
        return 0

    # 4. Embed chunks
    texts_to_embed = [item[1] for item in all_chunks]
    vectors = embedder.embed_documents(texts_to_embed)

    # 5. Prepare points and batch upsert
    point_ids = [item[0] for item in all_chunks]
    payloads = [item[2] for item in all_chunks]

    qdrant.store_vectors(
        chunks=payloads,
        vectors=vectors,
        vector_size=EMBEDDING_VECTOR_SIZE,
        collection_name=collection_name,
        point_ids=point_ids
    )

    print(f"     [SUCCESS] Upserted {len(point_ids)} points to '{collection_name}' (ID: {file_id}).")
    del all_chunks, texts_to_embed, vectors, payloads, point_ids
    gc.collect()
    return global_chunk_idx


def sync_clinical_folder(
    folder_key: str,
    full_resync: bool = False
) -> Dict[str, Any]:
    """
    Performs full or incremental synchronization for a single clinical subfolder.
    """
    col_cfg = get_collection_config(folder_key)
    if not col_cfg:
        raise ValueError(f"Unknown clinical folder key: '{folder_key}'")

    col_cfg["key"] = folder_key
    collection_name = col_cfg["collection_name"]
    folder_id = col_cfg["folder_id"]
    display_name = col_cfg["display_name"]

    print(f"\n=======================================================")
    print(f"Syncing: {display_name} -> Collection: '{collection_name}'")
    print(f"=======================================================")

    service = get_drive_client()
    qdrant = get_qdrant_service()
    embedder = get_embedding_service()

    # Step 1: Ensure collection and payload indexes exist
    qdrant.ensure_collection(vector_size=EMBEDDING_VECTOR_SIZE, collection_name=collection_name)
    qdrant.create_payload_indexes(collection_name=collection_name)

    # Step 2: Query Drive for all PDFs recursively
    drive_pdfs = list_drive_pdfs_recursive(service, folder_id, folder_key)
    print(f"Drive: Found {len(drive_pdfs)} PDF(s) in '{col_cfg['folder_name']}'.")

    # Step 3: Get current files stored in Qdrant
    stored_files = get_stored_files_in_collection(qdrant, collection_name)
    print(f"Qdrant: Currently storing {len(stored_files)} distinct file(s) in '{collection_name}'.")

    drive_file_ids = {f["id"]: f for f in drive_pdfs}

    # Step 4: Handle deleted files (in Qdrant but removed from Drive)
    deleted_count = 0
    for stored_fid, meta in stored_files.items():
        if stored_fid not in drive_file_ids:
            print(f"  [DELETED] File '{meta.get('file_name')}' (ID: {stored_fid}) removed from Drive. Deleting vectors...")
            qdrant.delete_drive_file_vectors(stored_fid, collection_name=collection_name)
            deleted_count += 1

    # Step 5: Process Drive files (incremental check)
    ingested_count = 0
    skipped_count = 0

    chunk_size = int(os.getenv("CHUNK_SIZE", "150"))
    chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "25"))

    for pdf in drive_pdfs:
        fid = pdf["id"]
        fname = pdf["name"]
        curr_md5 = pdf.get("md5Checksum", "")
        curr_mod = pdf.get("modifiedTime", "")

        needs_ingest = False
        if full_resync:
            needs_ingest = True
        elif fid not in stored_files:
            needs_ingest = True
        else:
            stored_meta = stored_files[fid]
            stored_md5 = stored_meta.get("md5Checksum", "")
            stored_mod = stored_meta.get("modified_time", "")
            if curr_md5 and stored_md5 and curr_md5 != stored_md5:
                print(f"  [CHANGED] MD5 mismatch for '{fname}'. Re-ingesting...")
                needs_ingest = True
            elif curr_mod and stored_mod and curr_mod != stored_mod:
                print(f"  [CHANGED] Modified time mismatch for '{fname}'. Re-ingesting...")
                needs_ingest = True

        if needs_ingest:
            # If changed/re-ingesting, delete old points first
            if fid in stored_files:
                qdrant.delete_drive_file_vectors(fid, collection_name=collection_name)
            
            pts = ingest_single_pdf(
                service=service,
                file_info=pdf,
                collection_cfg=col_cfg,
                qdrant=qdrant,
                embedder=embedder,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap
            )
            ingested_count += 1
        else:
            print(f"  [SKIPPED] '{fname}' is unchanged (MD5 & time match).")
            skipped_count += 1

    final_count = qdrant.client.count(collection_name=collection_name).count
    print(f"Finished sync for '{collection_name}': {ingested_count} ingested, {skipped_count} unchanged, {deleted_count} deleted.")
    print(f"Total points in '{collection_name}': {final_count}\n")

    return {
        "folder_key": folder_key,
        "collection_name": collection_name,
        "total_points": final_count,
        "ingested": ingested_count,
        "skipped": skipped_count,
        "deleted": deleted_count
    }


def main():
    parser = argparse.ArgumentParser(description="Clinical Knowledge Google Drive Ingestion & Sync CLI")
    parser.add_argument(
        "--folder",
        type=str,
        default="all",
        choices=["all", "journals", "other", "tools", "reflections"],
        help="Target folder to ingest (default: all)"
    )
    parser.add_argument(
        "--full-resync",
        action="store_true",
        help="Force full re-sync and re-ingest all files regardless of MD5/modifiedTime"
    )

    args = parser.parse_args()

    target_folders = list(CLINICAL_COLLECTIONS.keys()) if args.folder == "all" else [args.folder]
    results = {}

    print(f"Starting Ingestion CLI | Target Folders: {target_folders} | Full Resync: {args.full_resync}")
    for f_key in target_folders:
        res = sync_clinical_folder(f_key, full_resync=args.full_resync)
        results[f_key] = res

    print("\n" + "=" * 60)
    print("INGESTION SUMMARY")
    print("=" * 60)
    for k, v in results.items():
        print(f"[{k.upper()}] Collection: '{v['collection_name']}' | Points: {v['total_points']} | Ingested: {v['ingested']} | Skipped: {v['skipped']}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
