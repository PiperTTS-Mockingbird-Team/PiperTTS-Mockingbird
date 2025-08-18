// gpt-api.js

// Multi-provider GPT judgment helper

export async function fetchGPTJudgment(snippet) {
  const { goal = "MCAT" } = await chrome.storage.local.get(["goal"]);
  const { providers = [] } = await chrome.storage.sync.get("providers");

  const prompt = `
The user is focused on the goal: "${goal}".

Here is a snippet (last ${snippet.length} characters) of their recent ChatGPT conversation:

"${snippet}"

Question: Does this conversation appear to be related to the goal "${goal}"?

Answer only "Yes" or "No".
  `;

  const ordered = [...providers].sort((a,b)=>a.order-b.order);
  const noKeys = ordered.every(p=>!p.key);

  for (const p of ordered) {
    if (!p.key) continue;
    try {
      if (p.name === 'openai') {
        const response = await fetch("https://api.openai.com/v1/chat/completions", {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${p.key}`,
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            model: "gpt-4o-mini",
            messages: [ { role: "user", content: prompt } ],
            temperature: 0
          })
        });
        const data = await response.json();
        const judgment = data.choices?.[0]?.message?.content.trim();
        if (judgment) return { judgment };
      } else if (p.name === 'gemini') {
        const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key=${p.key}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] })
        });
        const data = await response.json();
        const judgment = data.candidates?.[0]?.content?.parts?.[0]?.text?.trim();
        if (judgment) return { judgment };
      }
    } catch (err) {
      console.error("❌ API call failed:", p.name, err);
    }
  }

  if (noKeys) {
    console.warn("No API key set — assuming 'No'");
    return { judgment: "No", missingKey: true };
  }

  return { judgment: null, error: "All providers failed" };
}

