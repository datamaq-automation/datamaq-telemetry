# Informe de Cambios de Contrato — Autenticación, 2FA y Recuperación de Contraseña (`/api/v1/auth`)

> **Para:** Equipo de Frontend (`app-datamaq` / `www-datamaq`)  
> **De:** Equipo de Backend (`datamaq-telemetry`)  
> **Fecha:** 2026-09-06  
> **Tipo de cambio:** **Evolutivo**. Contiene cambios de contrato en login (usernames estrictos en formato email y reto condicional 2FA), más la adición de nuevos endpoints de 2FA y Recuperación de Contraseña vía correo.

---

## 1. Resumen Ejecutivo de Impacto

1. **Nombre de usuario (`username`) es ahora obligatoriamente un correo electrónico:**
   - Todo username debe cumplir formato `usuario@dominio.ext`.
   - Se migraron los usuarios predeterminados en producción: `admin` $\rightarrow$ `admin@datamaq.com.ar`, `invitado` $\rightarrow$ `invitado@datamaq.com.ar`.
   - En el formulario de login, el input debe ser `type="email"` con validación de formato.

2. **Login adaptativo para Autenticación de Dos Factores (2FA / TOTP):**
   - Si el usuario tiene 2FA configurado, `POST /api/v1/auth/token` ya no devuelve el token definitivo inmediatamente; devuelve un objeto `{ "requiere_2fa": true, "pre_auth_token": "..." }`.
   - El frontend debe presentar la pantalla de ingreso del código de 6 dígitos (o código de respaldo de 8 caracteres) y enviar a `POST /api/v1/auth/2fa/login`.

3. **Nuevo flujo de Recuperación de Contraseña por Correo Electrónico:**
   - Solicitud de recuperación mediante `POST /api/v1/auth/recuperar-contrasena` con `{"usuario": "correo@datamaq.com.ar"}`.
   - El usuario recibe un correo con enlace a:
     ```text
     https://www.datamaq.com.ar/restablecer-contrasena?token=<JWT>
     ```
     *(Válido por 15 minutos, de un solo uso).*
   - El frontend debe proveer la vista `/restablecer-contrasena` para capturar `token` y enviar la nueva clave a `POST /api/v1/auth/restablecer-contrasena`.

---

## 2. Cambios en el Flujo de Inicio de Sesión (Login)

### 2.1. Solicitud de Token (`POST /api/v1/auth/token`)

- **Content-Type:** `application/x-www-form-urlencoded`
- **Body:**
  - `username`: Correo electrónico (ej. `admin@datamaq.com.ar`). **Requerido**.
  - `password`: Contraseña en texto plano. **Requerido**.

#### Caso A: Usuario SIN 2FA activado (o usuario `invitado`)
Comportamiento estándar habitual (sin cambios):
- **Status:** `200 OK`
- **Set-Cookie:** `datamaq_token=...; HttpOnly; SameSite=Lax; Path=/`
- **Body:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6...",
  "token_type": "bearer",
  "rol": "operador",
  "username": "operador@datamaq.com.ar"
}
```

#### Caso B: Usuario CON 2FA activado
El backend NO genera la sesión final todavía; devuelve un token previo efímero (validez de 5 minutos):
- **Status:** `200 OK`
- **Body:**
```json
{
  "requiere_2fa": true,
  "pre_auth_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```
*(Nota: En este caso no se envía el header `Set-Cookie` de autenticación).*

---

### 2.2. Verificación de 2FA en Login (`POST /api/v1/auth/2fa/login`)

Cuando `requiere_2fa === true`, el frontend debe redirigir o mostrar un modal para ingresar el código TOTP o código de respaldo.

- **Método:** `POST`
- **Ruta:** `/api/v1/auth/2fa/login`
- **Content-Type:** `application/json`
- **Body:**
```json
{
  "pre_auth_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6...",
  "codigo": "123456"
}
```
> **Nota sobre el campo `codigo`:** Acepta tanto un código TOTP de 6 dígitos numéricos (Google Authenticator, Bitwarden, Authy, etc.) como un código de respaldo alfanumérico de 8 caracteres (ej. `A1B2C3D4`).

- **Respuestas:**
  - **`200 OK`**: Código verificado exitosamente. Emite la sesión definitiva:
    - **Set-Cookie:** `datamaq_token=...; HttpOnly; SameSite=Lax; Path=/`
    - **Body:**
      ```json
      {
        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6...",
        "token_type": "bearer",
        "rol": "admin",
        "username": "admin@datamaq.com.ar"
      }
      ```
  - **`401 Unauthorized`**: Código incorrecto o token expirado:
    ```json
    {
      "detail": "Código 2FA o código de respaldo inválido"
    }
    ```

---

## 3. Endpoints de Gestión de 2FA (Perfil de Usuario)

Todos estos endpoints requieren autenticación activa (`datamaq_token` en cookie o Bearer header).

| Método | Ruta | Descripción | Payload | Respuesta Exitosa |
|---|---|---|---|---|
| `GET` | `/api/v1/auth/2fa/estado` | Consulta estado de 2FA del usuario | *Ninguno* | `200 OK`<br>`{ "totp_habilitado": boolean, "codigos_restantes": number }` |
| `POST` | `/api/v1/auth/2fa/activar-inicio` | Inicia el enrolamiento de 2FA | *Ninguno* | `200 OK`<br>`{ "secreto": "...", "uri_otpauth": "otpauth://...", "qr_svg": "<svg>...</svg>" }` |
| `POST` | `/api/v1/auth/2fa/activar-confirmar` | Confirma el enrolamiento con el primer código | `{ "codigo": "123456" }` | `200 OK`<br>`{ "exito": true, "mensaje": "...", "codigos_respaldo": ["...", ...] }` |
| `POST` | `/api/v1/auth/2fa/desactivar` | Desactiva 2FA | `{ "contrasena": "...", "codigo": "123456" }` | `200 OK`<br>`{ "exito": true, "mensaje": "2FA desactivado exitosamente." }` |
| `POST` | `/api/v1/auth/2fa/regenerar-codigos` | Regenera los 10 códigos de respaldo | `{ "contrasena": "..." }` | `200 OK`<br>`{ "exito": true, "codigos_respaldo": [...] }` |

> **Recomendación UI:** El string SVG retornado en `qr_svg` puede inyectarse directamente en el DOM mediante `dangerouslySetInnerHTML` o convirtiéndose a un Data URI (`data:image/svg+xml;utf8,...`). Los códigos de respaldo deben mostrarse al usuario con opción de "Copiar al portapapeles" o "Descargar como TXT".

---

## 4. Flujo de Recuperación de Contraseña por Correo Electrónico

### 4.1. Solicitud de Recuperación (`POST /api/v1/auth/recuperar-contrasena`)

- **Ubicación UI sugerida:** Enlace "¿Olvidaste tu contraseña?" debajo del botón de login.
- **Método:** `POST`
- **Ruta:** `/api/v1/auth/recuperar-contrasena`
- **Content-Type:** `application/json`
- **Body:**
```json
{
  "usuario": "agustin@datamaq.com.ar"
}
```
- **Respuesta:**
  - **`200 OK`**: Responde siempre con el mismo mensaje genérico (independientemente de si el correo existe o no, para prevenir ataques de enumeración):
```json
{
  "exito": true,
  "mensaje": "Si el usuario existe y está activo, se ha enviado un correo con instrucciones para restablecer la contraseña."
}
```

---

### 4.2. Vista de Restablecimiento en el Frontend (`/restablecer-contrasena`)

El usuario recibe un correo emitido por `no-reply@datamaq.com.ar` con un enlace al frontend:
```text
https://www.datamaq.com.ar/restablecer-contrasena?token=<TOKEN_JWT>
```

#### Especificación para el Frontend:
1. **Ruta:** Configurar la ruta `/restablecer-contrasena` en el router de la aplicación.
2. **Parámetro:** Extraer el token de la URL mediante query params:
   ```ts
   const searchParams = new URLSearchParams(window.location.search);
   const token = searchParams.get("token");
   ```
3. **Formulario:** Presentar campos:
   - "Nueva Contraseña" (mínimo 8 caracteres).
   - "Confirmar Nueva Contraseña".
4. **Envío al Backend:**
   - **Método:** `POST`
   - **Ruta:** `/api/v1/auth/restablecer-contrasena`
   - **Content-Type:** `application/json`
   - **Body:**
   ```json
   {
     "token": "<TOKEN_JWT>",
     "nueva_contrasena": "MiNuevaPasswordSegura2026!"
   }
   ```
5. **Respuestas:**
   - **`200 OK`**:
     ```json
     {
       "exito": true,
       "mensaje": "Contraseña restablecida exitosamente. Ya puede iniciar sesión con sus nuevas credenciales."
     }
     ```
     *(Redirigir automáticamente al login tras mostrar mensaje de éxito).*
   - **`400 Bad Request`**:
     - Token inválido o expirado:
       ```json
       {
         "detail": "El token de recuperación es inválido o ha expirado."
       }
       ```
     - Contraseña débil (< 8 caracteres):
       ```json
       {
         "detail": "La contraseña debe tener al menos 8 caracteres."
       }
       ```

> **Seguridad y Garantía de Un Solo Uso:** El token queda inmediatamente invalidado tras ser consumido (firmado criptográficamente contra el hash de la contraseña anterior). Si el usuario tenía 2FA activo, este **permanece activo** protegiendo su cuenta.

---

## 5. Resumen de Tipos TypeScript para el Frontend

```typescript
// --- Login ---
export interface LoginCredentials {
  username: string; // Obligatorio formato email
  password: string;
}

export type LoginResponse = 
  | { requiere_2fa: false | undefined; access_token: string; token_type: string; rol: string; username: string }
  | { requiere_2fa: true; pre_auth_token: string };

export interface TwoFactorLoginPayload {
  pre_auth_token: string;
  codigo: string; // 6 dígitos TOTP o 8 caracteres de respaldo
}

// --- Gestión 2FA ---
export interface TwoFactorStatusResponse {
  totp_habilitado: boolean;
  codigos_restantes: number;
}

export interface TwoFactorInitResponse {
  secreto: string;
  uri_otpauth: string;
  qr_svg: string;
}

export interface TwoFactorConfirmPayload {
  codigo: string;
}

export interface TwoFactorConfirmResponse {
  exito: boolean;
  mensaje: string;
  codigos_respaldo: string[];
}

export interface TwoFactorDisablePayload {
  contrasena: string;
  codigo: string;
}

// --- Recuperación de Contraseña ---
export interface PasswordRecoveryRequest {
  usuario: string; // Email
}

export interface PasswordResetPayload {
  token: string;
  nueva_contrasena: string;
}

export interface GenericMessageResponse {
  exito: boolean;
  mensaje: string;
}
```

---
*Cualquier consulta sobre la integración o pruebas en el entorno de staging/producción puede canalizarse con el equipo de backend.*
