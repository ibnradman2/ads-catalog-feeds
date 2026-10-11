# -*- coding: utf-8 -*-
r"""ترجمة تسميات custom_label_0..3 في ملفات اللغات (أمر المالك 2026-10-11: لا بيانات بغير لغة الملف).
القيمة التي لا ترجمة لها تُحذف من الملف ولا تبقى عربية، وتظهر في ملخص التشغيل فتُضاف هنا."""
L = ["en", "hi", "tl", "id", "fr", "tr", "zh", "es", "it", "pt"]
TIER = {  # «أداء أ/ب/ج/د»
    "en": ("Performance", "ABCD"), "hi": ("प्रदर्शन", ["ए", "बी", "सी", "डी"]), "tl": ("Pagganap", "ABCD"),
    "id": ("Kinerja", "ABCD"), "fr": ("Performance", "ABCD"), "tr": ("Performans", "ABCD"), "zh": ("表现", ["甲", "乙", "丙", "丁"]), "es": ("Rendimiento", "ABCD"), "it": ("Prestazioni", "ABCD"), "pt": ("Desempenho", "ABCD")}
TIER_AR = {"أ": 0, "ب": 1, "ج": 2, "د": 3}
SEASON = {  # custom_label_1
    "دائم": dict(en="Year-round", hi="पूरे साल", tl="Buong taon", id="Sepanjang tahun", fr="Toute l'année", tr="Tüm yıl", zh="全年", es="Todo el año", it="Tutto l'anno", pt="O ano todo"),
    "الشتاء": dict(en="Winter", hi="सर्दी", tl="Taglamig", id="Musim dingin", fr="Hiver", tr="Kış", zh="冬季", es="Invierno", it="Inverno", pt="Inverno"),
    "اليوم الوطني": dict(en="National Day", hi="राष्ट्रीय दिवस", tl="Pambansang Araw", id="Hari Nasional", fr="Fête nationale", tr="Ulusal Gün", zh="国庆日", es="Día Nacional", it="Festa Nazionale", pt="Dia Nacional"),
    "يوم التأسيس": dict(en="Founding Day", hi="स्थापना दिवस", tl="Araw ng Pagkakatatag", id="Hari Pendirian", fr="Journée de la fondation", tr="Kuruluş Günü", zh="建国日", es="Día de la Fundación", it="Giorno della Fondazione", pt="Dia da Fundação"),
    "رمضان": dict(en="Ramadan", hi="रमज़ान", tl="Ramadan", id="Ramadan", fr="Ramadan", tr="Ramazan", zh="斋月", es="Ramadán", it="Ramadan", pt="Ramadã"),
    "العيد": dict(en="Eid", hi="ईद", tl="Eid", id="Idulfitri", fr="Aïd", tr="Bayram", zh="开斋节", es="Eid", it="Eid", pt="Eid"),
}
BAND = {  # custom_label_2 بترتيب: أقل من 100، 100 إلى 299، 300 إلى 599، 600 فأكثر
    "en": ("Under 100", "100 to 299", "300 to 599", "600 and above"),
    "hi": ("100 से कम", "100 से 299", "300 से 599", "600 और अधिक"),
    "tl": ("Wala pang 100", "100 hanggang 299", "300 hanggang 599", "600 pataas"),
    "id": ("Di bawah 100", "100 hingga 299", "300 hingga 599", "600 ke atas"),
    "fr": ("Moins de 100", "100 à 299", "300 à 599", "600 et plus"),
    "tr": ("100'ün altı", "100 ila 299", "300 ila 599", "600 ve üzeri"),
    "zh": ("100以下", "100至299", "100至299", "600及以上")}
BAND["it"] = ("Meno di 100", "da 100 a 299", "da 300 a 599", "600 e oltre")
BAND["pt"] = ("Menos de 100", "100 a 299", "300 a 599", "600 ou mais")
BAND["es"] = ("Menos de 100", "100 a 299", "300 a 599", "600 o más")
BAND["zh"] = ("100以下", "100至299", "300至599", "600及以上")
BAND_AR = ["أقل من 100", "100 إلى 299", "300 إلى 599", "600 فأكثر"]
FAM_AR = ["عسل آخر", "مجرى أبيض", "زهور", "سدر", "سمرة", "مشتقات النحل", "سمن", "تمور", "دقيق", "بهارات وأعشاب",
          "طلح", "فواكه مجففة", "خلطات العسل", "خل", "عناية بالبشرة", "هدايا", "مشروب عسل", "مانوكا", "زعفران",
          "زيوت", "مكسرات وبذور", "طحينة", "منقوعات", "بن وقهوة", "هيل"]
FAM = {  # custom_label_3 بترتيب FAM_AR
    "en": ["Other Honey", "White Majra Honey", "Flower Honey", "Sidr Honey", "Samra Honey", "Bee Products", "Ghee", "Dates", "Flour", "Spices and Herbs", "Talh Honey", "Dried Fruits", "Honey Blends", "Vinegar", "Skin Care", "Gifts", "Honey Drink", "Manuka", "Saffron", "Oils", "Nuts and Seeds", "Tahini", "Infusions", "Coffee", "Cardamom"],
    "hi": ["अन्य शहद", "सफेद मजरा शहद", "फूलों का शहद", "सिदर शहद", "समरा शहद", "मधुमक्खी उत्पाद", "घी", "खजूर", "आटा", "मसाले और जड़ी-बूटियाँ", "तलह शहद", "सूखे फल", "शहद मिश्रण", "सिरका", "त्वचा की देखभाल", "उपहार", "शहद पेय", "मनुका", "केसर", "तेल", "मेवे और बीज", "ताहिनी", "हर्बल इन्फ्यूज़न", "कॉफ़ी", "इलायची"],
    "tl": ["Ibang Pulot-pukyutan", "Puting Majra na Pulot", "Pulot ng Bulaklak", "Pulot ng Sidr", "Pulot ng Samra", "Produkto ng Bubuyog", "Ghee", "Datiles", "Harina", "Pampalasa at Halamang-gamot", "Pulot ng Talh", "Pinatuyong Prutas", "Halo ng Pulot", "Suka", "Pangangalaga sa Balat", "Regalo", "Inuming Pulot", "Manuka", "Safron", "Mga Langis", "Mani at Buto", "Tahini", "Herbal na Pagbubuhos", "Kape", "Kardamono"],
    "id": ["Madu Lainnya", "Madu Majra Putih", "Madu Bunga", "Madu Sidr", "Madu Samra", "Produk Lebah", "Ghee", "Kurma", "Tepung", "Rempah dan Herbal", "Madu Talh", "Buah Kering", "Campuran Madu", "Cuka", "Perawatan Kulit", "Hadiah", "Minuman Madu", "Manuka", "Saffron", "Minyak", "Kacang dan Biji", "Tahini", "Seduhan Herbal", "Kopi", "Kapulaga"],
    "fr": ["Autres miels", "Miel Majra blanc", "Miel de fleurs", "Miel de Sidr", "Miel de Samra", "Produits de la ruche", "Ghee", "Dattes", "Farine", "Épices et herbes", "Miel de Talh", "Fruits secs", "Mélanges de miel", "Vinaigre", "Soins de la peau", "Cadeaux", "Boisson au miel", "Manuka", "Safran", "Huiles", "Noix et graines", "Tahini", "Infusions", "Café", "Cardamome"],
    "tr": ["Diğer Ballar", "Beyaz Mecra Balı", "Çiçek Balı", "Sidr Balı", "Semure Balı", "Arı Ürünleri", "Sade Yağ (Ghee)", "Hurma", "Un", "Baharat ve Bitkiler", "Talh Balı", "Kuru Meyveler", "Bal Karışımları", "Sirke", "Cilt Bakımı", "Hediyeler", "Bal İçeceği", "Manuka", "Safran", "Yağlar", "Kuruyemiş ve Tohumlar", "Tahin", "Bitki Çayları", "Kahve", "Kakule"],
    "zh": ["其他蜂蜜", "白色马吉拉蜂蜜", "花蜜", "西德尔蜂蜜", "萨姆拉蜂蜜", "蜂产品", "酥油", "椰枣", "面粉", "香料与草本", "塔勒蜂蜜", "干果", "蜂蜜混合", "醋", "护肤", "礼品", "蜂蜜饮品", "麦卢卡", "藏红花", "油类", "坚果与种子", "芝麻酱", "草本冲泡", "咖啡", "小豆蔻"],
}
FAM["es"] = ["Otras mieles", "Miel Majra blanca", "Miel de flores", "Miel de Sidr", "Miel de Samra", "Productos de la colmena", "Ghee", "Dátiles", "Harina", "Especias y hierbas", "Miel de Talh", "Frutas secas", "Mezclas de miel", "Vinagre", "Cuidado de la piel", "Regalos", "Bebida de miel", "Manuka", "Azafrán", "Aceites", "Frutos secos y semillas", "Tahini", "Infusiones", "Café", "Cardamomo"]
FAM["it"] = ["Altri mieli", "Miele Majra bianco", "Miele di fiori", "Miele di Sidr", "Miele di Samra", "Prodotti dell'alveare", "Ghee", "Datteri", "Farina", "Spezie ed erbe", "Miele di Talh", "Frutta secca", "Miscele di miele", "Aceto", "Cura della pelle", "Regali", "Bevanda al miele", "Manuka", "Zafferano", "Oli", "Frutta a guscio e semi", "Tahina", "Infusi", "Caffè", "Cardamomo"]
FAM["pt"] = ["Outros méis", "Mel Majra branco", "Mel de flores", "Mel de Sidr", "Mel de Samra", "Produtos da colmeia", "Ghee", "Tâmaras", "Farinha", "Especiarias e ervas", "Mel de Talh", "Frutas secas", "Misturas de mel", "Vinagre", "Cuidados com a pele", "Presentes", "Bebida de mel", "Manuka", "Açafrão", "Óleos", "Nozes e sementes", "Tahine", "Infusões", "Café", "Cardamomo"]
for _l in L:
    assert len(FAM[_l]) == len(FAM_AR), _l


def translate(n, value, lang):
    """قيمة custom_label_<n> العربية بلغة الملف، أو None إن لم توجد ترجمة (فتُحذف)."""
    v = " ".join((value or "").split())
    if lang not in L or not v:
        return None
    if n == 0 and v.startswith("أداء "):
        i = TIER_AR.get(v[5:].strip())
        if i is None:
            return None
        word, letters = TIER[lang]
        return f"{word} {letters[i]}"
    if n == 1:
        return (SEASON.get(v) or {}).get(lang)
    if n == 2:
        return BAND[lang][BAND_AR.index(v)] if v in BAND_AR else None
    if n == 3:
        return FAM[lang][FAM_AR.index(v)] if v in FAM_AR else None
    return None
