#!/bin/sh
set -e
ARCH=$(uname -m)
echo ARCH $ARCH
if [ "$ARCH" != "x86_64" ]
then
    apt-get update
    apt-get install -y gcc build-essential python3-dev
fi
pip3 install --no-cache-dir -r requirements-dev.txt
if [ "$ARCH" != "x86_64" ]
then
    apt-get remove --autoremove --purge -y gcc build-essential python3-dev '*-dev'
    rm -rf /var/lib/apt/lists/*
fi
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
