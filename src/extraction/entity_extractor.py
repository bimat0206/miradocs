"""Architecture entity extraction using regex + dictionary + optional LLM."""
import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.config import get_config

logger = logging.getLogger(__name__)

# --- Regex patterns ---
CIDR_PATTERN = re.compile(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2})\b')
IP_PATTERN = re.compile(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b')
ARN_PATTERN = re.compile(r'\b(arn:aws[a-zA-Z-]*:[a-zA-Z0-9-]+:\S+)\b')
ACCOUNT_ID_PATTERN = re.compile(r'\b(\d{12})\b')

# --- Dictionaries ---
AWS_SERVICES = {
    "EC2", "S3", "VPC", "IAM", "Lambda", "ECS", "EKS", "RDS", "DynamoDB",
    "CloudFront", "Route 53", "Route53", "CloudWatch", "CloudTrail",
    "GuardDuty", "Security Hub", "SecurityHub", "Config", "AWS Config",
    "KMS", "Secrets Manager", "Systems Manager", "SSM",
    "Transit Gateway", "TGW", "Direct Connect", "VPN", "Site-to-Site VPN",
    "NAT Gateway", "Internet Gateway", "IGW", "ALB", "NLB", "ELB",
    "WAF", "Shield", "Macie", "Inspector", "Detective",
    "Organizations", "Control Tower", "Landing Zone",
    "CodePipeline", "CodeBuild", "CodeDeploy", "CodeCommit",
    "SQS", "SNS", "EventBridge", "Step Functions",
    "Glue", "Athena", "Redshift", "Kinesis", "EMR",
    "SageMaker", "Bedrock", "OpenSearch", "ElastiCache",
    "EFS", "FSx", "Backup", "DataSync",
    "PrivateLink", "Endpoint", "VPC Endpoint",
    "RAM", "Resource Access Manager",
    "SCPs", "SCP", "RCP", "Service Control Policy",
    "CloudFormation", "Terraform", "CDK",
}

AZURE_SERVICES = {
    "Azure", "Virtual Network", "VNet", "NSG", "Azure AD", "Entra ID",
    "Azure Firewall", "Application Gateway", "Front Door",
    "Azure Monitor", "Log Analytics", "Sentinel",
    "Key Vault", "Azure Policy", "Management Group",
    "ExpressRoute", "VPN Gateway", "Azure DNS",
}

ENVIRONMENT_LABELS = {
    "Production", "Prod", "Non-Production", "NonProd", "Non-Prod",
    "UAT", "SIT", "Dev", "Development", "Staging", "DR",
    "Disaster Recovery", "Sandbox", "Test", "QA", "Pre-Prod",
}

GOVERNANCE_TERMS = {
    "OU", "Organizational Unit", "Root OU", "Security OU",
    "Workload OU", "Sandbox OU", "Shared Services",
    "Log Archive", "Audit Account", "Management Account",
    "Network Account", "Security Account",
}


def extract_entities(pages_text: list[dict], doc_id: str) -> list[dict]:
    """Extract entities from page texts. Returns entity inventory."""
    all_entities = []
    entity_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for page_info in pages_text:
        page_num = page_info.get("page", 0)
        text = page_info.get("text", "")
        if not text:
            continue

        # Regex-based extraction
        for cidr in CIDR_PATTERN.findall(text):
            all_entities.append(_entity("cidr", cidr, page_num))
            entity_counts["cidr"][cidr] += 1

        for arn in ARN_PATTERN.findall(text):
            all_entities.append(_entity("arn", arn, page_num))
            entity_counts["arn"][arn] += 1

        # Dictionary-based extraction
        text_upper = text.upper()
        for svc in AWS_SERVICES:
            if svc.upper() in text_upper:
                all_entities.append(_entity("aws_service", svc, page_num))
                entity_counts["aws_service"][svc] += 1

        for svc in AZURE_SERVICES:
            if svc.upper() in text_upper:
                all_entities.append(_entity("azure_service", svc, page_num))
                entity_counts["azure_service"][svc] += 1

        for env in ENVIRONMENT_LABELS:
            if re.search(r'\b' + re.escape(env) + r'\b', text, re.IGNORECASE):
                all_entities.append(_entity("environment", env, page_num))
                entity_counts["environment"][env] += 1

        for term in GOVERNANCE_TERMS:
            if term.upper() in text_upper:
                all_entities.append(_entity("governance", term, page_num))
                entity_counts["governance"][term] += 1

    # Optional LLM enrichment
    cfg = get_config()
    if cfg["entity_extraction"]["use_llm"]:
        all_entities = _enrich_with_llm(all_entities, pages_text, cfg)

    # Build summary
    summary = _build_summary(entity_counts)

    # Save
    output_dir = Path(get_config()["app"]["data_dir"]) / "parsed" / doc_id
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "entities.json").write_text(
        json.dumps({"entities": all_entities, "summary": summary}, indent=2),
        encoding="utf-8"
    )

    logger.info(f"Extracted {len(all_entities)} entity occurrences for {doc_id}")
    return all_entities


def _entity(entity_type: str, value: str, page: int) -> dict:
    return {"type": entity_type, "value": value, "page": page}


def _build_summary(counts: dict) -> list[dict]:
    """Build deduplicated entity summary with occurrence counts."""
    summary = []
    for entity_type, values in counts.items():
        for value, count in sorted(values.items(), key=lambda x: -x[1]):
            summary.append({
                "type": entity_type,
                "value": value,
                "count": count,
            })
    return summary


def _enrich_with_llm(
    entities: list[dict], pages_text: list[dict], cfg: dict
) -> list[dict]:
    """Optional LLM enrichment for ambiguous entities."""
    try:
        import httpx
        ollama_url = cfg["embedding"]["ollama_url"]
        model = cfg["entity_extraction"]["ollama_model"]

        # Send a sample of text for entity classification
        sample_text = " ".join(
            p["text"][:500] for p in pages_text[:5] if p.get("text")
        )
        if not sample_text:
            return entities

        prompt = (
            "Extract architecture entities from this text. "
            "Return JSON array of {type, value} objects. "
            "Types: vpc_name, subnet_name, account_name, route_table, security_group.\n\n"
            f"Text: {sample_text[:2000]}"
        )

        resp = httpx.post(
            f"{ollama_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=30.0,
        )
        if resp.status_code == 200:
            response_text = resp.json().get("response", "")
            # Try to parse JSON from response
            try:
                # Find JSON array in response
                start = response_text.find("[")
                end = response_text.rfind("]") + 1
                if start >= 0 and end > start:
                    llm_entities = json.loads(response_text[start:end])
                    for e in llm_entities:
                        if isinstance(e, dict) and "type" in e and "value" in e:
                            entities.append({
                                "type": e["type"],
                                "value": e["value"],
                                "page": 0,
                                "source": "llm",
                            })
            except json.JSONDecodeError:
                pass
    except Exception as e:
        logger.warning(f"LLM enrichment failed: {e}")

    return entities
