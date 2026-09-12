// aiService.js
// Thin wrapper around the Google Gemini API used by all AI features:
//   1. classifyAndAssessUrgency  -> auto-categorization + priority + safety-urgency check
//   2. findDuplicateComplaints   -> duplicate/similar complaint detection
//   3. generateInsightsSummary   -> AI-written analytics summary for wardens/admins
//
// Requires GEMINI_API_KEY in backend/.env - get a free key (no credit card) at
// https://aistudio.google.com/apikey
// Optional: GEMINI_MODEL (defaults to gemini-2.0-flash-lite, the most generous free tier)

const MODEL = process.env.GEMINI_MODEL || "gemini-2.0-flash-lite";
const GEMINI_API_URL = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent`;

const CATEGORIES = [
  "Electrical",
  "Plumbing",
  "Furniture",
  "Washroom",
  "WiFi",
  "Cleaning",
  "Security",
  "Other",
];

/**
 * Low-level call to the Gemini generateContent API.
 * Throws if the API key is missing or the request fails, so callers
 * can decide how to gracefully degrade (the app must never crash
 * because AI is unavailable).
 */
async function callGemini(system, userMessage, maxOutputTokens = 400) {
  if (!process.env.GEMINI_API_KEY) {
    throw new Error("GEMINI_API_KEY is not configured on the server");
  }

  const response = await fetch(`${GEMINI_API_URL}?key=${process.env.GEMINI_API_KEY}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      system_instruction: { parts: [{ text: system }] },
      contents: [{ parts: [{ text: userMessage }] }],
      generationConfig: {
        maxOutputTokens,
        responseMimeType: "application/json", // ask Gemini to return raw JSON directly
      },
    }),
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`Gemini API error ${response.status}: ${errText}`);
  }

  const data = await response.json();
  const text = data?.candidates?.[0]?.content?.parts?.[0]?.text || "";
  return text;
}

/** Strips markdown fences (just in case) and parses JSON, returning null on failure. */
function safeParseJSON(raw) {
  if (!raw) return null;
  const cleaned = raw
    .trim()
    .replace(/^```json\s*/i, "")
    .replace(/^```\s*/i, "")
    .replace(/```$/i, "")
    .trim();

  try {
    return JSON.parse(cleaned);
  } catch {
    const objMatch = cleaned.match(/\{[\s\S]*\}/);
    const arrMatch = cleaned.match(/\[[\s\S]*\]/);
    const candidate = objMatch?.[0] || arrMatch?.[0];
    if (!candidate) return null;
    try {
      return JSON.parse(candidate);
    } catch {
      return null;
    }
  }
}

/**
 * FEATURE 1 + 3: Auto-categorization, priority prediction, and
 * safety-urgency escalation, in a single model call.
 */
export const classifyAndAssessUrgency = async (description) => {
  const system = `You are an assistant for a hostel/college dormitory complaint system.
Given a student's complaint description, classify it.

Valid categories (choose exactly one): ${CATEGORIES.join(", ")}.
Valid priorities (choose exactly one): low, medium, high.

Mark "isUrgent" true ONLY for genuine safety or health hazards - e.g. exposed/sparking
wiring, gas smell, fire risk, major flooding, structural damage, or an immediate
security threat. Do NOT mark routine issues (a slow drain, a flickering bulb, a
broken chair) as urgent.

Respond with ONLY a JSON object and nothing else:
{"category": "...", "priority": "...", "isUrgent": true or false, "reason": "one short sentence"}`;

  const raw = await callGemini(system, description, 250);
  const parsed = safeParseJSON(raw);
  if (!parsed) return null;

  if (!CATEGORIES.includes(parsed.category)) parsed.category = "Other";
  if (!["low", "medium", "high"].includes(parsed.priority)) parsed.priority = "medium";
  parsed.isUrgent = Boolean(parsed.isUrgent);
  parsed.reason = parsed.reason || "";

  return parsed;
};

/**
 * FEATURE 2: Duplicate / similar complaint detection.
 * `candidates` is a small pre-filtered list (same category, still open,
 * recent) fetched from MongoDB by the controller - we never send the
 * whole complaints table to the model.
 */
export const findDuplicateComplaints = async (description, candidates) => {
  if (!candidates || candidates.length === 0) return [];

  const system = `You compare a NEW hostel complaint against a list of EXISTING open
complaints and identify which existing ones describe the SAME underlying issue
(e.g. the same broken equipment, the same outage affecting a room/block, the same
recurring problem) rather than merely the same category.

Respond with ONLY a JSON array, where each item is:
{"id": "<candidate id>", "confidence": 0-100, "reason": "short reason"}
Only include candidates you are reasonably confident (confidence >= 60) describe
the same issue. If nothing matches, respond with exactly: []`;

  const candidateList = candidates
    .map((c) => `id: ${c.id}\nroom: ${c.roomNumber}\ndescription: ${c.description}`)
    .join("\n---\n");

  const userMsg = `NEW COMPLAINT:\n${description}\n\nEXISTING OPEN COMPLAINTS:\n${candidateList}`;

  const raw = await callGemini(system, userMsg, 500);
  const parsed = safeParseJSON(raw);
  if (!Array.isArray(parsed)) return [];

  return parsed.filter((m) => m && m.id && typeof m.confidence === "number" && m.confidence >= 60);
};

/**
 * FEATURE 4: AI-generated narrative summary for the Analytics dashboard.
 * `stats` is a small pre-aggregated JSON object (counts, averages) -
 * never raw complaint text with personal data.
 *
 * Note: this one needs plain prose, not JSON, so it skips the
 * responseMimeType JSON mode by calling Gemini directly with a
 * dedicated maxOutputTokens value.
 */
export const generateInsightsSummary = async (stats) => {
  if (!process.env.GEMINI_API_KEY) {
    throw new Error("GEMINI_API_KEY is not configured on the server");
  }

  const system = `You are an operations analyst for a college hostel complaint
management system. Given aggregated statistics (JSON), write a short, plain-English
summary (4-6 sentences) for hostel wardens/admins covering: overall performance,
the most problematic category, any SLA breaches, and one concrete, actionable
recommendation. Write it like a human analyst's note, not a robotic recap of every
number. No markdown headers or bullet points, just prose.`;

  const response = await fetch(`${GEMINI_API_URL}?key=${process.env.GEMINI_API_KEY}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      system_instruction: { parts: [{ text: system }] },
      contents: [{ parts: [{ text: JSON.stringify(stats) }] }],
      generationConfig: { maxOutputTokens: 400 }, // plain text, no JSON mode here
    }),
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`Gemini API error ${response.status}: ${errText}`);
  }

  const data = await response.json();
  const text = data?.candidates?.[0]?.content?.parts?.[0]?.text || "";
  return text.trim();
};
