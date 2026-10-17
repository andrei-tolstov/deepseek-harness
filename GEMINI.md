# GEMINI.md - DeepSeek Harness Project Guidelines


## Project Context
`deepseek-harness` is a local deployment and orchestration environment for local LLM inference and agent workflows. It coordinates Docker services including `deepseek-harness` (Cordis/web interface), `laya` (System 1 Decision Studio on GPU), `omniroute` (model proxy gateway), and `llama-server` (LLM inference engines).

---

## Knowledge Graph & Architecture Navigation (Graphify)

A persistent knowledge graph is generated and maintained in `graphify-out/` (`graphify-out/graph.json`, `graphify-out/GRAPH_REPORT.md`).

### Rules for Agents
1. **Query the Graph First**:
   - When asked architectural questions (e.g., "How does module X work?", "What calls function Y?", "Trace data flow from A to B"), **always query the knowledge graph first** before performing broad file system searches or reading dozens of files sequentially.
   - Use the native `graphify` MCP server tools:
     - `query_graph(question, mode="bfs"|"dfs", project_path=...)`: Semantic and structural context search across the graph.
     - `get_neighbors(node_id)` / `get_node(node_id)`: Inspect specific node dependencies, callers, and callees.
     - `god_nodes(project_path=...)`: Identify core hubs, architectural centers, and high-degree dependencies.
     - `shortest_path(source, target)`: Find direct and indirect dependency chains between components.
     - `graph_stats(project_path=...)`: Inspect graph health, node/edge counts, and communities.
   - Alternatively, invoke the `/graphify query "<question>"` skill.

2. **Impact Analysis Before Refactoring**:
   - Before renaming or altering signatures of core services, APIs, or shared utility functions, inspect their connections via `get_neighbors` to prevent regression.

3. **Graph Maintenance**:
   - A git post-commit hook is installed to incrementally update code AST relationships on commits.
   - For manual incremental updates or updating after document/config changes, run:
     ```bash
     graphify --update
     ```

---

