FROM oittaa/imagemagick:7.1.0-51 as base

ARG DEBIAN_FRONTEND=noninteractive

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True
ENV APP_HOME /app
ENV GUNICORN_WORKERS 8
ENV GUNICORN_THREADS 1

RUN apt-get -y update && \
    apt-get -y install python3-pip && \
    python3 -m pip install --no-cache-dir --upgrade pip && \
    apt-get remove --autoremove --purge -y gcc build-essential '*-dev' && \
    rm -rf /var/lib/apt/lists/*

FROM base as src
WORKDIR $APP_HOME
COPY main.py requirements.txt ./
COPY static/ ./static/
COPY templates/ ./templates/
RUN pip3 install --no-cache-dir -r requirements.txt

FROM src as test
COPY test.py test.sh requirements-dev.txt ./
RUN magick -list format && \
    ./test.sh

FROM src as prod
COPY --from=test ${APP_HOME}/coverage.xml .
ENTRYPOINT []
CMD exec gunicorn --bind :$PORT --workers $GUNICORN_WORKERS --threads $GUNICORN_THREADS --timeout 0 main:app
