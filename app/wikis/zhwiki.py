"""中文维基百科: 頁面存廢討論 — одна страница на день (記錄/YYYY/MM/DD).

Номинация — секция `==`; закрытое обсуждение обёрнуто {{delh|結果}} … {{delf}},
результат — в параметре шаблона (нужен вики-текст). Позиции — шаблоны-значки
вида «(-)刪除», «(+)保留», «(▲)改為消歧義». Подпись: «2026年7月1日 (三) 12:00 (UTC)».
"""

from ..core.listing import DayPage
from ..core.outcome import ClosingTemplate
from ..core.pages import HeadingLinks, Subsections, TitleFromHeading
from ..core.spec import Locale, ReasonClass, WikiSpec
from ..core.stance import VoteWords

MONTHS = {str(i): i for i in range(1, 13)}

WIKI = WikiSpec(
    dbname="zhwiki",
    host="zh.wikipedia.org",
    lang="zh",
    locale=Locale(
        months=MONTHS,
        user_prefixes=("User", "User talk", "用户", "用戶", "使用者", "用户讨论", "用戶討論",
                       "使用者討論", "U", "UT"),
        contrib_prefixes=("Special:Contributions", "Special:用户贡献", "特殊:用户贡献",
                          "特殊:用戶貢獻", "特殊:使用者貢獻"),
        namespaces={
            "Wikipedia": 4, "WP": 4, "维基百科": 4, "維基百科": 4, "Talk": 1, "User": 2,
            "User talk": 3, "Category": 14, "分类": 14, "分類": 14, "Template": 10, "模板": 10,
            "File": 6, "文件": 6, "檔案": 6, "Portal": 100, "主题": 100, "主題": 100,
            "Module": 828, "模块": 828, "模組": 828, "Draft": 118, "草稿": 118, "Help": 12,
            "帮助": 12, "幫助": 12, "Wikipedia talk": 5, "Template talk": 11, "Category talk": 15,
        },
        signature_pattern=(r"(?P<year>\d{4})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日 "
                           r"\([一二三四五六日]\) (?P<hh>\d{2}):(?P<mm>\d{2}) \(UTC\)"),
        known_bots=frozenset({"Jimmy-bot", "Cewbot", "Liangent-bot", "A2093064-bot", "InternetArchiveBot"}),
        noise_patterns=(r"xfd_relist", r"mw-archivedtalk"),
    ),
    listing=DayPage("Wikipedia:頁面存廢討論/記錄/{yyyy}/{mm}/{dd}", nomination_level=2),
    pages=(Subsections(), HeadingLinks(), TitleFromHeading()),
    outcome=ClosingTemplate(
        pattern=r"\{\{\s*delh\s*\|\s*([^}|]+)",
        kinds={
            # коды {{delh|…}}: d/sd — удалено, k/sk/nc/tk/ir — оставлено, rr/r — перенаправление,
            # merge* — объединено, relist — продлено (берётся ПОСЛЕДНИЙ delh секции)
            r"^s?d\s*$|快速?刪除|快速?删除|刪除|删除": "delete",
            r"^s?k\s*$|^nc\s*$|^tk\s*$|^ir\s*$|保留|無共識|无共识": "keep",
            r"^rr?\s*$|重定向|重新導向": "redirect",
            r"^merge\w*\s*$|^m\s*$|合併|合并": "merge",
            r"移動|移动|移至|草稿化": "moved",
            r"^w\s*$|撤回|撤销|撤銷": "withdrawn",
            r"^relist\s*$|重新提交|改為|改为|消歧義|消歧义": "other",
        },
    ),
    stance=VoteWords(
        ("快速刪除", "快速删除", "刪除", "删除", "保留", "重定向", "合併", "合并", "改為消歧義",
         "改为消歧义", "移动", "移動", "草稿化"),
        boundary=False,
        prefix=r"(?:[（(][^）)]{0,4}[）)]\s*)?",
    ),
    reason=ReasonClass(discussion=r"頁面存廢討論|页面存废讨论|存废讨论|存廢討論", speedy=r"\b(?:CSD|快速删除|快速刪除)\s*#?\s*([A-Z]\d+|[A-Z]+\d*)"),
    label="中文维基百科 — 頁面存廢討論",
)
