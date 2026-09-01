"""Строки интерфейса витрины.

Обзорная страница — по-английски (общая для всех). Страница раздела говорит
на языке раздела: ключ — spec.lang. Отсутствующий перевод падает в английский;
тест на полноту словаря лежит в tests/test_i18n.py — новый язык без полного
набора строк не пройдёт CI.
"""

from __future__ import annotations

LANGS = ("en", "ru", "de", "uk", "zh", "it", "ja")

S: dict[str, dict[str, str]] = {
    "site_title": {
        "en": "talk-snapshots: what happens to articles nominated for deletion",
        "ru": "talk-snapshots: что происходит со статьями после номинации на удаление",
        "de": "talk-snapshots: Was mit zur Löschung vorgeschlagenen Artikeln geschieht",
        "uk": "talk-snapshots: що відбувається зі статтями після номінації на вилучення",
        "zh": "talk-snapshots：条目被提删之后的命运",
        "it": "talk-snapshots: cosa succede alle voci proposte per la cancellazione",
        "ja": "talk-snapshots: 削除依頼された記事のゆくえ",
    },
    "updated": {
        "en": "Updated {date} UTC", "ru": "Обновлено {date} UTC", "de": "Stand: {date} UTC",
        "uk": "Оновлено {date} UTC", "zh": "更新于 {date} UTC", "it": "Aggiornato il {date} UTC",
        "ja": "更新: {date} UTC",
    },
    "sources": {
        "en": "data: discussions (DiscussionTools), deletion logs and page state (Wikimedia database replicas)",
        "ru": "данные: обсуждения (DiscussionTools), журналы удалений и состояние страниц (реплики баз Wikimedia)",
        "de": "Daten: Diskussionen (DiscussionTools), Lösch-Logbücher und Seitenstatus (Wikimedia-Datenbankreplikate)",
        "uk": "дані: обговорення (DiscussionTools), журнали вилучень і стан сторінок (репліки баз Wikimedia)",
        "zh": "数据来源：讨论（DiscussionTools）、删除日志与页面状态(Wikimedia 数据库副本)",
        "it": "dati: discussioni (DiscussionTools), registri di cancellazione e stato delle pagine (repliche dei database Wikimedia)",
        "ja": "データ: 議論 (DiscussionTools)、削除記録とページ状態 (Wikimedia データベースレプリカ)",
    },
    "code": {"en": "code", "ru": "код", "de": "Quellcode", "uk": "код", "zh": "源代码", "it": "codice", "ja": "ソースコード"},
    "overview": {"en": "All wikis", "ru": "Все разделы", "de": "Alle Wikis", "uk": "Усі розділи",
                 "zh": "所有语言版本", "it": "Tutte le wiki", "ja": "全言語版"},
    "note": {
        "en": "<b>Page fate</b> comes from the logs: exists / deleted / redirect / renamed. <b>Discussion outcome</b> is "
              "what the closers wrote — a different thing: an article can be kept at the discussion and speedily deleted a "
              "month later. “In discussion” = no outcome yet and the nomination is under two weeks old; “no outcome” = older, "
              "with neither an outcome nor a log entry. Non-articles (categories, templates, project pages) are not counted.",
        "ru": "<b>Судьба страницы</b> — по журналам: существует / удалена / перенаправление / переименована. <b>Исход "
              "обсуждения</b> — что записали подводившие итог; это разные вещи: статью могут оставить итогом и удалить быстро "
              "через месяц. «Обсуждается» — итога нет и номинации меньше двух недель; «висит» — старше двух недель без итога и "
              "без записи в журнале. Не-статьи (категории, шаблоны, проектные страницы) в судьбу не входят.",
        "de": "<b>Schicksal der Seite</b> laut Logbüchern: vorhanden / gelöscht / Weiterleitung / verschoben. <b>Ergebnis der "
              "Diskussion</b> ist, was die Abarbeitenden notiert haben — nicht dasselbe: ein Artikel kann behalten und einen "
              "Monat später schnellgelöscht werden. „In Diskussion“ = noch kein Ergebnis, Nominierung jünger als zwei Wochen; "
              "„ohne Ergebnis“ = älter, ohne Ergebnis und ohne Logbucheintrag. Nicht-Artikel zählen nicht mit.",
        "uk": "<b>Доля сторінки</b> — за журналами: існує / вилучена / перенаправлення / перейменована. <b>Підсумок "
              "обговорення</b> — що записали підбивачі; це різні речі: статтю можуть залишити підсумком і швидко вилучити "
              "за місяць. «Обговорюється» — підсумку немає і номінації менше двох тижнів; «висить» — старша, без підсумку та "
              "без запису в журналі. Не-статті (категорії, шаблони, проєктні сторінки) не враховуються.",
        "zh": "<b>页面命运</b>来自日志：存在 / 已删除 / 重定向 / 已移动。<b>讨论结果</b>是结案者写下的结论——两者不同：条目可能先被保留，一个月后又被快速删除。"
              "“讨论中”＝尚无结果且提删不足两周；“无结果”＝超过两周且既无结果也无日志记录。非条目页面（分类、模板、项目页）不计入。",
        "it": "<b>Sorte della pagina</b> dai registri: esiste / cancellata / redirect / rinominata. <b>Esito della "
              "discussione</b> è ciò che hanno scritto i chiusori — cosa diversa: una voce può essere mantenuta e cancellata "
              "in immediata un mese dopo. «In discussione» = nessun esito e nomina più giovane di due settimane; «senza esito» "
              "= più vecchia, senza esito né voce di registro. Le non-voci non sono conteggiate.",
        "ja": "<b>ページの結末</b>は記録から: 存在 / 削除済み / リダイレクト / 改名。<b>議論の結果</b>は閉じた人が書いた結論で、別物です — "
              "存続と決まった記事が翌月に即時削除されることもあります。「議論中」= 結果がなく依頼から2週間未満。「結果なし」= それより古く、"
              "結果も記録もないもの。記事以外(カテゴリ、テンプレート等)は数えません。",
    },
    "meta_line": {
        "en": "nominations {a} — {b}; article pages {n}; group nominations {g}, non-articles {na}",
        "ru": "номинации {a} — {b}; страниц-статей {n}; групповых номинаций {g}, не-статей {na}",
        "de": "Nominierungen {a} — {b}; Artikelseiten {n}; Sammelnominierungen {g}, Nicht-Artikel {na}",
        "uk": "номінації {a} — {b}; сторінок-статей {n}; групових номінацій {g}, не-статей {na}",
        "zh": "提删 {a} — {b}；条目页 {n}；批量提删 {g}，非条目 {na}",
        "it": "nomine {a} — {b}; pagine-voce {n}; nomine multiple {g}, non-voci {na}",
        "ja": "依頼 {a} — {b}、記事ページ {n}、一括依頼 {g}、記事以外 {na}",
    },
    # KPI
    "kpi_nominations": {"en": "nominations", "ru": "номинаций", "de": "Nominierungen", "uk": "номінацій",
                        "zh": "提删数", "it": "nomine", "ja": "依頼数"},
    "kpi_articles": {"en": "articles", "ru": "статей", "de": "Artikel", "uk": "статей", "zh": "条目", "it": "voci", "ja": "記事数"},
    "kpi_comments": {"en": "comments", "ru": "реплик", "de": "Beiträge", "uk": "реплік", "zh": "发言", "it": "interventi", "ja": "発言数"},
    "kpi_participants": {"en": "participants", "ru": "участников", "de": "Beteiligte", "uk": "учасників",
                         "zh": "参与者", "it": "partecipanti", "ja": "参加者数"},
    "kpi_deleted": {"en": "deleted", "ru": "удалено", "de": "gelöscht", "uk": "вилучено", "zh": "已删除", "it": "cancellate", "ja": "削除済み"},
    "kpi_kept": {"en": "kept", "ru": "оставлено", "de": "behalten", "uk": "залишено", "zh": "保留", "it": "mantenute", "ja": "存続"},
    "kpi_open": {"en": "still open", "ru": "ещё открыто", "de": "noch offen", "uk": "ще відкрито", "zh": "未结", "it": "ancora aperte", "ja": "未決"},
    # заголовки графиков
    "ch_week": {"en": "Fate of articles by nomination week", "ru": "Судьба статей по неделям номинации",
                "de": "Schicksal der Artikel nach Nominierungswoche", "uk": "Доля статей за тижнями номінації",
                "zh": "按提删周划分的条目命运", "it": "Sorte delle voci per settimana di nomina", "ja": "依頼週ごとの記事の結末"},
    "ch_share": {"en": "Fate of articles (share)", "ru": "Судьба статей (часть от целого)",
                 "de": "Schicksal der Artikel (Anteile)", "uk": "Доля статей (частка від цілого)",
                 "zh": "条目命运（占比）", "it": "Sorte delle voci (quote)", "ja": "記事の結末 (割合)"},
    "all_articles": {"en": "all articles", "ru": "все статьи", "de": "alle Artikel", "uk": "усі статті",
                     "zh": "全部条目", "it": "tutte le voci", "ja": "全記事"},
    "ch_delay": {"en": "Days from nomination to deletion", "ru": "Через сколько дней после номинации удалили",
                 "de": "Tage von der Nominierung bis zur Löschung", "uk": "Днів від номінації до вилучення",
                 "zh": "从提删到删除的天数", "it": "Giorni dalla nomina alla cancellazione", "ja": "依頼から削除までの日数"},
    "ch_outcome": {"en": "Discussion outcomes — what the closers decided", "ru": "Исход обсуждения — что решили люди",
                   "de": "Ergebnis der Diskussion — Entscheidung der Abarbeitenden", "uk": "Підсумок обговорення — що вирішили люди",
                   "zh": "讨论结果——结案者的决定", "it": "Esito della discussione — cosa hanno deciso i chiusori",
                   "ja": "議論の結果 — 決定の内訳"},
    "ch_reasons": {"en": "Deletion grounds (from the log)", "ru": "Основание удаления (по журналу)",
                   "de": "Löschgrund (laut Logbuch)", "uk": "Підстава вилучення (за журналом)",
                   "zh": "删除依据（日志）", "it": "Motivo della cancellazione (dal registro)", "ja": "削除理由 (記録より)"},
    "ch_cpn": {"en": "Comments per nomination", "ru": "Реплик на номинацию", "de": "Beiträge pro Nominierung",
               "uk": "Реплік на номінацію", "zh": "每次提删的发言数", "it": "Interventi per nomina", "ja": "依頼あたりの発言数"},
    "ch_heat": {"en": "When people write (weekday × hour UTC)", "ru": "Когда пишут (день недели × час UTC)",
                "de": "Wann geschrieben wird (Wochentag × Stunde UTC)", "uk": "Коли пишуть (день тижня × година UTC)",
                "zh": "发言时间（星期 × 小时，UTC）", "it": "Quando si scrive (giorno × ora UTC)", "ja": "投稿の時間帯 (曜日 × 時 UTC)"},
    "ch_votes": {"en": "Formal stances in comments", "ru": "Формальные позиции в репликах",
                 "de": "Formale Voten in Beiträgen", "uk": "Формальні позиції в репліках",
                 "zh": "发言中的正式立场", "it": "Posizioni formali negli interventi", "ja": "発言中の投票"},
    "ch_topic": {"en": "Topic × fate", "ru": "Тема × судьба", "de": "Thema × Schicksal", "uk": "Тема × доля",
                 "zh": "主题 × 命运", "it": "Tema × sorte", "ja": "分野 × 結末"},
    "ch_top": {"en": "Most active (bots and temporary accounts excluded)",
               "ru": "Самые активные (боты и временные аккаунты исключены)",
               "de": "Aktivste (ohne Bots und temporäre Konten)", "uk": "Найактивніші (без ботів і тимчасових акаунтів)",
               "zh": "最活跃者（不含机器人与临时账号）", "it": "Più attivi (esclusi bot e utenze temporanee)",
               "ja": "最も活発な参加者 (ボット・仮アカウント除く)"},
    # таблица
    "th_user": {"en": "user", "ru": "участник", "de": "Konto", "uk": "користувач", "zh": "用户", "it": "utente", "ja": "利用者"},
    "th_comments": {"en": "comments", "ru": "реплик", "de": "Beiträge", "uk": "реплік", "zh": "发言", "it": "interventi", "ja": "発言"},
    "th_nominations": {"en": "nominations", "ru": "номинаций", "de": "Nominierungen", "uk": "номінацій",
                       "zh": "提删", "it": "nomine", "ja": "依頼"},
    "th_closes": {"en": "closes", "ru": "итогов", "de": "Abschlüsse", "uk": "підсумків", "zh": "结案", "it": "chiusure", "ja": "対処"},
    # судьба
    "life_discussing": {"en": "in discussion", "ru": "обсуждается", "de": "in Diskussion", "uk": "обговорюється",
                        "zh": "讨论中", "it": "in discussione", "ja": "議論中"},
    "life_hanging": {"en": "no outcome", "ru": "висит без итога", "de": "ohne Ergebnis", "uk": "висить без підсумку",
                     "zh": "无结果", "it": "senza esito", "ja": "結果なし"},
    "life_kept": {"en": "kept", "ru": "оставлена", "de": "behalten", "uk": "залишена", "zh": "保留", "it": "mantenuta", "ja": "存続"},
    "life_deleted": {"en": "deleted", "ru": "удалена", "de": "gelöscht", "uk": "вилучена", "zh": "已删除", "it": "cancellata", "ja": "削除"},
    "life_redirect": {"en": "redirect", "ru": "перенаправление", "de": "Weiterleitung", "uk": "перенаправлення",
                      "zh": "重定向", "it": "redirect", "ja": "リダイレクト"},
    "life_moved": {"en": "renamed", "ru": "переименована", "de": "verschoben", "uk": "перейменована",
                   "zh": "已移动", "it": "rinominata", "ja": "改名"},
    "life_recreated": {"en": "deleted and recreated", "ru": "удалена и пересоздана", "de": "gelöscht und neu angelegt",
                       "uk": "вилучена й перестворена", "zh": "删后重建", "it": "cancellata e ricreata", "ja": "削除後再作成"},
    "life_missing": {"en": "not found", "ru": "не найдена", "de": "nicht gefunden", "uk": "не знайдена",
                     "zh": "未找到", "it": "non trovata", "ja": "不明"},
    "life_open": {"en": "open", "ru": "открыта", "de": "offen", "uk": "відкрита", "zh": "未结", "it": "aperta", "ja": "未決"},
    # исход обсуждения
    "out_delete": {"en": "delete", "ru": "удалить", "de": "löschen", "uk": "вилучити", "zh": "删除", "it": "cancellare", "ja": "削除"},
    "out_keep": {"en": "keep", "ru": "оставить", "de": "behalten", "uk": "залишити", "zh": "保留", "it": "mantenere", "ja": "存続"},
    "out_redirect": {"en": "redirect", "ru": "перенаправить", "de": "Weiterleitung", "uk": "перенаправити",
                     "zh": "重定向", "it": "redirect", "ja": "リダイレクト化"},
    "out_merge": {"en": "merge", "ru": "объединить", "de": "zusammenführen", "uk": "об'єднати", "zh": "合并", "it": "unire", "ja": "統合"},
    "out_rename": {"en": "rename", "ru": "переименовать", "de": "umbenennen", "uk": "перейменувати", "zh": "移动", "it": "rinominare", "ja": "改名"},
    "out_moved": {"en": "move out", "ru": "перенести", "de": "auslagern", "uk": "перенести", "zh": "移出", "it": "spostare", "ja": "移動"},
    "out_withdrawn": {"en": "withdrawn", "ru": "снята", "de": "zurückgezogen", "uk": "знято", "zh": "撤回", "it": "ritirata", "ja": "取り下げ"},
    "out_other": {"en": "other", "ru": "иное", "de": "sonstiges", "uk": "інше", "zh": "其他", "it": "altro", "ja": "その他"},
    "out_revdel": {"en": "revision deletion", "ru": "удаление версий", "de": "Versionslöschung", "uk": "вилучення версій",
                   "zh": "修订版本删除", "it": "cancellazione di versioni", "ja": "版指定削除"},
    "out_relisted": {"en": "relisted", "ru": "продлена", "de": "verlängert", "uk": "продовжена", "zh": "重新提交", "it": "riproposta", "ja": "再提出"},
    # причины
    "reason_discussion": {"en": "discussion outcome", "ru": "итог обсуждения", "de": "Löschdiskussion", "uk": "підсумок обговорення",
                          "zh": "讨论结果", "it": "esito della discussione", "ja": "議論の結果"},
    "reason_speedy": {"en": "speedy", "ru": "быстрое", "de": "Schnelllöschung", "uk": "швидке", "zh": "快速删除", "it": "immediata", "ja": "即時削除"},
    "reason_other": {"en": "other", "ru": "другое", "de": "sonstiges", "uk": "інше", "zh": "其他", "it": "altro", "ja": "その他"},
    # разное
    "no_data": {"en": "no data yet", "ru": "данных ещё нет", "de": "noch keine Daten", "uk": "даних ще немає",
                "zh": "暂无数据", "it": "ancora nessun dato", "ja": "データなし"},
    "comments_short": {"en": "{n} comments", "ru": "{n} реплик", "de": "{n} Beiträge", "uk": "{n} реплік",
                       "zh": "{n} 条发言", "it": "{n} interventi", "ja": "{n} 件の発言"},
    "week_of": {"en": "week of {date}", "ru": "неделя с {date}", "de": "Woche ab {date}", "uk": "тиждень від {date}",
                "zh": "{date} 起的一周", "it": "settimana dal {date}", "ja": "{date} からの週"},
    "of_total": {"en": "{n} of {total}", "ru": "{n} из {total}", "de": "{n} von {total}", "uk": "{n} з {total}",
                 "zh": "{total} 中的 {n}", "it": "{n} su {total}", "ja": "{total} 件中 {n}"},
    "weekdays": {"en": "Mon|Tue|Wed|Thu|Fri|Sat|Sun", "ru": "Пн|Вт|Ср|Чт|Пт|Сб|Вс", "de": "Mo|Di|Mi|Do|Fr|Sa|So",
                 "uk": "Пн|Вт|Ср|Чт|Пт|Сб|Нд", "zh": "一|二|三|四|五|六|日", "it": "lun|mar|mer|gio|ven|sab|dom",
                 "ja": "月|火|水|木|金|土|日"},
    # обзор
    "ov_lead": {"en": "Deletion discussions across Wikipedias, one pipeline: who nominates, who argues, and what actually "
                      "happens to the pages — from the discussions themselves and the deletion logs. Wikis ordered by volume.",
                "ru": "Обсуждения удаления в разных Википедиях одним конвейером: кто номинирует, кто спорит и что реально "
                      "происходит со страницами — по самим обсуждениям и журналам удалений. Разделы упорядочены по объёму.",
                "de": "", "uk": "", "zh": "", "it": "", "ja": ""},
    "ov_fate": {"en": "Fate of nominated articles (July 1 onwards)", "ru": "Судьба номинированных статей (с 1 июля)",
                "de": "", "uk": "", "zh": "", "it": "", "ja": ""},
    "ov_hint": {"en": "click a wiki for the full picture in its own language",
                "ru": "клик по разделу — полная картина на языке раздела",
                "de": "", "uk": "", "zh": "", "it": "", "ja": ""},
}


def t(lang: str, key: str, **fmt) -> str:
    entry = S[key]
    text = entry.get(lang) or entry["en"]
    return text.format(**fmt) if fmt else text


def weekdays(lang: str) -> list[str]:
    return t(lang, "weekdays").split("|")
