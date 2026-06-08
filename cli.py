from systems import run_agent, strip_reasoning
from prompts.v3 import AGENT_PROMPT, BASELINE_PROMPT

VERSION = "v3"

def main():
    print("Welcome to Jeffrey's Wikipedia Agent!")
    print("Please type 'exit' to end the session.\n")

    while True:
        try:
            user_input = input("You: ")
            if user_input.lower() == "exit":
                break

            print("Thinking...\n")
            result = run_agent(user_input, AGENT_PROMPT)
            text = result["response"].content[0].text
            if VERSION == "v3":
                text = strip_reasoning(text)
            print("Response: {response}\n".format(response=text))
        except KeyboardInterrupt:
            break
        except Exception as e:
            print("Error {e}".format(e=e))

if __name__ == "__main__":
    main()