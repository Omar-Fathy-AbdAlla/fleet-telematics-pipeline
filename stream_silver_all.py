import os
import json
import time
import logging
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, to_timestamp, date_format, when, lit
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType,
    LongType, DoubleType, BooleanType,
)

# ============================================================
# 1. CONFIGURATION
# ============================================================
KAFKA_SERVER = os.getenv("KAFKA_SERVER", "54.89.41.4:9094")          # Upstream broker (read-only)
TELEMETRY_TOPIC = os.getenv("KAFKA_TOPIC_TELEMETRY", "fleet.telemetry.v1")
REEFER_TOPIC = os.getenv("KAFKA_TOPIC_REEFER", "fleet.reefer.v1")

KAFKA_OUTPUT_SERVER = os.getenv("KAFKA_OUTPUT_SERVER", "kafka-silver:29092")  # Local broker
TELEMETRY_OUTPUT_TOPIC = os.getenv("KAFKA_OUTPUT_TOPIC_TELEMETRY", "fleet.silver.telemetry.v1")
REEFER_OUTPUT_TOPIC = os.getenv("KAFKA_OUTPUT_TOPIC_REEFER", "fleet.silver.reefer.v1")

S3_BUCKET = os.getenv("S3_BUCKET", "supply-chain-graduation-project")
S3_TELEMETRY_PATH = f"s3a://{S3_BUCKET}/fleet/silver/telemetry/"
S3_REEFER_PATH = f"s3a://{S3_BUCKET}/fleet/silver/reefer/"
CHECKPOINT_BASE = f"s3a://{S3_BUCKET}/fleet/silver/_checkpoints/"

TRIGGER_INTERVAL = os.getenv("SPARK_TRIGGER_INTERVAL", "10 seconds")
MAX_OFFSETS = os.getenv("SPARK_MAX_OFFSETS_PER_TRIGGER", "20000")
S3_SINK_MODE = os.getenv("S3_SINK_MODE", "batch").lower()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("fleet-silver-stream")

# ============================================================
# 2. SPARK SESSION (with Fast S3 Committer v2)
# ============================================================
spark = (
    SparkSession.builder.appName("FleetSilverStreaming")
    .config("spark.sql.shuffle.partitions", "2")
    .config("spark.hadoop.mapreduce.fileoutputcommitter.algorithm.version", "2")
    .config("spark.hadoop.fs.s3a.fast.upload", "true")
    .config("spark.hadoop.fs.s3a.fast.upload.buffer", "bytebuffer")
    .config("spark.hadoop.fs.s3a.threads.max", "20")
    .config("spark.hadoop.fs.s3a.connection.maximum", "30")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("WARN")

hadoop_conf = spark.sparkContext._jsc.hadoopConfiguration()
aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
aws_session_token = os.getenv("AWS_SESSION_TOKEN")

if aws_access_key and aws_secret_key:
    hadoop_conf.set("fs.s3a.access.key", aws_access_key)
    hadoop_conf.set("fs.s3a.secret.key", aws_secret_key)
    if aws_session_token:
        hadoop_conf.set("fs.s3a.session.token", aws_session_token)
        hadoop_conf.set("fs.s3a.aws.credentials.provider",
                        "org.apache.hadoop.fs.s3a.TemporaryAWSCredentialsProvider")
    else:
        hadoop_conf.set("fs.s3a.aws.credentials.provider",
                        "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider")

logger.info("Spark session started. Source=%s Output=%s Bucket=%s S3 mode=%s",
            KAFKA_SERVER, KAFKA_OUTPUT_SERVER, S3_BUCKET, S3_SINK_MODE)

# ============================================================
# 3. INPUT SCHEMAS
# ============================================================
telemetry_schema = StructType([
    StructField("schema_version", IntegerType(), True),
    StructField("event_id", StringType(), True),
    StructField("vehicle_id", StringType(), True),
    StructField("device_id", StringType(), True),
    StructField("event_ts", StringType(), True),
    StructField("source_sequence", LongType(), True),
    StructField("lat", DoubleType(), True),
    StructField("lon", DoubleType(), True),
    StructField("speed_mph", DoubleType(), True),
    StructField("heading_deg", IntegerType(), True),
    StructField("rpm", IntegerType(), True),
    StructField("engine_temp_f", DoubleType(), True),
    StructField("fuel_gph", DoubleType(), True),
    StructField("fuel_level_gal", DoubleType(), True),
    StructField("odometer_mi", DoubleType(), True),
    StructField("engine_on", BooleanType(), True),
])

reefer_schema = StructType([
    StructField("schema_version", IntegerType(), True),
    StructField("event_id", StringType(), True),
    StructField("vehicle_id", StringType(), True),
    StructField("trailer_id", StringType(), True),
    StructField("sensor_id", StringType(), True),
    StructField("unit_mode", StringType(), True),
    StructField("event_ts", StringType(), True),
    StructField("source_sequence", LongType(), True),
    StructField("cargo_temp_f", DoubleType(), True),
    StructField("setpoint_f", DoubleType(), True),
    StructField("compressor_on", BooleanType(), True),
    StructField("door_open", BooleanType(), True),
    StructField("ambient_temp_f", DoubleType(), True),
    StructField("reefer_fuel_gph", DoubleType(), True),
])

# ============================================================
# 4. READ SOURCE KAFKA TOPICS
# ============================================================
def read_kafka_topic(topic_name):
    return (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_SERVER)
        .option("subscribe", topic_name)
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "false")
        .option("maxOffsetsPerTrigger", MAX_OFFSETS)
        .load()
    )

telemetry_raw = read_kafka_topic(TELEMETRY_TOPIC)
reefer_raw = read_kafka_topic(REEFER_TOPIC)

# ============================================================
# 5. TELEMETRY TRANSFORM
# ============================================================
telemetry_parsed = (
    telemetry_raw
    .select(from_json(col("value").cast("string"), telemetry_schema).alias("data"))
    .select("data.*")
    .withColumn("event_timestamp", to_timestamp(col("event_ts"), "yyyy-MM-dd'T'HH:mm:ssX"))
    .filter(col("event_id").isNotNull() & col("vehicle_id").isNotNull()
            & col("event_timestamp").isNotNull())
)

telemetry_silver = (
    telemetry_parsed
    .withColumn("speed_kmh", col("speed_mph") * lit(1.60934))
    .withColumn("stream_latency_sec", lit(None).cast(DoubleType()))
    .withColumn("is_speeding", when(col("speed_mph") > 70, True).otherwise(False))
    .withColumn("is_engine_overheating", when(col("engine_temp_f") > 215, True).otherwise(False))
    .withColumn("is_low_fuel", when(col("fuel_level_gal") < 30, True).otherwise(False))
    .withColumn("is_idling",
                when((col("engine_on") == True) & (col("speed_mph") < 3), True).otherwise(False))
    .withColumn("motion_status",
                when((col("engine_on") == False) | col("engine_on").isNull(), "PARKED")
                .when(col("speed_mph") < 3, "IDLING")
                .otherwise("DRIVING"))
    .withColumn("dt", date_format(col("event_timestamp"), "yyyy-MM-dd"))
    .withColumn("hr", date_format(col("event_timestamp"), "HH"))
)

# ============================================================
# 6. REEFER TRANSFORM
# ============================================================
reefer_parsed = (
    reefer_raw
    .select(from_json(col("value").cast("string"), reefer_schema).alias("data"))
    .select("data.*")
    .withColumn("event_timestamp", to_timestamp(col("event_ts"), "yyyy-MM-dd'T'HH:mm:ssX"))
    .filter(col("event_id").isNotNull() & col("vehicle_id").isNotNull()
            & col("event_timestamp").isNotNull())
)

reefer_silver = (
    reefer_parsed
    .withColumn("commodity_type",
                when(col("setpoint_f") == 41, "Pharma")
                .when(col("setpoint_f") == 36, "Chilled")
                .when(col("setpoint_f") == -5, "Frozen")
                .otherwise("Other"))
    .withColumn("allowed_temp_min_f",
                when(col("setpoint_f") == 41, 35.0)
                .when(col("setpoint_f") == 36, 32.0)
                .when(col("setpoint_f") == -5, -10.0)
                .otherwise(col("setpoint_f") - 5))
    .withColumn("allowed_temp_max_f",
                when(col("setpoint_f") == 41, 46.0)
                .when(col("setpoint_f") == 36, 40.0)
                .when(col("setpoint_f") == -5, 0.0)
                .otherwise(col("setpoint_f") + 5))
    .withColumn("is_temp_breach",
                when((col("cargo_temp_f") < col("allowed_temp_min_f"))
                     | (col("cargo_temp_f") > col("allowed_temp_max_f")), True).otherwise(False))
    .withColumn("is_reefer_unit_failure",
                when((col("compressor_on") == False)
                     & (col("cargo_temp_f") > col("setpoint_f") + 5), True).otherwise(False))
    .withColumn("dt", date_format(col("event_timestamp"), "yyyy-MM-dd"))
    .withColumn("hr", date_format(col("event_timestamp"), "HH"))
)

# ============================================================
# 7. BATCH WRITER (Single-Read -> Local Kafka + S3 Parquet)
# ============================================================
def to_jsonable(record):
    for k, v in list(record.items()):
        if isinstance(v, datetime):
            record[k] = v.isoformat()
    return record


def make_batch_writer(name, s3_path, kafka_topic):
    def process(batch_df, batch_id):
        t0 = time.time()
        rows = batch_df.collect()
        if not rows:
            return
        t1 = time.time()

        vehicles = set()
        kafka_pairs = []
        for row in rows:
            rec = to_jsonable(row.asDict())
            vid = str(rec.get("vehicle_id", ""))
            if vid:
                vehicles.add(vid)
            kafka_pairs.append((vid, json.dumps(rec, ensure_ascii=False, default=str)))

        # Local Kafka Sink
        (spark.createDataFrame(kafka_pairs, ["key", "value"])
            .coalesce(1)
            .write.format("kafka")
            .option("kafka.bootstrap.servers", KAFKA_OUTPUT_SERVER)
            .option("topic", kafka_topic)
            .save())
        t2 = time.time()

        # S3 Parquet Sink
        if S3_SINK_MODE == "batch":
            local_df = spark.createDataFrame(rows, schema=batch_df.schema).coalesce(1)
            (local_df.write.mode("append")
                .partitionBy("dt", "hr")
                .parquet(s3_path))
        t3 = time.time()

        logger.info(
            "%s batch %s: %s rows, %s vehicles | collect %.1fs kafka %.1fs s3 %.1fs | total %.1fs",
            name, batch_id, len(rows), len(vehicles),
            t1 - t0, t2 - t1, t3 - t2, t3 - t0)
    return process


telemetry_query = (
    telemetry_silver.writeStream
    .foreachBatch(make_batch_writer("telemetry", S3_TELEMETRY_PATH, TELEMETRY_OUTPUT_TOPIC))
    .option("checkpointLocation", CHECKPOINT_BASE + "telemetry_v3/")
    .trigger(processingTime=TRIGGER_INTERVAL)
    .start()
)

reefer_query = (
    reefer_silver.writeStream
    .foreachBatch(make_batch_writer("reefer", S3_REEFER_PATH, REEFER_OUTPUT_TOPIC))
    .option("checkpointLocation", CHECKPOINT_BASE + "reefer_v3/")
    .trigger(processingTime=TRIGGER_INTERVAL)
    .start()
)

logger.info("Streaming queries started. S3 mode=%s", S3_SINK_MODE)
spark.streams.awaitAnyTermination()