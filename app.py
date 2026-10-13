
import streamlit as st
import re
from natasha import (
    Segmenter, MorphVocab, NewsEmbedding,
    NewsNERTagger, Doc
)
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from docx import Document
from PyPDF2 import PdfReader
import io

# ========== НАСТРОЙКИ ==========
st.set_page_config(
    page_title="Комплаенс-анализ документов",
    page_icon="🔍",
    layout="wide"
)

# ========== ИНИЦИАЛИЗАЦИЯ NATASHA ==========
@st.cache_resource
def init_natasha():
    segmenter = Segmenter()
    emb = NewsEmbedding()
    ner_tagger = NewsNERTagger(emb)
    return segmenter, ner_tagger

segmenter, ner_tagger = init_natasha()

# ========== FIREWALL ==========
PATTERNS = {
    'ИНН': r'\b\d{10,12}\b',
    'ПАСПОРТ': r'\b\d{2}\s?\d{2}\s?\d{6}\b',
    'ТЕЛЕФОН': r'\+?7[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
    'EMAIL': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    'СНИЛС': r'\b\d{3}[\s\-]?\d{3}[\s\-]?\d{3}[\s\-]?\d{2}\b',
    'ОГРН': r'\b\d{13}\b',
    'КПП': r'\b\d{9}\b',
}

def mask_pii(text):
    masked = text
    replacements = {}
    counter = 1
    
    for name, pattern in PATTERNS.items():
        def replacer(match):
            nonlocal counter
            key = f'[{name}_{counter}]'
            replacements[key] = match.group(0)
            counter += 1
            return key
        masked = re.sub(pattern, replacer, masked)
    
    doc = Doc(masked)
    doc.segment(segmenter)
    doc.tag_ner(ner_tagger)
    
    for span in doc.spans:
        if span.type == 'PER':
            key = f'[ФИО_{counter}]'
            replacements[key] = span.text
            counter += 1
            masked = masked[:span.start] + key + masked[span.stop:]
    
    return masked, replacements

def unmask_pii(masked_text, replacements):
    result = masked_text
    for key, value in replacements.items():
        result = result.replace(key, value)
    return result

# ========== ИЗВЛЕЧЕНИЕ ТЕКСТА ==========
def extract_text(uploaded_file):
    if uploaded_file.name.endswith('.docx'):
        doc = Document(uploaded_file)
        return '\n'.join([p.text for p in doc.paragraphs])
    elif uploaded_file.name.endswith('.pdf'):
        reader = PdfReader(uploaded_file)
        return '\n'.join([p.extract_text() for p in reader.pages])
    else:
        return uploaded_file.read().decode('utf-8')

# ========== GIGACHAT ==========
@st.cache_resource
def init_gigachat(key):
    return GigaChat(
        credentials=key,
        scope="GIGACHAT_API_PERS",
        model="GigaChat-3-Ultra",
        verify_ssl_certs=False
    )

# ========== ИНТЕРФЕЙС ==========
st.title("🔍 Комплаенс-анализ документов")
st.markdown("Проверка документов на соответствие 152-ФЗ")

# Сайдбар
with st.sidebar:
    st.header("⚙️ Настройки")
    api_key = st.text_input("GigaChat API Key", type="password")
    st.markdown("---")
    st.markdown("**Как использовать:**")
    st.markdown("1. Вставь API-ключ")
    st.markdown("2. Загрузи документ")
    st.markdown("3. Получи отчёт")

# Загрузка
uploaded_file = st.file_uploader(
    "📎 Загрузите документ",
    type=['docx', 'pdf', 'txt']
)

if uploaded_file and api_key:
    # Извлечение текста
    with st.spinner("📄 Извлечение текста..."):
        text = extract_text(uploaded_file)
    
    st.success(f"✅ Загружено {len(text)} символов")
    
    # Firewall
    with st.spinner("🔒 Маскировка ПДн..."):
        masked_text, replacements = mask_pii(text)
    
    st.info(f"✅ Замаскировано {len(replacements)} объектов ПДн")
    
    with st.expander("🔍 Показать замаскированный текст"):
        st.text(masked_text)
    
    # GigaChat
    with st.spinner("🤖 Анализ GigaChat-3-Ultra..."):
        giga = init_gigachat(api_key)
        
        prompt = f"""Ты — эксперт по 152-ФЗ "О персональных данных".
Проанализируй документ на соответствие требованиям закона.
Выдай структурированный отчёт:

🔴 КРИТИЧЕСКИЕ РИСКИ:
- [описание] — [статья закона]

🟡 ТРЕБУЮЩИЕ ВНИМАНИЯ:
- [описание] — [статья закона]

🟢 МИНОРНЫЕ:
- [описание]

РЕКОМЕНДАЦИИ:
- [что делать]

Документ:
{masked_text}
"""
        
        chat = Chat(
            model="GigaChat-3-Ultra",
            messages=[Messages(role=MessagesRole.USER, content=prompt)]
        )
        
        response = giga.chat(chat)
        answer = response.choices[0].message.content
    
    # Отчёт
    st.markdown("## 📋 Отчёт")
    st.markdown(answer)
    
    # Восстановление
    with st.expander("🔓 Показать отчёт с восстановленными ПДн"):
        restored = unmask_pii(answer, replacements)
        st.markdown(restored)
    
    # Скачать
    st.download_button(
        "📥 Скачать отчёт",
        data=answer,
        file_name="compliance_report.md",
        mime="text/markdown"
    )

elif uploaded_file and not api_key:
    st.warning("⚠️ Введите API-ключ в сайдбаре")

else:
    st.info("👆 Загрузите документ для анализа")
