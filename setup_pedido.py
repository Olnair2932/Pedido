import os

print("🚀 Gerando estrutura da RFC-002 v3.0 em ~/downloads/Pedido...")

def criar_arquivo(caminho, conteudo):
    d = os.path.dirname(caminho)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(caminho, 'w', encoding='utf-8') as f:
        f.write(conteudo.strip() + '\n')
    print(f"  [+] Criado: {caminho}")

# 1. Docker Compose (Postgres+PostGIS, Redis, RabbitMQ)
docker_compose = """
version: '3.8'
services:
  postgres:
    image: postgis/postgis:15-3.3
    container_name: viamao_postgres
    environment:
      POSTGRES_DB: viamao_db
      POSTGRES_USER: viamao_user
      POSTGRES_PASSWORD: viamao_password
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    container_name: viamao_redis
    ports:
      - "6379:6379"

  rabbitmq:
    image: rabbitmq:3-management-alpine
    container_name: viamao_rabbitmq
    ports:
      - "5672:5672"
      - "15672:15672"
    environment:
      RABBITMQ_DEFAULT_USER: guest
      RABBITMQ_DEFAULT_PASS: guest

volumes:
  pgdata:
"""

# 2. pom.xml
pom_xml = """
<project xmlns="http://maven.apache.org/POM/4.0.0" 
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.viamao</groupId>
    <artifactId>delivery</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <name>viamao-delivery</name>
    <description>Viamão Delivery - Monólito Modular Event-Driven</description>
    
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-redis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-amqp</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.hibernate.orm</groupId>
            <artifactId>hibernate-spatial</artifactId>
        </dependency>
        <dependency>
            <groupId>org.flywaydb</groupId>
            <artifactId>flyway-core</artifactId>
        </dependency>
        <dependency>
            <groupId>org.flywaydb</groupId>
            <artifactId>flyway-database-postgresql</artifactId>
        </dependency>
        <dependency>
            <groupId>io.github.resilience4j</groupId>
            <artifactId>resilience4j-spring-boot3</artifactId>
            <version>2.1.0</version>
        </dependency>
        <dependency>
            <groupId>org.projectlombok</groupId>
            <artifactId>lombok</artifactId>
            <optional>true</optional>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
"""

# 3. Application YML
application_yml = """
spring:
  application:
    name: viamao-delivery
  datasource:
    url: jdbc:postgresql://localhost:5432/viamao_db?currentSchema=order_domain,payment,delivery,catalog,geofence,notification
    username: viamao_user
    password: viamao_password
  jpa:
    hibernate:
      ddl-auto: validate
    show-sql: true
    properties:
      hibernate.dialect: org.hibernate.spatial.dialect.postgis.PostgisDialect
  data:
    redis:
      host: localhost
      port: 6379
  flyway:
    enabled: true
    schemas: order_domain,payment,delivery,catalog,geofence,notification
    default-schema: order_domain

resilience4j:
  circuitbreaker:
    instances:
      gatewayPayment:
        slidingWindowSize: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 30000ms
"""

# 4. Máquina de Estados (OrderStatus.java)
order_status_enum = """
package com.viamao.delivery.order.domain;

public enum OrderStatus {
    CRIADO,
    AGUARDANDO_PAGAMENTO,
    PROCESSANDO_RECONCILIACAO, // FIX-01 (Race Condition PIX vs Timeout)
    AGUARDANDO_ACEITE_LOJA,
    EM_PREPARO,
    PRONTO_PARA_ENVIO,
    AGUARDANDO_ENTREGADOR,
    EM_TRANSITO,
    ENTREGUE,
    CANCELADO,
    CANCELADO_COM_COMPENSACAO, // FIX-03 (Compensacao 70% lojista)
    EM_CONTESTE // FIX-05 (Fraude Dinheiro / PIN/OTP)
}
"""

# 5. Lock de Despacho com Redis Lua Script (FIX-02)
dispatch_lock_service = """
package com.viamao.delivery.delivery.service;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

import java.util.Collections;

@Service
public class DispatchLockService {

    private final StringRedisTemplate redisTemplate;

    // FIX-02: Lua Script atômico sem SELECT FOR UPDATE no Postgres
    private static final String LUA_SCRIPT = 
        "if redis.call('SET', KEYS[1], ARGV[1], 'NX', 'EX', 30) then return 1 else return 0 end";

    public DispatchLockService(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public boolean tentarLockDespacho(String entregaId, String entregadorId) {
        String key = "entrega:" + entregaId;
        DefaultRedisScript<Long> redisScript = new DefaultRedisScript<>();
        redisScript.setScriptText(LUA_SCRIPT);
        redisScript.setResultType(Long.class);

        Long result = redisTemplate.execute(redisScript, Collections.singletonList(key), entregadorId);
        return result != null && result == 1L;
    }
}
"""

# 6. Entidade Outbox Pattern (Seção 4)
outbox_entity = """
package com.viamao.delivery.shared.outbox;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

import java.time.LocalDateTime;
import java.util.UUID;

@Entity
@Table(name = "outbox_events", schema = "order_domain")
@Getter
@Setter
public class OutboxEvent {

    @Id
    private UUID id = UUID.randomUUID();

    @Column(nullable = false)
    private String aggregateType;

    @Column(nullable = false)
    private String aggregateId;

    @Column(nullable = false)
    private String eventType;

    @Column(columnDefinition = "TEXT", nullable = false)
    private String payload;

    @Column(nullable = false)
    private LocalDateTime createdAt = LocalDateTime.now();

    private Boolean processed = false;
}
"""

# 7. Migration SQL Flyway (V1)
flyway_sql = """
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
"""

# Gravação dos arquivos
criar_arquivo("docker-compose.yml", docker_compose)
criar_arquivo("pom.xml", pom_xml)
criar_arquivo("src/main/resources/application.yml", application_yml)
criar_arquivo("src/main/java/com/viamao/delivery/order/domain/OrderStatus.java", order_status_enum)
criar_arquivo("src/main/java/com/viamao/delivery/delivery/service/DispatchLockService.java", dispatch_lock_service)
criar_arquivo("src/main/java/com/viamao/delivery/shared/outbox/OutboxEvent.java", outbox_entity)
criar_arquivo("src/main/resources/db/migration/V1__init_schemas.sql", flyway_sql)

print("\n✅ Todos os arquivos foram criados com sucesso em ~/downloads/Pedido!")
