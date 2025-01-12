#!/bin/bash
if git pull; then
    echo -e "\e[1;32m PULL complete \e[0m"
else
    echo -e "\e[1;31m PULL failed \e[0m"
    exit;
fi


if  docker compose -f docker-compose.prod.yml build --push; then
    echo -e "\e[1;32m Docker images BUILD SUCCESS \e[0m"
else
    echo -e "\e[1;31m Docker images BUILD FAILED \e[0m"
    exit;
fi

if  docker stack deploy --compose-file docker-compose.prod.yml rbzk_pro; then
    echo -e "\e[1;32m Stack UPDATE SUCCESS \e[0m"
else
    echo -e "\e[1;31m STACK UPDATE FAILED \e[0m"
    exit;
fi



