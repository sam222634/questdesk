from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from app.config import settings
from app.routers import catalogs, tickets

app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description="Módulo 1: Gestor de Tickets Normalizado con generación de Bitácoras Markdown.",
)

app.include_router(catalogs.router)
app.include_router(tickets.router)


@app.get("/health", tags=["Sistema"])
def healthcheck():
    return {"status": "ok", "service": "core-tickets", "version": settings.app_version}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def web_dashboard():
    """Panel web ligero local para visualizar, crear y cambiar el estado de tickets desde PC o móvil."""
    return """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>QuestDesk — Gestor de Tickets</title>
  <style>
    :root {
      --bg: #0f172a;
      --panel: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --success: #22c55e;
      --warn: #f59e0b;
      --danger: #ef4444;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 1.5rem;
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--border);
      padding-bottom: 1rem;
      margin-bottom: 1.5rem;
      flex-wrap: wrap;
      gap: 1rem;
    }
    h1 { margin: 0; font-size: 1.4rem; }
    .subtitle { color: var(--muted); font-size: 0.9rem; }
    .layout {
      display: grid;
      grid-template-columns: 320px 1fr;
      gap: 1.5rem;
    }
    @media (max-width: 860px) {
      .layout { grid-template-columns: 1fr; }
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1.2rem;
    }
    label { display: block; font-size: 0.85rem; color: var(--muted); margin-top: 0.8rem; margin-bottom: 0.3rem; }
    input, select, textarea, button {
      width: 100%;
      padding: 0.55rem 0.7rem;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: #0b1120;
      color: var(--text);
      font-size: 0.9rem;
    }
    button {
      background: var(--accent);
      color: #0f172a;
      font-weight: 600;
      border: none;
      cursor: pointer;
      margin-top: 1rem;
    }
    button.secondary {
      background: transparent;
      color: var(--text);
      border: 1px solid var(--border);
      width: auto;
      margin-top: 0;
      padding: 0.35rem 0.65rem;
      font-size: 0.8rem;
    }
    .tickets-grid { display: flex; flex-direction: column; gap: 0.8rem; }
    .ticket-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
      background: #0b1120;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.9rem 1rem;
      flex-wrap: wrap;
    }
    .badge {
      display: inline-block;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      font-size: 0.75rem;
      font-weight: 600;
      background: var(--border);
    }
    .prio-CRITICAL, .prio-HIGH { background: rgba(239,68,68,0.2); color: #fca5a5; }
    .prio-MEDIUM { background: rgba(245,158,11,0.2); color: #fcd34d; }
    .prio-LOW { background: rgba(56,189,248,0.15); color: #7dd3fc; }
    .code { font-family: monospace; color: var(--accent); font-weight: 700; }
    .meta { font-size: 0.8rem; color: var(--muted); margin-top: 0.3rem; }
    .actions { display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap; }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>QuestDesk — Módulo 1: Core de Tickets</h1>
      <div class="subtitle">PostgreSQL Normalizado + Bitácoras Markdown Automáticas</div>
    </div>
    <div class="actions">
      <label style="margin:0"><input type="checkbox" id="showClosed" style="width:auto" onchange="loadTickets()"> Ver resueltos</label>
      <a href="/docs" style="color:var(--accent);font-size:0.85rem;margin-left:1rem;">API Docs (Swagger)</a>
    </div>
  </header>

  <div class="layout">
    <div class="card">
      <h3 style="margin-top:0">Nuevo Ticket</h3>
      <form id="ticketForm" onsubmit="createTicket(event)">
        <label>Título</label>
        <input type="text" id="title" required placeholder="Ej. Configurar respaldo de base de datos" />

        <label>Descripción inicial</label>
        <textarea id="description" rows="4" required placeholder="Contexto o requerimiento..."></textarea>

        <label>Cola / Área</label>
        <select id="queue_slug">
          <option value="general">General (GEN)</option>
          <option value="infra">Infraestructura (INF)</option>
          <option value="dev">Desarrollo (DEV)</option>
          <option value="personal">Personal (PER)</option>
        </select>

        <label>Prioridad</label>
        <select id="priority_name">
          <option value="LOW">Baja (LOW)</option>
          <option value="MEDIUM" selected>Media (MEDIUM)</option>
          <option value="HIGH">Alta (HIGH)</option>
          <option value="CRITICAL">Crítica (CRITICAL)</option>
        </select>

        <label>Esfuerzo estimado (1 a 10 pts)</label>
        <input type="number" id="estimated_points" min="1" max="10" value="2" />

        <button type="submit">Crear Ticket + Bitácora .md</button>
      </form>
    </div>

    <div class="card">
      <h3 style="margin-top:0">Cola de Tickets</h3>
      <div id="ticketsList" class="tickets-grid">Cargando...</div>
    </div>
  </div>

  <script>
    async function loadTickets() {
      const includeClosed = document.getElementById('showClosed').checked;
      const res = await fetch(`/api/v1/tickets?include_closed=${includeClosed}`);
      const tickets = await res.json();
      const container = document.getElementById('ticketsList');
      if (!tickets.length) {
        container.innerHTML = '<div class="subtitle">No hay tickets activos en este momento.</div>';
        return;
      }
      container.innerHTML = tickets.map(t => `
        <div class="ticket-row">
          <div>
            <div>
              <span class="code">${t.ticket_code}</span>
              <strong style="margin-left:0.4rem">${t.title}</strong>
              <span class="badge prio-${t.priority_name}">${t.priority_name}</span>
              <span class="badge">${t.status_name}</span>
            </div>
            <div class="meta">
              Área: ${t.queue_name} · Esfuerzo: ${t.estimated_points} pts · Tiempo: ${t.total_minutes} min · Bitácora: <code>${t.bitacora_uri || ''}</code>
            </div>
          </div>
          <div class="actions">
            ${t.status_name !== 'IN_PROGRESS' && !t.is_closed ? `<button class="secondary" onclick="setStatus('${t.ticket_code}', 'IN_PROGRESS')">Iniciar Foco</button>` : ''}
            ${!t.is_closed ? `<button class="secondary" onclick="setStatus('${t.ticket_code}', 'RESOLVED')">Resolver</button>` : ''}
          </div>
        </div>
      `).join('');
    }

    async function createTicket(e) {
      e.preventDefault();
      const payload = {
        title: document.getElementById('title').value,
        description: document.getElementById('description').value,
        queue_slug: document.getElementById('queue_slug').value,
        priority_name: document.getElementById('priority_name').value,
        estimated_points: parseInt(document.getElementById('estimated_points').value, 10),
        channel: 'WEB_UI'
      };
      const res = await fetch('/api/v1/tickets', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        document.getElementById('ticketForm').reset();
        loadTickets();
      }
    }

    async function setStatus(code, status_name) {
      await fetch(`/api/v1/tickets/${code}/status`, {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ status_name, actor: 'web_ui' })
      });
      loadTickets();
    }

    loadTickets();
  </script>
</body>
</html>"""
