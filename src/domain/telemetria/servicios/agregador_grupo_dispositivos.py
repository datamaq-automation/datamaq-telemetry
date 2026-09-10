from dataclasses import dataclass
from datetime import date

from src.domain.telemetria.entities import EnergiaAgregada, LecturaInstantanea


@dataclass(frozen=True)
class PotenciaSumadaGrupo:
    """Suma de la última lectura conocida de cada dispositivo miembro de un grupo.

    ``dispositivos_sin_dato`` lista los device_id sin ninguna lectura instantánea
    todavía, para que la UI pueda avisar que el total es parcial.
    """

    potencia_activa_total_w: float | None
    dispositivos_sin_dato: list[str]


class AgregadorGrupoDispositivosService:
    """Suma lecturas de varios dispositivos ya resueltas por dispositivo, sin acceso a I/O.

    Tolera desalineamiento temporal entre dispositivos a propósito (confirmado con el
    negocio): suma la última lectura conocida de cada uno, no exige timestamps iguales.
    """

    @staticmethod
    def sumar_ultimas_lecturas(
        lecturas_por_dispositivo: dict[str, LecturaInstantanea | None],
    ) -> PotenciaSumadaGrupo:
        total = 0.0
        hubo_dato = False
        sin_dato: list[str] = []
        for dispositivo_id, lectura in lecturas_por_dispositivo.items():
            if lectura is None or lectura.potencia_activa_total is None:
                sin_dato.append(dispositivo_id)
                continue
            total += lectura.potencia_activa_total.vatios
            hubo_dato = True
        return PotenciaSumadaGrupo(
            potencia_activa_total_w=round(total, 2) if hubo_dato else None,
            dispositivos_sin_dato=sin_dato,
        )

    @staticmethod
    def sumar_energia_agregada(
        agregados_por_dispositivo: dict[str, list[EnergiaAgregada]],
    ) -> list[EnergiaAgregada]:
        totales_por_periodo: dict[date, float] = {}
        hubo_dato_por_periodo: dict[date, bool] = {}
        for agregados in agregados_por_dispositivo.values():
            for item in agregados:
                if item.energia_activa_neta_kwh is None:
                    totales_por_periodo.setdefault(item.periodo, 0.0)
                    hubo_dato_por_periodo.setdefault(item.periodo, False)
                    continue
                totales_por_periodo[item.periodo] = (
                    totales_por_periodo.get(item.periodo, 0.0) + item.energia_activa_neta_kwh
                )
                hubo_dato_por_periodo[item.periodo] = True

        return [
            EnergiaAgregada(
                periodo=periodo,
                energia_activa_neta_kwh=round(totales_por_periodo[periodo], 4)
                if hubo_dato_por_periodo.get(periodo)
                else None,
            )
            for periodo in sorted(totales_por_periodo)
        ]
