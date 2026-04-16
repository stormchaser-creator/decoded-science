"""Sprint A3+A4: Seed condition/phenotype/process bridge entities + expand
aliases on frequently-fragmented molecular entities.

Condition-level entities (insulin resistance, cellular senescence, oxidative
stress, etc.) are the cross-subfield bridges Pearl flagged as essential —
they connect molecular biology papers to clinical outcome papers. They
appear 50-500 times each in paper_claim_triples and are invisible to
normalization until they're registered as canonical_entities.

Molecular aliases: mTOR/mTORC1/FRAP1/rapamycin-sensitive complex all point
to the same biological entity — literature fragments them into separate
strings. Alias expansion on the canonical entity collapses them at the
normalization layer (Pearl's rule: collapse strings, not biology).

Idempotent via canonical_name UNIQUE constraint.
"""

from __future__ import annotations
import logging, os
import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("seed_bridges")

DB_HOST = os.environ.get("PGHOST", "Whits-Mac-mini.local")
DB_NAME = os.environ.get("PGDATABASE", "encoded_human")


# ---------------------------------------------------------------------------
# BRIDGE ENTITIES — condition / phenotype / process / disease level
# These appear heavily as subject/object in paper_claim_triples but are NOT
# molecules. They bridge molecular-to-clinical literature.
# ---------------------------------------------------------------------------
BRIDGE_ENTITIES = [
    # --- Phenotypes (measurable body states) ---
    ("Aging", "phenotype", "process", ["aging", "ageing", "age", "biological aging", "chronological aging"]),
    ("Cellular senescence", "phenotype", "process", ["senescence", "cell senescence", "senescent cells", "senescent phenotype", "inflammaging"]),
    ("Insulin resistance", "phenotype", "condition", ["insulin_resistance", "IR", "insulin-resistant state", "reduced insulin sensitivity"]),
    ("Insulin sensitivity", "phenotype", "condition", ["insulin-sensitive state", "normal insulin response"]),
    ("Hyperglycemia", "phenotype", "condition", ["elevated blood glucose", "chronic hyperglycemia", "high blood sugar"]),
    ("Obesity", "phenotype", "condition", ["adiposity", "visceral obesity", "abdominal obesity", "central obesity"]),
    ("Sarcopenia", "phenotype", "condition", ["muscle wasting", "age-related muscle loss", "sarcopenic obesity"]),
    ("Oxidative stress", "phenotype", "process", ["ROS burden", "redox imbalance", "oxidative damage"]),
    ("Mitochondrial dysfunction", "phenotype", "process", ["mito dysfunction", "mitochondrial failure", "impaired mitochondrial function", "mitochondrial impairment"]),
    ("Endothelial dysfunction", "phenotype", "condition", ["endothelial_dysfunction", "vascular dysfunction", "impaired endothelial function"]),
    ("Cognitive impairment", "phenotype", "condition", ["cognitive decline", "cognitive dysfunction", "cognitive deficit"]),
    ("Cognitive function", "phenotype", "process", ["cognition", "executive function", "cognitive performance"]),
    ("Neuroinflammation", "phenotype", "process", ["brain inflammation", "CNS inflammation", "glial activation"]),
    ("Chronic inflammation", "phenotype", "process", ["systemic inflammation", "low-grade inflammation", "persistent inflammation"]),
    ("Inflammation", "phenotype", "process", ["inflammatory response", "acute inflammation"]),
    ("Neurodegeneration", "phenotype", "process", ["neuronal loss", "neurodegeneration process", "neuronal degeneration"]),
    ("Neuroprotection", "phenotype", "process", ["neuroprotective effect", "neuronal protection"]),
    ("All-cause mortality", "phenotype", "phenotype", ["total mortality", "overall mortality"]),
    ("Lifespan extension", "phenotype", "phenotype", ["extended lifespan", "increased longevity", "life extension"]),
    ("Longevity", "phenotype", "phenotype", ["long life", "healthy aging", "lifespan"]),
    ("Apoptosis", "process", "process", ["programmed cell death", "apoptotic cell death", "intrinsic apoptosis", "extrinsic apoptosis"]),
    ("Ferroptosis", "process", "process", ["iron-dependent cell death", "ferroptotic cell death"]),
    ("Mitophagy", "process", "process", ["mitochondrial autophagy", "mito quality control"]),
    ("Angiogenesis", "process", "process", ["vascular formation", "neovascularization", "blood vessel formation"]),
    ("Cell proliferation", "process", "process", ["proliferation", "cellular proliferation", "cell division"]),
    ("Intestinal barrier integrity", "phenotype", "process", ["gut barrier function", "intestinal permeability", "leaky gut"]),
    ("Hypoxia", "phenotype", "condition", ["low oxygen", "oxygen deprivation", "hypoxic conditions"]),
    ("Metabolic syndrome", "phenotype", "condition", ["MetS", "metabolic X", "syndrome X"]),

    # --- Conditions (dietary/lifestyle interventions as condition-level entities) ---
    ("Exercise", "condition", "process", ["physical activity", "physical exercise", "aerobic exercise", "resistance exercise", "resistance training"]),
    ("Caloric restriction", "condition", "process", ["calorie restriction", "CR", "dietary restriction", "food restriction"]),
    ("Intermittent fasting", "condition", "process", ["time-restricted feeding", "time-restricted eating", "TRF", "TRE"]),
    ("Sleep deprivation", "condition", "process", ["sleep loss", "insufficient sleep", "sleep restriction"]),
    ("High-fat diet", "condition", "process", ["HFD", "western diet", "high-fat feeding"]),

    # --- Diseases ---
    ("Type 2 diabetes", "disease", "disease", ["T2D", "T2DM", "type 2 diabetes mellitus", "adult-onset diabetes", "non-insulin-dependent diabetes"]),
    ("Diabetes mellitus", "disease", "disease", ["DM", "diabetes"]),
    ("Gestational diabetes mellitus", "disease", "disease", ["GDM", "gestational diabetes", "pregnancy-related diabetes"]),
    ("Alzheimer's disease", "disease", "disease", ["AD", "alzheimer disease", "senile dementia"]),
    ("Hypertension", "disease", "condition", ["high blood pressure", "HTN", "arterial hypertension"]),
    ("Cardiovascular disease", "disease", "disease", ["CVD", "heart disease", "cardiovascular disorder"]),
    ("Atherosclerosis", "disease", "disease", ["atheromatous disease", "atherosclerotic disease"]),
    ("Ischemic stroke", "disease", "condition", ["cerebral ischemia", "stroke", "cerebrovascular accident", "CVA"]),
    ("Traumatic brain injury", "disease", "condition", ["TBI", "head injury", "brain trauma"]),
    ("Depression", "disease", "condition", ["major depression", "MDD", "depressive disorder"]),
    ("SARS-CoV-2 infection", "disease", "condition", ["sars-cov-2", "COVID-19", "COVID", "coronavirus infection"]),
    ("Dysbiosis", "phenotype", "condition", ["gut dysbiosis", "gut microbiota dysbiosis", "microbial dysbiosis", "dysbiotic microbiota", "intestinal dysbiosis"]),

    # --- Tissues/substrates ---
    ("Gut microbiota", "tissue", "tissue", ["gut microbiome", "intestinal microbiota", "gut flora", "gut microbiota composition"]),
    ("Gut microbiome", "tissue", "tissue", ["intestinal microbiome"]),
    ("Adipose tissue", "tissue", "tissue", ["fat tissue", "visceral adipose tissue", "VAT", "subcutaneous adipose tissue"]),
    ("Skeletal muscle", "tissue", "tissue", ["muscle tissue", "skeletal muscle tissue"]),

    # --- Cytokines/signaling high-frequency bridges (molecules but act as bridges) ---
    ("IL-6", "molecule", "protein", ["interleukin-6", "interleukin 6", "IL6"]),
    ("IL-10", "molecule", "protein", ["interleukin-10", "interleukin 10", "IL10"]),
    ("IL-1β", "molecule", "protein", ["IL-1 beta", "interleukin-1 beta", "IL1B"]),
    ("TNF-α", "molecule", "protein", ["TNF alpha", "tumor necrosis factor alpha", "TNFα", "TNF"]),
    ("IFN-γ", "molecule", "protein", ["interferon gamma", "IFN gamma", "IFNG"]),
    ("BDNF", "molecule", "protein", ["brain-derived neurotrophic factor"]),
    ("Leptin", "molecule", "protein", ["LEP", "OB protein"]),
    ("Adiponectin", "molecule", "protein", ["ADIPOQ", "GBP-28", "APM1"]),
    ("Estrogen", "molecule", "metabolite", ["estrogens", "estrogenic hormones"]),
    ("Melatonin", "molecule", "metabolite", ["N-acetyl-5-methoxytryptamine"]),
    ("LPS", "molecule", "metabolite", ["lipopolysaccharide", "bacterial LPS", "endotoxin"]),
    ("Short-chain fatty acids", "molecule", "metabolite", ["SCFA", "short chain fatty acids", "SCFAs"]),

    # --- Interventions ---
    ("Probiotics", "drug", "drug", ["probiotic supplementation", "probiotic bacteria"]),
    ("Curcumin", "drug", "drug", ["diferuloylmethane"]),
    ("SGLT2 inhibitors", "drug", "drug", ["SGLT2i", "sodium-glucose cotransporter 2 inhibitors", "gliflozins"]),

    # --- Signaling process-level (for bridge crossings) ---
    ("Insulin signaling", "pathway", "pathway", ["insulin receptor signaling", "insulin pathway"]),
    ("HPA axis", "process", "process", ["hypothalamic-pituitary-adrenal axis", "HPA"]),
    ("Immune response", "process", "process", ["immunity", "adaptive immune response", "innate immune response"]),
]


# ---------------------------------------------------------------------------
# ALIAS EXPANSIONS — for already-registered canonical entities that appear
# under many fragmented strings in the literature. Patching the aliases array
# makes the normalizer collapse them on next run.
# ---------------------------------------------------------------------------
ALIAS_EXPANSIONS = {
    # mTOR family — the biggest fragmentation issue (Pearl 2026-04-16)
    "mTOR":    ["mtor", "frap1", "mammalian target of rapamycin", "mechanistic target of rapamycin",
                "mtor pathway", "mtor signaling", "mtor pathway activation", "mtor activation",
                "mtor inhibition", "mtor pathway inhibition"],
    "mTORC1":  ["mtorc1", "mtor complex 1", "mtorc1 signaling", "mtorc1 activation",
                "mtorc1 inhibition", "mtorc1 hyperactivation", "rapamycin-sensitive complex"],
    "mTORC2":  ["mtorc2", "mtor complex 2", "rapamycin-insensitive complex"],
    # NF-κB
    "NF-κB":   ["nf-kb", "nfkb", "nfkb1", "nf kappa b", "rela", "p65", "nf-κb pathway",
                "nf-κb signaling", "nf-κb activation"],
    # Akt
    "Akt":     ["akt", "akt1", "pkb", "protein kinase b", "akt phosphorylation",
                "akt activation", "akt pathway", "pi3k/akt", "pi3k-akt"],
    # AMPK
    "AMPK":    ["ampk", "prkaa1", "amp-activated protein kinase", "amp activated protein kinase",
                "ampk activation", "ampk signaling", "ampk pathway"],
    # SIRT1
    "SIRT1":   ["sirt1", "sirtuin 1", "sirtuin-1", "silent information regulator 1"],
    # p53
    "p53":     ["tp53", "trp53", "p53 pathway", "p53 activation", "p53 signaling"],
    # HIF-1α
    "HIF-1α":  ["hif-1alpha", "hif1a", "hif 1 alpha", "hypoxia-inducible factor 1-alpha", "hif-1a"],
    # PI3K
    "PI3K":    ["pi3k", "pik3ca", "phosphoinositide 3-kinase", "pi3 kinase"],
    # FOXO3
    "FOXO3":   ["foxo3", "foxo3a", "forkhead box o3"],
    # PGC-1α
    "PGC-1α":  ["pgc-1a", "pgc1a", "ppargc1a", "pgc1-alpha"],
    # GR
    "GR":      ["glucocorticoid receptor", "nr3c1"],
    # CRH
    "CRH":     ["crh", "corticotropin-releasing hormone", "corticotropin releasing hormone", "crf",
                "corticotropin-releasing factor"],
    # ACTH
    "ACTH":    ["acth", "adrenocorticotropic hormone", "adrenocorticotrophic hormone", "corticotropin"],
    # Cortisol
    "Cortisol": ["cortisol", "hydrocortisone", "compound f", "free cortisol", "serum cortisol"],
    # DHEA
    "DHEA":    ["dhea", "dehydroepiandrosterone", "5-dehydroepiandrosterone"],
    "DHEA-S":  ["dhea-s", "dheas", "dhea sulfate", "dehydroepiandrosterone sulfate"],
    # Pregnenolone
    "Pregnenolone": ["pregnenolone", "p5", "5-pregnenolone"],
    # Insulin receptor
    "Insulin receptor": ["insr", "insulin receptor signaling"],
    # CLOCK
    "CLOCK":   ["clock", "clock gene", "circadian locomotor output cycles kaput"],
    # BMAL1
    "BMAL1":   ["bmal1", "arntl", "mop3"],
    # Autophagy
    "Autophagy": ["autophagy", "autophagic flux", "macroautophagy", "autophagic process"],
    # NAD+
    "NAD+":    ["nad", "nad+", "nicotinamide adenine dinucleotide"],
    # CD38
    "CD38":    ["cd38", "adp-ribosyl cyclase 1", "adp ribosyl cyclase 1"],
    # NAMPT
    "NAMPT":   ["nampt", "visfatin", "pbef", "nicotinamide phosphoribosyltransferase",
                "pre-b cell colony-enhancing factor"],
    # Beclin-1
    "Beclin-1": ["beclin-1", "becn1", "beclin 1"],
    # ULK1
    "ULK1":    ["ulk1", "atg1", "unc-51 like autophagy activating kinase 1"],
    # LC3
    "LC3":     ["lc3", "map1lc3a", "map1lc3b", "lc3-i", "lc3-ii", "lc3b"],
    # p62
    "p62":     ["p62", "sqstm1", "sequestosome 1", "sequestosome-1"],
    # Rapamycin
    "Rapamycin": ["rapamycin", "sirolimus", "rapamune"],
    # Metformin
    "Metformin": ["metformin", "glucophage"],
    # Resveratrol
    "Resveratrol": ["resveratrol", "trans-resveratrol", "3,5,4'-trihydroxy-trans-stilbene"],
}


def db_connect():
    return psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def run() -> None:
    conn = db_connect()
    stats = {"bridges_inserted": 0, "bridges_updated": 0, "aliases_expanded": 0}
    try:
        with conn.cursor() as cur:
            # ---------- A3: Insert bridge entities ----------
            for name, semantic_level, entity_type, aliases in BRIDGE_ENTITIES:
                cur.execute(
                    """
                    INSERT INTO canonical_entities
                        (canonical_name, entity_type, aliases, semantic_level, is_bridge_entity)
                    VALUES (%s, %s, %s, %s, TRUE)
                    ON CONFLICT (canonical_name) DO UPDATE SET
                        entity_type = EXCLUDED.entity_type,
                        aliases = (
                            SELECT ARRAY(SELECT DISTINCT UNNEST(
                                canonical_entities.aliases || EXCLUDED.aliases))
                        ),
                        semantic_level = EXCLUDED.semantic_level,
                        is_bridge_entity = TRUE,
                        updated_at = NOW()
                    RETURNING (xmax = 0) AS was_insert
                    """,
                    (name, entity_type, aliases, semantic_level),
                )
                row = cur.fetchone()
                if row["was_insert"]:
                    stats["bridges_inserted"] += 1
                else:
                    stats["bridges_updated"] += 1

            # ---------- A4: Expand aliases on existing entities ----------
            for canonical_name, new_aliases in ALIAS_EXPANSIONS.items():
                cur.execute(
                    """
                    UPDATE canonical_entities
                    SET aliases = (
                        SELECT ARRAY(SELECT DISTINCT UNNEST(aliases || %s::text[]))
                    ),
                    updated_at = NOW()
                    WHERE canonical_name = %s
                    RETURNING id
                    """,
                    (new_aliases, canonical_name),
                )
                if cur.fetchone():
                    stats["aliases_expanded"] += 1

            conn.commit()

        # Report
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM canonical_entities")
            total = cur.fetchone()["n"]
            cur.execute(
                """SELECT semantic_level, COUNT(*) AS n
                   FROM canonical_entities GROUP BY 1 ORDER BY 2 DESC"""
            )
            sem_dist = cur.fetchall()
            cur.execute(
                """SELECT COUNT(*) AS n FROM canonical_entities WHERE is_bridge_entity = TRUE"""
            )
            bridges = cur.fetchone()["n"]
            cur.execute(
                """SELECT canonical_name, array_length(aliases, 1) AS alias_count
                   FROM canonical_entities WHERE aliases IS NOT NULL
                   ORDER BY alias_count DESC NULLS LAST LIMIT 10"""
            )
            top_aliases = cur.fetchall()

        log.info("=" * 60)
        log.info("SPRINT A3+A4 COMPLETE")
        log.info("=" * 60)
        for k, v in stats.items():
            log.info("  %-30s %s", k, v)
        log.info("")
        log.info("canonical_entities now: %s (bridge entities: %s)", total, bridges)
        log.info("")
        log.info("Semantic level distribution:")
        for r in sem_dist:
            log.info("  %-12s %s", r["semantic_level"] or "(none)", r["n"])
        log.info("")
        log.info("Top 10 entities by alias count:")
        for r in top_aliases:
            log.info("  %-30s %s aliases", r["canonical_name"][:30], r["alias_count"])
    finally:
        conn.close()


if __name__ == "__main__":
    run()
