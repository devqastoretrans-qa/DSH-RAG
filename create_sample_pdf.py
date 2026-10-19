import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet


def make_sample_pdf(output_path="documents/sample.pdf"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    title_style = styles["Title"]
    heading_style = styles["Heading2"]
    normal_style = styles["Normal"]

    # Title & Document Header
    story.append(Paragraph("Acme Corporation - Employee Handbook 2026", title_style))
    story.append(Spacer(1, 14))

    # Section 1: Working Hours & Remote Work
    story.append(Paragraph("Section 1: Work Hours and Remote Work Policy", heading_style))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Standard working hours at Acme Corporation are 9:00 AM to 5:00 PM local time, Monday through Friday. "
        "Employees are expected to log in promptly and remain reachable during core collaboration hours (10 AM - 4 PM). "
        "Remote work is permitted up to 3 days per week with prior manager approval. Full-time remote working arrangements "
        "require formal approval from the department head and HR representative.", normal_style
    ))
    story.append(Spacer(1, 16))

    # Section 2: Annual Leave & Paid Time Off
    story.append(Paragraph("Section 2: Annual Leave & Time Off Policy", heading_style))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "All full-time employees are entitled to 20 days of paid annual leave per calendar year. "
        "Leave requests must be submitted through the internal employee portal at least two weeks in advance. "
        "Employees may carry over up to 5 unused leave days into the subsequent calendar year, expiring on March 31st. "
        "Sick leave covers up to 10 paid days per year; medical certification is mandatory for consecutive absences exceeding 2 days.", normal_style
    ))
    story.append(Spacer(1, 16))

    # Section 3: Health Benefits & Wellness Stipend
    story.append(Paragraph("Section 3: Health Benefits & Wellness Stipend", heading_style))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Acme Corporation provides comprehensive medical, dental, and vision health insurance coverage for all full-time team members and their eligible dependents. "
        "In addition, every team member receives an annual wellness stipend of $500 intended for physical fitness subscriptions, ergonomic desk setups, "
        "or mental wellness resources.", normal_style
    ))
    story.append(Spacer(1, 16))

    # Section 4: Information Security & Data Protection
    story.append(Paragraph("Section 4: Data Protection & Information Security", heading_style))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "All company laptops must remain encrypted at rest. Password manager usage is mandatory for accessing internal systems. "
        "Multi-factor authentication (MFA) must be enabled on all company accounts. Employees are strictly prohibited from storing customer data "
        "or internal source code on unauthorized personal cloud storage accounts.", normal_style
    ))

    doc.build(story)
    print(f"Sample PDF successfully generated at {output_path}")


if __name__ == "__main__":
    make_sample_pdf()
