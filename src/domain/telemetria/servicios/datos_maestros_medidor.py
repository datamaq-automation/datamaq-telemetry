"""src/domain/telemetria/servicios/datos_maestros_medidor.py."""

from dataclasses import replace

from src.domain.telemetria.entities import Dispositivo, InstalacionMedidor, NodoUnifilar
from src.domain.telemetria.exceptions import CampoGestionadoPorYamlError
from src.domain.telemetria.servicios.arbol_unifilar import ArbolUnifilarService
from src.domain.telemetria.value_objects import TipoNodoUnifilar

CAMPOS_CONTRATO: frozenset[str] = frozenset({"categoria_tarifaria", "penalizacion_reactiva_aplica"})


class DatosMaestrosMedidorService:
    """Precedencia del YAML sobre MySQL para los datos de instalación y de contrato.

    Regla: lo que el YAML declara, manda; lo que no declara, sale de la base
    (comportamiento histórico intacto). Y lo que el YAML gobierna no se edita
    por API — un cambio de TI o de tarifa es una gestión de cambio, no un PATCH.
    """

    @staticmethod
    def aplicar_instalacion(dispositivo: Dispositivo, instalacion: InstalacionMedidor | None) -> Dispositivo:
        if instalacion is None:
            return dispositivo
        cambios: dict[str, str] = {}
        if instalacion.tag_ubicacion is not None:
            cambios["ubicacion_tag"] = instalacion.tag_ubicacion
        if instalacion.tipo_instalacion is not None:
            cambios["tipo_instalacion"] = instalacion.tipo_instalacion
        if instalacion.fases_con_ti is not None:
            cambios["fases_con_ti"] = instalacion.fases_con_ti
        if instalacion.ct_fases_invertidas is not None:
            cambios["ct_fases_invertidas"] = instalacion.ct_fases_invertidas
        if instalacion.correccion_angular_fases is not None:
            cambios["correccion_angular_fases"] = instalacion.correccion_angular_fases
        return replace(dispositivo, **cambios) if cambios else dispositivo

    @staticmethod
    def acometida_de(dispositivo_id: str, nodos: list[NodoUnifilar]) -> NodoUnifilar | None:
        """Sube por el unifilar desde el nodo medido por `dispositivo_id` hasta la acometida."""
        if not nodos:
            return None
        arbol = ArbolUnifilarService(nodos)
        actual = next((n for n in nodos if n.device_id == dispositivo_id), None)
        visitados: set[str] = set()
        while actual is not None and actual.id not in visitados:
            visitados.add(actual.id)
            if actual.tipo == TipoNodoUnifilar.ACOMETIDA:
                return actual
            if actual.parent_id is None:
                return None
            try:
                actual = arbol.obtener(actual.parent_id)
            except Exception:
                return None
        return None

    @classmethod
    def aplicar_contrato(cls, dispositivo: Dispositivo, nodos: list[NodoUnifilar]) -> Dispositivo:
        acometida = cls.acometida_de(dispositivo.id, nodos)
        if acometida is None:
            return dispositivo
        cambios: dict[str, object] = {}
        if acometida.categoria_tarifaria is not None:
            cambios["categoria_tarifaria"] = acometida.categoria_tarifaria
        if acometida.penalizacion_reactiva_aplica is not None:
            cambios["penalizacion_reactiva_aplica"] = acometida.penalizacion_reactiva_aplica
        return replace(dispositivo, **cambios) if cambios else dispositivo

    @classmethod
    def campos_gobernados_por_yaml(
        cls, dispositivo_id: str, instalacion: InstalacionMedidor | None, nodos: list[NodoUnifilar]
    ) -> set[str]:
        campos = instalacion.campos_declarados() if instalacion else set()
        acometida = cls.acometida_de(dispositivo_id, nodos)
        if acometida is not None:
            if acometida.categoria_tarifaria is not None:
                campos.add("categoria_tarifaria")
            if acometida.penalizacion_reactiva_aplica is not None:
                campos.add("penalizacion_reactiva_aplica")
        return campos

    @classmethod
    def rechazar_escritura_de_campos_gobernados(cls, campos_a_escribir: set[str], gobernados: set[str]) -> None:
        conflicto = sorted(campos_a_escribir & gobernados)
        if conflicto:
            raise CampoGestionadoPorYamlError(
                "Gestionado por YAML: "
                + ", ".join(conflicto)
                + ". Estos datos se declaran en data/organizaciones.yml y cambian por commit, no por API."
            )
