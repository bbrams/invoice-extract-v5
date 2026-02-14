"""Tests for Google Drive connector (mocked — no real API calls)."""

import os
import sys
from unittest.mock import MagicMock, patch, mock_open

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestDriveConnectorListInvoices:
    """Test listing invoices from a Drive folder."""

    @patch('core.drive.DriveConnector._build_service')
    def test_list_invoices_returns_files(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_service.files().list().execute.return_value = {
            'files': [
                {'id': '1', 'name': 'invoice.pdf', 'mimeType': 'application/pdf', 'modifiedTime': '2025-01-15'},
                {'id': '2', 'name': 'receipt.jpg', 'mimeType': 'image/jpeg', 'modifiedTime': '2025-01-14'},
            ]
        }

        from core.drive import DriveConnector
        drive = DriveConnector()
        files = drive.list_invoices('folder123')

        assert len(files) == 2
        assert files[0]['name'] == 'invoice.pdf'

    @patch('core.drive.DriveConnector._build_service')
    def test_list_invoices_empty_folder(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_service.files().list().execute.return_value = {'files': []}

        from core.drive import DriveConnector
        drive = DriveConnector()
        files = drive.list_invoices('empty_folder')

        assert files == []


class TestDriveConnectorDownload:
    """Test downloading files from Drive."""

    @patch('core.drive.DriveConnector._build_service')
    def test_download_creates_local_file(self, mock_build, tmp_path):
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        # Mock file metadata
        mock_service.files().get().execute.return_value = {'name': 'test.pdf'}

        # Mock download: simulate MediaIoBaseDownload
        mock_request = MagicMock()
        mock_service.files().get_media.return_value = mock_request

        from core.drive import DriveConnector

        with patch('googleapiclient.http.MediaIoBaseDownload') as mock_dl_class:
            mock_dl = MagicMock()
            mock_dl.next_chunk.return_value = (None, True)  # Done immediately
            mock_dl_class.return_value = mock_dl

            drive = DriveConnector()
            path = drive.download('file123', dest_dir=str(tmp_path))

        assert path == os.path.join(str(tmp_path), 'test.pdf')


class TestDriveConnectorRename:
    """Test renaming files in Drive."""

    @patch('core.drive.DriveConnector._build_service')
    def test_rename_calls_api(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_service.files().update().execute.return_value = {
            'id': 'file123',
            'name': 'AWS_#123_01-01-2025_500USD.pdf',
        }

        from core.drive import DriveConnector
        drive = DriveConnector()
        result = drive.rename('file123', 'AWS_#123_01-01-2025_500USD.pdf')

        assert result['name'] == 'AWS_#123_01-01-2025_500USD.pdf'


class TestDriveConnectorMove:
    """Test moving files between Drive folders."""

    @patch('core.drive.DriveConnector._build_service')
    def test_move_to_folder(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_service.files().get().execute.return_value = {'parents': ['old_folder']}
        mock_service.files().update().execute.return_value = {
            'id': 'file123',
            'name': 'invoice.pdf',
            'parents': ['new_folder'],
        }

        from core.drive import DriveConnector
        drive = DriveConnector()
        result = drive.move_to_folder('file123', 'new_folder')

        assert result['parents'] == ['new_folder']
