FROM node:22-slim

WORKDIR /app

# Installed from the lockfile before the source is copied, so editing a
# component does not reinstall node_modules.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

# The Vite dev server is the deliberate runtime here, not an oversight: it
# gives hot reload during development and proxies /api to the API container,
# which keeps the browser on a single origin and avoids CORS entirely. A
# production build would instead emit static assets to a CDN -- see the
# README's productionisation section.
CMD ["npm", "run", "dev"]
