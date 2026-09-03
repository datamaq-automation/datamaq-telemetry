import bisect
import itertools
import math
import statistics
import threading
from collections import Counter
from dataclasses import replace
from datetime import datetime
from typing import Any

from src.domain.disponibilidad.value_objects import (
    DiagnosticoConfianzaModal,
    DiagnosticoEstacionariedad,
    EstadoMaquina,
    NaturalezaRegimen,
    RegimenOperacion,
    SegmentacionPotencia,
)
from src.domain.telemetria.value_objects import LecturaPotenciaTemporal


class ClasificadorDisponibilidadService:
    """Clasifica el estado instantáneo de una máquina comparando potencia contra un umbral calibrado."""

    @staticmethod
    def evaluar(potencia_w: float, umbral_marcha_w: float) -> EstadoMaquina:
        return EstadoMaquina.MARCHA if potencia_w >= umbral_marcha_w else EstadoMaquina.PARADA


class FiltroPersistenciaEstadoService:
    """Exige que un cambio de estado (marcha↔parada) persista antes de confirmarlo.

    Generaliza para disponibilidad la misma idea anti-transitorios de
    `src.domain.telemetria.services.FiltroPersistenciaTemporalService` (evitar que un
    solo pico o dip de potencia dispare un evento), pero parametrizada por máquina:
    cada `Maquina` define su propia ventana de persistencia
    (`ventana_persistencia_lecturas` / `ventana_persistencia_segundos`).
    Thread-safe vía `threading.Lock`.
    """

    def __init__(self) -> None:
        self._pendientes: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def confirmar_cambio(
        self,
        maquina_id: str,
        estado_confirmado: EstadoMaquina | None,
        estado_candidato: EstadoMaquina,
        min_lecturas: int,
        min_segundos: float,
        ahora: datetime,
    ) -> bool:
        """`True` si `estado_candidato` debe reemplazar a `estado_confirmado` ahora."""
        with self._lock:
            if estado_confirmado == estado_candidato:
                self._pendientes.pop(maquina_id, None)
                return False

            pendiente = self._pendientes.get(maquina_id)
            if pendiente is None or pendiente["estado"] != estado_candidato:
                self._pendientes[maquina_id] = {"estado": estado_candidato, "conteo": 1, "desde": ahora}
                return min_lecturas <= 1

            pendiente["conteo"] += 1
            delta_seg = (ahora - pendiente["desde"]).total_seconds()
            if pendiente["conteo"] >= min_lecturas or delta_seg >= min_segundos:
                self._pendientes.pop(maquina_id, None)
                return True
            return False

    def limpiar(self) -> None:
        with self._lock:
            self._pendientes.clear()


class SegmentadorRegimenesService:
    """Parte el eje de potencia en regímenes de operación (partición modal).

    El histograma de potencia de una máquina es multimodal: cada **moda** es una
    "potencia típica" (un régimen estable) y cada **antimoda** (valle) es la frontera
    entre dos regímenes. Este servicio estima la densidad, encuentra las modas que
    valen la pena y devuelve la partición — sin saber nada de marcha/parada, porque las
    mismas herramientas sirven para un medidor que agrega varias cargas (NILM), donde
    no hay ningún umbral binario que calibrar.

    Tres decisiones de método, cada una respondiendo a un problema concreto:

    1. **Bins de ancho constante en `log(P + eps)`**, no en watts. Un ancho fijo en watts
       lo termina fijando el outlier (un arranque de motor es 6-8x la nominal) y no puede
       resolver a la vez un standby angosto de decenas de W y una marcha ancha de kW.
       En log, el ancho es *relativo* constante, que además es como escala el ruido de
       potencia de una máquina en régimen.
    2. **Persistencia topológica** para decidir qué modas son reales. Generaliza a k modas
       la heurística de prominencia que servía solo para dos, y da un *ranking* de
       saliencia comparable entre máquinas.
    3. **Barrido del ancho de suavizado** para validar. El número de modas es monótono no
       creciente en el suavizado: la estructura que sobrevive a un rango amplio es real,
       la que aparece solo en una ventana angosta es ruido de muestreo.

    Sin numpy/scipy: el dominio es stdlib puro (ver CONVENTIONS.md).
    """

    MIN_LECTURAS = 20
    NUM_BINS_POR_DEFECTO = 60
    VENTANA_SUAVIZADO = 3

    PERSISTENCIA_MINIMA_RELATIVA = 0.25
    """Una moda sobrevive si se eleva al menos esta fracción del rango total de densidad
    por encima del valle que la conecta con una moda más alta."""

    DECADAS_MAXIMAS = 5.0
    """Tope de rango dinámico del eje log. Sin esto, una sola lectura casi nula haría que
    `log` estire el eje por décadas vacías y desperdicie todos los bins."""

    EPSILON_MINIMO_W = 0.01
    """Piso absoluto: ningún medidor de tablero resuelve por debajo de esto."""

    VENTANAS_BARRIDO = (1, 3, 5, 7, 9, 11, 13, 15)
    FRACCION_CONSISTENCIA_MINIMA = 0.6

    FACTOR_HUECO_CADENCIA = 3.0
    """Un par de lecturas separado por más de este múltiplo de la cadencia mediana es un
    hueco de datos, no una transición: no aporta ΔP."""

    NUM_SUBVENTANAS_ESTACIONARIEDAD = 4
    DERIVA_MAXIMA_RELATIVA = 0.20

    # ------------------------------------------------------------------ densidad

    @classmethod
    def _estimar_epsilon(cls, lecturas_w: list[float], piso_resolucion_w: float | None = None) -> float:
        """Piso para `log(P + eps)`.

        Si el medidor declara su resolución, se usa. Si no, se estima el cuanto de
        cuantización del ADC/firmware como un percentil bajo de los saltos entre valores
        distintos consecutivos, y se acota para no exceder `DECADAS_MAXIMAS` de rango.
        """
        positivas = [v for v in lecturas_w if v > 0.0]
        maximo = max(positivas) if positivas else 0.0
        piso_por_rango = maximo / (10.0**cls.DECADAS_MAXIMAS)

        if piso_resolucion_w is not None and piso_resolucion_w > 0.0:
            return max(piso_resolucion_w, cls.EPSILON_MINIMO_W)

        distintos = sorted(set(positivas))
        saltos = sorted(b - a for a, b in itertools.pairwise(distintos) if b > a)
        cuanto = cls._percentil(saltos, 0.10) if saltos else 0.0

        return max(cuanto, piso_por_rango, cls.EPSILON_MINIMO_W)

    @staticmethod
    def _percentil(ordenados: list[float], fraccion: float) -> float:
        if not ordenados:
            return 0.0
        indice = int(fraccion * (len(ordenados) - 1))
        return ordenados[min(max(indice, 0), len(ordenados) - 1)]

    @classmethod
    def _construir_bins_log(cls, lecturas_w: list[float], num_bins: int, eps_w: float) -> tuple[list[float], list[int]]:
        """Bins de ancho fijo en escala log; bordes devueltos en watts (ancho variable).

        Devuelve `num_bins + 1` bordes: con bins de ancho variable el consumidor no puede
        reconstruir el último borde asumiendo espaciado uniforme.

        Nota: potencias <= 0 se pisan a 0.0 para la transformación logarítmica pero se conservan
        en su valor real para masa, mediana y ΔP, y se contabilizan en el diagnóstico.
        Revisar este supuesto si aparecen máquinas con frenado regenerativo (potencia negativa real).
        """
        transformados = [math.log(max(v, 0.0) + eps_w) for v in lecturas_w]
        minimo, maximo = min(transformados), max(transformados)

        if maximo <= minimo:
            borde = math.exp(minimo) - eps_w
            return [borde, borde], [len(lecturas_w)]

        ancho = (maximo - minimo) / num_bins
        conteos = [0] * num_bins
        for valor in transformados:
            indice = min(int((valor - minimo) / ancho), num_bins - 1)
            conteos[indice] += 1

        bordes = [math.exp(minimo + i * ancho) - eps_w for i in range(num_bins + 1)]
        return bordes, conteos

    @staticmethod
    def _suavizar(conteos: list[int], ventana: int = 3) -> list[float]:
        if ventana < 2 or len(conteos) < ventana:
            return [float(c) for c in conteos]
        radio = ventana // 2
        suavizados = []
        for i in range(len(conteos)):
            desde = max(0, i - radio)
            hasta = min(len(conteos), i + radio + 1)
            valores_ventana = conteos[desde:hasta]
            suavizados.append(sum(valores_ventana) / len(valores_ventana))
        return suavizados

    @staticmethod
    def _detectar_picos_locales(suavizados: list[float]) -> list[int]:
        """Detecta índices de máximos locales en una curva suavizada."""
        picos: list[int] = []
        for i in range(1, len(suavizados) - 1):
            if suavizados[i] > suavizados[i - 1] and suavizados[i] >= suavizados[i + 1]:
                picos.append(i)
        return picos

    # ------------------------------------------------------------- persistencia

    @staticmethod
    def _persistencia_de_modas(alturas: list[float]) -> dict[int, tuple[float, int | None]]:
        """`{indice_de_moda: (persistencia, indice_de_la_antimoda_donde_muere)}`.

        Merge tree 1-D por union-find, barriendo de mayor a menor altura. Cada índice o
        bien nace como componente nueva (es un máximo local), o extiende una componente
        existente, o fusiona dos: en la fusión **muere la componente más joven** (la del
        pico más bajo), y su persistencia es cuánto hay que descender desde su pico hasta
        ese punto de unión para alcanzar un pico más alto. El máximo global nunca muere.

        Es la formalización de "qué tan saliente es esta moda": una comparable entre
        máquinas, a diferencia de una prominencia expresada como fracción del pico vecino.
        """
        n = len(alturas)
        if n == 0:
            return {}

        orden = sorted(range(n), key=lambda i: (-alturas[i], i))
        padre: dict[int, int] = {}
        nacimiento: dict[int, float] = {}
        activo = [False] * n
        resultado: dict[int, tuple[float, int | None]] = {}

        def encontrar(i: int) -> int:
            raiz = i
            while padre[raiz] != raiz:
                raiz = padre[raiz]
            while padre[i] != raiz:
                padre[i], i = raiz, padre[i]
            return raiz

        for i in orden:
            activo[i] = True
            padre[i] = i
            nacimiento[i] = alturas[i]

            raices: list[int] = []
            for vecino in (i - 1, i + 1):
                if 0 <= vecino < n and activo[vecino]:
                    raiz = encontrar(vecino)
                    if raiz not in raices:
                        raices.append(raiz)

            if not raices:
                continue  # nace una componente: i es máximo local

            raices.sort(key=lambda r: (-nacimiento[r], r))
            principal = raices[0]
            for secundaria in raices[1:]:
                resultado[secundaria] = (nacimiento[secundaria] - alturas[i], i)
                padre[secundaria] = principal
            padre[i] = principal

        resultado[encontrar(orden[0])] = (math.inf, None)
        return resultado

    @classmethod
    def _seleccionar_modas(cls, suavizados: list[float], persistencia_minima_relativa: float) -> list[int]:
        """Índices de las modas que superan el corte de persistencia, ordenados por potencia."""
        if not suavizados:
            return []
        rango = max(suavizados) - min(suavizados)
        if rango <= 0.0:
            return []
        corte = persistencia_minima_relativa * rango
        persistencias = cls._persistencia_de_modas(suavizados)
        return sorted(i for i, (persistencia, _) in persistencias.items() if persistencia >= corte)

    @staticmethod
    def _antimoda_entre(suavizados: list[float], izquierda: int, derecha: int) -> int:
        """Bin del valle entre dos modas; con el valle chato, su centro.

        Entre dos regímenes bien separados el valle no es un punto sino una meseta vacía
        de varios bins. Quedarse con el primer mínimo pegaría la frontera contra el
        régimen de menor potencia; el centro de la meseta es el punto equidistante, que
        es lo que corresponde para clasificar una lectura que caiga en esa zona.
        """
        tramo = range(izquierda, derecha + 1)
        minimo = min(suavizados[i] for i in tramo)
        empatados = [i for i in tramo if suavizados[i] == minimo]
        return empatados[len(empatados) // 2]

    # ------------------------------------------------------------------ barrido

    @classmethod
    def _barrer_ancho_banda(cls, conteos: list[int], persistencia_minima_relativa: float) -> DiagnosticoConfianzaModal:
        """Cuenta modas para cada ancho de suavizado y mide qué estructura sobrevive.

        Reemplaza al umbral de prominencia fijo como criterio de "¿es multimodal de
        verdad?", y devuelve una confianza continua en vez de un booleano opaco.
        """
        conteos_de_modas = [
            len(cls._seleccionar_modas(cls._suavizar(conteos, ventana), persistencia_minima_relativa))
            for ventana in cls.VENTANAS_BARRIDO
        ]
        if not conteos_de_modas:
            return DiagnosticoConfianzaModal(0, 0.0, False)

        num_estable, repeticiones = Counter(conteos_de_modas).most_common(1)[0]
        fraccion = repeticiones / len(conteos_de_modas)
        return DiagnosticoConfianzaModal(
            num_modas_estable=num_estable,
            fraccion_ventanas_consistentes=round(fraccion, 4),
            es_multimodal_confiable=num_estable >= 2 and fraccion >= cls.FRACCION_CONSISTENCIA_MINIMA,
        )

    # ------------------------------------------------------------------- ΔP/Δt

    @classmethod
    def _estimar_cadencia_nominal(cls, lecturas: list[LecturaPotenciaTemporal]) -> float | None:
        """Mediana de los Δt en segundos. Se infiere de la serie, no se hardcodea: el
        mismo dispositivo alterna 5 min estándar y modo ráfaga de 1-5 s."""
        deltas = [
            (b.momento - a.momento).total_seconds()
            for a, b in itertools.pairwise(lecturas)
            if (b.momento - a.momento).total_seconds() > 0
        ]
        return statistics.median(deltas) if deltas else None

    @classmethod
    def _deltas_potencia_validos(
        cls, lecturas: list[LecturaPotenciaTemporal], factor_hueco: float | None = None
    ) -> list[tuple[float, float]]:
        """`[(potencia_media_del_par, |ΔP|/Δt en W/s), ...]`.

        Se normaliza por Δt en vez de usar |ΔP| crudo para que la estadística sea
        comparable entre tramos de cadencia distinta. Los pares separados por un hueco
        de datos se descartan: no son transiciones.
        """
        cadencia = cls._estimar_cadencia_nominal(lecturas)
        if not cadencia:
            return []
        limite = (factor_hueco or cls.FACTOR_HUECO_CADENCIA) * cadencia
        tasas: list[tuple[float, float]] = []
        for anterior, actual in itertools.pairwise(lecturas):
            delta_t = (actual.momento - anterior.momento).total_seconds()
            if delta_t <= 0 or delta_t > limite:
                continue
            potencia_media = (anterior.potencia_w + actual.potencia_w) / 2.0
            tasas.append((potencia_media, abs(actual.potencia_w - anterior.potencia_w) / delta_t))
        return tasas

    @classmethod
    def _tasas_de_variacion(
        cls, lecturas: list[LecturaPotenciaTemporal], cadencia_s: float
    ) -> list[tuple[float, float]]:
        limite = cls.FACTOR_HUECO_CADENCIA * cadencia_s
        tasas: list[tuple[float, float]] = []
        for anterior, actual in itertools.pairwise(lecturas):
            delta_t = (actual.momento - anterior.momento).total_seconds()
            if delta_t <= 0 or delta_t > limite:
                continue
            potencia_media = (anterior.potencia_w + actual.potencia_w) / 2.0
            tasas.append((potencia_media, abs(actual.potencia_w - anterior.potencia_w) / delta_t))
        return tasas

    # --------------------------------------------------------------- regímenes

    @classmethod
    def _armar_regimenes(
        cls,
        lecturas_w: list[float],
        bordes: list[float],
        suavizados: list[float],
        modas: list[int],
        persistencias: dict[int, tuple[float, int | None]],
    ) -> list[RegimenOperacion]:
        if not modas:
            return []

        cortes_w = [
            (lambda j: (bordes[j] + bordes[j + 1]) / 2.0)(cls._antimoda_entre(suavizados, izq, der))
            for izq, der in itertools.pairwise(modas)
        ]

        grupos: list[list[float]] = [[] for _ in modas]
        for valor in lecturas_w:
            grupos[bisect.bisect_right(cortes_w, valor)].append(valor)

        total = len(lecturas_w)
        limites = [bordes[0], *cortes_w, bordes[-1]]
        regimenes: list[RegimenOperacion] = []

        for indice, (bin_moda, valores) in enumerate(zip(modas, grupos, strict=True)):
            mediana = statistics.median(valores) if valores else (bordes[bin_moda] + bordes[bin_moda + 1]) / 2.0
            mad = statistics.median([abs(v - mediana) for v in valores]) if valores else 0.0
            persistencia = persistencias.get(bin_moda, (0.0, None))[0]
            regimenes.append(
                RegimenOperacion(
                    indice=indice,
                    potencia_tipica_w=round((bordes[bin_moda] + bordes[bin_moda + 1]) / 2.0, 4),
                    limite_inferior_w=round(limites[indice], 4),
                    limite_superior_w=round(limites[indice + 1], 4),
                    masa=round(len(valores) / total, 6) if total else 0.0,
                    mediana_w=round(mediana, 4),
                    mad_w=round(mad, 4),
                    persistencia=round(persistencia / max(suavizados) if math.isfinite(persistencia) else 1.0, 4),
                )
            )
        return regimenes

    @classmethod
    def _clasificar_naturaleza(
        cls,
        regimenes: list[RegimenOperacion],
        tasas: list[tuple[float, float]],
        cadencia_s: float,
    ) -> list[RegimenOperacion]:
        """Asigna a cada régimen su |ΔP|/Δt mediano y lo marca estable o transitorio.

        Criterio: un régimen es **transitorio** si el salto típico entre dos lecturas
        consecutivas cruza su banda entera. Es la definición literal de "la máquina no se
        queda acá, pasa": dentro de un régimen estable las lecturas sucesivas caen dentro
        de la banda, y en una zona de paso un solo paso la atraviesa de lado a lado.

        Deliberadamente **no** se compara la tasa contra una mediana global de la serie:
        el ruido de potencia escala con la potencia (la misma heterocedasticidad que
        obliga a binear en log), así que un criterio en W/s absolutos marcaría como
        transitoria a toda marcha de alta potencia solo por ser más ruidosa. El ancho de
        banda del propio régimen es la escala correcta con la cual comparar.

        Sin pares asignados el régimen queda `INDETERMINADO`: nunca se afirma una
        clasificación sin respaldo. Ojo, además, con el límite de muestreo — a cadencia de
        5 min una rampa de 20 s casi no deja muestras, así que un valle poco poblado
        suele ser un régimen desocupado y no una transición observada.
        """
        if not tasas or not regimenes:
            return regimenes

        cortes_w = [r.limite_superior_w for r in regimenes[:-1]]
        por_regimen: list[list[float]] = [[] for _ in regimenes]
        for potencia_media, tasa in tasas:
            por_regimen[bisect.bisect_right(cortes_w, potencia_media)].append(tasa)

        clasificados: list[RegimenOperacion] = []
        for regimen, propias in zip(regimenes, por_regimen, strict=True):
            if not propias:
                clasificados.append(regimen)
                continue
            tasa_regimen = statistics.median(propias)
            salto_tipico_w = tasa_regimen * cadencia_s
            ancho_banda_w = regimen.limite_superior_w - regimen.limite_inferior_w
            naturaleza = NaturalezaRegimen.TRANSITORIO if salto_tipico_w > ancho_banda_w else NaturalezaRegimen.ESTABLE
            clasificados.append(replace(regimen, variacion_mediana_w_s=round(tasa_regimen, 6), naturaleza=naturaleza))
        return clasificados

    # --------------------------------------------------------- estacionariedad

    @classmethod
    def evaluar_estacionariedad(
        cls,
        lecturas: list[LecturaPotenciaTemporal],
        num_subventanas: int | None = None,
        num_bins: int | None = None,
    ) -> DiagnosticoEstacionariedad:
        """Verifica que las modas se sostengan a lo largo de la ventana analizada.

        Parte la serie en tramos cronológicos de igual cantidad de lecturas, segmenta cada
        uno y empareja las modas de tramos consecutivos por cercanía (vecino más cercano).
        Un corrimiento grande significa que el proceso cambió: el histograma agregado
        estaría fundiendo campanas distintas en una sola, ancha y falsa.
        """
        tramos = num_subventanas or cls.NUM_SUBVENTANAS_ESTACIONARIEDAD
        if len(lecturas) < cls.MIN_LECTURAS * tramos or tramos < 2:
            return DiagnosticoEstacionariedad(tramos, None, None, True)

        tamano = len(lecturas) // tramos
        modas_por_tramo: list[list[float]] = []
        for t in range(tramos):
            fin = len(lecturas) if t == tramos - 1 else (t + 1) * tamano
            potencias = [lectura.potencia_w for lectura in lecturas[t * tamano : fin]]
            segmentacion = cls.analizar(potencias, num_bins=num_bins, con_barrido=False)
            modas_por_tramo.append([r.potencia_tipica_w for r in segmentacion.regimenes])

        deriva_relativa = 0.0
        deriva_w = 0.0
        for actuales, siguientes in itertools.pairwise(modas_por_tramo):
            for moda in actuales:
                if not siguientes:
                    continue
                vecina = min(siguientes, key=lambda m: abs(m - moda))
                diferencia = abs(vecina - moda)
                referencia = max(abs(moda), cls.EPSILON_MINIMO_W)
                if diferencia / referencia > deriva_relativa:
                    deriva_relativa = diferencia / referencia
                    deriva_w = diferencia

        return DiagnosticoEstacionariedad(
            num_subventanas=tramos,
            desplazamiento_maximo_relativo=round(deriva_relativa, 4),
            desplazamiento_maximo_w=round(deriva_w, 4),
            es_estacionario=deriva_relativa <= cls.DERIVA_MAXIMA_RELATIVA,
        )

    # ------------------------------------------------------------ punto de entrada

    @classmethod
    def analizar(
        cls,
        lecturas_w: list[float],
        num_bins: int | None = None,
        piso_resolucion_w: float | None = None,
        persistencia_minima_relativa: float | None = None,
        con_barrido: bool = True,
    ) -> SegmentacionPotencia:
        """Segmenta la distribución de potencia en regímenes. Punto de entrada del servicio."""
        bins = num_bins or cls.NUM_BINS_POR_DEFECTO
        persistencia = (
            persistencia_minima_relativa
            if persistencia_minima_relativa is not None
            else cls.PERSISTENCIA_MINIMA_RELATIVA
        )
        no_positivas = sum(1 for v in lecturas_w if v <= 0.0)

        if len(lecturas_w) < cls.MIN_LECTURAS:
            return SegmentacionPotencia([], [], [], 0.0, len(lecturas_w), no_positivas)

        eps = cls._estimar_epsilon(lecturas_w, piso_resolucion_w)
        bordes, conteos = cls._construir_bins_log(lecturas_w, bins, eps)
        suavizados = cls._suavizar(conteos, cls.VENTANA_SUAVIZADO)

        modas = cls._seleccionar_modas(suavizados, persistencia)
        persistencias = cls._persistencia_de_modas(suavizados)
        regimenes = cls._armar_regimenes(lecturas_w, bordes, suavizados, modas, persistencias)

        return SegmentacionPotencia(
            bordes_bins_w=[round(b, 4) for b in bordes],
            frecuencias=conteos,
            regimenes=regimenes,
            epsilon_w=round(eps, 6),
            lecturas_analizadas=len(lecturas_w),
            lecturas_no_positivas=no_positivas,
            diagnostico_modal=cls._barrer_ancho_banda(conteos, persistencia) if con_barrido else None,
        )

    @classmethod
    def analizar_serie(
        cls,
        lecturas: list[LecturaPotenciaTemporal],
        num_bins: int | None = None,
        piso_resolucion_w: float | None = None,
        persistencia_minima_relativa: float | None = None,
    ) -> SegmentacionPotencia:
        """`analizar` más lo que solo la serie temporal puede aportar: dinámica y deriva.

        El histograma es la distribución *marginal* y descarta el orden temporal — por eso
        no puede distinguir un régimen por el que la máquina pasa rápido de uno que
        simplemente se usa poco. Esa distinción vive en |ΔP|/Δt, no en la densidad.
        """
        potencias = [lectura.potencia_w for lectura in lecturas]
        base = cls.analizar(potencias, num_bins, piso_resolucion_w, persistencia_minima_relativa)
        cadencia = cls._estimar_cadencia_nominal(lecturas)

        regimenes = base.regimenes
        if cadencia:
            regimenes = cls._clasificar_naturaleza(regimenes, cls._tasas_de_variacion(lecturas, cadencia), cadencia)

        return SegmentacionPotencia(
            bordes_bins_w=base.bordes_bins_w,
            frecuencias=base.frecuencias,
            regimenes=regimenes,
            epsilon_w=base.epsilon_w,
            lecturas_analizadas=base.lecturas_analizadas,
            lecturas_no_positivas=base.lecturas_no_positivas,
            diagnostico_modal=base.diagnostico_modal,
            diagnostico_estacionariedad=cls.evaluar_estacionariedad(lecturas, num_bins=num_bins),
            cadencia_mediana_s=cadencia,
        )

    @classmethod
    def segmentar(
        cls,
        lecturas_w: list[float],
        num_bins: int | None = None,
        piso_resolucion_w: float | None = None,
        persistencia_minima_relativa: float | None = None,
        con_barrido: bool = True,
    ) -> list[RegimenOperacion]:
        """Punto de entrada de conveniencia: devuelve directamente la lista de regímenes."""
        return cls.analizar(
            lecturas_w,
            num_bins=num_bins,
            piso_resolucion_w=piso_resolucion_w,
            persistencia_minima_relativa=persistencia_minima_relativa,
            con_barrido=con_barrido,
        ).regimenes

    @classmethod
    def segmentar_con_transiciones(
        cls,
        lecturas: list[LecturaPotenciaTemporal],
        num_bins: int | None = None,
        piso_resolucion_w: float | None = None,
        persistencia_minima_relativa: float | None = None,
    ) -> list[RegimenOperacion]:
        """Punto de entrada de conveniencia: devuelve regímenes clasificados con serie temporal."""
        return cls.analizar_serie(
            lecturas,
            num_bins=num_bins,
            piso_resolucion_w=piso_resolucion_w,
            persistencia_minima_relativa=persistencia_minima_relativa,
        ).regimenes


class CalibradorUmbralService:
    """Calibra el umbral marcha/parada a partir del histograma de potencia de una máquina.

    Es el caso k=2 de `SegmentadorRegimenesService`: el umbral es la antimoda que separa
    el régimen de menor potencia (parada/standby) del resto. Toda la matemática vive en el
    segmentador; acá solo queda la traducción al vocabulario binario de disponibilidad.

    Devuelve `None` cuando la distribución no sostiene más de un régimen: no se fuerza un
    umbral sobre datos que no lo respaldan. En ese caso corresponde calibración manual
    (`PATCH /maquinas/{id}` con `umbral_marcha_w` explícito).
    """

    MIN_LECTURAS = SegmentadorRegimenesService.MIN_LECTURAS

    @classmethod
    def construir_histograma(
        cls, lecturas_w: list[float], num_bins: int | None = None
    ) -> tuple[list[float], list[int]]:
        """Bordes de bins y frecuencias, vacíos si no hay suficientes lecturas.

        Los bordes son `len(frecuencias) + 1` y de **ancho variable** (escala log).
        """
        segmentacion = SegmentadorRegimenesService.analizar(lecturas_w, num_bins, con_barrido=False)
        return segmentacion.bordes_bins_w, segmentacion.frecuencias

    @classmethod
    def calcular_umbral(cls, lecturas_w: list[float], num_bins: int | None = None) -> float | None:
        return SegmentadorRegimenesService.analizar(lecturas_w, num_bins, con_barrido=False).umbral_marcha_sugerido_w
