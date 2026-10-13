#!/bin/bash
for d in api.xkiro.com api.openai.com api.anthropic.com openrouter.ai google.com github.com yandex.ru; do
    echo -n "$d -> "
    dig @192.168.50.1 +short "$d" | tr '\n' ' '
    echo
done
