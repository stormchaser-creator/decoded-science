"""PMC Open Access Bulk Importer.

Strategy:
1. Download oa_file_list.csv (index of ALL 3.5M OA papers with file paths, ~910MB)
2. Run comprehensive PubMed searches for aging/longevity to collect all relevant PMIDs
3. Cross-reference PMIDs → file paths in the index
4. Download individual article tar.gz files from NCBI FTP
5. Extract JATS XML, parse, load into raw_papers

This gets 50,000-100,000 aging papers vs ~5,000 from keyword search.

CLI usage:
    python -m decoded.ingest.bulk_pmc --phase index          # Download filelist CSV
    python -m decoded.ingest.bulk_pmc --phase search         # Collect aging PMIDs from PubMed
    python -m decoded.ingest.bulk_pmc --phase download       # Download + import matched papers
    python -m decoded.ingest.bulk_pmc --phase all            # Run all phases
    python -m decoded.ingest.bulk_pmc --phase download --limit 5000   # Import first 5000
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import io
import json
import logging
import os
import tarfile
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env", override=True)

from decoded.ingest.parse import parse_article

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("decoded.ingest.bulk_pmc")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PMC_FTP_BASE = "https://ftp.ncbi.nlm.nih.gov/pub/pmc"
OA_FILE_LIST_URL = f"{PMC_FTP_BASE}/oa_file_list.csv"
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ELINK_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

DATA_DIR = _ROOT / "data" / "pmc_bulk"
FILELIST_PATH = DATA_DIR / "oa_file_list.csv"
PMID_INDEX_PATH = DATA_DIR / "aging_pmids.json"
DOWNLOAD_DIR = DATA_DIR / "xml"

# Comprehensive aging/longevity MeSH + keyword queries
AGING_QUERIES = [
    # Core hallmarks
    '"Aging"[MeSH] AND ("Longevity"[MeSH] OR "Life Expectancy"[MeSH])',
    '"Cellular Senescence"[MeSH]',
    '"Aging"[MeSH] AND "Oxidative Stress"[MeSH]',
    '"Aging"[MeSH] AND "Mitochondria"[MeSH]',
    '"Aging"[MeSH] AND "Autophagy"[MeSH]',
    '"Aging"[MeSH] AND "Epigenesis, Genetic"[MeSH]',
    '"Aging"[MeSH] AND "Telomere"[MeSH]',
    '"Aging"[MeSH] AND "mTOR" OR "mechanistic target of rapamycin"',
    '"Aging"[MeSH] AND "NAD"[MeSH]',
    '"Sirtuins"[MeSH]',
    '"Proteostasis"[tiab] AND aging',
    '"Inflammaging"[tiab]',
    '"Caloric Restriction"[MeSH] AND "Aging"[MeSH]',
    # Interventions
    '"Rapamycin"[MeSH] AND "Aging"[MeSH]',
    '"Metformin"[MeSH] AND "Aging"[MeSH]',
    '"Senolytics"[tiab] OR "Senolytic"[tiab]',
    '"Resveratrol"[MeSH] AND "Aging"[MeSH]',
    '"Spermidine"[tiab] AND "Aging"[MeSH]',
    '"NMN"[tiab] AND aging',
    '"Stem Cells"[MeSH] AND "Aging"[MeSH]',
    # Systems
    '"Gut Microbiome"[tiab] AND "Aging"[MeSH]',
    '"Microbiota"[MeSH] AND "Aging"[MeSH]',
    '"Neurodegeneration"[tiab] AND "Aging"[MeSH]',
    '"Cardiovascular Diseases"[MeSH] AND "Aging"[MeSH]',
    '"Sarcopenia"[MeSH]',
    '"Osteoporosis"[MeSH] AND "Aging"[MeSH]',
    '"Immune Senescence"[tiab] OR "Immunosenescence"[tiab]',
    '"Alzheimer Disease"[MeSH] AND "Aging"[MeSH]',
    # Biomarkers & clocks
    '"Biological Age"[tiab]',
    '"Epigenetic Clock"[tiab]',
    '"DNA Methylation"[MeSH] AND "Aging"[MeSH]',
    '"Proteomics"[MeSH] AND "Aging"[MeSH]',
    '"Transcriptomics"[tiab] AND "Aging"[MeSH]',
    # Model organisms
    '"Caenorhabditis elegans"[MeSH] AND "Aging"[MeSH]',
    '"Drosophila"[MeSH] AND "Aging"[MeSH]',
    '"Mice"[MeSH] AND "Aging"[MeSH] AND "Longevity"[MeSH]',
    '"Saccharomyces cerevisiae"[MeSH] AND "Aging"[MeSH]',
    # Genetics
    '"Longevity"[MeSH] AND "Polymorphism, Genetic"[MeSH]',
    '"Centenarians"[MeSH]',
    '"FOXO"[tiab] AND "Aging"[MeSH]',
    # Circadian & sleep
    '"Circadian Rhythm"[MeSH] AND "Aging"[MeSH]',
    '"Sleep"[MeSH] AND "Aging"[MeSH] AND ("Cognitive Dysfunction"[MeSH] OR "Neurodegeneration"[tiab])',

    # ===================================================================
    # TIER 1 — Follow the connectome's own topology
    # Entity/mechanism-centric, not domain-centric
    # ===================================================================

    # CRP — highest-connectivity inflammatory marker
    '"C-Reactive Protein"[MeSH]',
    '"C-Reactive Protein"[MeSH] AND "Inflammation"[MeSH]',
    '"C-Reactive Protein"[MeSH] AND ("Cardiovascular Diseases"[MeSH] OR "Brain"[MeSH])',

    # IL-6 — central cytokine hub
    '"Interleukin-6"[MeSH]',
    '"Interleukin-6"[MeSH] AND ("Aging"[MeSH] OR "Neuroinflammatory Diseases"[MeSH])',
    '"Interleukin-6"[MeSH] AND ("Depression"[MeSH] OR "Stress, Physiological"[MeSH])',

    # mTOR — master regulator node
    '"TOR Serine-Threonine Kinases"[MeSH]',
    '"TOR Serine-Threonine Kinases"[MeSH] AND "Autophagy"[MeSH]',
    '"TOR Serine-Threonine Kinases"[MeSH] AND ("Neoplasms"[MeSH] OR "Cell Proliferation"[MeSH])',

    # Autophagy — clearance mechanism
    '"Autophagy"[MeSH]',
    '"Mitophagy"[tiab]',
    '"Autophagy"[MeSH] AND "Neurodegeneration"[tiab]',
    '"Autophagy"[MeSH] AND "Cellular Senescence"[MeSH]',

    # BDNF — neuroplasticity hub
    '"Brain-Derived Neurotrophic Factor"[MeSH]',
    '"Brain-Derived Neurotrophic Factor"[MeSH] AND ("Exercise"[MeSH] OR "Neuronal Plasticity"[MeSH])',
    '"Brain-Derived Neurotrophic Factor"[MeSH] AND ("Depression"[MeSH] OR "Cognition"[MeSH])',

    # TNF-alpha — inflammatory signaling
    '"Tumor Necrosis Factor-alpha"[MeSH]',
    '"Tumor Necrosis Factor-alpha"[MeSH] AND "NF-kappa B"[MeSH]',
    '"Tumor Necrosis Factor-alpha"[MeSH] AND ("Neuroinflammatory Diseases"[MeSH] OR "Apoptosis"[MeSH])',

    # NF-kB — master inflammatory transcription factor
    '"NF-kappa B"[MeSH]',
    '"NF-kappa B"[MeSH] AND ("Inflammation"[MeSH] OR "Aging"[MeSH])',
    '"NF-kappa B"[MeSH] AND "Signal Transduction"[MeSH]',

    # AMPK — energy sensor
    '"AMP-Activated Protein Kinases"[MeSH]',
    '"AMP-Activated Protein Kinases"[MeSH] AND ("Mitochondria"[MeSH] OR "Autophagy"[MeSH])',
    '"AMP-Activated Protein Kinases"[MeSH] AND ("Insulin Resistance"[MeSH] OR "Metabolism"[MeSH])',

    # p53 — tumor suppressor / senescence gatekeeper
    '"Tumor Suppressor Protein p53"[MeSH]',
    '"Tumor Suppressor Protein p53"[MeSH] AND ("Cellular Senescence"[MeSH] OR "Apoptosis"[MeSH])',
    '"Tumor Suppressor Protein p53"[MeSH] AND "Aging"[MeSH]',

    # Telomerase — replicative aging
    '"Telomerase"[MeSH]',
    '"Telomerase"[MeSH] AND ("Aging"[MeSH] OR "Cellular Senescence"[MeSH])',

    # Tier 1 — universal cellular mechanisms
    '"Signal Transduction"[MeSH] AND "Aging"[MeSH]',
    '"Apoptosis"[MeSH] AND ("Aging"[MeSH] OR "Neurodegeneration"[tiab])',
    '"Calcium Signaling"[MeSH] AND ("Brain"[MeSH] OR "Aging"[MeSH])',
    '"Reactive Oxygen Species"[MeSH] AND ("Mitochondria"[MeSH] OR "Aging"[MeSH])',
    '"Insulin-Like Growth Factor I"[MeSH] AND "Aging"[MeSH]',
    '"Wnt Signaling Pathway"[MeSH] AND ("Aging"[MeSH] OR "Stem Cells"[MeSH])',
    '"Notch Signaling Pathway"[tiab] AND ("Aging" OR "Stem Cells")',
    '"Hedgehog Proteins"[MeSH] AND "Aging"[MeSH]',

    # Tier 1 — cross-tissue boundary signals
    '"Exosomes"[MeSH]',
    '"Exosomes"[MeSH] AND ("Aging"[MeSH] OR "Neurodegeneration"[tiab] OR "Biomarkers"[MeSH])',
    '"Neuropeptides"[MeSH] AND ("Aging"[MeSH] OR "Inflammation"[MeSH])',
    '"Nitric Oxide"[MeSH] AND ("Endothelium"[MeSH] OR "Brain"[MeSH] OR "Aging"[MeSH])',
    '"Cytokines"[MeSH] AND "Brain"[MeSH]',
    '"Extracellular Vesicles"[MeSH] AND ("Aging"[MeSH] OR "Biomarkers"[MeSH])',

    # ===================================================================
    # TIER 2-5 — Pearl's domain-stratified, mechanism-pure queries
    # Fill the floor plan before deepening the neuro/immune hole
    # ===================================================================

    # CARDIOVASCULAR
    '"Endothelium, Vascular"[MeSH]',
    '"Vascular Stiffness"[MeSH]',
    '"Nitric Oxide Synthase"[MeSH]',
    '"Heart Rate"[MeSH] AND "Autonomic Nervous System"[MeSH]',
    '"Atherosclerosis"[MeSH] AND "Inflammation"[MeSH]',
    '"Endothelial Dysfunction"[tiab]',
    '"Platelet Aggregation"[MeSH]',
    '"Angiogenesis"[MeSH] AND "Hypoxia"[MeSH]',
    '"Cardiac Fibrosis"[tiab]',
    '"Myocardial Remodeling"[MeSH]',

    # METABOLIC / INSULIN AXIS
    '"Insulin Resistance"[MeSH]',
    '"Glucose Metabolism Disorders"[MeSH]',
    '"Adiponectin"[MeSH]',
    '"Leptin"[MeSH]',
    '"Peroxisome Proliferator-Activated Receptors"[MeSH]',
    '"Gluconeogenesis"[MeSH]',
    '"Fatty Acids"[MeSH] AND "Mitochondria"[MeSH]',
    '"Glycogen Synthase Kinase 3"[MeSH]',
    '"Adipose Tissue"[MeSH] AND "Inflammation"[MeSH]',
    '"Fasting"[MeSH] AND "Metabolism"[MeSH]',

    # GUT / LIVER / DETOX
    '"Gastrointestinal Microbiome"[MeSH]',
    '"Intestinal Permeability"[tiab]',
    '"Bile Acids and Salts"[MeSH]',
    '"Short Chain Fatty Acids"[MeSH]',
    '"Mucus"[MeSH] AND "Intestinal Mucosa"[MeSH]',
    '"Hepatic Stellate Cells"[MeSH]',
    '"Dysbiosis"[tiab]',
    '"Gut-Brain Axis"[tiab]',
    '"Glutathione"[MeSH] AND "Oxidative Stress"[MeSH]',
    '"Liver"[MeSH] AND "Detoxification, Metabolic"[MeSH]',

    # HPA AXIS / STRESS PHYSIOLOGY
    '"Hypothalamo-Hypophyseal System"[MeSH]',
    '"Corticotropin-Releasing Hormone"[MeSH]',
    '"Glucocorticoids"[MeSH] AND "Inflammation"[MeSH]',
    '"Stress, Physiological"[MeSH] AND "Adrenal Glands"[MeSH]',
    '"Allostatic Load"[tiab]',
    '"Sympathetic Nervous System"[MeSH] AND "Cardiovascular System"[MeSH]',
    '"Hydrocortisone"[MeSH] AND "Feedback"[tiab]',
    '"Cortisol"[tiab] AND "Circadian Rhythm"[MeSH]',

    # SLEEP / CIRCADIAN
    '"Circadian Rhythm"[MeSH]',
    '"CLOCK Proteins"[MeSH]',
    '"Melatonin"[MeSH] AND "Mitochondria"[MeSH]',
    '"Sleep Deprivation"[MeSH] AND "Inflammation"[MeSH]',
    '"Suprachiasmatic Nucleus"[MeSH]',
    '"Glymphatic System"[tiab]',
    '"Chronobiology Disorders"[MeSH]',

    # IMMUNE REGULATION (non-neuro)
    '"Regulatory T-Lymphocytes"[MeSH]',
    '"Immune Tolerance"[MeSH]',
    '"Dendritic Cells"[MeSH] AND "Antigen Presentation"[MeSH]',
    '"Inflammasomes"[MeSH]',
    '"Complement System Proteins"[MeSH]',
    '"Natural Killer Cells"[MeSH]',
    '"Interleukin-10"[MeSH]',
    '"Neutrophil Extracellular Traps"[tiab]',
    '"Mast Cells"[MeSH] AND "Innate Immunity"[MeSH]',

    # MUSCULOSKELETAL / CONNECTIVE TISSUE
    '"Extracellular Matrix"[MeSH]',
    '"Collagen"[MeSH] AND "Fibroblasts"[MeSH]',
    '"Bone Remodeling"[MeSH]',
    '"Myokines"[tiab]',
    '"Skeletal Muscle"[MeSH] AND "Mitochondria"[MeSH]',
    '"Osteocalcin"[MeSH]',

    # REPRODUCTIVE / HORMONAL AXES
    '"Estrogens"[MeSH] AND "Inflammation"[MeSH]',
    '"Testosterone"[MeSH] AND "Mitochondria"[MeSH]',
    '"Thyroid Hormones"[MeSH] AND "Metabolism"[MeSH]',
    '"Sex Hormone-Binding Globulin"[MeSH]',
    '"Progesterone"[MeSH] AND "Neuroprotection"[tiab]',
    '"Follicle Stimulating Hormone"[MeSH]',
]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_db_conn():
    db_url = os.environ.get("DATABASE_URL", "postgresql://whit@localhost:5432/encoded_human")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    psycopg2.extras.register_uuid(conn)
    return conn


def get_existing_pmids(conn) -> set[str]:
    cur = conn.cursor()
    cur.execute("SELECT external_id FROM raw_papers WHERE source='pubmed'")
    return {str(r[0]) for r in cur.fetchall()}


def get_existing_pmcids(conn) -> set[str]:
    cur = conn.cursor()
    cur.execute("SELECT pmc_id FROM raw_papers WHERE pmc_id IS NOT NULL")
    return {str(r[0]) for r in cur.fetchall()}


def insert_paper(conn, run_id: str, record: dict) -> tuple[str, bool]:
    """Insert a paper from bulk download. Returns (paper_id, is_new)."""
    cur = conn.cursor()
    source = record.get("source", "pubmed")
    external_id = record.get("external_id") or record.get("pmid", "")
    if not external_id:
        return "", False

    cur.execute(
        "SELECT id FROM raw_papers WHERE source=%s AND external_id=%s",
        (source, external_id),
    )
    existing = cur.fetchone()
    if existing:
        return str(existing[0]), False

    from datetime import datetime
    pub_date = record.get("pub_date")
    pub_date_obj = None
    if pub_date and len(pub_date) >= 4:
        try:
            if len(pub_date) == 4:
                pub_date = f"{pub_date}-01-01"
            pub_date_obj = datetime.strptime(pub_date[:10], "%Y-%m-%d").date()
        except ValueError:
            pass

    pub_year = record.get("pub_year")
    if pub_year is None and pub_date_obj:
        pub_year = pub_date_obj.year

    paper_id = str(uuid.uuid4())
    status = "parsed" if record.get("full_text") or record.get("sections") else (
        "fetched" if record.get("abstract") else "queued"
    )

    cur.execute(
        """
        INSERT INTO raw_papers (
            id, source, external_id, title, abstract, full_text, sections,
            authors, journal, published_date, pub_year, doi, pmc_id,
            mesh_terms, keywords, status, ingest_run_id, raw_metadata,
            reference_count, references_list, created_at, updated_at
        ) VALUES (
            %s,%s,%s,%s,%s,%s,%s,
            %s,%s,%s,%s,%s,%s,
            %s,%s,%s,%s,%s,
            %s,%s,NOW(),NOW()
        )
        ON CONFLICT (source, external_id) DO NOTHING
        RETURNING id
        """,
        (
            paper_id, source, external_id,
            (record.get("title") or "")[:2000],
            record.get("abstract"),
            record.get("full_text"),
            json.dumps(record.get("sections") or {}),
            json.dumps(record.get("authors") or []),
            record.get("journal"),
            pub_date_obj,
            pub_year,
            record.get("doi"),
            record.get("pmc_id"),
            json.dumps(record.get("mesh_terms") or []),
            json.dumps(record.get("keywords") or []),
            status,
            run_id,
            json.dumps(record.get("raw_metadata") or {}),
            record.get("reference_count") or 0,
            json.dumps((record.get("references") or [])[:500]),
        ),
    )
    row = cur.fetchone()
    conn.commit()
    return (str(row[0]) if row else paper_id), bool(row)


# ---------------------------------------------------------------------------
# Phase 1: Download filelist index
# ---------------------------------------------------------------------------

async def download_filelist(force: bool = False):
    """Download oa_file_list.csv to DATA_DIR."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    if FILELIST_PATH.exists() and not force:
        size_mb = FILELIST_PATH.stat().st_size / 1024 / 1024
        logger.info("oa_file_list.csv already exists (%.0f MB) — skipping download", size_mb)
        return

    logger.info("Downloading oa_file_list.csv (~910MB) — this takes a few minutes...")
    tmp = FILELIST_PATH.with_suffix(".csv.tmp")

    async with httpx.AsyncClient(timeout=600) as client:
        async with client.stream("GET", OA_FILE_LIST_URL) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            last_log = 0

            with open(tmp, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if downloaded - last_log > 50 * 1024 * 1024:
                        pct = (downloaded / total * 100) if total else 0
                        logger.info(
                            "  Downloaded %.0f MB / %.0f MB (%.0f%%)",
                            downloaded / 1024 / 1024, total / 1024 / 1024, pct,
                        )
                        last_log = downloaded

    tmp.rename(FILELIST_PATH)
    logger.info("oa_file_list.csv saved: %.0f MB", FILELIST_PATH.stat().st_size / 1024 / 1024)


def build_pmid_to_path(pmids: set[str]) -> dict[str, dict]:
    """Scan oa_file_list.csv and return {pmid: {path, pmcid, license}} for matching PMIDs."""
    logger.info("Scanning oa_file_list.csv for %d PMIDs...", len(pmids))
    matched: dict[str, dict] = {}

    with open(FILELIST_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i % 500000 == 0 and i > 0:
                logger.info("  Scanned %d rows, matched %d so far", i, len(matched))
            pmid = row.get("PMID", "").strip()
            if pmid and pmid in pmids:
                matched[pmid] = {
                    "path": row.get("File", "").strip(),
                    "pmcid": row.get("Accession ID", "").strip(),
                    "license": row.get("License", "").strip(),
                    "citation": row.get("Article Citation", "").strip(),
                }

    logger.info("Found %d / %d PMIDs in OA filelist", len(matched), len(pmids))
    return matched


# ---------------------------------------------------------------------------
# Phase 2: Collect aging PMIDs from PubMed
# ---------------------------------------------------------------------------

async def collect_aging_pmids(api_key: str | None = None, max_per_query: int = 10000) -> set[str]:
    """Run comprehensive PubMed searches and collect all aging PMIDs."""
    pmids: set[str] = set()
    delay = 0.11 if api_key else 0.34

    logger.info("Collecting aging PMIDs from PubMed (%d queries)...", len(AGING_QUERIES))

    async with httpx.AsyncClient(timeout=60) as client:
        for i, query in enumerate(AGING_QUERIES):
            params = {
                "db": "pubmed",
                "term": query,
                "retmax": str(max_per_query),
                "retmode": "json",
                "usehistory": "n",
            }
            if api_key:
                params["api_key"] = api_key

            try:
                resp = await client.get(ESEARCH_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
                ids = data.get("esearchresult", {}).get("idlist", [])
                new_count = len(set(ids) - pmids)
                pmids.update(ids)
                logger.info(
                    "  [%d/%d] '%s...': %d hits, %d new (total: %d)",
                    i + 1, len(AGING_QUERIES), query[:60], len(ids), new_count, len(pmids),
                )
            except Exception as exc:
                logger.warning("  Query failed: %s — %s", query[:60], exc)

            await asyncio.sleep(delay)

    logger.info("Total unique aging PMIDs: %d", len(pmids))

    # Save for reuse
    with open(PMID_INDEX_PATH, "w") as f:
        json.dump(list(pmids), f)
    logger.info("Saved to %s", PMID_INDEX_PATH)

    return pmids


# ---------------------------------------------------------------------------
# Phase 3: Download + import matched papers
# ---------------------------------------------------------------------------

async def fetch_pubmed_metadata(pmids: list[str], api_key: str | None = None) -> dict[str, dict]:
    """Fetch PubMed metadata (title, abstract, authors, etc.) for a list of PMIDs."""
    import dataclasses
    from pubmed_tools import parse_pubmed_xml

    metadata: dict[str, dict] = {}
    chunk_size = 200
    delay = 0.11 if api_key else 0.34

    async with httpx.AsyncClient(timeout=60) as client:
        for i in range(0, len(pmids), chunk_size):
            chunk = pmids[i:i + chunk_size]
            params = {
                "db": "pubmed",
                "id": ",".join(chunk),
                "retmode": "xml",
                "rettype": "abstract",
            }
            if api_key:
                params["api_key"] = api_key
            try:
                resp = await client.get(EFETCH_URL, params=params)
                resp.raise_for_status()
                articles = parse_pubmed_xml(resp.text)
                for article in articles:
                    if article.pmid:
                        metadata[article.pmid] = dataclasses.asdict(article)
            except Exception as exc:
                logger.warning("efetch failed for chunk %d: %s", i, exc)
            await asyncio.sleep(delay)
            if (i // chunk_size) % 10 == 0:
                logger.info("  Fetched metadata: %d / %d", min(i + chunk_size, len(pmids)), len(pmids))

    return metadata


async def download_and_parse_article(
    pmcid: str,
    file_path: str,
    semaphore: asyncio.Semaphore,
) -> tuple[str, bytes] | None:
    """Download a PMC article tar.gz and return (format, xml_bytes)."""
    url = f"{PMC_FTP_BASE}/{file_path}"
    async with semaphore:
        try:
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    content = resp.content
                    # Extract XML from tar.gz
                    with tarfile.open(fileobj=io.BytesIO(content)) as tar:
                        for member in tar.getmembers():
                            if member.name.endswith(".xml") or member.name.endswith(".nxml"):
                                f = tar.extractfile(member)
                                if f:
                                    return "jats", f.read()
        except Exception as exc:
            logger.debug("Download failed for %s: %s", pmcid, exc)
        await asyncio.sleep(0.1)
    return None


async def run_download_phase(
    limit: int = 0,
    concurrency: int = 8,
    skip_existing: bool = True,
    api_key: str | None = None,
):
    """Download + import all matched aging papers."""
    # Load PMIDs
    if not PMID_INDEX_PATH.exists():
        logger.error("Run --phase search first to collect PMIDs")
        return

    with open(PMID_INDEX_PATH) as f:
        all_pmids = set(json.load(f))
    logger.info("Loaded %d aging PMIDs", len(all_pmids))

    # Load filelist to get paths
    if not FILELIST_PATH.exists():
        logger.error("Run --phase index first to download oa_file_list.csv")
        return

    path_map = build_pmid_to_path(all_pmids)

    conn = get_db_conn()
    existing_pmids = get_existing_pmids(conn) if skip_existing else set()
    existing_pmcids = get_existing_pmcids(conn) if skip_existing else set()

    # Filter to papers not already in DB
    to_process = {
        pmid: info for pmid, info in path_map.items()
        if pmid not in existing_pmids and info["pmcid"] not in existing_pmcids
        and info["path"]  # must have a download path
    }

    if limit:
        to_process = dict(list(to_process.items())[:limit])

    logger.info(
        "%d papers to import (%d already in DB, %d in OA filelist, %d have no OA full text)",
        len(to_process),
        len(path_map) - len(to_process),
        len(path_map),
        len(all_pmids) - len(path_map),
    )

    # Fetch PubMed metadata for all papers (title, abstract, authors, etc.)
    logger.info("Fetching PubMed metadata for %d papers...", len(to_process))
    metadata = await fetch_pubmed_metadata(list(to_process.keys()), api_key=api_key)
    logger.info("Got metadata for %d / %d papers", len(metadata), len(to_process))

    # Create ingest run record
    cur = conn.cursor()
    run_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO ingest_runs (id, domain, ring, source, query, max_results) VALUES (%s,%s,%s,%s,%s,%s)",
        (run_id, "longevity", 0, "pubmed", "PMC_OA_bulk_import", len(to_process)),
    )
    conn.commit()

    # Download + parse + import
    semaphore = asyncio.Semaphore(concurrency)
    stats = {"total": len(to_process), "imported": 0, "errors": 0, "no_xml": 0}

    async def process_one(pmid: str, info: dict):
        result = await download_and_parse_article(info["pmcid"], info["path"], semaphore)
        if result is None:
            # Fall back to abstract-only from PubMed metadata
            meta = metadata.get(pmid, {})
            if not meta.get("abstract"):
                stats["no_xml"] += 1
                return
            record = {
                "source": "pubmed",
                "external_id": pmid,
                "title": meta.get("title", ""),
                "abstract": meta.get("abstract"),
                "authors": meta.get("authors", []),
                "journal": meta.get("journal"),
                "pub_date": meta.get("pub_date"),
                "doi": meta.get("doi"),
                "pmc_id": info["pmcid"] or None,
                "mesh_terms": meta.get("mesh_terms", []),
                "keywords": meta.get("keywords", []),
                "raw_metadata": {"pmc_bulk": True, "license": info["license"]},
            }
        else:
            fmt, xml_bytes = result
            from decoded.ingest.parse import parse_article as _parse
            parsed = _parse(fmt, xml_bytes)
            if not parsed:
                stats["errors"] += 1
                return
            meta = metadata.get(pmid, {})
            # Merge PubMed metadata
            if not parsed.get("abstract") and meta.get("abstract"):
                parsed["abstract"] = meta["abstract"]
            if not parsed.get("authors") and meta.get("authors"):
                parsed["authors"] = meta["authors"]
            if not parsed.get("mesh_terms") and meta.get("mesh_terms"):
                parsed["mesh_terms"] = meta["mesh_terms"]
            record = {
                "source": "pubmed",
                "external_id": pmid,
                "pmc_id": info["pmcid"],
                "raw_metadata": {"pmc_bulk": True, "license": info["license"]},
                **parsed,
            }

        try:
            _, is_new = insert_paper(conn, run_id, record)
            if is_new:
                stats["imported"] += 1
        except Exception as exc:
            conn.rollback()
            stats["errors"] += 1
            logger.debug("Insert failed for PMID %s: %s", pmid, exc)
            return
        if stats["imported"] % 500 == 0 and stats["imported"] > 0:
            logger.info(
                "Progress: %d imported, %d errors, %d no_xml (total processed: %d)",
                stats["imported"], stats["errors"], stats["no_xml"],
                stats["imported"] + stats["errors"] + stats["no_xml"],
            )

    tasks = [process_one(pmid, info) for pmid, info in to_process.items()]
    await asyncio.gather(*tasks, return_exceptions=True)

    # Finish ingest run
    try:
        cur.execute(
            "UPDATE ingest_runs SET papers_found=%s, papers_new=%s, papers_skipped=%s, status='completed', completed_at=NOW() WHERE id=%s",
            (stats["total"], stats["imported"], stats["errors"] + stats["no_xml"], run_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
    conn.close()

    logger.info(
        "Bulk import complete: %d imported, %d errors, %d no_xml (of %d total)",
        stats["imported"], stats["errors"], stats["no_xml"], stats["total"],
    )
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def _async_main(args):
    api_key = os.environ.get("NCBI_API_KEY")

    if args.phase in ("index", "all"):
        await download_filelist(force=args.force)

    if args.phase in ("search", "all"):
        await collect_aging_pmids(api_key=api_key, max_per_query=args.max_per_query)

    if args.phase in ("download", "all"):
        await run_download_phase(
            limit=args.limit,
            concurrency=args.concurrency,
            api_key=api_key,
        )


def main():
    parser = argparse.ArgumentParser(
        description="PMC Open Access bulk importer for aging papers"
    )
    parser.add_argument(
        "--phase",
        choices=["index", "search", "download", "all"],
        required=True,
        help="index=download filelist, search=collect PMIDs, download=import papers, all=run everything",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max papers to import (0=all)")
    parser.add_argument("--concurrency", type=int, default=8, help="Concurrent downloads")
    parser.add_argument("--max-per-query", type=int, default=10000, help="Max results per PubMed query")
    parser.add_argument("--force", action="store_true", help="Re-download even if files exist")
    args = parser.parse_args()
    asyncio.run(_async_main(args))


if __name__ == "__main__":
    main()
