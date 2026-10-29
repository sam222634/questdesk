FROM php:8.3-cli-alpine

WORKDIR /var/www/html

COPY public/ ./

USER www-data

EXPOSE 8080

CMD ["php", "-S", "0.0.0.0:8080", "-t", "/var/www/html"]
