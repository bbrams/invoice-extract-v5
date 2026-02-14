"""Shared test configuration and fixtures."""

import os
import pytest

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures')


@pytest.fixture
def fixtures_dir():
    return FIXTURES_DIR


def load_fixture(name: str) -> str:
    """Load a text fixture file."""
    path = os.path.join(FIXTURES_DIR, name)
    with open(path, encoding='utf-8') as f:
        return f.read()


@pytest.fixture
def etisalat_text():
    return load_fixture('etisalat_sample.txt')


@pytest.fixture
def aws_text():
    return load_fixture('aws_sample.txt')


@pytest.fixture
def zoho_text():
    return load_fixture('zoho_sample.txt')


@pytest.fixture
def cursor_text():
    return load_fixture('cursor_sample.txt')


@pytest.fixture
def hilton_text():
    return load_fixture('hilton_sample.txt')


@pytest.fixture
def du_text():
    return load_fixture('du_sample.txt')


@pytest.fixture
def french_text():
    return load_fixture('french_invoice_sample.txt')


@pytest.fixture
def webkul_text():
    return load_fixture('webkul_sample.txt')
