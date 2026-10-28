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
