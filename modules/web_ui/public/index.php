<?php
declare(strict_types=1);

/**
 * QuestDesk - Módulo Web UI (PHP 8.3)
 * Sin acceso directo a base de datos ni credenciales SQL.
 * Se comunica exclusivamente con el intermediario Python mediante HTTP interno.
 */

$apiBase = rtrim(getenv('CORE_API_URL') ?: 'http://core-tickets:8000/api/v1', '/');

// Proxy interno para peticiones AJAX desde el navegador hacia el intermediario Python
if (isset($_GET['api'])) {
    header('Content-Type: application/json; charset=utf-8');
    $endpoint = (string) $_GET['api'];

    // Lista blanca estricta de rutas permitidas hacia el intermediario
    if (!preg_match('#^/(tickets(?:/[A-Za-z0-9_-]+/status)?|catalogs)$#', $endpoint)) {
        http_response_code(400);
        echo json_encode(['ok' => false, 'failed_step' => 'web_proxy', 'detail' => 'Ruta de API no permitida.']);
        exit;
    }

    $method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
    $queryParams = $_GET;
    unset($queryParams['api']);
    $queryString = !empty($queryParams) ? '?' . http_build_query($queryParams) : '';

    $targetUrl = $apiBase . $endpoint . $queryString;
    $rawBody = file_get_contents('php://input');

    $opts = [
        'http' => [
            'method' => $method,
            'header' => "Content-Type: application/json\r\nAccept: application/json\r\n",
            'timeout' => 10,
            'ignore_errors' => true,
        ],
    ];
    if ($rawBody !== false && $rawBody !== '') {
        $opts['http']['content'] = $rawBody;
    }

    $context = stream_context_create($opts);
    $response = @file_get_contents($targetUrl, false, $context);

    if ($response === false) {
        http_response_code(502);
        echo json_encode([
            'ok' => false,
            'failed_step' => 'core_api_connection',
            'detail' => 'No se pudo contactar con el servicio intermediario de tickets.',
        ]);
        exit;
    }

    $statusLine = $http_response_header[0] ?? 'HTTP/1.1 200 OK';
    if (preg_match('#HTTP/\S+\s+(\d{3})#', $statusLine, $matches)) {
        http_response_code((int) $matches[1]);
    }
    echo $response;
    exit;
}
?>
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>QuestDesk — Panel de Tickets</title>
  <link rel="stylesheet" href="/style.css" />
</head>
<body>
  <header>
    <div>
      <h1>QuestDesk — Panel de Gestión de Tickets</h1>
      <div class="subtitle">Frontend PHP Aislado &rarr; Intermediario Python &rarr; PostgreSQL</div>
    </div>
    <div class="actions">
      <label class="toggle-label">
        <input type="checkbox" id="showClosed" />
        Ver resueltos
      </label>
    </div>
  </header>

  <div id="errorBox" class="alert" role="alert"></div>

  <main class="layout">
    <section class="card">
      <h3>Nuevo Ticket</h3>
      <form id="ticketForm">
        <label for="title">Título</label>
        <input type="text" id="title" required maxlength="255" placeholder="Ej. Configurar respaldo de base de datos" />

        <label for="description">Descripción inicial</label>
        <textarea id="description" rows="4" required placeholder="Contexto o requerimiento..."></textarea>

        <label for="queue_slug">Cola / Área</label>
        <select id="queue_slug">
          <option value="general">General (GEN)</option>
          <option value="infra">Infraestructura (INF)</option>
          <option value="dev">Desarrollo (DEV)</option>
          <option value="personal">Personal (PER)</option>
        </select>

        <label for="priority_name">Prioridad</label>
        <select id="priority_name">
          <option value="LOW">Baja (LOW)</option>
          <option value="MEDIUM" selected>Media (MEDIUM)</option>
          <option value="HIGH">Alta (HIGH)</option>
          <option value="CRITICAL">Crítica (CRITICAL)</option>
        </select>

        <label for="estimated_points">Esfuerzo estimado (1 a 10 pts)</label>
        <input type="number" id="estimated_points" min="1" max="10" value="2" />

        <button type="submit">Crear Ticket + Bitácora .md</button>
      </form>
    </section>

    <section class="card">
      <h3>Cola de Tickets</h3>
      <div id="ticketsList" class="tickets-grid">Cargando...</div>
    </section>
  </main>

  <script src="/app.js"></script>
</body>
</html>
