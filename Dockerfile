FROM debian:buster-slim

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True
ENV APP_HOME /app

ARG IM_VERSION=7.0.10-58
ARG LIB_HEIF_VERSION=1.10.0
ARG LIB_AOM_VERSION=2.0.1

# Based on https://github.com/dooman87/imagemagick-docker/blob/master/Dockerfile.buster

RUN apt-get -y update && \
    apt-get install -y git make gcc pkg-config autoconf curl g++ python3-pip \
    # libaom
    yasm cmake \
    # libheif
    libde265-0 libde265-dev libjpeg62-turbo libjpeg62-turbo-dev x265 libx265-dev libtool \
    # IM
    libpng16-16 libpng-dev libjpeg62-turbo libjpeg62-turbo-dev libwebp6 libwebp-dev libgomp1 libwebpmux3 libwebpdemux2 ghostscript libxml2-dev libxml2-utils && \
    # Building libaom
    git clone https://aomedia.googlesource.com/aom && \
    cd aom && git checkout v${LIB_AOM_VERSION} && cd .. && \
    mkdir build_aom && \
    cd build_aom && \
    cmake ../aom/ -DENABLE_TESTS=0 -DBUILD_SHARED_LIBS=1 && make && make install && \
    ldconfig /usr/local/lib && \
    cd .. && \
    rm -rf aom && \
    rm -rf build_aom && \
    # Building libheif
    curl -L https://github.com/strukturag/libheif/releases/download/v${LIB_HEIF_VERSION}/libheif-${LIB_HEIF_VERSION}.tar.gz -o libheif.tar.gz && \
    tar -xzvf libheif.tar.gz && cd libheif-${LIB_HEIF_VERSION}/ && ./autogen.sh && ./configure && make && make install && cd .. && \
    ldconfig /usr/local/lib && \
    rm -rf libheif-${LIB_HEIF_VERSION} && rm libheif.tar.gz && \
    # Building ImageMagick
    git clone https://github.com/ImageMagick/ImageMagick.git && \
    cd ImageMagick && git checkout ${IM_VERSION} && \
    ./configure --without-magick-plus-plus --disable-docs --disable-static && \
    make && make install && \
    ldconfig /usr/local/lib && \
    apt-get remove --autoremove --purge -y gcc make cmake curl g++ yasm git autoconf pkg-config libpng-dev libjpeg62-turbo-dev libwebp-dev libde265-dev libx265-dev libxml2-dev && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /ImageMagick

# Cleanup and Python app installation
WORKDIR $APP_HOME
RUN pip3 install Flask gunicorn python-magic requests google-cloud-storage coverage
COPY main.py test.py ./
COPY static/ ./static/
COPY templates/ ./templates/
RUN convert identify -list format && coverage run --source=./ test.py && coverage report -m && coverage html && mv htmlcov static/

# Run the web service on container startup. Here we use the gunicorn
# webserver, with one worker process and 8 threads.
# For environments with multiple CPU cores, increase the number of workers
# to be equal to the cores available.
CMD exec gunicorn --bind :$PORT --workers $(nproc) --threads 8 --timeout 0 main:app
