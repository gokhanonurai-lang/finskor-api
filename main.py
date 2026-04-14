"""
FinSkor — FastAPI Backend v2
Çalıştır: uvicorn main:app --reload --port 8000
"""

from __future__ import annotations
import os
import tempfile
import logging
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx

from parser import parse_mizan
from scorer import skorla
from analyzer import analiz_et, tum_analizler
from reporter import rapor_olustur

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ─── KALİTE KONTROL ───────────────────────────────────────────────────────────

async def kalite_kontrol(sonuc, bs) -> tuple[bool, str]:
    """Raporu Claude Haiku ile kalite kontrolünden geçirir."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    aktif_pasif_fark = abs(bs.toplam_aktif - bs.toplam_pasif)
    aktif_pasif_oran = (aktif_pasif_fark / bs.toplam_aktif * 100) if bs.toplam_aktif > 0 else 100

    prompt = f"""Finansal rapor kalite kontrolü yap. Sadece GECER veya HATA: [açıklama] döndür.

VERİLER:
- Toplam Aktif: {bs.toplam_aktif:,.0f} TL
- Toplam Pasif: {bs.toplam_pasif:,.0f} TL
- Aktif-Pasif Fark Oranı: %{aktif_pasif_oran:.1f}
- Net Satışlar: {bs.net_satislar:,.0f} TL
- FAVÖK: {bs.favok:,.0f} TL
- Net Kâr: {bs.net_kar:,.0f} TL
- Özkaynaklar: {bs.ozkaynaklar:,.0f} TL
- Skor: {sonuc.skor}/100
- Bant: {sonuc.harf}

KONTROL ET ve sadece aşağıdaki durumlarda HATA ver, aksi halde GECER yaz:
1. Toplam aktif sıfır veya 100,000 TL altında mı?
2. Aktif-pasif fark oranı %5 veya daha fazla mı? (%3.2 gibi %5 altı değerler GECER'dir)
NOT: Net satışlar sıfır olabilir — yıl sonu kapatılmış mizanlarda gelir tablosu kapalıdır, bu normaldir.

Sadece GECER veya HATA: [kısa açıklama] yaz."""

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}]
        )
        sonuc = message.content[0].text.strip()
        if sonuc.startswith("GECER"):
            return True, "OK"
        elif sonuc.startswith("HATA:"):
            return False, sonuc[5:].strip()
        elif "GECER" in sonuc:
            return True, "OK"
        else:
            return True, "OK"
    except Exception as e:
        logger.warning(f"Kalite kontrol hatasi: {e}")
        return True, "OK"



app = FastAPI(title="FinSkor API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


security = HTTPBearer()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ymjwtntlfioexudvacsj.supabase.co")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": SUPABASE_ANON_KEY,
            }
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Geçersiz veya süresi dolmuş oturum.")
    return resp.json()

@app.get("/health")
@app.head("/health")
def health():
    return {"status": "ok", "service": "FinSkor API v2"}


@app.post("/analyze")
async def analyze(
    user = Depends(verify_token),
    file: UploadFile = File(...),
    sektor: str = Form(default="ticaret"),
    sirket_adi: str = Form(default=""),
):
    if sektor not in ("ticaret", "uretim", "hizmet"):
        raise HTTPException(400, "sektor 'ticaret', 'uretim' veya 'hizmet' olmalı")
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Sadece .xlsx veya .xls dosyaları kabul edilir")
    content_check = await file.read()
    if len(content_check) > 10 * 1024 * 1024:
        raise HTTPException(400, "Dosya boyutu 10MB'ı geçemez.")
    await file.seek(0)

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        firma_adi = sirket_adi or file.filename.replace(".xlsx", "").replace(".xls", "")

        use_ai = bool(os.getenv("ANTHROPIC_API_KEY"))
        bs = parse_mizan(tmp_path, sector=sektor, use_ai_fallback=use_ai)
        sonuc = skorla(bs, sektor=sektor)
        analizler = tum_analizler(sonuc.tum_rasyolar, sektor=sektor)
        rapor = rapor_olustur(bs, sonuc, analizler, sektor=sektor, firma_adi=firma_adi)

        # Kalite kontrolü
        gecti, hata_mesaji = await kalite_kontrol(sonuc, bs)
        if not gecti:
            raise HTTPException(
                status_code=422,
                detail=f"Mizanınızda tutarsızlık tespit edildi: {hata_mesaji}. Lütfen mizanınızı kontrol edip tekrar yükleyin."
            )

        # Firma özeti
        firma_ozet = {
            "sirket_adi": firma_adi,
            "sektor": sektor,
            "toplam_aktif": round(bs.toplam_aktif),
            "net_satislar": round(bs.net_satislar),
            "favok": round(bs.favok),
            "net_kar": round(bs.net_kar),
            "donen_varliklar": round(bs.donen_varliklar),
            "duran_varliklar": round(bs.duran_varliklar),
            "kv_borclar": round(bs.kv_borclar),
            "uv_borclar": round(bs.uv_borclar),
            "ozkaynaklar": round(bs.ozkaynaklar),
            "nakit": round(bs.nakit_ve_benzerleri),
            "stoklar": round(bs.stoklar),
            "ticari_alacaklar": round(bs.ticari_alacaklar),
        }

        # Rasyolar
        analiz_dict = {a.rasyo_id: a for a in analizler}
        rasyolar = []
        for r in sonuc.rasyolar:
            rasyo_id = getattr(r, "id", r.ad.lower().replace(" ", "_"))
            analiz = analiz_dict.get(rasyo_id)
            rasyolar.append({
                "id": rasyo_id,
                "ad": r.ad,
                "formul": r.formul,
                "deger": round(r.deger, 4),
                "deger_fmt": r.deger_fmt,
                "bant": r.bant,
                "puan": r.puan,
                "max_puan": r.max_puan,
                "aciklama": analiz.ne_anlama_gelir if analiz else r.aciklama,
                "iyilestirme_adimlari": analiz.nasil_iyilestirilir if analiz else [],
                "sektor_ort": analiz.sektor_ort_fmt if analiz else "",
                "kategori": r.kategori,
            })

        # Senaryolar
        senaryolar = [{
            "aciklama": s.aciklama,
            "yeni_skor": s.yeni_skor,
            "skor_delta": s.skor_delta,
            "yeni_harf": s.yeni_harf,
            "yeni_limit_aciklama": s.yeni_limit_aciklama,
        } for s in rapor.senaryolar]

        # Banka soruları
        banka_sorulari = [{
            "kategori": b.kategori,
            "soru": b.soru,
            "bankacinin_amaci": b.bankacinin_amaci,
            "hazir_cevap": b.hazir_cevap,
            "skor_etkisi": b.skor_etkisi,
            "oncelik": b.oncelik,
        } for b in rapor.banka_sorulari]

        # Kredi türü
        kt = rapor.kredi_turu_oneri
        kredi_turu = {
            "birincil_tur": kt.birincil_tur,
            "birincil_aciklama": kt.birincil_aciklama,
            "birincil_miktar": kt.birincil_miktar,
            "neden": kt.neden,
            "alternatif_turler": kt.alternatif_turler,
        } if kt else None

        # Nakit akış
        na = rapor.nakit_akis_analiz
        nakit_akis = {
            "aylik_favok_fmt": na.aylik_favok_fmt,
            "mevcut_borc_servisi_fmt": na.mevcut_borc_servisi_fmt,
            "favok_kullanim_orani": round(na.favok_kullanim_orani * 100, 1),
            "yeni_kredi_taksiti_fmt": na.yeni_kredi_taksiti_fmt,
            "toplam_borc_servisi_fmt": na.toplam_borc_servisi_fmt,
            "toplam_favok_kullanim_orani": round(na.toplam_favok_kullanim_orani * 100, 1),
            "kapasite_degerlendirmesi": na.kapasite_degerlendirmesi,
            "yorum": na.yorum,
        } if na else None

        # Zaman çizelgesi
        zaman_cizelgesi = [{
            "donem": z["donem"],
            "aksiyonlar": z["aksiyonlar"],
            "beklenen_etki": z["beklenen_etki"],
        } for z in rapor.zaman_cizelgesi]

        # Zayıf yönler
        zayif_yonler = []
        for z in rapor.zayif_yonler:
            if isinstance(z, dict):
                zayif_yonler.append({
                    "mesaj": z.get("mesaj", ""),
                    "seviye": z.get("seviye", ""),
                    "iyilestir": z.get("iyilestir", []),
                })
            else:
                zayif_yonler.append({"mesaj": str(z), "seviye": "", "iyilestir": []})

        return {
            "firma_ozet": firma_ozet,
            "yonetici_ozeti": rapor.yonetici_ozeti,
            "potansiyel_raporu": rapor.potansiyel_raporu,
            "skor": sonuc.skor,
            "harf": sonuc.harf,
            "kredi_band": sonuc.kredi_band,
            "kredi_limit_aciklama": sonuc.kredi_limit_aciklama,
            "teminat_aciklama": sonuc.teminat_aciklama,
            "likidite_puan": sonuc.likidite_puan,
            "sermaye_puan": sonuc.sermaye_puan,
            "karlilik_puan": sonuc.karlilik_puan,
            "faaliyet_puan": sonuc.faaliyet_puan,
            "borc_puan": sonuc.borc_puan,
            "rasyolar": rasyolar,
            "kirmizi_bayraklar": [
                {"kod": b.kod, "mesaj": b.mesaj, "ciddiyet": b.ciddiyet}
                for b in sonuc.kirmizi_bayraklar
            ],
            "guclu_yonler": list(rapor.guclu_yonler),
            "zayif_yonler": zayif_yonler,
            "senaryolar": senaryolar,
            "banka_sorulari": banka_sorulari,
            "kredi_turu": kredi_turu,
            "nakit_akis": nakit_akis,
            "zaman_cizelgesi": zaman_cizelgesi,
            "banka_hazirlik": {
                "belgeler": list(rapor.banka_hazirlik.hazirlanacak_belgeler),
                "dikkat_edilecekler": list(rapor.banka_hazirlik.dikkat_edilecekler),
            },
            "parse_method": bs.parse_method,
            "match_rate": round(bs.match_rate, 3),
            "warnings": bs.warnings,
        }

    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        logger.exception("Analiz hatası")
        raise HTTPException(500, f"Analiz sırasında hata: {str(e)}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)
