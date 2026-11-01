let currentUser = null;
let catalogs = { queues: [], statuses: [], priorities: [], users: [] };
let allTickets = [];
let selectedTicketCode = null;

function escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function showError(msg, targetId = 'errorBox') {
  const box = document.getElementById(targetId);
  if (!box) return;
  if (!msg) {
    box.style.display = 'none';
    box.textContent = '';
    return;
  }
  box.textContent = msg;
  box.style.display = 'block';
}

function showNotice(msg) {
  const box = document.getElementById('noticeBox');
  if (!msg) {
    box.style.display = 'none';
    box.textContent = '';
    return;
  }
  box.textContent = msg;
  box.style.display = 'block';
  setTimeout(() => {
    box.style.display = 'none';
  }, 3500);
}

function renderMarkdownPreview(md) {
  const lines = String(md ?? '').split('\n');
  let html = '';
  let inCode = false;
  let inFrontmatter = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (i === 0 && line.trim() === '---') {
      inFrontmatter = true;
      html += '<pre class="frontmatter">';
      continue;
    }
    if (inFrontmatter) {
      if (line.trim() === '---') {
        inFrontmatter = false;
        html += '</pre>';
      } else {
        html += escapeHtml(line) + '\n';
      }
      continue;
    }
    if (line.trim().startsWith('```')) {
      inCode = !inCode;
      html += inCode ? '<pre><code>' : '</code></pre>';
      continue;
    }
    if (inCode) {
      html += escapeHtml(line) + '\n';
      continue;
    }
    if (line.startsWith('# ')) {
      html += `<h1>${escapeHtml(line.slice(2))}</h1>`;
    } else if (line.startsWith('## ')) {
      html += `<h2>${escapeHtml(line.slice(3))}</h2>`;
    } else if (line.startsWith('### ')) {
      html += `<h3>${escapeHtml(line.slice(4))}</h3>`;
    } else if (line.startsWith('- [x] ') || line.startsWith('- [X] ')) {
      html += `<div><input type="checkbox" checked disabled style="width:auto;margin-right:0.4rem;">${escapeHtml(line.slice(6))}</div>`;
    } else if (line.startsWith('- [ ] ')) {
      html += `<div><input type="checkbox" disabled style="width:auto;margin-right:0.4rem;">${escapeHtml(line.slice(6))}</div>`;
    } else if (line.startsWith('- ')) {
      html += `<div>&bull; ${escapeHtml(line.slice(2))}</div>`;
    } else if (line.trim() === '') {
      html += '<br/>';
    } else {
      html += `<p style="margin:0.25rem 0;">${escapeHtml(line)}</p>`;
    }
  }
  if (inCode) html += '</code></pre>';
  return html;
}

async function checkSession() {
  const res = await fetch('/?auth=status');
  const data = await res.json().catch(() => ({ authenticated: false }));
  if (data.authenticated && data.user) {
    currentUser = data.user;
    document.getElementById('loginScreen').style.display = 'none';
    document.getElementById('appScreen').style.display = 'block';
    document.getElementById('userDisplayName').textContent = `${currentUser.display_name} (${currentUser.username})`;
    document.getElementById('userRoleBadge').textContent = currentUser.role;
    await loadCatalogs();
    await loadTickets();
  } else {
    currentUser = null;
    document.getElementById('appScreen').style.display = 'none';
    document.getElementById('loginScreen').style.display = 'flex';
  }
}

async function handleLogin(e) {
  e.preventDefault();
  showError(null, 'loginError');
  const apiKey = document.getElementById('loginApiKey').value;
  const res = await fetch('/?auth=login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey })
  });
  const data = await res.json().catch(() => ({}));
  if (res.ok && data.ok) {
    document.getElementById('loginForm').reset();
    await checkSession();
  } else {
    showError(data.detail || 'Credencial inválida o revocada.', 'loginError');
  }
}

async function handleLogout() {
  await fetch('/?auth=logout', { method: 'POST' });
  selectedTicketCode = null;
  document.getElementById('inspectorContent').style.display = 'none';
  document.getElementById('inspectorEmpty').style.display = 'block';
  await checkSession();
}

async function loadCatalogs() {
  const res = await fetch('/?api=/catalogs');
  if (!res.ok) return;
  catalogs = await res.json();

  const filterQueue = document.getElementById('filterQueue');
  const newQueue = document.getElementById('queue_slug');
  filterQueue.innerHTML = '<option value="">Todas las áreas</option>' +
    catalogs.queues.map(q => `<option value="${escapeHtml(q.slug)}">${escapeHtml(q.name)} (${escapeHtml(q.prefix)})</option>`).join('');
  newQueue.innerHTML = catalogs.queues.map(q => `<option value="${escapeHtml(q.slug)}">${escapeHtml(q.name)} (${escapeHtml(q.prefix)})</option>`).join('');

  const filterStatus = document.getElementById('filterStatus');
  const manageStatus = document.getElementById('manageStatusSelect');
  filterStatus.innerHTML = '<option value="">Todos los estados</option>' +
    catalogs.statuses.map(s => `<option value="${escapeHtml(s.name)}">${escapeHtml(s.name)}</option>`).join('');
  manageStatus.innerHTML = catalogs.statuses.map(s => `<option value="${escapeHtml(s.name)}">${escapeHtml(s.name)}</option>`).join('');

  const newPrio = document.getElementById('priority_name');
  newPrio.innerHTML = catalogs.priorities.map(p =>
    `<option value="${escapeHtml(p.name)}" ${p.name === 'MEDIUM' ? 'selected' : ''}>${escapeHtml(p.name)}</option>`
  ).join('');

  const delegateSelect = document.getElementById('delegateUserSelect');
  const newAssignee = document.getElementById('newTicketAssignee');
  const userOptions = catalogs.users.map(u =>
    `<option value="${escapeHtml(u.user_uuid)}">${escapeHtml(u.display_name)} (${escapeHtml(u.username)} - ${escapeHtml(u.role)})</option>`
  ).join('');
  delegateSelect.innerHTML = userOptions;
  newAssignee.innerHTML = '<option value="">Asignar a mi usuario actual</option>' + userOptions;
}

function updateDashboardKPIs(tickets) {
  let countNew = 0;
  let countInProgress = 0;
  let countBlocked = 0;
  let countHighPrio = 0;
  let countResolved = 0;
  let totalMinutes = 0;
  let totalPoints = 0;
  const byQueue = {};

  for (const t of tickets) {
    totalMinutes += Number(t.total_minutes || 0);
    totalPoints += Number(t.estimated_points || 0);
    byQueue[t.queue_name] = (byQueue[t.queue_name] || 0) + 1;

    if (t.is_closed) {
      countResolved++;
    } else {
      if (t.status_name === 'NEW' || t.status_name === 'ASSIGNED') countNew++;
      if (t.status_name === 'IN_PROGRESS') countInProgress++;
      if (t.status_name === 'BLOCKED') countBlocked++;
      if (t.priority_name === 'HIGH' || t.priority_name === 'CRITICAL') countHighPrio++;
    }
  }

  document.getElementById('kpiNew').textContent = String(countNew);
  document.getElementById('kpiInProgress').textContent = String(countInProgress);
  document.getElementById('kpiBlocked').textContent = String(countBlocked);
  document.getElementById('kpiHighPrio').textContent = String(countHighPrio);
  document.getElementById('kpiResolved').textContent = String(countResolved);
  document.getElementById('kpiEffort').textContent = `${totalMinutes}m / ${totalPoints} pts`;

  const distContainer = document.getElementById('queueDistribution');
  const entries = Object.entries(byQueue);
  distContainer.innerHTML = entries.length
    ? entries.map(([qName, count]) => `<span class="queue-pill"><strong>${escapeHtml(qName)}:</strong> ${count}</span>`).join('')
    : '<span>Sin distribución por área</span>';
}

function renderTicketsTable() {
  const search = document.getElementById('filterSearch').value.trim().toLowerCase();
  const filtered = allTickets.filter(t => {
    if (!search) return true;
    return (
      String(t.ticket_code).toLowerCase().includes(search) ||
      String(t.title).toLowerCase().includes(search) ||
      String(t.assignee_display_name || '').toLowerCase().includes(search)
    );
  });

  document.getElementById('ticketsCount').textContent = `${filtered.length} registros`;
  const tbody = document.getElementById('ticketsTableBody');

  if (!filtered.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="subtitle">No hay tickets que coincidan con los criterios actuales.</td></tr>';
    return;
  }

  tbody.innerHTML = filtered.map(t => {
    const code = escapeHtml(t.ticket_code);
    const isSelected = selectedTicketCode === t.ticket_code ? 'selected' : '';
    return `
      <tr class="${isSelected}" data-ticket-code="${code}">
        <td><span class="code">${code}</span></td>
        <td><strong>${escapeHtml(t.title)}</strong></td>
        <td>${escapeHtml(t.queue_name)}</td>
        <td><span class="badge prio-${escapeHtml(t.priority_name)}">${escapeHtml(t.priority_name)}</span></td>
        <td><span class="badge">${escapeHtml(t.status_name)}</span></td>
        <td>${escapeHtml(t.assignee_display_name || '')}</td>
        <td>${Number(t.estimated_points)} pts</td>
        <td>${Number(t.total_minutes)} min</td>
      </tr>`;
  }).join('');
}

async function loadTickets() {
  const includeClosed = document.getElementById('showClosed').checked;
  const queue = document.getElementById('filterQueue').value;
  const status = document.getElementById('filterStatus').value;

  const params = new URLSearchParams({ include_closed: String(includeClosed) });
  if (queue) params.set('queue', queue);
  if (status) params.set('status', status);

  const res = await fetch(`/?api=/tickets&${params.toString()}`);
  const data = await res.json().catch(() => []);
  if (!res.ok) {
    if (res.status === 401) {
      await checkSession();
      return;
    }
    showError(`Error al consultar tickets [${data.failed_step || 'api'}]: ${data.detail || 'Error'}`);
    return;
  }

  allTickets = Array.isArray(data) ? data : [];
  updateDashboardKPIs(allTickets);
  renderTicketsTable();

  if (selectedTicketCode) {
    await selectTicket(selectedTicketCode, false);
  }
}

async function selectTicket(code, switchTabToBitacora = false) {
  selectedTicketCode = code;
  renderTicketsTable();
  showError(null);

  const [detailRes, bitacoraRes] = await Promise.all([
    fetch(`/?api=/tickets/${encodeURIComponent(code)}`),
    fetch(`/?api=/tickets/${encodeURIComponent(code)}/bitacora`)
  ]);

  if (!detailRes.ok) {
    const err = await detailRes.json().catch(() => ({}));
    showError(`No se pudo abrir el expediente [${err.failed_step || 'acceso'}]: ${err.detail || 'Error'}`);
    return;
  }

  const detail = await detailRes.json();
  const bitacora = bitacoraRes.ok ? await bitacoraRes.json() : { uri: detail.bitacora_uri, content: '' };

  document.getElementById('inspectorEmpty').style.display = 'none';
  document.getElementById('inspectorContent').style.display = 'block';

  document.getElementById('detailCode').textContent = detail.ticket_code;
  document.getElementById('detailStatusBadge').textContent = detail.status_name;
  const prioBadge = document.getElementById('detailPrioBadge');
  prioBadge.textContent = detail.priority_name;
  prioBadge.className = `badge prio-${detail.priority_name}`;
  document.getElementById('detailTitle').textContent = detail.title;

  document.getElementById('detailMetaBar').textContent =
    `Área: ${detail.queue_name} · Responsable: ${detail.assignee_display_name} (${detail.assignee_username}) · Esfuerzo: ${detail.estimated_points} pts · Tiempo acumulado: ${detail.total_minutes} min`;

  const quickActions = document.getElementById('quickStatusActions');
  quickActions.innerHTML = '';
  if (detail.status_name !== 'IN_PROGRESS' && !detail.is_closed) {
    quickActions.innerHTML += `<button type="button" class="secondary" data-quick-status="IN_PROGRESS">Iniciar Foco</button> `;
  }
  if (!detail.is_closed) {
    quickActions.innerHTML += `<button type="button" class="secondary" data-quick-status="RESOLVED">Resolver</button>`;
  }

  document.getElementById('manageStatusSelect').value = detail.status_name;
  if (detail.assignee_uuid) {
    document.getElementById('delegateUserSelect').value = detail.assignee_uuid;
  }

  document.getElementById('bitacoraPathLabel').textContent = bitacora.uri || detail.bitacora_uri || '';
  document.getElementById('bitacoraEditor').value = bitacora.content || '';
  document.getElementById('bitacoraPreview').innerHTML = renderMarkdownPreview(bitacora.content || '');

  const workLogs = Array.isArray(detail.work_logs) ? detail.work_logs : [];
  document.getElementById('workLogsContainer').innerHTML = workLogs.length
    ? workLogs.map(w => `
        <div class="log-item">
          <strong>${w.duration_minutes != null ? `${w.duration_minutes} min` : 'En curso'}</strong>
          · Inicio: ${escapeHtml(w.started_at)}
          <div>${escapeHtml(w.notes || '')}</div>
        </div>`).join('')
    : '<div class="subtitle">Sin sesiones registradas.</div>';

  const auditLogs = Array.isArray(detail.audit_logs) ? detail.audit_logs : [];
  document.getElementById('auditLogsContainer').innerHTML = auditLogs.length
    ? auditLogs.map(a => `
        <div class="log-item">
          <strong>${escapeHtml(a.action)}</strong> por <code>${escapeHtml(a.actor)}</code>
          <span class="subtitle">(${escapeHtml(a.created_at)})</span>
          <div><code>${escapeHtml(JSON.stringify(a.new_value || {}))}</code></div>
        </div>`).join('')
    : '<div class="subtitle">Sin eventos de auditoría.</div>';

  if (switchTabToBitacora) {
    activateTab('tabBitacora');
  }
}

async function saveBitacora() {
  if (!selectedTicketCode) return;
  showError(null);
  const content = document.getElementById('bitacoraEditor').value;
  const res = await fetch(`/?api=/tickets/${encodeURIComponent(selectedTicketCode)}/bitacora`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content })
  });
  if (res.ok) {
    document.getElementById('bitacoraPreview').innerHTML = renderMarkdownPreview(content);
    showNotice(`Bitácora ${selectedTicketCode}.md guardada y auditada.`);
    await selectTicket(selectedTicketCode, false);
  } else {
    const err = await res.json().catch(() => ({}));
    showError(`Error al guardar bitácora [${err.failed_step || 'bitacora'}]: ${err.detail || 'Error'}`);
  }
}

async function createTicket(e) {
  e.preventDefault();
  showError(null);
  const assigneeVal = document.getElementById('newTicketAssignee').value;
  const payload = {
    title: document.getElementById('title').value,
    description: document.getElementById('description').value,
    queue_slug: document.getElementById('queue_slug').value,
    priority_name: document.getElementById('priority_name').value,
    estimated_points: parseInt(document.getElementById('estimated_points').value, 10),
    channel: 'WEB_UI'
  };
  if (assigneeVal) {
    payload.assignee_uuid = assigneeVal;
  }

  const res = await fetch('/?api=/tickets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (res.ok) {
    const created = await res.json();
    document.getElementById('ticketForm').reset();
    document.getElementById('modalNewTicket').style.display = 'none';
    showNotice(`Ticket ${created.ticket_code} creado.`);
    await loadTickets();
    await selectTicket(created.ticket_code, true);
  } else {
    const err = await res.json().catch(() => ({}));
    showError(`Transacción revertida en paso [${err.failed_step || 'validación'}]: ${err.detail || 'Error'}`);
  }
}

async function changeStatus(statusName, notes = null) {
  if (!selectedTicketCode) return;
  showError(null);
  const res = await fetch(`/?api=/tickets/${encodeURIComponent(selectedTicketCode)}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status_name: statusName, notes })
  });
  if (res.ok) {
    showNotice(`Estado de ${selectedTicketCode} actualizado a ${statusName}.`);
    await loadTickets();
  } else {
    const err = await res.json().catch(() => ({}));
    showError(`Transacción revertida en paso [${err.failed_step || 'estado'}]: ${err.detail || 'Error'}`);
  }
}

async function delegateTicket(e) {
  e.preventDefault();
  if (!selectedTicketCode) return;
  showError(null);
  const targetUuid = document.getElementById('delegateUserSelect').value;
  const notes = document.getElementById('delegateNotes').value;

  const res = await fetch(`/?api=/tickets/${encodeURIComponent(selectedTicketCode)}/assign`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_user_uuid: targetUuid, notes })
  });
  if (res.ok) {
    const data = await res.json();
    document.getElementById('delegateNotes').value = '';
    showNotice(`Ticket ${selectedTicketCode} delegado a ${data.new_assignee_display_name}.`);
    await loadTickets();
  } else {
    const err = await res.json().catch(() => ({}));
    showError(`Delegación rechazada en paso [${err.failed_step || 'jerarquía'}]: ${err.detail || 'Error'}`);
  }
}

async function addWorkLog(e) {
  e.preventDefault();
  if (!selectedTicketCode) return;
  showError(null);
  const notes = document.getElementById('workLogNotes').value;
  const res = await fetch(`/?api=/tickets/${encodeURIComponent(selectedTicketCode)}/work-logs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ notes })
  });
  if (res.ok) {
    document.getElementById('workLogNotes').value = '';
    showNotice(`Sesión registrada en ${selectedTicketCode}.`);
    await loadTickets();
  } else {
    const err = await res.json().catch(() => ({}));
    showError(`Error al registrar tiempo [${err.failed_step || 'work_log'}]: ${err.detail || 'Error'}`);
  }
}

function activateTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabId);
  });
  document.querySelectorAll('.tab-pane').forEach(pane => {
    pane.style.display = pane.id === tabId ? 'block' : 'none';
  });
}

document.getElementById('loginForm').addEventListener('submit', handleLogin);
document.getElementById('btnLogout').addEventListener('click', handleLogout);

document.getElementById('btnOpenNewTicket').addEventListener('click', () => {
  document.getElementById('modalNewTicket').style.display = 'flex';
});
document.getElementById('btnCloseNewTicket').addEventListener('click', () => {
  document.getElementById('modalNewTicket').style.display = 'none';
});
document.getElementById('ticketForm').addEventListener('submit', createTicket);

document.getElementById('filterSearch').addEventListener('input', renderTicketsTable);
document.getElementById('filterQueue').addEventListener('change', loadTickets);
document.getElementById('filterStatus').addEventListener('change', loadTickets);
document.getElementById('showClosed').addEventListener('change', loadTickets);

document.getElementById('ticketsTableBody').addEventListener('click', (e) => {
  const row = e.target.closest('tr[data-ticket-code]');
  if (row) {
    selectTicket(row.dataset.ticketCode, false);
  }
});

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => activateTab(btn.dataset.tab));
});

document.getElementById('btnMdEditMode').addEventListener('click', () => {
  document.getElementById('btnMdEditMode').classList.add('active');
  document.getElementById('btnMdPreviewMode').classList.remove('active');
  document.getElementById('bitacoraEditor').style.display = 'block';
  document.getElementById('bitacoraPreview').style.display = 'none';
});

document.getElementById('btnMdPreviewMode').addEventListener('click', () => {
  document.getElementById('btnMdPreviewMode').classList.add('active');
  document.getElementById('btnMdEditMode').classList.remove('active');
  document.getElementById('bitacoraPreview').innerHTML = renderMarkdownPreview(document.getElementById('bitacoraEditor').value);
  document.getElementById('bitacoraEditor').style.display = 'none';
  document.getElementById('bitacoraPreview').style.display = 'block';
});

document.getElementById('btnSaveBitacora').addEventListener('click', saveBitacora);

document.getElementById('quickStatusActions').addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-quick-status]');
  if (btn) {
    changeStatus(btn.dataset.quickStatus);
  }
});

document.getElementById('formChangeStatus').addEventListener('submit', (e) => {
  e.preventDefault();
  changeStatus(
    document.getElementById('manageStatusSelect').value,
    document.getElementById('manageStatusNotes').value || null
  );
  document.getElementById('manageStatusNotes').value = '';
});

document.getElementById('formDelegateTicket').addEventListener('submit', delegateTicket);
document.getElementById('formAddWorkLog').addEventListener('submit', addWorkLog);

checkSession();
