import os
import sys
import shutil
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super(NumberedCanvas, self).__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super(NumberedCanvas, self).showPage()
        super(NumberedCanvas, self).save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        
        # Header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(45, 11 * inch - 30, "DR. SARAH HENSLEY AI RAG — PRODUCTION OPERATIONS RUNBOOK")
            self.drawRightString(8.5 * inch - 45, 11 * inch - 30, "AWS EC2 Production Field Manual")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(45, 11 * inch - 35, 8.5 * inch - 45, 11 * inch - 35)

        # Footer (all pages)
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(45, 36, 8.5 * inch - 45, 36)
        
        self.setFont("Helvetica", 7.5)
        self.drawString(45, 25, "CONFIDENTIAL — Doctor Sarah Hensley AI RAG Production Operations")
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(8.5 * inch - 45, 25, page_str)
        self.restoreState()


def build_runbook_pdf(output_pdf_path="DSH_RAG_Production_Operations_Runbook.pdf"):
    doc = SimpleDocTemplate(
        str(output_pdf_path),
        pagesize=letter,
        leftMargin=45,
        rightMargin=45,
        topMargin=42,
        bottomMargin=42
    )

    styles = getSampleStyleSheet()

    c_navy = colors.HexColor("#0F172A")
    c_blue = colors.HexColor("#1E40AF")
    c_gold = colors.HexColor("#B8860B")
    c_slate = colors.HexColor("#334155")
    c_light_slate = colors.HexColor("#64748B")
    c_bg_light = colors.HexColor("#F8FAFC")
    c_border = colors.HexColor("#CBD5E1")
    c_emerald = colors.HexColor("#059669")
    c_code_bg = colors.HexColor("#F1F5F9")

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        textColor=c_navy
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13,
        textColor=c_blue
    )
    h1_style = ParagraphStyle(
        'Heading1',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=c_navy,
        spaceBefore=8,
        spaceAfter=4
    )
    h2_style = ParagraphStyle(
        'Heading2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=c_slate,
        spaceBefore=6,
        spaceAfter=3
    )
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=c_slate
    )
    body_bold = ParagraphStyle(
        'BodyBold',
        parent=body_style,
        fontName='Helvetica-Bold'
    )
    code_style = ParagraphStyle(
        'CodeStyle',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#0F172A")
    )
    code_bold = ParagraphStyle(
        'CodeBold',
        parent=code_style,
        fontName='Courier-Bold'
    )
    th_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.white
    )
    td_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        leading=9,
        textColor=c_slate
    )
    td_bold = ParagraphStyle(
        'TableCellBold',
        parent=td_style,
        fontName='Helvetica-Bold'
    )

    story = []

    # 1. Header Banner
    meta_table_data = [
        [
            Paragraph("<b>DR. SARAH HENSLEY AI RAG — PRODUCTION RUNBOOK</b>", title_style),
            Paragraph("<b>ENVIRONMENT:</b> PRODUCTION (AWS EC2)<br/><b>HOST:</b> agent.doctorsarahhensley.com<br/><b>IP:</b> 18.118.138.91 | <b>VERSION:</b> 2.2.0<br/><b>STATUS:</b> ACTIVE / HARDENED", td_style)
        ]
    ]
    meta_table = Table(meta_table_data, colWidths=[4.2 * inch, 3.0 * inch])
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 6))

    # Divider bar
    divider = Table([[""]], colWidths=[7.2 * inch], rowHeights=[2])
    divider.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), c_blue)]))
    story.append(divider)
    story.append(Spacer(1, 8))

    # SECTION 1: Architecture & Network Topology
    story.append(Paragraph("1. System Architecture & Port Binding Inventory", h1_style))
    story.append(Paragraph(
        "All internal services are strictly isolated to loopback interface (<code>127.0.0.1</code>) and reverse-proxied through Nginx with HSTS, TLS 1.3, and strict security headers.",
        body_style
    ))
    story.append(Spacer(1, 4))

    arch_data = [
        [Paragraph("Service", th_style), Paragraph("Internal Binding", th_style), Paragraph("Runtime / Supervisor", th_style), Paragraph("Role & Isolation Policy", th_style)],
        [Paragraph("<b>Nginx Proxy</b>", td_style), Paragraph("0.0.0.0:80 / 443", td_style), Paragraph("systemd / nginx", td_style), Paragraph("TLS Termination, HSTS, Rate Limiting, Static Asset Cache", td_style)],
        [Paragraph("<b>FastAPI Backend</b>", td_style), Paragraph("127.0.0.1:8000", td_style), Paragraph("systemd / dsh-rag.service", td_style), Paragraph("RAG Orchestration, SSE Streaming, User Personalization", td_style)],
        [Paragraph("<b>Qdrant Vector DB</b>", td_style), Paragraph("127.0.0.1:6333", td_style), Paragraph("Native Qdrant daemon", td_style), Paragraph("384-dim MiniLM vector search on collection <code>documents</code>", td_style)],
        [Paragraph("<b>MySQL 8.4 Server</b>", td_style), Paragraph("127.0.0.1:3306", td_style), Paragraph("systemd / mysqld", td_style), Paragraph("Relational CRM customer profiles & conversation memory", td_style)],
        [Paragraph("<b>SQLite DBs</b>", td_style), Paragraph("Embedded (*.db)", td_style), Paragraph("In-Process WAL mode", td_style), Paragraph("<code>users_data.db</code> & <code>ingestion_tracker.db</code> local cache", td_style)],
    ]
    arch_table = Table(arch_data, colWidths=[1.3 * inch, 1.3 * inch, 1.6 * inch, 3.0 * inch])
    arch_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_navy),
        ('GRID', (0,0), (-1,-1), 0.5, c_border),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, c_bg_light]),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(arch_table)
    story.append(Spacer(1, 8))

    # SECTION 2: Operations & Service Management
    story.append(Paragraph("2. Operational Management & Deployment Playbook", h1_style))
    story.append(Paragraph(
        "The application runs continuously as an unprivileged systemd service under the <code>ubuntu</code> user with automatic crash recovery (<code>Restart=always</code>, <code>RestartSec=3s</code>).",
        body_style
    ))
    story.append(Spacer(1, 4))

    cmd_box = [
        [Paragraph("<b>Core CLI Commands:</b><br/>"
                   "• Check Status: <code>sudo systemctl status dsh-rag.service</code><br/>"
                   "• Restart Service: <code>sudo systemctl restart dsh-rag.service</code><br/>"
                   "• Live App Logs: <code>journalctl -u dsh-rag.service -f</code><br/>"
                   "• Live Chat Stream: <code>tail -f /home/ubuntu/DSH-RAG/logs/chat.log</code><br/>"
                   "• Production Deploy: <code>cd /home/ubuntu/DSH-RAG &amp;&amp; git pull &amp;&amp; sudo systemctl restart dsh-rag.service</code>",
                   body_style)]
    ]
    cmd_table = Table(cmd_box, colWidths=[7.2 * inch])
    cmd_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_code_bg),
        ('BOX', (0,0), (-1,-1), 0.5, c_border),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(cmd_table)
    story.append(Spacer(1, 8))

    # SECTION 3: API & Security Catalog
    story.append(Paragraph("3. API Endpoints & Zero-Trust Security Policy", h1_style))
    story.append(Paragraph(
        "All incoming traffic is governed by strict zero-trust identity enforcement. Unauthenticated public callers are mathematically locked to <code>user_id='guest'</code> to prevent IDOR user impersonation.",
        body_style
    ))
    story.append(Spacer(1, 4))

    api_data = [
        [Paragraph("Endpoint", th_style), Paragraph("Method", th_style), Paragraph("Auth Requirement", th_style), Paragraph("Rate Limit", th_style), Paragraph("Purpose / Security Rule", th_style)],
        [Paragraph("<code>/chat</code>", td_style), Paragraph("POST", td_style), Paragraph("Public / Session Token", td_style), Paragraph("15 req/min", td_style), Paragraph("Interactive chat; forces unverified calls to 'guest'", td_style)],
        [Paragraph("<code>/chat/stream</code>", td_style), Paragraph("POST", td_style), Paragraph("Public / Session Token", td_style), Paragraph("15 req/min", td_style), Paragraph("Live SSE token stream with Layer 2 greeting guardrail", td_style)],
        [Paragraph("<code>/health</code>", td_style), Paragraph("GET", td_style), Paragraph("Public (Sanitized)", td_style), Paragraph("None", td_style), Paragraph("High-level readiness; redacts internal IPs & file paths", td_style)],
        [Paragraph("<code>/documents</code>", td_style), Paragraph("GET", td_style), Paragraph("Master <code>X-API-Key</code>", td_style), Paragraph("Admin", td_style), Paragraph("Protected; lists all 19 verified knowledge base files", td_style)],
        [Paragraph("<code>/drive/status</code>", td_style), Paragraph("GET", td_style), Paragraph("Master <code>X-API-Key</code>", td_style), Paragraph("Admin", td_style), Paragraph("Protected; returns Google Drive monitor connection status", td_style)],
        [Paragraph("<code>/drive/sync</code>", td_style), Paragraph("POST", td_style), Paragraph("Master <code>X-API-Key</code>", td_style), Paragraph("Admin", td_style), Paragraph("Protected; triggers immediate manual Google Drive re-scan", td_style)],
        [Paragraph("<code>/api/v1/ask</code>", td_style), Paragraph("POST", td_style), Paragraph("Master <code>X-API-Key</code>", td_style), Paragraph("Admin", td_style), Paragraph("Headless RAG retrieval for external service integrations", td_style)],
        [Paragraph("<code>/api/v1/cache/clear</code>", td_style), Paragraph("POST", td_style), Paragraph("Master <code>X-API-Key</code>", td_style), Paragraph("Admin", td_style), Paragraph("Flushes in-memory Semantic Cache and User Profile Cache", td_style)],
    ]
    api_table = Table(api_data, colWidths=[1.3 * inch, 0.6 * inch, 1.4 * inch, 0.8 * inch, 3.1 * inch])
    api_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_navy),
        ('GRID', (0,0), (-1,-1), 0.5, c_border),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, c_bg_light]),
        ('TOPPADDING', (0,0), (-1,-1), 2.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
    ]))
    story.append(api_table)
    story.append(Spacer(1, 8))

    # SECTION 4: Token Optimization & Guardrails
    story.append(Paragraph("4. Token Optimization & Safeguard Architecture", h1_style))
    story.append(Paragraph(
        "The generation engine enforces a multi-layer safeguard system to guarantee cost control, prompt caching discounts, and zero mid-sentence response cutoffs.",
        body_style
    ))
    story.append(Spacer(1, 4))

    safeguards_data = [
        [Paragraph("Safeguard Layer", th_style), Paragraph("Mechanism", th_style), Paragraph("Target Threshold", th_style), Paragraph("Operational Impact", th_style)],
        [Paragraph("<b>Layer 1: Static Prompt Cache</b>", td_style), Paragraph("Byte-identical system prompts", td_style), Paragraph("100% Static Prefix", td_style), Paragraph("Unlocks ~50% API cost discount via provider prompt caching", td_style)],
        [Paragraph("<b>Layer 2: Dynamic Token Ceilings</b>", td_style), Paragraph("Lane-specific <code>max_tokens</code>", td_style), Paragraph("250 / 700 / 800 tok", td_style), Paragraph("Short: 250, Clinical: 700, Sales: 800 (Prevents 2500-token runaway)", td_style)],
        [Paragraph("<b>Layer 3: Greeting Guardrail</b>", td_style), Paragraph("Deterministic Python regex", td_style), Paragraph("Turn 1 / Turn 2+", td_style), Paragraph("Forces 'Hi {Name},' on Turn 1; strips repetitive greetings on Turn 2+", td_style)],
        [Paragraph("<b>Layer 4: Truncation Trimmer</b>", td_style), Paragraph("<code>clean_trailing_truncation()</code>", td_style), Paragraph("Terminal punctuation", td_style), Paragraph("Snaps output to last full sentence; eliminates dangling '**Practical'", td_style)],
    ]
    safeguards_table = Table(safeguards_data, colWidths=[1.6 * inch, 1.7 * inch, 1.2 * inch, 2.7 * inch])
    safeguards_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_navy),
        ('GRID', (0,0), (-1,-1), 0.5, c_border),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, c_bg_light]),
        ('TOPPADDING', (0,0), (-1,-1), 2.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
    ]))
    story.append(safeguards_table)
    story.append(Spacer(1, 8))

    # Page break for operational schedules & disaster recovery
    story.append(PageBreak())

    # SECTION 5: Scheduled Automation & Logrotate
    story.append(Paragraph("5. Automated Schedules, Logrotate & Maintenance", h1_style))
    story.append(Paragraph(
        "Operational maintenance is fully automated via Linux <code>crontab</code> and <code>logrotate</code> to prevent disk exhaustion over prolonged high-volume production use.",
        body_style
    ))
    story.append(Spacer(1, 4))

    cron_data = [
        [Paragraph("Schedule (IST)", th_style), Paragraph("Script / Command", th_style), Paragraph("Target Assets", th_style), Paragraph("Retention & Outcome", th_style)],
        [Paragraph("<b>Daily 02:00 AM</b>", td_style), Paragraph("<code>sync_wordpress_to_mysql.py</code>", td_style), Paragraph("WooCommerce REST API", td_style), Paragraph("Syncs new orders, purchases, & quiz results to MySQL", td_style)],
        [Paragraph("<b>Daily 03:00 AM</b>", td_style), Paragraph("<code>backup_databases.py --local-only</code>", td_style), Paragraph("SQLite DBs & MySQL Dump", td_style), Paragraph("Zero-lock compressed snapshots; saves 98% space", td_style)],
        [Paragraph("<b>Sunday 04:00 AM</b>", td_style), Paragraph("<code>run_maintenance.py</code>", td_style), Paragraph("SQLite DBs & systemd journal", td_style), Paragraph("Runs <code>VACUUM</code>, updates query stats, vacuums 7d journal", td_style)],
        [Paragraph("<b>Automated Hourly</b>", td_style), Paragraph("<code>/etc/logrotate.d/dsh-rag</code>", td_style), Paragraph("All <code>logs/*.log</code> files", td_style), Paragraph("Rotates at 10MB; retains 7 compressed .gz files; zero downtime", td_style)],
    ]
    cron_table = Table(cron_data, colWidths=[1.2 * inch, 2.0 * inch, 1.8 * inch, 2.2 * inch])
    cron_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_navy),
        ('GRID', (0,0), (-1,-1), 0.5, c_border),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, c_bg_light]),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(cron_table)
    story.append(Spacer(1, 8))

    # SECTION 6: Knowledge Base Ingestion
    story.append(Paragraph("6. Knowledge Base & Google Drive Ingestion Operations", h1_style))
    story.append(Paragraph(
        "Dr. Sarah Hensley's clinical library is continuously synchronized from Google Drive into Qdrant vectors.",
        body_style
    ))
    story.append(Spacer(1, 4))

    kb_box = [
        [Paragraph(
            "<b>Folder Configuration:</b> Google Drive Folder ID: <code>13iyfLkaWOvvw8JQVyzjw_YjTec9cZ_PG</code><br/>"
            "<b>Service Account:</b> <code>/home/ubuntu/DSH-RAG/service_account.json</code> (Encrypted credentials)<br/>"
            "<b>Current Status:</b> 19 clinical documents ingested and marked <code>READY</code> in Qdrant.<br/>"
            "<b>Manual Re-Index Trigger:</b> <code>curl -X POST https://agent.doctorsarahhensley.com/drive/sync -H 'X-API-Key: dsh_rag_secret_key_2026'</code><br/>"
            "<b>Verification Endpoint:</b> <code>curl -s https://agent.doctorsarahhensley.com/documents -H 'X-API-Key: dsh_rag_secret_key_2026' | jq</code>",
            body_style
        )]
    ]
    kb_table = Table(kb_box, colWidths=[7.2 * inch])
    kb_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_code_bg),
        ('BOX', (0,0), (-1,-1), 0.5, c_border),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(kb_table)
    story.append(Spacer(1, 8))

    # SECTION 7: Incident Response & Disaster Recovery
    story.append(Paragraph("7. Incident Response Playbook & Disaster Recovery", h1_style))
    story.append(Paragraph(
        "Follow these standard operating procedures during system alerts, server restarts, or data recovery operations.",
        body_style
    ))
    story.append(Spacer(1, 4))

    playbook_data = [
        [Paragraph("Incident Scenario", th_style), Paragraph("Diagnostic Steps", th_style), Paragraph("Resolution Procedure", th_style)],
        [
            Paragraph("<b>502 Bad Gateway / Process Crash</b>", td_style),
            Paragraph("1. <code>sudo systemctl status dsh-rag.service</code><br/>2. <code>journalctl -u dsh-rag.service -n 50</code>", td_style),
            Paragraph("Check for port 8000 collisions or missing environment keys in <code>.env</code>. Execute <code>sudo systemctl restart dsh-rag.service</code>.", td_style)
        ],
        [
            Paragraph("<b>Qdrant Vector DB Offline</b>", td_style),
            Paragraph("1. <code>curl -s http://127.0.0.1:6333/healthz</code><br/>2. <code>ps aux | grep qdrant</code>", td_style),
            Paragraph("Restart Qdrant service: <code>sudo systemctl restart qdrant.service</code>. Verify port 6333 responds on localhost.", td_style)
        ],
        [
            Paragraph("<b>Primary Groq LLM API Outage</b>", td_style),
            Paragraph("Inspect <code>logs/application.log</code> for provider timeout errors.", td_style),
            Paragraph("Automatic failover is built-in: system automatically diverts to secondary OpenAI <code>gpt-4o-mini</code>. No manual restart required.", td_style)
        ],
        [
            Paragraph("<b>Database Recovery from Snapshot</b>", td_style),
            Paragraph("Locate latest compressed snapshot in <code>/home/ubuntu/DSH-RAG/backups/</code>.", td_style),
            Paragraph(
                "1. Stop service: <code>sudo systemctl stop dsh-rag.service</code><br/>"
                "2. Restore SQLite: <code>gunzip -c backups/users_data_*.db.gz &gt; users_data.db</code><br/>"
                "3. Restore MySQL: <code>gunzip -c backups/rag_users_*.sql.gz | mysql -u rag_user -p rag_users</code><br/>"
                "4. Start service: <code>sudo systemctl start dsh-rag.service</code>",
                td_style
            )
        ],
    ]
    playbook_table = Table(playbook_data, colWidths=[1.6 * inch, 2.3 * inch, 3.3 * inch])
    playbook_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_navy),
        ('GRID', (0,0), (-1,-1), 0.5, c_border),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, c_bg_light]),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(playbook_table)
    story.append(Spacer(1, 10))

    # Sign-off box
    signoff_box = [
        [Paragraph("<b>OPERATIONAL SIGN-OFF & CONTACT INFORMATION</b><br/>"
                   "• Primary Maintainer: DSH Engineering & Operations Team<br/>"
                   "• Production Server Host: AWS EC2 18.118.138.91 (us-east-2)<br/>"
                   "• Public Health Check: https://agent.doctorsarahhensley.com/health<br/>"
                   "• Automated Backup Directory: /home/ubuntu/DSH-RAG/backups/ (14-day rolling retention)",
                   body_style)]
    ]
    signoff_table = Table(signoff_box, colWidths=[7.2 * inch])
    signoff_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#EFF6FF")),
        ('BOX', (0,0), (-1,-1), 0.5, c_blue),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(signoff_table)

    # Build document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Runbook PDF generated successfully at: {output_pdf_path}")


if __name__ == "__main__":
    out_name = "DSH_RAG_Production_Operations_Runbook.pdf"
    build_runbook_pdf(output_pdf_path=out_name)
    
    # Also copy to artifact directory
    artifact_dir = Path("C:/Users/Admin/.gemini/antigravity/brain/94458de4-605a-4cbb-b00a-6fa12f7a4c1d")
    if artifact_dir.exists():
        dest = artifact_dir / out_name
        shutil.copyfile(out_name, dest)
        print(f"Copied to artifact directory: {dest}")

