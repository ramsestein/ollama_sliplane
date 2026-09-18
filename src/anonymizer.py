"""Self-contained anonymization layer (BERT + regex).

Detects entities with:
  - BERT `bsc-bio-ehr-es-carmen-anon` (multiclass token classification).
  - Regex rules (dates, times, phones, names, addresses, etc.).

and replaces them with reversible placeholders `[TAG_n]`. The
`placeholder -> real text` map lives only on the client: the server
never sees the real data.

No dependencies on `carmina_3_suite/`: all the relevant code lives here.
The only external resource is the BERT model, stored under `models/`.
"""
import os
import re
from pathlib import Path

from . import PROJECT_ROOT

ROOT = PROJECT_ROOT
DEFAULT_MODEL_REPO = "PlanTL-GOB-ES/bsc-bio-ehr-es-carmen-anon"
DEFAULT_MODEL_DIR = Path(os.environ.get("CARMINA_MODEL_DIR", ROOT / "models"))


def _read_env(key, default=""):
    if os.environ.get(key):
        return os.environ[key]
    try:
        with open(ROOT / ".env", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return default


def model_repo():
    return _read_env("BERT_MODEL", DEFAULT_MODEL_REPO)


def model_dirname():
    return model_repo().split("/")[-1]

# ── Unified taxonomy ────────────────────────────────────────────────────────
# BRAT (CARMEN) -> unified taxonomy
BRAT_TO_UNIFIED = {
    "FECHAS": "DATE",
    "HORAS": "TIME",
    "NOMBRE_SUJETO_ASISTENCIA": "NAME",
    "NOMBRE_PERSONAL_SANITARIO": "PROFESSIONAL",
    "FAMILIARES_SUJETO_ASISTENCIA": "FAMILY",
    "PROFESION": "PROFESSION",
    "EDAD_SUJETO_ASISTENCIA": "AGE",
    "SEXO_SUJETO_ASISTENCIA": "SEX",
    "CALLE": "LOCATION",
    "TERRITORIO": "LOCATION",
    "PAIS": "LOCATION",
    "HOSPITAL": "HOSPITAL",
    "CENTRO_SALUD": "HOSPITAL",
    "INSTITUCION": "ORGANIZATION",
    "NUMERO_TELEFONO": "PHONE",
    "NUMERO_FAX": "PHONE",
    "CORREO_ELECTRONICO": "EMAIL",
    "URL_WEB": "URL",
    "NUMERO_IDENTIF": "ID",
    "ID_SUJETO_ASISTENCIA": "ID",
    "ID_CONTACTO_ASISTENCIAL": "ID",
    "ID_ASEGURAMIENTO": "ID",
    "ID_EMPLEO_PERSONAL_SANITARIO": "ID",
    "ID_TITULACION_PERSONAL_SANITARIO": "ID",
    "OTROS_SUJETO_ASISTENCIA": "OTHER",
}

# step2 (regex) labels -> unified taxonomy
STEP2_TO_UNIFIED = {
    "DATE": "DATE",
    "TIME": "TIME",
    "PHONE": "PHONE",
    "DOCTOR": "PROFESSIONAL",
    "AGE": "AGE",
    "LOCATION": "LOCATION",
    "RELATION": "FAMILY",
    "IDENTIFICADOR": "ID",
    "HOSPITAL": "HOSPITAL",
    "PERSON": "NAME",
    "GENERICA": "OTHER",
}

# Unified label -> readable tag for the placeholder
TAGS = {
    "DATE": "FECHA",
    "TIME": "HORA",
    "NAME": "NOMBRE",
    "PROFESSIONAL": "PROFESIONAL",
    "FAMILY": "FAMILIAR",
    "PROFESSION": "PROFESION",
    "AGE": "EDAD",
    "SEX": "SEXO",
    "LOCATION": "LUGAR",
    "HOSPITAL": "HOSPITAL",
    "ORGANIZATION": "ORGANIZACION",
    "PHONE": "TELEFONO",
    "EMAIL": "CORREO",
    "URL": "URL",
    "ID": "ID",
    "OTHER": "ANONIMO",
    "PHI": "ANONIMO",
}


def _map_bert_label(label: str) -> str:
    base = label.split("-")[-1]
    if base == "ANON":
        return "PHI"
    return BRAT_TO_UNIFIED.get(base, "OTHER")


def _map_step2_label(label: str) -> str:
    return STEP2_TO_UNIFIED.get(label, "OTHER")


# ── Regex rules (step2) ─────────────────────────────────────────────────────
PATTERNS = {
    "date": re.compile(
        r"\b(?:0[1-9]|[12]\d|3[01]|[1-9])[./-](?:0[1-9]|1[0-2]|[1-9])[./-](?:\d{4}|\d{2})\b|"
        r"\b\d{1,2}\s+de\s+\w+\s+de\s+\d{4}\b|"
        r"\b\d{1,2}\s+de\s+(?:Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre|Octubre|Noviembre|Diciembre|Gener|Febrer|Març|Abril|Maig|Juny|Juliol|Setembre|Octubre|Novembre|Desembre)\b|"
        r"\b(?:0[1-9]|[12]\d|3[01])[./-](?:0[1-9]|1[0-2])\b|"
        r"\b(?:0[1-9]|1[0-2])[./-]\d{2,4}\b|"
        r"\b(?:Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre|Octubre|Noviembre|Diciembre|Gener|Febrer|Març|Abril|Maig|Juny|Juliol|Setembre|Octubre|Novembre|Desembre)[/-]\d{2,4}\b|"
        r"\b(?:Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre|Octubre|Noviembre|Diciembre|Gener|Febrer|Març|Abril|Maig|Juny|Juliol|Setembre|Octubre|Novembre|Desembre)\b|"
        r"\b(?:Lunes|Martes|Miércoles|Miercoles|Jueves|Viernes|Sábado|Sabado|Domingo|Dilluns|Dimarts|Dimecres|Dijous|Divendres|Dissabte|Diumenge)\b|"
        r"\b(19|20)\d{2}\b",
        re.IGNORECASE,
    ),
    "time": re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*h?\b", re.IGNORECASE),
    "phone": re.compile(r"\b(?:(?:\+|00)\d{1,3}[\s.-]?)?[3456789](?:[\s.-]?\d){8}\b"),
    "doctor": re.compile(
        r"\bdr[as]?\.?\s+(?!(?:OI|OD|HTA|EA|AP|ANM|AMC|dret|dreta|drenaje|dren|droga|drogueta|dramático|drástica)\b)[a-zÁÉÍÓÚÑ][a-zjqñáéíóúü]+(?:\s+[a-zÁÉÍÓÚÑ][a-zjqñáéíóúü]+)*(?=[.,;?\)\]\/\s-]*|$)",
        re.IGNORECASE,
    ),
    "age": re.compile(r"\b\d{1,3}\s?(?:años?|a)\b", re.IGNORECASE),
    "location": re.compile(
        r"\b(Barcelona|Hospitalet de Llobregat|L'Hospitalet|Badalona|Terrassa|Sabadell|Mataró|Santa Coloma de Gramenet|Cornellà de Llobregat|Sant Boi de Llobregat|Sant Cugat del Vallès|Manresa|Rubí|Vilanova i la Geltrú|Viladecans|Castelldefels|Prat de Llobregat|El Prat|Granollers|Cerdanyola del Vallès|Mollet del Vallès|Vic|Esplugues de Llobregat|Gavà|Sant Feliu de Llobregat|Igualada|Vilafranca del Penedès|Ripollet|Sant Adrià de Besòs|Montcada i Reixac|Sant Joan Despí|Barberà del Vallès|Sant Pere de Ribes|Sitges|Martorell|Premià de Mar|Pineda de Mar|Sant Vicenç dels Horts|Sant Andreu de la Barca|Molins de Rei|Santa Perpètua de Mogoda|Castellar del Vallès|Olesa de Montserrat|Masnou|Esparreguera|Manlleu|Vilassar de Mar|Calella|Malgrat de Mar|Sant Quirze del Vallès|Parets del Vallès|Berga|Les Franqueses del Vallès|Caldes de Montbui|Sant Celoni|Cardedeu|Canovelles|Sant Just Desvern|Montornès del Vallès|La Garriga|Girona|Figueres|Blanes|Lloret de Mar|Olot|Salt|Palafrugell|Sant Feliu de Guíxols|Banyoles|Roses|Palamós|Santa Coloma de Farners|Torroella de Montgrí|Castelló d'Empúries|La Bisbal d'Empordà|Lleida|Tàrrega|Balaguer|Mollerussa|La Seu d'Urgell|Cervera|Solsona|Tarragona|Reus|Tortosa|El Vendrell|Cambrils|Salou|Valls|Calafell|Amposta|Vilaseca|Sant Carles de la Ràpita|La Ràpita|Torredembarra|Móra d'Ebre|Sants|Les Corts|Sarrià|Horta|Nou Barris|Sant Andreu|Sant Martí|Gràcia|Eixample|Ciutat Vella|"
        r"Antigua y Barbuda|Argentina|Bahamas|Barbados|Belice|Bolivia|Brasil|Canadá|Chile|Colombia|Costa Rica|Cuba|Dominica|Ecuador|El Salvador|Estados Unidos|Granada|Guatemala|Guyana|Haití|Honduras|Jamaica|México|Nicaragua|Panamá|Paraguay|Perú|República Dominicana|San Cristóbal y Nieves|San Vicente y las Granadinas|Santa Lucía|Surinam|Trinidad y Tobago|Uruguay|Venezuela|Puerto Rico|Guayana Francesa|Groenlandia|Bermudas)\b",
        re.IGNORECASE,
    ),
    "family_relation": re.compile(
        r"\b(madre|padre|hijo|hija|esposo|esposa|marido|mujer|hermano|hermana|tío|tía|abuelo|abuela|nieto|nieta|sobrino|sobrina|primo|prima|cuñado|cuñada|suegro|suegra|yerno|nuera|pareja|cónyuge|viejo|vieja|papá|mamá|família|familia|mare|fill|filla|espòs|marit|dona|germà|germana|oncle|tia|avi|àvia|nét|néta|nebot|neboda|cosí|cosina|cunyat|cunyada|sogre|sogra|gendre|nora|parella|cònjuge|xicot|xicota|nòvio|nòvia)\b",
        re.IGNORECASE,
    ),
    "name_upper": re.compile(r"\b[A-ZÁÉÍÓÚÑ]{3,}(?:[\s,/,-]{1,2}[A-ZÁÉÍÓÚÑ]{2,})+\b"),
    "name_mixed": re.compile(r"\b[A-ZÁÉÍÓÚÑ][a-zjqñáéíúü]+(?:[\s,/,-]{1,2}[A-ZÁÉÍÓÚÑ][a-zjqñáéíúü]+)+\b"),
    "identifier": re.compile(r"\(?\d{6,11}\)?"),
    "hospital": re.compile(
        r"\b(?:H\.|Hospital|Clínica|CAP|Centre)\s+(?:(?:de|del|i|y|la|el|san|sant|santa)\s+)*[A-ZÁÉÍÓÚÑ][a-zjqñáéíóúü]+(?:[\s-](?:de|del|i|y|la|el|san|sant|santa|[A-ZÁÉÍÓÚÑ][a-zjqñáéíóúü]+))*\b",
        re.IGNORECASE,
    ),
    "address": re.compile(
        r"\b(?:Calle|Carrer|Avenida|Av\.?|Avda\.?|Paseo|Passeig|Plaza|Plaça|C\.?/?|Camino|Camí|Via|Vía|Ronda|Travesía|Travesia|Travessera|Passatge|Pasaje|Carretera|Ctra\.?)\s+"
        r"(?:(?:de|la|el|del|dels|i|y)\s+){0,2}"
        r"[A-ZÁÉÍÓÚÜ][a-záéíóúüñçàèìòù]{1,25}"
        r"(?:\s+(?:de|la|el|del|dels|i|y|san|sant|santa)\s+[A-ZÁÉÍÓÚÜ][a-záéíóúüñçàèìòù]{1,25}){0,3}"
        r"(?:,?\s*\d{1,4}(?:\s*[A-Za-z])?)?"
    ),
}

NAME_KEYWORDS = [
    "nombre", "paciente", "contacto", "persona", "responsable", "cuidador",
    "cuidadora", "tutor", "tutora", "familiar", "madre", "padre", "hijo",
    "hija", "esposa", "esposo", "marido", "mujer", "hermano", "hermana",
    "tío", "tía", "abuelo", "abuela", "nieto", "nieta", "sobrino", "sobrina",
    "primo", "prima", "cuñado", "cuñada", "suegro", "suegra", "yerno",
    "nuera", "pareja", "cónyuge", "novio", "novia", "nom", "contacte",
    "mare", "pare", "fill", "filla", "espòs", "marit", "dona", "germà",
    "germana", "oncle", "tia", "avi", "àvia", "nét", "néta", "nebot",
    "neboda", "cosí", "cosina", "cunyat", "cunyada", "sogre", "sogra",
    "gendre", "nora", "parella", "cònjuge", "xicot", "xicota", "nòvio",
    "nòvia", "facultatiu", "profesional", "responsables", "apellidos",
    "cognoms", "valoración", "valoració",
]

MEDICAL_ACRONYMS = {
    "urología", "cardiología", "digestivo", "respiratorio", "neurología",
    "traumatología", "urgencias", "medicina", "interna", "atención",
    "primaria", "mg/dl", "mmhg", "bpm", "lpm", "sat", "o2", "pcr", "vsg",
    "hba1c", "colesterol", "hdl", "ldl", "triglicéridos", "got", "gpt",
    "ggt", "fa", "bilirrubina", "creatinina", "urea", "sodio", "potasio",
    "cloro", "calcio", "fósforo", "magnesio", "hierro", "ferritina", "tsh",
    "t4", "t3", "vitamina", "clínic", "clínico", "hospital", "barcelona",
    "urgències", "urgencias", "informe", "hcp", "trastorno", "síndrome",
    "enfermedad", "diabetes", "mellitus", "insuficiencia", "renal",
    "cardíaca", "respiratoria", "aguda", "crónica", "severa", "leve",
    "moderada", "tratamiento", "dosis", "pauta", "comprimido", "pastilla",
    "jarabe", "solución", "inyección", "vía", "oral", "intravenosa",
    "intramuscular", "subcutánea", "paciente", "usuario", "historia",
    "clínica", "alta", "ingreso", "consulta", "visita", "diagnóstico",
    "evolución", "plan", "antecedentes", "personales", "familiares",
    "quirúrgicos", "patológicos", "psiquiátricos", "alergias", "hábitos",
    "tóxicos", "exploración", "física", "constantes", "vitales", "tensión",
    "arterial", "frecuencia", "temperatura", "saturación", "oxígeno",
    "peso", "talla", "índice", "masa", "corporal", "fármaco",
    "medicamento", "principio", "activo", "posología", "abilify", "adiro",
    "aspirina", "atorvastatina", "bisoprolol", "captopril", "depakine",
    "diazepam", "enalapril", "fluoxetina", "furosemida", "ibuprofeno",
    "insulina", "lorazepam", "metformina", "metamizol", "nolotil",
    "omeprazol", "paracetamol", "plavix", "prednisona", "quetiapina",
    "salbutamol", "sintrom", "simvastatina", "trankimazin", "ventolin",
    "zolpidem",
}

ROBUST_PUNC = r"[.,;?\)\]\/\s-]*"

EXCLUDED_HEADERS = {
    "ANTECEDENTES FAMILIARES", "ANTECEDENTES PERSONALES", "MOTIVO DE CONSULTA",
    "ENFERMEDAD ACTUAL", "EXPLORACIÓN FÍSICA", "PRUEBAS COMPLEMENTARIAS",
    "EVOLUCIÓN", "TRATAMIENTO", "DIAGNOSTICO", "DIAGNÓSTICO", "CURSO CLINICO",
    "CURSO CLÍNICO", "ALERGIAS", "HABITOS TOXICOS", "HÁBITOS TÓXICOS",
    "INTERCONSULTAS", "OBSERVACIONES", "PLAN", "RESUMEN", "HISTORIA ACTUAL",
}


def _load_whitelist() -> set:
    """Carga lista_blanca.txt del proyecto (si existe)."""
    path = ROOT / "lista_blanca.txt"
    terms = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                terms.add(line.lower())
    return terms


LISTA_BLANCA = _load_whitelist()


class Anonymizer:
    """BERT (carmen) + regex detector with reversible placeholder anonymization."""

    STRIDE = 128
    BATCH_SIZE = 32

    def __init__(self, model_dir=None, device=None, threshold=0.1):
        try:
            import torch
        except ImportError as exc:
            raise ImportError("Falta PyTorch. Instala: pip install torch") from exc
        try:
            from transformers import AutoModelForTokenClassification, AutoTokenizer
        except ImportError:
            try:
                from transformers.models.auto import AutoModelForTokenClassification
                from transformers import AutoTokenizer
            except ImportError as exc:
                raise ImportError(
                    "No se pudo importar AutoModelForTokenClassification. "
                    "Reinstala transformers: pip install -U transformers"
                ) from exc

        self.model_dir = Path(model_dir) if model_dir else DEFAULT_MODEL_DIR
        self.device = device or ("cuda:0" if torch.cuda.is_available() else "cpu")
        self.threshold = threshold

        model_path = self.model_dir / model_dirname()
        if not model_path.exists():
            raise FileNotFoundError(f"Modelo no encontrado: {model_path}")
        self.tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True)
        self.model = AutoModelForTokenClassification.from_pretrained(str(model_path), local_files_only=True)
        self.model.to(self.device).eval()

        # Placeholder map and counters (per request)
        self.reset()

    def reset(self):
        self.text_to_ph = {}   # real text -> placeholder (consistency)
        self.ph_to_text = {}   # placeholder -> real text (reversal)
        self.counters = {}     # tag -> counter

    # ── Detección BERT ────────────────────────────────────────────────────
    def _bert_detect(self, text: str) -> list[dict]:
        import numpy as np
        import torch

        enc = self.tokenizer(
            text,
            return_overflowing_tokens=True,
            stride=self.STRIDE,
            padding=True,
            truncation=True,
            max_length=self.tokenizer.model_max_length,
            return_offsets_mapping=True,
            return_special_tokens_mask=True,
            return_tensors="pt",
        )
        input_ids = enc["input_ids"].to(self.device)
        attention_mask = enc["attention_mask"].to(self.device)
        offset_mapping = enc["offset_mapping"]
        special_tokens_mask = enc["special_tokens_mask"]

        logits_parts = []
        with torch.no_grad():
            for i in range(0, input_ids.shape[0], self.BATCH_SIZE):
                out = self.model(
                    input_ids=input_ids[i:i + self.BATCH_SIZE],
                    attention_mask=attention_mask[i:i + self.BATCH_SIZE],
                )
                logits_parts.append(out.logits.cpu())
        logits = torch.cat(logits_parts, dim=0)
        probs = logits.softmax(dim=-1)
        scores, pred_ids = probs.max(dim=-1)

        id2label = self.model.config.id2label or {}
        label2id = self.model.config.label2id or {}
        o_id = label2id.get("O", 0)

        om = np.asarray(offset_mapping, dtype=np.int64)
        am = attention_mask.cpu().numpy().astype(bool)
        if torch.is_tensor(special_tokens_mask):
            spm = special_tokens_mask.cpu().numpy().astype(bool)
        else:
            spm = np.asarray(special_tokens_mask).astype(bool)
        pred = pred_ids.numpy()
        conf = scores.numpy()

        valid = am & ~spm & (om[:, :, 1] > om[:, :, 0]) & (pred != o_id)
        entries = []
        rows, cols = np.nonzero(valid)
        for w, t in zip(rows.tolist(), cols.tolist()):
            pid = int(pred[w, t])
            raw = id2label.get(pid)
            if raw is None:
                raw = id2label.get(str(pid), "O")
            base = raw[2:] if raw.startswith(("B-", "I-")) else raw
            entries.append((int(om[w, t, 0]), int(om[w, t, 1]), base, float(conf[w, t])))

        # Dedup by span (overlap between windows): keep best score
        best = {}
        for s, e, lab, sc in entries:
            key = (s, e)
            if key not in best or sc > best[key][3]:
                best[key] = (s, e, lab, sc)
        entries = sorted(best.values())

        # Merge contiguous tokens with the same label
        merged = []
        for s, e, lab, sc in entries:
            if merged and lab == merged[-1]["label"] and s <= merged[-1]["end"] + 1:
                merged[-1]["end"] = max(merged[-1]["end"], e)
                merged[-1]["score"] = max(merged[-1]["score"], sc)
            else:
                merged.append({"start": s, "end": e, "label": lab, "score": sc})

        entities = []
        for m in merged:
            if m["score"] < self.threshold or m["end"] <= m["start"]:
                continue
            ent_text = text[m["start"]:m["end"]]
            if ent_text.lower().strip() in LISTA_BLANCA:
                continue
            entities.append({
                "start": m["start"], "end": m["end"],
                "label": _map_bert_label(m["label"]), "text": ent_text,
            })
        return entities

    # ── Detección regex ────────────────────────────────────────────────────
    def _regex_detect(self, text: str) -> list[dict]:
        matches = []
        blocked = MEDICAL_ACRONYMS | LISTA_BLANCA

        for match in PATTERNS["date"].finditer(text):
            matches.append((match.start(), match.end(), "DATE", match.group()))
        for match in PATTERNS["time"].finditer(text):
            matches.append((match.start(), match.end(), "TIME", match.group()))
        for label in ["phone", "doctor", "hospital", "age", "location", "address", "family_relation", "identifier"]:
            for match in PATTERNS[label].finditer(text):
                if label == "family_relation":
                    out_label = "RELATION"
                elif label == "address":
                    out_label = "LOCATION"
                else:
                    out_label = label.upper()
                matches.append((match.start(), match.end(), out_label, match.group()))

        def already_marked(start, end):
            return any(s <= start and end <= e for s, e, _, _ in matches)

        # Names preceded by a keyword
        context_pattern = re.compile(
            r"\b(" + "|".join(NAME_KEYWORDS) + r")(?=" + ROBUST_PUNC + r"|$)",
            re.IGNORECASE,
        )
        lines = text.split("\n")
        current_pos = 0
        for line in lines:
            if context_pattern.search(line):
                for pattern_name in ["name_upper", "name_mixed"]:
                    for match in PATTERNS[pattern_name].finditer(line):
                        name = match.group()
                        if name.lower() not in blocked and (pattern_name != "name_mixed" or name.lower() not in NAME_KEYWORDS):
                            start = current_pos + match.start()
                            end = current_pos + match.end()
                            if not already_marked(start, end):
                                matches.append((start, end, "PERSON", name))
            current_pos += len(line) + 1

        # UPPERCASE with comma (surnames, name)
        for match in PATTERNS["name_upper"].finditer(text):
            name = match.group()
            clean_name = re.sub(r"[.,;:]+$", "", name).strip()
            if "," in name and name.lower() not in blocked and clean_name not in EXCLUDED_HEADERS:
                if not already_marked(match.start(), match.end()):
                    matches.append((match.start(), match.end(), "GENERICA", name))

        # Discovery pass: re-search texts already found
        discovered = set()
        for _, _, _, t in matches:
            clean = t.strip("()[].,;?/- ")
            if len(clean) > 3:
                discovered.add(clean)
        for t in discovered:
            pattern = re.compile(r"\b" + re.escape(t) + r"(?=" + ROBUST_PUNC + r"|$)", re.IGNORECASE)
            for match in pattern.finditer(text):
                label = "PERSON"
                for s, e, l, mt in matches:
                    if t.lower() in mt.lower():
                        label = l
                        break
                if not already_marked(match.start(), match.end()):
                    matches.append((match.start(), match.end(), label, match.group()))

        matches.sort(key=lambda x: x[0])
        entities = []
        for s, e, label, t in matches:
            entities.append({
                "start": s, "end": e,
                "label": _map_step2_label(label), "text": t,
            })
        return entities

    # ── Detección combinada ────────────────────────────────────────────────
    @staticmethod
    def _overlap(a, b):
        return a["start"] < b["end"] and b["start"] < a["end"]

    def detect(self, text: str) -> list[dict]:
        """BERT (base) + regex (complement that does not overlap BERT)."""
        if not text or not text.strip():
            return []
        merged = list(self._bert_detect(text))
        for e in self._regex_detect(text):
            if not any(self._overlap(e, m) for m in merged):
                merged.append(e)
        merged.sort(key=lambda x: x["start"])
        return merged

    # ── Anonimización reversible ───────────────────────────────────────────
    def anonymize(self, text: str) -> str:
        for e in sorted(self.detect(text), key=lambda x: x["start"], reverse=True):
            orig = e["text"]
            ph = self.text_to_ph.get(orig)
            if ph is None:
                tag = TAGS.get(e["label"], "ANONIMO")
                n = self.counters.get(tag, 0) + 1
                self.counters[tag] = n
                ph = f"[{tag}_{n}]"
                self.text_to_ph[orig] = ph
                self.ph_to_text[ph] = orig
            text = text[:e["start"]] + ph + text[e["end"]:]
        return text

    def deanonymize(self, text: str) -> str:
        # Longest placeholder first, to avoid breaking [NOMBRE_10] with [NOMBRE_1]
        for ph, orig in sorted(self.ph_to_text.items(), key=lambda kv: len(kv[0]), reverse=True):
            text = text.replace(ph, orig)
        return text


# Lazy singleton: loaded once; optional (None if unavailable).
_ANONYMIZER = None
_ANONYMIZER_FAILED = False


def get_anonymizer():
    global _ANONYMIZER, _ANONYMIZER_FAILED
    if _ANONYMIZER is None and not _ANONYMIZER_FAILED:
        try:
            _ANONYMIZER = Anonymizer()
        except Exception as exc:  # noqa: BLE001
            _ANONYMIZER_FAILED = True
            print(f"[anonymizer] unavailable, sending without anonymization: {exc}")
    return _ANONYMIZER


if __name__ == "__main__":
    sample = (
        "Paciente: María García López, 45 años, vive en Barcelona. "
        "Teléfono 600123456. Ingresó el 12/05/2024 en el Hospital Clínic."
    )
    anon = Anonymizer()
    out = anon.anonymize(sample)
    print("Anonimizado:", out)
    print("Restaurado:", anon.deanonymize(out))
