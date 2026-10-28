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
