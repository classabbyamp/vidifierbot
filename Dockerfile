FROM ghcr.io/void-linux/void-linux:latest-mini-x86_64
LABEL org.opencontainers.image.source https://github.com/classabbyamp/vidifierbot

COPY . /app
WORKDIR /app

ARG REPOSITORY=https://repo-ci.voidlinux.org/current
ARG PKGS="ffmpeg python3 python3-pip"
ARG UID 1000
ARG GID 1000

RUN \
    echo "**** update system ****" && \
    xbps-install -Muy -R ${REPOSITORY} xbps && \
    xbps-install -Muy -R ${REPOSITORY} && \
    echo "**** install system packages ****" && \
    xbps-install -My -R ${REPOSITORY} ${PKGS} && \
    echo "**** install pip packages ****" && \
    pip3 install -U pip setuptools wheel && \
    pip3 install -r requirements.txt && \
    echo "**** clean up ****" && \
    rm -rf \
        /root/.cache \
        /tmp/* \
        /var/cache/xbps/* && \
    mkdir tmp && \
    chown 1000:1000 tmp

ENV PYTHON_BIN python3
ENV PYTHONUNBUFFERED 1

USER $UID:$GID

CMD ["/bin/sh", "run.sh", "--pass-errors", "--no-botenv", "--upgrade"]
