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
