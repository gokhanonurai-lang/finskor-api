"""
BilankoIQ — Analyzer
Her rasyo için:
  - Ne anlama gelir (değere göre dinamik açıklama)
  - Sektör ortalamasıyla karşılaştırma
  - Nasıl iyileştirilir (somut adımlar)
Tamamen fix kurallar — AI kullanılmaz.
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
    ne_anlama_gelir: str      # Değere göre dinamik açıklama
    nasil_iyilestirilir: list[str]  # Somut adımlar


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
# 4. RASYO ANALİZ KATEGORİSİ
# Her rasyo: dinamik metin fonksiyonu + iyileştirme adımları
# ─────────────────────────────────────────────

def _analiz_cari_oran(d: float) -> str:
    if d >= 2.0:
        return (f"Her 1 TL kısa vadeli borca karşı {d:.2f} TL dönen varlığınız var. "
                "Bu, kısa vadeli yükümlülüklerinizi rahatlıkla karşılayabileceğinizi gösteriyor.")
    if d >= 1.5:
        return (f"Her 1 TL kısa vadeli borca karşı {d:.2f} TL dönen varlığınız var. "
                "Likidite durumunuz iyi, ancak beklenmedik ödemelere karşı tampon alanınız sınırlı.")
    if d >= 1.0:
        return (f"Her 1 TL kısa vadeli borca karşı yalnızca {d:.2f} TL dönen varlığınız var. "
                "Kısa vadeli borçlarınızı karşılayabiliyorsunuz ama marjiniz çok dar. "
                "Herhangi bir tahsilat gecikmesi likidite baskısı yaratır.")
    return (f"Kısa vadeli borçlarınız dönen varlıklarınızı aşıyor ({d:.2f}x). "
            "Bu kritik bir likidite sorunudur. Banka kredi başvurunuz bu nedenle reddedilebilir.")

def _analiz_asit_test(d: float) -> str:
    if d >= 1.3:
        return (f"Stokları hesaba katmadan bile kısa vadeli borçlarınızı karşılayabiliyorsunuz ({d:.2f}x). "
                "Gerçek anlamda güçlü bir likidite profili.")
    if d >= 1.0:
        return (f"Stok dışı dönen varlıklarınız KV borçlarınıza yakın ({d:.2f}x). "
                "Stoklar satılmasa bile büyük sıkıntı yaşanmaz ama tampon ince.")
    if d >= 0.7:
        return (f"Stoklar olmadan kısa vadeli borçları karşılamak güçleşiyor ({d:.2f}x). "
                "Stok satışında gecikme yaşandığında ödeme güçlüğü doğabilir.")
    return (f"Stok dışı likit varlıklarınız KV borçlarınızın çok gerisinde ({d:.2f}x). "
            "Bankalar stoku likit varlık saymaz — bu oran kredi notunuzu ciddi etkiliyor.")

def _analiz_nakit_oran(d: float) -> str:
    if d >= 0.4:
        return (f"Kasa ve banka bakiyeniz KV borçlarınızın {d*100:.0f}%'ini karşılıyor. "
                "Anlık ödeme gücünüz çok kuvvetli.")
    if d >= 0.2:
        return (f"Kasa ve banka bakiyeniz KV borçlarınızın {d*100:.0f}%'ini karşılıyor. "
                "Nakit pozisyonunuz makul. Acil ödemeleri karşılayabilirsiniz.")
    if d >= 0.1:
        return (f"Nakdiniz KV borçlarınızın yalnızca {d*100:.0f}%'i. "
                "Anlık ödeme yükümlülüğünde alacak veya stok harekete geçirmek zorunda kalırsınız.")
    return (f"Kasa ve banka bakiyeniz çok yetersiz — KV borçlarınızın {d*100:.0f}%'i. "
            "Operasyonel nakit yönetimi açısından acil önlem gerekiyor.")

def _analiz_borc_ozkaynak(d: float) -> str:
    if d <= 1.0:
        return (f"Her 1 TL özkaynağa karşı {d:.2f} TL borç taşıyorsunuz. "
                "Şirketiniz büyük ölçüde özkaynaklarıyla finanse ediliyor. Finansal yapı çok sağlam.")
    if d <= 2.0:
        return (f"Her 1 TL özkaynağa karşı {d:.2f} TL borç taşıyorsunuz. "
                "Borç-özkaynak dengesi kabul edilebilir seviyede.")
    if d <= 3.5:
        return (f"Her 1 TL özkaynağa karşı {d:.2f} TL borç taşıyorsunuz. "
                "Borç yükünüz yüksek. Bankalar yeni kredi açarken teminat talep eder.")
    return (f"Her 1 TL özkaynağa karşılık {d:.2f} TL borcunuz var. "
            "Bu oran bankacılıkta yüksek risk sınıfına giriyor. "
            "Yeni kredi temini çok zorlaşır.")

def _analiz_finansal_kaldırac(d: float) -> str:
    if d == 0:
        return "Özkaynak değeri sıfır olduğundan finansal kaldıraç hesaplanamıyor."
    if d <= 2.0:
        return (f"Toplam varlıklarınızın {100/d:.0f}%'i özkaynaklardan geliyor. "
                "Finansal yapınız sağlam ve kırılganlığa karşı dirençli.")
    if d <= 3.0:
        return (f"Varlıklarınızın özkaynak ile karşılanan kısmı {100/d:.0f}%. "
                "Kaldıraç oranı makul. Özkaynak tabanı hâlâ anlamlı.")
    if d <= 4.5:
        return (f"Varlıklarınızın yalnızca {100/d:.0f}%'i özkaynaklardan karşılanıyor. "
                "Varlıklarınızın büyük bölümü borçla finanse ediliyor.")
    return (f"Özkaynak tabanınız toplam varlıklarınıza kıyasla çok ince ({100/d:.0f}%). "
            "Olası bir kriz anında şirket hızla borca batık konuma geçebilir.")

def _analiz_kv_borc_orani(d: float) -> str:
    if d <= 0.40:
        return (f"Borçlarınızın yalnızca {d*100:.0f}%'i kısa vadeli. "
                "Borç vade yapınız dengeli — nakit akışı üzerindeki baskı düşük.")
    if d <= 0.60:
        return (f"Borçlarınızın {d*100:.0f}%'i kısa vadeli. "
                "Vade yapısı yönetilebilir, ancak her yıl önemli bir refinansman ihtiyacı var.")
    if d <= 0.80:
        return (f"Borçlarınızın {d*100:.0f}%'i kısa vadeli. "
                "Bu yüksek bir oran. Sürekli refinansman baskısı ve yüksek faiz riski taşıyor.")
    return (f"Borçlarınızın {d*100:.0f}%'i kısa vadeli — neredeyse tamamı. "
            "Bu yapı hem yüksek refinansman riski hem de sürekli likidite baskısı demektir.")

def _analiz_ortaklar_cari(d: float) -> str:
    if d <= 0.05:
        return (f"Ortaklara olan borç pasifinizin {d*100:.1f}%'i. "
                "Bankalar bu hesabı sorun olarak görmüyor.")
    if d <= 0.10:
        return (f"Ortaklara olan borç pasifinizin {d*100:.1f}%'i. "
                "Makul sınırda. Banka analisti açıklama isteyebilir ama büyük sorun değil.")
    if d <= 0.25:
        return (f"Ortaklara olan borç pasifinizin {d*100:.1f}%'i — dikkat çekici boyutta. "
                "Bankalar 'Bu para neden çekilmedi, gerçek borç mu özkaynak mı?' diye sorgular.")
    return (f"Ortaklara olan borç pasifinizin {d*100:.1f}%'ini oluşturuyor. "
            "Bu bankalar için kırmızı bayraktır. Tutarı gerçek borç olarak değerlendirip "
            "özkaynak hesabınızı bu kadar düşük görürler.")

def _analiz_brut_kar(d: float) -> str:
    if d >= 0.35:
        return (f"Her 100 TL satıştan {d*100:.1f} TL brüt kâr kalıyor. "
                "Temel ticari verimliliğiniz güçlü. Fiyatlandırma ve maliyet yönetiminiz iyi.")
    if d >= 0.20:
        return (f"Her 100 TL satıştan {d*100:.1f} TL brüt kâr kalıyor. "
                "Brüt kâr marjınız makul, ancak faaliyet giderlerinizi iyi yönetmeniz gerekiyor.")
    if d >= 0.10:
        return (f"Her 100 TL satıştan yalnızca {d*100:.1f} TL brüt kâr kalıyor. "
                "Düşük marj, fiyat rekabetinde çok az hareket alanı bırakıyor.")
    return (f"Her 100 TL satıştan {d*100:.1f} TL brüt kâr kalıyor — çok düşük. "
            "Ya satış fiyatları çok düşük ya da maliyetler çok yüksek.")

def _analiz_favok_marji(d: float) -> str:
    if d >= 0.20:
        return (f"Her 100 TL satıştan {d*100:.1f} TL FAVÖK üretiyorsunuz. "
                "Bu, finansman ve amortisman öncesi operasyonel gücünüzü gösteriyor. "
                "Bankalar bunu kredi geri ödeme kapasitesinin en güvenilir göstergesi sayar.")
    if d >= 0.10:
        return (f"Her 100 TL satıştan {d*100:.1f} TL FAVÖK üretiyorsunuz. "
                "Operasyonel verimliliğiniz kabul edilebilir seviyede.")
    if d >= 0.04:
        return (f"Her 100 TL satıştan {d*100:.1f} TL FAVÖK üretiyorsunuz. "
                "FAVÖK marjınız düşük. Faiz giderleri artsa veya satışlar gerilese "
                "kredi geri ödemesi zorlaşır.")
    return (f"Her 100 TL satıştan yalnızca {d*100:.1f} TL FAVÖK üretiyorsunuz. "
            "Esas faaliyetlerinizin nakit üretme kapasitesi çok zayıf. "
            "Bankalar kredi geri ödemesinin nasıl yapılacağını göremez.")

def _analiz_faaliyet_gider(d: float) -> str:
    if d <= 0.08:
        return (f"Satışlarınızın {d*100:.1f}%'i faaliyet giderlerine gidiyor. "
                "Maliyet disiplininiz çok iyi. Her TL satış yüksek oranda kâra dönüşüyor.")
    if d <= 0.15:
        return (f"Satışlarınızın {d*100:.1f}%'i faaliyet giderlerine gidiyor. "
                "Gider yapınız makul. Optimize edilebilecek kalemler olabilir.")
    if d <= 0.25:
        return (f"Satışlarınızın {d*100:.1f}%'i faaliyet giderlerine gidiyor. "
                "Gider oranı yüksek. Bu, büyüme anında karlılığı baskılar.")
    return (f"Satışlarınızın {d*100:.1f}%'i faaliyet giderlerine gidiyor — çok yüksek. "
            "Kira, personel veya genel giderler kontrol altına alınmalı.")

def _analiz_net_kar_marji(d: float) -> str:
    if d >= 0.10:
        return (f"Her 100 TL satıştan {d*100:.1f} TL net kâr kalıyor. "
                "Güçlü kârlılık. Vergi ve finansman yükü kazancı aşırı eritmemiş.")
    if d >= 0.04:
        return (f"Her 100 TL satıştan {d*100:.1f} TL net kâr kalıyor. "
                "Net kâr marjınız makul. Özkaynak birikimi devam ediyor.")
    if d >= 0.01:
        return (f"Her 100 TL satıştan yalnızca {d*100:.1f} TL net kâr kalıyor. "
                "Finansman giderleri veya vergi yükü operasyonel kârı eritiyor.")
    return (f"Net kâr marjınız {d*100:.1f}% — neredeyse sıfır ya da negatif. "
            "Özkaynak erimeye başlıyor. Bu sürdürülebilir değil.")

def _analiz_roe(d: float) -> str:
    if d >= 0.20:
        return (f"Ortakların koyduğu her 100 TL sermaye yılda {d*100:.1f} TL getiri üretiyor. "
                "Bu, bankaya 'şirket iyi yönetiliyor' mesajı verir.")
    if d >= 0.12:
        return (f"Özkaynak getirisi {d*100:.1f}%. "
                "Makul getiri — enflasyonun üzerinde reel kazanç sağlanıyor.")
    if d >= 0.05:
        return (f"Özkaynak getirisi {d*100:.1f}% — düşük. "
                "Ortakların parasını başka yerde değerlendirmesi daha kârlı olabilir.")
    return (f"Özkaynak getirisi yalnızca {d*100:.1f}%. "
            "Özkaynak büyümüyor, aksine eriyor olabilir.")

def _analiz_roa(d: float) -> str:
    if d >= 0.10:
        return (f"Her 100 TL varlık {d*100:.1f} TL net kâr üretiyor. "
                "Varlıklarınız verimli çalışıyor.")
    if d >= 0.05:
        return (f"Her 100 TL varlık {d*100:.1f} TL net kâr üretiyor. "
                "Varlık verimliliği makul seviyede.")
    if d >= 0.02:
        return (f"Her 100 TL varlıktan yalnızca {d*100:.1f} TL kâr elde ediliyor. "
                "Varlıklar yeterince verimli kullanılamıyor.")
    return (f"Varlık getiriniz {d*100:.1f}% — çok düşük. "
            "Bilanço büyüklüğüne oranla çok az kâr üretiliyor.")

def _analiz_stok_devir(d: float) -> str:
    if not d:
        return "Stok devir hızı hesaplanamadı — stok maliyeti veya stok bakiyesi sıfır."
    gun = 365 / d
    if d >= 12.0:
        return (f"Stoklarınız yılda {d:.1f} kez dönüyor — ortalama {gun:.0f} günde bir. "
                "Stok yönetiminiz çok verimli. Bağlı sermaye minimum.")
    if d >= 8.0:
        return (f"Stoklarınız yılda {d:.1f} kez dönüyor — ortalama {gun:.0f} günde bir. "
                "Stok yönetimi makul düzeyde.")
    if d >= 4.0:
        return (f"Stoklarınız yılda {d:.1f} kez dönüyor — ortalama {gun:.0f} günde bir. "
                "Stoklar yavaş dönüyor. Bu hem nakit döngüsünü uzatır hem de değer düşüklüğü riski taşır.")
    return (f"Stoklarınız yılda yalnızca {d:.1f} kez dönüyor — ortalama {gun:.0f} günde bir. "
            "Stok birikimi tehlikeli boyuta ulaşmış. "
            "Bankalar bu stoku likit varlık olarak kabul etmez.")

def _analiz_alacak_tahsil(d: float) -> str:
    if d <= 30:
        return (f"Satışlarınızın bedeli ortalama {d:.0f} günde tahsil ediliyor. "
                "Tahsilat çok hızlı. Alacak finansmanı ihtiyacınız minimal.")
    if d <= 50:
        return (f"Satışlarınızın bedeli ortalama {d:.0f} günde tahsil ediliyor. "
                "Tahsilat süresi makul. Yönetilebilir düzeyde.")
    if d <= 75:
        return (f"Satışlarınızın bedeli ortalama {d:.0f} günde tahsil ediliyor. "
                "Alacaklar uzun süre bekliyor. Nakit akışı bozuluyor ve tahsil edilememe riski artıyor.")
    return (f"Satışlarınızın bedeli ortalama {d:.0f} günde tahsil ediliyor — çok yüksek. "
            "Bu süre zarfında hem finansman maliyetiniz artıyor hem de alacak değer kaybı riski oluşuyor.")

def _analiz_nds(d: float) -> str:
    if d <= 20:
        return (f"Satın aldığınız mal/hammaddenin parası ortalama {d:.0f} günde geri dönüyor. "
                "Nakit döngünüz çok hızlı. İşletme sermayesi ihtiyacınız minimum.")
    if d <= 60:
        return (f"Nakit döngünüz {d:.0f} gün. "
                "Para makul sürede sistemde bağlı kalıyor. İşletme sermayesi finansmanı yönetilebilir.")
    if d <= 90:
        return (f"Nakit döngünüz {d:.0f} gün. "
                "Para uzun süre sistemde bağlı. Her büyüme adımı orantısız işletme sermayesi gerektiriyor.")
    return (f"Nakit döngünüz {d:.0f} gün — çok uzun. "
            "Bu, bankadan sürekli kısa vadeli kredi istemek demektir. "
            "Hem maliyetlidir hem de kırılganlık yaratır.")

def _analiz_faiz_karsilama(d: float) -> str:
    if d >= 5.0:
        return (f"FAVÖK'ünüz faiz giderlerinizin {d:.1f} katı. "
                "Faiz yükümlülüklerinizi rahatlıkla karşılayabiliyorsunuz. "
                "Bu oran, finansal değerlendirme süreçlerinde olumlu bir gösterge olarak değerlendirilebilir.")
    if d >= 3.0:
        return (f"FAVÖK'ünüz faiz giderlerinizin {d:.1f} katı. "
                "Faiz yükümlülüklerinizi karşılayabiliyorsunuz ve üzerinde tampon var.")
    if d >= 1.5:
        return (f"FAVÖK'ünüz faiz giderlerinizin yalnızca {d:.1f} katı. "
                "Faiz giderleriniz FAVÖK'ünüzü ciddi ölçüde yiyor. "
                "Satışlarda küçük bir düşüş faiz ödemesini tehlikeye atar.")
    return (f"FAVÖK'ünüz faiz giderlerinizin {d:.1f} katı — tehlikeli bölge. "
            "Faiz giderlerinizi karşılamakta zorlanıyorsunuz. "
            "Bu bankacılıkta en ağır uyarı işaretlerinden biridir.")

def _analiz_net_borc_favok(d: float) -> str:
    if d <= 1.5:
        return (f"Mevcut nakit akışınızla finansal borçlarınızı {d:.1f} yılda kapatabilirsiniz. "
                "Bu bankacılıkta ideal profildir.")
    if d <= 3.0:
        return (f"Mevcut nakit akışınızla finansal borçlarınızı {d:.1f} yılda kapatabilirsiniz. "
                "Borçlanma düzeyi makul. Kabul edilebilir sınırlar içinde.")
    if d <= 5.0:
        return (f"Borçlarınızın FAVÖK ile kapanması {d:.1f} yılı buluyor. "
                "Bankalar bu profil için ilave teminat talep eder.")
    return (f"Borçlarınızın kapanması {d:.1f} yılı aşıyor — tehlike bölgesi. "
            "Bankacılıkta genellikle 4–5x üst sınır uygulanır. "
            "Bu seviyede yeni kredi açmak çok güçtür.")

def _analiz_finansman_gider(d: float) -> str:
    if d <= 0.02:
        return (f"Her 100 TL satıştan yalnızca {d*100:.1f} TL faize gidiyor. "
                "Finansman maliyeti rekabet gücünüzü zayıflatmıyor.")
    if d <= 0.05:
        return (f"Her 100 TL satıştan {d*100:.1f} TL faize gidiyor. "
                "Finansman maliyeti yönetilebilir düzeyde.")
    if d <= 0.09:
        return (f"Her 100 TL satıştan {d*100:.1f} TL faize gidiyor. "
                "Faiz yükü ciroya oranla yüksek. Fiyat rekabetini zorlaştırıyor.")
    return (f"Her 100 TL satıştan {d*100:.1f} TL faize gidiyor — çok yüksek. "
            "Bu seviyede faiz yükü şirketi kârsızlaştırıyor olabilir.")


# ─────────────────────────────────────────────
# 5. İYİLEŞTİRME ADIM LİSTESİ
# ─────────────────────────────────────────────

IYILESTIRME_ADIMLARI = {
    "cari_oran": [
        "Vadesi geçmiş alacakları tahsil edin — nakit girişi cari oranı anında artırır",
        "Yavaş dönen stokları eritip nakde çevirin",
        "Kısa vadeli banka kredilerini uzun vadeye çevirin (en etkili yapısal adım)",
        "Ortaklar cari hesabını kapatın — KV borç azalır",
        "Tedarikçilerle ödeme vadelerini uzatmak için müzakere edin",
    ],
    "asit_test": [
        "Alacak tahsilatını hızlandırın — en doğrudan etki",
        "Stok seviyesini düşürüp nakit tutun",
        "KV borçları uzun vadeye taşıyın",
    ],
    "nakit_oran": [
        "Vadesi gelen alacakları öncelikli tahsil edin",
        "Gereksiz stok alımını durdurun, nakit biriktirin",
        "Kısa vadeli mevduat veya repo hesabı açarak atıl nakdi değerlendirin",
    ],
    "borc_ozkaynak": [
        "Ortaklar cari hesabını (331) sermayeye ekleyin — en hızlı ve maliyetsiz yöntem",
        "Dönem kârını dağıtmayın, birikimli özkaynak büyüsün",
        "Nakdi sermaye artırımı yapın",
        "Varlık satışı yapıp borç kapatın",
        "Uzun vadeli borçlanmayı azaltmak için yatırım planını gözden geçirin",
    ],
    "finansal_kaldırac": [
        "Borç/Özkaynak iyileştirme adımlarının tamamı burada da geçerli",
        "Kullanılmayan duran varlıkları satıp borç kapatın",
        "Yeni sabit yatırımları erteleyerek borç büyümesini yavaşlatın",
    ],
    "kv_borc_orani": [
        "Kısa vadeli kredileri uzun vadeli krediye çevirmek için bankanızla müzakere edin",
        "Rotatif (döner) krediyi uzun vadeli yatırım kredisine dönüştürün",
        "Tedarikçi borçlarının vadesini uzatmak için ticari anlaşmalar yapın",
    ],
    "ortaklar_cari_orani": [
        "Ortaklar cari hesabını sermayeye ilave edin — hem bu oranı hem Borç/Özkaynak'ı aynı anda iyileştirir",
        "Tutarı gerçekten borçsanız uzun vadeli ortaklar borç senedine bağlayın",
        "Kademeli olarak hesabı kapatın, ortağa nakit iade edin",
    ],
    "brut_kar_marji": [
        "Satış fiyatlarını gözden geçirin — maliyet artışlarını fiyata yansıtın",
        "Tedarikçilerle maliyet müzakeresi yapın",
        "Düşük marjlı ürün/hizmetleri portföyden çıkartın",
        "Toplu alımlarla hammadde maliyetini düşürün",
    ],
    "favok_marji": [
        "Satış fiyatlarını güncelleyin — enflasyon ortamında fiyat güncellemesi FAVÖK'ü hızla artırır",
        "Sabit giderleri (kira, personel) optimize edin",
        "Düşük marjlı ürün/hizmetleri portföyden çıkartın",
        "Tedarikçilerle maliyet müzakeresi yapın",
    ],
    "faaliyet_gider_orani": [
        "Kira maliyetlerini gözden geçirin — taşınma veya yeniden müzakere",
        "Personel verimliliğini analiz edin, IT ve otomasyon ile destekleyin",
        "Genel gider kalemlerini tek tek inceleyin (abonelikler, servisler, seyahat)",
        "Outsourcing ile bazı fonksiyonları değişken maliyete çevirin",
    ],
    "net_kar_marji": [
        "Finansman giderlerini düşürün — kredi faizlerini yeniden müzakere edin",
        "Düşük maliyetli kamu destekli kredilere yönelin (KGF, KOSGEB, Eximbank)",
        "Vergi planlaması yapın — yatırım indirimi ve Ar-Ge teşviklerinden yararlanın",
        "FAVÖK marjı iyileştirme adımları net kâr marjını da yukarı çeker",
    ],
    "roe": [
        "Net kâr marjını artırın — ROE doğrudan etkilenir",
        "Verimsiz varlıkları satarak özkaynak tabanını şişirmeden kâr artırın",
        "Gereksiz sermaye tutmayın — özkaynak fazlaysa getiri oranı düşer",
    ],
    "roa": [
        "Kullanılmayan veya atıl varlıkları satın",
        "Kârlılığı artırın (net kâr marjı adımları)",
        "Varlık devir hızını artırın — aynı varlıkla daha fazla satış yapın",
    ],
    "stok_devir": [
        "Eski ve yavaş dönen stokları indirimli satın",
        "Stok sipariş miktarlarını düşürün, 'tam zamanında' tedarik modeline geçin",
        "Hangi ürünlerin raflarda çürüdüğünü analiz edin, portföyü daraltın",
        "Stok yönetim yazılımı kullanarak min/max seviyelerini optimize edin",
    ],
    "alacak_tahsil_suresi": [
        "Gecikmiş alacaklar için aktif takip ve hatırlatma kampanyası başlatın",
        "Peşin veya kısa vadeli ödemelere %2–3 iskonto teklif edin",
        "Yeni satışlarda vade politikasını sıkılaştırın",
        "Faktoring kullanın — alacakları nakde çevirin",
        "Riskli müşterilere teminat mektubu veya çek talep edin",
    ],
    "nakit_donusum_suresi": [
        "Alacak tahsilini hızlandırın (yukarıdaki adımlar)",
        "Stok devir hızını artırın",
        "Tedarikçilerle vadeyi uzatın — aynı malı 30 yerine 60 günde ödemek döngüyü kısaltır",
        "Bu üç adımın kombinasyonu en hızlı sonucu verir",
    ],
    "faiz_karsilama": [
        "Faiz oranlarını yeniden müzakere edin — özellikle ticari kredi faizlerinde",
        "Yüksek faizli kredileri KGF destekli veya KOSGEB kredisiyle refinanse edin",
        "FAVÖK'ü artırın — faiz karşılama oranı da iyileşir",
        "Zorunlu olmayan yeni borçlanmayı durdurun",
    ],
    "net_borc_favok": [
        "FAVÖK'ü artırmak bu oranı hızla iyileştirir",
        "Borç ana parasını düzenli ödeyin, refinansmandan kaçının",
        "Likit olmayan varlıkları satıp borç kapatın — net borç düşer",
    ],
    "finansman_gider_orani": [
        "Düşük maliyetli kamu destekli kredilere yönelin (KOSGEB, Eximbank, Kalkınma Bankası)",
        "Yüksek faizli kredileri erken kapatın",
        "Satış hacmini artırarak paydayı büyütün — ciro artarsa oran düşer",
        "Faiz dönemi müzakeresi yapın — sabit faizden değişkene veya tam tersi geçiş fırsatı arayın",
    ],
}


# ─────────────────────────────────────────────
# 6. ANA FONKSİYON
# ─────────────────────────────────────────────

# Rasyo → açıklama fonksiyonu eşlemesi
_ANALIZ_FN = {
    "cari_oran":             _analiz_cari_oran,
    "asit_test":             _analiz_asit_test,
    "nakit_oran":            _analiz_nakit_oran,
    "borc_ozkaynak":         _analiz_borc_ozkaynak,
    "finansal_kaldırac":     _analiz_finansal_kaldırac,
    "kv_borc_orani":         _analiz_kv_borc_orani,
    "ortaklar_cari_orani":   _analiz_ortaklar_cari,
    "brut_kar_marji":        _analiz_brut_kar,
    "favok_marji":           _analiz_favok_marji,
    "faaliyet_gider_orani":  _analiz_faaliyet_gider,
    "net_kar_marji":         _analiz_net_kar_marji,
    "roe":                   _analiz_roe,
    "roa":                   _analiz_roa,
    "stok_devir":            _analiz_stok_devir,
    "alacak_tahsil_suresi":  _analiz_alacak_tahsil,
    "nakit_donusum_suresi":  _analiz_nds,
    "faiz_karsilama":        _analiz_faiz_karsilama,
    "net_borc_favok":        _analiz_net_borc_favok,
    "finansman_gider_orani": _analiz_finansman_gider,
}

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


def analiz_et(
    rasyo_id: str,
    deger: float,
    sektor: str = "ticaret",
    ad: str = "",
) -> RasyoAnaliz:
    """
    Tek bir rasyo için tam analiz üretir.

    Args:
        rasyo_id: Rasyo kimliği (örn. "cari_oran")
        deger: Hesaplanan rasyo değeri
        sektor: "ticaret" | "uretim" | "hizmet"
        ad: Ekranda gösterilecek ad (boş bırakılırsa rasyo_id kullanılır)

    Returns:
        RasyoAnaliz objesi
    """
    # Sektor: eski sistem ("ticaret"/"uretim"/"hizmet") veya NACE kodu ("63.11.08")
    if sektor in ("ticaret", "uretim", "hizmet"):
        ort = SEKTOR_ORT.get(rasyo_id, {}).get(sektor, 0)
    else:
        bolum = nace_to_bolum(sektor)
        ort = NACE_BOLUM_ORT.get(bolum, NACE_BOLUM_ORT["G"]).get(rasyo_id, 0)
    yon = _YON.get(rasyo_id, "yuksek_iyi")
    karsilastirma, karsilastirma_metin = _karsilastir(deger, ort, yon)

    analiz_fn = _ANALIZ_FN.get(rasyo_id)
    ne_anlama = analiz_fn(deger) if analiz_fn else f"Değer: {deger:.2f}"

    adimlar = IYILESTIRME_ADIMLARI.get(rasyo_id, [])

    return RasyoAnaliz(
        rasyo_id=rasyo_id,
        ad=ad or rasyo_id,
        deger=deger,
        deger_fmt=_fmt(deger, rasyo_id),
        sektor_ort=ort,
        sektor_ort_fmt=_fmt(ort, rasyo_id),
        karsilastirma=karsilastirma,
        karsilastirma_metin=karsilastirma_metin,
        ne_anlama_gelir=ne_anlama,
        nasil_iyilestirilir=adimlar,
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
