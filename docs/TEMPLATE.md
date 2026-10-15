# TEMPLATE - איך משכפלים את מנוע ה-affiliate לוורטיקל חדש

המטרה: להפעיל ערוץ affiliate חדש (תיקים, שעונים, סניקרס, הלבשה תחתונה...) בכתיבת niche config,
בלי לגעת בקוד המנוע. הערוץ החי `stiletto` (The Stiletto Vault) ממשיך להתנהג בדיוק אותו דבר:
כל ערך שנקרא מה-config יש לו fallback לליטרל המקורי.

## 1. מה משותף (Engine) ומה פר-נישה (Niche)

**משותף - קוד המנוע (`scripts/`, `control/`)**
- Scouting ופילטרים: `daily_heel_scout`, `aliexpress_scout`, `heel_hunter`, `taste_engine`
- Telegram: בחירת מוצר/תמונה דרך עופר (`telegram_sender`, `telegram_bridge`)
- ייצור: `orchestrator`, `space_runner`, `overlay`
- הפצה: `pickup_drop`, `social_publisher` (Zernio), `auto_schedule`, `tiktok_retry`
- אתר ומדידה: `build_site`, `pinterest_csv`, `collect_metrics`
- Control Center (`control/`, פורט 8787)

**פר-נישה - `niches/<id>/`**
- `niche.json` - כל הקונפיג (identity, site, sourcing, publishing, schedule, production, pinterest, compliance)
- `agents/` - `persona.md`, `poses.md`, `stylist.md`, `qa.md` (הבריף של מי מצלמים ואיך)
- `hub.json` - חשבונות וקישורים. **פרטי, ב-gitignore, לעולם לא ל-git**
- `data/` - ריק + README (ראו "מגבלות")
- סודות: רק ב-`scripts/.env` (שמות המשתנים מוגדרים ב-`publishing.env`)

הקריאה בקוד: `from control.niche import cfg` ואז `cfg("publishing.hashtags", <ליטרל נוכחי>)`.
`cfg` אף פעם לא זורק; קובץ חסר או מפתח חסר מחזירים את ה-default. הקריאות עטופות ב-try/except
כך שהסקריפט רץ גם אם `control` לא זמין. הקריאות מתמטמנות (cache) ומתרעננות כשה-mtime של `niche.json` משתנה.

## 2. צ'קליסט: להשיק וורטיקל חדש

1. **Clone**
   ```
   py -3 -m control.niche clone _template handbags "The Handbag Vault"
   ```
   (אפשר גם `clone stiletto <dst> "<שם>"` - ערכים ספציפיים מתרוקנים). נוצרים `niche.json` מרוקן,
   `agents/` עם שלדי TODO, `data/` עם README ו-`hub.json` ריק. הפקודה מדפיסה צ'קליסט.
2. **למלא `niches/<id>/niche.json`** (כל מפתח מתועד ב-`_doc` ב-`niches/_template/niche.json`):
   `identity` (name, product_noun, handle...), `site`, `sourcing` (חיפושי AliExpress או shops),
   `publishing` (hashtags, cta), `schedule`, `pinterest`, `thresholds`.
3. **חשבונות affiliate** - להירשם (Amazon / Awin / Admitad / ...) ולשים deeplink bases ב-`scripts/.env`. עופר נרשם בעצמו; הסוכן לא נרשם.
4. **דומיין + GitHub Pages repo + דפי compliance** - לפי הסעיף `compliance` ב-`niche.json`:
   דומיין משלנו, `about.html`, `disclosure.html`, `contact.html`, `privacy-policy.html`,
   disclosure בפוטר, `rel="sponsored noopener"`, בלי URL בקפשן + `#ad #affiliate`,
   עד 2 פוסטים ביום בחשבון חדש. למלא `site.public_url`, `site.assets_base_url`, `site.pages_repo`, `site.pages_dir`.
5. **Zernio** - לחבר חשבונות Instagram ו-TikTok, ולהוסיף ל-`scripts/.env` את
   `ZERNIO_<ID>_INSTAGRAM_ID` ו-`ZERNIO_<ID>_TIKTOK_ID` (השמות כבר ב-`publishing.env`). `ZERNIO_API_KEY` משותף או נפרד לפי החשבון.
6. **Magnific Space** - לשכפל את ה-Space של stiletto ולהעתיק ל-`production.space_id`
   ול-`production.nodes.*` (input_image, source_creation, ads_list...) את המזהים החדשים. `production.space_label` = שם ה-Space כפי שעופר רואה.
7. **Agents** - לערוך את `niches/<id>/agents/*.md` (כל ה-TODO) ולוודא ש-`production.agents_dir` מצביע אליהם.
8. **Telegram** - bot/chat לנישה (ראו מגבלות).
9. **Scheduled tasks** - לרשום משימות מתוזמנות לסקאוט היומי, לאיסוף ולפרסום (`scripts/register_*.ps1`).
10. **בדיקה**
    ```
    py -3 -m control.niche check <id>
    ```
    חייב לצאת 0. הפקודה בודקת: `identity.name`, `product_noun`, `site.public_url`, sourcing, `production.space_id`,
    קיום שמות משתני הסביבה ב-`scripts/.env` (רק שמות, אף פעם לא ערכים), קבצי agents, ודפי compliance.
11. **הפעלה** - `py -3 -m control.niche use <id>` מחליף את הנישה הפעילה (`niches/active.txt`).
    **שימו לב:** זה מחליף את כל המנוע, לא רק קובץ; ראו מגבלות.

## 3. מגבלות שעדיין גלובליות

- **`data/`** - קבצי state (`approved_catalog.json`, `production_queue.json`, `orchestrator_state.json`...) משותפים. שני ערוצים באותו ריפו יתערבבו.
  עד שיבוצע פיצול לכל נישה, ערוץ שני דורש עותק נפרד של הריפו (clone של התיקייה) עם `active.txt` משלו.
- **`GELEM/`** - תיקיית הגלם והתוצרים משותפת.
- **בוט Telegram יחיד** - `telegram_sender` קורא טוקן/צ'אט אחד מ-`.env`.
- **ריפו אתר יחיד** - `build_site` / `pickup_drop` כותבים ל-`img/` ול-`index.html` בריפו הנוכחי ודוחפים ל-remote יחיד.
- **טקסטים בקוד שנשארו ליטרליים** - זנבות כמו `" · link in bio #ad"` בכותרות TikTok, ושמות המשתנים ב-docstrings.
- **קבצי scouting** (`taste_engine`, `heel_filter`, `heel_hunter`...) עדיין מכוונים לעקבים; המפתחות `sourcing`/`thresholds` נקראים, אבל פילטר המוצר עצמו (heel_filter) הוא ספציפי.

## 4. הצעדים הבאים (מתוכנן)

1. `data_dir` לכל נישה: `cfg("paths.data", "data")` בכל הסקריפטים + מיגרציה של stiletto.
2. Telegram bot/chat לכל נישה (`publishing.telegram.*`).
3. פילטר מוצר גנרי (`sourcing.filter`) במקום `heel_filter`.
4. `agents_dir` נקרא ישירות על ידי סוכן הייצור (כרגע הנתיב מועבר בפרומפטים ב-`produce_queue.md`).
5. ריפו אתר לכל נישה (`site.pages_repo` כיעד push).
6. Control Center: בורר נישה פעילה + כפתור `check`.
