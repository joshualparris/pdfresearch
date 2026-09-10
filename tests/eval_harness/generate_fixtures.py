import csv
import json
from pathlib import Path
import fitz  # PyMuPDF

class FixtureGenerator:
    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.doc = fitz.open()
        self.current_page = 1
        self.boundaries = []
        self.duplicates = []

    def save(self, name: str):
        self.doc.save(self.out_dir / f"{name}.pdf")
        self.doc.close()
        
        with open(self.out_dir / f"{name}_boundaries.csv", "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["before_page", "label", "case_id", "notes"])
            writer.writerows(self.boundaries)
            
        with open(self.out_dir / f"{name}_duplicates.csv", "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["page", "canonical_page", "type", "case_id"])
            writer.writerows(self.duplicates)

    def add_page(self, text: str, header: str = "", footer: str = "", font_size: int = 11, 
                 title: str = "", title_size: int = 24, draw_rect: bool = False, 
                 draw_circle: bool = False, geom_override=None) -> int:
        
        width, height = geom_override if geom_override else (595, 842)
        page = self.doc.new_page(width=width, height=height)
        y = 50
        if header:
            page.insert_text((50, y), header, fontsize=10)
            y += 40
        if title:
            page.insert_text((50, y), title, fontsize=title_size)
            y += 60
        
        for line in text.split('\n'):
            page.insert_text((50, y), line, fontsize=font_size)
            y += font_size * 1.5
            
        if footer:
            page.insert_text((50, height - 42), footer, fontsize=10)
            
        if draw_rect:
            page.draw_rect(fitz.Rect(100, 400, 300, 500), color=(1,0,0), fill=(1,0,0))
        if draw_circle:
            page.draw_circle((200, 450), 50, color=(0,0,1), fill=(0,0,1))
            
        p = self.current_page
        self.current_page += 1
        return p
        
    def add_boundary(self, page: int, label: str, case_id: str, notes: str):
        self.boundaries.append([page, label, case_id, notes])
        
    def add_duplicate(self, page: int, canonical_page: int, dup_type: str, case_id: str):
        self.duplicates.append([page, canonical_page, dup_type, case_id])

def generate_all_fixtures(out_dir: Path):
    # We will generate one combined corpus, and we could also generate individual ones if needed.
    # To keep it simple, we generate one combined synthetic corpus with all cases, 
    # since we want to test boundaries between different cases too.
    
    gen = FixtureGenerator(out_dir)
    
    # CASE 1: Chapter heading that is not a boundary
    c1_p1 = gen.add_page("Doc Start", title="Report A")
    gen.add_boundary(c1_p1, "BOUNDARY", "case_1", "Doc start")
    c1_p2 = gen.add_page("Body", header="Report A", footer="Page 2")
    gen.add_boundary(c1_p2, "CONTINUATION", "case_1", "Body")
    c1_p3 = gen.add_page("Chapter Body", header="Report A", title="Chapter 2", footer="Page 3")
    gen.add_boundary(c1_p3, "CONTINUATION", "case_1", "Chapter heading")
    
    # CASE 2: Same template/header but genuine boundary
    c2_p1 = gen.add_page("Doc B", header="COMPANY TEMPLATE", title="Report B")
    gen.add_boundary(c2_p1, "BOUNDARY", "case_2", "New report same template")
    c2_p2 = gen.add_page("Body B", header="COMPANY TEMPLATE")
    gen.add_boundary(c2_p2, "CONTINUATION", "case_2", "Body B")
    c2_p3 = gen.add_page("Doc C", header="COMPANY TEMPLATE", title="Report C")
    gen.add_boundary(c2_p3, "BOUNDARY", "case_2", "Another new report same template")
    
    # CASE 3: Same text but different embedded image/signature
    form_text = "Standard Form Application\nName: John Doe\nSign below:"
    c3_p1 = gen.add_page(form_text, draw_rect=True)
    gen.add_boundary(c3_p1, "BOUNDARY", "case_3", "Form 1")
    c3_p2 = gen.add_page(form_text, draw_circle=True)
    gen.add_boundary(c3_p2, "BOUNDARY", "case_3", "Form 2")
    gen.add_duplicate(c3_p2, c3_p1, "SAME_TEXT_VISUALLY_DISTINCT", "case_3")
    
    # CASE 4: Exact repeated page legitimately occurring twice inside one document
    c4_p1 = gen.add_page("Important Notice", title="Notice")
    gen.add_boundary(c4_p1, "BOUNDARY", "case_4", "Doc start")
    c4_p2 = gen.add_page("Important Notice", title="Notice")
    gen.add_boundary(c4_p2, "CONTINUATION", "case_4", "Repeated page in doc")
    gen.add_duplicate(c4_p2, c4_p1, "EXACT_DUPLICATE", "case_4")
    
    # CASE 5: Exact repeated whole document
    c5_p1 = gen.add_page("Doc X Start", title="Document X", footer="1")
    gen.add_boundary(c5_p1, "BOUNDARY", "case_5", "Doc X start")
    c5_p2 = gen.add_page("Doc X Body", footer="2")
    gen.add_boundary(c5_p2, "CONTINUATION", "case_5", "Doc X body")
    
    c5_p3 = gen.add_page("Doc X Start", title="Document X", footer="1")
    gen.add_boundary(c5_p3, "BOUNDARY", "case_5", "Doc X dup start")
    gen.add_duplicate(c5_p3, c5_p1, "EXACT_DUPLICATE", "case_5")
    c5_p4 = gen.add_page("Doc X Body", footer="2")
    gen.add_boundary(c5_p4, "CONTINUATION", "case_5", "Doc X dup body")
    gen.add_duplicate(c5_p4, c5_p2, "EXACT_DUPLICATE", "case_5")
    
    # CASE 6: Near-duplicate whole document with one changed footer/date
    c6_p1 = gen.add_page("Doc Y Start", title="Document Y", footer="Date: 2026-01-01")
    gen.add_boundary(c6_p1, "BOUNDARY", "case_6", "Doc Y start")
    c6_p2 = gen.add_page("Doc Y Body", footer="Date: 2026-01-01")
    gen.add_boundary(c6_p2, "CONTINUATION", "case_6", "Doc Y body")
    
    c6_p3 = gen.add_page("Doc Y Start", title="Document Y", footer="Date: 2026-02-01")
    gen.add_boundary(c6_p3, "BOUNDARY", "case_6", "Doc Y near dup start")
    gen.add_duplicate(c6_p3, c6_p1, "NEAR_DUPLICATE", "case_6")
    c6_p4 = gen.add_page("Doc Y Body", footer="Date: 2026-02-01")
    gen.add_boundary(c6_p4, "CONTINUATION", "case_6", "Doc Y near dup body")
    gen.add_duplicate(c6_p4, c6_p2, "NEAR_DUPLICATE", "case_6")
    
    # CASE 7: Blank page inside a document
    c7_p1 = gen.add_page("Doc Z", title="Document Z")
    gen.add_boundary(c7_p1, "BOUNDARY", "case_7", "Doc Z start")
    c7_p2 = gen.add_page("")
    gen.add_boundary(c7_p2, "CONTINUATION", "case_7", "Blank page inside doc")
    c7_p3 = gen.add_page("Doc Z Part 2")
    gen.add_boundary(c7_p3, "CONTINUATION", "case_7", "Doc Z continuation")
    
    # CASE 8: Blank separator between documents
    c8_p1 = gen.add_page("")
    gen.add_boundary(c8_p1, "BOUNDARY", "case_8", "Blank separator")
    c8_p2 = gen.add_page("Doc W", title="Document W")
    gen.add_boundary(c8_p2, "BOUNDARY", "case_8", "Doc W start after blank")
    
    # CASE 9: Image-only page
    c9_p1 = gen.add_page("Doc V", title="Document V")
    gen.add_boundary(c9_p1, "BOUNDARY", "case_9", "Doc V start")
    c9_p2 = gen.add_page("", draw_rect=True, draw_circle=True)
    gen.add_boundary(c9_p2, "CONTINUATION", "case_9", "Image-only page")
    
    # CASE 10: Printed page-number reset at a real boundary
    c10_p1 = gen.add_page("Doc U", footer="Page 10")
    gen.add_boundary(c10_p1, "BOUNDARY", "case_10", "Doc U end")
    c10_p2 = gen.add_page("Doc T", footer="Page 1")
    gen.add_boundary(c10_p2, "BOUNDARY", "case_10", "Doc T start with page reset")
    
    # CASE 11: Printed page-number reset inside the same source
    c11_p1 = gen.add_page("Frontmatter", footer="Page iv")
    gen.add_boundary(c11_p1, "BOUNDARY", "case_11", "Frontmatter")
    c11_p2 = gen.add_page("Chapter 1", title="Chapter 1", footer="Page 1")
    gen.add_boundary(c11_p2, "CONTINUATION", "case_11", "Page reset inside same source")
    
    # CASE 12: Genuine boundary with same geometry/fonts/header family
    c12_p1 = gen.add_page("Memo 1 Content", header="MEMO", title="Memo 1", font_size=12)
    gen.add_boundary(c12_p1, "BOUNDARY", "case_12", "Memo 1")
    c12_p2 = gen.add_page("Memo 2 Content", header="MEMO", title="Memo 2", font_size=12)
    gen.add_boundary(c12_p2, "BOUNDARY", "case_12", "Memo 2 same geometry")
    
    gen.save("combined_corpus")

if __name__ == "__main__":
    out_dir = Path(__file__).parent / "data"
    generate_all_fixtures(out_dir)
    print(f"Generated synthetic fixtures at {out_dir}")
