# Documentation


## 📘 Fleet Data Platform: Project Documentation
|  |  |
|---|---|
| **Project** | Fleet Data Platform (end-to-end data engineering pipeline) |
| **Team** | Mohamed Bedier, Omar Fathy, Karim Mohamed, Mohamad Farah |
| **GitHub** | ‣ |

---

### How we document (3 rules)
1. Write the step **right after** you finish it, not later.
1. Each step = **what we did** (1 to 3 lines) + **screenshot** (+ code if any).
1. Never show passwords, keys, or tokens. Blur them or use `<YOUR_KEY>`.
**Screenshot naming:** `tool-stepnumber-name.png`
---

## 1. Project Overview ([Data Catalog](/p/404961599a4880f6898eea33b93d731d?pvs=25))
**Goal:** (1 to 2 sentences: what problem does this project solve?)
> Example: Build a pipeline that simulates a US trucking fleet and turns raw data into a dashboard for on-time delivery, fuel cost, and driver performance.
**Pipeline:**
`Python Generator → AWS EC2 → S3 → Airbyte → Snowflake → dbt → Power BI` (orchestrated by **Airflow**)
> 📌 architecture diagram image.
[image: schema-V1.png](attachment:60311514-962e-42d4-9224-676e1979d8eb:schema-V1.png)
| Tool | Role in the project |
|---|---|
| Python | Generates the raw fleet data |
| AWS EC2 | Server that runs the generator and kafka 24/7 |
| AWS S3 | Data lake: stores the raw files |
| Airbyte | Moves data from S3 to Snowflake |
| Snowflake | Data warehouse |
| dbt | Cleans and models the data |
| Airflow | Schedules and runs the whole pipeline |
| Power BI | Dashboard |

---

### Phase 2: AWS Infrastructure & Data Ingestion

#### 2.1 AWS EC2 Setup
We created an AWS EC2 instance to run the project's data generator.
**Instance configuration:**
- **AMI:** Ubuntu Server 24.04 LTS
- **Instance type:** `c7i-flex.large`
- **Compute:** 2 vCPUs and 4 GiB RAM
- **Root storage:** 20 GiB
- **Region:** `us-east-1`

### **Create key pair**
**Key pair name: supplychain-kafka-key-pair**
**Key pair type: **RSA
**Private key file format: **.pem
[image: image.png](attachment:6d3e88d9-0d32-42ed-9089-1a65a8ad4980:image.png)
**Configure storage**
[image: image.png](attachment:1abfdeb0-028b-4d60-baab-f57b51f765f4:image.png)
[header_4] SSH Connection  with SSH
We created an RSA key pair and downloaded the private key in `.pem` format.
On Windows, we configured the key file permissions and connected to the instance using SSH.
```json
icacls "supplychain-project-key-pair.pem" /inheritance:r
```
```json
icacls "supplychain-project-key-pair.pem" /remove "NT AUTHORITY\Authenticated Users"
icacls "supplychain-project-key-pair.pem" /remove "BUILTIN\Users"
icacls "supplychain-project-key-pair.pem" /remove "Everyone"
```
```json
icacls "supplychain-project-key-pair.pem" /grant:r "mohamedbedier:R"
```
```json
ssh -i "D:\Courses\SIC 8\supply-chain-graduation-project\supplychain-project-key-pair.pem" ubuntu@54.89.41.4
```
```json
Are you sure you want to continue connecting (yes/no/[fingerprint])? yes
```
[image: image.png](attachment:27bbc4a7-b6ce-4565-9221-da20337522b1:image.png)

#### Step 4: Install Python
```json
sudo apt update
sudo apt install -y openjdk-17-jdk python3 python3-venv python3-pip unzip curl wget tmux
```
```json
java -version
python3 --version
```
[image: image.png](attachment:f51d6e98-3c32-4f62-88f6-75fd9dfb9183:image.png)

#### 2.3 Apache Kafka Setup
Kafka was configured to use the following topics:
- `fleet.telemetry.v1`
- `fleet.reefer.v1`
The generator's environment configuration points to the local Kafka broker at `localhost:9092`.
```json
cd /opt
sudo wget https://downloads.apache.org/kafka/4.3.1/kafka_2.13-4.3.1.tgz
sudo tar -xzf kafka_2.13-4.3.1.tgz
sudo chown -R ubuntu:ubuntu /opt/kafka_2.13-4.3.1
```
```json
cd /opt/kafka_2.13-4.3.1
```
```json
nano config/server.properties
```
```json
listeners=PLAINTEXT://127.0.0.1:9092
advertised.listeners=PLAINTEXT://127.0.0.1:9092
```
[image: image.png](attachment:664bc585-553e-4cf5-b774-76a7854c1a8b:image.png)
```json
KAFKA_CLUSTER_ID="$(bin/kafka-storage.sh random-uuid)"
echo "$KAFKA_CLUSTER_ID"
```
DeCmS2SGSfOVulye3_7rRw
```json
tmux new -s kafka
```
```json
cd /opt/kafka_2.13-4.3.1
bin/kafka-broker-api-versions.sh --bootstrap-server localhost:9092
```
```json
tmux new -s kafka
```
the continue in another tirminal

#### 2.4 Configure IAM Access to Amazon S3
We attached an IAM role named: SupplyChainEC2S3Role
The role provides the EC2 instance with permissions to access the project's S3 bucket.
The policy includes permissions for listing the bucket, checking its location, and accessing objects.
**Bucket: **supply-chain-graduation-project
Using an IAM role allows the application to obtain AWS credentials through the instance role instead of storing permanent AWS access keys in the application configuration.
[image: image.png](attachment:703804f9-4f71-4cc1-ab32-8fdd951c51ba:image.png)
[image: image.png](attachment:5eaf3d52-803b-4b2f-bc6c-6531b44a5dca:image.png)
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "ListProjectBucket",
            "Effect": "Allow",
            "Action": [
                "s3:ListBucket",
                "s3:GetBucketLocation"
            ],
            "Resource": "arn:aws:s3:::supply-chain-graduation-project"
        },
        {
            "Sid": "AccessProjectObjects",
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:AbortMultipartUpload",
                "s3:ListMultipartUploadParts"
            ],
            "Resource": "arn:aws:s3:::supply-chain-graduation-project/*"
        }
    ]
}
```

#### 2.5 Amazon S3 Setup
We created the project's S3 bucket in the `us-east-1` region.
The Python generator is configured to write data using the following destination settings:
```plain text
S3_MODE=s3
S3_BUCKET=supply-chain-graduation-project
S3_PREFIX=fleet
AWS_REGION=us-east-1
```
The generated objects are stored under the `fleet` prefix.

#### Create the bucket
[image: image.png](attachment:58e795e9-0f5f-4552-b66b-3d1e49f2f6f9:image.png)
[image: image.png](attachment:8b8c8ccd-f7a0-4037-9684-66949712e989:image.png)
[image: image.png](attachment:0509f92d-32d8-49c5-b97f-c7ebf6a5c506:image.png)

### 2.4 Airbyte (S3 → Snowflake)

#### Step 1: Create the Source (S3)
**What we did:Screenshot:** 📷

#### Step 2: Create the Destination (Snowflake)
**What we did:Screenshot:** 📷

#### Step 3: Create the Connection and choose the streams
**What we did:Screenshot:** 📷

#### Step 4: Run the first sync
**What we did:Screenshot:** 📷
---

### 2.5 Snowflake

#### Step 1: Create the warehouse, database, and schemas
**What we did:**
```sql
-- paste the SQL here
```
**Screenshot:** 📷

#### Step 2: Create roles and users
**What we did:Screenshot:** 📷

#### Step 3: Verify the data arrived
**What we did:Screenshot:** 📷
---

### 2.6 dbt

#### Step 1: Initialize the project and connect to Snowflake
**What we did:Screenshot:** 📷

#### Step 2: Create the staging models (cleaning)
**What we did:Screenshot:** 📷

#### Step 3: Create the marts models (facts and dimensions)
**What we did:Screenshot:** 📷

#### Step 4: Add tests and run `dbt run` / `dbt test`
**What we did:Screenshot:** 📷

#### Step 5: Generate the docs and lineage graph
**What we did:Screenshot:** 📷
---

### 2.7 Airflow

#### Step 1: Install and start Airflow
**What we did:Screenshot:** 📷

#### Step 2: Create the connections (Airbyte, Snowflake)
**What we did:Screenshot:** 📷

#### Step 3: Write the DAG
**What we did:**
```python
# paste the DAG code here
```
**Screenshot:** 📷 (Graph view)

#### Step 4: Run the DAG
**What we did:Screenshot:** 📷
---

### 2.8 Power BI

#### Step 1: Connect to Snowflake
**What we did:Screenshot:** 📷

#### Step 2: Build the data model (relationships)
**What we did:Screenshot:** 📷

#### Step 3: Create the measures (KPIs)
**What we did:**
```plain text
-- paste the DAX here
```
**Screenshot:** 📷

#### Step 4: Build the dashboard pages
**What we did:Screenshot:** 📷
---

## 3. 🐞 Error Log
> Add every error here the moment it happens, even if it took 1 minute to fix.
| Date | Tool | Error message | Cause | Fix | Who |
|---|---|---|---|---|---|
| Oct 25 | EC2 | `Permission denied (publickey)` | Wrong key file or permissions | Ran `chmod 400 key.pem` and used the correct key | Mohamed |
|  |  |  |  |  |  |

---

## 4. Glossary
| Term | Meaning |
|---|---|
| EC2 | Elastic Compute Cloud (a virtual server on AWS) |
| S3 | Simple Storage Service (AWS file storage) |
| dbt | Data Build Tool |
| DAG | Directed Acyclic Graph (an Airflow workflow) |
| KPI | Key Performance Indicator |


## 5. Data Catalog
> Go to the Catalog

## 6. Data Quality & Testing
| Check | Where | Tool | Result |
|---|---|---|---|
| Row count S3 vs Snowflake | Ingestion | SQL |  |
| Duplicates removed | Staging | dbt test |  |
| Null foreign keys handled | Staging | dbt test |  |
| Dashboard numbers match SQL | BI | Manual |  |

> **✅ المطلوب منك:** كمّل الجدول بالـ checks اللي هتعملوها وسجّل النتائج.

## 8. Monitoring & Alerts
> **✅ المطلوب منك:** إيه اللي بتراقبوه (الـ generator logs، حجم S3، Airbyte syncs، Airflow failures، Snowflake credits) وإزاي.

## 9. Cost Log
| Week | AWS | Snowflake | Airbyte | Total | Notes |
|---|---|---|---|---|---|
|  |  |  |  |  |  |


## 10. 🐞 Error Log (Master)
> **✅ المطلوب منك:** كل error يطلع في أي أداة يتسجل هنا بنفس اللحظة. اعمله **Notion Database** بالـ properties دي: `Tool` (select)، `Error message`، `Cause`، `Fix`، `Screenshot`، `Date`، `Who fixed`، `Status`.
| Date | Tool | Error message | Cause | Fix | Who |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

---

## 16. References & Links
> **✅ المطلوب منك:** روابط الـ docs الرسمية اللي استخدمتوها والـ tutorials المفيدة.

### 2. Setup & Deployment
**AWS EC2 & Python:**

**S3 Bucket: supply-chain-graduation-project**