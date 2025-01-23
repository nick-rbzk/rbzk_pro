FROM nginx:1.23-alpine

RUN apt-get install bash
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d
COPY certs/rbzk_pro.crt /etc/nginx/ssl/
COPY certs/rbzk_pro.key /etc/nginx/ssl/
