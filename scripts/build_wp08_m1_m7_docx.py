import copy
import os
import tempfile
import zipfile
import xml.etree.ElementTree as ET

SOURCE_DOCX = r"datos_y_modelos\db\econometrics_db\Tabla_nuevas_estimaciones_FE_DK_Model5_final.docx"
DOCX = r"datos_y_modelos\db\econometrics_db\Tabla_nuevas_estimaciones_FE_DK_Modelos1_7_final.docx"

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ET.register_namespace("w", W)

def qn(tag):
    return f"{{{W}}}{tag}"

def add_run(p, text, size=17, bold=False):
    r = ET.SubElement(p, qn("r"))
    rpr = ET.SubElement(r, qn("rPr"))

    fonts = ET.SubElement(rpr, qn("rFonts"))
    fonts.set(qn("ascii"), "Times New Roman")
    fonts.set(qn("hAnsi"), "Times New Roman")

    sz = ET.SubElement(rpr, qn("sz"))
    sz.set(qn("val"), str(size))
    szcs = ET.SubElement(rpr, qn("szCs"))
    szcs.set(qn("val"), str(size))

    if bold:
        ET.SubElement(rpr, qn("b"))

    parts = str(text).split("\n")
    for i, part in enumerate(parts):
        if i:
            ET.SubElement(r, qn("br"))
        t = ET.SubElement(r, qn("t"))
        t.text = part

def make_cell(text, width, align="center", size=17, bold=False, shade=None):
    tc = ET.Element(qn("tc"))

    tcpr = ET.SubElement(tc, qn("tcPr"))
    tcw = ET.SubElement(tcpr, qn("tcW"))
    tcw.set(qn("w"), str(width))
    tcw.set(qn("type"), "dxa")

    valign = ET.SubElement(tcpr, qn("vAlign"))
    valign.set(qn("val"), "center")

    if shade:
        shd = ET.SubElement(tcpr, qn("shd"))
        shd.set(qn("fill"), shade)

    p = ET.SubElement(tc, qn("p"))
    ppr = ET.SubElement(p, qn("pPr"))

    jc = ET.SubElement(ppr, qn("jc"))
    jc.set(qn("val"), align)

    spacing = ET.SubElement(ppr, qn("spacing"))
    spacing.set(qn("before"), "0")
    spacing.set(qn("after"), "0")
    spacing.set(qn("line"), "200")
    spacing.set(qn("lineRule"), "auto")

    add_run(p, text, size=size, bold=bold)
    return tc

def make_row(values, widths, header=False, section=False):
    tr = ET.Element(qn("tr"))
    for i, value in enumerate(values):
        align = "left" if i == 0 else "center"
        shade = "E7E6E6" if header else ("F2F2F2" if section else None)
        tc = make_cell(
            value,
            widths[i],
            align=align,
            size=17,
            bold=(header or section),
            shade=shade,
        )
        tr.append(tc)
    return tr

def replace_paragraph_text(p, text, size=16):
    for child in list(p):
        p.remove(child)

    ppr = ET.SubElement(p, qn("pPr"))
    spacing = ET.SubElement(ppr, qn("spacing"))
    spacing.set(qn("before"), "80")
    spacing.set(qn("after"), "0")

    add_run(p, text, size=size, bold=False)

# ---------------------------------------------------------------------------
# Canonical results
# M1-M5: commit 6c82f2a
# M6-M7: wp08_brazil_3m_di_robustness.do
# ---------------------------------------------------------------------------

headers = [
    "Variable",
    "M1\nNER baseline",
    "M2\nRER",
    "M3\nSovereign",
    "M4\nLocal macro/RER",
    "M5\nNo issue size",
    "M6\nDI + Fed 3M",
    "M7\nDI; Fed omitted",
]

rows = [
    ["VIX",
     "1.9528**\n(0.8985)", "2.0921**\n(0.9008)", "0.9841\n(0.9831)",
     "1.8616**\n(0.8393)", "2.2104**\n(0.9520)", "1.3730\n(0.8811)",
     "0.2915\n(0.8827)"],

    ["Fed 3M Forward",
     "6.5803\n(11.0441)", "6.3219\n(10.8476)", "3.9733\n(7.4317)",
     "9.1231\n(10.6935)", "8.1139\n(11.1828)", "15.4899\n(9.9405)", ""],

    ["USD/BRL NER",
     "-27.4614\n(24.7518)", "", "", "", "-27.3060\n(25.9460)", "", ""],

    ["USD/BRL RER",
     "", "-0.7736\n(0.5369)", "", "-0.8216\n(0.5362)", "", "", ""],

    ["Brazil 3M DI",
     "", "", "", "", "", "-0.9267\n(3.2342)", "-1.5153\n(3.2061)"],

    ["GDP growth (YoY)",
     "3.8329*\n(2.2802)", "3.5882\n(2.2692)", "", "2.4085\n(2.2275)",
     "5.2236**\n(2.6063)", "4.8653*\n(2.6840)", "4.9289*\n(2.6284)"],

    ["Gross government debt (% GDP)",
     "3.3816\n(2.3077)", "3.3171\n(2.2928)", "", "4.7199**\n(1.9969)",
     "4.1278*\n(2.3877)", "4.9013**\n(2.2543)", "2.6201\n(1.8348)"],

    ["Sovereign Risk (BRL)",
     "-0.6159\n(0.4007)", "-0.6056\n(0.3975)", "-0.8013**\n(0.3912)",
     "", "-0.6131\n(0.4053)", "", ""],

    ["Operating cash flow / total assets",
     "-0.1794\n(0.3098)", "-0.1691\n(0.3090)", "-0.1486\n(0.3094)",
     "-0.1867\n(0.3104)", "-0.1831\n(0.3384)", "-0.2321\n(0.3451)",
     "-0.2491\n(0.3522)"],

    ["Issue amount / total assets",
     "10.4020***\n(1.5459)", "10.4092***\n(1.5484)", "11.0991***\n(1.5683)",
     "10.4072***\n(1.5578)", "", "", ""],

    ["Total debt / EBITDA",
     "-0.0736\n(0.0572)", "-0.0755\n(0.0576)", "-0.0850\n(0.0614)",
     "-0.0765\n(0.0583)", "-0.1603**\n(0.0728)", "-0.1555**\n(0.0715)",
     "-0.1558**\n(0.0684)"],

    ["Residual maturity (years, BUS/252)",
     "-24.9354*\n(13.2726)", "-23.8445**\n(11.6975)", "-26.2731***\n(5.1443)",
     "-20.8664*\n(11.2171)", "-18.2803\n(13.1826)", "-6.0339\n(8.4623)",
     "-16.8635***\n(4.7620)"],

    ["Within R-squared",
     "0.1982", "0.1995", "0.1834", "0.1971", "0.1489", "0.1440", "0.1366"],

    ["Observations",
     "4,648", "4,648", "4,648", "4,648", "4,648", "4,648", "4,648"],

    ["Number of bonds",
     "103", "103", "103", "103", "103", "103", "103"],

    ["rho",
     "0.7825", "0.7832", "0.7973", "0.7851", "0.4654", "0.5484", "0.4630"],
]

spec_rows = [
    ["Specification indicators", "", "", "", "", "", "", ""],
    ["Fed 3M included", "Yes", "Yes", "Yes", "Yes", "Yes", "Yes", "No"],
    ["NER included", "Yes", "No", "No", "No", "Yes", "No", "No"],
    ["RER included", "No", "Yes", "No", "Yes", "No", "No", "No"],
    ["Sovereign spread included", "Yes", "Yes", "Yes", "No", "Yes", "No", "No"],
    ["Issue size included", "Yes", "Yes", "Yes", "Yes", "No", "No", "No"],
    ["Brazil 3M DI included", "No", "No", "No", "No", "No", "Yes", "Yes"],
]

# Landscape A4 usable width:
# 16838 - 792 - 792 = 15254 twips
widths = [2654] + [1800] * 7

zin = zipfile.ZipFile(SOURCE_DOCX, "r")
root = ET.fromstring(zin.read("word/document.xml"))

# ElementTree may discard namespace-prefix declarations used only by
# mc:Ignorable, causing Word to reject the resulting DOCX. Removing this
# compatibility hint is safe for this simple table document.
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
root.attrib.pop(f"{{{MC}}}Ignorable", None)

# Rebuild the output in A4 landscape while preserving the original margins.
sect = root.find(f".//{qn('sectPr')}")
pg = sect.find(qn("pgSz"))
pg.set(qn("w"), "16838")
pg.set(qn("h"), "11906")
pg.set(qn("orient"), "landscape")

body = root.find(qn("body"))
old_table = body.find(qn("tbl"))

old_tblpr = old_table.find(qn("tblPr"))
new_table = ET.Element(qn("tbl"))

if old_tblpr is not None:
    new_tblpr = copy.deepcopy(old_tblpr)
    new_table.append(new_tblpr)
else:
    new_tblpr = ET.SubElement(new_table, qn("tblPr"))

# Force fixed-width layout.
layout = new_tblpr.find(qn("tblLayout"))
if layout is None:
    layout = ET.SubElement(new_tblpr, qn("tblLayout"))
layout.set(qn("type"), "fixed")

tblw = new_tblpr.find(qn("tblW"))
if tblw is None:
    tblw = ET.SubElement(new_tblpr, qn("tblW"))
tblw.set(qn("w"), str(sum(widths)))
tblw.set(qn("type"), "dxa")

grid = ET.SubElement(new_table, qn("tblGrid"))
for width in widths:
    col = ET.SubElement(grid, qn("gridCol"))
    col.set(qn("w"), str(width))

new_table.append(make_row(headers, widths, header=True))

for row in rows:
    new_table.append(make_row(row, widths))

for i, row in enumerate(spec_rows):
    new_table.append(make_row(row, widths, section=(i == 0)))

table_index = list(body).index(old_table)
body.remove(old_table)
body.insert(table_index, new_table)

# Put a compact title in the existing empty paragraph before the table.
for element in list(body)[:table_index]:
    if element.tag == qn("p"):
        replace_paragraph_text(
            element,
            "FE-DK estimates and Brazil 3M DI robustness (Models 1-7)",
            size=20,
        )
        jc = element.find(f"./{qn('pPr')}/{qn('jc')}")
        if jc is None:
            jc = ET.SubElement(element.find(qn("pPr")), qn("jc"))
        jc.set(qn("val"), "center")
        first_run = element.find(qn("r"))
        if first_run is not None:
            rpr = first_run.find(qn("rPr"))
            if rpr is not None:
                ET.SubElement(rpr, qn("b"))
        break

note = (
    "Notes: Bond fixed effects in all specifications. Driscoll-Kraay standard "
    "errors (maximum lag = 4) in parentheses. All models use the same 4,648 "
    "observations and 103 bonds. M2 replaces nominal USD/BRL with the bilateral "
    "real exchange-rate index. M3 is sovereign-risk focused and excludes local "
    "GDP, public debt and FX controls. M4 uses RER and local macro controls but "
    "excludes sovereign spread. M5 repeats M1 excluding issue amount / total "
    "assets. M6 is the Brazil 3M DI robustness specification: it includes Brazil 3M DI and "
    "nominal Fed 3M while omitting FX, sovereign spread and issue size. M7 repeats "
    "M6 omitting Fed 3M. Brazil 3M DI is the 3M point of "
    "Bloomberg YCSW0089 Index and is not a literal forward-starting SELIC rate. "
    "rho is obtained from the corresponding conventional fixed-effects regression. "
    "* p < 0.10, ** p < 0.05, *** p < 0.01."
)

for p in body.findall(qn("p")):
    text = "".join(t.text or "" for t in p.findall(f".//{qn('t')}"))
    if text.startswith("Notes:"):
        replace_paragraph_text(p, note, size=16)
        break

fd, tmp = tempfile.mkstemp(suffix=".docx")
os.close(fd)

zout = zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED)
for info in zin.infolist():
    if info.filename == "word/document.xml":
        zout.writestr(
            info,
            ET.tostring(root, encoding="utf-8", xml_declaration=True),
        )
    else:
        zout.writestr(info, zin.read(info.filename))

zout.close()
zin.close()
os.replace(tmp, DOCX)

print("Builder completed:", DOCX)
