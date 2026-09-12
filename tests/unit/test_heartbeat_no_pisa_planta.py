"""tests/unit/test_heartbeat_no_pisa_planta.py — El refresco de heartbeat de la ingesta no debe pisar planta_id con un valor cacheado obsoleto.

Ver docs de la sesión: reasignar un dispositivo (seed_cliente.py) mientras sigue transmitiendo
revertía la asignación al siguiente heartbeat, porque ResolvedorDispositivoIngesta reusaba
guardar() (sobrescribe todo el registro) con el objeto cacheado en memoria.
"""

import dataclasses
from datetime import datetime, timedelta, timezone

from src.application.use_cases.ingesta.resolvedor_dispositivo import (
    ResolvedorDispositivoIngesta,
)
from src.domain.telemetria.entities import Dispositivo
from src.domain.telemetria.value_objects import EstadoDispositivo, MacAddress


class _RepoDispSpy:
    """Registra qué método de persistencia se usó, sin permitir que actualizar_heartbeat toque planta_id."""

    def __init__(self, dispositivo: Dispositivo) -> None:
        self.dispositivos = {dispositivo.id: dispositivo}
        self.llamadas_guardar: list[str] = []
        self.llamadas_heartbeat: list[str] = []

    def obtener_por_uid(self, uid: MacAddress) -> Dispositivo | None:
        for d in self.dispositivos.values():
            if d.device_uid.valor == uid.valor:
                return d
        return None

    def obtener_por_id(self, dispositivo_id: str) -> Dispositivo | None:
        return self.dispositivos.get(dispositivo_id)

    def guardar(self, dispositivo: Dispositivo) -> Dispositivo:
        self.llamadas_guardar.append(dispositivo.id)
        # Copia, no la misma referencia: igual que el repo real (_to_entity mapea desde el
        # modelo ORM a una instancia nueva cada vez), para que mutar "la DB" después no mute
        # de rebote el objeto que quedó cacheado en ResolvedorDispositivoIngesta.
        copia = dataclasses.replace(dispositivo)
        self.dispositivos[dispositivo.id] = copia
        return copia

    def actualizar_heartbeat(
        self,
        dispositivo_id: str,
        estado: EstadoDispositivo,
        visto_por_ultima_vez,
        numero_serie=None,
        version_fw=None,
        version_hw=None,
    ) -> None:
        self.llamadas_heartbeat.append(dispositivo_id)
        # A propósito: esta firma no acepta planta_id, así que no hay forma de que el
        # refresco de heartbeat lo toque, ni siquiera por error de implementación.
        d = self.dispositivos.get(dispositivo_id)
        if d:
            d.estado = estado
            d.visto_por_ultima_vez = visto_por_ultima_vez


def _dispositivo() -> Dispositivo:
    return Dispositivo(
        id="dev-1",
        device_uid=MacAddress("AABBCCDDEEFF"),
        nombre="Powermeter-EEFF",
        planta_id="planta-a",
        estado=EstadoDispositivo.ONLINE,
    )


def _limpiar_caches() -> None:
    ResolvedorDispositivoIngesta.limpiar_cache()


def test_refresco_de_heartbeat_usa_actualizar_heartbeat_no_guardar():
    _limpiar_caches()
    dispositivo = _dispositivo()
    repo = _RepoDispSpy(dispositivo)
    t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Primer mensaje: cache-miss, dispositivo existe en "DB" -> usa guardar() (sin cambios).
    ResolvedorDispositivoIngesta.obtener_o_crear_dispositivo(
        mac_raw="AABBCCDDEEFF", dev_info=None, ahora=t0, repo_dispositivos=repo
    )
    assert repo.llamadas_guardar == ["dev-1"]
    assert repo.llamadas_heartbeat == []

    # 2. Reasignación externa simulada: otro proceso (ej. seed_cliente.py) escribe una fila
    #    nueva en la "DB" con planta_id distinto -- reemplaza el objeto en vez de mutarlo in
    #    place, para no tocar de rebote el que sigue cacheado en ResolvedorDispositivoIngesta
    #    (mismo desacople que hay en la realidad entre un proceso externo y el caché en RAM
    #    de este proceso).
    repo.dispositivos["dev-1"] = dataclasses.replace(repo.dispositivos["dev-1"], planta_id="planta-b")

    # 3. Segundo mensaje, más de 60s después: cache-hit con heartbeat vencido -> debe usar
    #    actualizar_heartbeat(), NUNCA guardar() (que pisaría planta_id con el valor cacheado
    #    "planta-a").
    t1 = t0 + timedelta(seconds=65)
    resultado = ResolvedorDispositivoIngesta.obtener_o_crear_dispositivo(
        mac_raw="AABBCCDDEEFF", dev_info=None, ahora=t1, repo_dispositivos=repo
    )

    assert repo.llamadas_guardar == ["dev-1"]  # sin cambios: no se volvió a llamar
    assert repo.llamadas_heartbeat == ["dev-1"]
    assert resultado.estado == EstadoDispositivo.ONLINE
    assert resultado.visto_por_ultima_vez == t1

    # La reasignación externa sigue intacta en la "DB": el heartbeat no la tocó.
    assert repo.dispositivos["dev-1"].planta_id == "planta-b"


def test_refresco_dentro_de_la_ventana_no_persiste_nada():
    _limpiar_caches()
    dispositivo = _dispositivo()
    repo = _RepoDispSpy(dispositivo)
    t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    ResolvedorDispositivoIngesta.obtener_o_crear_dispositivo(
        mac_raw="AABBCCDDEEFF", dev_info=None, ahora=t0, repo_dispositivos=repo
    )
    assert repo.llamadas_guardar == ["dev-1"]

    # Mensaje 30s después (dentro de la ventana de 60s): ni guardar() ni actualizar_heartbeat().
    t1 = t0 + timedelta(seconds=30)
    ResolvedorDispositivoIngesta.obtener_o_crear_dispositivo(
        mac_raw="AABBCCDDEEFF", dev_info=None, ahora=t1, repo_dispositivos=repo
    )
    assert repo.llamadas_guardar == ["dev-1"]
    assert repo.llamadas_heartbeat == []
