# WYKOJ-JUDGE

WYKOJ Judging Backend. Written in Python.

---

## Build (on Linux only)

* Install [isolate](https://github.com/ioi/isolate)  
* Clone this repository  
* Install pip requirements
* If building on WSL, v2 required T__T

```commandline
sudo apt-get install libcap-dev asciidoc-base make gcc uvicorn
cd ~/Downloads
git clone https://github.com/ioi/isolate.git
cd isolate
make
sudo make install
cd *whatever*
git clone https://github.com/wykoj/wykoj-judge.git
cd wykoj-judge
pip3 install -r requirements.txt
```

## Run

```commandline
uvicorn main:app
```