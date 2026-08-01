# WYKOJ-JUDGE

WYKOJ Judging Backend. Written in Python.

`isolate` (the sandbox used to run submissions) depends on Linux-only
kernel features (cgroups, namespaces), so this service only runs
natively on Linux. On other platforms (e.g. macOS), use the Docker
setup below.

---

## Setup

* Clone this repository
* Create `config.json` in the repo root (gitignored):

```json
{
    "TEST_CASES_GITHUB": "https://github.com/wykstemteam/wykoj-test-cases",
    "JUDGE_HOST": "http://localhost:8080",
    "SECRET_KEY": "...",
    "DB_URI": "...",
    "LICHESS_TOKEN": "..."
}
```

* Fetch the test cases submodule:

```commandline
git submodule update --init --recursive
```

Refer to [wykstemteam/wykoj](https://github.com/wykstemteam/wykoj)
for instructions to create a GitHub repo to store test cases.

## Build & run natively (Linux only)

```commandline
sudo apt-get install libcap-dev libseccomp-dev make gcc python3 python3-pip ocaml libsystemd-dev pkg-config
cd ~/Downloads
git clone https://github.com/ioi/isolate.git
cd isolate
sudo make install
cd *whatever*
pip3 install -r requirements.txt
python3 -m judge
```

If building on WSL, v2 is required.

Note to self: sometimes if WSL cannot export port 8000 to windows, just
restart entire machine.

## Build & run with Docker (macOS / other platforms)

```commandline
docker build -t wykoj-judge .
docker run -d --privileged -p 8080:8080 \
  -v "$(pwd)/config.json:/app/config.json:ro" \
  -v "$(pwd)/test_cases:/app/test_cases" \
  --name wykoj-judge wykoj-judge
```

Notes:

* `--privileged` is required — `isolate` needs to create cgroups.
* `test_cases` is bind-mounted so local changes to test cases don't
  require rebuilding the image.
* The frontend isn't dockerized, so if it's running on your host at
  `localhost:3000`, the judge container can't reach it via `localhost`
  (that resolves to the container itself). Point `FRONTEND_URL` in
  `judge/constants.py` at `http://host.docker.internal:3000` instead
  when testing locally with Docker.
* Rebuild the image (`docker build ...`) after pulling code changes,
  since the app code is baked into the image rather than bind-mounted.
