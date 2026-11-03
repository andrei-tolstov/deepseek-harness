from anyjev_server import backend, decider
from anyjev import Question

def qwen3_apply_chat_template(messages, tokenize=False, add_generation_prompt=True, **kwargs):
    parts = []
    for m in messages:
        role = m["role"]
        content = m["content"]
        parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
    if add_generation_prompt:
        parts.append("<|im_start|>assistant\n<think>\n</think>\n")
    rendered = "\n".join(parts)
    if tokenize:
        return backend.tokenizer.encode(rendered)
    return rendered

backend.tokenizer.apply_chat_template = qwen3_apply_chat_template

categories = [
    "marketplace_and_commerce", "desktop_and_computer_use", "filesystem",
    "terminal_execution", "web_and_search", "browser_automation",
    "system_and_tasks", "meta_and_skills", "multimedia_and_vision",
    "code_and_git", "devops_containers", "external_messaging", "general_utility"
]
q_td = Question.choice("Determine whether this request requires tools or chat", ["execute_tools", "direct_chat"], name="tool_decision")
q_cat = Question.choice("Which tool category best fits this request?", categories, name="category")

res = decider.decide("выведи список маркетплейсов которые тебе доступны", [q_td, q_cat])
print("\n[Marketplace query]:")
print("TD:", res["tool_decision"].answer, res["tool_decision"].confidence)
print("Cat:", res["category"].answer, res["category"].confidence)

res2 = decider.decide("бекап должен происходить в 18.00 по мск", [q_td, q_cat])
print("\n[Cron backup query]:")
print("TD:", res2["tool_decision"].answer, res2["tool_decision"].confidence)
print("Cat:", res2["category"].answer, res2["category"].confidence)
