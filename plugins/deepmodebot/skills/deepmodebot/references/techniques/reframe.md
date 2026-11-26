# reframe

**Use when:** `/reframe`, "what is this called", "expert words for what I'm building", or when an operator describes a system in plain words and needs precise domain vocabulary, neighboring-field analogies, unmentioned failure modes, and a rewritten specification.

1. Read the operator's own files, code, and description directly instead of working from a summary.
2. Disambiguate ambiguous descriptions first: when the description could name 2 or 3 distinct problems, list those 2 or 3 candidate problems, each with the single term that names it and the observable sign that tells it apart from the others; then pick the most likely problem and state why.
3. Give 8 to 12 expert terms, ranked by how much each changes what gets built. For every term, state:
   - the word and its meaning in one plain sentence;
   - the exact part of the operator's description or code it names;
   - one real project, paper, or shipped system that uses the term that way, with a link you opened and confirmed;
   - what naming that term lets the operator ask an agent to build or enforce.
4. Pick 2 or 3 neighboring fields that solved the same shape of problem under different names. For each field, state what transfers directly, where the analogy breaks down, and which terms carry back.
5. Name what the operator did not mention but should care about (invariants, edge boundaries, operational failure modes, or hidden state).
6. Rewrite the operator's description cleanly using the verified expert words.

**Hard rules.** Open every link (via web fetch/search or local repo docs) and confirm it uses the term that way; cut any citation you cannot confirm. Zero padding; pass prose through **unslop**.

**Done when** multi-meaning descriptions are disambiguated, 8–12 ranked terms each carry a confirmed link and concrete agent ask, 2–3 neighboring analogies state both transfer and breakdown limits, omitted concerns are named, and the description is rewritten in those terms.
