// gpt-api.js

// API key now comes from chrome.storage (set in options.html) 

export async function fetchGPTJudgment(snippet) {
  const { goal = "MCAT", apiKey = "" } =
        await chrome.storage.local.get(["goal", "apiKey"]);

  if (!apiKey) {
    console.warn("No OpenAI API key set — assuming 'No'");
    return { judgment: "No", missingKey: true };   // <-- flag it
  }
  const prompt = `
The user is focused on the goal: "${goal}".

Here is a snippet (last ${snippet.length} characters) of their recent ChatGPT conversation:

"${snippet}"

Question: Does this conversation appear to be related to the goal "${goal}"?

Answer only "Yes" or "No".
  `;

  try {
    const response = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${apiKey}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        model: "gpt-4o-mini",
        messages: [
          { role: "user", content: prompt }
        ],
        temperature: 0
      })
    });

    const data = await response.json();
    return { judgment: data.choices?.[0]?.message?.content.trim() };
  } catch (err) {
    console.error("❌ API call failed:", err);
    return { judgment: null, error: err.message };
  }

}

