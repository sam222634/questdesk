<?php
declare(strict_types=1);

header("Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'");
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: no-referrer');

session_start([
    'cookie_httponly' => true,
    'cookie_samesite' => 'Strict',
    'use_strict_mode' => true,
]);

$apiBase = rtrim(getenv('CORE_API_URL') ?: 'http://core-tickets:8000/api/v1', '/');

function callCoreApi(string $apiBase, string $method, string $endpoint, string $apiKey, ?string $rawBody = null): array
{
    $headers = [
        'Content-Type: application/json',
        'Accept: application/json',
        'X-API-Key: ' . $apiKey,
    ];
    $opts = [
        'http' => [
            'method' => $method,
            'header' => implode("\r\n", $headers) . "\r\n",
            'timeout' => 10,
            'ignore_errors' => true,
        ],
    ];
    if ($rawBody !== null && $rawBody !== '') {
        $opts['http']['content'] = $rawBody;
    }

    $context = stream_context_create($opts);
    $response = @file_get_contents($apiBase . $endpoint, false, $context);
    if ($response === false) {
        return [
            'status' => 502,
            'body' => json_encode([
                'ok' => false,
                'failed_step' => 'core_api_connection',
                'detail' => 'No se pudo contactar con el servicio intermediario de tickets.',
            ]),
        ];
    }

    $statusCode = 200;
    $statusLine = $http_response_header[0] ?? 'HTTP/1.1 200 OK';
    if (preg_match('#HTTP/\S+\s+(\d{3})#', $statusLine, $matches)) {
        $statusCode = (int) $matches[1];
    }

    return ['status' => $statusCode, 'body' => $response];
}

if (isset($_GET['auth'])) {
    header('Content-Type: application/json; charset=utf-8');
    $action = (string) $_GET['auth'];

    if ($action === 'status') {
        if (!empty($_SESSION['api_key']) && !empty($_SESSION['user'])) {
            echo json_encode(['authenticated' => true, 'user' => $_SESSION['user']]);
        } else {
            echo json_encode(['authenticated' => false]);
        }
        exit;
    }

    if ($action === 'logout' && ($_SERVER['REQUEST_METHOD'] ?? '') === 'POST') {
        $_SESSION = [];
        session_destroy();
        echo json_encode(['ok' => true]);
        exit;
    }

    if ($action === 'login' && ($_SERVER['REQUEST_METHOD'] ?? '') === 'POST') {
        $payload = json_decode((string) file_get_contents('php://input'), true);
        $candidateKey = trim((string) ($payload['api_key'] ?? ''));
        if ($candidateKey === '') {
            http_response_code(400);
            echo json_encode(['ok' => false, 'detail' => 'Ingresa una clave de acceso válida.']);
            exit;
        }

        $res = callCoreApi($apiBase, 'GET', '/auth/me', $candidateKey);
        http_response_code($res['status']);
        if ($res['status'] === 200) {
            $userData = json_decode($res['body'], true);
            session_regenerate_id(true);
            $_SESSION['api_key'] = $candidateKey;
            $_SESSION['user'] = $userData;
            echo json_encode(['ok' => true, 'user' => $userData]);
        } else {
            echo $res['body'];
        }
        exit;
    }

    http_response_code(400);
    echo json_encode(['ok' => false, 'detail' => 'Acción de autenticación no válida.']);
    exit;
}

if (isset($_GET['api'])) {
    header('Content-Type: application/json; charset=utf-8');
    $endpoint = (string) $_GET['api'];

    if (!preg_match('#^/(auth/me|catalogs|tickets(?:/[A-Za-z0-9_-]+(?:/(?:status|assign|work-logs|bitacora))?)?)$#', $endpoint)) {
        http_response_code(400);
        echo json_encode(['ok' => false, 'failed_step' => 'web_proxy', 'detail' => 'Ruta de API no permitida.']);
        exit;
    }

    $sessionKey = $_SESSION['api_key'] ?? '';
    $headerKey = !empty($_SERVER['HTTP_X_API_KEY']) ? trim((string) $_SERVER['HTTP_X_API_KEY']) : '';
    $activeKey = $headerKey !== '' ? $headerKey : $sessionKey;

    if ($activeKey === '') {
        http_response_code(401);
        echo json_encode([
            'ok' => false,
            'failed_step' => 'session_auth',
            'detail' => 'Sesión no iniciada. Ingresa tu clave de usuario.',
        ]);
        exit;
    }

    $method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
    $queryParams = $_GET;
    unset($queryParams['api']);
    $queryString = !empty($queryParams) ? '?' . http_build_query($queryParams) : '';

    $rawBody = file_get_contents('php://input');
    $res = callCoreApi($apiBase, $method, $endpoint . $queryString, $activeKey, $rawBody !== false ? $rawBody : null);
    http_response_code($res['status']);
    echo $res['body'];
    exit;
}
?>
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>QuestDesk — Sistema de Gestión de Tickets</title>
  <link rel="stylesheet" href="/style.css" />
</head>
<body>
  <div id="loginScreen" class="login-wrapper" style="display:none;">
    <div class="login-card">
      <h2>QuestDesk</h2>
      <p class="subtitle">Control de Tickets, Delegación y Bitácoras Técnicas</p>
      <div id="loginError" class="alert" role="alert"></div>
      <form id="loginForm">
        <label for="loginApiKey">Clave de Acceso Personal (API Key)</label>
        <input type="password" id="loginApiKey" required autocomplete="current-password" placeholder="Ingresa tu credencial de usuario..." />
        <button type="submit">Iniciar Sesión</button>
      </form>
    </div>
  </div>

  <div id="appScreen" style="display:none;">
    <header class="topbar">
      <div class="brand-block">
        <h1>QuestDesk</h1>
        <span class="subtitle">Consola de Operaciones y Bitácoras</span>
      </div>
      <div class="user-bar">
        <div class="user-info">
          <span id="userDisplayName" class="user-name"></span>
          <span id="userRoleBadge" class="badge"></span>
        </div>
        <button type="button" id="btnOpenNewTicket" class="btn-primary">Nuevo Ticket</button>
        <button type="button" id="btnLogout" class="secondary">Cerrar Sesión</button>
      </div>
    </header>

    <div id="errorBox" class="alert" role="alert"></div>
    <div id="noticeBox" class="notice" role="status"></div>

    <section class="kpi-strip">
      <div class="kpi-card">
        <span class="kpi-label">Pendientes / Nuevos</span>
        <strong id="kpiNew" class="kpi-value">0</strong>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">En Progreso (Foco)</span>
        <strong id="kpiInProgress" class="kpi-value">0</strong>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">Bloqueados</span>
        <strong id="kpiBlocked" class="kpi-value">0</strong>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">Prioridad Alta / Crítica</span>
        <strong id="kpiHighPrio" class="kpi-value kpi-critical">0</strong>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">Resueltos / Cerrados</span>
        <strong id="kpiResolved" class="kpi-value">0</strong>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">Tiempo / Esfuerzo Total</span>
        <strong id="kpiEffort" class="kpi-value">0m / 0 pts</strong>
      </div>
    </section>

    <section class="toolbar card">
      <div class="filters-row">
        <div class="filter-item">
          <label for="filterSearch">Buscar por código o título</label>
          <input type="text" id="filterSearch" placeholder="Ej. INF-0001 o firewall..." />
        </div>
        <div class="filter-item">
          <label for="filterQueue">Cola / Área</label>
          <select id="filterQueue">
            <option value="">Todas las áreas</option>
          </select>
        </div>
        <div class="filter-item">
          <label for="filterStatus">Estado</label>
          <select id="filterStatus">
            <option value="">Todos los activos</option>
          </select>
        </div>
        <div class="filter-item filter-check">
          <label class="toggle-label">
            <input type="checkbox" id="showClosed" />
            Incluir resueltos y cerrados
          </label>
        </div>
      </div>
      <div id="queueDistribution" class="queue-dist"></div>
    </section>

    <main class="workspace-grid">
      <section class="card table-panel">
        <div class="panel-header">
          <h3>Bandeja de Tickets Autorizados</h3>
          <span id="ticketsCount" class="subtitle">0 registros</span>
        </div>
        <div class="table-scroll">
          <table class="tickets-table">
            <thead>
              <tr>
                <th>Código</th>
                <th>Título</th>
                <th>Área</th>
                <th>Prioridad</th>
                <th>Estado</th>
                <th>Responsable</th>
                <th>Esfuerzo</th>
                <th>Tiempo</th>
              </tr>
            </thead>
            <tbody id="ticketsTableBody">
              <tr><td colspan="8" class="subtitle">Cargando...</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="card inspector-panel" id="inspectorPanel">
        <div id="inspectorEmpty" class="inspector-empty">
          Selecciona un ticket de la tabla para abrir su expediente, delegarlo o editar su bitácora Markdown.
        </div>

        <div id="inspectorContent" style="display:none;">
          <div class="inspector-header">
            <div>
              <span id="detailCode" class="code"></span>
              <span id="detailStatusBadge" class="badge"></span>
              <span id="detailPrioBadge" class="badge"></span>
              <h3 id="detailTitle" class="detail-title"></h3>
            </div>
            <div class="quick-status-actions" id="quickStatusActions"></div>
          </div>

          <div class="detail-meta-bar" id="detailMetaBar"></div>
          <div class="notice" id="readOnlyNotice" role="status" style="display:none;">
            Solo lectura: este ticket está asignado a otro usuario. Únicamente su responsable puede modificarlo.
          </div>

          <div class="tabs-bar">
            <button type="button" class="tab-btn active" data-tab="tabBitacora">Bitácora Markdown (.md)</button>
            <button type="button" class="tab-btn" data-tab="tabManage">Estado, Delegación y Tiempo</button>
            <button type="button" class="tab-btn" data-tab="tabAudit">Trazabilidad y Auditoría</button>
          </div>

          <div id="tabBitacora" class="tab-pane active">
            <div class="md-toolbar">
              <span id="bitacoraPathLabel" class="code-path"></span>
            </div>
            <div id="bitacoraSections"></div>
          </div>

          <div id="tabManage" class="tab-pane" style="display:none;">
            <div class="manage-grid">
              <form id="formChangeStatus" class="subcard">
                <h4>Cambiar Estado del Ticket</h4>
                <label for="manageStatusSelect">Nuevo Estado</label>
                <select id="manageStatusSelect" required></select>
                <label for="manageStatusNotes">Nota de transición</label>
                <input type="text" id="manageStatusNotes" placeholder="Motivo o avance..." />
                <button type="submit">Actualizar Estado</button>
              </form>

              <form id="formDelegateTicket" class="subcard">
                <h4>Delegar / Reasignar Ticket</h4>
                <label for="delegateUserSelect">Asignar a (Subordinado / Usuario)</label>
                <select id="delegateUserSelect" required></select>
                <label for="delegateNotes">Motivo de delegación</label>
                <input type="text" id="delegateNotes" placeholder="Ej. Corresponde a especialidad de redes..." />
                <button type="submit">Delegar Ticket</button>
              </form>

              <form id="formAddWorkLog" class="subcard">
                <h4>Registrar Sesión de Trabajo</h4>
                <label for="workLogNotes">Actividad realizada</label>
                <input type="text" id="workLogNotes" required placeholder="Descripción breve del bloque trabajado..." />
                <button type="submit">Registrar Sesión</button>
              </form>
            </div>
          </div>

          <div id="tabAudit" class="tab-pane" style="display:none;">
            <h4>Sesiones de Tiempo Registradas</h4>
            <div id="workLogsContainer" class="logs-list"></div>

            <h4>Historial Inmutable de Auditoría</h4>
            <div id="auditLogsContainer" class="logs-list"></div>
          </div>
        </div>
      </section>
    </main>
  </div>

  <div id="modalNewTicket" class="modal-backdrop" style="display:none;">
    <div class="modal-card">
      <div class="panel-header">
        <h3>Crear Nuevo Ticket</h3>
        <button type="button" id="btnCloseNewTicket" class="secondary">Cerrar</button>
      </div>
      <form id="ticketForm">
        <label for="title">Título</label>
        <input type="text" id="title" required maxlength="255" placeholder="Ej. Configurar respaldo de base de datos" />

        <label for="description">Descripción inicial</label>
        <textarea id="description" rows="4" required placeholder="Contexto técnico o requerimiento..."></textarea>

        <div class="form-row-2">
          <div>
            <label for="queue_slug">Cola / Área</label>
            <select id="queue_slug"></select>
          </div>
          <div>
            <label for="priority_name">Prioridad</label>
            <select id="priority_name"></select>
          </div>
        </div>

        <div class="form-row-2">
          <div>
            <label for="estimated_points">Esfuerzo estimado (1 a 10 pts)</label>
            <input type="number" id="estimated_points" min="1" max="10" value="2" />
          </div>
          <div>
            <label for="newTicketAssignee" id="newTicketAssigneeLabel">Responsable</label>
            <select id="newTicketAssignee"></select>
          </div>
        </div>

        <button type="submit">Crear Ticket e Inicializar Bitácora .md</button>
      </form>
    </div>
  </div>

  <script src="/app.js"></script>
</body>
</html>
