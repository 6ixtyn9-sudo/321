import pytest
from datetime import datetime

@pytest.fixture
def dummy_html_content():
    return b"<html><body>Test</body></html>"
    
@pytest.fixture
def current_time():
    return datetime.now()
