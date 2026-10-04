"""src/infrastructure/energy_ml/descubridor_http.py — Adaptador HTTP a energy-ml."""

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from src.domain.cargas.exceptions import DescubridorNoDisponibleError
from src.domain.cargas.ports import DescubridorCargasPort
from src.domain.cargas.value_objects import CargaCandidata


class EnergyMlHttpDescubridor(DescubridorCargasPort):
    """Descubridor que consulta energy-ml vía HTTP."""

    def __init__(self, base_url: str, timeout_s: int = 120):
        self.base_url = base_url
        self.timeout_s = timeout_s

    def descubrir(self, medidor: str, desde: datetime, hasta: datetime) -> list[CargaCandidata]:
        """Descubre cargas consultando energy-ml.

        Args:
            medidor: nombre del medidor (ej. "Trafo arriba")
            desde: inicio del período en ISO
            hasta: fin del período en ISO

        Returns:
            Lista de CargaCandidata (ya en W).

        Raises:
            DescubridorNoDisponibleError si la respuesta no es válida.
        """
        # Construir URL
        params = {
            "medidor": medidor,
            "desde": desde.date().isoformat(),
            "hasta": hasta.date().isoformat(),
        }
        query_string = urllib.parse.urlencode(params)
        url = f"{self.base_url}/api/v1/identify-loads?{query_string}"

        try:
            response = urllib.request.urlopen(url, timeout=self.timeout_s)

            if response.status != 200:
                raise DescubridorNoDisponibleError(f"energy-ml respondió con status {response.status}")

            body = response.read().decode("utf-8")
            data = json.loads(body)

            candidatas = []
            for item in data.get("cargas", []):
                # Convertir kW → W
                potencia_w = item.get("potencia_kw", 0) * 1000
                dispersion_w = item.get("dispersion_kw", 0.0) * 1000

                candidata = CargaCandidata(
                    potencia_w=potencia_w,
                    dispersion_w=dispersion_w,
                    encendidos=item.get("encendidos", 0),
                    apagados=item.get("apagados", 0),
                    ciclos_por_dia=item.get("ciclos_por_dia"),
                    on_off=item.get("on_off", True),
                )
                candidatas.append(candidata)

            return candidatas

        except (json.JSONDecodeError, ValueError) as e:
            raise DescubridorNoDisponibleError(f"JSON inválido de energy-ml: {e}") from e
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            raise DescubridorNoDisponibleError(f"Error conectando a energy-ml: {e}") from e
        except Exception as e:
            raise DescubridorNoDisponibleError(f"Error inesperado en descubridor: {e}") from e
