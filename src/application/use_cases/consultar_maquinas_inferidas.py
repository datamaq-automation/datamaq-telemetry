"""src/application/use_cases/consultar_maquinas_inferidas.py."""

from datetime import datetime, timezone

from src.application.dtos.maquina_dto import (
    ListaMaquinasInferidaDTO,
    MaquinaInferidaDTO,
)
from src.domain.cargas.ports import RepositorioCargasPort
from src.domain.cargas.value_objects import OrigenFirma


class ConsultarMaquinasInferidaUseCase:
    """Consulta máquinas propuestas por energy-ml para un dispositivo."""

    def __init__(self, cargas: RepositorioCargasPort) -> None:
        """Args:
        cargas: Repositorio de cargas para acceder a las inferidas.
        """
        self.cargas = cargas

    def __call__(
        self,
        dispositivo_id: str,
    ) -> ListaMaquinasInferidaDTO:
        """Obtiene máquinas propuestas por ML para un dispositivo.

        Args:
            dispositivo_id: ID del dispositivo (acceso validado por router)

        Returns:
            ListaMaquinasInferidaDTO con máquinas inferidas ordenadas por confianza DESC.

        Note:
            Validación de acceso (org_id, planta_id) es responsabilidad del router
            usando el patrón PlantaPermitida. El use case solo consulta datos.
        """
        # Buscar todas las cargas inferidas del dispositivo
        todas_cargas = self.cargas.listar_por_dispositivo(dispositivo_id, solo_activas=False)
        cargas_inferidas = [c for c in todas_cargas if c.firma and c.firma.origen == OrigenFirma.INFERIDA]

        # Mapear a DTOs
        maquinas_dtos = [self._mapear_a_dto(carga) for carga in cargas_inferidas]

        # Ordenar por confianza DESC
        maquinas_dtos.sort(key=lambda m: m.confianza, reverse=True)

        # Calcular promedio de confianza
        total_confianza_prom = sum(m.confianza for m in maquinas_dtos) / len(maquinas_dtos) if maquinas_dtos else 0.0

        # Retornar respuesta
        return ListaMaquinasInferidaDTO(
            dispositivo_id=dispositivo_id,
            maquinas_inferidas=maquinas_dtos,
            ultima_ejecucion_ml=datetime.now(timezone.utc),  # TODO: guardar en BD
            total_confianza_prom=total_confianza_prom,
        )

    @staticmethod
    def _mapear_a_dto(carga) -> MaquinaInferidaDTO:
        """Mapea una Carga inferida a MaquinaInferidaDTO.

        Args:
            carga: Entidad Carga con origen=INFERIDA

        Returns:
            MaquinaInferidaDTO con datos derivados de la Carga.

        Note:
            - confianza: derivada de dispersion_w / potencia_w (0.0-1.0)
            - patrones_detectados: del patron_operacion y naturaleza_electrica
            - energia_kwh_mes: placeholder (requerirá histórico real)
            - costo_estimado_ars: placeholder (requerirá tarifa real)
        """
        # Calcular confianza: 1.0 - (dispersion_w / potencia_w), clamped
        confianza = 0.8  # MVP: valor fijo (mejora: calcular de dispersion_w)
        if carga.firma and carga.firma.potencia_w > 0:
            if carga.firma.dispersion_w is not None:
                ratio = carga.firma.dispersion_w / carga.firma.potencia_w
                confianza = max(0.0, min(1.0, 1.0 - ratio))

        # Patrones detectados: del patron_operacion y naturaleza_electrica
        patrones = []
        if carga.patron_operacion:
            patrones.append(str(carga.patron_operacion.value).lower())
        if carga.naturaleza_electrica:
            patrones.append(str(carga.naturaleza_electrica.value).lower())

        return MaquinaInferidaDTO(
            id=carga.id,
            nombre=carga.nombre,
            tipo_maquina=str(carga.categoria.value).lower() if carga.categoria else "otros",
            confianza=confianza,
            patrones_detectados=patrones,
            energia_kwh_mes=0.0,  # TODO: calcular del histórico
            costo_estimado_ars=0.0,  # TODO: calcular con tarifa real
        )
