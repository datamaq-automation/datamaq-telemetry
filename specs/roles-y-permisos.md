# Spec: Documentar roles y permisos de la plataforma

> **Estado:** implementado en `datamaq-telemetry` (documentación, sin cambio de comportamiento) · **Fecha:** 2026-10-15
> **Issue:** datamaq-automation/datamaq#38 · **Rama:** `docs/issue-38-matriz-roles-permisos`
> **Decisiones aplicables:** `decisions/2026-10-15_roles-y-permisos-antes-de-enb.md`, `decisions/2026-09-19_adecuacion-sge-iso50001-limpieza-redundancias.md` (punto 6)
> **Reemplaza:** `specs/roles-permisos.md` (desactualizado, ver banner en ese archivo)

## 1. Objetivo y Contexto

**Objetivo:** dejar un único documento de roles y permisos que describa **lo que el código hace hoy**, con la matriz rol × endpoint generada leyendo las rutas.

**Alcance:**
- Matriz de los ocho roles contra cada endpoint de `src/infrastructure/fastapi/routes/`: guard, chequeo manual y roles que pasan.
- Alcance por organización y por planta.
- Inconsistencias encontradas, **sin corregirlas**.

**Fuera de alcance:** cambiar permisos, agregar un rol "cliente", crear endpoints de carga de EnB.

## 2. Dominio & Puertos

**Sin cambio de comportamiento.** No se toca `src/`. Se agrega `scripts/generate_matriz_roles.py`, que solo lee código con `ast` y no importa la aplicación.

Fuentes que lee el generador:
- `ROLES_VALIDOS` en `src/application/use_cases/autenticar_usuario.py` (los ocho roles).
- Guards en `src/infrastructure/fastapi/dependencies.py`: el rol que pasa se calcula evaluando la condición `if ... raise` de cada guard para cada rol.
- Alias `Annotated[..., Depends(...)]` (p. ej. `PlantaPermitida`) y `dependencies=[...]` a nivel router y a nivel decorador.
- Dependencias propias en `src/infrastructure/fastapi/*.py`, que se siguen un nivel por ruta para detectar chequeos manuales.

## 3. Casos de Uso & DTOs

**Sin cambio de comportamiento.** No hay casos de uso nuevos.

## 4. Matriz de Pruebas

`tests/unit/test_matriz_roles.py` (4 tests):
- `test_matriz_roles_file_is_in_sync`: falla si `docs/matriz-roles-permisos.md` no coincide con lo que genera el script (mismo patrón que `docs/database_erd.md`).
- `test_roles_validos_salen_de_la_fuente_de_autenticacion`: los ocho roles.
- `test_guards_dejan_pasar_exactamente_los_roles_que_su_codigo_dice`: los cinco guards.
- `test_cada_endpoint_tiene_su_guard_o_una_razon_para_no_tenerlo`: todo endpoint declara guard o autenticación.

## 5. Commits

1. `chore(scripts): generador de matriz de roles desde las rutas` — script, test y `docs/matriz-roles-permisos.md`.
2. `docs(roles): spec de roles y permisos e inconsistencias` — esta spec y el banner en `specs/roles-permisos.md`.

## 6. Criterios del Gauntlet

- `APP_ENV=test ./scripts/pre-push.sh` en verde.
- `scripts/generate_matriz_roles.py --check` pasa (la matriz está sincronizada).
- Sin cambios en `src/`: el diff no toca código de producto.

## Matriz generada

Ver `docs/matriz-roles-permisos.md`. Es el resultado del análisis estático de los decoradores `@router.<verbo>` de `routes/` (121 en total); la tabla tiene una fila por endpoint.

**Cómo leer "Roles que pasan":** es lo que deja el guard declarado. Un endpoint marcado **chequeo manual: sí** compara el rol en su cuerpo o en una dependencia propia; ese recorte no aparece en la columna y hay que leer la ruta.

**Limitación:** los chequeos dentro de funciones auxiliares llamadas desde el cuerpo (p. ej. `_resolver_org_id(claims)` en `planta_estructura_router.py`) no se detectan. Un "chequeo manual: no" no prueba que no haya control de alcance.

## Alcance por organización y por planta

- **Acceso global:** `superadmin` e `invitado_global` (`ROLES_ACCESO_GLOBAL`, `src/domain/auth/services.py:71`). Esa lista se escribe a mano también en `device_ownership.py` (cuatro funciones), `alertas_router.py:39` y `server.py:407`.
- **Organización:** `usuarios_router.py` limita a la organización del claim `org` (`_verificar_misma_organizacion`). `organizaciones_router.py` y `alertas_router.py` filtran por organización.
- **Planta:** `resolver_planta_permitida` (`planta_ownership.py`) y `PoliticaAccesoPlantasService` (`domain/auth/services.py`). Resuelven las plantas asignadas por `GestionarAccesoPlantasUseCase`.
- **Dispositivos, máquinas, alertas y eventos:** `device_ownership.py` (`verificar_propiedad_*`). Todas omiten el chequeo si `AUTH_REQUIRED` está apagado o el rol es global.

## Inconsistencias encontradas (sin corregir)

Verificadas por lectura de código; **ninguna probada en runtime** salvo que se indique.

| # | Severidad | Hallazgo | Evidencia |
|---|---|---|---|
| I1 | Alta | Un `admin` puede crear o cambiar un usuario de su organización a cualquier rol, incluido `superadmin`. El guard admite `admin` y ningún chequeo valida el rol destino. | `usuarios_router.py:56-80` (`crear_usuario`, `dto.rol` directo), `usuarios_router.py:158-171` (`usuario.rol = dto.rol`), `dependencies.py:496-499` |
| I2 | Alta | `GET /api/v1/cargas` (y `/{carga_id}`, `/intervalos`, `/perfil`, `/presets`, etc.) no recibe `claims` y el caso de uso lista sin filtrar por organización. Cualquier rol autenticado, incluido `invitado`, lee cargas de todas las organizaciones. | `cargas_router.py` (0 referencias a `claims`), `gestionar_cargas.py:41-48` (`repo_cargas.listar()`) |
| I3 | Media | Los roles no se validan en la entrada: `CambiarRolUsuarioDTO.rol` y `CrearUsuarioRequestDTO.rol` aceptan cualquier texto de 2 a 50 caracteres. `ROLES_VALIDOS` solo se usa en `autenticar_usuario.py:159` (`me()`), así que un rol inválido se guarda y después `/auth/me` falla. | `usuarios_router.py:30,35`, `autenticar_usuario.py:159` |
| I4 | Media | El rol `auditor` pasa `requiere_rol_escritura`: puede escribir en los endpoints con ese guard (ver matriz) (p. ej. `POST /api/v1/cargas`). No está claro si es intención. | `dependencies.py:502-505`; matriz |
| I5 | Baja | Los roles `mantenimiento` e `ingeniero` pasan los guards de escritura sin tener un guard propio. Su significado de negocio no está definido. | matriz; decisión 2026-10-15 |
| I6 | Baja | La lista `(superadmin, invitado_global)` está repetida a mano en vez de usar `ROLES_ACCESO_GLOBAL`. Si cambia una, las otras pueden quedar desfasadas. | `device_ownership.py:58,90,116,140`, `alertas_router.py:39`, `server.py:407` |
| I7 | Baja | `sge_router.py:201` usa `"operador"` como rol por defecto si no hay claim `rol`. Con un token válido el rol siempre está, así que es un valor por defecto defensivo. | `sge_router.py:201` |
| I8 | Revisar | Rutas sin dependencia de auth: además de las esperables (`/health*`, `/favicon.ico`, `/.well-known/*`, `/api/v1/auth/*` de login y recuperación, y `/oauth/token`, `/oauth/revoke`, `/oauth/register`, que autentican al cliente OAuth y no por rol), quedan `GET /api/v1/system/ws-status` y `POST /api/v1/webhooks/mercadopago`. Este último necesita verificar que valide la firma del proveedor; **no verificado**. | matriz, columna Autenticación |
| I9 | Revisar | Con `AUTH_REQUIRED` apagado todo request es `admin` (`dependencies.py:451-452`) y `resolver_planta_permitida` resuelve como `superadmin` (`planta_ownership.py:30`). Es de desarrollo; falta confirmar que producción tenga `AUTH_REQUIRED=True`. **No verificado en esta sesión.** | `dependencies.py:451-452`, `planta_ownership.py:30` |

**Pendiente de verificación:** la lectura de `documentacion_sge` (`roles_permitidos` en `adapters/gateways/in_memory_documentacion_sge_repository.py`) y de los endpoints de EnB (`GET /api/v1/sge/plantas/{id}/linea-base`) no se hizo en esta pasada.

## Preguntas para el dueño (no las responde el código)

1. ¿Qué significa cada rol en el negocio? En particular, ¿qué rol tiene el usuario de un cliente (`operador`, `admin` de su organización u otro)?
2. ¿`auditor` debe poder escribir (I4)? ¿`mantenimiento` e `ingeniero` deben tener escritura?
3. ¿Un `admin` de organización debe poder asignar `superadmin` (I1)? Lo esperable sería que no.

Estas preguntas bloquean la aprobación del documento, no la matriz (decisión 2026-10-15).
