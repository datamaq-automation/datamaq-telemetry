"""src/application/use_cases/caracterizar_carga.py."""

import uuid
from datetime import datetime, timedelta, timezone

from src.application.dtos.carga_dto import CampanaCreateDTO, CampanaResponseDTO
from src.application.mappers.carga_mapper import CampanaMapper
from src.application.use_cases.ingesta.registro_campanas import RegistroCampanasActivas
from src.domain.cargas.entities import CampanaCaracterizacion
from src.domain.cargas.exceptions import (
    CampanaEnCursoError,
    CampanaNoEncontradaError,
    CampanaYaCerradaError,
    CargaNoEncontradaError,
)
from src.domain.cargas.ports import (
    ComandoRafagaPort,
    RepositorioCampanasPort,
    RepositorioCargasPort,
)
from src.domain.cargas.servicios.calibrador_firma import CalibradorFirmaService
from src.domain.cargas.value_objects import EstadoCampana, TipoCampana
from src.domain.telemetria.exceptions import DispositivoNoEncontradoError
from src.domain.telemetria.ports import RepositorioDispositivosPort


class CaracterizarCargaUseCase:
    """Abre, sostiene y cierra campañas de caracterización a alta resolución.

    Resuelve por instrumentación un problema que la matemática no puede: a 300 s de
    cadencia, un encendido de dos minutos nunca fue medido, y ningún algoritmo puede
    recuperar una muestra que no existe. La campaña pone el medidor en ráfaga durante
    una ventana acotada y guarda todo lo que llega, sin alterar la cadencia permanente.

    La ráfaga del firmware (`realtime_sync_mode`) se agota sola: su parámetro es una
    **duración**, no un período. Por eso `renovar_rafagas` tiene que llamarse
    periódicamente mientras la campaña siga viva, y por eso una campaña olvidada se
    apaga sola en vez de dejar al medidor publicando para siempre.
    """

    SEGUNDOS_RAFAGA = 120
    """Duración que se le pide al medidor en cada renovación. Coincide con la que ya usa
    el heartbeat del WebSocket; el bucle de campañas renueva más seguido que esto."""

    def __init__(
        self,
        repo_campanas: RepositorioCampanasPort,
        repo_cargas: RepositorioCargasPort,
        repo_dispositivos: RepositorioDispositivosPort,
        registro: RegistroCampanasActivas,
        comando_rafaga: ComandoRafagaPort | None = None,
    ) -> None:
        self.repo_campanas = repo_campanas
        self.repo_cargas = repo_cargas
        self.repo_dispositivos = repo_dispositivos
        self.registro = registro
        self.comando_rafaga = comando_rafaga

    def _uid_de(self, dispositivo_id: str) -> str:
        dispositivo = self.repo_dispositivos.obtener_por_id(dispositivo_id)
        if dispositivo is None:
            raise DispositivoNoEncontradoError(f"Dispositivo '{dispositivo_id}' no encontrado.")
        return dispositivo.device_uid.valor

    def _pedir_rafaga(self, device_uid: str) -> bool:
        if self.comando_rafaga is None:
            return False
        return self.comando_rafaga.activar_rafaga(device_uid, self.SEGUNDOS_RAFAGA)

    def _iniciar(self, dto: CampanaCreateDTO, tipo: TipoCampana, usuario_id: str | None) -> CampanaResponseDTO:
        device_uid = self._uid_de(dto.dispositivo_id)

        if dto.carga_id is not None and self.repo_cargas.obtener_por_id(dto.carga_id) is None:
            raise CargaNoEncontradaError(f"Carga '{dto.carga_id}' no encontrada.")

        en_curso = self.repo_campanas.obtener_en_curso_por_dispositivo(dto.dispositivo_id)
        if en_curso is not None and not en_curso.esta_vencida():
            raise CampanaEnCursoError(
                f"El dispositivo '{dto.dispositivo_id}' ya tiene la campaña '{en_curso.id}' en curso. "
                "Dos campañas sobre el mismo medidor miden la misma señal y ninguna podría atribuirse su parte."
            )

        ahora = datetime.now(timezone.utc)
        campana = CampanaCaracterizacion(
            id=str(uuid.uuid4()),
            dispositivo_id=dto.dispositivo_id,
            carga_id=dto.carga_id,
            tipo=tipo,
            inicio_at=ahora,
            fin_planificado_at=ahora + timedelta(seconds=dto.duracion_segundos),
            notas=dto.notas,
            creado_por_usuario_id=usuario_id,
        )
        guardada = self.repo_campanas.guardar(campana)
        self.registro.activar(guardada.dispositivo_id, guardada.id, guardada.fin_planificado_at)
        return CampanaMapper.to_dto(guardada, rafaga_solicitada=self._pedir_rafaga(device_uid))

    def iniciar_activa(self, dto: CampanaCreateDTO, usuario_id: str | None = None) -> CampanaResponseDTO:
        """Para lo que se puede prender a voluntad: pava, horno, lavarropas, iluminación."""
        return self._iniciar(dto, TipoCampana.ACTIVA, usuario_id)

    def iniciar_pasiva(self, dto: CampanaCreateDTO, usuario_id: str | None = None) -> CampanaResponseDTO:
        """Para lo que cicla solo: heladera, freezer, termotanque.

        No se declara un encendido; se declara que el resto de la casa está apagado y
        se deja que el termostato haga su trabajo durante la ventana.
        """
        return self._iniciar(dto, TipoCampana.PASIVA, usuario_id)

    def _obtener_o_fallar(self, campana_id: str) -> CampanaCaracterizacion:
        campana = self.repo_campanas.obtener_por_id(campana_id)
        if campana is None:
            raise CampanaNoEncontradaError(f"Campaña '{campana_id}' no encontrada.")
        return campana

    def obtener(self, campana_id: str) -> CampanaResponseDTO:
        return CampanaMapper.to_dto(self._obtener_o_fallar(campana_id))

    def listar_por_carga(self, carga_id: str) -> list[CampanaResponseDTO]:
        return [CampanaMapper.to_dto(c) for c in self.repo_campanas.listar_por_carga(carga_id)]

    def finalizar(self, campana_id: str) -> CampanaResponseDTO:
        """Cierra la campaña, calibra la firma y —solo si salió limpia— la fija en la carga."""
        campana = self._obtener_o_fallar(campana_id)
        if not campana.esta_en_curso:
            raise CampanaYaCerradaError(f"La campaña '{campana_id}' ya está en estado {campana.estado.value}.")

        muestras = self.repo_campanas.listar_muestras(campana_id)
        resultado = CalibradorFirmaService.calibrar(muestras, campana.tipo)

        campana.linea_base_w = resultado.linea_base_w
        campana.linea_base_var = resultado.linea_base_var
        campana.muestras = len(muestras)
        campana.cerrar(resultado.estado, motivo=resultado.motivo, detalle=resultado.detalle)
        guardada = self.repo_campanas.guardar(campana)
        self.registro.desactivar(campana.dispositivo_id)

        if resultado.firma is not None and campana.carga_id is not None:
            carga = self.repo_cargas.obtener_por_id(campana.carga_id)
            if carga is not None:
                carga.firma = resultado.firma
                self.repo_cargas.guardar(carga)

        return CampanaMapper.to_dto(guardada, resultado=resultado)

    def descartar(self, campana_id: str, motivo: str | None = None) -> CampanaResponseDTO:
        campana = self._obtener_o_fallar(campana_id)
        if not campana.esta_en_curso:
            raise CampanaYaCerradaError(f"La campaña '{campana_id}' ya está en estado {campana.estado.value}.")

        campana.cerrar(EstadoCampana.DESCARTADA, detalle=motivo)
        guardada = self.repo_campanas.guardar(campana)
        self.registro.desactivar(campana.dispositivo_id)
        return CampanaMapper.to_dto(guardada)

    def sostener_campanas_activas(self, ahora: datetime | None = None) -> tuple[int, int]:
        """Renueva la ráfaga de las campañas vivas y cierra las vencidas.

        Pensado para llamarse desde un bucle del servidor, más seguido que
        `SEGUNDOS_RAFAGA`. Devuelve (renovadas, cerradas).
        """
        momento = ahora or datetime.now(timezone.utc)
        renovadas = 0
        cerradas = 0

        for campana in self.repo_campanas.listar_en_curso():
            if campana.esta_vencida(momento):
                self.finalizar(campana.id)
                cerradas += 1
                continue
            # Rehidrata el registro: si el proceso se reinició, la campaña sigue viva en
            # la base pero el registro en memoria arrancó vacío.
            self.registro.activar(campana.dispositivo_id, campana.id, campana.fin_planificado_at)
            if self._pedir_rafaga(self._uid_de(campana.dispositivo_id)):
                renovadas += 1

        return renovadas, cerradas
