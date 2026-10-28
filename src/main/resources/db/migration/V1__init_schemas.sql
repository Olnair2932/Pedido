CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS catalog;
CREATE SCHEMA IF NOT EXISTS order_domain;
CREATE SCHEMA IF NOT EXISTS delivery;
CREATE SCHEMA IF NOT EXISTS payment;
CREATE SCHEMA IF NOT EXISTS geofence;
CREATE SCHEMA IF NOT EXISTS notification;

-- Outbox Table (Section 4)
CREATE TABLE order_domain.outbox_events (
    id UUID PRIMARY KEY,
    aggregate_type VARCHAR(255) NOT NULL,
    aggregate_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(255) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    processed BOOLEAN DEFAULT FALSE
);

-- Pagamentos (FIX-01 & FIX-06)
CREATE TABLE payment.pagamentos (
    id UUID PRIMARY KEY,
    pedido_id UUID NOT NULL,
    gateway_origem VARCHAR(50) NOT NULL,
    txid VARCHAR(255) UNIQUE,
    idempotency_key UUID NOT NULL UNIQUE,
    valor DECIMAL(10,2) NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

-- Compensações Lojista (FIX-03)
CREATE TABLE payment.compensacoes (
    id UUID PRIMARY KEY,
    lojista_id UUID NOT NULL,
    pedido_id UUID NOT NULL,
    valor_insumo DECIMAL(10,2) NOT NULL,
    percentual_aplicado DECIMAL(5,2) DEFAULT 70.00,
    created_at TIMESTAMP NOT NULL
);

-- Geofencing Lojas (FIX-04 & Section 5)
CREATE TABLE geofence.zonas_loja (
    id UUID PRIMARY KEY,
    loja_id UUID NOT NULL,
    zona_entrega GEOMETRY(Polygon, 4326) NOT NULL
);
