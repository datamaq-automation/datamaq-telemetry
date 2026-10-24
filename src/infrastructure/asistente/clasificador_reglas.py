import re
import unicodedata
from typing import ClassVar

from src.domain.asistente.entities import IntencionClasificada
from src.domain.asistente.ports import ClasificadorIntencionPort


class ClasificadorIntencionReglasAdapter(ClasificadorIntencionPort):
    """Clasificador determinístico y ligero en CPU local."""

    PATRONES: ClassVar[dict[str, list[tuple[str, int]]]] = {
        "EXPLICAR_ALERTAS": [
            (r"\balerta(s)?\b", 3),
            (r"\bnotificacion(es)?\b", 3),
            (r"\badvertencia(s)?\b", 3),
            (r"\bdesconexion(es)?\b", 3),
            (r"\binestable\b", 2),
            (r"\bcorte(s)?\b", 2),
            (r"\bproblema(s)?\b", 2),
            (r"\bfallo(s)?\b", 2),
            (r"\bpor que\b.*\bavis\w*", 3),
            (r"\bque\b.*\b(paso|ocurrio)\b.*\b(alerta|problema|fallo)\b", 3),
            (r"\bque\b.*\b(paso|ocurrio)\b.*\bmaquina\b", 2),
        ],
        "SALUD_DISPOSITIVOS": [
            (r"\bsalud\b", 3),
            (r"\bestado\b", 2),
            (r"\bonline\b", 2),
            (r"\boffline\b", 2),
            (r"\bmedidor(es)?\b", 2),
            (r"\bconectad[oa]s?\b", 2),
            (r"\bdesconectad[oa]s?\b", 2),
            (r"\bdispositivo(s)?\b", 2),
            (r"\bmaquina(s)?\b", 1),
            (r"\btrafo(s)?\b", 1),
            (r"\busina(s)?\b", 1),
            (r"\bhorno(s)?\b", 1),
        ],
        "RESUMEN_TELEMETRIA": [
            (r"\bpotencia\b", 3),
            (r"\bconsumo\b", 3),
            (r"\bestamos consumiendo\b", 3),
            (r"\bcuanto\b.*\bconsum", 3),
            (r"\bcual\b.*\bconsumo\b", 3),
            (r"\bkw\b", 2),
            (r"\bkwh\b", 2),
            (r"\btelemetria\b", 3),
            (r"\bfactor de potencia\b", 3),
            (r"\bfp\b", 2),
            (r"\btension\b", 3),
            (r"\bvoltaje\b", 3),
            (r"\bcorriente\b", 3),
            (r"\bamper(es)?\b", 2),
        ],
    }

    def clasificar(self, pregunta: str) -> IntencionClasificada:
        """Clasifica una pregunta según las reglas y sus puntajes."""
        texto = unicodedata.normalize("NFKD", pregunta.lower().strip())
        texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))

        if not texto:
            return IntencionClasificada(
                nombre="DESCONOCIDO",
                confianza=0.0,
            )

        puntajes: dict[str, int] = {intencion: 0 for intencion in self.PATRONES}
        coincidencias: dict[str, int] = {intencion: 0 for intencion in self.PATRONES}

        for intencion, patrones in self.PATRONES.items():
            for patron, peso in patrones:
                if re.search(patron, texto):
                    puntajes[intencion] += peso
                    coincidencias[intencion] += 1

        mejor_puntaje = max(puntajes.values())

        if mejor_puntaje == 0:
            return IntencionClasificada(
                nombre="DESCONOCIDO",
                confianza=0.1,
            )

        mejores_intenciones = [intencion for intencion, puntaje in puntajes.items() if puntaje == mejor_puntaje]

        # Si hay empate de puntaje, comparamos la cantidad de reglas coincidentes.
        if len(mejores_intenciones) > 1:
            mayor_numero_coincidencias = max(coincidencias[intencion] for intencion in mejores_intenciones)

            mejores_intenciones = [
                intencion for intencion in mejores_intenciones if coincidencias[intencion] == mayor_numero_coincidencias
            ]

        # Si el empate continúa, no elegimos una intención arbitrariamente.
        if len(mejores_intenciones) > 1:
            return IntencionClasificada(
                nombre="DESCONOCIDO",
                confianza=0.0,
            )

        mejor_intencion = mejores_intenciones[0]
        confianza = min(0.6 + (0.05 * mejor_puntaje), 0.95)

        return IntencionClasificada(
            nombre=mejor_intencion,
            confianza=confianza,
        )
