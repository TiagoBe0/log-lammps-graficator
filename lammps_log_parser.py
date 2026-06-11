"""Parser de logs de LAMMPS.

Extrae de cada log:
  - Cada seccion thermo (run) como DataFrame de pandas, tolerando warnings
    intercalados y runs truncados (simulaciones todavia corriendo).
  - Metricas de computo por run: Loop time, Performance (ns/day, timesteps/s...),
    % de uso de CPU, tareas MPI / hilos OpenMP, memoria por rank y el
    desglose de tiempos MPI (Pair/Neigh/Comm/...).
  - Metadatos globales: version de LAMMPS, Total wall time y warnings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

_RE_LOOP = re.compile(
    r"^Loop time of ([\d.eE+\-]+) on (\d+) procs for (\d+) steps with (\d+) atoms"
)
_RE_PERF = re.compile(r"^Performance:\s*(.+)$")
_RE_PERF_ITEM = re.compile(r"([\d.eE+\-]+)\s+([^\s,]+)")
_RE_CPU = re.compile(
    r"^([\d.]+)% CPU use with (\d+) MPI tasks? x (\d+) OpenMP threads?"
)
_RE_MEM = re.compile(
    r"^Per MPI rank memory allocation \(min/avg/max\) = "
    r"([\d.eE+\-]+) \| ([\d.eE+\-]+) \| ([\d.eE+\-]+) (\w+)"
)
_RE_HEADER = re.compile(r"^\s*Step\s+\S")
_RE_WALL = re.compile(r"^Total wall time:\s*(\S+)")


@dataclass
class Run:
    """Una seccion thermo del log con sus metricas de computo asociadas."""

    index: int
    columns: list[str]
    df: pd.DataFrame
    complete: bool = False          # False si el run fue truncado (sin "Loop time")
    loop_time: float | None = None  # segundos
    n_procs: int | None = None
    n_steps: int | None = None
    n_atoms: int | None = None
    performance: dict[str, float] = field(default_factory=dict)  # {"ns/day": x, ...}
    cpu_use: float | None = None    # %
    mpi_tasks: int | None = None
    omp_threads: int | None = None
    memory_mb: tuple[float, float, float] | None = None  # min/avg/max
    mpi_breakdown: pd.DataFrame | None = None

    @property
    def label(self) -> str:
        steps = f"{self.n_steps} steps" if self.n_steps is not None else (
            f"{len(self.df)} filas" + ("" if self.complete else ", incompleto")
        )
        return f"Run {self.index + 1} ({steps})"


@dataclass
class LammpsLog:
    version: str = ""
    runs: list[Run] = field(default_factory=list)
    total_wall_time: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def all_columns(self) -> list[str]:
        cols: list[str] = []
        for run in self.runs:
            for c in run.columns:
                if c not in cols:
                    cols.append(c)
        return cols


def _dedupe(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for n in names:
        if n in seen:
            seen[n] += 1
            out.append(f"{n}_{seen[n]}")
        else:
            seen[n] = 0
            out.append(n)
    return out


def _try_floats(tokens: list[str]) -> list[float] | None:
    try:
        return [float(t) for t in tokens]
    except ValueError:
        return None


def _parse_mpi_breakdown(lines: list[str], start: int) -> tuple[pd.DataFrame, int]:
    """Parsea la tabla 'MPI task timing breakdown' a partir de su titulo."""
    rows = []
    i = start + 1
    while i < len(lines):
        line = lines[i]
        parts = [p.strip() for p in line.split("|")]
        if len(parts) == 6 and parts[0] and not line.startswith("Section"):
            def num(s: str) -> float | None:
                try:
                    return float(s)
                except ValueError:
                    return None
            rows.append(
                {
                    "Seccion": parts[0],
                    "min (s)": num(parts[1]),
                    "avg (s)": num(parts[2]),
                    "max (s)": num(parts[3]),
                    "%varavg": num(parts[4]),
                    "%total": num(parts[5]),
                }
            )
        elif rows and not line.startswith(("Section", "---")):
            break
        i += 1
    return pd.DataFrame(rows), i


def parse_log(text: str) -> LammpsLog:
    lines = text.splitlines()
    log = LammpsLog()
    if lines and lines[0].startswith("LAMMPS"):
        log.version = lines[0].strip()

    pending_memory: tuple[float, float, float] | None = None
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        if line.startswith("WARNING"):
            log.warnings.append(line.strip())
            i += 1
            continue

        m = _RE_MEM.match(line)
        if m:
            pending_memory = (float(m.group(1)), float(m.group(2)), float(m.group(3)))
            i += 1
            continue

        m = _RE_WALL.match(line)
        if m:
            log.total_wall_time = m.group(1)
            i += 1
            continue

        if not _RE_HEADER.match(line):
            i += 1
            continue

        # --- Comienza una seccion thermo ---
        columns = _dedupe(line.split())
        run = Run(index=len(log.runs), columns=columns, df=pd.DataFrame())
        run.memory_mb = pending_memory
        pending_memory = None
        data: list[list[float]] = []
        i += 1

        while i < n:
            line = lines[i]
            if line.startswith("WARNING"):
                log.warnings.append(line.strip())
                i += 1
                continue
            tokens = line.split()
            if len(tokens) == len(columns):
                values = _try_floats(tokens)
                if values is not None:
                    data.append(values)
                    i += 1
                    continue
            m = _RE_LOOP.match(line)
            if m:
                run.complete = True
                run.loop_time = float(m.group(1))
                run.n_procs = int(m.group(2))
                run.n_steps = int(m.group(3))
                run.n_atoms = int(m.group(4))
                i += 1
                break
            if _RE_HEADER.match(line):
                break  # nuevo run sin cerrar el anterior (log truncado/raro)
            i += 1  # warning u otra linea intercalada en la tabla thermo

        run.df = pd.DataFrame(data, columns=columns)

        # --- Metricas de computo que siguen al "Loop time" ---
        if run.complete:
            while i < n:
                line = lines[i]
                if _RE_HEADER.match(line) or _RE_MEM.match(line):
                    break
                m = _RE_PERF.match(line)
                if m:
                    for value, unit in _RE_PERF_ITEM.findall(m.group(1)):
                        run.performance[unit] = float(value)
                    i += 1
                    continue
                m = _RE_CPU.match(line)
                if m:
                    run.cpu_use = float(m.group(1))
                    run.mpi_tasks = int(m.group(2))
                    run.omp_threads = int(m.group(3))
                    i += 1
                    continue
                if line.startswith("MPI task timing breakdown"):
                    run.mpi_breakdown, i = _parse_mpi_breakdown(lines, i)
                    break
                if line.startswith("WARNING"):
                    log.warnings.append(line.strip())
                m = _RE_WALL.match(line)
                if m:
                    log.total_wall_time = m.group(1)
                i += 1

        if not run.df.empty:
            log.runs.append(run)
        else:
            run.index = len(log.runs)  # descarta secciones vacias

    return log


def runs_summary(log: LammpsLog) -> pd.DataFrame:
    """Tabla resumen de metricas de computo, una fila por run."""
    rows = []
    for run in log.runs:
        row: dict[str, object] = {
            "Run": run.index + 1,
            "Steps": run.n_steps,
            "Atomos": run.n_atoms,
            "Loop time (s)": run.loop_time,
            "% CPU": run.cpu_use,
            "MPI x OMP": (
                f"{run.mpi_tasks} x {run.omp_threads}" if run.mpi_tasks else None
            ),
            "Memoria avg (MB)": run.memory_mb[1] if run.memory_mb else None,
            "Completo": "si" if run.complete else "no (corriendo/truncado)",
        }
        for unit, value in run.performance.items():
            row[unit] = value
        rows.append(row)
    return pd.DataFrame(rows)
