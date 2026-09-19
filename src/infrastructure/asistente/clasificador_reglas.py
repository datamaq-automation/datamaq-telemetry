# src/infrastructure/asistente/clasificador_reglas.py
import re
from typing import ClassVar

from src.domain.asistente.entities import IntencionClasificada
from src.domain.asistente.ports import ClasificadorIntencionPort


class ClasificadorIntencionReglasAdapter(ClasificadorIntencionPort):
    """Adaptador determinístico y ligero en CPU local que clasifica la intención de la pregunta

    del usuario utilizando reglas semánticas y patrones de palabras clave.
    """

    PATRONES: ClassVar[dict[str, list[str]]] = {
        "EXPLICAR_ALERTAS": [
            r"alerta",
            r"notificaci",
            r"advertencia",
            r"desconexi",
            r"inestable",
            r"corte",
            r"problema",
            r"fallo",
            r"por qu[eé] me avis[oó]",
            r"qu[eé] pas[oó]",
        ],
        "SALUD_DISPOSITIVOS": [
            r"salud",
            r"estado",
            r"online",
            r"offline",
            r"medidor",
            r"conectad",
            r"dispositivo",
            r"trafo",
            r"usina",
            r"horno",
        ],
        "RESUMEN_TELEMETRIA": [
            r"potencia",
            r"consumo",
            r"kw",
            r"kwh",
            r"telemetr[ií]a",
            r"factor de potencia",
            r"fp",
            r"tensi[oó]n",
            r"corriente",
        ],
    }

    def clasificar(self, pregunta: str) -> IntencionClasificada:
        texto = pregunta.lower()

        # Evaluar patrones
        for intencion, patrones in self.PATRONES.items():
            for pat in patrones:
                if re.search(pat, texto):
                    return IntencionClasificada(nombre=intencion, confianza=0.9)

        return IntencionClasificada(nombre="DESCONOCIDO", confianza=0.1)
