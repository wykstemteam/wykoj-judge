FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    libcap-dev libseccomp-dev make gcc git python3 python3-pip ocaml libsystemd-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/ioi/isolate.git /tmp/isolate \
    && cd /tmp/isolate && make install \
    && rm -rf /tmp/isolate

# isolate 2.6+ requires a system user "isolate" with a subordinate
# uid/gid range configured, used for its restricted user namespaces.
RUN useradd -M isolate \
    && usermod --add-subuids 200000-265535 --add-subgids 200000-265535 isolate

WORKDIR /app
COPY requirements.txt .
RUN pip3 install -r requirements.txt

# Since /app is typically bind-mounted from the host at runtime (owned
# by the host user, not the container's root), git refuses to operate
# on it ("detected dubious ownership") unless explicitly trusted.
RUN git config --global --add safe.directory /app \
    && git config --global --add safe.directory /app/test_cases

COPY . .

CMD ["python3", "-m", "judge"]
