function escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function showError(msg) {
  const box = document.getElementById('errorBox');
  if (!msg) {
    box.style.display = 'none';
    box.textContent = '';
    return;
  }
  box.textContent = msg;
  box.style.display = 'block';
}

async function loadTickets() {
  const includeClosed = document.getElementById('showClosed').checked;
  const res = await fetch(`/?api=/tickets&include_closed=${includeClosed}`);
  const tickets = await res.json().catch(() => []);
  const container = document.getElementById('ticketsList');

  if (!res.ok) {
    showError(`Error al consultar tickets [${tickets.failed_step || 'api'}]: ${tickets.detail || 'Error de conexión'}`);
    return;
  }

  if (!Array.isArray(tickets) || !tickets.length) {
    container.innerHTML = '<div class="subtitle">No hay tickets activos en este momento.</div>';
    return;
  }

  container.innerHTML = tickets.map(t => {
    const code = escapeHtml(t.ticket_code);
    const title = escapeHtml(t.title);
    const prio = escapeHtml(t.priority_name);
    const status = escapeHtml(t.status_name);
    const queue = escapeHtml(t.queue_name);
    const uri = escapeHtml(t.bitacora_uri || '');

    return `
      <div class="ticket-row">
        <div>
          <div>
            <span class="code">${code}</span>
            <strong style="margin-left:0.4rem">${title}</strong>
            <span class="badge prio-${prio}">${prio}</span>
            <span class="badge">${status}</span>
          </div>
          <div class="meta">
            Área: ${queue} · Esfuerzo: ${Number(t.estimated_points)} pts · Tiempo: ${Number(t.total_minutes)} min · Bitácora: <code>${uri}</code>
          </div>
        </div>
        <div class="actions">
          ${t.status_name !== 'IN_PROGRESS' && !t.is_closed ? `<button type="button" class="secondary" data-code="${code}" data-status="IN_PROGRESS">Iniciar Foco</button>` : ''}
          ${!t.is_closed ? `<button type="button" class="secondary" data-code="${code}" data-status="RESOLVED">Resolver</button>` : ''}
        </div>
      </div>`;
  }).join('');
}

async function createTicket(e) {
  e.preventDefault();
  showError(null);
  const payload = {
    title: document.getElementById('title').value,
    description: document.getElementById('description').value,
    queue_slug: document.getElementById('queue_slug').value,
    priority_name: document.getElementById('priority_name').value,
    estimated_points: parseInt(document.getElementById('estimated_points').value, 10),
    channel: 'WEB_UI'
  };

  const res = await fetch('/?api=/tickets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (res.ok) {
    document.getElementById('ticketForm').reset();
    loadTickets();
  } else {
    const err = await res.json().catch(() => ({}));
    showError(`Transacción revertida en paso [${err.failed_step || 'validación'}]: ${err.detail || 'Error al procesar solicitud'}`);
  }
}

async function setStatus(code, status_name) {
  showError(null);
  const res = await fetch(`/?api=/tickets/${encodeURIComponent(code)}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status_name, actor: 'web_ui' })
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    showError(`Transacción revertida en paso [${err.failed_step || 'estado'}]: ${err.detail || 'No se pudo cambiar el estado'}`);
  }
  loadTickets();
}

document.getElementById('ticketForm').addEventListener('submit', createTicket);
document.getElementById('showClosed').addEventListener('change', loadTickets);
document.getElementById('ticketsList').addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-code]');
  if (btn) {
    setStatus(btn.dataset.code, btn.dataset.status);
  }
});

loadTickets();
