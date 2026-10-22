"""tests/unit/test_auditar_produccion_uc.py — Caso de uso de auditoría de producción (solo lectura)."""

import pytest

from src.application.ports.auditoria_produccion_port import AuditoriaProduccionPort
from src.application.use_cases.auditar_produccion import AuditarProduccionUseCase


class _PuertoFalso(AuditoriaProduccionPort):
    def __init__(self) -> None:
        self.consultas: list[str] = []

    def consultar(self, nombre: str) -> list[dict[str, object]]:
        self.consultas.append(nombre)
        return [{"nombre": nombre, "filas": 1}]

    def entorno_remoto(self) -> dict[str, object]:
        return {"otp_hmac_key_longitud": 32, "app_env": "production"}


def test_ejecuta_los_tres_checks_y_devuelve_claves_ordenadas():
    puerto = _PuertoFalso()
    resultado = AuditarProduccionUseCase(puerto).ejecutar()
    assert list(resultado.keys()) == sorted(resultado.keys())
    assert set(resultado.keys()) == {
        "auditoria_cambio_contrasena",
        "cobertura_telemetria",
        "entorno_remoto",
        "thd_i_agregados",
    }
    assert sorted(puerto.consultas) == ["auditoria_cambio_contrasena", "cobertura_telemetria", "thd_i_agregados"]


def test_entorno_remoto_se_devuelve_tal_cual_lo_reporta_el_puerto():
    resultado = AuditarProduccionUseCase(_PuertoFalso()).ejecutar()
    assert resultado["entorno_remoto"] == {"otp_hmac_key_longitud": 32, "app_env": "production"}


def test_no_contiene_sql_ni_nombres_fuera_de_los_checks_permitidos():
    puerto = _PuertoFalso()
    AuditarProduccionUseCase(puerto).ejecutar()
    assert all(
        nombre in {"thd_i_agregados", "auditoria_cambio_contrasena", "cobertura_telemetria"}
        for nombre in puerto.consultas
    )


def test_falla_del_puerto_se_propaga_sin_resultado_parcial():
    class _Roto(_PuertoFalso):
        def consultar(self, nombre: str) -> list[dict[str, object]]:
            raise RuntimeError("ssh falló")

    with pytest.raises(RuntimeError, match="ssh falló"):
        AuditarProduccionUseCase(_Roto()).ejecutar()
