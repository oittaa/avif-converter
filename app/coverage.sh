#!/bin/sh
set -e
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
