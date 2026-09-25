# Estado actual: Integración GF-SMBOX-PLUS

**Fecha:** 2026-09-25 15:00 UTC  
**Problema:** 🔴 BLOQUEADOR - Local Key no accesible

---

## Problema detectado

El GF-SMBOX-PLUS está **funcional en Smart Life** pero **NO aparece en API Tuya**.

### Hechos comprobados

✅ **Funciona:**
- Dispositivo conectado a WiFi "Maestros"
- Smart Life lo controla (encender/apagar funciona)
- Conectividad: -41 dBm (excelente)

❌ **No funciona:**
- API Cloud Tuya: 0 dispositivos encontrados
- Región US, EU, SA, CN, IN: todas 0 dispositivos  
- Cuenta: agustin.deoz@gmail.com
- ADB: No se pudo conectar smartphone para extracción local
- Broadcast local: No responde en puertos 6666-6668

### Causa probable

El dispositivo fue vinculado a una **cuenta Google OAuth diferente** o **nunca se registró en API Tuya** (solo en Smart Life local).

---

## Soluciones alternativas

### Opción 1: Readicionar el dispositivo
**Proceso:**
1. Desvincula en Smart Life
2. Reset el GF-SMBOX-PLUS (botón factory reset ~10s)
3. Vuelve a vincularlo a la misma cuenta (agustin.deoz@gmail.com)
4. Intenta nuevamente obtener Local Key vía API

**Riesgo:** Perder configuración actual  
**Beneficio:** Garantiza que está en la API

### Opción 2: Fuerza bruta del Local Key
**Proceso:**
- El Local Key de Tuya tiene un formato conocido
- Podemos intentar valores comunes o patrones
- Menos ideal pero posible

**Riesgo:** Podría no funcionar  
**Beneficio:** No requiere readicionar

### Opción 3: Extraer Local Key del teléfono (ADB)
**Proceso:**
1. Habilitar USB Debugging en Android
2. Extraer archivos de Smart Life  
3. Parsear Local Key del JSON

**Riesgo:** Requiere acceso root en algunos teléfonos  
**Beneficio:** Funciona sin readicionar

### Opción 4: Usar bridge alternativo
**Proceso:**
- Hay librerías que pueden hacer sniffing del protocolo Tuya
- Capturan comandos Smart Life → dispositivo
- Extraen Local Key automáticamente

**Riesgo:** Complejo  
**Beneficio:** Automático

---

## Recomendación

**Opción 1 (Readicionar)** es la más simple y confiable.

**Pasos:**
```bash
# 1. En Smart Life:
#    - Eliminar dispositivo
#    - Resetear GF-SMBOX (botón durante 10s)
#    - Añadir nuevamente
#    - Esperar "Conectado"

# 2. En laptop:
cd /home/agustin/proyectos_software/datamaq-telemetry
source venv/bin/activate
TUYA_EMAIL="agustin.deoz@gmail.com" \
TUYA_PASSWORD="Temporal_12345" \
python scripts/extract_tuya_credentials.py
```

¿Procedemos con Option 1?
