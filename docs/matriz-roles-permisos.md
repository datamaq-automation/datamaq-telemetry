<!-- Generado por scripts/generate_matriz_roles.py. No editar a mano: regenerar. -->
# Matriz de roles y permisos (generada desde el código)

Endpoints analizados: **119**. Roles válidos (`ROLES_VALIDOS`): `admin`, `ingeniero`, `mantenimiento`, `operador`, `solo_lectura`, `superadmin`.

Cómo se lee: "Roles que pasan" es lo que deja el guard de rol que la ruta declara (evaluado con la condición real del guard). Si la columna "Chequeo manual" dice `sí`, el cuerpo de la ruta o de una dependencia propia compara el rol o usa `ROLES_ACCESO_GLOBAL`: ese recorte no está en la columna y hay que leer la ruta para saberlo.

Con `AUTH_REQUIRED` apagado, `get_usuario_actual` devuelve `{"sub": "anon", "rol": "admin"}`: todos los guards dejan pasar y la matriz no aplica. Es un comportamiento de desarrollo.

## Resumen por guard

| Guard | Roles que pasan |
|---|---|
| `no_permitido_para_invitados_2fa` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` |
| `requiere_rol_admin` | `admin`, `superadmin` |
| `requiere_rol_auditor_o_superadmin` | `superadmin` |
| `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` |
| `requiere_rol_superadmin` | `superadmin` |

## Endpoints

| Método | Ruta | Guards | Roles que pasan | Autenticación | Chequeo manual | Código |
|---|---|---|---|---|---|---|
| GET | `/.well-known/oauth-authorization-server` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/oauth_router.py:metadata_oauth_authorization_server` |
| GET | `/.well-known/oauth-protected-resource` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/oauth_router.py:metadata_oauth_protected_resource` |
| GET | `/.well-known/oauth-protected-resource/mcp` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/oauth_router.py:metadata_oauth_protected_resource` |
| GET | `/.well-known/oauth-protected-resource/{resource_path:path}` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/oauth_router.py:metadata_oauth_protected_resource` |
| GET | `/api/v1/admin/auditoria/cambios-ti` | `requiere_rol_admin` | `admin`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/admin_router.py:listar_cambios_ti` |
| GET | `/api/v1/admin/auditoria/cambios-ti/{cambio_id}` | `requiere_rol_admin` | `admin`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/admin_router.py:detalle_cambio_ti` |
| GET | `/api/v1/alertas` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/alertas_router.py:list_alertas` |
| PATCH | `/api/v1/alertas/{alerta_id}/resolver` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/alertas_router.py:resolve_alerta` |
| POST | `/api/v1/alertas/{alerta_id}/resolver` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/alertas_router.py:resolve_alerta` |
| GET | `/api/v1/analitica/banco-capacitores/planta` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/analitica_router.py:obtener_banco_capacitores_planta` |
| GET | `/api/v1/analitica/penalizaciones/planta` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/analitica_router.py:obtener_penalizaciones_planta` |
| POST | `/api/v1/asistente/preguntar` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/asistente_router.py:preguntar` |
| GET | `/api/v1/audit/logs` | `requiere_rol_auditor_o_superadmin` | `superadmin` | — | no | `src/infrastructure/fastapi/routes/audit_router.py:listar_audit_logs` |
| POST | `/api/v1/auth/2fa/activar` | `no_permitido_para_invitados_2fa` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/auth_router.py:activar_2fa` |
| POST | `/api/v1/auth/2fa/desactivar` | `no_permitido_para_invitados_2fa` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/auth_router.py:desactivar_2fa` |
| POST | `/api/v1/auth/2fa/setup` | `no_permitido_para_invitados_2fa` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/auth_router.py:setup_2fa` |
| POST | `/api/v1/auth/2fa/verificar` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/auth_router.py:verificar_2fa` |
| PATCH | `/api/v1/auth/confirm-password-change` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/auth_router.py:confirm_password_change` |
| POST | `/api/v1/auth/dispositivos/revocar-todos` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/auth_router.py:revocar_dispositivos` |
| POST | `/api/v1/auth/login` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/auth_router.py:login` |
| POST | `/api/v1/auth/logout` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/auth_router.py:logout` |
| POST | `/api/v1/auth/logout-todas` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/auth_router.py:logout_todas` |
| GET | `/api/v1/auth/me` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/auth_router.py:me` |
| POST | `/api/v1/auth/recuperar-contrasena` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/auth_router.py:solicitar_recuperacion` |
| PATCH | `/api/v1/auth/request-password-change-code` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/auth_router.py:request_password_change_code` |
| POST | `/api/v1/auth/restablecer-contrasena` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/auth_router.py:restablecer_contrasena` |
| GET | `/api/v1/cargas` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/cargas_router.py:listar_cargas` |
| POST | `/api/v1/cargas` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/cargas_router.py:registrar_carga` |
| POST | `/api/v1/cargas/analisis` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/cargas_router.py:disparar_analisis` |
| GET | `/api/v1/cargas/atribucion` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/cargas_router.py:obtener_atribucion` |
| POST | `/api/v1/cargas/campanas/activas` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/cargas_router.py:iniciar_campana_activa` |
| POST | `/api/v1/cargas/campanas/pasivas` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/cargas_router.py:iniciar_campana_pasiva` |
| GET | `/api/v1/cargas/campanas/{campana_id}` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/cargas_router.py:obtener_campana` |
| PATCH | `/api/v1/cargas/campanas/{campana_id}/descartar` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/cargas_router.py:descartar_campana` |
| PATCH | `/api/v1/cargas/campanas/{campana_id}/finalizar` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/cargas_router.py:finalizar_campana` |
| GET | `/api/v1/cargas/exportar/csv` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/cargas_router.py:exportar_cargas_csv` |
| GET | `/api/v1/cargas/intervalos` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/cargas_router.py:listar_intervalos` |
| PATCH | `/api/v1/cargas/intervalos/{intervalo_id}/corregir` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/cargas_router.py:corregir_intervalo` |
| GET | `/api/v1/cargas/perfil` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/cargas_router.py:perfilar_consumo` |
| GET | `/api/v1/cargas/presets` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/cargas_router.py:obtener_presets_catalogo` |
| POST | `/api/v1/cargas/presets/inicializar` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/cargas_router.py:inicializar_presets_catalogo` |
| GET | `/api/v1/cargas/{carga_id}` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/cargas_router.py:obtener_carga` |
| PATCH | `/api/v1/cargas/{carga_id}` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/cargas_router.py:actualizar_carga` |
| GET | `/api/v1/cargas/{carga_id}/campanas` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/cargas_router.py:listar_campanas_de_carga` |
| PUT | `/api/v1/cargas/{carga_id}/firma` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/cargas_router.py:fijar_firma_manual` |
| GET | `/api/v1/cargas/{carga_id}/intervalos` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/cargas_router.py:listar_intervalos_de_carga` |
| PATCH | `/api/v1/disponibilidad/eventos/{evento_id}/corregir` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:corregir_clasificacion` |
| POST | `/api/v1/disponibilidad/eventos/{evento_id}/corregir` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:corregir_clasificacion` |
| GET | `/api/v1/disponibilidad/maquinas` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:listar_maquinas` |
| POST | `/api/v1/disponibilidad/maquinas` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:registrar_maquina` |
| GET | `/api/v1/disponibilidad/maquinas/{maquina_id}` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:obtener_maquina` |
| PATCH | `/api/v1/disponibilidad/maquinas/{maquina_id}` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:actualizar_maquina` |
| GET | `/api/v1/disponibilidad/maquinas/{maquina_id}/eventos` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:listar_eventos` |
| GET | `/api/v1/disponibilidad/maquinas/{maquina_id}/exportar/csv` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:exportar_disponibilidad_csv` |
| GET | `/api/v1/disponibilidad/maquinas/{maquina_id}/histograma` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:obtener_histograma` |
| GET | `/api/v1/disponibilidad/maquinas/{maquina_id}/metricas-oee` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:obtener_metricas_oee` |
| GET | `/api/v1/disponibilidad/paradas-programadas` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:listar_paradas_programadas` |
| POST | `/api/v1/disponibilidad/paradas-programadas` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/disponibilidad_router.py:registrar_parada_programada` |
| GET | `/api/v1/dispositivos` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/dispositivos_router.py:list_dispositivos` |
| POST | `/api/v1/dispositivos` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/dispositivos_router.py:register_dispositivo` |
| GET | `/api/v1/dispositivos/{device_id}` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/dispositivos_router.py:get_dispositivo` |
| PATCH | `/api/v1/dispositivos/{device_id}` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/dispositivos_router.py:update_dispositivo` |
| PUT | `/api/v1/dispositivos/{device_id}` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/dispositivos_router.py:update_dispositivo` |
| POST | `/api/v1/dispositivos/{device_id}/realtime` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/dispositivos_router.py:activate_realtime_mode` |
| GET | `/api/v1/nodo/unifilar/{nodo_id}` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/planta_estructura_router.py:resumen_nodo_unifilar_directo` |
| POST | `/api/v1/oauth/authorize` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/oauth_router.py:autorizar_consentimiento_oauth` |
| POST | `/api/v1/oauth/consent` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/oauth_router.py:procesar_consentimiento_oauth` |
| GET | `/api/v1/oauth/consent-info` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/oauth_router.py:obtener_consent_info_oauth` |
| POST | `/api/v1/oauth/register` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/oauth_router.py:registrar_cliente_dinamico_oauth` |
| POST | `/api/v1/oauth/revoke` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/oauth_router.py:revocar_token_oauth` |
| POST | `/api/v1/oauth/token` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/oauth_router.py:canjear_token_oauth` |
| GET | `/api/v1/organizaciones` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/organizaciones_router.py:list_organizaciones` |
| GET | `/api/v1/planes` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/planes_router.py:list_planes` |
| POST | `/api/v1/planes` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/planes_router.py:create_plan` |
| GET | `/api/v1/planta/areas` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/planta_estructura_router.py:get_areas_estadisticas_default` |
| GET | `/api/v1/planta/layout` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/planta_estructura_router.py:get_layout_default` |
| GET | `/api/v1/planta/unifilar` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/planta_estructura_router.py:get_unifilar_default` |
| GET | `/api/v1/plantas` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/organizaciones_router.py:list_plantas` |
| GET | `/api/v1/plantas/{planta_id}/areas` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/planta_estructura_router.py:get_areas_estadisticas_by_planta` |
| GET | `/api/v1/plantas/{planta_id}/layout` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/planta_estructura_router.py:get_layout_by_planta` |
| GET | `/api/v1/plantas/{planta_id}/unifilar` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/planta_estructura_router.py:get_unifilar_by_planta` |
| GET | `/api/v1/plantas/{planta_id}/unifilar/nodos/{nodo_id}` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/planta_estructura_router.py:resumen_nodo_unifilar` |
| GET | `/api/v1/plantas/{planta_id}/unifilar/nodos/{nodo_id}/resumen` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/planta_estructura_router.py:resumen_nodo_unifilar` |
| GET | `/api/v1/plantas/{planta_id}/unifilar/nodos/{nodo_id}/resumen/historico` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/planta_estructura_router.py:historico_nodo_unifilar` |
| POST | `/api/v1/produccion/lecturas` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/produccion_router.py:registrar_lectura` |
| POST | `/api/v1/sge/competencias/acuse` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/sge_router.py:registrar_acuse_capacitacion` |
| GET | `/api/v1/sge/competencias/mis-capacitaciones` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/sge_router.py:consultar_mis_competencias` |
| GET | `/api/v1/sge/documentacion` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/sge_router.py:obtener_documentacion_sge` |
| GET | `/api/v1/sge/plantas/{planta_id}/ahorros-cusum` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/sge_router.py:obtener_ahorros_cusum` |
| GET | `/api/v1/sge/plantas/{planta_id}/balance-energia` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/sge_router.py:obtener_balance_energia` |
| GET | `/api/v1/sge/plantas/{planta_id}/costo-estimado` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/sge_router.py:obtener_costo_estimado` |
| GET | `/api/v1/sge/plantas/{planta_id}/facturas-distribuidora` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/sge_router.py:obtener_facturas_distribuidora` |
| GET | `/api/v1/sge/plantas/{planta_id}/linea-base` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/sge_router.py:obtener_lineas_base` |
| POST | `/api/v1/suscripciones/checkout` | `requiere_rol_admin` | `admin`, `superadmin` | — | no | `src/infrastructure/fastapi/routes/billing_router.py:crear_checkout_suscripcion` |
| POST | `/api/v1/system/purge` | `requiere_rol_superadmin` | `superadmin` | — | no | `src/infrastructure/fastapi/routes/system_router.py:trigger_purge` |
| GET | `/api/v1/system/ws-status` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/system_router.py:websocket_status` |
| GET | `/api/v1/telemetria/alerts/{device_id}` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/telemetria_router.py:get_alerts_history` |
| GET | `/api/v1/telemetria/energy/{device_id}` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/telemetria_router.py:get_energy_history` |
| GET | `/api/v1/telemetria/exportar/csv` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/telemetria_router.py:exportar_telemetria_csv` |
| GET | `/api/v1/telemetria/fases-diagnostico/{device_id}` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/telemetria_router.py:get_phase_diagnostic` |
| GET | `/api/v1/telemetria/instantaneous/{device_id}` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/telemetria_router.py:get_instantaneous_history` |
| GET | `/api/v1/telemetria/latest/{device_id}` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/telemetria_router.py:get_latest_telemetry` |
| GET | `/api/v1/tuya/notificador/estado` | — | todos (sin guard) | autenticado (cualquier rol) | sí | `src/infrastructure/fastapi/routes/notificador_router.py:estado_alarma` |
| POST | `/api/v1/usuarios` | `requiere_rol_admin` | `admin`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/usuarios_router.py:crear_usuario` |
| GET | `/api/v1/usuarios/integraciones` | — | todos (sin guard) | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/oauth_router.py:listar_integraciones_usuario` |
| DELETE | `/api/v1/usuarios/integraciones/{client_id}` | `requiere_rol_escritura` | `admin`, `ingeniero`, `mantenimiento`, `operador`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/oauth_router.py:revocar_integracion_usuario` |
| DELETE | `/api/v1/usuarios/{usuario_id}` | `requiere_rol_admin` | `admin`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/usuarios_router.py:dar_baja_usuario` |
| GET | `/api/v1/usuarios/{usuario_id}/plantas` | `requiere_rol_admin` | `admin`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/usuarios_router.py:listar_plantas_usuario` |
| PUT | `/api/v1/usuarios/{usuario_id}/plantas` | `requiere_rol_admin` | `admin`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/usuarios_router.py:asignar_plantas_usuario` |
| PATCH | `/api/v1/usuarios/{usuario_id}/rol` | `requiere_rol_admin` | `admin`, `superadmin` | autenticado (cualquier rol) | no | `src/infrastructure/fastapi/routes/usuarios_router.py:cambiar_rol_usuario` |
| POST | `/api/v1/webhooks/mercadopago` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/billing_router.py:webhook_mercadopago` |
| GET | `/favicon.ico` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/system_router.py:favicon` |
| GET | `/health` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/system_router.py:health_check` |
| GET | `/health/build` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/system_router.py:health_build` |
| GET | `/health/live` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/system_router.py:liveness_check` |
| GET | `/health/ready` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/system_router.py:readiness_check` |
| POST | `/oauth/register` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/oauth_router.py:registrar_cliente_dinamico_oauth` |
| POST | `/oauth/revoke` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/oauth_router.py:revocar_token_oauth` |
| POST | `/oauth/token` | — | todos (sin guard) | sin dependencia de auth detectada | no | `src/infrastructure/fastapi/routes/oauth_router.py:canjear_token_oauth` |
