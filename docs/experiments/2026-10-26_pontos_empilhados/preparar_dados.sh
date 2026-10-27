#!/bin/bash
# Prepara os dados do experimento a partir dos downloads oficiais, só com o GDAL do QGIS.
#
#   bash preparar_dados.sh <pasta com os originais> <pasta de saída>
#
# Originais (baixar à mão):
#   shp_cnuc_2025_08.zip — CNUC/MMA, polígonos de 2025_08:
#     https://dados.mma.gov.br/dataset/44b6dc8a-dc82-4a84-8d95-1b0da7c85dac/resource/6ba9a557-87e8-4882-acb7-b3e0f0ea192d/download/shp_cnuc_2025_08.zip
#   0006183-261023074918325.zip — GBIF.org (26 October 2026) GBIF Occurrence Download
#     https://doi.org/10.15468/dl.kee8xx (CC BY-NC 4.0; os registros não são redistribuídos aqui)
#
# QGIS_BIN aponta para a pasta bin do QGIS (padrão: QGIS 4.0.2 no Windows).
set -eu
export MSYS_NO_PATHCONV=1
ORIG="$1"; OUT="$2"
BIN="${QGIS_BIN:-/c/Program Files/QGIS 4.0.2/bin}"
mkdir -p "$OUT"
rm -f "$OUT/parna_itatiaia.gpkg" "$OUT/gbif_registros.gpkg"
"$BIN/ogr2ogr.exe" -f GPKG "$OUT/parna_itatiaia.gpkg" "/vsizip/$ORIG/shp_cnuc_2025_08.zip/cnuc_2025_08.shp" \
  -where "cd_cnuc = '0000.00.0184'" -nln parna_itatiaia -nlt PROMOTE_TO_MULTI
# Todas as linhas do download; só as colunas, entre elas as que identificam quem publicou cada registro.
"$BIN/ogr2ogr.exe" -f GPKG "$OUT/gbif_registros.gpkg" \
  "/vsizip/$ORIG/0006183-261023074918325.zip/0006183-261023074918325.csv" -nln gbif_registros -a_srs EPSG:4326 \
  -oo SEPARATOR=TAB -oo X_POSSIBLE_NAMES=decimalLongitude -oo Y_POSSIBLE_NAMES=decimalLatitude \
  -oo KEEP_GEOM_COLUMNS=NO -oo AUTODETECT_TYPE=YES \
  -select gbifID,datasetKey,publishingOrgKey,basisOfRecord,kingdom,class,species,scientificName,year,coordinateUncertaintyInMeters,institutionCode,license
"$BIN/ogrinfo.exe" -ro -so "$OUT/gbif_registros.gpkg" gbif_registros | grep -E "Feature Count"
