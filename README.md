# Home of Exile — MVP v1 (PoB Export Code Import)

This repo contains a minimal MVP:
- Backend: Spring Boot REST endpoint to decode + parse a Path of Building (PoB) export code
- Frontend: Vue SPA to paste an export code and display parsed results

## Run (local)

### Backend
From `backend/`:
- `mvn test`
- `mvn spring-boot:run`

Backend listens on `http://localhost:8080`.

### Frontend
From `frontend/`:
- `npm install`
- `npm run dev`

Frontend listens on `http://localhost:5173` and proxies `/api` to the backend.

### Cypress (e2e)
From `frontend/` (with dev server running):
- `npm run cy:run`

## API
- `POST /api/import/pob`

Request:
```json
{ "exportCode": "..." }
```
