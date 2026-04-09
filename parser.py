"""
BilankoIQ — Mizan Parser
Excel mizandan standart bilanço ve gelir tablosu çıkarır.

Akış:
  1. Excel oku (openpyxl)
  2. Hesap kodu kolonunu tespit et
  3. TDHP eşleştirme tablosuyla kalemlere ata
  4. Eşleşme oranı düşükse Claude API fallback
  5. Normalize edilmiş BalanceSheet objesi dön
"""

from __future__ import annotations
import re
import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import openpyxl

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 1. VERİ MODELİ
# ─────────────────────────────────────────────

@dataclass
class BalanceSheet:
    """Normalize edilmiş bilanço ve gelir tablosu kalemleri (TL)."""

    # AKTİF — Dönen Varlıklar
    kasa: float = 0.0                    # 100
    banka: float = 0.0                   # 102
    diger_hazir_degerler: float = 0.0    # 108
    ticari_alacaklar: float = 0.0        # 120 + 121
    diger_alacaklar_kv: float = 0.0      # 126 + 136
    stoklar: float = 0.0                 # 150–158 toplamı
    diger_donen_varliklar: float = 0.0   # 180–195

    # AKTİF — Duran Varlıklar
    ticari_alacaklar_uv: float = 0.0     # 220 + 221
    diger_alacaklar_uv: float = 0.0      # 226 + 236
    mali_duran_varliklar: float = 0.0    # 240–248
    maddi_duran_varliklar: float = 0.0   # 250–258 (net)
    maddi_olmayan_duv: float = 0.0       # 260–268 (net)
    diger_duran_varliklar: float = 0.0   # 270–299

    # PASİF — Kısa Vadeli Yükümlülükler
    banka_kredileri_kv: float = 0.0      # 300 + 301
    uzun_vadeli_borclar_kv: float = 0.0  # 303
    ticari_borclar_kv: float = 0.0       # 320 + 321
    ortaklara_borclar: float = 0.0       # 331
    diger_kv_borclar: float = 0.0        # 330–399 (331 hariç)

    # PASİF — Uzun Vadeli Yükümlülükler
    banka_kredileri_uv: float = 0.0      # 400 + 401
    diger_uv_borclar: float = 0.0        # 402–499

    # PASİF — Özkaynaklar
    odenmis_sermaye: float = 0.0         # 500
    sermaye_yedekleri: float = 0.0       # 520–529
    kar_yedekleri: float = 0.0           # 540–549
    gecmis_yil_karlari: float = 0.0      # 570
    donem_net_kari: float = 0.0          # 590

    # GELİR TABLOSU
    net_satislar: float = 0.0            # 600 - 610
    satislarin_maliyeti: float = 0.0     # 620 + 621 + 622
    pazarlama_giderleri: float = 0.0     # 630
    genel_yonetim_giderleri: float = 0.0 # 631
    arge_giderleri: float = 0.0          # 632
    diger_faaliyet_gelirleri: float = 0.0 # 640–649
    diger_faaliyet_giderleri: float = 0.0# 650–659
    finansman_gelirleri: float = 0.0     # 670–679
    finansman_giderleri: float = 0.0     # 660 + 661
    vergi_oncesi_kar: float = 0.0        # 690 (hesaplanır)
    vergi_gideri: float = 0.0            # 691 + 692

    # META
    parse_method: str = "rule_based"     # "rule_based" | "ai_fallback"
    match_rate: float = 0.0              # Eşleşme oranı (0–1)
    warnings: list = field(default_factory=list)

    # ─── Türetilmiş toplamlar ───────────────────

    @property
    def nakit_ve_benzerleri(self) -> float:
        return self.kasa + self.banka + self.diger_hazir_degerler

    @property
    def donen_varliklar(self) -> float:
        return (self.nakit_ve_benzerleri + self.ticari_alacaklar +
                self.diger_alacaklar_kv + self.stoklar + self.diger_donen_varliklar)

    @property
    def duran_varliklar(self) -> float:
        return (self.ticari_alacaklar_uv + self.diger_alacaklar_uv +
                self.mali_duran_varliklar + self.maddi_duran_varliklar +
                self.maddi_olmayan_duv + self.diger_duran_varliklar)

    @property
    def toplam_aktif(self) -> float:
        return self.donen_varliklar + self.duran_varliklar

    @property
    def kv_borclar(self) -> float:
        return (self.banka_kredileri_kv + self.uzun_vadeli_borclar_kv +
                self.ticari_borclar_kv + self.ortaklara_borclar + self.diger_kv_borclar)

    @property
    def uv_borclar(self) -> float:
        return self.banka_kredileri_uv + self.diger_uv_borclar

    @property
    def toplam_borclar(self) -> float:
        return self.kv_borclar + self.uv_borclar

    @property
    def ozkaynaklar(self) -> float:
        return (self.odenmis_sermaye + self.sermaye_yedekleri +
                self.kar_yedekleri + self.gecmis_yil_karlari + self.donem_net_kari)

    @property
    def toplam_pasif(self) -> float:
        return self.toplam_borclar + self.ozkaynaklar

    @property
    def brut_kar(self) -> float:
        return self.net_satislar - self.satislarin_maliyeti

    @property
    def faaliyet_giderleri(self) -> float:
        return (self.pazarlama_giderleri + self.genel_yonetim_giderleri +
                self.arge_giderleri)

    @property
    def favok(self) -> float:
        """FAVÖK = Brüt Kâr - Faaliyet Giderleri + Diğer Faaliyet Gelirleri - Diğer Faaliyet Giderleri"""
        return (self.brut_kar - self.faaliyet_giderleri +
                self.diger_faaliyet_gelirleri - self.diger_faaliyet_giderleri)

    @property
    def net_kar(self) -> float:
        if self.donem_net_kari != 0:
            return self.donem_net_kari
        return self.favok + self.finansman_gelirleri - self.finansman_giderleri - self.vergi_gideri

    @property
    def finansal_borclar(self) -> float:
        """Sadece banka/finansal borçlar (ticari borçlar hariç)."""
        return self.banka_kredileri_kv + self.uzun_vadeli_borclar_kv + self.banka_kredileri_uv

    @property
    def net_borc(self) -> float:
        return self.finansal_borclar - self.nakit_ve_benzerleri

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update({
            "nakit_ve_benzerleri": self.nakit_ve_benzerleri,
            "donen_varliklar": self.donen_varliklar,
            "duran_varliklar": self.duran_varliklar,
            "toplam_aktif": self.toplam_aktif,
            "kv_borclar": self.kv_borclar,
            "uv_borclar": self.uv_borclar,
            "toplam_borclar": self.toplam_borclar,
            "ozkaynaklar": self.ozkaynaklar,
            "brut_kar": self.brut_kar,
            "faaliyet_giderleri": self.faaliyet_giderleri,
            "favok": self.favok,
            "net_kar": self.net_kar,
            "finansal_borclar": self.finansal_borclar,
            "net_borc": self.net_borc,
        })
        return d


# ─────────────────────────────────────────────
# 2. TDHP HESAP KODU → KALEM EŞLEŞTİRME TABLOSU
# ─────────────────────────────────────────────

# Her kalem için (hesap_kodu_prefix_listesi, BalanceSheet_field_adı, işaret)
# işaret: +1 borçlu bakiye pozitif, -1 alacaklı bakiye pozitif ekler
ACCOUNT_MAP: list[tuple[list[str], str, int]] = [
    # NAKİT
    (["100"], "kasa", 1),
    (["102"], "banka", 1),
    (["108"], "diger_hazir_degerler", 1),

    # TİCARİ ALACAKLAR (KV)
    (["120", "121"], "ticari_alacaklar", 1),
    (["122", "124", "126", "127", "128", "129",
      "136", "137", "138", "139"], "diger_alacaklar_kv", 1),

    # STOKLAR
    (["150", "151", "152", "153", "154", "157", "158"], "stoklar", 1),

    # DİĞER DÖNEN VARLIKLAR
    (["180", "181", "182", "183", "184", "185",
      "190", "191", "192", "193", "195"], "diger_donen_varliklar", 1),

    # TİCARİ ALACAKLAR (UV)
    (["220", "221"], "ticari_alacaklar_uv", 1),
    (["226", "236"], "diger_alacaklar_uv", 1),

    # MALİ DURAN VARLIKLAR
    (["240", "241", "242", "243", "244", "245",
      "246", "247", "248"], "mali_duran_varliklar", 1),

    # MADDİ DURAN VARLIKLAR (net — birikmiş amortisman düşülmüş gelir)
    (["250", "251", "252", "253", "254", "255",
      "256", "257", "258"], "maddi_duran_varliklar", 1),
    (["257", "258"], "maddi_duran_varliklar", -1),  # Birikmiş amortismanlar

    # MADDİ OLMAYAN DURAN VARLIKLAR
    (["260", "261", "262", "263", "264", "265",
      "266", "267", "268"], "maddi_olmayan_duv", 1),
    (["267", "268"], "maddi_olmayan_duv", -1),

    # DİĞER DURAN VARLIKLAR
    (["270", "271", "272", "273", "274", "275",
      "276", "277", "278", "279",
      "280", "281", "282", "284", "285",
      "291", "292", "293", "294", "295",
      "296", "297", "298", "299"], "diger_duran_varliklar", 1),

    # KV BANKA KREDİLERİ
    (["300", "301"], "banka_kredileri_kv", 1),
    (["303"], "uzun_vadeli_borclar_kv", 1),

    # TİCARİ BORÇLAR (KV)
    (["320", "321"], "ticari_borclar_kv", 1),

    # ORTAKLARA BORÇLAR
    (["331"], "ortaklara_borclar", 1),

    # DİĞER KV BORÇLAR (331 hariç)
    (["330", "332", "333", "334", "335", "336",
      "337", "338", "339",
      "340", "341", "342", "343", "344", "345",
      "346", "347", "348", "349",
      "350", "351", "352", "353", "354", "355",
      "356", "357", "358", "359",
      "360", "361", "362", "363", "364", "365",
      "366", "368", "369",
      "370", "371", "372", "373", "374", "375",
      "376", "377", "378", "379",
      "380", "381", "382", "383", "384", "385",
      "386", "387", "388", "389",
      "390", "391", "392", "393", "394", "395",
      "396", "397", "398", "399"], "diger_kv_borclar", 1),

    # UV BANKA KREDİLERİ
    (["400", "401"], "banka_kredileri_uv", 1),
    (["402", "403", "404", "405", "406", "407",
      "408", "409",
      "410", "411", "412", "413", "414", "415",
      "416", "417", "418", "419",
      "420", "421", "422", "431", "432", "433",
      "438", "439",
      "440", "441", "442", "443", "444", "445",
      "446", "447", "448", "449",
      "480", "481", "482", "483", "484", "485",
      "486", "487", "488", "489",
      "490", "491", "492", "493", "494", "495",
      "496", "497", "498", "499"], "diger_uv_borclar", 1),

    # ÖZKAYNAKLAR
    (["500"], "odenmis_sermaye", 1),
    (["520", "521", "522", "523", "524", "525",
      "526", "527", "528", "529"], "sermaye_yedekleri", 1),
    (["540", "541", "542", "543", "544", "545",
      "546", "547", "548", "549"], "kar_yedekleri", 1),
    (["570"], "gecmis_yil_karlari", 1),
    (["590"], "donem_net_kari", 1),

    # GELİR TABLOSU
    (["600"], "net_satislar", 1),
    (["610"], "net_satislar", -1),          # Satış indirimleri
    (["620", "621", "622"], "satislarin_maliyeti", 1),
    (["630"], "pazarlama_giderleri", 1),
    (["631"], "genel_yonetim_giderleri", 1),
    (["632"], "arge_giderleri", 1),
    (["640", "641", "642", "643", "644",
      "645", "646", "647", "648", "649"], "diger_faaliyet_gelirleri", 1),
    (["650", "651", "652", "653", "654",
      "655", "656", "657", "658", "659"], "diger_faaliyet_giderleri", 1),
    (["660", "661"], "finansman_giderleri", 1),
    (["670", "671", "672", "673", "674",
      "675", "676", "677", "678", "679"], "finansman_gelirleri", 1),
    (["691", "692"], "vergi_gideri", 1),
]

# Hızlı lookup: hesap_kodu → (field_adı, işaret) listesi
_CODE_LOOKUP: dict[str, list[tuple[str, int]]] = {}
for prefixes, field_name, sign in ACCOUNT_MAP:
    for p in prefixes:
        _CODE_LOOKUP.setdefault(p, []).append((field_name, sign))


# ─────────────────────────────────────────────
# 3. EXCEL OKUMA
# ─────────────────────────────────────────────

def _normalize_code(raw: str | int | float | None) -> str | None:
    """Hesap kodunu temizler: '120.01', '120 01', 120 → '120'"""
    if raw is None:
        return None
    s = str(raw).strip().split(".")[0].split(" ")[0].split("-")[0]
    s = re.sub(r"\D", "", s)
    return s if s else None


def _find_columns(ws) -> tuple[int | None, int | None, int | None]:
    """
    Hesap kodu, borç ve alacak kolonlarını otomatik tespit eder.
    Üç değer döner: (code_col, borc_col, alacak_col)
    Tek bakiye kolonlu formatlarda alacak_col=None döner.
    """
    max_col = min(ws.max_column, 20)
    code_col = None
    borc_col = None
    alacak_col = None
    balance_col = None

    for row in ws.iter_rows(min_row=1, max_row=20, max_col=max_col):
        for cell in row:
            val = str(cell.value or "").strip().lower()
            if any(kw in val for kw in ["hesap kodu", "kod", "hs. kd", "hs.kd", "account"]):
                code_col = cell.column
            # Borç kolonu
            if any(kw in val for kw in ["borç bakiye", "borç tutar", "borc bakiye", "debit"]):
                borc_col = cell.column
            # Alacak kolonu
            if any(kw in val for kw in ["alacak bakiye", "alacak tutar", "credit"]):
                alacak_col = cell.column
            # Tek bakiye kolonu
            if any(kw in val for kw in ["net bakiye", "net tutar", "bakiye", "tutar", "balance"]):
                if "borç" not in val and "alacak" not in val and "borc" not in val:
                    balance_col = cell.column

    if code_col is None:
        code_col = 1

    # Borç/alacak çift kolon varsa öncelik onlarda
    if borc_col and alacak_col:
        return code_col, borc_col, alacak_col

    # Tek bakiye kolonu
    if balance_col:
        return code_col, balance_col, None

    # Fallback: son numeric kolon
    for row in ws.iter_rows(min_row=2, max_row=10, max_col=max_col):
        for cell in reversed(row):
            if isinstance(cell.value, (int, float)):
                balance_col = cell.column
                break
        if balance_col:
            break

    return code_col, balance_col, None


def _is_parent_code(code, all_codes):
    prefix = code + "."
    for other in all_codes:
        if other != code and other.startswith(prefix):
            return True
    return False


def _get_root3(code):
    return code.split(".")[0][:3]


def _read_excel(filepath):
    wb = openpyxl.load_workbook(filepath, data_only=True)
    best_ws = max(wb.worksheets, key=lambda ws: ws.max_row)
    code_col, borc_col, alacak_col = _find_columns(best_ws)
    if not code_col or not borc_col:
        raise ValueError("Hesap kodu veya bakiye kolonu tespit edilemedi.")

    raw_rows = []
    for row in best_ws.iter_rows(min_row=2):
        raw_code = row[code_col - 1].value
        if raw_code is None:
            continue
        s = str(raw_code).strip()
        s = re.sub(r"[^0-9.]", ".", s)
        s = re.sub(r"[.]+", ".", s).strip(".")
        if not s:
            continue
        try:
            borc = float(row[borc_col - 1].value or 0)
        except (TypeError, ValueError):
            borc = 0.0
        alacak = 0.0
        if alacak_col:
            try:
                alacak = float(row[alacak_col - 1].value or 0)
            except (TypeError, ValueError):
                alacak = 0.0
        raw_rows.append((s, borc, alacak))

    if not raw_rows:
        return []

    all_codes = set(r[0] for r in raw_rows)
    has_hierarchy = any("." in code for code in all_codes)

    result = []
    skipped = 0
    for code, borc, alacak in raw_rows:
        if borc == 0 and alacak == 0:
            continue
        if has_hierarchy and _is_parent_code(code, all_codes):
            skipped += 1
            continue
        root = _get_root3(code)
        if not root:
            continue
        # Bakiye hesapla
        # Eğer bakiye sütunları bulunduysa (E=borc bakiye, F=alacak bakiye):
        # borc sütunu = borç bakiyesi, alacak sütunu = alacak bakiyesi
        # Hangisi sıfırdan büyükse onu al — ikisi aynı anda dolu olmaz
        # Eğer hareket sütunları bulunduysa (C=borc tutarı, D=alacak tutarı):
        # net = borc - alacak
        if alacak_col is not None:
            # Her iki sütun da var - bakiye mi hareket mi olduğunu anla
            # Bakiye sütunlarında biri 0, diğeri dolu olur
            # Hareket sütunlarında ikisi de dolu olabilir
            if borc > 0 and alacak > 0:
                # Her ikisi de dolu = hareket sütunları, net al
                balance = borc - alacak if borc > alacak else alacak - borc
            elif borc > 0:
                balance = borc
            elif alacak > 0:
                balance = alacak
            else:
                continue
        else:
            balance = borc if borc > 0 else 0
        if balance > 0:
            result.append((root, balance))

    print(f"{'detay' if has_hierarchy else 'duz'} mizan | ham:{len(raw_rows)} atlanan:{skipped} islenen:{len(result)}")
    return result

# ─────────────────────────────────────────────
# 4. KURAL TABANLI EŞLEŞTİRME
# ─────────────────────────────────────────────

def _match_code(code: str) -> list[tuple[str, int]]:
    """
    Hesap kodunu TDHP tablosuna eşleştirir.
    Önce tam eşleşme, sonra 3 haneli prefix, sonra 2 haneli prefix dener.
    """
    # Tam eşleşme (3 hane)
    if code[:3] in _CODE_LOOKUP:
        return _CODE_LOOKUP[code[:3]]
    # 2 haneli prefix
    if len(code) >= 2 and code[:2] in _CODE_LOOKUP:
        return _CODE_LOOKUP[code[:2]]
    return []


def _apply_rules(rows: list[tuple[str, float]]) -> tuple[BalanceSheet, float]:
    """
    Satırları TDHP tablosuna göre BalanceSheet'e uygular.
    match_rate: eşleşen satır sayısı / toplam satır sayısı
    """
    bs = BalanceSheet()
    matched = 0

    for code, balance in rows:
        mappings = _match_code(code)
        if not mappings:
            logger.debug(f"Eşleşmeyen kod: {code} ({balance:,.0f})")
            continue
        matched += 1
        for field_name, sign in mappings:
            current = getattr(bs, field_name)
            setattr(bs, field_name, current + sign * balance)

    match_rate = matched / len(rows) if rows else 0.0
    bs.match_rate = match_rate
    return bs, match_rate


# ─────────────────────────────────────────────
# 5. AI FALLBACK (Claude API)
# ─────────────────────────────────────────────

def _ai_tamamla(bs: BalanceSheet, rows: list[tuple[str, float]], sector: str) -> BalanceSheet:
    """
    Fix kuralların eşleşme oranı yüksek ama bazı kalemler sıfır kaldıysa,
    AI sadece eksikleri tamamlar. Mevcut değerlere dokunmaz.
    """
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic paketi yok, AI tamamlama atlandı.")
        return bs

    kritik_alanlar = [
        "net_satislar", "satislarin_maliyeti", "finansman_giderleri",
        "genel_yonetim_giderleri", "stoklar", "ticari_alacaklar",
        "ticari_borclar_kv", "banka_kredileri_kv", "banka_kredileri_uv",
    ]
    eksik = [f for f in kritik_alanlar if getattr(bs, f, 0) == 0]

    if not eksik:
        logger.info("AI tamamlama: eksik kritik kalem yok, atlandı.")
        return bs

    logger.info(f"AI tamamlama: eksik kalemler → {eksik}")

    mizan_text = "\n".join(f"{code}\t{balance:,.2f}" for code, balance in rows[:200])
    eksik_str = ", ".join(eksik)

    system_prompt = f"""Sen bir Türk muhasebe uzmanısın.
Sana bir mizan veriliyor. Şu kalemler tespit edilemedi: {eksik_str}
SADECE bu eksik kalemlerin değerlerini JSON olarak ver.
Diğer kalemlere dokunma. Markdown veya açıklama ekleme, sadece JSON."""

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": f"Sektör: {sector}\n\nMizan:\n{mizan_text}"
            }]
        )
        raw = re.sub(r"```json|```", "", response.content[0].text).strip()
        data = json.loads(raw)
        for field_name, value in data.items():
            if hasattr(bs, field_name) and getattr(bs, field_name) == 0:
                try:
                    setattr(bs, field_name, float(value or 0))
                except (TypeError, ValueError):
                    pass
        logger.info("AI tamamlama başarılı.")
    except Exception as e:
        logger.warning(f"AI tamamlama başarısız: {e}")

    return bs


def _parse_with_ai(rows: list[tuple[str, float]], sector: str) -> BalanceSheet:
    """
    Kural tabanlı eşleşme düşük olduğunda Claude API'ye gönderir.
    Dönen JSON'u BalanceSheet'e dönüştürür.
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic paketi kurulu değil: pip install anthropic")

    # Mizan satırlarını metin olarak hazırla
    mizan_text = "\n".join(f"{code}\t{balance:,.2f}" for code, balance in rows[:300])

    system_prompt = """Sen bir Türk muhasebe uzmanısın. Sana bir mizan verilecek.
Mizan'daki hesap kodu ve bakiye verilerinden standart bilanço ve gelir tablosu kalemlerini çıkar.
SADECE JSON formatında yanıt ver, başka hiçbir metin ekleme.

JSON yapısı şu field'ları içermeli (TL cinsinden float değerler):
kasa, banka, diger_hazir_degerler, ticari_alacaklar, diger_alacaklar_kv, stoklar,
diger_donen_varliklar, ticari_alacaklar_uv, diger_alacaklar_uv, mali_duran_varliklar,
maddi_duran_varliklar, maddi_olmayan_duv, diger_duran_varliklar,
banka_kredileri_kv, uzun_vadeli_borclar_kv, ticari_borclar_kv, ortaklara_borclar,
diger_kv_borclar, banka_kredileri_uv, diger_uv_borclar,
odenmis_sermaye, sermaye_yedekleri, kar_yedekleri, gecmis_yil_karlari, donem_net_kari,
net_satislar, satislarin_maliyeti, pazarlama_giderleri, genel_yonetim_giderleri,
arge_giderleri, diger_faaliyet_gelirleri, diger_faaliyet_giderleri,
finansman_gelirleri, finansman_giderleri, vergi_gideri"""

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=system_prompt,
        messages=[{
            "role": "user",
            "content": f"Sektör: {sector}\n\nMizan:\nKod\tBakiye\n{mizan_text}"
        }]
    )

    raw = response.content[0].text.strip()
    # JSON fences temizle
    raw = re.sub(r"```json|```", "", raw).strip()
    data = json.loads(raw)

    bs = BalanceSheet()
    for field_name, value in data.items():
        if hasattr(bs, field_name):
            try:
                setattr(bs, field_name, float(value or 0))
            except (TypeError, ValueError):
                pass

    bs.parse_method = "ai_fallback"
    bs.match_rate = 1.0
    return bs


# ─────────────────────────────────────────────
# 6. DOĞRULAMA
# ─────────────────────────────────────────────

def _normalize_bilanco(bs: BalanceSheet) -> BalanceSheet:
    """
    Mizan türünü tespit eder ve aktif-pasif dengesini sağlar.

    İki meşru mizan tipi:
    A) Yıl sonu kapatılmış: 590 > 0, 600-699 = 0 → bilanço dengeli
    B) Ara dönem açık:      590 = 0, 600-699 > 0 → bilanço dengeli

    Sorunlu durum — her ikisi aynı anda:
    590 > 0 VE 600 > 0 → muhasebeci yıl sonu kapatmış ama
    gelir tablosunu da bırakmış. Bu durumda 590'ı baz al,
    gelir tablosu kalemlerini scorer/analyzer için koru
    ama bilanço dengesini bozmamak için donem_net_kari'ni
    gelir tablosundan türetilmiş değerle ezmeyiz.

    Negatif duran varlık koruması:
    Mizanda net bakiye geliyorsa amortisman zaten düşülmüştür.
    """
    # Negatif duran varlık koruması
    if bs.maddi_duran_varliklar < 0:
        bs.maddi_duran_varliklar = 0
    if bs.maddi_olmayan_duv < 0:
        bs.maddi_olmayan_duv = 0

    # Mizan tipi tespiti
    var_590 = bs.donem_net_kari != 0
    var_600 = bs.net_satislar != 0

    if var_590 and var_600:
        # Çakışma: ikisi birden var
        # 590 hesabı bilanço dengesini sağlıyor, güvenilir
        # Gelir tablosundan net kâr türetmeyi dondur —
        # net_kar property'si zaten 590'ı önceliklendiriyor
        logger.info("Mizan tipi: Yıl sonu + gelir tablosu çakışması — 590 baz alınıyor.")
        bs.warnings = getattr(bs, 'warnings', [])
        bs.warnings.append(
            "Mizanda hem 590 (dönem net kârı) hem gelir tablosu kalemleri mevcut. "
            "Bilanço dengesi için 590 baz alındı."
        )
    elif var_590 and not var_600:
        logger.info("Mizan tipi: Yıl sonu kapatılmış — 590 mevcut, gelir tablosu kapalı.")
    elif not var_590 and var_600:
        logger.info("Mizan tipi: Ara dönem açık — gelir tablosu kalemlerinden net kâr türetilecek.")
        # Gelir tablosundan net kâr hesapla ve özkaynağa ekle
        hesaplanan_net_kar = (
            bs.net_satislar - bs.satislarin_maliyeti
            - bs.faaliyet_giderleri
            + bs.diger_faaliyet_gelirleri - bs.diger_faaliyet_giderleri
            + bs.finansman_gelirleri - bs.finansman_giderleri
            - bs.vergi_gideri
        )
        bs.donem_net_kari = hesaplanan_net_kar
        logger.info(f"Ara dönem net kârı hesaplandı: {hesaplanan_net_kar:,.0f} ₺")
    else:
        logger.warning("Mizan tipi tespit edilemedi — ne 590 ne de 600 mevcut.")

    # Son kontrol: aktif-pasif hâlâ tutmuyorsa logla, müdahale etme
    aktif = bs.toplam_aktif
    pasif = bs.toplam_pasif
    if aktif > 0 and pasif > 0:
        fark_oran = abs(aktif - pasif) / max(aktif, pasif)
        if fark_oran > 0.02:  # %2'den fazla fark varsa uyar
            logger.warning(
                f"Bilanço dengesi sağlanamadı: Aktif {aktif:,.0f} ₺, "
                f"Pasif {pasif:,.0f} ₺ (fark %{fark_oran*100:.1f}) — "
                f"muhtemelen mizanda eksik kalemler var."
            )

    return bs


def _validate(bs: BalanceSheet) -> list[str]:
    """Temel muhasebe denklemlerini kontrol eder, uyarı listesi döner."""
    warnings = []

    # Aktif = Pasif kontrolü (±%5 tolerans)
    if bs.toplam_aktif > 0:
        imbalance = abs(bs.toplam_aktif - bs.toplam_pasif) / bs.toplam_aktif
        if imbalance > 0.05:
            warnings.append(
                f"Aktif-Pasif dengesi bozuk: Aktif {bs.toplam_aktif:,.0f} ₺, "
                f"Pasif {bs.toplam_pasif:,.0f} ₺ (fark %{imbalance*100:.1f})"
            )

    # Net satış sıfır uyarısı
    if bs.net_satislar == 0:
        warnings.append("Net satış sıfır — gelir tablosu verileri eksik olabilir.")

    # Negatif özkaynak uyarısı
    if bs.ozkaynaklar < 0:
        warnings.append("Özkaynaklar negatif — şirket teknik olarak borca batık.")

    # Toplam aktif sıfır
    if bs.toplam_aktif == 0:
        warnings.append("Toplam aktif sıfır — parse başarısız olmuş olabilir.")

    return warnings


# ─────────────────────────────────────────────
# 7. ANA FONKSİYON
# ─────────────────────────────────────────────

def parse_mizan(
    filepath: str | Path,
    sector: str = "ticaret",
    use_ai_fallback: bool = True,
) -> BalanceSheet:
    """
    Ana parser fonksiyonu — Hybrid model.

    Akış:
      1. Fix kurallar (TDHP hesap kodu eşleştirme) çalışır
      2. use_ai_fallback=True ise AI her zaman devreye girer:
         - Eşleşme %80+ → AI sadece eksik/sıfır kalemleri tamamlar
         - Eşleşme %80 altı → AI tüm mizanı baştan parse eder
      3. Doğrulama çalışır

    Args:
        filepath: Excel mizan dosyası yolu
        sector: "ticaret" | "uretim" | "hizmet"
        use_ai_fallback: AI tamamlama kullanılsın mı (önerilen: True)

    Returns:
        BalanceSheet: Normalize edilmiş finansal veriler
    """
    logger.info(f"Parser başladı: {filepath}")

    # Excel oku
    rows = _read_excel(filepath)
    if not rows:
        raise ValueError("Excel dosyasında geçerli satır bulunamadı.")
    logger.info(f"{len(rows)} satır okundu.")

    # Aşama 1: Fix kurallar
    bs, match_rate = _apply_rules(rows)
    logger.info(f"Fix kural eşleşmesi: %{match_rate*100:.1f}")

    if use_ai_fallback:
        if match_rate >= 0.80:
            # Yüksek eşleşme — AI sadece eksik kalemleri tamamlar
            logger.info("Yüksek eşleşme — AI eksik kalemleri tamamlıyor...")
            bs = _ai_tamamla(bs, rows, sector)
            bs.parse_method = "hybrid"
        else:
            # Düşük eşleşme — AI tüm mizanı baştan parse eder
            logger.info(f"Düşük eşleşme (%{match_rate*100:.0f}) — AI tam parse yapıyor...")
            bs = _parse_with_ai(rows, sector)
            bs.warnings.append(
                f"Fix kural eşleşmesi %{match_rate*100:.0f} — AI ile tam parse yapıldı."
            )

    # Aşama 2: Bilanço normalize et (denge düzeltme)
    bs = _normalize_bilanco(bs)

    # Doğrulama
    validation_warnings = _validate(bs)
    bs.warnings.extend(validation_warnings)

    for w in bs.warnings:
        logger.warning(w)

    logger.info(f"Parse tamamlandı. Yöntem: {bs.parse_method}, "
                f"Toplam Aktif: {bs.toplam_aktif:,.0f} ₺")
    return bs


# ─────────────────────────────────────────────
# 8. CLI — TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        print("Kullanım: python parser.py mizan.xlsx [ticaret|uretim|hizmet]")
        sys.exit(1)

    filepath = sys.argv[1]
    sector = sys.argv[2] if len(sys.argv) > 2 else "ticaret"

    bs = parse_mizan(filepath, sector)
    result = bs.to_dict()

    print("\n" + "="*50)
    print("BİLANÇO ÖZETİ")
    print("="*50)
    print(f"Dönen Varlıklar   : {bs.donen_varliklar:>15,.0f} ₺")
    print(f"Duran Varlıklar   : {bs.duran_varliklar:>15,.0f} ₺")
    print(f"Toplam Aktif      : {bs.toplam_aktif:>15,.0f} ₺")
    print(f"KV Borçlar        : {bs.kv_borclar:>15,.0f} ₺")
    print(f"UV Borçlar        : {bs.uv_borclar:>15,.0f} ₺")
    print(f"Özkaynaklar       : {bs.ozkaynaklar:>15,.0f} ₺")
    print(f"Toplam Pasif      : {bs.toplam_pasif:>15,.0f} ₺")
    print()
    print("GELİR TABLOSU")
    print("="*50)
    print(f"Net Satışlar      : {bs.net_satislar:>15,.0f} ₺")
    print(f"Brüt Kâr          : {bs.brut_kar:>15,.0f} ₺")
    print(f"FAVÖK             : {bs.favok:>15,.0f} ₺")
    print(f"Net Kâr           : {bs.net_kar:>15,.0f} ₺")
    print()
    if bs.warnings:
        print("UYARILAR")
        print("="*50)
        for w in bs.warnings:
            print(f"  ⚠ {w}")
    print(f"\nEşleşme oranı: %{bs.match_rate*100:.1f} | Yöntem: {bs.parse_method}")
