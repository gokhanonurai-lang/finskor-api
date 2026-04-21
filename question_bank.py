"""
FinSkor — Question Bank v2
Sonnet bazlı dinamik banka sorusu üretimi.
"""

from __future__ import annotations
import os
import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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
    """
    Sonnet ile firmaya özgü banka görüşme soruları üretir.
    Hata durumunda boş liste döner.
    """
    try:
        return _uret_sonnet(bs, skor_sonuc, sektor, alt_hesap_analizleri or [], analizler or [])
    except Exception as e:
        logger.warning(f"Banka soruları üretilemedi: {e}")
        return []


def _uret_sonnet(bs, skor_sonuc, sektor: str, alt_hesap_analizleri: list, analizler: list) -> list[BankaSorusu]:
    import anthropic
    from analyzer import NACE_BOLUM_ORT, nace_to_bolum

    bolum = nace_to_bolum(sektor)
    sekt_ort = NACE_BOLUM_ORT.get(bolum, NACE_BOLUM_ORT.get("G", {}))

    # ── Firma verileri ──────────────────────────────────────────────────
    toplam_aktif = bs.toplam_aktif or 1
    firma_verileri = (
        f"Skor: {skor_sonuc.skor}/100 ({skor_sonuc.harf} — {skor_sonuc.kredi_band})\n"
        f"Sektör: {sektor} (NACE bölüm: {bolum})\n"
        f"Net Satışlar: {bs.net_satislar:,.0f} TL\n"
        f"FAVÖK: {bs.favok:,.0f} TL  |  FAVÖK Marjı: %{bs.favok/bs.net_satislar*100:.1f}" if bs.net_satislar else ""
        f"Net Kâr: {bs.net_kar:,.0f} TL\n"
        f"Toplam Aktif: {bs.toplam_aktif:,.0f} TL\n"
        f"Özkaynaklar: {bs.ozkaynaklar:,.0f} TL\n"
    )

    # ── Rasyo sonuçları — kötü/zayıf önce ──────────────────────────────
    analiz_by_id = {a.rasyo_id: a for a in analizler} if analizler else {}

    kotu_zayif = [r for r in skor_sonuc.rasyolar if r.bant in ("kotu", "zayif")]
    diger = [r for r in skor_sonuc.rasyolar if r.bant not in ("kotu", "zayif")]

    def rasyo_satir(r) -> str:
        rid = getattr(r, "id", "")
        ort = sekt_ort.get(rid)
        ort_str = f"  |  sektör ort: {ort:.2f}" if ort else ""
        analiz = analiz_by_id.get(rid)
        kars = f"  |  karşılaştırma: {analiz.karsilastirma_metin}" if analiz else ""
        return f"  - {r.ad}: {r.deger_fmt} [{r.bant.upper()}] (puan: {r.puan}/{r.max_puan}){ort_str}{kars}"

    rasyo_satirlari = ""
    if kotu_zayif:
        rasyo_satirlari += "KÖTÜ/ZAYIF RASYOLAR (öncelikli incele):\n"
        rasyo_satirlari += "\n".join(rasyo_satir(r) for r in kotu_zayif) + "\n\n"
    rasyo_satirlari += "DİĞER RASYOLAR:\n"
    rasyo_satirlari += "\n".join(rasyo_satir(r) for r in diger)

    # ── Alt hesap özeti ──────────────────────────────────────────────────
    alt_hesap_ozeti = ""
    if alt_hesap_analizleri:
        satirlar = []
        for h in alt_hesap_analizleri:
            if isinstance(h, dict):
                kod = h.get("ana_hesap_kodu", "")
                adi = h.get("ana_hesap_adi", "")
                analiz = h.get("analiz_metni", "")
                uyari = h.get("uyari_notu", "")
                if analiz and analiz.strip() and analiz.strip() != "Analiz üretilemedi":
                    satirlar.append(f"[{kod} — {adi}]\n{analiz[:400]}" + (f"\nUYARI: {uyari}" if uyari else ""))
        alt_hesap_ozeti = "\n\n".join(satirlar[:12]) if satirlar else "Mevcut değil."
    else:
        alt_hesap_ozeti = "Mevcut değil."

    # ── Bilanço özeti ────────────────────────────────────────────────────
    ortaklardan_alacak = getattr(bs, "ortaklardan_alacaklar", 0) or getattr(bs, "diger_alacaklar_kv", 0)
    bilanco_ozeti = (
        f"Kasa (100): {bs.kasa:,.0f} TL (%{bs.kasa/toplam_aktif*100:.1f} aktif)\n"
        f"Banka (102): {bs.banka:,.0f} TL (%{bs.banka/toplam_aktif*100:.1f} aktif)\n"
        f"Toplam Nakit: {bs.nakit_ve_benzerleri:,.0f} TL\n"
        f"Ticari Alacaklar: {bs.ticari_alacaklar:,.0f} TL (%{bs.ticari_alacaklar/toplam_aktif*100:.1f} aktif)\n"
        f"Stoklar: {bs.stoklar:,.0f} TL (%{bs.stoklar/toplam_aktif*100:.1f} aktif)\n"
        f"Dönen Varlıklar: {bs.donen_varliklar:,.0f} TL\n"
        f"Duran Varlıklar: {bs.duran_varliklar:,.0f} TL\n"
        f"KV Borçlar: {bs.kv_borclar:,.0f} TL\n"
        f"  - KV Banka Kredileri: {bs.banka_kredileri_kv:,.0f} TL\n"
        f"  - Ticari Borçlar: {bs.ticari_borclar_kv:,.0f} TL\n"
        f"  - Ortaklara Borçlar: {bs.ortaklara_borclar:,.0f} TL\n"
        f"UV Borçlar: {bs.uv_borclar:,.0f} TL\n"
        f"Özkaynaklar: {bs.ozkaynaklar:,.0f} TL\n"
        f"Ortaklardan Alacaklar (131): {ortaklardan_alacak:,.0f} TL\n"
        f"Finansman Giderleri: {bs.finansman_giderleri:,.0f} TL\n"
        f"Geçmiş Yıl Kâr/Zararı: {bs.gecmis_yil_karlari:,.0f} TL\n"
    )

    prompt = f"""Sen deneyimli bir Türk kurumsal bankacısın. Bu firmayla kredi görüşmesi yapacaksın. Aşağıdaki verileri derinlemesine incele ve bankacı gözüyle sorular üret.

Öncelik sırası — her birini atlamadan incele:

1. Kritik ve zayıf rasyolar — kötü/zayıf bandındaki her rasyo için gerekiyorsa soru sor, rakamları kullan
2. Sektör sapmaları — sektör ortalamasından önemli ölçüde sapan her kalemi sorgula
3. Zorunlu kalemler — bunları mutlaka sorgula:
   - Kasa hesabı (100): Bakiye şişkin görünüyorsa gerçekten mevcut mu? Bankacı fiktif nakit riskini ölçüyor — tatmin olmazsa bilanço kalitesi ve sermaye düşer
   - Stoklar: Gerçek piyasa değeri ne? Eskimiş veya yavaş dönen var mı? Teminat olarak kabul edilebilir mi?
   - Ticari alacaklar: Tahsil edilebilir mi? Gecikmiş veya şüpheli var mı? Konsantrasyon riski?
   - Alıcılar (120): En büyük müşterilerin ödeme disiplini nasıl? Tek müşteriye bağımlılık var mı?
   - Borç vade yapısı: Neden tüm borçlar kısa vadeli? Uzun vadeli borç neden yok? Refinansman riski?
   - Ortaklardan alacaklar (131): Bu kalem şişkin mi? Ortağa verilen para geri dönecek mi? Örtülü kâr dağıtımı riski var mı?
4. Alt hesap anomalileri — konsantrasyonlar, tek kaynağa bağımlılık, büyük avanslar, açıklanamayan kalemler — alt kalemlere kadar in
5. Mizana özel dikkat çekenler — olağandışı gelirler, lüks varlıklar, sıra dışı her şey

Kurallar:
- Minimum 5 soru, üst sınır yok — önemli hiçbir konuyu atlama
- Her soru bu firmaya özgü olsun, gerçek rakamları kullan
- Bankacının amacını net yaz — riski nasıl ölçüyor, ne arıyor
- Hazır yanıt savunmacı değil, güven verici ve gerçekçi olsun — placeholder kullanma, gerçek rakamları koy
- Türkçe yaz
- Sadece JSON döndür, başka hiçbir şey yazma

JSON formatı:
[{{"kategori": "Bilanço Kalitesi | Kârlılık | Borç Ödeme Kapasitesi | Teminat | Operasyonel", "soru": "...", "bankacinin_amaci": "...", "hazir_cevap": "...", "oncelik": 1}}]
oncelik: 1=kritik, 2=önemli, 3=bilgi

FİRMA VERİLERİ:
{firma_verileri}

RASYO SONUÇLARI (bant ve sektör ortalamaları ile):
{rasyo_satirlari}

ALT HESAP ANALİZLERİ:
{alt_hesap_ozeti}

BİLANÇO ÖZETİ:
{bilanco_ozeti}"""

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    for deneme in range(3):
        try:
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()

            # JSON bloğu varsa çıkar
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            data = json.loads(raw)
            sorular = []
            for item in data:
                sorular.append(BankaSorusu(
                    kategori=item.get("kategori", "Genel"),
                    soru=item.get("soru", ""),
                    bankacinin_amaci=item.get("bankacinin_amaci", ""),
                    hazir_cevap=item.get("hazir_cevap", ""),
                    skor_etkisi=item.get("skor_etkisi", ""),
                    oncelik=int(item.get("oncelik", 2)),
                    tetikleyen="sonnet",
                ))
            sorular.sort(key=lambda s: s.oncelik)
            return sorular

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning(f"Banka sorusu parse hatası (deneme {deneme+1}/3): {e}")
            if deneme == 2:
                return []

    return []
