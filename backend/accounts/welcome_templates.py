"""Default welcome-letter templates, one per language.

The default letter is a fixed formal letter of appreciation, so every language
is translated ONCE and stored here as reviewed text — no translation service is
involved at send time for any language listed below. Only a language missing
from ``DEFAULT_LETTERS`` (or a letter the account owner rewrote themselves)
falls back to machine translation; see ``cards/services/welcome_translate.py``.

TRANSLATION PROVENANCE: Arabic and English are the originals supplied by the
ministry. The remaining languages were translated for this platform and SHOULD
BE REVIEWED by a native speaker before being relied upon; each one is only used
when a card is printed in that language.

Every body starts with ``SALUTATION_TOKEN``, replaced at send time with a
salutation tailored to the card holder (see ``cards/services/welcome_text.py``).
An account owner who rewrites the letter may keep the token to keep the
per-card salutation, or drop it to send their own text verbatim.
"""

from __future__ import annotations

SALUTATION_TOKEN = '{{salutation}}'

# Languages written right-to-left, so the email body is rendered with dir="rtl".
RTL_LANGUAGES = {'ar', 'he', 'fa', 'ur', 'ps', 'sd', 'ug', 'ku'}

# ── Arabic (original) ─────────────────────────────────────────────────────────
SUBJECT_AR = 'رسالة شكر وتقدير'
BODY_AR = """{{salutation}}

يطيب لي أن أتقدم إليكم بخالص الشكر والتقدير على زيارتكم الكريمة إلى وزارة الاقتصاد والصناعة، وعلى ما تفضلتم به من وقت واهتمام، وما عكسه اللقاء من روح إيجابية وتقدير متبادل.

إننا نثمّن عاليًا زيارتكم وما أتاحته من فرصة للحوار وتبادل الرؤى والأفكار، ونؤمن بأن تعزيز التواصل والتعاون مع مختلف الفعاليات والجهات يشكل رافدًا مهمًا لدعم مسيرة العمل الاقتصادي والصناعي وخدمة المصلحة العامة.

وإذ نعتز بهذا اللقاء، نتطلع إلى استمرار التواصل وتعزيز جسور التعاون والشراكة، بما يسهم في تحقيق المزيد من التقدم والنجاح.

مع خالص التقدير والاحترام،
نائب وزير الاقتصاد والصناعة
وزارة الاقتصاد والصناعة"""

# ── English (original) ────────────────────────────────────────────────────────
SUBJECT_EN = 'Message of Appreciation'
BODY_EN = """{{salutation}}

It is my pleasure to extend my sincere appreciation and gratitude for your kind visit to the Ministry of Economy and Industry, and for the time and attention you so generously shared with us. Your visit was greatly valued and reflected a spirit of mutual respect and positive engagement.

We highly appreciate this opportunity for dialogue and the exchange of views and ideas. We firmly believe that strengthening communication and cooperation with various stakeholders and institutions is an important foundation for advancing economic and industrial development and serving the public interest.

We greatly value this meeting and look forward to continued communication and to further strengthening the bonds of cooperation and partnership in pursuit of greater progress and shared success.

With our highest appreciation and respect,
Deputy Minister of Economy and Industry
Ministry of Economy and Industry"""

# ── French ───────────────────────────────────────────────────────────────────
SUBJECT_FR = 'Lettre de remerciement'
BODY_FR = """{{salutation}}

Il m'est agréable de vous adresser mes sincères remerciements et ma profonde gratitude pour votre aimable visite au Ministère de l'Économie et de l'Industrie, ainsi que pour le temps et l'attention que vous nous avez si généreusement consacrés, et pour l'esprit positif et le respect mutuel dont cette rencontre a témoigné.

Nous apprécions vivement votre visite et l'occasion qu'elle nous a offerte de dialoguer et d'échanger points de vue et idées. Nous sommes convaincus que le renforcement de la communication et de la coopération avec les différents acteurs et institutions constitue un appui essentiel au développement économique et industriel et au service de l'intérêt général.

Honorés de cette rencontre, nous formons le vœu de poursuivre nos échanges et de consolider les liens de coopération et de partenariat, en vue de nouveaux progrès et de succès partagés.

Avec l'expression de notre plus haute considération,
Le Vice-Ministre de l'Économie et de l'Industrie
Ministère de l'Économie et de l'Industrie"""

# ── German ───────────────────────────────────────────────────────────────────
SUBJECT_DE = 'Dankschreiben'
BODY_DE = """{{salutation}}

es ist mir eine Freude, Ihnen meinen aufrichtigen Dank und meine Anerkennung für Ihren freundlichen Besuch im Ministerium für Wirtschaft und Industrie auszusprechen, ebenso für die Zeit und die Aufmerksamkeit, die Sie uns so großzügig gewidmet haben, und für den positiven Geist und die gegenseitige Wertschätzung, die dieses Treffen geprägt haben.

Wir schätzen Ihren Besuch sowie die damit verbundene Gelegenheit zum Dialog und zum Austausch von Ansichten und Ideen sehr. Wir sind überzeugt, dass die Stärkung der Kommunikation und der Zusammenarbeit mit den verschiedenen Akteuren und Institutionen einen wichtigen Beitrag zur wirtschaftlichen und industriellen Entwicklung und zum Gemeinwohl leistet.

Wir fühlen uns durch dieses Treffen geehrt und freuen uns auf einen fortdauernden Austausch sowie auf die weitere Festigung der Bande der Zusammenarbeit und Partnerschaft, im Interesse weiteren Fortschritts und gemeinsamen Erfolgs.

Mit vorzüglicher Hochachtung,
Der Stellvertretende Minister für Wirtschaft und Industrie
Ministerium für Wirtschaft und Industrie"""

# ── Turkish ──────────────────────────────────────────────────────────────────
SUBJECT_TR = 'Teşekkür Mektubu'
BODY_TR = """{{salutation}}

Ekonomi ve Sanayi Bakanlığına gerçekleştirdiğiniz nazik ziyaretiniz, bize cömertçe ayırdığınız zaman ve gösterdiğiniz ilgi ile görüşmemize yansıyan olumlu ruh ve karşılıklı saygı için en samimi şükranlarımı ve takdirlerimi sunmaktan memnuniyet duyarım.

Ziyaretinizi ve sağladığı diyalog ile görüş ve fikir alışverişi fırsatını büyük bir takdirle karşılıyoruz. Çeşitli kurum ve kuruluşlarla iletişim ve iş birliğinin güçlendirilmesinin, ekonomik ve sınai kalkınmanın ilerletilmesi ve kamu yararına hizmet edilmesi bakımından önemli bir dayanak oluşturduğuna inanıyoruz.

Bu görüşmeden onur duyar, iletişimin sürdürülmesini ve daha fazla ilerleme ile ortak başarı adına iş birliği ve ortaklık bağlarının daha da güçlendirilmesini temenni ederiz.

En derin saygı ve takdirlerimle,
Ekonomi ve Sanayi Bakan Yardımcısı
Ekonomi ve Sanayi Bakanlığı"""

# ── Russian ──────────────────────────────────────────────────────────────────
SUBJECT_RU = 'Благодарственное письмо'
BODY_RU = """{{salutation}}

Мне приятно выразить Вам искреннюю благодарность и признательность за Ваш любезный визит в Министерство экономики и промышленности, а также за время и внимание, которые Вы столь щедро нам уделили, и за дух доброжелательности и взаимного уважения, которым была отмечена наша встреча.

Мы высоко ценим Ваш визит и предоставленную им возможность для диалога и обмена мнениями и идеями. Мы убеждены, что укрепление связей и сотрудничества с различными организациями и учреждениями служит важной опорой для развития экономики и промышленности и для служения общественным интересам.

Дорожа этой встречей, мы надеемся на продолжение общения и на дальнейшее укрепление связей сотрудничества и партнёрства во имя новых успехов и общих достижений.

С глубоким уважением,
Заместитель Министра экономики и промышленности
Министерство экономики и промышленности"""

# ── Spanish ──────────────────────────────────────────────────────────────────
SUBJECT_ES = 'Carta de agradecimiento'
BODY_ES = """{{salutation}}

Me complace expresarles mi más sincero agradecimiento y reconocimiento por su amable visita al Ministerio de Economía e Industria, así como por el tiempo y la atención que generosamente nos han dedicado, y por el espíritu positivo y el respeto mutuo que caracterizaron nuestro encuentro.

Valoramos enormemente su visita y la oportunidad de diálogo y de intercambio de puntos de vista e ideas que ha propiciado. Estamos convencidos de que fortalecer la comunicación y la cooperación con las distintas entidades e instituciones constituye un apoyo fundamental para impulsar el desarrollo económico e industrial y servir al interés general.

Honrados por este encuentro, esperamos mantener la comunicación y seguir estrechando los lazos de cooperación y colaboración, en aras de un mayor progreso y de un éxito compartido.

Con nuestra más alta consideración,
Viceministro de Economía e Industria
Ministerio de Economía e Industria"""

# ── Chinese (Simplified) ─────────────────────────────────────────────────────
SUBJECT_ZH = '感谢函'
BODY_ZH = """{{salutation}}

我谨向您致以最诚挚的感谢与敬意，感谢您拨冗莅临经济与工业部访问，并在会晤中给予我们宝贵的时间与关注；此次会晤所体现的积极氛围与相互尊重，令我们深受鼓舞。

我们高度重视此次访问，以及由此带来的对话与交流意见和思想的机会。我们坚信，加强与各界机构和组织的沟通与合作，是推动经济与工业发展、服务公共利益的重要支撑。

我们对此次会晤深感荣幸，并期待继续保持联系，进一步巩固合作与伙伴关系的纽带，以取得更大的进步与共同的成功。

顺致最崇高的敬意，
经济与工业部副部长
经济与工业部"""

# Reviewed letters, keyed by ISO 639-1 code. A card language present here never
# needs a translation call.
DEFAULT_LETTERS: dict[str, tuple[str, str]] = {
    'ar': (SUBJECT_AR, BODY_AR),
    'en': (SUBJECT_EN, BODY_EN),
    'fr': (SUBJECT_FR, BODY_FR),
    'de': (SUBJECT_DE, BODY_DE),
    'tr': (SUBJECT_TR, BODY_TR),
    'ru': (SUBJECT_RU, BODY_RU),
    'es': (SUBJECT_ES, BODY_ES),
    'zh': (SUBJECT_ZH, BODY_ZH),
}

# Used when the card carries no usable name to address — the wording the ministry
# used before per-card salutations existed.
DEFAULT_SALUTATIONS: dict[str, str] = {
    'ar': 'السادة الضيوف الكرام،',
    'en': 'Dear Esteemed Guests,',
    'fr': 'Mesdames, Messieurs, chers invités,',
    'de': 'Sehr geehrte Gäste,',
    'tr': 'Sayın Konuklarımız,',
    'ru': 'Уважаемые гости,',
    'es': 'Estimados invitados,',
    'zh': '尊敬的各位来宾：',
}


def is_rtl(language: str) -> bool:
    return (language or '').lower() in RTL_LANGUAGES


def default_letter(language: str) -> tuple[str, str] | None:
    """The reviewed (subject, body) for ``language``, or None when we have none."""
    return DEFAULT_LETTERS.get((language or '').lower())


def default_salutation(language: str) -> str:
    return DEFAULT_SALUTATIONS.get((language or '').lower(), DEFAULT_SALUTATIONS['en'])
