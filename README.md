# GreenEarthX Co-Work Platform

Enterprise platform for green fuel finance.

## Quick Start

### Backend (Port 8000)
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend (Port 3000)
```bash
cd frontend
npm install
npm run dev
```

### Finance Engine (Port 8001)
```bash
cd finance-engine/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

## Features

- Decision Twin certification engine
- Project finance orchestrator
- TR1-TR9 tracking
- 5-tranche drawdown management
- Covenant monitoring
