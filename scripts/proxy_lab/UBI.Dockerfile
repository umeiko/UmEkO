ARG UBI_BASE=registry.access.redhat.com/ubi9/ubi:latest
FROM ${UBI_BASE}

# Only the disposable lab image is changed; no host package or daemon changes.
RUN dnf -y --setopt=install_weak_deps=False install python3.11 python3.11-pip nginx \
    && dnf clean all
RUN python3.11 -m venv /opt/lab-venv
ENV PATH="/opt/lab-venv/bin:${PATH}" \
    PYTHONPATH="/app:/lab" \
    PYTHONUNBUFFERED=1 \
    UMEKO_LAB_RUNTIME=/runtime \
    UMEKO_LAB_MODEL_URL=https://model:19443/v1
COPY docker-requirements.txt /opt/docker-requirements.txt
RUN python -m pip install --no-cache-dir -r /opt/docker-requirements.txt
WORKDIR /app
