"""Test end-to-end de app.py con streamlit AppTest, simulando la subida de logs."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

os.chdir(Path(__file__).parent)
sys.path.insert(0, str(Path(__file__).parent))

from streamlit.testing.v1 import AppTest


class FakeUpload:
    def __init__(self, path: str):
        self.name = Path(path).name
        self._data = Path(path).read_bytes()

    def getvalue(self) -> bytes:
        return self._data


def run_app(files, mutate=None):
    fakes = [FakeUpload(f) for f in files]
    with patch(
        "streamlit.delta_generator.DeltaGenerator.file_uploader",
        return_value=fakes,
    ):
        at = AppTest.from_file("app.py", default_timeout=120)
        at.run()
        if mutate:
            mutate(at)
            at.run()
    return at


def check(at, label):
    if at.exception:
        print(f"FAIL [{label}]:")
        for e in at.exception:
            print(e.value)
            print(e.stack_trace)
        sys.exit(1)
    print(f"OK   [{label}]  (errores: {len(at.error)}, warnings UI: {len(at.warning)})")


# 1. Dos logs, defaults (comparacion multi-archivo + tab computo + info)
at = run_app(["log_T5500_g8.lammps", "log_T5800_g5.lammps"])
check(at, "2 logs, defaults")
metrics = [m.label for m in at.metric]
assert "Wall time total" in metrics, metrics
assert len(at.multiselect) >= 3

# 2. Un log, varias columnas Y + subplots + suavizado + log Y + sin unir runs
def mutate(at):
    at.multiselect[2].set_value(["Temp", "TotEng", "Press"])
    at.radio[0].set_value("Subplot por columna")
    at.checkbox[0].set_value(False)   # unir runs
    at.slider[0].set_value(21)        # suavizado
    at.checkbox[2].set_value(True)    # escala log

at = run_app(["log_T5500_g8.lammps"], mutate)
check(at, "1 log, subplots+suavizado+log+runs separados")

# 3. Eje X = Time (columna que no existe en todos los runs)
def mutate_x(at):
    at.selectbox[0].set_value("Time")
    at.multiselect[2].set_value(["c_Tnw", "v_ke_max"])

at = run_app(["log_T5500_g8.lammps"], mutate_x)
check(at, "1 log, X=Time, columnas custom")

# 4. Archivo que no es un log de LAMMPS
Path("basura.txt").write_text("esto no es un log\n1 2 3\n")
at = run_app(["basura.txt"])
check(at, "archivo invalido")
assert at.warning, "deberia avisar que no es un log"

print("\nTodos los tests pasaron ✅")
