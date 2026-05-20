# comicinfo-gen

スキャンした書籍カバー画像から `ComicInfo.xml` を自動生成するスクリプト。

カバー画像のバーコード（または OCR）からISBNを取得し、楽天Books APIとOpenBD APIを使って書誌データを引き、[ComicInfo.xml](https://github.com/anansi-project/comicinfo) を出力します。

Kavita、ComicRack、Komga などの漫画・電子書籍管理ソフトで利用できる形式です。

## 特徴

- **見開きカバー対応**: アスペクト比から見開き画像を自動判定し、裏表紙側（右半分）から情報を取得
- **OCRフォールバック**: バーコードがビニルカバー側にしかない書籍でも、印字されたISBN文字列をOCRで認識
- **2段階API**: 楽天Books API（主）+ OpenBD API（副）で書誌データを取得
- **D&D実行**: `.bat` ファイルに画像をドラッグ&ドロップするだけで生成

## 出力例

```xml
<?xml version='1.0' encoding='utf-8'?>
<ComicInfo>
  <Series>七月の蝉と、八日目の空 -晴れ、ときどき風そよぐ季の約束ー</Series>
  <Title>七月の蝉と、八日目の空 -晴れ、ときどき風そよぐ季の約束ー</Title>
  <Genre></Genre>
  <Summary>一生忘れたくない一週間ーー金色に輝く髪の少女と...</Summary>
  <Publisher>講談社</Publisher>
  <Imprint>講談社ラノベ文庫</Imprint>
  <Day>2</Day>
  <Month>8</Month>
  <Year>2024</Year>
  <LanguageISO>ja</LanguageISO>
  <Manga>YesAndRightToLeft</Manga>
  <AgeRating>Everyone</AgeRating>
  <Writer>界達 かたる</Writer>
  <CoverArtist>古弥月</CoverArtist>
  <Number>1</Number>
  <BlackAndWhite>Yes</BlackAndWhite>
  <GTIN>9784065364246</GTIN>
</ComicInfo>
```

## 必要なもの

- Windows
- Python 3.10 以上
- 楽天Web Service のアプリID（無料）
- Tesseract OCR（OCRフォールバック用）

## セットアップ

### 1. Pythonライブラリのインストール

```cmd
pip install -r requirements.txt
```

### 2. Tesseract OCR のインストール

OCR機能（バーコードなしのカバー対策）に必要です。

[UB Mannheim版インストーラー](https://github.com/UB-Mannheim/tesseract/wiki) からダウンロードしてインストールしてください。

インストール時の注意：
- 「Additional language data (download)」で **Japanese** を選択する
- デフォルトのインストール先は `C:\Program Files\Tesseract-OCR\`

PATHを通すか、スクリプト冒頭の `TESSERACT_CMD` にインストール先を指定してください。

### 3. 楽天APIアプリの登録

[Rakuten Developer Portal](https://webservice.rakuten.co.jp/) でアプリを新規登録します。

設定例：
- アプリケーションタイプ: **APIバックエンドサービス**
- 許可されたIPアドレス: 自宅のグローバルIP（IPv4 + IPv6両方推奨、CIDR表記可）
- 予想QPS: 1

登録後に `applicationId` と `accessKey` が発行されます。

### 4. スクリプトの設定

`comicinfo_gen.py` の冒頭を編集します：

```python
RAKUTEN_APP_ID = "YOUR_APP_ID_HERE"         # ← applicationId を貼る
RAKUTEN_ACCESS_KEY = "YOUR_ACCESS_KEY_HERE" # ← accessKey を貼る

TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"  # ← インストール先
```

## 使い方

### D&D（推奨）

`comicinfo_gen.bat` にカバー画像をドラッグ&ドロップ。

画像と同じフォルダに `ComicInfo.xml` が生成されます。

### CLI

```cmd
python comicinfo_gen.py <画像ファイルパス>
```

## 入力画像について

- 形式: PNG、JPEG など Pillow が読める形式
- 推奨: カバー見開き（表紙+背+裏表紙を1枚にスキャンしたもの）
- 単体画像（裏表紙のみ）でもOK

幅 / 高さ > 1.5 のとき見開きと判定し、右半分（裏表紙側）でバーコード検出・OCRを行います。

## 動作の流れ

```
カバー画像
   ↓
[1] 画像判定（見開き or 単体）
   ↓
[2] バーコード検出（pyzbar）
   ├─ 成功 → ISBN取得
   └─ 失敗 → OCR（tesseract）でISBN文字列を抽出
   ↓
[3] 書誌データ取得
   ├─ 楽天Books API（主）
   │   → Title, Summary, Publisher, Imprint,
   │     Writer, CoverArtist, Year/Month/Day
   └─ OpenBD API（副）
       → Number(巻数), 楽天で取れなかったフィールドを補完
   ↓
[4] ComicInfo.xml 生成
```

## フィールドマッピング

| ComicInfoフィールド | 取得元 | 備考 |
|---|---|---|
| Series / Title | 楽天 `title` | 同一値で出力 |
| Summary | 楽天 `itemCaption` | |
| Publisher | 楽天 `publisherName` | |
| Imprint | 楽天 `seriesName` | レーベル名 |
| Writer | 楽天 `author` の `/` 分割[0] | |
| CoverArtist | 楽天 `author` の `/` 分割[1] | あれば |
| Year/Month/Day | 楽天 `salesDate` | パース |
| Number | OpenBD `PartNumber` 末尾 | 目視確認推奨 |
| GTIN | バーコード/OCRで取得したISBN | |
| Genre | （空タグ） | 手修正用 |
| LanguageISO | `ja` | 固定 |
| Manga | `YesAndRightToLeft` | 固定 |
| AgeRating | `Everyone` | 固定 |
| BlackAndWhite | `Yes` | 固定 |

## エラー時の挙動

- **ISBN取得失敗**: 固定値のみのスケルトンXMLを出力
- **API取得失敗**: 固定値 + GTIN のみのXMLを出力

どちらのケースでも処理は止まらず、最小限のXMLは生成されます。

## ライセンス

MIT License

## 利用しているAPI

- [楽天Books書籍検索API](https://webservice.rakuten.co.jp/documentation/books-book-search) — 楽天株式会社
- [openBD](https://openbd.jp/) — 版元ドットコム + カーリル

## 参考

- [ComicInfo.xml 仕様](https://github.com/anansi-project/comicinfo)
