I'm integrating with a LangServe `/invoke` endpoint (a LangChain Runnable served
over HTTP, Bedrock/Claude underneath). I need its exact wire format so I can
configure a client adapter. You have access to the LangChain client code that
calls this endpoint, and the endpoint URL is:

    {PASTE_GATEWAY_URL_HERE}

Do BOTH of these:

1. Read the client/chain code I've given you and infer how the Runnable is built
   and invoked (is it a bare chat model, `model.bind_tools(...)`, a custom chain
   taking a dict, `configurable_fields`/`configurable_alternatives`, etc.).

2. Produce ready-to-run `curl` commands (and run them if you have a tool that
   can) for:
     - GET  {URL}/input_schema
     - GET  {URL}/output_schema
     - POST {URL}/invoke   with a minimal 1-message input AND one tool defined,
       so I can see a real request body and a real response (a tool call if the
       model decides to use it).
   Include the exact auth header the client uses (redact the token value).

Then answer EVERY question below in this exact template. Paste raw JSON for the
schemas and the sample request/response (redact secrets). If something can't be
determined, say "unknown" — don't guess.

=== REQUEST (POST /invoke body) ===
R1. Top-level keys present (input / config / kwargs / other)?
R2. Is `input` a JSON object, a JSON array (list of messages), or a string?
R3. If object: which key holds the conversation/messages?
R4. How are tools passed per call? Pick one and give the exact key path:
    (a) inside `input` under key: ____
    (b) inside `config.configurable` under key: ____
    (c) bound server-side / NOT accepted per call (tools are fixed)
    (d) other: ____
R5. Tool schema format the endpoint expects:
    OpenAI function dict {"type":"function","function":{name,description,parameters}}
    / raw JSON Schema / Anthropic {"name","input_schema"} / other (show one tool as JSON)
R6. Per-turn message format — show one user, one assistant-with-tool-call, and one
    tool-result message as the endpoint expects them. Which is it:
    OpenAI {"role","content"}(+ "tool_calls", {"role":"tool","tool_call_id"})
    / LangChain {"type":"human|ai|system|tool","content",...}
    / "constructor" envelope {"type":"constructor","id":[...],"kwargs":{...}}
R7. How is a system prompt supplied — a system-role message in the list, or a
    separate field/key?

=== RESPONSE (/invoke result) ===
S1. Top-level keys (output / metadata / callback_events / other)?
S2. Is `output` a serialized message object, a plain string, or a dict wrapping
    a message? Give the key path to the message.
S3. Serialization form: flat (`.model_dump()`, fields at top level) or
    "constructor" envelope (fields nested under `kwargs`)?
S4. Where do tool calls appear, and the EXACT item shape? e.g.
    top-level `tool_calls: [{"name","args","id"}]`  OR
    `additional_kwargs.tool_calls: [{"id","function":{"name","arguments"}}]`
S5. Where is the text content — a top-level `content` string, or a list of typed
    blocks [{"type":"text","text":...}]?
S6. Is token usage present, and under what key (e.g. `usage_metadata` with
    input_tokens/output_tokens)?

=== AUTH ===
A1. Exact HTTP header carrying the token and its scheme/prefix
    (e.g. `Authorization: Bearer <token>`, `X-Api-Key: <token>`, raw token).

=== MODEL ===
M1. Does the chain pin the model server-side, or accept a per-call model
    override? If override-able, give the exact key path.

=== RAW DUMPS (paste verbatim, secrets redacted) ===
- /input_schema JSON
- /output_schema JSON
- the sample /invoke request body you sent
- the sample /invoke response body you got back
