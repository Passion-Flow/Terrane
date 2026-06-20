FROM golang:1.26 AS build
WORKDIR /src
COPY go.mod go.sum* ./
RUN go mod download 2>/dev/null || true
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /gateway ./cmd/gateway
FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /gateway /gateway
EXPOSE 43080
ENTRYPOINT ["/gateway"]
