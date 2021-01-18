FROM debian:buster-slim

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True
ENV APP_HOME /app
ENV BUILD_DIR /tmp/build
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR $BUILD_DIR
RUN apt-get update \
  && apt-get install -y build-essential libjpeg-dev libpng-dev libssl-dev ninja-build cmake pkg-config git curl python3-pip libmagic1 imagemagick

# Modified from https://github.com/AOMediaCodec/libavif/blob/master/tests/docker/build.sh

# NASM
RUN curl -L https://www.nasm.us/pub/nasm/releasebuilds/2.15.05/nasm-2.15.05.tar.gz | tar xvz \
  && cd nasm-2.15.05 \
  && ./configure --prefix=/usr \
  && make -j2 \
  && make install \
  && nasm --version \
  && rm -rf ../nasm-2.15.05

# Rust env and rav1e
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
  && cargo install cargo-c \
  && git clone -b 0.4 --depth 1 https://github.com/xiph/rav1e.git \
  && cd rav1e \
  && RUSTFLAGS="-C target-feature=+avx2,+fma" cargo cinstall --prefix=/usr --release \
  && rm -rf ../rav1e $HOME/.cargo $HOME/.rustup

# libavif
RUN git clone --depth 1 https://github.com/AOMediaCodec/libavif.git \
  && cd libavif \
  && mkdir build \
  && cd build \
  && cmake -G Ninja -DCMAKE_INSTALL_PREFIX=/usr -DAVIF_CODEC_RAV1E=1 -DAVIF_BUILD_APPS=1 .. \
  && ninja install \
  && rm -rf ../../libavif

# Cleanup and Python app installation
WORKDIR $APP_HOME
RUN apt-get remove --autoremove --purge -y build-essential libjpeg-dev libpng-dev libssl-dev ninja-build cmake pkg-config git curl \
  && rm -rf /var/lib/apt/lists/* \
  && rm -rf $BUILD_DIR
RUN pip3 install Flask gunicorn python-magic requests google-cloud-storage coverage
COPY main.py test.py ./
COPY static/ ./static/
COPY templates/ ./templates/
RUN coverage run --source=./ test.py && coverage report -m && coverage html && mv htmlcov static/

# Run the web service on container startup. Here we use the gunicorn
# webserver, with one worker process and 8 threads.
# For environments with multiple CPU cores, increase the number of workers
# to be equal to the cores available.
CMD exec gunicorn --bind :$PORT --workers $(nproc) --threads 8 --timeout 0 main:app
