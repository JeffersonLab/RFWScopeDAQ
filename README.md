# RFWScopeDAQ
Application for downloading and storing RF Waveforms from C100 FCCs.  This projects relies on python v3.11+.

This application is intended to be deployed to CSUE.

## Documentation
Documentation is provided in the docs folder.

## Quick Start Guide
Clone the repo and install the application using pip.  You man want to use a virtual environment.  You may optionally
start the docker containers before running the application (`docker compose up`).  Then run the application using the
appropriate launcher script.

**Linux:**
```bash
git clone https://github.com/JeffersonLab/RFWScopeDAQ
cd RFWScopeDAQ
python3.11 -m venv venv
. venv/bin/activate
pip install .[dev]
bin/RFWScopeDAQ.bash -h
```

**Windows:**
```bash
git clone https://github.com/JeffersonLab/RFWScopeDAQ
cd RFWScopeDAQ
python3.11 -m venv venv
. venv/bin/activate
pip install .[dev]
bin\RFWScopeDAQ.ps1 -h
```

 ## Developer Quick Start Guide
Download the repo, create a virtual environment using pythong 3.11+, and install the package in editable mode with 
development dependencies.  Then develop using your preferred IDE, etc..  This is very similar to the above, except that 
the package is installed in editable mode.

*Linux*
```bash
git clone https://github.com/JeffersonLab/RFWScopeDAQ
cd RFWScopeDAQ
python3.11 -m venv venv
venv/bin/activate
pip install -e .[dev]
```

*Windows*
```bash
git clone https://github.com/JeffersonLab/RFWScopeDAQ
cd RFWScopeDAQ
\path\to\python3 -m venv venv
venv\Scripts\activate.ps1
pip install -e .[dev]
```

To start the provided containers:
```
docker compose up
```

### Testing
This application only has limited unit tests and should be tested using interactive command line.  The bundled softIOC
supports tests against the R1M (1L22) zone.  Other zones are unsupported. 

| Test Type          | Command                                  |
|--------------------|------------------------------------------|
| Unit               | `pytest test/unit`                       |

Useful CLI tests are:
- Test file workflow: `bin\RFWScopeDAQ.ps1 -z R1M -t 0.25 -o file -d dist -e your@email.com -f .\cfg.yaml`
- Test database workflow: `bin\RFWScopeDAQ.ps1 -z R1M -t 0.25 -o db -e your@email.com -f .\cfg.yaml`
- Test single cavity file: `bin\RFWScopeDAQ.ps1 -c R1M1 -t 0.25 -o file -d dist -e your@email.com -f .\cfg.yaml`
- Test single cavity database: `bin\RFWScopeDAQ.ps1 -c R1M1 -t 0.25 -o db -e your@email.com -f .\cfg.yaml`


### Documentation
Basic documentation is provided in the docs folder.

### Release
Releases are generated automatically when the VERSION file recieves a commit on the main branch.  Artifcats (packages) are not deployed to PyPI automatically as this is intended as a limited use application.  Build artifacts are automatically attached to the releases when generated along with the python dependency information for the build (requirements.txt).

## See Also
- [rfscopedb-container](https://github.com/JeffersonLab/rfscopedb-container)
