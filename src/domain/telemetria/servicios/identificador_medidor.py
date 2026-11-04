"""src/domain/telemetria/servicios/identificador_medidor.py — identificador de medidor en las rutas.

Formas aceptadas para un dispositivo buscado por MAC:
- ``8C8C291C3FB4``    → MAC, medidor 0 (equipos de un solo medidor).
- ``8C8C291C3FB4_1``  → MAC + medidor 1 (Pro15 con varios medidores).

Se usa "_" y no "-" porque MacAddress normaliza y quita los "-" como separadores (un "-1" se confundiría
con una MAC mal escrita). Los ids internos (UUID) se buscan antes por id y no pasan por acá.
"""

from dataclasses import dataclass

from src.domain.telemetria.exceptions import MacAddressInvalidaError
from src.domain.telemetria.value_objects import MacAddress

SEPARADOR_MEDIDOR = "_"


@dataclass(frozen=True)
class IdentificadorMedidor:
    mac: MacAddress
    medidor_id: int


def parsear_identificador_medidor(texto: str) -> IdentificadorMedidor:
    """Devuelve (MAC, medidor_id). Lanza MacAddressInvalidaError si la MAC o el medidor no son válidos."""
    partes = texto.strip().split(SEPARADOR_MEDIDOR)
    if len(partes) > 2:
        raise MacAddressInvalidaError(f"Identificador de medidor inválido: {texto}")
    mac = MacAddress(partes[0])
    if len(partes) == 1:
        return IdentificadorMedidor(mac=mac, medidor_id=0)
    if not partes[1].isdigit():
        raise MacAddressInvalidaError(f"Medidor inválido en el identificador: {texto}")
    return IdentificadorMedidor(mac=mac, medidor_id=int(partes[1]))
