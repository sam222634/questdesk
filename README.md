# Sistema Modular de Tickets Ciberfísico y Gamificado

Sistema de código abierto diseñado bajo una arquitectura modular orientada a eventos. Combina un núcleo empresarial de gestión de tickets (PostgreSQL + API REST) con generación automática de bitácoras en Markdown, integración de tarjetas de tinta electrónica pasivas (Waveshare NFC e-Paper), automatización de enfoque y un motor de progresión RPG asistido por IA local.

## Estructura del Proyecto

```text
.
├── ARQUITECTURA_PROYECTO.md   # Especificación detallada de arquitectura y módulos
├── LICENSE                    # Licencia Apache 2.0
├── docker-compose.yml         # Orquestación aislada de contenedores
├── database/                  # Scripts DDL de inicialización para PostgreSQL
├── bitacoras/                 # Archivos Markdown generados por cada ticket
└── modules/
    ├── core_tickets/          # Módulo 1: API REST, Interfaz Web y CLI de tickets
    ├── email_ingestor/        # Submódulo de entrada de correo (Webhook / IMAP)
    └── markdown_logger/       # Módulo 2: Sincronizador y generador de bitácoras MD
```

## Principios Clave

1. **Aislamiento por Contenedores (Docker):** Cada servicio se ejecuta con sus propias dependencias sin contaminar el sistema operativo anfitrión.
2. **Separación de Datos:** PostgreSQL gestiona los datos cuantitativos, estados y auditoría transaccional; Markdown almacena la bitácora cualitativa de resolución.
3. **Privacidad Local (*Local-First*):** Sin dependencia de servicios en la nube. Integración con modelos locales vía Ollama y webhooks locales.

## Licencia

Distribuido bajo la licencia **Apache 2.0**. Consulta el archivo [LICENSE](./LICENSE) para más detalles.

## Reglas de negocio de tickets

- `QUESTDESK_MODE=enterprise` (por defecto): todo ticket se crea asignado a otro usuario; no existe autoasignación. Un usuario sin subordinados (AGENT) no puede crear tickets.
- `QUESTDESK_MODE=personal`: el usuario puede crearse tickets a sí mismo.
- Al asignar o reasignar, el ticket pasa de `NEW` a `ASSIGNED` y se cierran las sesiones de tiempo abiertas del responsable anterior. No se pueden asignar tickets resueltos o cerrados.
- Solo el responsable actual (o ADMIN) modifica estado, tiempo, bitácora y delegación. Quien delegó conserva acceso de solo lectura (`can_edit: false`).
- Los KPIs del dashboard se calculan sobre todos los tickets autorizados; el interruptor "Incluir resueltos y cerrados" solo filtra la tabla.
- Devolución: el responsable actual puede devolver el ticket a quien se lo asignó (último `CREATED`/`ASSIGNED` en auditoría), además de delegar a sus subordinados. Un ADMIN puede reasignarlo a cualquiera.
- Bitácora: la estructura (frontmatter, título y encabezados) es fija. Solo se modifican o agregan bloques de texto en las secciones 2, 3 y 4 mediante `PUT /api/v1/tickets/{codigo}/bitacora/sections/{seccion}` (`investigacion`, `causa_raiz`, `solucion`; `mode`: `replace` o `append`). La sección 1 es de solo lectura. El servidor rechaza HTML, enlaces `javascript:`/`vbscript:`/`data:`, encabezados nivel 1-2, bloques de código sin cerrar y textos de más de 20000 caracteres. La interfaz escapa todo el contenido y `index.php` envía una Content-Security-Policy restrictiva.
