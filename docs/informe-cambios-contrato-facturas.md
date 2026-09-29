# Informe de Cambios de Contrato — Facturas de la distribuidora (UPP)

> **Para:** equipo de `app-datamaq`
> **Fecha:** 2026-09-28 · en producción desde `7e517da` (datos: datamaq-data `6c2ce49`)
> **Tipo de cambio:** **sin cambios de forma.** Cambian los datos de UPP y la semántica de
> `potenciaAdquirida*Kw`. **Cero breaking changes** según `CONVENTIONS.md` §5.
> **Versión para compartir:** artefacto "Contrato de facturas UPP"
> (https://claude.ai/artifact/FuYW45JEfGJcQdtNiC1QRV). Si difieren, manda este archivo.

---

## 1. Resumen

Ningún DTO cambió de forma: mismos campos, tipos y nulabilidad en
`GET /api/v1/sge/plantas/{plantaId}/facturas-distribuidora` y `GET …/costo-estimado`. Cambiaron los
datos de UPP (`4f68f653-a604-4834-8154-31f938248572`): se quitaron 2 filas falsas y se cargaron las 12
facturas reales de EDELAP. También cambió el significado de `potenciaAdquirida*Kw`. Si el frontend ya
agrupa por `tipoDato` y trata `null` como "sin dato", no hay nada que migrar.

Este informe existe porque el OpenAPI no muestra ninguno de estos cambios (ver §4).

---

## 2. Qué cambió

| Qué | Antes | Ahora |
|---|---|---|
| Documentos de UPP | 2, del período "2026-08": EDELAP potencia + CAMMESA energía. Eran falsos: la factura EDELAP 2024-11 mal fechada y una fila de CAMMESA armada a mano con datos de EDELAP. | 12 documentos `tipoDato: "potencia"`, `proveedor: "EDELAP"`, de 2023-12 a 2024-11, sin huecos. |
| Documentos de energía | 1 (el falso de CAMMESA) | **Ninguno.** Los campos de energía llegan en `null`. |
| `importeTotalArs` | 0 en 11 filas (bug de regex del parser) | Total real del 1º vencimiento, con impuestos (ej. 2024-11: 21.031.736,78). |
| `potenciaAdquiridaPuntaKw` / `potenciaAdquiridaFueraPuntaKw` | Contratada + exceso facturado | **Demanda registrada por el medidor.** Fuera de punta = máx(resto, valle), igual que factura EDELAP. En un mes sin exceso queda por debajo de la contratada (2024-02: 508 / 529 kW, contratada 800 / 850). |
| `potenciaExcedida*Kw` | Exceso facturado | Sigue siendo `max(0, adquirida − contratada)`. En 2024-09 da 345 kW y EDELAP facturó 344: la demanda registrada fue 1145 kW. |
| `importePotenciaArs` | Suma de un tramo de texto de la factura | Solo potencia contratada + excesos (neto, sin impuestos). Igual que antes en 11 meses; en 2024-02 ya no incluye interés por mora ni el CTT. |
| `costo-estimado` de UPP | ≈2,02 $/kWh sacado de la fila falsa de CAMMESA | `valorEnergiaArsKwhPromedio: null`, `costoEnergiaArs: null` (caso "s/d", decisión 2026-09-27 D1). |

Commits: `690b868` (importe total), `7e517da` (demanda registrada, meses sin exceso),
`e800676` (spec); datamaq-data `001771a` (quita las filas falsas), `6c2ce49` (carga 2024-02).

---

## 3. Qué revisar en `app-datamaq`

Verificado leyendo el código de `app-datamaq` el 2026-09-28, sin modificarlo.

1. **Bug: 404 al entrar a Facturas por slug.** `src/app/views/FacturasPage.vue` pide el histórico antes
   de que cargue el catálogo de plantas. El fallback `?? plantaIdRuta.value` manda
   `planta-principal-upp` y el backend responde `404 planta_no_encontrada`. El backend solo acepta
   UUID: la traducción slug → UUID es del frontend (decisión 2026-09-25). No pedir hasta tener el
   UUID resuelto.
2. **Bug: respuestas viejas en `facturasStore.cargarHistorico`.** No descarta las respuestas cuyo
   `idPlanta` ya no es el actual. Si el 404 del slug llega después que la respuesta buena, `error`
   queda cargado aunque haya datos.
3. **Revisar:** `src/app/views/UnifilarPage.vue` usa el mismo patrón de resolución del slug.
4. **Hecho, sin pushear** (`58530b4`, `613a4b8`, `3b2f387`): gráfico de energía sin barras de 2 px
   cuando no hay dato, meses faltantes rotulados "s/f" y comentarios que presentaban el par
   "2026-08" como dato real.
5. **Recordatorio:** validar con `safeParse`, no con `parse`. Los próximos campos (§5) van a llegar
   como opcionales y aditivos.

---

## 4. Cómo leer el contrato

`/openapi.json`, `/docs` y `/redoc` están publicados solo para la tailnet (decisión
2026-09-19): el dominio público devuelve 403. Caminos verificados el 2026-09-28:

```bash
# Desde una máquina en la tailnet: resolver el dominio a la IP Tailscale del VPS
curl --resolve api.datamaq.com.ar:443:100.93.233.48 \
  https://api.datamaq.com.ar/openapi.json -o openapi.json

# Por SSH al VPS: Uvicorn escucha en localhost
ssh vps 'curl -s http://127.0.0.1:8885/openapi.json' > openapi.json
```

- **Lo que sí dice:** 84 rutas, con sus parámetros y respuestas; campos, tipos y nulabilidad de cada
  DTO (camelCase). Sirve para generar tipos o comparar contra los schemas de Zod.
- **Lo que no dice:** cambios de datos (lo de este informe no aparece en ningún diff del schema);
  semántica (solo 45 de 790 propiedades tienen descripción, y ninguna de
  `FacturaDistribuidoraResponseDTO` ni de `CostoEstimadoResponseDTO`); versión (siempre `1.0.0`).

La forma del contrato se consulta en el OpenAPI. Los cambios de semántica o de datos se siguen
avisando con un informe como este.

---

## 5. Qué viene (sin fecha)

- **Cargos unitarios e impuestos** en cada factura ($/kW, $/kWh, IVA, percepciones, subsidio). Todos
  opcionales. La decisión está redactada y espera la respuesta del dueño.
- **Facturas de CAMMESA de UPP.** Cuando el parser nuevo las lea, van a aparecer documentos
  `tipoDato: "energia"` y el costo estimado va a dejar de ser "s/d".
- **Penalización por energía reactiva.** Cambiaría la fórmula del banner a kVArh excedente × $/kVArh
  del cuadro tarifario, y se presentaría como exposición, no como recargo ya cobrado. Afecta a
  `BannerPenalizacionReactiva.vue`.
