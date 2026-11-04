"""src/domain/telemetria/servicios/pro15_payload.py — Pro15 (un equipo, varios medidores).

Puro (stdlib). Convierte los mensajes ``pro15/{MAC}/{sub}/v1`` a los formatos por fase que ya entiende
la ingesta, separando cada medidor interno (``id`` 0, 1, …). Las fases van por POSICIÓN (0→R, 1→S, 2→T),
sin clave ``n``. Ver specs/ingesta-pro15-multimedidor.md.

Nunca lanza ante payload malformado: devuelve listas/dicts vacíos y el caso de uso decide qué registrar.
"""

import math
from dataclasses import dataclass, field
from typing import Any

PREFIJO_PRO15 = "pro15"
SUBTOPICOS_PRO15: frozenset[str] = frozenset({"inst", "acc", "energyio", "thd", "onoff", "status"})
_FASES_POR_POSICION: tuple[str, ...] = ("R", "S", "T")


@dataclass(frozen=True)
class TopicPro15:
    mac: str
    subtopico: str


def parsear_topico_pro15(topico: str) -> TopicPro15 | None:
    """``pro15/{MAC}/{sub}/v1`` → TopicPro15. None si el tópico no tiene esa forma.

    Se valida la forma completa para no confundir ``inst`` con una MAC (trampa de
    ``IngestarTelemetriaUseCase.ejecutar``, que toma ``partes[2]`` como MAC).
    """
    partes = topico.split("/")
    if len(partes) != 4 or partes[0] != PREFIJO_PRO15 or partes[3] != "v1":
        return None
    if partes[2] not in SUBTOPICOS_PRO15:
        return None
    mac = partes[1].replace(":", "").replace("-", "").upper()
    if len(mac) != 12 or any(c not in "0123456789ABCDEF" for c in mac):
        return None
    return TopicPro15(mac=mac, subtopico=partes[2])


@dataclass(frozen=True)
class BloquePro15:
    """Datos de un medidor interno en un instante. ``datos`` ya tiene el formato de la ingesta por fase."""

    medidor_id: int
    timestamp: str | None
    datos: dict[str, Any] = field(default_factory=dict)


def _numero(valor: Any) -> float | None:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    numero = float(valor)
    return numero if math.isfinite(numero) else None


def _medidor_id(valor: Any) -> int | None:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
        return None
    return valor


def _fases_por_posicion(lista: Any) -> list[dict[str, Any]]:
    """Las primeras 3 entradas dict van a R, S, T por posición. Entradas no dict se reemplazan por {}."""
    if not isinstance(lista, list):
        return []
    fases: list[dict[str, Any]] = []
    for item in lista[: len(_FASES_POR_POSICION)]:
        fases.append(item if isinstance(item, dict) else {})
    return fases


def _iterar_bloques(payload: Any) -> list[tuple[int, str | None, Any]]:
    """Lista de (medidor_id, t, cuerpo) para los mensajes que son una lista por medidor."""
    if not isinstance(payload, list):
        return []
    bloques: list[tuple[int, str | None, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        medidor = _medidor_id(item.get("id"))
        if medidor is None:
            continue
        t = item.get("t") if isinstance(item.get("t"), str) else None
        bloques.append((medidor, t, item))
    return bloques


def bloques_inst(payload: Any) -> list[BloquePro15]:
    """``inst`` → por medidor: {"f": [{"v","i","p","q"}, …]} (R,S,T por posición), formato de parse_fase."""
    resultado: list[BloquePro15] = []
    for medidor, t, item in _iterar_bloques(payload):
        fases = _fases_por_posicion(item.get("f"))
        resultado.append(BloquePro15(medidor_id=medidor, timestamp=t, datos={"f": _fases_con_clave(fases)}))
    return resultado


def _fases_con_clave(fases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Asigna la clave ``n`` por posición (no la inventa el firmware)."""
    return [{"n": _FASES_POR_POSICION[i], **fase} for i, fase in enumerate(fases)]


def bloques_acc(payload: Any) -> list[BloquePro15]:
    """``acc`` → por medidor: {"f": [{"n","a","r"}], "total": {…}} con a=kWh, r=kVARh (formato de EnergiaPayloadParser)."""
    resultado: list[BloquePro15] = []
    for medidor, t, item in _iterar_bloques(payload):
        fases = _fases_por_posicion(item.get("f"))
        convertidas = []
        for i, fase in enumerate(fases):
            convertidas.append(
                {
                    "n": _FASES_POR_POSICION[i],
                    "a": _numero(fase.get("kWh")),
                    "r": _numero(fase.get("kVARh")),
                }
            )
        resultado.append(BloquePro15(medidor_id=medidor, timestamp=t, datos={"f": convertidas}))
    return resultado


def bloques_energyio(payload: Any) -> list[BloquePro15]:
    """``energyio`` → por medidor: {"total": {…}} con las claves que lee EnergiaPayloadParser."""
    resultado: list[BloquePro15] = []
    for medidor, t, item in _iterar_bloques(payload):
        tot = item.get("tot") if isinstance(item.get("tot"), dict) else {}
        total = {
            "imported_active_energy_KWH": _numero(tot.get("kWhi")),
            "exported_active_energy_KWH": _numero(tot.get("kWho")),
            "imported_reactive_energy_KVARH": _numero(tot.get("kVARhi")),
            "exported_reactive_energy_KVARH": _numero(tot.get("kVARho")),
        }
        resultado.append(BloquePro15(medidor_id=medidor, timestamp=t, datos={"total": total}))
    return resultado


def bloques_thd(payload: Any) -> list[BloquePro15]:
    """``thd`` → por medidor: {"f": [{"n": 0|1|2, "THDv","THDi"}]}, la forma que lee parsear_thd_harmonics."""
    resultado: list[BloquePro15] = []
    for medidor, t, item in _iterar_bloques(payload):
        fases = _fases_por_posicion(item.get("f"))
        convertidas = [{"n": i, "THDv": fase.get("THDv"), "THDi": fase.get("THDi")} for i, fase in enumerate(fases)]
        resultado.append(BloquePro15(medidor_id=medidor, timestamp=t, datos={"f": convertidas}))
    return resultado


def bloques_por_subtopico(subtopico: str, payload: Any) -> list[BloquePro15]:
    """Despacha al conversor del subtópico. Subtópicos sin conversor (onoff, status) devuelven []."""
    conversores = {
        "inst": bloques_inst,
        "acc": bloques_acc,
        "energyio": bloques_energyio,
        "thd": bloques_thd,
    }
    conversor = conversores.get(subtopico)
    return conversor(payload) if conversor else []


def device_info_pro15_a_formato_ingesta(device_info: Any) -> dict[str, Any] | None:
    """`device_info` del Pro15 → claves que lee el resolvedor (serial_number, device_fw, device_model).

    El Pro15 manda `sn`, `fw` y `model`; el resolvedor espera otros nombres. Sin este mapeo el equipo
    se registraría como `SmartPlus` y sin serie ni firmware.
    """
    if not isinstance(device_info, dict):
        return None
    mapeado: dict[str, Any] = {}
    for origen, destino in (("sn", "serial_number"), ("fw", "device_fw"), ("model", "device_model")):
        valor = device_info.get(origen)
        if isinstance(valor, str) and valor.strip():
            mapeado[destino] = valor.strip()
    return mapeado or None
