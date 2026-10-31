FROM php:8.4-cli-alpine

# Aplicar todos los parches de seguridad más recientes de Alpine y PHP
RUN apk update && apk upgrade --no-cache

WORKDIR /var/www/html

COPY public/ ./

USER www-data

EXPOSE 8080

CMD ["php", "-S", "0.0.0.0:8080", "-t", "/var/www/html"]
