from pprint import pprint

from scripts.evaluate import real_score


TEST_JDS = [
    {
        "url": "https://www.linkedin.com/jobs/view/deliveroo-ml-job-123",
        "title": "Machine Learning Engineer",
        "company": "Deliveroo",
        "location": "London, UK",
        "salary_visible": "Not listed",
        "description": """
Deliveroo is hiring a Machine Learning Engineer in London.

You will work on production machine learning systems, experimentation, recommendation models, and data-driven product features.
Requirements include Python, SQL, machine learning, stakeholder collaboration, and experience building or maintaining ML pipelines.
This is a product-focused technical role with strong learning opportunities and cross-functional collaboration.
Visa sponsorship may be available depending on candidate circumstances.
""",
    },
    {
        "url": "https://www.linkedin.com/jobs/view/version1-analytics-job-456",
        "title": "Analytics Consultant",
        "company": "Version 1",
        "location": "London, UK",
        "salary_visible": "Not listed",
        "description": """
Version 1 is hiring an Analytics Consultant in London.

The role focuses on analytics delivery, dashboarding, stakeholder engagement, KPI reporting, and business intelligence work for clients.
The stack includes SQL, Python, Power BI, and some modern analytics tooling.
This is a consulting environment with stable delivery work and some technical growth, but much of the day-to-day work is reporting and analytics rather than product ML.
Visa sponsorship is available for suitable candidates.
""",
    },
]


def main():
    for jd in TEST_JDS:
        print("=" * 80)
        print("URL:", jd["url"])
        try:
            result = real_score(jd)
        except Exception as e:
            print(f"[ERROR] {repr(e)}")
            print()
            continue

        pprint(result)
        print()

        grade = result.get("grade")
        score = result.get("overall_score") or result.get("score")
        summary = result.get("summary") or result.get("explanation") or ""

        print("Company:", jd["company"])
        print("Title:", jd["title"])
        print("Grade:", grade)
        print("Overall score:", score)
        print("Recommended:", result.get("recommended"))
        print("Summary (truncated):")
        print(summary[:800])
        print()


if __name__ == "__main__":
    main()
