"""Prueba de integración end-to-end del buffer en RAM de telemetría en vivo.

A diferencia de `tests/unit/test_buffer_telemetria_en_vivo.py` (que testea el adapter aislado)
y de los tests de `test_use_cases.py` (que usan un fake del puerto), esta prueba ejercita el
wiring de producción real: levanta la app con su `lifespan` (que suscribe
`global_telemetria_buffer.agregar` al `global_event_broadcaster`, igual que hace
`server.py` con el listener MQTT real), simula una lectura `inst` llegando por el broadcaster
—tal como la publicaría `IngestarTelemetriaUseCase` al recibir un mensaje MQTT—, y confirma que
el endpoint REST que el frontend ya consume en cada F5
(`GET /api/telemetria/instantaneous/{device_id}`) la devuelve mezclada con el histórico de BD,
sin requerir MySQL ni un broker MQTT reales.
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.domain.telemetria.entities import Dispositivo, LecturaInstantanea, MedicionFase
from src.domain.telemetria.ports import RepositorioDispositivosPort, RepositorioTelemetriaPort
from src.domain.telemetria.value_objects import MacAddress, PotenciaActiva
from src.infrastructure.fastapi.dependencies import (
    get_telemetria_use_case,
    get_usuario_actual,
    global_event_broadcaster,
    global_telemetria_buffer,
)
from src.infrastructure.fastapi.server import create_app


class _RepoDispositivosFake(RepositorioDispositivosPort):
    def __init__(self, dispositivo: Dispositivo):
        self._dispositivo = dispositivo

    def obtener_por_id(self, dispositivo_id: str) -> Dispositivo | None:
        return self._dispositivo if dispositivo_id == self._dispositivo.id else None

    def obtener_por_uid(self, uid: MacAddress) -> Dispositivo | None:
        return self._dispositivo if uid.valor == self._dispositivo.device_uid.valor else None

    def listar(self, planta_id: str | None = None) -> list[Dispositivo]:
        return [self._dispositivo]

    def contar_por_organizacion(self, organizacion_id: str) -> int:
        return 1

    def guardar(self, dispositivo: Dispositivo) -> Dispositivo:
        return dispositivo


class _RepoTelemetriaFakeSoloDb(RepositorioTelemetriaPort):
    """Simula la BD: solo contiene lo que ya se persistió, nunca lo que llega por el buffer."""

    def __init__(self, instantaneas: list[LecturaInstantanea]):
        self._instantaneas = instantaneas

    def guardar_instantanea(self, lectura: LecturaInstantanea) -> None:
        self._instantaneas.append(lectura)

    def guardar_energia(self, acumulado: object) -> None:
        pass

    def guardar_log_estado(self, log: object) -> None:
        pass

    def guardar_alerta(self, alerta: object) -> None:
        pass

    def listar_alertas(self, **kwargs: object) -> list:
        return []

    def obtener_alerta_por_id(self, alerta_id: int) -> None:
        return None

    def obtener_ultima_instantanea(self, dispositivo_id: str) -> LecturaInstantanea | None:
        return self._instantaneas[-1] if self._instantaneas else None

    def obtener_ultimo_acumulado(self, dispositivo_id: str) -> None:
        return None

    def listar_instantaneas(
        self, dispositivo_id: str, limite: int, desde: datetime | None = None
    ) -> list[LecturaInstantanea]:
        return [i for i in self._instantaneas if i.dispositivo_id == dispositivo_id][:limite]

    def listar_energias(self, dispositivo_id: str, limite: int, desde: datetime | None = None) -> list:
        return []

    def listar_acumulados_para_agregacion(self, dispositivo_id: str, desde: datetime | None = None) -> list:
        return []

    def purgar_instantaneas_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        return 0

    def purgar_energias_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        return 0

    def purgar_status_logs_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        return 0

    def purgar_alertas_resueltas_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        return 0


def test_recarga_de_pagina_recupera_lectura_en_vivo_no_persistida_todavia():
    dispositivo = Dispositivo(id="dev-e2e-1", device_uid=MacAddress("D48C49F03564"), nombre="Medidor E2E")

    # "BD": solo tiene la lectura de hace 4 minutos (la última que pasó el downsampling de 300s).
    persistida = LecturaInstantanea(
        id=1,
        dispositivo_id=dispositivo.id,
        registrado_en=datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc),
        fase_r=MedicionFase(),
        fase_s=MedicionFase(),
        fase_t=MedicionFase(),
        potencia_activa_total=PotenciaActiva(700.0),
    )
    repo_telem = _RepoTelemetriaFakeSoloDb([persistida])
    repo_disp = _RepoDispositivosFake(dispositivo)

    app = create_app()
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "user-test", "rol": "operador"}
    app.dependency_overrides[get_telemetria_use_case] = lambda: ConsultarTelemetriaUseCase(
        repo_telem, repo_disp, buffer_en_vivo=global_telemetria_buffer
    )

    # `with` dispara el lifespan real de server.py, que suscribe
    # global_telemetria_buffer.agregar al broadcaster (igual que en producción).
    with TestClient(app) as client:
        # Antes de que llegue nada en vivo: la respuesta es solo lo persistido en "BD".
        respuesta_inicial = client.get("/api/telemetria/instantaneous/dev-e2e-1?hours=1")
        assert respuesta_inicial.status_code == 200
        assert len(respuesta_inicial.json()) == 1

        # Simula lo que IngestarTelemetriaUseCase hace al recibir un paquete MQTT `inst`:
        # llama publicar_telemetria_en_vivo(topico, dto_normalizado) en el broadcaster global.
        # Todavía no pasaron 300s, así que esta lectura NO está (ni estaría) en la "BD".
        global_event_broadcaster.publicar_telemetria_en_vivo(
            "m/wifi/D48C49F03564/inst",
            {
                "dispositivo_id": "dev-e2e-1",
                "registrado_en": "2026-09-02T12:03:00Z",
                "fase_r": {"voltage_V": 224.5},
                "fase_s": {"voltage_V": 223.1},
                "fase_t": {"voltage_V": 225.0},
                "potencia_activa_total_W": 8080.0,
            },
        )

        # Simula un F5: el frontend vuelve a llamar exactamente el mismo endpoint REST.
        respuesta_tras_recarga = client.get("/api/telemetria/instantaneous/dev-e2e-1?hours=1")

    assert respuesta_tras_recarga.status_code == 200
    datos = respuesta_tras_recarga.json()
    assert len(datos) == 2
    # La lectura en vivo (más reciente) aparece primero.
    assert datos[0]["registrado_en"] == "2026-09-02T12:03:00Z"
    assert datos[0]["potencia_activa_total_W"] == 8080.0
    assert datos[1]["registrado_en"] == "2026-09-02T12:00:00Z"
