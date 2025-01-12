#!/bin/bash
git pull;
docker compose -f docker-compose.prod.yml build --push;
docker stack deploy --compose-file docker-compose.prod.yml rbzk_pro;


