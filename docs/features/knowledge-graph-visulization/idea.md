# Feature Idea: Knowledge Graph Visualizations

## Overview

Enable users to visually explore their persona, projects, and learned facts as an interactive knowledge graph. This feature will provide intuitive, actionable insights into how their expertise, content, and learning are connected, and reveal areas of strong or weak evidence support.

The visualization UI will be implemented using **Streamlit**, providing a lightweight, interactive, and local-first web interface.

## Problem Statement (Project Context)

Currently, the knowledge graph is a powerful but hidden subsystem. Users cannot easily see how their persona, projects, and accumulated knowledge are interlinked, nor can they identify gaps, weakly supported claims, or new relationships. This limits transparency, explainability, and user engagement with the system’s intelligence.

## Proposed Solution

- Render the knowledge graph as an interactive visualization using Streamlit (web UI)
- Show nodes for persona, projects, skills, facts, and evidence
- Edges represent relationships (e.g., persona→project, project→fact, fact→evidence)
- Color/size nodes by type, evidence strength, or uncertainty
- Allow users to:
  - Click nodes to see details, evidence, and support paths
  - Filter by SSI component, topic, or evidence strength
  - Highlight “islands” (nodes with weak or no support)
  - Discover new or emerging relationships
- Support export (image, JSON, or GraphML)

## Expected Benefits (Project User Impact)

- Transparency: Users see exactly how their knowledge and content are structured
- Explainability: Easy to trace why a claim is strong/weak, and what evidence supports it
- Engagement: Encourages users to explore, validate, and grow their knowledge base
- Guidance: Reveals gaps, isolated nodes, and opportunities for new content or learning

## Technical Considerations (Project Integration)

- Use NetworkX for graph structure (already in use)
- For visualization:
  - **Explicitly use Streamlit** for the UI. Streamlit apps are pure Python, require no JS/HTML, and run locally for privacy. They support NetworkX, Plotly, and PyVis visualizations out of the box, and are easy to extend with filters and controls.
  - MVP: Streamlit app renders the NetworkX knowledge graph with interactive controls and node/edge details.
  - Only consider heavier web frameworks (Dash, React/D3) if multi-user or advanced features are required.
- Integrate with persona, project, and learning data (from KnowledgeGraphManager)
- Highlight uncertainty/weak support using node/edge attributes
- CLI flag to export or launch visualization (e.g., `--graph-vis`)
- Security: Ensure no private data is exposed in exports

## Project System Integration

- Leverage existing KnowledgeGraphManager for data extraction
- Visualization will be a standalone Streamlit web UI (optionally launched via CLI)
- Optionally integrate with the main CLI (main.py) for seamless user experience
- Exported graphs can be used for reporting, debugging, or sharing

## Initial Scope

- Export current knowledge graph to D3.js-compatible JSON
- Simple Streamlit web UI to render and interact with the graph
- Node/edge coloring by type and evidence strength
- Node detail popups (persona, project, fact, evidence)
- Highlight weakly supported or isolated nodes

## Success Criteria

- Users can view and interact with their knowledge graph
- Can identify strong/weak areas, isolated nodes, and evidence paths
- Streamlit app launches with a single command and runs locally (no server setup required)
- No private data leaks in exports or UI
- Feature is documented and discoverable via CLI/docs
- Export and visualization work for typical persona/project/fact graphs
- No private data leaks in exports
- Feature is documented and discoverable via CLI/docs
