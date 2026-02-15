import streamlit as st
import pandas as pd
import re, io, zipfile, uuid
from rapidfuzz import process, fuzz
from PIL import Image

# ===== STREAMLIT CLOUD FIX =====
import os
os.environ['STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION'] = 'false'
os.environ['STREAMLIT_SERVER_ENABLE_CORS'] = 'false'

# ================= CONFIG =================
DEFAULT_MATCH = 80
DEFAULT_CHECK = 65
IMAGES_PER_ROW = 3
FIXED_FOLDER_NAME = "TM PRO"
RESIZE_W, RESIZE_H = 1200, 800
BATCH_SIZE = 30  # Ek baar me 30 images process hongi

st.set_page_config(page_title="TM PRO Image Tool", layout="wide")

# ================= SIDEBAR =================
with st.sidebar:
    st.header("⚙️ Matching Settings")
    MATCH_MIN = st.slider("Perfect Match Score (%)", 0, 100, DEFAULT_MATCH)
    CHECK_MIN = st.slider("Review Match Score (%)", 0, 100, DEFAULT_CHECK)
    
    st.markdown("---")
    st.info(f"📌 **Batch Processing Active**\nEk baar me {BATCH_SIZE} images process hongi\nTotal images: {len(st.session_state.get('all_images', [])) if 'all_images' in st.session_state else 0}")

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

def resize_image(file):
    img = Image.open(file).convert("RGB")
    img = img.resize((RESIZE_W, RESIZE_H))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    buf.seek(0)
    return buf

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
st.markdown(f"##### Batch Processing Mode - 300+ Images Supported")

c1, c2 = st.columns(2)
with c1:
    uploaded_excel = st.file_uploader("📄 Upload Excel / CSV", ["xlsx", "xls", "csv"])
with c2:
    uploaded_images = st.file_uploader(
        "🖼️ Upload Images (300+ supported)",
        ["jpg", "jpeg", "png", "webp", "jfif"],
        accept_multiple_files=True
    )

# Store images in session state
if uploaded_images and len(uploaded_images) > 0:
    st.session_state.all_images = uploaded_images
    st.session_state.current_batch = 0
    st.success(f"✅ {len(uploaded_images)} images ready for processing")

# Process in batches
if uploaded_excel and 'all_images' in st.session_state:
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
    
    # Initialize session state
    if "final_results" not in st.session_state:
        st.session_state.final_results = {"MATCH": [], "CHECK": [], "DUPLICATE": []}
        st.session_state.used_base = set()
        st.session_state.processed_batches = 0
    
    # Calculate total batches
    total_batches = (len(st.session_state.all_images) + BATCH_SIZE - 1) // BATCH_SIZE
    
    # Show batch info
    st.info(f"📊 Total batches: {total_batches} | Processed: {st.session_state.processed_batches}")
    
    # Process next batch button
    if st.session_state.processed_batches < total_batches:
        if st.button(f"🚀 Process Batch {st.session_state.processed_batches + 1}/{total_batches}"):
            start_idx = st.session_state.processed_batches * BATCH_SIZE
            end_idx = min(start_idx + BATCH_SIZE, len(st.session_state.all_images))
            current_batch = st.session_state.all_images[start_idx:end_idx]
            
            with st.spinner(f"🔄 Processing batch {st.session_state.processed_batches + 1}/{total_batches}..."):
                for img in current_batch:
                    bname = base_name(clean_text(img.name))
                    if bname in st.session_state.used_base:
                        st.session_state.final_results["DUPLICATE"].append({"original": img.name})
                        continue

                    st.session_state.used_base.add(bname)
                    resized = resize_image(img)

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

                    used_items = {r["final"] for r in st.session_state.final_results["MATCH"]}

                    if food_type(img.name) != food_type(real_item):
                        target = "CHECK"
                        score = 0
                    elif real_item in used_items:
                        target = "DUPLICATE"
                    else:
                        target = "MATCH" if score >= MATCH_MIN else "CHECK"

                    st.session_state.final_results[target].append({
                        "id": str(uuid.uuid4()),
                        "image": resized,
                        "original": img.name,
                        "final": real_item,
                        "score": round(score, 2)
                    })
            
            st.session_state.processed_batches += 1
            st.rerun()
    
    # Show results after all batches processed
    if st.session_state.processed_batches == total_batches and total_batches > 0:
        st.success("✅ All batches processed successfully!")
        
        results = st.session_state.final_results
        
        m, c, d = st.columns(3)
        m.metric("✅ MATCH", len(results["MATCH"]))
        c.metric("⚠️ CHECK", len(results["CHECK"]))
        d.metric("♻️ DUPLICATE", len(results["DUPLICATE"]))

        def render_section(title, key, allow_confirm):
            data = results[key]
            if not data:
                return

            st.markdown(f"### {title} ({len(data)})")

            bulk_list = []
            if key == "CHECK":
                bc1, bc2 = st.columns(2)
                with bc1:
                    sel_confirm = st.checkbox("✅ Select All for Confirm", key=f"bulk_conf_cb_{key}")
                with bc2:
                    sel_remove = st.checkbox("❌ Select All for Remove", key=f"bulk_rem_cb_{key}")

            for i in range(0, len(data), IMAGES_PER_ROW):
                cols = st.columns(IMAGES_PER_ROW)
                for j in range(IMAGES_PER_ROW):
                    if i + j >= len(data): break
                    item = data[i + j]
                    uid = item["id"]

                    with cols[j]:
                        st.image(item["image"], use_container_width=True)
                        st.caption(f"Original: {item['original']}")

                        item["final"] = st.selectbox(
                            "Select Item", sheet_items,
                            index=sheet_items.index(item["final"]) if item["final"] in sheet_items else 0,
                            key=f"{key}_sel_{uid}"
                        )
                        st.progress(item["score"] / 100)

                        if st.button("✅ Confirm", key=f"{key}_conf_{uid}"):
                            results["MATCH"].append(item)
                            results[key].remove(item)
                            st.rerun()
                        
                        if st.button("❌ Remove", key=f"{key}_rm_{uid}"):
                            results[key].remove(item)
                            st.rerun()

                        if key == "CHECK":
                            if sel_confirm or sel_remove:
                                bulk_list.append(item)

            if key == "CHECK" and bulk_list:
                st.divider()
                if sel_confirm:
                    if st.button(f"🚀 Confirm All Selected ({len(bulk_list)})"):
                        for r in bulk_list:
                            if r in results["CHECK"]:
                                results["MATCH"].append(r)
                                results["CHECK"].remove(r)
                        st.rerun()
                
                if sel_remove:
                    if st.button(f"🗑️ Remove All Selected ({len(bulk_list)})"):
                        for r in bulk_list:
                            if r in results["CHECK"]:
                                results["CHECK"].remove(r)
                        st.rerun()

        render_section("✅ MATCH", "MATCH", False)
        render_section("⚠️ CHECK", "CHECK", True)

        if results["MATCH"]:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                for r in results["MATCH"]:
                    zipf.writestr(f"{FIXED_FOLDER_NAME}/{r['final']}.jpg", r["image"].getvalue())

            st.download_button(
                "📥 Download TM PRO Folder (ZIP)",
                zip_buffer.getvalue(),
                file_name=f"{FIXED_FOLDER_NAME}.zip",
                mime="application/zip"
            )
        
        # Reset button
        if st.button("🔄 Start New Batch"):
            for key in ['all_images', 'final_results', 'used_base', 'processed_batches']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
