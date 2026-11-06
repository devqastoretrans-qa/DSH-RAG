"""
RAG Document Preparation Guidelines PDF Generator (Calibrated 4-Page Standard)
"""
import os
from playwright.sync_api import sync_playwright

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>RAG Knowledge Base & Document Preparation Guidelines</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

  @page {
    size: A4;
    margin: 10mm 12mm 12mm 12mm;
    @bottom-right {
      content: "Page " counter(page) " of " counter(pages);
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 7.5pt;
      font-weight: 600;
      color: #64748b;
    }
    @bottom-left {
      content: "Doctor Sarah Hensley AI Ecosystem • Document Preparation & Handoff Standard v2.0";
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 7.5pt;
      color: #64748b;
    }
  }

  *, *::before, *::after {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }

  body {
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: #1e293b;
    background: #ffffff;
    font-size: 8.5pt;
    line-height: 1.42;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  .page-container {
    page-break-after: always;
    height: 272mm;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
  }
  .page-container:last-child {
    page-break-after: avoid;
  }

  /* Header Bar */
  .doc-header {
    border-bottom: 2px solid #0284c7;
    padding-bottom: 6px;
    margin-bottom: 10px;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
  }
  .doc-header-left h1 {
    font-size: 15.5pt;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: -0.4px;
    line-height: 1.15;
  }
  .doc-header-left .subtitle {
    font-size: 8.5pt;
    font-weight: 600;
    color: #0284c7;
    margin-top: 1px;
  }
  .doc-header-right {
    text-align: right;
    font-size: 7.5pt;
    color: #64748b;
    line-height: 1.3;
  }
  .doc-header-right strong {
    color: #0f172a;
  }

  /* Section Styling */
  .section {
    margin-bottom: 10px;
  }
  .section-title {
    font-size: 10pt;
    font-weight: 700;
    color: #0f172a;
    display: flex;
    align-items: center;
    gap: 5px;
    margin-bottom: 5px;
    padding-bottom: 2px;
    border-bottom: 1px solid #e2e8f0;
  }
  .section-number {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 17px;
    height: 17px;
    background: #0284c7;
    color: #ffffff;
    font-size: 7.5pt;
    font-weight: 800;
    border-radius: 3px;
  }

  p {
    margin-bottom: 5px;
    color: #334155;
    font-size: 8.3pt;
  }

  /* Callout Boxes */
  .callout {
    border-radius: 5px;
    padding: 6px 10px;
    margin-bottom: 8px;
    font-size: 8pt;
    line-height: 1.4;
    border-left: 3px solid;
  }
  .callout-info {
    background: #f0f9ff;
    border-color: #0284c7;
    color: #0369a1;
  }
  .callout-warning {
    background: #fffbeb;
    border-color: #d97706;
    color: #92400e;
  }
  .callout-critical {
    background: #fef2f2;
    border-color: #ef4444;
    color: #991b1b;
  }
  .callout strong {
    font-weight: 700;
  }

  /* Two Column Layout */
  .grid-2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-bottom: 8px;
  }

  .card {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 5px;
    padding: 7px 9px;
  }
  .card-title {
    font-size: 8.8pt;
    font-weight: 700;
    color: #0f172a;
    margin-bottom: 3px;
    display: flex;
    align-items: center;
    gap: 4px;
  }

  /* Badges */
  .badge {
    display: inline-block;
    padding: 1px 4.5px;
    border-radius: 3px;
    font-size: 6.8pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }
  .badge-success { background: #dcfce7; color: #15803d; }
  .badge-danger { background: #fee2e2; color: #b91c1c; }
  .badge-warning { background: #fef3c7; color: #b45309; }
  .badge-blue { background: #e0f2fe; color: #0369a1; }

  /* Tables */
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 7.6pt;
    margin-bottom: 8px;
  }
  th {
    background: #f1f5f9;
    color: #0f172a;
    font-weight: 700;
    text-align: left;
    padding: 4.5px 6.5px;
    border: 1px solid #cbd5e1;
    font-size: 7.4pt;
  }
  td {
    padding: 4px 6.5px;
    border: 1px solid #e2e8f0;
    color: #334155;
    vertical-align: top;
    line-height: 1.32;
  }
  tr:nth-child(even) td {
    background: #f8fafc;
  }

  /* Directory Tree Display */
  .dir-tree {
    background: #0f172a;
    color: #e2e8f0;
    padding: 7px 10px;
    border-radius: 4px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 7.2pt;
    line-height: 1.35;
    margin-bottom: 8px;
  }
  .dir-tree .folder { color: #38bdf8; font-weight: 600; }
  .dir-tree .file { color: #a5f3fc; }
  .dir-tree .comment { color: #94a3b8; font-style: italic; }

  /* Code / Monospace */
  code {
    font-family: 'JetBrains Mono', monospace;
    font-size: 7.2pt;
    background: #f1f5f9;
    padding: 1px 2.5px;
    border-radius: 2px;
    color: #0f172a;
  }

  /* Visual Compare Box */
  .compare-box {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-bottom: 8px;
  }
  .compare-item {
    border-radius: 5px;
    padding: 7px 8px;
    font-size: 7.5pt;
  }
  .compare-bad {
    background: #fff5f5;
    border: 1px solid #fecaca;
  }
  .compare-bad-title {
    color: #dc2626;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 3px;
    margin-bottom: 3px;
    font-size: 8pt;
  }
  .compare-good {
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
  }
  .compare-good-title {
    color: #16a34a;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 3px;
    margin-bottom: 3px;
    font-size: 8pt;
  }

  /* Flow Diagram */
  .flow-container {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 5px;
    padding: 6px 8px;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .flow-step {
    flex: 1;
    text-align: center;
    padding: 3px;
  }
  .flow-step-icon {
    font-size: 13pt;
    margin-bottom: 1px;
  }
  .flow-step-title {
    font-size: 7.4pt;
    font-weight: 700;
    color: #0f172a;
  }
  .flow-step-desc {
    font-size: 6.5pt;
    color: #64748b;
  }
  .flow-arrow {
    color: #0284c7;
    font-size: 11pt;
    font-weight: 800;
    padding: 0 3px;
  }

  /* Interaction Dialog Box */
  .dialog-box {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 5px;
    padding: 6px 9px;
    margin-bottom: 6px;
    font-size: 7.6pt;
  }
  .dialog-user {
    background: #f1f5f9;
    padding: 4px 7px;
    border-radius: 3px;
    margin-bottom: 4px;
    border-left: 2.5px solid #64748b;
  }
  .dialog-bot {
    background: #f0f9ff;
    padding: 4px 7px;
    border-radius: 3px;
    border-left: 2.5px solid #0284c7;
  }
  .dialog-label {
    font-size: 6.8pt;
    font-weight: 700;
    text-transform: uppercase;
    margin-bottom: 2px;
    display: block;
  }

  ul {
    margin-left: 12px;
    margin-bottom: 5px;
    font-size: 8pt;
    color: #334155;
  }
  li {
    margin-bottom: 2px;
  }
</style>
</head>
<body>

<!-- ================================= PAGE 1 ================================= -->
<div class="page-container">
  <div class="doc-header">
    <div class="doc-header-left">
      <h1>RAG Document Preparation Guidelines</h1>
      <div class="subtitle">Operational Standards for Knowledge Ingestion, Hygiene & Sales Handoff</div>
    </div>
    <div class="doc-header-right">
      <strong>Target System:</strong> Doctor Sarah Hensley AI<br>
      <strong>Version:</strong> 2.0 (Client Edition)<br>
      <strong>Date:</strong> November 2026 • Status: <span class="badge badge-success">Mandatory Standard</span>
    </div>
  </div>

  <div class="callout callout-info">
    <strong>Executive Purpose:</strong> This document outlines the required file preparation, folder structure, and document naming standards for Dr. Sarah Hensley's AI Knowledge Base. Adhering to these rules guarantees accurate therapeutic responses, prevents commercial sales leakage into clinical reflections, and enables the AI to guide clients to the correct masterclasses and direct purchase links.
  </div>

  <!-- SECTION 1 -->
  <div class="section">
    <div class="section-title"><span class="section-number">1</span> Dual-Bot Architecture: Why File Separation is Essential</div>
    <p>Our platform runs two isolated AI pipelines to safeguard client trust and guarantee professional boundaries:</p>
    
    <div class="grid-2">
      <div class="card" style="border-top: 3px solid #0284c7;">
        <div class="card-title">
          <span>🧠</span> Clinical Assistant Bot
          <span class="badge badge-blue">Non-Commercial</span>
        </div>
        <p><strong>Role:</strong> Provides relationship psychoeducation, emotional de-escalation, and guided reflection using Dr. Sarah's proprietary clinical protocols.</p>
        <p><strong>Strict Guardrail:</strong> It must <em>never</em> push courses or pitch pricing during emotional distress. It references therapeutic frameworks only.</p>
      </div>

      <div class="card" style="border-top: 3px solid #16a34a;">
        <div class="card-title">
          <span>🎯</span> Sales & Program Advisor Bot
          <span class="badge badge-success">Consultative Sales</span>
        </div>
        <p><strong>Role:</strong> Analyzes the client's relationship pain points, explains course syllabi, and recommends specific masterclasses, books, or coaching.</p>
        <p><strong>Strict Guardrail:</strong> Recommends offerings with <em>direct checkout links</em>. Never uses pushy, aggressive, or high-pressure tactics.</p>
      </div>
    </div>

    <div class="callout callout-critical">
      <strong>Risk of Mixed Documents:</strong> If sales brochures are placed in clinical folders, the Clinical Bot will attempt to sell courses to clients seeking crisis support. Conversely, if clinical exercises are placed in sales folders, the Sales Advisor loses focus and fails to present direct purchase links.
    </div>
  </div>

  <!-- SECTION 2 -->
  <div class="section">
    <div class="section-title"><span class="section-number">2</span> Mandatory Google Drive Folder Structure</div>
    <p>All files synced to the AI must reside in two designated, mutually exclusive directories in Google Drive:</p>

    <div class="dir-tree">
<span class="folder">📁 Google Drive Sync Root/</span>
├── <span class="folder">📁 1. Sales & Course Catalog/</span> <span class="comment">──► [Qdrant Collection: 'documents']</span>
│   ├── <span class="file">Sales_Catalog_Masterclasses_and_Bundles.pdf</span>
│   ├── <span class="file">Pricing_and_Coaching_Packages_Directory.pdf</span>
│   └── <span class="file">Course_Enrollment_FAQs_and_Refund_Policy.pdf</span>
│
└── <span class="folder">📁 2. Clinical Knowledge Base/</span> <span class="comment">──► [Strict Clinical Subfolder Routing]</span>
    ├── <span class="folder">📁 Tools/</span>        <span class="comment">(Step-by-step psychological exercises: SOLACE, DARE SOFT, Fast Down Shift)</span>
    ├── <span class="folder">📁 Journals/</span>     <span class="comment">(Structured worksheets: Relationship Vision, Personal Needs, Daily Logs)</span>
    ├── <span class="folder">📁 Reflections/</span>  <span class="comment">(Post-conflict reviews, repair logs, trigger analysis)</span>
    └── <span class="folder">📁 Other/</span>        <span class="comment">(Attachment theory whitepapers, research, foundational guides)</span>
    </div>

    <table>
      <thead>
        <tr>
          <th style="width: 28%;">Folder Location</th>
          <th style="width: 18%;">Target AI Bot</th>
          <th style="width: 54%;">Approved Content & Document Scope</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>Sales & Course Catalog</strong></td>
          <td><span class="badge badge-success">Sales Bot</span></td>
          <td>Masterclass syllabi, coaching package tiers, pricing guides, direct checkout URLs, program duration, enrollment FAQs, book overviews.</td>
        </tr>
        <tr>
          <td><strong>Clinical Knowledge &gt; Tools</strong></td>
          <td><span class="badge badge-blue">Clinical Bot</span></td>
          <td>Actionable somatic & psychological protocols (e.g., SOLACE™, DARE SOFT, Boundary Ladder, Fast Down Shift, Repair Scripts).</td>
        </tr>
        <tr>
          <td><strong>Clinical Knowledge &gt; Journals</strong></td>
          <td><span class="badge badge-blue">Clinical Bot</span></td>
          <td>Fillable prompt sheets, Relationship Vision blueprints, Personal & Attachment Needs inventory questions.</td>
        </tr>
        <tr>
          <td><strong>Clinical Knowledge &gt; Reflections</strong></td>
          <td><span class="badge badge-blue">Clinical Bot</span></td>
          <td>Post-argument reflection steps, trigger reaction logs, 1-1-1 Reflection Protocol guides.</td>
        </tr>
        <tr>
          <td><strong>Clinical Knowledge &gt; Other</strong></td>
          <td><span class="badge badge-blue">Clinical Bot</span></td>
          <td>General psychoeducational essays, attachment style definitions (Anxious, Avoidant, Disorganized, Secure).</td>
        </tr>
      </tbody>
    </table>
  </div>
</div>

<!-- ================================= PAGE 2 ================================= -->
<div class="page-container">
  <div class="doc-header">
    <div class="doc-header-left">
      <h1>RAG Document Preparation Guidelines</h1>
      <div class="subtitle">Section 3: Issue-to-Purchase-Link Mapping Matrix (Clinical Handoff)</div>
    </div>
    <div class="doc-header-right">
      <strong>Target System:</strong> Doctor Sarah Hensley AI<br>
      <strong>Version:</strong> 2.0 (Client Edition)<br>
      <strong>Date:</strong> November 2026
    </div>
  </div>

  <!-- SECTION 3 -->
  <div class="section">
    <div class="section-title"><span class="section-number">3</span> The Issue-to-Purchase-Link Mapping Requirement</div>
    <p>To enable the AI to analyze a client's clinical struggle and guide them to the exact right course or coaching option, the content team <strong>must provide a Master Offering Reference Table</strong> in the Sales folder. This allows the bot to map clinical pain points directly to the active checkout URL.</p>

    <!-- Workflow diagram -->
    <div class="flow-container">
      <div class="flow-step">
        <div class="flow-step-icon">💬</div>
        <div class="flow-step-title">1. Client Shares Struggle</div>
        <div class="flow-step-desc">"I panic when he takes hours to text back and I send 10 messages."</div>
      </div>
      <div class="flow-arrow">➔</div>
      <div class="flow-step">
        <div class="flow-step-icon">🔬</div>
        <div class="flow-step-title">2. Bot Analyzes Dynamics</div>
        <div class="flow-step-desc">Identifies: Anxious Attachment, Abandonment Fear, Protest Behavior.</div>
      </div>
      <div class="flow-arrow">➔</div>
      <div class="flow-step">
        <div class="flow-step-icon">🗺️</div>
        <div class="flow-step-title">3. Matrix Lookup</div>
        <div class="flow-step-desc">Matches identified symptoms to the authoritative course catalog.</div>
      </div>
      <div class="flow-arrow">➔</div>
      <div class="flow-step">
        <div class="flow-step-icon">💳</div>
        <div class="flow-step-title">4. Direct Purchase Card</div>
        <div class="flow-step-desc">Provides course overview + <strong>Direct Checkout URL</strong>.</div>
      </div>
    </div>

    <p style="font-weight: 600; color: #0f172a; margin-bottom: 3px;">Mandatory Master Offering Table Format (Must be included in Sales Catalog file):</p>
    <table>
      <thead>
        <tr>
          <th style="width: 22%;">Program / Offering Name</th>
          <th style="width: 25%;">Direct Checkout URL</th>
          <th style="width: 33%;">Target Clinical Issues & Pain Points</th>
          <th style="width: 8%;">Price</th>
          <th style="width: 12%;">Format</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>Healing Anxious Attachment Masterclass</strong></td>
          <td><code>.../checkout/anxious-attachment</code></td>
          <td>Fear of abandonment, relationship anxiety, overthinking, obsessive texting, protest behaviors, hypervigilance, needing constant reassurance.</td>
          <td><strong>$97</strong></td>
          <td>Self-Paced Video (4 Modules)</td>
        </tr>
        <tr>
          <td><strong>Deactivating Avoidant: Deep Dive Workshop</strong></td>
          <td><code>.../checkout/avoidant-deep-dive</code></td>
          <td>Emotional shutdown, stonewalling, feeling smothered or trapped, withdrawing during conflict, phantom ex syndrome, hyper-independence.</td>
          <td><strong>$97</strong></td>
          <td>Workshop & Reflection PDFs</td>
        </tr>
        <tr>
          <td><strong>The Boundary Ladder & Conflict Repair Protocol</strong></td>
          <td><code>.../checkout/boundary-ladder</code></td>
          <td>Circular fighting, inability to say no, people-pleasing, resentments, post-fight repair breakdown, boundary violations.</td>
          <td><strong>$67</strong></td>
          <td>Audio Guide + PDF Framework</td>
        </tr>
        <tr>
          <td><strong>The Secure Relationship Complete Bundle</strong></td>
          <td><code>.../checkout/secure-bundle</code></td>
          <td>Mixed anxious-avoidant couples, recurring toxic communication cycles, partners seeking joint healing, all masterclasses included.</td>
          <td><strong>$197</strong></td>
          <td>Complete Digital Curriculum</td>
        </tr>
        <tr>
          <td><strong>Private 1-on-1 SOLACE™ Consultation</strong></td>
          <td><code>.../checkout/private-consultation</code></td>
          <td>Infidelity crisis, immediate breakup crossroads, complex relational trauma, personalized roadmap directly with Dr. Sarah.</td>
          <td><strong>$250</strong></td>
          <td>55-Minute Video Session</td>
        </tr>
        <tr>
          <td><strong>The Science of Attachment: Guide & Workbook</strong></td>
          <td><code>.../checkout/attachment-workbook</code></td>
          <td>Self-study learners, structured journaling habit, guided diagnostic checklists, budget-conscious individuals.</td>
          <td><strong>$29</strong></td>
          <td>Downloadable 120-Page PDF</td>
        </tr>
      </tbody>
    </table>

    <!-- Real Bot Interaction Demonstration -->
    <div class="dialog-box">
      <div style="font-weight: 700; color: #0f172a; margin-bottom: 3px;">Example: How the Bot Uses This Matrix in Live Chat</div>
      <div class="dialog-user">
        <span class="dialog-label" style="color: #475569;">User Query:</span>
        <em>"Every time my boyfriend asks for a weekend to himself, I get a knot in my stomach and obsessively check his social media. I feel like he's falling out of love with me."</em>
      </div>
      <div class="dialog-bot">
        <span class="dialog-label" style="color: #0284c7;">Bot Clinical Analysis & Next Step Recommendation:</span>
        What you are experiencing is a classic <strong>anxious attachment activation</strong> triggered by emotional space. When your partner requests solitude, your nervous system perceives separation as abandonment, triggering protest behavior (monitoring his social media).<br><br>
        <strong>### Recommended Next Step for Your Journey</strong><br>
        To break this cycle and develop internal soothing, Dr. Sarah Hensley's <strong>Healing Anxious Attachment Masterclass ($97)</strong> provides step-by-step cognitive and somatic frameworks to stop protest behaviors and regain your peace. <a href="https://doctorsarahhensley.com/checkout/anxious-attachment" style="color: #0284c7; font-weight: 700;">[Click here to explore details and enroll]</a>.
      </div>
    </div>
  </div>
</div>

<!-- ================================= PAGE 3 ================================= -->
<div class="page-container">
  <div class="doc-header">
    <div class="doc-header-left">
      <h1>RAG Document Preparation Guidelines</h1>
      <div class="subtitle">Sections 4 & 5: Document Formats & Naming Standards</div>
    </div>
    <div class="doc-header-right">
      <strong>Target System:</strong> Doctor Sarah Hensley AI<br>
      <strong>Version:</strong> 2.0 (Client Edition)<br>
      <strong>Date:</strong> November 2026
    </div>
  </div>

  <!-- SECTION 4 -->
  <div class="section">
    <div class="section-title"><span class="section-number">4</span> Document Format & Technical Hygiene Standards</div>
    <p>The automated ingestion worker continuously monitors Google Drive. The file formats below are strictly regulated:</p>

    <table>
      <thead>
        <tr>
          <th style="width: 20%;">Format / Feature</th>
          <th style="width: 15%;">Status</th>
          <th style="width: 65%;">Technical Requirement & Client Action</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>Modern PDF (<code>.pdf</code>)</strong></td>
          <td><span class="badge badge-success">Accepted</span></td>
          <td>Text must be <strong>searchable and selectable</strong>. Generated via "Save As PDF" or "Export as PDF" from Word/Google Docs.</td>
        </tr>
        <tr>
          <td><strong>Modern Word (<code>.docx</code>)</strong></td>
          <td><span class="badge badge-success">Accepted</span></td>
          <td>Native Microsoft Word or Google Docs exports with standard typography heading styles applied.</td>
        </tr>
        <tr>
          <td><strong>Legacy Word (<code>.doc</code>)</strong></td>
          <td><span class="badge badge-danger">Strictly Banned</span></td>
          <td>Pre-2007 binary format causes Python parser crashes (<code>PackageNotFoundError</code>). Convert to <code>.docx</code> or <code>.pdf</code> before uploading.</td>
        </tr>
        <tr>
          <td><strong>Scanned Image PDFs</strong></td>
          <td><span class="badge badge-danger">Strictly Banned</span></td>
          <td>Scanned paper documents contain no digital text layer and result in empty AI chunks. All documents must be natively digital.</td>
        </tr>
        <tr>
          <td><strong>Duplicate Download Tags</strong></td>
          <td><span class="badge badge-danger">Strictly Banned</span></td>
          <td>Files named with browser suffixes like <code>(1).pdf</code> or stacked extensions <code>.docx.pdf</code> must be cleaned before upload.</td>
        </tr>
        <tr>
          <td><strong>Superseded Drafts</strong></td>
          <td><span class="badge badge-warning">Archive Only</span></td>
          <td>Never leave multiple revisions (e.g. <code>v1</code>, <code>v2_final</code>) in the active folder. Overwrite or archive older drafts to prevent conflicting AI answers.</td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- SECTION 5 -->
  <div class="section">
    <div class="section-title"><span class="section-number">5</span> Standardized Document Naming Conventions</div>
    <p>Identical or vague titles (e.g., <em>"Worksheet.pdf"</em>) destroy retrieval precision. Every document must follow the standard naming syntax: <code>[Category]_[Specific_Tool_or_Topic]_[Official_Title].pdf</code></p>

    <div class="compare-box">
      <div class="compare-item compare-bad">
        <div class="compare-bad-title">❌ Rejected File Names (Causes System Errors)</div>
        <ul>
          <li><code>Worksheet.pdf</code> <span class="comment">(Too generic; vector collision)</span></li>
          <li><code>Attachment Needs FAQ V1.docx (2).pdf</code> <span class="comment">(Stacked extensions)</span></li>
          <li><code>1-1-1 Reflection Protocol (1).pdf</code> <span class="comment">(Download duplicate)</span></li>
          <li><code>Course Info.pdf</code> <span class="comment">(Lacks pricing and topic scope)</span></li>
          <li><code>SOLACE draft final copy.docx</code> <span class="comment">(Ambiguous versioning)</span></li>
          <li><code>Journal.pdf</code> <span class="comment">(No functional topic specified)</span></li>
        </ul>
      </div>

      <div class="compare-item compare-good">
        <div class="compare-good-title">✅ Approved File Names (Guarantees 100% Precision)</div>
        <ul>
          <li><code>Tool_SOLACE_Protocol_Master_Guide.pdf</code></li>
          <li><code>Journal_Personal_and_Attachment_Needs.pdf</code></li>
          <li><code>Tool_1-1-1_Conflict_Reflection_Protocol.pdf</code></li>
          <li><code>Sales_Catalog_Masterclasses_and_Bundles_2024.pdf</code></li>
          <li><code>Reflection_Post_Argument_Trigger_Log.pdf</code></li>
          <li><code>Journal_Relationship_Vision_Blueprint.pdf</code></li>
        </ul>
      </div>
    </div>

    <div class="callout callout-warning">
      <strong>Rule on Revisions:</strong> When updating a document, maintain the <em>exact same file name</em> and replace the file in Google Drive. This automatically updates existing vector embeddings without creating duplicate entries or broken citations.
    </div>
  </div>
</div>

<!-- ================================= PAGE 4 ================================= -->
<div class="page-container">
  <div class="doc-header">
    <div class="doc-header-left">
      <h1>RAG Document Preparation Guidelines</h1>
      <div class="subtitle">Sections 6, 7 & 8: In-Document Structure & Pre-Upload Checklist</div>
    </div>
    <div class="doc-header-right">
      <strong>Target System:</strong> Doctor Sarah Hensley AI<br>
      <strong>Version:</strong> 2.0 (Client Edition)<br>
      <strong>Date:</strong> November 2026
    </div>
  </div>

  <!-- SECTION 6 -->
  <div class="section">
    <div class="section-title"><span class="section-number">6</span> In-Document Structure & Writing for Chunking</div>
    <p>The RAG system divides documents into ~500-word segments ("chunks"). Structured headers allow the system to map user queries directly to specific protocol steps.</p>

    <div class="compare-box">
      <div class="compare-item compare-bad">
        <div class="compare-bad-title">❌ Poor Document Layout (Chunks Lose Context)</div>
        <div style="background: #ffffff; padding: 5px; border: 1px solid #cbd5e1; border-radius: 4px; font-size: 7.2pt; color: #64748b; line-height: 1.35;">
          <strong>Attachment Guide</strong><br>
          Step 1: Notice your body. When you feel anxious take a deep breath. Next you should pause before calling. Step 2: Write down what you feel. You can use our journal. Next step is to talk to your partner using the script...
          <div style="color: #dc2626; margin-top: 3px; font-weight: 600;">Issue: No headings. Chunks become meaningless excerpts labeled "Attachment Guide Chunk 2".</div>
        </div>
      </div>

      <div class="compare-item compare-good">
        <div class="compare-good-title">✅ Optimized Document Layout (Perfect RAG Citations)</div>
        <div style="background: #ffffff; padding: 5px; border: 1px solid #cbd5e1; border-radius: 4px; font-size: 7.2pt; color: #1e293b; line-height: 1.35;">
          <strong style="color: #0f172a; font-size: 7.6pt;"># SOLACE™ Protocol: Somatic De-Escalation Guide</strong><br>
          <strong style="color: #0284c7;">## Step 1: Stop and Regulate Somatic Arousal</strong><br>
          Place one hand on your heart and one on your abdomen. Practice 4-7-8 physiological sigh breathing.<br>
          <strong style="color: #0284c7;">## Step 2: Observe Emotional Triggers</strong><br>
          Identify whether this is an Anxious protest panic or an Avoidant deactivation urge...
          <div style="color: #16a34a; margin-top: 3px; font-weight: 600;">Result: Chunks preserve exact step numbers and protocol names.</div>
        </div>
      </div>
    </div>

    <ul>
      <li><strong>H1 Document Title:</strong> Begin every file on Page 1 with a prominent Title styled as Heading 1 (e.g. <code># SOLACE™ Protocol</code>).</li>
      <li><strong>Descriptive H2 Subheadings:</strong> Use explicit subheadings including the tool name (e.g., use <code>## SOLACE Protocol — Step 2: Observe</code> rather than generic <code>## Step 2</code>).</li>
      <li><strong>Single Topic Containment:</strong> Keep each distinct tool, exercise, or protocol in its own standalone document. Avoid combining 5 different exercises into a single 50-page PDF.</li>
    </ul>
  </div>

  <!-- SECTION 7 -->
  <div class="section">
    <div class="section-title"><span class="section-number">7</span> Content Team Pre-Upload Verification Checklist</div>
    <div class="card" style="background: #f0fdf4; border: 1px solid #86efac; padding: 7px 9px;">
      <ul style="margin-left: 15px; margin-bottom: 0;">
        <li><strong>[ ] Folder Separation Verified:</strong> File is strictly placed in <code>Sales & Course Catalog</code> OR one of the 4 <code>Clinical Knowledge</code> subfolders (<code>Tools/</code>, <code>Journals/</code>, <code>Reflections/</code>, <code>Other/</code>).</li>
        <li><strong>[ ] Direct Purchase Link Included:</strong> If a sales or course document, it includes the exact checkout URL (not just homepage).</li>
        <li><strong>[ ] Clinical Pain Points Defined:</strong> Course listings clearly state the emotional struggles and attachment issues they solve.</li>
        <li><strong>[ ] Standardized Naming Convention:</strong> File is named with category prefix (e.g. <code>Tool_SOLACE_Guide.pdf</code>) with all <code>(1)</code> or <code>.docx.pdf</code> stripped.</li>
        <li><strong>[ ] Searchable Digital Format:</strong> File is an exported modern <code>.pdf</code> or <code>.docx</code> with selectable text (no scanned images or <code>.doc</code> files).</li>
        <li><strong>[ ] Structured Headings Applied:</strong> Page 1 has an H1 Title, and major sections use descriptive H2/H3 headings.</li>
        <li><strong>[ ] Single Master Copy Maintained:</strong> Old revisions and draft copies have been removed or archived from Google Drive.</li>
      </ul>
    </div>
  </div>

  <!-- SECTION 8 -->
  <div class="section" style="margin-top: 5px;">
    <div class="section-title"><span class="section-number">8</span> Technical Support & Sign-Off</div>
    <p style="font-size: 7.6pt; color: #64748b; line-height: 1.35;">
      For questions regarding document formatting, folder permissions, or automated indexing verification, please reach out to the <strong>Engineering Team</strong>. After updating your Google Drive folders, notify the technical team to trigger a clean vector re-indexing run across the production cluster.
    </p>
  </div>
</div>

</body>
</html>
"""

def generate_pdf():
    out_dir = r"c:\Users\Admin\Downloads"
    target_pdf = os.path.join(out_dir, "RAG Document Preparation Guidelines.pdf")
    optimized_pdf = os.path.join(out_dir, "RAG_Document_Preparation_Guidelines_Optimized.pdf")
    html_file = os.path.join(out_dir, "rag_guidelines_temp.html")

    print(f"Writing calibrated HTML to: {html_file}")
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(HTML_CONTENT)

    print("Launching Playwright Chromium...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"file:///{html_file.replace(os.sep, '/')}", wait_until="networkidle")

        print(f"Rendering PDF to: {target_pdf}")
        page.pdf(
            path=target_pdf,
            format="A4",
            print_background=True,
            margin={"top": "0mm", "bottom": "0mm", "left": "0mm", "right": "0mm"}
        )

        print(f"Rendering copy to: {optimized_pdf}")
        page.pdf(
            path=optimized_pdf,
            format="A4",
            print_background=True,
            margin={"top": "0mm", "bottom": "0mm", "left": "0mm", "right": "0mm"}
        )
        browser.close()

    print("PDF generation complete successfully!")

if __name__ == "__main__":
    generate_pdf()
