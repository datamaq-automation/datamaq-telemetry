"""tests/unit/test_verificador_propiedad_dispositivo.py — VerificadorPropiedadDispositivo (#95).

El router de cargas usa el verificador en vez de recibir la Session. Las llamadas imperativas no pasan
acceso_plantas (igual que antes del cambio): solo se aplica el filtro de organización.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.infrastructure.fastapi.device_ownership import (
    VerificadorPropiedadDispositivo,
    get_verificador_propiedad_dispositivo,
)

CLAIMS = {"sub": "usr-1", "rol": "operador", "org": "org-1"}
PARCHE = "src.infrastructure.fastapi.device_ownership.verificar_propiedad_dispositivo"


@patch(PARCHE)
def test_exigir_delega_con_los_mismos_argumentos_y_sin_acceso_plantas(mock_verificar: MagicMock):
    db = MagicMock()
    verificador = VerificadorPropiedadDispositivo(CLAIMS, db)

    verificador.exigir("disp-1")

    mock_verificar.assert_called_once_with(claims=CLAIMS, db=db, dispositivo_id="disp-1")
    assert "acceso_plantas" not in mock_verificar.call_args.kwargs


@patch(PARCHE)
def test_exigir_propaga_el_404_del_chequeo(mock_verificar: MagicMock):
    mock_verificar.side_effect = HTTPException(status_code=404, detail="dispositivo_no_encontrado")
    verificador = VerificadorPropiedadDispositivo(CLAIMS, MagicMock())

    with pytest.raises(HTTPException) as exc:
        verificador.exigir("disp-x")

    assert exc.value.status_code == 404


@patch(PARCHE)
def test_pertenece_devuelve_true_cuando_el_chequeo_pasa(mock_verificar: MagicMock):
    mock_verificar.return_value = None
    verificador = VerificadorPropiedadDispositivo(CLAIMS, MagicMock())

    assert verificador.pertenece("disp-1") is True


@patch(PARCHE)
def test_pertenece_devuelve_false_cuando_el_chequeo_responde_404(mock_verificar: MagicMock):
    mock_verificar.side_effect = HTTPException(status_code=404, detail="dispositivo_no_encontrado")
    verificador = VerificadorPropiedadDispositivo(CLAIMS, MagicMock())

    assert verificador.pertenece("disp-ajeno") is False


def test_get_verificador_arma_el_verificador_con_claims_y_sesion():
    db = MagicMock()

    verificador = get_verificador_propiedad_dispositivo(CLAIMS, db)

    assert isinstance(verificador, VerificadorPropiedadDispositivo)
    assert verificador._claims is CLAIMS
    assert verificador._db is db
