"""Normas de figura das revistas: larguras, altura, fonte mínima, formatos, resolução.

Cada revista tem as suas, e a instrução aos autores manda. Um perfil diz o
que o compositor precisa saber para a figura sair dentro delas, e o que a
auditoria confere (CART083). Todo valor de perfil vem da página oficial da
revista ou da editora, com o endereço e a data em que foi lido; o que a
página não diz fica ``None``, e o compositor usa o padrão dele.

Para uma revista fora da tabela, ``journal_profile`` recebe os mesmos campos,
tirados da instrução aos autores dela.

Sem PyQGIS de propósito: são decisões editoriais, verificáveis em CI.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .params import ParameterError

#: Colunas que um perfil pode declarar, da mais estreita à mais larga.
COLUMN_NAMES = ("single", "one_and_half", "double")
#: Apelidos aceitos em ``journal_column``.
COLUMN_ALIASES = {
    "simple": "single", "simples": "single", "uma": "single", "1": "single", "one": "single",
    "dupla": "double", "2": "double", "duas": "double", "full": "double", "page": "double", "two": "double",
    "1.5": "one_and_half", "1,5": "one_and_half", "meia": "one_and_half", "one_half": "one_and_half",
}
#: Formatos que o compositor exporta.
EXPORT_FORMATS = ("pdf", "svg", "png", "tif", "tiff", "jpg", "jpeg", "eps")
#: Tolerância (mm) entre a largura da figura e a da coluna da revista.
WIDTH_TOLERANCE_MM = 1.0


@dataclass(frozen=True)
class JournalProfile:
    """O que uma revista pede das figuras. ``None`` é "a página não diz"."""

    key: str
    name: str
    widths_mm: dict[str, float]
    max_height_mm: float | None = None
    #: Revistas que dão uma faixa ou uma área máxima, e não colunas fixas:
    #: qualquer largura entre as duas vale.
    min_width_mm: float | None = None
    max_width_mm: float | None = None
    #: Linha mais fina aceita (mm).
    min_line_mm: float | None = None
    min_font_pt: float | None = None
    fonts: tuple[str, ...] = ()
    formats: tuple[str, ...] = ()
    vector_preferred: bool = False
    line_art_dpi: int | None = None
    halftone_dpi: int | None = None
    combination_dpi: int | None = None
    colour: str | None = None
    panel_labels: str | None = None
    title_in_caption: bool | None = None
    alt_text: bool = False
    sources: tuple[str, ...] = ()
    checked: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["fonts"] = list(self.fonts)
        data["formats"] = list(self.formats)
        data["sources"] = list(self.sources)
        data["notes"] = list(self.notes)
        return data

    def raster_dpi(self, has_halftone: bool = False) -> int | None:
        """A resolução de um mapa exportado em raster.

        Um mapa é traço (linhas, texto); com relevo sombreado ou mapa de base
        por baixo, é combinação de traço e meio-tom. Vale a resolução que a
        revista dá para o caso, e a mais exigente das declaradas quando ela
        não separa.
        """
        if has_halftone and self.combination_dpi:
            return self.combination_dpi
        if not has_halftone and self.line_art_dpi:
            return self.line_art_dpi
        values = [v for v in (self.combination_dpi, self.line_art_dpi, self.halftone_dpi) if v]
        return max(values) if values else None

    def accepts_width(self, width_mm: float) -> bool:
        """A largura vale nesta revista: é uma das colunas, ou está na faixa que ela dá."""
        if self.max_width_mm is not None:
            return (self.min_width_mm or 0.0) - WIDTH_TOLERANCE_MM <= width_mm <= self.max_width_mm + WIDTH_TOLERANCE_MM
        if not self.widths_mm:
            return True
        return any(abs(width_mm - w) <= WIDTH_TOLERANCE_MM for w in self.widths_mm.values())

    def width_text(self) -> str:
        """As larguras da revista, para mensagens."""
        if self.max_width_mm is not None:
            low = f"{self.min_width_mm:g}" if self.min_width_mm else "0"
            return f"de {low} a {self.max_width_mm:g} mm"
        return ", ".join(f"{w:g} mm ({n})" for n, w in self.widths_mm.items()) or "largura não declarada"


#: Perfis lidos nas páginas oficiais. A chave é o que vai em ``journal``.
#: Onde a página não diz, o campo fica vazio e vale o padrão do SIGMAI; onde
#: duas páginas da mesma revista discordam, a nota diz qual foi usada.
JOURNAL_PROFILES: dict[str, JournalProfile] = {
    "biodiversity_informatics": JournalProfile(
        key="biodiversity_informatics",
        name="Biodiversity Informatics",
        widths_mm={"single": 88.0, "double": 180.0},
        max_height_mm=230.0,
        formats=("pdf", "eps", "tiff", "tif", "jpeg", "jpg"),
        vector_preferred=True,
        line_art_dpi=600,
        halftone_dpi=350,
        panel_labels="A",
        title_in_caption=True,
        alt_text=True,
        sources=(
            "https://journals.ku.edu/jbi/about/submissions — \"Illustrations, when published, will be reduced to a "
            "maximum of 88 mm (single column) or 180 mm in width and 230 mm in length; calculate line thickness and "
            "symbol sizes accordingly.\"",
            "Evolution, Author guidelines (Oxford Academic), que a Biodiversity Informatics adota — \"Final figure "
            "files should be provided in one of the following formats: jpeg, jpg, tiff, eps or pdf.\"; \"minimum "
            "resolution for printed line art: 600 dpi\"; \"Images of maps, charts, graphs, and diagrams are best "
            "rendered digitally as geometric forms called vector graphics.\"; \"Each panel should be labelled with "
            "a letter (A, B, C, D, etc.) in the upper-left corner of each panel.\"; \"Figure titles and legends "
            "should be included in the main text file --they should not be included in the image file.\"; alt "
            "text \"directly under the figure legend for the relevant figure, preceded by `Alt text:'\".",
        ),
        checked="2026-10-23",
        notes=("Fonte mínima não declarada: vale o piso do SIGMAI (6 pt).",
               "Traço complexo ou fino: 1.200 dpi, pela mesma norma."),
    ),
    "elsevier": JournalProfile(
        key="elsevier",
        name="Elsevier",
        widths_mm={"single": 90.0, "one_and_half": 140.0, "double": 190.0},
        min_font_pt=7.0,
        fonts=("Arial", "Helvetica", "Times", "Courier", "Symbol"),
        formats=("eps", "pdf", "tiff", "tif", "jpeg", "jpg"),
        vector_preferred=True,
        line_art_dpi=1000,
        combination_dpi=500,
        halftone_dpi=300,
        min_line_mm=0.035,
        colour="RGB",
        title_in_caption=True,
        sources=(
            "https://www.elsevier.com/about/policies-and-standards/author/artwork-and-media-instructions/artwork-sizing"
            " — tabela: single column 90 mm, 1.5 column 140 mm, double column 190 mm; \"a finished, printed size of 7 "
            "pt for normal text\"; \"300 DPI for halftone images; 500 DPI for combination art; 1000 DPI for line art.\"",
            ".../artwork-overview — \"Elsevier recommends that only EPS, PDF, TIFF or JPEG formats are used for "
            "electronic artwork.\"",
            ".../artwork-faq — \"recommended line width of 0.25 pt (absolute minimum line width is 0.1 pt)\"",
            ".../artwork-formats-checklist — \"My color images are provided in the preferred RGB colorspace\"",
        ),
        checked="2026-11-07",
        notes=("Norma geral da editora: algumas revistas têm instruções próprias, que vencem.",
               "Altura máxima não declarada.", "Sobrescrito e subscrito: 6 pt no mínimo."),
    ),
    "springer": JournalProfile(
        key="springer",
        name="Springer",
        widths_mm={"single": 84.0, "double": 174.0},
        max_height_mm=234.0,
        min_font_pt=8.0,
        fonts=("Helvetica", "Arial"),
        formats=("eps", "tiff", "tif"),
        vector_preferred=True,
        line_art_dpi=1200,
        combination_dpi=600,
        halftone_dpi=300,
        min_line_mm=0.1,
        colour="RGB",
        panel_labels="a",
        title_in_caption=True,
        sources=(
            "https://link.springer.com/journal/10531/submission-guidelines (Artwork and Illustrations Guidelines, texto "
            "padrão das revistas Springer) — \"For large-sized journals the figures should be 84 mm (for "
            "double-column text areas), or 174 mm (for single-column text areas) wide and not higher than 234 mm.\"; "
            "\"usually about 2–3 mm (8–12 pt)\"; \"All lines should be at least 0.1 mm (0.3 pt) wide.\"; \"For "
            "vector graphics, the preferred format is EPS; for halftones, please use TIFF format.\"; line art "
            "\"minimum resolution of 1200 dpi\"; \"Combination artwork should have a minimum resolution of 600 dpi.\";"
            " \"Figure parts should be denoted by lowercase letters (a, b, c, etc.).\"; \"Do not include titles or "
            "captions within your illustrations.\"",
        ),
        checked="2026-11-07",
        notes=("Revistas de formato pequeno: 119 mm de largura e até 195 mm de altura; cada revista pode mudar o texto.",
               "PDF não aparece na seção de arte: exporte em EPS (traço) ou TIFF."),
    ),
    "nature": JournalProfile(
        key="nature",
        name="Nature",
        widths_mm={"single": 89.0, "one_and_half": 120.0, "double": 183.0},
        max_height_mm=247.0,
        min_font_pt=5.0,
        fonts=("Helvetica", "Arial"),
        formats=("pdf", "eps", "tiff", "tif", "jpeg", "jpg"),
        vector_preferred=True,
        halftone_dpi=300,
        min_line_mm=0.088,
        colour="RGB",
        panel_labels="a",
        title_in_caption=True,
        sources=(
            "https://www.nature.com/nature/for-authors/final-submission — \"standard figure sizes are 89 mm wide "
            "(single column) and 183 mm wide (double column)\"; \"column-and-a-half where necessary (120–136 mm)\"; "
            "\"The full depth of a Nature page is 247 mm.\"; \"minimum text size should be 5 pt\"; \"Line weights and "
            "strokes should be set between 0.25 and 1 pt at the final size\"; line drawings in \"Adobe Illustrator "
            "(AI), Postscript, Vector EPS or PDF format\"; \"labelled with 8 pt bold, upright (not italic) a, b, c.\"",
            "https://www.nature.com/nature/for-authors/formatting-guide — \"text, including keys to symbols, should be "
            "provided in the legend rather than on the figure itself.\"",
        ),
        checked="2026-11-07",
        notes=("As páginas da Nature discordam: o formatting guide diz 90 e 180 mm; usado o final-submission (89 e 183).",
               "Revista Nature; outras do grupo Nature Portfolio têm páginas próprias.",
               "A Nature pede a chave dos símbolos na legenda do texto, e não na figura: considere legend_placement='none'.",
               "\"Please do not rasterize line art or text\": exporte em PDF.",
               "247 mm é a altura da página inteira, e não um limite declarado para figura."),
    ),
    "wiley": JournalProfile(
        key="wiley",
        name="Wiley",
        widths_mm={},
        min_width_mm=80.0,
        max_width_mm=180.0,
        formats=("pdf", "png", "tiff", "tif"),
        vector_preferred=True,
        line_art_dpi=600,
        halftone_dpi=300,
        title_in_caption=True,
        sources=(
            "https://authors.wiley.com/author-resources/Journal-Authors/Prepare/manuscript-preparation-guidelines.html/"
            "figure-preparation.html — \"Figures are created at a size between 80mm and 180mm in width and between "
            "300dpi and 600dpi.\"; \"When in doubt, submit a PDF.\"; \"Figure legends should be included as a separate "
            "section in the main text file.\"",
        ),
        checked="2026-11-07",
        notes=("Muitas revistas Wiley têm guias de arte próprios (PDF), com fonte e linha mínimas: confira o da revista.",),
    ),
    "plos_one": JournalProfile(
        key="plos_one",
        name="PLOS ONE",
        widths_mm={"single": 132.0, "double": 190.5},
        min_width_mm=66.8,
        max_width_mm=190.5,
        max_height_mm=222.3,
        min_font_pt=8.0,
        fonts=("Arial", "Times", "Symbol"),
        formats=("tiff", "tif", "eps"),
        halftone_dpi=300,
        colour="RGB",
        panel_labels="(A)",
        title_in_caption=True,
        sources=(
            "https://journals.plos.org/plosone/s/figures — \"Width: 789 – 2250 pixels (at 300 dpi)\" (66,8 a 190,5 mm);"
            " \"make it no wider than 5.2 inches (13.2 cm)\"; altura máxima 22,23 cm; \"Use only Arial, Times, or "
            "Symbol font in 8-12 point.\"; \"TIFF or EPS only.\"; \"RGB (8 bit/channel) or grayscale only.\"; \"(A) or "
            "(a)\"; \"Do not include author names, article title, or figure number/title/caption within figure files.\"",
        ),
        checked="2026-11-07",
        notes=("Resolução: \"no greater than 300-600 dpi\"; abaixo de 300 sai borrada.",
               "Só TIFF ou EPS.",
               "13,2 cm é a coluna de texto; 19,05 cm, a página inteira."),
    ),
    "zookeys": JournalProfile(
        key="zookeys",
        name="ZooKeys",
        widths_mm={},
        max_width_mm=167.0,
        max_height_mm=242.0,
        formats=("eps", "svg", "tiff", "tif", "png", "jpeg", "jpg"),
        halftone_dpi=300,
        panel_labels="A",
        title_in_caption=True,
        sources=(
            "https://zookeys.pensoft.net/about — \"printed in A4 paper size with the maximum printing area of 167 mm × "
            "242 mm\"; \"EPS (preferred format for diagrams) | TIFF (at least 300dpi resolution, with LZW compression) "
            "| PNG … | JPEG … | GIF | BMP | SVG\"; \"Figure parts: Use capital letters in bold.\"; \"Caption as text "
            "(not as part of the image)\"",
        ),
        checked="2026-11-07",
        notes=("PDF vale só para árvores filogenéticas e cladogramas; para mapas, SVG, TIFF ou PNG.",),
    ),
    "check_list": JournalProfile(
        key="check_list",
        name="Check List",
        widths_mm={"single": 81.0, "double": 166.0},
        formats=("eps", "jpeg", "jpg", "tiff", "tif", "png"),
        halftone_dpi=300,
        title_in_caption=True,
        sources=(
            "https://checklist.pensoft.net/about — \"(width of 1 column = 81 mm, 2 columns = 166 mm)\"; \"EPS "
            "(preferred format for diagrams)\"; \"TIFF, JPEG, and PSD files need only be 300 pixels per inch, at the "
            "size they will appear on the page\"; \"Caption as text (not as part of the image)\"; mapas com \"A simple "
            "north arrow\" e \"A scale bar (do not indicate scale as a ratio…)\", coordenadas nas margens.",
        ),
        checked="2026-11-07",
        notes=("Mapa de distribuição obrigatório, com norte simples, barra de escala (sem escala numérica) e "
               "coordenadas nas margens.", "Letras dos painéis em negrito; maiúscula ou minúscula não é dito."),
    ),
    "biodiversity_data_journal": JournalProfile(
        key="biodiversity_data_journal",
        name="Biodiversity Data Journal",
        widths_mm={},
        formats=("jpeg", "jpg", "png"),
        sources=(
            "https://arpha.pensoft.net/tips/Figures — \"supported are JPEG, GIF & PNG graphics file formats of size up "
            "to 15 MB\" (https://bdj.pensoft.net/about não traz normas de figura)",
        ),
        checked="2026-11-07",
        notes=("Largura, resolução e fonte não declaradas: passe figure_width_mm.", "Arquivo de até 15 MB."),
    ),
    "mdpi_diversity": JournalProfile(
        key="mdpi_diversity",
        name="Diversity (MDPI)",
        widths_mm={},
        formats=("png", "jpeg", "jpg", "tiff", "tif"),
        line_art_dpi=600,
        halftone_dpi=600,
        colour="RGB",
        sources=(
            "https://www.mdpi.com/journal/diversity/instructions — \"All figures should be of a high quality "
            "(preferably no less than 600 dpi) in PNG, JPEG or TIFF formats.\"; \"(RGB at 8-bit per channel)\"; "
            "\"figures should contain only English text\"",
        ),
        checked="2026-11-07",
        notes=("Largura não declarada: passe figure_width_mm.", "Só texto em inglês na figura (map_language='en').",
               "\"There should be no editable parts in the images\": exporte em raster."),
    ),
    "taylor_francis": JournalProfile(
        key="taylor_francis",
        name="Taylor & Francis",
        widths_mm={},
        fonts=("Times", "Helvetica", "Arial", "Symbol"),
        formats=("tiff", "tif", "jpeg", "jpg", "eps"),
        line_art_dpi=1200,
        combination_dpi=600,
        halftone_dpi=300,
        min_line_mm=0.106,
        panel_labels="(a)",
        title_in_caption=True,
        sources=(
            "https://authorservices.taylorandfrancis.com/publishing-your-research/making-your-submission/"
            "submit-electronic-artwork/ — \"Line art or monochrome images – 1200dpi | Combination images "
            "(photographs and labelling) – 600dpi\"; \"Any lines are a minimum of 0.3pt.\"; \"preferred formats: JPEG "
            "| TIFF\"; EPS \"is the recommended format for line art\"; \"Images supplied in PDF format will be "
            "converted\"; \"Do not include captions and figure titles with your image files.\"; \"Images do not "
            "contain any layers or transparent objects.\"",
        ),
        checked="2026-11-07",
        notes=("Largura de cada revista: \"Check the individual journal's page\"; passe figure_width_mm.",
               "Sem camadas nem transparência: exporte em TIFF, que achata a figura."),
    ),
    "zootaxa": JournalProfile(
        key="zootaxa",
        name="Zootaxa",
        widths_mm={},
        max_width_mm=170.0,
        max_height_mm=250.0,
        formats=("tiff", "tif"),
        line_art_dpi=600,
        halftone_dpi=300,
        sources=(
            "https://www.mapress.com/zt/about/submissions — \"the journal has a matter size of 25 cm by 17 cm\"; "
            "\"figures in TIFF (line drawing scanned at 600 dpi and half tone at 300 dpi\"",
            "https://mapress.com/zootaxa/imaging/index.html — \"The maximum size of illustrations in Zootaxa is 17 x "
            "25 cm\"; \"Line art generated in vector graphics programs … must be submitted as .tif or .bmp files.\"",
        ),
        checked="2026-11-07",
        notes=("As páginas discordam: o Q&A (https://www.mapress.com/zt/qna) diz 14 x 20 cm para pranchas; usado 17 x 25 "
               "cm, que duas páginas dão.", "Impressa em preto e branco (cor só on-line): confira a figura em cinza.",
               "Legendas depois das referências."),
    ),
    "zoological_journal_linnean_society": JournalProfile(
        key="zoological_journal_linnean_society",
        name="Zoological Journal of the Linnean Society",
        widths_mm={},
        max_width_mm=168.0,
        max_height_mm=225.0,
        formats=("tiff", "tif", "jpeg", "jpg", "pdf", "eps"),
        vector_preferred=True,
        line_art_dpi=800,
        combination_dpi=800,
        halftone_dpi=300,
        panel_labels="A",
        title_in_caption=True,
        alt_text=True,
        sources=(
            "https://academic.oup.com/zoolinnean/pages/General_Instructions — \"The maximum dimensions of published "
            "figures are 168 × 225 mm.\"; \"saved uncompressed as TIFF, JPEG, editable PDF, PPT, DOC or EPS files\"; "
            "\"If any labelling or line drawings are embedded in the file then the resolution must be a minimum of "
            "800 dpi.\"; \"Use upper case letters for subdivisions (e.g. Figure 1A-D)\"; alt text \"directly under the "
            "figure caption ... preceded by 'Alt text:'\"",
        ),
        checked="2026-11-07",
        notes=("Fora as letras dos painéis, todo texto da figura em minúsculas.",),
    ),
    "systematic_biology": JournalProfile(
        key="systematic_biology",
        name="Systematic Biology",
        widths_mm={},
        fonts=("Geneva", "Helvetica", "Arial"),
        formats=("tiff", "tif", "eps", "pdf", "jpeg", "jpg"),
        vector_preferred=True,
        halftone_dpi=600,
        min_line_mm=0.176,
        colour="CMYK",
        panel_labels="a)",
        title_in_caption=True,
        alt_text=True,
        sources=(
            "https://academic.oup.com/sysbio/pages/General_Instructions — \"each figure will be rendered in either "
            "single or double column width\"; \"minimum stroke weight of 0.5pts\"; \"Color figures to appear in print "
            "should be submitted in CMYK color format.\"; \"Captions should not be placed on the figures.\"",
            "https://academic.oup.com/sysbio/pages/Manuscript_Preparation_Guidelines — \"strongly prefer figures in "
            "vector format\"; \"the resolution should be 600 ppi\"",
        ),
        checked="2026-11-07",
        notes=("Larguras de coluna sem valor em mm: passe figure_width_mm.",
               "Letras dos painéis no canto superior esquerdo, como \"a)\"; \"No box should be drawn around a graph\"."),
    ),
    "biota_neotropica": JournalProfile(
        key="biota_neotropica",
        name="Biota Neotropica",
        widths_mm={},
        fonts=("Arial", "Helvetica"),
        formats=("jpeg", "jpg", "png", "tiff", "tif"),
        halftone_dpi=300,
        panel_labels="a",
        title_in_caption=True,
        sources=(
            "https://www.scielo.br/journal/bn/about/ — \"any bitmap file format (e.g., JPG, PNG, TIFF, GIF, BMP)\"; "
            "\"at least 300 dpi\"; \"text contained in figures should use sans-serif fonts, such as Arial or "
            "Helvetica\"; \"(e.g., Figure 1a, Figure 1b)\"; \"Figures should not contain captions.\"",
        ),
        checked="2026-11-07",
        notes=("Largura não declarada: passe figure_width_mm.", "Só bitmap: exporte em TIFF ou PNG."),
    ),
    "zoologia": JournalProfile(
        key="zoologia",
        name="Zoologia (Curitiba)",
        widths_mm={},
        max_width_mm=167.0,
        max_height_mm=242.0,
        formats=("eps", "svg", "tiff", "tif", "png", "jpeg", "jpg"),
        halftone_dpi=300,
        panel_labels="A",
        title_in_caption=True,
        sources=(
            "https://zoologia.pensoft.net/about — \"The journal is printed in A4 paper size with the maximum printing "
            "area of 167 mm × 242 mm.\"; \"TIFF (at least 300dpi resolution, with LZW compression)\"; \"Figure parts: "
            "Use capital letters in bold.\"; \"Caption as text (not as part of the image)\"; \"No image border\"",
        ),
        checked="2026-11-07",
        notes=("Fundo branco ou transparente, sem moldura na imagem.",
               "Mapa do Google: atribuição visível (\"Map data 2019 (C) Google\")."),
    ),
    "papeis_avulsos_de_zoologia": JournalProfile(
        key="papeis_avulsos_de_zoologia",
        name="Papéis Avulsos de Zoologia",
        widths_mm={},
        formats=("tiff", "tif", "jpeg", "jpg"),
        halftone_dpi=300,
        panel_labels="A",
        title_in_caption=True,
        sources=(
            "https://www.scielo.br/journal/paz/about/ — \"“.PSD”, “.TIF”, “.JPG” “.PCX”, “.GIF” or “.BMP” for "
            "figures\"; \"(300 DPI minimum)\"; \"identified by a capital letter\"; \"The figures will be printed in "
            "black and white but maintained in color in the final PDF file.\"",
        ),
        checked="2026-11-07",
        notes=("Largura não declarada: passe figure_width_mm.", "Impressa em preto e branco: confira a figura em cinza.",
               "Letras dos painéis, quando possível, no canto inferior esquerdo."),
    ),
}

#: Nomes pelos quais a revista pode ser pedida.
JOURNAL_ALIASES = {
    "bi": "biodiversity_informatics", "jbi": "biodiversity_informatics",
    "plos": "plos_one", "plosone": "plos_one",
    "checklist": "check_list",
    "bdj": "biodiversity_data_journal",
    "diversity": "mdpi_diversity", "mdpi": "mdpi_diversity",
    "t&f": "taylor_francis", "taylor and francis": "taylor_francis", "taylor & francis": "taylor_francis",
    "tandf": "taylor_francis",
    "zjls": "zoological_journal_linnean_society",
    "zoological journal of the linnean society": "zoological_journal_linnean_society",
    "sysbio": "systematic_biology", "syst biol": "systematic_biology",
    "biota": "biota_neotropica",
    "zoologia curitiba": "zoologia",
    "paz": "papeis_avulsos_de_zoologia", "papeis avulsos": "papeis_avulsos_de_zoologia",
    "papéis avulsos de zoologia": "papeis_avulsos_de_zoologia",
    "springer nature": "springer", "nature portfolio": "nature",
}


def _key(text: str) -> str:
    return " ".join(str(text).strip().lower().replace("-", " ").replace("_", " ").split())


def find_journal(name: str) -> JournalProfile | None:
    """O perfil da revista pelo nome, pela chave ou por um apelido; ``None`` se não há."""
    wanted = _key(name)
    if not wanted:
        return None
    for key, profile in JOURNAL_PROFILES.items():
        if wanted in (_key(key), _key(profile.name)):
            return profile
    alias = JOURNAL_ALIASES.get(wanted)
    return JOURNAL_PROFILES.get(alias) if alias else None


def _number(data: dict[str, Any], name: str, low: float, high: float) -> float | None:
    value = data.get(name)
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ParameterError(f"journal_profile.{name} precisa ser um número; recebido {value!r}.") from exc
    if not low <= number <= high:
        raise ParameterError(f"journal_profile.{name}={number:g} fora de {low:g} a {high:g}.")
    return number


def profile_from_dict(data: Any) -> JournalProfile:
    """Perfil de uma revista fora da tabela, com os campos de ``JournalProfile``.

    ``widths_mm`` é obrigatório (ao menos "single" ou "double"); o resto é
    opcional. Recusa campo desconhecido, para que um erro de digitação não
    vire uma norma ignorada em silêncio.
    """
    if not isinstance(data, dict):
        raise ParameterError("journal_profile precisa ser um objeto com widths_mm e as demais normas da revista.")
    known = set(JournalProfile.__dataclass_fields__) - {"key"}
    unknown = sorted(set(data) - known)
    if unknown:
        raise ParameterError(f"journal_profile tem campos desconhecidos: {', '.join(unknown)}. Aceitos: "
                             + ", ".join(sorted(known)) + ".")
    raw_widths = data.get("widths_mm") or {}
    if not isinstance(raw_widths, dict) or (not raw_widths and data.get("max_width_mm") is None):
        raise ParameterError("journal_profile precisa de widths_mm, como {\"single\": 84, \"double\": 174}, ou de "
                             "max_width_mm (e min_width_mm) quando a revista dá uma faixa.")
    widths: dict[str, float] = {}
    for name, value in raw_widths.items():
        column = COLUMN_ALIASES.get(_key(name).replace(" ", "_"), _key(name).replace(" ", "_"))
        if column not in COLUMN_NAMES:
            raise ParameterError(f"journal_profile.widths_mm: coluna {name!r} desconhecida. Use "
                                 + ", ".join(COLUMN_NAMES) + ".")
        width = _number({"w": value}, "w", 30.0, 600.0)
        widths[column] = float(width)  # type: ignore[arg-type]
    formats = tuple(str(f).strip().lower().lstrip(".") for f in (data.get("formats") or ()))
    colour = data.get("colour")
    if colour is not None and str(colour).upper() not in ("RGB", "CMYK"):
        raise ParameterError("journal_profile.colour aceita 'RGB' ou 'CMYK'.")
    labels = data.get("panel_labels")
    if labels is not None and str(labels) not in PANEL_LABEL_STYLES:
        raise ParameterError("journal_profile.panel_labels aceita 'A', 'a', '(a)', '(A)', 'a)' ou 'A)'.")

    def ints(name: str) -> int | None:
        number = _number(data, name, 72.0, 2400.0)
        return int(number) if number is not None else None

    return JournalProfile(
        key="custom",
        name=str(data.get("name") or "revista informada").strip(),
        widths_mm=widths,
        max_height_mm=_number(data, "max_height_mm", 30.0, 600.0),
        min_width_mm=_number(data, "min_width_mm", 30.0, 600.0),
        max_width_mm=_number(data, "max_width_mm", 30.0, 600.0),
        min_line_mm=_number(data, "min_line_mm", 0.01, 2.0),
        min_font_pt=_number(data, "min_font_pt", 4.0, 14.0),
        fonts=tuple(str(f) for f in (data.get("fonts") or ())),
        formats=formats,
        vector_preferred=bool(data.get("vector_preferred", False)),
        line_art_dpi=ints("line_art_dpi"),
        halftone_dpi=ints("halftone_dpi"),
        combination_dpi=ints("combination_dpi"),
        colour=str(colour).upper() if colour is not None else None,
        panel_labels=str(labels) if labels is not None else None,
        title_in_caption=None if data.get("title_in_caption") is None else bool(data["title_in_caption"]),
        alt_text=bool(data.get("alt_text", False)),
        sources=tuple(str(s) for s in (data.get("sources") or ())),
        checked=str(data.get("checked") or ""),
        notes=tuple(str(n) for n in (data.get("notes") or ())),
    )


def resolve_journal(params: dict[str, Any]) -> JournalProfile | None:
    """O perfil pedido: ``journal_profile`` (revista fora da tabela) ou ``journal`` (nome ou chave)."""
    if params.get("journal_profile") is not None:
        return profile_from_dict(params["journal_profile"])
    name = params.get("journal")
    if name in (None, ""):
        return None
    profile = find_journal(str(name))
    if profile is None:
        known = ", ".join(f"'{key}' ({p.name})" for key, p in JOURNAL_PROFILES.items())
        raise ParameterError(
            f"journal={name!r} não está na tabela de normas do SIGMAI ({known}). Leia a instrução aos autores da "
            "revista e passe journal_profile com widths_mm, max_height_mm, min_font_pt, formats e line_art_dpi; "
            "o que a revista não disser fica de fora.")
    return profile


#: Estilos de letra de painel aceitos, como a revista os escreve.
PANEL_LABEL_STYLES = ("A", "a", "(a)", "(A)", "a)", "A)")
#: Estilo numa figura sem revista: maiúscula em negrito, a mais comum nas revistas de biologia.
DEFAULT_PANEL_LABEL_STYLE = "A"


def panel_label(index: int, style: str | None = None) -> str:
    """A letra do painel ``index`` (0 = o primeiro) no estilo da revista: "A", "b", "(c)", "d)"."""
    style = style if style in PANEL_LABEL_STYLES else DEFAULT_PANEL_LABEL_STYLE
    letter = "abcdefghijklmnopqrstuvwxyz"[max(0, int(index)) % 26]
    if any(c.isupper() for c in style):
        letter = letter.upper()
    if style.startswith("("):
        return f"({letter})"
    if style.endswith(")"):
        return f"{letter})"
    return letter


def column_width(profile: JournalProfile, column: str | None) -> tuple[str, float]:
    """A coluna pedida (padrão: a mais estreita) e a largura dela nesta revista.

    Revista que só dá a área máxima (ZooKeys, Zootaxa): sem coluna pedida, a
    largura máxima, e a figura pode ser composta mais estreita com
    figure_width_mm.
    """
    if not profile.widths_mm and profile.max_width_mm is not None and not column:
        return "max", profile.max_width_mm
    if not profile.widths_mm:
        raise ParameterError(
            f"A {profile.name} não declara largura de figura ({profile.width_text()}): cada revista da editora tem a "
            "sua. Passe figure_width_mm com a largura da instrução aos autores da revista.")
    if not column:
        name = next(name for name in COLUMN_NAMES if name in profile.widths_mm)
        return name, profile.widths_mm[name]
    wanted = _key(column).replace(" ", "_")
    name = COLUMN_ALIASES.get(wanted, wanted)
    if name not in profile.widths_mm:
        offered = ", ".join(f"{n} ({w:g} mm)" for n, w in profile.widths_mm.items())
        raise ParameterError(f"A {profile.name} não tem coluna {column!r}. Tem: {offered}.")
    return name, profile.widths_mm[name]


def check_figure(profile: JournalProfile, width_mm: float | None, height_mm: float | None,
                 smallest_font_pt: float | None, output_format: str | None, dpi: float | None,
                 has_halftone: bool = False, thinnest_line_mm: float | None = None,
                 thinnest_line_where: str = "") -> list[str]:
    """O que a figura descumpre nas normas da revista, em frases; vazio se cumpre tudo que dá para medir."""
    problems: list[str] = []
    if width_mm is not None and not profile.accepts_width(width_mm):
        problems.append(f"largura de {width_mm:.1f} mm, e a {profile.name} imprime em {profile.width_text()}")
    if height_mm is not None and profile.max_height_mm and height_mm > profile.max_height_mm + WIDTH_TOLERANCE_MM:
        problems.append(f"altura de {height_mm:.1f} mm, acima dos {profile.max_height_mm:g} mm da {profile.name}")
    if smallest_font_pt is not None and profile.min_font_pt and smallest_font_pt < profile.min_font_pt - 0.05:
        problems.append(f"texto de {smallest_font_pt:g} pt, abaixo dos {profile.min_font_pt:g} pt da {profile.name}")
    fmt = (output_format or "").lower().lstrip(".")
    if fmt and profile.formats and fmt not in profile.formats:
        problems.append(f"formato {fmt.upper()}, que a {profile.name} não aceita ("
                        + ", ".join(f.upper() for f in profile.formats) + ")")
    if thinnest_line_mm is not None and profile.min_line_mm and thinnest_line_mm < profile.min_line_mm - 0.005:
        where = f" ({thinnest_line_where})" if thinnest_line_where else ""
        problems.append(f"traço de {thinnest_line_mm:.2f} mm{where}, abaixo dos {profile.min_line_mm:g} mm da "
                        f"{profile.name}")
    wanted_dpi = profile.raster_dpi(has_halftone)
    # 1 % de folga: a largura em pixels é arredondada, e 300 dpi saíam 299,99.
    if fmt in ("png", "tif", "tiff", "jpg", "jpeg") and wanted_dpi and dpi is not None and float(dpi) < wanted_dpi * 0.99:
        problems.append(f"{float(dpi):.0f} dpi, abaixo dos {wanted_dpi} dpi que a {profile.name} pede")
    return problems
