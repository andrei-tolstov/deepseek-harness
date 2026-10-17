import { Context } from "/usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/cordis/lib/index.js";
import LlmPiAi from "/usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-llm-pi-ai/lib/index.js";

const config = {
  providers: {
    omniroute: {
      displayName: "omniroute",
      apiKeyEnv: "OMNIROUTE_API_KEY",
      api: "openai-completions",
      baseURL: "http://192.168.50.101:20128/v1",
      models: [
        {
          id: "qwen38/qwen3.8",
          name: "Qwen 3.8 27B (Local V100 180K)",
          contextWindow: 180000,
          maxTokens: 32768,
          input: ["text", "image"]
        }
      ]
    }
  }
};

const ctx = new Context();
const plugin = new LlmPiAi(ctx, config);

const snapshot = plugin.current();
const model = plugin.modelOf(snapshot, "omniroute", "qwen38/qwen3.8");

console.log("Resolved modelOf in plugin:");
console.log({
  id: model?.id,
  name: model?.name,
  contextWindow: model?.contextWindow,
  maxTokens: model?.maxTokens,
  api: model?.api,
  baseUrl: model?.baseUrl
});
