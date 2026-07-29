# Étape 1 : génération du site avec Go (aucune dépendance externe requise)
FROM golang:1.22-alpine AS build
WORKDIR /app
COPY . .
RUN go run ./cmd/generator -rides ./rides -footer ./content/footer.md -legal ./content/mentions-legales.md -umami-id "" -out ./public

# Étape 2 : image légère qui sert uniquement le site statique généré
FROM nginx:alpine AS serve
COPY --from=build /app/public /usr/share/nginx/html
EXPOSE 80
