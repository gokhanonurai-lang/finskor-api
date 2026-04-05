"""
BilankoIQ — Reporter
Tam rapor içeriğini üretir:
  1. Yönetici özeti
  2. Güçlü yönler
  3. Zayıf yönler ve aksiyon planı
  4. Senaryo motoru (ne yaparsan skor ne olur)
  5. Banka başvuru hazırlığı
  6. Zaman çizelgesi
  7. Yasal disclaimer
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scorer import SkorSonuc
    from analyzer import RasyoAnaliz


# ─────────────────────────────────────────────
# 1. VERİ MODELLERİ
# ─────────────────────────────────────────────

@dataclass
class SenaryoSonuc:
    aciklama: str
    degisiklik: dict           # {"alan": delta_TL}
    yeni_skor: int
    skor_delta: int
    yeni_harf: str
    yeni_limit_aciklama: str
    etkilenen_rasyolar: list[str]


@dataclass
class BankaHazirlik:
    muhtemel_sorular: list[str]
    hazirlanacak_belgeler: list[str]
    dikkat_edilecekler: list[str]


@dataclass
class KrediTuruOneri:
    birincil_tur: str
    birincil_aciklama: str
    birincil_miktar: str
    alternatif_turler: list[dict]   # [{"tur": ..., "aciklama": ...}]
    neden: str


@dataclass
class NakitAkisAnaliz:
    aylik_favok: float
    aylik_favok_fmt: str
    mevcut_borc_servisi_aylik: float
    mevcut_borc_servisi_fmt: str
    favok_kullanim_orani: float       # mevcut borç / FAVÖK
    yeni_kredi_taksiti_aylik: float   # limit tahminine göre
    yeni_kredi_taksiti_fmt: str
    toplam_borc_servisi_aylik: float
    toplam_borc_servisi_fmt: str
    toplam_favok_kullanim_orani: float
    kapasite_degerlendirmesi: str     # "rahat" | "makul" | "riskli" | "kritik"
    yorum: str


@dataclass
class TamRapor:
    firma_adi: str
    sektor: str
    # Bölümler
    yonetici_ozeti: str
    guclu_yonler: list[str]
    zayif_yonler: list[str]
    rasyo_analizleri: list
    kredi_turu_oneri: KrediTuruOneri
    nakit_akis_analiz: NakitAkisAnaliz
    banka_sorulari: list          # BankaSorusu listesi
    aksiyon_plani: list[dict]
    senaryolar: list[SenaryoSonuc]
    banka_hazirlik: BankaHazirlik
    zaman_cizelgesi: list[dict]
    disclaimer: str


# ─────────────────────────────────────────────
# 2. YÖNETİCİ ÖZETİ
# ─────────────────────────────────────────────

def _yonetici_ozeti(skor_sonuc: "SkorSonuc", bs) -> str:
    skor = skor_sonuc.skor
    harf = skor_sonuc.harf
    favok = bs.favok
    mevcut_borc = bs.finansal_borclar

    # Genel durum cümlesi
    if skor >= 85:
        genel = (
            f"Şirketinizin finansal yapısı bankacılık standartlarına göre mükemmel "
            f"seviyededir. {harf} notu ile kredi başvurunuzda teminat olarak yalnızca "
            f"kişisel kefalet yeterli olacaktır."
        )
    elif skor >= 75:
        genel = (
            f"Şirketinizin finansal yapısı güçlü görünmektedir. {harf} notu ile "
            f"bankalardan uygun koşullarda kredi kullanabilirsiniz. "
            f"Küçük iyileştirmelerle AAA bandına ulaşmanız mümkündür."
        )
    elif skor >= 65:
        genel = (
            f"Şirketinizin finansal yapısı iyi düzeydedir ancak bazı alanlarda "
            f"iyileştirme yapılması gereklidir. {harf} notu ile bankalar kredi açacaktır, "
            f"ancak teminat talep edebilirler."
        )
    elif skor >= 55:
        genel = (
            f"Şirketinizin finansal yapısı orta düzeydedir. {harf} notu ile kredi "
            f"alabilirsiniz ancak teminat zorunluluğu olacak ve faiz oranınız "
            f"daha yüksek bankalar tarafından belirlenebilir."
        )
    elif skor >= 45:
        genel = (
            f"Şirketinizin finansal yapısında önemli zayıflıklar tespit edilmiştir. "
            f"{harf} notu ile kredi imkânınız sınırlı olup güçlü teminat "
            f"göstermeniz gerekmektedir."
        )
    else:
        genel = (
            f"Şirketinizin finansal yapısı bankacılık değerlendirmesinde kritik "
            f"seviyededir. Öncelikle bilanço iyileştirme çalışması yapılmadan "
            f"kredi başvurusu yapılması önerilmemektedir."
        )

    # Kırmızı bayrak varsa ek uyarı
    bayrak_mesaji = ""
    kritik_bayraklar = [b for b in skor_sonuc.kirmizi_bayraklar if b.ciddiyet == "kritik"]
    if kritik_bayraklar:
        bayrak_mesaji = (
            f"\n\nDİKKAT: Analizde {len(kritik_bayraklar)} kritik uyarı tespit edilmiştir. "
            f"Bu uyarılar banka değerlendirmesinde doğrudan olumsuz etki yaratır ve "
            f"kredi başvurusunun reddedilmesine neden olabilir."
        )

    # Limit bilgisi
    carpan_map = {"AAA": 3.0, "AA": 2.5, "A": 2.0}
    carpan = carpan_map.get(harf)
    limit_mesaji = ""
    if carpan and favok > 0:
        kullanilabilir = max(0, favok * carpan - mevcut_borc)
        limit_mesaji = (
            f"\n\nMevcut finansal yapınızla tahmini kullanılabilir kredi limitiniz "
            f"{kullanilabilir:,.0f} TL'dir. "
            f"(Hesaplama: Yıllık işletme kârı × {carpan} − mevcut banka borçları)"
        )

    return genel + bayrak_mesaji + limit_mesaji


# ─────────────────────────────────────────────
# 3. GÜÇLÜ YÖNLER
# ─────────────────────────────────────────────

def _guclu_yonler(skor_sonuc: "SkorSonuc", analizler: list["RasyoAnaliz"]) -> list[str]:
    guclu = []

    for a in analizler:
        if a.karsilastirma == "iyi":
            # Açıklamayı ilk cümleyle sınırla — sayı sonrası noktada kesme
            aciklama = a.ne_anlama_gelir
            # Cümle sonu tespiti: nokta + boşluk + büyük harf veya cümle sonu
            import re
            cumleler = re.split(r'(?<=[a-züöçşığıA-ZÜÖÇŞİĞI])\. ', aciklama)
            ozet = cumleler[0].rstrip('.') + "." if cumleler else aciklama
            guclu.append(
                f"{a.ad}: {a.deger_fmt} — sektör ortalamasının "
                f"({a.sektor_ort_fmt}) üzerinde. {ozet}"
            )

    # Skor kategorisine göre ek güçlü mesajlar
    if skor_sonuc.borc_puan / 16 >= 0.80:
        guclu.append(
            "Borç ödeme kapasiteniz güçlü. Bankalar kredi geri ödemesini "
            "güvence altında görüyor."
        )
    if skor_sonuc.karlilik_puan / 26 >= 0.75:
        guclu.append(
            "Kârlılık yapınız sağlam. Şirketin nakit üretme kapasitesi iyi düzeyde."
        )
    if skor_sonuc.faaliyet_puan / 18 >= 0.75:
        guclu.append(
            "Faaliyet etkinliğiniz yüksek. Varlıklar ve işletme sermayesi "
            "verimli kullanılıyor."
        )

    return guclu[:6] if guclu else ["Mevcut finansal verilere göre öne çıkan güçlü alan tespit edilemedi."]


# ─────────────────────────────────────────────
# 4. ZAYIF YÖNLER
# ─────────────────────────────────────────────

def _zayif_yonler(skor_sonuc: "SkorSonuc", analizler: list["RasyoAnaliz"]) -> list[dict]:
    """
    Zayıf yönleri mesaj + iyileştirme adımlarıyla döner.
    Her eleman: {"seviye": "kritik"|"uyari", "mesaj": str, "iyilestir": list[str]}
    """
    zayif = []
    analiz_dict = {a.rasyo_id: a for a in analizler}

    # Kırmızı bayraklar en önce
    for b in skor_sonuc.kirmizi_bayraklar:
        seviye = "kritik" if b.ciddiyet == "kritik" else "uyari"
        zayif.append({
            "seviye": seviye,
            "mesaj": b.mesaj,
            "iyilestir": b.iyilestirme_onerileri if hasattr(b, 'iyilestirme_onerileri') else [],
        })

    # Kötü bantlı rasyolar
    for r in skor_sonuc.rasyolar:
        if r.bant == "kotu":
            analiz = analiz_dict.get(getattr(r, 'id', ''))
            iyilestir = analiz.nasil_iyilestirilir[:3] if analiz and analiz.nasil_iyilestirilir else []
            zayif.append({
                "seviye": "kritik",
                "mesaj": (
                    f"{r.ad}: {r.deger_fmt} — kritik seviyede. "
                    f"Bu rasyo bankacılık değerlendirmesinde olumsuz etki yaratıyor."
                ),
                "iyilestir": iyilestir,
            })

    # Zayıf bantlı rasyolar
    for r in skor_sonuc.rasyolar:
        if r.bant == "zayif":
            analiz = analiz_dict.get(getattr(r, 'id', ''))
            iyilestir = analiz.nasil_iyilestirilir[:3] if analiz and analiz.nasil_iyilestirilir else []
            zayif.append({
                "seviye": "uyari",
                "mesaj": (
                    f"{r.ad}: {r.deger_fmt} — zayıf seviyede. "
                    f"İyileştirme yapılması önerilir."
                ),
                "iyilestir": iyilestir,
            })

    return zayif


# ─────────────────────────────────────────────
# KREDİ TÜRÜ ÖNERİSİ
# Bilançodaki zayıflıklara ve ihtiyaca göre tespit
# ─────────────────────────────────────────────

def _kredi_turu_oneri(bs, skor_sonuc: "SkorSonuc", sektor: str) -> KrediTuruOneri:
    """
    Bilanço yapısından firmanın hangi kredi türüne ihtiyacı olduğunu tespit eder.
    """
    nds       = (bs.stoklar * 365 / bs.satislarin_maliyeti if bs.satislarin_maliyeti else 0) + \
                (bs.ticari_alacaklar * 365 / bs.net_satislar if bs.net_satislar else 0) - \
                (bs.ticari_borclar_kv * 365 / bs.satislarin_maliyeti if bs.satislarin_maliyeti else 0)
    cari_oran = bs.donen_varliklar / bs.kv_borclar if bs.kv_borclar else 0
    duran_varlik_orani = bs.duran_varliklar / bs.toplam_aktif if bs.toplam_aktif else 0

    # Tespit: birincil ihtiyaç
    if cari_oran < 1.3 or nds > 70:
        # İşletme sermayesi sıkıntısı
        isletme_ihtiyac = bs.kv_borclar * 0.3
        birincil = "Rotatif (Döner) Kredi"
        birincil_aciklama = (
            "Cari oranınız ve nakit dönüşüm süreniz işletme sermayesi "
            "sıkıntısına işaret ediyor. Rotatif kredi, ihtiyaç duydukça "
            "çekip geri ödeyebildiğiniz esnek bir kredi türüdür. "
            "Stok alımı, alacak finansmanı ve günlük işletme giderleri için idealdir."
        )
        birincil_miktar = (
            f"Tahmini ihtiyaç: {isletme_ihtiyac:,.0f} – {isletme_ihtiyac*1.5:,.0f} TL "
            f"(KV borçlarınızın yaklaşık %30–50'si)"
        )
        neden = (
            f"Nakit dönüşüm süreniz {nds:.0f} gün — paranız uzun süre "
            f"stok ve alacakta bağlı kalıyor. Rotatif kredi bu döngüyü finanse eder."
        )
    elif duran_varlik_orani > 0.5 and bs.banka_kredileri_uv < bs.duran_varliklar * 0.3:
        # Duran varlıklar yüksek, yatırım finansmanı eksik
        birincil = "Yatırım Kredisi"
        birincil_aciklama = (
            "Duran varlıklarınız toplam aktifinizin önemli bir bölümünü oluşturuyor "
            "ancak uzun vadeli banka finansmanı görece düşük. "
            "Yatırım kredisi, makine, ekipman veya gayrimenkul alımı için "
            "uzun vadeli ve düşük taksitli finansman sağlar."
        )
        birincil_miktar = (
            f"Duran varlık değeriniz: {bs.duran_varliklar:,.0f} TL. "
            f"Mevcut uzun vadeli kredi: {bs.banka_kredileri_uv:,.0f} TL."
        )
        neden = (
            "Duran varlıklarınızın büyük bölümü kısa vadeli finansmanla karşılanıyor "
            "görünüyor. Bu vade uyumsuzluğu nakit akışı baskısı yaratır."
        )
    else:
        # Genel işletme kredisi
        birincil = "Spot / Taksitli İşletme Kredisi"
        birincil_aciklama = (
            "Belirli bir tutar için tek seferlik kredi kullanımı. "
            "Sabit taksitlerle geri ödenir. Nakit akışı planlaması daha kolaydır. "
            "Stok yenileme, vergi ödemeleri veya kısa vadeli nakit ihtiyaçları için uygundur."
        )
        birincil_miktar = (
            f"Tahmini ihtiyaç: {bs.favok * 0.5:,.0f} – {bs.favok:,.0f} TL "
            f"(6 aylık işletme kârı bazında)"
        )
        neden = (
            "Finansal yapınız genel işletme ihtiyacına işaret ediyor. "
            "Spot kredi en esnek ve yaygın kullanılan KOBİ kredi türüdür."
        )

    # Alternatif türler
    alternatifler = []

    if sektor == "ticaret" and bs.ticari_alacaklar > bs.net_satislar * 0.1:
        alternatifler.append({
            "tur": "Faktoring",
            "aciklama": (
                f"Ticari alacaklarınız {bs.ticari_alacaklar:,.0f} TL. "
                "Faktoring ile alacaklarınızı beklemeden nakde çevirebilirsiniz. "
                "Banka kredisi yerine alternatif veya tamamlayıcı finansman."
            ),
        })

    if bs.net_satislar > 5_000_000:
        alternatifler.append({
            "tur": "Çek / Senet İskontosu",
            "aciklama": (
                "Müşterilerinizden aldığınız çek ve senetleri vadesi gelmeden "
                "bankaya iskonto ettirerek nakit elde edebilirsiniz. "
                "Düşük maliyetli ve hızlı bir finansman yöntemi."
            ),
        })

    if sektor in ("uretim", "ticaret") and bs.stoklar > bs.net_satislar * 0.08:
        alternatifler.append({
            "tur": "Stok / Emtia Kredisi",
            "aciklama": (
                f"Stoklarınız {bs.stoklar:,.0f} TL. Stokları teminat göstererek "
                "işletme kredisi kullanabilirsiniz. Stok rehni ile daha yüksek "
                "limit almanız mümkün olabilir."
            ),
        })

    alternatifler.append({
        "tur": "KGF Destekli Kredi",
        "aciklama": (
            "Teminat yetersizliği durumunda KGF kefaleti ile banka limitinizi artırabilirsiniz. "
            "KGF başvurusu bankanız aracılığıyla yapılır, ek belge gerekmez."
        ),
    })

    return KrediTuruOneri(
        birincil_tur=birincil,
        birincil_aciklama=birincil_aciklama,
        birincil_miktar=birincil_miktar,
        alternatif_turler=alternatifler,
        neden=neden,
    )


# ─────────────────────────────────────────────
# NAKİT AKIŞ ANALİZİ
# ─────────────────────────────────────────────

def _nakit_akis_analiz(bs, skor_sonuc: "SkorSonuc") -> NakitAkisAnaliz:
    """
    Aylık FAVÖK, mevcut borç servisi ve yeni kredi taksiti karşılaştırması.
    """
    # Aylık FAVÖK
    aylik_favok = bs.favok / 12 if bs.favok > 0 else 0

    # Mevcut borç servisi tahmini
    # Finansal borçların ortalama 36 ay vadede ödendiğini varsay
    VADE_AY = 36
    FAIZ_ORANI_AYLIK = 0.035  # %3.5 aylık — yaklaşık cari TL kredi faizi
    fb = bs.finansal_borclar
    if fb > 0:
        # Anuitet formülü: taksit = borç × (r × (1+r)^n) / ((1+r)^n - 1)
        r = FAIZ_ORANI_AYLIK
        n = VADE_AY
        mevcut_taksit = fb * (r * (1+r)**n) / ((1+r)**n - 1)
    else:
        mevcut_taksit = 0

    # Kullanılabilir yeni kredi limiti tahmini
    carpan_map = {"AAA": 3.0, "AA": 2.5, "A": 2.0, "BBB": 1.5, "BB": 1.0}
    carpan = carpan_map.get(skor_sonuc.harf, 1.0)
    yeni_limit = max(0, bs.favok * carpan - fb)

    # Yeni kredi taksiti
    if yeni_limit > 0:
        yeni_taksit = yeni_limit * (FAIZ_ORANI_AYLIK * (1+FAIZ_ORANI_AYLIK)**VADE_AY) / \
                      ((1+FAIZ_ORANI_AYLIK)**VADE_AY - 1)
    else:
        yeni_taksit = 0

    toplam_taksit = mevcut_taksit + yeni_taksit

    # Kapasite değerlendirmesi
    if aylik_favok > 0:
        mevcut_oran = mevcut_taksit / aylik_favok
        toplam_oran = toplam_taksit / aylik_favok
    else:
        mevcut_oran = 0
        toplam_oran = 0

    if toplam_oran <= 0.40:
        kapasite = "rahat"
        yorum = (
            f"Aylık işletme kârınızın ({aylik_favok:,.0f} TL) yalnızca "
            f"{toplam_oran*100:.0f}%'i borç servisine gidecek. "
            f"Kredi geri ödemesinde rahat bir kapasiteniz var."
        )
    elif toplam_oran <= 0.60:
        kapasite = "makul"
        yorum = (
            f"Aylık işletme kârınızın {toplam_oran*100:.0f}%'i borç servisine gidecek. "
            f"Yönetilebilir bir yük ancak beklenmedik gider durumunda dikkatli olunmalı."
        )
    elif toplam_oran <= 0.80:
        kapasite = "riskli"
        yorum = (
            f"Aylık işletme kârınızın {toplam_oran*100:.0f}%'i borç servisine gidecek. "
            f"Bu yüksek bir oran. Satışlarda küçük bir düşüş ödeme güçlüğü yaratabilir. "
            f"Kredi miktarını azaltmayı veya vadeyi uzatmayı düşünün."
        )
    else:
        kapasite = "kritik"
        yorum = (
            f"Aylık işletme kârınızın {toplam_oran*100:.0f}%'i borç servisine gidecek — "
            f"kritik seviye. Bu krediyi geri ödemek çok güçtür. "
            f"Daha düşük limitten başlamanızı veya önce FAVÖK'ü artırmanızı öneririz."
        )

    def fmt_tl(v):
        return f"{v:,.0f} TL"

    return NakitAkisAnaliz(
        aylik_favok=aylik_favok,
        aylik_favok_fmt=fmt_tl(aylik_favok),
        mevcut_borc_servisi_aylik=mevcut_taksit,
        mevcut_borc_servisi_fmt=fmt_tl(mevcut_taksit),
        favok_kullanim_orani=mevcut_oran,
        yeni_kredi_taksiti_aylik=yeni_taksit,
        yeni_kredi_taksiti_fmt=fmt_tl(yeni_taksit),
        toplam_borc_servisi_aylik=toplam_taksit,
        toplam_borc_servisi_fmt=fmt_tl(toplam_taksit),
        toplam_favok_kullanim_orani=toplam_oran,
        kapasite_degerlendirmesi=kapasite,
        yorum=yorum,
    )




def _senaryo_hesapla(bs, sektor: str, aciklama: str, degisiklikler: dict) -> SenaryoSonuc:
    """
    Verilen bilanço değişikliklerini uygular ve yeni skoru hesaplar.
    degisiklikler: {"alan_adi": delta_TL}
    """
    from scorer import skorla
    import copy

    # BalanceSheet'i kopyala
    import dataclasses
    bs2 = dataclasses.replace(bs)

    # Değişiklikleri uygula
    for alan, delta in degisiklikler.items():
        if hasattr(bs2, alan):
            mevcut = getattr(bs2, alan)
            setattr(bs2, alan, mevcut + delta)

    # Yeni skor hesapla
    yeni_sonuc = skorla(bs2, sektor=sektor)

    return SenaryoSonuc(
        aciklama=aciklama,
        degisiklik=degisiklikler,
        yeni_skor=yeni_sonuc.skor,
        skor_delta=yeni_sonuc.skor - 0,  # base skor dışarıdan gelecek
        yeni_harf=yeni_sonuc.harf,
        yeni_limit_aciklama=yeni_sonuc.kredi_limit_aciklama,
        etkilenen_rasyolar=[],
    )


SENARYO_TANIMLARI = [
    {
        "aciklama": "Ortaklar cari hesabını (331) sermayeye ekle",
        "degisiklikler": lambda bs: {
            "ortaklara_borclar": -bs.ortaklara_borclar,
            "odenmis_sermaye": bs.ortaklara_borclar,
        },
        "etkilenen": ["borc_ozkaynak", "finansal_kaldırac", "ortaklar_cari_orani", "kv_borc_orani"],
    },
    {
        "aciklama": "Kısa vadeli banka kredisinin yarısını uzun vadeye çevir",
        "degisiklikler": lambda bs: {
            "banka_kredileri_kv": -(bs.banka_kredileri_kv * 0.5),
            "banka_kredileri_uv": bs.banka_kredileri_kv * 0.5,
        },
        "etkilenen": ["cari_oran", "asit_test", "kv_borc_orani"],
    },
    {
        "aciklama": "Stokların %30'unu erit, nakde çevir",
        "degisiklikler": lambda bs: {
            "stoklar": -(bs.stoklar * 0.3),
            "banka": bs.stoklar * 0.3,
        },
        "etkilenen": ["cari_oran", "asit_test", "stok_devir", "nakit_donusum_suresi"],
    },
    {
        "aciklama": "Vadesi geçmiş alacakların %50'sini tahsil et",
        "degisiklikler": lambda bs: {
            "ticari_alacaklar": -(bs.ticari_alacaklar * 0.5),
            "banka": bs.ticari_alacaklar * 0.5,
        },
        "etkilenen": ["asit_test", "nakit_oran", "alacak_tahsil_suresi", "nakit_donusum_suresi"],
    },
    {
        "aciklama": "Sermaye artırımı (özkaynaklar kadar ek sermaye)",
        "degisiklikler": lambda bs: {
            "odenmis_sermaye": bs.ozkaynaklar,
            "banka": bs.ozkaynaklar,
        },
        "etkilened": ["borc_ozkaynak", "finansal_kaldırac", "cari_oran", "nakit_oran"],
    },
    {
        "aciklama": "Tüm aksiyonları birlikte uygula",
        "degisiklikler": lambda bs: {
            "ortaklara_borclar": -bs.ortaklara_borclar,
            "odenmis_sermaye": bs.ortaklara_borclar,
            "banka_kredileri_kv": -(bs.banka_kredileri_kv * 0.5),
            "banka_kredileri_uv": bs.banka_kredileri_kv * 0.5,
            "stoklar": -(bs.stoklar * 0.3),
            "ticari_alacaklar": -(bs.ticari_alacaklar * 0.3),
            "banka": (bs.stoklar * 0.3 + bs.ticari_alacaklar * 0.3),
        },
        "etkilened": ["cari_oran", "asit_test", "borc_ozkaynak", "kv_borc_orani", "ortaklar_cari_orani"],
    },
]


def _senaryolari_hesapla(bs, skor_sonuc: "SkorSonuc", sektor: str) -> list[SenaryoSonuc]:
    from scorer import skorla
    import dataclasses

    baz_skor = skor_sonuc.skor
    sonuclar = []

    for tanim in SENARYO_TANIMLARI:
        try:
            bs2 = dataclasses.replace(bs)
            delta = tanim["degisiklikler"](bs)
            for alan, deger in delta.items():
                if hasattr(bs2, alan):
                    setattr(bs2, alan, max(0, getattr(bs2, alan) + deger))

            yeni = skorla(bs2, sektor=sektor)
            sonuclar.append(SenaryoSonuc(
                aciklama=tanim["aciklama"],
                degisiklik=delta,
                yeni_skor=yeni.skor,
                skor_delta=yeni.skor - baz_skor,
                yeni_harf=yeni.harf,
                yeni_limit_aciklama=yeni.kredi_limit_aciklama,
                etkilenen_rasyolar=tanim.get("etkilenen", []),
            ))
        except Exception as e:
            pass

    # "Tüm aksiyonları uygula" senaryosunu sona al
    tekli = [s for s in sonuclar if "birlikte" not in s.aciklama.lower()]
    kombine = [s for s in sonuclar if "birlikte" in s.aciklama.lower()]

    # Zorluk/etki oranına göre sırala (yüksek etki + düşük zorluk önce)
    # Senaryo tanımına zorluk puanı ekleyelim
    zorluk_map = {
        "Ortaklar cari": 3,      # Düşük zorluk
        "vadesi geçmiş": 2,      # Orta zorluk
        "Stok": 2,               # Orta zorluk
        "Kısa vadeli banka": 2,  # Orta zorluk
        "Sermaye artırımı": 1,   # Yüksek zorluk
    }

    def oncelik(s):
        zorluk = 1
        for anahtar, puan in zorluk_map.items():
            if anahtar.lower() in s.aciklama.lower():
                zorluk = puan
                break
        return s.skor_delta * zorluk

    tekli.sort(key=oncelik, reverse=True)
    return tekli + kombine


def _senaryo_tl_aciklama(aciklama: str, degisiklik: dict, bs) -> str:
    """Senaryo için somut TL rakamı içeren açıklama üretir."""
    for alan, delta in degisiklik.items():
        delta_abs = abs(delta)
        if delta_abs > 0:
            if alan == "ortaklara_borclar":
                return f"{aciklama} ({delta_abs:,.0f} TL)"
            if alan == "banka_kredileri_kv":
                return f"{aciklama} ({delta_abs:,.0f} TL)"
            if alan == "stoklar":
                return f"{aciklama} ({delta_abs:,.0f} TL nakde çevrilir)"
            if alan == "ticari_alacaklar":
                return f"{aciklama} ({delta_abs:,.0f} TL tahsil edilir)"
            if alan == "odenmis_sermaye" and "artırım" in aciklama.lower():
                return f"{aciklama} ({delta_abs:,.0f} TL ek sermaye)"
    return aciklama


# ─────────────────────────────────────────────
# 6. BANKA BAŞVURU HAZIRLIĞI
# ─────────────────────────────────────────────

def _banka_hazirlik(skor_sonuc: "SkorSonuc", bs) -> BankaHazirlik:
    harf = skor_sonuc.harf
    bayraklar = {b.kod for b in skor_sonuc.kirmizi_bayraklar}

    # Muhtemel sorular — skor bandına ve zayıf noktalara göre
    sorular = [
        "Son 3 yılın finansal tablolarını görebilir miyiz?",
        "Şirketin ana faaliyet geliri ve müşteri yapısı nedir?",
        "Mevcut banka kredilerinin vade ve faiz yapısı nedir?",
    ]

    if "ortaklar_cari_siskinligi" in bayraklar:
        sorular.append(
            "Ortaklar cari hesabında görünen tutar neden bu kadar yüksek? "
            "Bu tutar gerçek bir borç mu yoksa geçici bir kalem mi?"
        )
    if skor_sonuc.likidite_puan / 22 < 0.5:
        sorular.append(
            "Kısa vadeli borç yükümlülüklerinizi nasıl karşılıyorsunuz? "
            "Nakit akışı projeksiyonunuz var mı?"
        )
    if skor_sonuc.sermaye_puan / 24 < 0.5:
        sorular.append(
            "Borç/özkaynak oranınız yüksek görünüyor. "
            "Sermaye yapısını güçlendirmek için planınız nedir?"
        )
    if harf in ("BB", "B", "D"):
        sorular.append("Teklif edebileceğiniz teminatların detaylarını paylaşabilir misiniz?")
        sorular.append("Sektörünüzdeki rekabet durumu ve büyüme planınız nedir?")

    # Hazırlanacak belgeler
    belgeler = [
        "Son 2 yıl vergi levhası ve beyanname",
        "Son dönem mizan veya bilanço",
        "Son 3 ay banka hesap özeti (tüm bankalar)",
        "Şirket imza sirküleri ve ticaret sicil gazetesi",
        "Ortaklar ve yöneticilerin kimlik fotokopisi",
        "SGK ve vergi borcu yoktur yazısı",
    ]

    if harf in ("BBB", "BB", "B"):
        belgeler += [
            "Gayrimenkul varsa tapu ve ekspertiz raporu",
            "Araç/ekipman varsa ruhsat ve değerleme",
            "KGF başvurusu için NACE kodu teyit belgesi",
        ]

    if skor_sonuc.karlilik_puan / 26 > 0.7:
        belgeler.append("Son dönem sipariş/sözleşme listesi (güçlü ciro kanıtı için)")

    # Dikkat edilecekler
    dikkatler = [
        "Bankaya gitmeden önce Findeks kredi notunuzu kontrol edin",
        "Tüm ortakların kişisel kredi sicilinin temiz olduğunu doğrulayın",
        "Vergi ve SGK borcu varsa başvuru öncesinde kapatın",
        "Birden fazla bankaya aynı anda başvurmak kredi notunuzu olumsuz etkileyebilir",
        "Bu raporu destekleyici belge olarak bankaya sunabilirsiniz",
    ]

    if "ortaklar_cari_siskinligi" in bayraklar:
        dikkatler.insert(0,
            "ÖNCE YAPILACAK: Ortaklar cari hesabını sermayeye ekleyin — "
            "bu tek adım banka değerlendirmenizi önemli ölçüde iyileştirir"
        )

    return BankaHazirlik(
        muhtemel_sorular=sorular,
        hazirlanacak_belgeler=belgeler,
        dikkat_edilecekler=dikkatler,
    )


# ─────────────────────────────────────────────
# 7. ZAMAN ÇİZELGESİ
# ─────────────────────────────────────────────

def _zaman_cizelgesi(skor_sonuc: "SkorSonuc", senaryolar: list[SenaryoSonuc]) -> list[dict]:
    """
    Skor bandına ve mevcut zayıflıklara göre aksiyon zaman çizelgesi üretir.
    """
    cizelge = []
    bayraklar = {b.kod for b in skor_sonuc.kirmizi_bayraklar}

    # Hemen yapılabilecekler (1–4 hafta)
    hemen = []
    if "ortaklar_cari_siskinligi" in bayraklar:
        hemen.append("Ortaklar cari hesabını sermayeye ekle (muhasebe kaydı yeterli, maliyet sıfır)")
    if any(r.bant == "kotu" for r in skor_sonuc.rasyolar if r.kategori == "likidite"):
        hemen.append("Vadesi geçmiş alacaklar için acil tahsilat kampanyası başlat")
    hemen.append("Findeks raporu al, kişisel kredi sicilini kontrol et")
    hemen.append("Vergi ve SGK borcu varsa öde veya yapılandır")

    if hemen:
        cizelge.append({
            "donem": "Hemen (1–4 hafta)",
            "aksiyonlar": hemen,
            "beklenen_etki": "Kırmızı bayrakların temizlenmesi, banka başvurusuna hazırlık",
        })

    # Kısa vadeli (1–3 ay)
    kisa = []
    for r in skor_sonuc.rasyolar:
        if r.bant in ("kotu", "zayif") and r.kategori in ("likidite", "faaliyet"):
            rid = getattr(r, 'id', '')
            if rid == "stok_devir":
                kisa.append("Yavaş dönen stokları indirimli sat, nakde çevir")
            elif rid == "alacak_tahsil_suresi":
                kisa.append("Alacak tahsilat sürecini sıkılaştır, vade politikasını güncelle")
            elif rid == "nakit_donusum_suresi":
                kisa.append("Tedarikçilerle ödeme vadesi uzatma müzakeresi yap")
    kisa.append("Banka başvurusu için gerekli belgeler toparla")

    if skor_sonuc.skor >= 55:
        kisa.append("Seçilen 1–2 bankaya ön görüşme talebi ilet")

    if kisa:
        cizelge.append({
            "donem": "Kısa vadeli (1–3 ay)",
            "aksiyonlar": list(dict.fromkeys(kisa)),  # tekrar temizle
            "beklenen_etki": "Likidite iyileşmesi, banka görüşmelerine hazırlık",
        })

    # Orta vadeli (3–6 ay)
    orta = []
    for r in skor_sonuc.rasyolar:
        if r.bant in ("kotu", "zayif") and r.kategori == "sermaye":
            rid = getattr(r, 'id', '')
            if rid == "kv_borc_orani":
                orta.append("Kısa vadeli kredileri uzun vadeye çevirmek için banka müzakeresi")
            elif rid == "borc_ozkaynak":
                orta.append("Kâr dağıtımı yapmayarak özkaynak birikimini hızlandır")

    # En yüksek etkili senaryo bandı iyileştirme
    if senaryolar:
        en_iyi = senaryolar[0]
        if en_iyi.skor_delta >= 5:
            orta.append(
                f"'{en_iyi.aciklama}' aksiyonunu uygula → "
                f"tahmini +{en_iyi.skor_delta} puan, {en_iyi.yeni_harf} bandı"
            )

    if orta:
        cizelge.append({
            "donem": "Orta vadeli (3–6 ay)",
            "aksiyonlar": list(dict.fromkeys(orta)),
            "beklenen_etki": "Sermaye yapısı iyileşmesi, kredi limiti artışı",
        })

    # Uzun vadeli (6–12 ay)
    uzun = [
        "Düzenli aylık finansal raporlama sistemi kur",
        "Bir sonraki dönem için daha yüksek skor hedefi belirle",
        "Banka ilişkisini aktif tut — limit artırım başvurusu değerlendir",
    ]

    if skor_sonuc.skor < 65:
        uzun.insert(0, "Finansal yapı iyileştirmesi tamamlandıktan sonra banka başvurusu yap")

    cizelge.append({
        "donem": "Uzun vadeli (6–12 ay)",
        "aksiyonlar": uzun,
        "beklenen_etki": "Sürdürülebilir finansal sağlık, düşük maliyetli kredi erişimi",
    })

    return cizelge


# ─────────────────────────────────────────────
# 8. DISCLAIMER
# ─────────────────────────────────────────────

DISCLAIMER = """
YASAL UYARI VE SINIRLAMALAR

Bu rapor, yüklenen mizan verisi baz alınarak BilankoIQ sistemi tarafından otomatik 
olarak üretilmiştir. Aşağıdaki hususların dikkate alınması zorunludur:

1. TAHMİNİ ANALİZ: Bu raporda yer alan KrediSkor, harf notu, kredi limit tahminleri 
   ve teminat yapısı bilgileri yalnızca ön değerlendirme niteliğindedir. Herhangi bir 
   bankanın kredi kararını temsil etmez ve garanti etmez.

2. BANKA BAĞIMSIZLIĞI: Her bankanın kendi iç kredi değerlendirme metodolojisi, sektör 
   politikaları ve risk iştahı farklıdır. Aynı finansal verilerle farklı bankalar 
   farklı kararlar verebilir.

3. VERİ DOĞRULUĞU: Analizin kalitesi yüklenen mizan verisinin doğruluğuna bağlıdır. 
   Eksik, hatalı veya güncel olmayan veriler sonuçları olumsuz etkileyebilir.

4. MALİ MÜŞAVİR DANIŞMANLIĞI: Bu rapor, serbest muhasebeci mali müşavir (SMMM) veya 
   yeminli mali müşavir (YMM) görüşünün yerine geçmez. Önemli finansal kararlar 
   öncesinde uzman danışmanlık alınması tavsiye edilir.

5. NİTEL FAKTÖRLER: Banka değerlendirmesi yalnızca finansal rasyolarla sınırlı değildir. 
   Yönetim kalitesi, sektör görünümü, müşteri ilişkileri ve teminat değeri gibi nitel 
   faktörler de kredi kararını etkiler.

6. GÜNCELLIK: Bu analiz raporun üretildiği tarih itibarıyla geçerlidir. Finansal 
   tablolardaki değişiklikler sonuçları etkileyecektir.

BilankoIQ bu rapordaki bilgilere dayanılarak alınan kararlar sonucunda oluşabilecek 
zararlardan sorumlu tutulamaz.
""".strip()


# ─────────────────────────────────────────────
# 9. ANA FONKSİYON
# ─────────────────────────────────────────────

def rapor_olustur(
    bs,
    skor_sonuc: "SkorSonuc",
    analizler: list["RasyoAnaliz"],
    sektor: str = "ticaret",
    firma_adi: str = "Firma",
) -> TamRapor:
    """
    Tam raporu üretir.

    Args:
        bs: BalanceSheet objesi
        skor_sonuc: SkorSonuc objesi (scorer.py çıktısı)
        analizler: RasyoAnaliz listesi (analyzer.py çıktısı)
        sektor: "ticaret" | "uretim" | "hizmet"
        firma_adi: Raporda görünecek firma adı

    Returns:
        TamRapor objesi
    """
    # Senaryolar
    senaryolar = _senaryolari_hesapla(bs, skor_sonuc, sektor)

    # Skor deltalarını düzelt (baz skor eksikti)
    for s in senaryolar:
        s.skor_delta = s.yeni_skor - skor_sonuc.skor

    # Filtrele — sadece pozitif etkileri göster
    senaryolar = [s for s in senaryolar if s.skor_delta > 0]

    # Senaryolara TL açıklaması ekle
    for s in senaryolar:
        s.aciklama = _senaryo_tl_aciklama(s.aciklama, s.degisiklik, bs)

    from question_bank import sorulari_uret
    banka_sorulari = sorulari_uret(bs, skor_sonuc)

    return TamRapor(
        firma_adi=firma_adi,
        sektor=sektor,
        yonetici_ozeti=_yonetici_ozeti(skor_sonuc, bs),
        guclu_yonler=_guclu_yonler(skor_sonuc, analizler),
        zayif_yonler=_zayif_yonler(skor_sonuc, analizler),
        rasyo_analizleri=analizler,
        kredi_turu_oneri=_kredi_turu_oneri(bs, skor_sonuc, sektor),
        nakit_akis_analiz=_nakit_akis_analiz(bs, skor_sonuc),
        banka_sorulari=banka_sorulari,
        aksiyon_plani=skor_sonuc.aksiyon_listesi,
        senaryolar=senaryolar,
        banka_hazirlik=_banka_hazirlik(skor_sonuc, bs),
        zaman_cizelgesi=_zaman_cizelgesi(skor_sonuc, senaryolar),
        disclaimer=DISCLAIMER,
    )
