#!/usr/bin/env python3
"""점검서 양식(xlsx / pptx / docx / hwpx)의 글자를 위치 기준으로 읽고, 서식을 유지한 채 값만 바꾼다.

1) 읽기:   python3 doc_fill.py dump  FILE [--json]
   → 모든 텍스트 칸을 "위치<TAB>내용" 으로 출력. 위치 예시
       xlsx : 시트명!B5
       pptx : s2/sh7/r3c1  (슬라이드 2, 도형 id 7, 표 3행 1열 — 0부터)   s1/sh4/p0 (텍스트상자 문단 0)
       docx : p12          (문서 전체 문단 순번, 표 안 문단 포함)
       hwpx : Contents/section0.xml#p12

2) 수정:   python3 doc_fill.py fill  FILE  EDITS.json  OUT
   EDITS.json 형식 (배열):
     {"loc": "s2/sh7/r3c1", "new": "47 도"}                  위치로 교체
     {"loc": "Sheet1!Q5", "new": "18%", "old": "15%"}        old 를 주면 현재 값이 다를 때 건너뛰고 경고
     {"find": "2026.10.15", "replace": "2026.11.17"}          문서 전체 찾아바꾸기
     {"remove_shape": "s1/sh10"}                              (pptx) 지난달 서명 스캔 그림 등 도형 삭제
   새 값 안의 "\n" 은 문단/줄바꿈으로 들어간다(pptx·docx·hwpx 는 문단 내 줄바꿈, xlsx 는 셀 줄바꿈).

서식 보존 원칙: 문단의 첫 run(글자 묶음)에 새 글자를 넣고 나머지 run 은 비운다 → 글꼴·크기·색은 첫 run 것을 따른다.
"""
from __future__ import annotations

import copy
import json
import re
import sys
import zipfile
from pathlib import Path

# ───────────────────────── 공통 ─────────────────────────


def set_runs(runs, new: str, make_run=None) -> None:
    """runs: .text 속성을 가진 객체 리스트. 첫 run 에 값, 나머지는 빈 문자열."""
    if not runs:
        if make_run is None:
            raise ValueError("빈 문단이라 글자를 넣을 run 이 없음")
        make_run(new)
        return
    runs[0].text = new
    for r in runs[1:]:
        r.text = ""


def replace_in_runs(runs, find: str, repl: str) -> bool:
    """run 하나 안에서 끝나면 그 run 만 바꿈(서식 완전 보존). 여러 run 에 걸치면 문단 전체를 합쳐 첫 run 에."""
    hit = False
    for r in runs:
        if r.text and find in r.text:
            r.text = r.text.replace(find, repl)
            hit = True
    if hit:
        return True
    full = "".join(r.text or "" for r in runs)
    if find in full:
        set_runs(runs, full.replace(find, repl))
        return True
    return False


# ───────────────────────── XLSX ─────────────────────────


def xlsx_items(path):
    import openpyxl

    wb = openpyxl.load_workbook(path)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.value is not None and str(c.value).strip() != "":
                    yield f"{ws.title}!{c.coordinate}", str(c.value)


NS_X = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PR = "http://schemas.openxmlformats.org/package/2006/relationships"


def _col_num(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + ord(ch) - 64
    return n


def _split(coord: str):
    m = re.fullmatch(r"([A-Z]+)(\d+)", coord.upper())
    if not m:
        raise ValueError(f"셀 주소 오류: {coord}")
    return m.group(1), int(m.group(2))


def xlsx_fill(path, edits, out):
    """openpyxl 로 저장하면 머리글 로고·그림이 사라지므로 XML 을 직접 고친다 (서식·그림·인쇄설정 그대로)."""
    from lxml import etree

    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}
    X = f"{{{NS_X}}}"
    wb = etree.fromstring(data["xl/workbook.xml"])
    rels = etree.fromstring(data["xl/_rels/workbook.xml.rels"])
    rid2target = {r.get("Id"): r.get("Target") for r in rels.iter(f"{{{NS_PR}}}Relationship")}
    sheets = {}
    for sh in wb.iter(f"{X}sheet"):
        t = rid2target[sh.get(f"{{{NS_R}}}id")].lstrip("/")
        sheets[sh.get("name")] = t if t.startswith("xl/") else "xl/" + t
    trees = {}

    def tree(name):
        if name not in trees:
            trees[name] = etree.fromstring(data[name])
        return trees[name]

    sst = tree("xl/sharedStrings.xml") if "xl/sharedStrings.xml" in data else None
    sst_items = list(sst.iter(f"{X}si")) if sst is not None else []

    def cell_text(c):
        v = c.find(f"{X}v")
        if c.get("t") == "s" and v is not None:
            return "".join(sst_items[int(v.text)].itertext())
        if c.get("t") == "inlineStr":
            return "".join(c.find(f"{X}is").itertext())
        return "" if v is None else (v.text or "")

    def get_cell(sheet_xml, coord, create=True):
        col, rown = _split(coord)
        sd = sheet_xml.find(f"{X}sheetData")
        row = next((r for r in sd.findall(f"{X}row") if int(r.get("r")) == rown), None)
        if row is None:
            if not create:
                return None
            row = etree.Element(f"{X}row", r=str(rown))
            after = [r for r in sd.findall(f"{X}row") if int(r.get("r")) < rown]
            (after[-1].addnext(row) if after else sd.insert(0, row))
        for c in row.findall(f"{X}c"):
            if c.get("r") == coord.upper():
                return c
        if not create:
            return None
        c = etree.Element(f"{X}c", r=coord.upper())
        before = [x for x in row.findall(f"{X}c") if _col_num(_split(x.get("r"))[0]) < _col_num(col)]
        (before[-1].addnext(c) if before else row.insert(0, c))
        return c

    for e in edits:
        if "loc" in e:
            sheet, coord = e["loc"].rsplit("!", 1)
            if sheet not in sheets:
                warn(f"시트 없음: {sheet}")
                continue
            c = get_cell(tree(sheets[sheet]), coord)
            if not check_old(e, cell_text(c)):
                continue
            for ch in list(c):
                c.remove(ch)  # 기존 값·수식 제거 (스타일 s 속성은 유지)
            val = to_number(e["new"])
            if isinstance(val, (int, float)):
                c.attrib.pop("t", None)
                etree.SubElement(c, f"{X}v").text = str(val)
            else:
                c.set("t", "inlineStr")
                t = etree.SubElement(etree.SubElement(c, f"{X}is"), f"{X}t")
                t.text = val
                t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        else:
            n = 0
            for si in sst_items:  # 공유 문자열 (같은 문자열 쓰는 모든 칸에 적용됨)
                n += replace_in_runs([_HwpRun(t) for t in si.iter(f"{X}t")], e["find"], e["replace"])
            for name in sheets.values():
                for isel in tree(name).iter(f"{X}is"):
                    n += replace_in_runs([_HwpRun(t) for t in isel.iter(f"{X}t")], e["find"], e["replace"])
            report_find(e, n)

    for name, root in trees.items():
        data[name] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    # 수식 결과 다시 계산하도록
    if any("loc" in e for e in edits):
        calc = wb.find(f"{X}calcPr")
        if calc is None:
            calc = etree.SubElement(wb, f"{X}calcPr")
        calc.set("fullCalcOnLoad", "1")
        data["xl/workbook.xml"] = etree.tostring(wb, xml_declaration=True, encoding="UTF-8", standalone=True)
    write_zip(infos, data, out)


def write_zip(infos, data, out):
    with zipfile.ZipFile(out, "w") as zo:
        for info in sorted(infos, key=lambda i: i.filename != "mimetype"):
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED
            zi.external_attr = info.external_attr
            zo.writestr(zi, data[info.filename])


def to_number(v):
    """'18%' 같은 표시용 문자열은 그대로 두고, 순수 숫자만 숫자로."""
    if isinstance(v, str) and re.fullmatch(r"-?\d+(\.\d+)?", v.strip()):
        return float(v) if "." in v else int(v)
    return v


# ───────────────────────── PPTX ─────────────────────────


def pptx_walk(prs):
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    def shapes(container):
        for sh in container:
            if sh.shape_type == MSO_SHAPE_TYPE.GROUP:
                yield from shapes(sh.shapes)
            else:
                yield sh

    for si, slide in enumerate(prs.slides, 1):
        for sh in shapes(slide.shapes):
            base = f"s{si}/sh{sh.shape_id}"
            if sh.has_table if hasattr(sh, "has_table") else False:
                for ri, row in enumerate(sh.table.rows):
                    for ci, cell in enumerate(row.cells):
                        if cell.is_spanned:
                            continue
                        yield f"{base}/r{ri}c{ci}", cell.text_frame
            elif getattr(sh, "has_text_frame", False) and sh.has_text_frame:
                for pi, p in enumerate(sh.text_frame.paragraphs):
                    yield f"{base}/p{pi}", p


def pptx_text(obj):
    return obj.text if hasattr(obj, "text") else ""


def pptx_big_pictures(prs):
    """슬라이드 80% 이상을 덮는 그림 = 지난달 서명본 스캔일 가능성 큼 → 값을 바꿔도 화면에 안 보임."""
    for si, slide in enumerate(prs.slides, 1):
        for sh in slide.shapes:
            if sh.shape_type == 13 and sh.width and sh.height:
                cover = (sh.width * sh.height) / (prs.slide_width * prs.slide_height)
                if cover >= 0.8:
                    yield f"s{si}/sh{sh.shape_id}", slide, sh, cover


def pptx_items(path):
    from pptx import Presentation

    prs = Presentation(path)
    for loc, _slide, _sh, cover in pptx_big_pictures(prs):
        yield loc, f"[그림이 슬라이드의 {cover:.0%} 를 덮음 — 지난달 서명 스캔본일 수 있음. 지우려면 {{\"remove_shape\": \"{loc}\"}}]"
    for loc, obj in pptx_walk(prs):
        t = pptx_text(obj)
        if t.strip():
            yield loc, t


def pptx_set(obj, new: str):
    """obj: 표 셀 text_frame 또는 문단. 줄마다 문단 하나, 서식은 첫 문단/첫 run 기준."""
    from pptx.text.text import _Paragraph

    lines = new.split("\n")
    if isinstance(obj, _Paragraph):
        set_runs(list(obj.runs), new.replace("\n", "\v"), lambda s: setattr(obj.add_run(), "text", s))
        return
    paras = list(obj.paragraphs)
    first = paras[0]
    set_runs(list(first.runs), lines[0], lambda s: setattr(first.add_run(), "text", s))
    for p in paras[1:]:
        p._p.getparent().remove(p._p)
    prev = first._p
    for line in lines[1:]:
        np_ = copy.deepcopy(first._p)
        prev.addnext(np_)
        prev = np_
        from pptx.text.text import _Paragraph as P

        para = P(np_, first._parent)
        set_runs(list(para.runs), line, lambda s: setattr(para.add_run(), "text", s))


def pptx_fill(path, edits, out):
    from pptx import Presentation

    prs = Presentation(path)
    index = dict(pptx_walk(prs))
    big = {loc: (slide, sh) for loc, slide, sh, _c in pptx_big_pictures(prs)}
    for e in edits:
        if "remove_shape" in e:
            sid = int(e["remove_shape"].split("/sh")[1])
            si = int(e["remove_shape"].split("/")[0][1:])
            sh = next((x for x in prs.slides[si - 1].shapes if x.shape_id == sid), None)
            if sh is None:
                warn(f"도형 없음: {e['remove_shape']}")
            else:
                sh._element.getparent().remove(sh._element)
                big.pop(e["remove_shape"], None)
            continue
        if "loc" in e:
            obj = index.get(e["loc"])
            if obj is None:
                warn(f"위치 없음: {e['loc']}")
                continue
            if not check_old(e, pptx_text(obj)):
                continue
            pptx_set(obj, e["new"])
        else:
            n = 0
            for loc, obj in index.items():
                paras = obj.paragraphs if hasattr(obj, "paragraphs") else [obj]
                for p in paras:
                    if replace_in_runs(list(p.runs), e["find"], e["replace"]):
                        n += 1
            report_find(e, n)
    edited_slides = {e["loc"].split("/")[0] for e in edits if "loc" in e}
    for loc in big:
        if loc.split("/")[0] in edited_slides:
            warn(f"{loc}: 전체 페이지 그림이 수정한 내용을 덮고 있음 (remove_shape 로 지울지 확인)")
    prs.save(out)


# ───────────────────────── DOCX ─────────────────────────


def docx_paras(doc):
    from docx.text.paragraph import Paragraph

    body = doc.element.body
    for i, p in enumerate(body.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p")):
        yield f"p{i}", Paragraph(p, doc)


def docx_items(path):
    import docx

    for loc, p in docx_paras(docx.Document(path)):
        if p.text.strip():
            yield loc, p.text


def docx_fill(path, edits, out):
    import docx

    doc = docx.Document(path)
    index = dict(docx_paras(doc))
    for e in edits:
        if "loc" in e:
            p = index.get(e["loc"])
            if p is None:
                warn(f"위치 없음: {e['loc']}")
                continue
            if not check_old(e, p.text):
                continue
            set_runs(list(p.runs), e["new"], lambda s: p.add_run(s))
            if "\n" in e["new"] and p.runs:  # python-docx 는 \n 을 <w:br/> 로 바꿔 줌
                p.runs[0].text = e["new"]
        else:
            n = sum(replace_in_runs(list(p.runs), e["find"], e["replace"]) for p in index.values())
            # 머리글/바닥글도
            for s in doc.sections:
                for part in (s.header, s.footer):
                    for p in part.paragraphs:
                        n += replace_in_runs(list(p.runs), e["find"], e["replace"])
            report_find(e, n)
    doc.save(out)


# ───────────────────────── HWPX ─────────────────────────

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"


class _HwpRun:
    """hp:t 요소를 .text 로 다루기 위한 래퍼 (안쪽 탭/줄바꿈 태그는 정리)."""

    def __init__(self, el):
        self.el = el

    @property
    def text(self):
        return "".join(self.el.itertext())

    @text.setter
    def text(self, v):
        for ch in list(self.el):
            self.el.remove(ch)
        self.el.text = v


def hwpx_sections(z: zipfile.ZipFile):
    return sorted(n for n in z.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n))


def hwpx_paras(root):
    """문단마다 (순번, hp:p, [그 문단에 직접 속한 hp:t]) — 표 안 문단은 따로 셈."""
    for i, p in enumerate(root.iter(f"{{{HP}}}p")):
        ts = [t for run in p.findall(f"{{{HP}}}run") for t in run.findall(f"{{{HP}}}t")]
        yield i, p, ts


def hwpx_items(path):
    from lxml import etree

    with zipfile.ZipFile(path) as z:
        for sec in hwpx_sections(z):
            root = etree.fromstring(z.read(sec))
            for i, _p, ts in hwpx_paras(root):
                t = "".join("".join(x.itertext()) for x in ts)
                if t.strip():
                    yield f"{sec}#p{i}", t


def hwpx_fill(path, edits, out):
    from lxml import etree

    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}
        secs = hwpx_sections(z)
    trees = {s: etree.fromstring(data[s]) for s in secs}
    index = {}
    for s, root in trees.items():
        for i, p, ts in hwpx_paras(root):
            index[f"{s}#p{i}"] = (p, ts)

    def make_run_for(p):
        def mk(text):
            run = p.find(f"{{{HP}}}run")
            if run is None:
                run = etree.SubElement(p, f"{{{HP}}}run", charPrIDRef="0")
            t = etree.SubElement(run, f"{{{HP}}}t")
            t.text = text
        return mk

    for e in edits:
        if "loc" in e:
            if e["loc"] not in index:
                warn(f"위치 없음: {e['loc']}")
                continue
            p, ts = index[e["loc"]]
            runs = [_HwpRun(t) for t in ts]
            if not check_old(e, "".join(r.text for r in runs)):
                continue
            set_runs(runs, e["new"].replace("\n", " "), make_run_for(p))
            if "\n" in e["new"]:
                warn(f"{e['loc']}: hwpx 는 줄바꿈 대신 공백으로 넣었음 — 여러 줄이면 문단별 loc 로 나눠 넣을 것")
        else:
            n = sum(replace_in_runs([_HwpRun(t) for t in ts], e["find"], e["replace"]) for _p, ts in index.values())
            report_find(e, n)

    for s, root in trees.items():
        data[s] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    write_zip(infos, data, out)  # mimetype 은 첫 항목 + 무압축


# ───────────────────────── 실행 ─────────────────────────

WARNINGS: list[str] = []


def warn(msg):
    WARNINGS.append(msg)
    print(f"[경고] {msg}", file=sys.stderr)


def check_old(e, current: str) -> bool:
    if "old" in e and e["old"].strip() != current.strip():
        warn(f"{e['loc']}: 현재 값 {current!r} ≠ old {e['old']!r} → 건너뜀")
        return False
    return True


def report_find(e, n):
    if n == 0:
        warn(f"찾기 실패: {e['find']!r}")
    else:
        print(f"[찾아바꾸기] {e['find']!r} → {e['replace']!r} : {n}곳", file=sys.stderr)


HANDLERS = {
    ".xlsx": (xlsx_items, xlsx_fill), ".xlsm": (xlsx_items, xlsx_fill),
    ".pptx": (pptx_items, pptx_fill),
    ".docx": (docx_items, docx_fill),
    ".hwpx": (hwpx_items, hwpx_fill),
}


def handler(path: Path):
    ext = path.suffix.lower()
    if ext not in HANDLERS:
        sys.exit(f"지원하지 않는 형식: {ext} (xls/ppt/doc/hwp 는 먼저 변환: soffice --headless --convert-to xlsx|pptx|docx)")
    return HANDLERS[ext]


def main(argv):
    if len(argv) >= 2 and argv[0] == "dump":
        path = Path(argv[1])
        items = list(handler(path)[0](path))
        if "--json" in argv:
            print(json.dumps(dict(items), ensure_ascii=False, indent=1))
        else:
            for loc, t in items:
                print(f"{loc}\t{t.replace(chr(10), ' ⏎ ').replace(chr(11), ' ⏎ ')}")
        return 0
    if len(argv) == 4 and argv[0] == "fill":
        src, edits_path, out = Path(argv[1]), Path(argv[2]), Path(argv[3])
        edits = json.loads(edits_path.read_text(encoding="utf-8"))
        if src.resolve() == out.resolve():
            sys.exit("원본에 덮어쓰지 말고 다른 OUT 경로를 쓸 것")
        handler(src)[1](src, edits, out)
        print(f"저장: {out}  (경고 {len(WARNINGS)}건)")
        return 1 if WARNINGS else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
