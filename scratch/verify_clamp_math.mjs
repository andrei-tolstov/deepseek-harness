import { estimateContextTokens } from "/usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules/@earendil-works/pi-ai/dist/utils/estimate.js";
import { clampMaxTokensToContext } from "/usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules/@earendil-works/pi-ai/dist/api/simple-options.js";
import fs from "fs";

// Load the exact messages from session-b102c5b1
// In session, DSH builds messages for pi-ai.
// Let's inspect how many characters and estimated tokens pi-ai calculates on the actual session object!
console.log("Checking clampMaxTokensToContext formula:");
const contextTokens = 1196690;
const contextWindow = 180000;
const available = contextWindow - contextTokens - 4096;
const clamped = Math.min(32768, Math.max(1, available));
console.log(`contextWindow (${contextWindow}) - contextTokens (${contextTokens}) - 4096 = available (${available})`);
console.log(`clamped maxTokens = ${clamped}`);
