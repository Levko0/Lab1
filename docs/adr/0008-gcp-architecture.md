# 8. Cloud Migration to Google Cloud (GCP) for Spry

* Status: Accepted
* Deciders: Levko Zhuraiev
* Date: 2026-11-24

## Context and Problem Statement
By Lab 7, our core project (Spry / SuccessfulSuccess Meetings) runs entirely on AWS and is declaratively managed with HashiCorp Terraform and HCP Terraform. Our AWS architecture leverages AWS-native serverless primitives:
- Static frontend hosted on Amazon S3 behind Amazon CloudFront with ACM HTTPS and AWS WAF.
- Containerized FastAPI backend running in AWS Lambda behind an AWS Lambda Function URL.
- Relational database using Amazon Aurora Serverless v2 PostgreSQL (0–1 ACU) configured to automatically pause when idle.
- Authentication managed by Amazon Cognito User Pool with Google IdP federation.
- Background weekly reporting pipeline orchestrated via EventBridge Scheduler, Amazon SQS, and auxiliary Lambda functions.
- Agenda parsing powered by Anthropic Claude Haiku 4.5 hosted on Amazon Bedrock.

As software architects, we encounter the fundamental question: **What would it take to run this identical system on Google Cloud Platform (GCP), what trade-offs exist across compute, data, and managed services, and what will it cost under various traffic profiles?**

This Architectural Decision Record documents the architectural mapping from AWS to Google Cloud, evaluates trade-offs (specifically regarding relational databases versus serverless document stores and multi-cloud boundaries), and specifies our service selections.

---

## Decision Drivers
* **Architectural Equivalence & Operational Simplicity:** Maintain feature parity (catalog, meetings management, authentication, reports) while minimizing rewrite overhead.
* **Cost Efficiency & Scale-to-Zero:** Preserve near-$0 idle running costs for student/portfolio traffic without sacrificing security or performance.
* **Security & Credential Management:** Eliminate long-lived static service account keys in favor of Google Cloud Application Default Credentials (ADC) locally and Workload Identity Federation in CI/CD.
* **Independent Cloud Lifecycle:** Decouple GCP Terraform state from AWS state into an independent workspace (`gcp/`), ensuring failures in one cloud cannot corrupt the other.

---

## Part 1 — Service-by-Service Mapping & Decision Matrix

| Spry on AWS Component | Google Cloud Counterpart | Decision (Keep / Replace / Drop) | Architectural Differences & Rationale |
| :--- | :--- | :--- | :--- |
| **S3 + CloudFront (Free plan) + WAF** | **Firebase Hosting** | **Replace** | Firebase Hosting provides global SSD-backed CDN caching, automatic managed SSL certificates, and zero-configuration custom domains out of the box. Cloud Storage buckets alone cannot terminate HTTPS on custom apex domains without an external HTTP(S) Load Balancer (which costs ~$18/month base charge). Firebase Hosting's free plan (10 GB storage, 360 MB/day egress) covers Spry completely at $0/month. |
| **Lambda + Function URL (FastAPI)** | **Cloud Run** | **Replace** | Cloud Run is GCP's premier container execution environment. Unlike Lambda, Cloud Run natively accepts raw OCI/Docker container images, removes the need for custom runtime adapters (such as Mangum or AWS Lambda Web Adapter), eliminates the 15-minute invocation ceiling, and automatically injects a managed HTTPS endpoint. It scales to zero (`min-instances = 0`), giving $0 idle cost. |
| **Amazon ECR** | **Artifact Registry** | **Replace** | Modern replacement for Google Container Registry (GCR). Supports Docker format, vulnerability scanning, and fine-grained IAM. Provides 0.5 GB/month free storage, easily accommodating our lightweight multi-stage Python container images. |
| **Aurora Serverless v2 (0–1 ACU, pauses)** | **Cloud SQL for PostgreSQL (`db-f1-micro`)** | **Replace (Core) / Evaluated vs Firestore** | Aurora Serverless v2 pauses to 0 ACUs after idle timeout, yielding $0 compute when inactive. Cloud SQL does **not** auto-pause on idle; it bills $0.0105/hour (~$7.67/month) continuously while running, plus $1.70/month for 10 GB SSD. However, keeping PostgreSQL preserves 100% of our SQLAlchemy async models, foreign key relations, and Alembic migrations without rewriting application logic. |
| **DynamoDB (NoSQL alternative)** | **Firestore (Datastore Mode)** | **Replace (Cost-optimized tier)** | Serverless NoSQL document database billed strictly per operation (reads/writes) and storage. With 50,000 free reads and 20,000 free writes per day, Firestore costs $0/month at student scale. However, it requires abandoning SQL relations, joins, and ACID transactions across disparate entities. |
| **Cognito User Pool + Google IdP** | **Identity Platform (Firebase Authentication)** | **Replace** | Built on Google's Identity Toolkit infrastructure. Provides 50,000 Monthly Active Users (MAUs) under the free tier (compared to Cognito's 10,000 MAUs). Natively integrates with Google OAuth and emits standard OIDC ID/access tokens verifiable by FastAPI. |
| **EventBridge Scheduler** | **Cloud Scheduler** | **Replace** | Fully managed cron service. Provides 3 free jobs per billing account ($0.10/job/month thereafter). Directly triggers Cloud Run HTTP endpoints via OIDC authenticated tokens. |
| **Amazon SQS** | **Cloud Pub/Sub (or Cloud Tasks)** | **Replace** | Cloud Pub/Sub provides high-throughput messaging with push subscriptions that deliver HTTP POST payloads straight to Cloud Run, removing the need for a long-running queue poller. Cloud Tasks is suited for rate-limited job execution. First 10 GiB/month free. |
| **S3 Event → Lambda** | **Cloud Storage + Eventarc → Cloud Run** | **Replace** | Standard event routing bus in GCP. Changes in Cloud Storage buckets publish CloudEvents through Eventarc directly to Cloud Run endpoints with zero intermediate polling code. |
| **Amazon SES** | **Keep SES (or SendGrid / Mailgun)** | **Keep (Multicloud SES)** | Google Cloud does not provide a native first-party SMTP transactional email service; Google officially recommends SendGrid, Mailgun, or retaining AWS SES. We elect to **Keep AWS SES** via standard SMTP credentials stored securely in GCP Secret Manager, demonstrating a pragmatic hybrid cloud pattern. |
| **Bedrock (Claude Haiku 4.5)** | **Vertex AI (Gemini 2.0 Flash / Claude 3.5)** | **Replace** | Vertex AI provides Gemini models natively (with lower latency and cost-effective pricing) as well as Anthropic Claude via Vertex Model Garden. Migrating the agenda parser prompt to Gemini Flash on Vertex AI maintains high extraction fidelity with minimal token costs. |
| **AWS Systems Manager / Secrets Manager** | **Secret Manager** | **Replace** | GCP Secret Manager provides 6 active secret versions and 10,000 API access operations per month under the Always Free tier. Seamlessly mounts secrets as environment variables or files into Cloud Run containers. |
| **Amazon CloudWatch Logs** | **Cloud Logging** | **Replace** | Integrated structured logging (50 GiB/month free ingestion). Captures stdout/stderr from Cloud Run and audit trails without manual agent configuration. |
| **AWS IAM Roles & Policies** | **Google Cloud Service Accounts & IAM** | **Replace** | Principle of least privilege: dedicated service accounts for Terraform pipeline (`terraform-sa`) and Cloud Run runtime (`spry-api-sa`). Workload Identity Federation replaces permanent access keys. |
| **Terraform `aws` Provider** | **Terraform `google` Provider** | **Replace** | Clean declarative HCL using `hashicorp/google` in a isolated workspace (`gcp/`). |

---

## Deep-Dive Architectural Questions

### 1. The Database: Cloud SQL 24/7 vs. Stopping at Night vs. Firestore vs. AWS Aurora Cross-Cloud

We analyzed four distinct architectural strategies for Spry's data tier:

| Strategy | Latency | Monthly Bill (Idle / Normal) | Code & Schema Impact | Architectural Assessment |
| :--- | :--- | :--- | :--- | :--- |
| **A. Cloud SQL (`db-f1-micro`) 24/7** | Lowest (~1–2 ms inside `us-central1` via unix socket) | **~$9.37/mo** ($7.67 compute + $1.70 10GB SSD) | **Zero.** 100% compatibility with current asyncpg, SQLAlchemy models, and Alembic migrations. | **Recommended for production/staging parity.** Guarantees zero code regressions; acceptable for funded projects. |
| **B. Cloud SQL stopped on schedule (e.g. night/weekends)** | Low when awake; High restart delay (~2–3 min boot latency) | **~$3.50–$5.00/mo** (Compute billed only while running; SSD storage $1.70/mo always billed) | **Zero.** Same codebase. Requires Cloud Scheduler + Cloud Function/Run job to issue Cloud SQL Admin API `PATCH` calls. | Good cost compromise, but cold starts render the application completely unavailable during stopped hours. |
| **C. Firestore (NoSQL Document Store)** | Low (~10–25 ms HTTP API) | **$0.00/mo** (Within 50k reads / 20k writes daily free quota) | **High Rewrite.** Complete removal of SQL, joins, foreign keys, and migrations. Requires document data access layer. | **Recommended for strict $0-budget portfolio projects.** Best scale-to-zero economics, but demands database redesign. |
| **D. Cross-Cloud: Cloud Run on GCP → Aurora PostgreSQL on AWS** | High (~40–80 ms cross-region WAN TLS handshake + latency) | **~$0.30/mo** (Aurora paused) + **Egress fees** ($0.09/GB AWS egress to internet) | **Low to Medium.** Database connection string must point across public internet or costly AWS Direct Connect / GCP Interconnect. | **Anti-pattern.** Severe latency penalty on every query, security exposure over public WAN, and egress bandwidth costs negate compute savings. |

**Decision:** For our GCP Terraform reference implementation, we provide **Cloud SQL for PostgreSQL (`db-f1-micro`)** in `gcp/` to guarantee immediate zero-regression compatibility with Spry's relational schema, and document Firestore as the NoSQL scale-to-zero alternative.

---

### 2. Transactional Email: Provider Selection and Secret Management
Google Cloud does not offer an in-house email sending service (unlike AWS SES). Organizations must choose between:
1. **Third-party SaaS (SendGrid / Mailgun / Resend):** Requires creating and funding an external billing relationship.
2. **Hybrid Multi-Cloud AWS SES:** Retaining our existing verified AWS SES identity (`zhuraiev.pn@ucu.edu.ua`).

**Decision:** We select **AWS SES via SMTP / IAM credentials**. 
- **Security & Storage:** The AWS IAM SMTP username and password are stored exclusively in **Google Cloud Secret Manager** (`spry-ses-credentials`).
- **Cloud Run Injection:** Cloud Run references the secret via Secret Manager integration, mounting it as environment variables (`SMTP_USER`, `SMTP_PASSWORD`) at container startup.
- **Zero Disk Exposure:** No credentials reside in the container image, repository, or environment files.

---

### 3. Which of Spry's Features Would We NOT Move, and Why?
1. **Weekly Report Delivery Pipeline (EventBridge + SQS + Lambda Mailer):**
   - *Why Keep on AWS for now:* The existing AWS pipeline leverages native S3 Gateway Endpoints and EventBridge Scheduler with zero idle cost. Rebuilding this on GCP requires configuring Cloud Scheduler, Pub/Sub push topics, and Cloud Run consumer services. While architecturally straightforward, moving it adds operational complexity without adding user-facing business value during the initial core migration.
2. **Bedrock AI Agenda Parser (Claude Haiku 4.5):**
   - *Why Keep on AWS initially:* Our prompt is tuned and validated specifically for Anthropic Claude's XML-tag structuring on Amazon Bedrock. Migrating to Google Vertex AI requires either adapting prompts for Gemini 2.0 Flash or enabling third-party Anthropic partner models in Vertex Model Garden (which are excluded from Google Cloud trial credits). Keeping AI on AWS avoids billing surprises during the trial phase.

---

## Decision Outcome
* Implemented modular GCP infrastructure under `gcp/` using the HashiCorp `google` Terraform provider.
* Standardized compute on **Google Cloud Run (v2)** running our non-Lambda container image with zero-scaling enabled.
* Adopted **Google Cloud SQL for PostgreSQL** for data persistence with credentials managed via **Google Secret Manager**.
* Adopted **Firebase Hosting** for static frontend delivery.

## Consequences
* **Positive:**
  - Container portability: The same unmodified Docker container runs locally in Docker, on Cloud Run, or on Kubernetes.
  - Simplified networking: Cloud Run handles HTTPS termination, custom domains, and concurrency without custom API Gateway route definitions.
  - Generous free tiers on Cloud Run (2M requests/mo) and Identity Platform (50k MAUs).
* **Negative:**
  - Relational database baseline cost: Unlike Aurora Serverless v2, Cloud SQL `db-f1-micro` incurs ~$9.37/month unless explicitly replaced with Firestore or stopped.
  - Multi-cloud overhead: Retaining AWS SES requires managing IAM credentials across both GCP Secret Manager and AWS IAM.
