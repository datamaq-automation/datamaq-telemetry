import pytest

from src.domain.telemetria.exceptions import (
    FactorPotenciaInvalidoError,
    MacAddressInvalidaError,
    TensionInvalidaError,
)
from src.domain.telemetria.services import AnalizadorCalidadEnergiaService
from src.domain.telemetria.value_objects import (
    FactorPotencia,
    MacAddress,
    Tension,
)


def test_mac_address_valida():
    mac = MacAddress("d4:8c:49:f0:35:64")
    assert mac.valor == "D48C49F03564"
    assert mac.formateada() == "D4:8C:49:F0:35:64"


def test_mac_address_invalida():
    with pytest.raises(MacAddressInvalidaError):
        MacAddress("ZZ:8C:49:F0:35:64")


def test_tension_rango():
    t = Tension(220.5)
    assert t.voltios == 220.5

    with pytest.raises(TensionInvalidaError):
        Tension(-10.0)


def test_factor_potencia_rango():
    fp = FactorPotencia(0.95)
    assert fp.valor == 0.95

    with pytest.raises(FactorPotenciaInvalidoError):
        FactorPotencia(1.5)


def test_calculo_potencia_trifasica():
    total = AnalizadorCalidadEnergiaService.calcular_potencia_trifasica_activa(100.5, 200.25, 300.0)
    assert total is not None
    assert total.vatios == 600.75
