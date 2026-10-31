FROM php:8.5-cli-alpine

# Aplicar parches y verificar que la versión de PHP incluya el parche contra CVE-2026-109618 / CVE-2026-109619 (>= 8.5.12 o >= 8.4.27)
RUN apk update && apk upgrade --no-cache \
    && php -r 'if (version_compare(PHP_VERSION, "8.5.12", "<") && version_compare(PHP_VERSION, "8.4.27", "<")) { fwrite(STDERR, "ERROR: Versión de PHP vulnerable a PHP2Shell: " . PHP_VERSION . PHP_EOL); exit(1); }'

WORKDIR /var/www/html

COPY public/ ./

USER www-data

EXPOSE 8080

CMD ["php", "-S", "0.0.0.0:8080", "-t", "/var/www/html"]
