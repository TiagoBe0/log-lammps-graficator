# LAMMPS Log Graficator 📈

App web para arrastrar y soltar logs de LAMMPS y graficar al instante:

- **Termodinámica**: elegís qué columnas thermo graficar (Temp, Press, TotEng,
  computes `c_*`, variables `v_*`...), con suavizado, subplots, escala log,
  unión de runs y comparación entre varios logs. Exportá PNG de alta resolución
  (botón de cámara del gráfico), HTML interactivo standalone o CSV.
- **Cómputo**: ns/day, timesteps/s, %CPU, memoria por rank MPI y desglose de
  tiempos MPI (Pair/Neigh/Comm/...) de cada run, **graficados automáticamente**.
- Funciona con logs de simulaciones **todavía corriendo** (runs truncados).
- **Fondo seleccionable** (claro / oscuro / gris, gris por defecto) desde la
  barra lateral. Todos los gráficos llevan grilla y una estética tipo figura de
  *paper* científico (tipografía serif, paleta apta para daltonismo, ejes con
  marco).

## Instalación en el servidor (AlmaLinux)

```bash
cd /home/simaf/DISCO-2T/sbergamin/log_lammps_graficator

# Entorno virtual (requiere python >= 3.10; en AlmaLinux 9: dnf install python3.11)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Probar a mano

```bash
.venv/bin/streamlit run app.py --server.address 0.0.0.0 --server.port 8502
```

y abrir `http://<IP-del-servidor>:8502` desde cualquier máquina del laboratorio.

### Abrir el puerto en el firewall (AlmaLinux usa firewalld)

```bash
sudo firewall-cmd --add-port=8502/tcp --permanent
sudo firewall-cmd --reload
```

### Dejarla corriendo permanentemente (servicio systemd de usuario)

Servicio *de usuario* y no de sistema: SELinux impide que PID 1 ejecute el
python del venv (vive en miniconda/home y en el disco de datos → `203/EXEC`).

```bash
mkdir -p ~/.config/systemd/user
cp lammps-graficator.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now lammps-graficator
sudo loginctl enable-linger simaf   # arranca al boot aunque no haya sesion abierta

# estado y logs del servicio:
systemctl --user status lammps-graficator
journalctl --user -u lammps-graficator -f
```

Se reinicia sola si se cae y arranca al bootear el servidor.

## Estructura

| Archivo | Qué hace |
|---|---|
| `lammps_log_parser.py` | Parser puro: secciones thermo → DataFrames + métricas de cómputo |
| `app.py` | Interfaz Streamlit (gráficos Plotly) |
| `lammps-graficator.service` | Unidad systemd para correr como servicio |

## Notas

- El límite de subida está en 1 GB (`--server.maxUploadSize 1024`); subilo si
  tenés logs más grandes.
- El parser tolera warnings intercalados en la tabla thermo, headers distintos
  entre runs y logs cortados a la mitad.
- No soporta `thermo_style multi` (el formato multilínea viejo), solo el
  formato columnar de `thermo_style one/custom`, que es el habitual.
# log-lammps-graficator
