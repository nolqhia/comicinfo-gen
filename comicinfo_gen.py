#!/usr/bin/env python3
"""
ComicInfo.xml 自動生成スクリプト
カバースキャン画像からバーコード/OCRでISBNを取得し、
楽天Books API + OpenBD API で書誌データを取得して ComicInfo.xml を生成する。

使い方:
  python comicinfo_gen.py <画像ファイルパス>
  または .bat ファイルに D&D
"""

import sys
import os
import re
import xml.etree.ElementTree as ET
from xml.dom import minidom

import requests
from PIL import Image
from pyzbar.pyzbar import decode as pyzbar_decode

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

# === 設定 ===
RAKUTEN_APP_ID = "YOUR_APP_ID_HERE"         # ← 楽天APIのアプリID (applicationId)
RAKUTEN_ACCESS_KEY = "YOUR_ACCESS_KEY_HERE" # ← 楽天APIのアクセスキー (accessKey)

# tesseract.exe のパス（PATHが通っていない場合に指定）
# 通常は r"C:\Program Files\Tesseract-OCR\tesseract.exe"
# 不要なら None のまま
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

if HAS_TESSERACT and TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

# 見開き判定のアスペクト比閾値（幅/高さがこれを超えたら見開きと判定）
SPREAD_ASPECT_RATIO = 1.5


# =============================================================================
# ISBN 取得
# =============================================================================

def normalize_isbn(raw: str) -> str | None:
    """ISBN文字列を正規化して13桁に統一する。"""
    digits = re.sub(r"[^0-9X]", "", raw.upper())
    if len(digits) == 13 and digits.startswith("978"):
        return digits
    if len(digits) == 10:
        base = "978" + digits[:9]
        total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(base))
        check = (10 - total % 10) % 10
        return base + str(check)
    return None


def crop_target_region(image: Image.Image) -> Image.Image:
    """見開き画像なら右半分を切り出す。単体ならそのまま返す。"""
    w, h = image.size
    aspect = w / h
    if aspect > SPREAD_ASPECT_RATIO:
        cropped = image.crop((w // 2, 0, w, h))
        print(f"[画像] 見開き検出 (アスペクト比 {aspect:.2f}) → 右半分を使用")
        return cropped
    else:
        print(f"[画像] 単体画像 (アスペクト比 {aspect:.2f}) → 全体を使用")
        return image


def extract_isbn_barcode(image: Image.Image) -> str | None:
    """pyzbar でバーコードからISBNを読み取る。"""
    barcodes = pyzbar_decode(image)
    for barcode in barcodes:
        data = barcode.data.decode("utf-8", errors="ignore")
        isbn = normalize_isbn(data)
        if isbn:
            print(f"[バーコード] ISBN検出: {isbn}")
            return isbn
    return None


def extract_isbn_ocr(image: Image.Image) -> str | None:
    """tesseract OCR でISBN文字列を抽出する。"""
    if not HAS_TESSERACT:
        print("[OCR] pytesseract が未インストールです。スキップします。")
        return None

    print("[OCR] テキスト認識中...")
    try:
        text = pytesseract.image_to_string(image, lang="jpn+eng")
    except Exception:
        try:
            text = pytesseract.image_to_string(image, lang="eng")
        except Exception as e:
            print(f"[OCR] エラー: {e}")
            return None

    patterns = [
        r"ISBN[\s:-]*((97[89][\s-]*(?:\d[\s-]*){9}\d))",
        r"(97[89][\s-]*(?:\d[\s-]*){9}\d)",
    ]
    for pat in patterns:
        match = re.search(pat, text.replace("\n", " "))
        if match:
            raw = match.group(1)
            isbn = normalize_isbn(raw)
            if isbn:
                print(f"[OCR] ISBN検出: {isbn}")
                return isbn

    print("[OCR] ISBNを検出できませんでした。")
    return None


def extract_isbn(image_path: str) -> str | None:
    """画像からISBNを取得する（バーコード → OCR フォールバック）。"""
    image = Image.open(image_path)
    target = crop_target_region(image)

    isbn = extract_isbn_barcode(target)
    if isbn:
        return isbn

    print("[バーコード] 検出できず。グレースケールでリトライ...")
    gray = target.convert("L")
    isbn = extract_isbn_barcode(gray)
    if isbn:
        return isbn

    print("[バーコード] 検出できず。OCRにフォールバックします。")
    isbn = extract_isbn_ocr(target)
    return isbn


# =============================================================================
# API 呼び出し
# =============================================================================

def fetch_rakuten(isbn: str) -> dict | None:
    """楽天Books APIで書誌データを取得する。"""
    if RAKUTEN_APP_ID == "YOUR_APP_ID_HERE" or RAKUTEN_ACCESS_KEY == "YOUR_ACCESS_KEY_HERE":
        print("[楽天] アプリIDまたはアクセスキーが未設定です。スクリプト冒頭の設定を確認してください。")
        return None

    url = "https://openapi.rakuten.co.jp/services/api/BooksBook/Search/20170404"
    params = {
        "applicationId": RAKUTEN_APP_ID,
        "accessKey": RAKUTEN_ACCESS_KEY,
        "isbn": isbn,
    }

    print(f"[楽天] 問い合わせ中... ISBN={isbn}")
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[楽天] エラー: {e}")
        return None

    if data.get("count", 0) == 0:
        print("[楽天] ヒットなし。")
        return None

    item = data["Items"][0]["Item"]
    print(f"[楽天] ヒット: {item.get('title', '(不明)')}")
    return item


def fetch_openbd(isbn: str) -> dict | None:
    """OpenBD APIで書誌データを取得する。"""
    url = f"https://api.openbd.jp/v1/get?isbn={isbn}"

    print(f"[OpenBD] 問い合わせ中... ISBN={isbn}")
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[OpenBD] エラー: {e}")
        return None

    if not data or data[0] is None:
        print("[OpenBD] ヒットなし。")
        return None

    record = data[0]
    title = (record.get("summary") or {}).get("title", "(不明)")
    print(f"[OpenBD] ヒット: {title}")
    return record


# =============================================================================
# データ抽出
# =============================================================================

def parse_rakuten_date(sales_date: str) -> tuple[str, str, str]:
    """楽天の salesDate "2024年08月02日頃" から Year, Month, Day を抽出。"""
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", sales_date)
    if m:
        return m.group(1), str(int(m.group(2))), str(int(m.group(3)))
    m = re.search(r"(\d{4})年(\d{1,2})月", sales_date)
    if m:
        return m.group(1), str(int(m.group(2))), ""
    return "", "", ""


def parse_rakuten_author(author: str) -> tuple[str, str]:
    """楽天の author "界達 かたる/古弥月" から Writer, CoverArtist を分離。"""
    parts = [p.strip() for p in author.split("/") if p.strip()]
    writer = parts[0] if len(parts) >= 1 else ""
    cover_artist = parts[1] if len(parts) >= 2 else ""
    return writer, cover_artist


def extract_number_from_openbd(record: dict) -> str:
    """OpenBD の PartNumber からシリーズ巻数を推測する。"""
    try:
        title_elements = record["onix"]["DescriptiveDetail"]["Collection"]["TitleDetail"]["TitleElement"]
        if isinstance(title_elements, dict):
            title_elements = [title_elements]
        for elem in title_elements:
            part_number = elem.get("PartNumber", "")
            if part_number:
                nums = re.findall(r"\d+", part_number)
                if nums:
                    return nums[-1]
    except (KeyError, TypeError):
        pass
    return ""


# =============================================================================
# ComicInfo.xml 構築
# =============================================================================

def build_comicinfo(isbn: str | None, rakuten: dict | None, openbd: dict | None) -> ET.Element:
    """書誌データから ComicInfo XML を構築する。"""
    root = ET.Element("ComicInfo")

    title = ""
    summary = ""
    publisher = ""
    imprint = ""
    writer = ""
    cover_artist = ""
    year, month, day = "", "", ""

    if rakuten:
        title = rakuten.get("title", "")
        summary = rakuten.get("itemCaption", "")
        publisher = rakuten.get("publisherName", "")
        imprint = rakuten.get("seriesName", "")
        writer, cover_artist = parse_rakuten_author(rakuten.get("author", ""))
        year, month, day = parse_rakuten_date(rakuten.get("salesDate", ""))

    if not title and openbd:
        title = (openbd.get("summary") or {}).get("title", "")
    if not publisher and openbd:
        try:
            publisher = openbd["onix"]["PublishingDetail"]["Imprint"]["ImprintName"]
        except (KeyError, TypeError):
            publisher = (openbd.get("summary") or {}).get("publisher", "")
    if not imprint and openbd:
        try:
            elems = openbd["onix"]["DescriptiveDetail"]["Collection"]["TitleDetail"]["TitleElement"]
            if isinstance(elems, list):
                for e in elems:
                    content = (e.get("TitleText") or {}).get("content", "")
                    if content:
                        imprint = content
                        break
            elif isinstance(elems, dict):
                imprint = (elems.get("TitleText") or {}).get("content", "")
        except (KeyError, TypeError):
            pass
    if not writer and openbd:
        try:
            contributors = openbd["onix"]["DescriptiveDetail"]["Contributor"]
            if contributors:
                writer = contributors[0].get("PersonName", {}).get("content", "")
        except (KeyError, TypeError):
            writer = (openbd.get("summary") or {}).get("author", "")
    if not year and openbd:
        try:
            pub_dates = openbd["onix"]["PublishingDetail"]["PublishingDate"]
            if isinstance(pub_dates, list) and pub_dates:
                date_str = pub_dates[0].get("Date", "")
            elif isinstance(pub_dates, dict):
                date_str = pub_dates.get("Date", "")
            else:
                date_str = ""
            if len(date_str) >= 4:
                year = date_str[:4]
            if len(date_str) >= 6:
                month = str(int(date_str[4:6]))
            if len(date_str) >= 8:
                day = str(int(date_str[6:8]))
        except (KeyError, TypeError):
            pass

    number = ""
    if openbd:
        number = extract_number_from_openbd(openbd)

    def add(tag: str, value: str):
        if value:
            ET.SubElement(root, tag).text = value

    add("Series", title)
    add("Title", title)
    ET.SubElement(root, "Genre").text = ""
    add("Summary", summary)
    add("Publisher", publisher)
    add("Imprint", imprint)
    if day:
        add("Day", day)
    if month:
        add("Month", month)
    if year:
        add("Year", year)
    add("LanguageISO", "ja")
    add("Manga", "YesAndRightToLeft")
    add("AgeRating", "Everyone")
    add("Writer", writer)
    if cover_artist:
        add("CoverArtist", cover_artist)
    if number:
        add("Number", number)
    add("BlackAndWhite", "Yes")
    if isbn:
        add("GTIN", isbn)

    return root


# =============================================================================
# XML 出力
# =============================================================================

def prettify_xml(elem: ET.Element) -> str:
    """XML を整形して文字列にする。"""
    rough = ET.tostring(elem, encoding="unicode", short_empty_elements=False)
    parsed = minidom.parseString(rough)
    pretty = parsed.toprettyxml(indent="  ", encoding=None)
    lines = pretty.split("\n")
    lines[0] = "<?xml version='1.0' encoding='utf-8'?>"
    result = "\n".join(line for line in lines if line.strip())
    result = re.sub(r"<(\w+)\s*/>", r"<\1></\1>", result)
    return result


def write_xml(root: ET.Element, output_path: str):
    """XML をファイルに書き出し、プレビューを表示する。"""
    xml_str = prettify_xml(root)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(xml_str)
    print(f"\n=== 生成完了 ===")
    print(f"出力: {output_path}")
    print()
    print("--- 内容プレビュー ---")
    print(xml_str)


# =============================================================================
# メイン
# =============================================================================

def main():
    if len(sys.argv) < 2:
        print("使い方: python comicinfo_gen.py <画像ファイルパス>")
        print("  または .bat ファイルに画像を D&D")
        sys.exit(1)

    image_path = sys.argv[1]
    if not os.path.isfile(image_path):
        print(f"エラー: ファイルが見つかりません: {image_path}")
        sys.exit(1)

    output_dir = os.path.dirname(os.path.abspath(image_path))
    output_path = os.path.join(output_dir, "ComicInfo.xml")

    print(f"=== ComicInfo.xml 生成 ===")
    print(f"入力画像: {image_path}")
    print()

    isbn = extract_isbn(image_path)
    if not isbn:
        print("\n[警告] ISBNを取得できませんでした。固定値のみで生成します。")
        root = build_comicinfo(None, None, None)
        write_xml(root, output_path)
        print()
        input("Enterキーで終了...")
        return

    print(f"\n--- ISBN: {isbn} ---\n")

    rakuten = fetch_rakuten(isbn)
    openbd = fetch_openbd(isbn)

    if not rakuten and not openbd:
        print("\n[警告] どちらのAPIからも書誌データを取得できませんでした。固定値+ISBNのみで生成します。")

    root = build_comicinfo(isbn, rakuten, openbd)
    write_xml(root, output_path)
    print()
    input("Enterキーで終了...")


if __name__ == "__main__":
    main()
