# Entornos del proyecto

Este documento centraliza las rutas absolutas y el modo de acceso de cada **entorno** de trabajo.
(En español técnico se dice "entorno", no "modo" — "modo desarrollo" se usa más para un *flag* o
comportamiento de una app en ejecución, ej. `NODE_ENV=development`. Para hablar de "dónde vive el
código" el término correcto es **entorno de desarrollo** / **entorno de producción**.)

| Entorno | Equipo | Ruta absoluta | Acceso |
| --- | --- | --- | --- |
| Desarrollo | Laptop | `/home/agustin/proyectos_software/datamaq-telemetry` | Local |
| Desarrollo | PC de escritorio | `/home/agustin/proyectos_software/datamaq-telemetry` | Local |
| Producción | VPS | `/var/www/datamaq-telemetry` | `ssh vps` (alias en `~/.ssh/config`, ver abajo) |

## Detalle por entorno

### Desarrollo — Laptop

- Ruta: `/home/agustin/proyectos_software/datamaq-telemetry`
- Usuario del sistema: `agustin`
- Acceso: directo, es el equipo local.

### Desarrollo — PC de escritorio

- Ruta: `/home/agustin/proyectos_software/datamaq-telemetry` (misma ruta que en la laptop).
- Usuario del sistema: `agustin`.
- Acceso: directo, es el equipo local.

> Si en algún momento la ruta de la PC de escritorio difiere de la de la laptop, actualizar esta
> tabla — hoy se documentan como iguales.

### Producción — VPS

- Ruta de despliegue: `/var/www/datamaq-telemetry` (el `.env` de esa ruta tiene las credenciales
  reales, no versionadas).
- Acceso: `ssh vps` (alias definido en `~/.ssh/config` de cada equipo de desarrollo; internamente
  apunta a `root@168.181.184.103:5932` con clave `~/.ssh/id_ed25519`).
- Referencias de uso: [`docs/troubleshooting-conectividad-dispositivos.md`](./troubleshooting-conectividad-dispositivos.md)
  y [`docs/provisioning_guide.md`](./provisioning_guide.md).

## Notas de vocabulario

- **Entorno** (environment): dónde y cómo corre el código — desarrollo, staging, producción.
- **Modo** (mode): un comportamiento conmutable dentro de una misma ejecución (ej. modo oscuro,
  modo debug, `NODE_ENV=development` como variable que activa comportamientos de desarrollo).
- Es válido decir "estoy trabajando en desarrollo" o "estoy en el entorno de desarrollo"; "modo
  desarrollo" no es incorrecto coloquialmente, pero en documentación técnica preferí "entorno".
