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
    "JUDGE_HOST": "http://wykoj-judge:8080",
    "SECRET_KEY": "...",
    "DB_URI": "...",
    "LICHESS_TOKEN": "...",
    "GITHUB_TOKEN": "..."
}
```

`GITHUB_TOKEN` is used to authenticate the `git pull` in `update_test_cases()`/`/pull_test_cases`.
Use a fine-grained GitHub PAT with read-only access scoped to just that
repo. Omit it if you already have working GitHub credentials (SSH key,
credential helper, etc.) in whatever environment runs the judge.

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

```bash
docker build -t wykoj-judge .
docker network create wykoj-net
docker run -d --privileged -p 8080:8080 \
  --network wykoj-net \
  -v "$(pwd):/app" \
  --name wykoj-judge wykoj-judge
```

Notes:

* `--privileged` is required — `isolate` needs to create cgroups.
* Bind-mount the whole repo (rather than just `config.json`/`test_cases`)
  so `.git` is present for both the top-level repo and the `test_cases`
  submodule. `update_test_cases()` and the `/pull_test_cases` webhook
  run `git submodule foreach git pull origin master` — without `.git`
  in the container, this fails silently (`fatal: not a git repository`)
  and test cases never actually update, regardless of how often the
  webhook fires.
* This also means code changes take effect without rebuilding the
  image — only rebuild when `requirements.txt` or the `Dockerfile`
  itself changes.
* If the frontend is also containerized, put it on the same
  `--network` as the judge and have it reach the judge via the judge
  container's `--name` (e.g. `http://wykoj-judge:8080`), not
  `localhost`. If the frontend runs natively on the host instead,
  point it at `http://host.docker.internal:8080`.
