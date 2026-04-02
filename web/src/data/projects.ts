export type TeaserType = "SignalFlow" | "TextFlow" | "PolicyGrid" | "UrbanDots";

export interface Project {
  id: string;
  index: string;
  title: string;
  tagline: string;
  summary: string;
  recruiterNote: string;
  engineerNote: string;
  tags: string[];
  href: string;
  teaser: TeaserType;
  detail: {
    year: string;
    role: string;
    problem: string;
    approach: string;
    result: string;
  };
}

export const projects: Project[] = [
  {
    id: "ds-radar",
    index: "01",
    title: "ds-radar",
    tagline: "An agentic pipeline that hunts, evaluates, and applies to jobs.",
    summary:
      "Built a fully automated job search system that scans 5 ATS boards, scores 75+ roles across 10 dimensions using Claude Haiku, generates tailored CVs, and applies — end to end.",
    recruiterNote:
      "Built solo in 6 weeks · 75+ evaluations run · £0 spent on job platforms",
    engineerNote:
      "Playwright + Claude API · TSV state management · Sponsorship regex gate · 4-phase weekly pipeline",
    tags: ["python", "llm", "playwright", "agentic"],
    href: "/projects/ds-radar",
    teaser: "SignalFlow",
    detail: {
      year: "2024",
      role: "Solo engineer",
      problem:
        "Job searching is signal-poor and time-expensive. Most postings are noise. Manually evaluating dozens of roles per week against visa sponsorship requirements, domain fit, and seniority match is repetitive cognitive work that should be automated.",
      approach:
        "Built a 4-phase pipeline: Playwright crawlers scrape 5 ATS boards nightly, a sponsorship regex gate eliminates non-starters immediately, then Claude Haiku scores surviving roles on 10 dimensions (domain, stack, seniority, growth, culture, etc.), generating an A–F grade per role. High-grade roles trigger CV tailoring via LLM and automated application drafts. State is tracked in flat TSV files for portability.",
      result:
        "75+ roles evaluated in the first 6 weeks with zero manual ATS browsing. Pipeline runs in under 3 minutes. Identified and applied to 12 high-signal roles that would have been buried in manual search. Built entirely in Python with no paid job-search tooling.",
    },
  },
  {
    id: "un-speeches",
    index: "02",
    title: "UN Speeches",
    tagline: "Topic modeling 70 years of UN General Assembly debate.",
    summary:
      "NLP analysis of 8,000+ speeches from UN General Assembly sessions (1970–2020). Tracked how global priorities shifted across decades using LDA and BERTopic.",
    recruiterNote:
      "8,000+ speeches · 50 years of geopolitical trends · Published writeup",
    engineerNote:
      "BERTopic · LDA · HuggingFace · Python · Streamlit dashboard",
    tags: ["nlp", "bertopic", "python", "streamlit"],
    href: "/projects/un-speeches",
    teaser: "TextFlow",
    detail: {
      year: "2023",
      role: "Data scientist / researcher",
      problem:
        "The UN General Assembly Debate corpus is one of the richest longitudinal records of global political discourse — but it's 8,000+ unstructured documents spanning 50 years with no systematic topic indexing.",
      approach:
        "Applied both LDA (for interpretable topic extraction) and BERTopic (for semantic coherence) to the full corpus. Built a temporal analysis layer to track topic prevalence year-on-year, revealing macro-shifts — the rise of climate discourse post-1990, the Cold War's linguistic fingerprint, the emergence of 'terrorism' as a topic cluster post-2001. Visualized with a Streamlit dashboard.",
      result:
        "Clear evidence of 6 major thematic eras in the corpus. BERTopic outperformed LDA on coherence scores for this domain. Published a full writeup with interactive charts. Project sparked interest from a policy research team who adapted the methodology.",
    },
  },
  {
    id: "no-botes-tu-voto",
    index: "03",
    title: "No botes tu voto",
    tagline: "A policy alignment tool for the 2023 Spanish elections.",
    summary:
      "Interactive quiz that mapped voters to parties based on 20 policy questions. Scraped manifestos, built a similarity scoring model, served 12K users in election week.",
    recruiterNote:
      "12,000 users in election week · Media coverage · Zero ad spend",
    engineerNote:
      "Cosine similarity · Manifesto scraping · Streamlit · NLP preprocessing",
    tags: ["nlp", "python", "streamlit", "civic-tech"],
    href: "/projects/no-botes-tu-voto",
    teaser: "PolicyGrid",
    detail: {
      year: "2023",
      role: "Solo engineer + product designer",
      problem:
        "Spanish voters in the 2023 general election faced fragmented party landscape with 6+ viable parties. Manifestos run to hundreds of pages. Most voters make alignment decisions on incomplete information or tribal affiliation rather than actual policy positions.",
      approach:
        "Scraped and preprocessed electoral manifestos from 6 major parties. Extracted policy positions across 20 dimensions (economic policy, climate, housing, immigration, etc.) using NLP + manual curation. Built a 20-question quiz where user answers are vectorized and compared against party position vectors via cosine similarity. Deployed as a Streamlit app with results breakdown by policy area.",
      result:
        "12,000 users completed the quiz during election week. Shared organically on Spanish political Twitter and picked up by two digital media outlets. Zero ad spend. Several users reported the tool changed how they approached their vote decision.",
    },
  },
  {
    id: "london-bible",
    index: "04",
    title: "The London Bible",
    tagline: "A data-driven guide to London's 33 boroughs.",
    summary:
      "Aggregated 15+ open datasets (crime, transport, green space, cost of living) into a neighborhood comparison tool. Helps people make informed decisions about where to live.",
    recruiterNote:
      "15+ datasets · 33 boroughs · Open source · 300+ GitHub stars",
    engineerNote:
      "Pandas · ONS open data · Folium maps · Streamlit · GeoJSON",
    tags: ["geospatial", "open-data", "pandas", "streamlit"],
    href: "/projects/london-bible",
    teaser: "UrbanDots",
    detail: {
      year: "2023",
      role: "Solo engineer",
      problem:
        "Moving to London means making a housing decision with almost no comparable, structured information across boroughs. Crime stats, transport links, green space, school quality, and cost of living are all published as separate government datasets in incompatible formats.",
      approach:
        "Aggregated 15+ ONS and GLA open datasets into a unified borough-level dataframe. Built a scoring model across 8 livability dimensions, a Folium-based choropleth map, and a Streamlit interface for side-by-side borough comparison. GeoJSON boundaries for all 33 boroughs. Normalized all metrics to z-scores for fair comparison.",
      result:
        "300+ GitHub stars. Regularly referenced in London relocation forums. Used by a property consultancy to supplement client onboarding. Continues to get PRs from contributors adding new data sources.",
    },
  },
];
