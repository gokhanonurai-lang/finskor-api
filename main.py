"""
BilankoIQ — FastAPI Backend
Çalıştır: uvicorn main:app --reload --port 8000
"""

from __future__ import annotations
import os
import tempfile
import logging
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from parser import parse_mizan
from analyzer import analiz_et
from scorer import skorla, SkorSonuc

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="BilankoIQ API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Production'da Next.js URL'ini yaz
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# RESPONSE MODELLERİ
# ─────────────────────────────────────────────

class RasyoResponse(BaseModel):
    id: str
    ad: str
    formul: str
    deger: float
    deger_fmt: str
    bant: str
    puan: float
    max_puan: float
    aciklama: str
    kategori: str

class BayrakResponse(BaseModel):
    kod: str
    mesaj: str
    ciddiyet: str

class AksiyanResponse(BaseModel):
    id: str
    baslik: str
    etki: str
    zorluk: str

class AnalysisResponse(BaseModel):
    # Firma özeti
    firma_ozet: dict

    # Skor
    skor: int
    harf: str
    kredi_band: str
    kredi_limit_aciklama: str
    teminat_aciklama: str

    # Kategori puanları
    likidite_puan: float
    sermaye_puan: float
    karlilik_puan: float
    faaliyet_puan: float
    borc_puan: float

    # Detay
    rasyolar: list[RasyoResponse]
    kirmizi_bayraklar: list[BayrakResponse]
    aksiyon_listesi: list[AksiyanResponse]

    # Tüm rasyolar (eğitim paneli)
    tum_rasyolar: dict

    # Parse meta
    parse_method: str
    match_rate: float
    warnings: list[str]


# ─────────────────────────────────────────────
# ENDPOINTler
# ─────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "BilankoIQ API"}


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze(
    file: UploadFile = File(...),
    sektor: str = Form(default="ticaret"),
    sirket_adi: str = Form(default=""),
):
    """
    Ana endpoint. Excel mizan yükle, tam analiz al.

    Form fields:
        file    : Excel mizan dosyası (.xlsx)
        sektor  : ticaret | uretim | hizmet
        sirket_adi: Firma adı (opsiyonel)
    """
    # Sektör doğrula
    if sektor not in ("ticaret", "uretim", "hizmet"):
        raise HTTPException(400, "sektor 'ticaret', 'uretim' veya 'hizmet' olmalı")

    # Dosya uzantısı kontrol
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Sadece .xlsx veya .xls dosyaları kabul edilir")

    # Geçici dosyaya kaydet
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Parse
        use_ai = bool(os.getenv("ANTHROPIC_API_KEY"))
        bs = parse_mizan(tmp_path, sector=sektor, use_ai_fallback=use_ai)

        # Skorla
        sonuc: SkorSonuc = skorla(bs, sektor=sektor)

        # Firma özeti
        firma_ozet = {
            "sirket_adi": sirket_adi or file.filename.replace(".xlsx", ""),
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
            "ortaklara_borclar": round(bs.ortaklara_borclar),
            "finansman_giderleri": round(bs.finansman_giderleri),
        }

        # Rasyoları serialize et
        analizler = analiz_et(sonuc, sektor=sektor)
        analiz_dict = {a.rasyo_id: a for a in analizler}
        rasyolar = []
        for r in sonuc.rasyolar:
            rasyo_id = getattr(r, 'id', r.ad.lower().replace(' ', '_'))
            analiz = analiz_dict.get(rasyo_id)
            aciklama = analiz.aciklama if analiz else r.aciklama
            rasyolar.append(RasyoResponse(
                id=rasyo_id,
                ad=r.ad,
                formul=r.formul,
                deger=round(r.deger, 4),
                deger_fmt=r.deger_fmt,
                bant=r.bant,
                puan=r.puan,
                max_puan=r.max_puan,
                aciklama=aciklama,
                kategori=r.kategori,
            ))

        return AnalysisResponse(
            firma_ozet=firma_ozet,
            skor=sonuc.skor,
            harf=sonuc.harf,
            kredi_band=sonuc.kredi_band,
            kredi_limit_aciklama=sonuc.kredi_limit_aciklama,
            teminat_aciklama=sonuc.teminat_aciklama,
            likidite_puan=sonuc.likidite_puan,
            sermaye_puan=sonuc.sermaye_puan,
            karlilik_puan=sonuc.karlilik_puan,
            faaliyet_puan=sonuc.faaliyet_puan,
            borc_puan=sonuc.borc_puan,
            rasyolar=rasyolar,
            kirmizi_bayraklar=[
                BayrakResponse(kod=b.kod, mesaj=b.mesaj, ciddiyet=b.ciddiyet)
                for b in sonuc.kirmizi_bayraklar
            ],
            aksiyon_listesi=[
                AksiyanResponse(
                    id=a["id"],
                    baslik=a["baslik"],
                    etki=a["etki"],
                    zorluk=a["zorluk"],
                )
                for a in sonuc.aksiyon_listesi
            ],
            tum_rasyolar={k: round(v, 4) for k, v in sonuc.tum_rasyolar.items()},
            parse_method=bs.parse_method,
            match_rate=round(bs.match_rate, 3),
            warnings=bs.warnings,
        )

    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        logger.exception("Analiz hatası")
        raise HTTPException(500, f"Analiz sırasında hata: {str(e)}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)
