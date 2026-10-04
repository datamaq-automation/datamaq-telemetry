"""src/application/use_cases/proponer_firmas_inferidas.py."""

import uuid
from datetime import datetime

from src.application.dtos.carga_dto import ResumenPropuestaDTO
from src.domain.maquinas.entities import Carga, ahora_utc
from src.domain.maquinas.ports import DescubridorMáquinasPort, RepositorioMáquinasPort
from src.domain.maquinas.servicios.emparejador_candidatas import emparejar
from src.domain.maquinas.value_objects import CargaCandidata, FirmaCarga, OrigenFirma


class ProponerFirmasInferidasUseCase:
    """Propone firmas INFERIDA para cargas del dispositivo basado en descubrimiento externo."""

    def __init__(
        self, cargas: RepositorioMáquinasPort, descubridor: DescubridorMáquinasPort, tolerancia_relativa: float = 0.15
    ) -> None:
        self.cargas = cargas
        self.descubridor = descubridor
        self.tolerancia_relativa = tolerancia_relativa

    def _construir_firma_inferida(self, candidata: CargaCandidata, hasta: datetime) -> FirmaCarga:
        muestras = candidata.encendidos + candidata.apagados
        return FirmaCarga(
            potencia_w=candidata.potencia_w,
            dispersion_w=candidata.dispersion_w,
            origen=OrigenFirma.INFERIDA,
            muestras=muestras,
            medida_en=hasta,
        )

    def _procesar_candidata_emparejada(
        self, carga: Carga, candidata: CargaCandidata, hasta: datetime, actualizadas: list[str], protegidas: list[str]
    ) -> None:
        if carga.firma and carga.firma.origen == OrigenFirma.CAMPANA:
            protegidas.append(carga.nombre)
        else:
            carga.firma = self._construir_firma_inferida(candidata, hasta)
            carga.actualizado_en = ahora_utc()
            self.cargas.guardar(carga)
            actualizadas.append(carga.nombre)

    def _procesar_candidata_sin_pareja(
        self,
        dispositivo_id: str,
        candidata: CargaCandidata,
        hasta: datetime,
        actualizadas: list[str],
        creadas: list[str],
    ) -> None:
        nombre = f"Inferida ~{round(candidata.potencia_w / 1000)} kW"
        existente = self.cargas.obtener_por_nombre(dispositivo_id, nombre)
        if existente:
            existente.firma = self._construir_firma_inferida(candidata, hasta)
            existente.actualizado_en = ahora_utc()
            self.cargas.guardar(existente)
            actualizadas.append(nombre)
        else:
            nueva_carga = Carga(
                id=str(uuid.uuid4()),
                dispositivo_id=dispositivo_id,
                nombre=nombre,
                activa=False,
                firma=self._construir_firma_inferida(candidata, hasta),
            )
            self.cargas.guardar(nueva_carga)
            creadas.append(nombre)

    def execute(self, dispositivo_id: str, medidor: str, desde: datetime, hasta: datetime) -> ResumenPropuestaDTO:
        """Ejecuta la propuesta de firmas.

        Flujo:
        1. Descubre candidatas en el rango temporal.
        2. Filtra: descartar on_off=False o potencia_w <= 0.
        3. Obtiene catálogo del dispositivo.
        4. Por candidata, empareja con carga del catálogo (max 1 por corrida).
           - CAMPANA → protegida, no se toca.
           - CHAPA/None/INFERIDA → se actualiza a INFERIDA con dispersión y muestras.
           - Sin pareja → crea "Inferida ~N kW" inactiva si no existe (idempotencia).
        5. Devuelve resumen.

        Args:
            dispositivo_id: ID del dispositivo
            medidor: nombre del medidor (ej. "Trafo arriba")
            desde: inicio del rango de análisis
            hasta: fin del rango de análisis

        Returns:
            ResumenPropuestaDTO con actualizadas, creadas, protegidas, descartadas.

        Raises:
            DescubridorNoDisponibleError si el descubridor no responde.
        """
        # 1. Descubrir y filtrar candidatas
        candidatas_brutas = self.descubridor.descubrir(medidor, desde, hasta)
        descartadas_count = sum(1 for c in candidatas_brutas if not c.on_off or c.potencia_w <= 0)
        candidatas = [c for c in candidatas_brutas if c.on_off and c.potencia_w > 0]

        # 2. Obtener catálogo
        catalogo = self.cargas.listar_por_dispositivo(dispositivo_id, solo_activas=False)

        # 3. Procesar cada candidata
        actualizadas: list[str] = []
        creadas: list[str] = []
        protegidas: list[str] = []
        candidatas_emparejadas_ids: set[str] = set()

        for candidata in candidatas:
            cargas_disponibles = [c for c in catalogo if c.id not in candidatas_emparejadas_ids]
            carga = emparejar(candidata, cargas_disponibles, self.tolerancia_relativa)

            if carga:
                candidatas_emparejadas_ids.add(carga.id)
                self._procesar_candidata_emparejada(carga, candidata, hasta, actualizadas, protegidas)
            else:
                self._procesar_candidata_sin_pareja(dispositivo_id, candidata, hasta, actualizadas, creadas)

        return ResumenPropuestaDTO(
            dispositivo_id=dispositivo_id,
            actualizadas=actualizadas,
            creadas=creadas,
            protegidas=protegidas,
            descartadas=descartadas_count,
        )
