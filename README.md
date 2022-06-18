# WYKOJ-JUDGE

WYKOJ Judging Backend. Written in Python.

---

## Build (on Linux only)

* Install [isolate](https://github.com/ioi/isolate)
* Clone this repository
* Install pip requirements
* If building on WSL, v2 required

```commandline
sudo apt-get install libcap-dev make gcc python3 python3-pip ocaml
cd ~/Downloads
git clone https://github.com/ioi/isolate.git
cd isolate
sudo make install
cd *whatever*
git clone https://github.com/wykoj/wykoj-judge.git
cd wykoj-judge
pip3 install -r requirements.txt
```

## Run

```commandline
python3 -m judge
```
