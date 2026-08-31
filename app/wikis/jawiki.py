"""ウィキペディア日本語版: 削除依頼 — дневной лог транклюдирует страницу на номинацию.

Позиция — шаблон {{AFD|削除}} / {{AFD|存続}} в начале реплики, рендерится
словом. Закрытие — реплика с фразой «議論の結果、削除 に決定しました»;
её автор — закрывший. Подпись: «2026年7月1日 (水) 05:46 (UTC)».
"""

from ..core.listing import DailyLog
from ..core.outcome import CommentPattern
from ..core.pages import HeadingLinks, TitleAfterPrefix, TitleFromHeading
from ..core.spec import Locale, ReasonClass, WikiSpec
from ..core.stance import VoteWords

MONTHS = {str(i): i for i in range(1, 13)}

WIKI = WikiSpec(
    dbname="jawiki",
    host="ja.wikipedia.org",
    lang="ja",
    locale=Locale(
        months=MONTHS,
        user_prefixes=("利用者", "利用者‐会話", "利用者-会話", "User", "User talk"),
        contrib_prefixes=("特別:投稿記録", "Special:Contributions"),
        namespaces={
            "Wikipedia": 4, "WP": 4, "ノート": 1, "利用者": 2, "利用者‐会話": 3, "Category": 14,
            "Template": 10, "ファイル": 6, "File": 6, "Portal": 100, "モジュール": 828,
            "Help": 12, "下書き": 118, "Wikipedia‐ノート": 5, "Template‐ノート": 11,
            "Category‐ノート": 15, "プロジェクト": 102,
        },
        signature_pattern=(r"(?P<year>\d{4})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日 "
                           r"\([月火水木金土日]\) (?P<hh>\d{2}):(?P<mm>\d{2}) \(UTC\)"),
        known_bots=frozenset({"Bot", "SuperTheoryBot", "Cewbot", "InternetArchiveBot"}),
    ),
    listing=DailyLog("Wikipedia:削除依頼/ログ/{yyyy}年{m}月{d}日", nomination_level=3),
    pages=(
        TitleAfterPrefix("Wikipedia:削除依頼/", strip=r"(?:\s+\d{8}|\s*\(\d+\)|\s+\d+)$"),
        HeadingLinks(only_articles=True),
        TitleFromHeading(strip=r"（.*$"),
    ),
    outcome=CommentPattern(
        pattern=r"議論の結果、\s*(.+?)\s*に決定しました",
        kinds={
            r"即時削除|版指定削除|特定版削除|削除": "delete",
            r"存続": "keep",
            r"リダイレクト": "redirect",
            r"統合": "merge",
            r"移動": "moved",
            r"取り下げ": "withdrawn",
        },
    ),
    stance=VoteWords(("即時削除", "版指定削除", "特定版削除", "削除", "存続", "保留", "却下", "取り下げ"),
                     boundary=False),
    reason=ReasonClass(discussion=r"削除依頼/", speedy=r"即時削除|WP:CSD#?\s*([A-Z]?\d+(?:-\d+)?|全般\d+|記事\d+)"),
)
