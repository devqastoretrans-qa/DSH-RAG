import os
import re
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()


def strip_citation_markers(text: str) -> str:
    """
    Strips inline bracketed citation references such as [1], [2], [1][2], [1, 2],
    [Source 1], [Doc: ...], footnotes, and any trailing 'Sources' or 'References' section
    without breaking markdown links such as [Course Name](https://...).
    """
    if not text:
        return text

    # Strip trailing Sources/References section (e.g., "### Sources", "Sources:", "References:", "Grounded Citations:")
    text = re.sub(
        r'\n+\s*(?:###?\s*)?(?:Sources|References|Grounded Citations|Source Documents)\s*:?[\s\S]*$',
        '',
        text,
        flags=re.IGNORECASE
    )

    # Negative lookahead (?!\() ensures markdown link labels like [Course Name](http...) are NOT touched
    text = re.sub(
        r'\[(?:\s*Source\s*)?\d+(?:[,\s\-–]+\d+)*\](?!\()',
        '',
        text,
        flags=re.IGNORECASE
    )
    # Strip multiple consecutive bracket citations like [1][2]
    text = re.sub(
        r'(?:\[(?:\s*Source\s*)?\d+(?:[,\s\-–]+\d+)*\](?!\()\s*)+',
        '',
        text,
        flags=re.IGNORECASE
    )
    # Strip [Doc: ...] if not a markdown link
    text = re.sub(r'\[Doc:\s*[^\]]+\](?!\()', '', text, flags=re.IGNORECASE)
    # Strip explicit "Source [1]" or "Source 1"
    text = re.sub(r'\bSource\s*\[\d+\](?!\()', '', text, flags=re.IGNORECASE)

    # Clean up double spaces before punctuation marks created by removal
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()


class OpenAIGeneratorService:
    """
    RAG Generation service that queries OpenAI ChatGPT models
    to synthesize answers strictly grounded on retrieved Qdrant chunks.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        openai_key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        provider = os.getenv("LLM_PROVIDER", "").strip().lower()

        # Prioritize Groq if provider is explicitly groq, or if GROQ_API_KEY is present and OpenAI is not configured
        if provider == "groq" or (groq_key and not openai_key) or (groq_key and provider != "openai"):
            self.provider = "groq"
            self.api_key = groq_key
            self.base_url = "https://api.groq.com/openai/v1"
            self.model = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
            if openai_key:
                self.fallback_provider = "openai"
                self.fallback_api_key = openai_key
                self.fallback_base_url = None
                self.fallback_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            else:
                self.fallback_provider = None
                self.fallback_api_key = None
                self.fallback_base_url = None
                self.fallback_model = None
        else:
            self.provider = "openai"
            self.api_key = openai_key
            self.base_url = None
            self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            if groq_key:
                self.fallback_provider = "groq"
                self.fallback_api_key = groq_key
                self.fallback_base_url = "https://api.groq.com/openai/v1"
                self.fallback_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
            else:
                self.fallback_provider = None
                self.fallback_api_key = None
                self.fallback_base_url = None
                self.fallback_model = None

        self._client = None
        self._fallback_client = None

    @property
    def client(self):
        if self._client is None:
            if not self.api_key:
                raise ValueError(
                    "No LLM API key configured. Please set GROQ_API_KEY or OPENAI_API_KEY in your .env file."
                )
            from openai import OpenAI
            client_kwargs = {"api_key": self.api_key}
            if self.base_url:
                client_kwargs["base_url"] = self.base_url
            self._client = OpenAI(**client_kwargs)
        return self._client

    @property
    def fallback_client(self):
        if self._fallback_client is None and self.fallback_api_key:
            from openai import OpenAI
            client_kwargs = {"api_key": self.fallback_api_key}
            if self.fallback_base_url:
                client_kwargs["base_url"] = self.fallback_base_url
            self._fallback_client = OpenAI(**client_kwargs)
        return self._fallback_client

    def is_configured(self) -> bool:
        """Returns True if an LLM API key (Groq or OpenAI) is present."""
        return bool(self.api_key and self.api_key.strip())

    @staticmethod
    def _get_chit_chat_reply(
        query: str,
        user_context: Optional[Dict[str, Any]] = None,
        mode: str = "generic"
    ) -> Optional[str]:
        """
        Safety net for short conversational openers/salutations (<= 7 words)
        such as greetings or pleasantries. Only triggers on explicit greetings;
        unrelated out-of-scope topics are cleanly routed to the out-of-domain handler.
        """
        clean_q = query.strip().lower()
        words = clean_q.split()
        if len(words) > 7:
            return None

        # Strictly check for genuine greetings / salutations / pleasantries
        is_greeting = bool(re.search(
            r"^(hi|hello|hey|greetings|good\s+(morning|afternoon|evening|day)|"
            r"who\s+are\s+you|what\s+can\s+you\s+do|how\s+can\s+you\s+help|what\s+is\s+this|"
            r"thanks|thank\s+you|help)\b",
            clean_q
        ))
        if not is_greeting:
            return None

        name = (user_context or {}).get("name") if user_context else None
        salutation_name = f" {name}" if name else ""

        if mode == "sales":
            return (
                f"Hi{salutation_name}! Welcome to Dr. Sarah Hensley's Relationship & Attachment Practice.\n\n"
                "I'm your Relationship Program Advisor. I can help guide you toward the right masterclasses, courses, and resources for your specific attachment style and relationship goals. "
                "How can I help you today?"
            )
        else:
            return (
                f"Hello{salutation_name}!\n\n"
                "Welcome to Dr. Sarah Hensley's Attachment & Relationship Knowledge Base. "
                "I'm here to provide psychoeducation, attachment theory guidance, and emotional healing frameworks. "
                "How can I assist you with your relationship or attachment questions today?"
            )

    def generate_answer(
        self,
        query: str,
        retrieved_chunks: List[Dict[str, Any]],
        user_context: Optional[Dict[str, Any]] = None,
        temperature: float = 0.2,
        mode: str = "generic",
        chat_history: Optional[List[Dict[str, str]]] = None,
        is_follow_up: bool = False
    ) -> Dict[str, Any]:
        """
        Synthesize a personalized answer to `query` grounded strictly on `retrieved_chunks`,
        verified `user_context`, and multi-turn `chat_history`.
        """
        if not self.is_configured():
            return {
                "answer": "OpenAI API key is not configured in .env. Showing raw retrieved chunks only.",
                "model": None,
                "citations": [],
                "personalized": False
            }

        if not retrieved_chunks:
            chit_chat = self._get_chit_chat_reply(query, user_context=user_context, mode=mode)
            if chit_chat:
                return {
                    "answer": chit_chat,
                    "model": "system-chit-chat-safety-net",
                    "citations": [],
                    "personalized": bool(user_context and user_context.get("has_history", False)),
                    "customer_name": user_context.get("name") if user_context else None,
                    "out_of_domain": False
                }

            user_salutation = f"Hi {user_context.get('name')},\n\n" if (user_context and user_context.get("name")) else ""

            # Explicit Course / Purchase Inquiry Exception in Clinical Mode
            is_course_inquiry = bool(re.search(
                r"\b(course|courses|masterclass|masterclasses|pricing|price|cost|buy|enroll|program|programs|work with dr|session|consultation)\b",
                query,
                re.I
            ))
            if is_course_inquiry and mode == "generic":
                return {
                    "answer": (
                        f"{user_salutation}Dr. Sarah Hensley offers specialized masterclasses, guided workbooks, and deep-dive transformation programs—including dedicated tracks for anxious, avoidant, and secure attachment.\n\n"
                        "Because I am focused strictly on clinical education and relationship theory here, I recommend switching to our **Program Advisor** mode or visiting Dr. Hensley's official website at [drsarahhensley.com](https://drsarahhensley.com) to explore specific course offerings, syllabus details, and current enrollment pricing!\n\n"
                        "If you have questions about attachment dynamics, nervous system soothing, or communication frameworks, I'm here to guide you."
                    ),
                    "model": "system-course-inquiry-router",
                    "citations": [],
                    "personalized": bool(user_context and user_context.get("has_history", False)),
                    "customer_name": user_context.get("name") if user_context else None,
                    "out_of_domain": False
                }

            return {
                "answer": (
                    f"{user_salutation}I am dedicated exclusively to Dr. Sarah Hensley's relationship psychology, attachment theory, and relationship transformation programs.\n\n"
                    "The question you asked is outside the scope of our verified knowledge base documents. "
                    "Please feel free to ask about attachment styles, relationship healing, communication frameworks, or Dr. Hensley's masterclasses!"
                ),
                "model": self.model,
                "citations": [],
                "personalized": bool(user_context and user_context.get("has_history", False)),
                "customer_name": user_context.get("name") if user_context else None,
                "out_of_domain": True
            }

        # Pre-LLM Relevance Gate: Check if retrieved chunks meet minimum similarity threshold
        # (Bypassed if this is a follow-up or chat history exists to avoid false rejection)
        max_vector_score = max((float(c.get("vector_score", c.get("score", 0.0))) for c in retrieved_chunks), default=0.0)
        max_rerank_score = max((float(c.get("rerank_score", c.get("score", 0.0))) for c in retrieved_chunks), default=0.0)

        if not is_follow_up and not chat_history and max_vector_score < 0.25 and max_rerank_score < 0.02:
            chit_chat = self._get_chit_chat_reply(query, user_context=user_context, mode=mode)
            if chit_chat:
                return {
                    "answer": chit_chat,
                    "model": "system-chit-chat-safety-net",
                    "citations": [],
                    "personalized": bool(user_context and user_context.get("has_history", False)),
                    "customer_name": user_context.get("name") if user_context else None,
                    "out_of_domain": False
                }

            user_salutation = f"Hi {user_context.get('name')},\n\n" if (user_context and user_context.get("name")) else ""
            refusal_text = (
                f"{user_salutation}I am dedicated exclusively to Dr. Sarah Hensley's relationship psychology, attachment theory, and relationship transformation programs.\n\n"
                "The topic you asked about is outside the scope of our verified knowledge base documents. "
                "Please feel free to ask any question regarding attachment styles, relationship healing, communication frameworks, or Dr. Hensley's programs!"
            )
            return {
                "answer": refusal_text,
                "model": self.model,
                "citations": [],
                "personalized": bool(user_context and user_context.get("has_history", False)),
                "customer_name": user_context.get("name") if user_context else None,
                "out_of_domain": True
            }

        # Format context with numbered citations
        context_blocks = []
        citations_meta = []
        for idx, chunk in enumerate(retrieved_chunks, start=1):
            fn = chunk.get("document_name") or chunk.get("filename", "Unknown")
            pg = chunk.get("page") or chunk.get("page_number", 1)
            cid = chunk.get("chunk_id", idx)
            score = chunk.get("score", 0.0)
            text = chunk.get("parent_context") or chunk.get("text", "")
            doc_id = chunk.get("document_id", "")

            citation_ref = f"Knowledge Excerpt {idx}"
            context_blocks.append(f"{citation_ref}:\n{text}")
            citations_meta.append({
                "source_id": idx,
                "document_id": doc_id,
                "document_name": fn,
                "filename": fn,
                "page": pg,
                "page_number": pg,
                "chunk_id": cid,
                "score": score
            })

        formatted_context = "\n\n---\n\n".join(context_blocks)

        # Build personalized user background block if available
        user_profile_section = ""
        user_name = None
        has_history = False
        if user_context:
            user_name = user_context.get("name") or user_context.get("display_name")
            display_name = user_context.get("display_name") or user_name
            raw_pab = user_context.get("raw_pab_profile")
            has_history = user_context.get("has_history", False)

            import json
            if isinstance(raw_pab, dict):
                full_profile_json = json.dumps(raw_pab, indent=2)
            else:
                full_profile_json = json.dumps(user_context, indent=2)

            user_profile_section = (
                "=== COMPLETE VERIFIED USER PROFILE & PAB API DATA (FULL JSON) ===\n"
                f"{full_profile_json}\n"
                "=================================================================\n\n"
            )

        # Build personalized greeting and context rules
        greeting_name = None
        if user_context:
            greeting_name = user_context.get("first_name") or user_context.get("name") or user_context.get("display_name")
            if greeting_name and " " in str(greeting_name).strip():
                greeting_name = str(greeting_name).strip().split()[0]

        if not greeting_name or str(greeting_name).strip() == "":
            greeting_name = "there"

        recommended_products = []
        if mode == "sales":
            from src.sales_catalog import match_relevant_unowned_products
            recommended_products = match_relevant_unowned_products(query=query, user_profile=user_context, limit=2)
            catalog_summary = []
            for p in recommended_products:
                catalog_summary.append(
                    f"- {p['name']} ({p['price']}): {p['description']} | Checkout: {p['checkout_url']}"
                )
            catalog_text = "\n".join(catalog_summary) if catalog_summary else "No unowned products remaining in catalog."

            system_prompt = (
                "You are the official Senior Relationship Program Advisor for Dr. Sarah Hensley.\n"
                "Your role is a SOFT CONSULTATIVE, VALUE-FIRST SALES ADVISOR: You validate members with compassionate clinical insights first, and then naturally present the relevant masterclass, course, or session as the dedicated transformational solution.\n\n"
                "MANDATORY SALES CONSULTANT RULES:\n"
                f"1. GREETING SALUTATION: Always start line 1 with:\n"
                f"   'Hi {greeting_name},'\n\n"
                "2. PERSONALIZED OPENING:\n"
                "   - For simple/definition queries: Keep greeting and opening to 1 single short line (e.g. 'Hi Alex,').\n"
                "   - For complex relationship scenarios: Warmly acknowledge their journey and dedication from their profile.\n\n"
                "3. DYNAMIC LENGTH & ADAPTIVE DEPTH (CRITICAL):\n"
                "   - SHORT / SIMPLE QUERIES (Definitions, single questions, quick lookups, price questions, e.g. 'What is stonewalling?', 'How much is the course?'):\n"
                "     * Total response must be strictly UNDER 70-90 words.\n"
                "     * Provide a direct 2-sentence definition and a 1-sentence quick recommendation with link.\n"
                "   - COMPLEX / MULTI-PART RELATIONSHIP SCENARIOS (User sharing an emotional struggle, conflict cycle, specific pain points, e.g. 'My partner shuts down and I panic and text repeatedly'):\n"
                "     * Provide a thorough, empathetic, and structured breakdown (160 to 250 words).\n"
                "     * Cover the root attachment trigger, 2 actionable regulation takeaways, and the dedicated course solution.\n\n"
                "4. VALUE-FIRST CLINICAL GUIDANCE:\n"
                "   - Give an empathetic, insightful explanation of their specific relationship situation with key takeaways grounded in the knowledge excerpts.\n"
                "   - STRICT CITATION RULE: Do not include citations, source numbers, footnotes, or references in your answer. Write naturally using the information provided.\n\n"
                "5. MANDATORY CONSULTATIVE NEXT-STEP RECOMMENDATION (SALES CONCLUSION):\n"
                "   - You MUST end your response with a clearly separated markdown section starting exactly with:\n"
                "   '### Recommended Next Step for Your Journey'\n"
                "   - In this section, warmly recommend the unowned offering from the catalog list below that matches their specific pain point:\n"
                f"{catalog_text}\n"
                "   - Clearly explain WHY this specific offering directly solves their problem, state its verified price, list what is included, and provide the official checkout link.\n"
                "   - STRICT DON'T: NEVER recommend or pitch a product the user already owns in their profile!\n"
                "   - STRICT DON'T: Never invent discounts, fake urgency, or use pushy high-pressure sales tactics."
            )
        else:
            system_prompt = (
                "You are the clinical educational AI Assistant for Dr. Sarah Hensley.\n"
                "You have access to: (1) Complete Raw PAB Inspect Profile API JSON, and (2) Clinical Knowledge Excerpts.\n\n"
                "STRICT CLINICAL / NON-COMMERCIAL RULES:\n"
                "1. STRICT NON-COMMERCIAL BOUNDARY & COURSE INQUIRY EXCEPTION:\n"
                "   - You are primarily a clinical relationship educator and mindfulness guide.\n"
                "   - ORDINARY EDUCATIONAL QUESTIONS: You MUST NEVER proactively pitch, name, or sell paid programs, masterclasses, courses, or guides.\n"
                "   - EXPLICIT USER INQUIRY EXCEPTION: If the user explicitly asks about available courses, masterclasses, pricing, or how to work further with Dr. Hensley (e.g. 'Do you have a course for anxious attachment?', 'How much are masterclasses?'), do NOT coldly refuse or deny their existence. Instead, warmly acknowledge that Dr. Hensley offers specialized masterclasses and coaching programs, and guide them to connect with the Program Advisor or visit Dr. Hensley's official website to explore enrollment details.\n"
                "   - Focus 100% on psychological concepts, nervous system regulation, self-soothing, and communication boundaries.\n\n"
                f"2. GREETING SALUTATION: Always start line 1 with:\n"
                f"   'Hi {greeting_name},'\n\n"
                "3. INTENT-AWARE PERSONALIZATION & OPENING:\n"
                "   - FACTUAL, DEFINITIONAL & DIRECT INQUIRIES ('What is...', 'How do I...', 'Where can I find...'):\n"
                "     * Answer directly, crisply, and immediately. Do NOT recite the user's streaks, points, or membership dates.\n"
                f"     * Start with 'Hi {greeting_name},' followed immediately by the clear factual definition or explanation.\n"
                "   - COMPLEX OR EMOTIONAL RELATIONSHIP SCENARIOS ('I'm struggling with conflict...', personal vulnerability):\n"
                "     * Warmly acknowledge their dedication and relevant habit progress to validate their journey.\n"
                "   - AVOID WORDING REDUNDANCIES: Use clean, natural phrasing (e.g. 'provides a script', never 'provides a scripted script').\n\n"
                "4. DYNAMIC LENGTH & ADAPTIVE DEPTH (CRITICAL):\n"
                "   - SHORT / SIMPLE QUERIES (Definitions, single terms, quick questions like 'What is deactivation?'):\n"
                "     * Answer directly and crisply in UNDER 80-100 words. Skip lengthy preambles.\n"
                "   - COMPLEX / NUANCED SCENARIOS (Detailed relationship dynamics, multi-part situations):\n"
                "     * Provide a comprehensive clinical breakdown (150-250 words) with structured takeaways.\n\n"
                "5. NATURAL KNOWLEDGE SYNTHESIS (STRICT NO CITATIONS):\n"
                "   - Answer the user's question strictly grounded on the Clinical Knowledge Excerpts below.\n"
                "   - STRICT CITATION RULE: Do not include citations, source numbers, footnotes, or references in your answer. Write naturally using the information provided.\n"
                "   - The user is completely unaware that documents exist on the backend. Present all concepts and guidance authoritatively and seamlessly in Dr. Sarah Hensley's natural clinical voice.\n"
                "   - Do NOT invent outside facts.\n"
                "   - Refuse off-topic requests (e.g. computer coding, general math) by stating: 'I am dedicated exclusively to Dr. Sarah Hensley\'s relationship psychology, attachment theory, and relationship transformation programs.'"
            )

        if chat_history:
            system_prompt += (
                "\n\n5. CONTINUING CONVERSATION DIRECTIVE:\n"
                "This is an active continuing conversation. Answer the user's follow-up question directly, warmly, and concisely. "
                "Do NOT repeat the greeting or re-list their membership milestones and habit streaks from earlier turns."
            )

        user_prompt = f"{user_profile_section}Retrieved Knowledge Context:\n{formatted_context}\n\nUser Question: {query}\n\nPersonalized Answer:"

        # Assemble full conversation messages array
        messages = [{"role": "system", "content": system_prompt}]
        if chat_history:
            for turn in chat_history:
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": user_prompt})

        used_model = self.model
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=2500
            )
            generated_text = response.choices[0].message.content
        except Exception as e:
            if self.fallback_client:
                import logging
                logging.getLogger("rag_generator").warning(
                    f"Primary provider '{self.provider}' failed ({e}). Falling back to '{self.fallback_provider}'..."
                )
                try:
                    response = self.fallback_client.chat.completions.create(
                        model=self.fallback_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=2500
                    )
                    generated_text = response.choices[0].message.content
                    used_model = self.fallback_model
                except Exception as fb_err:
                    return {
                        "answer": f"Error calling {self.provider.upper()} and fallback {self.fallback_provider.upper()} API: {str(fb_err)}",
                        "model": self.model,
                        "citations": citations_meta,
                        "error": str(fb_err)
                    }
            else:
                return {
                    "answer": f"Error calling {self.provider.upper()} API: {str(e)}",
                    "model": self.model,
                    "citations": citations_meta,
                    "error": str(e)
                }

        if generated_text:
            generated_text = strip_citation_markers(generated_text)
            generated_text = re.sub(r'\bscripted\s+script\b', 'script', generated_text, flags=re.I)
            generated_text = re.sub(r'(\n\s*[-*•]\s*)$', '', generated_text.rstrip())

        if mode == "sales" and recommended_products and generated_text and "Recommended Next Step for Your Journey" not in generated_text:
            fallback_card = "\n\n### Recommended Next Step for Your Journey\n"
            for p in recommended_products:
                fallback_card += f"To deepen your healing on this dynamic, Dr. Sarah Hensley's **{p['name']}** ({p['price']}) provides step-by-step guidance. [Explore details and enroll here]({p['checkout_url']}).\n"
            generated_text += fallback_card

        return {
            "answer": generated_text,
            "model": used_model,
            "citations": citations_meta,
            "recommended_products": recommended_products,
            "mode": mode,
            "personalized": bool(user_context and has_history),
            "customer_name": user_name if user_context else None,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                "completion_tokens": response.usage.completion_tokens if response.usage else None,
                "total_tokens": response.usage.total_tokens if response.usage else None
            }
        }

    def generate_answer_stream(
        self,
        query: str,
        retrieved_chunks: List[Dict[str, Any]],
        user_context: Optional[Dict[str, Any]] = None,
        temperature: float = 0.2,
        mode: str = "generic",
        chat_history: Optional[List[Dict[str, str]]] = None,
        is_follow_up: bool = False,
        recommended_products: Optional[List[Dict[str, Any]]] = None
    ):
        """
        Streams synthesized tokens chunk by chunk using Server-Sent Events (SSE).
        Supports generic (clinical) and sales consultation modes, chat history, and provider failover.
        """
        if not self.is_configured():
            yield {"token": "LLM API key is not configured in .env.", "done": True}
            return

        if not retrieved_chunks:
            chit_chat = self._get_chit_chat_reply(query, user_context=user_context, mode=mode)
            if chit_chat:
                yield {"token": chit_chat, "done": True, "citations": []}
                return
            yield {"token": "No relevant document chunks were found in the knowledge base to answer your question.", "done": True}
            return

        # Pre-LLM Relevance Gate (bypassed if follow-up or chat history exists)
        max_vector_score = max((float(c.get("vector_score", c.get("score", 0.0))) for c in retrieved_chunks), default=0.0)
        max_rerank_score = max((float(c.get("rerank_score", c.get("score", 0.0))) for c in retrieved_chunks), default=0.0)

        if not is_follow_up and not chat_history and max_vector_score < 0.25 and max_rerank_score < 0.02:
            chit_chat = self._get_chit_chat_reply(query, user_context=user_context, mode=mode)
            if chit_chat:
                yield {"token": chit_chat, "done": True, "citations": []}
                return

            user_salutation = f"Hi {user_context.get('name')},\n\n" if (user_context and user_context.get("name")) else ""
            refusal_text = (
                f"{user_salutation}I am dedicated exclusively to Dr. Sarah Hensley's relationship psychology, attachment theory, and relationship transformation programs.\n\n"
                "The topic you asked about is outside the scope of our verified knowledge base documents. "
                "Please feel free to ask any question regarding attachment styles, relationship healing, communication frameworks, or Dr. Hensley's programs!"
            )
            yield {"token": refusal_text, "done": True, "citations": []}
            return

        # Format context blocks
        context_blocks = []
        citations_meta = []
        for idx, chunk in enumerate(retrieved_chunks, start=1):
            fn = chunk.get("document_name") or chunk.get("filename", "Unknown")
            pg = chunk.get("page") or chunk.get("page_number", 1)
            cid = chunk.get("chunk_id", idx)
            score = chunk.get("score", 0.0)
            text = chunk.get("parent_context") or chunk.get("text", "")
            doc_id = chunk.get("document_id", "")

            citation_ref = f"Knowledge Excerpt {idx}"
            context_blocks.append(f"{citation_ref}:\n{text}")
            citations_meta.append({
                "source_id": idx,
                "document_id": doc_id,
                "document_name": fn,
                "filename": fn,
                "page": pg,
                "page_number": pg,
                "chunk_id": cid,
                "score": score
            })

        formatted_context = "\n\n---\n\n".join(context_blocks)

        user_profile_section = ""
        user_name = None
        has_history = False
        greeting_name = "there"
        if user_context:
            user_name = user_context.get("name") or user_context.get("display_name")
            has_history = user_context.get("has_history", False)
            raw_pab = user_context.get("raw_pab_profile")

            import json
            if isinstance(raw_pab, dict):
                full_profile_json = json.dumps(raw_pab, indent=2)
            else:
                full_profile_json = json.dumps(user_context, indent=2)

            user_profile_section = (
                "=== COMPLETE VERIFIED USER PROFILE & PAB API DATA (FULL JSON) ===\n"
                f"{full_profile_json}\n"
                "=================================================================\n\n"
            )

            raw_greeting = user_context.get("first_name") or user_context.get("name") or user_context.get("display_name")
            if raw_greeting and " " in str(raw_greeting).strip():
                greeting_name = str(raw_greeting).strip().split()[0]
            elif raw_greeting:
                greeting_name = str(raw_greeting).strip()

        if mode == "sales":
            if recommended_products is None:
                from src.sales_catalog import match_relevant_unowned_products
                recommended_products = match_relevant_unowned_products(query=query, user_profile=user_context, limit=2)
            catalog_summary = []
            for p in recommended_products:
                catalog_summary.append(
                    f"- {p['name']} ({p['price']}): {p['description']} | Checkout: {p['checkout_url']}"
                )
            catalog_text = "\n".join(catalog_summary) if catalog_summary else "No unowned products remaining in catalog."

            system_prompt = (
                "You are the official Senior Relationship Program Advisor for Dr. Sarah Hensley.\n"
                "Your role is a SOFT CONSULTATIVE, VALUE-FIRST SALES ADVISOR: You validate members with compassionate clinical insights first, and then naturally present the relevant masterclass, course, or session as the dedicated transformational solution.\n\n"
                "MANDATORY SALES CONSULTANT RULES:\n"
                f"1. GREETING SALUTATION: Always start line 1 with:\n"
                f"   'Hi {greeting_name},'\n\n"
                "2. PERSONALIZED OPENING:\n"
                "   - For simple/definition queries: Keep greeting and opening to 1 single short line.\n"
                "   - For complex relationship scenarios: Warmly acknowledge their journey and dedication from their profile.\n\n"
                "3. DYNAMIC LENGTH & ADAPTIVE DEPTH (CRITICAL):\n"
                "   - SHORT / SIMPLE QUERIES: Total response strictly under 70-90 words.\n"
                "   - COMPLEX / MULTI-PART RELATIONSHIP SCENARIOS: Thorough breakdown (160 to 250 words).\n\n"
                "4. VALUE-FIRST CLINICAL GUIDANCE:\n"
                "   - Give an insightful explanation grounded in the knowledge excerpts.\n"
                "   - STRICT CITATION RULE: Do not include citations, source numbers, footnotes, or references in your answer. Write naturally using the information provided.\n\n"
                "5. MANDATORY CONSULTATIVE NEXT-STEP RECOMMENDATION:\n"
                "   - End with markdown section starting exactly with: '### Recommended Next Step for Your Journey'\n"
                f"{catalog_text}\n"
                "   - STRICT: Never recommend a product the user already owns! Never use pushy tactics."
            )
        else:
            system_prompt = (
                "You are the clinical educational AI Assistant for Dr. Sarah Hensley.\n"
                "You have access to: (1) Complete Raw PAB Profile API JSON, and (2) Clinical Knowledge Excerpts.\n\n"
                "STRICT CLINICAL / NON-COMMERCIAL RULES:\n"
                "1. STRICT NON-COMMERCIAL BOUNDARY: Never proactively sell paid programs. If asked explicitly about courses, acknowledge them and refer to Program Advisor or drsarahhensley.com.\n"
                f"2. GREETING SALUTATION: Always start line 1 with: 'Hi {greeting_name},'\n"
                "3. INTENT-AWARE OPENING:\n"
                "   - For direct factual/definitional questions ('What is...', 'How do I...', 'Where is...'): Jump directly into the answer. Do NOT recite habit streaks, points, or membership dates.\n"
                "   - For complex emotional or relationship situations: Warmly acknowledge their relevant progress or streaks.\n"
                "   - Avoid redundancies: Use 'provides a script' rather than 'provides a scripted script'.\n"
                "4. DYNAMIC LENGTH: Short queries under 80-100 words. Complex scenarios 150-250 words.\n"
                "5. NATURAL KNOWLEDGE SYNTHESIS (STRICT NO CITATIONS):\n"
                "   - Answer strictly grounded on the Clinical Knowledge Excerpts below.\n"
                "   - STRICT CITATION RULE: Do not include citations, source numbers, footnotes, or references in your answer. Write naturally using the information provided.\n"
                "   - The user is completely unaware that documents exist on the backend. Speak authoritatively and seamlessly in Dr. Sarah's natural clinical voice."
            )

        if chat_history:
            system_prompt += (
                "\n\nCONTINUING CONVERSATION DIRECTIVE:\n"
                "This is an active continuing conversation. Answer directly without repeating greetings or membership milestones."
            )

        user_prompt = f"{user_profile_section}Retrieved Knowledge Context:\n{formatted_context}\n\nUser Question: {query}\n\nPersonalized Answer:"

        messages = [{"role": "system", "content": system_prompt}]
        if chat_history:
            for turn in chat_history:
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": user_prompt})

        # Try primary stream, fallback to secondary if connection fails
        stream_client = self.client
        stream_model = self.model
        try:
            stream = stream_client.chat.completions.create(
                model=stream_model,
                messages=messages,
                temperature=temperature,
                max_tokens=2500,
                stream=True
            )
        except Exception as e:
            if self.fallback_client:
                import logging
                logging.getLogger("rag_generator").warning(
                    f"Primary stream '{self.provider}' failed ({e}). Falling back to '{self.fallback_provider}'..."
                )
                stream_client = self.fallback_client
                stream_model = self.fallback_model
                try:
                    stream = stream_client.chat.completions.create(
                        model=stream_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=2500,
                        stream=True
                    )
                except Exception as fb_err:
                    yield {"token": f"\n\n[Error generating stream: {str(fb_err)}]", "done": True, "error": str(fb_err)}
                    return
            else:
                yield {"token": f"\n\n[Error generating stream: {str(e)}]", "done": True, "error": str(e)}
                return

        try:
            full_text = []
            for chunk in stream:
                content = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else None
                if content:
                    full_text.append(content)
                    yield {"token": content, "done": False}

            combined_text = "".join(full_text)
            if mode == "sales" and recommended_products and "Recommended Next Step for Your Journey" not in combined_text:
                fallback_card = "\n\n### Recommended Next Step for Your Journey\n"
                for p in recommended_products:
                    fallback_card += f"To deepen your healing on this dynamic, Dr. Sarah Hensley's **{p['name']}** ({p['price']}) provides step-by-step guidance. [Explore details and enroll here]({p['checkout_url']}).\n"
                full_text.append(fallback_card)
                yield {"token": fallback_card, "done": False}

            yield {
                "token": "",
                "done": True,
                "full_answer": strip_citation_markers("".join(full_text)),
                "citations": citations_meta,
                "recommended_products": recommended_products or [],
                "model": stream_model,
                "mode": mode,
                "personalized": bool(user_context and has_history),
                "customer_name": user_name if user_context else None
            }
        except Exception as e:
            yield {"token": f"\n\n[Error generating stream: {str(e)}]", "done": True, "error": str(e)}


# Singleton instance
_generator_instance: Optional[OpenAIGeneratorService] = None


def get_generator_service() -> OpenAIGeneratorService:
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = OpenAIGeneratorService()
    return _generator_instance
