import { estimateContextTokens } from "/usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules/@earendil-works/pi-ai/dist/utils/estimate.js";
import { clampMaxTokensToContext } from "/usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules/@earendil-works/pi-ai/dist/api/simple-options.js";
import fs from "fs";

const logfile = "/var/lib/docker/volumes/deepseek_omniroute_data/_data/call_logs/2026-10-14/2026-10-14T17-15-42.345Z_90e8fd.json";
const log = JSON.parse(fs.readFileSync(logfile, "utf8"));
const messages = log.requestBody.messages;

console.log("Messages in log count:", messages.length);
const estimated = estimateContextTokens({ messages });
console.log("Estimated context tokens:", estimated);

const model180k = { contextWindow: 180000, maxTokens: 32768 };
const clamped180k = clampMaxTokensToContext(model180k, { messages }, 32768);
console.log("Clamped maxTokens with contextWindow=180000:", clamped180k);

const model65k = { contextWindow: 65536, maxTokens: 32768 };
const clamped65k = clampMaxTokensToContext(model65k, { messages }, 32768);
console.log("Clamped maxTokens with contextWindow=65536:", clamped65k);
