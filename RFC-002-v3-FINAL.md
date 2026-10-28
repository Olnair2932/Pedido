# RFC-002 v3.0 — Viamão Delivery — Especificação Final para Implementação
**Projeto:** Viamão Delivery
**Status:** Aprovado para execução
**Data:** 2026-10-28
**Substitui:** RFC-002 v2.0 (reprovado pelo Goldfish)

---

## 1. Visão Geral

Monólito Modular Event-Driven (Spring Boot) com Bounded Contexts isolados em schemas PostgreSQL separados, permitindo extração futura para microserviços sem reescrita.

**Stack definitiva:**
- Spring Boot 3 + PostgreSQL 15 + PostGIS + Redis 7 + RabbitMQ 3
- Outbox Pattern com Debezium CDC (não polling simples)
- Resilience4j, Prometheus + Grafana, FCM/APNS + fallback in-app

**Bounded Contexts:** Catalog, Order, Delivery, Payment, Geofence, Notification

---

## 2. Correções Obrigatórias da v2.0 (Goldfish)

### 2.1 FIX-01 — Race Condition PIX vs Timeout
**Problema:** Pagamento aos 14m45s, timeout cancela aos 15m00s, reconciliação encontra pago aos 16m00s → dinheiro debitado sem pedido.

**Solução:**
- Novo estado intermediário: `PROCESSANDO_RECONCILIACAO`
- Antes de aplicar timeout em `AGUARDANDO_PAGAMENTO`, adquirir lock distribuído Redis `lock:pedido:{id}` (TTL 30s)
- Worker de reconciliação marca `PROCESSANDO_RECONCILIACAO` antes de consultar gateway
- Se PIX confirmado em pedido já `CANCELADO`: disparar `EstornoAutomaticoEvent` imediatamente + notificar cliente
- Grace period: timeout só executa se `updated_at < now() - 15min AND status NOT IN ('PROCESSANDO_RECONCILIACAO')`
- Tabela `pagamentos` guarda `gateway_origem` (A ou B), `txid`, `idempotency_key UUIDv4`

### 2.2 FIX-02 — Lock de Despacho sem Postgres
**Problema:** `SELECT FOR UPDATE` estoura pool em pico.

**Solução:**
- Remover `FOR UPDATE`. Usar Redis Lua script atômico:
```lua
-- key: entrega:{id}, arg: entregador_id
if redis.call("SET", KEYS[1], ARGV[1], "NX", "EX", 30) then return 1 else return 0 end
```
- Primeiro aceite ganha (retorno 1). Demais recebem HTTP 409
- Entrega tem `version` (@Version) para controle otimista como segunda barreira
- TTL 30s evita deadlock se entregador desistir

### 2.3 FIX-03 — Compensação ao Lojista
**Regra nova:** Cancelamento após `PRONTO_PARA_ENVIO` por falta de entregador (culpa da plataforma):
- Lojista recebe `compensacao_insumo` = 70% do valor dos itens (tabela `compensacoes`)
- Cliente recebe estorno PIX integral + cupom
- Evento `PedidoCanceladoComCompensacaoEvent` alimenta financeiro

### 2.4 FIX-04 — Zona Rural / CEP Genérico
- Cadastro de endereço: se `accuracy_score < 0.7` ou CEP genérico, **obrigar Pin Drop no mapa**
- Armazenar `lat, lon, accuracy, fonte='manual'|'geocode'`
- Validação: `ST_Contains(loja.zona_entrega, ponto)` — se falhar, sugerir lojas que atendem o pino
- Cache Redis por `CEP+numero`, mas nunca usar coordenada de centro de bairro como definitiva

### 2.5 FIX-05 — Fraude no Dinheiro
- Remover validação só por GPS
- Fluxo: entregador informa valor recebido → app gera PIN de 4 dígitos para cliente confirmar OU cliente informa código OTP mostrado no app do entregador
- Sem confirmação bilateral em 10min → `EM_CONTESTE`, não libera garantia automática
- Log de GPS é evidência auxiliar, não decisória

### 2.6 FIX-06 — Multi-Gateway Sincronizado
- `pagamentos.gateway_origem` preenchido no checkout
- Circuit Breaker (Resilience4j): se Gateway A >50% erro em 30s, novas cobranças vão para B
- Worker de reconciliação consulta **o gateway de origem** do pedido, nunca o atual do circuit breaker

---

## 3. Máquina de Estados Final

Estados: `CRIADO`, `AGUARDANDO_PAGAMENTO`, `PROCESSANDO_RECONCILIACAO`, `AGUARDANDO_ACEITE_LOJA`, `EM_PREPARO`, `PRONTO_PARA_ENVIO`, `AGUARDANDO_ENTREGADOR`, `EM_TRANSITO`, `ENTREGUE`, `CANCELADO`, `CANCELADO_COM_COMPENSACAO`, `EM_CONTESTE`

Timeouts:
- CRIADO → cancela em 15min (com trava FIX-01)
- AGUARDANDO_ACEITE_LOJA → 10min → estorno PIX
- PRONTO_PARA_ENVIO / AGUARDANDO_ENTREGADOR → 20min → expansão de raio, depois cancela com compensação FIX-03
- EM_TRANSITO → 60min → auditoria

---

## 4. Outbox Pattern

1. Transação única: update domínio + insert `outbox_events`
2. Debezium CDC → RabbitMQ
3. 3 tentativas → DLQ + alerta Grafana
4. Consumers idempotentes por `event_id`

---

## 5. Geofencing

- Lojista desenha polígono GeoJSON no painel
- `lojas.zona_entrega GEOMETRY(Polygon, 4326)`
- Taxa: OSRM rota real + tabela lojista (urbano vs rural)

---

## 6. Telemetria GPS

- Client-side: envia se >25m OU >15s
- Payload delta compacto `{t,lat,lon,s}`
- Backend valida sanidade: descarta teletransporte >200km/h
- Fallback: SQLite local + batch gzip via POST se WebSocket cair
- Anti-fraude: rejeitar Mock Location (Android `isMock`)

---

## 7. Catálogo

- Snapshot do pedido no checkout (preço congelado)
- Redis cache com invalidação por `ProdutoIndisponivelEvent`

---

## 8. LGPD

- GPS entregador: purga 30 dias → Data Lake anonimizado
- Endereço/telefone mascarados pós-entrega
- Rota de exclusão de conta, retenção só fiscal

---

## 9. Observabilidade

- Prometheus: RPS WebSocket, lag outbox, taxa timeout aceite
- Circuit Breakers em pagamento, FCM, mapas
- Notificação: FCM/APNS + inbox in-app (fallback se push falhar)

---

## 10. Checklist para Executor de Código

- [ ] Schemas separados por contexto no Postgres + PostGIS
- [ ] Tabela outbox_events + Debezium → RabbitMQ + DLQ
- [ ] Redis para locks de despacho (Lua), cache geocode, idempotência
- [ ] State machine com todos estados acima + jobs de timeout com trava Redis
- [ ] Worker reconciliação PIX com gateway_origem
- [ ] Pin Drop obrigatório para accuracy baixa
- [ ] Compensação lojista 70%
- [ ] OTP/PIN para dinheiro
- [ ] Validação anti-mock GPS

**Pronto para codar.**
