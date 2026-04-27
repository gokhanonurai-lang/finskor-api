"""
BilankoIQ — Analyzer
Her rasyo için:
  - Sektör ortalamasıyla karşılaştırma (sabit kural tabanlı)
  - ne_anlama_gelir ve nasil_iyilestirilir: reporter.py'deki _zenginlestir_analizler()
    tarafından tek Sonnet çağrısıyla dinamik olarak doldurulur.
"""

from __future__ import annotations
from dataclasses import dataclass

# ─────────────────────────────────────────────
# 1. SEKTÖR ORTALAMALARI
# Kaynak: TCMB Sektör Bilançoları, TÜİK, BDDK KOBİ verileri
# ─────────────────────────────────────────────

SEKTOR_ORT = {
    # (ticaret, üretim, hizmet)
    "cari_oran":            {"ticaret": 1.65, "uretim": 1.40, "hizmet": 1.35},
    "asit_test":            {"ticaret": 1.10, "uretim": 0.90, "hizmet": 1.15},
    "nakit_oran":           {"ticaret": 0.28, "uretim": 0.20, "hizmet": 0.35},
    "borc_ozkaynak":        {"ticaret": 1.80, "uretim": 2.20, "hizmet": 1.40},
    "finansal_kaldırac":    {"ticaret": 2.80, "uretim": 3.20, "hizmet": 2.40},
    "kv_borc_orani":        {"ticaret": 0.58, "uretim": 0.52, "hizmet": 0.55},
    "ortaklar_cari_orani":  {"ticaret": 0.08, "uretim": 0.07, "hizmet": 0.06},
    "brut_kar_marji":       {"ticaret": 0.22, "uretim": 0.28, "hizmet": 0.42},
    "favok_marji":          {"ticaret": 0.09, "uretim": 0.13, "hizmet": 0.22},
    "faaliyet_gider_orani": {"ticaret": 0.12, "uretim": 0.14, "hizmet": 0.20},
    "net_kar_marji":        {"ticaret": 0.04, "uretim": 0.07, "hizmet": 0.13},
    "roe":                  {"ticaret": 0.15, "uretim": 0.12, "hizmet": 0.18},
    "roa":                  {"ticaret": 0.06, "uretim": 0.05, "hizmet": 0.09},
    "stok_devir":           {"ticaret": 9.0,  "uretim": 7.0,  "hizmet": 18.0},
    "alacak_tahsil_suresi": {"ticaret": 48.0, "uretim": 65.0, "hizmet": 32.0},
    "nakit_donusum_suresi": {"ticaret": 55.0, "uretim": 80.0, "hizmet": 22.0},
    "faiz_karsilama":       {"ticaret": 3.2,  "uretim": 3.5,  "hizmet": 4.0},
    "net_borc_favok":       {"ticaret": 2.8,  "uretim": 3.2,  "hizmet": 2.2},
    "finansman_gider_orani":{"ticaret": 0.04, "uretim": 0.04, "hizmet": 0.03},
}

SEKTOR_ADI = {"ticaret": "Ticaret", "uretim": "Üretim", "hizmet": "Hizmet"}

# ─────────────────────────────────────────────
# NACE BÖLÜM ORTALAMALARI (A–S, 17 bölüm × 19 rasyo)
# Kaynak: TCMB, TÜİK, BDDK sektörel finansal veriler
# ─────────────────────────────────────────────

NACE_BOLUM_ORT = {
    "A": {"cari_oran":1.930,"asit_test":0.748,"nakit_oran":0.201,"borc_ozkaynak":0.789,"finansal_kaldırac":1.789,"kv_borc_orani":0.362,"ortaklar_cari_orani":0.05,"brut_kar_marji":0.164,"favok_marji":0.100,"faaliyet_gider_orani":0.18,"net_kar_marji":0.013,"roe":0.036,"roa":0.020,"stok_devir":10.8,"alacak_tahsil_suresi":43,"nakit_donusum_suresi":45,"faiz_karsilama":1.72,"net_borc_favok":1.45,"finansman_gider_orani":0.058},
    "B": {"cari_oran":1.549,"asit_test":0.912,"nakit_oran":0.257,"borc_ozkaynak":0.751,"finansal_kaldırac":1.751,"kv_borc_orani":0.506,"ortaklar_cari_orani":0.05,"brut_kar_marji":0.304,"favok_marji":0.142,"faaliyet_gider_orani":0.16,"net_kar_marji":0.039,"roe":0.084,"roa":0.048,"stok_devir":6.7,"alacak_tahsil_suresi":37,"nakit_donusum_suresi":39,"faiz_karsilama":2.15,"net_borc_favok":1.16,"finansman_gider_orani":0.066},
    "C": {"cari_oran":1.735,"asit_test":1.000,"nakit_oran":0.270,"borc_ozkaynak":0.931,"finansal_kaldırac":1.931,"kv_borc_orani":0.324,"ortaklar_cari_orani":0.07,"brut_kar_marji":0.112,"favok_marji":0.121,"faaliyet_gider_orani":0.14,"net_kar_marji":0.023,"roe":0.042,"roa":0.022,"stok_devir":6.9,"alacak_tahsil_suresi":43,"nakit_donusum_suresi":51,"faiz_karsilama":2.57,"net_borc_favok":0.97,"finansman_gider_orani":0.047},
    "D": {"cari_oran":2.293,"asit_test":1.424,"nakit_oran":0.316,"borc_ozkaynak":0.761,"finansal_kaldırac":1.761,"kv_borc_orani":0.248,"ortaklar_cari_orani":0.06,"brut_kar_marji":0.099,"favok_marji":0.178,"faaliyet_gider_orani":0.12,"net_kar_marji":0.015,"roe":0.012,"roa":0.007,"stok_devir":10.4,"alacak_tahsil_suresi":37,"nakit_donusum_suresi":78,"faiz_karsilama":1.42,"net_borc_favok":1.76,"finansman_gider_orani":0.125},
    "E": {"cari_oran":1.597,"asit_test":0.893,"nakit_oran":0.113,"borc_ozkaynak":1.208,"finansal_kaldırac":2.208,"kv_borc_orani":0.247,"ortaklar_cari_orani":0.06,"brut_kar_marji":0.126,"favok_marji":0.110,"faaliyet_gider_orani":0.15,"net_kar_marji":-0.003,"roe":-0.004,"roa":-0.002,"stok_devir":6.9,"alacak_tahsil_suresi":34,"nakit_donusum_suresi":51,"faiz_karsilama":2.34,"net_borc_favok":1.07,"finansman_gider_orani":0.047},
    "F": {"cari_oran":1.503,"asit_test":0.938,"nakit_oran":0.095,"borc_ozkaynak":1.907,"finansal_kaldırac":2.907,"kv_borc_orani":0.112,"ortaklar_cari_orani":0.06,"brut_kar_marji":0.171,"favok_marji":0.220,"faaliyet_gider_orani":0.14,"net_kar_marji":0.010,"roe":0.009,"roa":0.003,"stok_devir":4.6,"alacak_tahsil_suresi":59,"nakit_donusum_suresi":18,"faiz_karsilama":4.49,"net_borc_favok":0.56,"finansman_gider_orani":0.049},
    "G": {"cari_oran":1.563,"asit_test":0.876,"nakit_oran":0.224,"borc_ozkaynak":1.513,"finansal_kaldırac":2.513,"kv_borc_orani":0.244,"ortaklar_cari_orani":0.08,"brut_kar_marji":0.125,"favok_marji":0.108,"faaliyet_gider_orani":0.12,"net_kar_marji":0.019,"roe":0.048,"roa":0.019,"stok_devir":9.9,"alacak_tahsil_suresi":40,"nakit_donusum_suresi":72,"faiz_karsilama":4.15,"net_borc_favok":0.60,"finansman_gider_orani":0.026},
    "H": {"cari_oran":1.729,"asit_test":1.379,"nakit_oran":0.478,"borc_ozkaynak":0.825,"finansal_kaldırac":1.825,"kv_borc_orani":0.237,"ortaklar_cari_orani":0.06,"brut_kar_marji":0.121,"favok_marji":0.079,"faaliyet_gider_orani":0.18,"net_kar_marji":0.029,"roe":0.097,"roa":0.053,"stok_devir":11.9,"alacak_tahsil_suresi":33,"nakit_donusum_suresi":66,"faiz_karsilama":2.82,"net_borc_favok":0.89,"finansman_gider_orani":0.028},
    "I": {"cari_oran":1.503,"asit_test":0.981,"nakit_oran":0.381,"borc_ozkaynak":0.695,"finansal_kaldırac":1.695,"kv_borc_orani":0.282,"ortaklar_cari_orani":0.05,"brut_kar_marji":0.244,"favok_marji":0.116,"faaliyet_gider_orani":0.18,"net_kar_marji":0.035,"roe":0.042,"roa":0.025,"stok_devir":32.5,"alacak_tahsil_suresi":29,"nakit_donusum_suresi":75,"faiz_karsilama":3.14,"net_borc_favok":0.80,"finansman_gider_orani":0.037},
    "J": {"cari_oran":1.911,"asit_test":1.616,"nakit_oran":0.725,"borc_ozkaynak":0.538,"finansal_kaldırac":1.538,"kv_borc_orani":0.160,"ortaklar_cari_orani":0.06,"brut_kar_marji":0.366,"favok_marji":0.159,"faaliyet_gider_orani":0.20,"net_kar_marji":0.053,"roe":0.051,"roa":0.033,"stok_devir":5.6,"alacak_tahsil_suresi":51,"nakit_donusum_suresi":42,"faiz_karsilama":3.79,"net_borc_favok":0.66,"finansman_gider_orani":0.042},
    "L": {"cari_oran":2.063,"asit_test":1.287,"nakit_oran":0.379,"borc_ozkaynak":0.626,"finansal_kaldırac":1.626,"kv_borc_orani":0.392,"ortaklar_cari_orani":0.05,"brut_kar_marji":0.619,"favok_marji":0.128,"faaliyet_gider_orani":0.16,"net_kar_marji":0.027,"roe":0.018,"roa":0.011,"stok_devir":11.9,"alacak_tahsil_suresi":42,"nakit_donusum_suresi":42,"faiz_karsilama":2.78,"net_borc_favok":0.90,"finansman_gider_orani":0.046},
    "M": {"cari_oran":1.691,"asit_test":1.436,"nakit_oran":0.317,"borc_ozkaynak":0.309,"finansal_kaldırac":1.309,"kv_borc_orani":0.431,"ortaklar_cari_orani":0.06,"brut_kar_marji":0.706,"favok_marji":0.079,"faaliyet_gider_orani":0.22,"net_kar_marji":0.033,"roe":0.030,"roa":0.023,"stok_devir":4.1,"alacak_tahsil_suresi":73,"nakit_donusum_suresi":21,"faiz_karsilama":4.65,"net_borc_favok":0.54,"finansman_gider_orani":0.017},
    "N": {"cari_oran":1.378,"asit_test":0.956,"nakit_oran":0.241,"borc_ozkaynak":1.660,"finansal_kaldırac":2.660,"kv_borc_orani":0.298,"ortaklar_cari_orani":0.06,"brut_kar_marji":0.173,"favok_marji":0.089,"faaliyet_gider_orani":0.22,"net_kar_marji":0.022,"roe":0.074,"roa":0.028,"stok_devir":8.7,"alacak_tahsil_suresi":24,"nakit_donusum_suresi":72,"faiz_karsilama":3.30,"net_borc_favok":0.76,"finansman_gider_orani":0.027},
    "P": {"cari_oran":1.004,"asit_test":0.788,"nakit_oran":0.394,"borc_ozkaynak":1.778,"finansal_kaldırac":2.778,"kv_borc_orani":0.098,"ortaklar_cari_orani":0.05,"brut_kar_marji":0.243,"favok_marji":0.070,"faaliyet_gider_orani":0.20,"net_kar_marji":0.001,"roe":0.003,"roa":0.001,"stok_devir":27.6,"alacak_tahsil_suresi":17,"nakit_donusum_suresi":51,"faiz_karsilama":3.68,"net_borc_favok":0.68,"finansman_gider_orani":0.019},
    "Q": {"cari_oran":2.028,"asit_test":1.357,"nakit_oran":0.388,"borc_ozkaynak":0.610,"finansal_kaldırac":1.610,"kv_borc_orani":0.261,"ortaklar_cari_orani":0.06,"brut_kar_marji":0.175,"favok_marji":0.141,"faaliyet_gider_orani":0.20,"net_kar_marji":0.056,"roe":0.095,"roa":0.059,"stok_devir":8.8,"alacak_tahsil_suresi":35,"nakit_donusum_suresi":81,"faiz_karsilama":3.36,"net_borc_favok":0.74,"finansman_gider_orani":0.042},
    "R": {"cari_oran":1.420,"asit_test":0.936,"nakit_oran":0.313,"borc_ozkaynak":0.724,"finansal_kaldırac":1.724,"kv_borc_orani":0.156,"ortaklar_cari_orani":0.05,"brut_kar_marji":0.381,"favok_marji":0.103,"faaliyet_gider_orani":0.20,"net_kar_marji":0.042,"roe":0.120,"roa":0.070,"stok_devir":23.2,"alacak_tahsil_suresi":34,"nakit_donusum_suresi":66,"faiz_karsilama":3.22,"net_borc_favok":0.78,"finansman_gider_orani":0.032},
    "S": {"cari_oran":1.571,"asit_test":0.895,"nakit_oran":0.224,"borc_ozkaynak":1.427,"finansal_kaldırac":2.427,"kv_borc_orani":0.178,"ortaklar_cari_orani":0.05,"brut_kar_marji":0.268,"favok_marji":0.093,"faaliyet_gider_orani":0.20,"net_kar_marji":0.025,"roe":0.075,"roa":0.031,"stok_devir":14.4,"alacak_tahsil_suresi":24,"nakit_donusum_suresi":75,"faiz_karsilama":3.72,"net_borc_favok":0.67,"finansman_gider_orani":0.025},
}

# 2 haneli NACE bölümü → bölüm harfi eşlemesi
NACE_2_BOLUM: dict[str, str] = {
    "01": "A", "02": "A", "03": "A",
    "05": "B", "06": "B", "07": "B", "08": "B", "09": "B",
    "10": "C", "11": "C", "12": "C", "13": "C", "14": "C",
    "15": "C", "16": "C", "17": "C", "18": "C", "19": "C",
    "20": "C", "21": "C", "22": "C", "23": "C", "24": "C",
    "25": "C", "26": "C", "27": "C", "28": "C", "29": "C",
    "30": "C", "31": "C", "32": "C", "33": "C",
    "35": "D",
    "36": "E", "37": "E", "38": "E", "39": "E",
    "41": "F", "42": "F", "43": "F",
    "45": "G", "46": "G", "47": "G",
    "49": "H", "50": "H", "51": "H", "52": "H", "53": "H",
    "55": "I", "56": "I",
    "58": "J", "59": "J", "60": "J", "61": "J", "62": "J", "63": "J",
    "64": "K", "65": "K", "66": "K",
    "68": "L",
    "69": "M", "70": "M", "71": "M", "72": "M", "73": "M", "74": "M", "75": "M",
    "77": "N", "78": "N", "79": "N", "80": "N", "81": "N", "82": "N",
    "85": "P",
    "86": "Q", "87": "Q", "88": "Q",
    "94": "S", "95": "S", "96": "S",
}


def nace_to_bolum(nace_kodu: str) -> str:
    """
    6 (veya daha kısa) haneli NACE kodundan bölüm harfini döndürür.
    Örn: "63.11.08" → "J", "28.13" → "C", "C" → "C"
    Bilinmeyen kodlar için varsayılan "G" (Ticaret) döner.
    """
    import re
    clean = re.sub(r"[^0-9]", "", str(nace_kodu))[:2]
    return NACE_2_BOLUM.get(clean, "G")


# ─────────────────────────────────────────────
# 2. ÇIKTI MODELİ
# ─────────────────────────────────────────────

@dataclass
class RasyoAnaliz:
    rasyo_id: str
    ad: str
    deger: float
    deger_fmt: str
    sektor_ort: float
    sektor_ort_fmt: str
    karsilastirma: str        # "iyi" | "orta" | "kotu"
    karsilastirma_metin: str  # "Sektör ortalamasının üzerinde"
    ne_anlama_gelir: str      # reporter._zenginlestir_analizler() tarafından doldurulur
    nasil_iyilestirilir: list[str]  # reporter._zenginlestir_analizler() tarafından doldurulur


# ─────────────────────────────────────────────
# 3. KARŞILAŞTIRMA MANTIĞI
# ─────────────────────────────────────────────

def _karsilastir(deger: float, ort: float, yon: str) -> tuple[str, str]:
    """
    Değeri sektör ortalamasıyla karşılaştırır.
    yon: "yuksek_iyi" | "dusuk_iyi"
    Döner: (karsilastirma, metin)
    """
    if yon == "yuksek_iyi":
        oran = deger / ort if ort else 1
        if oran >= 1.10:
            return "iyi",  f"Sektör ortalamasının {(oran-1)*100:.0f}% üzerinde"
        if oran >= 0.90:
            return "orta", f"Sektör ortalamasına yakın"
        return "kotu",     f"Sektör ortalamasının {(1-oran)*100:.0f}% altında"
    else:  # dusuk_iyi
        if not deger or not ort:
            return "orta", "Sektör ortalamasına yakın"
        oran = ort / deger
        if oran >= 1.10:
            return "iyi",  f"Sektör ortalamasından {(1-deger/ort)*100:.0f}% daha iyi"
        if oran >= 0.90:
            return "orta", "Sektör ortalamasına yakın"
        return "kotu",     f"Sektör ortalamasının {(deger/ort-1)*100:.0f}% gerisinde"


def _fmt(deger: float, rasyo_id: str) -> str:
    yuzde = {"brut_kar_marji","favok_marji","faaliyet_gider_orani","net_kar_marji",
             "roe","roa","ortaklar_cari_orani","kv_borc_orani","finansman_gider_orani"}
    gun   = {"alacak_tahsil_suresi","nakit_donusum_suresi"}
    if rasyo_id in yuzde:  return f"%{deger*100:.1f}"
    if rasyo_id in gun:    return f"{deger:.0f} gün"
    return f"{deger:.2f}x"


# ─────────────────────────────────────────────
# 4. RASYO YÖN TANIMI
# ─────────────────────────────────────────────

# Rasyoların yönü (sektör karşılaştırması için)
_YON = {
    "cari_oran": "yuksek_iyi", "asit_test": "yuksek_iyi", "nakit_oran": "yuksek_iyi",
    "borc_ozkaynak": "dusuk_iyi", "finansal_kaldırac": "dusuk_iyi",
    "kv_borc_orani": "dusuk_iyi", "ortaklar_cari_orani": "dusuk_iyi",
    "brut_kar_marji": "yuksek_iyi", "favok_marji": "yuksek_iyi",
    "faaliyet_gider_orani": "dusuk_iyi", "net_kar_marji": "yuksek_iyi",
    "roe": "yuksek_iyi", "roa": "yuksek_iyi",
    "stok_devir": "yuksek_iyi", "alacak_tahsil_suresi": "dusuk_iyi",
    "nakit_donusum_suresi": "dusuk_iyi", "faiz_karsilama": "yuksek_iyi",
    "net_borc_favok": "dusuk_iyi", "finansman_gider_orani": "dusuk_iyi",
}


# ─────────────────────────────────────────────
# 5. ANA FONKSİYONLAR
# ─────────────────────────────────────────────

def analiz_et(
    rasyo_id: str,
    deger: float,
    sektor: str = "ticaret",
    ad: str = "",
) -> RasyoAnaliz:
    """
    Tek bir rasyo için yapısal analiz üretir.
    ne_anlama_gelir ve nasil_iyilestirilir boş döner —
    reporter._zenginlestir_analizler() tarafından Sonnet ile doldurulur.
    """
    if sektor in ("ticaret", "uretim", "hizmet"):
        ort = SEKTOR_ORT.get(rasyo_id, {}).get(sektor, 0)
    else:
        bolum = nace_to_bolum(sektor)
        ort = NACE_BOLUM_ORT.get(bolum, NACE_BOLUM_ORT["G"]).get(rasyo_id, 0)
    yon = _YON.get(rasyo_id, "yuksek_iyi")
    karsilastirma, karsilastirma_metin = _karsilastir(deger, ort, yon)

    return RasyoAnaliz(
        rasyo_id=rasyo_id,
        ad=ad or rasyo_id,
        deger=deger,
        deger_fmt=_fmt(deger, rasyo_id),
        sektor_ort=ort,
        sektor_ort_fmt=_fmt(ort, rasyo_id),
        karsilastirma=karsilastirma,
        karsilastirma_metin=karsilastirma_metin,
        ne_anlama_gelir="",
        nasil_iyilestirilir=[],
    )


def tum_analizler(degerler: dict, sektor: str = "ticaret") -> list[RasyoAnaliz]:
    """
    Tüm rasyolar için analiz üretir.
    degerler: scorer._hesapla_degerler() çıktısı
    """
    RASYO_ADLARI = {
        "cari_oran": "Cari oran",
        "asit_test": "Asit-test oranı",
        "nakit_oran": "Nakit oranı",
        "borc_ozkaynak": "Borç / Özkaynak",
        "finansal_kaldırac": "Finansal kaldıraç",
        "kv_borc_orani": "KV Borç / Toplam Borç",
        "ortaklar_cari_orani": "Ortaklar cari / Toplam pasif",
        "brut_kar_marji": "Brüt kâr marjı",
        "favok_marji": "FAVÖK marjı",
        "faaliyet_gider_orani": "Faaliyet gideri oranı",
        "net_kar_marji": "Net kâr marjı",
        "roe": "ROE — Özkaynak kârlılığı",
        "roa": "ROA — Varlık kârlılığı",
        "stok_devir": "Stok devir hızı",
        "alacak_tahsil_suresi": "Alacak tahsil süresi",
        "nakit_donusum_suresi": "Nakit dönüşüm süresi",
        "faiz_karsilama": "Faiz karşılama oranı",
        "net_borc_favok": "Net Borç / FAVÖK",
        "finansman_gider_orani": "Finansman gideri / Net satış",
    }

    sonuclar = []
    for rid, ad in RASYO_ADLARI.items():
        if rid in degerler:
            sonuclar.append(analiz_et(rid, degerler[rid], sektor, ad))
    return sonuclar
