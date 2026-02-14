"""
Google Drive integration for invoice processing.

Supports two authentication modes:
1. Service Account (server / Cloud Functions) - uses GOOGLE_APPLICATION_CREDENTIALS
2. OAuth2 user credentials (local CLI) - opens browser for consent, caches token

Usage:
  # List invoices in a Drive folder
  connector = DriveConnector()
  files = connector.list_invoices(folder_id="1AbC...")

  # Download a file
  path = connector.download(file_id="1XyZ...", dest_dir="/tmp")

  # Rename a file in Drive
  connector.rename(file_id="1XyZ...", new_name="AWS_#123_01-02-2025_500USD.pdf")
"""

import io
import logging
import os
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

# OAuth scopes needed for Drive read + rename
SCOPES = ['https://www.googleapis.com/auth/drive']

# Supported invoice MIME types
INVOICE_MIMES = {
    'application/pdf',
    'image/jpeg',
    'image/png',
    'image/tiff',
    'image/bmp',
}

_CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', 'config')
_TOKEN_PATH = os.path.join(_CONFIG_DIR, 'drive_token.json')
_CREDENTIALS_PATH = os.path.join(_CONFIG_DIR, 'credentials.json')


class DriveConnector:
    """Google Drive connector for listing, downloading, and renaming invoice files."""

    def __init__(self, credentials_path: Optional[str] = None):
        self.service = self._build_service(credentials_path)

    @staticmethod
    def _build_service(credentials_path: Optional[str] = None):
        """
        Build Drive API service with auto-detected credentials:
        1. Service account (GOOGLE_APPLICATION_CREDENTIALS env var)
        2. OAuth2 user flow (config/credentials.json + cached token)
        """
        from googleapiclient.discovery import build

        # Try service account first (Cloud Functions / server)
        if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'],
                scopes=SCOPES,
            )
            logger.info("Drive: authenticated via service account")
            return build('drive', 'v3', credentials=creds)

        # OAuth2 user flow (local CLI)
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request

        creds = None
        if os.path.exists(_TOKEN_PATH):
            creds = Credentials.from_authorized_user_file(_TOKEN_PATH, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                creds_file = credentials_path or _CREDENTIALS_PATH
                if not os.path.exists(creds_file):
                    raise FileNotFoundError(
                        f"OAuth credentials not found at {creds_file}.\n"
                        "Download from Google Cloud Console > APIs & Services > Credentials > "
                        "OAuth 2.0 Client IDs > Download JSON, then save as config/credentials.json"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
                creds = flow.run_local_server(port=0)

            # Cache the token for next time
            os.makedirs(os.path.dirname(_TOKEN_PATH), exist_ok=True)
            with open(_TOKEN_PATH, 'w') as f:
                f.write(creds.to_json())
            logger.info("Drive: OAuth token cached")

        logger.info("Drive: authenticated via OAuth2")
        return build('drive', 'v3', credentials=creds)

    def list_invoices(
        self,
        folder_id: str,
        max_results: int = 100,
    ) -> list[dict]:
        """
        List invoice files (PDF, images) in a Drive folder.
        Returns list of {id, name, mimeType, modifiedTime}.
        """
        mime_filter = " or ".join(f"mimeType='{m}'" for m in INVOICE_MIMES)
        query = f"'{folder_id}' in parents and ({mime_filter}) and trashed=false"

        results = self.service.files().list(
            q=query,
            pageSize=max_results,
            fields="files(id, name, mimeType, modifiedTime)",
            orderBy="modifiedTime desc",
        ).execute()

        files = results.get('files', [])
        logger.info(f"Drive: found {len(files)} invoice(s) in folder {folder_id}")
        return files

    def download(
        self,
        file_id: str,
        dest_dir: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> str:
        """
        Download a file from Drive to a local path.
        Returns the local file path.
        """
        from googleapiclient.http import MediaIoBaseDownload

        # Get file metadata if filename not provided
        if not filename:
            meta = self.service.files().get(fileId=file_id, fields="name").execute()
            filename = meta['name']

        if dest_dir is None:
            dest_dir = tempfile.mkdtemp(prefix="invoice_")

        local_path = os.path.join(dest_dir, filename)

        request = self.service.files().get_media(fileId=file_id)
        with open(local_path, 'wb') as f:
            downloader = MediaIoBaseDownload(io.FileIO(f.fileno(), 'wb'), request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

        logger.info(f"Drive: downloaded {filename} -> {local_path}")
        return local_path

    def rename(self, file_id: str, new_name: str) -> dict:
        """
        Rename a file in Drive.
        Returns updated file metadata.
        """
        result = self.service.files().update(
            fileId=file_id,
            body={"name": new_name},
            fields="id, name",
        ).execute()

        logger.info(f"Drive: renamed {file_id} -> {new_name}")
        return result

    def move_to_folder(self, file_id: str, target_folder_id: str) -> dict:
        """
        Move a file to a different Drive folder.
        Useful for organizing processed invoices.
        """
        # Get current parents
        file = self.service.files().get(
            fileId=file_id, fields='parents'
        ).execute()
        previous_parents = ",".join(file.get('parents', []))

        result = self.service.files().update(
            fileId=file_id,
            addParents=target_folder_id,
            removeParents=previous_parents,
            fields='id, name, parents',
        ).execute()

        logger.info(f"Drive: moved {file_id} to folder {target_folder_id}")
        return result
