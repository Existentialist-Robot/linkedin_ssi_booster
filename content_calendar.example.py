"""
Content Calendar — EXAMPLE FILE
================================
Copy this file to content_calendar.py and replace the placeholder values
with your own topics, angles, and hashtags.

    cp content_calendar.example.py content_calendar.py

content_calendar.py is gitignored so your personal posting strategy
stays off the public repository.

SSI components:
  establish_brand       — Share builds, lessons, technical depth
  find_right_people     — Tools, communities, questions that attract audience
  engage_with_insights  — React to news/trends with a bold take
  build_relationships   — Behind-the-scenes stories, honest lessons
"""

CONTENT_CALENDAR = {
    "week_1": [
        {
            "title": "[YOUR PROJECT NAME]: [one-line description]",
            "angle": "Showcase: What you built, why it matters, and what others can learn from it.",
            "ssi_component": "establish_brand",
            "hashtags": ["YourTech", "OpenSource", "Python", "AI"]
        },
        {
            "title": "What I learned from [early-career technology or project]",
            "angle": "Retrospective: Hard-won lessons from [technology] that still apply today.",
            "ssi_component": "engage_with_insights",
            "hashtags": ["CareerLessons", "SoftwareEngineering", "TechHistory"]
        },
        {
            "title": "How [past experience] prepared me for [current challenge]",
            "angle": "The problems I debugged at [previous role] are exactly the problems [current domain] faces now.",
            "ssi_component": "build_relationships",
            "hashtags": ["CareerGrowth", "SoftwareDevelopment", "AIEngineering"]
        }
    ],
    "week_2": [
        {
            "title": "How we [achieved outcome] at [project or event]",
            "angle": "Story-driven: the approach, the pivots, the result.",
            "ssi_component": "build_relationships",
            "hashtags": ["Hackathon", "ProjectStory", "Engineering"]
        },
        {
            "title": "What is [concept] and why [your audience] needs to understand it",
            "angle": "Educational: explain [concept] vs [common misconception] for high-stakes use cases.",
            "ssi_component": "engage_with_insights",
            "hashtags": ["Education", "AI", "SoftwareArchitecture"]
        },
        {
            "title": "[Approach A] vs [Approach B] — why the hybrid beats the pure play",
            "angle": "Technical: benchmark or real-world example showing trade-offs.",
            "ssi_component": "establish_brand",
            "hashtags": ["TechComparison", "Engineering", "BestPractices"]
        }
    ],
    "week_3": [
        {
            "title": "How I built [project]: [key technical challenge]",
            "angle": "Behind the build: architecture decisions, mistakes, lessons.",
            "ssi_component": "establish_brand",
            "hashtags": ["BuildInPublic", "ProjectShowcase", "AI"]
        },
        {
            "title": "[Tool or protocol] is changing how we [do X] — here's what to know",
            "angle": "Timely take: new tooling + your hands-on perspective.",
            "ssi_component": "find_right_people",
            "hashtags": ["NewTool", "AIEngineering", "OpenSource"]
        },
        {
            "title": "What [domain problem] taught me about [engineering principle]",
            "angle": "Cross-domain insight: real production experience → generalizable lesson.",
            "ssi_component": "engage_with_insights",
            "hashtags": ["EngineeringLessons", "SoftwareDevelopment", "AI"]
        }
    ],
    "week_4": [
        {
            "title": "[X] years of [technology] → now applying it to [new domain]",
            "angle": "Career arc: deep expertise in the old domain is a superpower in the new one.",
            "ssi_component": "build_relationships",
            "hashtags": ["CareerTransition", "AI", "SoftwareEngineering"]
        },
        {
            "title": "Multi-agent vs single-agent: when the complexity is worth it",
            "angle": "Architectural opinion: most problems don't need multi-agent; here's when they do.",
            "ssi_component": "engage_with_insights",
            "hashtags": ["MultiAgent", "AIArchitecture", "LLM", "Engineering"]
        },
        {
            "title": "Context engineering: the skill nobody talks about",
            "angle": "Hot take: prompt engineering is table stakes; context engineering is the moat.",
            "ssi_component": "establish_brand",
            "hashtags": ["ContextEngineering", "PromptEngineering", "LLM", "AI"]
        }
    ],
}
