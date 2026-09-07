# 🛡️ Informe de Delegación a Infraestructura & DevOps: Ciberdefensa Perimetral (Fase 3)

> **De:** Equipo de Backend (`datamaq-telemetry`)  
> **Para:** Equipo de Infraestructura / DevOps / Sysadmin  
> **Fecha:** 2026-09-07  
> **Prioridad:** Alta  
> **Servicio afectado:** `api.datamaq.com.ar` / `app.datamaq.com.ar` (Reverse Proxy Nginx & Fail2ban)  
> **Estado Backend:** Fases 1 y 2 completadas y desplegadas en producción (`3faa17f`).

---

## 1. Contexto y Objetivos

En el backend (`datamaq-telemetry`) se implementaron y desplegaron las defensas a nivel de capa de aplicación (Fases 1 y 2):
- **Rate limiting dual en recuperación de contraseña:** Máximo 3 solicitudes por email y 10 por IP en 15 minutos (mitiga *Email Flooding* y saturación de la cuota SMTP).
- **Mitigación de Password Spraying en login:** Bloqueo tras 20 intentos fallidos acumulados por IP en 15 minutos.
- **Revocación de tokens JWT:** Inmediata al restablecer contraseña mediante verificación temporal de `iat`.
- **Cabeceras defensivas OWASP:** `Permissions-Policy`, `COOP`, `CORP`, HSTS y `CSP` estricto en cada respuesta HTTP.

### Justificación de la Fase 3 (Perímetro / Infraestructura)
Actualmente, el backend rechaza los excesos devolviendo `HTTP 429 Too Many Requests`. Sin embargo, para evaluar el rate limit a nivel de aplicación, la petición HTTP viaja a través de HAProxy -> Nginx -> Uvicorn/Python -> Base de Datos, consumiendo recursos de cómputo y sockets del servidor.

**Objetivo de DevOps:** Frenar ataques de fuerza bruta, DoS y scraping en el **perímetro (Nginx y Firewall del SO)** antes de que alcancen el runtime de Python.

---

## 2. Requerimientos Técnicos para DevOps

### Requerimiento 1: Rate Limiting en Nginx (`limit_req_zone`)

Configurar zonas de memoria compartida en Nginx para limitar la tasa de peticiones en los endpoints sensibles de autenticación.

#### A. Definición de zonas en Nginx (HTTP block o archivo de configuración global)
En `/etc/nginx/nginx.conf` (dentro del bloque `http {}`) o en un archivo común incluido (ej: `/etc/nginx/conf.d/rate-limiting.conf`):

```nginx
# /etc/nginx/conf.d/rate-limiting.conf

# Zona para Login: máx 10 peticiones por minuto por IP
limit_req_zone $binary_remote_addr zone=auth_login_zone:10m rate=10r/m;

# Zona para Recuperación de Contraseña: máx 3 peticiones por minuto por IP
limit_req_zone $binary_remote_addr zone=auth_recovery_zone:10m rate=3r/m;

# Código de estado a devolver cuando se supere el límite (RFC 6585)
limit_req_status 429;
```

#### B. Aplicación en los virtual hosts (`api.datamaq.com.ar` y `app.datamaq.com.ar`)

En `/etc/nginx/conf.d/api.datamaq.com.ar.conf` (dentro del `server` SSL en puerto 9443):

```nginx
    # Rate Limiting específico para Login
    location = /api/v1/auth/login {
        limit_req zone=auth_login_zone burst=5 nodelay;

        proxy_pass http://127.0.0.1:8885;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port 443;
    }

    # Rate Limiting específico para Recuperación de Contraseña
    location = /api/v1/auth/recuperar-contrasena {
        limit_req zone=auth_recovery_zone burst=2 nodelay;

        proxy_pass http://127.0.0.1:8885;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port 443;
    }
```

*Nota para `app.datamaq.com.ar.conf`: Replicar estas directivas si el frontend expone directamente los paths bajo `/api/v1/auth/...`.*

---

### Requerimiento 2: Bloqueo Automatizado a Nivel Firewall con Fail2ban

Fail2ban ya está instalado y activo en el VPS con la cárcel de `sshd`. Se requiere añadir una cárcel para banear en `iptables`/`nftables` a los clientes que generen respuestas `429` reiteradas.

#### A. Crear Filtro Fail2ban para Nginx 429
Archivo `/etc/fail2ban/filter.d/nginx-429.conf`:

```ini
[Definition]
# Captura cualquier petición que resulte en código HTTP 429 en los access logs de Nginx
failregex = ^<HOST> -.*"(GET|POST|PUT|DELETE|PATCH).*" 429 .*$
ignoreregex =
```

#### B. Crear Cárcel (Jail) para Nginx 429
Archivo `/etc/fail2ban/jail.d/nginx-429.local`:

```ini
[nginx-429]
enabled  = true
port     = http,https,2082,2083,2087,9443
filter   = nginx-429
logpath  = /var/log/nginx/*access*.log
maxretry = 5
findtime = 600
bantime  = 3600
action   = iptables-multiport[name=nginx-429, port="http,https,9443"]
```

*Parámetros sugeridos:*
- `findtime = 600` (ventana de 10 minutos).
- `maxretry = 5` (si una misma IP recibe 5 respuestas 429 en 10 minutos).
- `bantime = 3600` (bloqueo en firewall por 1 hora; puede configurarse `bantime.increment = true` para reincidentes).

---

### Requerimiento 3: Verificación y Validación

Una vez aplicadas las configuraciones, ejecutar:

```bash
# 1. Verificar sintaxis y recargar Nginx
nginx -t && systemctl reload nginx

# 2. Recargar y verificar estado de Fail2ban
fail2ban-client reload
fail2ban-client status nginx-429

# 3. Test de stress controlado desde host externo (ej: 15 solicitudes seguidas)
for i in {1..15}; do curl -s -o /dev/null -w "%{http_code}\n" -X POST https://api.datamaq.com.ar/api/v1/auth/login -H "Content-Type: application/json" -d '{"usuario":"test@datamaq.com.ar","password":"x"}'; done
# Deberá comenzar a responder con HTTP 429 a partir de la 6ta solicitud.
```

---

## 3. Matriz de Responsabilidades

| Capa de Defensa | Componente | Responsable | Estado |
| :--- | :--- | :--- | :--- |
| **L7 - Lógica de Negocio** | Rate limit por email / usuario, revocar JWT, sanitización de payloads | **Backend** (`datamaq-telemetry`) | ✅ Desplegado en producción |
| **L7 - HTTP Headers** | Strict CSP, HSTS, Permissions-Policy, COOP, CORP | **Backend** (`datamaq-telemetry`) | ✅ Desplegado en producción |
| **L7 - Web Server Perimetral** | `limit_req_zone` (Nginx), retención de conexiones abusivas | **DevOps / Infraestructura** | ⏳ **Pendiente (Este informe)** |
| **L3/L4 - Red y Firewall** | Baneo de IPs abusivas (Fail2ban + iptables/nftables) | **DevOps / Infraestructura** | ⏳ **Pendiente (Este informe)** |

Quedamos a disposición por cualquier duda técnica sobre los paths o el comportamiento esperado de la API.
