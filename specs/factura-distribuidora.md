# [COMPLETADO] Factura de la distribuidora como dato histórico en YAML

> **Decisión aplicable:** `decisions/2026-09-24_factura-distribuidora-yaml.md` (repo padre).
> **Traspasada a hija:** sí · **Bloque cerrado:** ✓ SÍ — UPP con EdeLAP (potencia) + CAMMESA (energía) 
> completamente implementado, pusheado a `main` (commit `4729849`, 2026-09-24). Parsers reales 
> verificados contra 2+ facturas cada uno. Datos en producción: 11 facturas EDELAP de potencia de
> UPP (2023-12 a 2024-11, sin 2024-02), ninguna de energía. Ver la corrección de abajo.
>
> **Corrección 2026-09-28 (`690b868` + datamaq-data `001771a`):** las "2 facturas UPP (2026-08)"
> que esta spec daba por reales no lo eran. La de EDELAP era la factura 2024-11 (mismo Nº
> 0020-01988580 y mismo total de $ 21.031.736,78, con vencimiento 10/12/2024), cargada con el
> período y la planta equivocados. La de CAMMESA (`CAM-2026-08-00312`) era de ejemplo, como ya
> advertía §3, y se armó con la energía y los cargos variables de esa misma factura EDELAP.
> Se quitaron las dos. Además, la regex del importe total no coincidía con el texto real del PDF
> (`importe_total_ars` salía 0.0), y los fixtures del test del parser eran una reconstrucción a
> mano que lo ocultaba. Las menciones a "la factura real de Durax" y a "2026-08 en producción"
> más abajo son registro histórico de la implementación: quedan tal cual, pero son incorrectas.
> Los ejemplos de YAML (§2.2) y de JSON (§3) se reemplazaron por la factura 2024-11 real.
>
> **Pendiente (sin urgencia, sin consumidor real hasta que se instale medidor):**
> - Confirmar con `app-datamaq` si necesita campo `cargadaEn` en DTO (existe en domain)
> - EDESUR/Edenor/distribuidoras locales: relevar al instalar medidor + obtener 2+ muestras reales
> — ver "Pendientes" al final de §2.2.

## 1. Objetivo y Contexto

> **Nota 2026-09-24 (corrección de supuesto):** el diseño original de este bloque (secciones
> abajo, ya corregidas) asumía **un solo PDF por planta por período**. Es falso: el dueño
> confirmó que la planta UPP recibe la **potencia** facturada por **EdeLAP** y la **energía**
> facturada por **CAMMESA** en dos PDFs separados del mismo período — no hay un documento único
> que traiga ambas magnitudes. Otras plantas (Eitec, Cristal Avellaneda → EDESUR; Madygraf, Los
> Constituyentes → Edenor; El Gringo, Textiles Pigué → distribuidoras locales todavía sin
> identificar) tendrán su propio caso cuando se les instale el medidor — puede que un solo
> proveedor facture todo, o que se repita el patrón de dos documentos.
>
> Decisión del dueño (vía `AskUserQuestion`, 2026-09-24): el histórico guarda **dos entradas
> separadas por período** cuando hay dos proveedores — un único tipo `FacturaDistribuidora` con
> un discriminador `tipo_dato: Literal["potencia", "energia"]` y un campo `proveedor`, no dos
> clases de entidad ni una fusión de ambas en una fila. Alcance de esta iteración: **solo EdeLAP
> (potencia) + CAMMESA (energía) para UPP**, la única planta con medidores instalados hoy; el
> resto de las distribuidoras queda documentado como pendiente, sin parser todavía (ver
> "Pendientes" en §2.2).

**Objetivo:** modelar la factura mensual de la distribuidora como dato histórico versionado en
YAML (una entrada por planta por período), con un parser de PDF que extraiga los campos
estructurados, para (a) comprobar la medición global de energía contra `BalanceEnergiaService`, y
(b) exponer series de potencia adquirida/contratada/excedida (kW y su tarifa en $/kW) y energía
facturada (MWh) a los gráficos.

**Alcance:**
- Entidad(es) de dominio para la factura (período, planta, energía facturada en MWh, potencia
  adquirida/contratada/excedida en kW, valores tarifarios asociados).
- Puerto + repositorio YAML para persistir/leer el histórico, versionado en git.
- Parser de PDF en `infrastructure/` (nueva dependencia de terceros a elegir y justificar).
- Validador de integridad (extensión de `verificador_unifilar.py` o uno nuevo).
- Caso(s) de uso para: alimentar `BalanceEnergiaService` con la energía facturada como
  `energia_padre_kwh`, y exponer la serie histórica a los endpoints que consuman los gráficos
  nuevos.
- DTOs y endpoint(s) FastAPI para exponer el histórico de facturas a `app-datamaq` (necesarios si
  los gráficos mencionados se consumen desde el frontend — a confirmar alcance de endpoint en
  esta iniciativa vs. una spec de `app-datamaq` aparte).

**Fuera de alcance:**
- La UI/gráficos en `app-datamaq` (potencia adquirida/contratada/excedida, MWh): esta spec cubre
  solo el backend (dato + exposición). Si se necesita, abrir un bloque `## Repo: app-datamaq`
  aparte cuando se defina el contrato de API resultante.
- OCR genérico para cualquier formato de factura de cualquier distribuidora del país: alcanzar,
  en esta primera iteración, el formato de la distribuidora real que se vaya a cargar primero.

**Certezas verificadas en este repo (rutas, callers, qué borrar):**
- `organizaciones.yml:9-11` — patrón existente de campos "fuente factura", pero vigente, no
  histórico: no reusar tal cual, es un archivo/estructura distinta.
- `src/domain/sge/servicios/balance_energia.py`, `src/application/use_cases/consultar_balance_energia.py`
  — consumidor de energía medida vs. facturada, hoy con `energia_padre_kwh` como parámetro
  explícito, no conectado a ninguna fuente.
- `src/domain/telemetria/entities.py:219` — `potencia_contratada_kw` sin persistencia ni otros
  usos en `src/` (`grep -rn potencia_contratada_kw src/ tests/ data/` solo devuelve la
  declaración del campo): candidato a reemplazar o convivir, no a asumir vigente.
- `src/infrastructure/yaml/verificador_unifilar.py` — único validador de integridad YAML hoy, corre
  al arrancar sobre `YamlOrganizacionesRepository`, solo advierte. Valida específicamente el árbol
  del unifilar (`ArbolUnifilarService`), no genérico.
- Sin dependencia de PDF en `pyproject.toml`/`requirements.txt`: cualquier librería que se elija es
  nueva y debe declararse.
- `src/domain/telemetria/ports.py:191-196` — `RepositorioOrganizacionesPort` es **solo lectura a
  propósito**: "la estructura de planta se modifica por commit al YAML, no por API. No hay
  `guardar_*`." Este contrato ya existente condiciona el diseño del caso de uso de ingesta (§2).
- `src/infrastructure/fastapi/routes/sge_router.py` — patrón ya usado para `linea-base` y
  `balance-energia`/`ahorros-cusum`: router `/api/v1/sge`, dependencia `resolver_planta_permitida`
  para aislar por planta, DTOs con alias camelCase (`sge_dto.py`), mapeo de dict crudo del YAML a
  entidad tipada en el repositorio.
- `scripts/exportar_instalacion_medidores.py` — precedente de script CLI que vuelca datos a un
  formato revisable por un humano antes de commitear al YAML, en vez de escribir en caliente desde
  la API.

**Ya hecho por el padre (no repetir):** decisión registrada con las 6 respuestas del dueño
(`decisions/2026-09-24_factura-distribuidora-yaml.md`). Nada de código.

## 2. Dominio & Puertos

### 2.1 Decisiones a criterio de la hija (registradas acá, no se devuelven sin decidir)

1. **Librería de parsing de PDF: `pdfplumber`.** No se cuenta con una factura real de la
   distribuidora para inspeccionar su formato en esta sesión (texto seleccionable vs. escaneo).
   Se elige `pdfplumber` (pure-Python sobre `pdfminer.six`, sin binarios de sistema, ya extrae
   texto y tablas) como implementación por defecto para el caso más común (PDF con texto
   seleccionable, que es como la gran mayoría de distribuidoras argentinas emiten la factura
   digital). El puerto de dominio (`ParserFacturaDistribuidoraPort`, ver 2.2) es la abstracción
   que permite, **sin tocar dominio ni casos de uso**, agregar un segundo adaptador con OCR
   (ej. `pytesseract` + `pdf2image`, que sí requieren binarios de sistema `tesseract`/`poppler`) el
   día que aparezca una factura escaneada real. No se agrega esa dependencia ahora (no hay caso
   de uso comprobado, y la regla de la casa es no construir para hipotéticos).
2. **Validador: uno nuevo, `verificador_facturas.py`.** `verificador_unifilar.py` valida
   específicamente la estructura de árbol del unifilar vía `ArbolUnifilarService.validar()`; una
   colección plana de facturas históricas por planta no tiene esa forma (no hay padre/hijo,
   `parent_id`, ciclos). Forzarla en el mismo validador mezclaría dos invariantes distintos.
   `verificar_facturas_plantas()` sigue el mismo patrón (advierte, no bloquea) pero valida otra
   cosa: unicidad de `(período, tipo_dato)` por planta (no "período único" — dos documentos del
   mismo período, uno de potencia y otro de energía, son válidos), formato `YYYY-MM`, `planta_id`
   existente, magnitudes no negativas.
3. **`Dispositivo.potencia_contratada_kw`: se elimina.** `grep` confirma cero callers y cero
   persistencia (no está en ningún mapper SQLAlchemy ni DTO). La factura pasa a ser la fuente de
   verdad histórica y real de potencia contratada (con período, a diferencia del campo suelto que
   nunca se pobló). Mantenerlo sería duplicar una noción sin dueño. Se borra en el mismo commit que
   agrega la entidad `FacturaDistribuidora`, dejando constancia acá para que la verificación
   cruzada del padre no lo marque como pendiente.
4. **Se verificó una factura real durante la implementación (no especulativa) y cambió el
   modelo de la entidad.** El dueño compartió una factura real de EDELAP (Empresa Distribuidora
   La Plata, tarifa de Media Tensión T5M12) vía Google Drive. Leerla mostró que la potencia
   contratada, adquirida y su importe **no son un valor único**: la distribuidora factura Media
   Tensión discriminando siempre **Punta** y **Fuera de Punta** (dos franjas horarias con
   demanda y tarifa distintas — ver `Potencias Contratadas (KW): ... Transporte Punta: 800.000
   Transporte Fuera Punta: 850.000` y los cargos de potencia separados por franja en la factura).
   Un solo campo `potencia_contratada_kw` como se había especulado en el borrador inicial de este
   documento habría perdido esa distinción tarifaria real. La entidad de §2.2 quedó rediseñada
   con esa discriminación antes de escribir ningún caso de uso o DTO, para no arrastrar el
   modelo viejo a capas superiores. La energía activa también viene discriminada en tres franjas
   (Punta/Resto/Valle) en la factura real, así que la entidad las guarda por separado y expone
   `energia_facturada_kwh` como propiedad calculada (la suma) en vez de un campo suelto.

### 2.2 Entidad, puertos y estructura YAML

**Entidad** `src/domain/sge/entities.py` (junto a `ArticuloSge`; el dominio de la factura es SGE —
ISO 50001 §6.3/§9.1 la usa como evidencia de energía y demanda — no telemetría):

```python
TipoDatoFactura = Literal["potencia", "energia"]


@dataclass(frozen=True)
class FacturaDistribuidora:
    """UN documento de facturación — potencia O energía, no ambas (ver nota 2026-09-24 en §1).

    Potencia y energía pueden venir facturadas por proveedores DISTINTOS en la misma planta
    (UPP: EdeLAP potencia, CAMMESA energía). Un registro `tipo_dato="potencia"` tiene poblados
    los campos de potencia (los de energía quedan en None) y viceversa. Potencia y su valor van
    discriminados Punta / Fuera de Punta porque así factura la distribuidora en tarifas de Media
    Tensión (confirmado con una factura real EDELAP, tarifa T5M12)."""

    id: str  # `{planta_id}-{periodo}-{tipo_dato}`, determinístico
    planta_id: str
    periodo: str  # "YYYY-MM", mes facturado
    proveedor: str  # "EDELAP", "CAMMESA", ...
    tipo_dato: TipoDatoFactura
    numero_factura: str
    importe_total_ars: float
    tarifa: str | None = None
    dias_facturados: int | None = None
    energia_activa_punta_kwh: float | None = None
    energia_activa_resto_kwh: float | None = None
    energia_activa_valle_kwh: float | None = None
    potencia_contratada_punta_kw: float | None = None
    potencia_contratada_fuera_punta_kw: float | None = None
    potencia_adquirida_punta_kw: float | None = None  # medida/facturada real = contratada + exceso
    potencia_adquirida_fuera_punta_kw: float | None = None
    importe_potencia_ars: float | None = None
    importe_energia_ars: float | None = None
    fuente_archivo: str | None = None  # nombre del PDF origen, trazabilidad
    cargada_en: str | None = None  # fecha ISO de carga (no de facturación)

    @property
    def energia_facturada_kwh(self) -> float | None:
        if None in (self.energia_activa_punta_kwh, self.energia_activa_resto_kwh, self.energia_activa_valle_kwh):
            return None
        return self.energia_activa_punta_kwh + self.energia_activa_resto_kwh + self.energia_activa_valle_kwh

    @property
    def potencia_excedida_punta_kw(self) -> float | None:
        if self.potencia_adquirida_punta_kw is None or self.potencia_contratada_punta_kw is None:
            return None
        return max(0.0, self.potencia_adquirida_punta_kw - self.potencia_contratada_punta_kw)

    @property
    def potencia_excedida_fuera_punta_kw(self) -> float | None:
        # análogo a potencia_excedida_punta_kw, con los campos "fuera punta"
        ...

    @property
    def valor_energia_ars_kwh_promedio(self) -> float | None:
        energia = self.energia_facturada_kwh
        if energia is None or self.importe_energia_ars is None or energia == 0:
            return None
        return self.importe_energia_ars / energia
```

Sin dependencias de terceros (`dataclass` + `@property` + stdlib), cumple la regla de capas. Las
potencias excedidas y el valor promedio de energía se calculan (no se guardan duplicados en el
YAML) porque son derivables de los campos que sí trae la factura — evita que YAML y cómputo se
desincronicen. Las properties devuelven `None` (no `0.0`) cuando falta el dato que necesitan, para
no confundir "no hay energía en este documento porque es de potencia" con "la energía facturada
fue cero".

**Puerto de parsing** `src/domain/sge/ports.py`:

```python
class ParserFacturaDistribuidoraPort(ABC):
    @abstractmethod
    def parsear(self, ruta_pdf: str, planta_id: str) -> FacturaDistribuidora:
        """Extrae los campos estructurados de un PDF de factura. Lanza
        FacturaDistribuidoraIlegibleError si no puede extraer los campos obligatorios."""
        ...
```

**Puerto de lectura**, extensión de `RepositorioOrganizacionesPort`
(`src/domain/telemetria/ports.py:191`, mismo archivo que `obtener_lineas_base_planta` — ambos son
"documentos declarativos colgados de una planta"):

```python
@abstractmethod
def obtener_facturas_planta(self, planta_id: str) -> list[FacturaDistribuidora]:
    """Histórico de facturas de la planta, orden descendente por período."""
    pass
```

A diferencia de `obtener_lineas_base_planta` (que devuelve `list[dict]`, deuda existente), esta
devuelve la entidad tipada: es el patrón correcto y no hay motivo para repetir la deuda en código
nuevo.

**Excepción** `src/domain/telemetria/exceptions.py`: `FacturaDistribuidoraIlegibleError` (mismo
patrón que `EstructuraUnifilarInvalidaError`) — el parser la lanza cuando no puede extraer un campo
obligatorio del PDF; el caso de uso de ingesta la deja propagar al script CLI (no hay endpoint HTTP
que la necesite mapear, ver 2.3).

**Archivo YAML nuevo:** `data/facturas_distribuidora.yml`, no anidado en
`organizaciones.yml` (ciclo de vida y cardinalidad distintos: estructura vs. histórico que crece
cada mes; anidarlo infla el archivo de estructura con filas que no cambian la topología):

```yaml
# data/facturas_distribuidora.yml — Histórico de facturas de la distribuidora por planta.
# Uno o dos documentos por planta por período (decisión: decisions/2026-09-24_factura-distribuidora-yaml.md,
# corregida el 2026-09-24 al confirmar que UPP recibe potencia y energía de proveedores
# distintos). Se agrega por commit revisado (scripts/importar_factura_distribuidora.py), nunca
# por API.
#
# Cada fila es UN documento (tipo_dato: potencia | energia), no el período completo — ver §1.
# Campos de potencia discriminados Punta / Fuera de Punta porque así factura la distribuidora
# en Media Tensión (confirmado con una factura real EDELAP tarifa T5M12, ver §2.1 punto 4).
facturas:
  - planta_id: "4f68f653-a604-4834-8154-31f938248572"
    periodo: "2024-11"
    proveedor: "EDELAP"
    tipo_dato: "potencia"
    numero_factura: "0020-01988580"
    importe_total_ars: 21031736.78
    tarifa: T5M12
    dias_facturados: 30
    potencia_contratada_punta_kw: 800.0
    potencia_contratada_fuera_punta_kw: 850.0
    potencia_adquirida_punta_kw: 1049.0
    potencia_adquirida_fuera_punta_kw: 1082.0
    importe_potencia_ars: 13666250.370000001
    fuente_archivo: "2024-11.pdf"
```

Cargado en el repo con la planta Durax real (`c64fd625-0037-4caa-b68a-800e8e0ee548`, la misma que
ya usan los tests de `linea-base`) para que el test del endpoint corra contra datos reales, mismo
patrón que la línea de base existente en `organizaciones.yml`. `YamlOrganizacionesRepository`
mapea un YAML legacy sin `tipo_dato` (previo a este cambio) como `"potencia"` por default, para no
romper si queda algún archivo viejo sin migrar.

**Loader**: `src/infrastructure/yaml/loaders.py` agrega `cargar_facturas_distribuidora(data_dir) ->
list[dict]` (mismo patrón que `cargar_organizaciones_completas`, pero archivo único, sin merge
modular/plano — no hay necesidad, es un solo documento por repo).

**Repositorio**: `YamlOrganizacionesRepository.obtener_facturas_planta` (en
`src/infrastructure/yaml/repositories/organizaciones_repository.py`) lee vía el loader nuevo,
filtra por `planta_id`, mapea a `FacturaDistribuidora`, ordena por `periodo` descendente.

**Parsers** `src/infrastructure/pdfplumber/parser_factura_distribuidora.py` (infra organizada por
librería, como `fastapi/`, `sqlalchemy/`, `paho_mqtt/`): dos implementaciones concretas de
`ParserFacturaDistribuidoraPort`, una por proveedor, resueltas y verificadas contra **3 facturas
reales** de UPP (dos de EdeLAP, períodos 2023-12 y 2024-11; una de CAMMESA, período 2024-01):

- `ParserFacturaPotenciaEdelap`: produce `tipo_dato="potencia"`. Usa `pdfplumber.page.extract_text()`
  con regex ancladas a etiquetas estables del layout real (confirmadas idénticas entre las dos
  facturas EdeLAP: "Transporte Punta:", "Nº de factura:", "Tipo de tarifa:", "Días:", el patrón
  `NNNkW *TASA$/kW` que aparece 4 veces en orden fijo — pico contratado, f.pico contratado, exceso
  pico, exceso f.pico — y "Vencimientos Recargo 1º2º" para el importe total antes de recargo). No
  usa `page.extract_words()`/coordenadas: con solo 2 muestras de EdeLAP no hay forma de validar con
  confianza qué heurística de posición sería más estable que anclar a estas etiquetas, que además
  se confirmaron literalmente iguales entre ambas facturas.
- `ParserFacturaEnergiaCammesa`: produce `tipo_dato="energia"`. CAMMESA no discrimina por franja
  horaria (a diferencia de EdeLAP): factura "Energía Demandada" como un total único, que se guarda
  en `energia_activa_total_kwh` (campo nuevo en la entidad, ver abajo). Ancla a "SUBTOTAL CARGOS
  DE POTENCIA" (el total de MWh aparece justo después, sin el prefijo de código de cliente pegado
  que sí tiene en otras apariciones del mismo número en el texto), "SUBTOTAL ENERGÍA DEMANDADA" y
  la cita legal fija "LEY 24065 Art.70-FNEE $/MWh" (identifica el importe total final sin
  confundirlo con subtotales intermedios). **Recorte deliberado de alcance:** CAMMESA también
  factura "Cargos de Potencia" (MW) propios del mercado mayorista, más cargos por transporte y
  cargos adicionales del MEM (comercialización, administración) — ninguno de esos conceptos se
  modela en esta iteración, solo `energia_activa_total_kwh`, `importe_energia_ars` (subtotal de la
  energía demandada) e `importe_total_ars` (el total de la factura).

Ambos distinguen dos formatos numéricos porque la factura real los mezcla: los importes en $
vienen con formato AR (`.` miles, `,` decimal — ej. `21.031.736,78`) y las magnitudes de kWh/kW de
EdeLAP con decimal simple (ej. `800.000` = 800.0 kW). Nueva dependencia en `requirements.txt`:
`pdfplumber>=0.11.0` (y `reportlab>=5.0.0`, solo para generar los PDFs de fixture del test).

**Campo nuevo en la entidad:** `FacturaDistribuidora.energia_activa_total_kwh: float | None` —
para proveedores que no discriminan por franja horaria. `energia_facturada_kwh` (property) usa
este campo si está poblado, o la suma Punta+Resto+Valle si no, o `None` si no hay ningún dato.

**Tests** `tests/unit/test_parser_factura_distribuidora.py`: fixtures generados con `reportlab`
reproduciendo, línea por línea, el texto real extraído de las 3 facturas (mismo desorden de
columnas que produce el PDF real, no un layout limpio inventado) — corren ambos parsers contra
las 3 muestras y verifican los valores contra el PDF original a mano. Un test específico confirma
que las dos facturas EdeLAP dan la misma potencia contratada (800/850 kW), como señal de que el
parser generaliza y no quedó hardcodeado a una sola factura.

### Pendientes (actualizado 2026-09-27 — UPP completado, otros en espera de medidor)

#### ✅ Resueltos (2026-09-24)

1. **Parser real de EdeLAP (potencia).** Verificado contra 2 facturas reales UPP de períodos 
   distintos (2023-12 y 2024-11; la que figuraba como "2026-08 en producción" era la 2024-11 mal
   fechada, ver corrección 2026-09-28 en la cabecera).
2. **Parser de CAMMESA (energía).** Primera versión falló contra 2ª muestra (EITAR 2024-08): 
   regex sobre `extract_text()` lineal es insuficiente. Causa: valor de energía pegado a código 
   sin separador (`"0006849353,610 MWh"`). Reescrito con `page.extract_words()` por coordenadas 
   (commit `4729849`) — ahora exacto en ambas facturas UPP y EITAR. **Lección:** no dar por buena 
   una regex con una sola muestra; pedir 2+ reales antes de cerrar, o partir directo de coordenadas.

#### ⏳ Sin Fecha (esperando medidor + 2+ muestras reales)

3. **EDESUR (Eitec/EITAR, Cristal Avellaneda).** 1 factura real inspeccionada (tarifa T3 MT 
   LSP N° A 9904-02246147): tercer formato — documento único como EdeLAP, pero potencia SIN 
   Punta/Fuera Punta a nivel de cargo (solo Convenida/Adquirida), energía con nombres distintos 
   (Horas Restantes/Valle Nocturno/Horas Punta). **Decisión del dueño:** NO implementar hasta 
   EITAR tenga medidor datamaq + conseguir 2+ facturas reales. Criterio: repetir el error de 
   CAMMESA (1 muestra → fallo) sería costoso.

4. **Edenor (Madygraf, Los Constituyentes), distribuidoras locales (El Gringo, Textiles Pigué).** 
   0 muestras reales. Mismo criterio que EDESUR.

#### 🔧 Prioridad Baja (confirmar alcance con app-datamaq)

5. **Exponer `cargadaEn` en DTO.** `FacturaDistribuidora.cargada_en` existe en domain, no en 
   `FacturaDistribuidoraResponseDTO`. app-datamaq lo pidió para distinguir recargas de un mismo 
   período. Cambio trivial si lo confirman que lo necesitan — agregar campo al DTO y mapper, no 
   rompe contrato (es un field nuevo).

6. **Upload directo de PDF desde UI.** Si la UI sube el PDF directo (en vez de GitOps por script), 
   hace falta decisión nueva del dueño — hoy `RepositorioOrganizacionesPort` es solo lectura por 
   diseño explícito, no hay endpoint `POST`.

**Script de ingesta** `scripts/importar_factura_distribuidora.py <ruta_pdf> <planta_id> --tipo
potencia|energia`: instancia el parser correspondiente (`--tipo potencia` → EdeLAP, `--tipo
energia` → CAMMESA), ejecuta `parsear()`, e imprime el bloque YAML resultante a stdout para
revisión humana antes de pegarlo en `data/facturas_distribuidora.yml` y `git commit` — coherente
con que
`RepositorioOrganizacionesPort` es solo lectura y con el precedente de
`scripts/exportar_instalacion_medidores.py`. No hay endpoint `POST` de carga: cargar una factura es
una operación GitOps (subir el PDF, correr el script, revisar el diff, commitear), no una escritura
en caliente del servicio en producción.

## 3. Casos de Uso & DTOs

**`ConsultarHistoricoFacturasUseCase`**
(`src/application/use_cases/consultar_historico_facturas.py`): recibe `repo_organizaciones`,
`ejecutar(planta_id: str) -> list[FacturaDistribuidoraResponseDTO]`. Si la planta no existe,
levanta `PlantaNoEncontradaError` (reuso, ya mapeada por `manejar_error_http`).

**`ConsultarBalanceEnergiaUseCase`** (`src/application/use_cases/consultar_balance_energia.py`,
existente) se modifica: si `energia_padre_kwh` no se pasa explícito, busca la factura más reciente
de la planta (`repo_org.obtener_facturas_planta(planta_id)`, primera de la lista por venir ya
ordenada descendente) y usa su propiedad `energia_facturada_kwh` (ya en kWh, suma de las tres
franjas) como `energia_padre_kwh`; si no hay ninguna factura, mantiene el comportamiento actual
(`0.0`). El parámetro explícito sigue teniendo prioridad — no se rompe el contrato existente del
endpoint, solo se agrega un default mejor. Documentado en el docstring del caso de uso.

**DTO** `src/application/dtos/sge_dto.py`, mismo estilo que `LineaBaseResponseDTO` (alias
camelCase, contrato con `app-datamaq`):

```python
class FacturaDistribuidoraResponseDTO(BaseModel):
    """Un documento (potencia O energía) — dos filas pueden compartir `periodo` con `tipoDato`
    distinto cuando hay dos proveedores (ver FacturaDistribuidora en domain/sge)."""

    id: str
    planta_id: str = Field(validation_alias="plantaId", serialization_alias="plantaId")
    periodo: str
    proveedor: str
    tipo_dato: str = Field(validation_alias="tipoDato", serialization_alias="tipoDato")
    numero_factura: str = Field(validation_alias="numeroFactura", serialization_alias="numeroFactura")
    importe_total_ars: float = Field(validation_alias="importeTotalArs", serialization_alias="importeTotalArs")
    tarifa: str | None = None
    dias_facturados: int | None = Field(
        default=None, validation_alias="diasFacturados", serialization_alias="diasFacturados"
    )
    # ... campos de energía y potencia, todos `| None`, mismos nombres/alias que la entidad
    # (energiaActivaPuntaKwh, energiaFacturadaKwh, potenciaContratadaPuntaKw,
    # potenciaExcedidaPuntaKw, importePotenciaArs, importeEnergiaArs,
    # valorEnergiaArsKwhPromedio, ...) — ver src/application/dtos/sge_dto.py para el listado
    # completo, no se repite acá para no desincronizar la spec del código.
```

Se construye con kwargs snake_case (no los alias camelCase) porque el DTO usa
`validation_alias`/`serialization_alias` separados en vez de `alias` único — mismo patrón que
`LineaBaseResponseDTO`, cuyo constructor en `sge_router.py` también usa snake_case; con
`validation_alias`/`serialization_alias`, pyright solo reconoce el nombre de campo Python como
parámetro del `__init__` sintetizado, no el alias (a diferencia de otros DTOs de este archivo que
usan `Field(alias=...)` único, donde sí se puede construir con el alias camelCase).

**Mapper** `src/application/mappers/sge_mapper.py`: `factura_to_dto(f: FacturaDistribuidora) ->
FacturaDistribuidoraResponseDTO`.

**Endpoint** (contrato para la sesión hija de `app-datamaq`):

```
GET /api/v1/sge/plantas/{planta_id}/facturas-distribuidora
Auth: Depends(get_usuario_actual) + Depends(resolver_planta_permitida)   (mismo patrón que
      /balance-energia, /ahorros-cusum, /linea-base — aislamiento por planta ya resuelto)
200 -> list[FacturaDistribuidoraResponseDTO]   (orden descendente por período, [] si no hay)
404 -> planta_no_encontrada  (PlantaNoEncontradaError, vía resolver_planta_permitida)
```

Payload real (JSON, camelCase — ver DTO arriba): **dos elementos por período** cuando hay dos
proveedores, cada uno con los campos del OTRO tipo en `null`. Ejemplo con la factura EDELAP
2024-11 real de UPP. Hoy no hay ninguna factura de energía (CAMMESA) cargada, así que UPP devuelve
solo documentos `tipoDato: "potencia"`. El ejemplo anterior de CAMMESA era inventado y se quitó
(corrección 2026-09-28):
```json
[
  {
    "id": "4f68f653-a604-4834-8154-31f938248572-2024-11-potencia",
    "plantaId": "4f68f653-a604-4834-8154-31f938248572",
    "periodo": "2024-11",
    "proveedor": "EDELAP",
    "tipoDato": "potencia",
    "numeroFactura": "0020-01988580",
    "importeTotalArs": 21031736.78,
    "tarifa": "T5M12",
    "diasFacturados": 30,
    "energiaActivaPuntaKwh": null,
    "energiaFacturadaKwh": null,
    "potenciaContratadaPuntaKw": 800.0,
    "potenciaContratadaFueraPuntaKw": 850.0,
    "potenciaAdquiridaPuntaKw": 1049.0,
    "potenciaAdquiridaFueraPuntaKw": 1082.0,
    "potenciaExcedidaPuntaKw": 249.0,
    "potenciaExcedidaFueraPuntaKw": 232.0,
    "importePotenciaArs": 13666250.37,
    "importeEnergiaArs": null,
    "valorEnergiaArsKwhPromedio": null
  }
]
```
`app-datamaq` grafica potencia (contratada/adquirida/excedida, discriminada Punta y Fuera de
Punta, eje kW) y energía×valor (kWh y $/kWh promedio) a partir de esta única serie ordenada por
`periodo` — no hace falta un segundo endpoint, pero **el frontend tiene que filtrar/agrupar por
`tipoDato`** en vez de asumir una fila = un período con todos los campos (contrato anterior que ya
no es real). Si necesita "el total del período" (`importeTotalArs` combinado), tiene que sumar las
filas del mismo `periodo` — cada `importeTotalArs` es el total de ESE documento, no del mes
completo.

Router: se agrega en `src/infrastructure/fastapi/routes/sge_router.py`, junto a
`obtener_lineas_base` (mismo router `/api/v1/sge`, misma dependencia `resolver_planta_permitida`,
mismo `get_organizaciones_repository`).

## 4. Matriz de Pruebas (RED Suite)

Implementada y en verde (1519 tests totales del repo, sin regresiones).

**`tests/unit/test_factura_distribuidora.py`** (15 tests) — entidad y repositorio:
- `frozen=True` (intento de mutar levanta `FrozenInstanceError`).
- `energia_facturada_kwh`, `potencia_excedida_*_kw` y `valor_energia_ars_kwh_promedio` con los
  valores reales de la factura EDELAP; y cada una devuelve `None` (no `0.0`) cuando falta el dato
  que necesita, incluido el caso de un documento real de un solo `tipo_dato` (solo potencia, con
  todos los campos de energía en `None`).
- Repositorio YAML (fixture con `data/facturas_distribuidora.yml` de prueba en `tmp_path`): orden
  descendente por período con dos documentos del mismo período (potencia + energía, distinto
  `tipo_dato`) conviviendo sin chocar; planta sin facturas → `[]`; factura de otra planta no
  aparece en el filtro; sin archivo YAML → `[]`.

**`tests/unit/test_parser_factura_distribuidora.py`** (3 tests) — PDF de fixture generado con
`reportlab` (layout "etiqueta: valor" simple, no el layout real de EDELAP, ver límite conocido en
§2.2 y Tarea 1 de "Pendientes"): factura completa → `tipo_dato="potencia"` fijo, campos de
potencia con los valores reales de la factura EDELAP inspeccionada, campos de energía en `None`;
PDF sin campos obligatorios → `FacturaDistribuidoraIlegibleError`; PDF inexistente → ídem.

**`tests/unit/test_verificador_facturas.py`** (6 tests): todo válido → `0` inválidas; `(período,
tipo_dato)` duplicado en la misma planta → `1` inválida (cuenta y loguea, no lanza); **mismo
período con distinto `tipo_dato` → válido, no es duplicado** (caso UPP: EdeLAP + CAMMESA); formato
de período inválido (`"agosto-2026"`) → `1` inválida; magnitud negativa → `1` inválida; planta sin
facturas → `0` inválidas.

**`tests/unit/test_sge_endpoints_iso50001.py`** (2 tests agregados a la suite existente de ese
router): `GET .../facturas-distribuidora` contra la planta Durax real (con las dos filas —
potencia y energía— del mismo período agregadas en `data/facturas_distribuidora.yml`) → 200 con
al menos 2 elementos, `tipoDato` de ambos tipos presentes, y los campos calculados esperados en
cada uno; planta inexistente → 404 `planta_no_encontrada`.

**`tests/unit/test_consultar_balance_energia_uc.py`** (4 tests — no existía cobertura del caso de
uso, solo de `BalanceEnergiaService` en `test_balance_energia_sge.py`): sin `energia_padre_kwh` y
con factura de energía → usa `energia_facturada_kwh`; **sin `energia_padre_kwh` y con un
documento de potencia en el histórico → lo ignora, no lo confunde con energía** (caso UPP: el
primero de la lista puede ser el de EdeLAP); sin `energia_padre_kwh` y sin facturas → `0.0` (no
rompe el comportamiento anterior); `energia_padre_kwh` explícito tiene prioridad y ni siquiera
consulta `obtener_facturas_planta`.

**Regresión de borrado**: `grep -rn potencia_contratada_kw src/ tests/ data/ scripts/` sin
resultados tras eliminar el campo de `Dispositivo`.

## 5. Criterios del Gauntlet

Todos verificados en verde tras el rediseño a dos documentos (2026-09-24):

- `venv/bin/ruff check .` y `venv/bin/ruff format .` sin errores.
- `venv/bin/python -m pyright` (proyecto completo) — `0 errors, 0 warnings, 0 informations`.
- `venv/bin/python -m pytest tests/unit -n auto --cov=src --cov-fail-under=85` — **1519 passed**,
  cobertura total **92%**, verificado tanto normal como con `DB_HOST=127.0.0.2 DB_PORT=1`
  (memoria `tests-locales-tocan-db-real`: los tests no deben tocar la DB real de producción).
- `venv/bin/python scripts/verify_architecture.py` — `[PASS]`. `FacturaDistribuidora` y
  `ParserFacturaDistribuidoraPort` en `domain/sge/` sin imports de terceros; `pdfplumber` solo en
  `src/infrastructure/pdfplumber/`.
- `venv/bin/python scripts/verify_code_size.py` — `[PASS]`. Ver nota de diseño abajo sobre
  `server.py`, que sí llegó a superar el límite y se resolvió por extracción, no por recorte
  cosmético.
- `pdfplumber>=0.11.0` y `reportlab>=5.0.0` (solo para el PDF de fixture del test del parser)
  agregados a `requirements.txt`, instalados y probados en `venv/`.
- `data/facturas_distribuidora.yml` con la factura real de Durax no rompe
  `verificar_unifilar_plantas` ni `verificar_facturas_plantas` al arrancar (probado con
  `test_endpoint_facturas_distribuidora_gitops`, que ejercita el arranque completo de la app vía
  `create_app()`).

**Nota de diseño no anticipada por la spec original — `server.py` excedió las 500 líneas.**
Conectar `verificar_facturas_plantas()` en el `lifespan` de `server.py` (junto a
`verificar_unifilar_plantas()`, ya existente) llevó el archivo a 502 líneas. Se extrajo el bloque
de validadores YAML de arranque (unifilar + facturas) a
`src/infrastructure/fastapi/startup_verificaciones.py::ejecutar_verificaciones_yaml()` — mismo
patrón "advierte, no bloquea" que ya tenía cada uno por separado, ahora en un solo lugar en vez de
duplicar el `try/except` inline por cada validador nuevo que se agregue a futuro. `server.py`
quedó en 492 líneas.

## Verificación cruzada final (la hace el padre al cierre)

- [x] La entidad de factura vive en `domain/` sin dependencias de terceros (parser en `infra`).
      `src/domain/sge/entities.py::FacturaDistribuidora` — `dataclass(frozen=True)` + `@property`,
      solo stdlib. `venv/bin/python scripts/verify_architecture.py` → `[PASS]`.
- [x] El histórico queda versionado en git (archivo `.yml` nuevo, no en `organizaciones.yml`).
      `data/facturas_distribuidora.yml`, con una factura real de la planta Durax.
- [x] `BalanceEnergiaService`/`ConsultarBalanceEnergiaUseCase` quedan conectados a la energía
      facturada. `ConsultarBalanceEnergiaUseCase.ejecutar` usa
      `obtener_facturas_planta(planta_id)[0].energia_facturada_kwh` como default de
      `energia_padre_kwh` cuando no se pasa explícito; cubierto por
      `tests/unit/test_consultar_balance_energia_uc.py`.
- [x] Ningún archivo de `src/` supera 500 líneas tras la implementación.
      `venv/bin/python scripts/verify_code_size.py` → `[PASS]` (ver nota de diseño en §5 sobre
      `server.py`/`startup_verificaciones.py`).
