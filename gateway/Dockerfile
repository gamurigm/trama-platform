FROM golang:1.26-alpine AS build

WORKDIR /src
COPY gateway/go.mod gateway/go.sum ./
RUN go mod download
COPY gateway ./
ARG TRAMA_BINARY=trama-gateway
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /trama-service ./cmd/${TRAMA_BINARY}

FROM gcr.io/distroless/static-debian12:nonroot

COPY --from=build /trama-service /trama-service
EXPOSE 8080
USER nonroot:nonroot
ENTRYPOINT ["/trama-service"]
