# -*- coding: utf-8 -*-
"""
Mapa A4 do Parque Estadual das Carnaúbas (PEC) e municípios do entorno,
gerado 100% em PyQGIS (QgsPrintLayout), sem plugins.
Saídas: /tmp/lab_direto/mapa.png (200 dpi), /tmp/lab_direto/projeto.qgz
"""
import os, sys, datetime, locale
from qgis.core import *
from qgis.PyQt.QtCore import QRectF, Qt, QVariant
from qgis.PyQt.QtGui import QColor, QFont, QFontDatabase

qgs = QgsApplication([], True)   # GUI=True sob xvfb: evita erro de QFontDatabase
qgs.initQgis()

BASE = '/tmp/lab_direto'
D = BASE + '/dados/'
CRS_UTM = QgsCoordinateReferenceSystem('EPSG:31984')   # SIRGAS 2000 / UTM 24S
CRS_GEO = QgsCoordinateReferenceSystem('EPSG:4674')    # SIRGAS 2000 geográfico
FONT = 'DejaVu Sans'
fams = QFontDatabase().families()
print('Fonte DejaVu Sans disponível?', FONT in fams, '| n familias:', len(fams))

project = QgsProject.instance()
project.setCrs(CRS_UTM)
project.setTitle('Parque Estadual das Carnaúbas – mapa de localização (A4)')
project.writeEntry('Paths', '/Absolute', False)   # caminhos relativos -> projeto portátil

# ------------------------------------------------------------------ helpers
def fill(color, outline, width, style='solid', outline_style='solid', opacity=1.0):
    s = QgsFillSymbol.createSimple({'color': color, 'outline_color': outline,
                                    'outline_width': str(width), 'style': style,
                                    'outline_style': outline_style})
    s.setOpacity(opacity)
    return s

def qfont(size, bold=False, italic=False):
    f = QFont(FONT); f.setPointSizeF(float(size)); f.setBold(bold); f.setItalic(italic)
    return f

def text_format(size, color='#000000', bold=False, italic=False, buffer=None, spacing=0.0):
    f = qfont(size, bold, italic)
    if spacing:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    fmt = QgsTextFormat(); fmt.setFont(f); fmt.setSize(size); fmt.setColor(QColor(color))
    if buffer:
        b = QgsTextBufferSettings(); b.setEnabled(True); b.setSize(buffer)
        b.setColor(QColor('#ffffff')); b.setOpacity(0.9); fmt.setBuffer(b)
    return fmt

def label_layer(layer, field, fmt, is_expr=False, placement=None, priority=5,
                wrap=0, centroid_inside=True):
    s = QgsPalLayerSettings()
    s.fieldName = field; s.isExpression = is_expr
    s.setFormat(fmt)
    s.placement = placement if placement is not None else Qgis.LabelPlacement.Horizontal
    s.centroidWhole = False          # centróide da parte VISÍVEL do polígono
    s.centroidInside = centroid_inside
    s.priority = priority
    if wrap:
        s.autoWrapLength = wrap; s.useMaxLineLengthForAutoWrap = True
    s.multilineAlign = Qgis.LabelMultiLineAlignment.Center
    layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
    layer.setLabelsEnabled(True)

def add_label(layout, text, x, y, w, h, size=8, bold=False, italic=False,
              halign=Qt.AlignLeft, valign=Qt.AlignTop, color='#000000'):
    lb = QgsLayoutItemLabel(layout)
    lb.setText(text)
    lb.setTextFormat(text_format(size, color, bold=bold, italic=italic))
    lb.setHAlign(halign); lb.setVAlign(valign)
    lb.setMarginX(1.0); lb.setMarginY(0.5)
    layout.addLayoutItem(lb)
    lb.attemptSetSceneRect(QRectF(x, y, w, h))
    return lb

# camada de pontos de apoio (nomes de estados/oceano) gravada em GPKG para persistir no projeto
GPKG = BASE + '/apoio_rotulos.gpkg'
if os.path.exists(GPKG):
    os.remove(GPKG)
def write_points(layername, crs, pts, first):
    fields = QgsFields(); fields.append(QgsField('nome', QVariant.String))
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = 'GPKG'; opts.layerName = layername
    opts.actionOnExistingFile = (QgsVectorFileWriter.CreateOrOverwriteFile if first
                                 else QgsVectorFileWriter.CreateOrOverwriteLayer)
    w = QgsVectorFileWriter.create(GPKG, fields, QgsWkbTypes.Point, crs,
                                   QgsCoordinateTransformContext(), opts)
    if w.hasError() != QgsVectorFileWriter.NoError:
        print('ERRO GPKG:', w.errorMessage())
    for name, x, y in pts:
        f = QgsFeature(fields); f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        f.setAttributes([name]); w.addFeature(f)
    del w
    lyr = QgsVectorLayer(f'{GPKG}|layername={layername}', layername, 'ogr')
    print('camada apoio', layername, 'valida?', lyr.isValid(), 'n=', lyr.featureCount())
    return lyr

def write_lines(layername, crs, geom, nome):
    fields = QgsFields(); fields.append(QgsField('nome', QVariant.String))
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = 'GPKG'; opts.layerName = layername
    opts.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
    w = QgsVectorFileWriter.create(GPKG, fields, QgsWkbTypes.MultiLineString, crs,
                                   QgsCoordinateTransformContext(), opts)
    f = QgsFeature(fields); f.setGeometry(geom); f.setAttributes([nome]); w.addFeature(f)
    del w
    lyr = QgsVectorLayer(f'{GPKG}|layername={layername}', layername, 'ogr')
    print('camada apoio', layername, 'valida?', lyr.isValid(), 'n=', lyr.featureCount())
    return lyr

# ------------------------------------------------------------------ camadas
uc  = QgsVectorLayer(D + 'PE Carnaubas.kml', 'Parque Estadual das Carnaúbas', 'ogr')
uc2 = QgsVectorLayer(D + 'PE Carnaubas.kml', 'PEC (inset)', 'ogr')
mun = QgsVectorLayer(D + 'PI_Municipios_2024.shp', 'Municípios do Piauí (IBGE 2024)', 'ogr')
uf  = QgsVectorLayer(D + 'PI_UF_2024.shp', 'Limite estadual do Piauí (IBGE 2024)', 'ogr')
uf2 = QgsVectorLayer(D + 'PI_UF_2024.shp', 'Piauí (inset)', 'ogr')
for l in (uc, uc2, mun, uf, uf2):
    assert l.isValid(), l.name()

# fatos derivados dos dados (usados nos textos)
fuc = next(uc.getFeatures())
tr_uc = QgsCoordinateTransform(uc.crs(), CRS_UTM, project)
tr_uf = QgsCoordinateTransform(uf.crs(), CRS_UTM, project)
g_uc = QgsGeometry(fuc.geometry()); g_uc.transform(tr_uc)
g_uf = QgsGeometry(next(uf.getFeatures()).geometry()); g_uf.transform(tr_uf)
dist_km = g_uc.distance(g_uf) / 1000.0
area_ha = g_uc.area() / 1e4
municipios_uc = fuc['municipios']
print(f'UC: area calc {area_ha:.0f} ha | decreto {fuc["a_decr_ha"]:.1f} ha | dist. divisa PI {dist_km:.1f} km | municipios: {municipios_uc}')
print('UC bbox UTM:', g_uc.boundingBox().toString(0))

# ------------------------------------------------------------------ simbologia
uc.setRenderer(QgsSingleSymbolRenderer(fill('#4caf50', '#1b5e20', 0.7, opacity=0.65)))
uc2.setRenderer(QgsSingleSymbolRenderer(fill('#d50000', '#7f0000', 0.3)))
mun.setRenderer(QgsSingleSymbolRenderer(fill('#f4efe2', '#8a8a8a', 0.28)))
uf.setRenderer(QgsSingleSymbolRenderer(fill('0,0,0,0', '#000000', 0.9, style='no', outline_style='dash')))
uf2.setRenderer(QgsSingleSymbolRenderer(fill('#e6e2d6', '#333333', 0.35)))

label_layer(mun, 'NM_MUN', text_format(7.5, '#2b2b2b', buffer=0.8), wrap=14, priority=4)

# rótulos de apoio: mapa principal (UTM) e inset (geográfico)
rot_main = write_points('rotulos_mapa_principal', CRS_UTM,
                        [('PIAUÍ', 222400, 9662500), ('CEARÁ', 262000, 9612000)], first=True)
rot_uc = write_points('rotulo_uc', CRS_UTM, [(fuc['Nome_UC'], 268500, 9634500)], first=False)
c_pi = g_uf.poleOfInaccessibility(500)[0].asPoint()
tr_back = QgsCoordinateTransform(CRS_UTM, CRS_GEO, project)
c_pi_geo = tr_back.transform(c_pi)
rot_inset = write_points('rotulos_inset', CRS_GEO,
                         [('PIAUÍ', c_pi_geo.x(), c_pi_geo.y()),
                          ('MARANHÃO', -44.7, -5.2), ('CEARÁ', -40.0, -4.3),
                          ('BAHIA', -44.2, -10.75), ('Oceano Atlântico', -41.5, -2.45)],
                        first=False)
g_uf_geo = QgsGeometry(next(uf.getFeatures()).geometry())
b = QgsGeometry(g_uf_geo.constGet().boundary()); b.convertToMultiType()
print('boundary PI:', QgsWkbTypes.displayString(b.wkbType()), 'comprimento km (UTM):', round(QgsGeometry(b).transform(tr_uf) or 0, 0))
divisa = write_lines('limite_estadual_pi', uf.crs(), b, 'Limite estadual do Piauí (IBGE 2024)')
divisa.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple(
    {'color': '#000000', 'width': '0.9', 'line_style': 'dash', 'capstyle': 'flat'})))
label_layer(rot_main, 'nome', text_format(10, '#555555', bold=True, spacing=1.5, buffer=0.8),
            placement=Qgis.LabelPlacement.OverPoint, priority=10)
label_layer(rot_uc, 'nome', text_format(10, '#0b3d17', bold=True, buffer=1.0), wrap=16,
            placement=Qgis.LabelPlacement.OverPoint, priority=10)
for l in (rot_main, rot_inset, rot_uc):
    l.setRenderer(QgsNullSymbolRenderer())   # só rótulo, sem marcador
label_layer(rot_inset, 'nome', text_format(6, '#444444', bold=True, buffer=0.6),
            placement=Qgis.LabelPlacement.OverPoint, priority=10)

# árvore de camadas (ordem de cima para baixo)
root = project.layerTreeRoot()
for l in (rot_uc, rot_main, uc, divisa, mun, uc2, rot_inset, uf2):
    project.addMapLayer(l, False); root.addLayer(l)

# ------------------------------------------------------------------ layout A4 retrato
layout = QgsPrintLayout(project)
layout.initializeDefaults()
layout.setName('Mapa PE Carnaúbas A4')
page = layout.pageCollection().page(0)
page.setPageSize('A4', QgsLayoutItemPage.Portrait)

# --- título
add_label(layout, 'Parque Estadual das Carnaúbas e municípios do entorno',
          10, 6, 190, 10, size=15, bold=True, halign=Qt.AlignHCenter, valign=Qt.AlignVCenter)
add_label(layout, 'Municípios de Granja e Viçosa do Ceará (CE), junto à divisa com o Piauí',
          10, 15, 190, 6, size=9.5, italic=True, halign=Qt.AlignHCenter, valign=Qt.AlignVCenter, color='#333333')

# --- mapa principal
MX, MY, MW, MH = 20, 29, 175, 161
mapa = QgsLayoutItemMap(layout)
mapa.setCrs(CRS_UTM)
mapa.setLayers([rot_uc, rot_main, uc, divisa, mun]); mapa.setKeepLayerSet(True)
mapa.setBackgroundEnabled(True); mapa.setBackgroundColor(QColor('#ffffff'))
mapa.setFrameEnabled(True); mapa.setFrameStrokeWidth(QgsLayoutMeasurement(0.4))
layout.addLayoutItem(mapa)
mapa.attemptSetSceneRect(QRectF(MX, MY, MW, MH))
mapa.zoomToExtent(QgsRectangle(212600, 9600800, 291400, 9673200))
mapa.setScale(450000)
SCALE = int(round(mapa.scale()))
print('Escala do mapa principal:', SCALE, '| extent:', mapa.extent().toString(0))

# grade geográfica com moldura zebrada e coordenadas nas 4 bordas
grid = QgsLayoutItemMapGrid('Grade geográfica', mapa)
mapa.grids().addGrid(grid)
grid.setEnabled(True)
grid.setCrs(CRS_GEO)
grid.setIntervalX(0.25); grid.setIntervalY(0.25)      # 15'
grid.setStyle(QgsLayoutItemMapGrid.Cross); grid.setCrossLength(2.0)
grid.setLineSymbol(QgsLineSymbol.createSimple({'color': '#404040', 'width': '0.25'}))
grid.setFrameStyle(QgsLayoutItemMapGrid.Zebra)
grid.setFrameWidth(1.6); grid.setFramePenSize(0.3)
grid.setFrameFillColor1(QColor('#000000')); grid.setFrameFillColor2(QColor('#ffffff'))
grid.setAnnotationEnabled(True)
grid.setAnnotationFormat(QgsLayoutItemMapGrid.DegreeMinutePadded)
grid.setAnnotationPrecision(0)
grid.setAnnotationTextFormat(text_format(7, '#000000'))
grid.setAnnotationFrameDistance(1.0)
for side in (QgsLayoutItemMapGrid.Left, QgsLayoutItemMapGrid.Right,
             QgsLayoutItemMapGrid.Top, QgsLayoutItemMapGrid.Bottom):
    grid.setAnnotationPosition(QgsLayoutItemMapGrid.OutsideMapFrame, side)
    grid.setAnnotationDisplay(QgsLayoutItemMapGrid.ShowAll, side)
grid.setAnnotationDirection(QgsLayoutItemMapGrid.Vertical, QgsLayoutItemMapGrid.Left)
grid.setAnnotationDirection(QgsLayoutItemMapGrid.Vertical, QgsLayoutItemMapGrid.Right)
grid.setAnnotationDirection(QgsLayoutItemMapGrid.Horizontal, QgsLayoutItemMapGrid.Top)
grid.setAnnotationDirection(QgsLayoutItemMapGrid.Horizontal, QgsLayoutItemMapGrid.Bottom)

# --- seta de norte (SVG nativo do QGIS), canto superior direito do mapa
svg = None
for p in QgsApplication.svgPaths():
    for r, ds, fs in os.walk(p):
        for f in sorted(fs):
            if 'northarrow' in f.lower() and f.lower().endswith('.svg'):
                if svg is None or '04' in f:
                    svg = os.path.join(r, f)
print('SVG norte:', svg)
if svg:
    norte = QgsLayoutItemPicture(layout)
    norte.setPicturePath(svg, QgsLayoutItemPicture.FormatSVG)
    norte.setResizeMode(QgsLayoutItemPicture.Zoom)
    norte.setLinkedMap(mapa); norte.setNorthMode(QgsLayoutItemPicture.GridNorth)
    norte.setBackgroundEnabled(True); norte.setBackgroundColor(QColor(255, 255, 255, 200))
    layout.addLayoutItem(norte)
    norte.attemptSetSceneRect(QRectF(MX + MW - 17, MY + 3, 13, 16))
else:
    add_label(layout, 'N\n▲', MX + MW - 14, MY + 3, 10, 12, size=12, bold=True, halign=Qt.AlignHCenter)

def mm_of(E, N):
    ex = mapa.extent()
    return (MX + (E - ex.xMinimum()) / ex.width() * MW, MY + (ex.yMaximum() - N) / ex.height() * MH)
cx, cy = mm_of(262000, 9612000)
add_label(layout, 'malha municipal cearense\nnão disponível nesta base', cx - 25, cy + 4, 50, 8, size=6.5,
          italic=True, halign=Qt.AlignHCenter, color='#666666')

# ------------------------------------------------------------------ faixa inferior
BY = 199
# --- inset de localização
add_label(layout, 'Localização em relação ao Piauí', 10, BY - 1, 60, 5, size=8, bold=True)
inset = QgsLayoutItemMap(layout)
inset.setCrs(CRS_UTM)
inset.setLayers([rot_inset, uc2, uf2]); inset.setKeepLayerSet(True)
inset.setBackgroundEnabled(True); inset.setBackgroundColor(QColor('#ffffff'))
inset.setFrameEnabled(True); inset.setFrameStrokeWidth(QgsLayoutMeasurement(0.3))
layout.addLayoutItem(inset)
inset.attemptSetSceneRect(QRectF(10, BY + 4, 58, 83))
e = g_uf.boundingBox(); e.grow(60000); e.setXMaximum(e.xMaximum() + 90000)
inset.zoomToExtent(e)
ov = QgsLayoutItemMapOverview('Área do mapa principal', inset)
inset.overviews().addOverview(ov)
ov.setLinkedMap(mapa); ov.setEnabled(True)
ov.setFrameSymbol(fill('255,0,0,60', '#d50000', 0.5))
print('Escala inset:', int(inset.scale()))

# --- legenda
legenda = QgsLayoutItemLegend(layout)
legenda.setLinkedMap(mapa)
legenda.setTitle('Legenda')
LEG_NOMES = ((uc, 'Parque Estadual das Carnaúbas|(CEUC/SEMA-CE, 2006)'),
             (mun, 'Municípios do Piauí|(IBGE, 2024)'),
             (divisa, 'Limite estadual Piauí / Ceará|(IBGE, 2024)'))
# o rótulo de um nó "embutido no pai" é fixado quando o nó de legenda é criado -> definir ANTES do clone
for l, nome in LEG_NOMES:
    root.findLayer(l.id()).setCustomProperty('legend/title-label', nome)
legenda.setAutoUpdateModel(False)
lroot = legenda.model().rootGroup()
for l in (rot_main, rot_inset, rot_uc, uc2, uf2):
    n = lroot.findLayer(l.id())
    if n: lroot.removeChildNode(n)
for l, nome in LEG_NOMES:
    n = lroot.findLayer(l.id())
    if n:
        n.setCustomProperty('legend/title-label', nome)
        legenda.model().refreshLayerLegend(n)   # recria os nós de legenda com o rótulo novo
legenda.setStyleFont(QgsLegendStyle.Title, qfont(9, True))
legenda.setStyleFont(QgsLegendStyle.Subgroup, qfont(8, True))
legenda.setStyleFont(QgsLegendStyle.SymbolLabel, qfont(7.5))
legenda.setSymbolWidth(8); legenda.setSymbolHeight(4)
legenda.setBoxSpace(1.5); legenda.setWrapString('|')
legenda.setFrameEnabled(False)
layout.addLayoutItem(legenda)
legenda.attemptSetSceneRect(QRectF(72, BY - 1, 58, 40))
legenda.adjustBoxSize()
LY = BY + 34   # rect() ainda não foi recalculado nesta fase; altura real ~30 mm
print('altura legenda mm:', round(legenda.rect().height(), 1), '| LY =', round(LY, 1))

# --- barra de escala + escala numérica
sb = QgsLayoutItemScaleBar(layout)
sb.setLinkedMap(mapa); sb.setStyle('Single Box')
sb.setUnits(Qgis.DistanceUnit.Kilometers); sb.setMapUnitsPerScaleBarUnit(1.0)  # unidades já em km
sb.setUnitLabel('km'); sb.setNumberOfSegments(4); sb.setNumberOfSegmentsLeft(0)
sb.setUnitsPerSegment(5.0); sb.setHeight(2.2); sb.setLabelBarSpace(1.0)
sb.setTextFormat(text_format(7))
layout.addLayoutItem(sb); sb.update()
sb.attemptSetSceneRect(QRectF(73, LY, 55, 10))
add_label(layout, f'Escala numérica 1:{SCALE:,}'.replace(',', '.'), 72, LY + 10, 58, 5, size=7.5, bold=True)
add_label(layout, 'Projeção UTM, fuso 24 S\nDatum SIRGAS 2000 (EPSG:31984)\nGrade de coordenadas geográficas (graus e minutos)',
          72, LY + 16, 58, 14, size=7, color='#222222')
add_label(layout, f'Elaboração: Maria Silva\n{datetime.date.today().strftime("%d/%m/%Y")}',
          72, LY + 31, 58, 10, size=7.5, bold=True, color='#222222')

# --- fontes, autoria, nota metodológica
municipios_txt = municipios_uc.replace(';', ' e') if municipios_uc else 'Granja e Viçosa do Ceará'
area_dec = f'{fuc["a_decr_ha"]:,.0f}'.replace(',', '.')
notas = (
    'FONTES DOS DADOS\n'
    '• Malha municipal e limite estadual: IBGE, Malha Municipal Digital 2024 (SIRGAS 2000).\n'
    f'• Limite da UC: CEUC – CEDIB/COBIO/SEMA (Ceará); Decreto Estadual nº 28.154, de 15/02/2006; '
    f'área decretada {area_dec} ha; CNUC {fuc["Cod_CNUC"]}.\n\n'
    'NOTA\n'
    f'Segundo a base da CEUC/SEMA, o Parque situa-se nos municípios de {municipios_txt} (CE), '
    f'integralmente fora do Piauí, a cerca de {dist_km:.0f} km da divisa estadual. Como a malha municipal '
    'do Ceará não foi fornecida, apenas os municípios piauienses do entorno são representados; '
    'a área em branco a leste da divisa corresponde ao território cearense.'
)
add_label(layout, notas, 134, BY - 1, 66, 88, size=6.8, color='#111111')

# moldura fina da página / rodapé
add_label(layout, 'Mapa elaborado em QGIS 3.34 (PyQGIS).', 10, 289, 190, 5, size=6, italic=True,
          halign=Qt.AlignRight, color='#555555')

project.layoutManager().addLayout(layout)

# ------------------------------------------------------------------ exportação
exp = QgsLayoutExporter(layout)
st = QgsLayoutExporter.ImageExportSettings(); st.dpi = 200
res = exp.exportToImage(BASE + '/mapa.png', st)
print('Export PNG:', 'OK' if res == QgsLayoutExporter.Success else f'ERRO {res}')
ok = project.write(BASE + '/projeto.qgz')
print('Projeto salvo:', ok)

# ------------------------------------------------------------------ verificação do projeto
p2 = QgsProject()
print('Reabrir projeto:', p2.read(BASE + '/projeto.qgz'))
print('  camadas:', [(l.name(), l.isValid()) for l in p2.mapLayers().values()])
print('  layouts:', [(lt.name(), len(list(lt.items()))) for lt in p2.layoutManager().printLayouts()])
qgs.exitQgis()
