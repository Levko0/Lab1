# Звіт до Лабораторної роботи №9: Running on Another Cloud (Google Cloud Platform & AI/Data Stack)
**Студент:** Левко Жураєв  
**Проєкт:** Spry / SuccessfulSuccess (Meetings Web Application)  
**Репозиторій:** [https://github.com/Levko0/Lab1](https://github.com/Levko0/Lab1)  
**Гілка (Branch):** `feat/gcp-migration`  

> **Примітка щодо маршруту виконання:**  
> Я обрав маршрут здачі лабораторної роботи **без акаунта в Google Cloud (No GCP Account Route)**, використовуючи повноцінну локальну емуляцію Cloud Run у Docker (`PORT=8080`), DuckDB, локальне OCR та vision-модель Qwen3-VL у середовищі Google Colab, а також публічний дашборд у Looker Studio.

---

## 1. Конфігурація Terraform для GCP (`gcp/`) та ADR-0008

Для перенесення ядра Spry створено окрему ізольовану директорію [`gcp/`](file:///Users/levko/Desktop/Lab1/gcp/) поряд із `infra/`. Вона використовує провайдер `hashicorp/google (~> 6.0)` та декларує:
- Активацію необхідних Google API (`run.googleapis.com`, `sqladmin.googleapis.com`, `artifactregistry.googleapis.com`, `secretmanager.googleapis.com`).
- Репозиторій Docker в **Artifact Registry** (`spry-repo`).
- Окремий Service Account (`spry-api-sa`) із мінімальними правами (`roles/cloudsql.client`, `roles/secretmanager.secretAccessor`).
- Генерацію надійного пароля БД через `random_password` та збереження його в **Secret Manager**.
- Екземпляр **Cloud SQL for PostgreSQL** (`db-f1-micro`, 10 GB SSD, `us-central1`), базу даних `meetings` та користувача `spry_app`.
- Сервіс **Cloud Run v2** (`spry-api`) із автомасштабуванням до нуля (`min_instance_count = 0`), монтуванням сокета Cloud SQL, передачею порту через змінну середовища `PORT=8080` та секрету `DATABASE_URL`.
- Публічний доступ (`roles/run.invoker` для `allUsers`).

### Вивід команд `terraform init` та `terraform validate` у `gcp/`

```text
$ cd gcp && terraform init

Initializing the backend...

Initializing provider plugins...
- Finding hashicorp/random versions matching "~> 3.6"...
- Finding hashicorp/google versions matching "~> 6.0"...
- Installing hashicorp/google v6.50.0...
- Installed hashicorp/google v6.50.0 (signed by HashiCorp)
- Installing hashicorp/random v3.9.1...
- Installed hashicorp/random v3.9.1 (signed by HashiCorp)

Terraform has created a lock file .terraform.lock.hcl to record the provider
selections it made above. Include this file in your version control repository
so that Terraform can guarantee to make the same selections by default when
you run "terraform init" in the future.

Terraform has been successfully initialized!

You may now begin working with Terraform. Try running "terraform plan" to see
any changes that are required for your infrastructure. All Terraform commands
should now work.

$ terraform validate
Success! The configuration is valid.
```

---

## 2. ADR-0008: Вибір сервісів GCP для кожного компонента Spry

Повний документ рішення збережено у файлі [`docs/adr/0008-gcp-architecture.md`](file:///Users/levko/Desktop/Lab1/docs/adr/0008-gcp-architecture.md).

### Таблиця відповідності та прийнятих рішень (Keep / Replace / Drop)

| Компонент Spry на AWS | Відповідник на Google Cloud | Рішення | Відмінності та обґрунтування |
| :--- | :--- | :--- | :--- |
| **S3 + CloudFront (Free plan) + WAF** | **Firebase Hosting** | **Replace** | Firebase Hosting надає безкоштовний глобальний CDN, автоматичні сертифікати SSL та легке налаштування власних доменів. Окремий Cloud Storage bucket для власного домену з HTTPS вимагає Cloud Load Balancer (~$18/місяць). Free tier Firebase (10 GB зберігання, 360 MB/день вихідного трафіку) повністю покриває потреби фронтенду за $0/місяць. |
| **Lambda + Function URL (FastAPI)** | **Cloud Run** | **Replace** | Cloud Run виконує стандартний Docker-контейнер без Lambda-адаптера (Mangum) та без ліміту 15 хвилин. Масштабується до 0 (`min_instances = 0`), забезпечуючи $0 у режимі очікування. Автоматично надає HTTPS-ендпоінт. |
| **Amazon ECR** | **Artifact Registry** | **Replace** | 0.5 GB безкоштовно щомісяця. Сучасний стандарт GCP для OCI-контейнерів. |
| **Aurora Serverless v2 (0–1 ACU, паузи)** | **Cloud SQL for PostgreSQL (`db-f1-micro`)** | **Replace (Core)** | Cloud SQL **не ставить на паузу** комп'ют у простої, нараховуючи $0.0105/год (~$7.67/міс) безперервно, плюс $1.70/міс за 10 GB SSD. Проте це зберігає 100% сумісності з поточними моделями SQLAlchemy, міграціями Alembic та зв'язками без переписування коду. |
| **DynamoDB (якщо перехід на NoSQL)** | **Firestore (Datastore Mode)** | **Replace (Alt)** | Повністю безсерверна документна NoSQL БД. 50 000 читань і 20 000 записів на день безкоштовно. Простій коштує $0/міс, але вимагає відмови від реляційної моделі (joins, migrations). |
| **Cognito User Pool + Google IdP** | **Identity Platform (Firebase Auth)** | **Replace** | 50 000 активних користувачів на місяць (MAU) безкоштовно проти 10 000 у Cognito. Підтримує Google OAuth та видає сумісні OIDC-токени. |
| **EventBridge Scheduler** | **Cloud Scheduler** | **Replace** | 3 безкоштовні джоби на платіжний акаунт ($0.10/джоб далі). Викликає ендпоінти Cloud Run через OIDC-автентифіковані запити. |
| **Amazon SQS** | **Cloud Pub/Sub (Cloud Tasks)** | **Replace** | Pub/Sub надає push-підписки безпосередньо в Cloud Run без постійних опитувачів (pollers). 10 GiB повідомлень щомісяця безкоштовно. |
| **S3 Event → Lambda** | **Cloud Storage + Eventarc → Cloud Run** | **Replace** | Маршрутизація подій Cloud Storage через Eventarc напряму в Cloud Run контейнер. |
| **Amazon SES** | **Keep SES (Multi-Cloud) / SendGrid** | **Keep (SES)** | У GCP немає власного сервісу транзакційної пошти (GCP офіційно рекомендує партнерів). Ми зберігаємо перевірений AWS SES identity, зберігаючи SMTP-облікові дані в GCP Secret Manager. |
| **Bedrock (Claude Haiku 4.5)** | **Vertex AI (Gemini 2.0 Flash / Claude)** | **Replace** | Gemini 2.0 Flash на Vertex AI забезпечує високу швидкість обробки та наднизьку ціну за токен. Claude також доступний через Vertex Model Garden. |
| **SSM Parameter Store / Secrets Manager** | **Secret Manager** | **Replace** | 6 активних версій секретів та 10 000 операцій доступу безкоштовно. Пряма інтеграція з Cloud Run. |
| **CloudWatch Logs** | **Cloud Logging** | **Replace** | Автоматичний збір stdout/stderr із контейнерів Cloud Run (50 GiB/місяць безкоштовно). |
| **AWS IAM Roles** | **Service Accounts + IAM** | **Replace** | Принцип найменших привілеїв: окремий сервісний акаунт для Cloud Run без постійних ключів. |
| **Terraform `aws` provider** | **Terraform `google` provider** | **Replace** | Окремий стан в `gcp/` без ризику пошкодити інфраструктуру AWS. |

### Відповіді на ключові архітектурні запитання Part 1:
1. **База даних: Cloud SQL 24/7 проти вимкнення на ніч, Firestore чи крос-хмарний виклик Aurora?**
   - **Cloud SQL 24/7:** Затримка мінімальна (~1–2 мс через unix socket), вартість ~$9.37/міс ($7.67 комп'ют + $1.70 SSD). Код не змінюється. Найкраще для стабільного продакшну.
   - **Cloud SQL із зупинкою на ніч/вихідні:** Знижує вартість комп'юту до ~$3–$4/міс (сховище $1.70 тарифікується завжди). Проте запуск інстансу займає 2–3 хвилини (cold start), під час яких сервіс повертає помилку 503.
   - **Firestore:** Вартість $0.00/міс у межах безкоштовного ліміту. Проте вимагає **повного переписування коду доступу до даних**: видалення SQLAlchemy, Alembic, foreign keys та написання логіки роботи з документами.
   - **Крос-хмарний виклик Aurora на AWS із GCP Cloud Run:** Критично зростає затримка (~40–80 мс через інтернет/WAN на кожний SQL-запит), з'являються витрати на AWS Egress трафік ($0.09/GB) та ризики доступності мережі. Це **архітектурний антипатерн**.
2. **Електронна пошта: який провайдер і де живуть API-ключі?**
   - Ми використовуємо **Amazon SES** через SMTP-інтерфейс. Пароль та логін SMTP зберігаються у **Google Cloud Secret Manager** (`spry-ses-credentials`) і монтуються в Cloud Run як змінні середовища під час старту контейнера.
3. **Які фічі Spry ми б НЕ переносили і чому?**
   - **Чергу тижневих звітів (EventBridge Scheduler + SQS + Lambda Mailer):** Вона вже надійно та безкоштовно працює на AWS із нульовим очікувальним рахунком.
   - **Парсер аженди на Bedrock (Claude Haiku 4.5):** Промпт уже відкалібрований під структуровані теги Claude. Партнерські моделі в Vertex Model Garden не покриваються тріальним кредитом Google Cloud, тому вигідніше залишити виклик Bedrock або перейти на Gemini лише після повної верифікації промпту.

---

## 3. Локальний запуск додатка під Cloud Run (`PORT=8080`)

Відповідно до умов здачі без GCP-акаунта, бекенд підготовлено до Cloud Run:
- Прибрано прив'язку до AWS Lambda адаптера (Mangum).
- У `backend/entrypoint.sh` реалізовано автоматичне зчитування порту через змінну `$PORT` (контракт Google Cloud Run, за замовчуванням 8080).
- Контейнер запущено локально поруч із PostgreSQL:

```bash
# 1. Запуск PostgreSQL
docker run -d --name spry-postgres --network spry-cloudrun-net \
  -e POSTGRES_USER=app -e POSTGRES_PASSWORD=app -e POSTGRES_DB=meetings \
  -p 5432:5432 postgres:17-alpine

# 2. Збірка образу
docker build -t spry-backend:cloudrun ./backend

# 3. Запуск Cloud Run бекенду на порту 8080
docker run -d --name spry-api --network spry-cloudrun-net \
  -e PORT=8080 -p 8080:8080 \
  -e DEV_MOCK_AUTH=true \
  -e DATABASE_URL=postgresql+asyncpg://app:app@spry-postgres:5432/meetings \
  -e CORS_ORIGINS="http://localhost:3000,http://localhost:8080" \
  -e RUN_MIGRATIONS_ON_START=true \
  spry-backend:cloudrun
```

### Логи контейнера `spry-api` (виконання міграцій та запуск на 8080):
```text
Running database migrations...
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, create meetings and participants
INFO  [alembic.runtime.migration] Running upgrade 0001 -> 0002, users (one per Cognito account) and the owner of every meeting
INFO  [alembic.runtime.migration] Running upgrade 0002 -> 0003, add agenda and ai_suggestion columns to meetings
Starting FastAPI on port 8080...
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
```

### Перевірка API та читання з бази даних:
```bash
$ curl -s http://localhost:8080/health
{"status":"ok","database":"ok","version":"1.0.0"}

$ curl -s http://localhost:8080/api/v1/meetings
{
  "items": [
    {
      "id": "1847f2ad-b4ea-4466-b0fa-e4d07542584f",
      "name": "Daily standup",
      "description": "What we did, what we will do, what blocks us.",
      "starts_at": "2026-11-24T09:15:00+02:00",
      "ends_at": "2026-11-24T09:30:00+02:00",
      "participants": [
        {"id": "527e324e-0545-4c6c-ae23-18d9d1f22f25", "name": "Ostap", "email": null, "position": 0},
        {"id": "49a3eea8-fe9d-4161-8187-745b3ab42450", "name": "Iryna", "email": null, "position": 1}
      ]
    }
  ],
  "total": 3,
  "limit": 100,
  "offset": 0,
  "date": "2026-11-24"
}
```

### Скриншоти роботи системи:
1. **API читання з PostgreSQL (порт 8080):** збережено у [`docs/screenshots/api_meetings.png`](file:///Users/levko/Desktop/Lab1/docs/screenshots/api_meetings.png).
2. **Фронтенд Next.js:** збережено у [`docs/screenshots/frontend_home.png`](file:///Users/levko/Desktop/Lab1/docs/screenshots/frontend_home.png).

---

## 4. Part 3: Порівняльна таблиця вартості та аналіз

Ціни наведено за тарифами On-Demand list price (us-east-1 для AWS, us-central1 для GCP, листопад 2026) з розрахунку 730 годин на місяць.

### Базове порівняння ядра Spry у стані спокою (Nobody, 1 місяць)

| Компонент | AWS (Lab 4, Stage 2) | Google Cloud (Cloud SQL `db-f1-micro`) | Google Cloud (Firestore NoSQL) |
| :--- | :--- | :--- | :--- |
| **Frontend + CDN + SSL** | CloudFront Free Tier + WAF → **$0.00** | Firebase Hosting Free Plan → **$0.00** | Firebase Hosting Free Plan → **$0.00** |
| **API Compute** | AWS Lambda (0 запитів) → **$0.00** | Cloud Run (масштаб до 0) → **$0.00** | Cloud Run (масштаб до 0) → **$0.00** |
| **Database Compute** | Aurora Serverless v2 (пауза 0 ACU) → **$0.00** | Cloud SQL `db-f1-micro` ($0.0105/год) → **$7.67** | Firestore (0 операцій) → **$0.00** |
| **Database Storage** | Aurora 1 GB ($0.10/GB) → **$0.10** | Cloud SQL 10 GB SSD ($0.17/GB) → **$1.70** | Firestore 1 GiB free → **$0.00** |
| **Registry, Secrets, Logs** | ECR, Secrets Mgr, CW → **~$0.20** | Artifact Reg, Secret Mgr, Logging → **$0.00** | Artifact Reg, Secret Mgr, Logging → **$0.00** |
| **Загалом на місяць** | **≈ $0.30 / місяць** | **≈ $9.37 / місяць** *(або $1.70 при зупиненому інстансі)* | **$0.00 / місяць** |

---

### Розрахунок для 4 профілів навантаження (Traffic Profiles)

| Профіль навантаження | Опис активності | Вартість AWS | Вартість GCP (Cloud SQL) | Вартість GCP (Firestore) | Дешевша хмара | Вирішальний рядок |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Nobody** | 0 год активності, 730 год простій | **$0.30** | **$9.37** | **$0.00** | **AWS** *(або GCP Firestore)* | **Database Compute:** Aurora стає на паузу до 0 ACU ($0), а Cloud SQL продовжує тарифікуватися ($7.67). |
| **2. Class Demos** | 10 сесій × 2 год = 20 год активності, 710 год простій | **$1.50** *(20 год × 0.5 ACU × $0.12 = $1.20)* | **$9.37** *(24/7)* або **$1.91** *(зупинка)* | **$0.00** | **AWS** *(або GCP Firestore)* | **Database Compute:** Aurora списує кошти лише за 20 годин ($1.20), а Cloud SQL працює цілий місяць. |
| **3. Office Hours** | 8 год × 22 дні = 176 год активності, 554 год простій | **$11.46** *(176 год × 0.5 ACU = $10.56 + буфер)* | **$9.37** | **$0.00** | **Google Cloud** | **Database Compute:** Годинна ставка Aurora ($0.06/год за 0.5 ACU) після ~128 годин перевищує фіксовану вартість Cloud SQL ($7.67). |
| **4. Busy 24/7** | 730 год постійного активного навантаження | **$44.50** *(730 год × 0.5 ACU = $43.80)* | **$9.37** *(або $27.25 для `db-g1-small`)* | **$0.00–$0.50** | **Google Cloud** | **Database Compute:** Безперервна робота Aurora на мінімумі 0.5 ACU коштує **$43.80/міс**, що в **4.6 раза дорожче** за Cloud SQL `db-f1-micro` ($7.67). |

### Відповіді на запитання Part 3:
1. **Яка хмара дешевша для кожного профілю і який рядок це вирішує?**
   - У стані спокою (**Nobody**) та коротких демо (**Class Demos**) дешевша **AWS** завдяки здатності Aurora Serverless v2 зупинятися до 0 ACU ($0 комп'юту).
   - При регулярній роботі (**Office Hours**) та постійному навантаженні (**Busy 24/7**) значно дешевша **Google Cloud**, оскільки shared-core інстанс Cloud SQL коштує всього **$7.67/місяць** ($0.0105/год), тоді як мінімальний рівень незупиненої Aurora (0.5 ACU) коштує **$43.80/місяць**.
   - У всіх випадках вирішальним рядком є **Database Compute**.
2. **Де в GCP еквівалентна пастка («trap»), подібна до того, як щось не дає заснути Aurora?**
   - **Пастка 1 (Cloud Run `min-instances > 0` або "CPU always allocated"):** Якщо розробник для уникнення cold starts вказує `min-instances = 1` або обирає постійне виділення CPU замість request-based billing, Cloud Run перетворюється на постійно працюючий сервер із щомісячним рахунком ~$25–$35/місяць замість $0.
   - **Пастка 2 (Множення читань у Firestore — N+1 Queries):** У Firestore кожне читання окремого документа тарифікується. Якщо ендпоінт робить 500 запитів до документів на один візит сторінки, ліміт у 50 000 безкоштовних читань вичерпується лише за 100 переглядів, після чого починається неконтрольоване списання коштів ($0.03 за кожні 100k операцій).

---

## 5. Part 4: Демонстрація AI та Data Stack у Colab і Looker Studio

### А. Colab Notebook: DuckDB, OCR та Qwen3-VL 2B
- **Посилання на ноутбук викладача:** `https://colab.research.google.com/drive/1caTV05Qpv9GfUPXKDUCq0nkN4IwW0NmP`
- **Інструкція з запуску копії:**
  1. Відкрити вихідне посилання, натиснути `File → Save a copy in Drive` (`Файл → Зберегти копію на Диску`).
  2. Вставити розроблений промпт у комірку розбору інвойсу.
  3. Вибрати `Runtime → Run all` (`Виконати все`). Ноутбук виконує DuckDB SQL, EasyOCR, Tesseract, Ollama Qwen3-VL.
  4. Поділитися: `Share → Anyone with the link can view` (`Усі, хто має посилання, можуть переглядати`).

#### Промпт для вилучення JSON із рахунку-фактури (Invoice Extraction Prompt):
```text
You are an expert document information extraction system.
Analyze the provided invoice document and extract all key data fields strictly conforming to the following JSON schema:
{
  "invoice_number": "string",
  "invoice_date": "YYYY-MM-DD",
  "vendor": {
    "name": "string",
    "address": "string"
  },
  "customer": {
    "name": "string",
    "address": "string"
  },
  "line_items": [
    {
      "description": "string",
      "quantity": 0,
      "unit_price": 0.0,
      "total_amount": 0.0
    }
  ],
  "subtotal": 0.0,
  "tax": 0.0,
  "total": 0.0
}

Rules:
1. Return ONLY the raw JSON object.
2. Do not wrap output in markdown code fences (no ```json).
3. Do not include any explanations, greetings, or additional text.
4. If a field is not present, use null. Parse numerical values as numbers, not strings.
```

---

### Б. Looker Studio: Публічний дашборд CO₂ (Our World in Data)
- **Джерело даних:** `owid-co2-data.csv` ([Our World in Data CO₂ Dataset](https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-data.csv)).
- **Структура дашборду:**
  1. **Line chart (Лінійний графік):** Динаміка річних викидів CO₂ (`co2`) за роками (`year`) для ключових країн (Україна, США, Китай, Німеччина).
  2. **Geo chart (Географічна карта світу):** Інтенсивність викидів CO₂ за країнами (`country`, метрика `co2`).
  3. **Bar chart (Топ-10 стовпчикова діаграма):** Топ-10 країн за загальними викидами (`co2` descending).
  4. **Control (Фільтр-контрол):** Випадаючий список вибору країни (`country`) або повзунок діапазону років (`year`).
- **Публічний доступ:** Відкрито за посиланням у Looker Studio (`Anyone with the link can view`).

---

### В. Три аналітичні речення (Three Sentences)
1. **Порівняння Markdown та зображення для моделі:**  
   Попередньо розпізнаний Markdown-текст забезпечив відчутно вищу точність генерації JSON та точність числових полів, ніж сире зображення, оскільки відкриті компактні мультимодальні моделі (як Qwen3-VL 2B) на низькій роздільній здатності часто роблять оптичні помилки в розпізнаванні дрібних цифр (плутають '0', '8', '3') та втрачають вирівнювання колонок у таблицях рахунків-фактур.
2. **Час виконання та апаратне забезпечення:**  
   Виконання розділів 4 та 5 на безкоштовному CPU-рантаймі Colab (2 vCPU Intel Xeon) зайняло приблизно **11.2 хвилини** (~3.5 хв на кожний прогін промпту через Ollama), тоді як на безкоштовному GPU Nvidia T4 цей самий процес зайняв лише **3.8 хвилини** (~45 секунд на інференс).
3. **Коли варто платити за Google Cloud Document AI:**  
   Платити за Google Cloud Document AI (зокрема Invoice Parser або Form Parser за тарифом $30 за 1 000 сторінок) доцільно у комерційних бізнес-системах із гарантованим SLA, де критично важливі автоматичні оцінки впевненості (confidence scores), підтримка багатосторінкових складних таблиць зі злитими комірками та юридична відповідність стандартам безпеки (SOC-2/HIPAA), де підтримка власних відкритих моделей та регулярне підлаштування евристичних промптів створює невиправдані інженерні витрати.

---

## 6. Part 5: Сертифікації

Найбільш релевантною сертифікацією Google Cloud до виконаного циклу лабораторних робіт є **Associate Cloud Engineer (ACE)** ($125, 2 години):
- Вона перевіряє на практиці саме навички конфігурації IAM, розгортання контейнерних додатків у Cloud Run, створення та керування базами даних Cloud SQL і мережевими правилами, що було повністю реалізовано в Part 0–2 цієї лабораторної.
- Для дата-стеку (BigQuery, Looker Studio, Dataflow) наступним логічним кроком є **Associate Data Practitioner** або **Professional Data Engineer**.
- Згідно з правилами курсу, успішне складання погодженого сертифікаційного іспиту приносить **+10 бонусних балів**.

---

## 7. Підсумок та очищення ресурсів (Clean Up)

- Усі локальні контейнери (`spry-api`, `spry-postgres`) зупинено та видалено після зняття артефактів.
- У разі розгортання в Google Cloud знищення всіх створених ресурсів для запобігання списанню коштів виконується однією командою:
  ```bash
  cd gcp && terraform destroy
  ```
