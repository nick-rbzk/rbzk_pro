#!/bin/bash

set -o errexit
set -o nounset

celery -A rbzk worker -l INFO -Q low_priority,default