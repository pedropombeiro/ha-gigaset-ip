"""Load the standalone web client without importing Home Assistant."""

import importlib.util
import inspect
import sys
from functools import wraps
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from aiohttp import ClientResponse

if importlib.util.find_spec("pytest_homeassistant_custom_component"):
    pytest_plugins = ["pytest_homeassistant_custom_component"]

PATH = Path(__file__).parents[1] / "custom_components/gigaset_ip/api.py"
spec = importlib.util.spec_from_file_location("gigaset_api", PATH)
api = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = api
spec.loader.exec_module(api)


@pytest.fixture
def client_api():
    return api


@pytest.fixture
def status_html():
    return (Path(__file__).parent / "fixtures/connections.html").read_text()


@pytest.fixture(autouse=True)
def aioresponses_stream_writer_compat():
    """Bridge aioresponses 0.7.9 to aiohttp 3.14's response constructor.

    Only mock response construction is affected. Remove when aioresponses
    supplies stream_writer itself. The production client is unchanged.
    """
    original = ClientResponse.__init__
    if "stream_writer" not in inspect.signature(original).parameters:
        yield
        return

    @wraps(original)
    def initialize(self, *args, **kwargs):
        kwargs.setdefault("stream_writer", Mock(output_size=0))
        original(self, *args, **kwargs)

    with patch.object(ClientResponse, "__init__", initialize):
        yield
