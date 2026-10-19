import time
import re
import logging
from typing import Dict, Any, List, Optional
from src.search import search_similar_chunks, expand_query_semantics
from src.generator import get_generator_service
from src.user_db import get_user_db
from src.embeddings import get_embedding_service
from src.semantic_cache import get_semantic_cache

logger = logging.getLogger("rag_service")


class UserNotFoundError(Exception):
    """Raised when the specified user_id is not found in the database."""
    pass


class RAGGenerationError(Exception):
    """Raised when LLM or RAG pipeline fails unexpectedly."""
    pass


# Tier 0: Acute Crisis & Immediate Safety Guardrail Regex
CRISIS_REGEX = re.compile(
    r"\b("
    r"suicid(e|al)|kill\s+(my\s*self|me)|end\s+my\s+life|want\s+to\s+die|"
    r"self[- ]?harm|cutting\s+myself|hurt(ing)?\s+myself|"
    r"he\s+hits\s+me|she\s+hits\s+me|physically\s+abusive|beating\s+me|domestic\s+violence|"
    r"threatened\s+to\s+kill\s+me|in\s+immediate\s+danger"
    r")\b",
    re.I
)

# Tier 0.5: Vague / Low-Entropy Distress Regex (<5 words expressing distress/confusion)
VAGUE_DISTRESS_REGEX = re.compile(
    r"^\s*("
    r"help(\s+me)?|please\s+help|i\s+need\s+help|"
    r"i('?m|\s+am)(\s+feeling|\s+so|\s+really)?\s+(hurt|lost|crying|broken|sad|heartbroken|confused|stuck|overwhelmed|falling\s+apart|alone)|"
    r"(i\s+)?feel(\s+so|\s+really)?\s+(hurt|lost|crying|broken|sad|heartbroken|confused|stuck|overwhelmed|falling\s+apart|alone)|"
    r"what\s+do\s+i\s+do|i\s+don'?t\s+know\s+what\s+to\s+do|so\s+lost|so\s+confused|so\s+overwhelmed"
    r")\s*[.?!]*$",
    re.I
)

# Tier 0.7: Explicit Course / Purchase Inquiry in Clinical Mode Regex
COURSE_INQUIRY_REGEX = re.compile(
    r"\b("
    r"(do\s+you\s+have|is\s+there)\s+a\s+(course|masterclass|program|workbook|class|webinar)|"
    r"(how\s+much|what\s+is\s+the\s+price|cost\s+of|pricing\s+for)\s+(a\s+|the\s+|are\s+|for\s+)?(courses?|masterclass(es)?|programs?|sessions?|consultations?)|"
    r"(how\s+(can|do)\s+i|where\s+(can|do)\s+i)\s+(buy|purchase|enroll|sign\s+up|join|work\s+with(\s+dr)?)|"
    r"what\s+(courses|masterclasses|programs)\s+(do\s+you|are)\s+(have|offer|available)|"
    r"available\s+(courses|masterclasses|programs)"
    r")\b",
    re.I
)


def _build_fast_response(
    answer_text: str,
    ai_model: str,
    user_id: str,
    conversation_id: Optional[str],
    clean_query: str,
    mode: str,
    user_profile: Dict[str, Any],
    start_time: float,
    conv_memory: Optional[Any] = None
) -> Dict[str, Any]:
    """Helper to render HTML and package instant sub-millisecond responses with memory tracking."""
    duration_ms = (time.time() - start_time) * 1000
    try:
        from markdown_it import MarkdownIt
        md = MarkdownIt("commonmark", {"breaks": True, "html": False})
        answer_html = md.render(answer_text)
    except Exception:
        answer_html = answer_text

    payload = {
        "success": True,
        "mode": mode,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "question": clean_query,
        "answer": answer_text,
        "answer_html": answer_html,
        "recommended_products": [],
        "sources": [],
        "raw_chunks": [],
        "user_profile": user_profile or {},
        "citations": [],
        "ai_model": ai_model,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "personalized": bool(user_profile and user_profile.get("has_history", False)),
        "duration_ms": round(duration_ms, 2)
    }

    if conv_memory:
        try:
            conv_memory.record_turn(
                user_id=user_id,
                conversation_id=conversation_id,
                user_query=clean_query,
                assistant_answer=answer_text,
                retrieved_chunks=[],
                mode=mode
            )
        except Exception:
            pass

    return payload


def execute_rag_pipeline(
    query: str,
    user_id: Optional[str] = "guest",
    top_k: int = 5,
    generate_answer: bool = True,
    mode: str = "generic",
    conversation_id: Optional[str] = None,
    folders: Optional[List[str]] = None,
    user_profile: Optional[Dict[str, Any]] = None,
    chat_history: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    """
    Unified RAG Pipeline Service used by both the REST API (/api/v1/ask)
    and the web UI (/search).

    Supports:
    - Direct stateless user_profile injection (zero database queries/duplication)
    - Direct frontend chat_history passing (stateless multi-turn memory)
    - Live WordPress API retrieval with in-memory caching fallback
    """
    start_time = time.time()
    
    if not query or not query.strip():
        raise ValueError("question is required")

    clean_query = query.strip()
    effective_uid = str(user_id or (user_profile.get("user_id") if user_profile else "guest")).strip()
    
    # 0. Tier 0: Acute Crisis & Immediate Safety Guardrail (<1ms instant response)
    if CRISIS_REGEX.search(clean_query):
        crisis_text = (
            "If you or someone you know is in acute distress, having thoughts of self-harm, or in an unsafe environment, please know you are not alone and free, confidential support is available 24/7:\n\n"
            "• **National Suicide & Crisis Lifeline**: Call or text **988** (Available 24/7 in the US & Canada).\n"
            "• **The Crisis Text Line**: Text **HOME** to **741741** to connect with a crisis counselor.\n"
            "• **National Domestic Violence Hotline**: Call **1-800-799-SAFE (7233)** or text **START** to **88788**.\n"
            "• **International Resources**: If you are outside the US, please visit [findahelpline.com](https://findahelpline.com) or contact your local emergency services (e.g., 911, 999, 112).\n\n"
            "While I am an AI assistant focused on relationship psychology and attachment theory, your immediate physical and emotional safety comes first. Please reach out to these trained professionals right away."
        )
        logger.warning(f"[RAG] Crisis safety guardrail triggered for user '{effective_uid}' on query: '{clean_query}'")
        return _build_fast_response(
            answer_text=crisis_text,
            ai_model="safety-crisis-guardrail",
            user_id=effective_uid,
            conversation_id=conversation_id,
            clean_query=clean_query,
            mode=mode,
            user_profile={},
            start_time=start_time,
            conv_memory=None
        )

    # 1. Fast Conversational Follow-up Resolution (0.1ms, zero LLM cost)
    from src.conversation_memory import get_conversation_memory
    conv_memory = get_conversation_memory()
    resolved_query, can_reuse_chunks, cached_chunks = conv_memory.resolve_follow_up(
        user_id=effective_uid,
        conversation_id=conversation_id,
        query=clean_query
    )
    is_follow_up = (resolved_query != clean_query) or can_reuse_chunks
    if is_follow_up:
        logger.info(f"[RAG] Follow-up detected. Stitched query: '{clean_query}' -> '{resolved_query}' (Parent chunk reuse: {can_reuse_chunks})")

    # 1.5 Query Expansion with Dating Slang to Clinical Terminology
    expanded_query = expand_query_semantics(resolved_query)

    # 2. Resolve User Profile & Query Vector:
    # If user_profile is passed directly in the request, normalize in RAM — zero DB lookups or disk writes!
    embedder = get_embedding_service()
    if user_profile and isinstance(user_profile, dict):
        clean_name = user_profile.get("name") or user_profile.get("display_name") or effective_uid or "Valued Member"
        owned = (
            user_profile.get("owned_products")
            or user_profile.get("all_purchases")
            or user_profile.get("courses_purchased")
            or []
        )
        user_profile = {
            "user_id": str(user_profile.get("user_id") or effective_uid or "guest"),
            "name": clean_name,
            "first_name": user_profile.get("first_name") or clean_name.split()[0],
            "display_name": clean_name,
            "email": user_profile.get("email") or f"{effective_uid}@example.com",
            "courses_purchased": user_profile.get("courses_purchased") or owned,
            "books_purchased": user_profile.get("books_purchased") or [],
            "all_purchases": owned,
            "owned_products": owned,
            "attachment_style": user_profile.get("attachment_style"),
            "streaks": user_profile.get("streaks") or [],
            "recent_activities": user_profile.get("recent_activities") or [],
            "past_records": user_profile.get("past_records") or [],
            "has_history": bool(owned or user_profile.get("streaks") or user_profile.get("past_records")),
            "backend": "Stateless Request Payload"
        }
        query_vector = embedder.embed_query(expanded_query)
    else:
        user_db = get_user_db()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_user = executor.submit(user_db.get_user_profile, effective_uid)
            future_embed = executor.submit(embedder.embed_query, expanded_query)
            user_profile = future_user.result()
            query_vector = future_embed.result()

    if not user_profile:
        user_profile = {
            "user_id": effective_uid,
            "name": effective_uid.capitalize(),
            "first_name": effective_uid.capitalize(),
            "email": f"{effective_uid}@example.com",
            "courses_purchased": [],
            "books_purchased": [],
            "all_purchases": [],
            "owned_products": [],
            "past_records": [],
            "has_history": False,
            "backend": "Graceful Fallback"
        }

    logger.info(f"[RAG] Request received for user '{effective_uid}' (question length: {len(clean_query)})")

    # 2.2 Tier 0.5: Vague / Low-Entropy Distress Diagnostic Router
    if VAGUE_DISTRESS_REGEX.match(clean_query):
        greeting_name = (
            user_profile.get("first_name")
            or user_profile.get("name")
            or user_profile.get("display_name")
            or "there"
        )
        if " " in str(greeting_name).strip():
            greeting_name = str(greeting_name).strip().split()[0]

        distress_text = (
            f"Hi {greeting_name},\n\n"
            "I hear you, and it is completely understandable to feel overwhelmed when navigating relationship pain. You don't have to carry it all alone or figure everything out at once.\n\n"
            "To help me give you the most relevant guidance and frameworks from Dr. Sarah Hensley, which of these feels closest to what you're experiencing right now?\n\n"
            "1. **Anxious triggers**: Feeling panicked, intense fear of abandonment, hyper-fixating, or waiting anxiously by your phone?\n"
            "2. **Avoidant withdrawal**: Feeling overwhelmed or suffocated, or experiencing your partner pulling away, shutting down, or going cold?\n"
            "3. **Conflict & communication**: Dealing with repeated circular arguments, walking on eggshells, or struggling to set a firm boundary?\n\n"
            "Tell me a little more about what's going on, and we can unpack it together step-by-step."
        )
        logger.info(f"[RAG] Vague distress diagnostic triggered for user '{user_id}' on query: '{clean_query}'")
        return _build_fast_response(
            answer_text=distress_text,
            ai_model="diagnostic-distress-router",
            user_id=user_id,
            conversation_id=conversation_id,
            clean_query=clean_query,
            mode=mode,
            user_profile=user_profile,
            start_time=start_time,
            conv_memory=conv_memory
        )

    # 2.3 Tier 0.7: Explicit Course / Masterclass Inquiry in Clinical Mode (<15ms instant response)
    if mode == "generic" and COURSE_INQUIRY_REGEX.search(clean_query):
        greeting_name = (
            user_profile.get("first_name")
            or user_profile.get("name")
            or user_profile.get("display_name")
            or "there"
        )
        if " " in str(greeting_name).strip():
            greeting_name = str(greeting_name).strip().split()[0]

        course_text = (
            f"Hi {greeting_name},\n\n"
            "Dr. Sarah Hensley offers several specialized masterclasses, guided workbooks, and deep-dive transformation programs—including dedicated tracks for anxious, avoidant, and secure attachment.\n\n"
            "Because I am focused strictly on clinical education and relationship theory here, I recommend switching to our **Program Advisor** mode or visiting Dr. Hensley's official website at [drsarahhensley.com](https://drsarahhensley.com) to explore specific course offerings, syllabus details, and current enrollment pricing!\n\n"
            "If you have questions about attachment dynamics, nervous system soothing, or communication frameworks, I'm here to guide you."
        )
        logger.info(f"[RAG] Course inquiry redirection triggered for user '{user_id}' on query: '{clean_query}'")
        return _build_fast_response(
            answer_text=course_text,
            ai_model="system-course-inquiry-router",
            user_id=user_id,
            conversation_id=conversation_id,
            clean_query=clean_query,
            mode=mode,
            user_profile=user_profile,
            start_time=start_time,
            conv_memory=conv_memory
        )

    # 2.5 Fast Greeting Intent Router (Tier 1: <12ms instant response for salutations & openers)
    greeting_regex = re.compile(
        r"^\s*("
        r"h+i+|h+e+y+|h+e+l+l+o+|heya|greetings|howdy|sup|yo+|hola|bonjour|namaste|salaam|ciao|aloha|"
        r"(good\s+)?(morning|afternoon|evening|day)|"
        r"what'?s\s+up|wassup|how('?s\s+it\s+going|\s+are\s+you(\s+doing)?)|"
        r"is\s+anyone\s+(there|here)|"
        r"(who|what)\s+are\s+you|what\s+can\s+you\s+do"
        r")(\s+(dr(\.|\s+)?sarah(\s+hensley)?|sarah|doc|team|bot|there))?[!.? ]*$",
        re.I
    )
    if greeting_regex.match(clean_query):
        greeting_name = (
            user_profile.get("first_name")
            or user_profile.get("name")
            or user_profile.get("display_name")
            or "there"
        )
        if " " in str(greeting_name).strip():
            greeting_name = str(greeting_name).strip().split()[0]

        is_identity_query = bool(re.search(r"\b(who|what)\s+are\s+you\b|\bwhat\s+can\s+you\s+do\b", clean_query, re.I))

        # Extract streaks if present
        raw_pab = user_profile.get("raw_pab_profile") or {}
        streaks = raw_pab.get("gamplify_attachmentos_user_streaks") or user_profile.get("gamplify_attachmentos_user_streaks") or []
        streak_mentions = []
        if isinstance(streaks, list):
            for s in streaks:
                if isinstance(s, dict) and s.get("habit") and s.get("streak"):
                    streak_mentions.append(f"{s['habit']} ({s['streak']}-day streak)")
        streak_text = f" I see you're staying dedicated with your {', '.join(streak_mentions[:2])}." if streak_mentions else ""

        if is_identity_query:
            if mode == "sales":
                greeting_text = (
                    f"Hi {greeting_name}! I am Doctor Sarah Hensley's official Program & Relationship Advisor.\n\n"
                    "I help members identify their attachment dynamics, navigate relationship roadblocks, and connect with the right course, bundle, or consultation tailored to their healing goals. "
                    "How can I assist you with your relationship today?"
                )
            else:
                greeting_text = (
                    f"Hi {greeting_name}! I am Doctor Sarah Hensley's Relationship Science AI Assistant.\n\n"
                    "I provide clinically validated relationship strategies, attachment theory breakdowns, and conflict de-escalation frameworks (such as the 1-1-1 journal and Boundary Ladder) based on Dr. Sarah's verified knowledge base. "
                    "What relationship topic or challenge would you like to explore?"
                )
        elif mode == "sales":
            greeting_text = (
                f"Hi {greeting_name}!\n\n"
                f"I'm Dr. Sarah Hensley's official Program & Relationship Advisor.{streak_text}\n\n"
                "Whether you're looking for guidance on anxious or avoidant dynamics, boundary tools, or exploring which masterclass, workbook, or private session can deepen your healing journey, how can I support you today?"
            )
        else:
            greeting_text = (
                f"Hi {greeting_name}!\n\n"
                f"Welcome to Doctor Sarah Hensley's Relationship Science knowledge assistant.{streak_text}\n\n"
                "I can provide clinical guidance, reflection protocols, and attachment strategies from our verified resource library. What relationship question or topic would you like to explore today?"
            )

        logger.info(f"[RAG] Greeting intent handled for user '{user_id}'")
        return _build_fast_response(
            answer_text=greeting_text,
            ai_model="system-greeting-router",
            user_id=user_id,
            conversation_id=conversation_id,
            clean_query=clean_query,
            mode=mode,
            user_profile=user_profile,
            start_time=start_time,
            conv_memory=conv_memory
        )

    # 3. Semantic Query Cache Lookup (bypassed on follow-ups)
    cache = get_semantic_cache()
    if generate_answer and not is_follow_up:
        cached_result = cache.lookup(query_vector, user_id=user_id, mode=mode)
        if cached_result:
            cache_duration_ms = (time.time() - start_time) * 1000
            cached_result["duration_ms"] = round(cache_duration_ms, 2)
            cached_result["question"] = clean_query  # reflect current user query phrasing
            logger.info(
                f"[RAG] Semantic Cache HIT for user '{user_id}' [mode: {mode}] in {cache_duration_ms:.2f}ms (similarity: {cached_result.get('cache_similarity')})"
            )
            cached_ans = cached_result.get("answer", "")
            if cached_ans and not cached_ans.startswith("Error"):
                conv_memory.record_turn(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    user_query=clean_query,
                    assistant_answer=cached_ans,
                    retrieved_chunks=cached_result.get("raw_chunks", []),
                    mode=mode
                )
            return cached_result

    # 4. Context Retrieval (Parent Chunk Reuse or Qdrant Search)
    retrieval_start = time.time()
    if can_reuse_chunks and cached_chunks:
        # Optimization: Reuse parent context from previous turn (skips Qdrant & Cross-Encoder!)
        retrieved_chunks = cached_chunks
        retrieval_duration_ms = (time.time() - retrieval_start) * 1000
        logger.info(f"[RAG] Reused {len(retrieved_chunks)} parent context chunks from previous turn in {retrieval_duration_ms:.2f}ms (Saved 150ms)")
    else:
        try:
            search_output = search_similar_chunks(
                query=resolved_query,
                top_k=top_k,
                query_vector=query_vector,
                mode=mode,
                folders=folders
            )
            retrieved_chunks = search_output.get("results", [])
        except Exception as e:
            logger.error(f"[RAG] Qdrant retrieval error: {str(e)}", exc_info=True)
            raise RAGGenerationError("Unable to generate an answer")

        retrieval_duration_ms = (time.time() - retrieval_start) * 1000
        logger.info(
            f"[RAG] Retrieved {len(retrieved_chunks)} relevant chunks from Qdrant in {retrieval_duration_ms:.2f}ms"
        )

    # 5. Answer Synthesis via LLM with Conversational Memory
    generator = get_generator_service()
    ai_answer = None
    ai_model = None
    citations = []
    usage = None
    personalized = False

    from src.conversation_memory import CHAT_HISTORY_TURNS
    if not chat_history:
        chat_history = conv_memory.get_chat_history(user_id=effective_uid, conversation_id=conversation_id, max_turns=CHAT_HISTORY_TURNS)

    if generate_answer and generator.is_configured():
        gen_start = time.time()
        try:
            gen_res = generator.generate_answer(
                query=resolved_query if is_follow_up else clean_query,
                retrieved_chunks=retrieved_chunks,
                user_context=user_profile,
                mode=mode,
                chat_history=chat_history,
                is_follow_up=is_follow_up
            )
            gen_duration_ms = (time.time() - gen_start) * 1000
            
            ai_answer = gen_res.get("answer")
            ai_model = gen_res.get("model")
            citations = gen_res.get("citations", [])
            usage = gen_res.get("usage")
            personalized = gen_res.get("personalized", False)
            
            logger.info(f"[RAG] Generated AI answer using {ai_model} in {gen_duration_ms:.2f}ms")
        except Exception as e:
            logger.error(f"[RAG] LLM generation error: {str(e)}", exc_info=True)
            raise RAGGenerationError("Unable to generate an answer")
    elif not generator.is_configured():
        ai_answer = "OpenAI API key is not configured in .env. Showing raw retrieved chunks only."

    # 6. Format Sources without leaking internal sensitive storage paths
    formatted_sources = []
    for chunk in retrieved_chunks:
        doc_name = chunk.get("document_name") or chunk.get("filename") or "Document"
        score = float(chunk.get("rerank_score", chunk.get("score", chunk.get("vector_score", 0.0))))
        page = chunk.get("page") or chunk.get("page_number")
        chunk_id = chunk.get("chunk_id")
        
        source_entry = {
            "document": doc_name,
            "relevance_score": round(score, 4)
        }
        if page is not None:
            source_entry["page"] = page
        if chunk_id is not None:
            source_entry["chunk_id"] = chunk_id
            
        formatted_sources.append(source_entry)

    total_duration_ms = (time.time() - start_time) * 1000
    logger.info(f"[RAG] Request for user '{user_id}' completed successfully in {total_duration_ms:.2f}ms")

    # Clean HTML rendering for UI and WordPress integration
    answer_html = None
    if ai_answer:
        from src.generator import strip_citation_markers
        ai_answer = strip_citation_markers(ai_answer)
        try:
            from markdown_it import MarkdownIt
            md = MarkdownIt("commonmark", {"breaks": True, "html": False})
            answer_html = md.render(ai_answer)
        except Exception:
            answer_html = ai_answer

    response_payload = {
        "success": True,
        "mode": mode,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "question": clean_query,
        "answer": ai_answer or "No answer could be generated.",
        "answer_html": answer_html,
        "recommended_products": gen_res.get("recommended_products", []) if 'gen_res' in locals() and gen_res else [],
        "sources": formatted_sources,
        "raw_chunks": retrieved_chunks,
        "user_profile": user_profile,
        "citations": citations,
        "ai_model": ai_model,
        "usage": usage,
        "personalized": personalized,
        "duration_ms": round(total_duration_ms, 2)
    }

    # 7. Record Turn in Conversational Memory
    if generate_answer and ai_answer and not ai_answer.startswith("Error") and not ai_answer.startswith("No relevant"):
        conv_memory.record_turn(
            user_id=user_id,
            conversation_id=conversation_id,
            user_query=clean_query,
            assistant_answer=ai_answer,
            retrieved_chunks=retrieved_chunks,
            mode=mode
        )

    # 8. Store in Semantic Cache if valid answer was generated
    if generate_answer and ai_answer and not ai_answer.startswith("Error"):
        cache.store(query_vector=query_vector, user_id=user_id, response=response_payload, mode=mode)

    return response_payload


def execute_sales_rag_pipeline(
    query: str,
    user_id: Optional[str] = "guest",
    top_k: int = 5,
    generate_answer: bool = True,
    conversation_id: Optional[str] = None,
    user_profile: Optional[Dict[str, Any]] = None,
    chat_history: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    """
    Dedicated Sales Pipeline: Soft-consultative relationship guidance
    paired with unowned course and book recommendations and multi-turn memory.
    Supports stateless user_profile and chat_history injection.
    """
    return execute_rag_pipeline(
        query=query,
        user_id=user_id,
        top_k=top_k,
        generate_answer=generate_answer,
        mode="sales",
        conversation_id=conversation_id,
        user_profile=user_profile,
        chat_history=chat_history
    )


