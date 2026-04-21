"""
FinSkor — Question Bank v2
Sonnet bazlı dinamik banka sorusu üretimi — 3 parçalı çağrı.
"""

from __future__ import annotations
import os
import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_JSON_FORMAT = (
    '[{"kategori": "Bilanço Kalitesi | Kârlılık | Borç Ödeme Kapasitesi | Teminat | Operasyonel", '
    '"soru": "...", "bankacinin_amaci": "...", "hazir_cevap": "...", "oncelik": 1}]\n'
    "oncelik: 1=kritik, 2=önemli, 3=bilgi"
)


@dataclass
class BankaSorusu:
    kategori: str
    soru: str
    bankacinin_amaci: str
    hazir_cevap: str
    skor_etkisi: str
    oncelik: int
    tetikleyen: str


def sorulari_uret(
    bs,
    skor_sonuc,
    sektor: str = "ticaret",
    alt_hesap_analizleri: list | None = None,
    analizler: list | None = None,
) -> list[BankaSorusu]:
    try:
        return _uret_sonnet(bs, skor_sonuc, sektor, alt_hesap_analizleri or [], analizler or [])
    except Exception as e:
        logger.warning(f"Banka soruları üretilemedi: {e}")
        return []


# ── Yardımcı: JSON parse ────────────────────────────────────────────────────

def _parse_json(raw: str) -> list[dict]:
    raw = raw.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def _json_to_sorular(data: list[dict]) -> list[BankaSorusu]:
    return [
        BankaSorusu(
            kategori=item.get("kategori", "Genel"),
            soru=item.get("soru", ""),
            bankacinin_amaci=item.get("bankacinin_amaci", ""),
            hazir_cevap=item.get("hazir_cevap", ""),
            skor_etkisi=item.get("skor_etkisi", ""),
            oncelik=int(item.get("oncelik", 2)),
            tetikleyen="sonnet",
        )
        for item in data
    ]


def _cagri(client, prompt: str, etiket: str) -> list[BankaSorusu]:
    """Tek Sonnet çağrısı — 3 retry, hata durumunda boş liste."""
    for deneme in range(3):
        try:
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=8000,
                messages=[{"role": "user", "content": prompt}],
            )
            data = _parse_json(msg.content[0].text)
            sorular = _json_to_sorular(data)
            logger.info(f"[{etiket}] {len(sorular)} soru üretildi")
            return sorular
        except json.JSONDecodeError as e:
            logger.warning(f"[{etiket}] JSON parse hatası (deneme {deneme+1}/3): {e}")
        except Exception as e:
            logger.warning(f"[{etiket}] Hata (deneme {deneme+1}/3): {type(e).__name__}: {e}")
    logger.error(f"[{etiket}] 3 denemede üretilemedi")
    return []


# ── Ana fonksiyon ────────────────────────────────────────────────────────────

def _uret_sonnet(bs, skor_sonuc, sektor: str, alt_hesap_analizleri: list, analizler: list) -> list[BankaSorusu]:
    import anthropic
    from analyzer import NACE_BOLUM_ORT, nace_to_bolum

    bolum = nace_to_bolum(sektor)
    sekt_ort = NACE_BOLUM_ORT.get(bolum, NACE_BOLUM_ORT.get("G", {}))
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    toplam_aktif = bs.toplam_aktif or 1
    ortaklardan_alacak = getattr(bs, "ortaklardan_alacaklar", 0) or getattr(bs, "diger_alacaklar_kv", 0)

    # ── Ortak bağlam blokları ────────────────────────────────────────────
    favok_satir = (
        f"FAVÖK: {bs.favok:,.0f} TL  |  FAVÖK Marjı: %{bs.favok/bs.net_satislar*100:.1f}\n"
        if bs.net_satislar else f"FAVÖK: {bs.favok:,.0f} TL\n"
    )
    firma_profil = (
        f"Skor: {skor_sonuc.skor}/100 ({skor_sonuc.harf} — {skor_sonuc.kredi_band})\n"
        f"Sektör: {sektor} (NACE bölüm: {bolum})\n"
        f"Net Satışlar: {bs.net_satislar:,.0f} TL\n"
        + favok_satir +
        f"Net Kâr: {bs.net_kar:,.0f} TL\n"
        f"Toplam Aktif: {bs.toplam_aktif:,.0f} TL\n"
        f"Özkaynaklar: {bs.ozkaynaklar:,.0f} TL\n"
    )

    analiz_by_id = {a.rasyo_id: a for a in analizler} if analizler else {}

    def rasyo_satir(r) -> str:
        rid = getattr(r, "id", "")
        ort = sekt_ort.get(rid)
        ort_str = f"  |  sektör ort: {ort:.2f}" if ort else ""
        analiz = analiz_by_id.get(rid)
        kars = f"  |  {analiz.karsilastirma_metin}" if analiz else ""
        return f"  - {r.ad}: {r.deger_fmt} [{r.bant.upper()}] (puan: {r.puan}/{r.max_puan}){ort_str}{kars}"

    kotu_zayif = [r for r in skor_sonuc.rasyolar if r.bant in ("kotu", "zayif")]
    kotu_zayif_satirlar = "\n".join(rasyo_satir(r) for r in kotu_zayif) if kotu_zayif else "Yok."

    bilanco_ozeti = (
        f"Kasa (100): {bs.kasa:,.0f} TL (%{bs.kasa/toplam_aktif*100:.1f} aktif)\n"
        f"Banka (102): {bs.banka:,.0f} TL (%{bs.banka/toplam_aktif*100:.1f} aktif)\n"
        f"Toplam Nakit: {bs.nakit_ve_benzerleri:,.0f} TL\n"
        f"Ticari Alacaklar: {bs.ticari_alacaklar:,.0f} TL (%{bs.ticari_alacaklar/toplam_aktif*100:.1f} aktif)\n"
        f"Stoklar: {bs.stoklar:,.0f} TL (%{bs.stoklar/toplam_aktif*100:.1f} aktif)\n"
        f"KV Borçlar: {bs.kv_borclar:,.0f} TL\n"
        f"  - KV Banka Kredileri: {bs.banka_kredileri_kv:,.0f} TL\n"
        f"  - Ticari Borçlar: {bs.ticari_borclar_kv:,.0f} TL\n"
        f"  - Ortaklara Borçlar: {bs.ortaklara_borclar:,.0f} TL\n"
        f"UV Borçlar: {bs.uv_borclar:,.0f} TL\n"
        f"Ortaklardan Alacaklar (131): {ortaklardan_alacak:,.0f} TL\n"
        f"Finansman Giderleri: {bs.finansman_giderleri:,.0f} TL\n"
        f"Geçmiş Yıl Kâr/Zararı: {bs.gecmis_yil_karlari:,.0f} TL\n"
    )

    # Alt hesap analizlerini koda göre indexle
    alt_by_kod: dict[str, str] = {}
    for h in alt_hesap_analizleri:
        if isinstance(h, dict):
            kod = h.get("ana_hesap_kodu", "")
            analiz_m = h.get("analiz_metni", "")
            uyari = h.get("uyari_notu", "")
            adi = h.get("ana_hesap_adi", "")
            if analiz_m and analiz_m.strip() != "Analiz üretilemedi":
                metin = f"[{kod} — {adi}]\n{analiz_m[:500]}"
                if uyari:
                    metin += f"\nUYARI: {uyari}"
                alt_by_kod[kod] = metin

    _CAGRI1_HESAPLAR = {"120", "131", "159", "300", "320", "321", "340"}
    alt_cagri1 = "\n\n".join(v for k, v in alt_by_kod.items() if k in _CAGRI1_HESAPLAR) or "Mevcut değil."
    alt_cagri3 = "\n\n".join(v for k, v in alt_by_kod.items() if k not in _CAGRI1_HESAPLAR) or "Mevcut değil."

    # ── ÇAĞRI 1: Kritik rasyolar ve zorunlu kalemler ─────────────────────
    prompt1 = f"""Sen deneyimli bir Türk kurumsal bankacısın. Bu firmada kritik olan finansal sorunlar için banka görüşme soruları üret. Sadece JSON döndür.

Odak noktaları — hepsini kapsayacak sorular üret:
- Kötü/zayıf bandındaki rasyolar: rakamları ve sektör ortalamalarını kullan
- Kasa (100): Bakiye fiktif mi? Bankacı bunu sorgular — tatmin olmazsa bilanço kalitesi düşer
- Stoklar: Gerçek piyasa değeri, eskimiş/yavaş dönen var mı, teminat kabul edilebilirliği
- Ticari alacaklar: Tahsil edilebilirlik, gecikmiş/şüpheli bakiye, konsantrasyon riski
- Alıcılar (120): Büyük müşteri ödeme disiplini, tek müşteriye bağımlılık
- Borç vade yapısı: KV/UV oranı, refinansman riski, neden uzun vadeli borç yok
- Ortaklardan alacaklar (131): Şişkin mi, geri dönecek mi, örtülü kâr dağıtımı riski

Kurallar:
- Her soru bu firmaya özgü olsun, gerçek rakamları kullan
- Hazır yanıtta placeholder kullanma, gerçek rakamları yaz
- Türkçe yaz, sadece JSON döndür

JSON formatı:
{_JSON_FORMAT}

FİRMA PROFİLİ:
{firma_profil}
KÖTÜ/ZAYIF RASYOLAR:
{kotu_zayif_satirlar}
BİLANÇO ÖZETİ:
{bilanco_ozeti}
ALT HESAP ANALİZLERİ (120, 131, 159, 300, 320, 321, 340):
{alt_cagri1}"""

    # ── ÇAĞRI 2: Alt hesap anomalileri ───────────────────────────────────
    prompt2 = f"""Sen deneyimli bir Türk kurumsal bankacısın. Aşağıdaki hesaplardaki anomaliler için banka görüşme soruları üret. Daha önce üretilen sorularla tekrar etme. Sadece JSON döndür.

Odak: Konsantrasyonlar, tek kaynağa bağımlılık, büyük avanslar, açıklanamayan kalemler — alt kalemlere kadar in.
Her hesap için en az 1 somut soru üret. Gerçek firma rakamlarını ve kalem adlarını kullan.

JSON formatı:
{_JSON_FORMAT}

FİRMA PROFİLİ:
{firma_profil}
ALT HESAP ANALİZLERİ (120, 131, 159, 300, 320, 321, 340):
{alt_cagri1}"""

    # ── ÇAĞRI 3: Mizana özel dikkat çekenler ─────────────────────────────
    prompt3 = f"""Sen deneyimli bir Türk kurumsal bankacısın. Bu firmaya özel olağandışı kalemler için banka görüşme soruları üret. Daha önce üretilen sorularla tekrar etme. Sadece JSON döndür.

Odak: Olağandışı gelirler, lüks varlıklar, sıra dışı kalemler, kalan alt hesaplardaki riskler, firma profilindeki çarpıcı noktalar.

JSON formatı:
{_JSON_FORMAT}

FİRMA PROFİLİ:
{firma_profil}
KALAN ALT HESAP ANALİZLERİ:
{alt_cagri3}
BİLANÇO ÖZETİ:
{bilanco_ozeti}"""

    # ── Üç çağrıyı yap, birleştir ────────────────────────────────────────
    tum_sorular: list[BankaSorusu] = []
    tum_sorular += _cagri(client, prompt1, "Çağrı-1-kritik")
    tum_sorular += _cagri(client, prompt2, "Çağrı-2-alt-hesap")
    tum_sorular += _cagri(client, prompt3, "Çağrı-3-olagandusu")

    tum_sorular.sort(key=lambda s: s.oncelik)
    logger.info(f"Toplam banka sorusu: {len(tum_sorular)}")
    return tum_sorular
