"""Application Service para ejecutar diagnóstico de TI (orquestador)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol

from src.domain.telemetria.servicios.diagnostico_ti import DiagnosticoTIService
from src.domain.telemetria.value_objects import CandidatoTI


class RepositorioTelemetriaPort(Protocol):
    """Contrato de repositorio de telemetría (lectura de mediciones)."""

    def obtener_mediciones_dispositivo(
        self,
        dispositivo_id: str,
        inicio: datetime,
        fin: datetime,
    ) -> list[dict]:
        """Retorna lista de dicts con p_r, q_r, s_r, fp_r, p_s, ... para el período."""
        ...


class EjecutarDiagnosticoTIApplicationService:
    """Application Service: ejecutar diagnóstico de TI para un dispositivo.

    Orquesta:
    1. Lectura de telemetría desde repositorio
    2. Conversión de tipos (Decimal → float)
    3. Llamada a DiagnosticoTIService.rankear_candidatos()
    4. Retorna resultado estructurado
    """

    def __init__(self, repo_telemetria: RepositorioTelemetriaPort) -> None:
        self.repo_telemetria = repo_telemetria

    def ejecutar(
        self,
        dispositivo_id: str,
        fases_con_ti: tuple[str, ...],
        periodo_horas: int = 24,
    ) -> DiagnosticoTIResultDTO:
        """Ejecuta diagnóstico de TI para un dispositivo.

        Args:
            dispositivo_id: UUID del dispositivo
            fases_con_ti: Tupla de fases disponibles (ej. ("R", "S"))
            periodo_horas: Período histórico a analizar

        Returns:
            DiagnosticoTIResultDTO con candidatos rankeados
        """
        inicio = datetime.now(timezone.utc) - timedelta(hours=periodo_horas)
        fin = datetime.now(timezone.utc)

        registros_db = self.repo_telemetria.obtener_mediciones_dispositivo(dispositivo_id, inicio, fin)

        if not registros_db:
            return DiagnosticoTIResultDTO(
                dispositivo_id=dispositivo_id,
                periodo_horas=periodo_horas,
                registros_analizados=0,
                candidatos=[],
                error="Sin datos en el período especificado",
            )

        # Convertir Decimal → float
        registros = self._convertir_tipos(registros_db)

        # Rankear candidatos
        candidatos = DiagnosticoTIService.rankear_candidatos(registros, fases_con_ti)

        return DiagnosticoTIResultDTO(
            dispositivo_id=dispositivo_id,
            periodo_horas=periodo_horas,
            registros_analizados=len(registros),
            candidatos=candidatos,
            error=None,
        )

    @staticmethod
    def _convertir_tipos(registros_db: list[dict]) -> list[dict]:
        """Convierte Decimal (de BD) a float para cálculos numéricos."""
        resultado = []
        for reg in registros_db:
            reg_convertido = {}
            for key, val in reg.items():
                if val is not None and hasattr(val, "__float__"):
                    reg_convertido[key] = float(val)
                else:
                    reg_convertido[key] = val
            resultado.append(reg_convertido)
        return resultado


class DiagnosticoTIResultDTO:
    """DTO: resultado del diagnóstico de TI."""

    def __init__(
        self,
        dispositivo_id: str,
        periodo_horas: int,
        registros_analizados: int,
        candidatos: list[CandidatoTI],
        error: str | None = None,
    ) -> None:
        self.dispositivo_id = dispositivo_id
        self.periodo_horas = periodo_horas
        self.registros_analizados = registros_analizados
        self.candidatos = candidatos
        self.error = error

    def to_dict(self) -> dict:
        """Serializa a dict para JSON."""
        return {
            "dispositivo_id": self.dispositivo_id,
            "periodo_horas": self.periodo_horas,
            "registros_analizados": self.registros_analizados,
            "error": self.error,
            "candidatos": [
                {
                    "orden_fases": list(cand.orden_fases),
                    "invertido": cand.invertido,
                    "score": round(cand.score, 4),
                    "justificacion": cand.justificacion,
                }
                for cand in self.candidatos
            ],
        }
