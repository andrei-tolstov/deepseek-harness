import BasicCompactionEngine from "/usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-compaction-basic/lib/index.js";
import { Context } from "/usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/cordis/lib/index.js";

const ctx = new Context();
const engine = new BasicCompactionEngine(ctx, {
  headroomTokens: 4096,
  thresholdRatio: 0.95,
  retainRatio: 0.15,
  maxTokens: 32768
});
console.log("=== COMPACTION RESOLVED CONFIG ===");
console.log("headroomTokens:", engine.config.headroomTokens);
console.log("thresholdRatio:", engine.config.thresholdRatio);
console.log("retainRatio:", engine.config.retainRatio);
console.log("maxTokens:", engine.config.maxTokens);

const contextWindow = 180000;
const reservedCompletionTokens = 32768;
const messageBudgetTokens = contextWindow - reservedCompletionTokens;
const pressureBudgetTokens = messageBudgetTokens - engine.config.headroomTokens;
const thresholdTokens = Math.floor(Math.min(contextWindow * engine.config.thresholdRatio, pressureBudgetTokens));
const retainTokens = Math.floor(messageBudgetTokens * engine.config.retainRatio);

console.log("\n=== COMPACTION SPEC SIMULATION (180K) ===");
console.log("contextWindow:", contextWindow);
console.log("reservedCompletionTokens:", reservedCompletionTokens);
console.log("messageBudgetTokens:", messageBudgetTokens);
console.log("pressureBudgetTokens:", pressureBudgetTokens);
console.log("thresholdTokens:", thresholdTokens, `(${((thresholdTokens / contextWindow) * 100).toFixed(2)}%)`);
console.log("retainTokens:", retainTokens, `(${((retainTokens / contextWindow) * 100).toFixed(2)}%)`);
