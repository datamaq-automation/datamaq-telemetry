# Informe de Cambios de Contrato — Desagregación de Cargas (`/api/v1/cargas`)

> **Para:** equipo de `app-datamaq`
> **Fecha:** 2026-09-04
> **Tipo de cambio:** **aditivo puro**. Recurso nuevo. **Cero breaking changes.**

---

## 1. Resumen para quien no quiera leer el resto

Se agregó el recurso `/api/v1/cargas`. **No se modificó ningún DTO, endpoint ni enum existente**, en particular nada de `/api/v1/telemetria`. Si el frontend no consume el recurso nuevo, no hay nada que hacer.

Este informe existe porque `CONVENTIONS.md` §5 lo pide para cualquier cambio de contrato, y porque hay antecedente de una rotura por un valor de enum nuevo llegando sin aviso.

---

## 2. Qué se agregó

Recurso `/api/v1/cargas` — catálogo de electrodomésticos o cargas detrás de un medidor agregado, campañas para medir su firma eléctrica, y atribución del consumo entre ellas.

| Método | Ruta | Devuelve |
|---|---|---|
| `GET` | `/api/v1/cargas?device_id&solo_activas` | `CargaResponseDTO[]` |
| `POST` | `/api/v1/cargas` | `CargaResponseDTO` |
| `GET`/`PATCH` | `/api/v1/cargas/{carga_id}` | `CargaResponseDTO` |
| `PUT` | `/api/v1/cargas/{carga_id}/firma` | `CargaResponseDTO` |
| `GET` | `/api/v1/cargas/perfil?device_id&dias&zona` | `PerfilConsumoResponseDTO` |
| `POST` | `/api/v1/cargas/campanas/activas` \| `/pasivas` | `CampanaResponseDTO` |
| `GET` | `/api/v1/cargas/campanas/{campana_id}` | `CampanaResponseDTO` |
| `PATCH` | `/api/v1/cargas/campanas/{id}/finalizar` \| `/descartar` | `CampanaResponseDTO` |
| `GET` | `/api/v1/cargas/{carga_id}/campanas` | `CampanaResponseDTO[]` |
| `POST` | `/api/v1/cargas/analisis?device_id&dias` | `AnalisisConsumoResponseDTO` |
| `GET` | `/api/v1/cargas/atribucion?device_id&dias` | `AtribucionConsumoResponseDTO` |
| `GET` | `/api/v1/cargas/{carga_id}/intervalos?limite` | `IntervaloActividadResponseDTO[]` |
| `PATCH` | `/api/v1/cargas/intervalos/{id}/corregir` | `IntervaloActividadResponseDTO` |

Autenticación igual que el resto: cookie `datamaq_token`. Las escrituras requieren rol distinto de `invitado`; **todas las lecturas, incluido `/perfil` y `/atribucion`, están disponibles para `invitado`**.

---

## 3. Enums nuevos

Todos viven **solo** dentro del recurso nuevo. Ninguno se agregó a un enum ya consumido.

```ts
type CategoriaCarga = "REFRIGERACION" | "COCCION" | "CALENTAMIENTO_AGUA" | "LAVADO"
                    | "ILUMINACION" | "CLIMATIZACION" | "FUERZA_MOTRIZ" | "OTROS";
type NaturalezaElectrica = "RESISTIVA" | "MOTOR" | "ELECTRONICA" | "MIXTA";
type PatronOperacion = "CICLICO_TERMOSTATICO" | "MANUAL_PULSO" | "MANUAL_PROLONGADO"
                     | "PROGRAMADO_SECUENCIAL" | "CONTINUO_DIARIO" | "INDETERMINADO";
type OrigenFirma = "CHAPA" | "CAMPANA" | "INFERIDA";
type TipoCampana = "ACTIVA" | "PASIVA";
type EstadoCampana = "EN_CURSO" | "COMPLETADA" | "CONTAMINADA" | "DESCARTADA";
type MotivoDescarte = "SIN_MUESTRAS" | "SIN_LINEA_BASE" | "SIN_ENCENDIDO_DETECTADO"
                    | "DISPERSION_EXCESIVA" | "ESCALON_AJENO" | "CICLOS_INSUFICIENTES";
type OrigenClasificacionCarga = "REGLA" | "CORRECCION_HUMANA";
```

> Se prevé agregar valores a `CategoriaCarga` y `MotivoDescarte` a medida que aparezcan casos. **Validar con `safeParse` y una rama por defecto**, no con `parse`.

---

## 4. Contratos TypeScript

```ts
interface FirmaCargaDTO {
  potencia_w: number;
  dispersion_w: number;
  potencia_reactiva_var: number | null;
  factor_potencia: number | null;
  duracion_encendido_s: number | null;
  duracion_encendido_mad_s: number | null;
  duracion_apagado_s: number | null;
  pico_arranque_w: number | null;
  origen: OrigenFirma;
  muestras: number;
  medida_en: string | null;   // ISO 8601 con offset
  es_resistiva: boolean;
  esta_completa: boolean;     // tiene potencia Y duración: sin duración no desambigua
}

interface CargaResponseDTO {
  id: string; dispositivo_id: string; nombre: string;
  categoria: CategoriaCarga;
  naturaleza_electrica: NaturalezaElectrica;
  patron_operacion: PatronOperacion;
  potencia_nominal_w: number | null;   // de chapa, declarada
  potencia_esperada_w: number | null;  // firma medida si existe, si no la chapa
  firma: FirmaCargaDTO | null;
  esta_caracterizada: boolean;
  activa: boolean;
  creado_en: string; actualizado_en: string;
}

interface PerfilConsumoResponseDTO {
  dispositivo_id: string; desde: string; hasta: string;
  dias_analizados: number; zona_horaria: string;
  cantidad_lecturas: number; lecturas_truncadas: boolean;
  linea_base: {
    linea_base_W: number | null;
    linea_base_nocturna_W: number | null;  // consumo con la casa "apagada"
    linea_base_diurna_W: number | null;
    delta_diurno_W: number | null;         // ojo: NO es "iluminación", ver abajo
    potencia_media_W: number | null; potencia_maxima_W: number | null;
    muestras: number; ventanas_nocturnas: number; ventanas_diurnas: number;
    cadencia_mediana_s: number | null;
  };
  ciclos_sobre_linea_base: {
    ciclos: number;
    duracion_encendido_mediana_s: number | null;
    duracion_encendido_mad_s: number | null;
    duracion_apagado_mediana_s: number | null;
    duracion_apagado_mad_s: number | null;
    periodo_mediano_s: number | null;
    duty_cycle: number | null;             // fracción [0,1]
    patron: PatronOperacion;
    es_regular: boolean;
    cadencia_mediana_s: number | null;
  };
  umbral_ciclos_W: number | null;
  regimenes: RegimenOperacionDTO[];        // el mismo tipo que ya usa /disponibilidad
  advertencia_cadencia: string | null;     // mostrar siempre que venga, ver §5
}

interface AtribucionConsumoResponseDTO {
  dispositivo_id: string; desde: string; hasta: string;
  energia_total_kwh: number | null;        // del contador acumulado, exacto
  energia_atribuida_kwh: number;
  residual_kwh: number | null;
  residual_porcentaje: number | null;      // fracción [0,1]
  items: {
    carga_id: string | null;               // null = "No atribuido"
    nombre: string;
    energia_kwh: number;
    porcentaje: number;
    intervalos: number;
    confianza_media: number | null;
  }[];
  calidad_suficiente: boolean;
  advertencia: string | null;
}
```

---

## 5. Tres cosas que la UI tiene que respetar

**1. `advertencia_cadencia` no es decorativa.** A 300 s de cadencia hay aparatos que el medidor nunca midió: una pava de 3 minutos tiene ~60% de chance de dejar *una sola* muestra. Si el perfil no los muestra no es porque no se usaron. Mostrar el texto tal cual viene, para que el usuario distinga **"no hubo"** de **"no se pudo ver"**.

**2. `delta_diurno_W` no es iluminación.** Es la diferencia entre la línea de base diurna y la nocturna: todo lo que se suma de día y no se puede separar en escalones. Etiquetarlo "iluminación" en la UI sería inventar precisión que el dato no tiene.

**3. El item con `carga_id: null` ("No atribuido") es un resultado, no un error.** Hay exactamente una fila así como máximo, y agrupa tanto los episodios detectados sin imputar como el residual del balance contra el contador. Los porcentajes se calculan todos contra el consumo real. **Cuando `residual_kwh` es negativo**, lo atribuido supera al total medido: hay cargas contándose dos veces por anidamiento, `calidad_suficiente` viene en `false` y `advertencia` lo explica. En ese caso los porcentajes suman más de 100 — es correcto y hay que mostrarlo así, no normalizarlo.

---

## 6. Códigos de error

| Situación | HTTP | `detail` |
|---|---|---|
| Carga / campaña / intervalo inexistente | `404` | mensaje en castellano |
| Firma inválida (dispersión > potencia) | `400` | mensaje |
| Carga duplicada en el mismo medidor, campaña ya en curso, campaña ya cerrada | `422` | mensaje |
| Rol `invitado` intentando escribir | `403` | `forbidden` |
| Validación de contrato (Pydantic) | `422` | detalle estándar de FastAPI |

`detail` es un **string**, igual que en el resto de la API.

---

## 7. Deuda de contrato conocida

* El factor horario del emparejador es neutro: falta declarar franjas típicas por carga, lo que agregaría campos opcionales a `CargaResponseDTO` (aditivo).
* Heladera y freezer pueden no separarse; se evalúa un agrupamiento `REFRIGERACION` que agregaría un valor a un enum ya consumido. **Ese sí sería un cambio a coordinar.**
