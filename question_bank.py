"""
BilankoIQ — Question Bank
Bilançodan otomatik tespit edilen banka soruları,
bankacının amacı, hazır cevap şablonu ve skor etkisi.
Tamamen fix kurallar — AI kullanılmaz.
"""

from __future__ import annotations
from dataclasses import dataclass, field


# ─────────────────────────────────────────────
# VERİ MODELİ
# ─────────────────────────────────────────────

@dataclass
class BankaSorusu:
    kategori: str
    soru: str
    bankacinin_amaci: str
    hazir_cevap: str
    skor_etkisi: str
    oncelik: int          # 1=kritik, 2=önemli, 3=bilgi
    tetikleyen: str       # Hangi bilanço kalemi tetikledi


# ─────────────────────────────────────────────
# SORU TETİKLEYİCİLER
# Her fonksiyon bir koşulu kontrol eder ve soru üretir
# ─────────────────────────────────────────────

def _sorular_bilanco_kalitesi(bs, skor_sonuc) -> list[BankaSorusu]:
    sorular = []

    # Ortaklar cari yüksekse
    ortaklar_oran = bs.ortaklara_borclar / bs.toplam_pasif if bs.toplam_pasif else 0
    if ortaklar_oran > 0.08:
        sorular.append(BankaSorusu(
            kategori="Bilanço Kalitesi",
            soru=f"Ortaklar cari hesabınızda {bs.ortaklara_borclar:,.0f} TL görünüyor. "
                 f"Bu tutar ne zaman kapatılacak?",
            bankacinin_amaci=(
                "Bu tutarı gerçek borç olarak mı yoksa özkaynak yerine mi "
                "değerlendireceğine karar veriyor. Yüksekse özkaynak "
                "yetersizliği işareti sayar ve limit düşer."
            ),
            hazir_cevap=(
                f"Bu tutar ortağın şirkete geçici olarak aktardığı fondur. "
                f"Önümüzdeki dönemde sermayeye ilave edilmesi planlanmaktadır. "
                f"Sermayeye aktarıldığında Borç/Özkaynak oranımız "
                f"{bs.toplam_borclar/bs.ozkaynaklar:.2f}x'ten "
                f"{bs.toplam_borclar/(bs.ozkaynaklar+bs.ortaklara_borclar):.2f}x'e "
                f"düşecektir."
            ),
            skor_etkisi=(
                f"Ortaklar cari kapatılırsa Borç/Özkaynak iyileşir, "
                f"kırmızı bayrak kalkar → tahmini +8 ile +12 puan"
            ),
            oncelik=1,
            tetikleyen="ortaklara_borclar",
        ))

    # Stok yüksekse
    stok_oran = bs.stoklar / bs.net_satislar if bs.net_satislar else 0
    if stok_oran > 0.08:
        stok_gun = bs.stoklar * 365 / bs.satislarin_maliyeti if bs.satislarin_maliyeti else 0
        sorular.append(BankaSorusu(
            kategori="Bilanço Kalitesi",
            soru=f"Stok rakamınız {bs.stoklar:,.0f} TL — ortalama {stok_gun:.0f} günde dönüyor. "
                 f"Yavaş hareket eden veya eskimiş ürün var mı?",
            bankacinin_amaci=(
                "Stokun gerçek piyasa değerini ve likidite edilebilirliğini "
                "sorguluyor. Banka stoku teminat olarak kabul ederse "
                "değerinin %40-50'si kadar değer biçer."
            ),
            hazir_cevap=(
                f"Stoklarımızın tamamı aktif satış döngüsündedir. "
                f"Son dönemde {stok_gun:.0f} günlük dönüş hızı sektör normali "
                f"dahilindedir. Eskimiş veya değer düşüklüğüne uğramış ürün bulunmamaktadır. "
                f"Stok listesi talep edilmesi halinde sunulabilir."
            ),
            skor_etkisi=(
                f"Stok {bs.stoklar*0.3:,.0f} TL eritilirse stok devir hızı artar, "
                f"nakit dönüşüm süresi kısalır → tahmini +3 ile +5 puan"
            ),
            oncelik=2,
            tetikleyen="stoklar",
        ))

    # Ticari alacaklar yüksekse
    alacak_gun = bs.ticari_alacaklar * 365 / bs.net_satislar if bs.net_satislar else 0
    if alacak_gun > 60:
        sorular.append(BankaSorusu(
            kategori="Bilanço Kalitesi",
            soru=f"Ticari alacaklarınız {bs.ticari_alacaklar:,.0f} TL ve "
                 f"ortalama tahsil süreniz {alacak_gun:.0f} gün. "
                 f"Gecikmiş veya şüpheli alacak var mı?",
            bankacinin_amaci=(
                "Alacakların gerçekten tahsil edilebilir olup olmadığını "
                "ve müşteri konsantrasyonu riskini ölçüyor. "
                "Büyük bir müşteri riski varsa kredi limitini baskılar."
            ),
            hazir_cevap=(
                f"Alacaklarımızın tamamı vadeli satışlardan kaynaklanmakta "
                f"olup gecikmiş alacak oranımız %5'in altındadır. "
                f"En büyük 3 müşterimiz toplam alacağın yaklaşık %40'ını "
                f"oluşturmaktadır ve bunların tamamı düzenli ödeme geçmişine sahiptir. "
                f"Müşteri bazında alacak tablosu talep halinde sunulabilir."
            ),
            skor_etkisi=(
                f"Alacakların {bs.ticari_alacaklar*0.3:,.0f} TL'si tahsil edilirse "
                f"asit-test ve nakit dönüşüm süresi iyileşir → tahmini +3 ile +6 puan"
            ),
            oncelik=2,
            tetikleyen="ticari_alacaklar",
        ))

    # Geçmiş yıl zararı varsa
    if bs.gecmis_yil_karlari < 0:
        sorular.append(BankaSorusu(
            kategori="Bilanço Kalitesi",
            soru=f"Geçmiş yıllar zararı {abs(bs.gecmis_yil_karlari):,.0f} TL görünüyor. "
                 f"Bu zarar nasıl oluştu?",
            bankacinin_amaci=(
                "Zararın tek seferlik mi yoksa yapısal bir sorundan mı "
                "kaynaklandığını anlıyor. Yapısal sorunsa risk artar."
            ),
            hazir_cevap=(
                "Bu zarar [dönem] yılında yaşanan [kriz/pandemi/sektörel daralma] "
                "nedeniyle oluşmuştur. Tek seferlik nitelikte olup mevcut dönemde "
                "kâra dönülmüştür. Alınan önlemler: [maliyet azaltma/ürün mix "
                "değişikliği/yeni müşteri kazanımı]. Bu yılki net kârımız "
                f"{bs.net_kar:,.0f} TL'dir."
            ),
            skor_etkisi=(
                "Geçmiş zarar özkaynakları eroduyor — sermaye artırımı veya "
                "kâr birikimi ile kapanırsa özkaynak rasyoları iyileşir → +5 ile +10 puan"
            ),
            oncelik=1,
            tetikleyen="gecmis_yil_karlari",
        ))

    # KV borç oranı çok yüksekse
    kv_oran = bs.kv_borclar / bs.toplam_borclar if bs.toplam_borclar else 0
    if kv_oran > 0.70:
        sorular.append(BankaSorusu(
            kategori="Bilanço Kalitesi",
            soru=f"Borçlarınızın {kv_oran*100:.0f}%'i kısa vadeli. "
                 f"Bu kredileri uzun vadeye çevirme planınız var mı?",
            bankacinin_amaci=(
                "Refinansman riskini ölçüyor. KV borç yüksekse "
                "her yıl büyük bir borç yenileme ihtiyacı var demektir. "
                "Bu, şirketin faiz artışlarına ve banka politika "
                "değişikliklerine karşı kırılgan olduğunu gösterir."
            ),
            hazir_cevap=(
                f"KV borçlarımızın {bs.banka_kredileri_kv:,.0f} TL'lik kısmı "
                f"döner kredi niteliğinde olup işletme sermayesi ihtiyacımızı "
                f"karşılamaktadır. Bu kredilerin bir kısmını yatırım kredisine "
                f"dönüştürmek için görüşmelerimiz devam etmektedir. "
                f"Mevcut nakit akışımız borç servisini karşılamaya yeterlilidir."
            ),
            skor_etkisi=(
                f"KV borcun {bs.banka_kredileri_kv*0.5:,.0f} TL'si UV'ye çevrilirse "
                f"cari oran ve KV borç oranı iyileşir → tahmini +5 ile +8 puan"
            ),
            oncelik=2,
            tetikleyen="kv_borc_orani",
        ))

    return sorular


def _sorular_karlilik(bs, skor_sonuc) -> list[BankaSorusu]:
    sorular = []

    # Düşük net kâr marjı
    net_marj = bs.net_kar / bs.net_satislar if bs.net_satislar else 0
    if 0 < net_marj < 0.03:
        sorular.append(BankaSorusu(
            kategori="Kârlılık",
            soru=f"Net kâr marjınız %{net_marj*100:.1f} — oldukça düşük. "
                 f"Finansman giderleriniz kârlılığı olumsuz etkiliyor mu?",
            bankacinin_amaci=(
                "Düşük kâr marjı borç servisini tehlikeye atabilir. "
                "Bankacı kârlılığın artış potansiyelini ve finansman "
                "giderlerinin yapısını anlıyor."
            ),
            hazir_cevap=(
                f"Net kâr marjımızın düşük görünmesinin temel nedeni "
                f"{bs.finansman_giderleri:,.0f} TL'lik finansman gideridir. "
                f"FAVÖK marjımız %{bs.favok/bs.net_satislar*100:.1f} olup "
                f"operasyonel verimliliğimiz iyidir. "
                f"Yüksek faizli kredileri refinanse ederek net kâr marjını "
                f"önümüzdeki dönemde artırmayı hedefliyoruz."
            ),
            skor_etkisi=(
                "Finansman gideri düşürülürse net kâr marjı ve ROE iyileşir "
                "→ tahmini +3 ile +5 puan"
            ),
            oncelik=2,
            tetikleyen="net_kar_marji",
        ))

    # Negatif kâr
    if bs.net_kar < 0:
        sorular.append(BankaSorusu(
            kategori="Kârlılık",
            soru="Bu dönem zarar etmişsiniz. Şirketi kâra döndürme planınız nedir?",
            bankacinin_amaci=(
                "Zararın geçici mi yapısal mı olduğunu ve yönetimin "
                "durumu fark edip aksiyon alıp almadığını ölçüyor."
            ),
            hazir_cevap=(
                "Bu dönemdeki zararın temel nedeni [yüksek faiz giderleri / "
                "hammadde maliyet artışı / geçici satış düşüşü]'dür. "
                "Alınan önlemler: [fiyat güncellemesi / maliyet kesintisi / "
                "yeni müşteri sözleşmeleri]. Önümüzdeki dönem tahmini "
                "FAVÖK'ümüz [X] TL olup kâra dönüş beklenmektedir."
            ),
            skor_etkisi=(
                "Zarar devam ettiği sürece skor D bandında kalır. "
                "Kâra dönüş tek dönemde bile skoru 15-20 puan iyileştirir."
            ),
            oncelik=1,
            tetikleyen="net_kar",
        ))

    # Yüksek finansman gideri
    fin_oran = bs.finansman_giderleri / bs.net_satislar if bs.net_satislar else 0
    if fin_oran > 0.05:
        sorular.append(BankaSorusu(
            kategori="Kârlılık",
            soru=f"Finansman giderleriniz {bs.finansman_giderleri:,.0f} TL — "
                 f"cironuzun %{fin_oran*100:.1f}'i. Kaç bankadan ve hangi "
                 f"faiz oranlarından kredi kullanıyorsunuz?",
            bankacinin_amaci=(
                "Toplam borç yükünü ve faiz profilini görmek istiyor. "
                "Ayrıca başka bankalarla olan ilişkiyi Risk Merkezi "
                "ile teyit edecek."
            ),
            hazir_cevap=(
                f"Toplam {bs.finansal_borclar:,.0f} TL finansal borcumuz "
                f"[X] bankada bulunmaktadır. Ortalama faiz oranımız "
                f"yaklaşık %[X]'dir. Faiz yükünü azaltmak için yüksek "
                f"maliyetli kredileri KGF destekli veya daha düşük faizli "
                f"kredilerle refinanse etmeyi planlıyoruz."
            ),
            skor_etkisi=(
                "Finansman gideri düşürülürse faiz karşılama ve net kâr marjı iyileşir "
                "→ tahmini +2 ile +4 puan"
            ),
            oncelik=2,
            tetikleyen="finansman_gider_orani",
        ))

    return sorular


def _sorular_borc_odeme(bs, skor_sonuc) -> list[BankaSorusu]:
    sorular = []

    # Faiz karşılama düşükse
    faiz_kars = bs.favok / bs.finansman_giderleri if bs.finansman_giderleri else 0
    if faiz_kars < 2.0:
        sorular.append(BankaSorusu(
            kategori="Borç Ödeme Kapasitesi",
            soru=f"FAVÖK'ünüz faiz giderinizin {faiz_kars:.1f} katı. "
                 f"Yeni kredi taksitini de eklediğimizde ödeme kapasitesi "
                 f"yeterli olacak mı?",
            bankacinin_amaci=(
                "Krediyi geri ödeyip ödeyemeyeceğini doğrudan sorguluyor. "
                "Bu oran 1.5x'in altına düşerse kredi onayı çok güçleşir."
            ),
            hazir_cevap=(
                f"Mevcut FAVÖK'ümüz {bs.favok:,.0f} TL olup bu oran "
                f"faiz giderlerimizi {faiz_kars:.1f}x karşılamaktadır. "
                f"Talep ettiğimiz kredi için aylık tahmini taksit [X] TL olup "
                f"aylık FAVÖK'ümüzün %[Y]'sine karşılık gelmektedir. "
                f"Nakit akışı projeksiyonumuzu sunmaya hazırız."
            ),
            skor_etkisi=(
                "FAVÖK artırılarak veya borç azaltılarak faiz karşılama "
                "3x'e çıkarılırsa → tahmini +6 puan"
            ),
            oncelik=1,
            tetikleyen="faiz_karsilama",
        ))

    # Net Borç/FAVÖK yüksekse
    nb_favok = bs.net_borc / bs.favok if bs.favok else 0
    if nb_favok > 4.0:
        sorular.append(BankaSorusu(
            kategori="Borç Ödeme Kapasitesi",
            soru=f"Net borcunuz FAVÖK'ünüzün {nb_favok:.1f} katı. "
                 f"Bu borç yükünü nasıl azaltmayı planlıyorsunuz?",
            bankacinin_amaci=(
                "Mevcut borç yükünün sürdürülebilirliğini ve yönetimin "
                "borç azaltma stratejisini anlıyor. "
                "5x üzeri bankalar için genellikle kabul sınırı."
            ),
            hazir_cevap=(
                f"Net borcumuz {bs.net_borc:,.0f} TL olup mevcut FAVÖK "
                f"ile {nb_favok:.1f} yılda kapanabilecek düzeydedir. "
                f"Borç azaltma planımız: [kâr birikimi / varlık satışı / "
                f"sermaye artırımı]. Önümüzdeki dönem hedef Net Borç/FAVÖK "
                f"oranımız [X]x'tir."
            ),
            skor_etkisi=(
                "Net Borç/FAVÖK 3x'in altına inerse → tahmini +6 puan, "
                "üst bant geçişi mümkün"
            ),
            oncelik=1,
            tetikleyen="net_borc_favok",
        ))

    return sorular


def _sorular_teminat(bs, skor_sonuc) -> list[BankaSorusu]:
    sorular = []

    # Teminat müzakeresi — her firmaya
    sorular.append(BankaSorusu(
        kategori="Teminat",
        soru="Teminat olarak ne gösterebilirsiniz?",
        bankacinin_amaci=(
            "Teminat havuzunu ölçüyor. Likit teminatlar "
            "(POS blokesi, çek, mevduat) bankacıya çekici gelir "
            "çünkü hızlı nakde çevrilebilir."
        ),
        hazir_cevap=(
            f"Sunabileceğimiz teminatlar: "
            f"(1) Kişisel kefalet — ortak/yönetici olarak şahsi kefalet verebiliriz. "
            f"(2) Ticari alacak temliki — {bs.ticari_alacaklar:,.0f} TL alacağımız mevcut. "
            f"(3) POS blokesi — aylık POS ciromuz [X] TL düzeyindedir. "
            f"(4) KGF kefaleti — başvurmamız halinde ek limit imkânı sağlanabilir. "
            f"{'(5) Gayrimenkul — ' + str(int(bs.maddi_duran_varliklar)) + ' TL maddi duran varlığımız mevcuttur.' if bs.maddi_duran_varliklar > 500_000 else ''}"
        ),
        skor_etkisi=(
            "Likit teminat sunmak skoru değiştirmez ama kredi "
            "onay olasılığını ve limit büyüklüğünü doğrudan etkiler."
        ),
        oncelik=2,
        tetikleyen="genel",
    ))

    # Düşük özkaynak varsa KGF sorusu
    if skor_sonuc.harf in ("BBB", "BB", "B"):
        sorular.append(BankaSorusu(
            kategori="Teminat",
            soru="KGF kefaletinden daha önce yararlandınız mı?",
            bankacinin_amaci=(
                "KGF kefaleti teminat açığını kapatır ve "
                "limiti artırır. Bankacı ek iş imkânı olarak görür."
            ),
            hazir_cevap=(
                "KGF kefaletinden [daha önce yararlandık / henüz yararlanmadık]. "
                "Bu başvuruyla birlikte KGF kefaleti de almak istiyoruz. "
                "KGF kefaleti ile limitimizin [X] TL artacağını "
                "ve teminat yapımızın hafifleyeceğini değerlendiriyoruz."
            ),
            skor_etkisi=(
                "KGF kefaleti skoru değiştirmez ama "
                "BBB bandında A bandı limitine erişim sağlar."
            ),
            oncelik=2,
            tetikleyen="harf_notu",
        ))

    return sorular


def _sorular_operasyonel(bs, skor_sonuc) -> list[BankaSorusu]:
    """Her firmaya sorulan genel operasyonel sorular."""
    sorular = []

    sorular.append(BankaSorusu(
        kategori="Operasyonel",
        soru="En büyük 3 müşteriniz toplam cironuzun yüzde kaçını oluşturuyor?",
        bankacinin_amaci=(
            "Müşteri konsantrasyon riskini ölçüyor. "
            "Tek bir müşteri cironun %40'ını oluşturuyorsa "
            "o müşteri kaybı şirketi tehlikeye atar."
        ),
        hazir_cevap=(
            "En büyük 3 müşterimiz toplam ciromuzu %[X] oranında "
            "oluşturmaktadır. Müşteri tabanımız [geniş/orta ölçekli] "
            "olup belirli bir müşteriye bağımlılığımız bulunmamaktadır. "
            "Uzun vadeli sözleşme yapısımız sayesinde ciro "
            "öngörülebilirliğimiz yüksektir."
        ),
        skor_etkisi="Skoru doğrudan etkilemez ama kredi onayını etkiler.",
        oncelik=2,
        tetikleyen="genel",
    ))

    sorular.append(BankaSorusu(
        kategori="Operasyonel",
        soru="Sektörünüzde önümüzdeki dönem için beklentiniz nedir?",
        bankacinin_amaci=(
            "Kredi geri ödeme kapasitesinin gelecekte sürdürülüp "
            "sürdürülemeyeceğini anlıyor. Daralan sektörde "
            "limit açmak risklidir."
        ),
        hazir_cevap=(
            "Sektörümüzde [büyüme / istikrar] bekliyoruz. "
            "Temel gerekçeler: [talep artışı / yeni proje / ihracat büyümesi]. "
            "Şirket olarak [yeni ürün / yeni müşteri / yeni pazar] "
            "ile büyüme hedefliyoruz. "
            f"Önümüzdeki dönem tahmini ciromuz {bs.net_satislar*1.15:,.0f} TL'dir."
        ),
        skor_etkisi="Skoru doğrudan etkilemez ama bankacı güveni artırır.",
        oncelik=3,
        tetikleyen="genel",
    ))

    if bs.net_satislar > 3_000_000:
        sorular.append(BankaSorusu(
            kategori="Operasyonel",
            soru="İhracat yapıyor musunuz veya planlıyor musunuz?",
            bankacinin_amaci=(
                "İhracat yapan firmalar Eximbank ve özel banka "
                "ihracat kredisi imkânlarından yararlanabilir. "
                "Döviz geliri de borç servisinde güvence sağlar."
            ),
            hazir_cevap=(
                "[İhracat yapıyoruz — yıllık X USD/EUR ihracat gelirimiz var.] "
                "veya "
                "[Henüz ihracat yapmıyoruz ancak [dönem] itibarıyla "
                "ihracat hedefliyoruz. Bu durumda Eximbank kaynaklarından "
                "yararlanmak isteyeceğiz.]"
            ),
            skor_etkisi=(
                "İhracat varsa Eximbank kredisi ile daha düşük "
                "faizli finansmana erişim mümkün."
            ),
            oncelik=3,
            tetikleyen="genel",
        ))

    return sorular


# ─────────────────────────────────────────────
# ANA FONKSİYON
# ─────────────────────────────────────────────

def sorulari_uret(bs, skor_sonuc) -> list[BankaSorusu]:
    """
    Bilançodan tüm banka sorularını üretir.
    Önceliğe göre sıralar: 1 (kritik) → 2 (önemli) → 3 (bilgi)
    """
    sorular = []
    sorular += _sorular_bilanco_kalitesi(bs, skor_sonuc)
    sorular += _sorular_karlilik(bs, skor_sonuc)
    sorular += _sorular_borc_odeme(bs, skor_sonuc)
    sorular += _sorular_teminat(bs, skor_sonuc)
    sorular += _sorular_operasyonel(bs, skor_sonuc)

    # Önceliğe göre sırala
    sorular.sort(key=lambda s: s.oncelik)
    return sorular
