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
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scorer import SkorSonuc
    from analyzer import RasyoAnaliz

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# CLAUDE API RETRY WRAPPER (529 Overloaded)
# ─────────────────────────────────────────────
def _claude_call(client, model, max_tokens, messages_list, max_retries=6):
    import time, anthropic
    for attempt in range(max_retries):
        try:
            return client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=messages_list,
            )
        except anthropic.APIStatusError as e:
            if e.status_code == 529:
                wait = min(2 ** attempt, 60)
                print(f"[529 overloaded] {wait}s bekleniyor (deneme {attempt+1}/{max_retries})...")
                time.sleep(wait)
            else:
                raise
    raise Exception(f"Claude API {max_retries} denemede yanıt vermedi (529 overloaded)")


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
    potansiyel_raporu: str
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
    skor_iyilestirme: str
    alt_hesap_analizi: list   # list[dict] — her dict: ana_hesap_kodu, ana_hesap_adi, analiz_metni, uyari_notu
    disclaimer: str


# ─────────────────────────────────────────────
# 2. YÖNETİCİ ÖZETİ
# ─────────────────────────────────────────────

def _yonetici_ozeti(skor_sonuc: "SkorSonuc", bs) -> str:
    import anthropic, os, re

    guclu = [(r.ad, r.deger_fmt) for r in skor_sonuc.rasyolar if r.bant in ("mukemmel", "iyi")]
    zayif = [(r.ad, r.deger_fmt) for r in skor_sonuc.rasyolar if r.bant in ("kotu", "zayif")]
    kritik_bayraklar = [b for b in skor_sonuc.kirmizi_bayraklar if b.ciddiyet == "kritik"]

    guclu_str = ", ".join([f"{ad} {fmt}" for ad, fmt in guclu[:5]])
    zayif_str = ", ".join([f"{ad} {fmt}" for ad, fmt in zayif[:5]])
    bayrak_str = ", ".join([b.mesaj[:60] for b in kritik_bayraklar[:3]]) if kritik_bayraklar else "Yok"

    carpan_map = {"AAA": 3.0, "AA": 2.5, "A": 2.0}
    carpan = carpan_map.get(skor_sonuc.harf, 0)
    kullanilabilir = max(0, bs.favok * carpan - bs.finansal_borclar) if carpan else 0
    favok_marj = bs.favok / bs.net_satislar * 100 if bs.net_satislar else 0

    limit_str = f"{kullanilabilir:,.0f} TL" if kullanilabilir > 0 else "Mevcut finansal yapıda kredi limiti düşük — iyileştirme gerekli"
    toplam_aktif = bs.toplam_aktif or 1

    prompt = f"""Sen deneyimli bir Türk bankacısın. Aşağıdaki finansal verilere göre firma sahibine hitap eden, samimi ve net bir yönetici özeti yaz. Türkçe yaz.

FİRMA FİNANSAL VERİLERİ:
- Kredi Skoru: {skor_sonuc.skor}/100 ({skor_sonuc.harf} bandı)
- Net Satışlar: {bs.net_satislar:,.0f} TL
- FAVÖK: {bs.favok:,.0f} TL (Marj: %{favok_marj:.1f})
- Net Kâr: {bs.net_kar:,.0f} TL
- Toplam Aktif: {bs.toplam_aktif:,.0f} TL
- Tahmini Kullanılabilir Limit: {limit_str}

HESAP DETAYLARI (bankacı gözüyle yorumlanacak):
DÖNEN VARLIKLAR:
- Kasa (100): {bs.kasa:,.0f} TL (%{bs.kasa/toplam_aktif*100:.1f} aktif)
- Banka (102): {bs.banka:,.0f} TL (%{bs.banka/toplam_aktif*100:.1f} aktif)
- Ticari Alacaklar (120-121): {bs.ticari_alacaklar:,.0f} TL (%{bs.ticari_alacaklar/toplam_aktif*100:.1f} aktif)
- Stoklar (150-158): {bs.stoklar:,.0f} TL (%{bs.stoklar/toplam_aktif*100:.1f} aktif)
- Diğer Dönen Varlıklar: {bs.diger_donen_varliklar:,.0f} TL

DURAN VARLIKLAR:
- Maddi Duran Varlıklar (250-258): {bs.maddi_duran_varliklar:,.0f} TL (%{bs.maddi_duran_varliklar/toplam_aktif*100:.1f} aktif)
- Mali Duran Varlıklar (240-248): {bs.mali_duran_varliklar:,.0f} TL
- Maddi Olmayan Duran Varlıklar: {bs.maddi_olmayan_duv:,.0f} TL

YABANCI KAYNAKLAR:
- Banka Kredileri KV (300-301): {bs.banka_kredileri_kv:,.0f} TL
- Ticari Borçlar KV (320-321): {bs.ticari_borclar_kv:,.0f} TL
- Ortaklara Borçlar (331): {bs.ortaklara_borclar:,.0f} TL
- Banka Kredileri UV (400-401): {bs.banka_kredileri_uv:,.0f} TL

ÖZKAYNAKLAR:
- Ödenmiş Sermaye (500): {bs.odenmis_sermaye:,.0f} TL
- Geçmiş Yıl Kârları (570): {bs.gecmis_yil_karlari:,.0f} TL
- Dönem Net Kârı (590): {bs.donem_net_kari:,.0f} TL
- Toplam Özkaynaklar: {bs.ozkaynaklar:,.0f} TL

GELİR TABLOSU:
- Satışların Maliyeti: {bs.satislarin_maliyeti:,.0f} TL (Brüt Marj: %{(bs.net_satislar-bs.satislarin_maliyeti)/bs.net_satislar*100 if bs.net_satislar else 0:.1f})
- Pazarlama Giderleri: {bs.pazarlama_giderleri:,.0f} TL
- Genel Yönetim Giderleri: {bs.genel_yonetim_giderleri:,.0f} TL
- Finansman Giderleri: {bs.finansman_giderleri:,.0f} TL
- Finansman Gelirleri: {bs.finansman_gelirleri:,.0f} TL

GÜÇLÜ YÖNLER: {guclu_str}
ZAYIF YÖNLER: {zayif_str}
KRİTİK UYARILAR: {bayrak_str}

YAZIM KURALLARI:
Aşağıdaki 5 bölümü sırayla yaz, her biri bir paragraf olsun:

1. GENEL DEĞERLENDİRME: Skor bandının ne anlama geldiğini, şirketin genel finansal profilini anlat.
2. VARLIK YAPISI YORUMU: Kasa yüksekse "bankalar fiktif kabul eder, sermayeden mahsup edilir" gibi bankacı perspektifinden uyarılar ver. Alacaklar yüksekse tahsilat riskine dikkat çek. Stoklar şişkince "stok devir hızı yavaş, bu nakit akışını zorlar" de. Her kalem için aktife oranını kullanarak somut yorum yap.
3. BORÇ VE ÖZKAYNAK YAPISI: Ortaklara borç yüksekse "bankalar bunu örtülü kâr dağıtımı olarak değerlendirebilir" de. Finansman giderleri yüksekse faiz yüküne dikkat çek. Sermaye yetersizse bunu vurgula.
4. GÜÇLÜ VE ZAYIF YÖNLER: En kritik güçlü ve zayıf yönleri somut rakamlarla anlat.
5. BilancoSkor YAKLAŞIMI: Finansal göstergelerin genel değerlendirmesini ve olası senaryoları özetle.

- Sayıları TL formatında yaz
- Şirketiniz diye hitap et
- Teknik jargondan kaçın ama bankacı uyarılarını net ver
- İstediğin kadar yaz, kesme
- ÖNEMLİ — DİL KURALLARI: BilancoSkor bir finansal analiz yazılımıdır, resmi kredi derecelendirme kuruluşu değildir. Bu yüzden:
  * "kredi kullanabilirsiniz" veya "kredi başvurusu değerlendirilebilir" yerine "finansal göstergeler olumlu profil oluştuğuna işaret etmektedir" yaz
  * "kredi verilmez" yerine "kredi onayı zorlaşabilir" yaz
  * "bankalar sizi AA olarak görür" gibi kesin yargılar yazma, "AA bandındaki firmalar genellikle..." şeklinde yaz
  * "AA bandındaki firmalar genellikle bankalar nezdinde olumlu değerlendirme almakta" yerine "AA bandındaki finansal profiller, finansal değerlendirme süreçlerinde olumlu olarak yorumlanabilmektedir" yaz
  * "KREDİ POTANSİYELİ VE ÖNERİLER" başlığı yerine "BilancoSkor Yaklaşımı" başlığını kullan
  * "limit alabilirsiniz" yerine "tahmini limit potansiyeli oluşabilir" yaz
  * Hiçbir zaman kredi kararı verir gibi yazma, her zaman tahmini/algoritmik analiz olduğunu hissettir
  * "bankalar tarafından düşük risk profili olarak değerlendirilmekte" gibi banka adına kesin yargı yazma; yerine "AA bandındaki firmalar genellikle düşük risk göstergelerine sahip olmaktadır" formatını kullan
  * "tavsiye ederim", "öneriyorum", "yapmanızı öneririm" gibi birinci tekil şahıs danışmanlık ifadeleri kullanma; bunların yerine "bu göstergede iyileşme sağlanması durumunda..." veya "bu adım finansal profili güçlendirebilir" formatını kullan"""

    try:
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        message = _claude_call(client, "claude-sonnet-4-20250514", 2000, [{"role": "user", "content": prompt}])
        return message.content[0].text.strip()
    except Exception as e:
        harf = skor_sonuc.harf
        skor = skor_sonuc.skor
        if skor >= 75:
            return f"Şirketinizin finansal yapısı güçlü görünmektedir. {harf} notu, finansal göstergeler açısından olumlu bir profil oluştuğuna işaret etmektedir."
        elif skor >= 55:
            return f"Şirketinizin finansal yapısı orta düzeydedir. {harf} notu, teminatlı finansman senaryolarında olumlu profil oluştuğuna işaret etmektedir."
        else:
            return f"Şirketinizin finansal yapısında önemli zayıflıklar tespit edilmiştir. {harf} notu, mevcut finansal profilde kredi erişiminin zorlaşabileceğine işaret etmektedir."


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
            import re
            aciklama_k = analiz.ne_anlama_gelir if analiz else ""
            cumleler_k = re.split(r'(?<=[a-züöçşığıA-ZÜÖÇŞİĞI])\. ', aciklama_k)
            ozet_k = cumleler_k[0].rstrip('.') + "." if cumleler_k else ""
            zayif.append({
                "seviye": "kritik",
                "mesaj": (
                    f"{r.ad}: {r.deger_fmt} — kritik seviyede. "
                    + (ozet_k + " " if ozet_k else "")
                    + "Bu rasyo kredilendirilme sürecinizi olumsuz etkileyebilir."
                ),
                "iyilestir": iyilestir,
            })

    # Zayıf bantlı rasyolar
    for r in skor_sonuc.rasyolar:
        if r.bant == "zayif":
            analiz = analiz_dict.get(getattr(r, 'id', ''))
            iyilestir = analiz.nasil_iyilestirilir[:3] if analiz and analiz.nasil_iyilestirilir else []
            import re
            aciklama_z = analiz.ne_anlama_gelir if analiz else ""
            cumleler_z = re.split(r'(?<=[a-züöçşığıA-ZÜÖÇŞİĞI])\. ', aciklama_z)
            ozet_z = cumleler_z[0].rstrip('.') + "." if cumleler_z else ""
            zayif.append({
                "seviye": "uyari",
                "mesaj": (
                    f"{r.ad}: {r.deger_fmt} — zayıf seviyede. "
                    + (ozet_z + " " if ozet_z else "")
                    + "Bu göstergede iyileştirme yapılması durumunda finansal profil güçlenebilir."
                ),
                "iyilestir": iyilestir,
            })

    return zayif


# ─────────────────────────────────────────────
# FİNANSMAN ARAÇLARI – GENEL BİLGİLENDİRME
# Bilançodaki zayıflıklara ve ihtiyaca göre tespit
# ─────────────────────────────────────────────

def _kredi_turu_oneri(bs, skor_sonuc: "SkorSonuc", sektor: str) -> KrediTuruOneri:
    """
    Bilanço yapısından firmanın hangi kredi türüne ihtiyacı olduğunu tespit eder.
    """
    nds           = (bs.stoklar * 365 / bs.satislarin_maliyeti if bs.satislarin_maliyeti else 0) + \
                    (bs.ticari_alacaklar * 365 / bs.net_satislar if bs.net_satislar else 0) - \
                    (bs.ticari_borclar_kv * 365 / bs.satislarin_maliyeti if bs.satislarin_maliyeti else 0)
    alacak_gun    = bs.ticari_alacaklar * 365 / bs.net_satislar if bs.net_satislar else 0
    cari_oran     = bs.donen_varliklar / bs.kv_borclar if bs.kv_borclar else 0
    duran_oran    = bs.duran_varliklar / bs.toplam_aktif if bs.toplam_aktif else 0
    skor          = skor_sonuc.skor

    # ── BİRİNCİL KREDİ ──────────────────────────────────────────
    # Rotatif: işletme sermayesi sıkıntısı varsa her zaman öncelik
    isletme_ihtiyac = bs.kv_borclar * 0.3
    birincil = "Rotatif (Döner) Kredi"
    birincil_aciklama = (
        "Rotatif kredi, ihtiyaç duydukça çekip geri ödeyebildiğiniz "
        "esnek bir kredi türüdür. Stok alımı, alacak finansmanı ve "
        "günlük işletme giderleri için bu tür profillerde yaygın tercih edilen bir finansman aracıdır."
    )
    birincil_miktar = (
        f"Tahmini ihtiyaç: {isletme_ihtiyac:,.0f} – {isletme_ihtiyac*1.5:,.0f} TL "
        f"(KV borçlarınızın yaklaşık %30–50'si)"
    )

    # Alacak tahsil süresine göre spot kredi önerisi
    if 45 <= alacak_gun <= 95 and bs.ticari_alacaklar > 0:
        aylik_tahsilat = bs.net_satislar / 12 if bs.net_satislar else 0
        gun_fmt = f"{alacak_gun:.0f}"
        neden = (
            f"Ortalama alacak tahsil süreniz {gun_fmt} gün. "
            f"Aylık ortalama tahsilatınız {aylik_tahsilat:,.0f} TL civarında. "
            f"Bu durumda {gun_fmt} günlük vadeli spot krediler kullanarak "
            f"hem kısa vadeli kalır hem de limitiniz sürekli kapanıp açılır. "
            f"Rotatif ile birlikte kullanıldığında nakit akışınızı optimize eder."
        )
    elif cari_oran < 1.3 or nds > 70:
        neden = (
            f"Nakit dönüşüm süreniz {nds:.0f} gün — paranız uzun süre "
            f"stok ve alacakta bağlı kalıyor. Rotatif kredi bu döngüyü finanse eder."
        )
    else:
        neden = (
            "İşletme sermayenizi esnek tutmak ve nakit akışı dalgalanmalarını "
            "yönetmek için rotatif kredi yaygın olarak tercih edilen bir finansman aracıdır."
        )

    # ── ALTERNATİF KREDİLER ──────────────────────────────────────
    alternatifler = []

    # 1. Taksitli İşletme Kredisi (12/24 ay) — duran varlık yatırımı varsa
    if duran_oran > 0.4 or bs.banka_kredileri_uv < bs.duran_varliklar * 0.2:
        alternatifler.append({
            "tur": "Taksitli İşletme Kredisi (12–24 ay)",
            "aciklama": (
                f"Duran varlıklarınız {bs.duran_varliklar:,.0f} TL. "
                "Makine, ekipman veya yapısal yatırımlar için 12–24 ay vadeli "
                "taksitli kredi uygundur. Sabit taksitlerle nakit akışı planlaması kolaylaşır. "
                "Faiz ortamına bağlı olarak uzun vadeli finansman tercihleri farklı riskler barındırabilir."
            ),
        })

    # 2. Çek / Senet İskontosu — alacak senedi varsa
    if bs.ticari_alacaklar > 0 and alacak_gun > 45:
        alternatifler.append({
            "tur": "Çek / Senet İskontosu",
            "aciklama": (
                f"Alacak tahsil süreniz {alacak_gun:.0f} gün. "
                "Müşterilerinizden aldığınız çek ve senetleri vadesi gelmeden "
                "bankaya iskonto ettirerek hızlıca nakde çevirebilirsiniz. "
                "Düşük maliyetli ve hızlı bir finansman yöntemi."
            ),
        })

    # 3. Stok / Emtia Kredisi — stok yüksekse
    if sektor in ("uretim", "ticaret") and bs.stoklar > bs.net_satislar * 0.1:
        alternatifler.append({
            "tur": "Stok / Emtia Kredisi",
            "aciklama": (
                f"Stoklarınız {bs.stoklar:,.0f} TL. Stokları teminat göstererek "
                "işletme kredisi kullanabilirsiniz. Stok rehni ile daha yüksek "
                "limit almanız mümkün olabilir."
            ),
        })

    # 4. Faktoring — sadece skor >= 65 olan güçlü firmalara öner
    if skor >= 65 and alacak_gun > 60 and bs.ticari_alacaklar > 0:
        alternatifler.append({
            "tur": "Faktoring",
            "aciklama": (
                f"Ticari alacaklarınız {bs.ticari_alacaklar:,.0f} TL ve "
                f"tahsil süreniz {alacak_gun:.0f} gün. "
                "Faktoring ile alacaklarınızı beklemeden nakde çevirebilirsiniz. "
                "Banka kredisine alternatif veya tamamlayıcı bir finansman yöntemidir."
            ),
        })

    # 5. Sat-geri-kirala — duran varlık yüksek ve nakit sıkışıksa
    if duran_oran > 0.4 and cari_oran < 1.2:
        alternatifler.append({
            "tur": "Sat-Geri-Kirala (Sale & Leaseback)",
            "aciklama": (
                f"Maddi duran varlıklarınız {bs.maddi_duran_varliklar:,.0f} TL. "
                "Sahip olduğunuz gayrimenkul veya ekipmanı satıp geri kiralayarak "
                "önemli miktarda nakit açığa çıkarabilirsiniz. "
                "Varlığı kullanmaya devam ederken likiditinizi artırırsınız."
            ),
        })

    # 6. KGF — teminat yetersizse veya skor 55-70 arasındaysa
    maddi_duran_oran = bs.maddi_duran_varliklar / bs.toplam_aktif if bs.toplam_aktif else 0
    if 55 <= skor <= 70 or maddi_duran_oran < 0.15:
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


def _potansiyel_raporu(skor_sonuc: "SkorSonuc", bs) -> str:
    import anthropic, os
    from scorer import RASYO_TANIMLARI, _bant_bul

    kotu_zayif = [
        r for r in skor_sonuc.rasyolar
        if r.bant in ("kotu", "zayif")
    ]
    if not kotu_zayif:
        return ""

    kayip_puan  = sum(r.max_puan - r.puan for r in kotu_zayif)
    mevcut_skor = skor_sonuc.skor
    maksimum_skor = min(100, mevcut_skor + kayip_puan)

    # ── Her rasyo için bir sonraki bant eşiğini hesapla ──
    rasyo_meta = {t["id"]: t for t in RASYO_TANIMLARI}
    sektor = getattr(bs, "sektor", "ticaret") or "ticaret"

    rasyo_detay = ""
    for r in kotu_zayif:
        kayip = r.max_puan - r.puan
        rid   = getattr(r, "id", "")
        t     = rasyo_meta.get(rid)
        esik_notu = ""
        if t:
            esikler_tuple = t["esikler"].get(sektor) or t["esikler"].get("ticaret")
            if esikler_tuple:
                m, i, z = esikler_tuple
                if t["yon"] == "yuksek_iyi":
                    sonraki = z if r.bant == "kotu" else i
                else:  # dusuk_iyi
                    sonraki = z if r.bant == "kotu" else i
                esik_notu = f", bir sonraki bant eşiği: {sonraki:.2f}"
        rasyo_detay += (
            f"- {r.ad}: {r.deger_fmt} "
            f"(bant: {r.bant}, kayıp puan: {kayip}/{r.max_puan}{esik_notu})\n"
        )

    # ── Hesaplanmış likidite değerleri ──
    likit_varliklar  = bs.donen_varliklar - bs.stoklar
    likidite_acigi   = bs.kv_borclar - bs.donen_varliklar
    cari_ek_gereken  = max(0, bs.kv_borclar * 1.0 - bs.donen_varliklar)
    asit_ek_gereken  = max(0, bs.kv_borclar * 0.7 - likit_varliklar)

    hesaplanmis = (
        f"- Likidite Açığı (KV Borçlar − Dönen Varlıklar): "
        f"{likidite_acigi:,.0f} TL\n"
        if likidite_acigi > 0 else
        f"- Dönen Varlıklar KV Borçlardan {abs(likidite_acigi):,.0f} TL fazla (pozitif likidite)\n"
    )
    if cari_ek_gereken > 0:
        hesaplanmis += (
            f"- Cari oran 1.0x için gereken ek dönen varlık: {cari_ek_gereken:,.0f} TL\n"
        )
    if asit_ek_gereken > 0:
        hesaplanmis += (
            f"- Asit-test 0.7x için gereken ek likit varlık (stok hariç): {asit_ek_gereken:,.0f} TL\n"
        )

    prompt = f"""Sen deneyimli bir Türk bankacı ve finansal danışmansın. Aşağıdaki firmaya özel verilerle, firmanın finansal skorunu iyileştirmesi için detaylı bir yol haritası yaz. Türkçe yaz.

FİRMA VERİLERİ:
- Mevcut Skor: {mevcut_skor}/100
- Senaryo ile Ulaşılabilir: {min(100, mevcut_skor + 9)} (bilanço aksiyonlarıyla)
- Operasyonel İyileştirmeyle Maksimum: {maksimum_skor}/100
- KV Borçlar: {bs.kv_borclar:,.0f} TL
- Dönen Varlıklar: {bs.donen_varliklar:,.0f} TL
- Likit Varlıklar (stok hariç): {likit_varliklar:,.0f} TL
- Net Satışlar: {bs.net_satislar:,.0f} TL
- Ticari Alacaklar: {bs.ticari_alacaklar:,.0f} TL
- Stoklar: {bs.stoklar:,.0f} TL
- Satışların Maliyeti: {bs.satislarin_maliyeti:,.0f} TL
- Toplam Aktif: {bs.toplam_aktif:,.0f} TL

Hesaplanmış değerler (bu değerleri kullan, kendin hesaplama):
{hesaplanmis}
İYİLEŞTİRİLMESİ GEREKEN RASYOLAR (her birinde "bir sonraki bant eşiği" verilmiştir):
{rasyo_detay}
YAZIM KURALLARI:
- Her rasyo için ayrı bir başlık aç
- Başlıkta rasyonun adını, mevcut değerini ve kazanılacak puanı yaz
- Her rasyonun altında:
  1. Neden bu kadar kötü olduğunu somut rakamlarla açıkla — likidite açığı ve ek gereken varlık rakamlarını "Hesaplanmış değerler" bölümünden al, kendin hesaplama yapma
  2. Hedef olarak "bir sonraki bant eşiği"ni kullan — mükemmel bandı değil. Gerçekçi olmayan büyük hedefler yazma
  3. Buna ulaşmak için 3-4 somut, uygulanabilir adım ver
  4. Bu adımların ne kadar sürede sonuç vereceğini belirt
- Bankacı gözüyle yaz — teknik ama anlaşılır
- Şirketiniz diye hitap et
- Rakamları TL formatında yaz
- Yazının sonuna imza, "Saygılarımla", "Başarılar dilerim", "Danışmanınız" gibi ifadeler EKLEME
- Sadece yol haritası içeriğini yaz, kapanış cümlesi yazma
- ÖNEMLİ — DİL KURALLARI: BilancoSkor bir finansal analiz yazılımıdır, resmi kredi derecelendirme kuruluşu değildir. Bu yüzden:
  * Kesin kredi kararı verir gibi yazma, "bu adımları uygularsanız skorunuz iyileşebilir" şeklinde yaz
  * "kredi kullanabilirsiniz" veya "kredi başvurusu değerlendirilebilir" yerine "finansal göstergeler olumlu profil oluştuğuna işaret etmektedir" kullan
  * "kredi verilmez" yerine "kredi onayı zorlaşabilir" yaz
  * Her zaman tahmini/algoritmik analiz olduğunu hissettir"""

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    try:
        message = _claude_call(client, "claude-sonnet-4-20250514", 6000, [{"role": "user", "content": prompt}])
        return message.content[0].text.strip()
    except Exception as e:
        print(f'[potansiyel_raporu ERROR] {e}')
    return ""

def _nakit_akis_analiz(bs, skor_sonuc: "SkorSonuc") -> NakitAkisAnaliz:
    """
    Aylık FAVÖK, mevcut borç servisi ve yeni kredi taksiti karşılaştırması.
    """
    # Aylık FAVÖK — negatif olsa da olduğu gibi göster
    aylik_favok = bs.favok / 12

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
    if aylik_favok <= 0:
        kapasite = "kritik"
        yorum = "FAVÖK negatif — borç servisi karşılanamıyor."
        mevcut_oran = 0
        toplam_oran = 0
    elif aylik_favok > 0:
        mevcut_oran = mevcut_taksit / aylik_favok
        toplam_oran = toplam_taksit / aylik_favok
        kullanim_oran = mevcut_oran
        if kullanim_oran <= 0.40:
            kapasite = "rahat"
            yorum = (
                f"Aylık işletme kârınızın ({aylik_favok:,.0f} TL) yalnızca "
                f"{mevcut_oran*100:.0f}%'i borç servisine gidecek. "
                f"Kredi geri ödemesinde rahat bir kapasiteniz var."
            )
        elif kullanim_oran <= 0.60:
            kapasite = "makul"
            yorum = (
                f"Aylık işletme kârınızın {mevcut_oran*100:.0f}%'i borç servisine gidecek. "
                f"Yönetilebilir bir yük ancak beklenmedik gider durumunda dikkatli olunmalı."
            )
        elif kullanim_oran <= 0.80:
            kapasite = "riskli"
            yorum = (
                f"Aylık işletme kârınızın {mevcut_oran*100:.0f}%'i borç servisine gidecek. "
                f"Bu yüksek bir oran. Satışlarda küçük bir düşüş ödeme güçlüğü yaratabilir."
            )
        else:
            kapasite = "kritik"
            yorum = (
                f"Aylık işletme kârınızın {mevcut_oran*100:.0f}%'i borç servisine gidecek — "
                f"kritik seviye. Bu krediyi geri ödemek çok güçtür. "
                f"Daha düşük limit veya FAVÖK artışı bu göstergeyi olumlu etkileyebilir."
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




def _senaryo_hesapla(bs, sektor: str, aciklama: str, degisiklikler: dict, baz_skor: int = 0) -> SenaryoSonuc:
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
        skor_delta=yeni_sonuc.skor - baz_skor,
        yeni_harf=yeni_sonuc.harf,
        yeni_limit_aciklama=yeni_sonuc.kredi_limit_aciklama,
        etkilenen_rasyolar=[],
    )


def _senaryolari_hesapla(bs, skor_sonuc: "SkorSonuc", sektor: str) -> list[SenaryoSonuc]:
    """
    Tamamen dinamik senaryo motoru.

    1. Zayıf/kötü rasyoları tespit et.
    2. Her rasyo için o rasyoyu bir sonraki banda taşıyacak minimum BS değişikliğini hesapla.
    3. BS2'ye uygula, raw_delta (toplam_puan farkı) hesapla — sadece > 0 olanları al.
    4. Sona kombine senaryo ekle.
    """
    from scorer import (skorla, RASYO_TANIMLARI, _bant_bul,
                        _hesapla_degerler, _harf_notu)
    import dataclasses

    baz_puan = skor_sonuc.toplam_puan
    baz_skor = skor_sonuc.skor
    degerler  = _hesapla_degerler(bs)

    rasyo_meta = {t["id"]: t for t in RASYO_TANIMLARI}

    # Zayıf/kötü rasyoların id → RasyoSonuc objesi
    zayif = {
        getattr(r, "id", ""): r
        for r in skor_sonuc.rasyolar
        if r.bant in ("kotu", "zayif")
    }

    def sonraki_esik(rid: str, val: float) -> float | None:
        """Bir sonraki bandın alt eşiğini döndür (None = zaten mükemmel)."""
        t = rasyo_meta.get(rid)
        if not t:
            return None
        m, i, z = t["esikler"].get(sektor, t["esikler"]["ticaret"])
        band = _bant_bul(val, (m, i, z), t["yon"])
        if t["yon"] == "yuksek_iyi":
            return {" kotu": z, "kotu": z, "zayif": i, "iyi": m}.get(band)
        else:
            return {"kotu": z, "zayif": i, "iyi": m}.get(band)

    def raw_delta(bs2) -> int:
        yeni = skorla(bs2, sektor=sektor)
        return round(yeni.toplam_puan) - round(baz_puan)

    def yeni_skor_harf(delta: int) -> tuple[int, str, str]:
        """Teorik (cap'siz) yeni skor, harf ve kredi limit açıklaması."""
        ys = min(100, baz_skor + delta)
        h, _, limit, *_ = _harf_notu(ys)
        return ys, h, limit

    def uygula(bs2, delta_dict: dict):
        for alan, deger in delta_dict.items():
            if hasattr(bs2, alan):
                setattr(bs2, alan, max(0, getattr(bs2, alan) + deger))

    # ── Senaryo üreticileri ──────────────────────────────────────────────

    uretilen: list[tuple[str, dict, list[str]]] = []
    # (aciklama, delta_dict, etkilenen_rasyolar)

    # 1. cari_oran — nakit enjeksiyonu (sermaye artırımı)
    if "cari_oran" in zayif:
        esik = sonraki_esik("cari_oran", degerler["cari_oran"])
        if esik is not None:
            # donen / kv_new >= esik → tek taraflı: donen arttır
            donen_needed = esik * bs.kv_borclar
            delta = donen_needed - bs.donen_varliklar
            if delta > 0:
                uretilen.append((
                    f"Nakit enjeksiyonu ile cari oran iyileştir — {delta:,.0f} TL sermaye artır",
                    {"odenmis_sermaye": delta, "banka": delta},
                    ["cari_oran", "asit_test", "nakit_oran",
                     "borc_ozkaynak", "finansal_kaldırac"],
                ))

    # 2. asit_test — stok eritme
    if "asit_test" in zayif:
        esik = sonraki_esik("asit_test", degerler["asit_test"])
        if esik is not None:
            # (donen - stok + delta) / kv >= esik → delta = esik*kv - (donen-stok)
            liquid_needed = esik * bs.kv_borclar
            liquid_cur    = bs.donen_varliklar - bs.stoklar
            delta = liquid_needed - liquid_cur
            delta = min(delta, bs.stoklar)   # stoklardan fazlasını eremeyiz
            if delta > 0:
                uretilen.append((
                    f"Stoklardan {delta:,.0f} TL nakde çevir — asit-test iyileştir",
                    {"stoklar": -delta, "banka": delta},
                    ["asit_test", "cari_oran", "stok_devir", "nakit_donusum_suresi"],
                ))

    # 3. nakit_oran — alacak tahsili
    if "nakit_oran" in zayif:
        esik = sonraki_esik("nakit_oran", degerler["nakit_oran"])
        if esik is not None:
            nakit_needed = esik * bs.kv_borclar
            delta = nakit_needed - bs.nakit_ve_benzerleri
            delta = min(delta, bs.ticari_alacaklar)
            if delta > 0:
                uretilen.append((
                    f"Alacaklardan {delta:,.0f} TL tahsil et — nakit oran iyileştir",
                    {"ticari_alacaklar": -delta, "banka": delta},
                    ["nakit_oran", "asit_test", "cari_oran",
                     "alacak_tahsil_suresi", "nakit_donusum_suresi"],
                ))

    # 4. kv_borc_orani — KV banka kredisini UV'ye çevir
    if "kv_borc_orani" in zayif:
        esik = sonraki_esik("kv_borc_orani", degerler["kv_borc_orani"])
        if esik is not None and bs.toplam_borclar > 0:
            # kv_new / toplam <= esik → kv_new = esik * toplam
            kv_new = esik * bs.toplam_borclar
            delta  = bs.kv_borclar - kv_new
            delta  = min(delta, bs.banka_kredileri_kv)
            if delta > 0:
                uretilen.append((
                    f"KV banka kredisinden {delta:,.0f} TL UV'ye çevir — vade yapısı iyileştir",
                    {"banka_kredileri_kv": -delta, "banka_kredileri_uv": delta},
                    ["kv_borc_orani", "cari_oran", "asit_test"],
                ))

    # 5. ortaklar_cari_orani — ortaklar borcu → sermaye
    if "ortaklar_cari_orani" in zayif and bs.ortaklara_borclar > 0:
        esik = sonraki_esik("ortaklar_cari_orani", degerler["ortaklar_cari_orani"])
        if esik is not None and bs.toplam_pasif > 0:
            # (ortaklar - delta) / pasif <= esik
            delta = bs.ortaklara_borclar - esik * bs.toplam_pasif
            delta = min(delta, bs.ortaklara_borclar)
            if delta > 0:
                uretilen.append((
                    f"Ortaklara borçtan {delta:,.0f} TL sermayeye dönüştür",
                    {"ortaklara_borclar": -delta, "odenmis_sermaye": delta},
                    ["ortaklar_cari_orani", "borc_ozkaynak",
                     "finansal_kaldırac", "cari_oran"],
                ))

    # 6. borc_ozkaynak — sermaye artırımı (cari_oran zaten hedeflenmiyorsa ayrı senaryo)
    if "borc_ozkaynak" in zayif and "cari_oran" not in zayif:
        esik = sonraki_esik("borc_ozkaynak", degerler["borc_ozkaynak"])
        if esik is not None and esik > 0:
            # borclar / oz_new <= esik → oz_new = borclar / esik
            oz_needed = bs.toplam_borclar / esik
            delta = oz_needed - bs.ozkaynaklar
            if delta > 0:
                uretilen.append((
                    f"Sermaye artırımı {delta:,.0f} TL — borç/özkaynak iyileştir",
                    {"odenmis_sermaye": delta, "banka": delta},
                    ["borc_ozkaynak", "finansal_kaldırac",
                     "cari_oran", "nakit_oran"],
                ))

    # 7. alacak_tahsil_suresi — alacak tahsili (nakit_oran zaten hedeflenmiyorsa)
    if "alacak_tahsil_suresi" in zayif and "nakit_oran" not in zayif and bs.net_satislar > 0:
        esik = sonraki_esik("alacak_tahsil_suresi", degerler["alacak_tahsil_suresi"])
        if esik is not None:
            alacak_new = esik * bs.net_satislar / 365
            delta = bs.ticari_alacaklar - alacak_new
            delta = min(delta, bs.ticari_alacaklar * 0.5)
            if delta > 0:
                uretilen.append((
                    f"Vadeli alacaklardan {delta:,.0f} TL tahsil et — tahsil süresi kısalt",
                    {"ticari_alacaklar": -delta, "banka": delta},
                    ["alacak_tahsil_suresi", "nakit_oran", "asit_test"],
                ))

    # ── Her senaryo için raw_delta hesapla, sadece > 0 olanları tut ────
    sonuclar: list[SenaryoSonuc] = []
    aktif_delta_dicts: list[dict] = []   # kombine senaryo için

    for aciklama, delta_dict, etkilenen in uretilen:
        try:
            bs2 = dataclasses.replace(bs)
            uygula(bs2, delta_dict)
            rd = raw_delta(bs2)
            if rd > 0:
                ys, harf, limit = yeni_skor_harf(rd)
                sonuclar.append(SenaryoSonuc(
                    aciklama=aciklama,
                    degisiklik=delta_dict,
                    yeni_skor=ys,
                    skor_delta=rd,
                    yeni_harf=harf,
                    yeni_limit_aciklama=limit,
                    etkilenen_rasyolar=etkilenen,
                ))
                aktif_delta_dicts.append(delta_dict)
        except Exception as e:
            logger.warning(f"Senaryo hesaplama hatası ({aciklama[:40]}): {e}")

    # ── Kombine senaryo ──────────────────────────────────────────────────
    if len(aktif_delta_dicts) >= 2:
        try:
            combo_dict: dict[str, float] = {}
            for d in aktif_delta_dicts:
                for alan, deger in d.items():
                    combo_dict[alan] = combo_dict.get(alan, 0.0) + deger

            bs_combo = dataclasses.replace(bs)
            uygula(bs_combo, combo_dict)
            rd_combo = raw_delta(bs_combo)
            if rd_combo > 0:
                ys, harf, limit = yeni_skor_harf(rd_combo)
                combo_etkilenen = sorted({r for s in sonuclar for r in s.etkilenen_rasyolar})
                sonuclar.append(SenaryoSonuc(
                    aciklama="Tüm aksiyonları birlikte uygula",
                    degisiklik=combo_dict,
                    yeni_skor=ys,
                    skor_delta=rd_combo,
                    yeni_harf=harf,
                    yeni_limit_aciklama=limit,
                    etkilenen_rasyolar=combo_etkilenen,
                ))
        except Exception as e:
            logger.warning(f"Kombine senaryo hatası: {e}")

    # Kombine en sonda, tekli delta'ya göre azalan
    tekli  = [s for s in sonuclar if "birlikte" not in s.aciklama]
    kombine = [s for s in sonuclar if "birlikte"     in s.aciklama]
    tekli.sort(key=lambda s: s.skor_delta, reverse=True)
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
        "Rapor, kullanıcıya ait bir analiz çıktısıdır; üçüncü taraflarla paylaşımı kullanıcının sorumluluğundadır.",
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
# 8. ALT HESAP ANALİZİ
# ─────────────────────────────────────────────

_ALT_HESAP_ADLARI = {
    "100": "Kasa",
    "102": "Bankalar",
    "120": "Alıcılar (Ticari Alacaklar)",
    "121": "Alacak Senetleri",
    "126": "Verilen Depozito ve Teminatlar",
    "150": "İlk Madde ve Malzeme",
    "151": "Yarı Mamul Stoklar",
    "152": "Mamuller",
    "153": "Ticari Mallar",
    "159": "Verilen Sipariş Avansları",
    "250": "Arazi ve Arsalar",
    "251": "Yeraltı ve Yerüstü Düzenleri",
    "252": "Binalar",
    "253": "Tesis, Makine ve Cihazlar",
    "254": "Taşıtlar",
    "255": "Demirbaşlar",
    "260": "Haklar",
    "264": "Özel Maliyetler",
    "268": "Birikmiş Amortismanlar",
    "300": "Banka Kredileri (KV)",
    "301": "Finansal Kiralama Yükümlülükleri (KV)",
    "320": "Satıcılar",
    "321": "Borç Senetleri",
    "329": "Diğer Ticari Borçlar (KV)",
    "331": "Ortaklara Borçlar",
    "340": "Alınan Sipariş Avansları",
    "360": "Ödenecek Vergi ve Fonlar",
    "400": "Banka Kredileri (UV)",
    "401": "Finansal Kiralama Yükümlülükleri (UV)",
}

# Fix liste: her zaman dahil, kalem sayısına bakılmaksızın
_FIX_LISTE = frozenset([
    "120", "150", "253", "254",
    "300", "301", "320", "321",
    "400", "401",
])

# Dinamik eklemeden kesinlikle hariç tutulacak hesaplar
_DINAMIK_HARIC = frozenset(["257", "268"])


def _hesap_tipi(parent: str) -> str:
    """Hesap koduna göre tip döndür: aktif | pasif | duran_varlik"""
    if parent in ("253", "254", "255", "264"):
        return "duran_varlik"
    if parent.startswith("1"):
        return "aktif"
    if parent.startswith("2"):
        return "duran_varlik"
    if parent.startswith("3") or parent.startswith("4"):
        return "pasif"
    return "aktif"


def _alt_hesap_analizi(bs) -> list:
    """
    Hibrit hesap seçimiyle alt hesapları her biri için ayrı Claude çağrısıyla analiz eder.

    Bakiye/hacim kuralları:
      - Pasif (300/301/320/321/329/340/400/401): bakiye = alacak bakiyesi, hacim = alacak_top
      - Aktif hacimli (120/150/159): bakiye = borç bakiyesi, hacim = borc_top
      - Aktif hacimsiz (180/280/253/254/255/264): bakiye = borç bakiyesi, hacim gönderilmez
      - Bakiyesi sıfır olan hesaplar atlanır
    """
    import anthropic, os, json as _json

    _AKTIF_HACIMLI  = frozenset(["120", "150", "159"])
    _AKTIF_HACIMSIZ = frozenset(["180", "280", "253", "254", "255", "264"])
    _PASIF_HESAPLAR = frozenset(["300", "301", "320", "321", "329", "340", "400", "401"])

    _HESAP_DIREKTIF: dict[str, str] = {
        "120": (
            "Bu AKTİF hesaptır. Bakiye = müşterilerin şirkete olan borcu, tahsil edilmemiş alacak.\n"
            "Hacim = o müşteriyle yapılan satış tutarı — 'borç hacmi' deme, 'satış hacmi' veya 'ciro' de.\n"
            "Büyük müşterileri ismiyle, satış hacimleriyle ve tahsil edilmemiş bakiyeleriyle say.\n"
            "Bu müşteriler ödeme yapamazsa nakit akışına etkisini değerlendir.\n"
            "Bakiyesi sıfır olan müşteriler tamamen tahsil edilmiş demektir.\n"
            "Konsantrasyon riski ve tahsilat riski açısından bankacılık perspektifinden yorumla."
        ),
        "150": (
            "Bu AKTİF STOK hesabıdır. Bakiye = eldeki hammadde stok değeri.\n"
            "Borç hareketi stok alımı, alacak hareketi stok kullanımıdır — bunlar ciro değil.\n"
            "Bankacılık perspektifi: stok değeri gerçekçi mi, hızlı nakde dönebilir mi, stok devir hızı nasıl.\n"
            "Stok çeşitlendirmesi veya tek madde bağımlılığı bankacılığı ilgilendirmez, bunu kesinlikle yazma.\n"
            "Teminat değeri ve likidite açısından değerlendir."
        ),
        "159": (
            "Bu AKTİF hesaptır. Bakiye = tedarikçilere verilmiş ama henüz mal/hizmet alınmamış avanslar.\n"
            "Şirket ALICI konumunda, tedarikçiye avans ödemiş. Müşteri kelimesini kullanma, bunlar tedarikçi.\n"
            "Büyük avansları ismiyle say, avansın karşılığı geldi mi gelmedi mi perspektifinden değerlendir.\n"
            "Nakit bağlama riski ve tedarikçi güvenilirliği açısından yorumla."
        ),
        "180": (
            "Bu AKTİF hesaptır. Bakiye = ileriki aylara ait peşin ödenmiş giderler (sigorta, abonelik vb.).\n"
            "Borç veya alacak değil, peşin gider. Sigorta giderlerinde konsantrasyon riski olmaz, bunu yazma.\n"
            "Büyük kalemleri ismiyle say, peşin ödeme yapısını ve gider planlaması açısından değerlendir."
        ),
        "280": (
            "Bu AKTİF hesaptır. Bakiye = gelecek yıllara ait peşin ödenmiş giderler.\n"
            "Büyük kalemleri ismiyle say, uzun vadeli peşin ödeme yapısını yorumla."
        ),
        "253": (
            "Bu DURAN VARLIK hesabıdır. Bakiye = makinelerin net defter değeri.\n"
            "En yüksek değerli makineleri ismiyle ve değeriyle say. Kalem adlarını mizanda yazan ismiyle kullan, kendi yorumunla isim türetme veya değiştirme.\n"
            "Yaş dağılımı, teminat kapasitesi ve teknolojik eskime riski açısından "
            "bankacılık perspektifinden yorumla."
        ),
        "254": (
            "Bu DURAN VARLIK hesabıdır. Bakiye = araçların net defter değeri.\n"
            "En değerli araçları ismiyle say. Kalem adlarını mizanda yazan ismiyle kullan, kendi yorumunla isim türetme veya değiştirme.\n"
            "Filo yapısı, yaş dağılımı, teminat kapasitesi açısından bankacılık perspektifinden yorumla."
        ),
        "255": (
            "Bu DURAN VARLIK hesabıdır. Bakiye = demirbaşların net defter değeri.\n"
            "Demirbaşlar bankacılıkta düşük teminat değeri taşır, bunu belirt.\n"
            "Kalem adlarını mizanda yazan ismiyle kullan, kendi yorumunla isim türetme veya değiştirme.\n"
            "Yaş dağılımı ve değer yapısını değerlendir."
        ),
        "264": (
            "Bu DURAN VARLIK hesabıdır. Bakiye = özelleştirilmiş yatırım maliyetleri.\n"
            "Büyük kalemleri ismiyle say. Kalem adlarını mizanda yazan ismiyle kullan, kendi yorumunla isim türetme veya değiştirme.\n"
            "Geri kazanılabilirlik ve teminat değeri açısından yorumla."
        ),
        "300": (
            "Bu PASİF hesaptır. Bakiye = şirketin kısa vadeli banka borcu.\n"
            "Her bankaya olan borcu ve o bankadan çekilen hacmi ayrı ayrı yaz.\n"
            "Hangi bankaya ne kadar bağımlı, vade yapısı ve KV borç riski açısından yorumla."
        ),
        "301": (
            "Bu PASİF hesaptır. Bakiye = kısa vadeli finansal kiralama yükümlülüğü.\n"
            "Kiralama yapısını ve ödeme planını değerlendir."
        ),
        "320": (
            "Bu PASİF hesaptır. Bakiye = şirketin tedarikçilere olan borcu.\n"
            "Hacim = o tedarikçiden yapılan alım miktarı.\n"
            "Büyük tedarikçileri ismiyle say.\n"
            "Bağımlılık riski, alternatif tedarikçi, ödeme gecikirse operasyonel etki açısından yorumla."
        ),
        "321": (
            "Bu PASİF hesaptır. Bakiye = şirketin bankalara verdiği ödenmemiş çeklerin tutarı.\n"
            "Bu hesap tamamen TL cinsindendir, dövizli değildir — dövizli ifadesini kesinlikle kullanma.\n"
            "Hangi bankalara verilen çekler var, toplam yükümlülük ne kadar, banka bazında dağılım nasıl değerlendir.\n"
            "Bakiyesi sıfır ise bu hesabı analiz etme."
        ),
        "329": (
            "Bu PASİF hesaptır. Bakiye = şirketin ödeyeceği diğer ticari borçlar.\n"
            "Şirket bu kişilere BORÇLU.\n"
            "Büyük borçları ismiyle say, borç yapısını ve konsantrasyon riskini değerlendir."
        ),
        "340": (
            "Bu PASİF hesaptır. Bakiye = müşterilerden alınan ama henüz teslim edilmemiş "
            "iş/mal karşılığı avanslar.\n"
            "Şirket bu müşterilere mal/hizmet teslim etmek ZORUNDA. Bu bakiye nakde dönmez, taahhüt yüküdür.\n"
            "Büyük avansları ismiyle say, teslim taahhüdü riski açısından yorumla."
        ),
        "400": (
            "Bu PASİF hesaptır. Bakiye = şirketin uzun vadeli banka borcu.\n"
            "Her bankaya olan borcu değerlendir, UV borç yapısını yorumla."
        ),
        "401": (
            "Bu PASİF hesaptır. Bakiye = uzun vadeli finansal kiralama yükümlülüğü.\n"
            "Kiralama yapısını ve ödeme planını değerlendir."
        ),
    }

    alt_hesaplar = getattr(bs, "alt_hesaplar", {})
    if not alt_hesaplar:
        return []

    # ── 1. Hibrit hesap seçimi ───────────────────────────────────────────
    secilen: list[str] = []
    for parent, veri in alt_hesaplar.items():
        kalemler = veri.get("kalemler", []) if isinstance(veri, dict) else []
        if not kalemler:
            continue
        if parent in _FIX_LISTE:
            secilen.append(parent)
        elif parent not in _DINAMIK_HARIC:
            bakiye_toplam = abs(sum(k["bakiye"] for k in kalemler))
            if len(kalemler) > 20 and bakiye_toplam > 2_000_000:
                secilen.append(parent)

    if not secilen:
        return []

    # ── 2. Her hesap için meta ve blok hazırla ───────────────────────────
    hesap_meta: dict = {}

    for parent in secilen:
        try:
            veri     = alt_hesaplar[parent]
            kalemler = veri.get("kalemler", []) if isinstance(veri, dict) else []
            uyari    = veri.get("uyari", "")    if isinstance(veri, dict) else ""
            if not kalemler:
                continue

            ana_ad   = _ALT_HESAP_ADLARI.get(parent, f"Hesap {parent}")
            direktif = _HESAP_DIREKTIF.get(
                parent,
                f"Bu hesabı bankacılık perspektifinden analiz et. "
                f"Bakiye dağılımını ve konsantrasyon riskini değerlendir."
            )

            # ── Hesap grubuna göre bakiye & hacim & sıralama ──
            if parent in _AKTIF_HACIMLI:
                sirali        = sorted(kalemler, key=lambda k: k["bakiye"], reverse=True)
                toplam_bakiye = sum(k["bakiye"] for k in kalemler if k["bakiye"] > 0)
                toplam_hacim  = sum(k["borc_top"] for k in kalemler)
                hacim_satir   = f"Borç (ciro) hacmi: {toplam_hacim:,.0f} TL | "
                def _fmt_aktif_hacimli(k):
                    return (
                        f"  {k['kod']} — {k['ad'][:40] if k['ad'] else '(adsız)'}: "
                        f"bakiye {k['bakiye']:,.0f} TL | hacim {k['borc_top']:,.0f} TL"
                    )
                kalem_satirlari = "\n".join(_fmt_aktif_hacimli(k) for k in sirali[:10])

            elif parent in _AKTIF_HACIMSIZ:
                sirali        = sorted(kalemler, key=lambda k: k["bakiye"], reverse=True)
                toplam_bakiye = sum(k["bakiye"] for k in kalemler if k["bakiye"] > 0)
                toplam_hacim  = 0.0
                hacim_satir   = ""
                def _fmt_aktif_hacimsiz(k):
                    return (
                        f"  {k['kod']} — {k['ad'][:40] if k['ad'] else '(adsız)'}: "
                        f"bakiye {k['bakiye']:,.0f} TL"
                    )
                kalem_satirlari = "\n".join(_fmt_aktif_hacimsiz(k) for k in sirali[:10])

            elif parent in _PASIF_HESAPLAR:
                sirali        = sorted(kalemler, key=lambda k: abs(k["bakiye"]), reverse=True)
                toplam_bakiye = sum(abs(k["bakiye"]) for k in kalemler if k["bakiye"] < 0)
                toplam_hacim  = sum(k["alacak_top"] for k in kalemler)
                hacim_satir   = f"Alacak (ciro) hacmi: {toplam_hacim:,.0f} TL | "
                def _fmt_pasif(k):
                    return (
                        f"  {k['kod']} — {k['ad'][:40] if k['ad'] else '(adsız)'}: "
                        f"bakiye (şirketin borcu) {abs(k['bakiye']):,.0f} TL | "
                        f"hacim {k['alacak_top']:,.0f} TL"
                    )
                kalem_satirlari = "\n".join(_fmt_pasif(k) for k in sirali[:10])

            else:
                # Bilinmeyen hesap — hesap tipine göre genel kural
                tip = _hesap_tipi(parent)
                if tip == "pasif":
                    sirali        = sorted(kalemler, key=lambda k: abs(k["bakiye"]), reverse=True)
                    toplam_bakiye = sum(abs(k["bakiye"]) for k in kalemler if k["bakiye"] < 0)
                    toplam_hacim  = sum(k["alacak_top"] for k in kalemler)
                    hacim_satir   = f"Alacak hacmi: {toplam_hacim:,.0f} TL | "
                    def _fmt_pasif_gen(k):
                        return (
                            f"  {k['kod']} — {k['ad'][:40] if k['ad'] else '(adsız)'}: "
                            f"bakiye {abs(k['bakiye']):,.0f} TL"
                        )
                    kalem_satirlari = "\n".join(_fmt_pasif_gen(k) for k in sirali[:10])
                else:
                    sirali        = sorted(kalemler, key=lambda k: k["bakiye"], reverse=True)
                    toplam_bakiye = sum(k["bakiye"] for k in kalemler if k["bakiye"] > 0)
                    toplam_hacim  = 0.0
                    hacim_satir   = ""
                    def _fmt_aktif_gen(k):
                        return (
                            f"  {k['kod']} — {k['ad'][:40] if k['ad'] else '(adsız)'}: "
                            f"bakiye {k['bakiye']:,.0f} TL"
                        )
                    kalem_satirlari = "\n".join(_fmt_aktif_gen(k) for k in sirali[:10])

            # Bakiyesi sıfır olan hesabı atla
            if toplam_bakiye == 0:
                logger.info(f"Alt hesap {parent} atlandı: toplam bakiye sıfır")
                continue

            top3          = sum(abs(k["bakiye"]) for k in sirali[:3])
            konsantrasyon = top3 / toplam_bakiye * 100 if toplam_bakiye else 0

            blok = (
                f"Hesap {parent} — {ana_ad}\n"
                f"Toplam bakiye: {toplam_bakiye:,.0f} TL | "
                + hacim_satir
                + f"Alt kalem sayısı: {len(kalemler)} | "
                f"İlk 3 kalemin bakiye payı: %{konsantrasyon:.0f}\n"
                f"Büyükten küçüğe ilk 10 kalem:\n{kalem_satirlari}"
            )

            hesap_meta[parent] = {
                "ana_ad":   ana_ad,
                "uyari":    uyari,
                "blok":     blok,
                "direktif": direktif,
            }
        except Exception as e:
            logger.warning(f"Alt hesap blok hazırlama hatası ({parent}): {e}")

    if not hesap_meta:
        return []

    # ── 3. Her hesap için ayrı Claude çağrısı ───────────────────────────
    client    = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    analizler: dict[str, str] = {}

    for parent, meta in hesap_meta.items():
        prompt = f"""BilankoSkor finansal analiz yazılımı — alt hesap analiz modülü.

{meta['blok']}

---
HESAP TANIMI VE ANALİZ DİREKTİFİ:
{meta['direktif']}

---
Bankacı bakışıyla analiz yaz.
Gözlemsel dil kullan — "bu dağılım konsantrasyon riski oluşturabilir", "bu yapı bankacılık değerlendirmelerinde dikkat çekebilir" gibi.
"Yapmanızı öneririm" veya "tavsiye ederim" kullanma. "Şirketiniz" diye hitap et.

Tam olarak şu 3 başlık:
**Tespit:** Direktife göre kalem detaylarını ve bakiye/hacim dağılımını betimle. 2-3 cümle.
**Risk/Fırsat:** Bu yapının finansal profile olası etkisi. 2 cümle.
**Öneri:** Finansal profili güçlendirebilecek potansiyel aksiyonlar. 1-2 cümle.

SADECE JSON döndür. Markdown veya açıklama ekleme. Format:
{{"analiz": "<**Tespit:** ... **Risk/Fırsat:** ... **Öneri:** ...>"}}

Türkçe yaz."""

        try:
            response = _claude_call(
                client,
                "claude-haiku-4-5-20251001",
                700,
                [{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            data = _json.loads(raw)
            analizler[parent] = data.get("analiz", "Analiz üretilemedi.")
        except Exception as e:
            logger.warning(f"Alt hesap Claude çağrısı başarısız ({parent}): {e}")
            analizler[parent] = "Analiz üretilemedi."

    # ── 4. Sonuçları birleştir ───────────────────────────────────────────
    sonuclar = []
    for parent, meta in hesap_meta.items():
        sonuclar.append({
            "ana_hesap_kodu": parent,
            "ana_hesap_adi":  meta["ana_ad"],
            "analiz_metni":   analizler.get(parent, "Analiz üretilemedi."),
            "uyari_notu":     meta["uyari"],
        })

    return sonuclar


# ─────────────────────────────────────────────
# 9. DISCLAIMER
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
# 10. ANA FONKSİYON
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

    # Negatif delta olanları çıkar; sıfır delta olanlar (yapısal iyileştirme) dahil edilir
    senaryolar = [s for s in senaryolar if s.skor_delta >= 0]

    from question_bank import sorulari_uret
    banka_sorulari = sorulari_uret(bs, skor_sonuc)

    return TamRapor(
        firma_adi=firma_adi,
        sektor=sektor,
        yonetici_ozeti=_yonetici_ozeti(skor_sonuc, bs),
        potansiyel_raporu=_potansiyel_raporu(skor_sonuc, bs),
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
        skor_iyilestirme=_potansiyel_raporu(skor_sonuc, bs),
        alt_hesap_analizi=_alt_hesap_analizi(bs),
        disclaimer=DISCLAIMER,
    )
