#!/bin/bash

set -o errexit
set -o nounset

celery -A rbzk worker -l INFO
