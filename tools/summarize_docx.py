"""Print a concise, human-readable skeleton of an inspected docx JSON."""
from __future__ import annotations
import argparse, json


def runfmt(p):
    out = []
    for r in p.get("runs", []):
        flags = []
        if r.get("bold"): flags.append("B")
        if r.get("italic"): flags.append("I")
        if r.get("underline"): flags.append("U")
        if r.get("size_pt"): flags.append(f"{r['size_pt']:g}pt")
        if r.get("font"): flags.append(r["font"])
        if r.get("color"): flags.append("#" + r["color"])
        if flags:
            out.append(f"[{'|'.join(flags)}]{r['text'][:40]!r}")
    return " ".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("--full-tables", action="store_true")
    args = ap.parse_args()
    d = json.load(open(args.json, encoding="utf-8"))
    print(f"== {d['path']}")
    for s in d["sections"]:
        print(f"SECTION {s['index']}: {s['page_width_in']:.2f}x{s['page_height_in']:.2f} in, "
              f"margins L{s['left_margin_in']:.2f} R{s['right_margin_in']:.2f} T{s['top_margin_in']:.2f} B{s['bottom_margin_in']:.2f}, "
              f"start={s['start_type']}, header={s['header_text']}, footer={s['footer_text']}")
    print(f"PARTS: {d['parts']}")
    for i, b in enumerate(d["blocks"]):
        if b["type"] == "paragraph":
            extra = []
            if b.get("has_section_break"): extra.append("SECTION-BREAK")
            if b.get("breaks"): extra.append("BREAKS=" + ",".join(b["breaks"]))
            if b.get("numbering"): extra.append("NUM=" + str(b["numbering"]))
            if b.get("page_break_before"): extra.append("PAGEBREAK-BEFORE")
            print(f"{i:03d} P [{b['style']}] align={b['alignment']} {' '.join(extra)} {b['text']!r}")
            if b.get("runs"):
                f = runfmt(b)
                if f: print(f"      runs: {f}")
        else:
            print(f"{i:03d} TABLE [{b['style']}] {b['rows']}x{b['cols']} grid={b['grid_cols_twips']} borders={b['borders']}")
            for ri, row in enumerate(b["cells"]):
                vals = []
                for c in row:
                    txt = c["text"].replace("\n", " / ")
                    if len(txt) > 90: txt = txt[:87] + "..."
                    vals.append(txt)
                print(f"      r{ri}: " + " | ".join(repr(v) for v in vals))
                if ri >= 7 and not args.full_tables:
                    if len(b["cells"]) > 8: print(f"      ... {len(b['cells'])-8} more rows")
                    break


if __name__ == "__main__":
    main()
