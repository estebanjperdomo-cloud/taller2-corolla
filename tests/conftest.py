import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from corolla import configuracion as config  # noqa: E402


@pytest.fixture
def rutas(tmp_path):
    """Carpeta de datos temporal, en modo prueba, para cada test."""
    return config.Rutas("prueba", tmp_path).crear()
