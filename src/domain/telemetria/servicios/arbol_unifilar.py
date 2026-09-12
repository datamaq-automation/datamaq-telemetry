"""src/domain/telemetria/servicios/arbol_unifilar.py."""

from collections import defaultdict

from src.domain.telemetria.entities import NodoUnifilar
from src.domain.telemetria.exceptions import (
    EstructuraUnifilarInvalidaError,
    NodoUnifilarNoEncontradoError,
)


class ArbolUnifilarService:
    """Navegación y validación del árbol del diagrama unifilar de una planta, sin I/O.

    Un nodo sin ``device_id`` es virtual: no tiene medidor propio y su medición se
    obtiene sumando los medidores frontera aguas abajo.
    """

    def __init__(self, nodos: list[NodoUnifilar]):
        self._nodos = list(nodos)
        self._por_id: dict[str, NodoUnifilar] = {}
        self._hijos: dict[str | None, list[NodoUnifilar]] = defaultdict(list)
        for nodo in self._nodos:
            self._por_id.setdefault(nodo.id, nodo)
            self._hijos[nodo.parent_id].append(nodo)
        for hijos in self._hijos.values():
            hijos.sort(key=lambda n: (n.orden, n.id))

    def validar(self) -> None:
        vistos: set[str] = set()
        for nodo in self._nodos:
            if nodo.id in vistos:
                raise EstructuraUnifilarInvalidaError(f"El nodo '{nodo.id}' está duplicado en el unifilar.")
            vistos.add(nodo.id)

        for nodo in self._nodos:
            if nodo.parent_id is None:
                continue
            if nodo.parent_id == nodo.id:
                raise EstructuraUnifilarInvalidaError(f"El nodo '{nodo.id}' se referencia a sí mismo como padre.")
            if nodo.parent_id not in self._por_id:
                raise EstructuraUnifilarInvalidaError(
                    f"El nodo '{nodo.id}' referencia un padre inexistente '{nodo.parent_id}'."
                )

        for nodo in self._nodos:
            camino: set[str] = set()
            actual: NodoUnifilar | None = nodo
            while actual is not None and actual.parent_id is not None:
                if actual.id in camino:
                    raise EstructuraUnifilarInvalidaError(
                        f"El unifilar tiene un ciclo que pasa por el nodo '{actual.id}'."
                    )
                camino.add(actual.id)
                actual = self._por_id.get(actual.parent_id)

    def obtener(self, nodo_id: str) -> NodoUnifilar:
        nodo = self._por_id.get(nodo_id)
        if nodo is None:
            raise NodoUnifilarNoEncontradoError(f"El nodo '{nodo_id}' no existe en el unifilar de la planta.")
        return nodo

    def hijos_de(self, nodo_id: str) -> list[NodoUnifilar]:
        return list(self._hijos.get(nodo_id, []))

    def medidores_frontera(self, nodo_id: str) -> list[str]:
        """Device ids de los medidores más cercanos aguas abajo, uno por rama.

        Se corta en el primer nodo medido de cada rama porque ese medidor ya integra
        todo lo que cuelga de él; seguir bajando duplicaría submediciones anidadas.
        """
        raiz = self.obtener(nodo_id)
        resultado: list[str] = []
        visitados: set[str] = set()
        pendientes = [raiz]
        while pendientes:
            nodo = pendientes.pop(0)
            if nodo.id in visitados:
                continue
            visitados.add(nodo.id)
            if nodo.device_id:
                resultado.append(nodo.device_id)
                continue
            pendientes.extend(self.hijos_de(nodo.id))
        return resultado
