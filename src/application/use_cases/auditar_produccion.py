"""src/application/use_cases/auditar_produccion.py — Auditoría de producción de solo lectura.

Orquesta los checks permitidos a través del puerto. No contiene SQL: los nombres de los checks
son la allowlist que el adaptador resuelve a consultas fijas.
"""

from src.application.ports.auditoria_produccion_port import AuditoriaProduccionPort

CHECKS_CONSULTA: tuple[str, ...] = ("auditoria_cambio_contrasena", "cobertura_telemetria", "thd_i_agregados")


class AuditarProduccionUseCase:
    def __init__(self, puerto: AuditoriaProduccionPort) -> None:
        self._puerto = puerto

    def ejecutar(self) -> dict[str, object]:
        resultado: dict[str, object] = {nombre: self._puerto.consultar(nombre) for nombre in CHECKS_CONSULTA}
        resultado["entorno_remoto"] = self._puerto.entorno_remoto()
        return {clave: resultado[clave] for clave in sorted(resultado)}
