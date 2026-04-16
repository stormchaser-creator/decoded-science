"""Pathway backbone data — Tier 1 of the connectome build-out.

Three curated pathways chosen as smoke-test chains for arbitrage traversal
(per Eric + Pearl's 2026-04-16 sequencing):

  1. Steroidogenesis  — cortisol/pregnenolone/DHEA cascade with HPA/circadian
                        Conduction layer (CRH, ACTH, CLOCK, BMAL1, StAR)
  2. NAD+/sirtuins    — longevity axis with circadian NAMPT regulation as the
                        Conduction operation tying it to temporal dynamics
  3. mTOR/autophagy   — nutrient sensing + autophagic clearance, with AMPK as
                        the Conduction switch and ULK1/ATG family as Elimination

Nodes carry:
  - primary_operation (1 of 8 — Reception/Transduction/Conduction/Regulation/
    Synthesis/Defense/Restoration/Elimination)
  - node_type (gene, protein, metabolite, receptor, complex, process, drug)
  - aliases (synonyms, common names)
  - optional: cellular_location, tissue_expression, DB identifiers

This is NOT supposed to be exhaustive — it's the canonical spine of each
chain. Papers populate the flesh around these vertebrae during Tier 2
entity normalization. Pearl's rule: small, high-quality backbone beats
large noisy backbone.

Conduction operation is deliberately over-represented relative to literature
frequency (~0.4% in Decoded's claims) because the temporal/oscillatory
dimension is what makes each cascade a cascade rather than a list.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# STEROIDOGENESIS + HPA + CIRCADIAN CONDUCTION
# ---------------------------------------------------------------------------
STEROIDOGENESIS = {
    "id": "steroidogenesis",
    "canonical_name": "Steroidogenesis (HPA + circadian)",
    "category": "endocrine",
    "description": "Cholesterol-to-steroid cascade with HPA regulation and circadian Conduction layer. Includes cortisol, pregnenolone, DHEA, aldosterone, sex steroids, and the pulsatile timing machinery that governs their release.",
    "operations": ["Synthesis", "Regulation", "Conduction", "Reception"],
    "kegg_ids": ["hsa00140"],
    "nodes": [
        # ----- Cholesterol → precursors (Synthesis backbone) -----
        {"id": "ster_cholesterol", "name": "Cholesterol", "aliases": ["cholesterol"], "node_type": "metabolite", "operation": "Synthesis", "description": "Steroid precursor, starting substrate for all steroidogenesis"},
        {"id": "ster_pregnenolone", "name": "Pregnenolone", "aliases": ["pregnenolone", "P5"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "ster_17oh_pregnenolone", "name": "17-hydroxypregnenolone", "aliases": ["17α-hydroxypregnenolone", "17OH-pregnenolone"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "ster_progesterone", "name": "Progesterone", "aliases": ["progesterone", "P4"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "ster_17oh_progesterone", "name": "17-hydroxyprogesterone", "aliases": ["17α-hydroxyprogesterone", "17OHP"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "ster_dhea", "name": "DHEA", "aliases": ["dehydroepiandrosterone", "dheas-precursor"], "node_type": "metabolite", "operation": "Synthesis", "description": "Dehydroepiandrosterone — adrenal androgen and neurosteroid; declines with age; central to the pregnenolone-steal hypothesis"},
        {"id": "ster_dhea_sulfate", "name": "DHEA-S", "aliases": ["dehydroepiandrosterone sulfate", "DHEAS"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "ster_pregnenolone_sulfate", "name": "Pregnenolone sulfate", "aliases": ["pregnenolone-S", "PREGS"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "ster_androstenedione", "name": "Androstenedione", "aliases": ["4-androstenedione", "A4"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "ster_testosterone", "name": "Testosterone", "aliases": ["testosterone", "T"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "ster_estradiol", "name": "Estradiol", "aliases": ["17β-estradiol", "E2"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "ster_estrone", "name": "Estrone", "aliases": ["E1"], "node_type": "metabolite", "operation": "Synthesis"},
        # ----- Mineralocorticoid + glucocorticoid arm -----
        {"id": "ster_11doc", "name": "11-deoxycorticosterone", "aliases": ["DOC", "11-DOC"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "ster_corticosterone", "name": "Corticosterone", "aliases": ["corticosterone", "B"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "ster_aldosterone", "name": "Aldosterone", "aliases": ["aldo"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "ster_11doc_cortisol", "name": "11-deoxycortisol", "aliases": ["compound S"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "ster_cortisol", "name": "Cortisol", "aliases": ["hydrocortisone", "compound F"], "node_type": "metabolite", "operation": "Synthesis", "description": "Primary human glucocorticoid; diurnally pulsatile; the 'stress steroid'"},
        {"id": "ster_cortisone", "name": "Cortisone", "aliases": ["compound E"], "node_type": "metabolite", "operation": "Synthesis"},
        # ----- Steroidogenic enzymes (Synthesis) -----
        {"id": "ster_cyp11a1", "name": "CYP11A1", "aliases": ["P450scc", "cholesterol side-chain cleavage enzyme"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "ster_cyp17a1", "name": "CYP17A1", "aliases": ["17α-hydroxylase", "17,20-lyase"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "ster_cyp21a2", "name": "CYP21A2", "aliases": ["21-hydroxylase"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "ster_cyp11b1", "name": "CYP11B1", "aliases": ["11β-hydroxylase"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "ster_cyp11b2", "name": "CYP11B2", "aliases": ["aldosterone synthase"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "ster_cyp19a1", "name": "CYP19A1", "aliases": ["aromatase"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "ster_hsd3b1", "name": "HSD3B1", "aliases": ["3β-hydroxysteroid dehydrogenase 1", "3β-HSD"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "ster_hsd3b2", "name": "HSD3B2", "aliases": ["3β-hydroxysteroid dehydrogenase 2"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "ster_hsd17b3", "name": "HSD17B3", "aliases": ["17β-HSD type 3"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "ster_hsd11b1", "name": "HSD11B1", "aliases": ["11β-HSD1"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "ster_hsd11b2", "name": "HSD11B2", "aliases": ["11β-HSD2"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "ster_sult2a1", "name": "SULT2A1", "aliases": ["DHEA sulfotransferase"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "ster_sts", "name": "STS", "aliases": ["steroid sulfatase"], "node_type": "protein", "operation": "Synthesis"},
        # ----- CONDUCTION LAYER — mitochondrial transport + circadian pulse -----
        {"id": "ster_star", "name": "StAR", "aliases": ["steroidogenic acute regulatory protein", "STARD1"], "node_type": "protein", "operation": "Conduction", "description": "Rate-limiting step of steroidogenesis — transports cholesterol from outer to inner mitochondrial membrane; executes the ACTH pulse as steroid output"},
        {"id": "ster_tspo", "name": "TSPO", "aliases": ["translocator protein", "peripheral benzodiazepine receptor"], "node_type": "protein", "operation": "Conduction"},
        {"id": "ster_clock", "name": "CLOCK", "aliases": ["circadian locomotor output cycles kaput"], "node_type": "gene", "operation": "Conduction", "description": "Core circadian transcription factor; heterodimerizes with BMAL1 to drive circadian Conduction"},
        {"id": "ster_bmal1", "name": "BMAL1", "aliases": ["ARNTL", "MOP3"], "node_type": "gene", "operation": "Conduction"},
        {"id": "ster_per1", "name": "PER1", "aliases": ["period 1"], "node_type": "gene", "operation": "Conduction"},
        {"id": "ster_per2", "name": "PER2", "aliases": ["period 2"], "node_type": "gene", "operation": "Conduction"},
        {"id": "ster_cry1", "name": "CRY1", "aliases": ["cryptochrome 1"], "node_type": "gene", "operation": "Conduction"},
        {"id": "ster_cry2", "name": "CRY2", "aliases": ["cryptochrome 2"], "node_type": "gene", "operation": "Conduction"},
        # ----- HPA REGULATION -----
        {"id": "ster_crh", "name": "CRH", "aliases": ["corticotropin-releasing hormone", "CRF"], "node_type": "protein", "operation": "Regulation", "description": "Hypothalamic peptide initiating the HPA axis — triggers ACTH release"},
        {"id": "ster_crhr1", "name": "CRHR1", "aliases": ["CRH receptor 1"], "node_type": "receptor", "operation": "Reception"},
        {"id": "ster_pomc", "name": "POMC", "aliases": ["pro-opiomelanocortin"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "ster_acth", "name": "ACTH", "aliases": ["adrenocorticotropic hormone", "corticotropin"], "node_type": "protein", "operation": "Regulation", "description": "Pituitary peptide; pulsatile release drives adrenal cortisol synthesis via StAR/CYP11A1"},
        {"id": "ster_mc2r", "name": "MC2R", "aliases": ["ACTH receptor", "melanocortin 2 receptor"], "node_type": "receptor", "operation": "Reception"},
        {"id": "ster_gr", "name": "GR", "aliases": ["NR3C1", "glucocorticoid receptor"], "node_type": "receptor", "operation": "Reception"},
        {"id": "ster_mr", "name": "MR", "aliases": ["NR3C2", "mineralocorticoid receptor"], "node_type": "receptor", "operation": "Reception"},
        {"id": "ster_sf1", "name": "SF-1", "aliases": ["NR5A1", "steroidogenic factor 1"], "node_type": "protein", "operation": "Regulation"},
        # ----- Tissues/processes -----
        {"id": "ster_hypothalamus", "name": "Hypothalamus", "aliases": ["hypothalamic nucleus"], "node_type": "tissue", "operation": "Regulation"},
        {"id": "ster_pituitary", "name": "Pituitary", "aliases": ["anterior pituitary", "adenohypophysis"], "node_type": "tissue", "operation": "Regulation"},
        {"id": "ster_adrenal_cortex", "name": "Adrenal cortex", "aliases": ["adrenal gland cortex", "zona fasciculata"], "node_type": "tissue", "operation": "Synthesis"},
        {"id": "ster_hpa_axis", "name": "HPA axis", "aliases": ["hypothalamic-pituitary-adrenal axis"], "node_type": "process", "operation": "Regulation"},
        {"id": "ster_pregnenolone_steal", "name": "Pregnenolone steal", "aliases": ["cortisol steal"], "node_type": "process", "operation": "Regulation", "description": "Hypothesized shunting of pregnenolone toward cortisol synthesis under chronic stress, depleting DHEA and sex-steroid substrates"},
    ],
    "edges": [
        {"from": "ster_cholesterol", "to": "ster_pregnenolone", "edge_type": "converts_to", "enzyme": "ster_cyp11a1", "rate_limiting": True, "mechanism": "Cholesterol side-chain cleavage inside mitochondrial matrix after StAR-mediated transport"},
        {"from": "ster_star", "to": "ster_cholesterol", "edge_type": "transports", "rate_limiting": True, "mechanism": "Transfers cholesterol from outer to inner mitochondrial membrane — acute regulatory step controlled by ACTH"},
        {"from": "ster_pregnenolone", "to": "ster_progesterone", "edge_type": "converts_to", "enzyme": "ster_hsd3b1", "mechanism": "3β-HSD oxidation at C3, isomerization Δ5→Δ4"},
        {"from": "ster_pregnenolone", "to": "ster_17oh_pregnenolone", "edge_type": "converts_to", "enzyme": "ster_cyp17a1", "mechanism": "17α-hydroxylation"},
        {"from": "ster_17oh_pregnenolone", "to": "ster_dhea", "edge_type": "converts_to", "enzyme": "ster_cyp17a1", "mechanism": "17,20-lyase activity"},
        {"from": "ster_dhea", "to": "ster_androstenedione", "edge_type": "converts_to", "enzyme": "ster_hsd3b2"},
        {"from": "ster_dhea", "to": "ster_dhea_sulfate", "edge_type": "converts_to", "enzyme": "ster_sult2a1", "reversible": True},
        {"from": "ster_dhea_sulfate", "to": "ster_dhea", "edge_type": "converts_to", "enzyme": "ster_sts"},
        {"from": "ster_pregnenolone", "to": "ster_pregnenolone_sulfate", "edge_type": "converts_to", "enzyme": "ster_sult2a1"},
        {"from": "ster_progesterone", "to": "ster_17oh_progesterone", "edge_type": "converts_to", "enzyme": "ster_cyp17a1"},
        {"from": "ster_17oh_progesterone", "to": "ster_11doc_cortisol", "edge_type": "converts_to", "enzyme": "ster_cyp21a2"},
        {"from": "ster_11doc_cortisol", "to": "ster_cortisol", "edge_type": "converts_to", "enzyme": "ster_cyp11b1", "rate_limiting": True},
        {"from": "ster_progesterone", "to": "ster_11doc", "edge_type": "converts_to", "enzyme": "ster_cyp21a2"},
        {"from": "ster_11doc", "to": "ster_corticosterone", "edge_type": "converts_to", "enzyme": "ster_cyp11b1"},
        {"from": "ster_corticosterone", "to": "ster_aldosterone", "edge_type": "converts_to", "enzyme": "ster_cyp11b2", "rate_limiting": True},
        {"from": "ster_androstenedione", "to": "ster_testosterone", "edge_type": "converts_to", "enzyme": "ster_hsd17b3"},
        {"from": "ster_testosterone", "to": "ster_estradiol", "edge_type": "converts_to", "enzyme": "ster_cyp19a1"},
        {"from": "ster_androstenedione", "to": "ster_estrone", "edge_type": "converts_to", "enzyme": "ster_cyp19a1"},
        {"from": "ster_cortisol", "to": "ster_cortisone", "edge_type": "converts_to", "enzyme": "ster_hsd11b2"},
        {"from": "ster_cortisone", "to": "ster_cortisol", "edge_type": "converts_to", "enzyme": "ster_hsd11b1"},
        # HPA regulation
        {"from": "ster_hypothalamus", "to": "ster_crh", "edge_type": "secretes", "mechanism": "Parvocellular paraventricular neurons release CRH into hypophyseal portal system"},
        {"from": "ster_crh", "to": "ster_crhr1", "edge_type": "activates"},
        {"from": "ster_crhr1", "to": "ster_pomc", "edge_type": "upregulates", "mechanism": "Gs/PKA/CREB signaling increases POMC transcription in corticotrophs"},
        {"from": "ster_pomc", "to": "ster_acth", "edge_type": "converts_to", "mechanism": "Prohormone convertase cleavage of POMC yields ACTH"},
        {"from": "ster_pituitary", "to": "ster_acth", "edge_type": "secretes"},
        {"from": "ster_acth", "to": "ster_mc2r", "edge_type": "activates"},
        {"from": "ster_mc2r", "to": "ster_star", "edge_type": "activates", "mechanism": "Gs/PKA pathway phosphorylates StAR and promotes cholesterol transport"},
        {"from": "ster_adrenal_cortex", "to": "ster_cortisol", "edge_type": "secretes"},
        {"from": "ster_cortisol", "to": "ster_gr", "edge_type": "activates"},
        {"from": "ster_gr", "to": "ster_crh", "edge_type": "inhibits", "mechanism": "Glucocorticoid negative feedback on hypothalamic CRH transcription"},
        {"from": "ster_gr", "to": "ster_acth", "edge_type": "inhibits", "mechanism": "Glucocorticoid negative feedback on POMC/ACTH at pituitary"},
        {"from": "ster_aldosterone", "to": "ster_mr", "edge_type": "activates"},
        {"from": "ster_sf1", "to": "ster_star", "edge_type": "activates"},
        {"from": "ster_sf1", "to": "ster_cyp11a1", "edge_type": "activates"},
        # Circadian conduction
        {"from": "ster_clock", "to": "ster_bmal1", "edge_type": "binds", "reversible": True, "mechanism": "CLOCK:BMAL1 heterodimer drives E-box transcription of PER/CRY and downstream targets"},
        {"from": "ster_bmal1", "to": "ster_per1", "edge_type": "activates"},
        {"from": "ster_bmal1", "to": "ster_per2", "edge_type": "activates"},
        {"from": "ster_bmal1", "to": "ster_cry1", "edge_type": "activates"},
        {"from": "ster_bmal1", "to": "ster_cry2", "edge_type": "activates"},
        {"from": "ster_per1", "to": "ster_clock", "edge_type": "inhibits", "mechanism": "Negative feedback loop of circadian oscillator"},
        {"from": "ster_cry1", "to": "ster_clock", "edge_type": "inhibits"},
        {"from": "ster_bmal1", "to": "ster_star", "edge_type": "activates", "mechanism": "Circadian regulation of StAR transcription imposes diurnal rhythm on cortisol synthesis"},
        {"from": "ster_bmal1", "to": "ster_crh", "edge_type": "activates", "mechanism": "Suprachiasmatic clock drives diurnal CRH release via multisynaptic pathway"},
        # Pregnenolone steal (hypothesis)
        {"from": "ster_pregnenolone_steal", "to": "ster_cortisol", "edge_type": "upregulates", "mechanism": "Sustained HPA activation directs pregnenolone substrate toward cortisol at the expense of DHEA/sex steroid synthesis"},
        {"from": "ster_pregnenolone_steal", "to": "ster_dhea", "edge_type": "downregulates", "mechanism": "Pregnenolone substrate diverted away from 17,20-lyase (DHEA) branch"},
    ],
}

# ---------------------------------------------------------------------------
# NAD+ / SIRTUINS / LONGEVITY — with circadian NAMPT Conduction layer
# ---------------------------------------------------------------------------
NAD_SIRTUINS = {
    "id": "nad_sirtuins",
    "canonical_name": "NAD+ / Sirtuins / Longevity",
    "category": "metabolism",
    "description": "NAD+ biosynthesis, consumption, and sirtuin-mediated regulation; NAMPT as the rate-limiting circadian-controlled enzyme; CD38 as the major age-related NAD+ drain; sirtuins as metabolic/longevity effectors.",
    "operations": ["Synthesis", "Regulation", "Restoration", "Conduction", "Defense", "Elimination"],
    "kegg_ids": ["hsa00760"],
    "nodes": [
        # Core NAD+ metabolites
        {"id": "nad_nadplus", "name": "NAD+", "aliases": ["nicotinamide adenine dinucleotide", "NAD"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "nad_nadh", "name": "NADH", "aliases": ["reduced NAD"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "nad_nadp", "name": "NADP+", "aliases": ["nicotinamide adenine dinucleotide phosphate"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "nad_nadph", "name": "NADPH", "aliases": ["reduced NADP"], "node_type": "metabolite", "operation": "Synthesis"},
        # Precursors
        {"id": "nad_nam", "name": "Nicotinamide", "aliases": ["NAM", "niacinamide"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "nad_nr", "name": "Nicotinamide riboside", "aliases": ["NR"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "nad_nmn", "name": "Nicotinamide mononucleotide", "aliases": ["NMN"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "nad_na", "name": "Nicotinic acid", "aliases": ["niacin", "vitamin B3"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "nad_trp", "name": "Tryptophan", "aliases": ["L-tryptophan"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "nad_kyn", "name": "Kynurenine", "aliases": ["L-kynurenine"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "nad_qa", "name": "Quinolinic acid", "aliases": ["QA"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "nad_naad", "name": "NAAD", "aliases": ["nicotinic acid adenine dinucleotide"], "node_type": "metabolite", "operation": "Synthesis"},
        # Synthesis enzymes
        {"id": "nad_nampt", "name": "NAMPT", "aliases": ["nicotinamide phosphoribosyltransferase", "visfatin", "PBEF"], "node_type": "protein", "operation": "Synthesis", "description": "Rate-limiting salvage enzyme converting nicotinamide to NMN; transcriptionally regulated by CLOCK/BMAL1 with ~24h periodicity — the Conduction node tying NAD+ to the circadian clock"},
        {"id": "nad_nmnat1", "name": "NMNAT1", "aliases": ["nuclear NMNAT"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "nad_nmnat2", "name": "NMNAT2", "aliases": ["cytosolic NMNAT"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "nad_nmnat3", "name": "NMNAT3", "aliases": ["mitochondrial NMNAT"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "nad_naprt", "name": "NAPRT", "aliases": ["nicotinate phosphoribosyltransferase"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "nad_nadk", "name": "NADK", "aliases": ["NAD kinase"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "nad_nads", "name": "NADSYN1", "aliases": ["NAD synthetase"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "nad_qprt", "name": "QPRT", "aliases": ["quinolinate phosphoribosyltransferase"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "nad_ido1", "name": "IDO1", "aliases": ["indoleamine 2,3-dioxygenase"], "node_type": "protein", "operation": "Defense"},
        {"id": "nad_tdo2", "name": "TDO2", "aliases": ["tryptophan 2,3-dioxygenase"], "node_type": "protein", "operation": "Synthesis"},
        # Consumers (drains)
        {"id": "nad_cd38", "name": "CD38", "aliases": ["ADP-ribosyl cyclase 1"], "node_type": "protein", "operation": "Defense", "description": "Major age-associated NAD+ consumer; rises with inflammaging, drives NAD+ decline that limits sirtuin activity"},
        {"id": "nad_cd157", "name": "CD157", "aliases": ["BST1"], "node_type": "protein", "operation": "Defense"},
        {"id": "nad_parp1", "name": "PARP1", "aliases": ["poly(ADP-ribose) polymerase 1"], "node_type": "protein", "operation": "Defense"},
        {"id": "nad_parp2", "name": "PARP2", "aliases": ["poly(ADP-ribose) polymerase 2"], "node_type": "protein", "operation": "Defense"},
        # Sirtuins
        {"id": "nad_sirt1", "name": "SIRT1", "aliases": ["sirtuin 1"], "node_type": "protein", "operation": "Regulation", "description": "Nuclear NAD+-dependent deacetylase; master metabolic regulator; feeds back onto CLOCK/BMAL1"},
        {"id": "nad_sirt2", "name": "SIRT2", "aliases": ["sirtuin 2"], "node_type": "protein", "operation": "Regulation"},
        {"id": "nad_sirt3", "name": "SIRT3", "aliases": ["sirtuin 3", "mitochondrial sirtuin"], "node_type": "protein", "operation": "Restoration"},
        {"id": "nad_sirt4", "name": "SIRT4", "aliases": ["sirtuin 4"], "node_type": "protein", "operation": "Regulation"},
        {"id": "nad_sirt5", "name": "SIRT5", "aliases": ["sirtuin 5"], "node_type": "protein", "operation": "Regulation"},
        {"id": "nad_sirt6", "name": "SIRT6", "aliases": ["sirtuin 6"], "node_type": "protein", "operation": "Defense"},
        {"id": "nad_sirt7", "name": "SIRT7", "aliases": ["sirtuin 7"], "node_type": "protein", "operation": "Regulation"},
        # Circadian (shared with steroidogenesis but duplicate here for pathway completeness)
        {"id": "nad_clock", "name": "CLOCK", "aliases": ["circadian locomotor output cycles kaput"], "node_type": "gene", "operation": "Conduction"},
        {"id": "nad_bmal1", "name": "BMAL1", "aliases": ["ARNTL", "MOP3"], "node_type": "gene", "operation": "Conduction"},
        # Downstream sirtuin targets
        {"id": "nad_foxo3", "name": "FOXO3", "aliases": ["forkhead box O3"], "node_type": "protein", "operation": "Regulation"},
        {"id": "nad_pgc1a", "name": "PGC-1α", "aliases": ["PPARGC1A"], "node_type": "protein", "operation": "Regulation"},
        {"id": "nad_p53", "name": "p53", "aliases": ["TP53"], "node_type": "protein", "operation": "Defense"},
        {"id": "nad_nfkb", "name": "NF-κB", "aliases": ["NFKB1", "RELA"], "node_type": "protein", "operation": "Defense"},
        {"id": "nad_hif1a", "name": "HIF-1α", "aliases": ["hypoxia-inducible factor 1-alpha"], "node_type": "protein", "operation": "Regulation"},
        {"id": "nad_mito_biogenesis", "name": "Mitochondrial biogenesis", "aliases": ["mitogenesis"], "node_type": "process", "operation": "Restoration"},
        {"id": "nad_autophagy", "name": "Autophagy", "aliases": ["autophagic clearance"], "node_type": "process", "operation": "Restoration"},
        {"id": "nad_dna_repair", "name": "DNA repair", "aliases": ["DDR"], "node_type": "process", "operation": "Defense"},
        {"id": "nad_senescence", "name": "Cellular senescence", "aliases": ["inflammaging"], "node_type": "process", "operation": "Defense"},
        # Drugs / interventions
        {"id": "nad_apigenin", "name": "Apigenin", "aliases": ["flavonoid apigenin"], "node_type": "drug", "operation": "Defense"},
        {"id": "nad_78c", "name": "78c", "aliases": ["CD38 inhibitor"], "node_type": "drug", "operation": "Defense"},
        {"id": "nad_resveratrol", "name": "Resveratrol", "aliases": ["trans-resveratrol"], "node_type": "drug", "operation": "Regulation"},
    ],
    "edges": [
        # Salvage pathway
        {"from": "nad_nam", "to": "nad_nmn", "edge_type": "converts_to", "enzyme": "nad_nampt", "rate_limiting": True, "mechanism": "Nicotinamide phosphoribosyltransferase rate-limiting step of the salvage pathway"},
        {"from": "nad_nmn", "to": "nad_nadplus", "edge_type": "converts_to", "enzyme": "nad_nmnat1"},
        {"from": "nad_nr", "to": "nad_nmn", "edge_type": "converts_to", "enzyme": "nad_nmnat1", "mechanism": "NRK-mediated phosphorylation, then NMNAT-mediated adenylation"},
        # De novo from tryptophan
        {"from": "nad_trp", "to": "nad_kyn", "edge_type": "converts_to", "enzyme": "nad_ido1"},
        {"from": "nad_kyn", "to": "nad_qa", "edge_type": "converts_to", "mechanism": "Multi-step kynurenine pathway"},
        {"from": "nad_qa", "to": "nad_naad", "edge_type": "converts_to", "enzyme": "nad_qprt"},
        {"from": "nad_naad", "to": "nad_nadplus", "edge_type": "converts_to", "enzyme": "nad_nads"},
        # Preiss-Handler (from nicotinic acid)
        {"from": "nad_na", "to": "nad_naad", "edge_type": "converts_to", "enzyme": "nad_naprt"},
        # NADP branch
        {"from": "nad_nadplus", "to": "nad_nadp", "edge_type": "converts_to", "enzyme": "nad_nadk"},
        # Consumers
        {"from": "nad_cd38", "to": "nad_nadplus", "edge_type": "degrades", "mechanism": "Hydrolysis of NAD+ to nicotinamide and ADP-ribose"},
        {"from": "nad_parp1", "to": "nad_nadplus", "edge_type": "degrades", "mechanism": "Poly-ADP-ribosylation consumes NAD+ during DNA damage response"},
        {"from": "nad_parp2", "to": "nad_nadplus", "edge_type": "degrades"},
        {"from": "nad_sirt1", "to": "nad_nadplus", "edge_type": "requires"},
        {"from": "nad_sirt3", "to": "nad_nadplus", "edge_type": "requires"},
        {"from": "nad_sirt6", "to": "nad_nadplus", "edge_type": "requires"},
        # Sirtuin regulation of clock (the feedback loop)
        {"from": "nad_sirt1", "to": "nad_clock", "edge_type": "inhibits", "mechanism": "SIRT1 deacetylates BMAL1 and PER2; closes the feedback loop between metabolism and circadian Conduction"},
        {"from": "nad_sirt1", "to": "nad_bmal1", "edge_type": "inhibits", "mechanism": "Deacetylates BMAL1 lysine"},
        {"from": "nad_clock", "to": "nad_bmal1", "edge_type": "binds", "mechanism": "CLOCK:BMAL1 heterodimer"},
        {"from": "nad_bmal1", "to": "nad_nampt", "edge_type": "activates", "mechanism": "CLOCK/BMAL1 E-box drives NAMPT transcription with 24h periodicity — imposes circadian Conduction on NAD+ availability"},
        # Sirtuin effects
        {"from": "nad_sirt1", "to": "nad_pgc1a", "edge_type": "activates", "mechanism": "Deacetylation of PGC-1α increases activity"},
        {"from": "nad_sirt1", "to": "nad_foxo3", "edge_type": "activates"},
        {"from": "nad_sirt1", "to": "nad_p53", "edge_type": "inhibits", "mechanism": "Deacetylation of p53 limits apoptosis induction"},
        {"from": "nad_sirt1", "to": "nad_nfkb", "edge_type": "inhibits", "mechanism": "Deacetylation of RelA subunit reduces inflammatory transcription"},
        {"from": "nad_sirt1", "to": "nad_hif1a", "edge_type": "inhibits"},
        {"from": "nad_sirt3", "to": "nad_mito_biogenesis", "edge_type": "activates"},
        {"from": "nad_sirt1", "to": "nad_autophagy", "edge_type": "activates"},
        {"from": "nad_sirt6", "to": "nad_dna_repair", "edge_type": "activates"},
        {"from": "nad_pgc1a", "to": "nad_mito_biogenesis", "edge_type": "activates"},
        # Aging axis
        {"from": "nad_cd38", "to": "nad_senescence", "edge_type": "activates", "mechanism": "CD38-mediated NAD+ depletion cripples sirtuin-dependent stress response"},
        {"from": "nad_senescence", "to": "nad_nfkb", "edge_type": "activates", "mechanism": "SASP drives NF-κB activation"},
        {"from": "nad_nfkb", "to": "nad_cd38", "edge_type": "activates", "mechanism": "Inflammaging feedback increases CD38 expression"},
        {"from": "nad_senescence", "to": "nad_sirt1", "edge_type": "inhibits"},
        # Interventions
        {"from": "nad_apigenin", "to": "nad_cd38", "edge_type": "inhibits"},
        {"from": "nad_78c", "to": "nad_cd38", "edge_type": "inhibits"},
        {"from": "nad_resveratrol", "to": "nad_sirt1", "edge_type": "activates"},
    ],
}

# ---------------------------------------------------------------------------
# mTOR / AUTOPHAGY — nutrient sensing, AMPK Conduction switch, ULK1/ATG Elimination
# ---------------------------------------------------------------------------
MTOR_AUTOPHAGY = {
    "id": "mtor_autophagy",
    "canonical_name": "mTOR signaling and autophagy",
    "category": "nutrient_sensing",
    "description": "mTORC1/2 signaling integrates nutrient, energy, and growth factor inputs; AMPK acts as the Conduction switch between growth and autophagy states; ULK1/ATG machinery executes autophagic Elimination.",
    "operations": ["Regulation", "Transduction", "Synthesis", "Restoration", "Elimination", "Conduction"],
    "kegg_ids": ["hsa04150", "hsa04140"],
    "nodes": [
        # mTOR core
        {"id": "mtor_mtor", "name": "mTOR", "aliases": ["MTOR", "FRAP1", "mechanistic target of rapamycin"], "node_type": "protein", "operation": "Regulation"},
        {"id": "mtor_raptor", "name": "RAPTOR", "aliases": ["RPTOR", "regulatory-associated protein of mTOR"], "node_type": "protein", "operation": "Regulation"},
        {"id": "mtor_rictor", "name": "RICTOR", "aliases": ["rapamycin-insensitive companion of mTOR"], "node_type": "protein", "operation": "Regulation"},
        {"id": "mtor_mlst8", "name": "mLST8", "aliases": ["GβL", "MLST8"], "node_type": "protein", "operation": "Regulation"},
        {"id": "mtor_pras40", "name": "PRAS40", "aliases": ["AKT1S1"], "node_type": "protein", "operation": "Regulation"},
        {"id": "mtor_deptor", "name": "DEPTOR", "aliases": ["DEPDC6"], "node_type": "protein", "operation": "Regulation"},
        {"id": "mtor_msin1", "name": "mSIN1", "aliases": ["MAPKAP1"], "node_type": "protein", "operation": "Regulation"},
        {"id": "mtor_mtorc1", "name": "mTORC1", "aliases": ["mTOR complex 1"], "node_type": "complex", "operation": "Regulation", "description": "mTOR + RAPTOR + mLST8; rapamycin-sensitive; drives anabolism and suppresses autophagy"},
        {"id": "mtor_mtorc2", "name": "mTORC2", "aliases": ["mTOR complex 2"], "node_type": "complex", "operation": "Regulation"},
        # Upstream regulators
        {"id": "mtor_tsc1", "name": "TSC1", "aliases": ["hamartin"], "node_type": "protein", "operation": "Regulation"},
        {"id": "mtor_tsc2", "name": "TSC2", "aliases": ["tuberin"], "node_type": "protein", "operation": "Regulation"},
        {"id": "mtor_rheb", "name": "Rheb", "aliases": ["RHEB", "Ras homolog enriched in brain"], "node_type": "protein", "operation": "Transduction"},
        {"id": "mtor_ampk", "name": "AMPK", "aliases": ["PRKAA1", "AMP-activated protein kinase"], "node_type": "protein", "operation": "Conduction", "description": "Master metabolic switch between anabolic (mTORC1-on) and catabolic (autophagy-on) states — the Conduction node that toggles the entire pathway"},
        {"id": "mtor_lkb1", "name": "LKB1", "aliases": ["STK11"], "node_type": "protein", "operation": "Regulation"},
        {"id": "mtor_akt", "name": "Akt", "aliases": ["AKT1", "protein kinase B"], "node_type": "protein", "operation": "Transduction"},
        {"id": "mtor_pi3k", "name": "PI3K", "aliases": ["PIK3CA"], "node_type": "protein", "operation": "Transduction"},
        {"id": "mtor_pten", "name": "PTEN", "aliases": ["phosphatase and tensin homolog"], "node_type": "protein", "operation": "Regulation"},
        {"id": "mtor_insulin_receptor", "name": "Insulin receptor", "aliases": ["INSR"], "node_type": "receptor", "operation": "Reception"},
        {"id": "mtor_igf1r", "name": "IGF1R", "aliases": ["insulin-like growth factor 1 receptor"], "node_type": "receptor", "operation": "Reception"},
        # Amino acid sensing
        {"id": "mtor_ragulator", "name": "Ragulator", "aliases": ["LAMTOR1-5 complex"], "node_type": "complex", "operation": "Reception"},
        {"id": "mtor_rag_gtpases", "name": "Rag GTPases", "aliases": ["RRAGA", "RRAGB", "RRAGC", "RRAGD"], "node_type": "protein", "operation": "Transduction"},
        {"id": "mtor_gator1", "name": "GATOR1", "aliases": ["DEPDC5-NPRL2-NPRL3 complex"], "node_type": "complex", "operation": "Regulation"},
        {"id": "mtor_gator2", "name": "GATOR2", "aliases": ["MIOS-WDR24-WDR59-SEH1L-SEC13 complex"], "node_type": "complex", "operation": "Regulation"},
        {"id": "mtor_sestrin2", "name": "Sestrin2", "aliases": ["SESN2"], "node_type": "protein", "operation": "Regulation"},
        # Amino acids (inputs)
        {"id": "mtor_leucine", "name": "Leucine", "aliases": ["L-leucine"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "mtor_arginine", "name": "Arginine", "aliases": ["L-arginine"], "node_type": "metabolite", "operation": "Synthesis"},
        {"id": "mtor_glucose", "name": "Glucose", "aliases": ["D-glucose"], "node_type": "metabolite", "operation": "Synthesis"},
        # Autophagy initiation
        {"id": "mtor_ulk1", "name": "ULK1", "aliases": ["ATG1"], "node_type": "protein", "operation": "Restoration", "description": "Autophagy-initiating kinase; repressed by mTORC1 phosphorylation, activated by AMPK phosphorylation"},
        {"id": "mtor_ulk2", "name": "ULK2", "aliases": ["ATG1-like"], "node_type": "protein", "operation": "Restoration"},
        {"id": "mtor_atg13", "name": "ATG13", "aliases": ["autophagy-related 13"], "node_type": "protein", "operation": "Restoration"},
        {"id": "mtor_atg101", "name": "ATG101", "aliases": ["C12orf44"], "node_type": "protein", "operation": "Restoration"},
        {"id": "mtor_fip200", "name": "FIP200", "aliases": ["RB1CC1"], "node_type": "protein", "operation": "Restoration"},
        {"id": "mtor_beclin1", "name": "Beclin-1", "aliases": ["BECN1"], "node_type": "protein", "operation": "Restoration"},
        {"id": "mtor_vps34", "name": "VPS34", "aliases": ["PIK3C3"], "node_type": "protein", "operation": "Restoration"},
        {"id": "mtor_atg14", "name": "ATG14", "aliases": ["ATG14L", "Barkor"], "node_type": "protein", "operation": "Restoration"},
        # Autophagosome elongation
        {"id": "mtor_atg5", "name": "ATG5", "aliases": ["autophagy-related 5"], "node_type": "protein", "operation": "Elimination"},
        {"id": "mtor_atg7", "name": "ATG7", "aliases": ["autophagy-related 7"], "node_type": "protein", "operation": "Elimination"},
        {"id": "mtor_atg12", "name": "ATG12", "aliases": ["autophagy-related 12"], "node_type": "protein", "operation": "Elimination"},
        {"id": "mtor_atg16l1", "name": "ATG16L1", "aliases": ["autophagy-related 16-like 1"], "node_type": "protein", "operation": "Elimination"},
        {"id": "mtor_lc3", "name": "LC3", "aliases": ["MAP1LC3A", "MAP1LC3B"], "node_type": "protein", "operation": "Elimination"},
        {"id": "mtor_p62", "name": "p62", "aliases": ["SQSTM1", "sequestosome 1"], "node_type": "protein", "operation": "Elimination"},
        {"id": "mtor_gabarap", "name": "GABARAP", "aliases": ["GABA receptor-associated protein"], "node_type": "protein", "operation": "Elimination"},
        # Downstream
        {"id": "mtor_4ebp1", "name": "4E-BP1", "aliases": ["EIF4EBP1"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "mtor_s6k1", "name": "S6K1", "aliases": ["RPS6KB1", "p70 S6 kinase"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "mtor_rps6", "name": "S6", "aliases": ["RPS6", "ribosomal protein S6"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "mtor_eif4e", "name": "eIF4E", "aliases": ["EIF4E"], "node_type": "protein", "operation": "Synthesis"},
        {"id": "mtor_autophagy", "name": "Autophagy", "aliases": ["autophagic flux"], "node_type": "process", "operation": "Elimination"},
        {"id": "mtor_protein_synthesis", "name": "Protein synthesis", "aliases": ["translation"], "node_type": "process", "operation": "Synthesis"},
        # Drugs
        {"id": "mtor_rapamycin", "name": "Rapamycin", "aliases": ["sirolimus"], "node_type": "drug", "operation": "Regulation"},
        {"id": "mtor_torin1", "name": "Torin1", "aliases": ["torin-1"], "node_type": "drug", "operation": "Regulation"},
        {"id": "mtor_metformin", "name": "Metformin", "aliases": ["glucophage"], "node_type": "drug", "operation": "Regulation"},
    ],
    "edges": [
        # mTORC1 complex
        {"from": "mtor_mtor", "to": "mtor_raptor", "edge_type": "binds", "reversible": True},
        {"from": "mtor_mtor", "to": "mtor_mlst8", "edge_type": "binds", "reversible": True},
        {"from": "mtor_raptor", "to": "mtor_mtorc1", "edge_type": "binds"},
        {"from": "mtor_mtor", "to": "mtor_mtorc1", "edge_type": "binds"},
        {"from": "mtor_rictor", "to": "mtor_mtorc2", "edge_type": "binds"},
        {"from": "mtor_msin1", "to": "mtor_mtorc2", "edge_type": "binds"},
        # Upstream: TSC/Rheb axis
        {"from": "mtor_tsc1", "to": "mtor_tsc2", "edge_type": "binds", "mechanism": "TSC1-TSC2 form GAP complex for Rheb"},
        {"from": "mtor_tsc2", "to": "mtor_rheb", "edge_type": "inhibits", "mechanism": "GAP activity converts Rheb-GTP to Rheb-GDP, inactivating it"},
        {"from": "mtor_rheb", "to": "mtor_mtorc1", "edge_type": "activates", "mechanism": "Rheb-GTP directly activates mTORC1 kinase at lysosomal surface"},
        # AMPK as Conduction switch
        {"from": "mtor_lkb1", "to": "mtor_ampk", "edge_type": "activates", "mechanism": "LKB1 phosphorylates AMPK at T172 under energy stress"},
        {"from": "mtor_ampk", "to": "mtor_tsc2", "edge_type": "activates", "mechanism": "AMPK phosphorylates TSC2, enhancing GAP activity and suppressing mTORC1"},
        {"from": "mtor_ampk", "to": "mtor_raptor", "edge_type": "inhibits", "mechanism": "Direct AMPK phosphorylation of RAPTOR inhibits mTORC1 substrate binding"},
        {"from": "mtor_ampk", "to": "mtor_ulk1", "edge_type": "activates", "mechanism": "AMPK directly phosphorylates ULK1 at S555/S317 to initiate autophagy"},
        # Insulin/PI3K/Akt branch
        {"from": "mtor_insulin_receptor", "to": "mtor_pi3k", "edge_type": "activates"},
        {"from": "mtor_igf1r", "to": "mtor_pi3k", "edge_type": "activates"},
        {"from": "mtor_pi3k", "to": "mtor_akt", "edge_type": "activates", "mechanism": "PI3K generates PIP3 which recruits Akt to the membrane"},
        {"from": "mtor_pten", "to": "mtor_akt", "edge_type": "inhibits", "mechanism": "PTEN dephosphorylates PIP3 back to PIP2"},
        {"from": "mtor_akt", "to": "mtor_tsc2", "edge_type": "inhibits", "mechanism": "Akt phosphorylates TSC2 at S939/T1462, relieving TSC1-TSC2 inhibition of Rheb"},
        {"from": "mtor_akt", "to": "mtor_pras40", "edge_type": "inhibits"},
        {"from": "mtor_mtorc2", "to": "mtor_akt", "edge_type": "activates", "mechanism": "mTORC2 phosphorylates Akt at S473"},
        # Amino acid sensing
        {"from": "mtor_leucine", "to": "mtor_sestrin2", "edge_type": "inhibits", "mechanism": "Leucine binds Sestrin2 and releases its inhibition on GATOR2"},
        {"from": "mtor_sestrin2", "to": "mtor_gator2", "edge_type": "inhibits", "reversible": True},
        {"from": "mtor_gator2", "to": "mtor_gator1", "edge_type": "inhibits"},
        {"from": "mtor_gator1", "to": "mtor_rag_gtpases", "edge_type": "inhibits"},
        {"from": "mtor_rag_gtpases", "to": "mtor_mtorc1", "edge_type": "activates", "mechanism": "Active Rag heterodimer recruits mTORC1 to lysosome surface"},
        {"from": "mtor_ragulator", "to": "mtor_rag_gtpases", "edge_type": "activates", "mechanism": "Ragulator functions as GEF for RagA/B"},
        # Downstream: anabolic targets
        {"from": "mtor_mtorc1", "to": "mtor_s6k1", "edge_type": "activates"},
        {"from": "mtor_s6k1", "to": "mtor_rps6", "edge_type": "activates"},
        {"from": "mtor_mtorc1", "to": "mtor_4ebp1", "edge_type": "inhibits", "mechanism": "Phosphorylation of 4E-BP1 releases eIF4E for cap-dependent translation"},
        {"from": "mtor_4ebp1", "to": "mtor_eif4e", "edge_type": "inhibits", "mechanism": "Unphosphorylated 4E-BP1 sequesters eIF4E"},
        {"from": "mtor_eif4e", "to": "mtor_protein_synthesis", "edge_type": "activates"},
        {"from": "mtor_s6k1", "to": "mtor_protein_synthesis", "edge_type": "activates"},
        # mTORC1 suppresses autophagy
        {"from": "mtor_mtorc1", "to": "mtor_ulk1", "edge_type": "inhibits", "mechanism": "mTORC1 phosphorylates ULK1 at S757, blocking AMPK activation site"},
        {"from": "mtor_mtorc1", "to": "mtor_atg13", "edge_type": "inhibits"},
        # Autophagy initiation
        {"from": "mtor_ulk1", "to": "mtor_atg13", "edge_type": "activates"},
        {"from": "mtor_atg13", "to": "mtor_fip200", "edge_type": "binds"},
        {"from": "mtor_ulk1", "to": "mtor_beclin1", "edge_type": "activates"},
        {"from": "mtor_beclin1", "to": "mtor_vps34", "edge_type": "binds"},
        {"from": "mtor_vps34", "to": "mtor_atg14", "edge_type": "binds"},
        # Elongation (ubiquitin-like conjugation)
        {"from": "mtor_atg7", "to": "mtor_atg12", "edge_type": "activates", "mechanism": "ATG7 is the E1-like enzyme for ATG12 activation"},
        {"from": "mtor_atg12", "to": "mtor_atg5", "edge_type": "binds", "mechanism": "ATG12-ATG5 conjugate"},
        {"from": "mtor_atg16l1", "to": "mtor_atg5", "edge_type": "binds"},
        {"from": "mtor_atg7", "to": "mtor_lc3", "edge_type": "activates"},
        {"from": "mtor_lc3", "to": "mtor_p62", "edge_type": "binds", "mechanism": "LC3-p62 binding selects ubiquitinated cargo for autophagy"},
        {"from": "mtor_lc3", "to": "mtor_autophagy", "edge_type": "activates"},
        {"from": "mtor_p62", "to": "mtor_autophagy", "edge_type": "activates"},
        {"from": "mtor_gabarap", "to": "mtor_autophagy", "edge_type": "activates"},
        # Drugs
        {"from": "mtor_rapamycin", "to": "mtor_mtorc1", "edge_type": "inhibits", "mechanism": "Rapamycin-FKBP12 complex binds the FRB domain of mTOR, allosterically inhibiting mTORC1"},
        {"from": "mtor_torin1", "to": "mtor_mtorc1", "edge_type": "inhibits", "mechanism": "ATP-competitive mTOR kinase inhibitor — blocks both mTORC1 and mTORC2"},
        {"from": "mtor_torin1", "to": "mtor_mtorc2", "edge_type": "inhibits"},
        {"from": "mtor_metformin", "to": "mtor_ampk", "edge_type": "activates", "mechanism": "Metformin inhibits mitochondrial complex I, raising AMP:ATP ratio, activating AMPK"},
        # Inputs to autophagy flux
        {"from": "mtor_ampk", "to": "mtor_autophagy", "edge_type": "activates"},
        {"from": "mtor_mtorc1", "to": "mtor_autophagy", "edge_type": "inhibits"},
    ],
}

ALL_PATHWAYS = [STEROIDOGENESIS, NAD_SIRTUINS, MTOR_AUTOPHAGY]
