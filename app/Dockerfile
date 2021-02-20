FROM debian:buster-slim as base

ARG IM_VERSION=7.0.10-62
ARG LIB_HEIF_VERSION=v1.11.0
ARG LIB_AOM_VERSION=v2.0.2
ARG IM_GIT=https://github.com/ImageMagick/ImageMagick.git
ARG LIB_HEIF_GIT=https://github.com/strukturag/libheif.git
ARG LIB_AOM_GIT=https://aomedia.googlesource.com/aom
ARG BUILD_DIR=/build

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True
ENV APP_HOME /app
ENV GUNICORN_WORKERS 8
ENV GUNICORN_THREADS 1

WORKDIR $BUILD_DIR
COPY requirements.txt git-latest-tag.sh ./
RUN apt-get -y update && \
    apt-get install -y git make gcc pkg-config autoconf g++ python3-pip \
    # libaom
    yasm cmake \
    # libheif
    libde265-0 libde265-dev libjpeg62-turbo libjpeg62-turbo-dev x265 libx265-dev libtool \
    # IM
    libpng16-16 libpng-dev libjpeg62-turbo libjpeg62-turbo-dev libwebp6 libwebp-dev libgomp1 libwebpmux3 libwebpdemux2 ghostscript libxml2-dev libxml2-utils && \
    # The latest Git tags
    ./git-latest-tag.sh ${LIB_AOM_GIT} ${LIB_AOM_VERSION} && \
    ./git-latest-tag.sh ${LIB_HEIF_GIT} ${LIB_HEIF_VERSION} && \
    ./git-latest-tag.sh ${IM_GIT} ${IM_VERSION} && \
    # Building libaom
    git clone --branch ${LIB_AOM_VERSION} --depth 1 --shallow-submodules --recurse-submodules ${LIB_AOM_GIT} && \
    mkdir build_aom && \
    cd build_aom && \
    cmake ../aom/ -DENABLE_TESTS=0 -DBUILD_SHARED_LIBS=1 && make && make install && \
    ldconfig /usr/local/lib && \
    cd .. && \
    # Building libheif
    git clone --branch ${LIB_HEIF_VERSION} --depth 1 --shallow-submodules --recurse-submodules ${LIB_HEIF_GIT} && \
    cd libheif && \
    ./autogen.sh && ./configure && make && make install &&  \
    ldconfig /usr/local/lib && \
    cd .. && \
    # Building ImageMagick
    git clone --branch ${IM_VERSION} --depth 1 --shallow-submodules --recurse-submodules ${IM_GIT} && \
    cd ImageMagick && \
    ./configure --without-magick-plus-plus --disable-docs --disable-static && \
    make && make install && \
    ldconfig /usr/local/lib && \
    cd .. && \
    # Python packages
    python3 -m pip install --upgrade pip && \
    pip3 install -r requirements.txt && \
    # Cleanup
    apt-get remove --autoremove --purge -y gcc make cmake g++ yasm git autoconf pkg-config build-essential '*-dev' && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf $BUILD_DIR

FROM base as src
WORKDIR $APP_HOME
COPY main.py ./
COPY static/ ./static/
COPY templates/ ./templates/

FROM src as test
COPY test.py coverage.sh ./
RUN pip3 install coverage
RUN convert identify -list format && \
    ./coverage.sh

FROM src as prod
COPY --from=test ${APP_HOME}/coverage.xml .
CMD exec gunicorn --bind :$PORT --workers $GUNICORN_WORKERS --threads $GUNICORN_THREADS --timeout 0 main:app
