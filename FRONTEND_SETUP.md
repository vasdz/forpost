# Forpost Dispatcher Console — Setup & Deployment Guide

## Overview

The Forpost platform now includes a complete **dispatcher web console** for real-time risk monitoring of critical municipal infrastructure (КИИ).

### Stack
- **Frontend**: React 18 + TypeScript + Vite
- **Styling**: Tailwind CSS (dark/navy industrial theme)
- **State Management**: TanStack Query + React Context (ABAC)
- **Routing**: react-router-dom
- **Backend Integration**: Axios + typed API client
- **UI Components**: Lucide icons, custom Badge/Card/SectionHeader

---

## Quick Start

### Prerequisites
- **Python 3.12+** with virtual environment (`c:\Users\alexl\PycharmProjects\forpost\.venv`)
- **Node.js 18+** and npm 9+ (installed)
- **Git** (already in use)

### Step 1: Start Backend (FastAPI)

```powershell
cd c:\Users\alexl\PycharmProjects\forpost
.\.venv\Scripts\python.exe -m uvicorn forpost_api.main:app `
  --host 127.0.0.1 --port 8000 --reload
```

**Output**:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

### Step 2: Start Frontend (Vite Dev Server)

```powershell
cd c:\Users\alexl\PycharmProjects\forpost\apps\web
npm run dev -- --host 0.0.0.0
```

**Output**:
```
  ➜ Local:   http://localhost:5173/
  ➜ press h + enter to show help
```

### Step 3: Open in Browser

Navigate to: **http://localhost:5173/**

---

## Features Walkthrough

### 1. Executive Overview (Dashboard)
- **Route**: `/dashboard` (default)
- **KPIs**: Active incidents, 24h predictions, critical risks, resilience score
- **Risk Heatmap**: Color-coded by category (green/yellow/red)
- **Category Breakdown**: Sensor failure, fire risk, unauthorized access, infrastructure wear

### 2. Risk Matrix Table
- **Route**: `/risks`
- **Filtering**: By district (rek-1...rek-4) and risk category
- **Drill-Down**: Click row for details (probability, horizon, explanation)
- **ABAC**: Sidebar shows accessible districts for current role

### 3. Data Ingest Hub
- **Route**: `/ingest`
- **Drag-and-Drop**: Upload CSV/XLSX files
- **Validation**: Type check + size limit (10 MB)
- **Security**: CDR mock for formula injection / zip bomb detection

### 4. Security & Audit Console
- **Route**: `/audit`
- **WORM Verification**: Click button to check hash-chain integrity
- **ABAC Context**: Display current user role and allowed districts
- **Context Switching**: Use sidebar to simulate different user roles

---

## ABAC (Attribute-Based Access Control)

Three predefined security contexts (simulated in dev):

| Role | User ID | Districts | Permissions |
|------|---------|-----------|------------|
| Диспетчер РЭК-1 | `disp-01` | rek-1, rek-2 | VIEW_RISKS, READ_TELEMETRY |
| Диспетчер РЭК-3 | `disp-03` | rek-3 | VIEW_RISKS, READ_TELEMETRY |
| Офицер ИБ | `aud-01` | rek-1..4 | AUDIT_READ (all districts) |

**API Headers** sent with each request:
```
x-user-id: disp-01
x-role: dispatcher
x-districts: rek-1,rek-2
```

---

## Development

### Build for Production

```powershell
cd apps/web
npm run build
```

**Output**: `dist/` folder ready for deployment

### Lint Code

```powershell
npm run lint
```

**Note**: Expected warning about barrel export in `contexts/index.tsx` (false positive)

### Run Tests (Backend)

```powershell
cd c:\Users\alexl\PycharmProjects\forpost
.\.venv\Scripts\python.exe -m pytest tests/unit tests/security -q
```

**Output**: 6 passed

---

## File Structure

```
apps/web/
├── src/
│   ├── api/                    # API client + TanStack Query hooks
│   │   ├── client.ts           # Axios config + getRisks(), verifyAuditChain()
│   │   └── queries.ts          # useRisksQuery() hook
│   ├── components/
│   │   └── ui/                 # Reusable UI components
│   ├── contexts/               # SecurityContext (ABAC)
│   ├── features/
│   │   └── risks/              # Screen components (4 pages)
│   ├── layout/                 # Layout + Sidebar
│   ├── types/                  # TypeScript interfaces
│   ├── App.tsx                 # Router setup
│   ├── main.tsx                # Entry point
│   └── index.css               # Tailwind + globals
├── vite.config.ts              # Proxy config (/api -> :8000)
├── tailwind.config.js
├── postcss.config.js
├── tsconfig.json
└── package.json
```

---

## Deployment

### Docker Example

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web . 
RUN npm run build

FROM node:20-alpine
WORKDIR /app
RUN npm install -g serve
COPY --from=build /app/dist ./dist
EXPOSE 3000
CMD ["serve", "-s", "dist", "-l", "3000"]
```

Build & run:
```bash
docker build -t forpost-web .
docker run -p 3000:3000 --env API_URL=http://backend:8000 forpost-web
```

### Kubernetes (Helm)

Deploy as separate service with ingress routing:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: forpost-web
spec:
  ports:
  - port: 3000
    targetPort: 3000
  selector:
    app: forpost-web
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: forpost-ingress
spec:
  rules:
  - host: forpost.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: forpost-web
            port:
              number: 3000
      - path: /api
        pathType: Prefix
        backend:
          service:
            name: forpost-api
            port:
              number: 8000
```

---

## Security Checklist

- [x] TypeScript strict mode (no `any`)
- [x] ABAC context management (role + districts)
- [x] API authentication headers (x-user-id, x-role, x-districts)
- [x] Client-side file validation (type + size)
- [x] Vite CSP proxy (no direct /api calls from browser)
- [x] Dark theme (industrial, no bright flashes)
- [x] All types synced with backend Pydantic models
- [x] Oxlint linting enabled

**Remaining** (out of scope for this phase):
- JWT/mTLS auth (mocked with headers in dev)
- CSR token validation
- Rate limiting on client (done on backend via slowapi)

---

## Troubleshooting

### Port Already in Use
```powershell
# Kill process on port 8000
Get-Process python | Where-Object { $_.CommandLine -match 'uvicorn' } | Stop-Process

# Kill process on port 5173
Get-Process node | Stop-Process -Force
```

### Module Not Found
```powershell
cd apps/web
npm install
```

### CORS Error in Console
- Ensure backend is running on `:8000`
- Check Vite proxy config in `vite.config.ts`
- Frontend should proxy to backend, not make direct cross-origin calls

### "useSecurityContext outside Provider"
- Verify `<SecurityProvider>` wraps entire `<BrowserRouter>` in `App.tsx`

### Build Fails
```powershell
npm run build  # Shows detailed TypeScript errors
```

---

## Git Commit History

Latest commit includes:
- Full Vite + React setup
- React Router with 4 pages
- ABAC context + sidebar
- Typed API client
- Tailwind dark theme
- All build/lint checks passing

```
commit 02d0ad7
feat(web): Implement dispatcher console with routing and sidebar
- 34 files changed, 4173 insertions(+)
```

---

## Next Steps

1. **Integration Testing**: Test all 4 screens against real backend data
2. **Mobile Responsiveness**: Add tablet/mobile breakpoints
3. **Dark Mode Toggle**: Allow users to switch themes
4. **Real JWT Auth**: Replace simulated headers with mTLS/JWT tokens
5. **Observability**: Add performance monitoring (Sentry, datadog)
6. **E2E Tests**: Add Cypress/Playwright tests

---

## Support

- **Backend Issues**: Check `/apps/api/` docs
- **Frontend Issues**: Check `/apps/web/README.md`
- **Type Mismatches**: Sync frontend types with `/packages/domain/src/forpost_domain/risks/entities.py`

---

**Deployment Date**: 2026-09-10  
**Version**: 0.1.0  
**Status**: ✅ Functional & Ready for QA
