import * as piAi from "/usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules/@earendil-works/pi-ai/dist/index.js";
console.log("piAi exports:", Object.keys(piAi));
if (piAi.getBuiltinModels) {
    const bm = piAi.getBuiltinModels();
    console.log("Builtin models count:", bm.length);
}
