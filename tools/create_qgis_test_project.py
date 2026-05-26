from __future__ import annotations

"""Run inside QGIS Python to create a temporary SIGMAI test project."""

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHAPES = Path(os.environ.get("SIGMAI_TEST_DATA_DIR", ROOT.parent / ("Shapes pra " + "Teste")))
OUTPUT = ROOT / "test_outputs" / "sigmai_test_project.qgz"


def main() -> None:
    from qgis.core import QgsProject, QgsVectorLayer  # type: ignore

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    project = QgsProject.instance()
    project.clear()
    for path in [
        SHAPES / "Pais" / "BR_Pais_2025.shp",
        SHAPES / "Estados" / "BR_UF_2025.shp",
        SHAPES / "Municipios" / "SP_Municipios_2025.shp",
    ]:
        layer = QgsVectorLayer(str(path), path.stem, "ogr")
        if not layer.isValid():
            raise RuntimeError(f"Could not load layer: {path}")
        project.addMapLayer(layer)
    project.write(str(OUTPUT))
    print(f"Test project written to {OUTPUT}")


if __name__ == "__main__":
    main()
