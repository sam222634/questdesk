from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from app.config import settings


def generate_bitacora_markdown(
    ticket_code: str,
    title: str,
    description: str,
    queue_slug: str,
    priority_name: str,
    estimated_points: int,
    channel: str,
    sender_email: Optional[str] = None,
) -> str:
    """Crea la plantilla Markdown inicial para la bitácora del ticket y devuelve su URI relativa."""
    target_dir: Path = settings.bitacoras_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    file_name = f"{ticket_code}.md"
    file_path = target_dir / file_name
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not file_path.exists():
        sender_line = f"\nsender_email: {sender_email}" if sender_email else ""
        content = f"""---
ticket_code: {ticket_code}
title: "{title.replace('"', '\\"')}"
queue: {queue_slug}
priority: {priority_name}
estimated_points: {estimated_points}
source_channel: {channel}{sender_line}
created_at: {now_iso}
status: NEW
---

# {ticket_code}: {title}

## 1. Descripción del Ticket
{description.strip()}

## 2. Bitácora de Investigación y Ejecución
- [ ] Análisis inicial del requerimiento
- [ ] Ejecución de pasos técnicos

```bash
# Registra aquí los comandos, pruebas o notas relevantes
```

## 3. Causa Raíz / Hallazgos
_Pendiente de documentar._

## 4. Solución Aplicada y Verificación
_Pendiente de documentar al resolver el ticket._
"""
        file_path.write_text(content, encoding="utf-8")

    return f"bitacoras/{file_name}"
