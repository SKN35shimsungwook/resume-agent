"""이력서·포트폴리오·공고 파일과 웹페이지를 텍스트로 바꾼다.

지원 형식: PDF, DOCX, HWP(5.0), HWPX, TXT/MD, 웹페이지 URL.
"""
import io
import re
import struct
import zipfile
import zlib
from pathlib import Path

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


def load_file(name: str, data: bytes) -> str:
    """업로드된 파일 이름(확장자)과 내용을 받아 텍스트를 돌려준다."""
    ext = Path(name).suffix.lower()
    if ext == ".pdf":
        return _load_pdf(data)
    if ext == ".docx":
        return _load_docx(data)
    if ext == ".hwp":
        return _load_hwp(data)
    if ext == ".hwpx":
        return _load_hwpx(data)
    if ext in (".txt", ".md"):
        return data.decode("utf-8", errors="replace")
    raise ValueError(f"지원하지 않는 파일 형식입니다: {ext}")


def load_url(url: str) -> str:
    """웹페이지 본문 텍스트. 자바스크립트로만 그려지는 페이지면 브라우저로 다시 읽는다."""
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    ctype = resp.headers.get("content-type", "")
    if "pdf" in ctype:
        return _load_pdf(resp.content)
    text = _html_to_text(resp.text)
    # 채용 공고 사이트 상당수가 JS 렌더링이라 정적 HTML에 본문이 거의 없다.
    if len(text) < 300:
        text = _html_to_text(_render_with_browser(url)) or text
    return text


def _load_pdf(data: bytes) -> str:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    text = "\n".join(pages).strip()
    if not text:
        raise ValueError("PDF에서 글자를 읽지 못했습니다. 스캔 이미지 PDF일 수 있습니다.")
    return text


def _load_docx(data: bytes) -> str:
    import docx

    doc = docx.Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    # 이력서는 표로 된 경우가 많아 표 안 글자도 모은다.
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    return "\n".join(p for p in parts if p.strip())


def _load_hwpx(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        sections = sorted(
            n for n in zf.namelist() if re.match(r"Contents/section\d+\.xml$", n)
        )
        paragraphs = []
        for name in sections:
            xml = zf.read(name).decode("utf-8", errors="replace")
            for para in re.findall(r"<hp:p\b.*?</hp:p>", xml, re.DOTALL):
                runs = re.findall(r"<hp:t\b[^>]*>(.*?)</hp:t>", para, re.DOTALL)
                line = re.sub(r"<[^>]+>", "", "".join(runs))
                if line.strip():
                    paragraphs.append(_unescape_xml(line))
    return "\n".join(paragraphs)


# HWP 5.0 문단 텍스트(HWPTAG_PARA_TEXT) 안의 제어 문자. 이 문자들은 8 WCHAR를 차지한다.
_HWP_WIDE_CONTROLS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23}
_HWPTAG_PARA_TEXT = 67


def _load_hwp(data: bytes) -> str:
    import olefile

    ole = olefile.OleFileIO(io.BytesIO(data))
    header = ole.openstream("FileHeader").read()
    flags = struct.unpack_from("<I", header, 36)[0]
    if flags & 0x04:
        raise ValueError("배포용(읽기 전용) HWP는 읽을 수 없습니다. PDF로 저장해서 올려주세요.")
    compressed = bool(flags & 0x01)

    sections = sorted(
        (entry for entry in ole.listdir() if entry[0] == "BodyText"),
        key=lambda e: int(re.sub(r"\D", "", e[1]) or 0),
    )
    paragraphs = []
    for entry in sections:
        raw = ole.openstream(entry).read()
        if compressed:
            raw = zlib.decompress(raw, -15)
        paragraphs.extend(_hwp_paragraphs(raw))
    return "\n".join(p for p in paragraphs if p.strip())


def _hwp_paragraphs(raw: bytes):
    pos = 0
    while pos + 4 <= len(raw):
        head = struct.unpack_from("<I", raw, pos)[0]
        pos += 4
        tag = head & 0x3FF
        size = (head >> 20) & 0xFFF
        if size == 0xFFF:
            size = struct.unpack_from("<I", raw, pos)[0]
            pos += 4
        body = raw[pos:pos + size]
        pos += size
        if tag == _HWPTAG_PARA_TEXT:
            yield _decode_hwp_text(body)


def _decode_hwp_text(body: bytes) -> str:
    chars = []
    i = 0
    n = len(body) // 2
    while i < n:
        code = struct.unpack_from("<H", body, i * 2)[0]
        if code in _HWP_WIDE_CONTROLS:
            i += 8
            continue
        if code < 32:
            if code in (10, 13):
                chars.append("\n")
            i += 1
            continue
        chars.append(chr(code))
        i += 1
    return "".join(chars)


def _html_to_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    lines = (line.strip() for line in soup.get_text("\n").splitlines())
    return "\n".join(line for line in lines if line)


def _render_with_browser(url: str) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        page.goto(url, wait_until="networkidle", timeout=30000)
        html = page.content()
        browser.close()
    return html


def _unescape_xml(text: str) -> str:
    return (
        text.replace("&lt;", "<").replace("&gt;", ">")
        .replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&")
    )
