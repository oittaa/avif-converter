FROM dpokidov/imagemagick:latest-buster

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True
ENV APP_HOME /app
ENV GUNICORN_WORKERS 8
ENV GUNICORN_THREADS 1

RUN apt-get -y update && \
    apt-get install -y python3-pip && \
    pip3 install Flask coverage flask-talisman google-cloud-storage gunicorn requests && \
    apt-get remove --autoremove --purge -y build-essential '*-dev' && \
    rm -rf /var/lib/apt/lists/*

# Python app installation
WORKDIR $APP_HOME
COPY main.py test.py ./
COPY static/ ./static/
COPY templates/ ./templates/
RUN convert identify -list format && coverage run --source=./ test.py && coverage report -m

# Run the web service on container startup. Here we use the gunicorn
# webserver, with one worker process and 8 threads.
# For environments with multiple CPU cores, increase the number of workers
# to be equal to the cores available.
ENTRYPOINT []
CMD exec gunicorn --bind :$PORT --workers $GUNICORN_WORKERS --threads $GUNICORN_THREADS --timeout 0 main:app
