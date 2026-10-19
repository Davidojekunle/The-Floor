# One image for production: the built frontend-v2 is served by the FastAPI app, so the site, the API and the
# live socket share one origin (the refresh cookie is SameSite=lax and needs that).

FROM node:22-alpine AS web
WORKDIR /web
COPY frontend-v2/package.json frontend-v2/package-lock.json ./
RUN npm ci
COPY frontend-v2/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ .
COPY --from=web /web/dist /app/frontend
ENV FRONTEND_DIST=/app/frontend
EXPOSE 8000
CMD ["sh", "start.sh"]
