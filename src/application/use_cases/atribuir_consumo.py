"""src/application/use_cases/atribuir_consumo.py."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src.application.dtos.carga_dto import (
    AnalisisConsumoResponseDTO,
    AtribucionConsumoResponseDTO,
    CorregirIntervaloRequestDTO,
    IntervaloActividadResponseDTO,
    ItemAtribucionDTO,
)
from src.application.mappers.carga_mapper import IntervaloActividadMapper
from src.domain.cargas.entities import Carga, IntervaloActividadCarga
from src.domain.cargas.exceptions import (
    CargaNoEncontradaError,
    IntervaloActividadNoEncontradoError,
)
from src.domain.cargas.ports import (
    RepositorioCargasPort,
    RepositorioIntervalosActividadPort,
    RepositorioSeriePotenciaPort,
)
from src.domain.cargas.servicios.atribuidor_consumo import AtribuidorConsumoService
from src.domain.cargas.servicios.clasificador_reglas import ClasificadorCargasReglasService
from src.domain.cargas.servicios.detector_escalones import DetectorEscalonesService
from src.domain.cargas.servicios.emparejador_firmas import EmparejadorFirmasService
from src.domain.cargas.servicios.presets_cargas import CatalogoPresetsCargas
from src.domain.cargas.value_objects import (
    AtribucionConsumo,
    EpisodioCarga,
)
from src.domain.telemetria.ports import RepositorioOrganizacionesPort
from src.domain.telemetria.value_objects import TipoNodoUnifilar

ZONA_POR_DEFECTO = "America/Argentina/Buenos_Aires"

_ADVERTENCIA_SIN_FIRMAS = (
    "Ninguna carga del catálogo tiene firma calibrada todavía, así que todos los episodios "
    "detectados quedan sin atribuir. Corré una campaña de caracterización por aparato."
)


class AtribuirConsumoUseCase:
    """Motor batch: detecta episodios en la serie y los imputa a las cargas del catálogo.

    Corre diferido y no en la ingesta a propósito. La duración de un encendido es la
    mitad de su identidad —es lo único que separa una pava de un termotanque de la misma
    potencia— y en vivo esa duración no se conoce hasta que el evento terminó. Sobre una
    ventana cerrada además se puede reprocesar cuando alguien corrige una etiqueta, sin
    poner trabajo pesado en el camino crítico de MQTT.

    Es idempotente: re-correr la misma ventana reescribe sus intervalos en vez de
    duplicarlos, y nunca pisa una corrección humana.
    """

    LIMITE_LECTURAS = 200_000

    def __init__(
        self,
        repo_serie: RepositorioSeriePotenciaPort,
        repo_cargas: RepositorioCargasPort,
        repo_intervalos: RepositorioIntervalosActividadPort,
        repo_organizaciones: RepositorioOrganizacionesPort | None = None,
    ):
        self.repo_serie = repo_serie
        self.repo_cargas = repo_cargas
        self.repo_intervalos = repo_intervalos
        self.repo_organizaciones = repo_organizaciones

    def _es_instalacion_industrial(self, dispositivo_id: str) -> bool:
        if not self.repo_organizaciones:
            return False
        instalacion = self.repo_organizaciones.obtener_instalacion_medidor(dispositivo_id)
        if instalacion and instalacion.tipo_instalacion:
            tipo = instalacion.tipo_instalacion.upper()
            if "INDUSTRIAL" in tipo:
                return True
            if "DOMESTICO" in tipo or "HOGAR" in tipo or "RESIDENCIAL" in tipo:
                return False
        try:
            plantas = self.repo_organizaciones.listar_plantas()
            for p in plantas:
                nodos = self.repo_organizaciones.obtener_nodos_unifilar(p.id)
                for n in nodos:
                    if n.device_id == dispositivo_id:
                        if (
                            n.tipo
                            in (TipoNodoUnifilar.TGBT, TipoNodoUnifilar.TRANSFORMADOR, TipoNodoUnifilar.SECCIONAL)
                            or n.uso_significativo
                        ):
                            return True
        except Exception:
            pass
        return False

    @staticmethod
    def _ventana(desde: datetime | None, hasta: datetime | None, dias: int) -> tuple[datetime, datetime]:
        fin = hasta or datetime.now(timezone.utc)
        return (desde or fin - timedelta(days=dias)), fin

    def _a_intervalo(
        self,
        dispositivo_id: str,
        episodio: EpisodioCarga,
        cargas: list[Carga],
        zona: ZoneInfo,
        todas_las_cargas: list[Carga] | None = None,
        es_industrial: bool = False,
    ) -> IntervaloActividadCarga:
        decision = EmparejadorFirmasService.decidir(episodio, cargas, zona)
        carga_id = decision.carga_id
        confianza = round(decision.confianza, 3) if decision.confianza is not None else None
        notas = decision.motivo

        if carga_id is None:
            diag = ClasificadorCargasReglasService.clasificar_episodio(episodio, es_industrial=es_industrial)
            if diag.aparato_sugerido != "Carga no clasificada" and diag.confianza >= 0.70:
                confianza = round(diag.confianza, 3)
                coincidente = None
                if todas_las_cargas:
                    sugerido_norm = diag.aparato_sugerido.strip().lower()
                    for c in todas_las_cargas:
                        nom = c.nombre.strip().lower()
                        if nom == sugerido_norm or sugerido_norm in nom or nom in sugerido_norm:
                            coincidente = c
                            break
                if coincidente is not None:
                    carga_id = coincidente.id
                    notas = (
                        f"Atribuido por regla a {coincidente.nombre} ({diag.aparato_sugerido}): "
                        f"{', '.join(diag.reglas_aplicadas)}"
                    )
                else:
                    notas = (
                        f"Sugerido por regla: {diag.aparato_sugerido} "
                        f"({diag.confianza:.0%}) - {', '.join(diag.reglas_aplicadas)}"
                    )

        return IntervaloActividadCarga(
            id=None,
            dispositivo_id=dispositivo_id,
            carga_id=carga_id,
            inicio_at=episodio.inicio,
            fin_at=episodio.fin,
            potencia_media_w=episodio.potencia_media_w,
            delta_reactiva_var=episodio.delta_reactiva_var,
            energia_kwh=episodio.energia_kwh,
            confianza=confianza,
            notas=notas,
        )

    def analizar(
        self,
        dispositivo_id: str,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        dias: int = 7,
        zona: str = ZONA_POR_DEFECTO,
    ) -> AnalisisConsumoResponseDTO:
        """Detecta episodios en la ventana y persiste su atribución. Idempotente."""
        inicio, fin = self._ventana(desde, hasta, dias)
        zona_info = ZoneInfo(zona)

        lecturas = self.repo_serie.listar_serie_potencia(dispositivo_id, inicio, fin, limite=self.LIMITE_LECTURAS)
        cargas = [c for c in self.repo_cargas.listar_por_dispositivo(dispositivo_id, solo_activas=True)]
        con_firma = [c for c in cargas if c.firma is not None]

        umbral = DetectorEscalonesService.umbral_escalon(lecturas) if lecturas else None
        episodios = DetectorEscalonesService.detectar_episodios(lecturas, umbral)
        es_industrial = self._es_instalacion_industrial(dispositivo_id)
        intervalos = [
            self._a_intervalo(
                dispositivo_id, e, con_firma, zona_info, todas_las_cargas=cargas, es_industrial=es_industrial
            )
            for e in episodios
        ]
        escritos = self.repo_intervalos.reemplazar_ventana(dispositivo_id, inicio, fin, intervalos)

        return AnalisisConsumoResponseDTO(
            dispositivo_id=dispositivo_id,
            desde=inicio,
            hasta=fin,
            cantidad_lecturas=len(lecturas),
            umbral_escalon_W=round(umbral, 2) if umbral is not None else None,
            episodios_detectados=len(episodios),
            intervalos_escritos=escritos,
            atribuidos=sum(1 for i in intervalos if i.esta_atribuido),
            no_atribuidos=sum(1 for i in intervalos if not i.esta_atribuido),
            cargas_con_firma=len(con_firma),
            advertencia_cadencia=_ADVERTENCIA_SIN_FIRMAS if not con_firma else None,
        )

    @staticmethod
    def _atribucion_a_dto(dispositivo_id: str, atribucion: AtribucionConsumo) -> AtribucionConsumoResponseDTO:
        residual_pct = (
            round(atribucion.residual_porcentaje * 100, 2) if atribucion.residual_porcentaje is not None else None
        )
        return AtribucionConsumoResponseDTO(
            dispositivo_id=dispositivo_id,
            desde=atribucion.desde,
            hasta=atribucion.hasta,
            energia_total_kwh=atribucion.energia_total_kwh,
            energia_atribuida_kwh=atribucion.energia_atribuida_kwh,
            residual_kwh=atribucion.residual_kwh,
            residual_porcentaje=residual_pct,
            items=[
                ItemAtribucionDTO(
                    carga_id=i.carga_id,
                    nombre=i.nombre,
                    energia_kwh=i.energia_kwh,
                    porcentaje=round(i.porcentaje * 100, 2),
                    intervalos=i.intervalos,
                    confianza_media=i.confianza_media,
                )
                for i in atribucion.items
            ],
            calidad_suficiente=atribucion.calidad_suficiente,
            advertencia=atribucion.advertencia,
        )

    def atribucion(
        self,
        dispositivo_id: str,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        dias: int = 30,
    ) -> AtribucionConsumoResponseDTO:
        """Reparto de kWh del período, contrastado contra el contador acumulado."""
        inicio, fin = self._ventana(desde, hasta, dias)
        intervalos = self.repo_intervalos.listar_por_dispositivo(dispositivo_id, inicio, fin)
        cargas = self.repo_cargas.listar_por_dispositivo(dispositivo_id)
        total = self.repo_serie.obtener_energia_consumida_kwh(dispositivo_id, inicio, fin)

        atribucion = AtribuidorConsumoService.atribuir(inicio, fin, intervalos, cargas, total)
        return self._atribucion_a_dto(dispositivo_id, atribucion)

    def listar_intervalos(self, carga_id: str, limite: int = 100) -> list[IntervaloActividadResponseDTO]:
        intervalos = self.repo_intervalos.listar_por_carga(carga_id, limite=limite)
        return [IntervaloActividadMapper.to_dto(i) for i in intervalos]

    def listar_intervalos_dispositivo(
        self,
        dispositivo_id: str,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        dias: int = 7,
        solo_no_atribuidos: bool = False,
        limite: int = 200,
    ) -> list[IntervaloActividadResponseDTO]:
        """Lista intervalos del dispositivo en la ventana, con opción de ver solo los no atribuidos."""
        inicio, fin = self._ventana(desde, hasta, dias)
        intervalos = self.repo_intervalos.listar_por_dispositivo(dispositivo_id, inicio, fin)
        if solo_no_atribuidos:
            intervalos = [i for i in intervalos if not i.esta_atribuido]
        if limite:
            intervalos = intervalos[:limite]
        return [IntervaloActividadMapper.to_dto(i) for i in intervalos]

    def corregir_intervalo(
        self, intervalo_id: int, dto: CorregirIntervaloRequestDTO, usuario_id: str
    ) -> IntervaloActividadResponseDTO:
        """Reimputa un intervalo a mano. Queda protegido de futuros reprocesos del batch."""
        intervalo = self.repo_intervalos.obtener_por_id(intervalo_id)
        if intervalo is None:
            raise IntervaloActividadNoEncontradoError(f"Intervalo de actividad {intervalo_id} no encontrado.")

        if dto.carga_id is not None and self.repo_cargas.obtener_por_id(dto.carga_id) is None:
            raise CargaNoEncontradaError(f"Carga '{dto.carga_id}' no encontrada.")

        intervalo.corregir(dto.carga_id, usuario_id=usuario_id, notas=dto.notas)
        return IntervaloActividadMapper.to_dto(self.repo_intervalos.guardar(intervalo))

    def inicializar_presets_catalogo(self, dispositivo_id: str) -> list[Carga]:
        """Inicializa en el repositorio las cargas con firmas estándar de catálogo que no existan."""
        existentes = {c.nombre.strip().lower(): c for c in self.repo_cargas.listar_por_dispositivo(dispositivo_id)}
        presets = CatalogoPresetsCargas.obtener_todas(dispositivo_id)
        resultado: list[Carga] = []
        for preset in presets:
            clave = preset.nombre.strip().lower()
            if clave in existentes:
                resultado.append(existentes[clave])
            else:
                self.repo_cargas.guardar(preset)
                resultado.append(preset)
                existentes[clave] = preset
        return resultado
