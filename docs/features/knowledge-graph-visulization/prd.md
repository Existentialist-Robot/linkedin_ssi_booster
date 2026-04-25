# Product Requirements Document: Knowledge Graph Visualization (Streamlit)

## 1. Executive Summary

This feature delivers an interactive, local-first knowledge graph visualization for the LinkedIn SSI Booster. Users can visually explore their persona, projects, and learned facts, identify strong/weak evidence areas, and discover new relationships in their knowledge base.

## 2. Project Context

- The system already maintains a rich NetworkX-based knowledge graph (persona, projects, facts, evidence).
- Users currently have no way to visually inspect or interact with this graph.
- Transparency, explainability, and engagement are core project values.
- Streamlit is chosen for its lightweight, pure-Python, interactive UI and local-first privacy. 

## 3. User Stories

- **As a user**, I want to launch a single command and see my knowledge graph in my browser, so I can understand how my persona, projects, and facts are connected.
- **As a user**, I want to click on nodes to see details (e.g., project, skill, evidence, uncertainty), so I can trace evidence and spot weak claims.
- **As a user**, I want to filter or highlight nodes by type, evidence strength, or uncertainty, so I can focus on areas that need improvement.
- **As a user**, I want to export the graph (image, JSON, GraphML), so I can share or analyze it elsewhere.

## 4. Functional Requirements

- [ ] Streamlit app renders the current knowledge graph (NetworkX) as an interactive graph.
- [ ] Nodes represent persona, projects, skills, facts, evidence.
- [ ] Edges represent relationships (persona→project, project→fact, fact→evidence, etc.).
- [ ] Node/edge coloring and sizing by type, evidence strength, or uncertainty.
- [ ] Node detail popups on click (showing all relevant attributes).
- [ ] Controls for filtering/highlighting by node type, evidence strength, uncertainty.
- [ ] Highlight “islands” (nodes with weak/no support or few connections).
- [ ] Export options: image (PNG/SVG), JSON, GraphML.
- [ ] CLI flag (`--graph-vis`) to launch the app from main.py or as a standalone script.
- [ ] Security: No private data leaks in UI or exports.

## 5. Non-Functional Requirements

- **Performance:** Graph loads and renders in under 2 seconds for graphs <2,000 nodes.
- **Usability:** One-command launch, intuitive UI, works in all major browsers.
- **Reliability:** Graceful fallback if graph is empty or missing data.
- **Maintainability:** Pure Python, minimal dependencies (Streamlit, NetworkX, PyVis/Plotly).
- **Security:** All data stays local; no uploads or external calls.

## 6. Project System Integration

- Uses existing KnowledgeGraphManager for data extraction.
- Streamlit app can be launched via CLI or as a standalone script.
- Optionally, integrate with main.py for seamless user experience.
- Exported graphs can be used for reporting, debugging, or sharing.

## 7. Dependencies

- Python 3.11+
- Streamlit
- NetworkX
- PyVis or Plotly (for rendering)

## 8. Success Metrics

- Users can launch the app and interact with their knowledge graph with a single command.
- Node/edge details, filtering, and highlighting work as described.
- Export features function correctly and securely.
- No private data is exposed in UI or exports.
- Feature is documented in README and usage guides.

## 9. Timeline & Milestones

- **Design & prototype:** 2 days
- **MVP implementation:** 2–3 days
- **Testing & polish:** 1 day
- **Docs & release:** 1 day

---

This PRD aligns with the project’s transparency, explainability, and local-first principles, and delivers a practical, user-friendly way to explore and validate the knowledge graph.
