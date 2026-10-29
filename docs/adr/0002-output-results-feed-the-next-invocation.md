# Output module results flow into the next invocation

Output modules dispatch fire-and-forget, but each dispatch returns an immediate output result (success/failure or textual detail), and that result becomes part of the state of the next invocation. This makes the system a closed feedback loop rather than a one-shot pipeline: a failed delivery or a module's textual reply is visible to the Agent on the next input, so the Agent can respond to its own outputs' outcomes in later turns.
