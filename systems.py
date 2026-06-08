'''
This file is in charge of running the agent. The cli and evals will call the functions 
in this file.
'''

import re
import time
import anthropic
from config import TARGET_MODEL, TEMPERATURE, ANTHROPIC_API_KEY, MAX_FETCHED_PAGES, MAX_TOOL_CALLS
from tool.wikipedia_tool import get_wikipedia_tool_definition, execute_wikipedia_search

client = anthropic.Anthropic(api_key = ANTHROPIC_API_KEY)


def strip_reasoning(text: str) -> str:
    return re.sub(r'###Reasoning###.*?###End of Reasoning###', '', text, flags=re.DOTALL).strip()

def run_agent(user_input: str, prompt: str, use_tools: bool = True):
    tools = [get_wikipedia_tool_definition()] if use_tools else []
    messages = [{"role": "user", "content": user_input}]

    start = time.perf_counter()
    total_input_tokens = 0
    total_output_tokens = 0

    kwargs = dict(
        model=TARGET_MODEL,
        max_tokens=1000,
        system=prompt,
        temperature=TEMPERATURE,
        messages=messages,
    )
    if tools:
        kwargs["tools"] = tools

    response = client.messages.create(**kwargs)
    total_input_tokens += response.usage.input_tokens
    total_output_tokens += response.usage.output_tokens

    tool_call_count = 0
    if use_tools:
        for _ in range(MAX_TOOL_CALLS):
            if response.stop_reason != "tool_use":
                break

            tool_calls = [block for block in response.content if block.type == "tool_use"]

            tool_results = []
            for tool_call in tool_calls:
                query = tool_call.input["query"]
                print("Searching Wikipedia for {query}".format(query=query))
                tool_result = execute_wikipedia_search(query)
                #print(tool_result, "Debug tool resut")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": tool_result,
                })


            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            response = client.messages.create(
                model=TARGET_MODEL,
                max_tokens=1000,
                system=prompt,
                temperature=TEMPERATURE,
                messages=messages,
                tools=tools,
            )
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens
            tool_call_count += len(tool_calls)

    return {
        "response": response,
        "latency_s": round(time.perf_counter() - start, 2),
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "tool_calls": tool_call_count,
    }
