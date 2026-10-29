# Real LLM calls use the OpenAI Chat Completions API through a user-supplied base URL

The demo must run against a real model, not a fake. The user supplies a base URL and API key; we use langchain-openai's ChatOpenAI pointed at that base_url with the Chat Completions chat model (not the Responses API), created through init_chat_model or ChatOpenAI directly. Because a custom base URL targets the official OpenAI spec, non-standard provider fields are not relied upon.
