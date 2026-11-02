"""tests/unit/test_value_objects_factories.py — Tests para Factory Methods semánticos en Value Objects."""

import pytest

from src.domain.telemetria.exceptions import MacAddressInvalidaError, TensionInvalidaError
from src.domain.telemetria.value_objects import (
    EnergiaActiva,
    EnergiaReactiva,
    FactorPotencia,
    MacAddress,
    PotenciaActiva,
    PotenciaAparente,
    PotenciaReactiva,
    Tension,
)


class TestMacAddressFactory:
    def test_desde_texto_formato_estandar(self):
        mac = MacAddress.desde_texto("ec:c9:ff:b5:7f:20")
        assert mac.valor == "ECC9FFB57F20"
        assert mac.formateada() == "EC:C9:FF:B5:7F:20"

    def test_desde_texto_con_guiones_y_espacios(self):
        mac = MacAddress.desde_texto("  EC-C9-FF-B5-7F-20  ")
        assert mac.valor == "ECC9FFB57F20"

    def test_desde_texto_con_puntos(self):
        mac = MacAddress.desde_texto("ecc9.ffb5.7f20")
        assert mac.valor == "ECC9FFB57F20"

    def test_desde_texto_invalido_lanza_error(self):
        with pytest.raises(MacAddressInvalidaError):
            MacAddress.desde_texto("ZZ:C9:FF:B5:7F:20")


class TestTensionFactory:
    def test_desde_kv(self):
        t = Tension.desde_kv(0.22)
        assert t.voltios == 220.0

    def test_desde_kv_fuera_de_rango(self):
        with pytest.raises(TensionInvalidaError):
            Tension.desde_kv(1.5)  # 1500V > 1000V


class TestPotenciasFactory:
    def test_potencia_activa_desde_kw(self):
        p = PotenciaActiva.desde_kw(15.5)
        assert p.vatios == 15500.0

    def test_potencia_reactiva_desde_kvar(self):
        q = PotenciaReactiva.desde_kvar(5.2)
        assert q.var == 5200.0

    def test_potencia_aparente_desde_kva(self):
        s = PotenciaAparente.desde_kva(20.0)
        assert s.va == 20000.0


class TestFactorPotenciaFactory:
    def test_desde_potencias_nominal(self):
        fp = FactorPotencia.desde_potencias(800.0, 1000.0)
        assert fp.valor == 0.8

    def test_desde_potencias_aparente_cero_retorna_uno(self):
        fp = FactorPotencia.desde_potencias(0.0, 0.0)
        assert fp.valor == 1.0

    def test_desde_potencias_acota_maximo(self):
        fp = FactorPotencia.desde_potencias(1200.0, 1000.0)
        assert fp.valor == 1.0

    def test_desde_potencias_acota_minimo(self):
        fp = FactorPotencia.desde_potencias(-1200.0, 1000.0)
        assert fp.valor == -1.0


class TestEnergiasFactory:
    def test_energia_activa_desde_mwh(self):
        e = EnergiaActiva.desde_mwh(1.234)
        assert e.kwh == 1234.0

    def test_energia_reactiva_desde_mvarh(self):
        e = EnergiaReactiva.desde_mvarh(0.567)
        assert e.kvarh == 567.0
