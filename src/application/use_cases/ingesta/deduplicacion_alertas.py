"""src/application/use_cases/ingesta/deduplicacion_alertas.py — Evita abrir dos veces la misma alerta."""

from src.domain.telemetria.ports import RepositorioTelemetriaPort

# Tope generoso: si el listado se corta antes de llegar a la alerta abierta, se duplicaría.
LIMITE_ALERTAS_ABIERTAS = 1000


def existe_alerta_abierta(repo: RepositorioTelemetriaPort, dispositivo_id: str, tipo_alerta: str) -> bool:
    """True si el dispositivo ya tiene una alerta abierta de ese tipo.

    El filtro de persistencia guarda su estado en memoria: tras un reinicio del worker dispararía de
    nuevo un episodio que sigue activo. Consultar la base evita crear una segunda fila abierta.
    """
    abiertas = repo.listar_alertas(
        dispositivo_id=dispositivo_id,
        solo_abiertas=True,
        limite=LIMITE_ALERTAS_ABIERTAS,
    )
    return any(a.tipo_alerta == tipo_alerta for a in abiertas)
