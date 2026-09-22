"""src/domain/telemetria/servicios/relacion_transformacion.py."""

import re
from dataclasses import dataclass

from src.domain.telemetria.entities import NodoUnifilar
from src.domain.telemetria.servicios.clasificador_nivel_tension import clasificar_nivel_tension

# Tolerancia con la que se acepta la relación de placa frente al cociente de
# nominales del árbol. 15% cubre la diferencia legítima entre el secundario de
# placa (400 V) y la nominal declarada de la barra (380 V) — 5% — dejando margen
# para tomas de regulación, sin tragarse un orden de magnitud equivocado.
TOLERANCIA_PLACA_VS_ARBOL = 0.15

# Por debajo de esta diferencia, el cociente de nominales se considera unitario:
# los medidores frontera ya están en el mismo nivel que el nodo consultado.
EPSILON_RELACION_UNITARIA = 0.05


@dataclass(frozen=True)
class RelacionTransformacion:
    """Factor con el que se proyecta el agregado por fase a la escala del nodo.

    El dominio no loguea (``structlog`` es una librería de terceros): expone el
    ``origen`` y una ``advertencia`` opcional para que la capa de aplicación las
    emita.
    """

    factor: float
    origen: str
    advertencia: str | None = None


def parsear_relacion_placa_kv(valor: str | None) -> float | None:
    """Parsea la relación de transformación de placa: "15/0.4" → 37.5.

    Tolera unidades y espacios ("13.2 kV / 0.4 kV" → 33.0). Devuelve ``None`` si
    el dato falta o no es interpretable; el llamador decide el default.
    """
    if not valor:
        return None
    partes = valor.split("/")
    if len(partes) != 2:
        return None
    match_primario = re.match(r"[\d.]+", partes[0].strip())
    match_secundario = re.match(r"[\d.]+", partes[1].strip())
    if not match_primario or not match_secundario:
        return None
    try:
        primario = float(match_primario.group())
        secundario = float(match_secundario.group())
    except ValueError:
        return None
    if primario <= 0.0 or secundario <= 0.0:
        return None
    return primario / secundario


def _nominal_comun_de_frontera(nodos_frontera: list[NodoUnifilar]) -> float | None:
    """Nominal de los nodos frontera si todos coinciden; ``None`` si difieren.

    Un escalar único sólo representa a la frontera cuando todos sus medidores
    están en el mismo nivel de tensión.
    """
    nominales = {nodo.tension_nominal_v for nodo in nodos_frontera if nodo.tension_nominal_v > 0.0}
    if len(nominales) != 1:
        return None
    return nominales.pop()


def derivar_relacion_transformacion(nodo: NodoUnifilar, nodos_frontera: list[NodoUnifilar]) -> RelacionTransformacion:
    """Decide el factor de escalado del agregado por fase de ``nodo``.

    Precedencia:

    1. Nodo consultado en BT → 1.0. Su ``relacion_tension_kv`` de placa, si la
       declara, es un dato del equipo (nameplate), no una instrucción de escalar
       este nodo (caso Durax: un transformador medido en su propia barra BT).
    2. Frontera heterogénea o vacía → 1.0, con advertencia.
    3. Cociente de nominales ≈ 1 → 1.0: los medidores frontera ya están en MT,
       así que la placa no aplica aunque esté declarada.
    4. Placa parseable y coherente con el cociente → se usa la placa, que es la
       relación de transformación real del equipo (turns ratio, IEC 60076).
    5. Si no → el cociente de nominales del árbol, con advertencia si había una
       placa que discrepaba.
    """
    if clasificar_nivel_tension(nodo.tension_nominal_v) != "MT":
        return RelacionTransformacion(factor=1.0, origen="nodo_bt")

    placa = parsear_relacion_placa_kv(nodo.metadatos_placa.relacion_tension_kv if nodo.metadatos_placa else None)

    if not nodos_frontera:
        return RelacionTransformacion(
            factor=placa if placa is not None else 1.0,
            origen="placa" if placa is not None else "sin_frontera",
            advertencia=None if placa is not None else "Nodo MT sin medidores frontera: no hay escala que derivar.",
        )

    nominal_frontera = _nominal_comun_de_frontera(nodos_frontera)
    if nominal_frontera is None:
        return RelacionTransformacion(
            factor=1.0,
            origen="frontera_heterogenea",
            advertencia=(
                "Los medidores frontera declaran tensiones nominales distintas; "
                "un factor único no los representa y no se escala."
            ),
        )

    cociente = nodo.tension_nominal_v / nominal_frontera

    if abs(cociente - 1.0) <= EPSILON_RELACION_UNITARIA:
        return RelacionTransformacion(factor=1.0, origen="medicion_en_nivel_del_nodo")

    if placa is not None and abs(placa - cociente) / cociente <= TOLERANCIA_PLACA_VS_ARBOL:
        return RelacionTransformacion(factor=placa, origen="placa")

    advertencia = None
    if placa is not None:
        advertencia = (
            f"La relación de placa ({placa:.2f}) discrepa del cociente de nominales del "
            f"árbol ({cociente:.2f}); se usa el árbol."
        )
    return RelacionTransformacion(factor=cociente, origen="cociente_nominales", advertencia=advertencia)
