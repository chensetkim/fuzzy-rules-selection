# Generates reports/figures/cars-framework.{svg,png,pdf} (run: python3 reports/figures/make_cars_framework.py)
# PNG and PDF are rendered with headless Chrome/Chromium; the SVG is always written.
import os, shutil, subprocess, tempfile
W, H = 1400, 810
C = {  # column x, accent, light fill
    1: (40, "#1d4ed8", "#eff6ff"), 2: (380, "#15803d", "#f0fdf4"),
    3: (720, "#c2410c", "#fff7ed"), 4: (1060, "#6d28d9", "#f5f3ff")}
out = []
def esc(s): return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def box(col, y, title, sub=None, h=58, w=300, strong=False, dx=0):
    x, acc, light = C[col]; x += dx
    fill = acc if strong else light
    tc = "#ffffff" if strong else "#111827"
    sc = "#e5e7eb" if strong else "#374151"
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{fill}" stroke="{acc}" stroke-width="1.6"/>')
    lines = [sub] if isinstance(sub, str) else (sub or [])
    ty = y + h / 2 - (len(lines) * 7) + (5 if not lines else 0)
    out.append(f'<text x="{x + w/2}" y="{ty + 4}" text-anchor="middle" class="t" fill="{tc}">{esc(title)}</text>')
    for i, l in enumerate(lines):
        out.append(f'<text x="{x + w/2}" y="{ty + 22 + i*15}" text-anchor="middle" class="s" fill="{sc}">{esc(l)}</text>')
def header(col, label):
    x, acc, _ = C[col]
    out.append(f'<rect x="{x}" y="78" width="300" height="38" rx="8" fill="{acc}"/>')
    out.append(f'<text x="{x+150}" y="103" text-anchor="middle" class="h">{esc(label)}</text>')
def arrow(points, color="#4b5563", dashed=False, label=None, lx=0, ly=0, anchor="middle"):
    d = "M" + " L".join(f"{x},{y}" for x, y in points)
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.8"{dash} marker-end="url(#ah)"/>')
    if label:
        out.append(f'<text x="{lx}" y="{ly}" text-anchor="{anchor}" class="l">{esc(label)}</text>')
def down(col, y1, y2, dx=150):
    x = C[col][0] + dx
    arrow([(x, y1), (x, y2 - 2)])

out.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="Noto Sans, DejaVu Sans, Arial, sans-serif">')
out.append('''<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#4b5563"/></marker>
<style>.t{font-size:15px;font-weight:700}.s{font-size:12px}.h{font-size:15px;font-weight:700;fill:#ffffff}.l{font-size:12px;fill:#374151;font-style:italic}.ttl{font-size:21px;font-weight:700;fill:#111827}.st{font-size:13px;fill:#4b5563}</style></defs>''')
out.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
out.append('<text x="40" y="38" class="ttl">CARS: data-driven fuzzy rule selection for FERMAD</text>')
out.append('<text x="40" y="60" class="st">No hand-crafted rules at any stage; every score uses the mote\'s own integer arithmetic.</text>')

header(1, "1  Data preparation"); header(2, "2  Candidate rule pool")
header(3, "3  Multi-objective selection"); header(4, "4  Choice, evaluation, deployment")

# column 1 (two-line boxes, pitch 84)
c1 = [("Cooja serial logs", ["one run per attack type × environment", "× attacker count × round"]),
      ("Parse and validate", ["FUZZRID,DET lines → evidence v1..v7", "range-checked 0–100"]),
      ("Label", ["attack iff the observed node is an attacker", "and t ≥ that attacker's own launch"]),
      ("Clean", ["drop attacker-reported events and", "attacker events before launch"]),
      ("Weighted rows", ["identical (vector, label) events", "→ one row × event count"]),
      ("Split", ["primary 70/30 · round-holdout ·", "leave-one-scenario-out"])]
for i, (t, sub) in enumerate(c1):
    box(1, 140 + 84 * i, t, sub, h=66)
    if i: down(1, 140 + 84 * i - 18, 140 + 84 * i)

# column 2
c2 = [("Bounded enumeration", ["every antecedent that uses", "1 to 4 of the 7 features"]),
      ("Wang–Mendel cells", ["the 200 most occupied", "full 7-term grid cells"]),
      ("Consequents", ["z = nearest of {0, 25, 50, 75, 100}", "to 100 × certainty grade"]),
      ("Pruning", ["support ≥ 0.005 and", "|confidence − 0.5| ≥ 0.15"])]
for i, (t, sub) in enumerate(c2):
    box(2, 140 + 84 * i, t, sub, h=66)
    if i: down(2, 140 + 84 * i - 18, 140 + 84 * i)
box(2, 476, "Candidate pool P", ["generated from the", "training data only"], h=66, strong=True)
down(2, 458, 476)
box(2, 600, "Fuzzy inference (firmware-exact)", ["L / M / H memberships, integer 0–100", "min t-norm → AC = ⌊Σ w·z / (1 + Σ w)⌋", "attack if AC ≥ 65"], h=96)

# column 3 (narrower boxes, loop on the right)
box(3, 140, "Chromosome", ["one bit per rule in P:", "bit j = 1 ⇔ rule j is in base S"], h=66, w=260)
box(3, 224, "Random initial population", ["sparse random subsets,", "no seeding"], h=66, w=260)
box(3, 308, "Evaluate each base S", ["minimise  1 − F1,  FPR,  |S| / 35", "subject to  12 ≤ |S| ≤ 35"], h=66, w=260, strong=True)
box(3, 400, "Next generation", ["selection, uniform crossover,", "bit-flip mutation"], h=66, w=260)
box(3, 506, "Pareto front", ["non-dominated", "rule bases"], h=66, w=260)
down(3, 206, 224, dx=130); down(3, 290, 308, dx=130); down(3, 374, 400, dx=130)
arrow([(980, 433), (1000, 433), (1000, 341), (982, 341)], label="× 250", lx=1004, ly=392, anchor="start")
arrow([(850, 466), (850, 504)], label="after the last generation", lx=858, ly=490, anchor="start")

# column 4
c4 = [("Knee pick", ["weights 0.6 / 0.3 / 0.1 on the", "training objectives only"], False),
      ("Selected rule base S*", ["12–35 readable", "IF–THEN rules"], True),
      ("Evaluation on held-out data", ["F1, FPR, recall, precision,", "compared with the data ceiling"], False),
      ("Integer C export", ["rule block for", "fuzzrid_fuzzy_infer_ac()"], False),
      ("Z1 / MSP430 mote", ["FERMAD detector,", "same integer arithmetic"], True)]
for i, (t, sub, st) in enumerate(c4):
    box(4, 140 + 84 * i, t, sub, h=66, strong=st)
    if i: down(4, 140 + 84 * i - 18, 140 + 84 * i)

# cross-column arrows
arrow([(340, 593), (360, 593), (360, 257), (378, 257)], label="training rows", lx=364, ly=215, anchor="start")
arrow([(680, 509), (692, 509), (692, 173), (718, 173)])
arrow([(680, 648), (704, 648), (704, 341), (718, 341)], dashed=True, label="fitness", lx=712, ly=640, anchor="start")
arrow([(980, 539), (1036, 539), (1036, 173), (1058, 173)])
arrow([(190, 626), (190, 780), (1048, 780), (1048, 341), (1058, 341)],
      label="test rows: never used for selection, scored with the same fuzzy inference", lx=640, ly=772)
out.append("</svg>")
HERE = os.path.dirname(os.path.abspath(__file__))
svg = os.path.join(HERE, "cars-framework.svg")
open(svg, "w").write("\n".join(out))
print(f"written {svg}")

chrome = next((shutil.which(c) for c in ("google-chrome", "chromium", "chromium-browser")
               if shutil.which(c)), None)
if chrome is None:
    print("no Chrome/Chromium found: PNG and PDF not rendered")
else:
    base = [chrome, "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars"]
    png = os.path.join(HERE, "cars-framework.png")
    subprocess.run(base + ["--force-device-scale-factor=2", f"--window-size={W},{H}",
                           f"--screenshot={png}", "file://" + svg],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"written {png} ({2 * W}x{2 * H})")
    # PDF: a page exactly the figure's size, no margins, vector text
    with tempfile.TemporaryDirectory() as tmp:
        html = os.path.join(tmp, "page.html")
        open(html, "w").write(
            f"<!doctype html><html><head><meta charset='utf-8'><style>@page{{size:{W}px {H}px;margin:0}}"
            f"html,body{{margin:0;padding:0;overflow:hidden}}svg{{display:block}}</style></head><body>{open(svg).read()}</body></html>")
        pdf = os.path.join(HERE, "cars-framework.pdf")
        subprocess.run(base + ["--no-pdf-header-footer", "--print-to-pdf-no-header",
                               f"--print-to-pdf={pdf}", "file://" + html],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"written {pdf}")
