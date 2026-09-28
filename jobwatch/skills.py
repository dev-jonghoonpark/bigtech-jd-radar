"""JD 텍스트에서 기술 키워드를 뽑는 사전. (카테고리, 표시명, 정규식)"""
from __future__ import annotations

import re

_RAW: dict[str, dict[str, str]] = {
    "Language": {
        "Python": r"\bpython\b",
        "Java": r"\bjava\b(?!script)",
        "C++": r"\bc\+\+|\bcpp\b",
        "C": r"\bc\s*/\s*c\+\+|\bc\s*(?:,|and|or)\s*c\+\+|(?<![\w+#.-])c(?=\s*(?:,|/|\)|\s+and\s+|\s+or\s+)\s*(?:c\+\+|rust|go\b|assembly))",
        "Go": r"\bgolang\b|(?:(?<=, )|(?<=/)|(?<=\())go\b(?![- ]to\b)|\bgo(?=\s*(?:,|/|\)))",
        "Rust": r"\brust\b",
        "Kotlin": r"\bkotlin\b",
        "Swift": r"\bswift\b(?!ly)",
        "Objective-C": r"objective-?c\b",
        "TypeScript": r"\btypescript\b",
        "JavaScript": r"\bjavascript\b|\bnode\.?js\b",
        "Scala": r"\bscala\b",
        "C#": r"\bc#|\.net\b",
        "SQL": r"\bsql\b",
        "Bash/Shell": r"\bbash\b|shell script",
        "CUDA": r"\bcuda\b",
        "Verilog/SystemVerilog": r"\bverilog\b|systemverilog",
    },
    "ML Framework": {
        "PyTorch": r"\bpytorch\b|\btorch\b",
        "TensorFlow": r"\btensorflow\b",
        "JAX": r"\bjax\b",
        "Triton": r"\btriton\b",
        "vLLM": r"\bvllm\b",
        "TensorRT": r"\btensorrt",
        "Hugging Face": r"hugging\s?face",
        "NumPy/Pandas": r"\bnumpy\b|\bpandas\b",
        "scikit-learn": r"scikit|sklearn",
        "Ray": r"\bray\b(?= |,|\.)(?=.{0,40}(distributed|cluster|train|serve|python))",
        "ONNX": r"\bonnx\b",
        "MLIR/XLA": r"\bmlir\b|\bxla\b",
    },
    "AI Topic": {
        "LLM": r"\bllms?\b|large language model",
        "Generative AI": r"generative ai|\bgenai\b|gen ai",
        "AI Agents": r"\bagents?\b(?=.{0,30}(ai|llm|model|autonom|tool))|agentic",
        "RAG/Retrieval": r"\brag\b|retrieval[- ]augmented|vector (db|database|search)|embeddings?",
        "RL/RLHF": r"\brlhf\b|reinforcement learning|\brl\b",
        "Fine-tuning/Post-training": r"fine[- ]?tun|post[- ]?training|\bsft\b|\bdpo\b|\blora\b",
        "Pre-training": r"pre[- ]?training|pretraining",
        "Evals": r"\bevals?\b|evaluation (framework|pipeline|harness)s?|model evaluation",
        "Transformers": r"transformer",
        "Diffusion": r"diffusion model|\bdiffusion\b",
        "Multimodal": r"multi-?modal|vision[- ]language|\bvlm",
        "Inference Optimization": r"inference (optimi|serving|efficien|latency|performance)|model serving|quantization|kv[- ]cache|speculative decoding|distillation",
        "Distributed Training": r"distributed training|data parallel|model parallel|tensor parallel|pipeline parallel|\bfsdp\b|deepspeed|megatron",
        "Computer Vision": r"computer vision|\bcv\b|image (recognition|understanding)|object detection",
        "NLP": r"\bnlp\b|natural language processing",
        "Speech/Audio": r"speech|\basr\b|\btts\b|audio",
        "Recommender/Ranking": r"recommend(er|ation) system|recommendations?|ranking|personalization",
        "AI Safety/Alignment": r"alignment|interpretability|ai safety|red[- ]team",
        "MLOps": r"mlops|ml (infrastructure|platform|pipelines?)|feature store|model (deployment|monitoring)",
        "Prompt/Context Eng": r"prompt engineering|context engineering",
        "MCP/Tool Use": r"model context protocol|\bmcp\b|tool[- ]use|function calling",
    },
    "Infra/Cloud": {
        "Kubernetes": r"kubernetes|\bk8s\b",
        "Docker/Containers": r"\bdocker\b|container",
        "AWS": r"\baws\b|amazon web services",
        "GCP": r"\bgcp\b|google cloud",
        "Azure": r"\bazure\b",
        "OCI (Oracle Cloud)": r"\boci\b|oracle cloud",
        "Terraform/IaC": r"terraform|infrastructure[- ]as[- ]code|\biac\b|pulumi",
        "Linux": r"\blinux\b|\bunix\b",
        "CI/CD": r"ci\s*/\s*cd|continuous (integration|deployment|delivery)",
        "Observability": r"observability|monitoring|prometheus|grafana|opentelemetry",
        "Serverless": r"serverless|lambda\b",
        "GPU Clusters/HPC": r"gpu cluster|\bhpc\b|high[- ]performance computing|supercomput|slurm|infiniband|nccl|rdma",
        "Networking": r"\btcp\b|networking|network protocols|\bbgp\b",
    },
    "Data": {
        "Spark": r"\bspark\b",
        "Kafka": r"\bkafka\b",
        "Airflow": r"\bairflow\b",
        "Flink": r"\bflink\b",
        "Hadoop": r"\bhadoop\b|\bhive\b",
        "PostgreSQL": r"postgres",
        "MySQL": r"\bmysql\b",
        "NoSQL": r"nosql|cassandra|mongodb|dynamodb|bigtable|\bredis\b",
        "Data Warehouse": r"snowflake|bigquery|redshift|databricks|data warehouse|lakehouse",
        "Data Pipelines/ETL": r"\betl\b|data pipelines?",
    },
    "Web/Mobile": {
        "React": r"\breact\b(?! native)",
        "React Native": r"react native",
        "GraphQL": r"graphql",
        "REST/gRPC APIs": r"\brest(ful)?\b|\bgrpc\b|protobuf",
        "iOS": r"\bios\b",
        "Android": r"\bandroid\b",
        "SwiftUI/UIKit": r"swiftui|uikit",
    },
    "Systems": {
        "Distributed Systems": r"distributed systems?",
        "Large-scale Systems": r"large[- ]scale (distributed |software |backend )?(systems|services|infrastructure)|(systems|services) at scale|hyperscale|planet[- ]scale|billions of (users|requests)",
        "Microservices": r"microservices?",
        "System Design": r"system design|software architecture|architect(ing|ure) (of )?(large|scalable|distributed)",
        "Concurrency": r"concurren|multi-?thread|parallel programming",
        "Performance Optimization": r"performance (optimi|tuning|engineering|analysis)|profiling|low[- ]latency",
        "OS/Kernel": r"operating systems?|\bkernel\b",
        "Compilers": r"compiler",
        "Embedded/Firmware": r"embedded|firmware|\brtos\b",
        "Storage Systems": r"storage systems?|file systems?|filesystems?",
        "Databases (internals)": r"database (internals|systems|engine)|query (engine|optimi)",
        "Security": r"security (engineering|systems|protocols|best practices|vulnerabilit)|secure (coding|software|systems)|cryptograph|vulnerabilit|threat model",
    },
    "Practice": {
        "Testing": r"unit test|integration test|test automation|testing frameworks?|test[- ]driven|\btdd\b",
        "Code Review": r"code reviews?",
        "Agile": r"\bagile\b|\bscrum\b",
        "Cross-functional": r"cross[- ]functional",
        "Mentoring": r"mentor",
        "On-call/Operations": r"on[- ]call|incident (response|management)|operational excellence",
        "AI Coding Tools": r"ai[- ](assisted|powered) (coding|development)|coding (assistants?|agents?)|copilot|claude code|cursor\b|codex\b",
    },
    "Degree": {
        "PhD": r"\bph\.?d\b|doctorate",
        "MS": r"\bm\.?s\.?\b|master'?s",
        "BS": r"\bb\.?s\.?\b|bachelor'?s",
    },
}

SKILLS: list[tuple[str, str, re.Pattern]] = [
    (cat, name, re.compile(rx, re.I)) for cat, d in _RAW.items() for name, rx in d.items()
]
CATEGORY_OF = {name: cat for cat, name, _ in SKILLS}


def extract(text: str) -> list[str]:
    if not text:
        return []
    return [name for _, name, rx in SKILLS if rx.search(text)]
