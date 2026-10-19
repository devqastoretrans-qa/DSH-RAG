import os
import io
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

from src.logger import log_application

load_dotenv()


class GoogleDriveService:
    """
    Modular Google Drive service handling authentication, folder discovery,
    file listing, metadata retrieval, and binary file downloads.
    """

    def __init__(
        self,
        folder_id: Optional[str] = None,
        service_account_file: Optional[str] = None,
        service_account_json: Optional[str] = None
    ):
        self.folder_id = folder_id or os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()
        self.service_account_file = service_account_file or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
        self.service_account_json = service_account_json or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        self._service = None
        self._mock_files: Optional[Dict[str, Dict[str, Any]]] = None

    def is_configured(self) -> bool:
        """Returns True if Google Drive folder ID and credentials (file or JSON env) are specified and valid."""
        if self._mock_files is not None:
            return True
        if not self.folder_id:
            return False
        if self.service_account_json:
            return True
        if self.service_account_file and Path(self.service_account_file).exists():
            return True
        return False

    def get_status_info(self) -> Dict[str, Any]:
        """Returns human-readable diagnostic status of the Drive service."""
        configured = self.is_configured()
        has_folder = bool(self.folder_id)
        has_creds = bool(self.service_account_json or (self.service_account_file and Path(self.service_account_file).exists()))
        auth_type = "EnvJSON" if self.service_account_json else ("ServiceAccountFile" if has_creds else "None")
        return {
            "configured": configured,
            "folder_id": self.folder_id if self.folder_id else None,
            "service_account_file": self.service_account_file if self.service_account_file else None,
            "has_service_account_json": bool(self.service_account_json),
            "credentials_found": has_creds,
            "auth_type": auth_type,
            "mode": "Mock/Testing" if self._mock_files is not None else ("ServiceAccount" if configured else "Unconfigured")
        }

    def _get_drive_client(self):
        if self._service is not None:
            return self._service

        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        scopes = ["https://www.googleapis.com/auth/drive.readonly"]

        if self.service_account_json:
            import json
            try:
                info = json.loads(self.service_account_json)
                creds = service_account.Credentials.from_service_account_info(
                    info,
                    scopes=scopes
                )
            except Exception as e:
                raise ValueError(f"Failed to parse GOOGLE_SERVICE_ACCOUNT_JSON: {e}")
        elif self.service_account_file and Path(self.service_account_file).exists():
            creds = service_account.Credentials.from_service_account_file(
                self.service_account_file,
                scopes=scopes
            )
        else:
            raise FileNotFoundError(
                f"Google Service Account credentials not found. Neither valid GOOGLE_SERVICE_ACCOUNT_JSON "
                f"nor file at '{self.service_account_file}' could be found. "
                "Please configure GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON."
            )

        self._service = build("drive", "v3", credentials=creds)
        log_application("INFO", f"Google Drive API client initialized for folder: {self.folder_id}")
        return self._service

    def list_pdf_files(self) -> List[Dict[str, Any]]:
        """
        Lists all non-trashed PDF files inside the configured Google Drive folder.
        Automatically discovers 'clinical' and 'sales' subfolders:
          - 'clinical_knowledge' / 'RAG_Clinical-Knowledge' -> category: 'clinical'
          - 'sales_catalog' / 'RAG_Sales' -> category: 'sales'
        If categorized subfolders exist, scans them and tags files with category.
        Falls back to root folder scanning if no subfolders exist.
        """
        if self._mock_files is not None:
            return [dict(f["meta"]) for f in self._mock_files.values()]

        if not self.is_configured():
            log_application("WARNING", "Google Drive service is not configured. Skipping Drive listing.")
            return []

        client = self._get_drive_client()

        # Step 1: Check for explicit or discovered subfolders
        categorized_folders = []

        env_clin_id = os.getenv("GOOGLE_DRIVE_CLINICAL_FOLDER_ID", "").strip()
        env_sales_id = os.getenv("GOOGLE_DRIVE_SALES_FOLDER_ID", "").strip()
        if env_clin_id:
            categorized_folders.append({"id": env_clin_id, "name": "Clinical (Env)", "category": "clinical"})
        if env_sales_id:
            categorized_folders.append({"id": env_sales_id, "name": "Sales (Env)", "category": "sales"})

        # If not explicitly set via individual env vars, auto-discover subfolders inside self.folder_id
        if not categorized_folders and self.folder_id:
            try:
                subfolders_query = (
                    f"'{self.folder_id}' in parents and "
                    f"mimeType = 'application/vnd.google-apps.folder' and "
                    f"trashed = false"
                )
                sub_res = client.files().list(
                    q=subfolders_query,
                    fields="files(id, name)",
                    pageSize=50
                ).execute()
                for sf in sub_res.get("files", []):
                    name_low = sf.get("name", "").lower()
                    if "clinical" in name_low:
                        categorized_folders.append({"id": sf["id"], "name": sf["name"], "category": "clinical"})
                    elif any(k in name_low for k in ("sales", "course", "catalog", "pricing", "masterclass")):
                        categorized_folders.append({"id": sf["id"], "name": sf["name"], "category": "sales"})
            except Exception as e:
                log_application("WARNING", f"Failed to list Drive subfolders: {e}")

        all_pdf_records = []

        # Step 2: If categorized subfolders were found, retrieve PDFs from each subfolder
        if categorized_folders:
            log_application("INFO", f"Drive: Scanning {len(categorized_folders)} categorized subfolders: {[f['name'] for f in categorized_folders]}")
            for folder_meta in categorized_folders:
                target_folder_id = folder_meta["id"]
                folder_category = folder_meta["category"]
                folder_name = folder_meta["name"]

                query = (
                    f"'{target_folder_id}' in parents and "
                    f"(mimeType = 'application/pdf' or "
                    f"mimeType = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' or "
                    f"mimeType = 'text/plain') and "
                    f"trashed = false"
                )
                res = client.files().list(
                    q=query,
                    fields="files(id, name, modifiedTime, size, version, mimeType)",
                    pageSize=100
                ).execute()
                for f in res.get("files", []):
                    fname_low = f.get("name", "").lower()
                    if any(fname_low.endswith(ext) for ext in (".pdf", ".docx", ".doc", ".txt", ".md", ".vtt", ".srt")):
                        all_pdf_records.append({
                            "id": f.get("id"),
                            "name": f.get("name"),
                            "modifiedTime": f.get("modifiedTime"),
                            "size": int(f.get("size", 0)),
                            "version": str(f.get("version", "1")),
                            "category": folder_category,
                            "folder_name": folder_name,
                            "folder_id": target_folder_id
                        })
            return all_pdf_records

        # Step 3: Fallback - if no categorized subfolders found, scan root parent folder directly
        query = (
            f"'{self.folder_id}' in parents and "
            f"(mimeType = 'application/pdf' or "
            f"mimeType = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' or "
            f"mimeType = 'text/plain') and "
            f"trashed = false"
        )
        results = client.files().list(
            q=query,
            fields="files(id, name, modifiedTime, size, version, mimeType)",
            pageSize=100
        ).execute()

        for f in results.get("files", []):
            f_name = f.get("name", "")
            f_low = f_name.lower()
            if any(f_low.endswith(ext) for ext in (".pdf", ".docx", ".doc", ".txt", ".md", ".vtt", ".srt")):
                cat = "sales" if any(k in f_low for k in ("sales", "catalog", "pricing", "checkout")) else "clinical"
                all_pdf_records.append({
                    "id": f.get("id"),
                    "name": f_name,
                    "modifiedTime": f.get("modifiedTime"),
                    "size": int(f.get("size", 0)),
                    "version": str(f.get("version", "1")),
                    "category": cat,
                    "folder_name": "Root",
                    "folder_id": self.folder_id
                })

        return all_pdf_records

    def download_file(self, file_id: str) -> bytes:
        """
        Downloads binary content of a file from Google Drive.
        """
        if self._mock_files is not None and file_id in self._mock_files:
            return self._mock_files[file_id]["content"]

        client = self._get_drive_client()
        from googleapiclient.http import MediaIoBaseDownload

        request = client.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()

        return fh.getvalue()

    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """
        Retrieves metadata for a specific file.
        """
        if self._mock_files is not None and file_id in self._mock_files:
            return dict(self._mock_files[file_id]["meta"])

        client = self._get_drive_client()
        file_meta = client.files().get(
            fileId=file_id,
            fields="id, name, modifiedTime, size, version"
        ).execute()
        return file_meta

    # Test / Mock helper methods for offline verification suite
    def set_mock_provider(self, mock_files: Dict[str, Dict[str, Any]]):
        """Sets in-memory mock files for testing."""
        self._mock_files = mock_files

    def clear_mock_provider(self):
        self._mock_files = None


_drive_service_instance: Optional[GoogleDriveService] = None


def get_drive_service() -> GoogleDriveService:
    global _drive_service_instance
    if _drive_service_instance is None:
        _drive_service_instance = GoogleDriveService()
    return _drive_service_instance
