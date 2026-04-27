"""
BilankoIQ — Scorer
BalanceSheet objesinden 28 rasyo hesaplar, 18'ini skorlar,
kırmızı bayrakları tespit eder, KrediSkor + harf notu üretir.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

Sektor = str  # "ticaret"/"uretim"/"hizmet" veya NACE kodu ("23.63.01")


# ─────────────────────────────────────────────
# 1. ÇIKTI MODELLERİ
# ─────────────────────────────────────────────

@dataclass
class RasyoSonuc:
    ad: str
    formul: str
    deger: float
    deger_fmt: str          # Ekranda gösterilecek format
    bant: str               # "mukemmel" | "iyi" | "zayif" | "kotu"
    puan: float             # Bu rasyodan kazanılan puan
    max_puan: float         # Bu rasyonun toplam ağırlığı
    aciklama: str           # Bant açıklaması
    kategori: str


@dataclass
class KirmiziBayrak:
    kod: str
    mesaj: str
    ciddiyet: Literal["kritik", "uyari"]


@dataclass
class SkorSonuc:
    # Ana skor
    toplam_puan: float
    max_puan: float = 100.0
    skor: int = 0           # 0-100
    harf: str = ""          # AAA, AA, A, BBB, BB, B, D

    # Kategori puanları
    likidite_puan: float = 0.0
    sermaye_puan: float = 0.0
    karlilik_puan: float = 0.0
    faaliyet_puan: float = 0.0
    borc_puan: float = 0.0

    # Detay
    rasyolar: list[RasyoSonuc] = field(default_factory=list)
    kirmizi_bayraklar: list[KirmiziBayrak] = field(default_factory=list)

    # Kredi bilgisi
    kredi_band: str = ""
    kredi_limit_aciklama: str = ""
    teminat_aciklama: str = ""
    teminat_araclari: list[str] = field(default_factory=list)
    kgf_notu: str | None = None

    # Aksiyon
    aksiyon_listesi: list[dict] = field(default_factory=list)

    # Tüm 28 rasyo (eğitim paneli için)
    tum_rasyolar: dict = field(default_factory=dict)


# ─────────────────────────────────────────────
# 2. BANT TANIMLAMALARI
# ─────────────────────────────────────────────

# Her rasyo: (ad, formül, max_puan, kategori, yön, eşikler_per_sektör)
# yön: "yuksek_iyi" | "dusuk_iyi"
# eşikler: {sektor: (mukemmel, iyi, zayif)} — zayıf altı = kötü

RASYO_TANIMLARI = [

    # ── LİKİDİTE (22p) ──────────────────────────────────────────────
    {
        "id": "cari_oran",
        "ad": "Cari oran",
        "formul": "Dönen Varlıklar / KV Borçlar",
        "max_puan": 9,
        "kategori": "likidite",
        "yon": "yuksek_iyi",
        "esikler": {
            "ticaret": (2.0, 1.5, 1.0),
            "uretim":  (1.7, 1.3, 1.0),
            "hizmet":  (1.5, 1.2, 0.9),
        },
    },
    {
        "id": "asit_test",
        "ad": "Asit-test oranı",
        "formul": "(Dönen V. - Stok) / KV Borçlar",
        "max_puan": 8,
        "kategori": "likidite",
        "yon": "yuksek_iyi",
        "esikler": {
            "ticaret": (1.3, 1.0, 0.7),
            "uretim":  (1.1, 0.8, 0.6),
            "hizmet":  (1.4, 1.0, 0.7),
        },
    },
    {
        "id": "nakit_oran",
        "ad": "Nakit oranı",
        "formul": "(Kasa + Banka) / KV Borçlar",
        "max_puan": 5,
        "kategori": "likidite",
        "yon": "yuksek_iyi",
        "esikler": {
            "ticaret": (0.4, 0.2, 0.1),
            "uretim":  (0.3, 0.15, 0.08),
            "hizmet":  (0.5, 0.25, 0.1),
        },
    },

    # ── SERMAYE YAPISI (24p) ─────────────────────────────────────────
    {
        "id": "borc_ozkaynak",
        "ad": "Borç / Özkaynak",
        "formul": "Toplam Borç / Özkaynaklar",
        "max_puan": 10,
        "kategori": "sermaye",
        "yon": "dusuk_iyi",
        "esikler": {
            "ticaret": (1.0, 2.0, 3.5),
            "uretim":  (1.5, 2.5, 4.0),
            "hizmet":  (0.8, 1.5, 2.5),
        },
    },
    {
        "id": "finansal_kaldırac",
        "ad": "Finansal kaldıraç",
        "formul": "Toplam Aktif / Özkaynaklar",
        "max_puan": 7,
        "kategori": "sermaye",
        "yon": "dusuk_iyi",
        "esikler": {
            "ticaret": (2.0, 3.0, 4.5),
            "uretim":  (2.5, 3.5, 5.0),
            "hizmet":  (1.8, 2.5, 3.5),
        },
    },
    {
        "id": "kv_borc_orani",
        "ad": "KV Borç / Toplam Borç",
        "formul": "KV Borçlar / Toplam Borçlar",
        "max_puan": 4,
        "kategori": "sermaye",
        "yon": "dusuk_iyi",
        "esikler": {
            "ticaret": (0.40, 0.60, 0.80),
            "uretim":  (0.35, 0.50, 0.75),
            "hizmet":  (0.40, 0.55, 0.80),
        },
    },
    {
        "id": "ortaklar_cari_orani",
        "ad": "Ortaklar cari / Toplam pasif",
        "formul": "Ortaklara Borçlar / Toplam Pasif",
        "max_puan": 3,
        "kategori": "sermaye",
        "yon": "dusuk_iyi",
        "esikler": {
            "ticaret": (0.05, 0.10, 0.25),
            "uretim":  (0.05, 0.10, 0.25),
            "hizmet":  (0.05, 0.10, 0.25),
        },
    },

    # ── KÂRLILIK (26p) ───────────────────────────────────────────────
    {
        "id": "brut_kar_marji",
        "ad": "Brüt kâr marjı",
        "formul": "Brüt Kâr / Net Satışlar",
        "max_puan": 4,
        "kategori": "karlilik",
        "yon": "yuksek_iyi",
        "esikler": {
            "ticaret": (0.30, 0.20, 0.10),
            "uretim":  (0.35, 0.25, 0.12),
            "hizmet":  (0.50, 0.35, 0.20),
        },
    },
    {
        "id": "favok_marji",
        "ad": "FAVÖK marjı",
        "formul": "FAVÖK / Net Satışlar",
        "max_puan": 7,
        "kategori": "karlilik",
        "yon": "yuksek_iyi",
        "esikler": {
            "ticaret": (0.15, 0.08, 0.03),
            "uretim":  (0.20, 0.12, 0.05),
            "hizmet":  (0.30, 0.18, 0.08),
        },
    },
    {
        "id": "faaliyet_gider_orani",
        "ad": "Faaliyet gideri oranı",
        "formul": "Faaliyet Giderleri / Net Satışlar",
        "max_puan": 2,
        "kategori": "karlilik",
        "yon": "dusuk_iyi",
        "esikler": {
            "ticaret": (0.08, 0.15, 0.25),
            "uretim":  (0.10, 0.18, 0.28),
            "hizmet":  (0.15, 0.25, 0.40),
        },
    },
    {
        "id": "net_kar_marji",
        "ad": "Net kâr marjı",
        "formul": "Net Kâr / Net Satışlar",
        "max_puan": 5,
        "kategori": "karlilik",
        "yon": "yuksek_iyi",
        "esikler": {
            "ticaret": (0.07, 0.03, 0.01),
            "uretim":  (0.10, 0.05, 0.02),
            "hizmet":  (0.18, 0.10, 0.04),
        },
    },
    {
        "id": "roe",
        "ad": "ROE — Özkaynak kârlılığı",
        "formul": "Net Kâr / Özkaynaklar",
        "max_puan": 6,
        "kategori": "karlilik",
        "yon": "yuksek_iyi",
        "esikler": {
            "ticaret": (0.20, 0.12, 0.05),
            "uretim":  (0.18, 0.10, 0.04),
            "hizmet":  (0.25, 0.15, 0.06),
        },
    },
    {
        "id": "roa",
        "ad": "ROA — Varlık kârlılığı",
        "formul": "Net Kâr / Toplam Aktif",
        "max_puan": 2,
        "kategori": "karlilik",
        "yon": "yuksek_iyi",
        "esikler": {
            "ticaret": (0.12, 0.06, 0.02),
            "uretim":  (0.10, 0.05, 0.02),
            "hizmet":  (0.15, 0.08, 0.03),
        },
    },

    # ── FAALİYET ETKİNLİĞİ (18p) ────────────────────────────────────
    {
        "id": "stok_devir",
        "ad": "Stok devir hızı",
        "formul": "Satış Maliyeti / Stoklar",
        "max_puan": 6,
        "kategori": "faaliyet",
        "yon": "yuksek_iyi",
        "esikler": {
            "ticaret": (12.0, 8.0, 4.0),
            "uretim":  (10.0, 6.0, 3.0),
            "hizmet":  (24.0, 12.0, 6.0),
        },
    },
    {
        "id": "alacak_tahsil_suresi",
        "ad": "Alacak tahsil süresi",
        "formul": "365 / (Net Satışlar / Ticari Alacaklar)",
        "max_puan": 6,
        "kategori": "faaliyet",
        "yon": "dusuk_iyi",
        "esikler": {
            "ticaret": (30, 45, 75),
            "uretim":  (45, 60, 90),
            "hizmet":  (20, 30, 50),
        },
    },
    {
        "id": "nakit_donusum_suresi",
        "ad": "Nakit dönüşüm süresi",
        "formul": "Stok günü + Alacak günü - Borç günü",
        "max_puan": 6,
        "kategori": "faaliyet",
        "yon": "dusuk_iyi",
        "esikler": {
            "ticaret": (30, 60, 90),
            "uretim":  (60, 90, 120),
            "hizmet":  (10, 20, 40),
        },
    },

    # ── BORÇ ÖDEME KAPASİTESİ (16p) ─────────────────────────────────
    {
        "id": "faiz_karsilama",
        "ad": "Faiz karşılama oranı",
        "formul": "FAVÖK / Finansman Giderleri",
        "max_puan": 6,
        "kategori": "borc",
        "yon": "yuksek_iyi",
        "esikler": {
            "ticaret": (5.0, 3.0, 1.5),
            "uretim":  (5.0, 3.0, 1.5),
            "hizmet":  (5.0, 3.0, 1.5),
        },
    },
    {
        "id": "net_borc_favok",
        "ad": "Net Borç / FAVÖK",
        "formul": "(Fin. Borçlar - Nakit) / FAVÖK",
        "max_puan": 6,
        "kategori": "borc",
        "yon": "dusuk_iyi",
        "esikler": {
            "ticaret": (1.5, 3.0, 5.0),
            "uretim":  (1.5, 3.0, 5.0),
            "hizmet":  (1.5, 3.0, 5.0),
        },
    },
    {
        "id": "finansman_gider_orani",
        "ad": "Finansman gideri / Net satış",
        "formul": "Finansman Giderleri / Net Satışlar",
        "max_puan": 4,
        "kategori": "borc",
        "yon": "dusuk_iyi",
        "esikler": {
            "ticaret": (0.02, 0.05, 0.09),
            "uretim":  (0.02, 0.05, 0.09),
            "hizmet":  (0.02, 0.05, 0.09),
        },
    },
]

# ─────────────────────────────────────────────
# NACE BÖLÜM EŞİKLERİ — dinamik türetme
# ─────────────────────────────────────────────

_LEGACY_TO_BOLUM = {"ticaret": "G", "uretim": "C", "hizmet": "M"}


def _sektor_to_bolum(sektor: str) -> str:
    """'ticaret'/'uretim'/'hizmet' veya NACE kodu → NACE bölüm harfi."""
    if sektor in _LEGACY_TO_BOLUM:
        return _LEGACY_TO_BOLUM[sektor]
    try:
        from analyzer import nace_to_bolum
        return nace_to_bolum(sektor)
    except Exception:
        return "G"


def _inject_nace_esikler() -> None:
    """
    NACE_BOLUM_ORT ortalamalarından eşik türetip RASYO_TANIMLARI'na enjekte eder.
    yuksek_iyi : (ort×1.2, ort×0.8, ort×0.6)
    dusuk_iyi  : (ort×0.8, ort×1.2, ort×1.6)
    K → J ortalaması, O → N ortalaması kullanılır.
    """
    try:
        from analyzer import NACE_BOLUM_ORT
    except Exception:
        return

    _BOLUMLER = ["A","B","C","D","E","F","G","H","I","J","K","L","M","N","P","Q","R","S"]
    _KAYNAK   = {"K": "J", "O": "N"}

    for t in RASYO_TANIMLARI:
        rid = t["id"]
        yon = t["yon"]
        for bolum in _BOLUMLER:
            kaynak      = _KAYNAK.get(bolum, bolum)
            ort         = NACE_BOLUM_ORT.get(kaynak, NACE_BOLUM_ORT["G"]).get(rid)
            if not ort:
                continue
            if yon == "yuksek_iyi":
                t["esikler"][bolum] = (ort * 1.2, ort * 0.8, ort * 0.6)
            else:
                t["esikler"][bolum] = (ort * 0.8, ort * 1.2, ort * 1.6)


_inject_nace_esikler()

# Puan çarpanları: mukemmel=1.0, iyi=0.65, zayıf=0.30, kötü=0.0
KATEGORI_MAX = {k: sum(t["max_puan"] for t in RASYO_TANIMLARI if t["kategori"] == k)
               for k in ["likidite", "sermaye", "karlilik", "faaliyet", "borc"]}

BANT_CARPAN = {"mukemmel": 1.0, "iyi": 0.65, "zayif": 0.30, "kotu": 0.0}
BANT_ETIKET = {
    "mukemmel": "Mükemmel",
    "iyi": "İyi",
    "zayif": "Zayıf",
    "kotu": "Kötü",
}


# ─────────────────────────────────────────────
# 3. BANT HESAPLAMA
# ─────────────────────────────────────────────

def _bant_bul(deger: float, esikler: tuple, yon: str) -> str:
    """
    Verilen değer için bant belirler.
    esikler = (mukemmel_esik, iyi_esik, zayif_esik)
    """
    m, i, z = esikler
    if yon == "yuksek_iyi":
        if deger >= m:  return "mukemmel"
        if deger >= i:  return "iyi"
        if deger >= z:  return "zayif"
        return "kotu"
    else:  # dusuk_iyi
        if deger <= m:  return "mukemmel"
        if deger <= i:  return "iyi"
        if deger <= z:  return "zayif"
        return "kotu"


def _fmt_deger(deger: float, rasyo_id: str) -> str:
    """Değeri ekran formatına çevirir."""
    yuzde_rasyolar = {
        "favok_marji", "net_kar_marji", "roe", "roa",
        "ortaklar_cari_orani", "finansman_gider_orani",
        "kv_borc_orani", "brut_kar_marji", "faaliyet_gider_orani",
    }
    gun_rasyolar = {"alacak_tahsil_suresi", "nakit_donusum_suresi"}
    x_rasyolar = {"stok_devir", "faiz_karsilama", "net_borc_favok",
                  "finansal_kaldırac", "borc_ozkaynak", "cari_oran",
                  "asit_test", "nakit_oran"}

    if rasyo_id in yuzde_rasyolar:
        return f"%{deger * 100:.1f}"
    if rasyo_id in gun_rasyolar:
        return f"{deger:.0f} gün"
    return f"{deger:.2f}x"


# ─────────────────────────────────────────────
# 4. RASYO DEĞERLERİ HESAPLAMA
# ─────────────────────────────────────────────

def _hesapla_degerler(bs) -> dict[str, float]:
    """BalanceSheet'ten tüm rasyo değerlerini hesaplar."""
    safe = lambda a, b: a / b if b and b != 0 else 0.0

    # Yardımcı değerler
    stok_gun = safe(bs.stoklar * 365, bs.satislarin_maliyeti) if bs.satislarin_maliyeti else 0
    alacak_gun = safe(bs.ticari_alacaklar * 365, bs.net_satislar)
    borc_gun = safe(bs.ticari_borclar_kv * 365, bs.satislarin_maliyeti) if bs.satislarin_maliyeti else 0
    nds = stok_gun + alacak_gun - borc_gun

    return {
        # Likidite
        "cari_oran":            safe(bs.donen_varliklar, bs.kv_borclar),
        "asit_test":            safe(bs.donen_varliklar - bs.stoklar, bs.kv_borclar),
        "nakit_oran":           safe(bs.nakit_ve_benzerleri, bs.kv_borclar),

        # Sermaye yapısı
        "borc_ozkaynak":        safe(bs.toplam_borclar, bs.ozkaynaklar),
        "finansal_kaldırac":    safe(bs.toplam_aktif, bs.ozkaynaklar),
        "kv_borc_orani":        safe(bs.kv_borclar, bs.toplam_borclar),
        "ortaklar_cari_orani":  safe(bs.ortaklara_borclar, bs.toplam_pasif),

        # Kârlılık
        "favok_marji":          safe(bs.favok, bs.net_satislar),
        "net_kar_marji":        safe(bs.net_kar, bs.net_satislar),
        "roe":                  safe(bs.net_kar, bs.ozkaynaklar),

        # Faaliyet etkinliği
        "stok_devir":           safe(bs.satislarin_maliyeti, bs.stoklar),
        "alacak_tahsil_suresi": alacak_gun,
        "nakit_donusum_suresi": nds,

        # Borç ödeme
        "faiz_karsilama":       safe(bs.favok, bs.finansman_giderleri),
        "net_borc_favok":       safe(bs.net_borc, bs.favok),
        "finansman_gider_orani":safe(bs.finansman_giderleri, bs.net_satislar),

        # Gelir tablosu rasyoları (skorlamaya giriyor)
        "brut_kar_marji":       safe(bs.brut_kar, bs.net_satislar),
        "faaliyet_gider_orani": safe(bs.faaliyet_giderleri, bs.net_satislar),
        "roa":                  safe(bs.net_kar, bs.toplam_aktif),

        # Ek rasyolar (eğitim paneli — skorlamaya girmiyor)
        "net_isletme_sermayesi": bs.donen_varliklar - bs.kv_borclar,
        "ozkaynak_aktif":       safe(bs.ozkaynaklar, bs.toplam_aktif),
        "net_borc_tl":          bs.net_borc,
        "stok_gun":             stok_gun,
        "borc_odeme_suresi":    borc_gun,
        "aktif_devir":          safe(bs.net_satislar, bs.toplam_aktif),
        "finansal_borc_favok":  safe(bs.finansal_borclar, bs.favok),
        "favok_tl":             bs.favok,
        "net_kar_tl":           bs.net_kar,
        "brut_kar_tl":          bs.brut_kar,
    }


# ─────────────────────────────────────────────
# 5. KIRMIZI BAYRAKLAR
# ─────────────────────────────────────────────

def _kirmizi_bayraklar_kontrol(bs, degerler: dict) -> list[KirmiziBayrak]:
    bayraklar = []

    if degerler["faiz_karsilama"] < 1.0 and bs.finansman_giderleri > 0:
        bayraklar.append(KirmiziBayrak(
            kod="faiz_odeme_riski",
            mesaj="Faaliyet kârınız finansman giderinizi karşılamıyor. "
                  "Bankalar bu dosyayı otomatik reddedebilir.",
            ciddiyet="kritik"
        ))

    if bs.ozkaynaklar < 0:
        bayraklar.append(KirmiziBayrak(
            kod="negatif_ozkaynak",
            mesaj="Özkaynaklar negatif — şirket teknik olarak borca batık. "
                  "Kredi imkânı çok sınırlı.",
            ciddiyet="kritik"
        ))

    if degerler["net_borc_favok"] > 6.0 and bs.favok > 0:
        bayraklar.append(KirmiziBayrak(
            kod="asiri_borclanma",
            mesaj=f"Net Borç/FAVÖK {degerler['net_borc_favok']:.1f}x — "
                  "mevcut nakit akışıyla borç 6 yılda kapanıyor. "
                  "Bankalar genellikle 4–5x üst sınır uygular.",
            ciddiyet="kritik"
        ))

    if degerler["cari_oran"] < 0.8:
        bayraklar.append(KirmiziBayrak(
            kod="likidite_krizi",
            mesaj="Kısa vadeli borçlarınızı dönen varlıklarınızla "
                  "karşılayamıyorsunuz. Acil işletme sermayesi riski var.",
            ciddiyet="kritik"
        ))

    if degerler["ortaklar_cari_orani"] > 0.25:
        bayraklar.append(KirmiziBayrak(
            kod="ortaklar_cari_siskinligi",
            mesaj=f"Ortaklara borç pasifin %{degerler['ortaklar_cari_orani']*100:.0f}'i. "
                  "Bankalar bunu özkaynak yetersizliğinin işareti sayar.",
            ciddiyet="uyari"
        ))

    if bs.favok < 0:
        bayraklar.append(KirmiziBayrak(
            kod="negatif_favok",
            mesaj="Esas faaliyetler zarar ediyor. "
                  "Kredi değerlendirmesi yapılamaz.",
            ciddiyet="kritik"
        ))

    return bayraklar


# ─────────────────────────────────────────────
# 6. HARF NOTU VE KREDİ BANDI
# ─────────────────────────────────────────────

HARF_BANTLARI = [
    (85, "AAA", "Mükemmel",      "FAVÖK × 3x − mevcut borç",  "Kişisel kefalet yeterli"),
    (75, "AA",  "Çok iyi",       "FAVÖK × 2.5x − mevcut borç","Kişisel kefalet + POS blokesi veya alacak çeki temliki"),
    (65, "A",   "İyi",           "FAVÖK × 2x − mevcut borç",  "Kefalet + alacak çekleri/senet temliki veya KGF kefaleti"),
    (55, "BBB", "Orta",          "Teminat değeri bazlı",       "KGF kefaleti + stok/araç rehni veya kısmi ipotek"),
    (45, "BB",  "Zayıf",         "Teminat değeri bazlı",       "1. derece ipotek + kişisel kefalet"),
    (35, "B",   "Riskli",        "Teminat değeri bazlı",       "Tam ipotek + mevduat blokesi + kişisel kefalet"),
    (0,  "D",   "Finansman erişimi sınırlı olabilir","—",      "—"),
]

# Bant bazında teminat araçlarının tam listesi
TEMINAT_DETAY = {
    "AAA": {
        "limit_aciklama": "FAVÖK × 3x − mevcut finansal borç",
        "teminat_araclari": [
            "Kişisel kefalet (ortak/yönetici)",
        ],
        "kgf_notu": None,
    },
    "AA": {
        "limit_aciklama": "FAVÖK × 2.5x − mevcut finansal borç",
        "teminat_araclari": [
            "Kişisel kefalet (ortak/yönetici)",
            "POS blokesi (1–3 aylık POS cirosu kadar)",
            "Alacak çekleri / senet temliki",
        ],
        "kgf_notu": None,
    },
    "A": {
        "limit_aciklama": "FAVÖK × 2x − mevcut finansal borç",
        "teminat_araclari": [
            "Kişisel kefalet (ortak/yönetici)",
            "Alacak çekleri / senet temliki",
            "Fatura temliki (spot faktoring)",
            "KGF kefaleti (opsiyonel — limit artırımı için)",
            "Araç / iş makinesi rehni",
        ],
        "kgf_notu": "KGF kefaleti alırsanız AA bandı limitine ulaşabilirsiniz.",
    },
    "BBB": {
        "limit_aciklama": "Teminat değeri bazlı (ipotek/rehin değerinin %70–80'i)",
        "teminat_araclari": [
            "KGF kefaleti (limit artırımı için önerilir)",
            "Kısmi gayrimenkul ipoteği (2. derece kabul edilebilir)",
            "Stok rehni (değişken kabul oranı, %40–50)",
            "Araç / iş makinesi rehni",
            "Alacak çekleri / senet temliki",
            "Kişisel kefalet (zorunlu ek teminat)",
        ],
        "kgf_notu": "KGF kefaleti alırsanız A bandı limitine ve teminat yapısına geçebilirsiniz.",
    },
    "BB": {
        "limit_aciklama": "Teminat değeri bazlı (1. derece ipotek değerinin %70'i)",
        "teminat_araclari": [
            "1. derece gayrimenkul ipoteği (zorunlu)",
            "Kişisel kefalet (zorunlu)",
            "Mevduat / repo blokesi (varsa)",
            "Araç / iş makinesi rehni",
        ],
        "kgf_notu": "KGF kefaleti + bilanço iyileştirmesiyle BBB bandına çıkabilirsiniz.",
    },
    "B": {
        "limit_aciklama": "Teminat değeri bazlı — çok sınırlı",
        "teminat_araclari": [
            "1. derece gayrimenkul ipoteği (zorunlu)",
            "Mevduat blokesi (zorunlu)",
            "Kişisel kefalet (zorunlu)",
            "Ek teminat talep edilebilir (araç, ekipman)",
        ],
        "kgf_notu": "Bu bantta KGF kefaleti tek başına yeterli olmaz, bilanço iyileştirmesi şart.",
    },
    "D": {
        "limit_aciklama": "—",
        "teminat_araclari": [],
        "kgf_notu": "Kredi değerlendirmesi yapılamaz. Önce bilanço iyileştirmesi gerekli.",
    },
}

def _harf_notu(skor: int) -> tuple[str, str, str, str, list[str], str | None]:
    """(harf, bant_aciklama, limit_aciklama, teminat_ozet, teminat_araclari, kgf_notu) döner."""
    for esik, harf, aciklama, limit, teminat in HARF_BANTLARI:
        if skor >= esik:
            detay = TEMINAT_DETAY.get(harf, {})
            return (
                harf,
                aciklama,
                detay.get("limit_aciklama", limit),
                teminat,
                detay.get("teminat_araclari", []),
                detay.get("kgf_notu"),
            )
    detay = TEMINAT_DETAY.get("D", {})
    return "D", "Finansman erişimi sınırlı olabilir", "—", "—", [], detay.get("kgf_notu")


# ─────────────────────────────────────────────
# 7. AKSİYON LİSTESİ
# ─────────────────────────────────────────────

AKSIYON_KATALOGU = [
    {
        "id": "ortaklar_cari_sermaye",
        "baslik": "Ortaklar cari hesabını sermayeye ekle",
        "etki": "Borç/Özkaynak ↓  ·  Finansal kaldıraç ↓  ·  Kırmızı bayrak kalkar",
        "zorluk": "Düşük",
        "ilgili_rasyolar": ["borc_ozkaynak", "finansal_kaldırac", "ortaklar_cari_orani"],
    },
    {
        "id": "kv_uv_cevirme",
        "baslik": "Kısa vadeli kredileri uzun vadeye çevir",
        "etki": "Cari oran ↑↑  ·  KV Borç/Toplam Borç ↓",
        "zorluk": "Orta",
        "ilgili_rasyolar": ["cari_oran", "kv_borc_orani"],
    },
    {
        "id": "alacak_tahsilat",
        "baslik": "Vadesi geçmiş alacakları tahsil et",
        "etki": "Asit-test ↑  ·  Alacak tahsil süresi ↓  ·  Nakit dönüşüm süresi ↓",
        "zorluk": "Orta",
        "ilgili_rasyolar": ["asit_test", "alacak_tahsil_suresi", "nakit_donusum_suresi"],
    },
    {
        "id": "stok_eritme",
        "baslik": "Yavaş dönen stokları erit",
        "etki": "Stok devir ↑  ·  Nakit dönüşüm süresi ↓  ·  Asit-test ↑",
        "zorluk": "Orta",
        "ilgili_rasyolar": ["stok_devir", "asit_test", "nakit_donusum_suresi"],
    },
    {
        "id": "sermaye_artirimi",
        "baslik": "Nakdi sermaye artırımı yap",
        "etki": "Borç/Özkaynak ↓  ·  Finansal kaldıraç ↓  ·  Cari oran ↑",
        "zorluk": "Yüksek",
        "ilgili_rasyolar": ["borc_ozkaynak", "finansal_kaldırac", "cari_oran"],
    },
    {
        "id": "finansman_maliyeti",
        "baslik": "Yüksek faizli kredileri refinanse et",
        "etki": "Faiz karşılama ↑  ·  Finansman gideri oranı ↓  ·  Net kâr ↑",
        "zorluk": "Orta",
        "ilgili_rasyolar": ["faiz_karsilama", "finansman_gider_orani", "net_kar_marji"],
    },
    {
        "id": "kar_dagitma",
        "baslik": "Kâr dağıtımı yapma, birikimli özkaynak büyüsün",
        "etki": "Borç/Özkaynak ↓  ·  ROE sabit  ·  Uzun vadeli etki",
        "zorluk": "Düşük",
        "ilgili_rasyolar": ["borc_ozkaynak", "finansal_kaldırac"],
    },
    {
        "id": "tedarikci_vade",
        "baslik": "Tedarikçi ödeme vadelerini uzat",
        "etki": "Nakit dönüşüm süresi ↓  ·  Likidite baskısı azalır",
        "zorluk": "Orta",
        "ilgili_rasyolar": ["nakit_donusum_suresi", "cari_oran"],
    },
]

def _aksiyon_listesi_olustur(
    rasyolar: list[RasyoSonuc],
    bayraklar: list[KirmiziBayrak],
) -> list[dict]:
    """
    Zayıf/kötü rasyolara göre öncelikli aksiyon listesi döner.
    Zorluk: Düşük > Orta > Yüksek sırasıyla önceliklendirilir.
    """
    zayif_rasyolar = {
        r.id for r in rasyolar
        if r.bant in ("zayif", "kotu")
    }
    bayrak_kodlari = {b.kod for b in bayraklar}

    skorlanmis = []
    for a in AKSIYON_KATALOGU:
        etki_sayisi = sum(1 for r in a["ilgili_rasyolar"] if r in zayif_rasyolar)
        if etki_sayisi == 0:
            continue
        zorluk_puan = {"Düşük": 3, "Orta": 2, "Yüksek": 1}.get(a["zorluk"], 1)
        # Kırmızı bayrak kaldıran aksiyonlara bonus
        bayrak_bonus = 2 if a["id"] == "ortaklar_cari_sermaye" and "ortaklar_cari_siskinligi" in bayrak_kodlari else 0
        oncelik = etki_sayisi * zorluk_puan + bayrak_bonus
        skorlanmis.append({**a, "oncelik": oncelik, "etki_sayisi": etki_sayisi})

    skorlanmis.sort(key=lambda x: x["oncelik"], reverse=True)
    return skorlanmis[:6]  # En fazla 6 aksiyon


# ─────────────────────────────────────────────
# 8. ANA FONKSİYON
# ─────────────────────────────────────────────

def skorla(bs, sektor: Sektor = "ticaret") -> SkorSonuc:
    """
    Ana skorlama fonksiyonu.

    Args:
        bs: BalanceSheet objesi (parser.py'dan)
        sektor: "ticaret" | "uretim" | "hizmet"

    Returns:
        SkorSonuc: Tam skor raporu
    """
    degerler = _hesapla_degerler(bs)

    # Her rasyoyu skorla
    rasyo_sonuclari: list[RasyoSonuc] = []
    kategori_max = {}
    for t in RASYO_TANIMLARI:
        kategori_max[t["kategori"]] = kategori_max.get(t["kategori"], 0) + t["max_puan"]

    kategori_puanlar = {
        "likidite": 0.0, "sermaye": 0.0,
        "karlilik": 0.0, "faaliyet": 0.0, "borc": 0.0,
    }

    for t in RASYO_TANIMLARI:
        rid = t["id"]
        deger = degerler.get(rid, 0.0)
        bolum   = _sektor_to_bolum(sektor)
        esikler = t["esikler"].get(bolum) or t["esikler"].get("ticaret")

        # Finansman gideri sıfırsa faiz_karsilama hesaplanamaz — max puan ver, N/A göster
        if rid == "faiz_karsilama" and bs.finansman_giderleri == 0:
            bant = "mukemmel"
            puan = t["max_puan"] * BANT_CARPAN[bant]
            rasyo_sonuclari.append(RasyoSonuc(
                ad=t["ad"],
                formul=t["formul"],
                deger=0.0,
                deger_fmt="N/A",
                bant=bant,
                puan=round(puan, 2),
                max_puan=t["max_puan"],
                aciklama="Finansman gideri yok — oran hesaplanamaz, değerlendirme dışı tutuldu.",
                kategori=t["kategori"],
            ))
            setattr(rasyo_sonuclari[-1], "id", rid)
            kategori_puanlar[t["kategori"]] += puan
            continue

        # Stok sıfırsa stok_devir hesaplanamaz — max puan ver, N/A göster
        if rid == "stok_devir" and bs.stoklar == 0:
            bant = "mukemmel"
            puan = t["max_puan"] * BANT_CARPAN[bant]
            rasyo_sonuclari.append(RasyoSonuc(
                ad=t["ad"],
                formul=t["formul"],
                deger=0.0,
                deger_fmt="N/A",
                bant=bant,
                puan=round(puan, 2),
                max_puan=t["max_puan"],
                aciklama="Stok bulunmuyor — oran hesaplanamaz, değerlendirme dışı tutuldu.",
                kategori=t["kategori"],
            ))
            setattr(rasyo_sonuclari[-1], "id", rid)
            kategori_puanlar[t["kategori"]] += puan
            continue

        bant = _bant_bul(deger, esikler, t["yon"])
        puan = t["max_puan"] * BANT_CARPAN[bant]

        # Bant açıklaması
        m, i, z = esikler
        if t["yon"] == "yuksek_iyi":
            if deger >= m:
                aciklama = f"Değer {round(deger,2)} — sektör normunun üzerinde, güçlü seviye."
            elif deger >= i:
                aciklama = f"Değer {round(deger,2)} — sektör normuna yakın, kabul edilebilir."
            elif deger >= z:
                aciklama = f"Değer {round(deger,2)} — sektör normunun altında, iyileştirme gerekiyor."
            else:
                aciklama = f"Değer {round(deger,2)} — kritik seviyede düşük, acil önlem gerekiyor."
        else:
            if deger <= m:
                aciklama = f"Değer {round(deger,2)} — sektör normunun altında, güçlü seviye."
            elif deger <= i:
                aciklama = f"Değer {round(deger,2)} — sektör normuna yakın, kabul edilebilir."
            elif deger <= z:
                aciklama = f"Değer {round(deger,2)} — sektör normunun üzerinde, iyileştirme gerekiyor."
            else:
                aciklama = f"Değer {round(deger,2)} — kritik seviyede yüksek, acil önlem gerekiyor."

        rasyo_sonuclari.append(RasyoSonuc(
            ad=t["ad"],
            formul=t["formul"],
            deger=deger,
            deger_fmt=_fmt_deger(deger, rid),
            bant=bant,
            puan=round(puan, 2),
            max_puan=t["max_puan"],
            aciklama=aciklama,
            kategori=t["kategori"],
        ))
        setattr(rasyo_sonuclari[-1], "id", rid)
        kategori_puanlar[t["kategori"]] += puan

    toplam = sum(r.puan for r in rasyo_sonuclari)
    skor = min(100, round(toplam))

    # Kırmızı bayraklar
    bayraklar = _kirmizi_bayraklar_kontrol(bs, degerler)

    # Kritik bayrak varsa skora tavan uygula (max 44 — BB bandında kalır)
    kritik_bayrak_var = any(b.ciddiyet == "kritik" for b in bayraklar)
    if kritik_bayrak_var:
        skor = min(skor, 44)

    harf, bant_aciklama, kredi_limit, teminat, teminat_araclari, kgf_notu = _harf_notu(skor)

    # Aksiyon listesi
    aksiyonlar = _aksiyon_listesi_olustur(rasyo_sonuclari, bayraklar)

    return SkorSonuc(
        toplam_puan=round(toplam, 2),
        skor=skor,
        harf=harf,
        likidite_puan=round(kategori_puanlar["likidite"], 2),
        sermaye_puan=round(kategori_puanlar["sermaye"], 2),
        karlilik_puan=round(kategori_puanlar["karlilik"], 2),
        faaliyet_puan=round(kategori_puanlar["faaliyet"], 2),
        borc_puan=round(kategori_puanlar["borc"], 2),
        rasyolar=rasyo_sonuclari,
        kirmizi_bayraklar=bayraklar,
        kredi_band=bant_aciklama,
        kredi_limit_aciklama=kredi_limit,
        teminat_aciklama=teminat,
        teminat_araclari=teminat_araclari,
        kgf_notu=kgf_notu,
        aksiyon_listesi=aksiyonlar,
        tum_rasyolar=degerler,
    )
