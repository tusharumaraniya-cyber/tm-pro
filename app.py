import streamlit as st
import pandas as pd
import re, io, zipfile, uuid, os, tempfile, shutil
from rapidfuzz import process, fuzz
from PIL import Image
from pathlib import Path

# ================= CONFIG =================
DEFAULT_MATCH = 80
DEFAULT_CHECK = 65
IMAGES_PER_ROW = 3
FIXED_FOLDER_NAME = "TM PRO"
RESIZE_W, RESIZE_H = 1200, 800

st.set_page_config(page_title="TM PRO Image Tool", layout="wide")

# ================= WORK DIRECTORY =================
WORK_DIR = Path(tempfile.gettempdir()) / "tm_pro_work"
WORK_DIR.mkdir(exist_ok=True)

# ================= SIDEBAR =================
with st.sidebar:
    st.header("⚙️ Matching Settings")
    MATCH_MIN = st.slider("Perfect Match Score (%)", 0, 100, DEFAULT_MATCH)
    CHECK_MIN = st.slider("Review Match Score (%)", 0, 100, DEFAULT_CHECK)

# ================= HELPERS =================
def clean_text(t):
    t = str(t).lower()
    t = re.sub(r"\.(jpg|jpeg|png|webp|jfif)", "", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()

def base_name(name):
    name = clean_text(name)
    name = re.sub(r"_\d+$", "", name)
    return name

def resize_image_to_disk(file):
    img = Image.open(file).convert("RGB")
    img.thumbnail((RESIZE_W, RESIZE_H))

    unique_name = str(uuid.uuid4()) + ".jpg"
    save_path = WORK_DIR / unique_name
    img.save(save_path, format="JPEG", quality=85, optimize=True)

    return str(save_path)

def food_type(name):
    name = name.lower()
    if any(k in name for k in ["egg", "anda"]):
        return "EGG"
    if any(k in name for k in ["chicken", "mutton", "fish", "prawn", "meat", "keema"]):
        return "NONVEG"
    return "VEG"

def two_word_strict_score(a, b):
    wa = a.split()
    wb = b.split()
    if len(wa) == 2 and len(wb) == 2 and wa[0] == wb[0]:
        return fuzz.ratio(wa[1], wb[1])
    return None

# ================= UI =================
st.markdown(f"## 🟢 {FIXED_FOLDER_NAME} Matching Tool")

c1, c2 = st.columns(2)
with c1:
    uploaded_excel = st.file_uploader("📄 Upload Excel / CSV", ["xlsx", "xls", "csv"])
with c2:
    uploaded_images = st.file_uploader(
        "🖼️ Upload Images",
        ["jpg", "jpeg", "png", "webp", "jfif"],
        accept_multiple_files=True
    )

# Limit protection
if uploaded_images and len(uploaded_images) > 300:
    st.error("⚠️ Maximum 300 images allowed at once.")
    st.stop()

SHOW_PREVIEW = True
if uploaded_images and len(uploaded_images) > 80:
    SHOW_PREVIEW = False

# Reset session on new upload
if uploaded_images:
    current_signature = str(len(uploaded_images))
    if "last_upload_signature" not in st.session_state:
        st.session_state.last_upload_signature = ""

    if current_signature != st.session_state.last_upload_signature:
        st.session_state.processed = False
        st.session_state.results = {"MATCH": [], "CHECK": [], "DUPLICATE": []}
        st.session_state.used_base = set()
        st.session_state.last_upload_signature = current_signature

if uploaded_excel and uploaded_images:

    df = pd.read_csv(uploaded_excel) if uploaded_excel.name.endswith(".csv") else pd.read_excel(uploaded_excel)

    sheet_items = (
        df[df.iloc[:, 3].isna()]
        .iloc[:, 2]
        .dropna()
        .astype(str)
        .str.strip()
        .tolist()
    )

    clean_map = {i: clean_text(i) for i in sheet_items}

    if "processed" not in st.session_state:
        st.session_state.processed = False
        st.session_state.results = {"MATCH": [], "CHECK": [], "DUPLICATE": []}
        st.session_state.used_base = set()

    if not st.session_state.processed:
        progress = st.progress(0)
        total = len(uploaded_images)

        for idx, img in enumerate(uploaded_images):

            bname = base_name(clean_text(img.name))
            if bname in st.session_state.used_base:
                st.session_state.results["DUPLICATE"].append({"original": img.name})
                continue

            st.session_state.used_base.add(bname)

            resized_path = resize_image_to_disk(img)

            best = process.extractOne(
                clean_text(img.name),
                clean_map.values(),
                scorer=fuzz.token_sort_ratio
            )

            real_item, score = sheet_items[0], 0
            if best:
                match_txt, score, _ = best
                real_item = next(k for k, v in clean_map.items() if v == match_txt)

            strict_score = two_word_strict_score(
                clean_text(img.name),
                clean_text(real_item)
            )
            if strict_score is not None:
                score = strict_score

            used_items = {r["final"] for r in st.session_state.results["MATCH"]}

            if food_type(img.name) != food_type(real_item):
                target = "CHECK"
                score = 0
            elif real_item in used_items:
                target = "DUPLICATE"
            else:
                target = "MATCH" if score >= MATCH_MIN else "CHECK"

            st.session_state.results[target].append({
                "id": str(uuid.uuid4()),
                "image_path": resized_path,
                "original": img.name,
                "final": real_item,
                "score": round(score, 2)
            })

            progress.progress((idx + 1) / total)

        st.session_state.processed = True

    m, c, d = st.columns(3)
    m.metric("✅ MATCH", len(st.session_state.results["MATCH"]))
    c.metric("⚠️ CHECK", len(st.session_state.results["CHECK"]))
    d.metric("♻️ DUPLICATE", len(st.session_state.results["DUPLICATE"]))

    # Download ZIP
    if st.session_state.results["MATCH"]:
        zip_path = WORK_DIR / f"{FIXED_FOLDER_NAME}.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for r in st.session_state.results["MATCH"]:
                zipf.write(
                    r["image_path"],
                    f"{FIXED_FOLDER_NAME}/{r['final']}.jpg"
                )

        with open(zip_path, "rb") as f:
            st.download_button(
                "📥 Download TM PRO Folder (ZIP)",
                f,
                file_name=f"{FIXED_FOLDER_NAME}.zip",
                mime="application/zip"
            )
