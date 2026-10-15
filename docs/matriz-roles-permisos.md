<!-- Generado por scripts/generate_matriz_roles.py. No editar a mano: regenerar. -->
# Matriz de roles y permisos (generada desde el código)

Endpoints analizados: **121**. Roles válidos (`ROLES_VALIDOS`): `admin`, `auditor`, `ingeniero`, `invitado`, `invitado_global`, `mantenimiento`, `operador`, `superadmin`.

Cómo se lee: "Roles que pasan" es lo que deja el guard de rol que la ruta declara (evaluado con la condición real del guard). Si la columna "Chequeo manual" dice `sí`, el cuerpo de la ruta o de una dependencia propia compara el rol o usa `ROLES_ACCESO_GLOBAL`: ese recorte no está en la columna y hay que leer la ruta para saberlo.

Con `AUTH_REQUIRED` apagado, `get_usuario_actual` devuelve `{"sub": "anon", "rol": "admin"}`: todos los guards dejan pasar y la matriz no aplica. Es un comportamiento de desarrollo.

## Resumen por guard

| Guard | Roles que pasan |
|---|---|
| `no_permitido_para_invitados_2fa` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` |
| `requiere_rol_admin` | `admin`, `superadmin` |
| `requiere_rol_auditor_o_superadmin` | `auditor`, `superadmin` |
| `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` |
| `requiere_rol_superadmin` | `superadmin` |

## Endpoints

| Método | Ruta | Guards | Roles que pasan | Autenticación | Chequeo manual | Código |
|---|---|---|---|---|---|---|
| GET | `/.well-known/oauth-authorization-server` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/oauth_router.py:43` |
| GET | `/.well-known/oauth-protected-resource` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/oauth_router.py:69` |
| GET | `/.well-known/oauth-protected-resource/mcp` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/oauth_router.py:69` |
| GET | `/.well-known/oauth-protected-resource/{resource_path:path}` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/oauth_router.py:69` |
| GET | `/api/v1/admin/auditoria/cambios-ti` | `requiere_rol_admin` | `admin`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/admin_router.py:52` |
| GET | `/api/v1/admin/auditoria/cambios-ti/{cambio_id}` | `requiere_rol_admin` | `admin`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/admin_router.py:88` |
| GET | `/api/v1/alertas` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/alertas_router.py:26` |
| PATCH | `/api/v1/alertas/{alerta_id}/resolver` | `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/alertas_router.py:65` |
| POST | `/api/v1/alertas/{alerta_id}/resolver` | `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/alertas_router.py:65` |
| GET | `/api/v1/analitica/banco-capacitores/planta` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/analitica_router.py:32` |
| GET | `/api/v1/analitica/penalizaciones/planta` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/analitica_router.py:58` |
| POST | `/api/v1/asistente/preguntar` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/asistente_router.py:30` |
| GET | `/api/v1/audit/logs` | `requiere_rol_auditor_o_superadmin` | `auditor`, `superadmin` | — | no | `src/infrastructure/fastapi/routes/audit_router.py:27` |
| POST | `/api/v1/auth/2fa/activar` | `no_permitido_para_invitados_2fa` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/auth_router.py:370` |
| POST | `/api/v1/auth/2fa/desactivar` | `no_permitido_para_invitados_2fa` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/auth_router.py:412` |
| POST | `/api/v1/auth/2fa/setup` | `no_permitido_para_invitados_2fa` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/auth_router.py:354` |
| POST | `/api/v1/auth/2fa/verificar` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/auth_router.py:288` |
| PATCH | `/api/v1/auth/confirm-password-change` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/auth_router.py:519` |
| POST | `/api/v1/auth/dispositivos/revocar-todos` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/auth_router.py:484` |
| POST | `/api/v1/auth/guest` | — | todos (sin guard) | sin dependencia de auth detectada | sí | `src/infrastructure/fastapi/routes/auth_router.py:169` |
| POST | `/api/v1/auth/login` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/auth_router.py:98` |
| POST | `/api/v1/auth/logout` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/auth_router.py:191` |
| POST | `/api/v1/auth/logout-todas` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/auth_router.py:228` |
| GET | `/api/v1/auth/me` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/auth_router.py:277` |
| POST | `/api/v1/auth/recuperar-contrasena` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/auth_router.py:450` |
| PATCH | `/api/v1/auth/request-password-change-code` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/auth_router.py:499` |
| POST | `/api/v1/auth/restablecer-contrasena` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/auth_router.py:470` |
| GET | `/api/v1/cargas` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/cargas_router.py:48` |
| POST | `/api/v1/cargas` | `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/cargas_router.py:192` |
| POST | `/api/v1/cargas/analisis` | `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/cargas_router.py:95` |
| GET | `/api/v1/cargas/atribucion` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/cargas_router.py:78` |
| POST | `/api/v1/cargas/campanas/activas` | `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/cargas_router.py:232` |
| POST | `/api/v1/cargas/campanas/pasivas` | `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/cargas_router.py:253` |
| GET | `/api/v1/cargas/campanas/{campana_id}` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/cargas_router.py:267` |
| PATCH | `/api/v1/cargas/campanas/{campana_id}/descartar` | `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/cargas_router.py:299` |
| PATCH | `/api/v1/cargas/campanas/{campana_id}/finalizar` | `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/cargas_router.py:282` |
| GET | `/api/v1/cargas/exportar/csv` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/cargas_router.py:334` |
| GET | `/api/v1/cargas/intervalos` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/cargas_router.py:157` |
| PATCH | `/api/v1/cargas/intervalos/{intervalo_id}/corregir` | `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/cargas_router.py:112` |
| GET | `/api/v1/cargas/perfil` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/cargas_router.py:60` |
| GET | `/api/v1/cargas/presets` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/cargas_router.py:130` |
| POST | `/api/v1/cargas/presets/inicializar` | `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/cargas_router.py:144` |
| GET | `/api/v1/cargas/{carga_id}` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/cargas_router.py:181` |
| PATCH | `/api/v1/cargas/{carga_id}` | `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/cargas_router.py:203` |
| GET | `/api/v1/cargas/{carga_id}/campanas` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/cargas_router.py:311` |
| PUT | `/api/v1/cargas/{carga_id}/firma` | `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/cargas_router.py:215` |
| GET | `/api/v1/cargas/{carga_id}/intervalos` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/cargas_router.py:322` |
| PATCH | `/api/v1/disponibilidad/eventos/{evento_id}/corregir` | `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:172` |
| POST | `/api/v1/disponibilidad/eventos/{evento_id}/corregir` | `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:172` |
| GET | `/api/v1/disponibilidad/maquinas` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:54` |
| POST | `/api/v1/disponibilidad/maquinas` | `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:82` |
| GET | `/api/v1/disponibilidad/maquinas/{maquina_id}` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:71` |
| PATCH | `/api/v1/disponibilidad/maquinas/{maquina_id}` | `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:101` |
| GET | `/api/v1/disponibilidad/maquinas/{maquina_id}/eventos` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:133` |
| GET | `/api/v1/disponibilidad/maquinas/{maquina_id}/exportar/csv` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:224` |
| GET | `/api/v1/disponibilidad/maquinas/{maquina_id}/histograma` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:117` |
| GET | `/api/v1/disponibilidad/maquinas/{maquina_id}/metricas-oee` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:149` |
| GET | `/api/v1/disponibilidad/paradas-programadas` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:190` |
| POST | `/api/v1/disponibilidad/paradas-programadas` | `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:205` |
| GET | `/api/v1/dispositivos` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/dispositivos_router.py:36` |
| POST | `/api/v1/dispositivos` | `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/dispositivos_router.py:68` |
| GET | `/api/v1/dispositivos/{device_id}` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/dispositivos_router.py:57` |
| PATCH | `/api/v1/dispositivos/{device_id}` | `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/dispositivos_router.py:153` |
| PUT | `/api/v1/dispositivos/{device_id}` | `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/dispositivos_router.py:153` |
| POST | `/api/v1/dispositivos/{device_id}/realtime` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/dispositivos_router.py:177` |
| GET | `/api/v1/dispositivos/{dispositivo_id}/maquinas/inferidas` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/maquinas_router.py:26` |
| GET | `/api/v1/nodo/unifilar/{nodo_id}` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/planta_estructura_router.py:125` |
| POST | `/api/v1/oauth/authorize` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/oauth_router.py:210` |
| POST | `/api/v1/oauth/consent` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/oauth_router.py:174` |
| GET | `/api/v1/oauth/consent-info` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/oauth_router.py:131` |
| POST | `/api/v1/oauth/register` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/oauth_router.py:95` |
| POST | `/api/v1/oauth/revoke` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/oauth_router.py:264` |
| POST | `/api/v1/oauth/token` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/oauth_router.py:232` |
| GET | `/api/v1/organizaciones` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/organizaciones_router.py:25` |
| GET | `/api/v1/planes` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/planes_router.py:24` |
| POST | `/api/v1/planes` | `requiere_rol_escritura` | `admin`, `auditor`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/planes_router.py:32` |
| GET | `/api/v1/planta/areas` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/planta_estructura_router.py:225` |
| GET | `/api/v1/planta/layout` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/planta_estructura_router.py:195` |
| GET | `/api/v1/planta/unifilar` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/planta_estructura_router.py:54` |
| GET | `/api/v1/plantas` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/organizaciones_router.py:40` |
| GET | `/api/v1/plantas/{planta_id}/areas` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/planta_estructura_router.py:242` |
| GET | `/api/v1/plantas/{planta_id}/layout` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/planta_estructura_router.py:210` |
| GET | `/api/v1/plantas/{planta_id}/unifilar` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/planta_estructura_router.py:69` |
| GET | `/api/v1/plantas/{planta_id}/unifilar/nodos/{nodo_id}` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/planta_estructura_router.py:91` |
| GET | `/api/v1/plantas/{planta_id}/unifilar/nodos/{nodo_id}/resumen` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/planta_estructura_router.py:91` |
| GET | `/api/v1/plantas/{planta_id}/unifilar/nodos/{nodo_id}/resumen/historico` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/planta_estructura_router.py:160` |
| POST | `/api/v1/produccion/enpi/calcular-sec` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/produccion_router.py:84` |
| POST | `/api/v1/produccion/lecturas` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/produccion_router.py:56` |
| POST | `/api/v1/sge/competencias/acuse` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/sge_router.py:215` |
| GET | `/api/v1/sge/competencias/mis-capacitaciones` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/sge_router.py:245` |
| GET | `/api/v1/sge/documentacion` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/sge_router.py:188` |
| GET | `/api/v1/sge/plantas/{planta_id}/ahorros-cusum` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/sge_router.py:301` |
| GET | `/api/v1/sge/plantas/{planta_id}/balance-energia` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/sge_router.py:269` |
| GET | `/api/v1/sge/plantas/{planta_id}/costo-estimado` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/sge_router.py:395` |
| GET | `/api/v1/sge/plantas/{planta_id}/facturas-distribuidora` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/sge_router.py:372` |
| GET | `/api/v1/sge/plantas/{planta_id}/linea-base` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/sge_router.py:333` |
| POST | `/api/v1/suscripciones/checkout` | `requiere_rol_admin` | `admin`, `superadmin` | — | no | `src/infrastructure/fastapi/routes/billing_router.py:39` |
| POST | `/api/v1/system/purge` | `requiere_rol_admin` | `admin`, `superadmin` | — | no | `src/infrastructure/fastapi/routes/system_router.py:109` |
| GET | `/api/v1/system/ws-status` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/system_router.py:98` |
| GET | `/api/v1/telemetria/alerts/{device_id}` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/telemetria_router.py:150` |
| GET | `/api/v1/telemetria/energy/{device_id}` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/telemetria_router.py:122` |
| GET | `/api/v1/telemetria/exportar/csv` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/telemetria_router.py:173` |
| GET | `/api/v1/telemetria/fases-diagnostico/{device_id}` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/telemetria_router.py:64` |
| GET | `/api/v1/telemetria/instantaneous/{device_id}` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/telemetria_router.py:80` |
| GET | `/api/v1/telemetria/latest/{device_id}` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/telemetria_router.py:49` |
| GET | `/api/v1/tuya/notificador/estado` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/notificador_router.py:27` |
| POST | `/api/v1/usuarios` | `requiere_rol_admin` | `admin`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/usuarios_router.py:58` |
| GET | `/api/v1/usuarios/integraciones` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/oauth_router.py:290` |
| DELETE | `/api/v1/usuarios/integraciones/{client_id}` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/oauth_router.py:300` |
| DELETE | `/api/v1/usuarios/{usuario_id}` | `requiere_rol_admin` | `admin`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/usuarios_router.py:121` |
| GET | `/api/v1/usuarios/{usuario_id}/plantas` | `requiere_rol_admin` | `admin`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/usuarios_router.py:214` |
| PUT | `/api/v1/usuarios/{usuario_id}/plantas` | `requiere_rol_admin` | `admin`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/usuarios_router.py:232` |
| PATCH | `/api/v1/usuarios/{usuario_id}/rol` | `requiere_rol_admin` | `admin`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/usuarios_router.py:158` |
| POST | `/api/v1/webhooks/mercadopago` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/billing_router.py:60` |
| GET | `/favicon.ico` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/system_router.py:48` |
| GET | `/health` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/system_router.py:92` |
| GET | `/health/live` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/system_router.py:53` |
| GET | `/health/ready` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/system_router.py:62` |
| POST | `/oauth/register` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/oauth_router.py:95` |
| POST | `/oauth/revoke` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/oauth_router.py:264` |
| POST | `/oauth/token` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/oauth_router.py:232` |
