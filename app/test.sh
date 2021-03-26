#!/bin/sh
set -e
pip3 install --no-cache-dir -r requirements-dev.txt
coverage run --source=./ --omit=test.py test.py
coverage report -m
cd /
cat > .coveragerc <<EOF
[paths]
source =
    app/
    $APP_HOME
EOF
coverage combine "${APP_HOME}/.coverage"
coverage xml -o "${APP_HOME}/coverage.xml"
rm -f .coverage*
