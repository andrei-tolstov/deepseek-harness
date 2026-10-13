import urllib.request
import json
import sys

url = "http://127.0.0.1:20128/api/settings/compression"
api_key = "sk-cb4c532e2e182bc0-083f70-ef5e4ebe"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# 1. Fetch current settings
req_get = urllib.request.Request(url, headers=headers, method="GET")
try:
    with urllib.request.urlopen(req_get) as resp:
        current = json.loads(resp.read().decode("utf-8"))
        print("Successfully fetched current settings.")
except Exception as e:
    print(f"Error fetching current settings: {e}")
    sys.exit(1)

# 2. Prepare payload for maximum compression without quality loss
update_payload = {
    "enabled": True,
    "defaultMode": "stacked",
    "autoTriggerMode": "lite",
    "autoTriggerTokens": 0,
    "cacheMinutes": 5,
    "preserveSystemPrompt": True,
    "preserveSystemPromptMode": "always",
    "mcpDescriptionCompressionEnabled": True,
    "stackedPipeline": [
        {"engine": "rtk", "intensity": "standard"},
        {"engine": "caveman", "intensity": "full"}
    ],
    "engines": {
        "session-dedup": {"enabled": True},
        "ccr": {"enabled": True},
        "lite": {"enabled": True},
        "rtk": {"enabled": True, "level": "standard"},
        "codex-responses": {"enabled": True},
        "headroom": {"enabled": True},
        "caveman": {"enabled": True, "level": "full"},
        "aggressive": {"enabled": False},
        "llmlingua": {"enabled": False},
        "ultra": {"enabled": False},
        "relevance": {"enabled": False},
        "omniglyph": {"enabled": False}
    },
    "enginesExplicit": True,
    "rtkConfig": {
        "enabled": True,
        "intensity": "standard",
        "applyToToolResults": True,
        "applyToCodeBlocks": False,
        "applyToAssistantMessages": False,
        "enabledFilters": [],
        "disabledFilters": [],
        "maxLinesPerResult": 120,
        "maxCharsPerResult": 12000,
        "deduplicateThreshold": 3,
        "customFiltersEnabled": True,
        "trustProjectFilters": False,
        "rawOutputRetention": "never",
        "rawOutputMaxBytes": 1048576,
        "rawOutputMaxFiles": 100000,
        "rawOutputMaxAgeDays": 30,
        "enableGrouping": False,
        "groupingThreshold": 3,
        "stripCodeComments": False,
        "preserveDocstrings": True,
        "enableRenderers": False
    },
    "cavemanConfig": {
        "enabled": True,
        "compressRoles": ["user"],
        "skipRules": [],
        "minMessageLength": 50,
        "preservePatterns": [],
        "intensity": "full"
    },
    "codexResponsesConfig": {
        "enabled": True,
        "minBytes": 512,
        "maxOutputBytes": 2097152,
        "maxCandidateBytes": 524288,
        "maxLines": 160,
        "minSearchMatches": 8,
        "minLogLines": 24,
        "preserveToolNames": [
            "Read", "Glob", "Grep", "Write", "Edit", "WebSearch", "WebFetch",
            "read", "glob", "grep", "write", "edit", "web_search", "web_fetch"
        ]
    },
    "lite": {
        "compressToolResults": True
    },
    "headroom": {
        "minRows": 8
    },
    "sessionDedup": {
        "minBlockChars": 80,
        "fuzzy": False
    },
    "ccr": {
        "minChars": 600,
        "retrievalRampFactor": 2
    }
}

# 3. Send PUT request
req_put = urllib.request.Request(
    url,
    data=json.dumps(update_payload).encode("utf-8"),
    headers=headers,
    method="PUT"
)

try:
    with urllib.request.urlopen(req_put) as resp:
        print("PUT Status:", resp.status)
        result = json.loads(resp.read().decode("utf-8"))
        print("Updated settings successfully!")
        print("defaultMode:", result.get("defaultMode"))
        print("enabled:", result.get("enabled"))
        print("preserveSystemPrompt:", result.get("preserveSystemPrompt"))
        print("stackedPipeline:", result.get("stackedPipeline"))
        print("engines.rtk:", result.get("engines", {}).get("rtk"))
        print("engines.caveman:", result.get("engines", {}).get("caveman"))
except urllib.error.HTTPError as e:
    print("HTTPError:", e.code, e.read().decode("utf-8"))
except Exception as e:
    print("Error during PUT:", e)
