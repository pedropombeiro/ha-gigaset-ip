"""Initialize Home Assistant before pytest autoloads HTTP-related plugins."""

import homeassistant  # noqa: F401
import pytest

if __name__ == "__main__":
    raise SystemExit(pytest.main())
