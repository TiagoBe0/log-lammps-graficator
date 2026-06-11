#!/bin/bash
# Muestra la URL publica actual del tunel de Cloudflare
url=$(curl -s http://127.0.0.1:20241/metrics 2>/dev/null | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com')
if [ -z "$url" ]; then
    echo "Tunel no activo. Verificar: systemctl --user status lammps-cloudflared"
else
    echo "URL publica: $url"
fi
