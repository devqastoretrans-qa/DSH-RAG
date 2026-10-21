import os
import re
import uuid
from typing import List, Dict, Optional


def split_into_sentences(text: str) -> List[str]:
    """
    Splits text into sentences while respecting common punctuation boundaries.
    """
    if not text:
        return []
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def chunk_text(
    text: str,
    chunk_size: int = 150,
    chunk_overlap: int = 25
) -> List[str]:
    """
    Splits a raw text string into semantically coherent, sentence-bounded chunks.
    Preserves sentence integrity whenever possible rather than cutting words mid-sentence.
    
    Args:
        text: Input string.
        chunk_size: Target number of words per chunk.
        chunk_overlap: Number of overlapping words between consecutive chunks.
        
    Returns:
        List of text chunk strings.
    """
    text = text.strip()
    if not text:
        return []

    # First attempt paragraph / double-newline split
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks = []
    current_sentences = []
    current_word_count = 0

    for para in paragraphs:
        sentences = split_into_sentences(para)
        if not sentences:
            sentences = [para]

        for sentence in sentences:
            sentence_words = sentence.split()
            sentence_word_count = len(sentence_words)

            # If a single sentence exceeds chunk_size, split by words
            if sentence_word_count > chunk_size:
                if current_sentences:
                    chunks.append(" ".join(current_sentences))
                    current_sentences = []
                    current_word_count = 0

                start = 0
                step = max(1, chunk_size - chunk_overlap)
                while start < sentence_word_count:
                    end = start + chunk_size
                    chunks.append(" ".join(sentence_words[start:end]))
                    if end >= sentence_word_count:
                        break
                    start += step
                continue

            # Check if sentence fits in the current accumulator
            if current_word_count + sentence_word_count <= chunk_size:
                current_sentences.append(sentence)
                current_word_count += sentence_word_count
            else:
                if current_sentences:
                    chunks.append(" ".join(current_sentences))
                    # Retain overlap sentences from the end
                    overlap_sentences = []
                    overlap_count = 0
                    for s in reversed(current_sentences):
                        s_count = len(s.split())
                        if overlap_count + s_count <= chunk_overlap or not overlap_sentences:
                            overlap_sentences.insert(0, s)
                            overlap_count += s_count
                        else:
                            break
                    current_sentences = overlap_sentences + [sentence]
                    current_word_count = sum(len(s.split()) for s in current_sentences)
                else:
                    current_sentences = [sentence]
                    current_word_count = sentence_word_count

    if current_sentences:
        chunks.append(" ".join(current_sentences))

    return chunks


def clean_document_title(filename: str) -> str:
    """
    Sanitizes raw filenames into clean, natural document titles.
    E.g. 'Gamification_FAQ_V1.docx.pdf' -> 'Gamification FAQ'
         'Todays Thoughts Journal FAQ V1.docx (2).pdf' -> 'Todays Thoughts Journal FAQ'
         'Personal & Attachment Needs FAQ V1.docx (1).pdf' -> 'Personal & Attachment Needs FAQ'
    """
    if not filename:
        return "Document"
    name = filename
    # Strip duplicate download markers like ' (1)', ' (2)', etc.
    name = re.sub(r'\s*\(\d+\)', '', name)
    # Strip common file extensions (even if chained like .docx.pdf)
    name = re.sub(r'\.(pdf|docx|doc|txt)', '', name, flags=re.IGNORECASE)
    # Remove version tags like _V1,  V1, _v2, etc.
    name = re.sub(r'[_ ]+[vV]\d+', '', name)
    name = re.sub(r'_\d{3,}$', '', name)
    # Replace underscores and multiple spaces with a single space
    name = re.sub(r'[_\-]+', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name or filename


def chunk_document_pages(
    pages: List[Dict],
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    document_id: Optional[str] = None,
    embedding_model: Optional[str] = None,
    category: Optional[str] = None
) -> List[Dict]:
    """
    Takes extracted page dictionaries and produces metadata-enriched chunk payloads
    with contextual headers ([Document: title | Page N]) for improved vector retrieval.
    
    Args:
        pages: List of dicts containing page_number, text, filename.
        chunk_size: Optional override for word count per chunk.
        chunk_overlap: Optional override for overlap word count.
        document_id: Optional unique identifier for the document batch.
        embedding_model: Optional name of the active embedding model.
        category: Optional category tag ('clinical' or 'sales').
        
    Returns:
        List of chunk dicts ready for payload insertion into Qdrant.
    """
    if chunk_size is None:
        chunk_size = int(os.getenv("CHUNK_SIZE", 150))
    if chunk_overlap is None:
        chunk_overlap = int(os.getenv("CHUNK_OVERLAP", 25))
    if not document_id:
        document_id = str(uuid.uuid4())
    if not embedding_model:
        embedding_model = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")

    chunk_records = []
    global_chunk_index = 1

    for page in pages:
        page_text = page.get("text", "")
        filename = page.get("filename", "document.pdf")
        page_number = page.get("page_number", 1)
        clean_title = clean_document_title(filename)

        text_chunks = chunk_text(page_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        for page_chunk_idx, text_chunk in enumerate(text_chunks, start=1):
            # Contextual grounding header: Bakes document title into the vector embedding
            context_header = f"[Document: {clean_title} | Page {page_number}]\n"
            enriched_text = f"{context_header}{text_chunk}"
            formatted_chunk_id = f"{document_id}_page_{page_number}_chunk_{page_chunk_idx:02d}"

            # Parent Context Window: Expand surrounding context (small-to-big retrieval)
            prev_chunk = text_chunks[page_chunk_idx - 2] if page_chunk_idx > 1 else ""
            next_chunk = text_chunks[page_chunk_idx] if page_chunk_idx < len(text_chunks) else ""
            
            expanded_parts = []
            if prev_chunk:
                expanded_parts.append(prev_chunk)
            expanded_parts.append(text_chunk)
            if next_chunk:
                expanded_parts.append(next_chunk)
            parent_context = f"[Document: {clean_title} | Page {page_number}]\n" + " ".join(expanded_parts)

            # Resolve category (clinical vs sales)
            chunk_category = category
            if not chunk_category:
                f_low = filename.lower()
                if any(k in f_low for k in ("sales", "catalog", "pricing", "checkout", "masterclass")):
                    chunk_category = "sales"
                else:
                    chunk_category = "clinical"

            chunk_records.append({
                "document_id": document_id,
                "document_title": clean_title,
                "document_name": clean_title,
                "filename": filename,  # preserved for backward compatibility
                "page": page_number,
                "page_number": page_number,  # preserved for backward compatibility
                "chunk_id": formatted_chunk_id,
                "chunk_index": global_chunk_index,
                "text": enriched_text,
                "raw_text": text_chunk,
                "parent_context": parent_context,
                "source": filename,
                "category": chunk_category,
                "embedding_model": embedding_model
            })
            global_chunk_index += 1

    return chunk_records



