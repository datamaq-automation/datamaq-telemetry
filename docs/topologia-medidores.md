# Topología de Medidores: Mapeo YAML ↔ Base de Datos

**Última actualización:** 2026-10-05  
**Fuentes:** `data/organizaciones.yml`, DB producción (`datamaq_telemetry.devices`, `datamaq_telemetry.telemetry_energy`)

---

## Mapeo Completo

| Alias YAML | Device UID | Device ID (UUID) | Nombre | Organización | Planta | Fases | Tipo | Datos desde | Estado |
|---|---|---|---|---|---|---|---|---|---|
| – | N/A | `2812d2af-b1cf-4daa-a379-40102fdb152d` | Tablero Principal | Hogar (medidor doméstico) | Casa | R | CONSUMO | 2026-09-01 | ONLINE |
| – | N/A | `51048a93-f1f3-4283-a708-24cbd39c7192` | TGBT Usina | Vajillas Durax | Planta Durax | R,S,T | CONSUMO | 2026-09-10 | ONLINE |
| – | N/A | `b5f4bcd6-b017-4796-bb3d-efcfb50dc8f0` | TGBT Horno | Vajillas Durax | Planta Durax | R,S,T | CONSUMO | 2026-09-10 | ONLINE |
| – | N/A | `a01b1642-ed29-4c3e-a793-f57de09504f8` | TGBT Arriba | Unión Papelera Platense | Planta UPP | R,S,T | CONSUMO | 2026-09-11 | ONLINE |
| – | N/A | `ce7e5a9a-c5e8-4936-be9a-a2057ccf8b4c` | TGBT Abajo | Unión Papelera Platense | Planta UPP | R,S,T | CONSUMO | 2026-09-11 | ONLINE |
| – | `D4:8C:49:F0:35:A8` | `7434647d-5b87-4d4e-b4a5-a0d351315f0a` | TGBT Trafo 1 | Los Constituyentes | Planta San Martín | R,S | CONSUMO | 2026-09-16 | ONLINE |
| **369** | `EC:C9:FF:B5:7F:20` | `c91713f1-0621-4a33-9279-c5327a317d96` | TGBT Trafo 2 | Los Constituyentes | Planta San Martín | R,S | CONSUMO | 2026-09-17 | ONLINE |

---

## Notas Importantes

### 1. IDs de YAML vs Database

- **YAML:** Usa alias numéricos (ej. `369`) o nombres legibles en documentación interna
- **Database:** Usa UUIDs (`device_id`) como clave primaria
- **Device UID (MAC):** Identificador del hardware (ECC9FFB57F20 para Trafo 2)

**Nunca asumir que '369' en YAML = '369' en DB.** Siempre mapear explícitamente.

### 2. Organización del Datos

```
organizaciones.yml
├── organizaciones[0]  (Hogar)
│   └── plantas[0]
│       └── medidores[0] → dispositivo_id: 2812d2af...
├── organizaciones[1]  (Vajillas Durax)
│   └── plantas[0]
│       └── medidores[] → dispositivo_ids: 51048a93..., b5f4bcd6...
├── organizaciones[2]  (Unión Papelera Platense)
│   └── plantas[0]
│       └── medidores[] → dispositivo_ids: a01b1642..., ce7e5a9a...
└── organizaciones[3]  (Los Constituyentes)
    └── plantas[0]  (San Martín)
        └── medidores[] → dispositivo_ids: 7434647d..., c91713f1... ✅ (Trafo 2)
```

### 3. Distribuidoras

**Importante:** Una planta puede tener múltiples distribuidoras (no son opciones mutuamente excluyentes).

- **Los Constituyentes (San Martín, Trafo 2):** EDELAP y CAMMESA (ambas facturan)
- **Unión Papelera Platense:** (verificar en documentos de facturación)

### 4. Validación de Consistencia

Ver `scripts/validate_topology.py` para:
- Verificar que todos los dispositivos en YAML existen en DB
- Detectar medidores sin datos (offline, no configurados)
- Alertar sobre mismatches device_uid
- Reportar discrepancias de fase (YAML vs DB)

---

## Cómo Actualizar Este Documento

1. Editar `data/organizaciones.yml` con nueva planta/medidor
2. Crear dispositivo en DB (via API o migración SQL)
3. Ejecutar: `python scripts/validate_topology.py --update-docs`
4. Commit ambos: `organizaciones.yml` y este documento

