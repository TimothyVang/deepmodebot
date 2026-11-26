## 7. Copy
- Write from the user's side, in the user's terms ("notifications", not "webhook config").
- Sentence case, active voice, plain verbs, no filler.
- A CTA names its result ("Save changes", not "Submit"). The name stays consistent through the flow ("Publish" produces the toast "Published").
- Destructive actions use Verb + Noun and never "OK" or "Confirm". A dialog's title and its primary button share the verb ("Delete project?" → "Delete project"). Explain what deletion does *before* the confirm. Offer undo when it can honestly be supported.
- Errors say what happened and how to fix it; they don't apologize and aren't vague. Upload errors are specific ("The file must be smaller than 2 MB").
- Empty states invite the next action. There are three kinds: nothing yet (educate), no results (adjust the query), failed to load (plain, no jokes).
- **Accessible names:** distinguishing word first (usually a verb), 1–3 words, never the role word, no trailing period. A switch's label never changes with its state.
- **Hedging tracks real reliability** ("is" vs "may"). No human persona framing for the agent: no "think", "understand" or "feel" in system copy, and no "Great question!". AI labels are verb-first and user-initiated ("Summarize with agent"); disclosure labels name the action ("Rewritten by agent"); attributions say "Because you…".
- In-progress labels end with `…` ("Saving…").
